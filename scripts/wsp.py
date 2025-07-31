import os
import whisper

# Ensure ffmpeg is available
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"
os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")

# Load Whisper model
model = whisper.load_model("tiny")  # or base/small/medium/large

# Transcribe with word-level timestamps
result = model.transcribe("d123.wav", word_timestamps=True)

# Print word timings
for segment in result["segments"]:
    for w in segment["words"]:
        print(f"{w['word']}  start={w['start']:.2f}s  end={w['end']:.2f}s")
