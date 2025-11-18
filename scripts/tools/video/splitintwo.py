import os
import subprocess

FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Adjust if needed

def split_video_maximum_precision(input_file, time_split="00:00:02.750"):
    """
    Maximum precision video splitting. Speed is sacrificed for absolute accuracy.
    Uses input seeking, frame-perfect encoding, and highest quality settings.
    """
    print("Using ffmpeg at:", FFMPEG_PATH)
    
    # Extract base name and extension
    base, ext = os.path.splitext(input_file)
    output_part1 = f"{base}_part1{ext}"
    output_part2 = f"{base}_part2{ext}"
    
    # First part: from start to exact split time
    # Using highest precision settings
    cmd1 = [
        FFMPEG_PATH,
        "-y",
        "-i", input_file,
        "-t", time_split,                    # Exact duration
        "-c:v", "libx264",                   # Re-encode video
        "-preset", "veryslow",               # Highest quality preset
        "-crf", "0",                         # Lossless encoding
        "-pix_fmt", "yuv444p",              # Highest quality pixel format
        "-c:a", "pcm_s32le",                # Lossless audio
        "-avoid_negative_ts", "make_zero",   # Handle timestamp issues
        "-fflags", "+genpts",               # Generate presentation timestamps
        "-vsync", "cfr",                    # Constant frame rate
        "-r", "60",                         # Force high frame rate for precision
        output_part1
    ]
    
    # Second part: from exact split time to end
    # Using input seeking for maximum accuracy
    cmd2 = [
        FFMPEG_PATH,
        "-y",
        "-ss", time_split,                   # Seek on input (most accurate)
        "-i", input_file,
        "-c:v", "libx264",
        "-preset", "veryslow",
        "-crf", "0",                         # Lossless
        "-pix_fmt", "yuv444p",
        "-c:a", "pcm_s32le",                # Lossless audio
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-vsync", "cfr",
        "-r", "60",
        output_part2
    ]
    
    print("Running maximum precision split (part 1)...")
    print("Command:", " ".join(cmd1))
    subprocess.run(cmd1, check=True)
    
    print("Running maximum precision split (part 2)...")
    print("Command:", " ".join(cmd2))
    subprocess.run(cmd2, check=True)
    
    print(f"Maximum precision split completed!")
    print(f"Saved clips:\n - {output_part1}\n - {output_part2}")
    print("Note: Files are lossless and will be larger than original.")

# Example usage
if __name__ == "__main__":
    input_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\sora2.mp4"
    split_video_maximum_precision(input_video)