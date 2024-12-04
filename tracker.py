from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

# Shared resources
peers = {}
files_metadata = {}

# Locks for thread-safe access
peers_lock = threading.Lock()
files_metadata_lock = threading.Lock()

@app.route("/")
def home():
    return "TORRENT LIKE APPLICATION"

# Register a new peer and track their files and chunks
@app.route('/register', methods=['POST'])
def register():
    thread = threading.Thread(target=handle_register, args=(request.json, request.remote_addr))
    thread.start()
    thread.join()
    registered_files = []
    with files_metadata_lock:
        for file_hash, metadata in files_metadata.items():
            file_info = {
                "file_name": metadata["file_name"],
                "file_hash": file_hash,
                "size": metadata["piece_count"] * 1024 * 512  # Giả sử mỗi mảnh là 524288 bytes (512 KB)
            }
            registered_files.append(file_info)

    return jsonify({
        "message": "Registration successful.",
        "files": registered_files
    }), 200

def handle_register(data, peer_address):
    peer_id = data['peer_id']
    peer_port = data['port']
    files = data['files']

    # Add peer info
    with peers_lock:
        peers[peer_id] = {
            "address": peer_address,
            "port": peer_port
        }
        print (f"line 50:{peers[peer_id]}")

    # Track files and chunks
    with files_metadata_lock:
        for file in files:
            file_hash = file["hash"]
            if file_hash not in files_metadata:
                files_metadata[file_hash] = {
                    "file_name": file["file_name"],
                    "piece_count": file["piece_count"],
                    "chunks": {i: [] for i in range(file["piece_count"])}
                }
            for chunk_id in range(file["piece_count"]):
                if peer_id not in files_metadata[file_hash]["chunks"][chunk_id]:
                    files_metadata[file_hash]["chunks"][chunk_id].append(peer_id)
    print(f"Peer {peer_id} registered with files: {files}")

# Retrieve list of peers owning chunks of a file
@app.route('/peers', methods=['GET'])
def get_peers():
    file_hash = request.args.get('hash')
    result = {}
    thread = threading.Thread(target=handle_get_peers, args=(file_hash, result))
    thread.start()
    thread.join()
    return jsonify(result)

def handle_get_peers(file_hash, result):
    with files_metadata_lock:
        result["chunks"] = files_metadata.get(file_hash, {}).get("chunks", {})

# Retrieve information about a specific peer
@app.route('/peerinfo/<peer_id>', methods=['GET'])
def get_peer_info(peer_id):
    with peers_lock:
        print(peers)
        peer_info = peers.get(peer_id)
        if peer_info:
            print(f"Peer {peer_id}: Address - {peer_info['address']}, Port - {peer_info['port']}")
        else:
            print(f"Peer {peer_id} không tồn tại.")
    if not peer_info:
        return jsonify({"error": "Peer not found"}), 404
    return jsonify({"peer": peer_info})

# Announce peer status
@app.route('/announce', methods=['POST'])
def announce():
    threading.Thread(target=handle_announce, args=(request.json,)).start()
    return jsonify({"message": "Announcement received"}), 202

def handle_announce(data):
    peer_id = data['peer_id']
    event = data['event']
    file_hash = data['file_hash']
    downloaded_chunks = data.get('downloaded_chunks', [])

    if event == "started":
        print(f"Peer {peer_id} started downloading {file_hash}.")
    elif event == "completed":
        print(f"Peer {peer_id} completed downloading {file_hash}.")
    elif event == "stopped":
        print(f"Peer {peer_id} stopped downloading {file_hash}.")

    # Update metadata to track downloaded chunks
    with files_metadata_lock:
        for chunk_id in downloaded_chunks:
            if chunk_id not in files_metadata[file_hash]["chunks"]:
                files_metadata[file_hash]["chunks"][chunk_id] = []
            if peer_id not in files_metadata[file_hash]["chunks"][chunk_id]:
                files_metadata[file_hash]["chunks"][chunk_id].append(peer_id)
    print(f"Updated chunks for {file_hash}: {downloaded_chunks}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, threaded=True)