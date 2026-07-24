import datetime
import os
import pickle
import re
import sys
import subprocess
import random
import concurrent.futures
import requests
import socket
import time
import json
import traceback

from googleapiclient.discovery import build
import yt_dlp

def execute_with_retry(api_request, max_retries=5):
    """Executes a Google API request with a built-in retry loop for transient SSL/Network errors."""
    for attempt in range(max_retries):
        try:
            return api_request.execute()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"        -> Google API connection dropped ({e}). Retrying in 5 seconds... ({attempt + 1}/{max_retries})")
            time.sleep(5)

youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
if not youtube_api_key:
    # Set a dummy one for testing if not available, or throw
    print("WARNING: YOUTUBE_API_KEY environment variable not set. It must be provided in production.")

PLAYLISTS = {
    "PLK5tc6FSo174pECpHWftUYDcw5KFk4HLs": "Gym",
    "PLK5tc6FSo175xc8zNBMrUZJIY9Q_K9I4w": "Driving",
    "PLK5tc6FSo177DVG_k_Tx57Ztvh0B-5Drd": "Songs"
}

if youtube_api_key:
    youtube = build('youtube', 'v3', developerKey=youtube_api_key)

current_time = datetime.datetime.now()

# Globals for proxy cache
working_proxies_cache = []
raw_proxy_pool = []

# Fetch tracked files to avoid relying on os.path.exists for large files excluded by sparse-checkout
try:
    tracked_files_output = subprocess.check_output(['git', 'ls-files']).decode('utf-8')
    git_tracked_files = set(tracked_files_output.splitlines())
except Exception:
    git_tracked_files = set()

def check_proxy(proxy_url):
    """Checks a proxy rapidly. If TCP connects, verify against YouTube."""
    try:
        ip, port = proxy_url.split("://")[1].split(":")
        with socket.create_connection((ip, int(port)), timeout=2):
            res = requests.get("https://www.youtube.com/generate_204", 
                               proxies={"http": proxy_url, "https": proxy_url}, timeout=3)
            if res.status_code == 204:
                return proxy_url
    except:
        pass
    return None

def refresh_proxies():
    """Fetches and verifies new proxy lists concurrently."""
    global raw_proxy_pool
    print("    -> Fetching and rapidly verifying fresh proxy lists...")
    
    urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
    ]
    
    temp_pool = []
    for url in urls:
        try:
            protocol = "socks5" if "socks5" in url else "socks4" if "socks4" in url else "http"
            resp = requests.get(url, timeout=5)
            for line in resp.text.splitlines():
                if line.strip():
                    temp_pool.append(f"{protocol}://{line.strip()}")
        except:
            pass

    random.shuffle(temp_pool)
    print("    -> Filtering proxies concurrently...")
    
    verified_pool = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
        for p in executor.map(check_proxy, temp_pool[:1000]):
            if p: verified_pool.append(p)
            
    raw_proxy_pool = verified_pool
    print(f"    -> Retained {len(raw_proxy_pool)} YouTube-ready proxies.")

def download_audio_ytdlp(vid_id, output_path, folder, proxy):
    """Uses yt-dlp Python library for faster, isolated downloading."""
    base_out = output_path.rsplit('.', 1)[0]
    temp_out = f"{base_out}.%(ext)s"
    
    ydl_opts = {
        'format': 'bestaudio[ext=webm]/bestaudio',
        'writethumbnail': True,
        'outtmpl': temp_out,
        'proxy': proxy,
        'extractor_args': {'youtube': {'player_client': ['web', 'default']}},
        'concurrent_fragment_downloads': 5,
        'socket_timeout': 15,
        'retries': 3,
        'fragment_retries': 3,
        'nocheckcertificate': True,
        'source_address': '0.0.0.0', # force ipv4
        'legacy_server_connect': True,
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid_id}"])
            
        if os.path.exists(output_path):
            thumb_dir = os.path.join(folder, "thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            source_thumb = f"{base_out}.jpg"
            if os.path.exists(source_thumb):
                os.replace(source_thumb, os.path.join(thumb_dir, os.path.basename(source_thumb)))
            return "SUCCESS"
        return "FAILED"
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if any(err in error_msg for err in ["Private video", "removed by the uploader", "account has been terminated", "copyright claim"]):
            return "FATAL_DELETED"
        if any(err in error_msg for err in ["Sign in to confirm your age", "age-restricted"]):
            return "FATAL_AGE_RESTRICTED"
        if any(err in error_msg for err in ["This video is not available", "Video unavailable", "not available in your country"]):
            return "GEO_BLOCKED"
            
        print(f"        -> yt-dlp Error: {error_msg.splitlines()[0]}")
        return "FAILED"
    except Exception as e:
        print(f"        -> yt-dlp Exception: {str(e)}")
        return "FAILED"

def git_commit_and_push(title):
    try:
        subprocess.run(['git', 'add', '-A'], check=True, stdout=subprocess.DEVNULL)
        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status.stdout.strip():
            print("    -> No changes to commit.")
            return
            
        subprocess.run(['git', 'commit', '-m', title], check=True, stdout=subprocess.DEVNULL)
        
        # Pull with rebase from origin main to resolve detached HEAD conflicts
        pull_res = subprocess.run(['git', 'pull', '--rebase', 'origin', 'main'], capture_output=True, text=True)
        if pull_res.returncode != 0:
            print(f"    -> Git pull warning: {pull_res.stderr.strip()}")
            
        # Push explicitly to origin HEAD:main since actions/checkout defaults to detached HEAD
        push_res = subprocess.run(['git', 'push', 'origin', 'HEAD:main'], capture_output=True, text=True)
        if push_res.returncode != 0:
            print(f"    -> Git push error: {push_res.stderr.strip()}")
        else:
            print("    -> Changes pushed to git.")
    except Exception as e:
        print(f"    -> Git commit/push failed: {e}")

def sanitize(name):
    return re.sub(r'[\\/*?:"<>|]', "", name) or "Unknown"

def main():
    if not youtube_api_key: return
    
    for playlist_id, playlist_name in PLAYLISTS.items():
        try:
            print(f"\nProcessing Playlist: {playlist_name}")
            folder = playlist_name
            os.makedirs(folder, exist_ok=True)

            data_file    = f"{folder}/Video_Playlist_Data.p"
            titles_file  = f"{folder}/Video_Titles.txt"
            added_file   = f"{folder}/Video_Titles_Added.txt"
            removed_file = f"{folder}/Video_Titles_Removed.txt"
            dead_file    = f"{folder}/dead_videos.txt"

            for f_path in [added_file, removed_file, dead_file]:
                if not os.path.exists(f_path): open(f_path, 'w').close()

            current = {}
            nextPageToken = None
            
            while True:
                pl_response = execute_with_retry(youtube.playlistItems().list(
                    part='contentDetails', playlistId=playlist_id, maxResults=50, pageToken=nextPageToken
                ))
                
                if not pl_response.get('items'): break

                vid_ids = [item["contentDetails"]["videoId"] for item in pl_response['items']]
                vid_response = execute_with_retry(youtube.videos().list(
                    part="snippet,contentDetails", id=','.join(vid_ids), maxResults=50
                ))

                for item in vid_response.get('items', []):
                    vid_id = item['id']
                    if vid_id in current: continue
                    
                    snippet = item['snippet']
                    current[vid_id] = {
                        "title": snippet['title'],
                        "channel": snippet['channelTitle'],
                        "published": snippet['publishedAt'],
                        "duration": item['contentDetails']['duration'],
                        "description": snippet.get('description', ''),
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "track_number": len(current) + 1,
                        "tags": snippet.get('tags', [])
                    }

                nextPageToken = pl_response.get("nextPageToken")
                if not nextPageToken: break

            sorted_current = sorted(current.items(), key=lambda x: x[1]['track_number'])
            previous = pickle.load(open(data_file, 'rb')) if os.path.exists(data_file) else {}

            def log_changes(filename, diff_dict, action):
                if not diff_dict: return
                with open(filename, "a", encoding="utf-8") as f:
                    f.write(f"{action} on: {current_time}\n\n")
                    for _, meta in diff_dict.items():
                        desc = meta['description'].replace('\n', ' ')[:150]
                        f.write(f"Track {meta.get('track_number', '?')}: {meta['title']}\n"
                                f"   Channel  : {meta['channel']}\n"
                                f"   Published: {meta['published']}\n"
                                f"   Duration : {meta['duration']}\n"
                                f"   URL      : {meta['url']}\n"
                                f"   Desc     : {desc}...\n\n")
                    f.write("#-----------------------------------------------#\n\n")

            log_changes(added_file, {k: v for k, v in current.items() if k not in previous}, "Added")
            log_changes(removed_file, {k: v for k, v in previous.items() if k not in current}, "Removed")

            with open(data_file, 'wb') as f:
                pickle.dump(current, f, protocol=pickle.HIGHEST_PROTOCOL)

            with open(titles_file, "w", encoding="utf-8") as f:
                f.write(f"Playlist last checked on: {current_time}\n\n")
                f.writelines([f"{meta['track_number']}: {meta['title']}\n" for _, meta in sorted_current])

            json_data = []
            m3u8_lines = ["#EXTM3U\n"]
            
            for vid_id, meta in sorted_current:
                safe_title, safe_channel = sanitize(meta['title']), sanitize(meta['channel'])
                detailed_name = f"{safe_title} - {safe_channel}"
                
                m3u8_lines.append(f"#EXTINF:-1,{meta['title']} - {meta['channel']}\n{detailed_name}.webm\n")
                
                json_data.append({
                    "id": vid_id, "title": meta.get('title', 'Unknown Title'),
                    "channel": meta.get('channel', 'Unknown Channel'),
                    "duration": meta.get('duration', 0),
                    "file_path": f"{folder}/{detailed_name}.webm",
                    "thumbnail_path": f"{folder}/thumbnails/{detailed_name}.jpg",
                    "description": meta.get('description', ''),
                    "upload_date": meta.get('published', ''),
                    "tags": meta.get('tags', [])
                })

            with open(f"{folder}/_Playlist_Order.m3u8", "w", encoding="utf-8") as f:
                f.writelines(m3u8_lines)
                
            with open(f"{folder}/_Playlist_Database.json", "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)

            with open(dead_file, "r", encoding="utf-8") as f:
                dead_videos = f.read()

            for vid_id, meta in sorted_current:
                detailed_name = f"{sanitize(meta['title'])} - {sanitize(meta['channel'])}"
                output_path = f"{folder}/{detailed_name}.webm"
                
                # Check if file exists locally OR is already tracked in git (but excluded by sparse checkout)
                is_tracked = output_path.replace('\\', '/') in git_tracked_files
                
                if os.path.exists(output_path) or is_tracked or vid_id in dead_videos:
                    continue

                print(f"Missing Audio: {detailed_name} | {meta['url']} | {playlist_name}")
                skip = False
                
                for cached_proxy in list(working_proxies_cache):
                    print(f"    -> Trying cached proxy: {cached_proxy}")
                    res = download_audio_ytdlp(vid_id, output_path, folder, cached_proxy)
                    if res == "SUCCESS":
                        print(f"    -> Download complete: {output_path}")
                        skip = True
                        break
                    elif res in ("FATAL_DELETED", "FATAL_AGE_RESTRICTED"):
                        with open(dead_file, "a", encoding="utf-8") as f:
                            f.write(f"{vid_id} - {detailed_name} - {meta['url']} ({res})\n")
                        dead_videos += f"{vid_id}\n"
                        skip = True 
                        break

                if skip: continue
                
                success = False
                unavailable_count = 0
                
                for attempt in range(15):  # Reduced from 30 for speed
                    if not raw_proxy_pool: refresh_proxies()
                    if not raw_proxy_pool:
                        print("    -> ERROR: Exhausted proxies. Skipping track.")
                        break
                        
                    proxy = raw_proxy_pool.pop(0)
                    print(f"    -> (Attempt {attempt+1}/15) Trying proxy: {proxy}")
                    res = download_audio_ytdlp(vid_id, output_path, folder, proxy)
                    
                    if res == "SUCCESS":
                        print(f"    -> Download complete: {output_path}")
                        working_proxies_cache.append(proxy) 
                        success = True
                        break
                    elif res in ("FATAL_DELETED", "FATAL_AGE_RESTRICTED"):
                        with open(dead_file, "a", encoding="utf-8") as f:
                            f.write(f"{vid_id} - {detailed_name} - {meta['url']} ({res})\n")
                        dead_videos += f"{vid_id}\n"  
                        break
                    elif res == "GEO_BLOCKED":
                        unavailable_count += 1
                        if unavailable_count >= 4:
                            with open(dead_file, "a", encoding="utf-8") as f:
                                f.write(f"{vid_id} - {detailed_name} - {meta['url']} (GEO_BLOCKED)\n")
                            dead_videos += f"{vid_id}\n"  
                            break
                        
                if not success and res not in ("FATAL_DELETED", "FATAL_AGE_RESTRICTED") and unavailable_count < 4:
                    print(f"ERROR: Could not download {detailed_name}.")

            print(f"    -> Syncing logs and new files for {playlist_name}...")
            git_commit_and_push(f"Sync {playlist_name} tracker, logs, and new audio files")

        except Exception as e:
            print(f"Failed to process {playlist_name}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
