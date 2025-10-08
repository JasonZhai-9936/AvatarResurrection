# lipsync_crossfade.py - Enhanced with emotion-based clip selection and emphasis detection

import os
import json
import random
import subprocess
import shutil
from pathlib import Path
import tempfile
from typing import List, Dict, Optional
from datetime import datetime
from colorama import Fore, Style, init

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
    print(f"{Fore.YELLOW}[LIPSYNC] Run: python -m spacy download en_core_web_sm{Style.RESET_ALL}")

class SimplifiedLipSyncSystem:
    # DEFAULT CONFIGURATION - Edit these to customize clip selection
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
    
    def __init__(self, archive_directory: str, emotion_clips: Dict[str, Dict[str, float]] = None,
                 base_clips: Dict[str, float] = None, avoid_repeats: bool = False, 
                 transition_duration: float = 0.1):
        self.archive_dir = archive_directory
        self.TRANSITION_DURATION = transition_duration
        
        self._check_ffmpeg_availability()
        
        # EMOTION-SPECIFIC CLIPS (for emphasized words)
        self.emotion_clip_mapping = emotion_clips if emotion_clips is not None else self.DEFAULT_EMOTION_CLIPS.copy()
        
        # BASE CLIPS (for non-emphasized words)
        self.base_clip_odds = base_clips if base_clips is not None else self.DEFAULT_BASE_CLIPS.copy()
        
        # Normalize base odds
        total_odds = sum(self.base_clip_odds.values())
        if total_odds > 0:
            self.base_clip_odds = {k: v / total_odds for k, v in self.base_clip_odds.items()}
        
        # Extract all unique clip prefixes (from both emotion and base clips)
        all_prefixes = set(self.base_clip_odds.keys())
        for emotion_clips_dict in self.emotion_clip_mapping.values():
            all_prefixes.update(emotion_clips_dict.keys())
        self.available_prefixes = list(all_prefixes)
        
        self.avoid_repeats = avoid_repeats
        self.last_used_prefix = None
        
        # Now scan for clips (after available_prefixes is set)
        self.available_clips = self.scan_available_clips()
        
        print(f"{Fore.GREEN}[LIPSYNC] Enhanced emotional lip-sync initialized{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Archive directory: {archive_directory}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Transition duration: {self.TRANSITION_DURATION}s{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Found {len(self.available_clips)} clips{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Available prefixes: {self.available_prefixes}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Emotion groups: {list(self.emotion_clip_mapping.keys())}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Base clip odds: {self.base_clip_odds}{Style.RESET_ALL}")

    def _check_ffmpeg_availability(self):
        """Check if FFmpeg and FFprobe are available"""
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        
        if not ffmpeg_path:
            raise RuntimeError("FFmpeg not found in system PATH")
        if not ffprobe_path:
            raise RuntimeError("FFprobe not found in system PATH")
        
        print(f"{Fore.GREEN}[LIPSYNC] FFmpeg found at: {ffmpeg_path}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[LIPSYNC] FFprobe found at: {ffprobe_path}{Style.RESET_ALL}")

    def scan_available_clips(self) -> List[Dict]:
        """Scan archive directory for clips"""
        clips = []
        
        if not os.path.exists(self.archive_dir):
            print(f"{Fore.RED}[LIPSYNC] Archive directory not found: {self.archive_dir}{Style.RESET_ALL}")
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

    def get_emphasized_words(self, text: str) -> List[str]:
        """
        Detect emphasized words using spaCy linguistic features.
        Returns lowercase list of emphasized words.
        """
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
        
        print(f"{Fore.MAGENTA}[LIPSYNC] Emphasized words: {emphasized}{Style.RESET_ALL}")
        return emphasized

    def select_clip_for_word(self, word: str, emotion: str, emphasized_words: List[str]) -> Optional[Dict]:
        """
        Select clip based on:
        - If word is emphasized → use emotion-specific clips with emotion-specific odds
        - If word is not emphasized → use base clips with averaged odds
        """
        is_emphasized = word.lower() in emphasized_words
        
        if is_emphasized and emotion in self.emotion_clip_mapping:
            # Use emotion-specific clips and odds
            emotion_clips = self.emotion_clip_mapping[emotion]
            allowed_prefixes = list(emotion_clips.keys())
            print(f"{Fore.YELLOW}[LIPSYNC] '{word}' EMPHASIZED → {emotion} clips{Style.RESET_ALL}")
            
            # Get clips matching emotion prefixes
            suitable_clips = [
                clip for clip in self.available_clips 
                if clip['prefix'] in allowed_prefixes
            ]
            
            # Use emotion-specific weights
            weights = [emotion_clips.get(clip['prefix'], 0.5) for clip in suitable_clips]
        else:
            # Use all available clips with base odds
            suitable_clips = [
                clip for clip in self.available_clips 
                if clip['prefix'] in self.base_clip_odds
            ]
            
            # Use base weights
            weights = [self.base_clip_odds.get(clip['prefix'], 0.5) for clip in suitable_clips]
        
        # Fallback to all clips if none match
        if not suitable_clips:
            suitable_clips = self.available_clips
            weights = [1.0] * len(suitable_clips)
        
        # Normalize weights
        if sum(weights) == 0:
            weights = [1.0] * len(suitable_clips)
        
        selected = random.choices(suitable_clips, weights=weights, k=1)[0]
        return selected

    def get_next_output_filename(self, base_name: str, directory: str = ".", extension: str = ".mp4") -> str:
        """Generate unique output filename"""
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
            
            if counter > 999:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{base_name}_{timestamp}{extension}"
                return os.path.join(directory, filename)

    def get_audio_duration(self, audio_file: str) -> float:
        """Get audio duration using FFprobe"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            audio_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            print(f"{Fore.RED}[LIPSYNC] Error getting audio duration: {e}{Style.RESET_ALL}")
            return 0.0
        except (ValueError, FileNotFoundError) as e:
            print(f"{Fore.RED}[LIPSYNC] Error processing audio duration: {e}{Style.RESET_ALL}")
            return 0.0

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration using FFprobe"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Error getting video duration: {e}{Style.RESET_ALL}")
            return 0.0

    def select_random_clip(self) -> Optional[Dict]:
        """Select random clip using base odds (fallback method)"""
        available_for_selection = []
        
        for clip in self.available_clips:
            prefix = clip['prefix']
            if self.avoid_repeats and prefix == self.last_used_prefix:
                continue
            if prefix in self.base_clip_odds:
                available_for_selection.append(clip)
        
        if not available_for_selection:
            available_for_selection = self.available_clips
        
        if not available_for_selection:
            return None
        
        weights = [self.base_clip_odds.get(clip['prefix'], 0.5) for clip in available_for_selection]
        
        if sum(weights) == 0:
            weights = [1.0] * len(available_for_selection)
        
        selected_clip = random.choices(available_for_selection, weights=weights, k=1)[0]
        self.last_used_prefix = selected_clip['prefix']
        
        return selected_clip

    def generate_clip_sequence(self, audio_duration: float, text: str = "", emotion: str = "neutral") -> List[Dict]:
        """
        Generate clip sequence with emotion-based selection.
        If text provided, use emphasis detection for word-level selection.
        """
        clip_sequence = []
        effective_duration = 0.0
        
        # Get emphasized words if text is provided
        emphasized_words = self.get_emphasized_words(text) if text else []
        words = text.split() if text else []
        word_index = 0
        
        print(f"{Fore.CYAN}[LIPSYNC] Generating sequence for {len(words)} words, emotion: {emotion}{Style.RESET_ALL}")
        
        while effective_duration < audio_duration:
            # Select clip based on current word and emotion
            if words:
                current_word = words[word_index % len(words)]
                clip = self.select_clip_for_word(current_word, emotion, emphasized_words)
                word_index += 1
            else:
                # No text provided, use random selection
                clip = self.select_random_clip()
            
            if not clip:
                continue
            
            clip_real_duration = self.get_video_duration(clip['path'])
            
            if clip_real_duration > 0:
                if not clip_sequence:
                    duration_to_add = clip_real_duration
                else:
                    duration_to_add = clip_real_duration - self.TRANSITION_DURATION
                
                if duration_to_add > 0:
                    clip_sequence.append(clip)
                    effective_duration += duration_to_add
                else:
                    print(f"{Fore.YELLOW}[LIPSYNC] Skipping short clip: {clip['filename']}{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}[LIPSYNC] Skipping 0-duration clip: {clip['filename']}{Style.RESET_ALL}")
            
            # Safety break
            if words and word_index > len(words) * 3:
                break
        
        if not clip_sequence and self.available_clips:
            clip_sequence = [random.choice(self.available_clips)]
        
        print(f"{Fore.GREEN}[LIPSYNC] Generated {len(clip_sequence)} clips{Style.RESET_ALL}")
        return clip_sequence
    
    def create_video_sequence_with_fades(self, clip_sequence: List[Dict], audio_duration: float, temp_dir: str) -> str:
        """Create video with crossfades"""
        if not clip_sequence:
            print(f"{Fore.RED}[LIPSYNC] Empty clip sequence{Style.RESET_ALL}")
            return None

        print(f"{Fore.CYAN}[LIPSYNC] Creating video with crossfades (transition: {self.TRANSITION_DURATION}s){Style.RESET_ALL}")

        input_args = []
        clips_with_duration = []
        for clip_info in clip_sequence:
            path = clip_info['path']
            duration = self.get_video_duration(path)
            if duration > 0:
                clips_with_duration.append({'path': path, 'duration': duration})
                input_args.extend(["-i", path])

        if not clips_with_duration:
            print(f"{Fore.RED}[LIPSYNC] No valid clips with duration{Style.RESET_ALL}")
            return None

        num_clips = len(clips_with_duration)
        
        # Scale clips
        scaling_filters = []
        for i in range(num_clips):
            scaling_filters.append(
                f"[{i}:v]scale=720:480:force_original_aspect_ratio=increase,crop=720:480,format=yuv420p[s{i}]"
            )
        
        # Create crossfades
        if num_clips > 1:
            xfade_filters = []
            stream_specifier = "[s0]"
            total_duration = 0

            for i in range(num_clips - 1):
                clip_duration = clips_with_duration[i]['duration']
                fade_offset = total_duration + clip_duration - self.TRANSITION_DURATION
                next_stream_specifier = f"[s{i + 1}]"
                output_stream_name = f"[v{i + 1}]"
                
                xfade_filters.append(
                    f"{stream_specifier}{next_stream_specifier}"
                    f"xfade=transition=fade:duration={self.TRANSITION_DURATION}:offset={fade_offset}"
                    f"{output_stream_name}"
                )
                
                stream_specifier = output_stream_name
                total_duration += clip_duration - self.TRANSITION_DURATION
            
            final_filter_graph = ";".join(scaling_filters) + ";" + ";".join(xfade_filters)
            final_output_pad = stream_specifier
        else:
            final_filter_graph = scaling_filters[0]
            final_output_pad = "[s0]"

        print(f"{Fore.CYAN}[LIPSYNC] Generated filter graph for {num_clips} clips{Style.RESET_ALL}")

        final_video_path = os.path.join(temp_dir, "video_only.mp4")
        
        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend([
            "-filter_complex", final_filter_graph,
            "-map", final_output_pad,
            "-c:v", "libx264",
            "-t", str(audio_duration),
            final_video_path
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(final_video_path):
            print(f"{Fore.GREEN}[LIPSYNC] ✓ Video sequence created{Style.RESET_ALL}")
            return final_video_path
        else:
            print(f"{Fore.RED}[LIPSYNC] Error creating video. FFmpeg stderr:{Style.RESET_ALL}")
            print(result.stderr)
            return None

    def generate_lip_sync_video(self, audio_file: str, output_file: str = None, 
                                  output_dir: str = None, use_sequential: bool = True,
                                  text: str = "", emotion: str = "neutral") -> str:
        """
        Main function - generate lip-sync with emotion-based clip selection.
        
        Args:
            audio_file: Path to audio file
            output_file: Optional output path
            output_dir: Output directory
            use_sequential: Use sequential numbering
            text: Spoken text (for emphasis detection)
            emotion: Emotion category (neutral/emphatic/contrastive/positive/negative)
        """
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(audio_file))[0] + f"_lipsynced_{emotion}"
            if output_dir is None:
                output_dir = os.path.dirname(audio_file) or "."
            output_file = self.get_next_output_filename(base_name, output_dir, ".mp4") if use_sequential else os.path.join(output_dir, base_name + ".mp4")
        
        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}EMOTIONAL LIP-SYNC GENERATION{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Input audio: {audio_file}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Output video: {output_file}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Emotion: {emotion}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Text: {text[:80]}...{Style.RESET_ALL}" if len(text) > 80 else f"{Fore.CYAN}Text: {text}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Crossfade duration: {self.TRANSITION_DURATION}s{Style.RESET_ALL}")
        
        audio_duration = self.get_audio_duration(audio_file)
        if audio_duration <= 0:
            print(f"{Fore.RED}[LIPSYNC] Invalid audio duration{Style.RESET_ALL}")
            return None
        
        print(f"{Fore.CYAN}[LIPSYNC] Audio duration: {audio_duration:.2f}s{Style.RESET_ALL}")
        
        # Generate emotional clip sequence
        clip_sequence = self.generate_clip_sequence(audio_duration, text, emotion)
        if not clip_sequence:
            print(f"{Fore.RED}[LIPSYNC] Failed to generate clip sequence{Style.RESET_ALL}")
            return None
        
        print(f"{Fore.CYAN}[LIPSYNC] Generated sequence of {len(clip_sequence)} clips{Style.RESET_ALL}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"{Fore.CYAN}[LIPSYNC] Using temp directory: {temp_dir}{Style.RESET_ALL}")
            
            video_only_file = self.create_video_sequence_with_fades(
                clip_sequence, audio_duration, temp_dir
            )
            
            if not video_only_file:
                print(f"{Fore.RED}[LIPSYNC] Failed to create video sequence{Style.RESET_ALL}")
                return None
            
            print(f"{Fore.CYAN}[LIPSYNC] Combining video with audio...{Style.RESET_ALL}")
            final_cmd = [
                "ffmpeg", "-y",
                "-i", video_only_file,
                "-i", audio_file,
                "-c:v", "copy",
                "-c:a", "aac",
                output_file
            ]
            
            result = subprocess.run(final_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}✓ SUCCESS! Emotional lip-sync created:{Style.RESET_ALL}")
                print(f"{Fore.GREEN}  {output_file}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}  Emotion: {emotion}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}  Crossfade: {self.TRANSITION_DURATION}s{Style.RESET_ALL}")
                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                return output_file
            else:
                print(f"{Fore.RED}[LIPSYNC] Error combining video and audio:{Style.RESET_ALL}")
                print(result.stderr)
                return None


# Example usage
if __name__ == "__main__":
    ARCHIVE_DIR = "./archive"
    OUTPUT_DIR = "./output"
    AVOID_REPEATS = True
    TRANSITION_DURATION = 0.15
    
    # EMOTION-SPECIFIC CLIPS (for emphasized words)
    EMOTION_CLIP_CONFIG = {
        'neutral': {
            'idle2': 1.0,
            'slight_look1': 0.8,
            'eye_look1': 0.5
        },
        'emphatic': {
            'nod1': 1.0,
            'slight_shake1': 1.0,
            'slight_shake2': 0.7,
            'slight_shake7': 0.8
        },
        'contrastive': {
            'slight_shake7': 1.0,
            'look_down1': 0.8,
            'slight_lean3': 0.7
        },
        'positive': {
            'smirk1': 1.0,
            'slight_look1': 0.8,
            'nod1': 0.9
        },
        'negative': {
            'look_down1': 1.0,
            'slight_lean3': 0.9,
            'circle1': 0.5
        }
    }
    
    # BASE CLIPS (for non-emphasized words) - INDEPENDENT CONFIGURATION
    BASE_CLIP_CONFIG = {
        'idle2': 1.0,
        'slight_look1': 0.8,
        'eye_look1': 0.6,
        'circle1': 0.3,
        'slight_shake1': 0.5,
        'nod1': 0.4
    }
    
    print(f"{Fore.GREEN}STARTING EMOTIONAL LIP-SYNC SYSTEM{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")
    
    try:
        lipsync_system = SimplifiedLipSyncSystem(
            archive_directory=ARCHIVE_DIR,
            emotion_clips=EMOTION_CLIP_CONFIG,
            base_clips=BASE_CLIP_CONFIG,
            avoid_repeats=AVOID_REPEATS,
            transition_duration=TRANSITION_DURATION
        )
        
        input_audio_file = "evo2.wav"
        test_text = "The Beagle voyage was an amazing adventure!"
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