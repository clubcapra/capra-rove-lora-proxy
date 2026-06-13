# test_proxy.py
from lora_proxy import pack_wire, unpack_wire, MAX_PAYLOAD

def test_round_trip():
    payload = b"hello"
    wire = pack_wire(6000, 6001, payload)
    dest, src, recovered = unpack_wire(wire)
    assert dest == 6000
    assert src == 6001
    assert recovered == payload

def test_malformed_too_short():
    assert unpack_wire(b"\x00") is None

def test_empty_payload():
    wire = pack_wire(6000, 6001, b"")
    dest, src, payload = unpack_wire(wire)
    assert payload == b""

def test_oversized_constant():
    # MAX_PAYLOAD enforced in proxy before pack — verify the constant is correct
    assert MAX_PAYLOAD == 236  # 240 LoRa limit - 4 byte header
