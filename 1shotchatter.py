import time
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

# -------------------------
# Benchmark: Model Loading
# -------------------------
t0 = time.time()
model = ChatterboxTTS.from_pretrained(device="cuda")
t1 = time.time()

# -------------------------
# Text with 4 emotions
# -------------------------
text = (
    "This is a neutral sentence for testing voice consistency. "
    "I am feeling very happy and excited about the results today! "
    "I am sad and disappointed that things didn’t go the way I hoped. "
    "I am angry and frustrated because nothing is working correctly."
)

# Your reference voice
AUDIO_PROMPT_PATH = "DavidA.mp3"

# -------------------------
# Benchmark: Generation
# -------------------------
t2 = time.time()
wav = model.generate(
    text,
    audio_prompt_path=AUDIO_PROMPT_PATH
)
t3 = time.time()

# -------------------------
# Save Output (Dynamic Name)
# -------------------------
# Uses current time to create a unique ID
timestamp = int(time.time())
OUTPUT = f"test_prompted_{timestamp}.wav"

ta.save(OUTPUT, wav, model.sr)

# -------------------------
# Final Benchmark Report
# -------------------------
print("\n===== BENCHMARK RESULTS =====")
print(f"Model Load Time:      {t1 - t0:.3f} seconds")
print(f"TTS Generation Time:  {t3 - t2:.3f} seconds")
print(f"Total Runtime:        {t3 - t0:.3f} seconds")
print(f"Output File:          {OUTPUT}")