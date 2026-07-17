import os
import uuid
import shutil
import threading
import time
from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)

# Use /tmp on Vercel (read-only filesystem), fallback to local dir elsewhere
IS_VERCEL = os.environ.get("VERCEL") == "1"
TEMP_FOLDER = "/tmp/ytmp3_downloads" if IS_VERCEL else os.path.join(os.getcwd(), "temp_downloads")
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Audio formats yt-dlp can download natively WITHOUT FFmpeg.
# Preference order: m4a (AAC) > webm (Opus) > best available.
AUDIO_EXTENSIONS = ('.m4a', '.webm', '.opus', '.ogg', '.mp3', '.aac', '.flac', '.wav')

def cleanup_old_files():
    """Periodically clean up the temp folder."""
    while True:
        try:
            now = time.time()
            for session_id in os.listdir(TEMP_FOLDER):
                session_path = os.path.join(TEMP_FOLDER, session_id)
                if os.path.isdir(session_path):
                    if os.path.getmtime(session_path) < now - 3600:
                        shutil.rmtree(session_path, ignore_errors=True)
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(1800)  # Run every 30 minutes

# Only run cleanup thread outside of serverless environments
if not IS_VERCEL:
    threading.Thread(target=cleanup_old_files, daemon=True).start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/convert", methods=["POST"])
def convert():
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "Please provide a valid URL"}), 400

    session_id = str(uuid.uuid4())
    session_folder = os.path.join(TEMP_FOLDER, session_id)
    os.makedirs(session_folder, exist_ok=True)

    ydl_opts = {
        # Prefer m4a (no FFmpeg needed), fall back to webm/opus, then anything
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
        # No postprocessors — avoids any FFmpeg dependency entirely
        'outtmpl': os.path.join(session_folder, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                # Rely on API-based non-web clients to bypass the "Sign in to confirm you're not a bot" block
                'player_client': ['android', 'ios', 'tv']
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # Find the downloaded audio file
            audio_file = None
            for f in os.listdir(session_folder):
                if f.lower().endswith(AUDIO_EXTENSIONS):
                    audio_file = os.path.join(session_folder, f)
                    break

            if not audio_file or not os.path.exists(audio_file):
                return jsonify({"error": "Download failed — no audio file was produced."}), 500

            filename = os.path.basename(audio_file)
            return jsonify({
                "success": True,
                "download_url": f"/download/{session_id}/{filename}",
                "title": info.get('title', 'Unknown Title'),
                "format": os.path.splitext(filename)[1].lstrip('.')
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download/<session_id>/<filename>")
def download(session_id, filename):
    file_path = os.path.join(TEMP_FOLDER, session_id, filename)

    if not os.path.exists(file_path):
        return "File not found", 404

    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
