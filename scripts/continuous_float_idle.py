"""
Continuous FLOAT Idle System - With Frame Continuity
Generates idle clips in background, using last frame of previous clip as reference
"""

import os
import time
import threading
from pathlib import Path
from typing import Optional
from colorama import Fore, Style, init
import subprocess
import cv2

init(autoreset=True)


class ContinuousFloatIdle:
    """Continuously generates FLOAT idle clips with frame continuity"""
    
    def __init__(self, project_dir: str, float_lipsync, idle_audio_generator):
        self.project_dir = project_dir
        self.float_lipsync = float_lipsync
        self.idle_audio_gen = idle_audio_generator
        
        # Configuration
        self.max_clips = 100
        self.clip_duration = 5.0
        self.use_ambient = False
        
        # ORDERED buffer (maintains sequence for continuity)
        self.clips_buffer = []  # List of clip paths in order
        self.current_index = 0  # Which clip we're currently showing
        
        # Generation tracking
        self.clips_generated = 0
        self.clips_replayed = 0
        
        # Generation control
        self.is_generating = False
        self.generation_thread = None
        self._stop_generation = False
        self.generation_lock = threading.Lock()
        
        # Frame continuity
        self.current_reference_image = None  # Path to current reference image
        self.original_reference_image = None  # Path to original reference (backup)
        self.frames_dir = os.path.join(project_dir, "tempstream", "float_frames")
        os.makedirs(self.frames_dir, exist_ok=True)
        
        # Clips directory
        self.clips_dir = os.path.join(project_dir, "tempstream", "float_idle_clips")
        os.makedirs(self.clips_dir, exist_ok=True)
        
        print(f"{Fore.GREEN}[FLOAT_IDLE] Continuous FLOAT idle system initialized{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[FLOAT_IDLE] Idle clips directory: {self.clips_dir}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[FLOAT_IDLE] Frames directory: {self.frames_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[FLOAT_IDLE] Frame continuity: ENABLED (each clip uses last frame of previous){Style.RESET_ALL}")
    
    def extract_last_frame(self, video_path: str) -> Optional[str]:
        """Extract the last frame from a video and resize to 512x512 for FLOAT"""
        try:
            # Open video
            cap = cv2.VideoCapture(video_path)
            
            # Get total frames
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Jump to last frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
            
            # Read last frame
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                print(f"{Fore.YELLOW}[FLOAT_IDLE] Failed to read last frame{Style.RESET_ALL}")
                return None
            
            # Get frame dimensions
            height, width = frame.shape[:2]
            
            # If not square, center crop to square first
            if height != width:
                size = min(height, width)
                y_offset = (height - size) // 2
                x_offset = (width - size) // 2
                frame = frame[y_offset:y_offset+size, x_offset:x_offset+size]
                print(f"{Fore.YELLOW}[FLOAT_IDLE] Cropped {width}x{height} to {size}x{size} (center crop){Style.RESET_ALL}")
            
            # Resize to 512x512 for FLOAT consistency
            # This ensures no misalignment between clips
            frame_512 = cv2.resize(frame, (512, 512), interpolation=cv2.INTER_LANCZOS4)
            
            # Save frame at 512x512
            frame_path = os.path.join(self.frames_dir, f"last_frame_{self.clips_generated}.png")
            cv2.imwrite(frame_path, frame_512)
            
            print(f"{Fore.CYAN}[FLOAT_IDLE] Extracted last frame (512x512) → {os.path.basename(frame_path)}{Style.RESET_ALL}")
            return frame_path
            
        except Exception as e:
            print(f"{Fore.RED}[FLOAT_IDLE] Error extracting last frame: {e}{Style.RESET_ALL}")
            return None
    
    def _generate_single_clip(self):
        """Generate a single idle clip using current reference image"""
        clip_num = self.clips_generated
        
        print(f"{Fore.CYAN}[FLOAT_IDLE] Generating idle clip {clip_num + 1}...{Style.RESET_ALL}")
        
        # Generate silent/ambient audio (using existing API without filename parameter)
        audio_path = self.idle_audio_gen.generate_silent_audio(duration=self.clip_duration)
        
        if not audio_path:
            print(f"{Fore.RED}[FLOAT_IDLE] Failed to generate audio{Style.RESET_ALL}")
            return False
        
        # Update FLOAT reference image if we have a new one
        if self.current_reference_image and os.path.exists(self.current_reference_image):
            # Temporarily update FLOAT's reference image
            self.float_lipsync.update_reference_image(self.current_reference_image)
            print(f"{Fore.CYAN}[FLOAT_IDLE] Using reference: {os.path.basename(self.current_reference_image)}{Style.RESET_ALL}")
        
        # Generate FLOAT video with FULL PATH
        print(f"{Fore.CYAN}[FLOAT_IDLE] Running FLOAT generation...{Style.RESET_ALL}")
        
        # CRITICAL FIX: Pass full path instead of just filename
        output_filename = f"float_idle_{clip_num}.mp4"
        full_output_path = os.path.join(self.clips_dir, output_filename)
        
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Output path: {full_output_path}{Style.RESET_ALL}")
        
        video_path = self.float_lipsync.generate_lipsync(
            audio_path=audio_path,
            output_filename=full_output_path  # Pass full path!
        )
        
        # The daemon might return just filename or full path, handle both
        if video_path and not os.path.isabs(video_path):
            video_path = os.path.join(self.clips_dir, video_path)
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Corrected to full path: {video_path}{Style.RESET_ALL}")
        
        # Verify file exists
        if not video_path or not os.path.exists(video_path):
            print(f"{Fore.RED}[FLOAT_IDLE] Video not found at: {video_path}{Style.RESET_ALL}")
            
            # Debug: Check if file exists anywhere
            possible_locations = [
                os.path.join(self.clips_dir, output_filename),
                output_filename,  # Current directory
                os.path.join(os.getcwd(), output_filename),
            ]
            
            for loc in possible_locations:
                if os.path.exists(loc):
                    print(f"{Fore.GREEN}[FLOAT_IDLE] Found video at: {loc}{Style.RESET_ALL}")
                    # Move it to correct location
                    import shutil
                    shutil.move(loc, full_output_path)
                    video_path = full_output_path
                    break
            else:
                print(f"{Fore.RED}[FLOAT_IDLE] Failed to generate video{Style.RESET_ALL}")
                return False
        
        # Extract last frame for next clip
        last_frame = self.extract_last_frame(video_path)
        if last_frame:
            self.current_reference_image = last_frame
        
        # Add to ordered buffer
        with self.generation_lock:
            self.clips_buffer.append(video_path)
            self.clips_generated += 1
            
            # Clean up old frames (keep only last 5)
            self._cleanup_old_frames()
        
        buffer_size = len(self.clips_buffer)
        print(f"{Fore.GREEN}[FLOAT_IDLE] ✓ Clip generated (buffer: {buffer_size}/{self.max_clips}){Style.RESET_ALL}")
        
        return True
    
    def _cleanup_old_frames(self):
        """Clean up old reference frames, keeping only recent ones"""
        try:
            frames = sorted(Path(self.frames_dir).glob("last_frame_*.png"))
            # Keep only last 5 frames
            if len(frames) > 5:
                for frame in frames[:-5]:
                    try:
                        frame.unlink()
                    except:
                        pass
        except Exception as e:
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Cleanup error: {e}{Style.RESET_ALL}")
    
    def _generation_loop(self):
        """Background thread that generates clips continuously"""
        print(f"{Fore.GREEN}[FLOAT_IDLE] Generation loop started{Style.RESET_ALL}")
        
        while not self._stop_generation:
            with self.generation_lock:
                buffer_size = len(self.clips_buffer)
            
            # Stop if buffer is full
            if buffer_size >= self.max_clips:
                print(f"{Fore.YELLOW}[FLOAT_IDLE] Buffer full ({self.max_clips} clips), pausing generation{Style.RESET_ALL}")
                time.sleep(5)  # Wait before checking again
                continue
            
            # Generate next clip
            try:
                self._generate_single_clip()
            except Exception as e:
                print(f"{Fore.RED}[FLOAT_IDLE] Error in generation loop: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()
                time.sleep(1)
        
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Generation loop stopped{Style.RESET_ALL}")
    
    def start_generation(self):
        """Start background generation"""
        if self.is_generating:
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Generation already running{Style.RESET_ALL}")
            return
        
        self.is_generating = True
        self._stop_generation = False
        
        self.generation_thread = threading.Thread(target=self._generation_loop, daemon=True)
        self.generation_thread.start()
        
        print(f"{Fore.GREEN}[FLOAT_IDLE] Background generation started{Style.RESET_ALL}")
    
    def stop_generation(self):
        """Stop background generation"""
        if not self.is_generating:
            return
        
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Stopping generation...{Style.RESET_ALL}")
        self._stop_generation = True
        self.is_generating = False
        
        if self.generation_thread:
            self.generation_thread.join(timeout=2)
        
        print(f"{Fore.GREEN}[FLOAT_IDLE] Generation stopped{Style.RESET_ALL}")
    
    def get_next_clip(self) -> Optional[str]:
        """
        Get next clip in sequence.
        If next clip not ready, replay current clip for seamless loop.
        """
        with self.generation_lock:
            buffer_size = len(self.clips_buffer)
            
            if buffer_size == 0:
                print(f"{Fore.RED}[FLOAT_IDLE] No clips in buffer!{Style.RESET_ALL}")
                return None
            
            # Try to advance to next clip
            next_index = self.current_index + 1
            
            if next_index < buffer_size:
                # Next clip is ready - advance
                self.current_index = next_index
                clip_path = self.clips_buffer[self.current_index]
                print(f"{Fore.BLUE}[FLOAT_IDLE] Next clip: {os.path.basename(clip_path)} ({self.current_index + 1}/{buffer_size}){Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}[FLOAT_IDLE] Full path: {clip_path}{Style.RESET_ALL}")
                return clip_path
            else:
                # Next clip not ready - replay current for seamless loop
                clip_path = self.clips_buffer[self.current_index]
                self.clips_replayed += 1
                print(f"{Fore.YELLOW}[FLOAT_IDLE] Next clip not ready, replaying current: {os.path.basename(clip_path)}{Style.RESET_ALL}")
                print(f"{Fore.MAGENTA}[FLOAT_IDLE] Full path: {clip_path}{Style.RESET_ALL}")
                return clip_path
    
    def get_buffer_status(self) -> dict:
        """Get current buffer status"""
        with self.generation_lock:
            return {
                'buffer_size': len(self.clips_buffer),
                'current_index': self.current_index,
                'max_clips': self.max_clips,
                'clips_generated': self.clips_generated,
                'clips_replayed': self.clips_replayed,
                'is_generating': self.is_generating,
                'buffer_full': len(self.clips_buffer) >= self.max_clips
            }
    
    def reset_to_start(self):
        """Reset playback to first clip (useful for testing)"""
        with self.generation_lock:
            self.current_index = 0
            print(f"{Fore.CYAN}[FLOAT_IDLE] Reset to start{Style.RESET_ALL}")