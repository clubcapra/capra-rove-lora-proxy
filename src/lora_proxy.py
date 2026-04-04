"""
lora_proxy.py

Transparent UDP proxy over LoRa.

Multiplexes multiple UDP port conversations over the single LoRa RF link.
Apps send to the proxy on port X — arrives on port X on the other side.
Source port is not preserved (not needed for fire-and-forget patterns).

Wire format:
  [dest_port: 2B big-endian][payload: up to 238B]
  total max: 240B (LoRa hardware buffer limit)

Reserved dest_port values:
  0 — internal ping, never routed to apps
  1 — internal pong, never routed to apps

Ping/pong:
  Send "marco" to proxy:7000. Proxy pings other proxy over LoRa.
  Replies "polo" to requester, or "timeout 10s" if no reply within 10s.
  Works both ways.

Usage:
  python3 lora_proxy.py --config config_station.yaml [--verbose]
"""

import socket
import struct
import threading
import logging
import time
import yaml
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("lora_proxy")

MAX_PAYLOAD = 238
HEADER_FORMAT = ">H"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 2 bytes

DEST_PORT_PING = 0
DEST_PORT_PONG = 1
PING_PORT = 7000
PING_TIMEOUT = 10.0

VERBOSE = False


def pack_wire(dest_port: int, payload: bytes) -> bytes:
    return struct.pack(HEADER_FORMAT, dest_port) + payload


def unpack_wire(data: bytes):
    if len(data) < HEADER_SIZE:
        return None
    dest_port = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])[0]
    payload = data[HEADER_SIZE:]
    return dest_port, payload


class LoraProxy:
    def __init__(self, config_path: str):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        self._lora_ip = cfg["lora_module_ip"]
        self._lora_send_port = cfg["lora_send_port"]
        self._lora_recv_port = cfg["lora_recv_port"]
        self._ports: list[int] = cfg.get("ports") or []

        self._app_sockets: dict[int, socket.socket] = {}

        self._lora_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._lora_sock.bind(("0.0.0.0", self._lora_recv_port))
        log.info(f"LoRa socket bound to 0.0.0.0:{self._lora_recv_port}")
        log.info(f"LoRa module at {self._lora_ip}:{self._lora_send_port}")

        self._fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # pending ping: (requester_ip, requester_port, sent_at) or None
        self._pending_ping: tuple | None = None
        self._pending_ping_lock = threading.Lock()
        self._pong_event = threading.Event()

        self._ping_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._ping_sock.bind(("0.0.0.0", PING_PORT))
        log.info(f"Ping listener on :{PING_PORT} — send 'marco' to test LoRa link")

        for port in self._ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", port))
            self._app_sockets[port] = sock
            log.info(f"  intercepting outbound on :{port}")

        if not self._ports:
            log.info("  no outbound ports configured (receive-only mode)")

    def start(self):
        for port, sock in self._app_sockets.items():
            threading.Thread(
                target=self._app_rx_loop,
                args=(port, sock),
                daemon=True,
                name=f"app-rx-{port}"
            ).start()

        threading.Thread(target=self._lora_rx_loop, daemon=True, name="lora-rx").start()
        threading.Thread(target=self._ping_rx_loop, daemon=True, name="ping-rx").start()

        log.info("Proxy running. Ctrl+C to stop.")
        threading.Event().wait()

    def _app_rx_loop(self, port: int, sock: socket.socket):
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except Exception as e:
                log.warning(f"[app->lora] recv error on :{port}: {e}")
                continue

            if len(data) > MAX_PAYLOAD:
                log.warning(
                    f"[app->lora] packet from {addr[0]}:{addr[1]} "
                    f"too large ({len(data)}B > {MAX_PAYLOAD}B), dropped"
                )
                continue

            wire = pack_wire(port, data)
            try:
                self._lora_sock.sendto(wire, (self._lora_ip, self._lora_send_port))
                if VERBOSE:
                    log.info(
                        f"[app->lora] {len(data)}B from {addr[0]}:{addr[1]} "
                        f"on :{port} -> LoRa (dest_port={port})"
                    )
            except Exception as e:
                log.warning(f"[app->lora] send to LoRa failed: {e}")

    def _ping_rx_loop(self):
        while True:
            try:
                data, addr = self._ping_sock.recvfrom(4096)
            except Exception as e:
                log.warning(f"[ping] recv error: {e}")
                continue

            if data.strip().lower() != b"marco":
                log.warning(f"[ping] unexpected message from {addr}: {data!r}, ignored")
                continue

            log.info(f"[ping] marco from {addr[0]}:{addr[1]} — pinging other proxy")

            with self._pending_ping_lock:
                self._pending_ping = (addr[0], addr[1], time.monotonic())
                self._pong_event.clear()

            wire = pack_wire(DEST_PORT_PING, b"ping")
            try:
                self._lora_sock.sendto(wire, (self._lora_ip, self._lora_send_port))
            except Exception as e:
                log.warning(f"[ping] failed to send ping over LoRa: {e}")
                with self._pending_ping_lock:
                    self._pending_ping = None
                self._fwd_sock.sendto(b"error: lora send failed", addr)
                continue

            threading.Thread(
                target=self._await_pong,
                args=(addr,),
                daemon=True,
                name="await-pong"
            ).start()

    def _await_pong(self, requester: tuple):
        received = self._pong_event.wait(timeout=PING_TIMEOUT)

        if received:
            # _lora_rx_loop already sent the reply
            return

        # timed out
        with self._pending_ping_lock:
            self._pending_ping = None

        log.warning(f"[ping] timeout — replying to {requester}")
        self._fwd_sock.sendto(f"timeout {int(PING_TIMEOUT)}s".encode(), requester)

    def _lora_rx_loop(self):
        while True:
            try:
                data, addr = self._lora_sock.recvfrom(4096)
            except Exception as e:
                log.warning(f"[lora->app] recv error: {e}")
                continue

            result = unpack_wire(data)
            if result is None:
                log.warning(
                    f"[lora->app] malformed packet from {addr[0]}:{addr[1]}, dropped"
                )
                continue

            dest_port, payload = result

            # internal ping — reply with pong
            if dest_port == DEST_PORT_PING:
                log.info("[ping] received ping from other proxy — sending pong")
                wire = pack_wire(DEST_PORT_PONG, b"pong")
                try:
                    self._lora_sock.sendto(wire, (self._lora_ip, self._lora_send_port))
                except Exception as e:
                    log.warning(f"[ping] failed to send pong: {e}")
                continue

            # internal pong — unblock _await_pong and reply to requester
            if dest_port == DEST_PORT_PONG:
                with self._pending_ping_lock:
                    if self._pending_ping is None:
                        log.warning("[ping] unexpected pong, ignored")
                        continue
                    requester_ip, requester_port, sent_at = self._pending_ping
                    self._pending_ping = None

                elapsed = time.monotonic() - sent_at
                log.info(f"[ping] pong received in {elapsed:.2f}s — replying polo")
                self._fwd_sock.sendto(b"polo", (requester_ip, requester_port))
                self._pong_event.set()
                continue

            # normal packet — deliver to local app
            try:
                self._fwd_sock.sendto(payload, ("127.0.0.1", dest_port))
                if VERBOSE:
                    log.info(
                        f"[lora->app] {len(payload)}B from {addr[0]}:{addr[1]} "
                        f"-> localhost:{dest_port}"
                    )
            except Exception as e:
                log.warning(f"[lora->app] forward to :{dest_port} failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="LoRa transparent UDP proxy")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--verbose", action="store_true", help="Log every packet")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    if VERBOSE:
        log.info("Verbose packet logging enabled")

    proxy = LoraProxy(args.config)
    try:
        proxy.start()
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()