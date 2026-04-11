import socket, time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 506))

count = 0
first = None
last = None

print("waiting for packets...")
while True:
    data, addr = sock.recvfrom(4096)
    if first is None:
        first = time.time()
        print("first packet received")
    last = time.time()
    count += 1
    if count % 100 == 0:
        elapsed = last - first
        print(f"{count} packets in {elapsed:.2f}s — {count*len(data)/elapsed:.0f} bytes/sec received")