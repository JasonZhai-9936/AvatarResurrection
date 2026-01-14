import os
import subprocess
import sys
import shutil

# --- CONFIGURATION ---
REF_AUDIO = "DavidA.mp3"
REF_TEXT = "This is the transcript of David's audio clip." 
TARGET_TEXT = "This is the new audio generated using David's voice profile. Windows compatibility mode active."
MODEL_REPO = "fishaudio/openaudio-s1-mini"
CHECKPOINT_DIR = "checkpoints/openaudio-s1-mini"

def run_command(command, description):
    print(f"\n>>> {description}...")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Failed during: {description}")
        sys.exit(1)

def main():
    if not os.path.exists("fish-speech"):
        run_command(["git", "clone", "https://github.com/fishaudio/fish-speech.git"], "Cloning Repository")
        os.chdir("fish-speech")
        run_command([sys.executable, "-m", "pip", "install", "-e", "."], "First-time Install")
    else:
        os.chdir("fish-speech")

    if not os.path.exists(CHECKPOINT_DIR):
        run_command(["huggingface-cli", "download", MODEL_REPO, "--local-dir", CHECKPOINT_DIR], "Downloading Weights")

    parent_audio = os.path.join("..", REF_AUDIO)
    if os.path.exists(parent_audio):
        shutil.copy(parent_audio, REF_AUDIO)

    # --- INFERENCE PIPELINE ---

    # Step 1: Voice Extraction
    run_command([
        "python", "fish_speech/models/dac/inference.py",
        "-i", REF_AUDIO,
        "--checkpoint-path", f"{CHECKPOINT_DIR}/codec.pth"
    ], "Step 1/3: Extracting voice")

    # Step 2: Semantic Generation
    # We removed --compile and --half. This is the most stable 'High Quality' mode for Windows.
    run_command([
        "python", "fish_speech/models/text2semantic/inference.py",
        "--text", TARGET_TEXT,
        "--prompt-text", REF_TEXT,
        "--prompt-tokens", "fake.npy",
        "--checkpoint-path", CHECKPOINT_DIR
    ], "Step 2/3: Semantic Generation")

    code_file = "codes_0.npy"
    if os.path.exists(os.path.join("temp", "codes_0.npy")):
        code_file = os.path.join("temp", "codes_0.npy")

    # Step 3: Final Decode
    run_command([
        "python", "fish_speech/models/dac/inference.py",
        "-i", code_file,
        "--checkpoint-path", f"{CHECKPOINT_DIR}/codec.pth",
        "-o", "final_cloned_output.wav"
    ], "Step 3/3: Decoding")

    if os.path.exists("final_cloned_output.wav"):
        shutil.move("final_cloned_output.wav", "../final_cloned_output.wav")
        print("\nSUCCESS! Saved as 'final_cloned_output.wav'")

if __name__ == "__main__":
    main()