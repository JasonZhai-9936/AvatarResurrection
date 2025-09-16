# Enhanced Audio-to-Video Lip Sync System with Gap Filling
# Extends clips to fill gaps and uses idle clips for larger gaps

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
GAP_THRESHOLD = 0.7  # Gap threshold in seconds for using idle clip

class LipSyncSystem:
    def __init__(self, archive_directory: str, preferred_prefix: str = "idle1", 
                 clip_odds: Dict[str, float] = None, avoid_repeats: bool = False):
        self.archive_dir = archive_directory
        self.preferred_prefix = preferred_prefix
        self.gap_threshold = GAP_THRESHOLD
        
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
            "circle1", "eye_look1", "idle2", "slight_look1", "slight_shake1"
        ]
        
        # Set up clip odds (probability weights for each prefix)
        if clip_odds is None:
            self.clip_odds = {
                "circle1": 1.0,
                "eye_look1": 1.0,
                "idle2": 1.0,
                "slight_look1": 1.0,
                "slight_shake1": 1.0
            }
        else:
            self.clip_odds = clip_odds
        
        # Normalize odds
        total_odds = sum(self.clip_odds.values())
        if total_odds > 0:
            self.clip_odds = {k: v/total_odds for k, v in self.clip_odds.items()}
        
        self.avoid_repeats = avoid_repeats
        self.last_used_prefix = None
        
        print(f"Lip sync system initialized with archive: {archive_directory}")
        print(f"Gap threshold: {self.gap_threshold}s")
        print(f"Clip odds configured: {self.clip_odds}")
        print(f"Avoid repeats: {self.avoid_repeats}")

    def get_next_output_filename(self, base_name: str, directory: str = ".", extension: str = ".mp4") -> str:
        """Generate a unique output filename with sequential numbering."""
        os.makedirs(directory, exist_ok=True)
        
        if base_name.endswith(extension):
            base_name = base_name[:-len(extension)]
        
        counter = 1
        while True:
            filename = f"{base_name}_{counter:03d}{extension}"
            filepath = os.path.join(directory, filename)
            
            if not os.path.exists(filepath):
                return filepath
            
            counter += 1
            
            if counter > 9999:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{base_name}_{timestamp}{extension}"
                return os.path.join(directory, filename)

    def transcribe_audio_with_timing(self, audio_file: str) -> Dict:
        """Use Whisper to transcribe audio and get word-level timing"""
        print(f"Transcribing audio: {audio_file}")
        
        result = self.whisper_model.transcribe(
            audio_file,
            word_timestamps=True,
            verbose=False
        )
        
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
    
    def select_prefix_with_odds(self, available_prefixes: List[str]) -> str:
        """Select a prefix based on configured odds and repeat avoidance"""
        if not available_prefixes:
            return None
        
        if self.avoid_repeats and self.last_used_prefix in available_prefixes and len(available_prefixes) > 1:
            candidate_prefixes = [p for p in available_prefixes if p != self.last_used_prefix]
        else:
            candidate_prefixes = available_prefixes
        
        weights = []
        for prefix in candidate_prefixes:
            weight = self.clip_odds.get(prefix, 1.0)
            weights.append(weight)
        
        if sum(weights) == 0:
            weights = [1.0] * len(candidate_prefixes)
        
        selected = random.choices(candidate_prefixes, weights=weights, k=1)[0]
        self.last_used_prefix = selected
        
        return selected
    
    def find_clip_file(self, pattern: str, prefix: str = None) -> Optional[str]:
        """Find the actual clip file for a pattern"""
        available_clips = []
        available_prefixes_for_pattern = []
        
        if prefix:
            clip_filename = f"{prefix}_{pattern}.mp4"
            clip_path = os.path.join(self.archive_dir, clip_filename)
            if os.path.exists(clip_path):
                return clip_path
        
        for prefix in self.available_prefixes:
            clip_filename = f"{prefix}_{pattern}.mp4"
            clip_path = os.path.join(self.archive_dir, clip_filename)
            if os.path.exists(clip_path):
                available_clips.append(clip_path)
                available_prefixes_for_pattern.append(prefix)
        
        if available_prefixes_for_pattern:
            selected_prefix = self.select_prefix_with_odds(available_prefixes_for_pattern)
            if selected_prefix:
                clip_filename = f"{selected_prefix}_{pattern}.mp4"
                return os.path.join(self.archive_dir, clip_filename)
        
        return None
    
    def get_idle_clip(self) -> str:
        """Get the idle0.mp4 clip path"""
        idle_path = os.path.join(self.archive_dir, "idle0.mp4")
        if os.path.exists(idle_path):
            return idle_path
        # Fallback to any neutral clip
        return self.find_clip_file("1syl_s0_e0")
    
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
            return 1.0
    
    def create_word_clips(self, word_segments: List[Dict]) -> List[Dict]:
        """Create clip information for each word segment"""
        word_clips = []
        
        if self.avoid_repeats:
            self.last_used_prefix = None
        
        for i, segment in enumerate(word_segments):
            word = segment["word"]
            start_time = segment["start"]
            end_time = segment["end"]
            duration = end_time - start_time
            
            pattern = self.get_clip_pattern(word)
            clip_path = self.find_clip_file(pattern)
            
            if clip_path:
                clip_filename = os.path.basename(clip_path)
                clip_prefix = clip_filename.split('_')[0]
                
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
                neutral_pattern = f"{self.get_syllables(word)}syl_s0_e0"
                neutral_clip = self.find_clip_file(neutral_pattern)
                
                fallback_prefix = "none"
                if neutral_clip:
                    fallback_filename = os.path.basename(neutral_clip)
                    fallback_prefix = fallback_filename.split('_')[0]
                
                clip_info = {
                    "word": word,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "clip_path": neutral_clip or self.find_clip_file("1syl_s0_e0"),
                    "clip_prefix": fallback_prefix,
                    "pattern": pattern,
                    "found": False,
                    "fallback": True
                }
            
            word_clips.append(clip_info)
        
        return word_clips
    
    def process_gaps_and_extend_clips(self, word_clips: List[Dict], audio_duration: float) -> List[Dict]:
        """
        Process gaps between words and extend clips or insert idle clips
        Returns a list of clip segments with adjusted timing
        """
        if not word_clips:
            return []
        
        processed_clips = []
        
        for i in range(len(word_clips)):
            current_clip = word_clips[i].copy()
            
            # Check gap after current word (if not last word)
            if i < len(word_clips) - 1:
                next_clip = word_clips[i + 1]
                gap_start = current_clip["end_time"]
                gap_end = next_clip["start_time"]
                gap_duration = gap_end - gap_start
                
                if gap_duration > 0:
                    if gap_duration <= self.gap_threshold:
                        # Small gap: extend current and next clips equally
                        extend_amount = gap_duration / 2
                        current_clip["end_time"] += extend_amount
                        current_clip["extended_end"] = extend_amount
                        
                        # Mark the next clip to start earlier
                        if i + 1 < len(word_clips):
                            word_clips[i + 1]["start_time"] -= extend_amount
                            word_clips[i + 1]["extended_start"] = extend_amount
                    else:
                        # Large gap: insert idle clip
                        idle_clip = {
                            "word": "[idle]",
                            "start_time": gap_start,
                            "end_time": gap_end,
                            "duration": gap_duration,
                            "clip_path": self.get_idle_clip(),
                            "clip_prefix": "idle",
                            "pattern": "idle",
                            "is_gap_filler": True
                        }
                        processed_clips.append(current_clip)
                        processed_clips.append(idle_clip)
                        continue
            
            # Handle last clip - extend to audio duration if needed
            elif i == len(word_clips) - 1:
                remaining_time = audio_duration - current_clip["end_time"]
                if remaining_time > 0:
                    if remaining_time <= self.gap_threshold:
                        # Extend the last clip to the end
                        current_clip["end_time"] = audio_duration
                        current_clip["extended_end"] = remaining_time
                    else:
                        # Add the current clip first
                        processed_clips.append(current_clip)
                        # Then add idle clip for the remaining duration
                        idle_clip = {
                            "word": "[idle_end]",
                            "start_time": current_clip["end_time"],
                            "end_time": audio_duration,
                            "duration": remaining_time,
                            "clip_path": self.get_idle_clip(),
                            "clip_prefix": "idle",
                            "pattern": "idle",
                            "is_gap_filler": True
                        }
                        processed_clips.append(idle_clip)
                        continue
            
            processed_clips.append(current_clip)
        
        return processed_clips
    
    def create_enhanced_video_sequence(self, word_clips: List[Dict], audio_duration: float, temp_dir: str) -> str:
        """Create video sequence with gap filling"""
        if not word_clips:
            return None
        
        # Process gaps and extend clips
        processed_clips = self.process_gaps_and_extend_clips(word_clips, audio_duration)
        
        # Create individual timed clips
        timed_clips = []
        
        for i, clip_info in enumerate(processed_clips):
            clip_path = clip_info["clip_path"]
            start_time = clip_info["start_time"]
            end_time = clip_info["end_time"]
            duration = end_time - start_time
            
            # Get original clip duration
            original_duration = self.get_video_duration(clip_path)
            
            # Calculate speed adjustment
            speed_factor = original_duration / duration if duration > 0 else 1.0
            
            # Handle extended clips (trim from beginning or end as needed)
            trim_start = 0
            trim_end = original_duration
            
            if "extended_start" in clip_info:
                # This clip was extended at the beginning
                extend_ratio = clip_info["extended_start"] / duration
                trim_start = original_duration * extend_ratio
            
            if "extended_end" in clip_info:
                # This clip was extended at the end
                extend_ratio = clip_info["extended_end"] / duration
                trim_end = original_duration * (1 - extend_ratio)
            
            # Create individual timed clip
            temp_clip = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
            
            # Build filter for trimming and speed adjustment
            if clip_info.get("is_gap_filler"):
                # For idle clips, loop if needed and adjust speed
                filter_str = f"scale=640:480,setpts=PTS*{speed_factor}"
            else:
                # For word clips, handle trimming if extended
                if "extended_start" in clip_info or "extended_end" in clip_info:
                    filter_str = f"trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS,scale=640:480,setpts=PTS*{speed_factor}"
                else:
                    filter_str = f"scale=640:480,setpts=PTS*{speed_factor}"
            
            cmd = [
                os.path.join(FFMPEG_BIN_PATH, "ffmpeg"), "-y",
                "-i", clip_path,
                "-vf", filter_str,
                "-t", str(duration),
                "-c:v", "libx264",
                "-an",
                temp_clip
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(temp_clip):
                timed_clips.append(temp_clip)
            else:
                print(f"Warning: Failed to create clip {i}: {result.stderr}")
        
        if not timed_clips:
            return None
        
        # Create concat file
        concat_file = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_file, 'w') as f:
            for clip_path in timed_clips:
                f.write(f"file '{clip_path}'\n")
        
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
        """Main function to generate lip-synced video from audio with gap filling"""
        # Determine output path
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(audio_file))[0] + "_lipsynced"
            
            if output_dir is None:
                output_dir = os.path.dirname(audio_file) or "."
            
            if use_sequential:
                output_file = self.get_next_output_filename(base_name, output_dir, ".mp4")
            else:
                output_file = os.path.join(output_dir, base_name + ".mp4")
        
        print(f"Output will be saved as: {output_file}")
        print("Starting lip sync generation with gap filling...")
        
        # Get actual audio duration first
        audio_duration = self.get_audio_duration(audio_file)
        print(f"Audio duration: {audio_duration:.2f}s")
        
        # Step 1: Transcribe audio with timing
        transcription = self.transcribe_audio_with_timing(audio_file)
        word_segments = transcription["word_segments"]
        
        if not word_segments:
            print("No words detected in audio")
            return None
        
        print(f"Transcription: {transcription['full_text']}")
        
        # Step 2: Create word clips mapping
        word_clips = self.create_word_clips(word_segments)
        
        # Print mapping and gap analysis
        print("\nWord-to-clip mapping and gap analysis:")
        for i, clip_info in enumerate(word_clips):
            status = "✓" if clip_info["found"] else "⚠"
            clip_type = clip_info.get("clip_prefix", "unknown")
            print(f"  {status} {clip_info['word']} → {clip_info['pattern']} [{clip_type}] ({clip_info['start_time']:.2f}s-{clip_info['end_time']:.2f}s)")
            
            # Show gap info
            if i < len(word_clips) - 1:
                gap = word_clips[i + 1]["start_time"] - clip_info["end_time"]
                if gap > 0:
                    action = "extend clips" if gap <= self.gap_threshold else "insert idle"
                    print(f"    Gap: {gap:.3f}s → {action}")
            elif i == len(word_clips) - 1:
                # Show remaining audio time
                remaining = audio_duration - clip_info["end_time"]
                if remaining > 0:
                    action = "extend last clip" if remaining <= self.gap_threshold else "add idle clip"
                    print(f"    Remaining audio: {remaining:.3f}s → {action}")
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            print("\nProcessing video clips with gap filling...")
            
            # Step 3: Create video sequence with gap handling
            video_file = self.create_enhanced_video_sequence(word_clips, audio_duration, temp_dir)
            
            if not video_file:
                print("Failed to create video sequence")
                return None
            
            print("Combining with audio...")
            
            # Step 4: Combine with audio (no -shortest flag)
            final_cmd = [
                os.path.join(FFMPEG_BIN_PATH, "ffmpeg"), "-y",
                "-i", video_file,
                "-i", audio_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                output_file
            ]
            
            result = subprocess.run(final_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✓ Lip sync video created: {output_file}")
                return output_file
            else:
                print(f"Final combine error: {result.stderr}")
                return None
    
    def get_audio_duration(self, audio_file: str) -> float:
        """Get the duration of an audio file"""
        cmd = [
            os.path.join(FFMPEG_BIN_PATH, "ffprobe"),
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            audio_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            # Fallback: try to get from transcription
            return 10.0  # Default fallback


# Example usage
if __name__ == "__main__":
    ARCHIVE_DIR = "./archive"
    PREFERRED_PREFIX = "idle2"
    OUTPUT_DIR = "./output"
    
    CLIP_ODDS = {
        "circle1": 0.5,
        "eye_look1": 1.0,
        "idle2": 2.0,
        "slight_look1": 1.0,
        "slight_shake1": 0.3
    }
    
    AVOID_REPEATS = True
    
    print("ENHANCED LIP SYNC SYSTEM WITH GAP FILLING")
    print("=" * 60)
    
    try:
        lipsync = LipSyncSystem(
            ARCHIVE_DIR, 
            PREFERRED_PREFIX,
            clip_odds=CLIP_ODDS,
            avoid_repeats=AVOID_REPEATS
        )
        
        test_audio = "evo.wav"  # Replace with your audio file
        
        if os.path.exists(test_audio):
            print(f"\nProcessing: {test_audio}")
            print(f"Gap handling: <{GAP_THRESHOLD}s = extend clips, >{GAP_THRESHOLD}s = idle clip")
            
            output_video = lipsync.generate_lip_sync_video(
                test_audio,
                output_dir=OUTPUT_DIR,
                use_sequential=True
            )
            
            if output_video:
                print(f"\n✓ Success! Generated: {output_video}")
            else:
                print(f"\n✗ Failed to generate video")
        
    except Exception as e:
        print(f"Error: {e}")