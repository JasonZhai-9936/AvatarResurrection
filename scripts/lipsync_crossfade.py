# Simplified Audio-to-Video Lip Sync System - CROSSFADE VERSION with PATH-based FFmpeg
# Preserves natural clip speed and adds smooth transitions

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
                 avoid_repeats: bool = False, transition_duration: float = 0.1):
        self.archive_dir = archive_directory
        
        # Set the global transition duration for all crossfades
        self.TRANSITION_DURATION = transition_duration
        
        # Check if FFmpeg is available in PATH
        self._check_ffmpeg_availability()
        
        # Available clip prefixes from your archive
        # These are the ACTUAL prefixes in your filenames
        self.available_prefixes = [
            "circle1", "eye_look1", "idle2", "slight_look1", "slight_shake1", "nod1", "slight_shake2"
        ]
        
        # Set up clip odds (probability weights for each prefix)
        if clip_odds is None:
            self.clip_odds = {
                "circle1": 0.5,
                "eye_look1": 0.5,
                "idle2": 1.0,
                "slight_look1": 1.0,
                "slight_shake1": 1.0,
                "slight_shake2": 1.0,
                "nod1": 1.0,
                "main2": 1.0,
            }
        else:
            self.clip_odds = clip_odds
        
        # Normalize odds
        total_odds = sum(self.clip_odds.values())
        if total_odds > 0:
            self.clip_odds = {k: v / total_odds for k, v in self.clip_odds.items()}
        
        self.avoid_repeats = avoid_repeats
        self.last_used_prefix = None
        
        # Build list of all available clips
        self.available_clips = self.scan_available_clips()
        
        # Print debug info about what was found
        print(f"Simplified lip sync system initialized")
        print(f"Archive directory: {archive_directory}")
        print(f"Transition duration: {self.TRANSITION_DURATION}s")
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
            
            if counter > 999:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{base_name}_{timestamp}{extension}"
                return os.path.join(directory, filename)

    def get_audio_duration(self, audio_file: str) -> float:
        """Get the duration of an audio file using FFprobe from PATH."""
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
        """Get the duration of a video file using FFprobe from PATH."""
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
            print(f"Error getting video duration for {video_path}: {e}")
            return 0.0

    def select_random_clip(self) -> Optional[Dict]:
        """Select a random clip based on configured odds and repeat avoidance."""
        available_for_selection = []
        
        for clip in self.available_clips:
            prefix = clip['prefix']
            if self.avoid_repeats and prefix == self.last_used_prefix:
                continue
            if prefix in self.clip_odds or prefix == 'idle':
                available_for_selection.append(clip)
        
        if not available_for_selection:
            available_for_selection = self.available_clips
        
        if not available_for_selection:
            return None
        
        weights = [self.clip_odds.get(clip['prefix'], 0.5) for clip in available_for_selection]
        
        if sum(weights) == 0:
            weights = [1.0] * len(available_for_selection)
        
        selected_clip = random.choices(available_for_selection, weights=weights, k=1)[0]
        self.last_used_prefix = selected_clip['prefix']
        
        return selected_clip

    def generate_clip_sequence(self, audio_duration: float) -> List[Dict]:
        """
        Generate a sequence of clips to fill the audio duration.
        Plays clips at their natural speed.
        """
        clip_sequence = []
        current_duration = 0.0

        # Fill the duration by adding clips one by one
        while current_duration < audio_duration:
            clip = self.select_random_clip()
            if not clip:
                continue  # Try again if no clip was selected

            # Get the clip's real duration to add to our total
            clip_real_duration = self.get_video_duration(clip['path'])

            if clip_real_duration > 0:
                clip_sequence.append(clip)
                current_duration += clip_real_duration
            else:
                print(f"Warning: Skipping clip with 0 duration: {clip['filename']}")

        # If no clips were selected, use a fallback
        if not clip_sequence and self.available_clips:
            clip_sequence = [random.choice(self.available_clips)]

        return clip_sequence

    def create_video_sequence_with_fades(self, clip_sequence: List[Dict], audio_duration: float, temp_dir: str) -> str:
        """
        Create a video sequence using crossfades for smooth transitions.
        Uses the class-level TRANSITION_DURATION for all crossfades.
        This version FIXES resolution mismatches by scaling clips BEFORE fading.
        """
        if not clip_sequence:
            print("Error: Clip sequence is empty.")
            return None

        print(f"\nCreating video sequence with crossfades:")
        print(f"  Transition duration: {self.TRANSITION_DURATION}s")

        input_args = []
        clips_with_duration = []
        for clip_info in clip_sequence:
            path = clip_info['path']
            duration = self.get_video_duration(path)
            if duration > 0:
                clips_with_duration.append({'path': path, 'duration': duration})
                input_args.extend(["-i", path])

        if not clips_with_duration:
            print("Error: None of the selected clips have a valid duration.")
            return None

        num_clips = len(clips_with_duration)
        
        # --- Step 1: Create filter strings to scale each input clip first ---
        # This is the crucial fix. We create standardized streams named [s0], [s1], etc.
        scaling_filters = []
        for i in range(num_clips):
            scaling_filters.append(
                f"[{i}:v]scale=720:480:force_original_aspect_ratio=increase,crop=720:480,format=yuv420p[s{i}]"
            )
        
        # --- Step 2: Chain the scaled streams together with xfade ---
        if num_clips > 1:
            xfade_filters = []
            stream_specifier = "[s0]" # Start with the first SCALED stream
            total_duration = 0

            for i in range(num_clips - 1):
                clip_duration = clips_with_duration[i]['duration']
                fade_offset = total_duration + clip_duration - self.TRANSITION_DURATION  # Use class variable
                next_stream_specifier = f"[s{i + 1}]" # Use the next SCALED stream
                output_stream_name = f"[v{i + 1}]"
                
                xfade_filters.append(
                    f"{stream_specifier}{next_stream_specifier}"
                    f"xfade=transition=fade:duration={self.TRANSITION_DURATION}:offset={fade_offset}"  # Use class variable
                    f"{output_stream_name}"
                )
                
                stream_specifier = output_stream_name
                total_duration += clip_duration - self.TRANSITION_DURATION  # Use class variable
            
            # Combine scaling and fading filters into one graph
            final_filter_graph = ";".join(scaling_filters) + ";" + ";".join(xfade_filters)
            final_output_pad = stream_specifier # The output of the last fade
        else:
            # If there's only one clip, we just need to scale it.
            final_filter_graph = scaling_filters[0]
            final_output_pad = "[s0]"

        print(f"  Generated filter graph for {num_clips} clip(s).")

        # --- Step 3: Execute the FFmpeg command using FFmpeg from PATH ---
        final_video_path = os.path.join(temp_dir, "video_only.mp4")
        
        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend([
            "-filter_complex", final_filter_graph,
            "-map", final_output_pad,
            "-c:v", "libx264",
            "-t", str(audio_duration), # Trim final video to audio length
            final_video_path
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(final_video_path):
            print(f"  ✓ Video sequence with fades created successfully.")
            return final_video_path
        else:
            print(f"  Error creating faded sequence. FFmpeg stderr:")
            print(result.stderr)
            return None

    def generate_lip_sync_video(self, audio_file: str, output_file: str = None, 
                                  output_dir: str = None, use_sequential: bool = True) -> str:
        """
        Main function to generate a lip-synced video from an audio file.
        Uses the class-level TRANSITION_DURATION for crossfades.
        """
        if output_file is None:
            base_name = os.path.splitext(os.path.basename(audio_file))[0] + "_lipsynced"
            if output_dir is None:
                output_dir = os.path.dirname(audio_file) or "."
            output_file = self.get_next_output_filename(base_name, output_dir, ".mp4") if use_sequential else os.path.join(output_dir, base_name + ".mp4")
        
        print(f"\n{'='*60}")
        print(f"LIP SYNC GENERATION (CROSSFADE VERSION)")
        print(f"{'='*60}")
        print(f"Input audio: {audio_file}")
        print(f"Output video: {output_file}")
        print(f"Crossfade duration: {self.TRANSITION_DURATION}s")
        
        audio_duration = self.get_audio_duration(audio_file)
        if audio_duration <= 0:
            print("Error: Could not determine audio duration or duration is zero.")
            return None
        
        print(f"Audio duration: {audio_duration:.2f} seconds")
        
        clip_sequence = self.generate_clip_sequence(audio_duration)
        if not clip_sequence:
            print("Error: Could not generate clip sequence.")
            return None
        
        print(f"\nGenerated sequence of {len(clip_sequence)} clips to fill the duration.")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Using temporary directory: {temp_dir}")
            
            video_only_file = self.create_video_sequence_with_fades(
                clip_sequence, audio_duration, temp_dir
            )
            
            if not video_only_file:
                print("Error: Failed to create the video-only sequence.")
                return None
            
            print("\nCombining final video with audio...")
            final_cmd = [
                "ffmpeg", "-y",
                "-i", video_only_file,
                "-i", audio_file,
                "-c:v", "copy", # No need to re-encode the video
                "-c:a", "aac",
                output_file
            ]
            
            result = subprocess.run(final_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"\n{'='*60}")
                print(f"✓ SUCCESS! Lip sync video created:")
                print(f"  {output_file}")
                print(f"  Crossfade duration used: {self.TRANSITION_DURATION}s")
                print(f"{'='*60}")
                return output_file
            else:
                print(f"Error combining video and audio. FFmpeg stderr:")
                print(result.stderr)
                return None

# ==============================================================================
#                               EXAMPLE USAGE
# ==============================================================================
if __name__ == "__main__":
    # --- Main Configuration ---
    ARCHIVE_DIR = "./archive" # Folder containing your .mp4 clips
    OUTPUT_DIR = "./output"   # Folder where final videos will be saved
    AVOID_REPEATS = True      # Avoid using the same clip prefix back-to-back
    TRANSITION_DURATION = 0.15 # Duration of ALL crossfades in seconds (centrally controlled)

    # Clip selection odds (higher number = more likely to be selected)
    CLIP_ODDS = {
        "circle1": 0.5,
        "eye_look1": 0.5,
        "idle2": 1.0,
        "slight_look1": 1.0,
        "slight_shake1": 1.0,
        "slight_shake2": 1.0,
        "nod1": 1.0,
        "main2": 1.0,
    }
    
    print("STARTING LIP SYNC SYSTEM")
    print("-" * 60)
    
    try:
        # Initialize the system with your configuration - NOW WITH CENTRALIZED TRANSITION DURATION
        lipsync_system = SimplifiedLipSyncSystem(
            archive_directory=ARCHIVE_DIR,
            clip_odds=CLIP_ODDS,
            avoid_repeats=AVOID_REPEATS,
            transition_duration=TRANSITION_DURATION  # This controls ALL crossfades
        )
        
        # Specify the audio file you want to process
        input_audio_file = "evo.wav" # <-- IMPORTANT: CHANGE THIS TO YOUR AUDIO FILE
        
        if os.path.exists(input_audio_file):
            # Generate the video - no need to pass transition_duration again
            output_video_path = lipsync_system.generate_lip_sync_video(
                audio_file=input_audio_file,
                output_dir=OUTPUT_DIR,
                use_sequential=True
            )
            
            if output_video_path:
                print(f"\nProcess finished. Output is at: {output_video_path}")
            else:
                print("\nProcess failed. Please check the error messages above.")
        else:
            print(f"Error: Input audio file not found at '{input_audio_file}'")
            print("Please make sure the file exists in the same directory as the script, or provide a full path.")
            
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()