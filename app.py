from flask import Flask, request, send_file, jsonify
import yt_dlp
import os
import tempfile

app = Flask(__name__)

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Missing URL'}), 400

    # Temporary directory for download
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tmpdir, '%(title)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)
            
            # Send the downloaded file back to client
            return send_file(filepath, as_attachment=True)
        except Exception as e:
            return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
