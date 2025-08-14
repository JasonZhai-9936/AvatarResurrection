import os
import subprocess

FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Adjust if needed

def split_video_auto(input_file, time_split="00:02:16"):
    """
    Split a video into two clips at the given time (default 2 min 16 sec),
    automatically naming the outputs based on the original filename.
    """
    print("Using ffmpeg at:", FFMPEG_PATH)

    # Extract base name and extension
    base, ext = os.path.splitext(input_file)
    output_part1 = f"{base}_part1{ext}"
    output_part2 = f"{base}_part2{ext}"

    # First part: from start to time_split
    cmd1 = [
        FFMPEG_PATH,
        "-y",
        "-i", input_file,
        "-t", time_split,
        "-c", "copy",
        output_part1
    ]

    # Second part: from time_split to end
    cmd2 = [
        FFMPEG_PATH,
        "-y",
        "-i", input_file,
        "-ss", time_split,
        "-c", "copy",
        output_part2
    ]

    print("Running:", " ".join(cmd1))
    subprocess.run(cmd1, check=True)

    print("Running:", " ".join(cmd2))
    subprocess.run(cmd2, check=True)

    print(f"Saved clips:\n - {output_part1}\n - {output_part2}")


# Example usage
input_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\sora1.mp4"
split_video_auto(input_video)
