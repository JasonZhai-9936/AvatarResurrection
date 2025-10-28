# lipsync_whisper_aligned_improved.py - Word-aligned lip-sync with stretch limits

import os
import random
import subprocess
import shutil
import tempfile
from typing import List, Dict, Optional
from datetime import datetime
from colorama import Fore, Style, init
from faster_whisper import WhisperModel

init(autoreset=True)

# Try to load spaCy for emphasis detection
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
    print(f"{Fore.GREEN}[LIPSYNC] spaCy loaded for emphasis detection{Style.RESET_ALL}")
except:
    nlp = None
    SPACY_AVAILABLE = False
    print(f"{Fore.YELLOW}[LIPSYNC] spaCy not available - emphasis detection disabled{Style.RESET_ALL}")

# Global Whisper model
_whisper_model = None

# STRETCH LIMIT CONFIGURATION
MAX_STRETCH_RATIO = 1.5  # Don't stretch clips more than 1.5x
MIN_STRETCH_RATIO = 0.5  # Don't slow down clips more than 0.5x (2x slower)
MAX_SELECTION_ATTEMPTS = 5  # Try 5 times before using fallback

def get_whisper_model():
    """Get or create Whisper model instance"""
    global _whisper_model
    if _whisper_model is None:
        print(f"{Fore.CYAN}[WHISPER] Loading tiny model...{Style.RESET_ALL}")
        
        # Use CPU for reliability (tiny model is fast enough on CPU)
        try:
            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            print(f"{Fore.GREEN}[WHISPER] Model loaded (CPU - optimized for speed){Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[WHISPER] Failed to load model: {e}{Style.RESET_ALL}")
            raise
    
    return _whisper_model

class WhisperAlignedLipSync:
    # Default emotion and base clips configuration
    DEFAULT_EMOTION_CLIPS = {
        'neutral': {
            'idle2': 1.0,
            'circle1': 0.3,
            'slight_shake1': 0.5,
            'slight_lean3': 0.4,
            'main2': 0.4,
            'idle3': 1.0,
        },
        'emphatic': {
            'nod1': 1.0,
            'smirk1': 1.0,
            'head_lower1': 0.5,
            'head_lower2': 0.5,
            'head_raise1': 0.5,
        },
        'contrastive': {
            'look_down1': 1.0,
            'slight_shake7': 0.8,
            'head_lower1': 0.5,
            'slight_shake2': 0.5,
            'slight_look1': 0.8,
            'eye_look1': 0.6,
            'idle_hand1': 0.6,
            'idle4': 0.6,
            'nod3': 0.6,
            'slight_shake3': 0.5,
        },
        'positive': {
            'nod1': 0.5,
            'smirk1': 0.5,
        },
        'negative': {
            'look_down1': 1.0,
            'slight_shake7': 0.9,
            'slight_shake2': 0.5,
            'eye_look1': 0.6,
            'idle_hand1': 0.6,
            'nod2': 0.6,
            'nod3': 0.6,
        }
    }
    
    DEFAULT_BASE_CLIPS = {
        'idle2': 1.0,
        'circle1': 0.3,
        'slight_shake1': 0.5,
        'slight_lean3': 0.4,
        'main2': 0.4,
        'idle3': 1.0,
    }
    
    DEFAULT_IDLE_CLIPS = {
        'idle4.mp4': 1.0,
        'idle5.mp4': 1.0,
        'idle6.mp4': 1.0,
    }
    
    # Default word library clips (prefixes that have word-specific clips)
    DEFAULT_WORD_LIBRARY_CLIPS = {
        'idle7': 1.0,
        'slight_shake7': 0.8,
        'idle6': 1.0,
    }
    
    # Default short clips (used as fallback when stretch limits are exceeded)
    DEFAULT_SHORT_CLIPS = {
        'idle4': 1.0,
        'idle5': 1.0,
        'idle6': 1.0,
    }
    
    def __init__(self, archive_directory: str, emotion_clips: Dict[str, Dict[str, float]] = None,
                 base_clips: Dict[str, float] = None, idle_clips: Dict[str, float] = None,
                 word_library_clips: Dict[str, float] = None, short_clips: Dict[str, float] = None,
                 word_clip_odds: int = 3, syllable_clip_odds: int = 1,
                 avoid_repeats: bool = False):
        self.archive_dir = archive_directory
        self.word_library_dir = os.path.join(archive_directory, "word_library")
        
        self._check_ffmpeg_availability()
        
        self.emotion_clip_mapping = emotion_clips if emotion_clips is not None else self.DEFAULT_EMOTION_CLIPS.copy()
        self.base_clip_odds = base_clips if base_clips is not None else self.DEFAULT_BASE_CLIPS.copy()
        self.idle_clip_odds = idle_clips if idle_clips is not None else self.DEFAULT_IDLE_CLIPS.copy()
        self.word_library_clip_odds = word_library_clips if word_library_clips is not None else self.DEFAULT_WORD_LIBRARY_CLIPS.copy()
        self.short_clip_odds = short_clips if short_clips is not None else self.DEFAULT_SHORT_CLIPS.copy()
        
        # Word vs Syllable preference odds
        self.word_clip_odds = word_clip_odds
        self.syllable_clip_odds = syllable_clip_odds
        
        print(f"{Fore.CYAN}[LIPSYNC] Word clip odds: {word_clip_odds}, Syllable clip odds: {syllable_clip_odds}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Stretch limits: {MIN_STRETCH_RATIO}x - {MAX_STRETCH_RATIO}x, Max attempts: {MAX_SELECTION_ATTEMPTS}{Style.RESET_ALL}")
        
        # Normalize base odds
        total_odds = sum(self.base_clip_odds.values())
        if total_odds > 0:
            self.base_clip_odds = {k: v / total_odds for k, v in self.base_clip_odds.items()}
        
        # Normalize idle odds
        total_idle_odds = sum(self.idle_clip_odds.values())
        if total_idle_odds > 0:
            self.idle_clip_odds = {k: v / total_idle_odds for k, v in self.idle_clip_odds.items()}
        
        # Normalize word library odds
        total_word_library_odds = sum(self.word_library_clip_odds.values())
        if total_word_library_odds > 0:
            self.word_library_clip_odds = {k: v / total_word_library_odds for k, v in self.word_library_clip_odds.items()}
        
        # Normalize short clips odds
        total_short_clip_odds = sum(self.short_clip_odds.values())
        if total_short_clip_odds > 0:
            self.short_clip_odds = {k: v / total_short_clip_odds for k, v in self.short_clip_odds.items()}
        
        # Extract all unique clip prefixes
        all_prefixes = set(self.base_clip_odds.keys())
        for emotion_clips_dict in self.emotion_clip_mapping.values():
            all_prefixes.update(emotion_clips_dict.keys())
        all_prefixes.update(self.word_library_clip_odds.keys())
        all_prefixes.update(self.short_clip_odds.keys())  # Add short clips to scanning
        self.available_prefixes = list(all_prefixes)
        
        self.avoid_repeats = avoid_repeats
        self.last_used_prefix = None
        
        # Scan syllable clips
        self.available_clips = self.scan_available_clips()
        
        # Scan word library clips
        self.word_library_clips = self.scan_word_library_clips()
        
        # Scan for idle clips
        self.available_idle_clips = []
        for idle_filename in self.idle_clip_odds.keys():
            idle_path = os.path.join(self.archive_dir, idle_filename)
            if os.path.exists(idle_path):
                self.available_idle_clips.append({
                    'filename': idle_filename,
                    'path': idle_path,
                    'weight': self.idle_clip_odds[idle_filename]
                })
        
        if not self.available_idle_clips:
            print(f"{Fore.YELLOW}[LIPSYNC] Warning: No idle clips found for deadtime fill{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}[LIPSYNC] Found {len(self.available_idle_clips)} idle clips for deadtime{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}[LIPSYNC] Whisper-aligned lip-sync initialized{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Found {len(self.available_clips)} syllable clips{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Found {len(self.word_library_clips)} word-specific clips{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Short clips for fallback: {list(self.short_clip_odds.keys())}{Style.RESET_ALL}")

    def _check_ffmpeg_availability(self):
        """Check if FFmpeg and FFprobe are available"""
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg not found in system PATH")
        if not shutil.which("ffprobe"):
            raise RuntimeError("FFprobe not found in system PATH")

    def scan_available_clips(self) -> List[Dict]:
        """Scan archive directory for syllable clips (lazy load durations)"""
        clips = []
        if not os.path.exists(self.archive_dir):
            return clips
        
        for file in os.listdir(self.archive_dir):
            if file.endswith('.mp4'):
                prefix_found = None
                for prefix in self.available_prefixes:
                    if file.startswith(prefix + "_") or file.startswith(prefix + "."):
                        prefix_found = prefix
                        break
                
                if prefix_found:
                    full_path = os.path.join(self.archive_dir, file)
                    
                    clips.append({
                        'filename': file,
                        'path': full_path,
                        'prefix': prefix_found,
                        'duration': None  # Will be loaded on-demand
                    })
        
        if clips:
            print(f"{Fore.GREEN}[LIPSYNC] Syllable clips scanned: {len(clips)} clips{Style.RESET_ALL}")
        
        return clips

    def scan_word_library_clips(self) -> Dict[str, List[Dict]]:
        """Scan word_library directory for word-specific clips (lazy load durations)"""
        word_clips = {}
        
        if not os.path.exists(self.word_library_dir):
            print(f"{Fore.YELLOW}[LIPSYNC] Warning: word_library directory not found{Style.RESET_ALL}")
            return word_clips
        
        for file in os.listdir(self.word_library_dir):
            if file.endswith('.mp4'):
                # Check if filename matches any word library prefix
                for prefix in self.word_library_clip_odds.keys():
                    if file.startswith(prefix + "_"):
                        # Extract word from filename (e.g., "idle7_hello.mp4" -> "hello")
                        word = file[len(prefix)+1:-4].lower()
                        full_path = os.path.join(self.word_library_dir, file)
                        
                        if word not in word_clips:
                            word_clips[word] = []
                        
                        word_clips[word].append({
                            'filename': file,
                            'path': full_path,
                            'prefix': prefix,
                            'duration': None,  # Will be loaded on-demand
                            'weight': self.word_library_clip_odds[prefix]
                        })
                        break
        
        total_clips = sum(len(clips) for clips in word_clips.values())
        if word_clips:
            print(f"{Fore.GREEN}[LIPSYNC] Word library loaded: {len(word_clips)} unique words, {total_clips} total clips{Style.RESET_ALL}")
        
        return word_clips

    def count_syllables(self, word: str) -> int:
        """Estimate syllable count"""
        word = word.lower().strip('.,!?;:"\'-')
        vowels = "aeiouy"
        syllable_count = 0
        previous_was_vowel = False
        
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel
        
        if word.endswith("e"):
            syllable_count -= 1
        
        if word.endswith("le") and len(word) > 2 and word[-3] not in vowels:
            syllable_count += 1
        
        return max(1, syllable_count)

    def select_random_idle_clip(self) -> Optional[str]:
        """Select random idle clip using weighted odds"""
        if not self.available_idle_clips:
            return None
        
        clips = [clip['path'] for clip in self.available_idle_clips]
        weights = [clip['weight'] for clip in self.available_idle_clips]
        
        if sum(weights) == 0:
            weights = [1.0] * len(weights)
        
        selected_path = random.choices(clips, weights=weights, k=1)[0]
        return selected_path

    def get_emphasized_words(self, text: str) -> List[str]:
        """Detect emphasized words using spaCy"""
        if not SPACY_AVAILABLE or not nlp:
            return []
        
        doc = nlp(text)
        emphasized = []
        
        for token in doc:
            if (
                token.pos_ in {"ADJ", "ADV", "VERB", "INTJ"}
                or token.dep_ in {"ROOT", "attr", "acomp"}
                or token.ent_type_ != ""
                or token.tag_ in {"JJR", "JJS", "RBR", "RBS"}
            ):
                emphasized.append(token.text.lower())
        
        return emphasized

    def get_word_timestamps(self, audio_file: str) -> List[Dict]:
        """Get word-level timestamps using Whisper"""
        model = get_whisper_model()
        
        print(f"{Fore.CYAN}[WHISPER] Transcribing audio for word alignment...{Style.RESET_ALL}")
        
        segments, info = model.transcribe(audio_file, beam_size=5, word_timestamps=True)
        
        word_timings = []
        for segment in segments:
            if hasattr(segment, 'words'):
                for word in segment.words:
                    word_timings.append({
                        'word': word.word.strip(),
                        'start': word.start,
                        'end': word.end,
                        'duration': word.end - word.start
                    })
        
        print(f"{Fore.GREEN}[WHISPER] Found {len(word_timings)} words with timestamps{Style.RESET_ALL}")
        return word_timings

    def select_clip_with_stretch_limit(self, clips_pool: List[Dict], weights: List[float], 
                                       target_duration: float, clip_type: str) -> Optional[Dict]:
        """
        Select a clip that won't exceed MAX_STRETCH_RATIO or go below MIN_STRETCH_RATIO.
        Try up to MAX_SELECTION_ATTEMPTS times, then use the shortest clip as fallback.
        
        Args:
            clips_pool: List of available clips
            weights: Corresponding weights for selection
            target_duration: Duration the clip needs to be stretched to
            clip_type: Description for logging (e.g., "word", "syllable", "emotion")
        """
        if not clips_pool:
            return None
        
        attempted_clips = []  # Track all attempts to find shortest
        
        for attempt in range(MAX_SELECTION_ATTEMPTS):
            selected = random.choices(clips_pool, weights=weights, k=1)[0]
            clip_duration = self.get_clip_duration(selected)  # Load on-demand
            
            attempted_clips.append((selected, clip_duration))
            
            if clip_duration == 0:
                print(f"{Fore.YELLOW}[STRETCH] Warning: Clip has 0 duration, using anyway{Style.RESET_ALL}")
                return selected
            
            stretch_ratio = target_duration / clip_duration
            
            # Check if stretch ratio is within acceptable range
            if MIN_STRETCH_RATIO <= stretch_ratio <= MAX_STRETCH_RATIO:
                if attempt > 0:
                    print(f"{Fore.GREEN}[STRETCH] Found suitable {clip_type} clip on attempt {attempt + 1} (stretch: {stretch_ratio:.2f}x){Style.RESET_ALL}")
                return selected
            else:
                if attempt < MAX_SELECTION_ATTEMPTS - 1:
                    if stretch_ratio > MAX_STRETCH_RATIO:
                        print(f"{Fore.YELLOW}[STRETCH] Attempt {attempt + 1}: {clip_type} clip too short (would need {stretch_ratio:.2f}x stretch), retrying...{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}[STRETCH] Attempt {attempt + 1}: {clip_type} clip too long (would be {stretch_ratio:.2f}x stretch), retrying...{Style.RESET_ALL}")
        
        # After MAX_SELECTION_ATTEMPTS, use short clips pool as fallback
        # Filter available clips to only those in short_clip_odds
        short_clips_pool = [
            clip for clip in clips_pool 
            if clip['prefix'] in self.short_clip_odds
        ]
        
        if not short_clips_pool:
            # If no short clips available, fall back to finding closest clip from original pool
            shortest_clip = min(attempted_clips, key=lambda x: abs(x[1] - target_duration))
            selected = shortest_clip[0]
            stretch_ratio = target_duration / self.get_clip_duration(selected)
            print(f"{Fore.RED}[STRETCH] No short clips available, using closest from attempts (orig:{shortest_clip[1]:.2f}s, stretch: {stretch_ratio:.2f}x){Style.RESET_ALL}")
            return selected
        
        # Select from short clips pool with weights
        short_weights = [self.short_clip_odds.get(clip['prefix'], 1.0) for clip in short_clips_pool]
        if sum(short_weights) == 0:
            short_weights = [1.0] * len(short_clips_pool)
        
        selected = random.choices(short_clips_pool, weights=short_weights, k=1)[0]
        clip_duration = self.get_clip_duration(selected)
        stretch_ratio = target_duration / clip_duration
        
        print(f"{Fore.MAGENTA}[STRETCH] Using SHORT CLIP fallback: {selected['prefix']} (orig:{clip_duration:.2f}s, stretch: {stretch_ratio:.2f}x){Style.RESET_ALL}")
        return selected

    def select_clip_for_word(self, word: str, word_duration: float, emotion: str, 
                            emphasized_words: List[str]) -> Optional[Dict]:
        """
        Select clip based on word and emotion, with stretch limit checking.
        Priority: word-specific clips > syllable clips with stretch checking
        """
        is_emphasized = word.lower() in emphasized_words
        word_normalized = word.lower().strip('.,!?;:')
        
        # STEP 1: Check word-specific clips first
        has_word_clip = word_normalized in self.word_library_clips
        
        if has_word_clip:
            # Decide whether to use word clip or syllable clip based on odds
            choice = random.choices(
                ['word', 'syllable'],
                weights=[self.word_clip_odds, self.syllable_clip_odds],
                k=1
            )[0]
            
            if choice == 'word':
                available_word_clips = self.word_library_clips[word_normalized]
                weights = [clip['weight'] for clip in available_word_clips]
                
                if sum(weights) == 0:
                    weights = [1.0] * len(weights)
                
                # Try to find a word clip that doesn't exceed stretch limit
                selected = self.select_clip_with_stretch_limit(
                    available_word_clips, weights, word_duration, f"word '{word}'"
                )
                
                if selected:
                    print(f"{Fore.MAGENTA}[WORD] Using word clip for '{word}': {selected['prefix']}{Style.RESET_ALL}")
                    return selected
        
        # STEP 2: Fall back to syllable-based selection with emotion weighting
        syllable_count = self.count_syllables(word)
        
        if is_emphasized and emotion in self.emotion_clip_mapping:
            # Use emotion-weighted clips for emphasized words
            emotion_clips = self.emotion_clip_mapping[emotion]
            allowed_prefixes = list(emotion_clips.keys())
            
            suitable_clips = [
                clip for clip in self.available_clips 
                if clip['prefix'] in allowed_prefixes
            ]
            
            weights = [emotion_clips.get(clip['prefix'], 0.5) for clip in suitable_clips]
            clip_type = f"emotion ({emotion})"
        else:
            # Use base clips for non-emphasized words
            suitable_clips = [
                clip for clip in self.available_clips 
                if clip['prefix'] in self.base_clip_odds
            ]
            
            weights = [self.base_clip_odds.get(clip['prefix'], 0.5) for clip in suitable_clips]
            clip_type = "syllable"
        
        # Filter for clips with no weights
        if not suitable_clips:
            suitable_clips = self.available_clips
            weights = [1.0] * len(suitable_clips)
        
        if sum(weights) == 0:
            weights = [1.0] * len(suitable_clips)
        
        # Try to find a syllable/emotion clip that doesn't exceed stretch limit
        selected = self.select_clip_with_stretch_limit(
            suitable_clips, weights, word_duration, clip_type
        )
        
        return selected

    def get_clip_duration(self, clip: Dict) -> float:
        """Get clip duration, loading on-demand and caching result"""
        if 'duration' not in clip or clip['duration'] is None:
            clip['duration'] = self.get_video_duration(clip['path'])
        return clip['duration']

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe"""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            return 0.0

    def get_audio_duration(self, audio_file: str) -> float:
        """Get audio duration using ffprobe"""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            audio_file
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            return 0.0

    def time_stretch_video(self, input_video: str, output_video: str, speed_factor: float, target_duration: float) -> bool:
        """Stretch/compress video using FFmpeg setpts filter with forced duration and re-encoding"""
        pts_factor = 1.0 / speed_factor
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-filter:v", f"setpts={pts_factor}*PTS,fps=30,scale=1440:1080:force_original_aspect_ratio=increase,crop=1440:1080,format=yuv420p",
            "-t", str(target_duration),  # Force exact output duration
            "-an",
            "-c:v", "libx264",
            "-preset", "fast",
            output_video
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Verify the output duration
            actual_duration = self.get_video_duration(output_video)
            if abs(actual_duration - target_duration) > 0.1:
                print(f"{Fore.YELLOW}[STRETCH] Warning: duration mismatch: {actual_duration:.2f}s vs {target_duration:.2f}s{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.RED}[STRETCH] FFmpeg error: {result.stderr[:200]}{Style.RESET_ALL}")
            return False

    def concatenate_clips(self, clips: List[str], output_file: str) -> bool:
        """Concatenate video clips using FFmpeg concat demuxer"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            concat_file = f.name
            for clip in clips:
                f.write(f"file '{clip}'\n")
        
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        finally:
            if os.path.exists(concat_file):
                os.remove(concat_file)

    def get_next_output_filename(self, base_output_file: str) -> str:
        """Generate incremental filename if file exists"""
        if not os.path.exists(base_output_file):
            return base_output_file
        
        directory = os.path.dirname(base_output_file)
        filename = os.path.basename(base_output_file)
        name, ext = os.path.splitext(filename)
        
        counter = 1
        while True:
            new_filename = f"{name}_{counter}{ext}"
            new_path = os.path.join(directory, new_filename)
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def generate_word_aligned_sequence(self, audio_file: str, text: str, 
                                      emotion: str, temp_dir: str) -> List[str]:
        """Generate time-aligned video sequence based on Whisper word timestamps"""
        
        # Get word timestamps from Whisper
        word_timings = self.get_word_timestamps(audio_file)
        
        if not word_timings:
            print(f"{Fore.RED}[LIPSYNC] No word timings detected{Style.RESET_ALL}")
            return []
        
        # Get emphasized words
        emphasized_words = self.get_emphasized_words(text)
        print(f"{Fore.CYAN}[LIPSYNC] Emphasized words: {emphasized_words}{Style.RESET_ALL}")
        
        timed_clips = []
        audio_duration = self.get_audio_duration(audio_file)
        
        for i, word_info in enumerate(word_timings):
            word = word_info['word']
            start_time = word_info['start']
            end_time = word_info['end']
            word_duration = word_info['duration']
            
            # Select clip with stretch limit checking
            selected_clip = self.select_clip_for_word(
                word, word_duration, emotion, emphasized_words
            )
            
            if not selected_clip:
                print(f"{Fore.YELLOW}[LIPSYNC] No clip found for word '{word}'{Style.RESET_ALL}")
                continue
            
            clip_path = selected_clip['path']
            clip_duration = self.get_clip_duration(selected_clip)  # Load on-demand
            
            if clip_duration == 0:
                print(f"{Fore.YELLOW}[LIPSYNC] Clip has 0 duration: {clip_path}{Style.RESET_ALL}")
                continue
            
            # Calculate speed adjustment
            speed_factor = clip_duration / word_duration
            stretch_ratio = word_duration / clip_duration  # This is the actual stretch amount
            
            # Time-stretch the clip
            stretched_clip = os.path.join(temp_dir, f"stretched_{i}_{word}.mp4")
            
            if self.time_stretch_video(clip_path, stretched_clip, speed_factor, word_duration):
                timed_clips.append(stretched_clip)
                prefix = selected_clip.get('prefix', 'unknown')
                print(f"{Fore.GREEN}[LIPSYNC] '{word}' (word:{word_duration:.2f}s, orig:{clip_duration:.2f}s, stretch:{stretch_ratio:.2f}x) → {prefix}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[LIPSYNC] Failed to stretch clip for '{word}'{Style.RESET_ALL}")
            
            # Fill gaps with idle clips
            if i < len(word_timings) - 1:
                next_start = word_timings[i + 1]['start']
                gap_duration = next_start - end_time
                
                if gap_duration > 0.1:
                    idle_clip_path = self.select_random_idle_clip()
                    if idle_clip_path:
                        idle_duration = self.get_video_duration(idle_clip_path)
                        if idle_duration > 0:
                            idle_speed = idle_duration / gap_duration
                            stretched_idle = os.path.join(temp_dir, f"idle_{i}.mp4")
                            idle_filename = os.path.basename(idle_clip_path)
                            
                            if self.time_stretch_video(idle_clip_path, stretched_idle, idle_speed, gap_duration):
                                timed_clips.append(stretched_idle)
                                print(f"{Fore.CYAN}[LIPSYNC] Deadtime {gap_duration:.2f}s - inserting {idle_filename}{Style.RESET_ALL}")
        
        # Fill final deadtime if needed
        if word_timings:
            last_word_end = word_timings[-1]['end']
            final_gap = audio_duration - last_word_end
            
            if final_gap > 0.1:
                idle_clip_path = self.select_random_idle_clip()
                if idle_clip_path:
                    idle_duration = self.get_video_duration(idle_clip_path)
                    if idle_duration > 0:
                        idle_speed = idle_duration / final_gap
                        stretched_idle = os.path.join(temp_dir, f"idle_final.mp4")
                        idle_filename = os.path.basename(idle_clip_path)
                        
                        if self.time_stretch_video(idle_clip_path, stretched_idle, idle_speed, final_gap):
                            timed_clips.append(stretched_idle)
                            print(f"{Fore.CYAN}[LIPSYNC] Final deadtime {final_gap:.2f}s - inserting {idle_filename}{Style.RESET_ALL}")
        
        return timed_clips
    
    def generate_lip_sync_video(self, audio_file: str, output_file: str = None,
                                  output_dir: str = None, use_sequential: bool = True,
                                  text: str = "", emotion: str = "neutral") -> str:
        """Main function - generate word-aligned lip-sync"""
        if not text:
            print(f"{Fore.RED}[LIPSYNC] Text required for Whisper alignment{Style.RESET_ALL}")
            return None
        
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(audio_file))[0] + f"_whisper_{emotion}"
            if output_dir is None:
                output_dir = os.path.dirname(audio_file) or "."
            output_file = os.path.join(output_dir, base_name + ".mp4")
        
        # Get next available filename with incremental numbering
        output_file = self.get_next_output_filename(output_file)
        
        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}WHISPER-ALIGNED LIP-SYNC (with stretch limits){Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Audio: {audio_file}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Text: {text}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Emotion: {emotion}{Style.RESET_ALL}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            timed_clips = self.generate_word_aligned_sequence(audio_file, text, emotion, temp_dir)
            
            if not timed_clips:
                print(f"{Fore.RED}[LIPSYNC] No clips generated{Style.RESET_ALL}")
                return None
            
            video_only = os.path.join(temp_dir, "video_only.mp4")
            if not self.concatenate_clips(timed_clips, video_only):
                print(f"{Fore.RED}[LIPSYNC] Failed to concatenate clips{Style.RESET_ALL}")
                return None
            
            video_duration = self.get_video_duration(video_only)
            audio_duration = self.get_audio_duration(audio_file)
            
            print(f"{Fore.CYAN}[LIPSYNC] Video duration: {video_duration:.2f}s{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[LIPSYNC] Audio duration: {audio_duration:.2f}s{Style.RESET_ALL}")
            
            if abs(video_duration - audio_duration) > 0.5:
                print(f"{Fore.YELLOW}[LIPSYNC] Warning: Duration mismatch > 0.5s{Style.RESET_ALL}")
            
            cmd = [
                "ffmpeg", "-y",
                "-i", video_only,
                "-i", audio_file,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                final_duration = self.get_video_duration(output_file)
                print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}✓ Word-aligned lip-sync created:{Style.RESET_ALL}")
                print(f"{Fore.GREEN}  {output_file}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}  Final duration: {final_duration:.2f}s{Style.RESET_ALL}")
                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                return output_file
            else:
                print(f"{Fore.RED}[LIPSYNC] Error merging audio:{Style.RESET_ALL}")
                print(result.stderr)
            
            return None
        

if __name__ == "__main__":
    ARCHIVE_DIR = "./archive"
    OUTPUT_DIR = "./output"
    
    # EMOTION-SPECIFIC CLIPS (for emphasized words)
    EMOTION_CLIP_CONFIG = {
        'neutral': {
            'idle2': 1.0,
            'circle1': 0.3,
            'slight_shake1': 0.5,
            'slight_lean3': 0.4,
            'main2': 0.4,
            'idle3': 1.0,
        },
        'emphatic': {
            'nod1': 1.0,
            'smirk1': 1.0,
            'head_lower1': 0.5,
            'head_lower2': 0.5,
            'head_raise1': 0.5,
        },
        'contrastive': {
            'look_down1': 1.0,
            'slight_shake7': 0.8,
            'head_lower1': 0.5,
            'slight_shake2': 0.5,
            'slight_look1': 0.8,
            'eye_look1': 0.6,
            'idle_hand1': 0.6,
            'idle4': 0.6,
            'nod3': 0.6,
            'slight_shake3': 0.5,
        },
        'positive': {
            'nod1': 0.5,
            'smirk1': 0.5,
        },
        'negative': {
            'look_down1': 1.0,
            'slight_shake7': 0.9,
            'slight_shake2': 0.5,
            'eye_look1': 0.6,
            'idle_hand1': 0.6,
            'nod2': 0.6,
            'nod3': 0.6,
        }
    }
    
    # BASE CLIPS (for non-emphasized words)
    BASE_CLIP_CONFIG = {
        'idle2': 0.3,
        'idle4': 0.3,
        # 'idle5': 0.7,
        # 'idle6': 0.7,
        # 'idle7': 0.7,
        # 'nod1': 1.0,
        # 'smirk1': 1.0,
        'head_lower1': 1,
        'head_lower2': 1,
        'head_raise1': 1,
        'look_down1': 1.0,
        'slight_shake7': 0.8,
        'slight_shake2': 0.5,
        'slight_look1': 0.8,
        'eye_look1': 0.6,
        'idle_hand1': 0.6,
        'nod3': 0.6,
        'slight_shake3': 0.5,
    }
    
    # IDLE CLIPS (for deadtime gaps)
    IDLE_CLIP_CONFIG = {
        'idle4.mp4': 1.0,
        'idle5.mp4': 1.0,
        'idle6.mp4': 1.0,
    }
    
    # WORD LIBRARY CLIPS
    WORD_LIBRARY_CONFIG = {
        # 'idle7': 1.0,
        'slight_shake7': 0.5,
        # 'idle6': 1.0,
        # 'idle7': 1.0,
        # 'idle6': 1.0,
        # 'idle_4f': 1.0,
        # 'idle7.5': 0.5,
    }
    
    # SHORT CLIPS (fallback when stretch limits exceeded after 5 attempts)
    SHORT_CLIPS_CONFIG = {
        'idle4': 1.0,
        'idle5': 1.0,
        'idle6': 1.0,
    }
    
    # WORD vs SYLLABLE PREFERENCE
    WORD_CLIP_ODDS = 1
    SYLLABLE_CLIP_ODDS = 9
    
    print(f"{Fore.GREEN}STARTING WHISPER-ALIGNED LIP-SYNC SYSTEM (WITH STRETCH LIMITS){Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")
    
    try:
        lipsync_system = WhisperAlignedLipSync(
            archive_directory=ARCHIVE_DIR,
            emotion_clips=EMOTION_CLIP_CONFIG,
            base_clips=BASE_CLIP_CONFIG,
            idle_clips=IDLE_CLIP_CONFIG,
            word_library_clips=WORD_LIBRARY_CONFIG,
            short_clips=SHORT_CLIPS_CONFIG,
            word_clip_odds=WORD_CLIP_ODDS,
            syllable_clip_odds=SYLLABLE_CLIP_ODDS,
            avoid_repeats=False
        )
        
        # CONFIGURE YOUR AUDIO FILE AND TEXT HERE
        input_audio_file = "heygen_s.m4a"
        test_text = "Everything in your life is a reflection of a choice you have made. If you want a different result, make a different choice"
        test_emotion = "emphatic"
        
        if os.path.exists(input_audio_file):
            output_video_path = lipsync_system.generate_lip_sync_video(
                audio_file=input_audio_file,
                output_dir=OUTPUT_DIR,
                use_sequential=True,
                text=test_text,
                emotion=test_emotion
            )
            
            if output_video_path:
                print(f"\n{Fore.GREEN}Process finished. Output: {output_video_path}{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}Process failed{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Error: Input audio file not found: '{input_audio_file}'{Style.RESET_ALL}")
            
    except Exception as e:
        print(f"\n{Fore.RED}Error occurred: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()