from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import os
import time
import uuid
import subprocess
import threading
import sys

app = Flask(__name__, template_folder="templates")
CORS(app)

# =========================================================
# CONFIG
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "static")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")

# Files कितनी देर बाद delete हों
FILE_MAX_AGE = 10 * 60  # 10 minutes

# Download timeout
DOWNLOAD_TIMEOUT = 300  # 5 minutes


# =========================================================
# CREATE DOWNLOAD FOLDER
# =========================================================

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# =========================================================
# DELETE OLD FILES
# =========================================================

def delete_old_files():
    try:
        now = time.time()

        for filename in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)

            if not os.path.isfile(file_path):
                continue

            try:
                age = now - os.path.getmtime(file_path)

                if age > FILE_MAX_AGE:
                    os.remove(file_path)
                    print(f"Deleted old file: {filename}")

            except Exception as e:
                print(f"Could not delete {filename}: {e}")

    except Exception as e:
        print(f"Cleanup error: {e}")


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# DOWNLOAD
# =========================================================

@app.route("/download", methods=["GET"])
def download_media():

    video_url = request.args.get("url", "").strip()
    media_type = request.args.get("type", "audio").lower().strip()

    # -----------------------------------------------------
    # Check URL
    # -----------------------------------------------------

    if not video_url:
        return jsonify({
            "success": False,
            "error": "No URL provided"
        }), 400

    # केवल audio/video
    if media_type not in ["audio", "video"]:
        media_type = "audio"

    # -----------------------------------------------------
    # Cleanup old files
    # -----------------------------------------------------

    delete_old_files()

    # -----------------------------------------------------
    # Unique filename
    # -----------------------------------------------------

    unique_id = uuid.uuid4().hex

    # yt-dlp खुद final extension लगाएगा
    output_template = os.path.join(
        DOWNLOAD_FOLDER,
        f"{unique_id}.%(ext)s"
    )

    # -----------------------------------------------------
    # Use yt-dlp through current Python
    # -----------------------------------------------------

    command = [
        sys.executable,
        "-m",
        "yt_dlp",

        "--no-playlist",

        "-o",
        output_template,
    ]

    # -----------------------------------------------------
    # Cookies
    # -----------------------------------------------------

    if os.path.isfile(COOKIES_FILE):
        command.extend([
            "--cookies",
            COOKIES_FILE
        ])
        print("Using cookies.txt")
    else:
        print("cookies.txt not found. Continuing without cookies.")

    # -----------------------------------------------------
    # AUDIO
    # -----------------------------------------------------

    if media_type == "audio":

        command.extend([
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "192K"
        ])

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    else:

        command.extend([
            "-f",
            "bestvideo+bestaudio/best",
            "--merge-output-format",
            "mp4"
        ])

    # URL सबसे आखिर में
    command.append(video_url)

    print("=" * 60)
    print("Starting download")
    print("URL:", video_url)
    print("TYPE:", media_type)
    print("COMMAND:", " ".join(command))
    print("=" * 60)

    # -----------------------------------------------------
    # RUN YT-DLP
    # -----------------------------------------------------

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT
        )

        print("yt-dlp return code:", result.returncode)

        if result.stdout:
            print("yt-dlp stdout:")
            print(result.stdout)

        if result.stderr:
            print("yt-dlp stderr:")
            print(result.stderr)

        # -------------------------------------------------
        # yt-dlp failed
        # -------------------------------------------------

        if result.returncode != 0:

            return jsonify({
                "success": False,
                "error": "yt-dlp download failed",
                "return_code": result.returncode,
                "details": result.stderr[-4000:] if result.stderr else "Unknown error"
            }), 500

        # -------------------------------------------------
        # Find downloaded file
        # -------------------------------------------------

        downloaded_file = None

        for filename in os.listdir(DOWNLOAD_FOLDER):

            if filename.startswith(unique_id):

                file_path = os.path.join(
                    DOWNLOAD_FOLDER,
                    filename
                )

                if os.path.isfile(file_path):
                    downloaded_file = filename
                    break

        # -------------------------------------------------
        # File not found
        # -------------------------------------------------

        if not downloaded_file:

            return jsonify({
                "success": False,
                "error": "Download completed but output file was not found",
                "yt_dlp_output": result.stdout[-3000:] if result.stdout else "",
                "yt_dlp_error": result.stderr[-3000:] if result.stderr else ""
            }), 500

        # -------------------------------------------------
        # Generate URL
        # -------------------------------------------------

        file_url = (
            request.host_url.rstrip("/")
            + "/static/"
            + downloaded_file
        )

        print("Download successful:", downloaded_file)

        return jsonify({
            "success": True,
            "file_url": file_url,
            "filename": downloaded_file,
            "message": "Download successful"
        }), 200

    # -----------------------------------------------------
    # TIMEOUT
    # -----------------------------------------------------

    except subprocess.TimeoutExpired:

        return jsonify({
            "success": False,
            "error": "Download timed out. Please try again."
        }), 504

    # -----------------------------------------------------
    # yt-dlp not installed
    # -----------------------------------------------------

    except FileNotFoundError:

        return jsonify({
            "success": False,
            "error": "yt-dlp is not installed. Install it using: pip install yt-dlp"
        }), 500

    # -----------------------------------------------------
    # Unexpected error
    # -----------------------------------------------------

    except Exception as e:

        print("Unexpected download error:", repr(e))

        return jsonify({
            "success": False,
            "error": "Unexpected server error",
            "details": str(e)
        }), 500


# =========================================================
# STATIC FILE
# =========================================================

@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory(
        DOWNLOAD_FOLDER,
        filename
    )


# =========================================================
# KEEP ALIVE
# =========================================================

@app.route("/keepalive", methods=["GET"])
def keep_alive():
    return jsonify({
        "success": True,
        "message": "Server is alive!"
    }), 200


# =========================================================
# CHANNEL API
# =========================================================

@app.route("/channel", methods=["GET"])
def get_channel():

    return jsonify({
        "channel_link": "https://m.youtube.com/mirrykal"
    })


# =========================================================
# NO CACHE
# =========================================================

@app.after_request
def add_header(response):

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )

    return response


# =========================================================
# KEEP ALIVE THREAD
# =========================================================

def run_keep_alive():

    while True:

        time.sleep(600)

        try:

            # अगर अपना Render URL है तो यहाँ बदल देना
            subprocess.run(
                [
                    "curl",
                    "-L",
                    "--max-time",
                    "20",
                    "https://mirrykal.onrender.com/keepalive"
                ],
                check=False
            )

        except Exception as e:

            print("Keep-alive error:", e)


# Thread start
threading.Thread(
    target=run_keep_alive,
    daemon=True
).start()


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 25456)),
        debug=False
    )
