import os
import urllib.request
from io import BytesIO
from PIL import Image
from flask import Flask, request, jsonify
import yt_dlp
import threading
from flask_cors import CORS
import time
import json
import random
import re
import warnings
import tempfile
import shutil

app = Flask(__name__)

def sanitize(filename):
    """Sanitize the filename to remove invalid characters."""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename).strip()
    filename = filename.replace(' ', '_')
    if not filename:
        filename = "Untitled_" + str(int(time.time()))
    return filename

def search_youtube_music(query):
    """Search YouTube Music and return the first video URL."""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'default_search': 'ytsearch',
        'format': 'bestaudio/best',
        'noplaylist': True,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls', 'mhtml']
            }
        },
        'compat_opts': {
            'youtube-dl': True,
            'no-youtube-unavailable-videos': True
        },
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'skip_unavailable_fragments': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                return info['entries'][0]['url']
    except Exception as e:
        print(f"Search error: {e}")
    return None

def download_mp3_and_thumbnail(url, song_name, temp_dir):
    try:
        # Get video information
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': False,
            'ignoreerrors': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls', 'mhtml'],
                    'player_client': ['android', 'web']
                }
            },
            'compat_opts': {
                'youtube-dl': True,
                'no-youtube-unavailable-videos': True
            },
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.youtube.com/',
            },
            'live_from_start': True,
            'wait_for_video': (30, 300),
            'hls_prefer_native': True,
            'hls_use_mpegts': True,
            'external_downloader': 'ffmpeg',
            'external_downloader_args': ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'],
            'youtube_include_dash_manifest': False,
            'youtube_include_hls_manifest': False,
            'ffmpeg_location': '/usr/bin/ffmpeg',
        }

        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            
            is_live = info.get('is_live', False)
            was_live = info.get('was_live', False)
            is_upcoming = info.get('live_status') == 'upcoming'
            
            original_title = info.get("title", "Unknown_Song")
            title = sanitize(original_title)
            thumbnail_url = info.get("thumbnail", "")
            duration = info.get('duration', 0)
            
            if is_live or was_live:
                duration_str = "LIVE"
            elif is_upcoming:
                duration_str = "UPCOMING"
            elif duration > 0:
                mins, secs = divmod(duration, 60)
                duration_str = f"{mins}:{secs:02d}"
            else:
                duration_str = "N/A"

        # Download audio
        ydl_opts_download = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, f"{title}.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': False,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls', 'mhtml'],
                    'player_client': ['android', 'web']
                }
            },
            'compat_opts': {
                'youtube-dl': True,
                'no-youtube-unavailable-videos': True
            },
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.youtube.com/',
            },
            'noplaylist': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'buffersize': '1024k',
            'noresizebuffer': True,
            'http_chunk_size': '1048576',
            'continuedl': True,
            'ratelimit': '10M',
            'throttledratelimit': '5M',
            'retry_sleep_functions': {
                'http': lambda n: 5 + 0.5 * n,
                'fragment': lambda n: 5 + 0.5 * n,
            },
            'live_from_start': True,
            'wait_for_video': (30, 300),
            'hls_prefer_native': True,
            'hls_use_mpegts': True,
            'external_downloader': 'ffmpeg',
            'external_downloader_args': ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'],
            'youtube_include_dash_manifest': False,
            'youtube_include_hls_manifest': False,
            'concurrent_fragment_downloads': 4,
            'keep_fragments': True,
            'fragment_retries': 20,
            'extract_flat': 'in_playlist',
            'ffmpeg_location': '/usr/bin/ffmpeg',
        }

        max_attempts = 3
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]

        for attempt in range(max_attempts):
            try:
                ydl_opts_download['headers']['User-Agent'] = user_agents[attempt % len(user_agents)]
                with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                    ydl.download([url])
                break
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise
                print(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(2)

        mp3_path = os.path.join(temp_dir, f"{title}.mp3")
        png_path = os.path.join(temp_dir, f"{title}.png")
        
        max_wait_time = 120 if duration > 3600 else 30
        wait_interval = 0.5
        waited = 0
        while not os.path.exists(mp3_path) and waited < max_wait_time:
            time.sleep(wait_interval)
            waited += wait_interval

        if not os.path.exists(mp3_path):
            possible_files = [f for f in os.listdir(temp_dir) if f.startswith(title)]
            if possible_files:
                mp3_path = os.path.join(temp_dir, possible_files[0])
            else:
                raise FileNotFoundError(f"Audio file not created at {mp3_path}")

        # Download thumbnail if available
        if thumbnail_url:
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', random.choice(user_agents))]
                urllib.request.install_opener(opener)
                
                response = urllib.request.urlopen(thumbnail_url)
                img_data = response.read()
                image = Image.open(BytesIO(img_data))
                
                image.save(png_path, format="PNG")
            except Exception as e:
                print(f"Error downloading thumbnail: {e}")
                png_path = None
        
        return {
            'success': True,
            'title': original_title,
            'artist': info.get("uploader", "Unknown Artist"),
            'duration': duration_str,
            'mp3_path': mp3_path,
            'png_path': png_path,
            'source': 'YouTube',
            'thumbnailUrl': thumbnail_url if thumbnail_url else None,
            'status': 'completed',
            'audioType': 'audio/mpeg',
            'imageType': 'image/png' if png_path else None,
            'version': 1,
            'isLive': is_live,
            'wasLive': was_live
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# API Endpoints
@app.route('/')
def index():
    return "YouTube Music Downloader API is running!"

@app.route('/api/download', methods=['POST'])
def download_song():
    """Download a song by name and return audio and thumbnail data"""
    try:
        data = request.get_json()
        song_name = data.get('song_name', '').strip()
        
        if not song_name:
            return jsonify({
                'success': False,
                'message': 'Please provide a song name'
            }), 400
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        # Search YouTube for the song
        url = search_youtube_music(song_name)
        
        if not url:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({
                'success': False,
                'message': 'No results found for your search'
            }), 404
        
        # Download and process the song
        result = download_mp3_and_thumbnail(url, song_name, temp_dir)
        
        if result['success']:
            # Read the audio and thumbnail files
            mp3_path = result['mp3_path']
            png_path = result.get('png_path')
            
            with open(mp3_path, 'rb') as f:
                audio_data = f.read().hex()
            
            image_data = None
            if png_path and os.path.exists(png_path):
                with open(png_path, 'rb') as f:
                    image_data = f.read().hex()
            
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return jsonify({
                'success': True,
                'title': result['title'],
                'artist': result['artist'],
                'duration': result['duration'],
                'audio_data': audio_data,
                'image_data': image_data,
                'audio_type': 'audio/mpeg',
                'image_type': 'image/png' if image_data else None,
                'source': 'YouTube'
            })
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return jsonify({
                'success': False,
                'message': result.get('error', 'Unknown error occurred')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Server error: {str(e)}"
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time()
    })

# For PythonAnywhere
application = app

CORS(app)


if __name__ == '__main__':
    # Start background tasks if any
    threading.Thread(target=lambda: print("Background task placeholder"), daemon=True).start()
    
