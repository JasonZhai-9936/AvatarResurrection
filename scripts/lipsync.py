# lipsync.py - Integrated positional lipsync for the Darwin avatar system
"""
This module provides the lipsync functionality for the Darwin avatar system.
It uses the advanced positional lipsync system with word-level timing and head positions.

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
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from colorama import Fore, Style, init
from TTS_Piper import generate_and_stream_audio

# Initialize colorama
init(autoreset=True)

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
AVATAR_DIR = os.path.join(PROJECT_DIR, "avatars", "Darwin")
WORD_CLIPS_DIR = os.path.join(AVATAR_DIR, "movinghead", "word_clips")

# Output directory for lipsync videos
LIPSYNC_OUTPUT_DIR = os.path.join(PROJECT_DIR, "temp_lipsync")

# Ensure output directory exists
os.makedirs(LIPSYNC_OUTPUT_DIR, exist_ok=True)

# CONFIGURATION - Optimized for your Darwin avatar
POSITION_CONFIG = {
    # Available head positions
    "positions": ["main", "focus_in", "slight_tilt"],
    
    # Probability of switching to a new position after N words
    "switch_odds": {
        2: 0.2,   # 20% chance to switch after 2 words (less aggressive)
        3: 0.4,   # 40% chance to switch after 3 words  
        4: 0.7,   # 70% chance to switch after 4 words
        5: 1.0    # Always switch after 5 words
    },
    
    # Position weights - favor main position for smoother experience
    "position_weights": {
        "main": 0.6,        # Main position - most common
        "focus_in": 0.25,   # Close engagement
        "slight_tilt": 0.15 # Subtle head tilt
    },
    
    # Group size limits
    "min_words_per_group": 2,
    "max_words_per_group": 5,
    
    # Transitions
    "use_transitions": True,
    "fallback_position": "main",
    
    # Hub-based transition rules
    "transition_rules": {
        "main": ["focus_in", "slight_tilt"],
        "focus_in": ["main"],
        "slight_tilt": ["main"]
    },
    
    # Available direct transitions
    "available_transitions": {
        ("main", "focus_in"): "main2focus_in.mp4",
        ("focus_in", "main"): "focus_in2main.mp4",
        ("main", "slight_tilt"): "main2slight-tilt.mp4",
        ("slight_tilt", "main"): "slight_tilt2main.mp4",
    },
    
    # Default fallback words
    "default_words": {
        "main": ["the", "and", "a", "to", "of", "in", "is", "it"],
        "focus_in": ["the", "and", "a", "to", "of"],
        "slight_tilt": ["the", "and", "a", "to", "of"]
    },
    
    # Known corrupted clips to avoid
    "corrupted_clips": ["main_water.mp4", "main_paper.mp4"]
}

# Similarity matching configuration
SIMILARITY_CONFIG = {
    "enable_fuzzy_matching": True,
    "similarity_threshold": 0.6,
    "max_length_difference": 3,
    "prefer_shorter_words": True,
}

class IntegratedLipsyncer:
    """Integrated lipsync system for the Darwin avatar"""
    
    def __init__(self, model_size: str = "tiny"):
        self.word_clips_dir = WORD_CLIPS_DIR
        self.temp_dir = os.path.join(PROJECT_DIR, "tempstream", "lipsync_temp")
        
        # Ensure directories exist
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(LIPSYNC_OUTPUT_DIR, exist_ok=True)
        
        # Initialize Whisper
        try:
            self.model = whisper.load_model(model_size, device="cpu")
            print(f"{Fore.GREEN}[LIPSYNC] Whisper model loaded: {model_size}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Error loading Whisper: {e}{Style.RESET_ALL}")
            self.model = None
        
        # Check FFmpeg
        self.ffmpeg_available = self._check_ffmpeg()
        
        # Load word clips
        self.position_clips = self._load_position_clips()
        
        # Current position tracking
        self.current_position = "main"
        
        print(f"{Fore.GREEN}[LIPSYNC] Integrated lipsyncer initialized{Style.RESET_ALL}")
        self._print_status()

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
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
                    return True
            except:
                continue
        
        print(f"{Fore.RED}[LIPSYNC] FFmpeg not found{Style.RESET_ALL}")
        return False

    def _extract_word_from_filename(self, filename: str) -> Optional[str]:
        """Extract word from clip filename"""
        name = os.path.splitext(filename)[0]
        
        if name.startswith('main_'):
            return name[5:]
        elif name.startswith('focus_in_body_'):
            parts = name.split('_')
            if len(parts) >= 4:
                word_part = '_'.join(parts[3:])
                word_part = re.sub(r'_\d+$', '', word_part)
                return word_part
        elif name.startswith('slight_tilt_body_'):
            parts = name.split('_')
            if len(parts) >= 4:
                word_part = '_'.join(parts[3:])
                word_part = re.sub(r'_\d+$', '', word_part)
                return word_part
        elif name.startswith('l1_'):
            return name[3:]
        elif '_' in name:
            parts = name.split('_')
            if len(parts) >= 2:
                word_part = parts[-1]
                word_part = re.sub(r'\d+$', '', word_part)
                return word_part if word_part else parts[-1]
        
        clean_name = re.sub(r'_\d+$', '', name.lower())
        return clean_name if clean_name else name.lower()

    def _load_position_clips(self) -> Dict[str, Dict[str, str]]:
        """Load all available word clips organized by position"""
        position_clips = {}
        
        for position in POSITION_CONFIG["positions"]:
            position_dir = os.path.join(self.word_clips_dir, position)
            position_clips[position] = {}
            
            if os.path.exists(position_dir):
                clip_files = [f for f in os.listdir(position_dir) if f.endswith('.mp4')]
                
                for file in clip_files:
                    word = self._extract_word_from_filename(file)
                    if word and word.strip():
                        position_clips[position][word.lower()] = os.path.join(position_dir, file)
        
        return position_clips

    def _print_status(self):
        """Print system status"""
        total_clips = sum(len(clips) for clips in self.position_clips.values())
        print(f"{Fore.CYAN}[LIPSYNC] Loaded {total_clips} clips across {len(self.position_clips)} positions{Style.RESET_ALL}")
        
        for position, clips in self.position_clips.items():
            print(f"{Fore.CYAN}[LIPSYNC] {position}: {len(clips)} words{Style.RESET_ALL}")

    def transcribe_audio(self, audio_file: str) -> List[Dict]:
        """Transcribe audio using Whisper"""
        if not self.model:
            print(f"{Fore.RED}[LIPSYNC] Whisper model not available{Style.RESET_ALL}")
            return []
        
        try:
            result = self.model.transcribe(audio_file, word_timestamps=True)
            
            word_data = []
            if 'segments' in result:
                for segment in result['segments']:
                    if 'words' in segment:
                        for word_info in segment['words']:
                            word_data.append({
                                'word': word_info['word'].strip().lower(),
                                'start': word_info['start'],
                                'end': word_info['end'],
                                'duration': word_info['end'] - word_info['start']
                            })
            
            print(f"{Fore.GREEN}[LIPSYNC] Transcribed {len(word_data)} words{Style.RESET_ALL}")
            return word_data
            
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Transcription error: {e}{Style.RESET_ALL}")
            return []

    def clean_word_data(self, word_data: List[Dict]) -> List[Dict]:
        """Clean transcribed word data"""
        cleaned_words = []
        for word_info in word_data:
            word = word_info['word']
            clean_word = re.sub(r'[^\w]', '', word.lower())
            
            if len(clean_word) > 0:
                cleaned_words.append({
                    'word': clean_word,
                    'start': word_info['start'],
                    'end': word_info['end'],
                    'duration': word_info['duration']
                })
        
        return cleaned_words

    def create_word_groups(self, word_data: List[Dict]) -> List[Tuple[str, List[Dict]]]:
        """Group words by position"""
        if not word_data:
            return []
        
        groups = []
        current_group = []
        current_position = self.current_position
        
        for i, word_info in enumerate(word_data):
            current_group.append(word_info)
            group_size = len(current_group)
            
            should_switch = False
            
            if group_size >= POSITION_CONFIG["max_words_per_group"]:
                should_switch = True
            elif group_size >= POSITION_CONFIG["min_words_per_group"]:
                switch_probability = POSITION_CONFIG["switch_odds"].get(group_size, 0.5)
                should_switch = random.random() < switch_probability
            
            if should_switch or i == len(word_data) - 1:
                groups.append((current_position, current_group.copy()))
                
                if should_switch and i < len(word_data) - 1:
                    available_positions = POSITION_CONFIG["transition_rules"].get(current_position, ["main"])
                    
                    if available_positions == ["main"]:
                        current_position = "main"
                    else:
                        weights = [POSITION_CONFIG["position_weights"].get(p, 0.1) for p in available_positions]
                        current_position = random.choices(available_positions, weights=weights)[0]
                
                current_group = []
        
        return groups

    def _find_working_clip(self, word: str, position: str, max_attempts: int = 5) -> Optional[str]:
        """Find a working clip with multiple fallback strategies"""
        attempts = []
        
        # Attempt 1: Exact match in preferred position
        clip_path = self._try_exact_match(word, position)
        if clip_path:
            attempts.append(("exact_match", clip_path))
        
        # Attempt 2: Fuzzy match in same position
        if SIMILARITY_CONFIG["enable_fuzzy_matching"]:
            clip_path = self._try_fuzzy_match_in_position(word, position)
            if clip_path:
                attempts.append(("fuzzy_same_pos", clip_path))
        
        # Attempt 3: Exact match in main position
        if position != "main":
            clip_path = self._try_exact_match(word, "main")
            if clip_path:
                attempts.append(("exact_main", clip_path))
        
        # Attempt 4: Fuzzy match across all positions
        clip_path = self._try_fuzzy_match_any_position(word)
        if clip_path:
            attempts.append(("fuzzy_any", clip_path))
        
        # Attempt 5: Default word in position
        clip_path = self._try_default_word(position)
        if clip_path:
            attempts.append(("default_pos", clip_path))
        
        # Attempt 6: Default word in main
        if position != "main":
            clip_path = self._try_default_word("main")
            if clip_path:
                attempts.append(("default_main", clip_path))
        
        # Test each attempt to find one that works
        for attempt_name, clip_path in attempts[:max_attempts]:
            if self._test_clip_quickly(clip_path):
                if attempt_name != "exact_match":
                    actual_word = self._get_word_from_path(clip_path)
                    print(f"{Fore.CYAN}[LIPSYNC] Using {attempt_name}: '{word}' -> '{actual_word}'{Style.RESET_ALL}")
                return clip_path
            else:
                print(f"{Fore.YELLOW}[LIPSYNC] {attempt_name} clip failed test: {os.path.basename(clip_path)}{Style.RESET_ALL}")
        
        return None
    
    def _try_exact_match(self, word: str, position: str) -> Optional[str]:
        """Try exact word match in position"""
        clean_word = word.lower().strip()
        if position in self.position_clips and clean_word in self.position_clips[position]:
            clip_path = self.position_clips[position][clean_word]
            if not self._is_clip_corrupted(clip_path):
                return clip_path
        return None
    
    def _try_fuzzy_match_in_position(self, word: str, position: str) -> Optional[str]:
        """Try fuzzy matching within same position"""
        if position not in self.position_clips:
            return None
        
        clean_word = word.lower().strip()
        best_match, best_score = None, 0.0
        
        for available_word in self.position_clips[position].keys():
            clip_path = self.position_clips[position][available_word]
            if self._is_clip_corrupted(clip_path):
                continue
                
            if abs(len(clean_word) - len(available_word)) > SIMILARITY_CONFIG["max_length_difference"]:
                continue
            
            similarity = difflib.SequenceMatcher(None, clean_word, available_word).ratio()
            
            if similarity > best_score and similarity >= SIMILARITY_CONFIG["similarity_threshold"]:
                best_match = available_word
                best_score = similarity
        
        if best_match:
            return self.position_clips[position][best_match]
        return None
    
    def _try_fuzzy_match_any_position(self, word: str) -> Optional[str]:
        """Try fuzzy matching across all positions"""
        clean_word = word.lower().strip()
        best_match, best_score, best_position = None, 0.0, None
        
        for position, clips in self.position_clips.items():
            for available_word in clips.keys():
                clip_path = clips[available_word]
                if self._is_clip_corrupted(clip_path):
                    continue
                    
                if abs(len(clean_word) - len(available_word)) > SIMILARITY_CONFIG["max_length_difference"]:
                    continue
                
                similarity = difflib.SequenceMatcher(None, clean_word, available_word).ratio()
                
                if similarity > best_score and similarity >= SIMILARITY_CONFIG["similarity_threshold"]:
                    best_match = available_word
                    best_score = similarity
                    best_position = position
        
        if best_match and best_position:
            return self.position_clips[best_position][best_match]
        return None
    
    def _try_default_word(self, position: str) -> Optional[str]:
        """Try default word in position"""
        default_words = POSITION_CONFIG["default_words"].get(position, ["the", "and", "a"])
        
        if position in self.position_clips:
            for word in default_words:
                if word in self.position_clips[position]:
                    clip_path = self.position_clips[position][word]
                    if not self._is_clip_corrupted(clip_path):
                        return clip_path
        return None
    
    def _test_clip_quickly(self, clip_path: str) -> bool:
        """Quickly test if a clip is usable"""
        try:
            if not os.path.exists(clip_path):
                return False
            
            # Check file size
            if os.path.getsize(clip_path) < 1000:
                return False
            
            # Quick ffprobe test (with shorter timeout)
            cmd = [self.ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', clip_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            
            if result.returncode == 0:
                info = json.loads(result.stdout)
                video_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
                return len(video_streams) > 0
            
            return False
            
        except Exception:
            return False
    
    def _get_word_from_path(self, clip_path: str) -> str:
        """Extract word from clip path for logging"""
        filename = os.path.basename(clip_path)
        word = self._extract_word_from_filename(filename)
        return word if word else filename
    
    def _get_emergency_fallback_clip(self, position: str) -> Optional[str]:
        """Get an emergency fallback clip that's guaranteed to work"""
        # Try the most common words first
        emergency_words = ["the", "a", "and", "to", "of", "in"]
        
        for word in emergency_words:
            for pos in [position, "main"]:  # Try current position first, then main
                if pos in self.position_clips and word in self.position_clips[pos]:
                    clip_path = self.position_clips[pos][word]
                    if self._test_clip_quickly(clip_path):
                        print(f"{Fore.MAGENTA}[LIPSYNC] Emergency fallback: using '{word}' from {pos}{Style.RESET_ALL}")
                        return clip_path
        
        # Last resort: find ANY working clip in the position
        if position in self.position_clips:
            for word, clip_path in list(self.position_clips[position].items())[:10]:  # Test first 10
                if self._test_clip_quickly(clip_path):
                    print(f"{Fore.MAGENTA}[LIPSYNC] Last resort fallback: using '{word}' from {position}{Style.RESET_ALL}")
                    return clip_path
        
        return None

    def _is_clip_corrupted(self, clip_path: str) -> bool:
        """Check if clip is corrupted"""
        filename = os.path.basename(clip_path)
        return filename in POSITION_CONFIG["corrupted_clips"]

    def _find_default_word_in_position(self, position: str) -> Optional[str]:
        """Find first available default word in position"""
        default_words = POSITION_CONFIG["default_words"].get(position, ["the", "and", "a"])
        
        if position in self.position_clips:
            for word in default_words:
                if word in self.position_clips[position]:
                    clip_path = self.position_clips[position][word]
                    if not self._is_clip_corrupted(clip_path):
                        return word
        
        return None

    def get_video_info(self, video_path: str) -> Dict:
        """Get video information"""
        try:
            cmd = [
                self.ffprobe_path, '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            if video_stream:
                fps = eval(video_stream.get('r_frame_rate', '25/1'))
                duration = float(video_stream.get('duration', 1.0))
                return {'fps': fps, 'duration': duration}
        except:
            pass
        
        return {'fps': 25, 'duration': 1.0}

    def process_word_clip(self, word_info: Dict, position: str, clip_index: int) -> Optional[str]:
        """Process a single word clip with timing adjustment and robust fallback"""
        word = word_info['word']
        target_duration = word_info['duration']
        
        # Try to find a working clip with multiple fallback attempts
        clip_path = self._find_working_clip(word, position)
        if not clip_path:
            print(f"{Fore.YELLOW}[LIPSYNC] No working clip found for '{word}', skipping{Style.RESET_ALL}")
            return None
        
        # Validate the clip before processing
        if not self._validate_video_clip_quick(clip_path):
            print(f"{Fore.YELLOW}[LIPSYNC] Clip validation failed for '{word}', trying fallback{Style.RESET_ALL}")
            clip_path = self._get_emergency_fallback_clip(position)
            if not clip_path:
                return None
        
        video_info = self.get_video_info(clip_path)
        original_duration = video_info.get('duration', 1.0)
        
        if original_duration == 0:
            original_duration = 1.0
        
        speed_factor = max(0.5, min(2.0, original_duration / target_duration))
        
        output_path = os.path.join(self.temp_dir, f"word_{clip_index:04d}_{word}.mp4")
        
        # Try multiple FFmpeg approaches
        success = False
        
        # Approach 1: Standard processing
        cmd = [
            self.ffmpeg_path, '-y', '-i', clip_path,
            '-an',
            '-vf', f'setpts={1/speed_factor}*PTS',
            '-t', str(target_duration),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-avoid_negative_ts', 'make_zero',
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                success = True
        except Exception as e:
            print(f"{Fore.YELLOW}[LIPSYNC] Standard processing failed for '{word}': {str(e)[:100]}{Style.RESET_ALL}")
        
        # Approach 2: Simple copy with duration trim (no speed adjustment)
        if not success:
            try:
                os.remove(output_path) if os.path.exists(output_path) else None
                cmd = [
                    self.ffmpeg_path, '-y', '-i', clip_path,
                    '-an', '-t', str(target_duration),
                    '-c:v', 'libx264', '-preset', 'ultrafast',
                    output_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    success = True
                    print(f"{Fore.CYAN}[LIPSYNC] Used simple copy for '{word}'{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}[LIPSYNC] Simple copy failed for '{word}': {str(e)[:100]}{Style.RESET_ALL}")
        
        # Approach 3: Direct copy (no processing)
        if not success:
            try:
                os.remove(output_path) if os.path.exists(output_path) else None
                shutil.copy2(clip_path, output_path)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    success = True
                    print(f"{Fore.CYAN}[LIPSYNC] Used direct copy for '{word}'{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}[LIPSYNC] Direct copy failed for '{word}': {e}{Style.RESET_ALL}")
        
        if success:
            return output_path
        else:
            print(f"{Fore.RED}[LIPSYNC] All processing approaches failed for '{word}'{Style.RESET_ALL}")
            return None

    def create_position_group_video(self, position: str, word_group: List[Dict], group_index: int) -> Optional[str]:
        """Create video for a group of words in same position with robust error handling"""
        if not word_group:
            return None
        
        video_clips = []
        failed_words = []
        
        for i, word_info in enumerate(word_group):
            word_clip = self.process_word_clip(word_info, position, i)
            if word_clip:
                video_clips.append(word_clip)
            else:
                failed_words.append(word_info['word'])
        
        # If we have some clips, continue. If we have none, try emergency fallback
        if not video_clips:
            print(f"{Fore.RED}[LIPSYNC] No clips generated for group {group_index}, trying emergency word{Style.RESET_ALL}")
            
            # Create emergency clip using a guaranteed working word
            emergency_clip = self._create_emergency_clip(position, word_group[0]['duration'])
            if emergency_clip:
                video_clips.append(emergency_clip)
            else:
                print(f"{Fore.RED}[LIPSYNC] Emergency clip creation failed for group {group_index}{Style.RESET_ALL}")
                return None
        
        if failed_words:
            print(f"{Fore.YELLOW}[LIPSYNC] Group {group_index}: {len(video_clips)} clips created, {len(failed_words)} failed: {failed_words}{Style.RESET_ALL}")
        
        # Concatenate clips for this group
        output_path = os.path.join(self.temp_dir, f"group_{group_index:03d}_{position}.mp4")
        
        if self._concatenate_clips(video_clips, output_path):
            return output_path
        
        return None
    
    def _create_emergency_clip(self, position: str, duration: float) -> Optional[str]:
        """Create an emergency clip using the most reliable word"""
        emergency_clip = self._get_emergency_fallback_clip(position)
        if not emergency_clip:
            return None
        
        output_path = os.path.join(self.temp_dir, f"emergency_{int(time.time()*1000)}.mp4")
        
        # Simple copy with duration limit
        try:
            cmd = [
                self.ffmpeg_path, '-y', '-i', emergency_clip,
                '-an', '-t', str(duration),
                '-c:v', 'libx264', '-preset', 'ultrafast',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and os.path.exists(output_path):
                return output_path
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Emergency clip creation failed: {e}{Style.RESET_ALL}")
        
        return None

    def _concatenate_clips(self, clip_paths: List[str], output_path: str) -> bool:
        """Concatenate video clips"""
        if not self.ffmpeg_available or not clip_paths:
            return False
        
        if len(clip_paths) == 1:
            try:
                shutil.copy2(clip_paths[0], output_path)
                return True
            except:
                return False
        
        try:
            concat_file = os.path.join(self.temp_dir, f"concat_{int(time.time()*1000)}.txt")
            
            with open(concat_file, 'w') as f:
                for clip_path in clip_paths:
                    clip_path_fixed = clip_path.replace('\\', '/')
                    f.write(f"file '{clip_path_fixed}'\n")
            
            cmd = [
                self.ffmpeg_path, '-f', 'concat', '-safe', '0', '-i', concat_file,
                '-c', 'copy', '-y', output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            try:
                os.remove(concat_file)
            except:
                pass
            
            return result.returncode == 0 and os.path.exists(output_path)
            
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Concatenation error: {e}{Style.RESET_ALL}")
            return False

    def get_transition_clip(self, from_position: str, to_position: str) -> Optional[str]:
        """Get transition clip between positions"""
        if not POSITION_CONFIG["use_transitions"]:
            return None
        
        transitions_dir = os.path.join(self.word_clips_dir, "transitions")
        if not os.path.exists(transitions_dir):
            return None
        
        transition_key = (from_position, to_position)
        if transition_key in POSITION_CONFIG["available_transitions"]:
            transition_filename = POSITION_CONFIG["available_transitions"][transition_key]
            transition_path = os.path.join(transitions_dir, transition_filename)
            
            if os.path.exists(transition_path) and self._validate_video_clip_quick(transition_path):
                return transition_path
        
        return None

    def add_audio_to_video(self, video_path: str, audio_path: str, final_output_path: str) -> bool:
        """Add audio to video"""
        cmd = [
            self.ffmpeg_path, '-y', '-i', video_path, '-i', audio_path,
            '-c:v', 'copy', '-c:a', 'aac', '-strict', 'experimental',
            '-shortest',
            final_output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except:
            return False

    def generate_from_audio(self, audio_file: str, output_filename: str = None) -> Optional[str]:
        """Generate lipsync video from audio file"""
        if not os.path.exists(audio_file):
            return None
        
        if not output_filename:
            timestamp = int(time.time() * 1000)
            output_filename = f"lipsync_{timestamp}.mp4"
        
        final_output_path = os.path.join(LIPSYNC_OUTPUT_DIR, output_filename)
        
        try:
            # Transcribe audio
            word_data = self.transcribe_audio(audio_file)
            if not word_data:
                return None
            
            # Clean and group words
            cleaned_words = self.clean_word_data(word_data)
            if not cleaned_words:
                return None
            
            word_groups = self.create_word_groups(cleaned_words)
            if not word_groups:
                return None
            
            # Generate group videos
            group_videos = []
            prev_position = None
            
            for i, (position, group_words) in enumerate(word_groups):
                # Add transition if needed
                if prev_position and prev_position != position:
                    transition_clip = self.get_transition_clip(prev_position, position)
                    if transition_clip:
                        group_videos.append(transition_clip)
                
                # Create group video
                group_video = self.create_position_group_video(position, group_words, i)
                if group_video:
                    group_videos.append(group_video)
                
                prev_position = position
            
            if not group_videos:
                return None
            
            # Concatenate all videos
            temp_video_path = os.path.join(self.temp_dir, "concatenated_video.mp4")
            if not self._concatenate_clips(group_videos, temp_video_path):
                return None
            
            # Add audio back
            if self.add_audio_to_video(temp_video_path, audio_file, final_output_path):
                print(f"{Fore.GREEN}[LIPSYNC] Generated: {final_output_path}{Style.RESET_ALL}")
                return final_output_path
            
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Generation error: {e}{Style.RESET_ALL}")
        
        return None

# Global instance for reuse
_lipsyncer = None

def get_lipsyncer():
    """Get or create lipsyncer instance"""
    global _lipsyncer
    if _lipsyncer is None:
        _lipsyncer = IntegratedLipsyncer()
    return _lipsyncer

def generate_lipsync_video(text: str, output_filename: str = None) -> Optional[str]:
    """
    Main function for generating lipsync videos from text.
    
    This function integrates with the existing Darwin avatar system:
    1. Generates TTS audio from text
    2. Creates positional lipsync video with head movements
    3. Returns path to final video file
    
    Args:
        text: Text to convert to lipsync video
        output_filename: Optional output filename
    
    Returns:
        str: Path to generated video file, or None if failed
    """
    if not text or not text.strip():
        print(f"{Fore.YELLOW}[LIPSYNC] No text provided{Style.RESET_ALL}")
        return None
    
    try:
        print(f"{Fore.CYAN}[LIPSYNC] Starting lipsync generation for: {text[:50]}...{Style.RESET_ALL}")
        
        # Step 1: Generate TTS audio
        print(f"{Fore.CYAN}[LIPSYNC] Generating TTS audio...{Style.RESET_ALL}")
        audio_file = generate_and_stream_audio(text, "lipsync_audio")
        
        if not audio_file or not os.path.exists(audio_file):
            print(f"{Fore.RED}[LIPSYNC] TTS audio generation failed{Style.RESET_ALL}")
            return None
        
        print(f"{Fore.GREEN}[LIPSYNC] TTS audio ready: {audio_file}{Style.RESET_ALL}")
        
        # Step 2: Generate lipsync video
        print(f"{Fore.CYAN}[LIPSYNC] Creating positional lipsync video...{Style.RESET_ALL}")
        lipsyncer = get_lipsyncer()
        
        if not output_filename:
            timestamp = int(time.time() * 1000)
            output_filename = f"darwin_lipsync_{timestamp}.mp4"
        
        video_path = lipsyncer.generate_from_audio(audio_file, output_filename)
        
        if video_path and os.path.exists(video_path):
            print(f"{Fore.GREEN}[LIPSYNC] Lipsync video generated successfully: {video_path}{Style.RESET_ALL}")
            
            # Convert to relative path for web serving
            relative_path = os.path.relpath(video_path, PROJECT_DIR)
            return relative_path
        else:
            print(f"{Fore.RED}[LIPSYNC] Lipsync video generation failed{Style.RESET_ALL}")
            return None
            
    except Exception as e:
        print(f"{Fore.RED}[LIPSYNC] Error in lipsync generation: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return None

def test_lipsync_system():
    """Test the integrated lipsync system"""
    test_text = "Hello, this is a test of the advanced lipsync system with positional head movements."
    
    print(f"{Fore.GREEN}[LIPSYNC] Testing integrated lipsync system{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[LIPSYNC] Test text: {test_text}{Style.RESET_ALL}")
    
    result = generate_lipsync_video(test_text, "test_lipsync_output.mp4")
    
    if result:
        print(f"{Fore.GREEN}[LIPSYNC] Test successful! Output: {result}{Style.RESET_ALL}")
        return True
    else:
        print(f"{Fore.RED}[LIPSYNC] Test failed{Style.RESET_ALL}")
        return False

if __name__ == "__main__":
    # Run test when executed directly
    test_lipsync_system()