import os

def list_word_clips():
    # List all .mp4 files in the current directory
    clips = [f for f in os.listdir('.') if f.lower().endswith('.mp4')]
    total_count = len(clips)

    # Extract base words (before the _### suffix)
    words = [os.path.splitext(f)[0] for f in clips]
    base_words = [w.rsplit('_', 1)[0] for w in words]
    unique_count = len(set(base_words))

    
    for word in sorted(words):
        print(f"- {word}")
    print(f"Found {total_count} clips total.")
    print(f"Unique words (ignoring _### suffix): {unique_count}\n")

if __name__ == "__main__":
    list_word_clips()
