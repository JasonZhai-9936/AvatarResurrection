import time
import os
import wave
from piper import PiperVoice, SynthesisConfig

VOICE_PATH = "en_GB-semaine-medium.onnx"  # downloaded voice
TEXT = "Welcome to the world of speech synthesis! This is a streaming test. Choose output filename without overwriting. Model loaded in"
USE_CUDA = True  # set to True if onnxruntime-gpu is installed
BASE_FILENAME = "output.wav"


def next_available_filename(base_filename: str) -> str:
    """Generate a new filename if base exists: output.wav -> output_1.wav etc."""
    if not os.path.exists(base_filename):
        return base_filename
    name, ext = os.path.splitext(base_filename)
    i = 1
    while True:
        new_name = f"{name}_{i}{ext}"
        if not os.path.exists(new_name):
            return new_name
        i += 1


def main():
    start = time.time()
    print("Loading voice model...")
    print(f"Using CUDA: {USE_CUDA}")
    voice = PiperVoice.load(VOICE_PATH, use_cuda=USE_CUDA)
    load_done = time.time()
    print(f"Model loaded in {load_done - start:.2f} s")

    # Config (adjust voice speed, volume etc.)
    syn_config = SynthesisConfig(
        volume=1.0,
        length_scale=1.0,
        noise_scale=1.0,
        noise_w_scale=1.0,
        normalize_audio=True
    )

    # Choose output filename without overwriting
    output_file = next_available_filename(BASE_FILENAME)
    print(f"Saving streamed audio to {output_file}")

    # We'll collect chunks and then write them as WAV
    audio_chunks = []
    print("Streaming synthesis started...")
    stream_start = time.time()

    for i, chunk in enumerate(voice.synthesize(TEXT, syn_config=syn_config), start=1):
        elapsed = time.time() - stream_start
        print(f"Chunk {i} at {elapsed:.2f}s ({len(chunk.audio_int16_bytes)} bytes)")
        audio_chunks.append(chunk)

    stream_done = time.time()
    print(f"Streaming finished in {stream_done - stream_start:.2f} s")
    print(f"Total time (load + stream): {stream_done - start:.2f} s")

    # Write collected audio to WAV
    if audio_chunks:
        sr = audio_chunks[0].sample_rate
        sw = audio_chunks[0].sample_width
        ch = audio_chunks[0].sample_channels
        with wave.open(output_file, "wb") as wav_file:
            wav_file.setnchannels(ch)
            wav_file.setsampwidth(sw)
            wav_file.setframerate(sr)
            for chunk in audio_chunks:
                wav_file.writeframes(chunk.audio_int16_bytes)
        print(f"Audio saved to {output_file}")


if __name__ == "__main__":
    main()
