"""
Flask Web Interface for TikTok Scraper
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, Response, stream_with_context
import queue
import os
import sys
import json
import threading
import time

import random
import traceback
import signal
import atexit
from datetime import datetime
from urllib.parse import unquote

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
from main import (
    get_user_dir,
    load_history,
    get_video_links,
    download_video,
    save_to_history,
    save_links_to_file,
    append_link_to_file,
    is_slideshow,
    download_slideshow,
    get_metadata_manager,
    find_downloaded_videos
)

app = Flask(__name__)

# Store background tasks with thread references
active_tasks = {}
active_threads = {}  # Store thread objects to check if actually running

# Shutdown flag
shutdown_event = threading.Event()

# --- Shutdown Handler ---
def cleanup_and_shutdown():
    """Arrête proprement tous les threads actifs avant de quitter"""
    global active_tasks, active_threads

    if shutdown_event.is_set():
        return  # Déjà en cours d'arrêt

    shutdown_event.set()
    print("\n[SHUTDOWN] Arrêt du serveur Flask...")
    emit_log("Arrêt du serveur en cours...", "warning", "SYSTEM")

    # Marquer toutes les tâches comme "stopping"
    for username in list(active_tasks.keys()):
        active_tasks[username] = "stopping"

    # Attendre que les threads se terminent (max 5 secondes)
    print(f"[SHUTDOWN] Attente de {len(active_threads)} threads actifs...")
    start_time = time.time()
    for username, thread in list(active_threads.items()):
        if thread.is_alive():
            remaining_time = max(0, 5 - (time.time() - start_time))
            thread.join(timeout=remaining_time)
            if thread.is_alive():
                print(f"[SHUTDOWN] Thread {username} n'a pas terminé à temps")
            else:
                print(f"[SHUTDOWN] Thread {username} terminé")

    # Nettoyer les dictionnaires
    active_tasks.clear()
    active_threads.clear()

    print("[SHUTDOWN] Nettoyage terminé")
    emit_log("Serveur arrêté", "info", "SYSTEM")

def signal_handler(signum, frame):
    """Gestionnaire de signaux pour arrêt propre"""
    print(f"\n[SIGNAL] Signal {signum} reçu")
    cleanup_and_shutdown()
    os._exit(0)

# Enregistrer les gestionnaires
atexit.register(cleanup_and_shutdown)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)



# --- ARCHITECTURE LOGGING ---

# 1. La file d'attente globale (Thread-safe)
log_queue = queue.Queue()

def emit_log(message, level="info", module="SYSTEM"):
    """
    Fonction helper pour pousser un log dans la queue.
    Levels: 'info', 'success' (OK), 'error' (ERROR), 'warning' (WARN)
    Format: [HH:MM:SS] [NIVEAU] [MODULE] Message
    """
    try:
        # Nettoyer le message pour éviter les problèmes d'encodage
        if isinstance(message, str):
            message = message.encode('utf-8', errors='ignore').decode('utf-8')

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

        # Print avec gestion d'erreur d'encodage
        try:
            print(f"[{module}] {message}")
        except UnicodeEncodeError:
            # Fallback en ASCII si problème d'encodage
            safe_message = message.encode('ascii', errors='replace').decode('ascii')
            print(f"[{module}] {safe_message}")
    except Exception as e:
        # Si vraiment tout échoue, on ignore silencieusement
        pass

def emit_stats_header(username, platform, total_videos, already_downloaded, new_videos, slideshows, mode, min_sleep, max_sleep):
    """Affiche les statistiques initiales avant le téléchargement"""
    separator = "=" * 68

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
        emit_log(f"  Slideshows détectés:            {slideshows}", "info", "STATS")
    emit_log("", "info", "STATS")

    emit_log("Configuration:", "info", "STATS")
    emit_log(f"  Mode:                           {mode}", "info", "STATS")
    emit_log(f"  Délais entre vidéos:            {min_sleep}-{max_sleep} secondes", "info", "STATS")
    emit_log(f"  Tentatives par vidéo:           3", "info", "STATS")
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

def emit_progress_bar(current, total, elapsed_seconds, total_size_mb):
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
        progress_line = f"[{bar}] {current}/{total} ({percentage}%) | {elapsed_time} | Terminé | {total_size_mb:.1f} MB"
    else:
        progress_line = f"[{bar}] {current}/{total} ({percentage}%) | {elapsed_time} | {remaining_time} | {total_size_mb:.1f} MB"

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

    # Send the file if found
    if os.path.exists(file_path):
        return send_from_directory(user_dir, filename)
    else:
        return jsonify({'error': 'Video not found'}), 404

@app.route('/api/profiles')
def get_profiles_api():
    """API endpoint to get all profiles"""
    profiles = get_all_profiles()
    return jsonify(profiles)

@app.route('/api/extract', methods=['POST'])
def extract_links():
    """Extract video links for a profile (Background Task)"""
    data = request.json
    username = data.get('username')
    platform = data.get('platform', 'tiktok')
    limit = data.get('limit')

    if not username:
        return jsonify({'error': 'Username required'}), 400

    # Ensure limit is an integer or None
    if limit is not None:
        try:
            limit = int(limit)
        except ValueError:
            limit = None

    emit_log(f"Reçu demande extraction pour {username} avec limite={limit} (type: {type(limit)})", "info", "SYSTEM")

    # Vérifier si un thread est déjà actif
    if username in active_threads:
        thread = active_threads[username]
        if thread.is_alive():
            return jsonify({'error': 'Extraction already in progress for this user'}), 409
        else:
            del active_threads[username]
            if username in active_tasks:
                del active_tasks[username]

    thread = threading.Thread(target=background_extract_task, args=(username, platform, limit))
    thread.daemon = True
    thread.start()

    # Enregistrer le thread
    active_threads[username] = thread

    return jsonify({"success": True, "message": f"Scan lancé pour {username}"})

def background_extract_task(username, platform, limit):
    """Background task to extract video links."""
    global active_tasks
    active_tasks[username] = "running"

    try:
        emit_log(f"Démarrage de l'extraction pour @{username}...", "info", "SCAN")

        # Vérifier si shutdown demandé
        if shutdown_event.is_set():
            emit_log("Arrêt demandé, extraction annulée", "warning", "SCAN")
            return

        # Ensure user directory exists
        user_dir = get_user_dir(username)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)

        # Load history
        history = load_history(username)

        # Define a callback for logging from main.py
        def log_callback(msg, level="info"):
            emit_log(msg, level, "SCAN")

        # Extract links using generator
        # Cookies file for TikTok authentication
        cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tiktok.com_cookies.txt')
        if not os.path.exists(cookies_file):
            cookies_file = None

        video_generator = get_video_links(
            username,
            history,
            platform,
            limit=limit,
            callback_log=log_callback,
            cookies_file=cookies_file
        )

        count = 0
        for video in video_generator:
            # Vérifier si shutdown demandé
            if shutdown_event.is_set():
                emit_log(f"Arrêt demandé, extraction interrompue à {count} vidéos", "warning", "SCAN")
                break

            # Save incrementally
            append_link_to_file(username, video['url'])
            count += 1
            if count % 5 == 0:
                 emit_log(f"{count} vidéos trouvées...", "info", "SCAN")

        if not shutdown_event.is_set():
            emit_log(f"Extraction terminée: {count} vidéos trouvées.", "success", "SCAN")
        
    except Exception as e:
        emit_log(f"Erreur extraction: {str(e)}", "error", "SCAN")
        traceback.print_exc()
    finally:
        if active_tasks.get(username) != "stopping":
            active_tasks[username] = "done"
        # Clean up thread reference
        if username in active_threads:
            del active_threads[username]

@app.route('/api/download', methods=['POST'])
def start_download():
    """Start a background download task"""
    data = request.json
    username = data.get('username')
    platform = data.get('platform', 'tiktok')
    min_sleep = data.get('min_sleep', 0)
    max_sleep = data.get('max_sleep', 0)
    force_update = data.get('force_update', False)

    if not username:
        return jsonify({'error': 'Username required'}), 400

    # Check if thread is actually running (not just status)
    if username in active_threads:
        thread = active_threads[username]
        if thread.is_alive():
            return jsonify({'error': 'Download already in progress for this user'}), 409
        else:
            # Thread finished but status not cleaned up
            del active_threads[username]
            if username in active_tasks:
                del active_tasks[username]

    # Start background task
    thread = threading.Thread(
        target=background_download_task,
        args=(username, platform, min_sleep, max_sleep, force_update),
        daemon=True
    )
    thread.start()

    # Store thread reference
    active_threads[username] = thread

    return jsonify({
        'status': 'started',
        'task_id': username,
        'message': f'Download started for @{username}'
    })

@app.route('/api/task/<task_id>')
def get_task_status(task_id):
    """Get the status of a background task"""
    if task_id in active_tasks:
        return jsonify({
            'task_id': task_id,
            'status': active_tasks[task_id]
        })
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/task/<task_id>/reset', methods=['POST'])
def reset_task_status(task_id):
    """Reset a task status (useful if stuck)"""
    if task_id in active_tasks or task_id in active_threads:
        old_status = active_tasks.get(task_id, 'unknown')
        if task_id in active_tasks:
            del active_tasks[task_id]
        if task_id in active_threads:
            del active_threads[task_id]
        emit_log(f"Réinitialisation de la tâche {task_id} (était: {old_status})", "warning", "SYSTEM")
        return jsonify({
            'success': True,
            'message': f'Task {task_id} reset',
            'old_status': old_status
        })
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/tasks/clear', methods=['POST'])
def clear_all_tasks():
    """Clear all tasks (useful after server restart)"""
    global active_tasks, active_threads
    count = len(active_tasks)
    active_tasks = {}
    active_threads = {}
    emit_log(f"Toutes les tâches ont été réinitialisées ({count} tâches)", "warning", "SYSTEM")
    return jsonify({
        'success': True,
        'message': f'{count} tasks cleared'
    })

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

        # Remove ID from metadata if found
        if video_id:
            manager = get_metadata_manager(username)
            manager.load()
            if video_id in manager._metadata:
                del manager._metadata[video_id]
                manager._id_set.discard(video_id)
                manager._save()

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

                # Get last scan time from metadata file
                manager = get_metadata_manager(username)
                last_scan = None
                if os.path.exists(manager.metadata_file):
                    last_scan = datetime.fromtimestamp(
                        os.path.getmtime(manager.metadata_file)
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



def background_download_task(username, platform, min_sleep, max_sleep, force_update=False):
    """Background task to run the download process."""
    global active_tasks
    active_tasks[username] = "running"
    start_time = time.time()

    # Cookies file for TikTok authentication
    cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tiktok.com_cookies.txt')
    if not os.path.exists(cookies_file):
        cookies_file = None
        emit_log("⚠ Fichier cookies non trouvé, téléchargement sans authentification", "warning", "SYSTEM")

    try:
        # Vérifier si shutdown demandé
        if shutdown_event.is_set():
            emit_log("Arrêt demandé, téléchargement annulé", "warning", "DOWNLOAD")
            return

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
        videos_raw = []
        video_generator = get_video_links(
            username,
            history,
            platform,
            limit=None,
            callback_log=log_callback,
            force_update=force_update,
            cookies_file=cookies_file
        )

        for video in video_generator:
            # Vérifier si shutdown demandé
            if shutdown_event.is_set():
                emit_log("Arrêt demandé pendant l'extraction", "warning", "SCAN")
                return
            videos_raw.append(video)

        if not videos_raw:
            emit_log("Aucune nouvelle vidéo trouvée", "warning", "SCAN")
            active_tasks[username] = "done"
            if username in active_threads:
                del active_threads[username]
            return

        emit_log("Analyse terminée", "success", "SCAN")
        emit_log("", "info", "SCAN")  # Ligne vide

        # 2. Categorize videos and slideshows (with caching for performance)
        items_to_download = []
        slideshow_count = 0
        video_count = 0
        unknown_count = 0

        for video in videos_raw:
            # Use cached is_slideshow for performance
            slideshow_flag = is_slideshow(video['url'], username=username, cookies_file=cookies_file)
            if slideshow_flag is None:
                # Type inconnu (cookies expirés, 403, réseau...) : signalé en erreur,
                # NON enregistré dans l'historique pour être réessayé au prochain lancement
                unknown_count += 1
                emit_log(f"Type inconnu pour {video['id']} (cookies/réseau ?) - ignoré, réessai au prochain lancement", "error", "SCAN")
                continue
            item_type = 'slideshow' if slideshow_flag else 'video'
            items_to_download.append({
                'url': video['url'],
                'id': video['id'],
                'type': item_type
            })
            if item_type == 'slideshow':
                slideshow_count += 1
            else:
                video_count += 1

        # Si rien à télécharger
        if not items_to_download:
            emit_log("Aucune vidéo ou slideshow à télécharger", "warning", "SCAN")
            active_tasks[username] = "done"
            if username in active_threads:
                del active_threads[username]
            return

        save_links_to_file(username, videos_raw)  # Save all links including slideshows

        # 3. Display initial statistics
        total_videos_on_profile = len(history) + len(videos_raw)  # Approximation
        mode_text = "Incrémental (seuil: 10 doublons)" if not force_update else "MAJ forcée (toutes les vidéos)"

        emit_stats_header(
            username=username,
            platform=platform.upper(),
            total_videos=total_videos_on_profile,
            already_downloaded=len(history),
            new_videos=video_count,
            slideshows=slideshow_count,
            mode=mode_text,
            min_sleep=min_sleep,
            max_sleep=max_sleep
        )
        emit_log("", "info", "DOWNLOAD")  # Ligne vide
        emit_log(f"Démarrage du téléchargement", "info", "DOWNLOAD")
        emit_log("", "info", "DOWNLOAD")  # Ligne vide

        # 4. Download Videos and Slideshows with progress bar
        downloaded_videos = 0
        downloaded_slideshows = 0
        total_size_mb = 0.0
        last_progress_time = time.time()  # Pour afficher la barre toutes les minutes

        for i, item in enumerate(items_to_download):
            # Vérifier si arrêt demandé (via API ou shutdown serveur)
            if active_tasks.get(username) == "stopping" or shutdown_event.is_set():
                emit_log(f"Arrêt demandé pour @{username}", "warning", "SYSTEM")
                break

            item_id = item['id']
            item_url = item['url']
            item_type = item['type']

            # Double check history
            if item_id in history and not force_update:
                continue

            # Pause anti-spam (sauf pour le premier item)
            if i > 0:
                sleep_time = random.uniform(min_sleep, max_sleep)
                emit_log(f"Pause: {int(sleep_time)} secondes", "info", "SYSTEM")
                time.sleep(sleep_time)

            # Téléchargement selon le type
            download_start = time.time()

            if item_type == 'slideshow':
                emit_log(f"[{i+1}/{len(items_to_download)}] Slideshow en cours...", "info", "DOWNLOAD")
                success = download_slideshow(item_url, username, item_id, cookies_file=cookies_file)
            else:
                emit_log(f"[{i+1}/{len(items_to_download)}] Vidéo en cours...", "info", "DOWNLOAD")
                success = download_video(item_url, username, item_id, cookies_file=cookies_file)

            download_duration = time.time() - download_start

            # Vidéo : un fichier vérifié est obligatoire avant d'enregistrer un succès
            video_files = []
            if success and item_type != 'slideshow':
                video_files = find_downloaded_videos(username, item_id)
                if not video_files:
                    success = False

            if success:
                if item_type == 'slideshow':
                    downloaded_slideshows += 1
                    # Count images in slideshow
                    image_count = 0
                    for f in os.listdir(user_dir):
                        if item_id in f and f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            image_count += 1
                    emit_log(f"[{i+1}/{len(items_to_download)}] Slideshow ({image_count} images) ({download_duration:.1f}s)", "success", "DOWNLOAD")

                    # Save to history with metadata
                    save_to_history(username, item_id, url=item_url, item_type="slideshow",
                                  file_size=0, file_count=image_count, success=True)
                else:
                    downloaded_videos += 1
                    # Trouver le fichier téléchargé pour obtenir sa taille
                    file_size = 0
                    try:
                        found_file = video_files[0] if video_files else None

                        if found_file:
                            file_size = os.path.getsize(found_file)
                            file_size_mb = file_size / (1024 * 1024)
                            total_size_mb += file_size_mb
                            emit_log(f"[{i+1}/{len(items_to_download)}] {os.path.basename(found_file)} ({download_duration:.1f}s)", "success", "DOWNLOAD")


                        else:
                            emit_log(f"[{i+1}/{len(items_to_download)}] Téléchargée ({download_duration:.1f}s)", "success", "DOWNLOAD")

                    except Exception as e:
                        emit_log(f"Erreur post-traitement: {e}", "error", "SYSTEM")

                    # Save to history with metadata
                    save_to_history(username, item_id, url=item_url, item_type="video",
                                  file_size=file_size, success=True)

                # Afficher la barre de progression toutes les minutes
                current_time = time.time()
                elapsed = current_time - start_time

                # Afficher si 60 secondes se sont écoulées depuis le dernier affichage
                if current_time - last_progress_time >= 60:
                    total_downloaded = downloaded_videos + downloaded_slideshows
                    emit_progress_bar(total_downloaded, len(items_to_download), elapsed, total_size_mb)
                    last_progress_time = current_time

            else:
                # Mark as failed in history
                save_to_history(username, item_id, url=item_url, item_type=item_type,
                              file_size=0, success=False)
                item_type_label = "slideshow" if item_type == 'slideshow' else "vidéo"
                emit_log(f"[{i+1}/{len(items_to_download)}] Échec du téléchargement ({item_type_label})", "error", "DOWNLOAD")

        # Afficher la barre finale (100%)
        total_time = time.time() - start_time
        total_downloaded = downloaded_videos + downloaded_slideshows
        if total_downloaded > 0:
            emit_progress_bar(total_downloaded, len(items_to_download), total_time, total_size_mb)

        # Final summary
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)

        separator = "=" * 68
        emit_log("", "info", "SUMMARY")
        emit_log(separator, "info", "SUMMARY")
        emit_log(f"RÉSUMÉ - @{username}", "info", "SUMMARY")
        emit_log(separator, "info", "SUMMARY")
        emit_log("", "info", "SUMMARY")

        emit_log("Téléchargement:", "info", "SUMMARY")
        total_downloaded = downloaded_videos + downloaded_slideshows
        success_rate = (total_downloaded / len(items_to_download) * 100) if len(items_to_download) > 0 else 0
        emit_log(f"  Succès:                         {total_downloaded}/{len(items_to_download)} ({success_rate:.0f}%)", "info", "SUMMARY")
        emit_log(f"    - Vidéos:                     {downloaded_videos}", "info", "SUMMARY")
        emit_log(f"    - Slideshows:                 {downloaded_slideshows}", "info", "SUMMARY")
        failed_count = len(items_to_download) - total_downloaded
        emit_log(f"  Échecs:                         {failed_count}", "info", "SUMMARY")
        if unknown_count:
            emit_log(f"  Type inconnu (réessai prévu):   {unknown_count}", "error", "SUMMARY")
        emit_log(f"  Durée totale:                   {minutes}m {seconds:02d}s", "info", "SUMMARY")
        emit_log(f"  Taille totale:                  {total_size_mb:.1f} MB", "info", "SUMMARY")
        if total_downloaded > 0 and total_time > 0:
            avg_speed = total_size_mb / (total_time / 60)
            emit_log(f"  Vitesse moyenne:                {avg_speed:.1f} MB/min", "info", "SUMMARY")
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
        # Clean up thread reference
        if username in active_threads:
            del active_threads[username]

if __name__ == '__main__':
    from preflight import check_environment
    for problem in check_environment('tiktok.com_cookies.txt'):
        print(f"[preflight] {problem}")
    app.run(debug=True, host='0.0.0.0', port=5001)