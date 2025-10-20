# lipsync_whisper_aligned.py - Word-aligned lip-sync using Whisper timestamps

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
    
    def __init__(self, archive_directory: str, emotion_clips: Dict[str, Dict[str, float]] = None,
                 base_clips: Dict[str, float] = None, idle_clips: Dict[str, float] = None,
                 avoid_repeats: bool = False):
        self.archive_dir = archive_directory
        
        self._check_ffmpeg_availability()
        
        self.emotion_clip_mapping = emotion_clips if emotion_clips is not None else self.DEFAULT_EMOTION_CLIPS.copy()
        self.base_clip_odds = base_clips if base_clips is not None else self.DEFAULT_BASE_CLIPS.copy()
        self.idle_clip_odds = idle_clips if idle_clips is not None else self.DEFAULT_IDLE_CLIPS.copy()
        
        # Normalize base odds
        total_odds = sum(self.base_clip_odds.values())
        if total_odds > 0:
            self.base_clip_odds = {k: v / total_odds for k, v in self.base_clip_odds.items()}
        
        # Normalize idle odds
        total_idle_odds = sum(self.idle_clip_odds.values())
        if total_idle_odds > 0:
            self.idle_clip_odds = {k: v / total_idle_odds for k, v in self.idle_clip_odds.items()}
        
        # Extract all unique clip prefixes
        all_prefixes = set(self.base_clip_odds.keys())
        for emotion_clips_dict in self.emotion_clip_mapping.values():
            all_prefixes.update(emotion_clips_dict.keys())
        self.available_prefixes = list(all_prefixes)
        
        self.avoid_repeats = avoid_repeats
        self.last_used_prefix = None
        
        self.available_clips = self.scan_available_clips()
        
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
        print(f"{Fore.CYAN}[LIPSYNC] Found {len(self.available_clips)} clips{Style.RESET_ALL}")

    def _check_ffmpeg_availability(self):
        """Check if FFmpeg and FFprobe are available"""
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg not found in system PATH")
        if not shutil.which("ffprobe"):
            raise RuntimeError("FFprobe not found in system PATH")

    def scan_available_clips(self) -> List[Dict]:
        """Scan archive directory for clips"""
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
                    clips.append({
                        'filename': file,
                        'path': os.path.join(self.archive_dir, file),
                        'prefix': prefix_found
                    })
        
        return clips

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

    def select_clip_for_word(self, word: str, emotion: str, emphasized_words: List[str]) -> Optional[Dict]:
        """Select clip based on word and emotion"""
        is_emphasized = word.lower() in emphasized_words
        
        if is_emphasized and emotion in self.emotion_clip_mapping:
            emotion_clips = self.emotion_clip_mapping[emotion]
            allowed_prefixes = list(emotion_clips.keys())
            
            suitable_clips = [
                clip for clip in self.available_clips 
                if clip['prefix'] in allowed_prefixes
            ]
            
            weights = [emotion_clips.get(clip['prefix'], 0.5) for clip in suitable_clips]
        else:
            suitable_clips = [
                clip for clip in self.available_clips 
                if clip['prefix'] in self.base_clip_odds
            ]
            
            weights = [self.base_clip_odds.get(clip['prefix'], 0.5) for clip in suitable_clips]
        
        if not suitable_clips:
            suitable_clips = self.available_clips
            weights = [1.0] * len(suitable_clips)
        
        if sum(weights) == 0:
            weights = [1.0] * len(suitable_clips)
        
        selected = random.choices(suitable_clips, weights=weights, k=1)[0]
        return selected

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

    def create_timed_clip(self, clip_path: str, target_duration: float, temp_dir: str, index: int) -> str:
        """Speed up or slow down a clip to match target duration with forced resolution"""
        original_duration = self.get_video_duration(clip_path)
        if original_duration == 0:
            return None
        
        output_path = os.path.join(temp_dir, f"timed_clip_{index}.mp4")
        
        # Calculate speed multiplier (speed up = >1, slow down = <1)
        speed = original_duration / target_duration
        
        # Force 1440x1080 landscape resolution with consistent format
        # Scale, crop, and ensure consistent pixel format
        cmd = [
            "ffmpeg", "-y", "-i", clip_path,
            "-filter:v", f"setpts={1/speed}*PTS,fps=30,scale=1440:1080:force_original_aspect_ratio=increase,crop=1440:1080,format=yuv420p",
            "-t", str(target_duration),  # Trim to exact duration
            "-an",  # Remove audio
            "-c:v", "libx264",  # Re-encode to ensure consistency
            "-preset", "fast",  # Fast encoding
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # Verify the output duration
            actual_duration = self.get_video_duration(output_path)
            if abs(actual_duration - target_duration) > 0.1:
                print(f"{Fore.YELLOW}[LIPSYNC] Warning: clip {index} duration mismatch: {actual_duration:.2f}s vs {target_duration:.2f}s{Style.RESET_ALL}")
            return output_path
        else:
            print(f"{Fore.RED}[LIPSYNC] Error creating timed clip {index}:{Style.RESET_ALL}")
            print(result.stderr)
        return None

    def generate_word_aligned_sequence(self, audio_file: str, text: str, emotion: str, temp_dir: str) -> List[str]:
        """Generate clip sequence aligned to word timestamps"""
        word_timings = self.get_word_timestamps(audio_file)
        emphasized_words = self.get_emphasized_words(text)
        
        # Get total audio duration
        audio_duration = self.get_audio_duration(audio_file)
        
        timed_clips = []
        
        for i, word_data in enumerate(word_timings):
            word = word_data['word']
            duration = word_data['duration']
            
            # Check for deadtime before this word
            if i > 0:
                prev_end = word_timings[i-1]['end']
                current_start = word_data['start']
                gap = current_start - prev_end
                
                if gap > 0.1:
                    # Select random idle clip for deadtime
                    idle_clip_path = self.select_random_idle_clip()
                    if idle_clip_path:
                        idle_filename = os.path.basename(idle_clip_path)
                        print(f"{Fore.YELLOW}[LIPSYNC] Deadtime {gap:.2f}s - inserting {idle_filename}{Style.RESET_ALL}")
                        idle_timed = self.create_timed_clip(idle_clip_path, gap, temp_dir, f"idle_{i}")
                        if idle_timed:
                            timed_clips.append(idle_timed)
            
            # Select and time clip for this word
            clip = self.select_clip_for_word(word, emotion, emphasized_words)
            if clip:
                timed_clip = self.create_timed_clip(clip['path'], duration, temp_dir, i)
                if timed_clip:
                    timed_clips.append(timed_clip)
                    print(f"{Fore.CYAN}[LIPSYNC] '{word}' ({duration:.2f}s) → {clip['prefix']}{Style.RESET_ALL}")
        
        # **FIX: Check for deadtime AFTER the last word**
        if word_timings:
            last_word_end = word_timings[-1]['end']
            final_gap = audio_duration - last_word_end
            
            if final_gap > 0.15:
                idle_clip_path = self.select_random_idle_clip()
                if idle_clip_path:
                    idle_filename = os.path.basename(idle_clip_path)
                    print(f"{Fore.YELLOW}[LIPSYNC] Final deadtime {final_gap:.2f}s - inserting {idle_filename}{Style.RESET_ALL}")
                    idle_timed = self.create_timed_clip(idle_clip_path, final_gap, temp_dir, f"idle_final")
                    if idle_timed:
                        timed_clips.append(idle_timed)
        
        return timed_clips

    def concatenate_clips(self, clip_paths: List[str], output_path: str) -> bool:
        """Concatenate all timed clips into final video with re-encoding for perfect alignment"""
        if not clip_paths:
            return False
        
        # Create concat file
        concat_file = output_path + "_concat.txt"
        with open(concat_file, 'w') as f:
            for clip in clip_paths:
                f.write(f"file '{clip}'\n")
        
        # **FIX: Re-encode instead of copy to ensure frame-perfect concatenation**
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",  # Re-encode instead of copy
            "-preset", "fast",
            "-crf", "18",  # High quality
            "-pix_fmt", "yuv420p",
            "-r", "30",  # Force consistent framerate
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        os.remove(concat_file)
        
        if result.returncode != 0:
            print(f"{Fore.RED}[LIPSYNC] Concatenation error:{Style.RESET_ALL}")
            print(result.stderr)
        
        return result.returncode == 0

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
        
        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}WHISPER-ALIGNED LIP-SYNC{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Audio: {audio_file}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Text: {text}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Emotion: {emotion}{Style.RESET_ALL}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Generate word-aligned clip sequence
            timed_clips = self.generate_word_aligned_sequence(audio_file, text, emotion, temp_dir)
            
            if not timed_clips:
                print(f"{Fore.RED}[LIPSYNC] No clips generated{Style.RESET_ALL}")
                return None
            
            # Concatenate clips
            video_only = os.path.join(temp_dir, "video_only.mp4")
            if not self.concatenate_clips(timed_clips, video_only):
                print(f"{Fore.RED}[LIPSYNC] Failed to concatenate clips{Style.RESET_ALL}")
                return None
            
            # Verify video duration matches audio
            video_duration = self.get_video_duration(video_only)
            audio_duration = self.get_audio_duration(audio_file)
            
            print(f"{Fore.CYAN}[LIPSYNC] Video duration: {video_duration:.2f}s{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[LIPSYNC] Audio duration: {audio_duration:.2f}s{Style.RESET_ALL}")
            
            if abs(video_duration - audio_duration) > 0.5:
                print(f"{Fore.YELLOW}[LIPSYNC] Warning: Duration mismatch > 0.5s{Style.RESET_ALL}")
            
            # **FIX: Combine with audio using shortest duration and explicit stream mapping**
            cmd = [
                "ffmpeg", "-y",
                "-i", video_only,
                "-i", audio_file,
                "-map", "0:v:0",  # Explicitly map video from first input
                "-map", "1:a:0",  # Explicitly map audio from second input
                "-c:v", "copy",   # Copy video stream
                "-c:a", "aac",    # Encode audio
                "-b:a", "192k",   # Audio bitrate
                "-shortest",      # Use shortest stream (should now be properly aligned)
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
    
    # BASE CLIPS (for non-emphasized words) - INDEPENDENT CONFIGURATION
    BASE_CLIP_CONFIG = {
        'idle2': 0.3,
        'idle4': 0.3,
        'idle5': 1.0,
        'idle6': 1.0,
        'idle7': 1.0,
    }
    
    # IDLE CLIPS (for deadtime gaps) - Individual clip filenames with odds
    IDLE_CLIP_CONFIG = {
        'idle4.mp4': 1.0,
        'idle5.mp4': 1.0,
        'idle6.mp4': 1.0,
    }
    
    print(f"{Fore.GREEN}STARTING WHISPER-ALIGNED LIP-SYNC SYSTEM{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")
    
    try:
        lipsync_system = WhisperAlignedLipSync(
            archive_directory=ARCHIVE_DIR,
            emotion_clips=EMOTION_CLIP_CONFIG,
            base_clips=BASE_CLIP_CONFIG,
            idle_clips=IDLE_CLIP_CONFIG,
            avoid_repeats=False
        )
        
        # CONFIGURE YOUR AUDIO FILE AND TEXT HERE
        input_audio_file = "heygen_s.m4a"
        test_text = "Everything in your life is a reflection of a choice you have made. If you want a different result, make a different choice"
        test_emotion = "positive"
        
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