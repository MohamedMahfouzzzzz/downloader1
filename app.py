from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import uuid

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins; customize as needed

@app.route('/')
def index():
    return '✅ yt-dlp API is running!'

@app.route('/download', methods=['POST', 'OPTIONS'])
def download_video():
    if request.method == 'OPTIONS':
        # Preflight request response (CORS)
        return '', 204

    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    filename = f"{uuid.uuid4()}.mp4"

    ydl_opts = {
        'format': 'best',
        'outtmpl': filename,
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return jsonify({'message': 'Downloaded', 'file': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
