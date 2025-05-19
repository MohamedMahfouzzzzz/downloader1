from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import yt_dlp
import os
from werkzeug.utils import secure_filename
import random

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def get_random_user_agent():
    """Return a random desktop user agent to mimic different browsers"""
    agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15'
    ]
    return random.choice(agents)

def download_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'quiet': True,
        # Anti-bot evasion techniques
        'user_agent': get_random_user_agent(),
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['dash', 'hls']
            }
        },
        'socket_timeout': 30,
        'retries': 3,
        'no_check_certificate': True,
        'ignoreerrors': True,
        'extract_flat': True,
        # Throttle to mimic human behavior
        'ratelimit': 500000,  # 500KB/s
        'throttledratelimit': 250000,
        # Proxy rotation could be added here if needed
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
                return {
                    'success': False,
                    'error': 'Failed to extract video info',
                    'needs_captcha': False
                }
            
            filename = ydl.prepare_filename(info)
            mp3_filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            return {
                'success': True,
                'filename': os.path.basename(mp3_filename),
                'title': info.get('title', 'audio'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', '')
            }
    except Exception as e:
        error_msg = str(e)
        needs_captcha = "confirm you're not a bot" in error_msg
        
        if needs_captcha:
            # Try fallback method for age-restricted content
            return attempt_age_restricted_fallback(url)
            
        return {
            'success': False,
            'error': error_msg,
            'needs_captcha': needs_captcha
        }

def attempt_age_restricted_fallback(url):
    """Alternative method for age-restricted content"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'skip': ['dash', 'hls']
                }
            },
            'force_ipv4': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US'
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            return {
                'success': True,
                'filename': os.path.basename(mp3_filename),
                'title': info.get('title', 'audio'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'used_fallback': True
            }
    except Exception as e:
        return {
            'success': False,
            'error': f"Fallback failed: {str(e)}",
            'needs_captcha': True
        }

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({
            'success': False,
            'error': 'URL is required'
        }), 400
    
    if 'youtube.com' not in data['url'] and 'youtu.be' not in data['url']:
        return jsonify({
            'success': False,
            'error': 'Only YouTube URLs are supported'
        }), 400
    
    result = download_audio(data['url'])
    
    if result.get('needs_captcha', False):
        return jsonify({
            'success': False,
            'error': 'This video requires human verification. Try again later or use a different video.',
            'needs_captcha': True
        }), 403
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

@app.route('/api/download/<filename>', methods=['GET'])
def serve_file(filename):
    try:
        safe_filename = secure_filename(filename)
        file_path = os.path.join(DOWNLOAD_FOLDER, safe_filename)
        
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'File not found or expired'
            }), 404
            
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    try:
        for filename in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
