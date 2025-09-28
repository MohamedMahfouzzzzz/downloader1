import os
import urllib.request
from io import BytesIO
from PIL import Image
from flask import Flask, request, jsonify
import yt_dlp
import threading
import time
import json
import random
import re
import cloudinary
import cloudinary.uploader
import cloudinary.api
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import hashlib
import warnings

app = Flask(__name__)

# Initialize Firebase
db = None
try:
    cred_path = os.path.expanduser('~/firebase-credentials.json')
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase initialized successfully")
    else:
        print("Firebase credentials file not found")
except Exception as e:
    print(f"Firebase initialization error: {e}")

# Configure Cloudinary
try:
    cloudinary.config(
        cloud_name="dgp55b9vn",
        api_key="738647756627725",
        api_secret="Vq7zyHPuHDl0zytJlW8igCdEPL4"
    )
    print("Cloudinary configured successfully")
except Exception as e:
    print(f"Cloudinary configuration error: {e}")

def sanitize(filename):
    """Sanitize the filename to remove invalid characters."""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename).strip()
    filename = filename.replace(' ', '_')
    if not filename:
        filename = "Untitled_" + str(int(time.time()))
    return filename

def sanitize_public_id(filename):
    """Sanitize filename for Cloudinary public_id requirements"""
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '', filename)
    filename = re.sub(r'[_\-\.]{2,}', '_', filename)
    filename = filename.strip('-.')
    filename = filename[:100]
    if not filename:
        filename = "file_" + str(int(time.time()))
    return filename

def generate_public_id(filename):
    """Generate a safe public_id from filename"""
    file_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
    safe_name = sanitize_public_id(filename)[:50]
    return f"{safe_name}_{file_hash}"

def create_m3ew_file(metadata, image_data, audio_data):
    """Create an M3EW file from metadata, image and audio data."""
    M3EW_HEADER = b"M3EW"
    IMAGE_START_MARKER = b"IMG_START"
    IMAGE_END_MARKER = b"IMG_END"
    AUDIO_START_MARKER = b"AUDIO_START"
    AUDIO_END_MARKER = b"AUDIO_END"
    
    metadata_str = json.dumps(metadata)
    metadata_bytes = metadata_str.encode('utf-8')
    metadata_length = len(metadata_bytes)
    
    header = bytearray(9)
    header[0:4] = M3EW_HEADER
    header[4] = metadata.get("version", 1)
    header[5:9] = metadata_length.to_bytes(4, 'little')
    
    parts = [
        header,
        metadata_bytes,
        IMAGE_START_MARKER,
        image_data,
        IMAGE_END_MARKER,
        AUDIO_START_MARKER,
        audio_data,
        AUDIO_END_MARKER
    ]
    
    return b''.join(parts)

def upload_to_cloudinary(file_path, public_id=None):
    """Upload file to Cloudinary and return secure URL."""
    try:
        file_size = os.path.getsize(file_path)
        
        if public_id:
            public_id = generate_public_id(public_id)
        
        if file_size > 10 * 1024 * 1024:
            response = cloudinary.uploader.upload_large(
                file_path,
                resource_type="raw",
                public_id=public_id,
                unique_filename=False,
                overwrite=True,
                chunk_size=20 * 1024 * 1024
            )
        else:
            response = cloudinary.uploader.upload(
                file_path,
                resource_type="raw",
                public_id=public_id,
                unique_filename=False,
                overwrite=True
            )
            
        return response['secure_url']
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def add_to_firestore(song_data, collection_name='recommendedSongs'):
    """Add song data to Firestore collection"""
    if not db:
        print("Firestore not initialized, skipping Firestore update")
        return False
    
    try:
        if 'createdAt' not in song_data:
            song_data['createdAt'] = datetime.now()
        
        doc_ref = db.collection(collection_name).document()
        doc_ref.set(song_data)
        print(f"Added song to Firestore with ID: {doc_ref.id}")
        return True
    except Exception as e:
        print(f"Error adding to Firestore: {e}")
        return False

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

def download_mp3_and_thumbnail(url, song_name, folder_path=None):
    try:
        # Create download directory if it doesn't exist
        if not folder_path:
            folder_path = os.path.expanduser('~/YouTube_Downloads')
        os.makedirs(folder_path, exist_ok=True)

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
            'ffmpeg_location': '/usr/bin/ffmpeg',  # PythonAnywhere specific
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
            'outtmpl': os.path.join(folder_path, f"{title}.%(ext)s"),
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
            'ffmpeg_location': '/usr/bin/ffmpeg',  # PythonAnywhere specific
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

        mp3_path = os.path.join(folder_path, f"{title}.mp3")
        
        max_wait_time = 120 if duration > 3600 else 30
        wait_interval = 0.5
        waited = 0
        while not os.path.exists(mp3_path) and waited < max_wait_time:
            time.sleep(wait_interval)
            waited += wait_interval

        if not os.path.exists(mp3_path):
            possible_files = [f for f in os.listdir(folder_path) if f.startswith(title)]
            if possible_files:
                mp3_path = os.path.join(folder_path, possible_files[0])
            else:
                raise FileNotFoundError(f"Audio file not created at {mp3_path}")

        # Download thumbnail if available
        image_data = b''
        if thumbnail_url:
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', random.choice(user_agents))]
                urllib.request.install_opener(opener)
                
                response = urllib.request.urlopen(thumbnail_url)
                img_data = response.read()
                image = Image.open(BytesIO(img_data))
                
                png_path = os.path.join(folder_path, f"{title}.png")
                jpg_path = os.path.join(folder_path, f"{title}.jpg")
                
                image.save(png_path, format="PNG")
                image.save(jpg_path, format="JPEG", quality=95)
                
                with open(png_path, 'rb') as f:
                    image_data = f.read()
            except Exception as e:
                print(f"Error downloading thumbnail: {e}")

        # Create M3EW file
        with open(mp3_path, 'rb') as f:
            audio_data = f.read()
        
        metadata = {
            "title": original_title,
            "artist": info.get("uploader", "Unknown Artist"),
            "audioType": "audio/mpeg",
            "imageType": "image/png" if image_data else None,
            "duration": duration_str,
            "source": "YouTube",
            "createdAt": datetime.now().isoformat(),
            "version": 1,
            "isLive": is_live,
            "wasLive": was_live
        }
        
        m3ew_data = create_m3ew_file(metadata, image_data, audio_data)
        m3ew_path = os.path.join(folder_path, f"{title}.m3ew")
        
        with open(m3ew_path, 'wb') as f:
            f.write(m3ew_data)
        
        # Upload to Cloudinary
        cloudinary_url = upload_to_cloudinary(m3ew_path, public_id=title)
        
        if cloudinary_url:
            # Prepare song data for Firestore
            song_data = {
                'title': original_title,
                'artist': info.get("uploader", "Unknown Artist"),
                'duration': duration_str,
                'cloudinaryUrl': cloudinary_url,
                'createdAt': datetime.now(),
                'source': 'YouTube',
                'thumbnailUrl': thumbnail_url if thumbnail_url else None,
                'localPath': m3ew_path,
                'status': 'completed',
                'audioType': 'audio/mpeg',
                'imageType': 'image/png' if image_data else None,
                'version': 1,
                'isLive': is_live,
                'wasLive': was_live
            }
            
            # Add to Firestore
            firestore_success = add_to_firestore(song_data)
            
            return {
                'success': True,
                'title': original_title,
                'artist': info.get("uploader", "Unknown Artist"),
                'duration': duration_str,
                'cloudinaryUrl': cloudinary_url,
                'source': 'YouTube',
                'thumbnailUrl': thumbnail_url if thumbnail_url else None,
                'localPath': m3ew_path,
                'status': 'completed',
                'audioType': 'audio/mpeg',
                'imageType': 'image/png' if image_data else None,
                'version': 1,
                'isLive': is_live,
                'wasLive': was_live,
                'firestoreSuccess': firestore_success
            }
        else:
            return {
                'success': False,
                'error': 'Failed to upload to Cloudinary',
                'localPath': m3ew_path
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
    """Download a song by name and upload to Cloudinary"""
    try:
        data = request.get_json()
        song_name = data.get('song_name', '').strip()
        folder_path = data.get('folder_path', '').strip()
        
        if not song_name:
            return jsonify({
                'success': False,
                'message': 'Please provide a song name'
            }), 400
        
        if not folder_path:
            folder_path = os.path.expanduser('~/YouTube_Downloads')
        
        # Search YouTube for the song
        url = search_youtube_music(song_name)
        
        if not url:
            return jsonify({
                'success': False,
                'message': 'No results found for your search'
            }), 404
        
        # Download and process the song
        result = download_mp3_and_thumbnail(url, song_name, folder_path)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'message': result.get('error', 'Unknown error occurred')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Server error: {str(e)}"
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get download history from Firestore"""
    try:
        if not db:
            return jsonify({
                'success': False,
                'message': 'Firestore not initialized',
                'songs': []
            }), 500
        
        limit = request.args.get('limit', 20, type=int)
        songs_ref = db.collection('recommendedSongs').order_by('createdAt', direction=firestore.Query.DESCENDING).limit(limit)
        songs = []
        
        for doc in songs_ref.stream():
            song_data = doc.to_dict()
            # Convert datetime to string for JSON serialization
            if 'createdAt' in song_data and hasattr(song_data['createdAt'], 'isoformat'):
                song_data['createdAt'] = song_data['createdAt'].isoformat()
            songs.append(song_data)
        
        return jsonify({
            'success': True,
            'songs': songs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e),
            'songs': []
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'firebase_initialized': db is not None
    })

# For PythonAnywhere
application = app

if __name__ == '__main__':
    # Start background tasks if any
    threading.Thread(target=lambda: print("Background task placeholder"), daemon=True).start()
    

