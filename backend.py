from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import json
from datetime import datetime
import shutil
import subprocess

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = '/storage/emulated/0/DCIM/Rick'
GALLERY_DIR = '/storage/emulated/0/DCIM/Camera'
HISTORY_FILE = '/storage/emulated/0/DCIM/Rick/history.json'
THUMBNAILS_DIR = '/storage/emulated/0/DCIM/Rick/thumbnails'
STATS_FILE = '/storage/emulated/0/DCIM/Rick/stats.json'
SETTINGS_FILE = '/storage/emulated/0/DCIM/Rick/settings.json'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(GALLERY_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

download_progress = {}

def auto_update_ytdlp():
    try:
        print("🔄 Actualizando yt-dlp...")
        subprocess.run(['pip', 'install', '--upgrade', 'yt-dlp', '--break-system-packages'], 
                      capture_output=True, timeout=30)
        version = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
        print(f"✅ yt-dlp: {version.stdout.strip()}")
    except Exception as e:
        print(f"⚠️ No se actualizó: {e}")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'auto_download': False, 'download_mode': 'turbo'}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

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

def extract_thumbnail(video_path, output_path):
    try:
        cmd = f'ffmpeg -i "{video_path}" -ss 00:00:01 -vframes 1 -vf scale=320:-1 "{output_path}" -y 2>/dev/null'
        subprocess.run(cmd, shell=True, timeout=10)
        return os.path.exists(output_path)
    except:
        return False

def progress_hook(d):
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        if total > 0:
            percent = (downloaded / total) * 100
            speed = d.get('speed', 0)
            download_progress['percent'] = round(percent, 1)
            download_progress['speed'] = f"{speed/1024/1024:.2f} MB/s" if speed else "0 MB/s"
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

    download_progress.clear()
    download_progress['percent'] = 0

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

    if 'tiktok' in url.lower() or 'vm.tiktok' in url.lower():
        print(f"🎵 Descargando TikTok: {url}")
        ydl_opts.update({
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.tiktok.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            },
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                }
            },
        })
    elif 'youtube' in url.lower() or 'youtu.be' in url.lower():
        print(f"▶️ Descargando YouTube: {url}")
        format_map = {
            'best': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
            '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
            '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
        }
        ydl_opts.update({
            'format': format_map.get(quality, format_map['best']),
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'concurrent_fragment_downloads': fragments,
            'http_chunk_size': 10485760,
        })
    elif 'facebook' in url.lower() or 'fb.' in url.lower():
        print(f"f Descargando Facebook: {url}")
        ydl_opts.update({
            'format': 'best',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
        })
    
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
                possible_files = [
                    os.path.join(DOWNLOAD_DIR, f"{title}_{timestamp}.mp4"),
                    os.path.join(DOWNLOAD_DIR, f"{title}_{timestamp}.webm"),
                    os.path.join(DOWNLOAD_DIR, f"{title}_{timestamp}.mkv"),
                ]
                for pf in possible_files:
                    if os.path.exists(pf):
                        filepath = pf
                        filename = os.path.basename(pf)
                        break
            
            if not os.path.exists(filepath):
                return jsonify({'error': 'Archivo no encontrado'}), 500
            
            if not audio_only:
                thumbnail_name = f"{filename}.jpg"
                thumbnail_path = os.path.join(THUMBNAILS_DIR, thumbnail_name)
                extract_thumbnail(filepath, thumbnail_path)
                
                try:
                    gallery_path = os.path.join(GALLERY_DIR, filename)
                    shutil.copy2(filepath, gallery_path)
                    in_gallery = True
                except:
                    in_gallery = False
            else:
                thumbnail_path = ''
                in_gallery = False
            
            filesize = os.path.getsize(filepath)
            duration = info.get('duration', 0)
            
            platform = 'YouTube' if 'youtube' in url or 'youtu.be' in url else ('TikTok' if 'tiktok' in url else 'Facebook')
            update_stats(platform, filesize / (1024*1024), audio_only)

            history_item = {
                'title': title,
                'filename': filename,
                'filepath': filepath,
                'thumbnail': thumbnail_path,
                'url': url,
                'original_url': url,
                'size': f"{filesize / (1024*1024):.2f} MB",
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'platform': platform,
                'type': 'Audio MP3' if audio_only else 'Video',
                'in_gallery': in_gallery
            }
            save_history(history_item)

            print(f"✅ Descargado: {filename}")
            return jsonify({'success': True, 'title': title, 'filename': filename})
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error: {error_msg}")
        
        if 'private' in error_msg.lower() or 'not available' in error_msg.lower():
            return jsonify({'error': 'Video privado o no disponible'}), 500
        elif 'geo' in error_msg.lower():
            return jsonify({'error': 'Video bloqueado en tu región'}), 500
        else:
            return jsonify({'error': f'Error: {error_msg[:100]}'}), 500

@app.route('/copy-to-gallery/<path:filename>', methods=['POST'])
def copy_to_gallery(filename):
    try:
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.exists(filepath):
            gallery_path = os.path.join(GALLERY_DIR, filename)
            shutil.copy2(filepath, gallery_path)
            
            history = load_history()
            for item in history:
                if item.get('filename') == filename:
                    item['in_gallery'] = True
                    break
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
            os.remove(filepath)
            
            thumbnail_path = os.path.join(THUMBNAILS_DIR, f"{filename}.jpg")
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            
            return jsonify({'success': True})
        return jsonify({'error': 'Not found'}), 404
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

@app.route('/settings', methods=['GET'])
def get_settings():
    return jsonify(load_settings())

@app.route('/settings', methods=['POST'])
def update_settings():
    data = request.json
    settings = load_settings()
    settings.update(data)
    save_settings(settings)
    return jsonify({'success': True})

@app.route('/history/delete/<int:index>', methods=['DELETE'])
def delete_history(index):
    history = load_history()
    if 0 <= index < len(history):
        history.pop(index)
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f)
        return jsonify({'success': True})
    return jsonify({'error': 'Error'}), 400

@app.route('/history/clear', methods=['DELETE'])
def clear_history():
    with open(HISTORY_FILE, 'w') as f:
        json.dump([], f)
    return jsonify({'success': True})

@app.route('/files')
def get_files():
    try:
        files = []
        if os.path.exists(DOWNLOAD_DIR):
            for filename in os.listdir(DOWNLOAD_DIR):
                if filename.endswith(('.mp4', '.mp3', '.webm', '.mkv')) and not filename.endswith('.json'):
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        thumbnail_name = f"{filename}.jpg"
                        thumbnail_path = os.path.join(THUMBNAILS_DIR, thumbnail_name)
                        
                        platform = 'YouTube' if 'youtube' in filename.lower() else ('TikTok' if 'tiktok' in filename.lower() else 'Facebook')
                        
                        history = load_history()
                        in_gallery = False
                        for item in history:
                            if item.get('filename') == filename:
                                in_gallery = item.get('in_gallery', False)
                                break
                        
                        files.append({
                            'name': filename,
                            'size': f"{stat.st_size / (1024*1024):.2f} MB",
                            'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                            'thumbnail': thumbnail_path if os.path.exists(thumbnail_path) else '',
                            'type': 'Audio' if filename.endswith('.mp3') else 'Video',
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

@app.route('/thumbnail/<path:filename>')
def get_thumbnail(filename):
    thumbnail_path = os.path.join(THUMBNAILS_DIR, filename)
    if os.path.exists(thumbnail_path):
        return send_file(thumbnail_path)
    return jsonify({'error': 'Not found'}), 404

@app.route('/test')
def test():
    return jsonify({'status': 'OK', 'version': 'RICK_V2_FINAL'})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 RICK DOWNLOADER V2.0 - INICIANDO")
    print("="*60)
    auto_update_ytdlp()
    print("\n✅ Backend: http://localhost:5000")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
