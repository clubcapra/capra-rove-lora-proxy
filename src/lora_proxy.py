"""
lora_proxy.py

Transparent UDP proxy over LoRa.

Each side exposes local UDP ports that mirror endpoints on the other side.
The proxy multiplexes all traffic through the single LoRa RF link by
prepending a 2-byte destination port header to every payload.

Wire format (LoRa payload):
  [dest_port: 2B big-endian][original payload: up to 238B]
  total max: 240B (LoRa hardware buffer limit)

Usage:
  python3 lora_proxy.py --config config_station.yaml
  python3 lora_proxy.py --config config_rove.yaml
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

MAX_PAYLOAD = 238   # 240 byte LoRa limit minus 2 byte port header
HEADER_SIZE = 2     # dest_port: uint16 big-endian


def pack_wire(dest_port: int, payload: bytes) -> bytes:
    """Prepend 2-byte destination port to payload."""
    return struct.pack(">H", dest_port) + payload


def unpack_wire(data: bytes):
    """
    Extract (dest_port, payload) from wire bytes.
    Returns None if data is too short.
    """
    if len(data) < HEADER_SIZE:
        return None
    dest_port = struct.unpack(">H", data[:HEADER_SIZE])[0]
    payload = data[HEADER_SIZE:]
    return dest_port, payload


class LoraProxy:
    def __init__(self, config_path: str):
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        self._lora_ip = cfg["lora_module_ip"]
        self._lora_send_port = cfg["lora_send_port"]   # module's local port
        self._lora_recv_port = cfg["lora_recv_port"]   # our local port to receive from module

        # port mappings:
        # expose_ports: list of {local_port, remote_port}
        # local_port  = port we expose on this machine
        # remote_port = port to hit on the other side
        self._expose = cfg.get("expose_ports", [])

        # local_port -> socket (one socket per exposed port)
        self._app_sockets: dict[int, socket.socket] = {}

        # remote_port -> local_port reverse map (for routing inbound LoRa traffic)
        self._remote_to_local: dict[int, int] = {}

        # Single socket that talks to the LoRa module
        self._lora_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._lora_sock.bind(("0.0.0.0", self._lora_recv_port))
        log.info(f"LoRa socket bound to 0.0.0.0:{self._lora_recv_port}")
        log.info(f"LoRa module at {self._lora_ip}:{self._lora_send_port}")

        # One socket per exposed local port
        for mapping in self._expose:
            local_port = mapping["local_port"]
            remote_port = mapping["remote_port"]

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", local_port))
            self._app_sockets[local_port] = sock
            self._remote_to_local[remote_port] = local_port

            log.info(f"Exposed :{local_port} -> remote:{remote_port}")

    def start(self):
        # One thread per app-facing socket (inbound from local apps -> out to LoRa)
        for local_port, sock in self._app_sockets.items():
            t = threading.Thread(
                target=self._app_rx_loop,
                args=(local_port, sock),
                daemon=True,
                name=f"app-rx-{local_port}"
            )
            t.start()

        # One thread for inbound LoRa traffic -> forward to local apps
        t = threading.Thread(
            target=self._lora_rx_loop,
            daemon=True,
            name="lora-rx"
        )
        t.start()

        log.info("Proxy running. Ctrl+C to stop.")
        threading.Event().wait()  # block main thread forever

    def _app_rx_loop(self, local_port: int, sock: socket.socket):
        """
        Receive UDP from a local app on local_port.
        Find the corresponding remote_port, wrap with header, send to LoRa module.
        """
        # find remote_port for this local_port
        remote_port = None
        for mapping in self._expose:
            if mapping["local_port"] == local_port:
                remote_port = mapping["remote_port"]
                break

        log.info(f"[app-rx-{local_port}] listening")

        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except Exception as e:
                log.warning(f"[app-rx-{local_port}] recv error: {e}")
                continue

            if len(data) > MAX_PAYLOAD:
                log.warning(
                    f"[app-rx-{local_port}] packet too large ({len(data)}B > {MAX_PAYLOAD}B), dropped"
                )
                continue

            wire = pack_wire(remote_port, data)
            try:
                self._lora_sock.sendto(wire, (self._lora_ip, self._lora_send_port))
                log.debug(f"[app-rx-{local_port}] {len(data)}B -> LoRa (dest_port={remote_port})")
            except Exception as e:
                log.warning(f"[app-rx-{local_port}] send to LoRa failed: {e}")

    def _lora_rx_loop(self):
        """
        Receive UDP from the LoRa module.
        Unpack the 2-byte dest_port header, forward payload to the right local app socket.
        """
        log.info("[lora-rx] listening")

        while True:
            try:
                data, addr = self._lora_sock.recvfrom(4096)
            except Exception as e:
                log.warning(f"[lora-rx] recv error: {e}")
                continue

            result = unpack_wire(data)
            if result is None:
                log.warning(f"[lora-rx] malformed packet ({len(data)}B), dropped")
                continue

            dest_port, payload = result

            if dest_port not in self._remote_to_local:
                log.warning(f"[lora-rx] unknown dest_port={dest_port}, dropped")
                continue

            local_port = self._remote_to_local[dest_port]
            sock = self._app_sockets[local_port]

            try:
                # Forward to localhost on the destination port
                sock.sendto(payload, ("127.0.0.1", dest_port))
                log.debug(f"[lora-rx] {len(payload)}B -> localhost:{dest_port}")
            except Exception as e:
                log.warning(f"[lora-rx] forward to :{dest_port} failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="LoRa transparent UDP proxy")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    args = parser.parse_args()

    proxy = LoraProxy(args.config)
    try:
        proxy.start()
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
