# app.py
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import yt_dlp
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import threading

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
DOWNLOAD_FOLDER = 'downloads'
COOKIES_FILE = 'cookies.txt'  # Path to your YouTube cookies file
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Cleanup scheduler
def cleanup_old_files():
    """Delete files older than 1 hour"""
    now = datetime.now()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if now - file_time > timedelta(hours=1):
                try:
                    os.unlink(file_path)
                    print(f"Deleted old file: {filename}")
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")

def schedule_cleanup():
    """Run cleanup every hour"""
    cleanup_old_files()
    threading.Timer(3600, schedule_cleanup).start()

# Start the cleanup scheduler
schedule_cleanup()

def download_audio(url):
    """Download YouTube audio and convert to MP3"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'quiet': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls'],
                'player_client': ['android', 'web']
            }
        },
        'socket_timeout': 30,
        'retries': 3
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            # Sanitize filename for web
            safe_filename = secure_filename(os.path.basename(mp3_filename))
            os.rename(mp3_filename, os.path.join(DOWNLOAD_FOLDER, safe_filename))
            
            return {
                'success': True,
                'filename': safe_filename,
                'title': info.get('title', 'audio'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', '')
            }
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            error_msg += "\nServer needs updated YouTube cookies"
        return {
            'success': False,
            'error': error_msg,
            'error_type': 'download_error'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': 'server_error'
        }

@app.route('/api/download', methods=['POST'])
def api_download():
    """Handle download requests"""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({
            'success': False,
            'error': 'URL is required',
            'error_type': 'invalid_request'
        }), 400
    
    # Validate YouTube URL
    if not any(p in data['url'] for p in ('youtube.com', 'youtu.be')):
        return jsonify({
            'success': False,
            'error': 'Invalid YouTube URL',
            'error_type': 'invalid_url'
        }), 400
    
    result = download_audio(data['url'])
    return jsonify(result)

@app.route('/api/download/<filename>', methods=['GET'])
def serve_file(filename):
    """Serve downloaded MP3 files"""
    try:
        safe_filename = secure_filename(filename)
        file_path = os.path.join(DOWNLOAD_FOLDER, safe_filename)
        
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'File not found or expired',
                'error_type': 'file_not_found'
            }), 404
            
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'error_type': 'server_error'
        }), 500

@app.route('/api/status', methods=['GET'])
def api_status():
    """Service health check"""
    return jsonify({
        'status': 'operational',
        'downloads_count': len(os.listdir(DOWNLOAD_FOLDER)),
        'storage_usage': f"{sum(os.path.getsize(f) for f in os.listdir(DOWNLOAD_FOLDER)) / (1024*1024):.2f} MB"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
