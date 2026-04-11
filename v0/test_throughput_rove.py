import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 506))
print("listening...")
while True:
    data, addr = sock.recvfrom(4096)
    print(f"received {len(data)}B from {addr}: {data}")