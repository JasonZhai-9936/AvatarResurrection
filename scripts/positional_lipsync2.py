# simplified_lipsyncer.py - Rewritten for Robust Timeline Alignment
#
# REQUIRED LIBRARIES:
# pip install openai-whisper syllables colorama
#
# REQUIRED EXTERNAL SOFTWARE:
# FFmpeg - https://ffmpeg.org/download.html
# After downloading, update the FFMPEG_BIN_PATH variable below.

import os
import time
import subprocess
import tempfile
import re
import json
import shutil
import whisper
import difflib
import syllables
from typing import List, Tuple, Optional, Dict
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# --- CONFIGURATION ---

# STEP 1: Set the project directory structure
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
AVATAR_DIR = os.path.join(PROJECT_DIR, "avatars", "Darwin")
WORD_CLIPS_DIR = os.path.join(AVATAR_DIR, "movinghead", "word_clips", "main")

# STEP 2: VERIFY THIS PATH
# Hardcode the full path to the FFmpeg 'bin' directory.
# This is the most reliable way to ensure the script finds FFmpeg.
# Use double backslashes (\\) or a raw string (r"").
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin" # Example: r"C:\Users\Jason\Desktop\ffmpeg\bin"

# Candidates for the neutral/silent mouth position clip
NEUTRAL_CLIP_CANDIDATES = ["neutral", "silent"]
# Minimum duration of a pause to be rendered as a silence clip
MIN_SILENCE_DURATION = 0.1 # seconds

SIMILARITY_CONFIG = {
    "enable_fuzzy_matching": True,
    "similarity_threshold": 0.6,
    "max_length_difference": 3,
}

SYLLABLE_FALLBACKS = {
    1: "the", 2: "hello", 3: "computer", 4: "information", 5: "understanding"
}

# Add any known problematic clips here
CORRUPTED_CLIPS = []

class SimplifiedLipsyncer:
    def __init__(self, avatar_name: str = "Darwin", model_size: str = "tiny"):
        self.avatar_name = avatar_name
        self.word_clips_dir = WORD_CLIPS_DIR
        self.temp_dir = os.path.join(PROJECT_DIR, "tempstream", "simplified_lipsync_rebuilt")
        os.makedirs(self.temp_dir, exist_ok=True)

        self.ffmpeg_path, self.ffprobe_path = self._find_ffmpeg()
        if not self.ffmpeg_path:
            raise EnvironmentError("FFmpeg not found. Please verify the FFMPEG_BIN_PATH variable in the script.")

        print(f"{Fore.CYAN}Initializing lipsyncer for avatar '{avatar_name}'...{Style.RESET_ALL}")
        self.model = whisper.load_model(model_size, device="cpu")
        self.word_clips = self._load_word_clips()
        self.neutral_clip_path = self._find_neutral_clip()
        
        self._print_system_status()

    def _find_ffmpeg(self) -> Tuple[Optional[str], Optional[str]]:
        # Check for the hardcoded path first
        if FFMPEG_BIN_PATH and os.path.isdir(FFMPEG_BIN_PATH):
            ffmpeg_path = os.path.join(FFMPEG_BIN_PATH, 'ffmpeg.exe')
            ffprobe_path = os.path.join(FFMPEG_BIN_PATH, 'ffprobe.exe')
            if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
                print(f"{Fore.GREEN}Found FFmpeg via hardcoded path: {ffmpeg_path}{Style.RESET_ALL}")
                return ffmpeg_path, ffprobe_path

        # If not found, search the system PATH
        for path_name in ('ffmpeg', 'ffmpeg.exe'):
            path = shutil.which(path_name)
            if path:
                ffprobe_path = path.replace('ffmpeg', 'ffprobe')
                print(f"{Fore.GREEN}Found FFmpeg in system PATH: {path}{Style.RESET_ALL}")
                return path, ffprobe_path
        
        print(f"{Fore.RED}FFmpeg not found. Please verify the FFMPEG_BIN_PATH variable in the script or add FFmpeg to your system's PATH.{Style.RESET_ALL}")
        return None, None

    def _load_word_clips(self) -> Dict[str, str]:
        word_clips = {}
        if not os.path.isdir(self.word_clips_dir):
            print(f"{Fore.RED}Word clips directory not found: {self.word_clips_dir}{Style.RESET_ALL}")
            return {}
        for filename in os.listdir(self.word_clips_dir):
            if filename.endswith('.mp4'):
                word = os.path.splitext(filename)[0].replace('main_', '')
                if word:
                    word_clips[word.lower()] = os.path.join(self.word_clips_dir, filename)
        return word_clips

    def _find_neutral_clip(self) -> Optional[str]:
        for candidate in NEUTRAL_CLIP_CANDIDATES:
            if candidate in self.word_clips:
                print(f"{Fore.GREEN}Found neutral clip: {os.path.basename(self.word_clips[candidate])}{Style.RESET_ALL}")
                return self.word_clips[candidate]
        
        print(f"{Fore.YELLOW}Warning: No dedicated neutral clip found. Will use fallback.{Style.RESET_ALL}")
        fallback_word = SYLLABLE_FALLBACKS.get(1)
        if fallback_word and fallback_word in self.word_clips:
            return self.word_clips[fallback_word]
            
        if self.word_clips:
            return next(iter(self.word_clips.values()))

        return None

    def _print_system_status(self):
        print(f"{Fore.CYAN}{'-'*40}\nSystem Status:\n{'-'*40}{Style.RESET_ALL}")
        print(f"Clips Loaded: {len(self.word_clips)}")
        if not self.neutral_clip_path:
            print(f"{Fore.RED}CRITICAL: No neutral clip could be found. Silences will not be rendered.{Style.RESET_ALL}")
        if not self.word_clips:
            print(f"{Fore.RED}CRITICAL: No word clips found in {self.word_clips_dir}.{Style.RESET_ALL}")

    def get_audio_duration(self, audio_path: str) -> float:
        cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"{Fore.RED}Error getting audio duration: {e}{Style.RESET_ALL}")
            return 0.0

    def get_video_info(self, video_path: str) -> Dict:
        """Gets the duration of a video clip using ffprobe."""
        cmd = [self.ffprobe_path, '-v', 'error', '-show_entries', 'stream=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {'duration': float(result.stdout.strip())}
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"{Fore.YELLOW}Warning: Could not get video info for {os.path.basename(video_path)}: {e}{Style.RESET_ALL}")
            return {'duration': 1.0} # Assume 1-second duration on error

    def create_timeline(self, audio_path: str) -> List[Dict]:
        """Transcribes audio and builds a comprehensive timeline of words and silences."""
        print(f"{Fore.CYAN}Step 1: Building timeline from '{os.path.basename(audio_path)}'...{Style.RESET_ALL}")
        total_duration = self.get_audio_duration(audio_path)
        if total_duration == 0: return []

        result = self.model.transcribe(audio_path, word_timestamps=True)
        
        timeline = []
        last_timestamp = 0.0
        
        words = []
        if 'segments' in result:
            for segment in result['segments']:
                if 'words' in segment:
                    words.extend(segment['words'])

        if not words:
            print(f"{Fore.YELLOW}No words transcribed. Treating audio as full silence.{Style.RESET_ALL}")
            timeline.append({'type': 'silence', 'start': 0, 'end': total_duration})
            return timeline

        # Handle initial silence
        first_word_start = words[0]['start']
        if first_word_start > MIN_SILENCE_DURATION:
            timeline.append({'type': 'silence', 'start': 0, 'end': first_word_start})
        
        # Process words and the gaps between them
        for i, word_info in enumerate(words):
            word_start, word_end = word_info['start'], word_info['end']
            
            # Gap before this word
            gap = word_start - last_timestamp
            if gap > MIN_SILENCE_DURATION:
                timeline.append({'type': 'silence', 'start': last_timestamp, 'end': word_start})

            # The word itself
            clean_word = re.sub(r'[^\w\']', '', word_info['word'].lower()).strip()
            if clean_word:
                 timeline.append({'type': 'word', 'start': word_start, 'end': word_end, 'content': clean_word})

            last_timestamp = word_end
        
        # Handle final silence
        if total_duration - last_timestamp > MIN_SILENCE_DURATION:
            timeline.append({'type': 'silence', 'start': last_timestamp, 'end': total_duration})

        # Add duration to all segments for convenience
        for segment in timeline:
            segment['duration'] = segment['end'] - segment['start']

        print(f"{Fore.GREEN}Timeline created with {len(timeline)} segments.{Style.RESET_ALL}")
        return timeline

    def find_word_clip(self, word: str) -> Optional[str]:
        """Finds a video clip for a word with fallbacks."""
        if word in self.word_clips and os.path.basename(self.word_clips[word]) not in CORRUPTED_CLIPS:
            return self.word_clips[word]
        
        # Fuzzy matching
        if SIMILARITY_CONFIG["enable_fuzzy_matching"]:
            best_match, best_score = None, 0.0
            for available_word, path in self.word_clips.items():
                if abs(len(word) - len(available_word)) > SIMILARITY_CONFIG["max_length_difference"]: continue
                similarity = difflib.SequenceMatcher(None, word, available_word).ratio()
                if similarity > best_score and similarity >= SIMILARITY_CONFIG["similarity_threshold"]:
                    best_match, best_score = path, similarity
            if best_match: return best_match
        
        # Syllable fallback
        try:
            count = syllables.estimate(word)
            count = min(count, max(SYLLABLE_FALLBACKS.keys()))
            fallback_word = SYLLABLE_FALLBACKS.get(count)
            if fallback_word and fallback_word in self.word_clips: return self.word_clips[fallback_word]
        except: pass
        
        # Ultimate fallback
        return self.neutral_clip_path

    def process_segment(self, segment: Dict, index: int) -> Optional[str]:
        """Generates a video clip for a single timeline segment."""
        target_duration = segment['duration']
        if target_duration <= 0.01: return None # Skip tiny segments

        if segment['type'] == 'word':
            source_clip_path = self.find_word_clip(segment['content'])
            label = segment['content']
        else: # 'silence'
            source_clip_path = self.neutral_clip_path
            label = 'silence'
        
        if not source_clip_path or not os.path.exists(source_clip_path):
            print(f"{Fore.RED}Source clip not found for segment '{label}'. Skipping.{Style.RESET_ALL}")
            return None
        
        # --- REVERTED TO OLDER, MORE COMPATIBLE LOGIC ---
        video_info = self.get_video_info(source_clip_path)
        original_duration = video_info.get('duration', 1.0)
        if original_duration <= 0: original_duration = 1.0

        # Calculate speed factor, ensuring no division by zero
        speed_factor = original_duration / target_duration if target_duration > 0 else 1.0
        # Clamp speed factor to a reasonable range to avoid extreme speeds
        speed_factor = max(0.25, min(4.0, speed_factor))

        output_path = os.path.join(self.temp_dir, f"segment_{index:04d}_{label}.mp4")
        
        # Use the older, more compatible setpts filter
        cmd = [
            self.ffmpeg_path, '-y', '-i', source_clip_path,
            '-vf', f"setpts={1/speed_factor}*PTS",
            '-an', # Remove audio from segment clips
            '-t', str(round(target_duration, 4)), # Use a rounded duration
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            output_path
        ]
        
        try:
            # For debugging, we can capture the output
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                # If there's an error, print FFmpeg's output
                print(f"{Fore.RED}FFmpeg error processing segment '{label}'. Exit code: {result.returncode}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}FFmpeg stderr: {result.stderr[-500:]}{Style.RESET_ALL}") # Print last 500 chars of error
                return None

            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return output_path
            return None
        except Exception as e:
            print(f"{Fore.RED}Python error calling FFmpeg for segment '{label}': {e}{Style.RESET_ALL}")
            return None

    def concatenate_clips(self, clip_paths: List[str], output_path: str) -> bool:
        """Stitches multiple video clips into one."""
        if not clip_paths: return False
        
        concat_file = os.path.join(self.temp_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            for path in clip_paths:
                # This corrected method avoids the f-string backslash error
                fixed_path = os.path.abspath(path).replace('\\', '/')
                f.write(f"file '{fixed_path}'\n")
        
        cmd = [self.ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', output_path]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
            return os.path.exists(output_path)
        except Exception as e:
            print(f"{Fore.RED}Concatenation failed: {e}{Style.RESET_ALL}")
            return False

    def add_audio_to_video(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Merges the final video with the original audio."""
        cmd = [self.ffmpeg_path, '-y', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', output_path]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            return os.path.exists(output_path)
        except Exception as e:
            print(f"{Fore.RED}Failed to add audio: {e}{Style.RESET_ALL}")
            return False

    def generate_lipsync(self, audio_file: str, output_filename: str = None) -> Optional[str]:
        """Main function to generate the lipsynced video."""
        start_time = time.time()
        if not os.path.exists(audio_file):
            print(f"{Fore.RED}Audio file not found: {audio_file}{Style.RESET_ALL}")
            return None
            
        # Step 1: Create the timeline
        timeline = self.create_timeline(audio_file)
        if not timeline:
            print(f"{Fore.RED}Failed to create timeline.{Style.RESET_ALL}")
            return None
            
        # Step 2: Process each segment in the timeline
        print(f"{Fore.CYAN}Step 2: Processing {len(timeline)} timeline segments...{Style.RESET_ALL}")
        processed_clips = []
        for i, segment in enumerate(timeline):
            clip_path = self.process_segment(segment, i)
            if clip_path:
                processed_clips.append(clip_path)

        if not processed_clips:
            print(f"{Fore.RED}No clips were processed successfully.{Style.RESET_ALL}")
            return None

        # Step 3: Concatenate segments into a single video
        print(f"{Fore.CYAN}Step 3: Stitching processed clips...{Style.RESET_ALL}")
        silent_video_path = os.path.join(self.temp_dir, "silent_video.mp4")
        if not self.concatenate_clips(processed_clips, silent_video_path):
            return None

        # Step 4: Add original audio
        print(f"{Fore.CYAN}Step 4: Merging with original audio...{Style.RESET_ALL}")
        if not output_filename:
            output_filename = f"lipsync_output_{int(start_time)}.mp4"
        
        # Place final output in a predictable 'outputs' folder
        output_dir = os.path.join(PROJECT_DIR, "tempstream", "outputs")
        os.makedirs(output_dir, exist_ok=True)
        final_output_path = os.path.join(output_dir, output_filename)
        
        if not self.add_audio_to_video(silent_video_path, audio_file, final_output_path):
            return None
        
        # Finalization and Cleanup
        elapsed = time.time() - start_time
        print(f"{Fore.GREEN}✓ Success! Lipsync video created in {elapsed:.2f} seconds.{Style.RESET_ALL}")
        print(f"--> {final_output_path}")
        
        # Clean the temp directory
        try:
            shutil.rmtree(self.temp_dir)
        except OSError as e:
            print(f"{Fore.YELLOW}Warning: Could not remove temp directory {self.temp_dir}: {e}{Style.RESET_ALL}")
        
        return final_output_path


# --- Main execution block for testing ---
def test_simplified_system():
    print(f"\n{Fore.YELLOW}{'='*60}\nRunning Lipsync System Test\n{'='*60}{Style.RESET_ALL}")
    
    # Find a test audio file
    test_audio_path = os.path.join(PROJECT_DIR, "tempstream", "d2.wav") # Example audio file
    if not os.path.exists(test_audio_path):
        print(f"{Fore.RED}Test audio file not found at: {test_audio_path}{Style.RESET_ALL}")
        print("Please ensure a test .wav file exists to run the test.")
        return

    try:
        lipsyncer = SimplifiedLipsyncer()
        lipsyncer.generate_lipsync(test_audio_path)
    except Exception as e:
        print(f"\n{Fore.RED}An error occurred during the test: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simplified_system()