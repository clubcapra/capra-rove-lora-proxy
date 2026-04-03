# lora_proxy

Transparent UDP tunnel over LoRa, designed to make LoRa behaviorally almost like
a direct ethernet connection (like MicroHard) from the application's perspective.

## Why this exists

The LORA-ETH module is a single-channel radio link — it has one UDP endpoint on
each side and forwards raw bytes between them. It has no concept of ports beyond
its own configured local/remote port pair.

This proxy sits between your application and the LoRa module, multiplexing
multiple UDP port conversations over that single RF link. The goal: your app
sends to `proxy_ip:6000` the same way it would send to `robot_ip:6000` over
MicroHard or a cable. The transport is swappable without touching application code.

## Wire format

Every packet crossing the LoRa link gets a 2-byte header prepended:

```
[dest_port: 2B big-endian][original payload: up to 238B]
```

- `dest_port` — where to deliver the packet on the other side
- max payload 238B enforced to respect the LoRa module's 240B hardware buffer
- packets exceeding 238B are dropped with a log warning

The LoRa hardware handles integrity — the SX1278 chip runs CRC and forward
error correction at the RF layer. What arrives at the proxy is either intact
or absent. No application-level checksumming is needed in this layer.

## Design decisions

**The proxy only binds ports it needs to intercept outbound traffic**

A port listed in `ports:` means "this machine wants to send traffic to that
port on the other side." The proxy binds that port to intercept the outbound
packets, reads the port number, and uses it as `dest_port` in the wire header.

For inbound traffic arriving from LoRa, the proxy delivers via an unbound
forwarding socket — it never binds the destination port. This means local apps
can freely listen on any port without conflicting with the proxy.

**`ports:` can be empty**

If a machine only receives and never sends, `ports:` can be left empty or
omitted entirely. The proxy still receives from LoRa and delivers locally.

**Source port is not preserved**

UDP source port spoofing requires raw sockets and root privileges. For
fire-and-forget traffic patterns (motor commands, telemetry) the source port
is irrelevant — nothing replies to the caller. Keeping it out of the design
removes an entire class of complexity.

**No retries, no acknowledgements, no timestamps**

This proxy is a pipe. Packet loss, staleness, and retry logic belong in the
application layer where the semantic meaning of each packet is known. The proxy
cannot make that distinction and should not try.

## Configuration

```yaml
lora_module_ip: 192.168.2.13   # IP of the LoRa module on this machine's LAN
lora_send_port: 505            # module's local port — proxy sends TO this
lora_recv_port: 507            # proxy binds here — module forwards RF traffic here

ports:                         # ports this machine sends outbound traffic on
  - 6000                       # proxy intercepts :6000, sets dest_port=6000 in wire
  - 6001                       # add as many as needed
```

Adding a new outbound endpoint is one line. Receive-only mode needs no ports listed.

## Running

```bash
python3 lora_proxy.py --config config_station.yaml
python3 lora_proxy.py --config config_rove.yaml

# verbose mode logs every individual packet (useful for debugging)
python3 lora_proxy.py --config config_station.yaml --verbose
```

By default only warnings and errors are logged. Use `--verbose` to see every
packet flowing through — useful during initial testing, too noisy for production.

## Setup the Services

> Do this on both the deck and the Pi.

### Steps

- 1. Set up passwordless sudo for `capra`

Add the following line at the end of `/etc/sudoers`:
```
capra ALL=(ALL:ALL) NOPASSWD: ALL
```

Edit the sudoers file safely with:
```bash
sudo visudo
```

- 2. Create the systemd service file
```bash
sudo nano /etc/systemd/system/lora_proxy.service
```

Paste the content of the `lora_proxy.service` file. 
In the `ExecStart` line, specify your config file path.

- 3. Reload and enable the service
```bash
sudo systemctl daemon-reload
sudo systemctl enable lora_proxy.service
```

- 4. Check the status
```bash
sudo systemctl status lora_proxy.service
```

## Update the Service

- 1. Update the port in the config file

Reflect the new port in the `port` section of your config file.

- 2. Restart the service
```bash
sudo systemctl restart lora_proxy.service
```

## Future additions

- **Timestamp validation** — drop stale packets at the application layer, not here
- **HMAC on specific ports** — add per-port signing in the application layer
- **Source port preservation** — requires raw sockets and root, implement only if
  request-response patterns are needed
