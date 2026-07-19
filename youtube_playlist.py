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

# Installs
print("Installing dependencies...")
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
raw_proxy_pool = []

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def get_working_proxy():
    global raw_proxy_pool
    if not raw_proxy_pool:
        urls = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        ]
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    raw_proxy_pool.extend([line.decode('utf-8').strip() for line in response if line.strip()])
            except: pass
        random.shuffle(raw_proxy_pool)
    return raw_proxy_pool.pop(0) if raw_proxy_pool else None

def download_audio_ytdlp(vid_id, output_path, folder, proxy=None):
    base_out = output_path.rsplit('.', 1)[0]
    temp_out = f"{base_out}.%(ext)s"
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio",
        "-x", "--audio-format", "opus",
        "--embed-metadata", 
        "--extractor-args", "youtube:player_client=tv,android,web",
        "--download-archive", f"{folder}/ytdlp_archive.txt",
        "--socket-timeout", "30",
        "--retries", "3",
        "--fragment-retries", "3",
        "--quiet", "--no-warnings",
        "-o", temp_out,
        f"https://www.youtube.com/watch?v={vid_id}"
    ]
    
    if proxy:
        cmd.extend(["--proxy", proxy])
        
    try:
        result = subprocess.run(cmd, timeout=120, capture_output=True, text=True)
        return os.path.exists(output_path)
    except:
        return False

def git_commit_and_push(msg):
    try:
        subprocess.run(['git', 'add', '-A'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'commit', '-m', msg], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'push'], check=True, stdout=subprocess.DEVNULL)
    except: pass

for playlist_id, playlist_name in playlist_ids.items():
    print(f"\nProcessing: {playlist_name}")
    folder = playlist_name
    os.makedirs(folder, exist_ok=True)
    
    # 1. Fetch Playlist Metadata
    current = {}
    nextPageToken = None
    while True:
        res = youtube.playlistItems().list(part='contentDetails', playlistId=playlist_id, maxResults=50, pageToken=nextPageToken).execute()
        vid_ids = [item["contentDetails"]["videoId"] for item in res['items']]
        vid_res = youtube.videos().list(part="snippet, contentDetails", id=','.join(vid_ids)).execute()
        for item in vid_res['items']:
            current[item['id']] = {
                "title": item['snippet']['title'],
                "channel": item['snippet']['channelTitle'],
                "track_number": len(current) + 1,
                "description": item['snippet'].get('description', '')
            }
        nextPageToken = res.get("nextPageToken")
        if not nextPageToken: break

    # 2. Process Downloads
    for vid_id, meta in current.items():
        safe_name = f"{sanitize_filename(meta['title'])} - {sanitize_filename(meta['channel'])}"
        output_path = f"{folder}/{safe_name}.opus"
        
        if not os.path.exists(output_path):
            print(f"Downloading: {meta['title']}...")
            
            # ATTEMPT 1: Direct Download (Efficiency)
            if download_audio_ytdlp(vid_id, output_path, folder, proxy=None):
                print(" -> Direct download success.")
                git_commit_and_push(f"Add track: {safe_name}")
                continue
            
            # ATTEMPT 2: Proxy Fallback
            for i in range(5): # Try 5 different proxies
                proxy = get_working_proxy()
                if proxy and download_audio_ytdlp(vid_id, output_path, folder, proxy=proxy):
                    print(f" -> Proxy download success using {proxy}")
                    git_commit_and_push(f"Add track: {safe_name}")
                    break
            else:
                print(f" -> FAILED: Could not download {meta['title']}")

    # 3. Final Sync
    print(f"Syncing playlist data for {playlist_name}...")
    git_commit_and_push(f"Sync {playlist_name} playlist")
