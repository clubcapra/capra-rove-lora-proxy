# sender.py — run on station (192.168.2.201)
import socket, time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 507))

total = 1000
payload = b'x' * 100  # 100 byte payload, adjust to test different sizes
start = time.time()

for i in range(total):
    sock.sendto(payload, ('192.168.2.13', 505))
    time.sleep(1 / 1)

elapsed = time.time() - start
print(f"sent {total} packets in {elapsed:.2f}s ({total*len(payload)/elapsed:.0f} bytes/sec)")