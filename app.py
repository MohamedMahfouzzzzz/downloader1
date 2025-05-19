from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import yt_dlp
import os
import random
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def get_random_user_agent():
    """Return random user agents to mimic different browsers/devices"""
    agents = [
        # Desktop browsers
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        
        # Mobile browsers
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36',
        
        # Smart TV browsers
        'Mozilla/5.0 (SMART-TV; Linux; Tizen 5.5) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/3.0 Chrome/69.0.3497.106 TV Safari/537.36'
    ]
    return random.choice(agents)

def download_with_retries(url, max_retries=3):
    """Attempt download with multiple strategies and retries"""
    strategies = [
        # Strategy 1: Android client with mobile user agent
        {
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'headers': {'User-Agent': get_random_user_agent()},
            'geo_bypass': True,
            'geo_bypass_country': random.choice(['US', 'GB', 'DE', 'JP', 'IN'])
        },
        
        # Strategy 2: Web client with desktop user agent
        {
            'extractor_args': {'youtube': {'player_client': ['web']}},
            'headers': {'User-Agent': get_random_user_agent()},
            'referer': 'https://www.youtube.com/'
        },
        
        # Strategy 3: TV client with different parameters
        {
            'extractor_args': {'youtube': {'player_client': ['tv_html5']}},
            'headers': {'User-Agent': get_random_user_agent()},
            'force_ipv4': True
        }
    ]
    
    for attempt in range(max_retries):
        try:
            # Select strategy with increasing timeout
            strategy = strategies[attempt % len(strategies)]
            current_timeout = 10 + (attempt * 5)  # 10, 15, 20 seconds
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'quiet': True,
                'socket_timeout': current_timeout,
                'retries': 3,
                'no_check_certificate': True,
                'ignoreerrors': True,
                'ratelimit': 500000,  # Limit download speed
                'throttledratelimit': 250000,
                **strategy  # Merge the current strategy
            }
            
            # Random delay between attempts
            time.sleep(random.uniform(1, 3))
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    continue  # Try next strategy
                
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
            if "Sign in to confirm you're not a bot" in str(e):
                continue  # Try next strategy
            return {
                'success': False,
                'error': str(e),
                'needs_captcha': True
            }
    
    return {
        'success': False,
        'error': 'All download attempts failed. YouTube is blocking these requests.',
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
    
    result = download_with_retries(data['url'])
    
    if result.get('needs_captcha', False):
        return jsonify({
            'success': False,
            'error': 'YouTube is requesting human verification.',
            'solution': 'Try again later or use a different video. Server cannot bypass this without cookies.'
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
