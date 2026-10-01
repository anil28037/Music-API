from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import os
import time
import uuid
import subprocess
import threading

app = Flask(__name__, template_folder="templates")
CORS(app)

# =========================
# Configuration
# =========================

DOWNLOAD_FOLDER = "static"
COOKIES_FILE = "cookies.txt"

# Bot-Hosting provides SERVER_PORT.
# 5000 is only used as a local fallback.
PORT = int(os.environ.get("SERVER_PORT", 5000))

# Create download folder if it doesn't exist
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# =========================
# Delete old downloaded files
# =========================

def delete_old_files():
    try:
        for filename in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)

            if os.path.isfile(file_path):
                try:
                    age = time.time() - os.path.getmtime(file_path)

                    # Delete files older than 10 seconds
                    if age > 10:
                        os.remove(file_path)

                except OSError:
                    pass

    except OSError:
        pass


# =========================
# Home page
# =========================

@app.route("/")
def home():
    return render_template("index.html")


# =========================
# Download API
# =========================

@app.route("/download", methods=["GET"])
def download_media():

    video_url = request.args.get("url")
    media_type = request.args.get("type", "audio").lower()

    if not video_url:
        return jsonify({
            "error": "No URL provided"
        }), 400

    if media_type not in ("audio", "video"):
        return jsonify({
            "error": "Invalid type. Use audio or video."
        }), 400

    # Clean old files
    delete_old_files()

    extension = "mp3" if media_type == "audio" else "mp4"

    unique_filename = f"{uuid.uuid4().hex}.{extension}"

    output_path = os.path.join(
        DOWNLOAD_FOLDER,
        unique_filename
    )

    # =========================
    # yt-dlp command
    # =========================

    command = [
        "yt-dlp",
        "--output",
        output_path
    ]

    # Use cookies only if the file exists
    if os.path.exists(COOKIES_FILE):
        command.extend([
            "--cookies",
            COOKIES_FILE
        ])

    if media_type == "audio":

        command.extend([
            "--extract-audio",
            "--audio-format",
            "mp3"
        ])

    else:

        command.extend([
            "-f",
            "best"
        ])

    command.append(video_url)

    # =========================
    # Run downloader
    # =========================

    try:

        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )

        # Check whether file exists
        if not os.path.exists(output_path):

            return jsonify({
                "error": "Download completed but output file was not found.",
                "details": result.stdout[-2000:]
            }), 500

        file_url = (
            request.host_url.rstrip("/")
            + "/static/"
            + unique_filename
        )

        return jsonify({
            "success": True,
            "file_url": file_url,
            "message": "Download successful"
        })

    except subprocess.CalledProcessError as e:

        return jsonify({
            "success": False,
            "error": "Download failed",
            "details": (e.stderr or str(e))[-3000:]
        }), 500

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================
# Static files
# =========================

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(
        DOWNLOAD_FOLDER,
        filename
    )


# =========================
# Keep Alive
# =========================

@app.route("/keepalive", methods=["GET"])
def keep_alive():
    return jsonify({
        "status": "alive"
    }), 200


# =========================
# YouTube Channel API
# =========================

@app.route("/channel", methods=["GET"])
def get_channel():

    return jsonify({
        "channel_link": "https://m.youtube.com/mirrykal"
    })


# =========================
# Disable browser caching
# =========================

@app.after_request
def add_header(response):

    response.headers[
        "Cache-Control"
    ] = "no-store, no-cache, must-revalidate, max-age=0"

    return response


# =========================
# Main
# =========================

if __name__ == "__main__":

    print("=" * 50)
    print("Music API starting...")
    print(f"Host: 0.0.0.0")
    print(f"Port: {PORT}")
    print("=" * 50)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
