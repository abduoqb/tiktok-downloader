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

# Verrou pour protéger l'accès au fichier telegram_topics.json
telegram_topics_lock = threading.Lock()

# --- ARCHITECTURE LOGGING ---

# 1. La file d'attente globale (Thread-safe)
log_queue = queue.Queue()

def emit_log(message, level="info", module="SYSTEM"):
    """
    Fonction helper pour pousser un log dans la queue.
    Levels: 'info', 'success' (OK), 'error' (ERROR), 'warning' (WARN)
    Format: [HH:MM:SS] [NIVEAU] [MODULE] Message
    """
    timestamp = datetime.now().strftime("%H:%M:%S")

    # Mapping des niveaux vers des labels plus sobres
    level_map = {
        "info": "INFO",
        "success": "OK",
        "error": "ERROR",
        "warning": "WARN"
    }
    level_label = level_map.get(level, "INFO")

    # Format sobre : [HH:MM:SS] [NIVEAU] [MODULE] Message
    formatted_message = f"[{timestamp}] [{level_label}] [{module}] {message}"

    data = {
        "message": formatted_message,
        "level": level,
        "time": timestamp
    }
    log_queue.put(data)

def emit_stats_header(username, platform, total_videos, already_downloaded, new_videos, slideshows, mode, min_sleep, max_sleep, telegram_enabled):
    """Affiche les statistiques initiales avant le téléchargement"""
    separator = "═" * 68

    emit_log(separator, "info", "STATS")
    emit_log(f"STATISTIQUES DE TÉLÉCHARGEMENT - @{username}", "info", "STATS")
    emit_log(separator, "info", "STATS")
    emit_log("", "info", "STATS")

    emit_log("Profil:", "info", "STATS")
    emit_log(f"  Plateforme:                     {platform}", "info", "STATS")
    emit_log(f"  Vidéos sur le profil:           {total_videos}", "info", "STATS")
    emit_log(f"  Déjà téléchargées:              {already_downloaded}", "info", "STATS")
    emit_log(f"  Nouvelles détectées:            {new_videos}", "info", "STATS")
    if slideshows > 0:
        emit_log(f"  Slideshows (ignorés):           {slideshows}", "info", "STATS")
    emit_log("", "info", "STATS")

    emit_log("Configuration:", "info", "STATS")
    emit_log(f"  Mode:                           {mode}", "info", "STATS")
    emit_log(f"  Délais entre vidéos:            {min_sleep}-{max_sleep} secondes", "info", "STATS")
    emit_log(f"  Tentatives par vidéo:           3", "info", "STATS")
    emit_log(f"  Telegram:                       {'Activé (topic: ' + username + ')' if telegram_enabled else 'Désactivé'}", "info", "STATS")
    emit_log("", "info", "STATS")

    # Estimation du temps (environ 3-5s par vidéo + délais)
    avg_time_per_video = (min_sleep + max_sleep) / 2 + 3.5  # 3.5s avg download
    estimated_minutes = (new_videos * avg_time_per_video) / 60
    estimated_size = new_videos * 5  # Environ 5 MB par vidéo

    emit_log("Prévisions:", "info", "STATS")
    emit_log(f"  Vidéos à télécharger:           {new_videos}", "info", "STATS")
    emit_log(f"  Temps estimé:                   ~{int(estimated_minutes)}-{int(estimated_minutes * 1.3)} minutes", "info", "STATS")
    emit_log(f"  Taille estimée:                 ~{int(estimated_size * 0.8)}-{int(estimated_size * 1.2)} MB", "info", "STATS")
    emit_log("", "info", "STATS")
    emit_log(separator, "info", "STATS")

def emit_progress_bar(current, total, elapsed_seconds, total_size_mb, telegram_sent):
    """
    Affiche une barre de progression simple sur une ligne.
    Format: [##··] 17/170 (10%) | 4m23s | ~39m34s | 17.0 MB | 17 envoyées
    """
    # Calcul de la barre
    bar_length = 20
    filled = int((current / total) * bar_length) if total > 0 else 0
    bar = "#" * filled + "·" * (bar_length - filled)
    percentage = int((current / total) * 100) if total > 0 else 0

    # Calcul du temps restant
    if current > 0 and elapsed_seconds > 0:
        avg_time_per_video = elapsed_seconds / current
        remaining_videos = total - current
        remaining_seconds = int(remaining_videos * avg_time_per_video)
        remaining_time = f"~{remaining_seconds // 60}m{remaining_seconds % 60:02d}s"
    else:
        remaining_time = "calcul..."

    # Format du temps écoulé
    elapsed_time = f"{int(elapsed_seconds // 60)}m{int(elapsed_seconds % 60):02d}s"

    # Ligne unique simple
    if current == total:
        progress_line = f"[{bar}] {current}/{total} ({percentage}%) | {elapsed_time} | Terminé | {total_size_mb:.1f} MB | {telegram_sent} envoyées"
    else:
        progress_line = f"[{bar}] {current}/{total} ({percentage}%) | {elapsed_time} | {remaining_time} | {total_size_mb:.1f} MB | {telegram_sent} envoyées"

    emit_log(progress_line, "info", "PROGRESS")

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

@app.route('/api/telegram/topics', methods=['GET'])
def get_telegram_topics():
    """Get the current Telegram topics mapping"""
    mapping_file = "telegram_topics.json"
    mapping = {}
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, "r") as f:
                mapping = json.load(f)
        except:
            pass
    return jsonify(mapping)

@app.route('/api/telegram/topics', methods=['POST'])
def add_telegram_topic():
    """Manually add a Telegram topic mapping"""
    data = request.json
    topic_name = data.get('topic_name')
    thread_id = data.get('thread_id')

    if not topic_name or not thread_id:
        return jsonify({'error': 'topic_name and thread_id required'}), 400

    mapping_file = "telegram_topics.json"

    with telegram_topics_lock:
        mapping = {}
        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, "r") as f:
                    mapping = json.load(f)
            except:
                pass

        mapping[topic_name] = int(thread_id)

        try:
            with open(mapping_file, "w") as f:
                json.dump(mapping, f, indent=2)
            return jsonify({'success': True, 'message': f'Topic {topic_name} ajouté avec ID {thread_id}'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/telegram/topics/<topic_name>', methods=['DELETE'])
def delete_telegram_topic(topic_name):
    """Remove a Telegram topic mapping"""
    mapping_file = "telegram_topics.json"

    with telegram_topics_lock:
        mapping = {}
        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, "r") as f:
                    mapping = json.load(f)
            except:
                pass

        if topic_name in mapping:
            del mapping[topic_name]
            try:
                with open(mapping_file, "w") as f:
                    json.dump(mapping, f, indent=2)
                return jsonify({'success': True, 'message': f'Topic {topic_name} supprimé'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        else:
            return jsonify({'error': 'Topic not found'}), 404

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
    Thread-safe grâce au verrou telegram_topics_lock.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    mapping_file = "telegram_topics.json"

    # Utiliser un verrou pour éviter les race conditions
    with telegram_topics_lock:
        # Recharger le mapping à chaque fois (au cas où il a été modifié par un autre thread)
        mapping = {}
        if os.path.exists(mapping_file):
            try:
                with open(mapping_file, "r") as f:
                    mapping = json.load(f)
            except Exception as e:
                emit_log(f"Erreur lecture telegram_topics.json: {str(e)}", "warning")

        # Si le topic existe déjà dans notre mapping, le retourner
        if topic_name in mapping:
            # Pas de log pour éviter la verbosité
            return mapping[topic_name]

        # Le topic n'existe pas dans notre mapping, le créer
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
                # Sauvegarder le mapping
                mapping[topic_name] = thread_id
                try:
                    with open(mapping_file, "w") as f:
                        json.dump(mapping, f, indent=2)
                    # Pas de log, on laisse le message d'envoi de vidéo parler
                except Exception as e:
                    emit_log(f"Erreur sauvegarde mapping: {str(e)}", "warning", "TELEGRAM")
                return thread_id
            else:
                error_desc = resp_data.get('description', 'Unknown error')
                emit_log(f"Erreur création topic '{topic_name}': {error_desc}", "error", "TELEGRAM")
                return None
        except Exception as e:
            emit_log(f"Erreur connexion: {e}", "error", "TELEGRAM")
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
            # Le message de succès est géré dans background_download_task
            pass
        else:
            emit_log(f"Échec envoi: {response.json().get('description')}", "error", "TELEGRAM")
    except Exception as e:
        emit_log(f"Erreur envoi: {e}", "error", "TELEGRAM")


# --- BACKGROUND TASKS ---

def background_extract_task(username, platform, limit):
    emit_log(f"Analyse du profil @{username}...", "info", "SCAN")
    try:
        history = load_history(username)

        # Callback silencieux pour get_video_links
        def log_wrapper(msg, level="info"):
            pass  # On ne veut pas les logs intermédiaires

        videos = get_video_links(username, history, platform, limit, callback_log=log_wrapper)

        if videos:
            save_links_to_file(username, videos)
            emit_log(f"Analyse terminée: {len(videos)} nouvelles vidéos détectées", "success", "SCAN")
        else:
            emit_log("Analyse terminée: Aucune nouvelle vidéo", "warning", "SCAN")

    except Exception as e:
        emit_log(f"Erreur lors de l'analyse: {str(e)}", "error", "SCAN")

def background_download_task(username, platform, min_sleep, max_sleep, force_update=False):
    """Background task to run the download process."""
    global active_tasks
    active_tasks[username] = "running"
    start_time = time.time()

    try:
        emit_log(f"Analyse du profil @{username}...", "info", "SCAN")

        # Ensure user directory exists
        user_dir = get_user_dir(username)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)

        # Load history
        history = load_history(username)

        if force_update:
            emit_log("Mode MAJ forcée activé", "warning", "SCAN")

        # Define a callback for logging from main.py (silenced)
        def log_callback(msg, level="info"):
            pass  # On ne veut pas les logs intermédiaires de main.py

        # 1. Extract Links
        videos_raw = get_video_links(
            username,
            history,
            platform,
            limit=None,
            callback_log=log_callback,
            force_update=force_update
        )

        if not videos_raw:
            emit_log("Aucune nouvelle vidéo trouvée", "warning", "SCAN")
            active_tasks[username] = "done"
            return

        emit_log("Analyse terminée", "success", "SCAN")
        emit_log("", "info", "SCAN")  # Ligne vide

        # 2. Filter slideshows BEFORE counting
        videos_to_download = []
        slideshow_count = 0

        for video in videos_raw:
            if is_slideshow(video['url']):
                # Slideshow détecté, on le sauvegarde silencieusement et on l'ignore
                save_to_slideshows(username, video['url'], video['id'])
                save_to_history(username, video['id'])
                slideshow_count += 1
            else:
                videos_to_download.append(video)

        # Si tout est des slideshows
        if not videos_to_download:
            if slideshow_count > 0:
                emit_log(f"{slideshow_count} slideshows détectés et ignorés", "info", "SCAN")
            emit_log("Aucune vidéo à télécharger", "warning", "SCAN")
            active_tasks[username] = "done"
            return

        save_links_to_file(username, videos_to_download)

        # 3. Display initial statistics
        total_videos_on_profile = len(history) + len(videos_raw)  # Approximation
        mode_text = "Incrémental (seuil: 10 doublons)" if not force_update else "MAJ forcée (toutes les vidéos)"
        telegram_enabled = TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID

        emit_stats_header(
            username=username,
            platform=platform.upper(),
            total_videos=total_videos_on_profile,
            already_downloaded=len(history),
            new_videos=len(videos_to_download),
            slideshows=slideshow_count,
            mode=mode_text,
            min_sleep=min_sleep,
            max_sleep=max_sleep,
            telegram_enabled=telegram_enabled
        )
        emit_log("", "info", "DOWNLOAD")  # Ligne vide
        emit_log(f"Démarrage du téléchargement", "info", "DOWNLOAD")
        emit_log("", "info", "DOWNLOAD")  # Ligne vide

        # 4. Download Videos with progress bar
        downloaded_count = 0
        telegram_sent_count = 0
        total_size_mb = 0.0
        last_progress_time = time.time()  # Pour afficher la barre toutes les minutes

        for i, video in enumerate(videos_to_download):
            if active_tasks.get(username) == "stopping":
                emit_log(f"Arrêt demandé pour @{username}", "warning", "SYSTEM")
                break

            video_id = video['id']
            video_url = video['url']

            # Double check history
            if video_id in history and not force_update:
                continue

            # Pause anti-spam (sauf pour la première vidéo)
            if i > 0:
                sleep_time = random.uniform(min_sleep, max_sleep)
                emit_log(f"Pause: {int(sleep_time)} secondes", "info", "SYSTEM")
                time.sleep(sleep_time)

            # Téléchargement
            video_filename = f"20250{i:02d}_{username}_{video_id}.mp4"  # Simplified, real name will vary
            emit_log(f"[{i+1}/{len(videos_to_download)}] En cours...", "info", "DOWNLOAD")

            download_start = time.time()
            success = download_video(video_url, username, video_id)
            download_duration = time.time() - download_start

            if success:
                downloaded_count += 1

                # Trouver le fichier téléchargé pour obtenir sa taille
                try:
                    found_file = None
                    for f in os.listdir(user_dir):
                        if video_id in f and f.endswith(".mp4"):
                            found_file = os.path.join(user_dir, f)
                            break

                    if found_file:
                        file_size_mb = os.path.getsize(found_file) / (1024 * 1024)
                        total_size_mb += file_size_mb
                        emit_log(f"[{i+1}/{len(videos_to_download)}] {os.path.basename(found_file)} ({download_duration:.1f}s)", "success", "DOWNLOAD")

                        # Telegram
                        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                            send_telegram_video(found_file, f"Nouveau TikTok de @{username} !\n{video_url}", username)
                            telegram_sent_count += 1
                            emit_log("Envoyée", "success", "TELEGRAM")
                    else:
                        emit_log(f"[{i+1}/{len(videos_to_download)}] Téléchargée ({download_duration:.1f}s)", "success", "DOWNLOAD")

                except Exception as e:
                    emit_log(f"Erreur post-traitement: {e}", "error", "SYSTEM")

                save_to_history(username, video_id)

                # Afficher la barre de progression toutes les minutes
                current_time = time.time()
                elapsed = current_time - start_time

                # Afficher si 60 secondes se sont écoulées depuis le dernier affichage
                if current_time - last_progress_time >= 60:
                    emit_progress_bar(downloaded_count, len(videos_to_download), elapsed, total_size_mb, telegram_sent_count)
                    last_progress_time = current_time

            else:
                emit_log(f"[{i+1}/{len(videos_to_download)}] Échec du téléchargement", "error", "DOWNLOAD")

        # Afficher la barre finale (100%)
        total_time = time.time() - start_time
        if downloaded_count > 0:
            emit_progress_bar(downloaded_count, len(videos_to_download), total_time, total_size_mb, telegram_sent_count)

        # Final summary
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)

        separator = "═" * 68
        emit_log("", "info", "SUMMARY")
        emit_log(separator, "info", "SUMMARY")
        emit_log(f"RÉSUMÉ - @{username}", "info", "SUMMARY")
        emit_log(separator, "info", "SUMMARY")
        emit_log("", "info", "SUMMARY")

        emit_log("Téléchargement:", "info", "SUMMARY")
        success_rate = (downloaded_count / len(videos_to_download) * 100) if len(videos_to_download) > 0 else 0
        emit_log(f"  Succès:                         {downloaded_count}/{len(videos_to_download)} ({success_rate:.0f}%)", "info", "SUMMARY")
        failed_count = len(videos_to_download) - downloaded_count
        emit_log(f"  Échecs:                         {failed_count}", "info", "SUMMARY")
        emit_log(f"  Durée totale:                   {minutes}m {seconds:02d}s", "info", "SUMMARY")
        emit_log(f"  Taille totale:                  {total_size_mb:.1f} MB", "info", "SUMMARY")
        if downloaded_count > 0:
            avg_speed = total_size_mb / (total_time / 60)
            emit_log(f"  Vitesse moyenne:                {avg_speed:.1f} MB/min", "info", "SUMMARY")
        emit_log("", "info", "SUMMARY")

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            emit_log("Telegram:", "info", "SUMMARY")
            emit_log(f"  Envoyées:                       {telegram_sent_count}/{downloaded_count}", "info", "SUMMARY")
            emit_log(f"  Topic:                          {username} (ID: mappé)", "info", "SUMMARY")
            emit_log("", "info", "SUMMARY")

        emit_log("Stockage:", "info", "SUMMARY")
        emit_log(f"  Dossier:                        downloads/{username}/", "info", "SUMMARY")

        # Calculer l'espace total utilisé
        total_dir_size = 0
        if os.path.exists(user_dir):
            for f in os.listdir(user_dir):
                file_path = os.path.join(user_dir, f)
                if os.path.isfile(file_path):
                    total_dir_size += os.path.getsize(file_path)
        total_dir_size_mb = total_dir_size / (1024 * 1024)
        emit_log(f"  Espace utilisé (total):         {total_dir_size_mb:.1f} MB", "info", "SUMMARY")
        emit_log("", "info", "SUMMARY")
        emit_log(separator, "info", "SUMMARY")

    except Exception as e:
        emit_log(f"Erreur critique: {str(e)}", "error", "SYSTEM")
        traceback.print_exc()
    finally:
        if active_tasks.get(username) != "stopping":
            active_tasks[username] = "done"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)