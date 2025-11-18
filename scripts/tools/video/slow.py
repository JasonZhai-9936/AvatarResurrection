import os
from pydub import AudioSegment
from pydub.utils import which

# Manually set the ffmpeg binary path:
FFMPEG_PATH = r"C:\ffmpeg\bin\ffmpeg.exe"  # Adjust if different
AudioSegment.converter = FFMPEG_PATH

def slow_down_audio(input_file, output_file, speed_ratio):
    print("Using ffmpeg at:", AudioSegment.converter)
    print("Working dir:", os.getcwd())

    # Load audio
    sound = AudioSegment.from_file(input_file)

    # Slow down or speed up
    new_frame_rate = int(sound.frame_rate * speed_ratio)
    slowed = sound._spawn(sound.raw_data, overrides={'frame_rate': new_frame_rate})
    slowed = slowed.set_frame_rate(sound.frame_rate)

    # Export
    slowed.export(output_file, format=output_file.split('.')[-1])
    print(f"Saved slowed audio to {output_file}")

# Use absolute paths to be safe:
input_path = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\t1.wav"
output_path = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\tools\t1s.wav"

slow_down_audio(input_path, output_path, 0.80)

