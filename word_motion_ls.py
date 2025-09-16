import os
import random
import librosa
import numpy as np
import subprocess
import speech_recognition as sr
from pydub import AudioSegment
import tempfile
import json

# Set FFmpeg path
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"

class LipSyncGenerator:
    def __init__(self, word_clips_dir="word_clips"):
        self.word_clips_dir = word_clips_dir
        self.ffmpeg_path = os.path.join(FFMPEG_BIN_PATH, "ffmpeg.exe")
        self.positions = ["main", "focus_in", "lean_in", "slight_tilt"]
        self.transitions = {
            "main": {
                "focus_in": "main2focus_in.mp4",
                "lean_in": "main2lean_in.mp4", 
                "slight_tilt": "main2slight-tilt.mp4"
            },
            "focus_in": {
                "main": "focus_in2main.mp4"
            },
            "lean_in": {
                "main": "lean_in2main.mp4"
            },
            "slight_tilt": {
                "main": "slight_tilt2main.mp4"
            }
        }
        
    def extract_text_from_audio(self, audio_path):
        """Extract text from audio using speech recognition"""
        r = sr.Recognizer()
        
        # Convert audio to wav if needed
        audio = AudioSegment.from_file(audio_path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            audio.export(temp_wav.name, format="wav")
            
            with sr.AudioFile(temp_wav.name) as source:
                audio_data = r.record(source)
                try:
                    text = r.recognize_google(audio_data)
                    return text.lower().split()
                except sr.UnknownValueError:
                    print("Could not understand audio")
                    return []
                except sr.RequestError as e:
                    print(f"Error with speech recognition: {e}")
                    return []
    
    def get_audio_duration(self, audio_path):
        """Get duration of audio file"""
        y, sr = librosa.load(audio_path)
        return librosa.get_duration(y=y, sr=sr)
    
    def get_video_duration(self, video_path):
        """Get duration of video file using ffprobe"""
        cmd = [
            os.path.join(FFMPEG_BIN_PATH, "ffprobe.exe"),
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration_str = result.stdout.strip()
            if duration_str == "N/A" or not duration_str:
                print(f"Warning: {video_path} has invalid duration, skipping...")
                return None  # Return None for invalid files
            return float(duration_str)
        except Exception as e:
            print(f"Error getting video duration for {video_path}: {e}")
            return None
    
    def find_word_clip(self, word, position="main"):
        """Find the video clip for a word in the specified position"""
        # Clean word of punctuation
        clean_word = ''.join(c for c in word if c.isalnum()).lower()
        
        # Handle special case for 'I' -> 'i' in main folder
        if clean_word == "i" and position == "main":
            clip_path = os.path.join(self.word_clips_dir, "main", "main_i.mp4")
        elif position == "main":
            clip_path = os.path.join(self.word_clips_dir, "main", f"main_{clean_word}.mp4")
        elif position == "focus_in":
            # Handle 'I' case for focus_in (stays uppercase in filename)
            if clean_word == "i":
                clip_path = os.path.join(self.word_clips_dir, "focus_in", "f1_I.mp4")
            else:
                clip_path = os.path.join(self.word_clips_dir, "focus_in", f"f1_{clean_word}.mp4")
        elif position == "lean_in":
            # Handle 'I' case for lean_in (stays uppercase in filename) 
            if clean_word == "i":
                clip_path = os.path.join(self.word_clips_dir, "lean_in", "l1_I.mp4")
            else:
                clip_path = os.path.join(self.word_clips_dir, "lean_in", f"l1_{clean_word}.mp4")
        elif position == "slight_tilt":
            # Handle 'I' case for slight_tilt (stays uppercase in filename)
            if clean_word == "i":
                clip_path = os.path.join(self.word_clips_dir, "slight_tilt", "slight_tilt_body_I.mp4")
            else:
                clip_path = os.path.join(self.word_clips_dir, "slight_tilt", f"slight_tilt_body_{clean_word}.mp4")
        
        if os.path.exists(clip_path):
            return clip_path
        
        # Fallback to main position if word not found in current position
        if position != "main":
            if clean_word == "i":
                main_clip = os.path.join(self.word_clips_dir, "main", "main_i.mp4")
            else:
                main_clip = os.path.join(self.word_clips_dir, "main", f"main_{clean_word}.mp4")
            if os.path.exists(main_clip):
                return main_clip
        
        # If still not found, try some common fallbacks that exist in your files
        fallbacks = ["the", "a", "and", "or", "but", "it", "that", "this", "we", "you", "he", "she"]
        for fallback in fallbacks:
            if position == "main":
                fallback_path = os.path.join(self.word_clips_dir, "main", f"main_{fallback}.mp4")
            elif position == "focus_in":
                fallback_path = os.path.join(self.word_clips_dir, "focus_in", f"f1_{fallback}.mp4")
            elif position == "lean_in":
                fallback_path = os.path.join(self.word_clips_dir, "lean_in", f"l1_{fallback}.mp4")
            elif position == "slight_tilt":
                fallback_path = os.path.join(self.word_clips_dir, "slight_tilt", f"slight_tilt_body_{fallback}.mp4")
            
            if os.path.exists(fallback_path):
                print(f"Using fallback {fallback} for word '{word}'")
                return fallback_path
                
        return None
    
    def get_transition_clip(self, from_pos, to_pos):
        """Get transition clip between positions"""
        if from_pos in self.transitions and to_pos in self.transitions[from_pos]:
            transition_filename = self.transitions[from_pos][to_pos]
            transition_path = os.path.join(self.word_clips_dir, "transitions", transition_filename)
            if os.path.exists(transition_path):
                return transition_path
        return None
    
    def plan_transitions(self, words):
        """Plan random transitions within sentences"""
        sentences = []
        current_sentence = []
        
        # Split into sentences (simple approach)
        for word in words:
            current_sentence.append(word)
            if word.endswith('.') or word.endswith('!') or word.endswith('?'):
                sentences.append(current_sentence)
                current_sentence = []
        
        if current_sentence:  # Add remaining words as a sentence
            sentences.append(current_sentence)
        
        planned_sequence = []
        current_position = "main"
        
        for sentence in sentences:
            if len(sentence) < 2:
                # Too short for transitions
                for word in sentence:
                    planned_sequence.append((word, current_position, None))
                continue
            
            # Decide number of transitions (1-3 per sentence)
            num_transitions = random.randint(1, min(3, len(sentence) // 2))
            transition_points = sorted(random.sample(range(1, len(sentence)), num_transitions))
            
            transition_idx = 0
            for i, word in enumerate(sentence):
                transition_clip = None
                
                # Check if this is a transition point
                if transition_idx < len(transition_points) and i == transition_points[transition_idx]:
                    # Choose new position (not current)
                    available_positions = [pos for pos in self.positions if pos != current_position]
                    new_position = random.choice(available_positions)
                    
                    # Get transition clip
                    transition_clip = self.get_transition_clip(current_position, new_position)
                    current_position = new_position
                    transition_idx += 1
                
                planned_sequence.append((word, current_position, transition_clip))
        
        return planned_sequence
    
    def create_ffmpeg_concat_file(self, video_clips, speed_factor):
        """Create FFmpeg concat file and speed-adjusted clips"""
        temp_dir = tempfile.mkdtemp()
        concat_file = os.path.join(temp_dir, "concat.txt")
        adjusted_clips = []
        
        print("Creating speed-adjusted clips...")
        
        with open(concat_file, 'w') as f:
            for i, clip_path in enumerate(video_clips):
                if clip_path and os.path.exists(clip_path):
                    # Create speed-adjusted version
                    adjusted_name = f"adjusted_{i}.mp4"
                    adjusted_path = os.path.join(temp_dir, adjusted_name)
                    
                    # Check if this is a transition clip
                    is_transition = "transition" in clip_path or any(trans in clip_path for trans in ["main2", "focus_in2", "lean_in2", "slight_tilt2"])
                    
                    print(f"Processing clip {i}: {os.path.basename(clip_path)} (transition: {is_transition})")
                    
                    # Check if clip has audio stream
                    has_audio_cmd = [
                        os.path.join(FFMPEG_BIN_PATH, "ffprobe.exe"),
                        "-v", "quiet",
                        "-select_streams", "a",
                        "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0",
                        clip_path
                    ]
                    
                    try:
                        audio_result = subprocess.run(has_audio_cmd, capture_output=True, text=True)
                        has_audio = "audio" in audio_result.stdout
                        print(f"  Has audio: {has_audio}")
                    except:
                        has_audio = False
                        print(f"  Could not detect audio")
                    
                    # FFmpeg command to adjust speed (handle video-only clips)
                    if has_audio:
                        cmd = [
                            self.ffmpeg_path,
                            "-i", clip_path,
                            "-filter:v", f"setpts={1/speed_factor}*PTS",
                            "-filter:a", f"atempo={speed_factor}",
                            "-y",  # Overwrite output
                            adjusted_path
                        ]
                    else:
                        # Video only - no audio filter
                        cmd = [
                            self.ffmpeg_path,
                            "-i", clip_path,
                            "-filter:v", f"setpts={1/speed_factor}*PTS",
                            "-an",  # No audio
                            "-y",  # Overwrite output
                            adjusted_path
                        ]
                    
                    print(f"  FFmpeg cmd: {' '.join(cmd)}")
                    
                    try:
                        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                        f.write(f"file '{adjusted_path}'\n")
                        adjusted_clips.append(adjusted_path)
                        print(f"  ✓ Speed adjusted successfully")
                    except subprocess.CalledProcessError as e:
                        print(f"  ✗ Error adjusting speed: {e}")
                        print(f"  ✗ FFmpeg stderr: {e.stderr if hasattr(e, 'stderr') else 'No stderr'}")
                        # Use original clip if speed adjustment fails
                        f.write(f"file '{clip_path}'\n")
                        adjusted_clips.append(clip_path)
        
        return concat_file, temp_dir, adjusted_clips
    
    def generate_lipsync_video(self, audio_path, output_path="output_lipsync.mp4"):
        """Main function to generate lip sync video"""
        print("Extracting text from audio...")
        words = self.extract_text_from_audio(audio_path)
        
        if not words:
            print("No words extracted from audio. Cannot proceed.")
            return
        
        print(f"Extracted words: {words}")
        
        # Get audio duration
        total_audio_duration = self.get_audio_duration(audio_path)
        print(f"Total audio duration: {total_audio_duration:.2f} seconds")
        
        # Plan transitions
        print("Planning transitions...")
        planned_sequence = self.plan_transitions(words)
        
        # Collect video clips
        video_clips = []
        clip_info = []  # Store detailed info for logging
        total_video_duration = 0
        
        print("Collecting video clips...")
        for word, position, transition_clip in planned_sequence:
            # Add transition clip if needed
            if transition_clip:
                if os.path.exists(transition_clip):
                    duration = self.get_video_duration(transition_clip)
                    if duration is not None:
                        video_clips.append(transition_clip)
                        total_video_duration += duration
                        clip_info.append(("TRANSITION", os.path.basename(transition_clip), duration, f"N/A -> {position}"))
                        print(f"Added transition: {os.path.basename(transition_clip)}")
                else:
                    print(f"Transition clip not found: {transition_clip}")
            
            # Add word clip
            word_clip_path = self.find_word_clip(word, position)
            if word_clip_path:
                duration = self.get_video_duration(word_clip_path)
                if duration is not None:  # Only add if duration is valid
                    video_clips.append(word_clip_path)
                    total_video_duration += duration
                    clip_info.append(("WORD", word, duration, position))
                    print(f"Added word: {word} ({position}) - {os.path.basename(word_clip_path)}")
                else:
                    print(f"Skipping corrupted file: {os.path.basename(word_clip_path)}")
            else:
                print(f"Warning: Could not find clip for word '{word}' in position '{position}'")
        
        if not video_clips:
            print("No video clips found. Cannot proceed.")
            return
        
        print(f"Total clips: {len(video_clips)}")
        print(f"Total video duration before adjustment: {total_video_duration:.2f} seconds")
        
        # Calculate speed factor
        speed_factor = total_video_duration / total_audio_duration
        print(f"Speed adjustment factor: {speed_factor:.3f}")
        
        # Create concat file and adjust speeds
        concat_file, temp_dir, adjusted_clips = self.create_ffmpeg_concat_file(video_clips, speed_factor)
        
        # Create temporary video without audio
        temp_video = os.path.join(temp_dir, "temp_video.mp4")
        print("Concatenating video clips...")
        
        cmd_concat = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            "-y",
            temp_video
        ]
        
        try:
            subprocess.run(cmd_concat, check=True, capture_output=True)
            print("Video clips concatenated successfully")
        except subprocess.CalledProcessError as e:
            print(f"Error concatenating videos: {e}")
            return
        
        # Combine with original audio
        print("Adding original audio...")
        cmd_audio = [
            self.ffmpeg_path,
            "-i", temp_video,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",  # Use shortest duration (should be same)
            "-y",
            output_path
        ]
        
        try:
            subprocess.run(cmd_audio, check=True, capture_output=True)
            print(f"Final video created: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error adding audio: {e}")
            return
        
        # Cleanup temporary files
        print("Cleaning up temporary files...")
        try:
            os.remove(concat_file)
            os.remove(temp_video)
            for clip in adjusted_clips:
                if os.path.exists(clip) and temp_dir in clip:
                    os.remove(clip)
            os.rmdir(temp_dir)
        except Exception as e:
            print(f"Warning: Could not clean up some temporary files: {e}")
        
        print(f"Lip sync video generated successfully: {output_path}")
        
        # Print detailed clip timing log
        print("\n=== DETAILED CLIP SEQUENCE ===")
        cumulative_time = 0
        for i, (clip_type, name, duration, position) in enumerate(clip_info):
            start_time = cumulative_time
            end_time = cumulative_time + (duration / speed_factor)  # Adjusted duration
            if clip_type == "TRANSITION":
                print(f"{i+1:2d}. {start_time:6.2f}s - {end_time:6.2f}s | TRANSITION: {name}")
            else:
                print(f"{i+1:2d}. {start_time:6.2f}s - {end_time:6.2f}s | WORD: '{name}' ({position})")
            cumulative_time = end_time
        
        # Print summary
        print("\n=== SUMMARY ===")
        print(f"Input audio duration: {total_audio_duration:.2f}s")
        print(f"Words processed: {len(words)}")
        print(f"Total clips used: {len(video_clips)}")
        print(f"  - Word clips: {len([c for c in clip_info if c[0] == 'WORD'])}")
        print(f"  - Transition clips: {len([c for c in clip_info if c[0] == 'TRANSITION'])}")
        print(f"Speed adjustment: {speed_factor:.3f}x")
        print(f"Output: {output_path}")

# Example usage
if __name__ == "__main__":
    # Initialize the generator
    generator = LipSyncGenerator("word_clips")
    
    # Process audio file
    audio_file = "t2.wav"  # Replace with your audio file path
    output_file = "lipsync_output18.mp4"
    
    if os.path.exists(audio_file):
        generator.generate_lipsync_video(audio_file, output_file)
    else:
        print(f"Audio file '{audio_file}' not found.")
        print("Please replace 'input_audio.wav' with the path to your audio file.")

# Dependencies needed:
# pip install librosa speechrecognition pydub