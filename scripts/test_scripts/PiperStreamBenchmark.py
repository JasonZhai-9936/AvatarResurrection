import time
import simpleaudio as sa
from piper import PiperVoice, SynthesisConfig

VOICE_PATH = "en_GB-semaine-medium.onnx"
TEXT = "This is a real-time streaming playback test using Piper, with correct pacing."
USE_CUDA = True  # True if you have onnxruntime-gpu installed


def main():
    print("Loading voice model...")
    print(f"Using CUDA: {USE_CUDA}")
    t0 = time.time()
    voice = PiperVoice.load(VOICE_PATH, use_cuda=USE_CUDA)
    print(f"Model loaded in {time.time() - t0:.2f} s")

    syn_config = SynthesisConfig(
        volume=1.0,
        length_scale=1.0,
        noise_scale=1.0,
        noise_w_scale=1.0,
        normalize_audio=True
    )

    print("Starting streaming synthesis with paced playback...")
    stream_start = time.time()
    playback_time = stream_start  # target playback timeline

    for i, chunk in enumerate(voice.synthesize(TEXT, syn_config=syn_config), start=1):
        elapsed = time.time() - stream_start
        duration = len(chunk.audio_int16_bytes) / (
            chunk.sample_rate * chunk.sample_channels * chunk.sample_width
        )
        print(f"Chunk {i}: ready at {elapsed:.2f}s, represents {duration:.2f}s of audio")

        # Align playback so chunks are scheduled at correct real-time pace
        now = time.time()
        if now < playback_time:
            time.sleep(playback_time - now)

        # Play chunk (blocking)
        play_obj = sa.play_buffer(
            chunk.audio_int16_bytes,
            num_channels=chunk.sample_channels,
            bytes_per_sample=chunk.sample_width,
            sample_rate=chunk.sample_rate,
        )
        play_obj.wait_done()

        playback_time += duration  # schedule next chunk

    print(f"Streaming + paced playback finished in {time.time() - stream_start:.2f} s")


if __name__ == "__main__":
    main()
