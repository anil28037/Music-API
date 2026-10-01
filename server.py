from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS

import os
import time
import uuid
import sys
import subprocess
import shutil

# Optional FFmpeg package
try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


# =========================================================
# FLASK APP
# =========================================================

app = Flask(
    __name__,
    template_folder="templates"
)

CORS(app)


# =========================================================
# CONFIGURATION
# =========================================================

DOWNLOAD_FOLDER = "static"
COOKIES_FILE = "cookies.txt"

# Bot-Hosting provides SERVER_PORT
PORT = int(os.environ.get("SERVER_PORT", "5000"))

# File lifetime
# 10 seconds was too short for Messenger.
FILE_MAX_AGE = 600  # 10 minutes


os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# =========================================================
# FIND FFMPEG
# =========================================================

def get_ffmpeg_path():

    # 1. System ffmpeg
    system_ffmpeg = shutil.which("ffmpeg")

    if system_ffmpeg:
        return system_ffmpeg

    # 2. imageio-ffmpeg package
    if imageio_ffmpeg is not None:
        try:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

            if ffmpeg_path and os.path.exists(ffmpeg_path):
                return ffmpeg_path

        except Exception:
            pass

    return None


# =========================================================
# DELETE OLD FILES
# =========================================================

def delete_old_files():

    try:

        now = time.time()

        for filename in os.listdir(DOWNLOAD_FOLDER):

            file_path = os.path.join(
                DOWNLOAD_FOLDER,
                filename
            )

            if not os.path.isfile(file_path):
                continue

            try:

                age = now - os.path.getmtime(file_path)

                if age > FILE_MAX_AGE:
                    os.remove(file_path)

            except OSError:
                pass

    except OSError:
        pass


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    try:
        return render_template("index.html")

    except Exception:

        return jsonify({
            "success": True,
            "service": "Music API",
            "status": "online"
        })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    ffmpeg = get_ffmpeg_path()

    return jsonify({
        "success": True,
        "status": "online",
        "yt_dlp": True,
        "ffmpeg": bool(ffmpeg),
        "port": PORT
    })


# =========================================================
# DOWNLOAD API
# =========================================================

@app.route("/download", methods=["GET"])
def download_media():

    video_url = request.args.get("url")
    media_type = request.args.get(
        "type",
        "audio"
    ).lower().strip()

    # -----------------------------------------------------
    # Validate URL
    # -----------------------------------------------------

    if not video_url:

        return jsonify({
            "success": False,
            "error": "No URL provided"
        }), 400

    # -----------------------------------------------------
    # Validate type
    # -----------------------------------------------------

    if media_type not in ("audio", "video"):

        return jsonify({
            "success": False,
            "error": "Invalid type. Use audio or video."
        }), 400

    # -----------------------------------------------------
    # Cleanup old files
    # -----------------------------------------------------

    delete_old_files()

    # -----------------------------------------------------
    # Check yt-dlp
    #
    # IMPORTANT:
    # Using Python module instead of:
    #     yt-dlp
    #
    # This fixes the PATH problem.
    # -----------------------------------------------------

    try:

        yt_check = subprocess.run(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--version"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if yt_check.returncode != 0:

            return jsonify({
                "success": False,
                "error": "yt-dlp is not installed.",
                "details": (
                    yt_check.stderr or
                    yt_check.stdout or
                    "Install yt-dlp in requirements.txt"
                )[-2000:]
            }), 500

        yt_version = yt_check.stdout.strip()

    except Exception as e:

        return jsonify({
            "success": False,
            "error": "yt-dlp check failed.",
            "details": str(e)
        }), 500

    # -----------------------------------------------------
    # FFmpeg
    # -----------------------------------------------------

    ffmpeg_path = get_ffmpeg_path()

    # -----------------------------------------------------
    # Filename
    # -----------------------------------------------------

    if media_type == "audio":
        extension = "mp3"
    else:
        extension = "mp4"

    unique_filename = (
        f"{uuid.uuid4().hex}.{extension}"
    )

    output_path = os.path.join(
        DOWNLOAD_FOLDER,
        unique_filename
    )

    # -----------------------------------------------------
    # yt-dlp command
    # -----------------------------------------------------

    command = [
        sys.executable,
        "-m",
        "yt_dlp",

        "--no-playlist",

        "--output",
        output_path
    ]

    # -----------------------------------------------------
    # Cookies
    # -----------------------------------------------------

    if os.path.isfile(COOKIES_FILE):

        command.extend([
            "--cookies",
            COOKIES_FILE
        ])

    # -----------------------------------------------------
    # AUDIO
    # -----------------------------------------------------

    if media_type == "audio":

        if not ffmpeg_path:

            return jsonify({
                "success": False,
                "error": "FFmpeg is not available.",
                "message": (
                    "imageio-ffmpeg should be installed "
                    "in requirements.txt"
                )
            }), 500

        command.extend([
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "192K",
            "--ffmpeg-location",
            ffmpeg_path
        ])

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    else:

        if ffmpeg_path:

            command.extend([
                "--ffmpeg-location",
                ffmpeg_path,

                "-f",
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "best[ext=mp4]/best",

                "--merge-output-format",
                "mp4"
            ])

        else:

            command.extend([
                "-f",
                "best[ext=mp4]/best"
            ])

    # -----------------------------------------------------
    # URL
    # -----------------------------------------------------

    command.append(video_url)

    # -----------------------------------------------------
    # RUN YT-DLP
    # -----------------------------------------------------

    try:

        print("=" * 60)
        print("[DOWNLOAD]")
        print("URL:", video_url)
        print("TYPE:", media_type)
        print("YT-DLP:", yt_version)
        print("FFMPEG:", ffmpeg_path)
        print("=" * 60)

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300
        )

        # -------------------------------------------------
        # yt-dlp error
        # -------------------------------------------------

        if result.returncode != 0:

            error_details = (
                result.stderr or
                result.stdout or
                "Unknown yt-dlp error"
            )

            print("[YT-DLP ERROR]")
            print(error_details)

            return jsonify({
                "success": False,
                "error": "Download failed",
                "details": error_details[-4000:]
            }), 500

        # -------------------------------------------------
        # Output filename
        #
        # yt-dlp can change extension after postprocessing.
        # -------------------------------------------------

        if not os.path.exists(output_path):

            possible_files = []

            base_name = os.path.splitext(
                output_path
            )[0]

            for filename in os.listdir(
                DOWNLOAD_FOLDER
            ):

                full_path = os.path.join(
                    DOWNLOAD_FOLDER,
                    filename
                )

                if (
                    os.path.isfile(full_path)
                    and filename.startswith(
                        os.path.basename(base_name)
                    )
                ):
                    possible_files.append(
                        full_path
                    )

            if possible_files:

                output_path = max(
                    possible_files,
                    key=os.path.getmtime
                )

                unique_filename = os.path.basename(
                    output_path
                )

        # -------------------------------------------------
        # File check
        # -------------------------------------------------

        if not os.path.exists(output_path):

            return jsonify({
                "success": False,
                "error": (
                    "Download completed but "
                    "output file was not found."
                ),
                "details": (
                    result.stdout or ""
                )[-2000:]
            }), 500

        file_size = os.path.getsize(
            output_path
        )

        if file_size <= 0:

            return jsonify({
                "success": False,
                "error": "Downloaded file is empty."
            }), 500

        # -------------------------------------------------
        # Create public URL
        # -------------------------------------------------

        base_url = request.host_url.rstrip("/")

        file_url = (
            f"{base_url}/static/"
            f"{unique_filename}"
        )

        print("[SUCCESS]")
        print("FILE:", unique_filename)
        print("SIZE:", file_size)
        print("URL:", file_url)

        # -------------------------------------------------
        # JSON response
        #
        # Multiple key names included so Messenger
        # code can easily read it.
        # -------------------------------------------------

        return jsonify({

            "success": True,

            "file_url": file_url,

            "download_url": file_url,

            "url": file_url,

            "type": media_type,

            "filename": unique_filename,

            "size": file_size,

            "message": "Download successful"

        }), 200

    # -----------------------------------------------------
    # Timeout
    # -----------------------------------------------------

    except subprocess.TimeoutExpired:

        return jsonify({
            "success": False,
            "error": "Download timeout.",
            "message": "Video took too long to download."
        }), 504

    # -----------------------------------------------------
    # Other error
    # -----------------------------------------------------

    except Exception as e:

        print("[SERVER ERROR]")
        print(str(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# =========================================================
# STATIC FILES
# =========================================================

@app.route("/static/<path:filename>")
def serve_static(filename):

    return send_from_directory(
        DOWNLOAD_FOLDER,
        filename
    )


# =========================================================
# KEEPALIVE
# =========================================================

@app.route("/keepalive")
def keep_alive():

    return jsonify({
        "success": True,
        "status": "alive"
    }), 200


# =========================================================
# CHANNEL
# =========================================================

@app.route("/channel")
def get_channel():

    return jsonify({
        "channel_link":
        "https://m.youtube.com/mirrykal"
    })


# =========================================================
# NO CACHE
# =========================================================

@app.after_request
def add_header(response):

    response.headers[
        "Cache-Control"
    ] = (
        "no-store, "
        "no-cache, "
        "must-revalidate, "
        "max-age=0"
    )

    return response


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("MUSIC API STARTING")
    print("Host: 0.0.0.0")
    print(f"Port: {PORT}")
    print("yt-dlp: Python module")
    print("FFmpeg:", get_ffmpeg_path())
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True
                )
