# positional_lipsync.py - Integrated Sora-based lipsync for the Darwin avatar system
"""
This module provides enhanced lipsync functionality using the proven Sora lipsync system.
It integrates with the Darwin avatar's positional video system and TTS generation.

Main function for external use:
    generate_lipsync_video(text: str, output_filename: str = None) -> str
"""

import os
import time
import random
import threading
import subprocess
import tempfile
import re
import json
import shutil
import whisper
import difflib
import nltk
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from colorama import Fore, Style, init
from TTS_Piper import generate_and_stream_audio

# Download required NLTK data
try:
    nltk.data.find('corpora/cmudict')
except LookupError:
    nltk.download('cmudict')

# Initialize colorama
init(autoreset=True)

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
AVATAR_DIR = os.path.join(PROJECT_DIR, "avatars", "Darwin")

# Sora clips directory structure
SORA_CLIPS_DIR = os.path.join(AVATAR_DIR, "sora", "all")

# Output directory for lipsync videos
LIPSYNC_OUTPUT_DIR = os.path.join(PROJECT_DIR, "temp_lipsync")

# Ensure output directory exists
os.makedirs(LIPSYNC_OUTPUT_DIR, exist_ok=True)

# Ensure ffmpeg is available
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"
if os.path.exists(FFMPEG_BIN_PATH):
    os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")

class PositionalLipSyncSystem:
    """
    Enhanced lipsync system using Sora clips with syllable-based matching
    """
    
    def __init__(self, clips_folder_path: str = None, model_size: str = "tiny"):
        # Set clips folder path
        self.clips_folder = Path(clips_folder_path) if clips_folder_path else Path(SORA_CLIPS_DIR)
        
        # Initialize temp directory
        self.temp_dir = os.path.join(PROJECT_DIR, "tempstream", "positional_lipsync_temp")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(LIPSYNC_OUTPUT_DIR, exist_ok=True)
        
        # Initialize Whisper model
        try:
            self.model = whisper.load_model(model_size, device="cpu")
            print(f"{Fore.GREEN}[POSLIPSYNC] Whisper model loaded: {model_size}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Error loading Whisper: {e}{Style.RESET_ALL}")
            self.model = None
        
        # Initialize CMU dictionary for syllable counting
        try:
            from nltk.corpus import cmudict
            self.pronunciation_dict = cmudict.dict()
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Error loading CMU dictionary: {e}{Style.RESET_ALL}")
            self.pronunciation_dict = {}
        
        # Check FFmpeg availability
        self.ffmpeg_available = self._check_ffmpeg()
        
        # Load available clips organized by syllable count
        self.available_clips = self._scan_clips_folder()
        
        # Configuration settings
        self.config = {
            'sentence_pause_duration': 0.25,  # seconds of pause between sentences
            'idle_clip_name': 'idle.mp4',     # name of idle clip in clips folder
            'use_sentence_pauses': False,      # enable/disable pauses between sentences
            'max_clip_duration_diff': 0.5,    # max difference in duration for clip selection
            'speed_adjustment_range': (0.5, 2.0)  # min and max speed adjustment
        }
        
        # Validate idle clip exists
        self.idle_clip_path = self.clips_folder / self.config['idle_clip_name']
        if self.idle_clip_path.exists():
            self.config['use_sentence_pauses'] = True
            print(f"{Fore.GREEN}[POSLIPSYNC] Found idle clip: {self.idle_clip_path}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[POSLIPSYNC] Idle clip not found, disabling sentence pauses{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}[POSLIPSYNC] Positional LipSync System initialized{Style.RESET_ALL}")
        self._print_status()

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available with GPU acceleration detection"""
        ffmpeg_paths = [
            'ffmpeg', 'ffmpeg.exe',
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe'
        ]
        
        for path in ffmpeg_paths:
            try:
                result = subprocess.run([path, '-version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.ffmpeg_path = path
                    self.ffprobe_path = path.replace('ffmpeg', 'ffprobe')
                    
                    # Check for hardware acceleration
                    if 'nvenc' in result.stdout.lower():
                        self.has_nvidia_gpu = True
                        print(f"{Fore.GREEN}[POSLIPSYNC] NVIDIA GPU acceleration available{Style.RESET_ALL}")
                    else:
                        self.has_nvidia_gpu = False
                        print(f"{Fore.YELLOW}[POSLIPSYNC] No GPU acceleration detected{Style.RESET_ALL}")
                    
                    return True
            except:
                continue
        
        print(f"{Fore.RED}[POSLIPSYNC] FFmpeg not found{Style.RESET_ALL}")
        return False

    def _scan_clips_folder(self) -> Dict[int, List[str]]:
        """Scan the clips folder and organize clips by syllable count"""
        clips_by_syllables = {}
        
        if not self.clips_folder.exists():
            print(f"{Fore.RED}[POSLIPSYNC] Clips folder not found: {self.clips_folder}{Style.RESET_ALL}")
            return clips_by_syllables
        
        # Scan for video files with the naming convention (number).mp4
        for file_path in self.clips_folder.glob("*.mp4"):
            filename = file_path.stem
            
            # Extract number from filename (e.g., "1", "2 (2)", "3")
            match = re.match(r'(\d+)', filename)
            if match:
                syllable_count = int(match.group(1))
                
                if syllable_count not in clips_by_syllables:
                    clips_by_syllables[syllable_count] = []
                clips_by_syllables[syllable_count].append(str(file_path))
        
        return clips_by_syllables
    
    def _print_status(self):
        """Print system status"""
        total_clips = sum(len(clips) for clips in self.available_clips.values())
        print(f"{Fore.CYAN}[POSLIPSYNC] Loaded {total_clips} clips across {len(self.available_clips)} syllable counts{Style.RESET_ALL}")
        
        for syllable_count, clips in sorted(self.available_clips.items()):
            print(f"{Fore.CYAN}[POSLIPSYNC] {syllable_count} syllables: {len(clips)} clips{Style.RESET_ALL}")

    def count_syllables_in_word(self, word: str) -> int:
        """Count syllables in a word using CMU Pronouncing Dictionary"""
        word = word.lower().strip('.,!?";:')
        
        if word in self.pronunciation_dict:
            # Count vowel sounds (which correspond to syllables)
            pronunciations = self.pronunciation_dict[word]
            # Use the first pronunciation
            syllable_count = len([phoneme for phoneme in pronunciations[0] if phoneme[-1].isdigit()])
            return max(1, syllable_count)  # At least 1 syllable
        else:
            # Fallback: estimate syllables by counting vowel groups
            vowels = "aeiouy"
            word = word.lower()
            syllable_count = 0
            prev_was_vowel = False
            
            for char in word:
                is_vowel = char in vowels
                if is_vowel and not prev_was_vowel:
                    syllable_count += 1
                prev_was_vowel = is_vowel
            
            # Handle silent 'e'
            if word.endswith('e') and syllable_count > 1:
                syllable_count -= 1
            
            return max(1, syllable_count)
    
    def count_syllables_in_sentence(self, sentence: str) -> int:
        """Count total syllables in a sentence"""
        words = re.findall(r'\b\w+\b', sentence)
        return sum(self.count_syllables_in_word(word) for word in words)

    def transcribe_audio(self, audio_file: str) -> List[Dict]:
        """Transcribe audio using Whisper with word-level timestamps"""
        if not self.model:
            print(f"{Fore.RED}[POSLIPSYNC] Whisper model not available{Style.RESET_ALL}")
            return []
        
        try:
            print(f"{Fore.CYAN}[POSLIPSYNC] Transcribing audio: {os.path.basename(audio_file)}{Style.RESET_ALL}")
            result = self.model.transcribe(audio_file, word_timestamps=True)
            
            # Extract sentences with timing information
            sentences = []
            current_sentence = {
                'words': [],
                'text': '',
                'start_time': None,
                'end_time': None
            }
            
            for segment in result["segments"]:
                for word_info in segment["words"]:
                    word = word_info['word'].strip()
                    
                    # Start new sentence if this is the first word
                    if current_sentence['start_time'] is None:
                        current_sentence['start_time'] = word_info['start']
                    
                    current_sentence['words'].append(word_info)
                    current_sentence['text'] += word
                    current_sentence['end_time'] = word_info['end']
                    
                    # Check if this word ends a sentence
                    if word.endswith(('.', '!', '?', ',')):
                        # Finalize current sentence
                        sentences.append(current_sentence.copy())
                        
                        # Start new sentence
                        current_sentence = {
                            'words': [],
                            'text': '',
                            'start_time': None,
                            'end_time': None
                        }
            
            # Add any remaining sentence
            if current_sentence['words']:
                sentences.append(current_sentence)
            
            print(f"{Fore.GREEN}[POSLIPSYNC] Split into {len(sentences)} sentences{Style.RESET_ALL}")
            for i, sentence in enumerate(sentences):
                print(f"{Fore.CYAN}[POSLIPSYNC] Sentence {i+1}: '{sentence['text'].strip()}' ({sentence['start_time']:.2f}s - {sentence['end_time']:.2f}s){Style.RESET_ALL}")
            
            return sentences
            
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Transcription error: {e}{Style.RESET_ALL}")
            return []

    def find_suitable_clip(self, sentence_syllables: int) -> Optional[str]:
        """Find a random clip that matches the syllable count (or closest available)"""
        available_counts = sorted(self.available_clips.keys())
        
        if not available_counts:
            print(f"{Fore.RED}[POSLIPSYNC] No clips available{Style.RESET_ALL}")
            return None
        
        # Try exact match first
        if sentence_syllables in self.available_clips:
            selected_clip = random.choice(self.available_clips[sentence_syllables])
            print(f"{Fore.GREEN}[POSLIPSYNC] Exact match for {sentence_syllables} syllables: {os.path.basename(selected_clip)}{Style.RESET_ALL}")
            return selected_clip
        
        # Find closest syllable count
        closest_count = min(available_counts, key=lambda x: abs(x - sentence_syllables))
        selected_clip = random.choice(self.available_clips[closest_count])
        print(f"{Fore.YELLOW}[POSLIPSYNC] No exact match for {sentence_syllables} syllables, using {closest_count} syllables: {os.path.basename(selected_clip)}{Style.RESET_ALL}")
        
        return selected_clip

    def extract_audio_segment(self, input_audio: str, start_time: float, end_time: float, output_path: str):
        """Extract audio segment using ffmpeg with fast seeking"""
        duration = end_time - start_time
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Use faster audio extraction - seek BEFORE input
        cmd = [
            self.ffmpeg_path, '-y',
            '-ss', str(start_time),  # Seek BEFORE input for faster processing
            '-i', input_audio,
            '-t', str(duration),
            '-acodec', 'copy',  # Use copy instead of re-encoding when possible
            '-avoid_negative_ts', 'make_zero',
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=15)
            print(f"{Fore.GREEN}[POSLIPSYNC] Fast extracted: {os.path.basename(output_path)}{Style.RESET_ALL}")
            return True
        except subprocess.CalledProcessError as e:
            # Fallback to slower but more compatible method
            print(f"{Fore.YELLOW}[POSLIPSYNC] Fast extraction failed, using fallback{Style.RESET_ALL}")
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', input_audio,
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'pcm_s16le',
                '-ar', '44100', '-ac', '2',
                output_path
            ]
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=20)
                print(f"{Fore.GREEN}[POSLIPSYNC] Fallback extracted: {os.path.basename(output_path)}{Style.RESET_ALL}")
                return True
            except Exception as e2:
                print(f"{Fore.RED}[POSLIPSYNC] Audio extraction failed: {e2}{Style.RESET_ALL}")
                return False

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe"""
        cmd = [
            self.ffprobe_path, '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Error getting video duration for {os.path.basename(video_path)}: {e}{Style.RESET_ALL}")
            return 1.0  # Default fallback duration

    def get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration using ffprobe"""
        cmd = [
            self.ffprobe_path, '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Error getting audio duration: {e}{Style.RESET_ALL}")
            return 1.0

    def sync_audio_to_video(self, audio_path: str, video_path: str, output_path: str) -> bool:
        """Sync audio to video, adjusting video speed if necessary"""
        try:
            # Get durations
            audio_duration = self.get_audio_duration(audio_path)
            video_duration = self.get_video_duration(video_path)
            
            print(f"{Fore.CYAN}[POSLIPSYNC] Syncing: Audio {audio_duration:.2f}s, Video {video_duration:.2f}s{Style.RESET_ALL}")
            
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            if abs(audio_duration - video_duration) <= self.config['max_clip_duration_diff']:
                # Durations are close enough, simple merge with audio
                cmd = [
                    self.ffmpeg_path, '-y',
                    '-i', video_path,
                    '-i', audio_path,
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-ac', '2',
                    '-pix_fmt', 'yuv420p',
                    '-map', '0:v:0',  # Take video from first input
                    '-map', '1:a:0',  # Take audio from second input
                    '-shortest',
                    output_path
                ]
            else:
                # Adjust video speed to match audio duration
                speed_factor = min(max(video_duration / audio_duration, 
                                     self.config['speed_adjustment_range'][0]), 
                                 self.config['speed_adjustment_range'][1])
                
                print(f"{Fore.YELLOW}[POSLIPSYNC] Adjusting video speed by factor: {speed_factor:.3f}{Style.RESET_ALL}")
                
                cmd = [
                    self.ffmpeg_path, '-y',
                    '-i', video_path,
                    '-i', audio_path,
                    '-filter:v', f'setpts={1/speed_factor}*PTS',
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-ac', '2',
                    '-pix_fmt', 'yuv420p',
                    '-map', '0:v:0',  # Take video from first input
                    '-map', '1:a:0',  # Take audio from second input
                    '-shortest',
                    output_path
                ]
            
            print(f"{Fore.CYAN}[POSLIPSYNC] FFmpeg command: {' '.join(cmd[:8])}...{Style.RESET_ALL}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            
            # Verify output has both video and audio
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                # Check if output has audio stream
                self._verify_video_has_audio(output_path)
                print(f"{Fore.GREEN}[POSLIPSYNC] Successfully synced: {os.path.basename(output_path)}{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[POSLIPSYNC] Sync output file is invalid{Style.RESET_ALL}")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"{Fore.RED}[POSLIPSYNC] FFmpeg sync error: {e.stderr}{Style.RESET_ALL}")
            return False
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Sync error: {e}{Style.RESET_ALL}")
            return False

    def _verify_video_has_audio(self, video_path: str):
        """Verify that the video has audio stream"""
        try:
            cmd = [
                self.ffprobe_path, '-v', 'quiet',
                '-select_streams', 'a',
                '-show_entries', 'stream=codec_name,duration',
                '-of', 'csv=p=0',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            
            if result.stdout.strip():
                print(f"{Fore.GREEN}[POSLIPSYNC] ✓ Video has audio: {result.stdout.strip()}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[POSLIPSYNC] ⚠ WARNING: Video has NO AUDIO!{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}[POSLIPSYNC] Could not verify audio: {e}{Style.RESET_ALL}")

    def create_pause_clip(self, output_path: str) -> Optional[str]:
        """Create a pause clip by cutting idle.mp4 to the specified duration"""
        if not self.config['use_sentence_pauses'] or not self.idle_clip_path.exists():
            return None
        
        duration = self.config['sentence_pause_duration']
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', str(self.idle_clip_path),
            '-t', str(duration),
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',
            '-pix_fmt', 'yuv420p',
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
            print(f"{Fore.GREEN}[POSLIPSYNC] Created pause clip: {os.path.basename(output_path)} ({duration}s){Style.RESET_ALL}")
            return output_path
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Failed to create pause clip: {e}{Style.RESET_ALL}")
            return None

    def concatenate_videos(self, video_list: List[str], output_path: str) -> bool:
        """Concatenate multiple videos into final output with audio"""
        if not video_list:
            print(f"{Fore.RED}[POSLIPSYNC] No videos to concatenate{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.CYAN}[POSLIPSYNC] Concatenating {len(video_list)} videos with audio...{Style.RESET_ALL}")
        
        # First verify each video has audio
        for i, video in enumerate(video_list):
            self._verify_video_has_audio(video)
        
        if len(video_list) == 1:
            # Single video, just copy
            try:
                shutil.copy2(video_list[0], output_path)
                print(f"{Fore.GREEN}[POSLIPSYNC] Single video copied with audio{Style.RESET_ALL}")
                return True
            except Exception as e:
                print(f"{Fore.RED}[POSLIPSYNC] Error copying single video: {e}{Style.RESET_ALL}")
                return False
        
        # Create temporary file list for ffmpeg
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                for video in video_list:
                    # Use absolute paths and escape special characters
                    abs_path = os.path.abspath(video).replace('\\', '/')
                    f.write(f"file '{abs_path}'\n")
                concat_file = f.name
            
            # Concatenate using ffmpeg with explicit audio handling
            cmd = [
                self.ffmpeg_path, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-ac', '2',
                '-pix_fmt', 'yuv420p',
                '-avoid_negative_ts', 'make_zero',
                output_path
            ]
            
            print(f"{Fore.CYAN}[POSLIPSYNC] Concatenation command: {' '.join(cmd[:8])}...{Style.RESET_ALL}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            
            # Clean up
            try:
                os.unlink(concat_file)
            except:
                pass
            
            # Verify output has audio
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                self._verify_video_has_audio(output_path)
                print(f"{Fore.GREEN}[POSLIPSYNC] Concatenation completed with audio{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[POSLIPSYNC] Concatenation output file is invalid{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Concatenation error: {e}{Style.RESET_ALL}")
            return False

    def get_unique_output_folder(self, base_output_dir: str = None) -> Path:
        """Create a unique output folder for this run"""
        if base_output_dir is None:
            base_output_dir = LIPSYNC_OUTPUT_DIR
        
        base_path = Path(base_output_dir)
        base_path.mkdir(exist_ok=True)
        
        # Find existing run folders
        existing_runs = []
        for folder in base_path.iterdir():
            if folder.is_dir() and folder.name.startswith("run_"):
                try:
                    run_number = int(folder.name.split("_")[1])
                    existing_runs.append(run_number)
                except (ValueError, IndexError):
                    continue
        
        # Determine next run number
        if existing_runs:
            next_run = max(existing_runs) + 1
        else:
            next_run = 1
        
        # Create unique folder
        unique_folder = base_path / f"run_{next_run:03d}"
        unique_folder.mkdir(exist_ok=True)
        
        print(f"{Fore.GREEN}[POSLIPSYNC] Created output folder: {unique_folder}{Style.RESET_ALL}")
        return unique_folder

    def process_audio_to_lipsync(self, audio_path: str, output_filename: str = None) -> Optional[str]:
        """Main processing function - convert audio to lipsync video"""
        if not os.path.exists(audio_path):
            print(f"{Fore.RED}[POSLIPSYNC] Audio file not found: {audio_path}{Style.RESET_ALL}")
            return None
        
        # Create unique output directory for this run
        if output_filename:
            output_path = Path(LIPSYNC_OUTPUT_DIR) / output_filename
            if not output_path.suffix:
                output_path = output_path.with_suffix('.mp4')
        else:
            timestamp = int(time.time() * 1000)
            output_path = Path(LIPSYNC_OUTPUT_DIR) / f"darwin_lipsync_{timestamp}.mp4"
        
        # Create temp directory for intermediate files
        temp_run_dir = Path(self.temp_dir) / f"run_{int(time.time() * 1000)}"
        temp_run_dir.mkdir(exist_ok=True)
        
        try:
            print(f"{Fore.CYAN}[POSLIPSYNC] Starting lipsync generation...{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[POSLIPSYNC] Audio: {os.path.basename(audio_path)}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[POSLIPSYNC] Output: {output_path.name}{Style.RESET_ALL}")
            
            # Step 1: Transcribe audio
            sentences = self.transcribe_audio(audio_path)
            if not sentences:
                print(f"{Fore.RED}[POSLIPSYNC] Transcription failed{Style.RESET_ALL}")
                return None
            
            # Step 2: Process each sentence
            sentence_videos = []
            
            for i, sentence in enumerate(sentences):
                print(f"\n{Fore.CYAN}[POSLIPSYNC] Processing sentence {i+1}: '{sentence['text'].strip()}'{Style.RESET_ALL}")
                
                # Count syllables
                syllable_count = self.count_syllables_in_sentence(sentence['text'])
                print(f"{Fore.CYAN}[POSLIPSYNC] Syllable count: {syllable_count}{Style.RESET_ALL}")
                
                # Find suitable clip
                selected_clip = self.find_suitable_clip(syllable_count)
                if not selected_clip:
                    print(f"{Fore.RED}[POSLIPSYNC] No suitable clip found for sentence {i+1}{Style.RESET_ALL}")
                    continue
                
                # Extract audio segment
                segment_audio = temp_run_dir / f"sentence_{i+1}_audio.wav"
                if not self.extract_audio_segment(
                    audio_path, 
                    sentence['start_time'], 
                    sentence['end_time'], 
                    str(segment_audio)
                ):
                    print(f"{Fore.RED}[POSLIPSYNC] Failed to extract audio for sentence {i+1}{Style.RESET_ALL}")
                    continue
                
                # Sync audio to video
                sentence_video = temp_run_dir / f"sentence_{i+1}_synced.mp4"
                if self.sync_audio_to_video(
                    str(segment_audio),
                    selected_clip,
                    str(sentence_video)
                ):
                    sentence_videos.append(str(sentence_video))
                    print(f"{Fore.GREEN}[POSLIPSYNC] Created: {sentence_video.name}{Style.RESET_ALL}")
                    
                    # Add pause clip after each sentence (except the last one)
                    if self.config['use_sentence_pauses'] and i < len(sentences) - 1:
                        pause_clip_path = temp_run_dir / f"pause_{i+1}.mp4"
                        pause_clip = self.create_pause_clip(str(pause_clip_path))
                        
                        if pause_clip:
                            sentence_videos.append(pause_clip)
                            print(f"{Fore.GREEN}[POSLIPSYNC] Added pause after sentence {i+1}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[POSLIPSYNC] Failed to sync sentence {i+1}{Style.RESET_ALL}")
                    continue
            
            # Step 3: Concatenate all sentences
            if not sentence_videos:
                print(f"{Fore.RED}[POSLIPSYNC] No videos were successfully created!{Style.RESET_ALL}")
                return None
            
            print(f"\n{Fore.CYAN}[POSLIPSYNC] Concatenating {len(sentence_videos)} videos...{Style.RESET_ALL}")
            if self.concatenate_videos(sentence_videos, str(output_path)):
                # Verify final output
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    final_duration = self.get_video_duration(str(output_path))
                    print(f"\n{Fore.GREEN}[POSLIPSYNC] SUCCESS! Lipsync video created: {output_path.name}{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}[POSLIPSYNC] Final video duration: {final_duration:.2f}s{Style.RESET_ALL}")
                    
                    # Convert to relative path for web serving
                    relative_path = os.path.relpath(output_path, PROJECT_DIR)
                    return relative_path.replace(os.sep, '/')
                else:
                    print(f"{Fore.RED}[POSLIPSYNC] Final output file is invalid{Style.RESET_ALL}")
                    return None
            else:
                print(f"{Fore.RED}[POSLIPSYNC] Concatenation failed{Style.RESET_ALL}")
                return None
                
        except Exception as e:
            print(f"{Fore.RED}[POSLIPSYNC] Processing error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            return None
        
        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(temp_run_dir)
            except:
                pass

# Global instance for reuse
_positional_lipsyncer = None

def get_positional_lipsyncer():
    """Get or create positional lipsyncer instance"""
    global _positional_lipsyncer
    if _positional_lipsyncer is None:
        _positional_lipsyncer = PositionalLipSyncSystem()
    return _positional_lipsyncer

def generate_lipsync_video(text: str, output_filename: str = None, silent_tts: bool = False) -> Optional[str]:
    """
    Main function for generating lipsync videos from text using the proven Sora system.
    
    This function integrates with the existing Darwin avatar system:
    1. Generates TTS audio from text (optionally silent for lipsync-only generation)
    2. Creates syllable-based lipsync video using Sora clips
    3. Returns path to final video file
    
    Args:
        text: Text to convert to lipsync video
        output_filename: Optional output filename
        silent_tts: If True, generates audio file but doesn't play it during generation
    
    Returns:
        str: Path to generated video file, or None if failed
    """
    if not text or not text.strip():
        print(f"{Fore.YELLOW}[POSLIPSYNC] No text provided{Style.RESET_ALL}")
        return None
    
    try:
        print(f"{Fore.CYAN}[POSLIPSYNC] Starting Sora lipsync generation...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[POSLIPSYNC] Text: {text[:100]}{'...' if len(text) > 100 else ''}{Style.RESET_ALL}")
        
        # Step 1: Generate TTS audio (silent mode for lipsync-only)
        print(f"{Fore.CYAN}[POSLIPSYNC] Generating TTS audio {'(silent mode)' if silent_tts else '(with playback)'}...{Style.RESET_ALL}")
        
        if silent_tts:
            # Generate audio file without playing it back
            audio_file = generate_silent_audio_for_lipsync(text, "sora_lipsync_audio")
        else:
            # Normal audio generation with playback
            audio_file = generate_and_stream_audio(text, "sora_lipsync_audio")
        
        if not audio_file or not os.path.exists(audio_file):
            print(f"{Fore.RED}[POSLIPSYNC] TTS audio generation failed{Style.RESET_ALL}")
            return None
        
        print(f"{Fore.GREEN}[POSLIPSYNC] TTS audio ready: {os.path.basename(audio_file)}{Style.RESET_ALL}")
        
        # Step 2: Generate lipsync video using Sora system
        print(f"{Fore.CYAN}[POSLIPSYNC] Creating syllable-based lipsync video...{Style.RESET_ALL}")
        lipsyncer = get_positional_lipsyncer()
        
        if not output_filename:
            timestamp = int(time.time() * 1000)
            output_filename = f"darwin_sora_lipsync_{timestamp}.mp4"
        
        video_path = lipsyncer.process_audio_to_lipsync(audio_file, output_filename)
        
        if video_path:
            print(f"{Fore.GREEN}[POSLIPSYNC] Sora lipsync video generated successfully!{Style.RESET_ALL}")
            print(f"{Fore.GREEN}[POSLIPSYNC] Output: {video_path}{Style.RESET_ALL}")
            return video_path
        else:
            print(f"{Fore.RED}[POSLIPSYNC] Sora lipsync video generation failed{Style.RESET_ALL}")
            return None
            
    except Exception as e:
        print(f"{Fore.RED}[POSLIPSYNC] Error in Sora lipsync generation: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return None

def generate_silent_audio_for_lipsync(text: str, output_filename: str = None) -> Optional[str]:
    """Generate TTS audio without playback for lipsync processing only"""
    if not text or not text.strip():
        return None
    
    # Prepare output file
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    
    if output_filename is None:
        timestamp = int(time.time() * 1000)
        output_filename = f"silent_tts_{timestamp}"
    
    output_path = os.path.join(temp_dir, f"{output_filename}.wav")
    
    try:
        # Import TTS components
        from TTS_Piper import get_voice_instance
        from piper import SynthesisConfig
        import wave
        
        # Get voice instance
        voice = get_voice_instance()
        
        # Configure synthesis
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=1.2,  # Normal speed
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True
        )
        
        print(f"{Fore.BLUE}[POSLIPSYNC] Generating silent TTS audio for lipsync...{Style.RESET_ALL}")
        
        # Generate without playback - collect all chunks first
        audio_chunks = []
        for chunk in voice.synthesize(text, syn_config=syn_config):
            audio_chunks.append(chunk)
        
        # Write complete audio to file
        if audio_chunks:
            print(f"{Fore.CYAN}[POSLIPSYNC] Writing TTS audio to file: {os.path.basename(output_path)}{Style.RESET_ALL}")
            
            with wave.open(output_path, 'wb') as wav_file:
                # Use properties from first chunk
                first_chunk = audio_chunks[0]
                wav_file.setnchannels(first_chunk.sample_channels)
                wav_file.setsampwidth(first_chunk.sample_width)
                wav_file.setframerate(first_chunk.sample_rate)
                
                # Write all chunks
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk.audio_int16_bytes)
            
            print(f"{Fore.GREEN}[POSLIPSYNC] Silent TTS audio generated: {os.path.basename(output_path)}{Style.RESET_ALL}")
            return output_path
        else:
            print(f"{Fore.RED}[POSLIPSYNC] No audio chunks generated{Style.RESET_ALL}")
            return None
            
    except Exception as e:
        print(f"{Fore.RED}[POSLIPSYNC] Error in silent TTS generation: {e}{Style.RESET_ALL}")
        return None

def test_positional_lipsync_system():
    """Test the positional lipsync system"""
    test_text = "Hello there! This is a comprehensive test of the new positional lipsync system. It should create smooth lip synchronization with proper syllable matching."
    
    print(f"{Fore.GREEN}[POSLIPSYNC] Testing positional lipsync system{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[POSLIPSYNC] Test text: {test_text}{Style.RESET_ALL}")
    
    result = generate_lipsync_video(test_text, "test_positional_lipsync.mp4")
    
    if result:
        print(f"{Fore.GREEN}[POSLIPSYNC] Test successful! Output: {result}{Style.RESET_ALL}")
        return True
    else:
        print(f"{Fore.RED}[POSLIPSYNC] Test failed{Style.RESET_ALL}")
        return False

if __name__ == "__main__":
    # Run test when executed directly
    test_positional_lipsync_system()