from threading import Thread
import pymongo
from pymongo import MongoClient
import os
import json

# connecting to mongo service
mongo_client = MongoClient('localhost', 27017)

# choosing a database
db = mongo_client.rmt

# https://stackoverflow.com/a/7392391
def is_binary(bytes):
    textchars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
    return bool(bytes.translate(None, textchars))

# storage
try:
    os.mkdir('storage')
except FileExistsError:
    pass

class ClientHandler(Thread):
    # constructor
    def __init__(self, cl_sock, cl_address):
        super().__init__()
        self.sock = cl_sock
        self.address = cl_address
        self.start()

    def registration_handler(self):
        username = self.get_msg()
        password = self.get_msg()
        is_premium = self.get_msg()
        same_username = db.users.find_one({"username": username})
        if (same_username == None):
            print('Registering new user')
            user = {"username": username,
                    "password": password,
                    "is_premium": is_premium,
                    "link": None,
                    'allowed_users': [],
                    'shared_with_me': [],
                    }
            self.user = user
            db.users.insert_one(user)
            os.mkdir('./storage/{}'.format(username))
            self.send_msg('registered')
        else:
            print('User already exists, retrying')
            self.send_msg('non unique')
            self.registration_handler()

    def login_handler(self):
        username = self.get_msg()
        password = self.get_msg()
        same_user = db.users.find_one({"username": username})
        if (same_user != None and same_user['username'] == username and same_user['password'] == password):
            print('Naso i salje ok')
            self.user = same_user
            self.send_msg(self.user['is_premium'])
            files = self.get_files()
            self.send_msg(json.dumps(files))
        else:
            print('ne postoji user')
            self.send_msg('not finished')
            self.login_handler()

    def run(self):
        # sign up / sing in / link access
        try:
            first_action = self.get_msg()
            if(first_action == 'register'):
                self.registration_handler()
            elif(first_action == 'login'):
                self.login_handler()
            while True:
                action = self.get_msg()
                choices = ['Upload', 'Choose file', 'Shared with me', 'Get shareable link', 'Share with user',
                           'Create folder', 'Rename folder', 'Move files', 'Delete folder']
                handlers = [self.upload_file, self.choose_file, self.list_shared_with_me, self.get_shareable_link, self.share_with_user,
                           self.create_folder, self.rename_folder, self.move_files, self.delete_folder]
                for i in range(len(choices)):
                    if (action == choices[i]):
                        handlers[i]()
        except RuntimeError:
            self.run()
        except:
            pass

    def rename_folder(self):
        pass

    def create_folder(self):
        pass

    def choose_file(self):
        file_name = self.sock.recv(4096).decode()

        path = './storage/{}/{}'.format(self.user['username'], file_name)

        # if (is_binary(open(path, 'r').read(1024).encode())):
        #     self.sock.send('y'.encode())
        # else:
        #     self.sock.send('n'.encode())

        print('Reading', path)
        with open(path, 'rb') as file:
            file_content = file.read()

        self.send_file(file_content)


    def get_files(self):
        files = []
        # r=root, d=directories, f = files
        for r, d, f in os.walk('./storage/{}'.format(self.user['username'])):
            for file in f:
                files.append(file)

        return files

    def upload_file(self):
        content = self.recv_file()
        filename = self.get_msg()

        path = './storage/{}/{}'.format(self.user['username'],filename)
        # mode = 'wb' if is_binary(content) else 'w'
        mode = 'wb'

        if self.user['is_premium']=='y' or len(self.get_files()) < 5:
            with open(path, mode) as file:
                file.write(content)
            print(mode)
            print(path)
            self.send_msg('UPLOADED')
        else:
            self.send_msg('STORAGE FULL')
            print(path)
            print(mode)



    def move_files(self):
        pass

    def list_shared_with_me(self):
        pass

    def delete_folder(self):
        pass

    def get_shareable_link(self):
        pass

    def share_with_user(self):
        pass

    def get_msg(self, response = 'OK'):
        msg = self.sock.recv(4096).decode()
        self.sock.send(response.encode())
        print('message received: {}'.format(msg))
        if (msg == 'EXIT'):
            raise RuntimeError
        return msg

    def send_msg(self, msg):

        self.sock.send(msg.encode())
        response = self.sock.recv(4096).decode()

    # https://stackoverflow.com/a/52723547
    def recv_file(self):
        # Get the expected length (eight bytes long, always)
        expected_size = b""
        while len(expected_size) < 8:
            more_size = self.sock.recv(8 - len(expected_size))
            if not more_size:
                raise Exception("Short file length received")
            expected_size += more_size

        # Convert to int, the expected file length
        expected_size = int.from_bytes(expected_size, 'big')

        # Until we've received the expected amount of data, keep receiving
        packet = b""  # Use bytes, not str, to accumulate
        while len(packet) < expected_size:
            buffer = self.sock.recv(expected_size - len(packet))
            if not buffer:
                raise Exception("Incomplete file received")
            packet += buffer
        return packet
        # with open(filename, 'wb') as f:
        #     f.write(packet)

    def send_file(self, bytes):
        print("Sending:", bytes)
        # Send actual length ahead of data, with fixed byteorder and size
        self.sock.sendall(len(bytes).to_bytes(8, 'big'))
        # You have the whole thing in memory anyway; don't bother chunking
        self.sock.sendall(bytes)
