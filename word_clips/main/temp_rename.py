import os
from pathlib import Path

# Configure directory (current folder)
AUDIO_DIR = Path(".")

# Allowed audio extensions
EXTENSIONS = {".wav", ".mp4", ".m4a", ".ogg", ".flac"}

def rename_files():
    for file in AUDIO_DIR.iterdir():
        if file.is_file() and file.suffix.lower() in EXTENSIONS:
            base = file.stem  # filename without extension
            ext = file.suffix
            new_name = f"{"main"}_{base}{ext}"
            new_path = file.with_name(new_name)

            # Skip if already renamed
            if file.name == new_name:
                continue

            print(f"Renaming: {file.name} -> {new_name}")
            os.rename(file, new_path)

if __name__ == "__main__":
    rename_files()
    print("Done!")
