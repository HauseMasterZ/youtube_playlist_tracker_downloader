import datetime
import os
import pickle
import json
import re
import sys
import subprocess
import random
import urllib.request
import concurrent.futures
import threading
from googleapiclient.discovery import build

print("Installing required multi-threading and proxy libraries...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "requests", "PySocks"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
import requests

youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
if not youtube_api_key:
    raise ValueError("YOUTUBE_API_KEY environment variable not set")

playlist_ids = {
    "PLK5tc6FSo174pECpHWftUYDcw5KFk4HLs": "Gym",
    "PLK5tc6FSo175xc8zNBMrUZJIY9Q_K9I4w": "Driving",
    "PLK5tc6FSo177DVG_k_Tx57Ztvh0B-5Drd": "Songs"
}

youtube = build('youtube', 'v3', developerKey=youtube_api_key)
current_time = datetime.datetime.now()

# Global caches
working_proxies_cache = []
raw_proxy_pool = []

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_working_proxy(vid_id):
    global raw_proxy_pool
    
    if not raw_proxy_pool:
        print("    -> Downloading fresh master proxy list from GitHub...")
        urls = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        ]
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    ptype = url.split('/')[-1].replace('.txt', '')
                    for line in response.read().decode('utf-8').splitlines():
                        if line.strip():
                            raw_proxy_pool.append(f"{ptype}://{line.strip()}")
            except Exception:
                pass
        random.shuffle(raw_proxy_pool)

    # Slice off a batch of 300 and remove them from the master pool so we never test duds twice
    batch = raw_proxy_pool[:300]
    raw_proxy_pool = raw_proxy_pool[300:]
    
    print(f"    -> Rapidly testing {len(batch)} proxies concurrently...")
    
    stop_event = threading.Event()

    def test_proxy(proxy):
        if stop_event.is_set():
            return None
        try:
            test_url = f"https://www.youtube.com/watch?v={vid_id}"
            res = requests.get(
                test_url, 
                proxies={"http": proxy, "https": proxy}, 
                timeout=5, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            if res.status_code == 200 and "Sign in to confirm" not in res.text:
                stop_event.set() # Instantly kill all other threads to save CPU
                return proxy
        except Exception:
            return None
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=150) as executor:
        futures = {executor.submit(test_proxy, p): p for p in batch}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                print(f"    -> [SUCCESS] Found lightning-fast, verified proxy: {result}")
                return result
                
    return None

def download_audio_ytdlp(vid_id, output_path, folder, proxy=None):
    base_out = output_path.rsplit('.', 1)[0]
    temp_out = f"{base_out}.%(ext)s"
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-x", "--audio-format", "opus", "--audio-quality", "96K",
        "--embed-metadata", 
        "--extractor-args", "youtube:player_client=tv,android,web",
        "--download-archive", f"{folder}/ytdlp_archive.txt",
        "--socket-timeout", "20",
        "--retries", "0",
        "--quiet", "--no-warnings",
        "-o", temp_out,
        f"https://www.youtube.com/watch?v={vid_id}"
    ]
    
    if proxy:
        cmd.extend(["--proxy", proxy])
        
    try:
        # Increased timeout to 120s to allow for slow proxy handshake
        result = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
        
        if os.path.exists(output_path):
            print(f"    -> Download complete: {output_path}")
            return True
        else:
            # More descriptive error capture
            err_lines = result.stderr.strip().splitlines()
            error_msg = err_lines[-1] if err_lines else "Unknown connection error"
            print(f"    -> yt-dlp Failed: {error_msg}")
            return False
            
    except subprocess.TimeoutExpired:
        print("    -> Process timed out (Proxy was too slow, took longer than 120 seconds).")
        return False

def git_commit_and_push(title):
    print(f"    -> Committing and pushing '{title}' to repository...")
    try:
        subprocess.run(['git', 'add', '-A'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'commit', '-m', f"Add track: {title}"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'push'], check=True, stdout=subprocess.DEVNULL)
        print("    -> Successfully pushed to GitHub.")
    except subprocess.CalledProcessError:
        print(f"    -> Git push skipped (no changes detected).")

for playlist_id, playlist_name in playlist_ids.items():
    try:
        print(f"\nProcessing Playlist: {playlist_name}")
        folder = playlist_name
        os.makedirs(folder, exist_ok=True)

        data_file    = f"{folder}/Video_Playlist_Data.p"
        titles_file  = f"{folder}/Video_Titles.txt"
        added_file   = f"{folder}/Video_Titles_Added.txt"
        removed_file = f"{folder}/Video_Titles_Removed.txt"

        for file_path in [added_file, removed_file]:
            if not os.path.exists(file_path):
                open(file_path, 'w').close()

        current       = {}
        track_map     = {}
        nextPageToken = None

        while True:
            pl_response = youtube.playlistItems().list(
                part       = 'contentDetails',
                playlistId = playlist_id,
                maxResults = 50,
                pageToken  = nextPageToken
            ).execute()
            
            if not pl_response.get('items'):
                break

            vid_ids = []
            for item in pl_response['items']:
                vid_id = item["contentDetails"]["videoId"]
                vid_ids.append(vid_id)
                # Map the exact playlist order index
                if vid_id not in track_map:
                    track_map[vid_id] = len(track_map) + 1

            vid_response = youtube.videos().list(
                part       = "snippet, contentDetails",
                id         = ','.join(vid_ids),
                maxResults = 50
            ).execute()

            for item in vid_response['items']:
                vid_id = item['id']
                
                desc = item['snippet'].get('description', '')
                
                current[vid_id] = {
                    "title"       : item['snippet']['title'],
                    "channel"     : item['snippet']['channelTitle'],
                    "published"   : item['snippet']['publishedAt'],
                    "duration"    : item['contentDetails']['duration'],
                    "description" : desc,
                    "url"         : f"https://www.youtube.com/watch?v={vid_id}",
                    "track_number": track_map[vid_id]
                }

            nextPageToken = pl_response.get("nextPageToken")
            if not nextPageToken:
                break

        # Sort the dictionary strictly by the YouTube playlist order
        sorted_current = sorted(current.items(), key=lambda x: x[1]['track_number'])

        if os.path.exists(data_file):
            with open(data_file, 'rb') as f:
                previous = pickle.load(f)
        else:
            previous = {}

        added   = {sid: current[sid]  for sid in current  if sid not in previous}
        removed = {sid: previous[sid] for sid in previous if sid not in current}

        if added:
            with open(added_file, "a", encoding="utf-8") as f:
                f.write(f"Added on: {current_time}\n\n")
                for vid_id, meta in added.items():
                    f.write(f"Track {meta['track_number']}: {meta['title']}\n")
                    f.write(f"   Channel  : {meta['channel']}\n")
                    f.write(f"   Published: {meta['published']}\n")
                    f.write(f"   Duration : {meta['duration']}\n")
                    f.write(f"   URL      : {meta['url']}\n")
                    
                    short_desc = meta['description'].replace('\n', ' ')[:150]
                    f.write(f"   Desc     : {short_desc}...\n\n")
                f.write("#-----------------------------------------------#\n\n")

        if removed:
            with open(removed_file, "a", encoding="utf-8") as f:
                f.write(f"Removed on: {current_time}\n\n")
                for vid_id, meta in removed.items():
                    f.write(f"Track {meta.get('track_number', '?')}: {meta['title']}\n")
                    f.write(f"   Channel  : {meta['channel']}\n")
                    f.write(f"   Published: {meta['published']}\n")
                    f.write(f"   Duration : {meta['duration']}\n")
                    f.write(f"   URL      : {meta['url']}\n")
                    
                    short_desc = meta['description'].replace('\n', ' ')[:150]
                    f.write(f"   Desc     : {short_desc}...\n\n")
                f.write("#-----------------------------------------------#\n\n")

        with open(data_file, 'wb') as f:
            pickle.dump(current, f, protocol=pickle.HIGHEST_PROTOCOL)

        with open(titles_file, "w", encoding="utf-8") as f:
            f.write(f"Playlist last checked on: {current_time}\n\n")
            for vid_id, meta in sorted_current:
                f.write(f"{meta['track_number']}: {meta['title']}\n")

        # Generate the strict-order playlist file
        m3u_path = f"{folder}/_Playlist_Order.m3u8"
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for vid_id, meta in sorted_current:
                safe_title = sanitize_filename(meta['title'])
                safe_channel = sanitize_filename(meta['channel'])
                if not safe_title: safe_title = vid_id
                if not safe_channel: safe_channel = "Unknown"
                
                f.write(f"#EXTINF:-1,{meta['title']} - {meta['channel']}\n")
                f.write(f"{safe_title} - {safe_channel}.opus\n")

        # Process and download missing audio files
        for vid_id, meta in sorted_current:
            safe_title = sanitize_filename(meta['title'])
            safe_channel = sanitize_filename(meta['channel'])
            
            if not safe_title:
                safe_title = vid_id
            if not safe_channel:
                safe_channel = "Unknown"
            
            detailed_name = f"{safe_title} - {safe_channel}"
            output_path = f"{folder}/{detailed_name}.opus"
            
            if not os.path.exists(output_path):
                print(f"Missing Audio File: {detailed_name}")
                success = False
                
                for cached_proxy in list(working_proxies_cache):
                    print(f"    -> Trying known good cached proxy: {cached_proxy}")
                    if download_audio_ytdlp(vid_id, output_path, folder, proxy=cached_proxy):
                        success = True
                        git_commit_and_push(detailed_name)
                        break
                    else:
                        print("    -> Cached proxy died. Removing from cache.")
                        working_proxies_cache.remove(cached_proxy)
                        
                if success:
                    continue
                
                for attempt in range(3):
                    print(f"    -> (Attempt {attempt+1}/3 to find a new proxy)")
                    new_proxy = get_working_proxy(vid_id)
                    
                    if not new_proxy:
                        print("    -> Could not find a verified proxy in this batch. Trying next batch...")
                        continue
                        
                    if download_audio_ytdlp(vid_id, output_path, folder, proxy=new_proxy):
                        success = True
                        working_proxies_cache.append(new_proxy)
                        git_commit_and_push(detailed_name)
                        break
                        
                if not success:
                    print(f"ERROR: Could not download {detailed_name} after exhausting all options.")
                    
        # Final sync push to make sure .m3u8 and tracking text files are updated on GitHub 
        # even if no actual audio was downloaded this run
        print(f"    -> Syncing exact playlist order (.m3u8) and logs for {playlist_name}...")
        try:
            subprocess.run(['git', 'add', '-A'], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(['git', 'commit', '-m', f"Sync {playlist_name} playlist data & M3U8 order"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(['git', 'push'], check=True, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            pass 

    except Exception as e:
        print(f"Failed to process {playlist_name}: {e}")
        continue
