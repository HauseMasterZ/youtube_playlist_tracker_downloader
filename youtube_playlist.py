import datetime
import os
import pickle
import re
import sys
import subprocess
import random
import urllib.request
from googleapiclient.discovery import build

print("Installing dependencies...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp", "requests", "PySocks"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
playlist_ids = {
    "PLK5tc6FSo174pECpHWftUYDcw5KFk4HLs": "Gym",
    "PLK5tc6FSo175xc8zNBMrUZJIY9Q_K9I4w": "Driving",
    "PLK5tc6FSo177DVG_k_Tx57Ztvh0B-5Drd": "Songs"
}

youtube = build('youtube', 'v3', developerKey=youtube_api_key)
raw_proxy_pool = []

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def refresh_proxy_pool():
    global raw_proxy_pool
    print(" -> Fetching fresh proxy list...")
    raw_proxy_pool = []
    urls = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
    ]
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                raw_proxy_pool.extend([line.decode('utf-8').strip() for line in response if line.strip()])
        except: continue
    random.shuffle(raw_proxy_pool)

def download_audio_ytdlp(vid_id, output_path, folder, proxy):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio", "-x", "--audio-format", "opus",
        "--embed-metadata", "--extractor-args", "youtube:player_client=tv,android,web",
        "--download-archive", f"{folder}/ytdlp_archive.txt",
        "--socket-timeout", "30", "--retries", "5",
        "--proxy", proxy,
        "--quiet", "--no-warnings",
        "-o", f"{output_path.rsplit('.', 1)[0]}.%(ext)s",
        f"https://www.youtube.com/watch?v={vid_id}"
    ]
    try:
        subprocess.run(cmd, timeout=150, check=True)
        return True
    except:
        return False

def git_commit_and_push(msg):
    try:
        subprocess.run(['git', 'add', '-A'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'commit', '-m', msg], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'push'], check=True, stdout=subprocess.DEVNULL)
    except: pass

for playlist_id, playlist_name in playlist_ids.items():
    folder = playlist_name
    os.makedirs(folder, exist_ok=True)
    
    # Get Playlist
    current = {}
    nextPageToken = None
    while True:
        res = youtube.playlistItems().list(part='contentDetails', playlistId=playlist_id, maxResults=50, pageToken=nextPageToken).execute()
        vid_ids = [item["contentDetails"]["videoId"] for item in res.get('items', [])]
        vid_res = youtube.videos().list(part="snippet", id=','.join(vid_ids)).execute()
        for item in vid_res.get('items', []):
            current[item['id']] = {'title': item['snippet']['title'], 'channel': item['snippet']['channelTitle']}
        nextPageToken = res.get("nextPageToken")
        if not nextPageToken: break

    # Download
    for vid_id, meta in current.items():
        safe_name = f"{sanitize_filename(meta['title'])} - {sanitize_filename(meta['channel'])}"
        output_path = f"{folder}/{safe_name}.opus"
        
        if not os.path.exists(output_path):
            print(f"Downloading: {meta['title']}...")
            success = False
            fail_count = 0
            
            while not success and fail_count < 10:
                if not raw_proxy_pool: refresh_proxy_pool()
                proxy = raw_proxy_pool.pop(0)
                
                if download_audio_ytdlp(vid_id, output_path, folder, proxy):
                    print(f" -> Success with {proxy}")
                    git_commit_and_push(f"Add: {safe_name}")
                    success = True
                else:
                    fail_count += 1
                    print(f" -> Failed with {proxy} ({fail_count}/10)")
