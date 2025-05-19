from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
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
import threading

# Initialize Flask app with CORS
app = Flask(__name__)
CORS(app)  # Enable CORS for all domains on all routes

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

def upload_large_file(file_path, public_id=None):
    """Upload file to Cloudinary with chunked upload support."""
    try:
        file_size = os.path.getsize(file_path)
        
        if file_size <= 10 * 1024 * 1024:  # 10MB or smaller
            response = cloudinary.uploader.upload(
                file_path,
                resource_type="raw",
                public_id=public_id,
                unique_filename=False,
                overwrite=True
            )
        else:
            # For files larger than 10MB
            response = cloudinary.uploader.upload_large(
                file_path,
                resource_type="raw",
                public_id=public_id,
                chunk_size=6 * 1024 * 1024,  # 6MB chunks
                timeout=300  # 5 minute timeout
            )
        return response['secure_url']
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

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

def download_webm_and_thumbnail(url, folder_path=None, doc_id=None):
    try:
        if not folder_path:
            folder_path = os.path.join(os.getcwd(), "YouTube_Downloads")
        os.makedirs(folder_path, exist_ok=True)

        # Set up yt-dlp options for WebM
        ydl_opts = {
            'format': 'bestaudio[ext=webm]',
            'outtmpl': os.path.join(folder_path, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls', 'mhtml'],
                    'player_client': ['android', 'web']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Get metadata
            original_title = info.get('title', 'Unknown_Song')
            title = sanitize(original_title)
            duration = info.get('duration', 0)
            duration_str = f"{duration//60}:{duration%60:02d}" if duration > 0 else "N/A"
            
            # Get thumbnail
            thumbnail_url = info.get('thumbnail', '')
            image_data = b''
            if thumbnail_url:
                try:
                    req = urllib.request.Request(
                        thumbnail_url,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    with urllib.request.urlopen(req) as response:
                        image_data = response.read()
                except Exception as e:
                    print(f"Thumbnail download failed: {e}")

            # Read WebM audio data
            with open(filename, 'rb') as f:
                audio_data = f.read()

            # Create metadata
            metadata = {
                "title": original_title,
                "artist": info.get("uploader", "Unknown Artist"),
                "audioType": "audio/webm",
                "imageType": "image/jpeg" if image_data else None,
                "duration": duration_str,
                "source": "YouTube",
                "createdAt": datetime.now().isoformat(),
                "version": 1
            }

            # Create M3EW file
            m3ew_data = create_m3ew_file(metadata, image_data, audio_data)
            m3ew_path = os.path.join(folder_path, f"{title}.m3ew")
            with open(m3ew_path, 'wb') as f:
                f.write(m3ew_data)

            # Upload to Cloudinary with chunking
            cloudinary_url = upload_large_file(m3ew_path, public_id=title)

            # Add to Firestore if successful
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
                    'audioType': 'audio/webm',
                    'imageType': 'image/jpeg' if image_data else None,
                    'version': 1
                }
                
                if add_to_firestore(song_data) and doc_id:
                    update_waiting_document(doc_id, {
                        'finished': True,
                        'cloudinaryUrl': cloudinary_url,
                        'completedAt': datetime.now()
                    })

            return {
                'status': 'success',
                'title': original_title,
                'artist': info.get("uploader", "Unknown Artist"),
                'duration': duration_str,
                'local_paths': {
                    'webm': filename,
                    'thumbnail': thumbnail_url,
                    'm3ew': m3ew_path
                },
                'cloudinary_url': cloudinary_url
            }

    except Exception as e:
        return {'status': 'error', 'message': str(e)}

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
                result = download_webm_and_thumbnail(url, folder_path, doc.id)
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

@app.route('/api/download', methods=['POST', 'OPTIONS'])
def api_download():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    data = request.get_json()
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
    
    result = download_webm_and_thumbnail(youtube_url, folder_path)
    response = jsonify(result)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route('/api/check_waiting', methods=['POST', 'OPTIONS'])
def api_check_waiting():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    folder_path = request.get_json().get('folder_path', os.path.join(os.getcwd(), "YouTube_Downloads"))
    result = check_waiting_songs(folder_path)
    response = jsonify(result)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route('/api/download_file', methods=['GET', 'OPTIONS'])
def api_download_file():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'GET')
        return response
    
    file_path = request.args.get('path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    
    try:
        return send_file(
            file_path,
            as_attachment=True,
            download_name=os.path.basename(file_path))
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

if __name__ == '__main__':
    # Start background thread when app starts
    threading.Thread(target=background_task, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
