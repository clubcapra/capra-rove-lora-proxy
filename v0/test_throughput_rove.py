import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 506))
print("listening...")

count = 0
first = None

while True:
    data, addr = sock.recvfrom(4096)
    now = time.time()
    if first is None:
        first = now
    count += 1
    elapsed = now - first
    print(f"[{elapsed:8.3f}s] #{count:04d} {len(data)}B from {addr[0]}:{addr[1]}") # | {data[:40]}