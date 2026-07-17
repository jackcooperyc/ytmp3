import os
import uuid
import shutil
import threading
import time
from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp

# Add bundled FFmpeg binaries to PATH (for Vercel and environments without system FFmpeg)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths(download_dir="/tmp")
except ImportError:
    pass  # Fall back to system FFmpeg if static_ffmpeg not installed

app = Flask(__name__)

# Use /tmp on Vercel (read-only filesystem), fallback to local dir elsewhere
IS_VERCEL = os.environ.get("VERCEL") == "1"
TEMP_FOLDER = "/tmp/ytmp3_downloads" if IS_VERCEL else os.path.join(os.getcwd(), "temp_downloads")
os.makedirs(TEMP_FOLDER, exist_ok=True)

def cleanup_old_files():
    """Periodically clean up the temp folder."""
    while True:
        try:
            now = time.time()
            for session_id in os.listdir(TEMP_FOLDER):
                session_path = os.path.join(TEMP_FOLDER, session_id)
                if os.path.isdir(session_path):
                    # Remove folders older than 1 hour
                    if os.path.getmtime(session_path) < now - 3600:
                        shutil.rmtree(session_path, ignore_errors=True)
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(1800)  # Run every 30 minutes

# Only run the cleanup thread outside of serverless environments
# (Vercel functions are stateless — threads don't persist between invocations)
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
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(session_folder, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'referer': 'https://www.google.com/',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'mweb', 'android']
            }
        },
        # cookiesfrombrowser omitted — no browser available in serverless environments
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Find the generated mp3 file
            mp3_file = None
            for f in os.listdir(session_folder):
                if f.endswith('.mp3'):
                    mp3_file = os.path.join(session_folder, f)
                    break
            
            if not mp3_file or not os.path.exists(mp3_file):
                return jsonify({"error": "Conversion failed. FFmpeg might be missing."}), 500

            filename = os.path.basename(mp3_file)
            return jsonify({
                "success": True,
                "download_url": f"/download/{session_id}/{filename}",
                "title": info.get('title', 'Unknown Title')
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
