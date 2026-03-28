import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('0.0.0.0', 506))  # bind to local port FIRST
s.sendto(b'Message sent from Rove', ('192.168.2.12', 504))
print('sent')

# now also listen for the reply
while True:
    data, addr = s.recvfrom(2048)
    print(f'received from {addr}: {data}')