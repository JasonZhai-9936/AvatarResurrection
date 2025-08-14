# positional_lipsyncer.py - Advanced word-level lipsync with head position variation and Whisper transcription

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

# Initialize colorama
init(autoreset=True)

# Set project directory - CORRECTED PATH
# From: AvatarResurrection/scripts/positional_lipsyncer.py
# To: AvatarResurrection/avatars/Darwin/movinghead/word_clips
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))  # AvatarResurrection
AVATAR_DIR = os.path.join(PROJECT_DIR, "avatars", "Darwin")
WORD_CLIPS_DIR = os.path.join(AVATAR_DIR, "movinghead", "word_clips")

# CONFIGURATION - Updated to match your actual file structure
POSITION_CONFIG = {
    # Available head positions (ONLY the ones that actually exist)
    "positions": ["main", "focus_in", "slight_tilt"],  # Removed lean_in since it's incomplete
    
    # Probability of switching to a new position after N words
    "switch_odds": {
        2: 0.3,   # 30% chance to switch after 2 words
        3: 0.6,   # 60% chance to switch after 3 words  
        4: 0.9,   # 90% chance to switch after 4 words
        5: 1.0    # Always switch after 5 words (max group size)
    },
    
    # Position transition preferences (higher = more likely)
    "position_weights": {
        "main": 0.5,        # Neutral position - most common
        "focus_in": 0.3,    # Close engagement
        "slight_tilt": 0.2  # Subtle head tilt
    },
    
    # Minimum and maximum words per position group
    "min_words_per_group": 2,
    "max_words_per_group": 5,
    
    # Whether to use transitions between positions
    "use_transitions": True,
    
    # Fallback position if word not found in chosen position
    "fallback_position": "main",
    
    # Hub-based transition rules - all transitions must go through main
    "transition_rules": {
        "main": ["focus_in", "slight_tilt"],           # Main can go to any position
        "focus_in": ["main"],                          # Focus_in can only go to main
        "slight_tilt": ["main"]                        # Slight_tilt can only go to main
    },
    
    # Direct transition mappings available in your transitions folder
    "available_transitions": {
        ("main", "focus_in"): "main2focus_in.mp4",
        ("focus_in", "main"): "focus_in2main.mp4",
        ("main", "slight_tilt"): "main2slight-tilt.mp4",
        ("slight_tilt", "main"): "slight_tilt2main.mp4",
        # Note: lean_in transitions exist but lean_in position is disabled
    },
    
    # Default fallback words for each position (multiple options in order of preference)
    "default_words": {
        "main": ["the", "and", "a", "to", "of", "in", "is", "it"],
        "focus_in": ["the", "and", "a", "to", "of"],
        "slight_tilt": ["the", "and", "a", "to", "of"]
    },
    
    # Corrupted clips to avoid (add problematic filenames here)
    "corrupted_clips": ["main_water.mp4", "main_paper.mp4"]
}

# SIMILARITY MATCHING CONFIGURATION
SIMILARITY_CONFIG = {
    "enable_fuzzy_matching": True,
    "similarity_threshold": 0.6,  # 60% similarity required
    "max_length_difference": 3,   # Don't match words that differ by more than 3 characters
    "prefer_shorter_words": True, # Prefer shorter similar words over longer ones
}

class PositionalLipsyncer:
    def __init__(self, avatar_name: str = "Darwin", model_size: str = "tiny"):
        self.avatar_name = avatar_name
        self.avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        self.word_clips_dir = WORD_CLIPS_DIR  # Fixed path
        self.temp_dir = os.path.join(PROJECT_DIR, "tempstream", "positional_lipsync")
        
        # Ensure directories exist
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Initialize Whisper for transcription
        self.model = whisper.load_model(model_size, device="cpu")
        
        # Check for FFmpeg
        self.ffmpeg_available = self._check_ffmpeg()
        
        # Load available word clips by position
        self.position_clips = self._load_position_clips()
        
        # Current position tracking
        self.current_position = "main"
        
        print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Initialized for avatar: {avatar_name}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Word clips directory: {self.word_clips_dir}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Whisper model loaded: {model_size}{Style.RESET_ALL}")
        self._print_system_status()

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
        
        print(f"{Fore.RED}[POSITIONAL_LIPSYNC] FFmpeg not found{Style.RESET_ALL}")
        return False

    def transcribe_audio(self, audio_file: str) -> List[Dict]:
        """Transcribe audio using Whisper and return word-level timestamps"""
        print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Transcribing audio: {os.path.basename(audio_file)}{Style.RESET_ALL}")
        
        try:
            # Use Whisper to transcribe with word-level timestamps
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
            
            print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Transcribed {len(word_data)} words from audio{Style.RESET_ALL}")
            return word_data
            
        except Exception as e:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Transcription error: {e}{Style.RESET_ALL}")
            return []

    def get_audio_duration(self, audio_file: str) -> float:
        """Get total duration of audio file"""
        try:
            cmd = [self.ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_format', audio_file]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            audio_info = json.loads(result.stdout)
            return float(audio_info['format']['duration'])
        except Exception as e:
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Could not get audio duration: {e}{Style.RESET_ALL}")
            return 10.0  # Default fallback

    def _extract_word_from_filename(self, filename: str) -> Optional[str]:
        """Extract word from clip filename - handles multiple naming patterns"""
        # Remove extension
        name = os.path.splitext(filename)[0]
        
        # Handle different naming patterns based on your actual structure:
        # main_word.mp4 -> word
        # focus_in_body_word_001.mp4 -> word  
        # slight_tilt_body_word_001.mp4 -> word
        # l1_word.mp4 -> word (for lean_in)
        
        if name.startswith('main_'):
            # main_word.mp4 pattern
            return name[5:]  # Remove "main_" prefix
        elif name.startswith('focus_in_body_'):
            # focus_in_body_word_001.mp4 pattern
            parts = name.split('_')
            if len(parts) >= 4:
                # Remove focus_in_body prefix and _001 suffix if present
                word_part = '_'.join(parts[3:])
                # Remove numeric suffix like _001, _002 etc
                word_part = re.sub(r'_\d+$', '', word_part)
                return word_part
        elif name.startswith('slight_tilt_body_'):
            # slight_tilt_body_word_001.mp4 pattern  
            parts = name.split('_')
            if len(parts) >= 4:
                # Remove slight_tilt_body prefix and _001 suffix if present
                word_part = '_'.join(parts[3:])
                # Remove numeric suffix like _001, _002 etc
                word_part = re.sub(r'_\d+$', '', word_part)
                return word_part
        elif name.startswith('l1_'):
            # l1_word.mp4 pattern (for lean_in if you add it later)
            return name[3:]  # Remove "l1_" prefix
        elif '_' in name:
            # Generic pattern: prefix_word.mp4
            parts = name.split('_')
            if len(parts) >= 2:
                # Take the last part and remove any numeric suffix
                word_part = parts[-1]
                word_part = re.sub(r'\d+$', '', word_part)
                return word_part if word_part else parts[-1]
        
        # Fallback: use the whole filename (clean any numbers)
        clean_name = re.sub(r'_\d+$', '', name.lower())
        return clean_name if clean_name else name.lower()

    def _load_position_clips(self) -> Dict[str, Dict[str, str]]:
        """Load all available word clips organized by position"""
        position_clips = {}
        
        print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Loading clips from: {self.word_clips_dir}{Style.RESET_ALL}")
        
        for position in POSITION_CONFIG["positions"]:
            position_dir = os.path.join(self.word_clips_dir, position)
            position_clips[position] = {}
            
            if os.path.exists(position_dir):
                clip_files = [f for f in os.listdir(position_dir) if f.endswith('.mp4')]
                print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Found {len(clip_files)} clips in {position}{Style.RESET_ALL}")
                
                for file in clip_files:
                    # Extract word from filename
                    word = self._extract_word_from_filename(file)
                    if word and word.strip():
                        position_clips[position][word.lower()] = os.path.join(position_dir, file)
                        if len(position_clips[position]) <= 5:  # Show first 5 for debugging
                            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] {position}: '{file}' -> '{word}'{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Position directory not found: {position_dir}{Style.RESET_ALL}")
        
        return position_clips

    def _print_system_status(self):
        """Print system status and available clips"""
        total_clips = 0
        for position, clips in self.position_clips.items():
            clip_count = len(clips)
            total_clips += clip_count
            print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] {position}: {clip_count} words{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Total clips: {total_clips} across {len(self.position_clips)} positions{Style.RESET_ALL}")
        
        if total_clips == 0:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] WARNING: No clips found! Check directory structure{Style.RESET_ALL}")
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Expected structure: {self.word_clips_dir}/<position>/<clips>{Style.RESET_ALL}")

    def clean_and_split_text(self, word_data: List[Dict]) -> List[Dict]:
        """Clean transcribed word data for processing"""
        if not word_data:
            return []
        
        cleaned_words = []
        for word_info in word_data:
            word = word_info['word']
            # Clean word - remove punctuation but keep timing
            clean_word = re.sub(r'[^\w]', '', word.lower())
            
            if len(clean_word) > 0:  # Keep all words that have letters
                cleaned_words.append({
                    'word': clean_word,
                    'start': word_info['start'],
                    'end': word_info['end'],
                    'duration': word_info['duration']
                })
        
        print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Cleaned to {len(cleaned_words)} timed words{Style.RESET_ALL}")
        return cleaned_words

    def create_word_groups(self, word_data: List[Dict]) -> List[Tuple[str, List[Dict]]]:
        """Group timed words by position, respecting hub-based transition rules"""
        if not word_data:
            return []
        
        groups = []
        current_group = []
        current_position = self.current_position
        
        for i, word_info in enumerate(word_data):
            current_group.append(word_info)
            group_size = len(current_group)
            
            # Determine if we should switch positions
            should_switch = False
            
            # Check if we've hit max group size
            if group_size >= POSITION_CONFIG["max_words_per_group"]:
                should_switch = True
            # Check probabilistic switching
            elif group_size >= POSITION_CONFIG["min_words_per_group"]:
                switch_probability = POSITION_CONFIG["switch_odds"].get(group_size, 0.5)
                should_switch = random.random() < switch_probability
            
            # Switch position or end of words
            if should_switch or i == len(word_data) - 1:
                word_list = [w['word'] for w in current_group]
                groups.append((current_position, current_group.copy()))
                print(f"{Fore.MAGENTA}[POSITIONAL_LIPSYNC] Group: {current_position} -> {word_list}{Style.RESET_ALL}")
                
                # Choose next position respecting transition rules
                if should_switch and i < len(word_data) - 1:
                    available_positions = POSITION_CONFIG["transition_rules"].get(current_position, ["main"])
                    
                    # If we can only go to main, go to main
                    if available_positions == ["main"]:
                        current_position = "main"
                        print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Hub transition: {current_position} -> main{Style.RESET_ALL}")
                    else:
                        # Choose from available positions using weights
                        weights = [POSITION_CONFIG["position_weights"].get(p, 0.1) for p in available_positions]
                        current_position = random.choices(available_positions, weights=weights)[0]
                        print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Direct transition to: {current_position}{Style.RESET_ALL}")
                
                current_group = []
        
        self.current_position = current_position
        return groups

    def _find_similar_word(self, target_word: str, threshold: float = None) -> Tuple[Optional[str], float, Optional[str]]:
        """Find the most similar word across all positions using fuzzy matching"""
        if threshold is None:
            threshold = SIMILARITY_CONFIG["similarity_threshold"]
        
        best_match = None
        best_score = 0.0
        best_position = None
        
        # Check all available words across all positions
        for position, clips in self.position_clips.items():
            for available_word in clips.keys():
                # Skip words that are too different in length
                if abs(len(target_word) - len(available_word)) > SIMILARITY_CONFIG["max_length_difference"]:
                    continue
                
                # Calculate similarity using difflib
                similarity = difflib.SequenceMatcher(None, target_word, available_word).ratio()
                
                # Apply preference for shorter words if enabled
                if SIMILARITY_CONFIG["prefer_shorter_words"] and len(available_word) < len(target_word):
                    similarity += 0.1  # Small bonus for shorter words
                
                if similarity > best_score and similarity >= threshold:
                    best_match = available_word
                    best_score = similarity
                    best_position = position
        
        return best_match, best_score, best_position

    def _is_clip_corrupted(self, clip_path: str) -> bool:
        """Check if a clip is known to be corrupted"""
        filename = os.path.basename(clip_path)
        return filename in POSITION_CONFIG["corrupted_clips"]

    def _find_default_word_in_position(self, position: str) -> Optional[str]:
        """Find the first available default word in the specified position"""
        default_words = POSITION_CONFIG["default_words"].get(position, ["the", "and", "a"])
        
        if position in self.position_clips:
            for word in default_words:
                if word in self.position_clips[position]:
                    clip_path = self.position_clips[position][word]
                    # Make sure the clip isn't corrupted
                    if not self._is_clip_corrupted(clip_path):
                        return word
        
        return None

    def find_word_clip(self, word: str, position: str) -> Optional[str]:
        """Find video clip for a word in specified position with enhanced fallback"""
        clean_word = word.lower().strip()
        
        # Try exact match in preferred position (avoid corrupted clips)
        if position in self.position_clips:
            if clean_word in self.position_clips[position]:
                clip_path = self.position_clips[position][clean_word]
                if not self._is_clip_corrupted(clip_path):
                    return clip_path
                else:
                    print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Skipping corrupted clip: {os.path.basename(clip_path)}{Style.RESET_ALL}")
        
        # Try fuzzy matching in the SAME position first (keep head position consistent)
        if SIMILARITY_CONFIG["enable_fuzzy_matching"] and position in self.position_clips:
            best_match, best_score = None, 0.0
            
            for available_word in self.position_clips[position].keys():
                clip_path = self.position_clips[position][available_word]
                if self._is_clip_corrupted(clip_path):
                    continue
                    
                # Skip words that are too different in length
                if abs(len(clean_word) - len(available_word)) > SIMILARITY_CONFIG["max_length_difference"]:
                    continue
                
                similarity = difflib.SequenceMatcher(None, clean_word, available_word).ratio()
                
                if similarity > best_score and similarity >= SIMILARITY_CONFIG["similarity_threshold"]:
                    best_match = available_word
                    best_score = similarity
            
            if best_match:
                print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Similar word in {position}: '{word}' -> '{best_match}' (score: {best_score:.2f}){Style.RESET_ALL}")
                return self.position_clips[position][best_match]
        
        # Fallback to main position
        fallback_pos = POSITION_CONFIG["fallback_position"]
        if fallback_pos in self.position_clips:
            if clean_word in self.position_clips[fallback_pos]:
                clip_path = self.position_clips[fallback_pos][clean_word]
                if not self._is_clip_corrupted(clip_path):
                    print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Fallback: '{word}' not in {position}, using {fallback_pos}{Style.RESET_ALL}")
                    return clip_path
        
        # Last resort: find in any position (exact match, avoid corrupted)
        for pos, clips in self.position_clips.items():
            if clean_word in clips:
                clip_path = clips[clean_word]
                if not self._is_clip_corrupted(clip_path):
                    print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Found '{word}' in {pos} instead of {position}{Style.RESET_ALL}")
                    return clip_path
        
        # Fuzzy matching across all positions (as last resort)
        if SIMILARITY_CONFIG["enable_fuzzy_matching"]:
            best_match, best_score, best_position = self._find_similar_word(clean_word)
            
            if best_match and best_position:
                clip_path = self.position_clips[best_position][best_match]
                if not self._is_clip_corrupted(clip_path):
                    print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Similar word: '{word}' -> '{best_match}' (score: {best_score:.2f}) in {best_position}{Style.RESET_ALL}")
                    return clip_path
        
        # FINAL FALLBACK: Use default word for this position
        default_word = self._find_default_word_in_position(position)
        if default_word:
            print(f"{Fore.MAGENTA}[POSITIONAL_LIPSYNC] Using default word: '{word}' -> '{default_word}' in {position}{Style.RESET_ALL}")
            return self.position_clips[position][default_word]
        
        # If default doesn't exist in this position, try main position default
        main_default = self._find_default_word_in_position("main")
        if main_default and "main" in self.position_clips:
            print(f"{Fore.MAGENTA}[POSITIONAL_LIPSYNC] Using main default: '{word}' -> '{main_default}' in main{Style.RESET_ALL}")
            return self.position_clips["main"][main_default]
        
        print(f"{Fore.RED}[POSITIONAL_LIPSYNC] CRITICAL: No usable clips found for '{word}'!{Style.RESET_ALL}")
        return None

    def get_transition_clip(self, from_position: str, to_position: str) -> Optional[str]:
        """Get transition clip between positions with hub-based routing"""
        if not POSITION_CONFIG["use_transitions"]:
            return None
        
        transitions_dir = os.path.join(self.word_clips_dir, "transitions")
        if not os.path.exists(transitions_dir):
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Transitions directory not found: {transitions_dir}{Style.RESET_ALL}")
            return None
        
        # Check if this is a valid direct transition
        transition_key = (from_position, to_position)
        if transition_key in POSITION_CONFIG["available_transitions"]:
            transition_filename = POSITION_CONFIG["available_transitions"][transition_key]
            transition_path = os.path.join(transitions_dir, transition_filename)
            
            if os.path.exists(transition_path) and self._validate_video_clip(transition_path):
                print(f"{Fore.BLUE}[POSITIONAL_LIPSYNC] Found direct transition: {transition_filename}{Style.RESET_ALL}")
                return transition_path
            else:
                print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Direct transition file missing or invalid: {transition_filename}{Style.RESET_ALL}")
        
        # If no direct transition available, check if we need to route through main
        if from_position != "main" and to_position != "main":
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] No direct transition {from_position}->{to_position}. Hub routing required.{Style.RESET_ALL}")
            return None  # Will be handled by inserting intermediate main group
        
        # List available transition files for debugging
        try:
            available_files = os.listdir(transitions_dir)
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] No transition {from_position}->{to_position}. Available: {available_files}{Style.RESET_ALL}")
        except:
            pass
        
        # FALLBACK: Create a simple fade transition on-the-fly
        return self._create_simple_transition(from_position, to_position)

    def _validate_video_clip(self, clip_path: str) -> bool:
        """Validate that a video clip is not corrupted"""
        try:
            if not os.path.exists(clip_path):
                return False
            
            # Check file size (should be at least 1KB)
            if os.path.getsize(clip_path) < 1000:
                return False
            
            # Quick ffprobe check
            cmd = [self.ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_streams', clip_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                info = json.loads(result.stdout)
                # Check if it has a video stream
                video_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
                return len(video_streams) > 0
            
            return False
            
        except Exception as e:
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Validation error for {os.path.basename(clip_path)}: {e}{Style.RESET_ALL}")
            return False

    def _create_simple_transition(self, from_position: str, to_position: str) -> Optional[str]:
        """Create a simple fade transition between positions"""
        if not self.ffmpeg_available:
            return None
        
        # Get a representative clip from each position for the transition
        from_clip = self._get_representative_clip(from_position)
        to_clip = self._get_representative_clip(to_position)
        
        if not from_clip or not to_clip:
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Cannot create transition - missing representative clips{Style.RESET_ALL}")
            return None
        
        # Create transition output path
        transition_path = os.path.join(self.temp_dir, f"auto_transition_{from_position}2{to_position}.mp4")
        
        try:
            # Create a simple crossfade transition (0.5 seconds)
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', from_clip, '-i', to_clip,
                '-filter_complex',
                '[0:v]trim=end=0.25,setpts=PTS-STARTPTS[v0];'
                '[1:v]trim=end=0.25,setpts=PTS-STARTPTS[v1];'
                '[v0][v1]xfade=transition=fade:duration=0.1:offset=0.15',
                '-t', '0.3',  # 0.3 second transition
                '-c:v', 'libx264', '-preset', 'fast',
                transition_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and os.path.exists(transition_path):
                print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Created auto-transition: {from_position} -> {to_position}{Style.RESET_ALL}")
                return transition_path
            else:
                print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Auto-transition failed: {result.stderr[-100:] if result.stderr else 'Unknown error'}{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Transition creation error: {e}{Style.RESET_ALL}")
        
        return None

    def _get_representative_clip(self, position: str) -> Optional[str]:
        """Get a representative clip from a position for transitions"""
        if position not in self.position_clips:
            return None
        
        # Try to find a common, non-corrupted word
        preferred_words = ["the", "and", "a", "to", "of", "in", "is"]
        
        for word in preferred_words:
            if word in self.position_clips[position]:
                clip_path = self.position_clips[position][word]
                if not self._is_clip_corrupted(clip_path) and self._validate_video_clip(clip_path):
                    return clip_path
        
        # Fallback: use any non-corrupted clip from this position
        for word, clip_path in self.position_clips[position].items():
            if not self._is_clip_corrupted(clip_path) and self._validate_video_clip(clip_path):
                return clip_path
        
        return None

    def get_video_info(self, video_path: str) -> Dict:
        """Get video information using ffprobe"""
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
                width = video_stream.get('width', 640)
                height = video_stream.get('height', 480)
                return {'fps': fps, 'duration': duration, 'width': width, 'height': height}
        except Exception as e:
            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Video info error: {e}{Style.RESET_ALL}")
        
        return {'fps': 25, 'duration': 1.0, 'width': 640, 'height': 480}

    def process_word_clip(self, word_info: Dict, position: str, clip_index: int) -> Optional[str]:
        """Process a single word clip with speed adjustment to match timing"""
        word = word_info['word']
        target_duration = word_info['duration']
        
        clip_path = self.find_word_clip(word, position)
        if not clip_path:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] CRITICAL: No clip found for word '{word}' in {position} - skipping{Style.RESET_ALL}")
            return None
        
        # Validate source video file
        if not os.path.exists(clip_path):
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Source clip not found: {clip_path}{Style.RESET_ALL}")
            return None
        
        # Get video info for speed adjustment
        video_info = self.get_video_info(clip_path)
        original_duration = video_info.get('duration', 1.0)
        
        if original_duration == 0:
            original_duration = 1.0
        
        # Calculate speed factor (limit to reasonable range)
        speed_factor = max(0.5, min(2.0, original_duration / target_duration))
        
        output_path = os.path.join(self.temp_dir, f"word_{clip_index:04d}_{word}.mp4")
        
        # Enhanced FFmpeg command with better error handling
        cmd = [
            self.ffmpeg_path, '-y', '-i', clip_path,
            '-an',  # Remove audio (we'll add it back later)
            '-vf', f'setpts={1/speed_factor}*PTS',
            '-t', str(target_duration),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-avoid_negative_ts', 'make_zero',  # Fix timestamp issues
            '-fflags', '+genpts',  # Generate presentation timestamps
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            
            # Verify output file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:  # At least 1KB
                print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Processed '{word}' (speed: {speed_factor:.2f}x, duration: {target_duration:.2f}s){Style.RESET_ALL}")
                return output_path
            else:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Output file '{word}' is invalid or empty{Style.RESET_ALL}")
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] FFmpeg error processing '{word}': {e.stderr[-200:] if e.stderr else 'Unknown error'}{Style.RESET_ALL}")
            return None
        except subprocess.TimeoutExpired:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Timeout processing '{word}'{Style.RESET_ALL}")
            return None

    def create_position_group_video(self, position: str, word_group: List[Dict], group_index: int) -> Optional[str]:
        """Create video for a group of words in the same position WITHOUT gap handling"""
        if not word_group:
            return None
        
        video_clips = []
        clip_counter = 0
        
        # Process each word without gap handling
        for word_info in word_group:
            word_clip = self.process_word_clip(word_info, position, clip_counter)
            if word_clip:
                video_clips.append(word_clip)
                clip_counter += 1
        
        if not video_clips:
            return None
        
        # Concatenate all clips for this group
        output_path = os.path.join(self.temp_dir, f"group_{group_index:03d}_{position}.mp4")
        
        if self._concatenate_clips(video_clips, output_path):
            return output_path
        
        return None

    def _concatenate_clips(self, clip_paths: List[str], output_path: str) -> bool:
        """Concatenate video clips using FFmpeg"""
        if not self.ffmpeg_available or not clip_paths:
            return False
        
        if len(clip_paths) == 1:
            # Single clip - just copy
            try:
                import shutil
                shutil.copy2(clip_paths[0], output_path)
                return True
            except Exception as e:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Copy failed: {e}{Style.RESET_ALL}")
                return False
        
        # Multiple clips - concatenate
        try:
            # Create concat file
            concat_file = os.path.join(self.temp_dir, f"concat_{int(time.time()*1000)}.txt")
            
            with open(concat_file, 'w') as f:
                for clip_path in clip_paths:
                    # Use forward slashes for FFmpeg compatibility
                    clip_path_fixed = clip_path.replace('\\', '/')
                    f.write(f"file '{clip_path_fixed}'\n")
            
            # FFmpeg concat command
            cmd = [
                self.ffmpeg_path, '-f', 'concat', '-safe', '0', '-i', concat_file,
                '-c', 'copy', '-y', output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # Cleanup concat file
            try:
                os.remove(concat_file)
            except:
                pass
            
            if result.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Concat failed: {result.stderr}{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Concatenation error: {e}{Style.RESET_ALL}")
            return False

    def add_audio_to_video(self, video_path: str, audio_path: str, final_output_path: str) -> bool:
        """Add original audio to the concatenated video"""
        cmd = [
            self.ffmpeg_path, '-y', '-i', video_path, '-i', audio_path,
            '-c:v', 'copy', '-c:a', 'aac', '-strict', 'experimental',
            '-shortest',
            final_output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Audio added to video successfully{Style.RESET_ALL}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Error adding audio: {e.stderr}{Style.RESET_ALL}")
            return False

    def generate_positional_lipsync(self, audio_file: str, output_filename: str = None) -> Tuple[bool, Optional[str]]:
        """
        Main function to generate positional lipsync video from audio file
        
        Args:
            audio_file: Path to audio file (WAV, MP3, etc.)
            output_filename: Optional output filename
            
        Returns:
            Tuple of (success: bool, video_path: str or None)
        """
        start_time = time.time()
        
        if not os.path.exists(audio_file):
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Audio file not found: {audio_file}{Style.RESET_ALL}")
            return False, None
        
        # Generate output filename
        if not output_filename:
            timestamp = int(time.time() * 1000)
            output_filename = f"positional_lipsync_{timestamp}.mp4"
        
        final_output_path = os.path.join(self.temp_dir, output_filename)
        
        try:
            print(f"{Fore.MAGENTA}[POSITIONAL_LIPSYNC] Starting generation for: {os.path.basename(audio_file)}{Style.RESET_ALL}")
            
            # Step 1: Transcribe audio using Whisper
            word_data = self.transcribe_audio(audio_file)
            if not word_data:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] No words found in audio transcription{Style.RESET_ALL}")
                return False, None
            
            # Step 2: Clean word data
            cleaned_words = self.clean_and_split_text(word_data)
            if not cleaned_words:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] No valid words after cleaning{Style.RESET_ALL}")
                return False, None
            
            # Step 3: Create word groups by position
            word_groups = self.create_word_groups(cleaned_words)
            if not word_groups:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] No word groups created{Style.RESET_ALL}")
                return False, None
            
            # Step 4: Generate videos for each position group with smart hub routing
            group_videos = []
            prev_position = None
            
            for i, (position, group_words) in enumerate(word_groups):
                word_list = [w['word'] for w in group_words]
                print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Processing group {i+1}/{len(word_groups)}: {position} -> {word_list}{Style.RESET_ALL}")
                
                # Handle transitions with hub routing
                if prev_position and prev_position != position and POSITION_CONFIG["use_transitions"]:
                    transition_clip = self.get_transition_clip(prev_position, position)
                    
                    if transition_clip:
                        # Direct transition available
                        if self._validate_video_clip(transition_clip):
                            group_videos.append(transition_clip)
                            print(f"{Fore.BLUE}[POSITIONAL_LIPSYNC] ✓ Added direct transition: {prev_position} -> {position}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] ✗ Transition clip invalid, skipping{Style.RESET_ALL}")
                    else:
                        # No direct transition - check if we need hub routing
                        if prev_position != "main" and position != "main":
                            print(f"{Fore.CYAN}[POSITIONAL_LIPSYNC] Hub routing required: {prev_position} -> main -> {position}{Style.RESET_ALL}")
                            
                            # Add transition to main first
                            to_main_clip = self.get_transition_clip(prev_position, "main")
                            if to_main_clip and self._validate_video_clip(to_main_clip):
                                group_videos.append(to_main_clip)
                                print(f"{Fore.BLUE}[POSITIONAL_LIPSYNC] ✓ Added hub transition: {prev_position} -> main{Style.RESET_ALL}")
                                
                                # Add a brief main position group (single default word)
                                main_word_info = {
                                    'word': 'the',
                                    'start': 0,
                                    'end': 0.5,
                                    'duration': 0.5
                                }
                                main_clip = self.process_word_clip(main_word_info, "main", 9999)
                                if main_clip:
                                    group_videos.append(main_clip)
                                    print(f"{Fore.BLUE}[POSITIONAL_LIPSYNC] ✓ Added brief main position{Style.RESET_ALL}")
                                
                                # Add transition from main to target position
                                from_main_clip = self.get_transition_clip("main", position)
                                if from_main_clip and self._validate_video_clip(from_main_clip):
                                    group_videos.append(from_main_clip)
                                    print(f"{Fore.BLUE}[POSITIONAL_LIPSYNC] ✓ Added hub transition: main -> {position}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] ✗ No transition found: {prev_position} -> {position}{Style.RESET_ALL}")
                
                # Create video for this word group
                group_video = self.create_position_group_video(position, group_words, i)
                if group_video:
                    group_videos.append(group_video)
                    print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] Group {i+1} completed: {os.path.basename(group_video)}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Group {i+1} FAILED to create video{Style.RESET_ALL}")
                
                prev_position = position
            
            if not group_videos:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] No group videos created{Style.RESET_ALL}")
                return False, None
            
            # Step 5: Concatenate all group videos
            temp_video_path = os.path.join(self.temp_dir, "concatenated_video.mp4")
            print(f"{Fore.MAGENTA}[POSITIONAL_LIPSYNC] Stitching {len(group_videos)} clips into video{Style.RESET_ALL}")
            
            if not self._concatenate_clips(group_videos, temp_video_path):
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Video concatenation failed{Style.RESET_ALL}")
                return False, None
            
            # Step 6: Add original audio back
            print(f"{Fore.MAGENTA}[POSITIONAL_LIPSYNC] Adding original audio back to video{Style.RESET_ALL}")
            
            if self.add_audio_to_video(temp_video_path, audio_file, final_output_path):
                elapsed_time = time.time() - start_time
                print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] ✓ Generation completed in {elapsed_time:.2f}s{Style.RESET_ALL}")
                print(f"{Fore.GREEN}[POSITIONAL_LIPSYNC] ✓ Final video: {final_output_path}{Style.RESET_ALL}")
                
                # Cleanup intermediate files
                self._cleanup_temp_files(group_videos + [temp_video_path], keep_final=True)
                
                return True, final_output_path
            else:
                print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Adding audio failed{Style.RESET_ALL}")
                return False, None
                
        except Exception as e:
            print(f"{Fore.RED}[POSITIONAL_LIPSYNC] Generation error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            return False, None

    def _cleanup_temp_files(self, temp_files: List[str], keep_final: bool = True):
        """Clean up temporary files"""
        for file_path in temp_files:
            if keep_final and "group_" in os.path.basename(file_path):
                # Keep group files for debugging if needed
                continue
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"{Fore.YELLOW}[POSITIONAL_LIPSYNC] Cleanup warning: {e}{Style.RESET_ALL}")

# Public API function for integration
def generate_positional_lipsync_video(audio_file: str, output_filename: str = None, avatar_name: str = "Darwin") -> Tuple[bool, Optional[str]]:
    """
    Public function for generating positional lipsync videos from audio
    
    Args:
        audio_file: Path to audio file (WAV, MP3, etc.)
        output_filename: Optional output filename  
        avatar_name: Avatar name (default: Darwin)
        
    Returns:
        Tuple of (success: bool, video_path: str or None)
    """
    lipsyncer = PositionalLipsyncer(avatar_name)
    return lipsyncer.generate_positional_lipsync(audio_file, output_filename)

# Test function to verify setup
def test_clip_loading():
    """Test function to verify clip loading"""
    print(f"{Fore.GREEN}{'='*60}")
    print(f"{Fore.YELLOW}Testing Clip Loading")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    
    lipsyncer = PositionalLipsyncer()
    
    # Test word extraction
    test_files = [
        "main_hello.mp4",
        "focus_in_body_world_001.mp4", 
        "slight_tilt_body_test_002.mp4",
        "l1_example.mp4"
    ]
    
    print(f"\n{Fore.CYAN}Testing filename extraction:{Style.RESET_ALL}")
    for filename in test_files:
        word = lipsyncer._extract_word_from_filename(filename)
        print(f"{Fore.YELLOW}'{filename}' -> '{word}'{Style.RESET_ALL}")
    
    # Test finding clips
    test_words = ["the", "and", "hello", "world", "test"]
    print(f"\n{Fore.CYAN}Testing word clip finding:{Style.RESET_ALL}")
    for word in test_words:
        for position in ["main", "focus_in", "slight_tilt"]:
            clip_path = lipsyncer.find_word_clip(word, position)
            if clip_path:
                print(f"{Fore.GREEN}Found '{word}' in {position}: {os.path.basename(clip_path)}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}Missing '{word}' in {position}{Style.RESET_ALL}")

# Test function
def test_positional_system():
    """Test the positional lipsync system"""
    try:
        print(f"{Fore.GREEN}{'='*60}")
        print(f"{Fore.YELLOW}Testing Positional Lipsync System with Audio")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        
        # Look for test audio file
        test_audio_files = [
            os.path.join(PROJECT_DIR, "tempstream", "t5.wav"),
            os.path.join(PROJECT_DIR, "test_audio.wav"),
            os.path.join(PROJECT_DIR, "tempstream", "darwin_response_*.wav")
        ]
        
        test_audio = None
        for audio_path in test_audio_files:
            if '*' in audio_path:
                # Find any matching files
                import glob
                matches = glob.glob(audio_path)
                if matches:
                    test_audio = matches[0]
                    break
            elif os.path.exists(audio_path):
                test_audio = audio_path
                break
        
        if not test_audio:
            print(f"{Fore.RED}✗ No test audio file found. Please ensure you have:{Style.RESET_ALL}")
            for path in test_audio_files[:2]:
                print(f"  - {path}")
            return False
        
        print(f"{Fore.CYAN}Using test audio: {test_audio}{Style.RESET_ALL}")
        
        success, video_path = generate_positional_lipsync_video(test_audio, "test_positional_lipsync.mp4")
        
        if success and video_path:
            print(f"\n{Fore.GREEN}✓ Test completed successfully!{Style.RESET_ALL}")
            print(f"{Fore.GREEN}✓ Output video: {video_path}{Style.RESET_ALL}")
            
            # Print file size
            try:
                file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                print(f"{Fore.GREEN}✓ File size: {file_size:.2f} MB{Style.RESET_ALL}")
            except:
                pass
                
            return True
        else:
            print(f"\n{Fore.RED}✗ Test failed{Style.RESET_ALL}")
            return False
            
    except Exception as e:
        print(f"\n{Fore.RED}✗ Test error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Run test when executed directly
    test_positional_system()