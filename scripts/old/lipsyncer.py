# lipsyncer.py - Advanced lipsync system for avatar chatbot

import os
import time
import random
import threading
import subprocess
import tempfile
import re
from pathlib import Path
from typing import List, Tuple, Optional
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

class LipsyncSystem:
    def __init__(self, avatar_name: str = "Darwin"):
        self.avatar_name = avatar_name
        self.avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        self.talking_clips_dir = os.path.join(self.avatar_dir, "talking_clips")
        self.temp_dir = os.path.join(PROJECT_DIR, "tempstream", "lipsync")
        
        # Timing constants
        self.clip_duration = 5.0  # Total clip duration
        self.idle_start = 1.0     # Idle time at start
        self.idle_end = 1.0       # Idle time at end
        self.talking_duration = 3.0  # Active talking time (center)
        
        # Ensure directories exist
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Check for required tools
        self.ffmpeg_available = self._check_ffmpeg()
        self.talking_clips = self._load_talking_clips()
        
        print(f"{Fore.GREEN}[LIPSYNC] Initialized for avatar: {avatar_name}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Found {len(self.talking_clips)} talking clips{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[LIPSYNC] Timing: {self.idle_start}s idle + {self.talking_duration}s talking + {self.idle_end}s idle{Style.RESET_ALL}")

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        ffmpeg_paths = [
            'ffmpeg',
            'ffmpeg.exe',
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe'
        ]
        
        for path in ffmpeg_paths:
            try:
                result = subprocess.run([path, '-version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0:
                    print(f"{Fore.GREEN}[LIPSYNC] FFmpeg found: {path}{Style.RESET_ALL}")
                    self.ffmpeg_path = path
                    return True
            except:
                continue
        
        print(f"{Fore.RED}[LIPSYNC] FFmpeg not found - video processing will be limited{Style.RESET_ALL}")
        return False

    def _load_talking_clips(self) -> List[str]:
        """Load all available talking video clips"""
        clips = []
        
        if not os.path.exists(self.talking_clips_dir):
            print(f"{Fore.YELLOW}[LIPSYNC] Creating talking_clips directory: {self.talking_clips_dir}{Style.RESET_ALL}")
            os.makedirs(self.talking_clips_dir, exist_ok=True)
            return clips
        
        for file in os.listdir(self.talking_clips_dir):
            if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                clips.append(os.path.join(self.talking_clips_dir, file))
        
        clips.sort()  # Consistent ordering
        return clips

    def split_text_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences, handling edge cases"""
        if not text or not text.strip():
            return []
        
        # Clean the text
        text = text.strip()
        
        # Split on sentence endings, but be smart about abbreviations
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        
        # Clean up sentences and filter out very short ones
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 3:  # Minimum sentence length
                cleaned_sentences.append(sentence)
        
        # If we got no sentences, treat the whole text as one sentence
        if not cleaned_sentences:
            cleaned_sentences = [text]
        
        print(f"{Fore.CYAN}[LIPSYNC] Split text into {len(cleaned_sentences)} sentences{Style.RESET_ALL}")
        for i, sentence in enumerate(cleaned_sentences):
            print(f"{Fore.CYAN}[LIPSYNC]   {i+1}: {sentence[:50]}...{Style.RESET_ALL}")
        
        return cleaned_sentences

    def generate_tts_for_sentence(self, sentence: str, output_path: str) -> Optional[str]:
        """Generate TTS audio for a single sentence"""
        try:
            # Import TTS function from your enhanced TTS system
            from enhanced_tts_piper import generate_complete_audio
            
            print(f"{Fore.BLUE}[LIPSYNC] Generating TTS for: {sentence[:30]}...{Style.RESET_ALL}")
            
            # Generate TTS audio
            audio_file = generate_complete_audio(sentence, 
                                               output_filename=os.path.splitext(os.path.basename(output_path))[0])
            
            if audio_file and os.path.exists(audio_file):
                # Move to our desired location if needed
                if audio_file != output_path:
                    import shutil
                    shutil.move(audio_file, output_path)
                
                print(f"{Fore.GREEN}[LIPSYNC] TTS generated: {os.path.basename(output_path)}{Style.RESET_ALL}")
                return output_path
            else:
                print(f"{Fore.RED}[LIPSYNC] TTS generation failed for sentence{Style.RESET_ALL}")
                return None
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] TTS error: {e}{Style.RESET_ALL}")
            return None

    def get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file using FFmpeg"""
        if not self.ffmpeg_available:
            # Fallback estimation
            try:
                file_size = os.path.getsize(audio_path)
                # Rough estimate: 16kHz, 16-bit, mono = ~2KB per second
                estimated_duration = file_size / 32000  # Rough estimate
                return max(0.5, min(10.0, estimated_duration))
            except:
                return 2.0
        
        try:
            cmd = [self.ffmpeg_path, '-i', audio_path, '-f', 'null', '-']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Parse duration from FFmpeg output
            for line in result.stderr.split('\n'):
                if 'Duration:' in line:
                    duration_str = line.split('Duration:')[1].split(',')[0].strip()
                    time_parts = duration_str.split(':')
                    if len(time_parts) == 3:
                        hours = float(time_parts[0])
                        minutes = float(time_parts[1])
                        seconds = float(time_parts[2])
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        return total_seconds
            
            return 2.0  # Fallback
            
        except Exception as e:
            print(f"{Fore.YELLOW}[LIPSYNC] Audio duration detection failed: {e}{Style.RESET_ALL}")
            return 2.0

    def check_video_has_audio(self, video_path: str) -> bool:
        """Check if video has an audio stream"""
        try:
            cmd = [self.ffmpeg_path, '-i', video_path, '-f', 'null', '-']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            # Check if stderr mentions audio stream
            return 'Audio:' in result.stderr
            
        except Exception:
            return False

    def merge_audio_with_video(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Merge audio with video, respecting timing constraints"""
        if not self.ffmpeg_available:
            print(f"{Fore.RED}[LIPSYNC] Cannot merge - FFmpeg not available{Style.RESET_ALL}")
            return False
        
        try:
            audio_duration = self.get_audio_duration(audio_path)
            
            # Calculate timing for audio placement
            # We want to center the audio in the 3-second talking window
            audio_start_time = self.idle_start + max(0, (self.talking_duration - audio_duration) / 2)
            
            print(f"{Fore.BLUE}[LIPSYNC] Merging: audio_duration={audio_duration:.2f}s, start_time={audio_start_time:.2f}s{Style.RESET_ALL}")
            
            # Check if video has audio
            video_has_audio = self.check_video_has_audio(video_path)
            
            if video_has_audio:
                # Video has audio - mix with our TTS audio
                cmd = [
                    self.ffmpeg_path,
                    '-i', video_path,      # Input video
                    '-i', audio_path,      # Input audio
                    '-filter_complex', 
                    f'[1:a]adelay={int(audio_start_time * 1000)}|{int(audio_start_time * 1000)}[delayed_audio];'
                    f'[0:a][delayed_audio]amix=inputs=2:duration=first[mixed_audio]',
                    '-map', '0:v',         # Use video from first input
                    '-map', '[mixed_audio]', # Use mixed audio
                    '-c:v', 'copy',        # Copy video codec (faster)
                    '-c:a', 'aac',         # Re-encode audio
                    '-shortest',           # Stop when shortest stream ends
                    '-y',                  # Overwrite output
                    output_path
                ]
            else:
                # Video has no audio - just add our TTS audio with delay
                cmd = [
                    self.ffmpeg_path,
                    '-i', video_path,      # Input video (no audio)
                    '-i', audio_path,      # Input audio
                    '-filter_complex', 
                    f'[1:a]adelay={int(audio_start_time * 1000)}|{int(audio_start_time * 1000)}[delayed_audio]',
                    '-map', '0:v',         # Use video from first input
                    '-map', '[delayed_audio]', # Use delayed audio
                    '-c:v', 'copy',        # Copy video codec (faster)
                    '-c:a', 'aac',         # Re-encode audio
                    '-shortest',           # Stop when shortest stream ends
                    '-y',                  # Overwrite output
                    output_path
                ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"{Fore.GREEN}[LIPSYNC] Successfully merged: {os.path.basename(output_path)}{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[LIPSYNC] Merge failed: {result.stderr}{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Merge error: {e}{Style.RESET_ALL}")
            return False

    def stitch_videos_together(self, video_files: List[str], output_path: str) -> bool:
        """Stitch multiple video files together into final output"""
        if not self.ffmpeg_available:
            print(f"{Fore.RED}[LIPSYNC] Cannot stitch - FFmpeg not available{Style.RESET_ALL}")
            return False
        
        if not video_files:
            print(f"{Fore.RED}[LIPSYNC] No videos to stitch{Style.RESET_ALL}")
            return False
        
        if len(video_files) == 1:
            # Just copy the single file
            import shutil
            shutil.copy2(video_files[0], output_path)
            return True
        
        try:
            # Create a temporary file list for FFmpeg concat
            concat_file = os.path.join(self.temp_dir, "concat_list.txt")
            
            with open(concat_file, 'w') as f:
                for video_file in video_files:
                    # Use forward slashes for FFmpeg compatibility
                    video_path = video_file.replace('\\', '/')
                    f.write(f"file '{video_path}'\n")
            
            print(f"{Fore.BLUE}[LIPSYNC] Stitching {len(video_files)} videos together{Style.RESET_ALL}")
            
            # FFmpeg concat command
            cmd = [
                self.ffmpeg_path,
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # Copy without re-encoding for speed
                '-y',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Clean up concat file
            try:
                os.remove(concat_file)
            except:
                pass
            
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"{Fore.GREEN}[LIPSYNC] Successfully stitched final video: {os.path.basename(output_path)}{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[LIPSYNC] Stitching failed: {result.stderr}{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Stitching error: {e}{Style.RESET_ALL}")
            return False

    def cleanup_temp_files(self, keep_final: bool = True):
        """Clean up temporary files, optionally keeping the final output"""
        try:
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                
                if keep_final and file.startswith('final_lipsync_'):
                    continue  # Keep final output files
                
                try:
                    os.remove(file_path)
                except:
                    pass
            
            print(f"{Fore.CYAN}[LIPSYNC] Cleaned up temporary files{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"{Fore.YELLOW}[LIPSYNC] Cleanup warning: {e}{Style.RESET_ALL}")

    def generate_lipsync(self, text: str, output_filename: str = None) -> Tuple[bool, Optional[str]]:
        """
        Main function to generate lipsync video from text
        
        Args:
            text: The text to convert to lipsync video
            output_filename: Optional custom filename for output
            
        Returns:
            Tuple of (success: bool, video_path: str or None)
        """
        start_time = time.time()
        
        if not text or not text.strip():
            print(f"{Fore.RED}[LIPSYNC] No text provided{Style.RESET_ALL}")
            return False, None
        
        if not self.talking_clips:
            print(f"{Fore.RED}[LIPSYNC] No talking clips available{Style.RESET_ALL}")
            return False, None
        
        # Generate output filename
        if not output_filename:
            timestamp = int(time.time() * 1000)
            output_filename = f"final_lipsync_{timestamp}.mp4"
        
        final_output_path = os.path.join(self.temp_dir, output_filename)
        
        try:
            print(f"{Fore.MAGENTA}[LIPSYNC] Starting lipsync generation for: {text[:50]}...{Style.RESET_ALL}")
            
            # Step 1: Split text into sentences
            sentences = self.split_text_into_sentences(text)
            
            if not sentences:
                print(f"{Fore.RED}[LIPSYNC] No valid sentences found{Style.RESET_ALL}")
                return False, None
            
            # Step 2: Process each sentence
            processed_videos = []
            
            for i, sentence in enumerate(sentences):
                print(f"{Fore.CYAN}[LIPSYNC] Processing sentence {i+1}/{len(sentences)}{Style.RESET_ALL}")
                
                # Choose a random talking clip
                video_clip = random.choice(self.talking_clips)
                
                # Generate TTS for this sentence
                audio_filename = f"tts_sentence_{i+1}_{int(time.time()*1000)}.wav"
                audio_path = os.path.join(self.temp_dir, audio_filename)
                
                tts_result = self.generate_tts_for_sentence(sentence, audio_path)
                
                if not tts_result:
                    print(f"{Fore.YELLOW}[LIPSYNC] Skipping sentence {i+1} due to TTS failure{Style.RESET_ALL}")
                    continue
                
                # Merge audio with video
                merged_filename = f"merged_clip_{i+1}_{int(time.time()*1000)}.mp4"
                merged_path = os.path.join(self.temp_dir, merged_filename)
                
                if self.merge_audio_with_video(video_clip, audio_path, merged_path):
                    processed_videos.append(merged_path)
                    print(f"{Fore.GREEN}[LIPSYNC] Sentence {i+1} processed successfully{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}[LIPSYNC] Failed to merge sentence {i+1}{Style.RESET_ALL}")
            
            if not processed_videos:
                print(f"{Fore.RED}[LIPSYNC] No videos were successfully processed{Style.RESET_ALL}")
                return False, None
            
            # Step 3: Stitch all videos together
            print(f"{Fore.MAGENTA}[LIPSYNC] Stitching {len(processed_videos)} clips together{Style.RESET_ALL}")
            
            if self.stitch_videos_together(processed_videos, final_output_path):
                elapsed_time = time.time() - start_time
                print(f"{Fore.GREEN}[LIPSYNC] ✓ Lipsync generation completed in {elapsed_time:.2f}s{Style.RESET_ALL}")
                print(f"{Fore.GREEN}[LIPSYNC] ✓ Final video: {final_output_path}{Style.RESET_ALL}")
                
                # Clean up intermediate files
                self.cleanup_temp_files(keep_final=True)
                
                return True, final_output_path
            else:
                print(f"{Fore.RED}[LIPSYNC] Failed to stitch final video{Style.RESET_ALL}")
                return False, None
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Generation error: {e}{Style.RESET_ALL}")
            return False, None

    def test_system(self) -> bool:
        """Test the lipsync system with a short sample"""
        try:
            test_text = "Hello, this is a test of the lipsync system. It should work correctly."
            
            print(f"{Fore.CYAN}[LIPSYNC] Running system test...{Style.RESET_ALL}")
            
            success, video_path = self.generate_lipsync(test_text, "lipsync_test.mp4")
            
            if success and video_path and os.path.exists(video_path):
                print(f"{Fore.GREEN}[LIPSYNC] ✓ System test passed!{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}[LIPSYNC] ✗ System test failed{Style.RESET_ALL}")
                return False
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Test error: {e}{Style.RESET_ALL}")
            return False

# Convenience function for integration with existing system
def generate_lipsync_with_integration(text: str, avatar_name: str = "Darwin") -> Tuple[bool, Optional[str]]:
    """
    Integration function that matches your existing system's expected interface
    """
    lipsync_system = LipsyncSystem(avatar_name)
    return lipsync_system.generate_lipsync(text)

def setup_lipsync_environment(avatar_name: str = "Darwin") -> bool:
    """
    Setup and test the lipsync environment
    Returns True if ready for use
    """
    try:
        lipsync_system = LipsyncSystem(avatar_name)
        return lipsync_system.test_system()
    except Exception as e:
        print(f"{Fore.RED}[LIPSYNC] Setup failed: {e}{Style.RESET_ALL}")
        return False

if __name__ == "__main__":
    # Test the system when run directly
    print(f"{Fore.GREEN}{'='*50}")
    print(f"{Fore.YELLOW}Testing Lipsync System")
    print(f"{Fore.GREEN}{'='*50}{Style.RESET_ALL}")
    
    lipsync = LipsyncSystem()
    
    test_text = """
    Welcome to the lipsync demonstration! 
    This system can convert text into synchronized video clips. 
    Each sentence gets its own video segment with matching audio.
    """
    
    success, video_path = lipsync.generate_lipsync(test_text.strip())
    
    if success:
        print(f"\n{Fore.GREEN}✓ Test completed successfully!")
        print(f"✓ Output video: {video_path}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}✗ Test failed{Style.RESET_ALL}")