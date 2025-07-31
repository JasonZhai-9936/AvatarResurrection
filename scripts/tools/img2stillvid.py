import os
import subprocess

# Path to ffmpeg executable
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Adjust if needed

def make_video_from_image(image_file, output_file, duration=5, fps=25, resolution=None):
    """
    Create a video of given duration from a single image using ffmpeg.
    
    :param image_file: Path to input image (jpg/png)
    :param output_file: Path to output video file (mp4)
    :param duration: Length of the output video in seconds
    :param fps: Frames per second for the video
    :param resolution: Optional resolution (width,height) to scale video
    """
    print("Using ffmpeg at:", FFMPEG_PATH)
    print("Working dir:", os.getcwd())
    
    # Build ffmpeg command
    cmd = [
        FFMPEG_PATH,
        "-y",                      # Overwrite output if exists
        "-loop", "1",              # Loop the image
        "-i", image_file,          # Input image
        "-c:v", "libx264",         # H.264 video codec
        "-t", str(duration),       # Duration in seconds
        "-pix_fmt", "yuv420p",     # Pixel format for compatibility
        "-vf", f"fps={fps}"
    ]

    # Add scaling if requested
    if resolution:
        width, height = resolution
        cmd[-1] = f"fps={fps},scale={width}:{height}"

    cmd.append(output_file)

    # Run ffmpeg
    print("Running command:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Saved video to {output_file}")

# Example usage:
image_path = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\l1_first_frame.png"
output_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\f1.mp4"

make_video_from_image(image_path, output_video, duration=2, fps=25)
