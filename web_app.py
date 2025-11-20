"""
Flask Web Interface for TikTok Scraper
"""
from flask import Flask, render_template, request, jsonify
import os

app = Flask(__name__)

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/profiles')
def get_profiles():
    """Get list of all profiles"""
    profiles = []
    downloads_dir = 'downloads'

    if os.path.exists(downloads_dir):
        for username in os.listdir(downloads_dir):
            user_dir = os.path.join(downloads_dir, username)
            if os.path.isdir(user_dir):
                profiles.append({
                    'username': username,
                    'video_count': 0  # TODO: Count from history
                })

    return jsonify(profiles)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
