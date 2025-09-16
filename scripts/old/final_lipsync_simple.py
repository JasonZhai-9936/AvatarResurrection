#old lipsyncer
# Simple Equal-Time Lip Sync System
# Transcribes audio, maps words to clips, divides total time equally

import os
import random
import subprocess
import tempfile
import whisper
import pyphen
import pronouncing
import nltk
from nltk.corpus import cmudict
import re
from typing import List, Dict, Optional
import shutil

# Configuration - Use system PATH for FFmpeg
WHISPER_MODEL = "tiny"

def get_ffmpeg_path():
    """Get FFmpeg executable path from system PATH"""
    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe is None:
        raise RuntimeError("FFmpeg not found in system PATH. Please install FFmpeg and add it to PATH.")
    return ffmpeg_exe

def get_ffprobe_path():
    """Get FFprobe executable path from system PATH"""
    ffprobe_exe = shutil.which("ffprobe")
    if ffprobe_exe is None:
        raise RuntimeError("FFprobe not found in system PATH. Please install FFmpeg (includes ffprobe) and add it to PATH.")
    return ffprobe_exe

class SimpleLipSync:
    def __init__(self, archive_directory: str):
        self.archive_dir = archive_directory
        
        # Get FFmpeg paths from system PATH
        self.ffmpeg_path = get_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()
        
        # Initialize syllable counter
        self.dic = pyphen.Pyphen(lang='en')
        
        # Initialize CMU dictionary
        try:
            self.cmu_dict = cmudict.dict()
        except LookupError:
            print("Warning: Run nltk.download('cmudict')")
            self.cmu_dict = {}
        
        # Initialize Whisper model
        print(f"Loading Whisper model: {WHISPER_MODEL}")
        self.whisper_model = whisper.load_model(WHISPER_MODEL)
        
        # 8-viseme system mapping
        self.phoneme_to_viseme = {
            # 0: Neutral/Rest
            'AH0': 0, 'AH1': 0, 'AH2': 0, 'ER0': 0, 'ER1': 0, 'ER2': 0,
            'UH0': 0, 'UH1': 0, 'UH2': 0,
            
            # 1: Wide (A, E sounds)
            'AA0': 1, 'AA1': 1, 'AA2': 1, 'AE0': 1, 'AE1': 1, 'AE2': 1,
            'EH0': 1, 'EH1': 1, 'EH2': 1, 'AW0': 1, 'AW1': 1, 'AW2': 1,
            
            # 2: Round (O, U sounds)
            'AO0': 2, 'AO1': 2, 'AO2': 2, 'OW0': 2, 'OW1': 2, 'OW2': 2,
            'UW0': 2, 'UW1': 2, 'UW2': 2, 'OY0': 2, 'OY1': 2, 'OY2': 2,
            
            # 3: Small (I, E sounds)
            'IH0': 3, 'IH1': 3, 'IH2': 3, 'IY0': 3, 'IY1': 3, 'IY2': 3,
            'EY0': 3, 'EY1': 3, 'EY2': 3, 'AY0': 3, 'AY1': 3, 'AY2': 3,
            
            # 4: Closed (P, B, M)
            'P': 4, 'B': 4, 'M': 4,
            
            # 5: Lip-Teeth (F, V)
            'F': 5, 'V': 5,
            
            # 6: Tongue (T, D, N, L, S, Z, TH, R)
            'T': 6, 'D': 6, 'N': 6, 'L': 6, 'S': 6, 'Z': 6, 'TH': 6, 
            'DH': 6, 'R': 6, 'SH': 6, 'ZH': 6, 'CH': 6, 'JH': 6,
            
            # 7: Open (K, G, H, W, Y, NG)
            'K': 7, 'G': 7, 'HH': 7, 'W': 7, 'Y': 7, 'NG': 7,
        }
        
        self.available_prefixes = [
            "circle1", "eye_look1", "idle1", "idle2", "slight_look1", "slight_shake1"
        ]
        
        print(f"Simple lip sync initialized with archive: {archive_directory}")
        print(f"Using FFmpeg: {self.ffmpeg_path}")
        print(f"Using FFprobe: {self.ffprobe_path}")

    def extract_words_from_audio(self, audio_file: str) -> List[str]:
        """Extract just the words from audio, no timing"""
        print(f"Extracting words from: {audio_file}")
        
        result = self.whisper_model.transcribe(audio_file, verbose=False)
        text = result["text"].strip()
        
        # Clean and split into words
        words = []
        for word in text.split():
            # Remove punctuation and convert to lowercase
            clean_word = re.sub(r'[^a-zA-Z]', '', word).lower()
            if clean_word:
                words.append(clean_word)
        
        print(f"Extracted {len(words)} words: {words}")
        return words

    def get_audio_duration(self, audio_file: str) -> float:
        """Get the total duration of the audio file with improved error handling"""
        
        # Check if audio file exists
        if not os.path.exists(audio_file):
            print(f"Audio file does not exist: {audio_file}")
            return 10.0  # Default fallback
        
        # Check if ffprobe is available
        if not hasattr(self, 'ffprobe_path') or self.ffprobe_path is None:
            print("FFprobe not found in system PATH")
            return 10.0  # Default fallback
        
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            audio_file
        ]
        
        try:
            print(f"Running ffprobe command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration_str = result.stdout.strip()
            print(f"FFprobe output: '{duration_str}'")
            
            if duration_str:
                duration = float(duration_str)
                print(f"Audio duration: {duration:.2f} seconds")
                return duration
            else:
                print("FFprobe returned empty output")
                return 10.0  # Default fallback
                
        except subprocess.CalledProcessError as e:
            print(f"FFprobe command failed with return code {e.returncode}")
            print(f"Error output: {e.stderr}")
            print(f"Standard output: {e.stdout}")
            return 10.0  # Default fallback
            
        except ValueError as e:
            print(f"Could not parse duration '{duration_str}' as float: {e}")
            return 10.0  # Default fallback
            
        except Exception as e:
            print(f"Unexpected error getting audio duration: {e}")
            return 10.0  # Default fallback

    def get_syllables(self, word: str) -> int:
        """Get syllable count, capped at 6"""
        count = len(self.dic.inserted(word).split('-'))
        return min(count, 6)
    
    def get_phonemes(self, word: str) -> List[str]:
        """Get phonemes for a word"""
        word_lower = word.lower()
        if word_lower in self.cmu_dict:
            return self.cmu_dict[word_lower][0]
        
        phones_list = pronouncing.phones_for_word(word)
        if phones_list:
            return phones_list[0].split()
        return []
    
    def phoneme_to_viseme_id(self, phoneme: str) -> int:
        """Convert phoneme to viseme ID"""
        base_phoneme = re.sub(r'\d', '', phoneme)
        return self.phoneme_to_viseme.get(phoneme, 
               self.phoneme_to_viseme.get(base_phoneme, 0))
    
    def get_start_end_visemes(self, word: str) -> tuple:
        """Get starting and ending visemes for a word"""
        phonemes = self.get_phonemes(word)
        if not phonemes:
            return 0, 0
        
        start_viseme = self.phoneme_to_viseme_id(phonemes[0])
        end_viseme = self.phoneme_to_viseme_id(phonemes[-1])
        
        return start_viseme, end_viseme
    
    def get_clip_pattern(self, word: str) -> str:
        """Get the clip pattern needed for a word"""
        syllables = self.get_syllables(word)
        start_vis, end_vis = self.get_start_end_visemes(word)
        
        return f"{syllables}syl_s{start_vis}_e{end_vis}"
    
    def find_all_available_clips(self, pattern: str) -> List[str]:
        """Find all available clips for a pattern across all prefixes"""
        available_clips = []
        
        for prefix in self.available_prefixes:
            clip_filename = f"{prefix}_{pattern}.mp4"
            clip_path = os.path.join(self.archive_dir, clip_filename)
            if os.path.exists(clip_path):
                available_clips.append(clip_path)
        
        return available_clips

    def map_words_to_clips(self, words: List[str]) -> List[Dict]:
        """Map each word to a random clip from available options"""
        word_clips = []
        
        for word in words:
            pattern = self.get_clip_pattern(word)
            available_clips = self.find_all_available_clips(pattern)
            
            if available_clips:
                selected_clip = random.choice(available_clips)
                clip_info = {
                    "word": word,
                    "pattern": pattern,
                    "clip_path": selected_clip,
                    "prefix": os.path.basename(selected_clip).split('_')[0],
                    "found": True
                }
            else:
                # Fallback to any available clip
                fallback_clips = []
                for prefix in self.available_prefixes:
                    fallback_path = os.path.join(self.archive_dir, f"{prefix}_1syl_s0_e0.mp4")
                    if os.path.exists(fallback_path):
                        fallback_clips.append(fallback_path)
                
                clip_info = {
                    "word": word,
                    "pattern": pattern,
                    "clip_path": random.choice(fallback_clips) if fallback_clips else None,
                    "prefix": "fallback",
                    "found": False
                }
            
            word_clips.append(clip_info)
        
        return word_clips

    def create_equal_time_video(self, word_clips: List[Dict], total_duration: float, temp_dir: str) -> str:
        """Create video where each clip gets equal time"""
        if not word_clips:
            return None
        
        # Calculate time per word
        time_per_word = total_duration / len(word_clips)
        
        print(f"Creating video: {len(word_clips)} clips, {time_per_word:.2f}s each")
        
        # Create individual timed clips
        timed_clips = []
        
        for i, clip_info in enumerate(word_clips):
            if not clip_info["clip_path"]:
                continue
                
            clip_path = clip_info["clip_path"]
            temp_clip = os.path.join(temp_dir, f"word_{i:03d}.mp4")
            
            # Create clip with exact duration
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", clip_path,
                "-vf", "scale=640:480",
                "-t", str(time_per_word),
                "-c:v", "libx264",
                "-an",  # Remove audio
                temp_clip
            ]
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0 and os.path.exists(temp_clip):
                timed_clips.append(temp_clip)
                print(f"  Created: {clip_info['word']} ({clip_info['prefix']}) -> {time_per_word:.2f}s")
        
        if not timed_clips:
            return None
        
        # Create concat file with proper Windows path handling
        concat_file = os.path.join(temp_dir, "concat_list.txt")
        
        # Use forward slashes for FFmpeg compatibility
        with open(concat_file, 'w') as f:
            for clip in timed_clips:
                # Convert Windows paths to forward slashes for FFmpeg
                clip_path_fixed = clip.replace('\\', '/')
                f.write(f"file '{clip_path_fixed}'\n")
        
        print(f"Concat file created with {len(timed_clips)} clips")
        
        # Debug: Check if concat file exists and show content
        if os.path.exists(concat_file):
            print(f"Concat file exists at: {concat_file}")
            with open(concat_file, 'r') as f:
                content = f.read()
                print(f"Concat file content (first 200 chars): {content[:200]}...")
        else:
            print(f"ERROR: Concat file not created at: {concat_file}")
            return None
        
        # Concatenate all clips
        final_video = os.path.join(temp_dir, "video_only.mp4")
        concat_cmd = [
            self.ffmpeg_path, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            "-avoid_negative_ts", "make_zero",
            final_video
        ]
        
        print(f"Running concat command...")
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(final_video):
            print(f"Video concatenation successful: {final_video}")
            return final_video
        else:
            print(f"Concat failed. Return code: {result.returncode}")
            print(f"Error output: {result.stderr}")
            print(f"Standard output: {result.stdout}")
            
            # Try alternative approach if concat fails
            print("Trying alternative approach...")
            return self.create_video_alternative_method(word_clips, total_duration, temp_dir)
    
    def create_video_alternative_method(self, word_clips: List[Dict], total_duration: float, temp_dir: str) -> str:
        """Alternative video creation method using filter_complex"""
        if not word_clips:
            return None
        
        time_per_word = total_duration / len(word_clips)
        
        # Build a simpler filter command
        inputs = []
        filters = []
        
        for i, clip_info in enumerate(word_clips):
            if clip_info["clip_path"]:
                inputs.append(clip_info["clip_path"])
                filters.append(f"[{i}:v]scale=640:480,setpts=PTS*1.0,trim=duration={time_per_word}[v{i}]")
        
        if not inputs:
            return None
        
        # Create concat filter
        concat_inputs = "".join([f"[v{i}]" for i in range(len(inputs))])
        concat_filter = f"{concat_inputs}concat=n={len(inputs)}:v=1:a=0[out]"
        
        filter_complex = ";".join(filters + [concat_filter])
        
        final_video = os.path.join(temp_dir, "video_alt.mp4")
        
        cmd = [self.ffmpeg_path, "-y"]
        
        # Add inputs
        for input_file in inputs:
            cmd.extend(["-i", input_file])
        
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            final_video
        ])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(final_video):
            return final_video
        else:
            print(f"Alternative method also failed: {result.stderr}")
            return None

    def generate_simple_lip_sync(self, audio_file: str, output_file: str = None) -> str:
        """Main function - simple version without timing alignment"""
        if output_file is None:
            output_file = os.path.splitext(audio_file)[0] + "_simple_lipsynced.mp4"
        
        print("Starting simple lip sync generation...")
        
        # Step 1: Extract words (no timing)
        words = self.extract_words_from_audio(audio_file)
        if not words:
            print("No words found in audio")
            return None
        
        # Step 2: Get total audio duration
        total_duration = self.get_audio_duration(audio_file)
        print(f"Audio duration: {total_duration:.2f}s")
        
        # Step 3: Map words to clips
        word_clips = self.map_words_to_clips(words)
        
        print(f"\nWord-to-clip mapping:")
        for clip_info in word_clips:
            status = "✓" if clip_info["found"] else "⚠"
            print(f"  {status} {clip_info['word']} -> {clip_info['pattern']} ({clip_info['prefix']})")
        
        # Step 4: Create video with equal timing
        with tempfile.TemporaryDirectory() as temp_dir:
            print("\nCreating equal-time video...")
            
            video_file = self.create_equal_time_video(word_clips, total_duration, temp_dir)
            
            if not video_file:
                print("Failed to create video")
                return None
            
            # Step 5: Combine with original audio
            print("Combining with audio...")
            
            final_cmd = [
                self.ffmpeg_path, "-y",
                "-i", video_file,
                "-i", audio_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_file
            ]
            
            result = subprocess.run(final_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Simple lip sync video created: {output_file}")
                return output_file
            else:
                print(f"Final combine error: {result.stderr}")
                return None

    def analyze_clip_usage(self, words: List[str]) -> Dict:
        """Analyze what clips would be used for a word list"""
        word_clips = self.map_words_to_clips(words)
        
        usage_stats = {}
        prefix_stats = {}
        
        for clip_info in word_clips:
            pattern = clip_info["pattern"]
            prefix = clip_info["prefix"]
            
            if pattern not in usage_stats:
                usage_stats[pattern] = []
            usage_stats[pattern].append(clip_info["word"])
            
            if prefix not in prefix_stats:
                prefix_stats[prefix] = 0
            prefix_stats[prefix] += 1
        
        return {
            "pattern_usage": usage_stats,
            "prefix_distribution": prefix_stats,
            "total_words": len(words),
            "found_clips": sum(1 for c in word_clips if c["found"]),
            "missing_clips": sum(1 for c in word_clips if not c["found"])
        }


# Simple usage functions
def quick_simple_lipsync(audio_file: str, archive_dir: str = "./archive") -> str:
    """Quick function for simple lip sync"""
    system = SimpleLipSync(archive_dir)
    return system.generate_simple_lip_sync(audio_file)

def test_word_extraction(audio_file: str, archive_dir: str = "./archive"):
    """Test function to see word extraction and clip mapping"""
    system = SimpleLipSync(archive_dir)
    
    # Extract words
    words = system.extract_words_from_audio(audio_file)
    
    # Show analysis
    analysis = system.analyze_clip_usage(words)
    
    print("\nCLIP USAGE ANALYSIS:")
    print("=" * 40)
    print(f"Total words: {analysis['total_words']}")
    print(f"Found clips: {analysis['found_clips']}")
    print(f"Missing clips: {analysis['missing_clips']}")
    
    print("\nPrefix distribution:")
    for prefix, count in analysis['prefix_distribution'].items():
        print(f"  {prefix}: {count} clips")
    
    print(f"\nMost used patterns:")
    sorted_patterns = sorted(analysis['pattern_usage'].items(), 
                           key=lambda x: len(x[1]), reverse=True)
    
    for pattern, words in sorted_patterns[:5]:
        print(f"  {pattern}: {len(words)} words ({', '.join(words[:3])}{'...' if len(words) > 3 else ''})")


# Example usage
if __name__ == "__main__":
    print("SIMPLE EQUAL-TIME LIP SYNC SYSTEM")
    print("=" * 50)
    
    # Test with your audio file
    audio_file = "d1.wav"  # CHANGE THIS TO YOUR FILE
    archive_dir = "./archive"
    
    if os.path.exists(audio_file):
        try:
            # Option 1: Just generate the lip sync
            print("Generating simple lip sync...")
            result = quick_simple_lipsync(audio_file, archive_dir)
            
            if result:
                print(f"Success! Output: {result}")
            else:
                print("Failed to generate lip sync")
                
        except Exception as e:
            print(f"Error: {e}")
            
    else:
        print(f"Audio file not found: {audio_file}")
        print("\nTo use:")
        print("1. Change 'your_audio_file.wav' to your actual audio file path")
        print("2. Run the script")
        print("\nExample:")
        print("  audio_file = 'C:/Users/YourName/Desktop/speech.wav'")
        
        # Alternative: Test word extraction only
        print("\nOr test word extraction with an existing file:")
        print("test_word_extraction('your_file.wav')")