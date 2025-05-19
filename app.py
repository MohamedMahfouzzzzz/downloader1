from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp as ytdlp
import tempfile
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all domains

@app.route('/')
def home():
    return "YT-DLP Video Downloader API is running."

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Missing URL'}), 400

    url = data['url']

    ydl_opts = {
        'format': 'best',  # best video+audio
        'noplaylist': True,
        'quiet': True,
        'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
        'no_warnings': True,
        'ignoreerrors': True,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
    }

    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            if info_dict is None:
                return jsonify({'error': 'Could not extract info'}), 500

            filename = ydl.prepare_filename(info_dict)
            if not os.path.exists(filename):
                return jsonify({'error': 'File not found after download'}), 500

            # Send file as attachment
            return send_file(filename, as_attachment=True, download_name=os.path.basename(filename))

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
