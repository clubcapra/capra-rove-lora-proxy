import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('0.0.0.0', 507))  # bind to local port FIRST
s.sendto(b'Message sent from Station', ('192.168.2.13', 505))
print('sent')

# now also listen for the reply
while True:
    data, addr = s.recvfrom(2048)
    print(f'received from {addr}: {data}')