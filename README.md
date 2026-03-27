# lora_proxy

Transparent UDP tunnel over LoRa, designed to make LoRa behaviorally identical
to a direct ethernet connection (like MicroHard) from the application's perspective.

## Why this exists

The LORA-ETH module is a single-channel radio link — it has one UDP endpoint on
each side and forwards raw bytes between them. It has no concept of ports beyond
its own configured local/remote port pair.

This proxy sits between your application and the LoRa module, multiplexing
multiple UDP port conversations over that single RF link. The goal: your app
sends to `proxy:6000` the same way it would send to `robot:6000` over MicroHard
or a cable. The transport is swappable without touching application code.

## Wire format

Every packet crossing the LoRa link gets a 4-byte header prepended:

```
[dest_port: 2B][src_port: 2B][original payload: up to 236B]
```

- `dest_port` — where to deliver the packet on the other side
- `src_port` — the original sender's port, carried for future request-response support
- max payload 236B enforced to respect the LoRa module's 240B hardware buffer

Packets exceeding 236B are silently dropped with a log warning. The LoRa
hardware itself handles integrity — the SX1278 chip runs CRC + forward error
correction at the RF layer, so what arrives at the proxy is either intact or
absent. No application-level checksumming is needed in this layer.

## Design decisions

**One socket per exposed port, not one shared socket**

Each exposed port gets its own bound socket. This means the OS handles
demultiplexing inbound app traffic by port — no manual dispatch needed.
It also means binding is explicit and startup fails loudly if a port is
already in use, rather than silently misrouting traffic.

**Source port is carried but not spoofed**

Python's socket API cannot spoof UDP source port without raw sockets (requires
root). The proxy carries `src_port` in the wire header for future use — if you
ever need true source transparency, you have the information available without
a wire format change. For now, the receiving app sees the proxy's bound port
as source, which is fine for fire-and-forget traffic patterns.

**Opt-in port exposure**

Only ports listed in `expose_ports` are proxied. If a remote endpoint replies
to a source port that is not listed, that reply is not routed — intentionally.
This gives you explicit control over which reply paths are active without any
additional filtering logic.

**No retries, no acknowledgements, no timestamps**

This proxy is a pipe. Packet loss, staleness, and retry logic belong in the
application layer where the semantic meaning of each packet is known. A stale
joystick command is dangerous; a stale temperature reading is harmless. The
proxy cannot make that distinction and should not try.

**Python is fine here**

The bottleneck is the LoRa radio (max ~19200 bps, tens of ms per packet).
The proxy spends 99.9% of its time blocked on `recvfrom` (kernel I/O, not
Python). The actual Python work per packet is a 4-byte `struct.pack` and a
`sendto`. GIL contention is not a concern because threads release the GIL
during I/O waits.

## Configuration

```yaml
lora_module_ip: 192.168.2.13      # IP of the LoRa module on this machine's LAN
lora_send_port: 505               # module's local port — proxy sends TO this
lora_recv_port: 507               # proxy binds to this — module forwards RF traffic here

robot_ip: 127.0.0.1               # where to forward inbound LoRa traffic locally

expose_ports:
  - local_port: 6000              # proxy listens here for app traffic
    remote_port: 6000             # delivered to this port on the other side
  - local_port: 6001              # add as many as needed, one line per endpoint
    remote_port: 6001
```

Adding a new endpoint is one entry in the config. No code changes.

## Running

```bash
# station side
python3 lora_proxy.py --config config_station.yaml

# rove side
python3 lora_proxy.py --config config_rove.yaml
```

## Testing end-to-end with netcat

Run in this order — proxies first, then listeners, then senders.

```bash
# Terminal 1
python3 lora_proxy.py --config config_station.yaml

# Terminal 2
python3 lora_proxy.py --config config_rove.yaml

# Terminal 3 — simulates robot receiving on rove side
nc -u -l 6000

# Terminal 4 — simulates station app sending
echo "hello from station" | nc -u 127.0.0.1 6000
```

`hello from station` should appear in terminal 3.

Reverse direction (rove → station):

```bash
# Terminal 3 — simulates station app receiving
nc -u -l 6000

# Terminal 4 — simulates robot sending from rove side
echo "hello from rove" | nc -u 127.0.0.1 6000
```

## Unit tests

Tests cover the wire format functions only — no networking required.
Socket forwarding is better validated by the netcat integration test above.

```bash
pip install pytest
pytest test_proxy.py -v
```


## Future additions

- **Timestamp validation** — add an 8-byte timestamp to the header and drop
  stale packets. Implement in the application layer rather than here unless
  you want a global staleness policy across all ports.
- **True source port spoofing** — requires raw sockets and root privileges.
  The src_port field in the wire format is already there; only the forwarding
  call needs updating.
- **HMAC on specific ports** — add an optional `hash: hmac` + `key` field per
  port in the config. The proxy checks before forwarding. Adds ~32 bytes per
  packet on signed ports only.
