import os
import cv2
import numpy as np
import subprocess
import json
import tempfile
import shutil
# - MODIFIED: Import the standard whisper library instead of faster-whisper
import whisper 
import re
from pathlib import Path

# --- Path Configuration ---
# The script determines paths relative to its own location.
# / (root)
# |- scripts/
# |  |- lipsync_reworked.py (this file)
# |- word_clips/
# |  |- focus_in/
# |     |- focus_in_body_saw.mp4
# |     |- ...
# |- test_audio.wav (example input)
# |- lipsync_output.mp4 (example output)

try:
    SCRIPT_DIR = Path(__file__).resolve().parent
    ROOT_DIR = SCRIPT_DIR.parent
except NameError:
    # Fallback for interactive environments
    SCRIPT_DIR = Path.cwd()
    ROOT_DIR = SCRIPT_DIR.parent
    
import os
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"
os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")

class LipSyncGenerator:
    def __init__(self, video_clips_dir, ffmpeg_path, model_size="tiny"):
        """
        Initializes the LipSyncGenerator.
        :param video_clips_dir: Path to the directory containing word video clips.
        :param ffmpeg_path: Path to the directory containing ffmpeg.exe and ffprobe.exe.
        :param model_size: The size of the Whisper model to use.
        """
        self.video_clips_dir = video_clips_dir
        self.ffmpeg_executable = os.path.join(ffmpeg_path, 'ffmpeg')
        self.ffprobe_executable = os.path.join(ffmpeg_path, 'ffprobe')
        # - MODIFIED: Load the model using the standard whisper library.
        #   The 'compute_type' argument is not used in the standard library.
        self.model = whisper.load_model(model_size, device="cpu")
        self.available_clips = self._scan_available_clips()
        self.temp_dir = tempfile.mkdtemp()
        
    def _scan_available_clips(self):
        """Scan the video clips directory and create a mapping of available words."""
        clips_dict = {}
        if os.path.exists(self.video_clips_dir):
            for file in os.listdir(self.video_clips_dir):
                if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    base_name = os.path.splitext(file)[0]
                    # New logic: Extract word from 'prefix_word' format
                    try:
                        word = base_name.split('_')[-1].lower()
                        clips_dict[word] = os.path.join(self.video_clips_dir, file)
                    except IndexError:
                        print(f"Warning: Could not parse word from filename: {file}")
                        
        print(f"Found {len(clips_dict)} video clips. A few examples: {list(clips_dict.keys())[:5]}")
        return clips_dict
    
    # - MODIFIED: Use whisper's transcribe method and process its dictionary output
    def transcribe_audio(self, audio_file):
        """Transcribe audio and return word-level timestamps"""
        # The standard whisper transcribe function doesn't have a 'beam_size' parameter
        # and returns a single dictionary containing all information.
        result = self.model.transcribe(audio_file, word_timestamps=True)
        
        word_data = []
        # The transcription result is a dictionary, not a generator of segment objects.
        if 'segments' in result:
            for segment in result['segments']:
                # Each segment contains a list of word dictionaries.
                if 'words' in segment:
                    for word_info in segment['words']:
                        word_data.append({
                            # Access data using dictionary keys instead of object attributes.
                            'word': word_info['word'].strip().lower(),
                            'start': word_info['start'],
                            'end': word_info['end'],
                            'duration': word_info['end'] - word_info['start']
                        })
        
        print(f"Transcribed {len(word_data)} words from audio")
        # Return the raw result dictionary in place of the old 'info' object.
        return word_data, result
    
    def find_video_clip(self, word):
        """Find the best matching video clip for a word"""
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word in self.available_clips:
            return self.available_clips[clean_word]
        
        # Fallback for cases where a clip might be missing
        if self.available_clips:
            fallback_word = list(self.available_clips.keys())[0]
            fallback_path = self.available_clips[fallback_word]
            print(f"Warning: No clip found for '{word}'. Using fallback: '{fallback_word}'")
            return fallback_path
        
        return None
    
    def get_video_info(self, video_path):
        """Get video information using ffprobe"""
        cmd = [
            self.ffprobe_executable, '-v', 'quiet', '-print_format', 'json', 
            '-show_format', '-show_streams', video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            
            video_stream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
            if video_stream:
                fps = eval(video_stream.get('r_frame_rate', '25/1'))
                duration = float(video_stream.get('duration', 0))
                width = video_stream.get('width', 640)
                height = video_stream.get('height', 480)
                return {'fps': fps, 'duration': duration, 'width': width, 'height': height}
        except subprocess.CalledProcessError as e:
            print(f"Error getting video info for {video_path}: {e.stderr}")
        return {'fps': 25, 'duration': 1.0, 'width': 640, 'height': 480}
    
    def process_word_clip(self, word_data, clip_index, prev_clip_path=None):
        """Process a single word clip with speed adjustment"""
        word = word_data['word']
        target_duration = word_data['duration']
        
        clip_path = self.find_video_clip(word)
        if not clip_path:
            print(f"Error: No video clip available for word '{word}' and no fallback available.")
            return None
        
        video_info = self.get_video_info(clip_path)
        original_duration = video_info['duration']
        
        if original_duration == 0:
            print(f"Warning: Zero duration for clip '{clip_path}'")
            return None
        
        speed_factor = max(0.5, min(2.0, original_duration / target_duration))
        output_path = os.path.join(self.temp_dir, f"word_{clip_index:04d}.mp4")
        
        cmd = [
            self.ffmpeg_executable, '-y', '-i', clip_path,
            '-an',
            '-vf', f'setpts={1/speed_factor}*PTS',
            '-t', str(target_duration),
            '-c:v', 'libx264', '-preset', 'fast',
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Processed '{word}' (speed: {speed_factor:.2f}x, duration: {target_duration:.2f}s)")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"Error processing clip for word '{word}': {e.stderr}")
            return prev_clip_path if prev_clip_path else None
    
    def create_gap_clip(self, prev_clip_path, gap_duration, gap_index):
        """Create a clip to fill gaps using the previous word's clip"""
        if not prev_clip_path or not os.path.exists(prev_clip_path):
            return None
        
        output_path = os.path.join(self.temp_dir, f"gap_{gap_index:04d}.mp4")
        cmd = [
            self.ffmpeg_executable, '-y', '-stream_loop', '-1', '-i', prev_clip_path,
            '-t', str(gap_duration),
            '-an',
            '-c:v', 'libx264', '-preset', 'fast',
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Created gap clip: {gap_duration:.2f}s")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"Error creating gap clip: {e.stderr}")
            return None
    
    def create_video_list(self, word_data, total_duration):
        """Create processed video clips and gap fillers"""
        video_list = []
        current_time = 0
        prev_clip_path = None
        clip_counter = 0
        gap_counter = 0
        
        for i, word_info in enumerate(word_data):
            word_start = word_info['start']
            word_end = word_info['end']
            
            if word_start > current_time:
                gap_duration = word_start - current_time
                if gap_duration > 0.05 and prev_clip_path:
                    gap_clip = self.create_gap_clip(prev_clip_path, gap_duration, gap_counter)
                    if gap_clip:
                        video_list.append(gap_clip)
                        gap_counter += 1
            
            word_clip = self.process_word_clip(word_info, clip_counter, prev_clip_path)
            if word_clip:
                video_list.append(word_clip)
                prev_clip_path = word_clip
                clip_counter += 1
            
            current_time = word_end
        
        if current_time < total_duration:
            gap_duration = total_duration - current_time
            if gap_duration > 0.05 and prev_clip_path:
                gap_clip = self.create_gap_clip(prev_clip_path, gap_duration, gap_counter)
                if gap_clip:
                    video_list.append(gap_clip)
        
        return video_list
    
    def concatenate_videos(self, video_list, output_path):
        """Concatenate all video clips using FFmpeg"""
        if not video_list:
            print("Error: No video clips to concatenate")
            return False
        
        concat_file = os.path.join(self.temp_dir, "concat_list.txt")
        with open(concat_file, 'w') as f:
            for video_path in video_list:
                f.write(f"file '{Path(video_path).as_posix()}'\n")
        
        cmd = [
            self.ffmpeg_executable, '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("Video concatenation completed")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error concatenating videos: {e.stderr}")
            return False
    
    def add_audio_to_video(self, video_path, audio_path, final_output_path):
        """Add original audio to the concatenated video"""
        cmd = [
            self.ffmpeg_executable, '-y', '-i', video_path, '-i', audio_path,
            '-c:v', 'copy', '-c:a', 'aac', '-strict', 'experimental',
            '-shortest',
            final_output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("Audio added to video successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error adding audio to video: {e.stderr}")
            return False
    
    def cleanup(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print("Temporary files cleaned up")
    
    def generate_lipsync_video(self, audio_file, output_file="lipsync_output.mp4"):
        """Main function to generate the lip-synced video"""
        print("Starting lip-sync video generation...")
        
        try:
            print("Step 1: Transcribing audio...")
            word_data, audio_info = self.transcribe_audio(audio_file)
            if not word_data:
                print("Error: No words found in audio transcription")
                return False
            
            audio_info_cmd = [self.ffprobe_executable, '-v', 'quiet', '-print_format', 'json', '-show_format', audio_file]
            result = subprocess.run(audio_info_cmd, capture_output=True, text=True, check=True)
            audio_duration = float(json.loads(result.stdout)['format']['duration'])
            
            print("Step 2: Processing video clips...")
            video_list = self.create_video_list(word_data, audio_duration)
            if not video_list:
                print("Error: No video clips could be created")
                return False
            
            print("Step 3: Concatenating video clips...")
            temp_video = os.path.join(self.temp_dir, "concatenated.mp4")
            if not self.concatenate_videos(video_list, temp_video):
                return False
            
            print("Step 4: Adding original audio...")
            # Ensure unique output filename by appending a number if needed
            base, ext = os.path.splitext(output_file)
            counter = 1
            final_output_file = output_file
            while os.path.exists(final_output_file):
                final_output_file = f"{base}_{counter}{ext}"
                counter += 1

            success = self.add_audio_to_video(temp_video, audio_file, final_output_file)    
            
            print(f"Lip-sync video {'successfully created' if success else 'creation failed'}: {output_file}")
            return success
            
        except Exception as e:
            print(f"An unexpected error occurred during video generation: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.cleanup()

def main():
    # --- CONFIGURATION ---
    FFMPEG_BIN_PATH = r"C:\ffmpeg\bin" # Path to your ffmpeg bin directory
    WORD_CLIPS_PATH = ROOT_DIR / "word_clips" / "focus_in"
    
    # Input audio file (should be in the root directory)
    audio_file = ROOT_DIR / "tempstream" / "t1s.wav"
    
    # Final output video file (will be saved in the root directory)
    output_file = ROOT_DIR / "lipsync_output.mp4"
    
    # --- CHECKS ---
    if not os.path.exists(FFMPEG_BIN_PATH):
        print(f"Error: FFmpeg path not found: '{FFMPEG_BIN_PATH}'")
        print("Please install FFmpeg and update the FFMPEG_BIN_PATH variable.")
        return

    if not os.path.exists(WORD_CLIPS_PATH):
        print(f"Error: Word clips directory not found: '{WORD_CLIPS_PATH}'")
        return
        
    if not os.path.exists(audio_file):
        print(f"Error: Audio file not found: '{audio_file}'")
        print("Please place your input audio file in the root directory and name it 'test_audio.wav' or update the 'audio_file' variable.")
        return

    # --- EXECUTION ---
    print(f"Using Script Directory: {SCRIPT_DIR}")
    print(f"Using Root Directory:   {ROOT_DIR}")
    print(f"Using Word Clips From:  {WORD_CLIPS_PATH}")
    print(f"Using Audio File:       {audio_file}")
    print(f"Outputting Video To:    {output_file}")
    print("-" * 20)

    generator = LipSyncGenerator(
        video_clips_dir=str(WORD_CLIPS_PATH),
        ffmpeg_path=FFMPEG_BIN_PATH
    )
    
    success = generator.generate_lipsync_video(str(audio_file), str(output_file))
    
    if success:
        print("\nLip-sync video generation completed successfully!")
    else:
        print("\nLip-sync video generation failed!")

if __name__ == "__main__":
    main()