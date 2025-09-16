import subprocess

FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"

def img_to_video(image_path, output_path, duration=5, fps=30):
    """
    Convert an image to a still video. Ensures even dimensions for yuv420p.
    """
    # Force even width/height, keep aspect ratio; then set fps
    vf = f"scale=trunc(iw/2)*2:trunc(ih/2)*2,fps={fps}"

    cmd = [
        FFMPEG_PATH,
        "-y",                 # overwrite
        "-loop", "1",         # loop the single frame
        "-i", image_path,
        "-t", str(duration),  # duration
        "-vf", vf,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

# Example:
img_to_video("main2.png", "main2.mp4", duration=5, fps=30)
