import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "YT-DLP Video Downloader API is running."

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing URL in request body'}), 400

    url = data['url']
    ydl_opts = {
        'format': 'best',
        'outtmpl': tempfile.gettempdir() + '/%(title)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # Send the downloaded file to client
        return send_file(filename, as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
