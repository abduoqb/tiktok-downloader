import argparse
import yt_dlp
import os
import sys
import json
import time
import random
import subprocess
import glob
import shutil
from datetime import datetime
from metadata_manager import OptimizedMetadataManager

def get_user_dir(username):
    """Returns the directory path for a specific user."""
    return os.path.join("downloads", username)

def get_metadata_manager(username):
    """
    Retourne ou crée un OptimizedMetadataManager pour l'utilisateur
    """
    user_dir = get_user_dir(username)
    os.makedirs(user_dir, exist_ok=True)

    return OptimizedMetadataManager(username, user_dir)

def load_history(username):
    """
    Loads the list of downloaded video IDs using OptimizedMetadataManager
    """
    manager = get_metadata_manager(username)
    return manager.get_all_ids()

def save_to_history(username, video_id, url="", item_type="video", file_size=0, file_count=1, success=True):
    """
    Saves a video ID to history with metadata using OptimizedMetadataManager
    """
    manager = get_metadata_manager(username)
    manager.add(video_id, url, item_type, file_size, file_count, success)

def is_slideshow(video_url, username=None, use_cache=True):
    """
    Detects if a video is a slideshow by checking available formats.
    Now with caching support for performance.

    Args:
        video_url: URL to check
        username: Optional username for cache lookup
        use_cache: If True, checks cache before API call

    Returns:
        bool: True if slideshow, False otherwise
    """
    # Try cache first if username provided
    if use_cache and username:
        manager = get_metadata_manager(username)
        cached_result = manager.get_slideshow_type_from_cache(video_url)
        if cached_result is not None:
            return cached_result

    # API call
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,  # Need full info
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            if not info:
                result = False
            else:
                # Check if there's video format available
                formats = info.get('formats', [])
                has_video = any(f.get('vcodec') != 'none' for f in formats)
                has_audio = any(f.get('acodec') != 'none' for f in formats)

                # If only audio available (no video), it's likely a slideshow
                result = has_audio and not has_video

        # Cache the result
        if use_cache and username:
            manager = get_metadata_manager(username)
            manager.cache_slideshow_type(video_url, result)

        return result

    except Exception as e:
        print(f"Error checking slideshow: {e}")
        return False

def download_slideshow(video_url, username, video_id):
    """Downloads a slideshow using gallery-dl and organizes files."""
    try:
        # Get upload date from TikTok
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        upload_date = None
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info:
                upload_date = info.get('upload_date', datetime.now().strftime('%Y%m%d'))

        if not upload_date:
            upload_date = datetime.now().strftime('%Y%m%d')

        # Temporary download directory
        temp_dir = "temp_slideshow"
        os.makedirs(temp_dir, exist_ok=True)

        # Configuration gallery-dl
        config = {
            "base-directory": temp_dir,
            "extractor": {
                "tiktok": {
                    "directory": ["{author[uniqueId]}", "{id}"],
                    "filename": "{num:>02}_{id}.{extension}",
                    "videos": False,  # Only images
                }
            }
        }

        # Create temporary config file
        config_file = "gallery-dl-config-temp.json"
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

        try:
            # Execute gallery-dl
            cmd = [
                'gallery-dl',
                '--config', config_file,
                video_url
            ]

            print(f"Downloading slideshow with gallery-dl: {video_url}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"gallery-dl error (returncode {result.returncode})")
                if result.stderr:
                    print(f"Error: {result.stderr}")
                return False

            # Find downloaded files in temp directory
            downloaded_files = glob.glob(f"{temp_dir}/**/*", recursive=True)
            image_files = [f for f in downloaded_files if os.path.isfile(f) and f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
            audio_files = [f for f in downloaded_files if os.path.isfile(f) and f.lower().endswith(('.mp3', '.m4a', '.aac'))]

            if not image_files:
                print("No images found after gallery-dl download")
                return False

            # Delete audio files (we don't need them)
            for audio_file in audio_files:
                try:
                    os.remove(audio_file)
                    print(f"Removed audio file: {os.path.basename(audio_file)}")
                except Exception as e:
                    print(f"Warning: Could not remove audio file: {e}")

            # Move images to final destination with proper naming
            output_dir = get_user_dir(username)
            os.makedirs(output_dir, exist_ok=True)

            # Sort images to maintain order
            image_files.sort()

            moved_count = 0
            for idx, img_file in enumerate(image_files, start=1):
                ext = os.path.splitext(img_file)[1]
                # Format: date_pseudo_id_img=numero.ext
                new_filename = f"{upload_date}_{username}_{video_id}_img={idx}{ext}"
                new_path = os.path.join(output_dir, new_filename)

                try:
                    shutil.move(img_file, new_path)
                    moved_count += 1
                    print(f"Moved: {new_filename}")
                except Exception as e:
                    print(f"Error moving {img_file}: {e}")

            # Cleanup temp directory
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Warning: Could not remove temp directory: {e}")

            print(f"Slideshow downloaded: {moved_count} images saved to {output_dir}")
            return True

        finally:
            # Clean up config file
            if os.path.exists(config_file):
                os.remove(config_file)

    except FileNotFoundError:
        print("ERROR: gallery-dl is not installed!")
        print("Install with: pip install gallery-dl")
        return False
    except Exception as e:
        print(f"Error downloading slideshow: {e}")
        import traceback
        traceback.print_exc()
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


    new_videos_count = 0
    consecutive_matches = 0
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Note: extract_info with download=False and extract_flat=True returns a dict
            # If it's a playlist/channel, 'entries' is a generator (lazy).
            info = ydl.extract_info(url, download=False)
            
            if not info:
                log("Failed to extract info (None returned).", "error")
                return

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
                                yield {'url': video_url, 'id': video_id}
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
                        yield {'url': video_url, 'id': video_id}
                    else:
                        log(f"Video {video_id} already in history.", "info")
                    
    except Exception as e:
        log(f"Error extracting links: {e}", "error")
        return

    log(f"Extraction finished. Found {new_videos_count} new videos.", "success")

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
    """Saves unique video links to a text file in the user's directory."""
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    filename = os.path.join(output_dir, f"{username}_videos.txt")
    try:
        # Read existing links if file exists
        existing_links = set()
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_links = set(line.strip() for line in f if line.strip())
        
        # Add new links
        new_links = [video['url'] for video in videos]
        all_links = existing_links.union(new_links)
        
        # Write all unique links back (sorted for consistency)
        with open(filename, "w", encoding="utf-8") as f:
            for link in sorted(all_links):
                f.write(link + "\n")
        
        added_count = len(all_links) - len(existing_links)
        print(f"Successfully saved {len(all_links)} unique links ({added_count} new) to {os.path.abspath(filename)}")
    except Exception as e:
        print(f"Error saving to file: {e}")

def append_link_to_file(username, video_url):
    """Appends a single video link to the user's video list file."""
    output_dir = get_user_dir(username)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    filename = os.path.join(output_dir, f"{username}_videos.txt")
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(video_url + "\n")
        return True
    except Exception as e:
        print(f"Error appending to file: {e}")
        return False

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
        if is_slideshow(args.username_or_url, username=username):
            print("Slideshow detected - downloading with gallery-dl")
            # Extract video ID from URL
            try:
                video_id = args.username_or_url.split('/video/')[1].split('?')[0]
            except:
                video_id = "unknown"

            success = download_slideshow(args.username_or_url, username, video_id)
            if success:
                print(f"Slideshow download complete! Saved to {user_dir}")
            else:
                print("Slideshow download failed.")
            return
        
        # Download the video
        print("Downloading video...")
        try:
            video_id = args.username_or_url.split('/video/')[1].split('?')[0]
        except:
            video_id = "unknown"
        
        success = download_video(args.username_or_url, username, video_id)
        if success:
            print(f"Download complete! Saved to {user_dir}")
        else:
            print("Download failed.")
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
        print("WARNING: FORCE UPDATE MODE ENABLED: Will scan all videos.")

    videos = get_video_links(username, history, args.platform, args.limit, force_update=args.force_update)
    
    if videos:
        save_links_to_file(username, videos)
        
        if args.download:
            print(f"\nStarting download of {len(videos)} new videos...")

            video_count = 0  # Regular video downloads
            slideshow_count = 0  # Slideshow downloads

            for i, video in enumerate(videos):
                video_id = video['id']
                video_url = video['url']

                # Double check history just in case (though get_video_links handles it)
                if video_id in history:
                    continue

                # Detect if it's a slideshow
                print(f"Checking ({i+1}/{len(videos)}): {video_url}")
                if is_slideshow(video_url, username=username):
                    slideshow_count += 1
                    print(f"Slideshow detected - downloading with gallery-dl ({slideshow_count} slideshows so far)")
                    success = download_slideshow(video_url, username, video_id)

                    if success:
                        # Count images
                        image_count = 0
                        user_dir = get_user_dir(username)
                        for f in os.listdir(user_dir):
                            if video_id in f and f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                image_count += 1

                        save_to_history(username, video_id, url=video_url, item_type="slideshow",
                                      file_size=0, file_count=image_count, success=True)
                        # Sleep to avoid rate limiting
                        sleep_time = random.randint(args.min_sleep, args.max_sleep)
                        print(f"Sleeping for {sleep_time} seconds...")
                        time.sleep(sleep_time)
                    else:
                        save_to_history(username, video_id, url=video_url, item_type="slideshow",
                                      file_size=0, success=False)
                        print("Slideshow download failed, marked as failed.")
                    continue

                video_count += 1
                print(f"Downloading video ({video_count}): {video_url}")
                success = download_video(video_url, username, video_id)

                if success:
                    # Get file size
                    file_size = 0
                    user_dir = get_user_dir(username)
                    for f in os.listdir(user_dir):
                        if video_id in f and f.endswith(".mp4"):
                            file_path = os.path.join(user_dir, f)
                            file_size = os.path.getsize(file_path)
                            break

                    save_to_history(username, video_id, url=video_url, item_type="video",
                                  file_size=file_size, success=True)
                    # Sleep to avoid rate limiting
                    sleep_time = random.randint(args.min_sleep, args.max_sleep)
                    print(f"Sleeping for {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    save_to_history(username, video_id, url=video_url, item_type="video",
                                  file_size=0, success=False)
                    print("Download failed, marked as failed.")

            print(f"\nDownload Summary:")
            print(f"   Videos: {video_count}")
            print(f"   Slideshows: {slideshow_count}")
            print(f"   Total: {video_count + slideshow_count}")
    else:
        print("No new videos found.")

if __name__ == "__main__":
    main()
