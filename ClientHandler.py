from threading import Thread
from pymongo import MongoClient
import os
import json
import uuid
import shutil

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
    def __init__(self, cl_sock, cl_address, users):
        super().__init__()
        self.sock = cl_sock
        self.address = cl_address
        self.start()
        self.selected_username = None
        self.user = None
        self.users = users

    def run(self):
        choices = {
            'upload': self.upload,
            'get file': self.get_file,
            'shared with me': self.shared_with_me,
            'get shareable link': self.get_shareable_link,
            'share with user': self.share_with_user,
            'create folder': self.create_folder,
            'rename folder': self.rename_folder,
            'move files': self.move_files,
            'delete folder': self.delete_folder,
            'login': self.login,
            'register': self.register,
            'access via link': self.access_via_link,
            'get files': self.get_files,
            'logout': self.logout,
            'select user': self.select_user,
            'reset selected user': self.reset_selected_user,
        }

        try:
            while True:
                action = self.get_msg(True)

                if action not in choices:
                    self.send_msg('BAD REQUEST')
                else:
                    choices[action]()
        except:
            pass

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

    def send_file(self, bytes):
        print("Sending:", bytes)
        # Send actual length ahead of data, with fixed byteorder and size
        self.sock.sendall(len(bytes).to_bytes(8, 'big'))
        # You have the whole thing in memory anyway; don't bother chunking
        self.sock.sendall(bytes)

    def get_msg(self, respond=False):
        message = self.sock.recv(4096).decode()
        print('Message received: ', message)

        if respond:
            print('Responding: OK')
            self.sock.send('OK'.encode())

        return message

    def send_msg(self, message, wait=False):
        print('Sending message: ', message)
        self.sock.send(message.encode())

        if wait:
            resp = self.sock.recv(4096)
            print('Response: ', resp)

    def select_user(self):
        self.selected_username = self.get_msg(True)

    def reset_selected_user(self):
        self.selected_username = None

    def logout(self):
        self.selected_username = None
        self.users.remove(self.user['username'])
        self.user = None

    def share_with_user(self):
        user_to_share = self.get_msg()

        same_user = db.users.find_one({"username": user_to_share})

        if same_user == None:
            self.send_msg('User does not exist!')
        else:
            myquery = {"username": user_to_share}
            # makes sure allowed users are unique
            newvalues = {'$addToSet': {'shared_with_me': self.user['username']}}
            db.users.update_one(myquery, newvalues)
            self.send_msg('shared')

    def create_folder(self):
        current_directory = self.get_msg(True)
        folder_name = self.get_msg()

        path = './storage/{}{}{}'.format(self.user['username'], current_directory, folder_name)

        try:
            os.mkdir(path)
            self.send_msg('created')
        except FileExistsError:
            self.send_msg('Folder already exists')

    def rename_folder(self):
        current_directory = self.get_msg(True)
        old_folder = self.get_msg(True)
        new_folder = self.get_msg()

        path_to_old = './storage/{}{}{}'.format(self.user['username'], current_directory, old_folder)
        path_to_new = './storage/{}{}{}'.format(self.user['username'], current_directory, new_folder)

        if not os.path.exists(path_to_old):
            self.send_msg('Folder {} does not exist'.format(old_folder))
        elif os.path.exists(path_to_new):
            self.send_msg('{} already exists'.format(new_folder))
        elif not os.path.isdir(path_to_old):
            self.send_msg('Must be a directory')
        else:
            os.rename(path_to_old, path_to_new)
            self.send_msg('renamed')

    def move_files(self):
        from_directory = self.get_msg(True)
        file_name = self.get_msg(True)
        to_directory = self.get_msg()

        from_path = './storage/{}{}{}'.format(self.user['username'], from_directory, file_name)
        to_path = './storage/{}{}{}'.format(self.user['username'], to_directory, file_name)

        if not os.path.exists(from_path):
            self.send_msg('From path does not exist')
        else:
            shutil.move(from_path, to_path)
            self.send_msg('moved')

    def delete_folder(self):
        current_directory = self.get_msg(True)
        folder_name = self.get_msg()

        path = './storage/{}{}{}'.format(self.user['username'], current_directory, folder_name)

        if not os.path.exists(path):
            self.send_msg('Folder doesn\'t exist')
        elif not os.path.isdir(path):
            self.send_msg('Cannot delete files')
        else:
            files = self.get_files_in_directory(path)

            if len(files) is not 0:
                self.send_msg('Folder is not empty')
            else:
                os.rmdir(path)
                self.send_msg('deleted')

    def login(self):
        username = self.get_msg(True)
        password = self.get_msg()

        user = db.users.find_one({"username": username})

        if user is not None and user['password'] == password:
            if username in self.users:
                self.send_msg('You are already logged in')
            else:
                self.send_msg(user['is_premium'])
                self.user = user
                self.users.append(username)
        else:
            self.send_msg('Username or password are not valid')

    def register(self):
        username = self.get_msg(True)
        password = self.get_msg(True)
        is_premium = self.get_msg()

        same_user = db.users.find_one({'username': username})

        if same_user is not None:
            self.send_msg('User already exists')
        else:
            new_user = {
                "username": username,
                "password": password,
                "is_premium": is_premium,
                "link": None,
                'shared_with_me': [],
            }

            db.users.insert_one(new_user)
            os.mkdir('./storage/{}'.format(username))
            self.send_msg('registered')
            self.user = new_user
            self.users.append(username)

    def access_via_link(self):
        link = self.get_msg()

        try:
            same_user = db.users.find_one({"link": uuid.UUID(link)})
        except ValueError:
            same_user = None

        if same_user is None:
            self.send_msg('Not found')
        else:
            self.send_msg('ok')
            self.selected_username = same_user['username']

    def get_files(self):
        current_directory = self.get_msg()

        username = self.selected_username or self.user['username']

        path = './storage/{}{}'.format(username, current_directory)

        files = self.get_files_in_directory(path)

        self.send_msg(json.dumps(files))

    def get_files_in_directory(self, path):
        files = []

        # r=root d- directory f-file
        for r, d, f in os.walk(path):
            for dir in d:
                files.append(dir + '/')

            for file in f:
                files.append(file)

            # get only files and directories from the root
            break

        return files

    def upload(self):
        current_directory = self.get_msg(True)
        file_name = self.get_msg(True)
        file_content = self.recv_file()

        path = './storage/{}{}'.format(self.user['username'], current_directory + file_name)

        user_files = self.get_files_in_directory('./storage/{}'.format(self.user['username']))

        if self.user['is_premium']=='y' or len(user_files) < 5:
            with open(path, 'wb') as file:
                file.write(file_content)
            self.send_msg('uploaded')
        else:
            self.send_msg('storage full')

    def get_file(self):
        username = self.selected_username or self.user['username']
        path = './storage/{}{}'.format(username, self.get_msg())

        if os.path.exists(path):
            self.send_msg('OK', True)
            with open(path, 'rb') as file:
                file_content = file.read()
            self.send_file(file_content)
        else:
            self.send_msg('File does not exist')

    def shared_with_me(self):
        self.get_msg()

        myquery = {"username": self.user['username']}
        self.user = db.users.find_one(myquery)
        self.send_msg(json.dumps(self.user['shared_with_me']))

    def get_shareable_link(self):
        self.get_msg()
        
        if self.user["link"] == None:
            myquery = {"username": self.user['username']}
            newvalues = {'$set': {'link': uuid.uuid4()}}
            db.users.update_one(myquery, newvalues)
            self.user = db.users.find_one({"username": self.user['username']})
        self.send_msg(str(self.user['link']))

