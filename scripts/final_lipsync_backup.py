# Complete Audio-to-Video Lip Sync System with Sequential Output Naming
# Uses Whisper for speech recognition and your video clips for lip sync generation

import os
import json
import random
import subprocess
from pathlib import Path
import tempfile
import whisper
import pyphen
import pronouncing
import nltk
from nltk.corpus import cmudict
import re
from typing import List, Dict, Tuple, Optional
import wave
import contextlib
from datetime import datetime

# Configuration
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"
WHISPER_MODEL = "base"  # Options: tiny, base, small, medium, large

class LipSyncSystem:
    def __init__(self, archive_directory: str, preferred_prefix: str = "idle1"):
        self.archive_dir = archive_directory
        self.preferred_prefix = preferred_prefix
        
        # Initialize syllable counter
        self.dic = pyphen.Pyphen(lang='en')
        
        # Initialize CMU dictionary
        try:
            self.cmu_dict = cmudict.dict()
        except LookupError:
            print("Warning: CMU dictionary not found. Run: nltk.download('cmudict')")
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
        
        self.viseme_names = ["Neutral", "Wide", "Round", "Small", "Closed", "Lip-Teeth", "Tongue", "Open"]
        self.max_syllables = 6
        
        # Available clip prefixes from your archive
        self.available_prefixes = [
            "circle1", "eye_look1",  "idle2", "slight_look1", "slight_shake1"
        ]
        
        print(f"Lip sync system initialized with archive: {archive_directory}")

    def get_next_output_filename(self, base_name: str, directory: str = ".", extension: str = ".mp4") -> str:
        """
        Generate a unique output filename with sequential numbering.
        
        Args:
            base_name: Base name for the file (without extension)
            directory: Directory to save the file in
            extension: File extension (default: .mp4)
            
        Returns:
            Unique filename with sequential number
        """
        # Ensure directory exists
        os.makedirs(directory, exist_ok=True)
        
        # Clean the base name (remove existing extension if any)
        if base_name.endswith(extension):
            base_name = base_name[:-len(extension)]
        
        # Check for existing files with the same base name
        counter = 1
        while True:
            # Format: basename_001.mp4, basename_002.mp4, etc.
            filename = f"{base_name}_{counter:03d}{extension}"
            filepath = os.path.join(directory, filename)
            
            if not os.path.exists(filepath):
                return filepath
            
            counter += 1
            
            # Safety limit to prevent infinite loops
            if counter > 9999:
                # Use timestamp as fallback
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{base_name}_{timestamp}{extension}"
                return os.path.join(directory, filename)

    def transcribe_audio_with_timing(self, audio_file: str) -> Dict:
        """Use Whisper to transcribe audio and get word-level timing"""
        print(f"Transcribing audio: {audio_file}")
        
        # Transcribe with word-level timestamps
        result = self.whisper_model.transcribe(
            audio_file,
            word_timestamps=True,
            verbose=False
        )
        
        # Extract word timing information
        word_segments = []
        
        for segment in result["segments"]:
            if "words" in segment:
                for word_info in segment["words"]:
                    word_segments.append({
                        "word": word_info["word"].strip().lower(),
                        "start": word_info["start"],
                        "end": word_info["end"],
                        "confidence": word_info.get("probability", 1.0)
                    })
        
        print(f"Found {len(word_segments)} words with timing")
        return {
            "full_text": result["text"],
            "word_segments": word_segments,
            "duration": result["segments"][-1]["end"] if result["segments"] else 0
        }

    def get_syllables(self, word: str) -> int:
        """Get syllable count, capped at max_syllables"""
        count = len(self.dic.inserted(word).split('-'))
        return min(count, self.max_syllables)
    
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
    
    def get_start_end_visemes(self, word: str) -> Tuple[int, int]:
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
    
    def find_clip_file(self, pattern: str, prefix: str = None) -> Optional[str]:
        """Find the actual clip file for a pattern - randomly selects from all available prefixes"""
        available_clips = []
        
        # If specific prefix requested, try that first
        if prefix:
            clip_filename = f"{prefix}_{pattern}.mp4"
            clip_path = os.path.join(self.archive_dir, clip_filename)
            if os.path.exists(clip_path):
                return clip_path
        
        # Find all available clips for this pattern across all prefixes
        for prefix in self.available_prefixes:
            clip_filename = f"{prefix}_{pattern}.mp4"
            clip_path = os.path.join(self.archive_dir, clip_filename)
            if os.path.exists(clip_path):
                available_clips.append(clip_path)
        
        # Randomly select from available clips
        if available_clips:
            return random.choice(available_clips)
        
        return None
    
    def get_video_duration(self, video_path: str) -> float:
        """Get the duration of a video file"""
        cmd = [
            os.path.join(FFMPEG_BIN_PATH, "ffprobe"),
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            return 1.0  # Default fallback duration
    
    def create_word_clips(self, word_segments: List[Dict]) -> List[Dict]:
        """Create clip information for each word segment"""
        word_clips = []
        
        for i, segment in enumerate(word_segments):
            word = segment["word"]
            start_time = segment["start"]
            end_time = segment["end"]
            duration = end_time - start_time
            
            # Get the appropriate clip
            pattern = self.get_clip_pattern(word)
            clip_path = self.find_clip_file(pattern)
            
            if clip_path:
                # Extract the prefix from the clip path
                clip_filename = os.path.basename(clip_path)
                clip_prefix = clip_filename.split('_')[0]  # Gets "idle2", "slight_shake1", etc.
                
                clip_info = {
                    "word": word,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "clip_path": clip_path,
                    "clip_prefix": clip_prefix,
                    "pattern": pattern,
                    "found": True
                }
            else:
                # Fallback to neutral clip
                neutral_pattern = f"{self.get_syllables(word)}syl_s0_e0"
                neutral_clip = self.find_clip_file(neutral_pattern)
                
                # Extract prefix from fallback clip if found
                fallback_prefix = "none"
                if neutral_clip:
                    fallback_filename = os.path.basename(neutral_clip)
                    fallback_prefix = fallback_filename.split('_')[0]
                
                clip_info = {
                    "word": word,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "clip_path": neutral_clip or self.find_clip_file("1syl_s0_e0"),  # Ultimate fallback
                    "clip_prefix": fallback_prefix,
                    "pattern": pattern,
                    "found": False,
                    "fallback": True
                }
            
            word_clips.append(clip_info)
        
        return word_clips
    
    def create_simple_video_sequence(self, word_clips: List[Dict], audio_duration: float, temp_dir: str) -> str:
        """Create video sequence using simpler approach - individual clips then concatenate"""
        if not word_clips:
            return None
        
        # Create individual timed clips
        timed_clips = []
        
        for i, clip_info in enumerate(word_clips):
            clip_path = clip_info["clip_path"]
            start_time = clip_info["start_time"]
            duration = clip_info["duration"]
            
            # Create individual timed clip
            temp_clip = os.path.join(temp_dir, f"word_{i:03d}.mp4")
            
            cmd = [
                os.path.join(FFMPEG_BIN_PATH, "ffmpeg"), "-y",
                "-i", clip_path,
                "-vf", f"scale=640:480,setpts=PTS*{duration}/{self.get_video_duration(clip_path)}",
                "-t", str(duration),
                "-c:v", "libx264",
                "-an",  # Remove audio from individual clips
                temp_clip
            ]
            
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(temp_clip):
                timed_clips.append({
                    "file": temp_clip,
                    "start": start_time,
                    "duration": duration
                })
        
        if not timed_clips:
            return None
        
        # Sort by start time
        timed_clips.sort(key=lambda x: x["start"])
        
        # Create concat file with gaps filled
        concat_file = os.path.join(temp_dir, "concat_list.txt")
        current_time = 0.0
        
        with open(concat_file, 'w') as f:
            for i, clip_info in enumerate(timed_clips):
                start_time = clip_info["start"]
                duration = clip_info["duration"]
                
                # Fill gap if needed
                if start_time > current_time:
                    gap_duration = start_time - current_time
                    # Use previous clip or neutral for gap
                    gap_source = timed_clips[i-1]["file"] if i > 0 else clip_info["file"]
                    gap_clip = os.path.join(temp_dir, f"gap_{i:03d}.mp4")
                    
                    # Create gap clip
                    gap_cmd = [
                        os.path.join(FFMPEG_BIN_PATH, "ffmpeg"), "-y",
                        "-i", gap_source,
                        "-vf", f"scale=640:480,loop=loop=-1:size=1:start=0",
                        "-t", str(gap_duration),
                        "-c:v", "libx264",
                        "-an",
                        gap_clip
                    ]
                    subprocess.run(gap_cmd, capture_output=True)
                    
                    if os.path.exists(gap_clip):
                        f.write(f"file '{gap_clip}'\n")
                
                # Add main clip
                f.write(f"file '{clip_info['file']}'\n")
                current_time = start_time + duration
        
        # Concatenate all clips
        final_video = os.path.join(temp_dir, "video_only.mp4")
        concat_cmd = [
            os.path.join(FFMPEG_BIN_PATH, "ffmpeg"), "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            final_video
        ]
        
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(final_video):
            return final_video
        else:
            print(f"Concat error: {result.stderr}")
            return None
    
    def generate_lip_sync_video(self, audio_file: str, output_file: str = None, 
                                output_dir: str = None, use_sequential: bool = True) -> str:
        """
        Main function to generate lip-synced video from audio
        
        Args:
            audio_file: Path to input audio file
            output_file: Specific output file path (overrides sequential naming)
            output_dir: Directory for output files (default: same as audio file)
            use_sequential: If True, use sequential numbering (default: True)
            
        Returns:
            Path to generated video file
        """
        # Determine output path
        if output_file is None:
            # Get base name from audio file
            base_name = os.path.splitext(os.path.basename(audio_file))[0] + "_lipsynced"
            
            # Determine output directory
            if output_dir is None:
                output_dir = os.path.dirname(audio_file) or "."
            
            # Get sequential filename if enabled
            if use_sequential:
                output_file = self.get_next_output_filename(base_name, output_dir, ".mp4")
            else:
                output_file = os.path.join(output_dir, base_name + ".mp4")
        
        print(f"Output will be saved as: {output_file}")
        print("Starting lip sync generation...")
        
        # Step 1: Transcribe audio with timing
        transcription = self.transcribe_audio_with_timing(audio_file)
        word_segments = transcription["word_segments"]
        audio_duration = transcription["duration"]
        
        if not word_segments:
            print("No words detected in audio")
            return None
        
        print(f"Transcription: {transcription['full_text']}")
        
        # Step 2: Create word clips mapping
        word_clips = self.create_word_clips(word_segments)
        
        # Print mapping for debugging
        print("\nWord-to-clip mapping:")
        for clip_info in word_clips:
            status = "✓" if clip_info["found"] else "⚠" 
            clip_type = clip_info.get("clip_prefix", "unknown")
            print(f"  {status} {clip_info['word']} → {clip_info['pattern']} [{clip_type}] ({clip_info['start_time']:.2f}s-{clip_info['end_time']:.2f}s)")
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            print("\nProcessing video clips...")
            
            # Step 3: Create video sequence
            video_file = self.create_simple_video_sequence(word_clips, audio_duration, temp_dir)
            
            if not video_file:
                print("Failed to create video sequence")
                return None
            
            print("Combining with audio...")
            
            # Step 4: Combine with audio
            final_cmd = [
                os.path.join(FFMPEG_BIN_PATH, "ffmpeg"), "-y",
                "-i", video_file,
                "-i", audio_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_file
            ]
            
            result = subprocess.run(final_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✓ Lip sync video created: {output_file}")
                return output_file
            else:
                print(f"Final combine error: {result.stderr}")
                return None
    
    def batch_process(self, audio_files: List[str], output_dir: str = None, use_sequential: bool = True):
        """
        Process multiple audio files
        
        Args:
            audio_files: List of audio file paths
            output_dir: Directory for output files
            use_sequential: If True, use sequential numbering
            
        Returns:
            List of processing results
        """
        results = []
        
        for audio_file in audio_files:
            print(f"\n{'='*60}")
            print(f"Processing file {audio_files.index(audio_file) + 1}/{len(audio_files)}: {audio_file}")
            print('='*60)
            
            result = self.generate_lip_sync_video(
                audio_file, 
                output_file=None,
                output_dir=output_dir,
                use_sequential=use_sequential
            )
            
            results.append({
                "input": audio_file,
                "output": result,
                "success": result is not None
            })
        
        # Print summary
        print(f"\n{'='*60}")
        print("BATCH PROCESSING SUMMARY")
        print('='*60)
        successful = sum(1 for r in results if r["success"])
        print(f"Successfully processed: {successful}/{len(results)} files")
        
        for r in results:
            status = "✓" if r["success"] else "✗"
            output = r["output"] if r["output"] else "Failed"
            print(f"{status} {os.path.basename(r['input'])} → {output}")
        
        return results


# Example usage and testing
if __name__ == "__main__":
    # Configuration
    ARCHIVE_DIR = "./archive"  # Your clip archive directory
    PREFERRED_PREFIX = "idle1"  # Default animation style
    OUTPUT_DIR = "./output"  # Output directory for generated videos
    
    print("COMPLETE LIP SYNC SYSTEM WITH SEQUENTIAL NAMING")
    print("=" * 50)
    
    # Initialize the system
    try:
        lipsync = LipSyncSystem(ARCHIVE_DIR, PREFERRED_PREFIX)
        
        # Example 1: Single file with auto-sequential naming
        test_audio = "d1.wav"  # Replace with your audio file
        
        if os.path.exists(test_audio):
            print(f"\nExample 1: Processing single file with sequential naming")
            print(f"Input: {test_audio}")
            
            # This will create: output/d1_lipsynced_001.mp4, _002.mp4, etc.
            output_video = lipsync.generate_lip_sync_video(
                test_audio,
                output_dir=OUTPUT_DIR,
                use_sequential=True  # Enable sequential naming
            )
            
            if output_video:
                print(f"\n✓ Success! Generated: {output_video}")
            else:
                print(f"\n✗ Failed to generate video")
        
       
        
    except Exception as e:
        print(f"Error initializing system: {e}")
        print("\nMake sure you have:")
        print("1. FFmpeg installed at the specified path")
        print("2. The archive directory with your video clips")
        print("3. Required Python packages: whisper, pyphen, pronouncing, nltk")


# Helper function for quick testing with sequential naming
def quick_lipsync(audio_file: str, archive_dir: str = "./archive", output_dir: str = "./output") -> str:
    """
    Quick lip sync function with automatic sequential naming
    
    Args:
        audio_file: Path to audio file
        archive_dir: Directory containing video clips
        output_dir: Directory for output files
        
    Returns:
        Path to generated video file
    """
    system = LipSyncSystem(archive_dir)
    return system.generate_lip_sync_video(
        audio_file, 
        output_dir=output_dir,
        use_sequential=True
    )


# Utility function to clean up old outputs
def cleanup_old_outputs(directory: str, pattern: str = "*_lipsynced_*.mp4", keep_recent: int = 5):
    """
    Clean up old output files, keeping only the most recent ones
    
    Args:
        directory: Directory to clean
        pattern: File pattern to match
        keep_recent: Number of recent files to keep
    """
    import glob
    
    files = glob.glob(os.path.join(directory, pattern))
    files.sort(key=os.path.getmtime, reverse=True)
    
    files_to_delete = files[keep_recent:]
    
    if files_to_delete:
        print(f"Cleaning up {len(files_to_delete)} old files...")
        for f in files_to_delete:
            try:
                os.remove(f)
                print(f"  Deleted: {os.path.basename(f)}")
            except Exception as e:
                print(f"  Error deleting {f}: {e}")
    else:
        print("No old files to clean up")