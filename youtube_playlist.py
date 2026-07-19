import datetime, os, pickle, re, sys, subprocess, random, urllib.request
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

def sanitize(name): return re.sub(r'[\\/*?:"<>|]', "", name)

def refresh_proxies():
    global raw_proxy_pool
    print(" -> Refreshing proxy pool...")
    raw_proxy_pool = []
    urls = ["https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"]
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                raw_proxy_pool.extend([l.decode('utf-8').strip() for l in r if l.strip()])
        except: continue
    random.shuffle(raw_proxy_pool)

def download_track(vid_id, output_path, folder, proxy=None):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestaudio", "-x", "--audio-format", "opus",
        "--embed-metadata", "--download-archive", f"{folder}/ytdlp_archive.txt",
        "--socket-timeout", "60", "--retries", "5",
        "--quiet", "--no-warnings",
        "-o", f"{output_path.rsplit('.', 1)[0]}.%(ext)s",
        f"https://www.youtube.com/watch?v={vid_id}"
    ]
    if proxy: cmd.extend(["--proxy", proxy])
    try:
        subprocess.run(cmd, timeout=300, check=True)
        return True
    except subprocess.CalledProcessError as e:
        # Check if it's a hard block (unavailable) vs connection error
        if "Video unavailable" in str(e) or "Private video" in str(e):
            return "UNAVAILABLE"
        return False

# Execution
for p_id, p_name in playlist_ids.items():
    os.makedirs(p_name, exist_ok=True)
    # [Playlist fetching logic remains same]
    # ...
    
    for vid_id, meta in current.items():
        # ... [File path setup]
        
        if not os.path.exists(output_path):
            print(f"Downloading: {meta['title']}...")
            
            # Attempt 1: Direct
            res = download_track(vid_id, output_path, p_name, proxy=None)
            if res == "UNAVAILABLE": continue
            if res: continue
            
            # Attempt 2: Proxies
            for _ in range(5):
                if not raw_proxy_pool: refresh_proxies()
                p = raw_proxy_pool.pop(0)
                res = download_track(vid_id, output_path, p_name, proxy=p)
                if res == "UNAVAILABLE": break
                if res: break
