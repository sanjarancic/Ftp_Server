from socket import *
from threading import *

from ClientHandler import ClientHandler

# service config
srv_address = 'localhost'
srv_port = 2222

srv_sock = socket(AF_INET, SOCK_STREAM)
srv_sock.bind((srv_address, srv_port))
srv_sock.listen(5)
print('Welcome to fake google drive :)')


while True:
    # get the client socket and client address when accepting the connection
    cl_sock, cl_address = srv_sock.accept()

    # we initialize the ClientThread class defined above
    client = ClientHandler(cl_sock, cl_address)