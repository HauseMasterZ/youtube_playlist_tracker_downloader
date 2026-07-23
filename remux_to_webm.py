import os
import subprocess

folders = ["Gym", "Driving", "Songs"]
files_changed = False

print("Starting lossless conversion and thumbnail extraction...")

for folder in folders:
    if not os.path.exists(folder):
        continue
        
    # Create the thumbnails subfolder
    thumb_dir = os.path.join(folder, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
        
    for filename in os.listdir(folder):
        if filename.endswith(".opus"):
            base_name = filename[:-5]
            opus_path = os.path.join(folder, filename)
            webm_path = os.path.join(folder, base_name + ".webm")
            
            # Route the extracted thumbnail to the subfolder
            thumb_path = os.path.join(thumb_dir, base_name + ".jpg")
            
            thumb_cmd = ["ffmpeg", "-y", "-i", opus_path, "-an", "-vframes", "1", thumb_path]
            webm_cmd = ["ffmpeg", "-y", "-i", opus_path, "-vn", "-map_metadata", "-1", "-c:a", "copy", webm_path]
            
            try:
                subprocess.run(thumb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(webm_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                
                os.remove(opus_path)
                print(f"    -> Converted & Extracted Art: {base_name}")
                files_changed = True
            except subprocess.CalledProcessError as e:
                print(f"    -> ERROR: Failed to convert {filename}: {e}")
                print(f"    -> FFMPEG LOG: {e.stderr.strip()}")

if not files_changed:
    print("No .opus files found to convert.")
