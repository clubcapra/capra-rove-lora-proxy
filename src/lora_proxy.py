"""
lora_proxy.py

Transparent UDP proxy over LoRa.

Multiplexes multiple UDP port conversations over the single LoRa RF link.
Apps send to the proxy on port X — arrives on port X on the other side.
Source port is not preserved (not needed for fire-and-forget patterns).

Wire format:
  [dest_port: 2B big-endian][payload: up to 238B]
  total max: 240B (LoRa hardware buffer limit)

Usage:
  python3 lora_proxy.py --config config_station.yaml
  python3 lora_proxy.py --config config_rove.yaml

  Add --verbose to log every packet (useful for debugging, noisy in production).
"""

import socket
import struct
import threading
import logging
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

# Set to True via --verbose flag to log every packet
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

        # port -> socket bound to that port (listens for outbound app traffic)
        self._app_sockets: dict[int, socket.socket] = {}

        # single socket for LoRa communication
        self._lora_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._lora_sock.bind(("0.0.0.0", self._lora_recv_port))
        log.info(f"LoRa socket bound to 0.0.0.0:{self._lora_recv_port}")
        log.info(f"LoRa module at {self._lora_ip}:{self._lora_send_port}")

        # unbound socket used only to forward inbound payloads to local apps
        self._fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

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

        threading.Thread(
            target=self._lora_rx_loop,
            daemon=True,
            name="lora-rx"
        ).start()

        log.info("Proxy running. Ctrl+C to stop.")
        threading.Event().wait()

    def _app_rx_loop(self, port: int, sock: socket.socket):
        """App sends to proxy:port — wrap and forward to LoRa."""
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

    def _lora_rx_loop(self):
        """LoRa sends packet — unwrap and deliver to local app on dest_port."""
        while True:
            try:
                data, addr = self._lora_sock.recvfrom(4096)
            except Exception as e:
                log.warning(f"[lora->app] recv error: {e}")
                continue

            result = unpack_wire(data)
            if result is None:
                log.warning(
                    f"[lora->app] malformed packet from {addr[0]}:{addr[1]} "
                    f"({len(data)}B), dropped"
                )
                continue

            dest_port, payload = result
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