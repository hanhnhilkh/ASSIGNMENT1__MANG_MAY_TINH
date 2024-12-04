import requests
import json
import socket
import hashlib
import os
import threading
from threading import Thread
import math
import sys
from flask import jsonify
import argparse


lock = threading.Lock()

def create_metainfo(file_name, url, piece_size=512*1024):
    file_hash = hashlib.sha1(file_name.encode()).hexdigest()
    file_path = f"./shared_files_{peer_id}/{file_name}"
    file_size = os.path.getsize(file_path)
    piece_count = math.ceil(file_size/piece_size)
    metainfo = {
        "file_name": file_name,
        "piece_size": piece_size,
        "piece_count": piece_count,
        "tracker_url": url,
        "hash": file_hash
    }
    torrent_dic = f"./torrent"
    os.makedirs(torrent_dic, exist_ok=True)
    with open(f"{torrent_dic}/{file_name}.torrent", "w") as f:
        json.dump(metainfo, f)
    return (metainfo)

def load_files_to_share(peer_id):
    share_folder = f"./shared_files_{peer_id}/"
    os.makedirs(share_folder, exist_ok=True)
    return {f: os.path.join(share_folder, f) for f in os.listdir(share_folder)}

class Peer:
    def __init__(self, peer_id, tracker_host="localhost", tracker_port=3000, self_port = 3000):
        self.peer_id = peer_id
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.files = load_files_to_share(peer_id)  # Load files in shared folder
        self.filechunks = {}
        self.downloaded_chunks = {}
        self.port= self_port
        self.total_size = 0
   
    def register(self):
        url = f"http://{self.tracker_host}:{self.tracker_port}/register"
        metainfo = []
        self.files = load_files_to_share(self.peer_id) #refresh  self.files khi peer tao file moi
        for file_name in self.files:
            file_info = create_metainfo(file_name, f"http://{self.tracker_host}:{self.tracker_port}/")
            metainfo.append(file_info)
            print(metainfo[0]["hash"])
        
        data = {"peer_id": self.peer_id, "port": self.port, "files": metainfo}
        print(data)
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("Here is the menu\n")
            peer_list= response.json()
            print(peer_list)  
        else:
            print(f"Request failed with status code: {response.status_code}")
            print(response.text)  
        
        
    def request_chunk(self, chunk, url, file_hash, file_name, chunk_size=512*1024):
        chunk_id, peers = chunk  
        print(f"Requesting chunk {chunk_id} from peers {peers}")

        for peer_id in peers:
            try:
                peer_info = requests.get(url + str(peer_id)).json()
                print(f"Peer Info: {peer_info}")

                request_data = {"file_hash": file_hash, "chunk_id": chunk_id}
                request = json.dumps(request_data).encode('utf-8')

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((peer_info["peer"]["address"], peer_info["peer"]["port"]))
                    s.sendall(request) 

                    chunk_dir = f"./shared_files_{self.peer_id}/{file_name}/"
                    os.makedirs(chunk_dir, exist_ok=True)
                    chunk_path = os.path.join(chunk_dir, f"{chunk_id}.chunk")

                    with open(chunk_path, "wb") as f:
                        while True:
                            start= time.time()
                            data = s.recv(chunk_size)
                            self.total_size+=len(data)
                            elapse = time.time()-start
                            dowload_speed = len(data)/elapse/1024 #KB/s
                            print(f"Download speed: {dowload_speed:.2f} KB/s")
                            if not data:  
                                break
                            f.write(data)

                    print(f"Downloaded chunk {chunk_id} of {file_name} from {peer_id}")
                    self.downloaded_chunks.append(chunk_id)
                    break  
            except ConnectionError:
                print(f"Could not connect to peer {peer_id}. Trying next peer.")
            except Exception as e:
                print(f"Error requesting chunk {chunk_id} from peer {peer_id}: {e}")
    
    def download(self, file_name, chunk_size = 512*1024):
        file_hash = hashlib.sha1(file_name.encode()).hexdigest()
        url = f"http://{self.tracker_host}:{self.tracker_port}/peers?hash={file_hash}"
        print(url)
        response = requests.get(url) # Tách các chunks từ file
        chunks = response.json()
        print(f"Line 142:{chunks}")
        self.downloaded_chunks = []
        missing_chunks = []
        if file_hash not in self.filechunks:
            self.files[file_hash] = {}
            self.filechunks[file_hash] = {}
        for chunk_id, peers in chunks.get('chunks', {}).items():
            if chunk_id not in self.filechunks[file_hash]:
                missing_chunks.append((chunk_id, peers))
        print(f"Line 151:{missing_chunks}")
        url = f"http://{self.tracker_host}:{self.tracker_port}/peerinfo/"
        threads = [Thread(target=self.request_chunk, args=(chunk, url, file_hash, file_name, chunk_size)) for chunk in missing_chunks]
        [t.start() for t in threads] # Bắt đầu các threads
        [t.join() for t in threads] # Chờ các threads chạy xong
        
        elapse = time.time()-start
        dowload_speed = len(self.total_size)/elapse/1024 #KB/s
        print(f"Average speed: {dowload_speed:.2f} KB/s")
        self.total_size = 0

        missing_chunk_ids = [chunk[0] for chunk in missing_chunks]
        # Compare downloaded chunks with missing chunk IDs
        if sorted(self.downloaded_chunks) == sorted(missing_chunk_ids):
            chunk_dir = f"./shared_files_{peer_id}/{file_name}/"
            output_file = os.path.join(chunk_dir, file_name)  # Define the output file path

            with open(output_file, 'w') as outfile:
                # Loop through all valid files in the directory
                for filename in sorted(
                    [f for f in os.listdir(chunk_dir) if f.split('.')[0].isdigit()],
                    key=lambda x: int(x.split('.')[0])
                ):
                    file_path = os.path.join(chunk_dir, filename)
                    # Check if it's a file
                    if os.path.isfile(file_path):
                        with open(file_path, 'r') as infile:
                            # Write contents to the output file
                            outfile.write(infile.read())

            print(f"Files merged into {output_file}")
        else:
            print("Not all chunks have been downloaded yet.")

    def start_peer_server(self, host="localhost", port=0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((host, port))
            self.port = server_socket.getsockname()[1]
            server_socket.listen(5)
            print(f"Peer {self.peer_id} running on {host}:{self.port}")

            while True:
                conn, addr = server_socket.accept()
                print(f"Connection from {addr}")
                threading.Thread(target=self.handle_peer_connection, args=(conn,)).start()

    def handle_peer_connection(self, conn):
        with conn:
            try:
                # Nhận yêu cầu tải file từ peer khác
                request_data = json.loads(conn.recv(1024).decode('utf-8'))
                file_hash = request_data.get("file_hash")
                chunk_id = request_data.get("chunk_id")
                self.files = load_files_to_share(self.peer_id)

                # Kiểm tra file hash tồn tại
                filename = None
                for file_name in self.files:
                    if (hashlib.sha1(file_name.encode()).hexdigest()== file_hash) :
                        filename= file_name

                if filename is not None:
                    file_path = self.files[filename]
                    if chunk_id is not None:
                        # Gửi chunk
                        self.send_chunk(conn, file_path, chunk_id)
                else:
                    conn.sendall(b"ERROR: File not found")
            except Exception as e:
                print(f"Error handling connection: {e}")

    def send_chunk(self, conn, file_path, chunk_id, chunk_size=512*1024):
        try:
            chunk_id = int(chunk_id)
            with open(file_path, "rb") as f: #need to print upload_speed
                f.seek(chunk_id * chunk_size)
                chunk = f.read(chunk_size)
                conn.sendall(chunk)
                print(f"Sent chunk {chunk_id} from {file_path}")
        except Exception as e:
            print(f"Error sending chunk: {e}")

    def get_command(self):
        '''print("REGISTER")###############
        cmd = input("Input command: ")'''
        
        cmd = input("Input command (REGISTER, DOWNLOAD, EXIT): ").strip().upper()
        if cmd == "REGISTER":
            # file_name = input("Enter file name to register: ").strip()
            self.register()
        elif cmd == "DOWNLOAD":
            file_name = input("Enter file name: ").strip()
            self.download(file_name)
        elif cmd == "EXIT":
            print("Exiting...")
            sys.exit(0)
    
    
def get_host_default_interface_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
       s.connect(('8.8.8.8',1))
       ip = s.getsockname()[0]
    except Exception:
       ip = '127.0.0.1'
    finally:
       s.close()
    return ip



if __name__ == "__main__":
    # Sử dụng argparse để định nghĩa các đối số
    parser = argparse.ArgumentParser(description="Peer-to-Peer File Sharing System")
    
    parser.add_argument(
        "--peer-id",
        required=True,
        type=str,
        help="Unique identifier for the peer (e.g., peer1, peer2)."
    )
    parser.add_argument(
        "--tracker-host",
        required=True,
        type=str,
        help="Hostname or IP address of the tracker."
    )
    parser.add_argument(
        "--tracker-port",
        required=True,
        type=int,
        help="Port number of the tracker."
    )
    parser.add_argument(
        "--peer-port",
        required=True,
        type=int,
        help="Port number for the peer's server to listen on."
    )

    args = parser.parse_args()

    peer_id = args.peer_id
    tracker_host = args.tracker_host
    tracker_port = args.tracker_port
    peer_port = args.peer_port

    peer = Peer(peer_id, tracker_host, tracker_port, peer_port)
    peer.register()
    hostip = get_host_default_interface_ip()
    threading.Thread(target=peer.start_peer_server, args=(hostip, peer.port)).start()
    while (1):
        peer.get_command()