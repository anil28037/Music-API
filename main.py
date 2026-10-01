from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import os
import time
import uuid
import subprocess
import threading

app = Flask(__name__, template_folder="templates")
CORS(app)

DOWNLOAD_FOLDER = "static"
COOKIES_FILE = "cookies.txt"  # Make sure you have cookies.txt

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Function to delete old files (older than 10 sec)
def delete_old_files():
    for file in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, file)
        if os.path.isfile(file_path) and time.time() - os.path.getctime(file_path) > 10:
            os.remove(file_path)

@app.route('/')
def home():
    return render_template("index.html")  # Show HTML page on homepage

@app.route('/download', methods=['GET'])
def download_media():
    video_url = request.args.get("url")
    media_type = request.args.get("type", "audio")  # Default: Audio

    if not video_url:
        return jsonify({"error": "No URL provided"}), 400

    delete_old_files()  # Clean old files

    unique_filename = f"{uuid.uuid4().hex}.{'mp3' if media_type == 'audio' else 'mp4'}"
    output_path = os.path.join(DOWNLOAD_FOLDER, unique_filename)

    # YouTube download command
    command = [
        "yt-dlp",
        "--output", output_path,
        "--cookies", COOKIES_FILE,
        video_url
    ]

    if media_type == "audio":
        command.extend(["--extract-audio", "--audio-format", "mp3"])
    else:
        command.extend(["-f", "best"])  # Best video quality available

    try:
        subprocess.run(command, check=True)
        file_url = request.host_url.rstrip('/') + f"/static/{unique_filename}"
        return jsonify({"file_url": file_url, "message": "Download successful"})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

# Static file serving
@app.route('/static/<filename>')
def serve_static(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

# Keep Alive Route
@app.route('/keepalive', methods=['GET'])
def keep_alive():
    return "Server is alive!", 200

# YouTube Channel API
@app.route('/channel', methods=['GET'])
def get_channel():
    return jsonify({"channel_link": "https://m.youtube.com/mirrykal"})

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

# Keep Alive Thread
def run_keep_alive():
    while True:
        time.sleep(600)  # Ping every 10 minutes
        try:
            subprocess.run(["curl", "https://mirrykal.onrender.com/keepalive"], check=True)
        except:
            pass

# Start Keep Alive in a separate thread
threading.Thread(target=run_keep_alive, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
