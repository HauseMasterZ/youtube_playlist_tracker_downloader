import os
import subprocess

folders = ["Gym", "Driving", "Songs"]
files_changed = False

print("Starting lossless conversion from .opus to .webm...")

for folder in folders:
    if not os.path.exists(folder):
        continue
        
    for filename in os.listdir(folder):
        if filename.endswith(".opus"):
            opus_path = os.path.join(folder, filename)
            webm_path = os.path.join(folder, filename[:-5] + ".webm")
            
            # -c:a copy transfers the audio stream exactly as it is without re-encoding and remove metadata
            cmd = ["ffmpeg", "-y", "-i", opus_path, "-map_metadata", "-1", "-c:a", "copy", webm_path]
            
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                os.remove(opus_path)
                print(f"    -> Remuxed: {filename}")
                files_changed = True
            except subprocess.CalledProcessError as e:
                print(f"    -> ERROR: Failed to convert {filename}: {e}")

if not files_changed:
    print("No .opus files found to convert.")
