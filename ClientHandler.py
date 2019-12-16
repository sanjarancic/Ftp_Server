from threading import Thread
import pymongo
from pymongo import MongoClient
from bson import json_util
import os
import json
import uuid

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
        self.selected_username = None

    def reset_selected_user(self):
        self.selected_username = None

    def registration_handler(self):
        self.reset_selected_user()
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
        self.reset_selected_user()
        username = self.get_msg()
        password = self.get_msg()
        same_user = db.users.find_one({"username": username})
        if (same_user != None and same_user['username'] == username and same_user['password'] == password):
            print('Naso i salje ok')
            self.user = same_user
            self.send_msg(self.user['is_premium'])
            # files = self.get_files()
            # self.send_msg(json.dumps(files))
        else:
            print('ne postoji user')
            self.send_msg('not finished')
            self.login_handler()

    def run(self):
        # sign up / sing in / link access
        try:
            while True:
                action = self.get_msg()
                choices = ['Upload', 'Choose file', 'Shared with me', 'Get shareable link', 'Share with user',
                           'Create folder', 'Rename folder', 'Move files', 'Delete folder', 'login', 'register',
                           'Access via link','see user\'s drive', 'Get Files']
                handlers = [self.upload_file, self.choose_file, self.list_shared_with_me, self.get_shareable_link, self.share_with_user,
                           self.create_folder, self.rename_folder, self.move_files, self.delete_folder, self.login_handler,
                            self.registration_handler, self.access_via_link, self.send_shared_drive, self.get_files_for_user_from_directory]
                for i in range(len(choices)):
                    if (action == choices[i]):
                        handlers[i]()
        except RuntimeError:
            self.run()
            #TODO manage EXIT
        except Exception as e:
            print('faaaak', e)

    def rename_folder(self):
        username = self.user['username']
        current_directory = self.get_msg()
        path_to_folder = './storage/{}{}'.format(username, current_directory)
        print('path to folder:',path_to_folder)
        old_name = self.get_msg()
        path_old = path_to_folder + old_name
        new_name = self.get_msg()
        path_new = path_to_folder + new_name
        print('path old', path_old)
        print('path new',path_new)

        files_in_current_dir = self.get_files_from_directory(path_to_folder)
        if old_name not in files_in_current_dir:
            self.send_msg('not found')
            print('old does not exist')
        else:
            if new_name not in files_in_current_dir:
                self.send_msg('found')
                os.rename(path_old,path_new)
                print('found old, no new, renamed')
            else:
                self.send_msg('exists')
                print('new exists already')


    def create_folder(self):
        try:
            username = self.user['username']
            folder_path = './storage/{}/{}'.format(username, self.sock.recv(4096).decode())
            os.mkdir(folder_path)
            self.sock.send('Successfull'.encode())
        except FileExistsError:
            self.sock.send('folder exists'.encode())

    def get_files_for_user_from_directory(self):
        username = self.user['username']
        path = './storage/{}/{}'.format(username, self.sock.recv(4096).decode())
        # same_user = db.users.find_one({"username": username})
        # self.selected_username = same_user['username']


        files = self.get_files_from_directory(path)
        self.send_msg(json.dumps(files))

    def access_via_link(self):
        link = self.sock.recv(4096).decode()
        try:
            same_user = db.users.find_one({"link": uuid.UUID(link)})
        except ValueError:
            same_user = None
        print('Accessing to user: ', same_user)
        if(same_user == None):
            self.send_msg('NOT FOUND')
        else:
            self.selected_username = same_user['username']
            self.send_msg('FOUND')
            files = self.get_files(same_user)
            self.send_msg(json.dumps(files))


    def choose_file(self):
        file_name = self.sock.recv(4096).decode()

        if self.selected_username == None:
            username = self.user['username']
        else:
            username = self.selected_username

        path = './storage/{}/{}'.format(username, file_name)

        # if we're looking at directory
        if (path[-1] == '/'):
            files = self.get_files_from_directory(path)
            self.sock.send(json.dumps(files).encode())
        else:
            print('Reading', path)
            with open(path, 'rb') as file:
                file_content = file.read()
            self.send_file(file_content)

    def get_files_from_directory(self, path):
        files = []

        for r, d, f in os.walk(path):
            for dir in d:
                files.append(dir + '/')

            for file in f:
                files.append(file)
            # get only files and directories from the root
            break

        return files

    def get_files(self, user = None):
        if (user == None):
            username = self.user['username']
        else:
            username = user['username']

        return self.get_files_from_directory('./storage/{}'.format(username))

    def upload_file(self):
        content = self.recv_file()
        self.sock.send('OK'.encode())
        filename = self.sock.recv(4096).decode()

        path = './storage/{}{}'.format(self.user['username'],filename)
        print(path)

        if self.user['is_premium']=='y' or len(self.get_files()) < 5:
            with open(path, 'wb') as file:
                file.write(content)
            self.send_msg('UPLOADED')
        else:
            self.send_msg('STORAGE FULL')



    def move_files(self):
        pass

    def send_shared_drive(self):
        username = self.sock.recv(4096).decode()
        self.selected_username = username
        same_user = db.users.find_one({"username": username})
        files = self.get_files(same_user)
        self.send_msg(json.dumps(files))

    def list_shared_with_me(self):
        myquery = {"allowed_users": self.user['username']}
        users_who_shared_with_me = [user['username'] for user in db.users.find(myquery)]
        self.sock.send(json.dumps(users_who_shared_with_me).encode())

    def delete_folder(self):
        current_directory = self.get_msg()
        folder_name = self.sock.recv(4096).decode()
        path_to = './storage/{}{}'.format(self.user['username'], current_directory)
        path = path_to + folder_name
        files_in_current_dir = self.get_files_from_directory(path_to)
        print('path to', files_in_current_dir, path_to)
        if folder_name not in files_in_current_dir:
            self.send_msg('not found')
        else:
            self.send_msg('found')
            files_in_dir = self.get_files_from_directory(path)
            print('path', files_in_dir, path)
            if not files_in_dir:
                os.rmdir(path)
                self.send_msg('deleted')
            else:
                self.send_msg('full')


        # self.('./storage/{}/{}'.format(self.user['username'], folder_name))

    def get_shareable_link(self):
        self.sock.recv(4096).decode()
        if(self.user["link"]==None):
            myquery = {"username": self.user['username']}
            newvalues = {'$set': {'link': uuid.uuid4()}}
            db.users.update_one(myquery,newvalues)
            self.user = db.users.find_one({"username": self.user['username']})
        self.send_msg(str(self.user['link']))

    def share_with_user(self):
        username = self.sock.recv(4096).decode()
        same_user = db.users.find_one({"username": username})
        if(same_user == None):
            self.sock.send("NOT FOUND".encode())
        else:
            self.sock.send("FOUND".encode())
            myquery = {"username": self.user['username']}
            # makes sure allowed users are unique
            newvalues = {'$addToSet': {'allowed_users':username}}
            db.users.update_one(myquery, newvalues)


    def get_msg(self, response = 'OK'):
        msg = self.sock.recv(4096).decode()
        self.sock.send(response.encode())
        print('message received: {}'.format(msg))
        if (msg == 'EXIT'):
            self.reset_selected_user()
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
