import time
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

# -------------------------
# 1. Benchmark: Model Loading
# -------------------------
print("Initializing model...")
t_start = time.time()

# English example
model = ChatterboxTTS.from_pretrained(device="cuda")

t_loaded = time.time()

# -------------------------
# 2. Benchmark: Generation
# -------------------------
text = "Ezreal and Jinx teamed up with Ahri, Yasuo, and Teemo to take down the enemy's Nexus in an epic late-game pentakill."

print(f"Generating audio for: '{text[:30]}...'")
wav = model.generate(text)

t_generated = time.time()

# -------------------------
# 3. Dynamic Naming & Saving
# -------------------------
# Create a unique filename using the current timestamp
timestamp = int(time.time())
output_filename = f"test-english_{timestamp}.wav"

ta.save(output_filename, wav, model.sr)

# -------------------------
# 4. Detailed Time Logging
# -------------------------
load_time = t_loaded - t_start
gen_time = t_generated - t_loaded
total_time = t_generated - t_start

print("\n===== DETAILED LOGS =====")
print(f"Model Load Time:   {load_time:.4f} sec")
print(f"Inference Time:    {gen_time:.4f} sec")
print(f"Total Runtime:     {total_time:.4f} sec")
print(f"File Saved As:     {output_filename}")
print("=========================")