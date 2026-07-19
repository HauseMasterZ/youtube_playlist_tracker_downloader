import datetime
import os
import pickle
import re
import sys
import subprocess
import random
import urllib.request
import concurrent.futures   # <--- ADD THIS
import requests             # <--- ADD THIS
from googleapiclient.discovery import build

print("Installing required multi-threading and proxy libraries...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "requests", "PySocks"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

# Globals
working_proxies_cache = []
raw_proxy_pool = []

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def refresh_proxies():
    global raw_proxy_pool
    print("    -> Fetching and rapidly verifying fresh proxy lists...")
    raw_proxy_pool = []
    temp_pool = []
    
    proxy_sources = {
        "socks5": [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"
        ],
        "socks4": [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt"
        ],
        "http": [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
        ]
    }
    
    for protocol, urls in proxy_sources.items():
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    for line in response.read().decode('utf-8').splitlines():
                        if line.strip(): temp_pool.append(f"{protocol}://{line.strip()}")
            except: pass

    random.shuffle(temp_pool)
    
    # Protocol-agnostic socket check (Preserves SOCKS proxies!)
    import socket
    def check_proxy(p):
        try:
            ip, port = p.split("://")[1].split(":")
            # Simple TCP ping to see if the server is alive
            with socket.create_connection((ip, int(port)), timeout=2):
                return p
        except: 
            return None

    print("    -> Filtering out offline proxies via TCP ping (this takes ~3 seconds)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=200) as executor:
        # Increased batch size to 500 to ensure we get plenty of working IPs
        results = list(executor.map(check_proxy, temp_pool[:500]))
        
    raw_proxy_pool = [r for r in results if r is not None]
    print(f"    -> Retained {len(raw_proxy_pool)} verified online proxies for yt-dlp.")

def download_audio_ytdlp(vid_id, output_path, folder, proxy):
    base_out = output_path.rsplit('.', 1)[0]
    temp_out = f"{base_out}.%(ext)s"
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio",
        "-x", "--audio-format", "opus",
        "--embed-metadata", 
        "--extractor-args", "youtube:player_client=android,web", # Removed 'tv' client as it currently triggers aggressive blocking
        "--download-archive", f"{folder}/ytdlp_archive.txt",
        "--socket-timeout", "20",  
        "--retries", "1",          
        "--no-check-certificates", 
        "--proxy", proxy,
        "--quiet", "--no-warnings",
        "-o", temp_out,
        f"https://www.youtube.com/watch?v={vid_id}"
    ]
        
    try:
        result = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        if os.path.exists(output_path):
            return "SUCCESS"
            
        # Expose the exact error message from yt-dlp to the console
        err_lines = result.stderr.strip().splitlines()
        if err_lines:
            error_msg = err_lines[-1]
            if "Video unavailable" in error_msg or "Private video" in error_msg:
                return "UNAVAILABLE"
            print(f"        -> yt-dlp Error: {error_msg}")
        else:
            print("        -> yt-dlp Error: Unknown proxy failure (Connection dropped).")
            
        return "FAILED"
        
    except subprocess.TimeoutExpired:
        print("        -> yt-dlp Error: Process timed out (Proxy too slow).")
        return "FAILED"
    except Exception as e:
        print(f"        -> yt-dlp Error: {str(e)}")
        return "FAILED"

def git_commit_and_push(title):
    try:
        subprocess.run(['git', 'add', '-A'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'commit', '-m', f"{title}"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'push'], check=True, stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        pass

for playlist_id, playlist_name in playlist_ids.items():
    try:
        print(f"\nProcessing Playlist: {playlist_name}")
        folder = playlist_name
        os.makedirs(folder, exist_ok=True)

        data_file    = f"{folder}/Video_Playlist_Data.p"
        titles_file  = f"{folder}/Video_Titles.txt"
        added_file   = f"{folder}/Video_Titles_Added.txt"
        removed_file = f"{folder}/Video_Titles_Removed.txt"
        dead_file    = f"{folder}/dead_videos.txt"

        for file_path in [added_file, removed_file, dead_file]:
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

        with open(dead_file, "r", encoding="utf-8") as f:
            dead_videos = f.read()

        for vid_id, meta in sorted_current:
            safe_title = sanitize_filename(meta['title'])
            safe_channel = sanitize_filename(meta['channel'])
            if not safe_title: safe_title = vid_id
            if not safe_channel: safe_channel = "Unknown"
            
            detailed_name = f"{safe_title} - {safe_channel}"
            output_path = f"{folder}/{detailed_name}.opus"
            
            if not os.path.exists(output_path):
                if vid_id in dead_videos:
                    continue

                print(f"Missing Audio File: {detailed_name}")
                success = False
                
                # Check cache first
                for cached_proxy in list(working_proxies_cache):
                    print(f"    -> Trying known good cached proxy: {cached_proxy}")
                    res = download_audio_ytdlp(vid_id, output_path, folder, proxy=cached_proxy)
                    
                    if res == "SUCCESS":
                        print(f"    -> Download complete: {output_path}")
                        git_commit_and_push(f"Add track: {detailed_name}")
                        success = True
                        break
                    elif res == "UNAVAILABLE":
                        print(f"    -> FATAL: Video is unavailable on YouTube. Skipping permanently.")
                        with open(dead_file, "a", encoding="utf-8") as f:
                            f.write(f"{vid_id} - {detailed_name}\n")
                        success = True # Technically not success, but allows loop to skip proxy search
                        break
                    else:
                        print("    -> Cached proxy failed. Removing from cache.")
                        working_proxies_cache.remove(cached_proxy)
                
                if success:
                    continue
                
                # Proxy Hunting
                for attempt in range(25):
                    if not raw_proxy_pool: refresh_proxies()
                    proxy = raw_proxy_pool.pop(0)
                    
                    print(f"    -> (Attempt {attempt+1}/25) Trying proxy: {proxy}")
                    res = download_audio_ytdlp(vid_id, output_path, folder, proxy=proxy)
                    
                    if res == "UNAVAILABLE":
                        print(f"    -> FATAL: Video is unavailable on YouTube. Skipping permanently.")
                        with open(dead_file, "a", encoding="utf-8") as f:
                            f.write(f"{vid_id} - {detailed_name}\n")
                        break
                        
                    if res == "SUCCESS":
                        print(f"    -> Download complete: {output_path}")
                        git_commit_and_push(f"Add track: {detailed_name}")
                        working_proxies_cache.append(proxy) # Save the golden IP
                        success = True
                        break
                        
                if not success and res != "UNAVAILABLE":
                    print(f"ERROR: Could not download {detailed_name} after exhausting proxy options.")

        print(f"    -> Syncing exact playlist order (.m3u8) and logs for {playlist_name}...")
        git_commit_and_push(f"Sync {playlist_name} tracker and logs")

    except Exception as e:
        print(f"Failed to process {playlist_name}: {e}")
        continue
