import os
import urllib.request
from io import BytesIO
from PIL import Image
import yt_dlp
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
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import threading

app = Flask(__name__)

# Initialize Firebase
def initialize_firebase():
    try:
        cred = credentials.Certificate('music-mk-e933c-firebase-adminsdk-3btm1-33d2f7718f.json')
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"Firebase initialization error: {e}")
        return None

db = initialize_firebase()

# Configure Cloudinary
cloudinary.config(
    cloud_name="dgp55b9vn",
    api_key="738647756627725",
    api_secret="Vq7zyHPuHDl0zytJlW8igCdEPL4"
)

# Utility functions
def sanitize(filename):
    """Sanitize the filename to remove invalid characters."""
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s+', ' ', filename).strip()
    filename = filename.replace(' ', '_')
    if not filename:
        filename = "Untitled_" + str(int(time.time()))
    return filename

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

def update_waiting_document(doc_id, updates):
    """Update a document in the waiting collection"""
    if not db:
        print("Firestore not initialized, skipping update")
        return False
    
    try:
        print(f"Updating document {doc_id} with: {updates}")
        db.collection('waiting').document(doc_id).update(updates)
        print(f"Successfully updated waiting document {doc_id}")
        return True
    except Exception as e:
        print(f"Error updating waiting document {doc_id}: {e}")
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
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if 'entries' in info and len(info['entries']) > 0:
                return info['entries'][0]['url']
    except Exception as e:
        print(f"Search error: {e}")
    return None

def download_mp3_and_thumbnail(url, folder_path=None, doc_id=None):
    try:
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
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            original_title = info.get("title", "Unknown_Song")
            title = sanitize(original_title)
            thumbnail_url = info.get("thumbnail", "")
            duration = info.get('duration', 0)
            
            if duration > 0:
                mins, secs = divmod(duration, 60)
                duration_str = f"{mins}:{secs:02d}"
            else:
                duration_str = "N/A"

        if not folder_path:
            folder_path = os.path.join(os.getcwd(), "YouTube_Downloads")
        os.makedirs(folder_path, exist_ok=True)

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
                time.sleep(2)

        mp3_path = os.path.join(folder_path, f"{title}.mp3")
        
        max_wait_time = 30
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

        result = {
            'status': 'success',
            'title': original_title,
            'artist': info.get("uploader", "Unknown Artist"),
            'duration': duration_str,
            'local_paths': {
                'mp3': mp3_path,
                'thumbnail': None,
                'm3ew': None
            },
            'cloudinary_url': None
        }

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
                
                with open(mp3_path, 'rb') as f:
                    audio_data = f.read()
                
                metadata = {
                    "title": original_title,
                    "artist": info.get("uploader", "Unknown Artist"),
                    "audioType": "audio/mpeg",
                    "imageType": "image/png",
                    "duration": duration_str,
                    "source": "YouTube",
                    "createdAt": datetime.now().isoformat(),
                    "version": 1
                }
                
                m3ew_data = create_m3ew_file(metadata, image_data, audio_data)
                m3ew_path = os.path.join(folder_path, f"{title}.m3ew")
                
                with open(m3ew_path, 'wb') as f:
                    f.write(m3ew_data)
                
                cloudinary_url = upload_to_cloudinary(m3ew_path, public_id=title)
                
                if cloudinary_url:
                    song_data = {
                        'title': original_title,
                        'artist': info.get("uploader", "Unknown Artist"),
                        'duration': duration_str,
                        'cloudinaryUrl': cloudinary_url,
                        'createdAt': datetime.now(),
                        'source': 'YouTube',
                        'thumbnailUrl': thumbnail_url,
                        'localPath': m3ew_path,
                        'status': 'completed',
                        'audioType': 'audio/mpeg',
                        'imageType': 'image/png',
                        'version': 1
                    }
                    
                    result['local_paths']['thumbnail'] = png_path
                    result['local_paths']['m3ew'] = m3ew_path
                    result['cloudinary_url'] = cloudinary_url
                    
                    if add_to_firestore(song_data):
                        result['firestore_status'] = 'added'
                        if doc_id:
                            update_waiting_document(doc_id, {
                                'finished': True,
                                'cloudinaryUrl': cloudinary_url,
                                'completedAt': datetime.now()
                            })
                    else:
                        result['firestore_status'] = 'failed'
            except Exception as thumb_error:
                try:
                    with open(mp3_path, 'rb') as f:
                        audio_data = f.read()
                    
                    metadata = {
                        "title": original_title,
                        "artist": info.get("uploader", "Unknown Artist"),
                        "audioType": "audio/mpeg",
                        "imageType": None,
                        "duration": duration_str,
                        "source": "YouTube",
                        "createdAt": datetime.now().isoformat(),
                        "version": 1
                    }
                    
                    m3ew_data = create_m3ew_file(metadata, b'', audio_data)
                    m3ew_path = os.path.join(folder_path, f"{title}.m3ew")
                    
                    with open(m3ew_path, 'wb') as f:
                        f.write(m3ew_data)
                    
                    cloudinary_url = upload_to_cloudinary(m3ew_path, public_id=title)
                    
                    if cloudinary_url:
                        song_data = {
                            'title': original_title,
                            'artist': info.get("uploader", "Unknown Artist"),
                            'duration': duration_str,
                            'cloudinaryUrl': cloudinary_url,
                            'createdAt': datetime.now(),
                            'source': 'YouTube',
                            'thumbnailUrl': None,
                            'localPath': m3ew_path,
                            'status': 'completed_no_thumbnail',
                            'audioType': 'audio/mpeg',
                            'imageType': None,
                            'version': 1
                        }
                        
                        result['local_paths']['m3ew'] = m3ew_path
                        result['cloudinary_url'] = cloudinary_url
                        
                        if add_to_firestore(song_data):
                            result['firestore_status'] = 'added_no_thumbnail'
                            if doc_id:
                                update_waiting_document(doc_id, {
                                    'finished': True,
                                    'cloudinaryUrl': cloudinary_url,
                                    'completedAt': datetime.now()
                                })
                        else:
                            result['firestore_status'] = 'failed_no_thumbnail'
                except Exception as m3ew_error:
                    result['status'] = 'partial_success'
                    result['error'] = str(m3ew_error)
        return result

    except yt_dlp.utils.DownloadError as e:
        if "HTTP Error 403" in str(e):
            return {'status': 'error', 'message': 'YouTube is blocking requests. Try again later or use a VPN/proxy.'}
        else:
            return {'status': 'error', 'message': str(e)}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def check_waiting_songs(folder_path):
    """Check Firestore waiting collection for songs to download"""
    if not db:
        return {'status': 'error', 'message': 'Firestore not initialized'}
    
    try:
        docs = db.collection('waiting').where('finished', '!=', True).stream()
        found_docs = list(docs)
        
        if not found_docs:
            return {'status': 'success', 'message': 'No waiting songs found'}
            
        results = []
        
        for doc in found_docs:
            doc_data = doc.to_dict()
            song_name = doc_data.get('songName')
            finished = doc_data.get('finished', False)
            
            if not song_name or finished:
                continue
                
            update_waiting_document(doc.id, {
                'processing': True, 
                'startedAt': datetime.now(),
                'lastUpdate': 'Starting download'
            })
            
            url = search_youtube_music(song_name)
            
            if url:
                result = download_mp3_and_thumbnail(url, folder_path, doc.id)
                results.append({
                    'doc_id': doc.id,
                    'song_name': song_name,
                    'result': result
                })
            else:
                update_waiting_document(doc.id, {
                    'error': 'No results found',
                    'finished': True,
                    'completedAt': datetime.now(),
                    'lastUpdate': 'No results found'
                })
                results.append({
                    'doc_id': doc.id,
                    'song_name': song_name,
                    'result': {'status': 'error', 'message': 'No results found'}
                })
            
            time.sleep(5)
        
        return {'status': 'success', 'results': results}
    
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# API Endpoints
@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
    
    query = data.get('query')
    url = data.get('url')
    folder_path = data.get('folder_path', os.path.join(os.getcwd(), "YouTube_Downloads"))
    
    if not query and not url:
        return jsonify({'status': 'error', 'message': 'Either query or url must be provided'}), 400
    
    if query:
        youtube_url = search_youtube_music(query)
        if not youtube_url:
            return jsonify({'status': 'error', 'message': 'No results found for your search'}), 404
    else:
        youtube_url = url
    
    result = download_mp3_and_thumbnail(youtube_url, folder_path)
    return jsonify(result)

@app.route('/api/check_waiting', methods=['POST'])
def api_check_waiting():
    folder_path = request.json.get('folder_path', os.path.join(os.getcwd(), "YouTube_Downloads"))
    result = check_waiting_songs(folder_path)
    return jsonify(result)

@app.route('/api/download_file', methods=['GET'])
def api_download_file():
    file_path = request.args.get('path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    
    try:
        return send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path)
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Background task to check waiting songs periodically
def background_task():
    folder_path = os.path.join(os.getcwd(), "YouTube_Downloads")
    while True:
        try:
            check_waiting_songs(folder_path)
        except Exception as e:
            print(f"Background task error: {e}")
        time.sleep(60 * 5)  # Check every 5 minutes

# Start background thread when app starts
if __name__ == '__main__':
    threading.Thread(target=background_task, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
else:
    threading.Thread(target=background_task, daemon=True).start()
