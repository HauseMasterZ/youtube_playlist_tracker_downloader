import os
import subprocess
import time

folders = ["Gym", "Driving", "Songs"]
BATCH_SIZE = 30  # Push to GitHub every 30 files
files_processed = 0
batch_count = 1

print("Starting lossless conversion and thumbnail extraction...")

# 1. Initialize Git Configuration
subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"])
subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])
subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])
subprocess.run(["git", "config", "--global", "http.version", "HTTP/1.1"])

def push_to_github(batch_number):
    """Commits and pushes the current batch of files to GitHub."""
    print(f"\n--- Pushing Batch {batch_number} to GitHub ---")
    subprocess.run(["git", "add", "-A"], stdout=subprocess.DEVNULL)
    
    # Check if there are staged changes
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
    if diff.returncode != 0:
        subprocess.run(["git", "commit", "-m", f"Convert Opus to WebM (Batch {batch_number})"], stdout=subprocess.DEVNULL)
        subprocess.run(["git", "pull", "--rebase"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Add a retry loop for network drops
        for attempt in range(3):
            push_res = subprocess.run(["git", "push"])
            if push_res.returncode == 0:
                print(f"    -> Batch {batch_number} push successful!")
                break
            else:
                print(f"    -> Push failed. Retrying in 5 seconds... ({attempt+1}/3)")
                time.sleep(5)
    print("-------------------------------------------\n")

for folder in folders:
    if not os.path.exists(folder):
        continue
        
    thumb_dir = os.path.join(folder, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
        
    for filename in os.listdir(folder):
        if filename.endswith(".opus"):
            base_name = filename[:-5]
            opus_path = os.path.join(folder, filename)
            webm_path = os.path.join(folder, base_name + ".webm")
            thumb_path = os.path.join(thumb_dir, base_name + ".jpg")
            
            thumb_cmd = ["ffmpeg", "-y", "-i", opus_path, "-an", "-vframes", "1", thumb_path]
            webm_cmd = ["ffmpeg", "-y", "-i", opus_path, "-vn", "-map_metadata", "-1", "-c:a", "copy", webm_path]
            
            try:
                subprocess.run(thumb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(webm_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
                os.remove(opus_path)
                print(f"    -> Converted: {base_name}")
                
                files_processed += 1
                
                # 2. Trigger a push if we hit the batch limit
                if files_processed >= BATCH_SIZE:
                    push_to_github(batch_count)
                    files_processed = 0
                    batch_count += 1
                    
            except subprocess.CalledProcessError as e:
                print(f"    -> ERROR: Failed to convert {filename}: {e}")
                print(f"    -> FFMPEG LOG: {e.stderr.strip()}")

# 3. Push any remaining files that didn't cleanly divide by 30
if files_processed > 0:
    push_to_github("Final")

print("Conversion complete.")
