"""
Flask Web Interface for TikTok Scraper
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
import os
import json
import threading
from datetime import datetime
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

@app.route('/video/<username>/<filename>')
def serve_video(username, filename):
    """Serve video files for playback"""
    # Security: prevent path traversal
    if '..' in username or '..' in filename:
        return jsonify({'error': 'Invalid path'}), 400

    user_dir = get_user_dir(username)

    # Check if file exists
    file_path = os.path.join(user_dir, filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'Video not found'}), 404

    return send_from_directory(user_dir, filename)

@app.route('/api/profiles')
def get_profiles():
    """Get list of all profiles (JSON)"""
    return jsonify(get_all_profiles())

@app.route('/api/extract', methods=['POST'])
def extract_links():
    """Extract video links for a profile"""
    data = request.json
    username = data.get('username')
    platform = data.get('platform', 'tiktok')
    limit = data.get('limit')

    if not username:
        return jsonify({'error': 'Username required'}), 400

    try:
        history = load_history(username)
        videos = get_video_links(username, history, platform, limit)

        if videos:
            save_links_to_file(username, videos)
            return jsonify({
                'success': True,
                'count': len(videos),
                'message': f'{len(videos)} new videos found'
            })
        else:
            return jsonify({
                'success': True,
                'count': 0,
                'message': 'No new videos found'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def start_download():
    """Start downloading videos in background"""
    data = request.json
    username = data.get('username')
    platform = data.get('platform', 'tiktok')
    limit = data.get('limit')
    min_sleep = data.get('min_sleep', 5)
    max_sleep = data.get('max_sleep', 15)

    if not username:
        return jsonify({'error': 'Username required'}), 400

    # Start background task
    task_id = f"{username}_{datetime.now().timestamp()}"
    thread = threading.Thread(
        target=download_task,
        args=(task_id, username, platform, limit, min_sleep, max_sleep)
    )
    thread.start()

    active_tasks[task_id] = {
        'username': username,
        'status': 'running',
        'progress': 0,
        'total': 0
    }

    return jsonify({
        'success': True,
        'task_id': task_id,
        'message': 'Download started'
    })

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

def download_task(task_id, username, platform, limit, min_sleep, max_sleep):
    """Background task for downloading videos"""
    import time
    import random

    try:
        history = load_history(username)
        videos = get_video_links(username, history, platform, limit)

        active_tasks[task_id]['total'] = len(videos)
        active_tasks[task_id]['status'] = 'downloading'

        for i, video in enumerate(videos):
            video_id = video['id']
            video_url = video['url']

            if video_id in history:
                continue

            # Check if slideshow
            if is_slideshow(video_url):
                save_to_slideshows(username, video_url, video_id)
                save_to_history(username, video_id)
                active_tasks[task_id]['progress'] = i + 1
                continue

            # Download
            success = download_video(video_url, username, video_id)

            if success:
                save_to_history(username, video_id)

            active_tasks[task_id]['progress'] = i + 1

            # Sleep between downloads
            if i < len(videos) - 1:
                sleep_time = random.randint(min_sleep, max_sleep)
                time.sleep(sleep_time)

        active_tasks[task_id]['status'] = 'completed'

    except Exception as e:
        active_tasks[task_id]['status'] = 'error'
        active_tasks[task_id]['error'] = str(e)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
