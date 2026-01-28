# continuous_float_idle.py - Continuous FLOAT idle clip generation and management

import os
import time
import threading
import random
import queue
from typing import Optional, List, Callable
from colorama import Fore, Style, init
from pathlib import Path

init(autoreset=True)

class ContinuousFloatIdle:
    """
    Manages continuous generation of FLOAT idle clips.
    
    Features:
    - Generates 5-second FLOAT clips on silent audio
    - Maintains a buffer of up to 100 clips
    - Replays random clips if generation is slower than playback
    - Runs generation in background thread
    """
    
    def __init__(self, project_dir: str, float_lipsync, idle_audio_generator):
        self.project_dir = project_dir
        self.float_lipsync = float_lipsync
        self.audio_generator = idle_audio_generator
        
        # Clip storage directory
        self.idle_clips_dir = os.path.join(project_dir, "tempstream", "float_idle_clips")
        os.makedirs(self.idle_clips_dir, exist_ok=True)
        
        # Buffer management
        self.max_clips = 100
        self.clip_buffer: List[str] = []  # List of video file paths
        self.buffer_lock = threading.Lock()
        
        # Generation settings
        self.clip_duration = 5.0  # seconds
        self.use_ambient = False  # Use silent audio by default (can be changed)
        
        # Background generation
        self.generation_thread = None
        self.generation_queue = queue.Queue()  # Queue for generation requests
        self.is_generating = False
        self.stop_event = threading.Event()
        
        # Playback tracking
        self.current_clip_index = 0
        self.playback_callback: Optional[Callable] = None
        
        # Statistics
        self.clips_generated = 0
        self.clips_replayed = 0
        
        print(f"{Fore.GREEN}[FLOAT_IDLE] Continuous FLOAT idle system initialized{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[FLOAT_IDLE] Idle clips directory: {self.idle_clips_dir}{Style.RESET_ALL}")
    
    def set_playback_callback(self, callback: Callable):
        """Set callback function to call when a new clip is ready to play"""
        self.playback_callback = callback
        print(f"{Fore.GREEN}[FLOAT_IDLE] Playback callback registered{Style.RESET_ALL}")
    
    def start_generation(self):
        """Start the background generation thread"""
        if self.generation_thread and self.generation_thread.is_alive():
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Generation already running{Style.RESET_ALL}")
            return
        
        self.stop_event.clear()
        self.generation_thread = threading.Thread(target=self._generation_loop, daemon=True)
        self.generation_thread.start()
        print(f"{Fore.GREEN}[FLOAT_IDLE] Background generation started{Style.RESET_ALL}")
    
    def stop_generation(self):
        """Stop the background generation thread"""
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Stopping generation...{Style.RESET_ALL}")
        self.stop_event.set()
        if self.generation_thread:
            self.generation_thread.join(timeout=5.0)
        print(f"{Fore.GREEN}[FLOAT_IDLE] Generation stopped{Style.RESET_ALL}")
    
    def _generation_loop(self):
        """Background thread that continuously generates idle clips"""
        print(f"{Fore.CYAN}[FLOAT_IDLE] Generation loop started{Style.RESET_ALL}")
        
        while not self.stop_event.is_set():
            try:
                # Check if we need more clips
                with self.buffer_lock:
                    buffer_size = len(self.clip_buffer)
                    need_generation = buffer_size < self.max_clips
                
                if need_generation:
                    # Generate a new clip
                    self._generate_single_clip()
                else:
                    # Buffer is full, wait a bit
                    print(f"{Fore.CYAN}[FLOAT_IDLE] Buffer full ({self.max_clips} clips), waiting...{Style.RESET_ALL}")
                    self.stop_event.wait(timeout=10.0)
            
            except Exception as e:
                print(f"{Fore.RED}[FLOAT_IDLE] Error in generation loop: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()
                # Wait before retrying
                self.stop_event.wait(timeout=5.0)
        
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Generation loop ended{Style.RESET_ALL}")
    
    def _generate_single_clip(self):
        """Generate a single idle clip"""
        try:
            self.is_generating = True
            gen_start = time.time()
            
            # Generate audio
            print(f"{Fore.CYAN}[FLOAT_IDLE] Generating idle clip {self.clips_generated + 1}...{Style.RESET_ALL}")
            
            if self.use_ambient:
                audio_path = self.audio_generator.generate_ambient_audio(
                    duration=self.clip_duration,
                    output_filename=f"idle_audio_{self.clips_generated}.wav"
                )
            else:
                audio_path = self.audio_generator.generate_silent_audio(
                    duration=self.clip_duration,
                    output_filename=f"idle_audio_{self.clips_generated}.wav"
                )
            
            if not audio_path:
                print(f"{Fore.RED}[FLOAT_IDLE] Failed to generate audio{Style.RESET_ALL}")
                return
            
            # Generate FLOAT video
            video_filename = f"float_idle_{self.clips_generated}.mp4"
            video_output_path = os.path.join(self.idle_clips_dir, video_filename)
            
            print(f"{Fore.CYAN}[FLOAT_IDLE] Running FLOAT generation...{Style.RESET_ALL}")
            video_path = self.float_lipsync.generate_lipsync(
                audio_path=audio_path,
                output_filename=video_output_path
            )
            
            if video_path and os.path.exists(video_path):
                # Add to buffer
                with self.buffer_lock:
                    self.clip_buffer.append(video_path)
                    self.clips_generated += 1
                
                gen_time = time.time() - gen_start
                print(f"{Fore.GREEN}[FLOAT_IDLE] ✓ Clip generated in {gen_time:.2f}s (buffer: {len(self.clip_buffer)}/{self.max_clips}){Style.RESET_ALL}")
                
                # Clean up audio file
                try:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                except:
                    pass
            else:
                print(f"{Fore.RED}[FLOAT_IDLE] Failed to generate video{Style.RESET_ALL}")
        
        except Exception as e:
            print(f"{Fore.RED}[FLOAT_IDLE] Error generating clip: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_generating = False
    
    def get_next_clip(self) -> Optional[str]:
        """
        Get the next clip to play.
        Returns newest clip if available, otherwise a random previous clip.
        """
        with self.buffer_lock:
            if not self.clip_buffer:
                print(f"{Fore.YELLOW}[FLOAT_IDLE] No clips in buffer yet!{Style.RESET_ALL}")
                return None
            
            # If we have new clips, play the oldest one (FIFO)
            # This ensures we're always playing through the buffer
            clip_path = self.clip_buffer.pop(0)
            
            # Re-add to end of buffer (circular buffer behavior)
            self.clip_buffer.append(clip_path)
            
            # Track if we're replaying (all clips have been played once)
            if len(self.clip_buffer) >= self.max_clips:
                self.clips_replayed += 1
            
            print(f"{Fore.BLUE}[FLOAT_IDLE] Next clip: {os.path.basename(clip_path)} (buffer: {len(self.clip_buffer)}){Style.RESET_ALL}")
            return clip_path
    
    def get_random_clip(self) -> Optional[str]:
        """Get a random clip from the buffer (for fallback)"""
        with self.buffer_lock:
            if not self.clip_buffer:
                return None
            
            clip_path = random.choice(self.clip_buffer)
            print(f"{Fore.BLUE}[FLOAT_IDLE] Random clip: {os.path.basename(clip_path)}{Style.RESET_ALL}")
            return clip_path
    
    def get_buffer_status(self) -> dict:
        """Get current buffer status"""
        with self.buffer_lock:
            return {
                'buffer_size': len(self.clip_buffer),
                'max_clips': self.max_clips,
                'clips_generated': self.clips_generated,
                'clips_replayed': self.clips_replayed,
                'is_generating': self.is_generating,
                'buffer_full': len(self.clip_buffer) >= self.max_clips
            }
    
    def cleanup_old_clips(self, keep_count: int = None):
        """Clean up old clips beyond the buffer"""
        if keep_count is None:
            keep_count = self.max_clips
        
        try:
            all_clips = []
            for file in os.listdir(self.idle_clips_dir):
                if file.startswith('float_idle_') and file.endswith('.mp4'):
                    file_path = os.path.join(self.idle_clips_dir, file)
                    all_clips.append((file_path, os.path.getmtime(file_path)))
            
            # Sort by modification time (newest first)
            all_clips.sort(key=lambda x: x[1], reverse=True)
            
            # Delete old clips
            for file_path, _ in all_clips[keep_count:]:
                try:
                    # Only delete if not in current buffer
                    with self.buffer_lock:
                        if file_path not in self.clip_buffer:
                            os.remove(file_path)
                            print(f"{Fore.YELLOW}[FLOAT_IDLE] Cleaned up: {os.path.basename(file_path)}{Style.RESET_ALL}")
                except:
                    pass
        
        except Exception as e:
            print(f"{Fore.RED}[FLOAT_IDLE] Error cleaning up clips: {e}{Style.RESET_ALL}")
    
    def preload_clips(self, count: int = 5):
        """Preload a specified number of clips before starting continuous generation"""
        print(f"{Fore.CYAN}[FLOAT_IDLE] Preloading {count} clips...{Style.RESET_ALL}")
        
        for i in range(count):
            if self.stop_event.is_set():
                break
            
            print(f"{Fore.CYAN}[FLOAT_IDLE] Preloading clip {i+1}/{count}...{Style.RESET_ALL}")
            self._generate_single_clip()
        
        print(f"{Fore.GREEN}[FLOAT_IDLE] ✓ Preload complete ({len(self.clip_buffer)} clips ready){Style.RESET_ALL}")


# Test the system
if __name__ == "__main__":
    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Testing Continuous FLOAT Idle System{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
    
    print(f"{Fore.YELLOW}Note: This test requires FLOAT system to be initialized{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Run this test from the main application, not standalone{Style.RESET_ALL}")
