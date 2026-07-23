import os
import json
import urllib.request
import subprocess

folders = ["Gym", "Driving", "Songs"]

print("Starting thumbnail download process...")

subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"])
subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])

for folder in folders:
    json_path = os.path.join(folder, "_Playlist_Database.json")
    if not os.path.exists(json_path):
        continue

    thumb_dir = os.path.join(folder, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)

    with open(json_path, "r", encoding="utf-8") as f:
        database = json.load(f)

    for track in database:
        vid_id = track.get("id")
        thumb_path = track.get("thumbnail_path")
        
        if not vid_id or not thumb_path or os.path.exists(thumb_path):
            continue
            
        # YouTube hosts thumbnails at multiple resolutions. Attempt max quality first.
        url_max = f"https://img.youtube.com/vi/{vid_id}/maxresdefault.jpg"
        url_hq = f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"
        
        try:
            urllib.request.urlretrieve(url_max, thumb_path)
            print(f"    -> Downloaded maxres thumbnail for {vid_id}")
        except urllib.error.HTTPError:
            try:
                urllib.request.urlretrieve(url_hq, thumb_path)
                print(f"    -> Downloaded HQ thumbnail for {vid_id}")
            except Exception as e:
                print(f"    -> ERROR: Failed to fetch thumbnail for {vid_id}: {e}")

print("\nUploading to GitHub...")
subprocess.run(["git", "add", "-A"])
diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
if diff.returncode != 0:
    subprocess.run(["git", "commit", "-m", "Download missing YouTube thumbnails"])
    subprocess.run(["git", "push"])
    print("Upload complete.")
else:
    print("No new thumbnails to upload.")
