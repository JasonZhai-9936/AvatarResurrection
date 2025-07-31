import os
import subprocess

# Path to ffmpeg executable
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Adjust if needed

def reverse_video_frames_only(input_file, output_file):
    """
    Reverse only the video frames (ignore audio) using ffmpeg.

    :param input_file: Path to input video
    :param output_file: Path to output reversed video
    """
    print("Using ffmpeg at:", FFMPEG_PATH)
    print("Working dir:", os.getcwd())

    # Build ffmpeg command
    cmd = [
        FFMPEG_PATH,
        "-y",                   # Overwrite output
        "-i", input_file,
        "-an",                  # Drop audio completely
        "-filter_complex", "reverse",  # Reverse video frames
        output_file
    ]

    # Run ffmpeg
    print("Running command:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Saved reversed video to {output_file}")


# Example usage:
input_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\main2lean_in.mp4"
output_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\main2lean_in_reversed.mp4"

reverse_video_frames_only(input_video, output_video)
