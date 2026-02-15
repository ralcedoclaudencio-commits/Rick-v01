from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import json
from datetime import datetime
import shutil
import subprocess

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DOWNLOAD_DIR = '/storage/emulated/0/DCIM/Rick'
GALLERY_DIR = '/storage/emulated/0/DCIM/Camera'
HISTORY_FILE = '/storage/emulated/0/DCIM/Rick/history.json'
STATS_FILE = '/storage/emulated/0/DCIM/Rick/stats.json'
THUMB_DIR = '/storage/emulated/0/DCIM/Rick/.thumbnails'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(GALLERY_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

download_progress = {}

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'total_downloads': 0, 'total_mb': 0, 'platforms': {'YouTube': 0, 'TikTok': 0, 'Facebook': 0}, 'audio_only': 0}

def save_stats(stats):
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def update_stats(platform, size_mb, is_audio=False):
    stats = load_stats()
    stats['total_downloads'] += 1
    stats['total_mb'] += size_mb
    if platform in stats['platforms']:
        stats['platforms'][platform] += 1
    if is_audio:
        stats['audio_only'] += 1
    save_stats(stats)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(item):
    history = load_history()
    history.insert(0, item)
    history = history[:100]
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def generate_thumbnail(video_path, filename):
    try:
        thumb_path = os.path.join(THUMB_DIR, filename + '.jpg')
        cmd = ['ffmpeg', '-i', video_path, '-ss', '00:00:01', '-vframes', '1', '-vf', 'scale=120:90', thumb_path, '-y']
        subprocess.run(cmd, capture_output=True, timeout=10)
        return thumb_path if os.path.exists(thumb_path) else None
    except:
        return None

def progress_hook(d):
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        if total > 0:
            percent = (downloaded / total) * 100
            speed = d.get('speed', 0)
            download_progress['percent'] = round(percent, 1)
            download_progress['speed'] = f"{speed/1024/1024:.2f} MB/s" if speed else "0 MB/s"
            download_progress['downloaded_mb'] = round(downloaded/1024/1024, 1)
            download_progress['total_mb'] = round(total/1024/1024, 1)
    elif d['status'] == 'finished':
        download_progress['percent'] = 100

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    quality = data.get('quality', 'best')
    audio_only = data.get('audio_only', False)
    mode = data.get('mode', 'turbo')

    if not url:
        return jsonify({'error': 'No URL'}), 400

    if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
        platform = 'YouTube'
    elif 'tiktok' in url.lower():
        platform = 'TikTok'
    elif 'facebook' in url.lower():
        platform = 'Facebook'
    else:
        platform = 'Unknown'

    download_progress.clear()
    download_progress['percent'] = 0
    download_progress['downloaded_mb'] = 0
    download_progress['total_mb'] = 0

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    fragments = 32 if mode == 'pro' else 16
    
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_{timestamp}.%(ext)s',
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
        'retries': 20,
        'fragment_retries': 20,
    }

    if platform == 'TikTok':
        ydl_opts.update({
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.tiktok.com/',
            },
        })
    elif platform == 'YouTube':
        format_map = {
            'best': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
            '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
            '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
        }
        ydl_opts.update({
            'format': format_map.get(quality, format_map['best']),
            'concurrent_fragment_downloads': fragments,
        })
    elif platform == 'Facebook':
        ydl_opts.update({'format': 'best'})
    
    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Video')
            ext = 'mp3' if audio_only else info.get('ext', 'mp4')
            filename = f"{title}_{timestamp}.{ext}"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            if not os.path.exists(filepath):
                possible = [f"{title}_{timestamp}.mp4", f"{title}_{timestamp}.webm", f"{title}_{timestamp}.mkv"]
                for pf in possible:
                    full_path = os.path.join(DOWNLOAD_DIR, pf)
                    if os.path.exists(full_path):
                        filepath = full_path
                        filename = pf
                        break
            
            if not os.path.exists(filepath):
                return jsonify({'error': 'Archivo no encontrado'}), 500
            
            if not audio_only:
                generate_thumbnail(filepath, filename)
                try:
                    gallery_path = os.path.join(GALLERY_DIR, filename)
                    shutil.copy2(filepath, gallery_path)
                    in_gallery = True
                except:
                    in_gallery = False
            else:
                in_gallery = False
            
            filesize = os.path.getsize(filepath)
            update_stats(platform, filesize / (1024*1024), audio_only)

            history_item = {
                'title': title,
                'filename': filename,
                'filepath': filepath,
                'url': url,
                'original_url': url,
                'size': f"{filesize / (1024*1024):.2f} MB",
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'platform': platform,
                'type': 'Audio MP3' if audio_only else 'Video',
                'in_gallery': in_gallery
            }
            save_history(history_item)

            return jsonify({'success': True, 'title': title, 'filename': filename})
            
    except Exception as e:
        return jsonify({'error': str(e)[:100]}), 500

@app.route('/thumbnail/<path:filename>')
def get_thumbnail(filename):
    thumb_path = os.path.join(THUMB_DIR, filename + '.jpg')
    if os.path.exists(thumb_path):
        return send_file(thumb_path, mimetype='image/jpeg')
    return '', 404

@app.route('/copy-to-gallery/<path:filename>', methods=['POST'])
def copy_to_gallery(filename):
    try:
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(filepath):
            shutil.copy2(filepath, os.path.join(GALLERY_DIR, filename))
            history = load_history()
            for item in history:
                if item.get('filename') == filename:
                    item['in_gallery'] = True
            with open(HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=2)
            return jsonify({'success': True})
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(filepath):
            filesize = os.path.getsize(filepath) / (1024*1024)
            os.remove(filepath)
            
            thumb_path = os.path.join(THUMB_DIR, filename + '.jpg')
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            
            gallery_path = os.path.join(GALLERY_DIR, filename)
            if os.path.exists(gallery_path):
                os.remove(gallery_path)
            
            stats = load_stats()
            stats['total_downloads'] = max(0, stats['total_downloads'] - 1)
            stats['total_mb'] = max(0, stats['total_mb'] - filesize)
            save_stats(stats)
            
            history = load_history()
            history = [h for h in history if h.get('filename') != filename]
            with open(HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=2)
            
            return jsonify({'success': True})
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete-history-item', methods=['POST'])
def delete_history_item():
    try:
        data = request.json
        index = data.get('index')
        history = load_history()
        if 0 <= index < len(history):
            history.pop(index)
            with open(HISTORY_FILE, 'w') as f:
                json.dump(history, f, indent=2)
            return jsonify({'success': True})
        return jsonify({'error': 'Invalid index'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete-download-info/<path:filename>', methods=['DELETE'])
def delete_download_info(filename):
    try:
        history = load_history()
        history = [h for h in history if h.get('filename') != filename]
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/progress')
def get_progress():
    return jsonify(download_progress)

@app.route('/history')
def get_history():
    return jsonify(load_history())

@app.route('/stats')
def get_stats():
    return jsonify(load_stats())

@app.route('/files')
def get_files():
    try:
        file_type = request.args.get('type', 'all')
        files = []
        history = load_history()
        
        if os.path.exists(DOWNLOAD_DIR):
            for filename in os.listdir(DOWNLOAD_DIR):
                is_video = filename.endswith(('.mp4', '.webm', '.mkv'))
                is_audio = filename.endswith('.mp3')
                
                if file_type == 'video' and not is_video:
                    continue
                if file_type == 'audio' and not is_audio:
                    continue
                if file_type == 'all' and not (is_video or is_audio):
                    continue
                
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    
                    platform = 'Unknown'
                    in_gallery = False
                    for item in history:
                        if item.get('filename') == filename:
                            platform = item.get('platform', 'Unknown')
                            in_gallery = item.get('in_gallery', False)
                            break
                    
                    files.append({
                        'name': filename,
                        'size': f"{stat.st_size / (1024*1024):.2f} MB",
                        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                        'type': 'Audio' if is_audio else 'Video',
                        'platform': platform,
                        'in_gallery': in_gallery
                    })
        files.sort(key=lambda x: x['date'], reverse=True)
        return jsonify(files)
    except:
        return jsonify([])

@app.route('/open/<path:filename>')
def open_file(filename):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return jsonify({'error': 'Not found'}), 404

@app.route('/clear-history', methods=['POST'])
def clear_history():
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump([], f)
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Failed'}), 500

@app.route('/clear-downloads-info', methods=['POST'])
def clear_downloads_info():
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump([], f)
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Failed'}), 500

@app.route('/test')
def test():
    return jsonify({'status': 'OK'})

if __name__ == '__main__':
    print("\n"+"="*50)
    print("🚀 RICK PRO V3.0 - SISTEMA INICIADO")
    print("="*50)
    print(f"📁 Directorio: {DOWNLOAD_DIR}")
    print(f"📸 Galería: {GALLERY_DIR}")
    print("🌐 Servidor: http://localhost:5000")
    print("🖥️  Web: http://localhost:8080")
    print("="*50+"\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
