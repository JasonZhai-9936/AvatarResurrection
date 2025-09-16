import os
# Disable symlinks warning and use regular file copying instead
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from faster_whisper import WhisperModel

model_size = "tiny"

# Run on GPU with FP16
model = WhisperModel(model_size, device="cuda", compute_type="float16")

# or run on GPU with INT8
# model = WhisperModel(model_size, device="cuda", compute_type="int8_float16")
# or run on CPU with INT8
# model = WhisperModel(model_size, device="cpu", compute_type="int8")

segments, info = model.transcribe("d123.wav", beam_size=5, word_timestamps=True)

print("Detected language '%s' with probability %f" % (info.language, info.language_probability))

# Print segment-level transcription
print("\n=== SEGMENT-LEVEL TRANSCRIPTION ===")
for segment in segments:
    print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))

# Reset segments iterator for word-level processing
segments, info = model.transcribe("DavidA.mp3", beam_size=5, word_timestamps=True)

# Print word-level timestamps
print("\n=== WORD-LEVEL TIMESTAMPS ===")
for segment in segments:
    for word in segment.words:
        print("[%.2fs -> %.2fs] %s" % (word.start, word.end, word.word))