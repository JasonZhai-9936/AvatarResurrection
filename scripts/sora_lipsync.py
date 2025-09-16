import os
import re
import random
import whisper
import subprocess
from pathlib import Path
import json
from typing import List, Dict, Tuple
import nltk
from nltk.corpus import cmudict
import tempfile

# Download required NLTK data
try:
    nltk.data.find('corpora/cmudict')
except LookupError:
    nltk.download('cmudict')

# Ensure ffmpeg is available
FFMPEG_BIN_PATH = r"C:\ffmpeg\bin"
os.environ["PATH"] = FFMPEG_BIN_PATH + os.pathsep + os.environ.get("PATH", "")

class LipSyncSystem:
    def __init__(self, clips_folder_path: str):
        self.clips_folder = Path(clips_folder_path)
        self.model = whisper.load_model("tiny")
        self.pronunciation_dict = cmudict.dict()
        self.available_clips = self._scan_clips_folder()
        
        # Configuration settings
        self.config = {
            'sentence_pause_duration': 0.10,  # seconds of pause between sentences
            'idle_clip_name': 'idle.mp4',    # name of idle clip in clips folder
            'use_sentence_pauses': False       # enable/disable pauses between sentences
        }
        
        # Validate idle clip exists
        self.idle_clip_path = self.clips_folder / self.config['idle_clip_name']
        if not self.idle_clip_path.exists():
            print(f"WARNING: Idle clip not found: {self.idle_clip_path}")
            self.config['use_sentence_pauses'] = False
        else:
            print(f"Found idle clip: {self.idle_clip_path}")
        
    def _scan_clips_folder(self) -> Dict[int, List[str]]:
        """Scan the clips folder and organize clips by syllable count"""
        clips_by_syllables = {}
        
        if not self.clips_folder.exists():
            raise FileNotFoundError(f"Clips folder not found: {self.clips_folder}")
        
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
        
        print(f"Found clips for syllable counts: {sorted(clips_by_syllables.keys())}")
        for count, clips in clips_by_syllables.items():
            print(f"  {count} syllables: {len(clips)} clips")
        
        return clips_by_syllables
    
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
    
    def transcribe_audio(self, audio_path: str) -> Dict:
        """Transcribe audio with word-level timestamps"""
        print(f"Transcribing audio: {audio_path}")
        result = self.model.transcribe(audio_path, word_timestamps=True)
        return result
    
    def split_into_sentences(self, transcription_result: Dict) -> List[Dict]:
        """Split transcription into sentences with timing information"""
        sentences = []
        current_sentence = {
            'words': [],
            'text': '',
            'start_time': None,
            'end_time': None
        }
        
        for segment in transcription_result["segments"]:
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
        
        print(f"Split into {len(sentences)} sentences:")
        for i, sentence in enumerate(sentences):
            print(f"  {i+1}: '{sentence['text'].strip()}' ({sentence['start_time']:.2f}s - {sentence['end_time']:.2f}s)")
        
        return sentences
    
    def find_suitable_clip(self, sentence_syllables: int) -> str:
        """Find a random clip that matches the syllable count (or closest available)"""
        available_counts = sorted(self.available_clips.keys())
        
        # Try exact match first
        if sentence_syllables in self.available_clips:
            return random.choice(self.available_clips[sentence_syllables])
        
        # Find closest syllable count
        closest_count = min(available_counts, key=lambda x: abs(x - sentence_syllables))
        print(f"No exact match for {sentence_syllables} syllables, using {closest_count} syllables clip")
        
        return random.choice(self.available_clips[closest_count])
    
    def extract_audio_segment(self, input_audio: str, start_time: float, end_time: float, output_path: str):
        """Extract audio segment using ffmpeg"""
        duration = end_time - start_time
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        cmd = [
            'ffmpeg', '-y',
            '-i', input_audio,
            '-ss', str(start_time),
            '-t', str(duration),
            '-acodec', 'pcm_s16le',  # Use uncompressed audio for better compatibility
            '-ar', '44100',          # Standard sample rate
            '-ac', '2',              # Stereo
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Extracted audio segment: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"Audio extraction error: {e.stderr}")
            raise
    
    def diagnose_video_file(self, video_path: str):
        """Diagnose video file properties for debugging"""
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            import json
            info = json.loads(result.stdout)
            
            print(f"Video file diagnosis for: {Path(video_path).name}")
            
            # Format info
            format_info = info.get('format', {})
            print(f"  Format: {format_info.get('format_name', 'unknown')}")
            print(f"  Duration: {format_info.get('duration', 'unknown')}s")
            print(f"  Size: {format_info.get('size', 'unknown')} bytes")
            
            # Stream info
            for i, stream in enumerate(info.get('streams', [])):
                print(f"  Stream {i}: {stream.get('codec_type', 'unknown')} - {stream.get('codec_name', 'unknown')}")
                if stream.get('codec_type') == 'video':
                    print(f"    Resolution: {stream.get('width', '?')}x{stream.get('height', '?')}")
                    print(f"    Frame rate: {stream.get('r_frame_rate', 'unknown')}")
                    print(f"    Pixel format: {stream.get('pix_fmt', 'unknown')}")
            
        except Exception as e:
            print(f"Could not diagnose video file: {e}")
    
    def get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe"""
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"Error getting video duration for {video_path}: {e}")
            self.diagnose_video_file(video_path)
            raise
    
    def sync_audio_to_video(self, audio_path: str, video_path: str, output_path: str):
        """Sync audio to video, adjusting video speed if necessary"""
        # Get durations
        audio_duration = self.get_audio_duration(audio_path)
        video_duration = self.get_video_duration(video_path)
        
        print(f"Audio duration: {audio_duration:.2f}s, Video duration: {video_duration:.2f}s")
        
        # First, let's check if the video file is valid
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if audio_duration <= video_duration:
            # Audio is shorter or equal - let video play to completion with audio + silence
            print(f"Audio is shorter, letting video play to completion ({video_duration:.2f}s)")
            
            # Create silent audio to pad the difference
            silence_duration = video_duration - audio_duration
            temp_padded_audio = os.path.join(os.path.dirname(output_path), f"temp_padded_{os.path.basename(audio_path)}")
            
            # First, create padded audio with silence
            pad_cmd = [
                'ffmpeg', '-y',
                '-i', audio_path,
                '-af', f'apad=pad_dur={silence_duration}',
                '-ar', '44100',
                '-ac', '2',
                temp_padded_audio
            ]
            
            try:
                subprocess.run(pad_cmd, check=True, capture_output=True, text=True)
                print(f"Created padded audio with {silence_duration:.2f}s silence")
                
                # Now sync the padded audio with video
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-i', temp_padded_audio,
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-ac', '2',
                    '-r', '30',
                    '-pix_fmt', 'yuv420p',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-shortest',  # This will use the shorter of video or padded audio (should be same length)
                    output_path
                ]
                
            except Exception as e:
                print(f"Failed to create padded audio: {e}")
                # Fallback to original method
                cmd = [
                    'ffmpeg', '-y',
                    '-i', video_path,
                    '-i', audio_path,
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-ac', '2',
                    '-r', '30',
                    '-pix_fmt', 'yuv420p',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-t', str(video_duration),  # Use video duration, not audio duration
                    output_path
                ]
        else:
            # Audio is longer - slow down video to match audio duration
            speed_factor = video_duration / audio_duration
            print(f"Slowing down video by factor: {speed_factor:.3f}")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-filter:v', f'setpts={1/speed_factor}*PTS',
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-ac', '2',
                '-pix_fmt', 'yuv420p',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-shortest',
                output_path
            ]
        
        print(f"Running ffmpeg command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"FFmpeg completed successfully")
            
            # Clean up temporary padded audio if it exists
            if 'temp_padded_audio' in locals() and os.path.exists(temp_padded_audio):
                os.unlink(temp_padded_audio)
                print("Cleaned up temporary padded audio")
            
            # Verify the output has audio
            self.verify_output_audio(output_path)
            
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error (exit code {e.returncode}):")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            
            # Clean up temporary file on error too
            if 'temp_padded_audio' in locals() and os.path.exists(temp_padded_audio):
                os.unlink(temp_padded_audio)
            
            # Try a simpler approach as fallback
            print("Trying fallback method...")
            self.sync_audio_to_video_fallback(audio_path, video_path, output_path)
    
    def verify_output_audio(self, video_path: str):
        """Verify that the output video has audio"""
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_name,duration',
            '-of', 'csv=p=0',
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout.strip():
                print(f"✓ Output video has audio: {result.stdout.strip()}")
            else:
                print(f"⚠ WARNING: Output video has NO AUDIO!")
        except Exception as e:
            print(f"Could not verify audio: {e}")
    
    def create_pause_clip(self, output_path: str):
        """Create a pause clip by cutting idle.mp4 to the specified duration"""
        if not self.config['use_sentence_pauses']:
            return None
        
        duration = self.config['sentence_pause_duration']
        idle_path = str(self.idle_clip_path)
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        cmd = [
            'ffmpeg', '-y',
            '-i', idle_path,
            '-t', str(duration),  # Cut to specified duration
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',
            '-pix_fmt', 'yuv420p',
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Created pause clip: {Path(output_path).name} ({duration}s)")
            return output_path
        except subprocess.CalledProcessError as e:
            print(f"Failed to create pause clip: {e.stderr}")
            return None
        """Fallback method with more compatible settings"""
        audio_duration = self.get_audio_duration(audio_path)
        video_duration = self.get_video_duration(video_path)
        
        # Simple approach: always re-encode everything with guaranteed audio
        if audio_duration <= video_duration:
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-vf', 'scale=720:480',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ac', '2',
                '-ar', '44100',
                '-map', '0:v',
                '-map', '1:a',
                '-t', str(audio_duration),
                output_path
            ]
        else:
            # Slow down video
            speed_factor = video_duration / audio_duration
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-vf', f'scale=720:480,setpts={1/speed_factor}*PTS',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ac', '2',
                '-ar', '44100',
                '-map', '0:v',
                '-map', '1:a',
                '-shortest',
                output_path
            ]
        
        print(f"Fallback command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Fallback method completed successfully")
        
        # Verify the fallback output has audio
        self.verify_output_audio(output_path)
    
    def sync_audio_to_video_fallback(self, audio_path: str, video_path: str, output_path: str):
        """Fallback method with more compatible settings"""
        audio_duration = self.get_audio_duration(audio_path)
        video_duration = self.get_video_duration(video_path)
        
        # Simple approach: always re-encode everything
        if audio_duration <= video_duration:
            # Let video play to completion, not just audio duration
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-vf', 'scale=720:480',  # Standard resolution
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-ac', '2',  # Stereo
                '-ar', '44100',  # Standard sample rate
                '-t', str(video_duration),  # Use video duration, not audio duration
                output_path
            ]
        else:
            # Slow down video
            speed_factor = video_duration / audio_duration
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-vf', f'scale=720:480,setpts={1/speed_factor}*PTS',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-ac', '2',
                '-ar', '44100',
                '-shortest',
                output_path
            ]
        
        print(f"Fallback command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Fallback method completed successfully")
        
        # Verify the fallback output has audio
        self.verify_output_audio(output_path)
    
    def get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration using ffprobe"""
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    
    def concatenate_videos(self, video_list: List[str], output_path: str):
        """Concatenate multiple videos into final output"""
        if not video_list:
            raise ValueError("No videos to concatenate")
        
        print(f"Concatenating {len(video_list)} videos...")
        
        # First, let's check each video has audio
        for i, video in enumerate(video_list):
            self.check_video_audio(video, i+1)
        
        # Create temporary file list for ffmpeg
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for video in video_list:
                # Use absolute paths and escape special characters
                abs_path = os.path.abspath(video).replace('\\', '/')
                f.write(f"file '{abs_path}'\n")
            concat_file = f.name
        
        try:
            # First attempt: use concat with re-encoding for compatibility
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-ac', '2',
                '-pix_fmt', 'yuv420p',
                output_path
            ]
            
            print(f"Concatenation command: {' '.join(cmd)}")
            
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                print("Concatenation completed successfully")
            except subprocess.CalledProcessError as e:
                print(f"Concatenation failed: {e.stderr}")
                print("Trying alternative concatenation method...")
                self.concatenate_videos_alternative(video_list, output_path)
                
        finally:
            if os.path.exists(concat_file):
                os.unlink(concat_file)
    
    def check_video_audio(self, video_path: str, video_num: int):
        """Check if video has audio track"""
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-select_streams', 'a',
            '-show_entries', 'stream=codec_name',
            '-of', 'csv=p=0',
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if result.stdout.strip():
                print(f"Video {video_num} has audio: {result.stdout.strip()}")
            else:
                print(f"WARNING: Video {video_num} has NO AUDIO: {Path(video_path).name}")
        except Exception as e:
            print(f"Could not check audio for video {video_num}: {e}")
    
    def concatenate_videos_alternative(self, video_list: List[str], output_path: str):
        """Alternative concatenation method using filter_complex"""
        if len(video_list) == 1:
            # Just copy the single video
            cmd = ['ffmpeg', '-y', '-i', video_list[0], '-c', 'copy', output_path]
            subprocess.run(cmd, check=True, capture_output=True)
            return
        
        # Build filter_complex for concatenation
        inputs = []
        for video in video_list:
            inputs.extend(['-i', video])
        
        # Create filter string
        filter_parts = []
        for i in range(len(video_list)):
            filter_parts.append(f'[{i}:v][{i}:a]')
        
        filter_string = f"{''.join(filter_parts)}concat=n={len(video_list)}:v=1:a=1[outv][outa]"
        
        cmd = [
            'ffmpeg', '-y'
        ] + inputs + [
            '-filter_complex', filter_string,
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',
            output_path
        ]
        
        print(f"Alternative concatenation command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Alternative concatenation completed")
    
    def get_unique_output_folder(self, base_output_dir: str = "output") -> Path:
        """Create a unique output folder for this run"""
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
        
        print(f"Created output folder: {unique_folder}")
        return unique_folder

    def process_audio(self, audio_path: str, output_dir: str = "output") -> str:
        """Main processing function"""
        # Create unique output directory for this run
        output_path = self.get_unique_output_folder(output_dir)
        
        # Create subdirectories for organization
        temp_dir = output_path / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        print(f"\n=== PROCESSING RUN ===")
        print(f"Output folder: {output_path}")
        print(f"Audio file: {Path(audio_path).name}")
        print("=" * 25)
        
        # Step 1: Transcribe audio
        transcription = self.transcribe_audio(audio_path)
        
        # Step 2: Split into sentences
        sentences = self.split_into_sentences(transcription)
        
        # Step 3: Process each sentence
        sentence_videos = []
        
        for i, sentence in enumerate(sentences):
            print(f"\nProcessing sentence {i+1}: '{sentence['text'].strip()}'")
            
            # Count syllables
            syllable_count = self.count_syllables_in_sentence(sentence['text'])
            print(f"Syllable count: {syllable_count}")
            
            # Find suitable clip
            selected_clip = self.find_suitable_clip(syllable_count)
            print(f"Selected clip: {Path(selected_clip).name}")
            
            # Diagnose the selected clip
            self.diagnose_video_file(selected_clip)
            
            # Extract audio segment (save to temp folder)
            segment_audio = temp_dir / f"sentence_{i+1}_audio.wav"
            try:
                self.extract_audio_segment(
                    audio_path, 
                    sentence['start_time'], 
                    sentence['end_time'], 
                    str(segment_audio)
                )
            except Exception as e:
                print(f"Failed to extract audio for sentence {i+1}: {e}")
                continue
            
            # Sync audio to video (save to main output folder)
            sentence_video = output_path / f"sentence_{i+1}_synced.mp4"
            try:
                self.sync_audio_to_video(
                    str(segment_audio),
                    selected_clip,
                    str(sentence_video)
                )
                
                sentence_videos.append(str(sentence_video))
                print(f"Created: {sentence_video.name}")
                
                # Add pause clip after each sentence (except the last one)
                if self.config['use_sentence_pauses'] and i < len(sentences) - 1:
                    pause_clip_path = output_path / f"pause_{i+1}.mp4"
                    pause_clip = self.create_pause_clip(str(pause_clip_path))
                    
                    if pause_clip:
                        sentence_videos.append(pause_clip)
                        print(f"Added pause after sentence {i+1}")
                
            except Exception as e:
                print(f"Failed to sync sentence {i+1}: {e}")
                # Continue with other sentences
                continue
        
        # Step 4: Concatenate all sentences
        if not sentence_videos:
            raise RuntimeError("No videos were successfully created!")
        
        final_output = output_path / "final_lipsynced_video.mp4"
        print(f"\nConcatenating {len(sentence_videos)} videos...")
        self.concatenate_videos(sentence_videos, str(final_output))
        
        # Final verification
        print(f"\n=== FINAL VERIFICATION ===")
        self.verify_output_audio(str(final_output))
        final_duration = self.get_video_duration(str(final_output))
        print(f"Final video duration: {final_duration:.2f}s")
        
        # Create summary file
        self.create_run_summary(output_path, audio_path, sentences, sentence_videos, final_duration)
        
        print(f"\nFinal lip-synced video created: {final_output}")
        print(f"All files saved in: {output_path}")
        return str(final_output)
    
    def create_run_summary(self, output_path: Path, audio_path: str, sentences: List[Dict], 
                          sentence_videos: List[str], final_duration: float):
        """Create a summary file for this run"""
        summary_file = output_path / "run_summary.txt"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("=== LIP SYNC RUN SUMMARY ===\n\n")
            f.write(f"Run folder: {output_path.name}\n")
            f.write(f"Timestamp: {output_path.stat().st_ctime}\n")
            f.write(f"Input audio: {Path(audio_path).name}\n")
            f.write(f"Final duration: {final_duration:.2f}s\n")
            f.write(f"Sentences processed: {len(sentences)}\n")
            f.write(f"Videos created: {len(sentence_videos)}\n")
            f.write(f"Pauses enabled: {'Yes' if self.config['use_sentence_pauses'] else 'No'}\n")
            if self.config['use_sentence_pauses']:
                f.write(f"Pause duration: {self.config['sentence_pause_duration']}s\n")
            f.write("\n" + "="*50 + "\n\n")
            
            f.write("SENTENCE BREAKDOWN:\n\n")
            for i, sentence in enumerate(sentences):
                f.write(f"Sentence {i+1}:\n")
                f.write(f"  Text: '{sentence['text'].strip()}'\n")
                f.write(f"  Duration: {sentence['start_time']:.2f}s - {sentence['end_time']:.2f}s\n")
                f.write(f"  Syllables: {self.count_syllables_in_sentence(sentence['text'])}\n")
                f.write("\n")
            
            f.write("\n" + "="*50 + "\n\n")
            f.write("FILES CREATED:\n\n")
            for video in sentence_videos:
                f.write(f"  {Path(video).name}\n")
            f.write(f"  final_lipsynced_video.mp4\n")
            f.write(f"  temp/ (folder with audio segments)\n")
        
        print(f"Run summary saved: {summary_file.name}")

# Usage example
if __name__ == "__main__":
    # Paths
    clips_folder = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\avatars\Darwin\sora\all"
    audio_file = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\old\t5.wav"
    
    # Initialize system
    lipsync = LipSyncSystem(clips_folder)
    
    # Process audio
    try:
        final_video = lipsync.process_audio(audio_file)
        print(f"Success! Final video: {final_video}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()