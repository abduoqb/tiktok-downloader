import argparse
import yt_dlp
import os
import sys
import json
import time
import random

def get_user_dir(username):
    """Returns the directory path for a specific user."""
    return os.path.join("downloads", username)

def get_history_file(username):
    """Returns the path to the history file for a specific user."""
    return os.path.join(get_user_dir(username), "download_history.json")

def load_history(username):
    """Loads the list of downloaded video IDs from the user's JSON file."""
    history_file = get_history_file(username)
    if not os.path.exists(history_file):
        return []
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading history: {e}")
        return []

def save_to_history(username, video_id):
    """Appends a video ID to the user's history file."""
    history = load_history(username)
    if video_id not in history:
        history.append(video_id)
        try:
            history_file = get_history_file(username)
            # Ensure directory exists
            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            print(f"Error saving history: {e}")

def get_slideshow_file(username):
    """Returns the path to the slideshow tracking file."""
    return os.path.join(get_user_dir(username), "slideshows.json")

def load_slideshows(username):
    """Loads the list of slideshow URLs."""
    slideshow_file = get_slideshow_file(username)
    if not os.path.exists(slideshow_file):
        return []
    try:
        with open(slideshow_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading slideshows: {e}")
        return []

def save_to_slideshows(username, video_url, video_id):
    """Saves a slideshow URL to the tracking file."""
    slideshows = load_slideshows(username)
    
    # Check if already in list
    for item in slideshows:
        if item.get('id') == video_id:
            return
    
    slideshows.append({
        'id': video_id,
        'url': video_url
    })
    
    try:
        slideshow_file = get_slideshow_file(username)
        os.makedirs(os.path.dirname(slideshow_file), exist_ok=True)
        
        with open(slideshow_file, "w", encoding="utf-8") as f:
            json.dump(slideshows, f, indent=4)
        print(f"Slideshow detected and saved to {slideshow_file}")
    except Exception as e:
        print(f"Error saving slideshow: {e}")

def is_slideshow(video_url):
    """Detects if a video is a slideshow by checking available formats."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,  # Need full info
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            if not info:
                return False
            
            # Check if there's video format available
            formats = info.get('formats', [])
            has_video = any(f.get('vcodec') != 'none' for f in formats)
            has_audio = any(f.get('acodec') != 'none' for f in formats)
            
            # If only audio available (no video), it's likely a slideshow
            if has_audio and not has_video:
                return True
            
            return False
    except Exception as e:
        print(f"Error checking slideshow: {e}")
        return False

def get_video_links(username, history, platform="tiktok", limit=None, callback_log=None, force_update=False):
    """
    Extracts video links for a given username using yt-dlp.
    Stops if a video ID is already in history (Incremental Mode), unless force_update is True.
    Stops if the limit of new videos is reached.
    Returns a list of dictionaries containing 'url' and 'id'.
    """
    if platform.lower() == "tiktok":
        url = f"https://www.tiktok.com/@{username}"
    elif platform.lower() == "youtube":
        url = f"https://www.youtube.com/@{username}/shorts"
    else:
        url = username

    def log(msg, level="info"):
        print(f"[{level.upper()}] {msg}")
        if callback_log:
            callback_log(msg, level)

    log(f"Fetching videos for: {url}")
    
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'ignoreerrors': True,
    }

    videos = []
    new_videos_count = 0
    consecutive_matches = 0
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                log("Failed to extract info (None returned).", "error")
                return []

            if 'entries' in info:
                log(f"Found channel/user: {info.get('title', username)}")
                # 'entries' can be a generator, so we iterate carefully
                for entry in info['entries']:
                    if entry:
                        video_id = entry.get('id')
                        
                        # INCREMENTAL CHECK (Smart Mode)
                        if video_id in history:
                            consecutive_matches += 1
                            if consecutive_matches >= 10 and not force_update:
                                log(f"Found {consecutive_matches} consecutive existing videos. Stopping extraction (Smart Incremental Mode).", "warning")
                                break
                        else:
                            consecutive_matches = 0 # Reset counter if we find a new video
                            
                            video_url = entry.get('url') or entry.get('webpage_url')
                            if video_url and video_id:
                                videos.append({'url': video_url, 'id': video_id})
                                new_videos_count += 1
                                
                                # LIMIT CHECK
                                if limit and new_videos_count >= limit:
                                    log(f"Limit of {limit} videos reached. Stopping extraction.", "warning")
                                    break
            else:
                video_url = info.get('url') or info.get('webpage_url')
                video_id = info.get('id')
                if video_url and video_id:
                    if video_id not in history:
                        videos.append({'url': video_url, 'id': video_id})
                    else:
                        log(f"Video {video_id} already in history.", "info")
                    
    except Exception as e:
        log(f"Error extracting links: {e}", "error")
        return []

    log(f"Found {len(videos)} new videos.", "success")
    return videos

def organize_slideshow(output_dir, video_id):
    """Post-process downloaded files to organize slideshows into folders."""
    import glob
    import shutil
    
    # Find all files with this video ID
    pattern = f'{output_dir}/*[{video_id}]*'
    files = glob.glob(pattern)
    
    if not files:
        return
    
    # Categorize files
    images = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.webp', '.png'))]
    audio = [f for f in files if f.lower().endswith(('.m4a', '.mp3', '.aac'))]
    videos = [f for f in files if f.lower().endswith(('.mp4', '.webm', '.mkv'))]
    
    # If we have multiple images, it's a slideshow
    if len(images) > 1:
        # Get base name from first image (without extension and numbering)
        base_name = os.path.basename(images[0])
        # Remove extension
        base_name = base_name.rsplit('.', 1)[0]
        # Remove potential _001, _01, etc suffixes that yt-dlp might add
        import re
        base_name = re.sub(r'_\d+$', '', base_name)
        
        # Create folder
        folder_path = os.path.join(output_dir, base_name)
        os.makedirs(folder_path, exist_ok=True)
        
        print(f"Detected slideshow: organizing {len(images)} images into folder...")
        
        # Move images to folder
        for img in images:
            dest = os.path.join(folder_path, os.path.basename(img))
            shutil.move(img, dest)
        
        # Delete audio files
        for aud in audio:
            try:
                os.remove(aud)
                print(f"Removed audio file: {os.path.basename(aud)}")
            except Exception as e:
                print(f"Could not remove audio: {e}")
        
        print(f"Slideshow organized in: {folder_path}")

def sanitize_filename(filename):
    """Clean filename by removing problematic characters"""
    import re
    # Remove or replace problematic characters
    # Keep only: alphanumeric, dash, underscore, dot, brackets
    filename = re.sub(r'[^\w\-_\.\[\]\(\)]', '_', filename)
    # Remove multiple consecutive underscores
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    return filename

def download_video(video_url, username, video_id, retries=3):
    """Downloads a single video using yt-dlp into the user's directory with retry logic."""
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'outtmpl': f'{output_dir}/%(upload_date)s_%(id)s.%(ext)s',
        'format': 'bestvideo[vcodec^=avc1]+bestaudio/best[vcodec^=avc1]/best',
        'quiet': False,
        'ignoreerrors': True,
        'restrictfilenames': True,
        'writeallthumbnails': True,
        # Force H.264 (avc1) codec for universal browser compatibility
        # Falls back to best available if H.264 not available
    }

    for attempt in range(retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            # Post-process: Rename to include username
            import glob
            
            # Find file with this video ID (just downloaded)
            pattern = f'{output_dir}/*{video_id}*'
            files = glob.glob(pattern)
            
            for file_path in files:
                if os.path.isfile(file_path):
                    old_name = os.path.basename(file_path)
                    # Extract date and extension
                    # Format: YYYYMMDD_ID.ext -> YYYYMMDD_username_ID.ext
                    parts = old_name.split('_')
                    if len(parts) >= 2:
                        date_part = parts[0]
                        # Last part has ID.ext
                        id_and_ext = '_'.join(parts[1:])
                        new_name = f"{date_part}_{username}_{id_and_ext}"
                        new_name = sanitize_filename(new_name)

                        if new_name != old_name:
                            new_path = os.path.join(output_dir, new_name)
                            try:
                                os.rename(file_path, new_path)
                                print(f"Renamed: {old_name} → {new_name}")
                            except Exception as e:
                                print(f"Could not rename: {e}")
            
            # Post-process: organize slideshows
            organize_slideshow(output_dir, video_id)
            
            return True
        except Exception as e:
            print(f"Error downloading {video_url} (Attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2) # Wait a bit before retrying
            else:
                print("Max retries reached.")
                return False

def save_links_to_file(username, videos):
    """Saves the list of links to a text file in the user's directory."""
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    filename = os.path.join(output_dir, f"{username}_videos.txt")
    try:
        # Append mode 'a' might be better for incremental, but 'w' keeps the file clean with only the latest batch?
        # Actually, usually users want a full list or just the new ones. 
        # Let's stick to overwriting with the NEW batch for now, or appending?
        # The prompt implies "create a list", usually implies the result of the current run.
        # But if we stop early, we only get new videos.
        # Let's append to the file if it exists, so we keep a master list?
        # Or maybe just write the new ones. Let's write the new ones for now to avoid massive duplicates in the text file if we ran without history check before.
        # Wait, if we run incremental, 'videos' only has new videos.
        # If we overwrite, we lose the old links in the text file.
        # Let's use append mode 'a' so the text file becomes a complete archive.
        
        mode = "a" if os.path.exists(filename) else "w"
        with open(filename, mode, encoding="utf-8") as f:
            for video in videos:
                f.write(video['url'] + "\n")
        print(f"Successfully added {len(videos)} links to {os.path.abspath(filename)}")
    except Exception as e:
        print(f"Error saving to file: {e}")

def main():
    parser = argparse.ArgumentParser(description="Extract and download videos from a user profile or single URL.")
    parser.add_argument("username_or_url", help="The username (pseudo) or a direct TikTok URL.")
    parser.add_argument("--platform", default="tiktok", help="Target platform (default: tiktok).")
    parser.add_argument("--download", action="store_true", help="Download the videos after extraction.")
    parser.add_argument("--min-sleep", type=int, default=5, help="Minimum sleep time in seconds (default: 5).")
    parser.add_argument("--max-sleep", type=int, default=15, help="Maximum sleep time in seconds (default: 15).")
    parser.add_argument("--limit", type=int, help="Limit the number of videos to extract/download.")
    parser.add_argument("--force-update", action="store_true", help="Force update mode: check all videos and ignore incremental stop.")
    
    args = parser.parse_args()
    
    # Check if input is a URL or username
    is_url = "tiktok.com" in args.username_or_url or "http" in args.username_or_url
    
    if is_url:
        # Single URL mode
        print(f"Single URL mode detected: {args.username_or_url}")
        
        # Extract username from URL for folder organization
        # Format: https://www.tiktok.com/@username/video/123
        try:
            username = args.username_or_url.split('@')[1].split('/')[0]
        except:
            username = "single_downloads"
        
        user_dir = get_user_dir(username)
        os.makedirs(user_dir, exist_ok=True)
        
        # Check if it's a slideshow
        print("Checking if slideshow...")
        if is_slideshow(args.username_or_url):
            print("⚠️  Slideshow detected - saving to slideshows.json")
            # Extract video ID from URL
            try:
                video_id = args.username_or_url.split('/video/')[1].split('?')[0]
            except:
                video_id = "unknown"
            save_to_slideshows(username, args.username_or_url, video_id)
            print("Slideshow saved. Exiting.")
            return
        
        # Download the video
        print("Downloading video...")
        try:
            video_id = args.username_or_url.split('/video/')[1].split('?')[0]
        except:
            video_id = "unknown"
        
        success = download_video(args.username_or_url, username, video_id)
        if success:
            print(f"✅ Download complete! Saved to {user_dir}")
        else:
            print("❌ Download failed.")
        return
    
    # Username mode (original behavior)
    username = args.username_or_url
    
    # Create user directory if it doesn't exist
    user_dir = get_user_dir(username)
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
        print(f"Created directory: {user_dir}")

    # Load history FIRST for incremental extraction
    history = load_history(username)

    print(f"Starting extraction for user: {username} on {args.platform}...")
    if args.force_update:
        print("⚠️  FORCE UPDATE MODE ENABLED: Will scan all videos.")

    videos = get_video_links(username, history, args.platform, args.limit, force_update=args.force_update)
    
    if videos:
        save_links_to_file(username, videos)
        
        if args.download:
            print(f"\nStarting download of {len(videos)} new videos...")
            
            download_count = 0  # Actual downloads (excluding slideshows)
            
            for i, video in enumerate(videos):
                video_id = video['id']
                video_url = video['url']
                
                # Double check history just in case (though get_video_links handles it)
                if video_id in history:
                    continue
                
                # Detect if it's a slideshow
                print(f"Checking ({i+1}/{len(videos)}): {video_url}")
                if is_slideshow(video_url):
                    print("⚠️  Slideshow detected - saving to slideshows.json and skipping download")
                    save_to_slideshows(username, video_url, video_id)
                    save_to_history(username, video_id)  # Mark as processed
                    continue
                
                download_count += 1
                print(f"Downloading ({download_count}): {video_url}")
                success = download_video(video_url, username, video_id)
                
                if success:
                    save_to_history(username, video_id)
                    # Sleep to avoid rate limiting
                    sleep_time = random.randint(args.min_sleep, args.max_sleep)
                    print(f"Sleeping for {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    print("Download failed, not adding to history.")
    else:
        print("No new videos found.")

if __name__ == "__main__":
    main()
