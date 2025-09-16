# Simplified Audio-to-Video Lip Sync System - PATH-based FFmpeg
# Evenly distributes clips across audio duration without word alignment

import os
import json
import random
import subprocess
import shutil
from pathlib import Path
import tempfile
from typing import List, Dict, Optional
from datetime import datetime

class SimplifiedLipSyncSystem:
    def __init__(self, archive_directory: str, clip_odds: Dict[str, float] = None, 
                 avoid_repeats: bool = False):
        self.archive_dir = archive_directory
        
        # Check if FFmpeg is available in PATH
        self._check_ffmpeg_availability()
        
        # Available clip prefixes from your archive
        # These are the ACTUAL prefixes in your filenames
        self.available_prefixes = [
            "circle1", "eye_look1", "idle2", "slight_look1", "slight_shake1","nod1", "slight_shake2"
        ]
        
        # Set up clip odds (probability weights for each prefix)
        if clip_odds is None:
            self.clip_odds = {
            "circle1": 0.5,
            "eye_look1": 0.5,
            "idle2": 1.0,
            "slight_look1": 1.0,
            "slight_shake1": 1,
            "slight_shake2": 1.0,  # Added
            "nod1": 1.0,           # Added
            "main2": 1.0, 
        }
        else:
            self.clip_odds = clip_odds
        
        # Normalize odds
        total_odds = sum(self.clip_odds.values())
        if total_odds > 0:
            self.clip_odds = {k: v/total_odds for k, v in self.clip_odds.items()}
        
        self.avoid_repeats = avoid_repeats
        self.last_used_prefix = None
        
        # Build list of all available clips
        self.available_clips = self.scan_available_clips()
        
        # Print debug info about what was found
        print(f"Simplified lip sync system initialized")
        print(f"Archive directory: {archive_directory}")
        print(f"Found {len(self.available_clips)} available clips")
        
        # Debug: Show distribution of clips by prefix
        prefix_counts = {}
        for clip in self.available_clips:
            prefix = clip['prefix']
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
        print(f"Clip distribution by prefix: {prefix_counts}")
        
        print(f"Clip odds configured: {self.clip_odds}")
        print(f"Avoid repeats: {self.avoid_repeats}")

    def _check_ffmpeg_availability(self):
        """Check if FFmpeg and FFprobe are available in system PATH"""
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        
        if not ffmpeg_path:
            raise RuntimeError(
                "FFmpeg not found in system PATH. Please install FFmpeg and ensure it's "
                "added to your system PATH, or install it using:\n"
                "- Windows: Download from https://ffmpeg.org/download.html or use 'winget install ffmpeg'\n"
                "- macOS: brew install ffmpeg\n"
                "- Linux: sudo apt install ffmpeg (Ubuntu/Debian) or sudo yum install ffmpeg (RHEL/CentOS)"
            )
        
        if not ffprobe_path:
            raise RuntimeError(
                "FFprobe not found in system PATH. FFprobe should be included with FFmpeg installation."
            )
        
        print(f"FFmpeg found at: {ffmpeg_path}")
        print(f"FFprobe found at: {ffprobe_path}")

    def scan_available_clips(self) -> List[Dict]:
        """Scan archive directory for all available clips"""
        clips = []
        
        if not os.path.exists(self.archive_dir):
            print(f"Warning: Archive directory not found: {self.archive_dir}")
            return clips
        
        for file in os.listdir(self.archive_dir):
            if file.endswith('.mp4'):
                # Better prefix detection
                # Check which prefix this file starts with
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
        
        # Add idle clip if exists (special case without underscore)
        idle_path = os.path.join(self.archive_dir, "idle0.mp4")
        if os.path.exists(idle_path):
            clips.append({
                'filename': 'idle0.mp4',
                'path': idle_path,
                'prefix': 'idle'
            })
        
        return clips

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

    def get_audio_duration(self, audio_file: str) -> float:
        """Get the duration of an audio file using FFprobe from PATH"""
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
            print(f"Error getting audio duration for {audio_file}: {e}")
            return 0.0
        except (ValueError, FileNotFoundError) as e:
            print(f"Error processing audio duration for {audio_file}: {e}")
            return 0.0

    def get_video_duration(self, video_path: str) -> float:
        """Get the duration of a video file using FFprobe from PATH"""
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
        except:
            return 1.0

    def select_random_clip(self) -> Dict:
        """Select a random clip based on configured odds and repeat avoidance"""
        # Filter clips by prefix odds
        available_for_selection = []
        
        for clip in self.available_clips:
            prefix = clip['prefix']
            # Skip if avoiding repeats and this was just used
            if self.avoid_repeats and prefix == self.last_used_prefix:
                continue
            # Add clip if its prefix has non-zero odds
            if prefix in self.clip_odds or prefix == 'idle':
                available_for_selection.append(clip)
        
        # If no clips available (due to repeat avoidance), use all clips
        if not available_for_selection:
            available_for_selection = self.available_clips
        
        if not available_for_selection:
            return None
        
        # Calculate weights based on prefix odds
        weights = []
        for clip in available_for_selection:
            prefix = clip['prefix']
            weight = self.clip_odds.get(prefix, 0.5)  # Default weight for idle
            weights.append(weight)
        
        # Normalize weights if all are zero
        if sum(weights) == 0:
            weights = [1.0] * len(available_for_selection)
        
        # Select clip based on weights
        selected_clip = random.choices(available_for_selection, weights=weights, k=1)[0]
        self.last_used_prefix = selected_clip['prefix']
        
        return selected_clip

    def generate_clip_sequence(self, audio_duration: float, target_clips: int = None) -> List[Dict]:
        """Generate a sequence of clips to fill the audio duration"""
        if target_clips is None:
            # Estimate based on average clip duration of 0.5 seconds
            target_clips = max(1, int(audio_duration / 0.5))
        
        clip_sequence = []
        
        for i in range(target_clips):
            clip = self.select_random_clip()
            if clip:
                clip_sequence.append(clip)
        
        # If no clips were selected, use a fallback
        if not clip_sequence and self.available_clips:
            clip_sequence = [random.choice(self.available_clips)]
        
        return clip_sequence

    def create_video_sequence(self, clip_sequence: List[Dict], audio_duration: float, temp_dir: str) -> str:
        """Create video sequence by evenly distributing clips across audio duration"""
        if not clip_sequence:
            return None
        
        num_clips = len(clip_sequence)
        target_duration_per_clip = audio_duration / num_clips
        
        print(f"\nCreating video sequence:")
        print(f"  Audio duration: {audio_duration:.2f}s")
        print(f"  Number of clips: {num_clips}")
        print(f"  Target duration per clip: {target_duration_per_clip:.3f}s")
        
        # Process each clip
        processed_clips = []
        
        for i, clip_info in enumerate(clip_sequence):
            clip_path = clip_info['path']
            original_duration = self.get_video_duration(clip_path)
            
            # Calculate speed adjustment to match target duration
            if original_duration > 0:
                speed_factor = original_duration / target_duration_per_clip
            else:
                speed_factor = 1.0
            
            # Create adjusted clip
            temp_clip = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
            
            # Build ffmpeg command with speed adjustment using FFmpeg from PATH
            cmd = [
                "ffmpeg", "-y",
                "-i", clip_path,
                "-vf", f"scale=720:480:force_original_aspect_ratio=increase,crop=720:480,setpts=PTS*{speed_factor}",
                "-t", str(target_duration_per_clip),
                "-c:v", "libx264",
                "-an",
                temp_clip
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(temp_clip):
                processed_clips.append(temp_clip)
                print(f"  [{i+1}/{num_clips}] {clip_info['filename']} → {target_duration_per_clip:.3f}s (speed: {1/speed_factor:.2f}x)")
            else:
                print(f"  Warning: Failed to process clip {i}: {clip_info['filename']}")
                if result.stderr:
                    print(f"    FFmpeg error: {result.stderr}")
        
        if not processed_clips:
            print("Error: No clips were successfully processed")
            return None
        
        # Create concat file
        concat_file = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_file, 'w') as f:
            for clip_path in processed_clips:
                f.write(f"file '{clip_path}'\n")
        
        # Debug: Print concat file contents
        print(f"\n  Concat file created with {len(processed_clips)} clips")
        
        # Concatenate all clips using FFmpeg from PATH
        final_video = os.path.join(temp_dir, "video_only.mp4")
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            final_video
        ]
        
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(final_video):
            print(f"  ✓ Video sequence created successfully")
            return final_video
        else:
            print(f"  Error concatenating clips: {result.stderr}")
            return None

    def generate_lip_sync_video(self, audio_file: str, output_file: str = None, 
                               output_dir: str = None, use_sequential: bool = True,
                               target_clips: int = None) -> str:
        """
        Main function to generate lip-synced video from audio
        Evenly distributes random clips across the audio duration
        
        Args:
            audio_file: Path to input audio file
            output_file: Optional specific output path
            output_dir: Optional output directory
            use_sequential: Whether to use sequential numbering for output
            target_clips: Optional number of clips to use (auto-calculated if None)
        """
        # Determine output path
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(audio_file))[0] + "_lipsynced"
            
            if output_dir is None:
                output_dir = os.path.dirname(audio_file) or "."
            
            if use_sequential:
                output_file = self.get_next_output_filename(base_name, output_dir, ".mp4")
            else:
                output_file = os.path.join(output_dir, base_name + ".mp4")
        
        print(f"\n{'='*60}")
        print(f"SIMPLIFIED LIP SYNC GENERATION")
        print(f"{'='*60}")
        print(f"Input audio: {audio_file}")
        print(f"Output will be saved as: {output_file}")
        
        # Get audio duration
        audio_duration = self.get_audio_duration(audio_file)
        if audio_duration <= 0:
            print("Error: Could not determine audio duration")
            return None
        
        print(f"Audio duration: {audio_duration:.2f} seconds")
        
        # Generate clip sequence
        clip_sequence = self.generate_clip_sequence(audio_duration, target_clips)
        
        if not clip_sequence:
            print("Error: Could not generate clip sequence")
            return None
        
        print(f"\nGenerated sequence of {len(clip_sequence)} clips:")
        
        # Show distribution in the sequence
        sequence_counts = {}
        for i, clip in enumerate(clip_sequence):
            prefix = clip['prefix']
            sequence_counts[prefix] = sequence_counts.get(prefix, 0) + 1
            print(f"  {i+1}. {clip['filename']} [{prefix}]")
        
        print(f"\nSequence distribution: {sequence_counts}")
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            print("\nProcessing video clips...")
            
            # Create video sequence
            video_file = self.create_video_sequence(clip_sequence, audio_duration, temp_dir)
            
            if not video_file:
                print("Error: Failed to create video sequence")
                return None
            
            print("\nCombining video with audio...")
            
            # Combine with audio using FFmpeg from PATH
            final_cmd = [
                "ffmpeg", "-y",
                "-i", video_file,
                "-i", audio_file,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",  # Use shortest stream duration
                output_file
            ]
            
            result = subprocess.run(final_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"\n{'='*60}")
                print(f"✓ SUCCESS! Lip sync video created:")
                print(f"  {output_file}")
                print(f"{'='*60}")
                return output_file
            else:
                print(f"Error combining video and audio: {result.stderr}")
                return None


# Example usage
if __name__ == "__main__":
    # Configuration
    ARCHIVE_DIR = "./archive"
    OUTPUT_DIR = "./output"
    
    # Clip selection odds (higher = more likely to be selected)
    CLIP_ODDS = {
        "circle1": 0,  # bad
        "eye_look1": 0.5,
        "idle2": 1.0,
        "slight_look1": 1.0,
        "slight_shake1": 1,
        "slight_shake2": 0.1,  # Added
        "nod1": 0,     # very bad, redo
        "main2": 1.0, 
    }
    
    AVOID_REPEATS = True  # Avoid using same prefix consecutively
    
    print("SIMPLIFIED LIP SYNC SYSTEM")
    print("=" * 60)
    print("This system evenly distributes clips across audio duration")
    print("No word alignment needed - much faster processing!")
    print()
    
    try:
        # Initialize system
        lipsync = SimplifiedLipSyncSystem(
            ARCHIVE_DIR,
            clip_odds=CLIP_ODDS,
            avoid_repeats=AVOID_REPEATS
        )
        
        # Process audio file
        test_audio = "evo.wav"  # Replace with your audio file
        
        if os.path.exists(test_audio):
            # Generate video with automatic clip count
            output_video = lipsync.generate_lip_sync_video(
                test_audio,
                output_dir=OUTPUT_DIR,
                use_sequential=True,
                target_clips=None  # Auto-calculate based on duration
            )
            
            # Or specify exact number of clips to use:
            # output_video = lipsync.generate_lip_sync_video(
            #     test_audio,
            #     output_dir=OUTPUT_DIR,
            #     use_sequential=True,
            #     target_clips=20  # Use exactly 20 clips
            # )
            
        else:
            print(f"Error: Audio file not found: {test_audio}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()