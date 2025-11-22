"""
Flask Web Interface for TikTok Scraper
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, Response, stream_with_context
import queue
import os
import json
import threading
import time
import requests
import random
import traceback
from datetime import datetime
from urllib.parse import unquote
from main import (
    get_user_dir,
    get_history_file,
    load_history,
    get_video_links,
    download_video,
    save_to_history,
    save_links_to_file,
    is_slideshow,
    save_to_slideshows
)

app = Flask(__name__)

# Store background tasks
active_tasks = {}

# --- Configuration Telegram ---
def load_config():
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

config = load_config()
TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = config.get("TELEGRAM_CHAT_ID")

# --- ARCHITECTURE LOGGING ---

# 1. La file d'attente globale (Thread-safe)
log_queue = queue.Queue()

def emit_log(message, level="info"):
    """
    Fonction helper pour pousser un log dans la queue.
    Levels: 'info' (gris), 'success' (vert), 'error' (rouge), 'warning' (jaune)
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    data = {
        "message": message,
        "level": level,
        "time": timestamp
    }
    log_queue.put(data)

# 2. Route SSE (Générateur)
@app.route('/stream_logs')
def stream_logs():
    def generate():
        while True:
            try:
                # On attend un message (bloquant, mais dans un thread géré par Flask)
                # timeout=1 permet de vérifier régulièrement si le client est toujours là
                data = log_queue.get(timeout=1)
                
                # Format SSE standard : "data: <json>\n\n"
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                # Si pas de log, on envoie un heartbeat (commentaire) pour garder la connexion active
                yield ": keep-alive\n\n"
            except GeneratorExit:
                # Le client s'est déconnecté
                break

    # stream_with_context est important si on accède à des variables de config Flask
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/')
def index():
    """Main dashboard page"""
    profiles = get_all_profiles()
    return render_template('index.html', profiles=profiles)

@app.route('/profile/<username>')
def profile_details(username):
    """Profile details page"""
    profile_data = get_profile_data(username)
    return render_template('profile.html', profile=profile_data)

@app.route('/video/<username>/<path:filename>')
def serve_video(username, filename):
    """Serve video files for playback"""
    # Decode URL-encoded characters
    filename = unquote(filename)
    username = unquote(username)

    # Security: prevent path traversal
    if '..' in username or '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid path'}), 400

    user_dir = get_user_dir(username)

    # Try to find the file (exact match first)
    file_path = os.path.join(user_dir, filename)

    if not os.path.exists(file_path):
        # Try to find a similar file (in case of encoding issues)
        if os.path.exists(user_dir):
            # Get all mp4 files
            files = [f for f in os.listdir(user_dir) if f.endswith('.mp4')]

            # Try to match by ID (most reliable)
            # Extract ID from requested filename (format: *_ID.mp4 or *[ID].mp4)
            import re
            id_match = re.search(r'_(\d{19})\.mp4$|[\[\(](\d{19})[\]\)]\.mp4$', filename)
            if id_match:
                video_id = id_match.group(1) or id_match.group(2)
                # Find file with this ID
                for f in files:
                    if video_id in f:
                        file_path = os.path.join(user_dir, f)
                        filename = f  # Update filename to the actual file
                        break

    if not os.path.exists(file_path):
        return jsonify({'error': 'Video not found', 'requested': filename}), 404

    return send_from_directory(user_dir, filename)

@app.route('/api/profiles')
def get_profiles():
    """Get list of all profiles (JSON)"""
    return jsonify(get_all_profiles())

@app.route('/api/extract', methods=['POST'])
def extract_links():
    """Extract video links for a profile (Background Task)"""
    data = request.json
    username = data.get('username')
    platform = data.get('platform', 'tiktok')
    limit = data.get('limit')

    if not username:
        return jsonify({'error': 'Username required'}), 400

    thread = threading.Thread(target=background_extract_task, args=(username, platform, limit))
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": f"Scan lancé pour {username}"})

@app.route('/api/download', methods=['POST'])
def start_download():
    """Start downloading videos in background"""
    data = request.json
    username = data.get('username')
    platform = data.get('platform', 'tiktok')
    limit = data.get('limit')
    min_sleep = int(data.get('min_sleep', 5))
    max_sleep = int(data.get('max_sleep', 15))
    force_update = data.get('force_update', False)

    if not username:
        return jsonify({'error': 'Username required'}), 400

    thread = threading.Thread(target=background_download_task, args=(username, platform, min_sleep, max_sleep, force_update))
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "message": f"Téléchargement lancé pour {username}"})

@app.route('/api/task/<task_id>')
def get_task_status(task_id):
    """Get status of a background task"""
    if task_id in active_tasks:
        return jsonify(active_tasks[task_id])
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/profile/<username>/delete', methods=['DELETE'])
def delete_profile(username):
    """Delete a profile and its data"""
    user_dir = get_user_dir(username)

    if os.path.exists(user_dir):
        import shutil
        shutil.rmtree(user_dir)
        return jsonify({'success': True, 'message': f'Profile {username} deleted'})

    return jsonify({'error': 'Profile not found'}), 404

@app.route('/api/video/<username>/<filename>/delete', methods=['DELETE'])
def delete_video(username, filename):
    """Delete a single video and remove its ID from history"""
    from urllib.parse import unquote
    import re

    # Decode URL-encoded characters
    filename = unquote(filename)
    username = unquote(username)

    # Security: prevent path traversal
    if '..' in username or '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({'error': 'Invalid path'}), 400

    user_dir = get_user_dir(username)
    file_path = os.path.join(user_dir, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': 'Video not found'}), 404

    try:
        # Extract video ID from filename
        # Format: YYYYMMDD_username_ID.ext
        id_match = re.search(r'_(\d{19})\.mp4$', filename)
        video_id = id_match.group(1) if id_match else None

        # Delete the video file
        os.remove(file_path)

        # Remove ID from history if found
        if video_id:
            history = load_history(username)
            if video_id in history:
                history.remove(video_id)
                # Save updated history
                history_file = get_history_file(username)
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, indent=4)

        return jsonify({
            'success': True,
            'message': f'Video {filename} deleted',
            'video_id': video_id
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """Get global statistics"""
    profiles = get_all_profiles()
    total_videos = sum(p['video_count'] for p in profiles)
    total_size = calculate_total_size()

    return jsonify({
        'total_profiles': len(profiles),
        'total_videos': total_videos,
        'total_size': total_size,
        'total_size_gb': round(total_size / (1024**3), 2)
    })

# Helper functions

def get_all_profiles():
    """Get list of all profiles with metadata"""
    profiles = []
    downloads_dir = 'downloads'

    if os.path.exists(downloads_dir):
        for username in os.listdir(downloads_dir):
            user_dir = os.path.join(downloads_dir, username)
            if os.path.isdir(user_dir) and username != '.gitkeep':
                history = load_history(username)

                # Get last scan time from history file
                history_file = get_history_file(username)
                last_scan = None
                if os.path.exists(history_file):
                    last_scan = datetime.fromtimestamp(
                        os.path.getmtime(history_file)
                    ).strftime('%Y-%m-%d %H:%M:%S')

                profiles.append({
                    'username': username,
                    'video_count': len(history),
                    'last_scan': last_scan,
                    'status': 'idle'
                })

    return profiles

def get_profile_data(username):
    """Get detailed data for a specific profile"""
    history = load_history(username)
    user_dir = get_user_dir(username)

    # Get video files
    videos = []
    if os.path.exists(user_dir):
        for file in os.listdir(user_dir):
            if file.endswith('.mp4'):
                file_path = os.path.join(user_dir, file)
                file_size = os.path.getsize(file_path)
                videos.append({
                    'filename': file,
                    'size': file_size,
                    'size_mb': round(file_size / (1024**2), 2),
                    'date': datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    ).strftime('%Y-%m-%d %H:%M:%S')
                })

    # Sort by date (most recent first)
    videos.sort(key=lambda x: x['date'], reverse=True)

    return {
        'username': username,
        'video_count': len(history),
        'downloaded_count': len(videos),
        'videos': videos
    }

def calculate_total_size():
    """Calculate total size of all downloaded videos"""
    total_size = 0
    downloads_dir = 'downloads'

    if os.path.exists(downloads_dir):
        for username in os.listdir(downloads_dir):
            user_dir = os.path.join(downloads_dir, username)
            if os.path.isdir(user_dir):
                for file in os.listdir(user_dir):
                    if file.endswith('.mp4'):
                        file_path = os.path.join(user_dir, file)
                        total_size += os.path.getsize(file_path)

    return total_size

# --- Telegram Helpers ---
def get_or_create_topic(topic_name):
    """
    Vérifie si un topic existe pour ce nom, sinon le crée.
    Retourne le message_thread_id.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    mapping_file = "telegram_topics.json"
    mapping = {}
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, "r") as f:
                mapping = json.load(f)
        except:
            pass

    if topic_name in mapping:
        return mapping[topic_name]

    # Création du topic
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createForumTopic"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "name": topic_name
    }
    
    try:
        response = requests.post(url, json=data)
        resp_data = response.json()
        
        if resp_data.get("ok"):
            thread_id = resp_data["result"]["message_thread_id"]
            # Sauvegarde du mapping
            mapping[topic_name] = thread_id
            with open(mapping_file, "w") as f:
                json.dump(mapping, f)
            emit_log(f"Topic Telegram créé pour {topic_name} (ID: {thread_id})", "success")
            return thread_id
        else:
            emit_log(f"Erreur création topic Telegram: {resp_data.get('description')}", "error")
            return None
    except Exception as e:
        emit_log(f"Erreur connexion Telegram: {e}", "error")
        return None

def send_telegram_video(video_path, caption, topic_name):
    """Envoie une vidéo dans le topic dédié."""
    thread_id = get_or_create_topic(topic_name)
    if not thread_id:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    
    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "message_thread_id": thread_id,
                "caption": caption
            }
            response = requests.post(url, data=data, files=files)
            
        if response.json().get("ok"):
            emit_log(f"Vidéo envoyée sur Telegram ({topic_name})", "success")
        else:
            emit_log(f"Échec envoi Telegram: {response.json().get('description')}", "error")
    except Exception as e:
        emit_log(f"Erreur envoi Telegram: {e}", "error")


# --- BACKGROUND TASKS ---

def background_extract_task(username, platform, limit):
    emit_log(f"Démarrage du scan pour {username}...", "info")
    try:
        history = load_history(username)
        
        # On passe un callback custom à get_video_links si on modifie main.py, 
        # sinon on log juste le début et la fin
        def log_wrapper(msg, level="info"):
            emit_log(msg, level)

        videos = get_video_links(username, history, platform, limit, callback_log=log_wrapper)

        if videos:
            save_links_to_file(username, videos)
            emit_log(f"Scan terminé : {len(videos)} nouvelles vidéos trouvées.", "success")
        else:
            emit_log("Scan terminé : Aucune nouvelle vidéo.", "warning")
            
    except Exception as e:
        emit_log(f"Erreur lors du scan : {str(e)}", "error")

def background_download_task(username, platform, min_sleep, max_sleep, force_update=False):
    """Background task to run the download process."""
    global active_tasks
    active_tasks[username] = "running"
    
    try:
        emit_log(f"Starting background download task for {username}...", "info")
        
        # Ensure user directory exists
        user_dir = get_user_dir(username)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
            emit_log(f"Created directory: {user_dir}", "info")

        # Load history
        history = load_history(username)
        emit_log(f"Loaded history with {len(history)} videos.", "info")
        
        if force_update:
            emit_log("⚠️ FORCE UPDATE MODE ENABLED: Will scan all videos.", "warning")

        # Define a callback for logging from main.py
        def log_callback(msg, level="info"):
            emit_log(msg, level)

        # 1. Extract Links
        emit_log(f"Extracting links from {platform}...", "info")
        videos = get_video_links(
            username, 
            history, 
            platform, 
            limit=None, 
            callback_log=log_callback,
            force_update=force_update
        )
        
        if not videos:
            emit_log("No new videos found to download.", "warning")
            active_tasks[username] = "done"
            return

        emit_log(f"Found {len(videos)} new videos. Saving list...", "success")
        save_links_to_file(username, videos)

        # 2. Download Videos
        emit_log(f"Starting download of {len(videos)} videos...", "info")
        
        for i, video in enumerate(videos):
            if active_tasks.get(username) == "stopping":
                emit_log(f"Arrêt demandé pour {username}.", "warning")
                break

            video_id = video['id']
            video_url = video['url']
            
            # Double check history (unless force update, but main.py handles list)
            if video_id in history and not force_update:
                continue
            
            emit_log(f"Processing ({i+1}/{len(videos)}): {video_url}", "info")
            
            # Check slideshow
            if is_slideshow(video_url):
                emit_log("Slideshow detected - saving to JSON (skip download)", "warning")
                save_to_slideshows(username, video_url, video_id)
                save_to_history(username, video_id)
                continue

            # Simulation de délai humain
            sleep_time = random.uniform(min_sleep, max_sleep)
            time.sleep(sleep_time)

            success = download_video(video_url, username, video_id)
            
            if success:
                emit_log(f"Downloaded: {video_url}", "success")
                save_to_history(username, video_id)
                
                # --- INTEGRATION TELEGRAM ---
                # On cherche le fichier téléchargé (on suppose que download_video a utilisé le format standard)
                # Le plus simple est de lister les fichiers récents ou de modifier download_video pour retourner le nom
                # Ici on va scanner le dossier pour trouver le fichier correspondant à l'ID
                try:
                    found_file = None
                    for f in os.listdir(user_dir):
                        if video_id in f and f.endswith(".mp4"):
                            found_file = os.path.join(user_dir, f)
                            break
                    
                    if found_file:
                        send_telegram_video(found_file, f"Nouveau TikTok de @{username} !\n{video_url}", username)
                except Exception as e:
                    emit_log(f"Erreur post-traitement Telegram: {e}", "error")
                # ----------------------------

            else:
                emit_log(f"Failed to download: {video_url}", "error")

        emit_log("Background task completed!", "success")

    except Exception as e:
        emit_log(f"Task failed: {str(e)}", "error")
        traceback.print_exc()
    finally:
        if active_tasks.get(username) != "stopping":
            active_tasks[username] = "done"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)