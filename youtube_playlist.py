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

working_proxies_cache = []

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_working_proxy(vid_id):
    print("    -> Scraping thousands of free proxies (HTTP/SOCKS4/SOCKS5)...")
    urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
    ]
    proxies = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                ptype = url.split('/')[-1].replace('.txt', '')
                for line in response.read().decode('utf-8').splitlines():
                    if line.strip():
                        proxies.append(f"{ptype}://{line.strip()}")
        except Exception:
            pass

    random.shuffle(proxies)
    print(f"    -> Rapidly testing {len(proxies)} proxies concurrently (5-second timeout limit)...")

    def test_proxy(proxy):
        try:
            test_url = f"https://www.youtube.com/watch?v={vid_id}"
            res = requests.get(
                test_url, 
                proxies={"http": proxy, "https": proxy}, 
                timeout=5, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            if res.status_code == 200 and "Sign in to confirm" not in res.text:
                return proxy
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=150) as executor:
        futures = {executor.submit(test_proxy, p): p for p in proxies[:300]}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                print(f"    -> [SUCCESS] Found lightning-fast, verified proxy: {result}")
                return result
                
    return None

def download_audio_ytdlp(vid_id, output_path, proxy=None):
    base_out = output_path.rsplit('.', 1)[0]
    temp_out = f"{base_out}.%(ext)s"
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-x", "--audio-format", "opus", "--audio-quality", "96K",
        "--extractor-args", "youtube:player_client=tv,android,web",
        "--socket-timeout", "20",
        "--retries", "0",
        "--quiet", "--no-warnings",
        "-o", temp_out,
        f"https://www.youtube.com/watch?v={vid_id}"
    ]
    
    if proxy:
        cmd.extend(["--proxy", proxy])
        
    try:
        # Reduced from 600 seconds to 90 seconds. 
        # If the proxy cannot download a 3MB file in 1.5 minutes, kill it.
        result = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        
        if os.path.exists(output_path):
            print(f"    -> Download complete: {output_path}")
            return True
        else:
            err_lines = result.stderr.strip().splitlines()
            error_msg = err_lines[-1] if err_lines else "Unknown connection error"
            print(f"    -> yt-dlp Failed: {error_msg}")
            return False
            
    except subprocess.TimeoutExpired:
        print("    -> Process timed out (Proxy was too slow, took longer than 90 seconds).")
        return False

def git_commit_and_push(file_path, title):
    print(f"    -> Committing and pushing '{title}' to repository...")
    try:
        subprocess.run(['git', 'add', file_path], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'add', '*.txt', '*.p'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'commit', '-m', f"Add track: {title}"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'push'], check=True, stdout=subprocess.DEVNULL)
        print("    -> Successfully pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"    -> Git push failed (may have timed out or had no changes): {e}")

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

            vid_ids = [item["contentDetails"]["videoId"] for item in pl_response['items']]

            vid_response = youtube.videos().list(
                part       = "snippet, contentDetails",
                id         = ','.join(vid_ids),
                maxResults = 50
            ).execute()

            for item in vid_response['items']:
                vid_id = item['id']
                current[vid_id] = {
                    "title"     : item['snippet']['title'],
                    "channel"   : item['snippet']['channelTitle'],
                    "published" : item['snippet']['publishedAt'],
                    "duration"  : item['contentDetails']['duration'],
                    "url"       : f"https://www.youtube.com/watch?v={vid_id}"
                }

            nextPageToken = pl_response.get("nextPageToken")
            if not nextPageToken:
                break

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
                for i, (vid_id, meta) in enumerate(added.items(), 1):
                    f.write(f"{i}: {meta['title']}\n")
                    f.write(f"   Channel  : {meta['channel']}\n")
                    f.write(f"   Published: {meta['published']}\n")
                    f.write(f"   Duration : {meta['duration']}\n")
                    f.write(f"   URL      : {meta['url']}\n\n")
                f.write("#-----------------------------------------------#\n\n")

        if removed:
            with open(removed_file, "a", encoding="utf-8") as f:
                f.write(f"Removed on: {current_time}\n\n")
                for i, (vid_id, meta) in enumerate(removed.items(), 1):
                    f.write(f"{i}: {meta['title']}\n")
                    f.write(f"   Channel  : {meta['channel']}\n")
                    f.write(f"   Published: {meta['published']}\n")
                    f.write(f"   Duration : {meta['duration']}\n")
                    f.write(f"   URL      : {meta['url']}\n\n")
                f.write("#-----------------------------------------------#\n\n")

        with open(data_file, 'wb') as f:
            pickle.dump(current, f, protocol=pickle.HIGHEST_PROTOCOL)

        with open(titles_file, "w", encoding="utf-8") as f:
            f.write(f"Playlist last checked on: {current_time}\n\n")
            for i, meta in enumerate(current.values(), 1):
                f.write(f"{i}: {meta['title']}\n")

        for vid_id, meta in current.items():
            safe_title = sanitize_filename(meta['title'])
            if not safe_title:
                safe_title = vid_id
            
            output_path = f"{folder}/{safe_title}.opus"
            
            if not os.path.exists(output_path):
                print(f"Missing Audio File: {meta['title']}")
                success = False
                
                for cached_proxy in list(working_proxies_cache):
                    print(f"    -> Trying known good cached proxy: {cached_proxy}")
                    if download_audio_ytdlp(vid_id, output_path, proxy=cached_proxy):
                        success = True
                        git_commit_and_push(output_path, meta['title'])
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
                        print("    -> Could not find a verified proxy in this batch.")
                        continue
                        
                    if download_audio_ytdlp(vid_id, output_path, proxy=new_proxy):
                        success = True
                        working_proxies_cache.append(new_proxy) 
                        git_commit_and_push(output_path, meta['title'])
                        break
                        
                if not success:
                    print(f"ERROR: Could not download {meta['title']} after exhausting all options.")

    except Exception as e:
        print(f"Failed to process {playlist_name}: {e}")
        continue
