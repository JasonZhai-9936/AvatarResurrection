import os
import subprocess

# Path to ffmpeg executable
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Adjust if needed

def extract_first_frame(input_file, output_image):
    """
    Extract the first frame of a video as an image.
    Keeps original aspect ratio and resolution.

    :param input_file: Path to input video
    :param output_image: Path to output image (jpg/png)
    """
    print("Using ffmpeg at:", FFMPEG_PATH)
    print("Working dir:", os.getcwd())

    # ffmpeg command:
    # -i input_file       : input video
    # -vf "select=eq(n\,0)" : pick frame number 0
    # -vframes 1          : only one frame
    # Output image format is inferred from extension
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i", input_file,
        "-vf", "select=eq(n\\,0)",
        "-vframes", "1",
        output_image
    ]

    print("Running command:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Saved first frame to {output_image}")


# Example usage:
input_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\lean_in_end.mp4"
output_image = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\l1_first_frame.png"

extract_first_frame(input_video, output_image)
