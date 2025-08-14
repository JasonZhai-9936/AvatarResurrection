import os
from moviepy import VideoFileClip

def list_video_durations(directory="."):
    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        
        if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in video_extensions:
            try:
                with VideoFileClip(filepath) as clip:
                    duration = clip.duration  # duration in seconds (float)
                    ms = round(duration * 1000)  # convert to ms
                    print(f"{filename}: {ms} ms ({duration:.3f} s)")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    list_video_durations(".")
