import os

# Set the directory containing the MP4 clips
directory = os.getcwd()

# List all MP4 files and extract the word (filename without extension)
word_clips = [
    os.path.splitext(f)[0]
    for f in os.listdir(directory)
    if f.lower().endswith(".wav")
]

# Print the list of words
print("Found word clips:")
for word in sorted(word_clips):
    print("-", word)
