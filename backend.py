from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import json
from datetime import datetime
import tempfile

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = tempfile.gettempdir()
download_progress = {}
download_history = []

def progress_hook(d):
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        if total > 0:
            percent = (downloaded / total) * 100
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            download_progress['percent'] = round(percent, 1)
            download_progress['speed'] = f"{speed/1024/1024:.2f} MB/s" if speed else "0 MB/s"
            download_progress['eta'] = f"{eta//60}:{eta%60:02d}" if eta else "0:00"
    elif d['status'] == 'finished':
        download_progress['percent'] = 100

@app.route('/')
def home():
    return jsonify({'status': 'Rick Backend API', 'version': '1.0'})

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    quality = data.get('quality', 'best')
    
    if not url:
        return jsonify({'error': 'No URL'}), 400
    
    download_progress.clear()
    download_progress['percent'] = 0
    
    format_map = {
        'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
        '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
        '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
        '360p': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]'
    }
    
    filename = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    ydl_opts = {
        'format': format_map.get(quality, 'best'),
        'outtmpl': filepath,
        'no_mtime': True,
        'progress_hooks': [progress_hook],
        'quiet': False,
    }
    
    if 'tiktok' in url:
        ydl_opts['format'] = 'best[ext=mp4]'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Video')
            filesize = info.get('filesize', 0) or info.get('filesize_approx', 0)
            duration = info.get('duration', 0)
            
            history_item = {
                'title': title,
                'url': url,
                'size': f"{filesize / (1024*1024):.2f} MB" if filesize else "N/A",
                'duration': f"{duration//60}:{duration%60:02d}" if duration else "N/A",
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'platform': 'YouTube' if 'youtube' in url else ('TikTok' if 'tiktok' in url else 'Facebook'),
                'download_url': f"/file/{filename}"
            }
            download_history.insert(0, history_item)
            
            return jsonify({
                'success': True,
                'title': title,
                'filename': filename,
                'download_url': f"/file/{filename}"
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/file/<filename>')
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/progress', methods=['GET'])
def get_progress():
    return jsonify(download_progress)

@app.route('/history', methods=['GET'])
def get_history():
    return jsonify(download_history)

@app.route('/support', methods=['POST'])
def support():
    return jsonify({'success': True, 'message': 'Mensaje recibido'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
