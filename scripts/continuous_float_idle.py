# continuous_float_idle.py - Continuous Idle Generation with Frame Continuity
# UPDATED: Added Avatar-Specific Filenames to prevent browser caching issues

import os
import time
import threading
from pathlib import Path
from typing import Optional
from colorama import Fore, Style, init
import subprocess
import cv2
import shutil

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
        
        # Output directories - will be set per avatar
        self.base_output_dir = os.path.join(project_dir, "tempstream", "float_idle_clips")
        self.output_dir = None  # Will be set by set_active_avatar
        
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
        self.frames_dir = None  # Will be set per avatar
        
        # Avatar name for filenames
        self.current_avatar_name = "Default"
        
        print(f"{Fore.GREEN}[FLOAT_IDLE] Continuous system initialized{Style.RESET_ALL}")

    def set_active_avatar(self, avatar_name: str):
        """
        Update the avatar name and create avatar-specific directories.
        
        NOTE: When called during avatar switching, the generation_lock must already be held.
        When called during initialization, no lock is needed as no generation thread exists yet.
        """
        # Clean name to be file-safe
        safe_name = "".join([c for c in avatar_name if c.isalnum() or c in (' ', '_', '-')]).strip()
        self.current_avatar_name = safe_name.replace(" ", "_")
        
        # Create avatar-specific directories
        self.output_dir = os.path.join(self.base_output_dir, self.current_avatar_name)
        self.frames_dir = os.path.join(self.project_dir, "tempstream", "last_frames", self.current_avatar_name)
        
        # Ensure directories exist
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.frames_dir, exist_ok=True)
        
        print(f"{Fore.CYAN}[FLOAT_IDLE] Avatar set to: {self.current_avatar_name}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[FLOAT_IDLE] Output directory: {self.output_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[FLOAT_IDLE] Frames directory: {self.frames_dir}{Style.RESET_ALL}")

    def start_generation(self):
        """Start the background generation thread"""
        if self.is_generating:
            return
        
        # Ensure directories are created before starting generation
        if not self.output_dir:
            print(f"{Fore.YELLOW}[FLOAT_IDLE] No avatar set, using default 'Darwin'{Style.RESET_ALL}")
            self.set_active_avatar("Darwin")
            
        self._stop_generation = False
        self.is_generating = True
        self.generation_thread = threading.Thread(target=self._generation_loop, daemon=True)
        self.generation_thread.start()
        print(f"{Fore.GREEN}[FLOAT_IDLE] Background generation started{Style.RESET_ALL}")

    def stop_generation(self):
        """Stop the background generation thread"""
        self._stop_generation = True
        if self.generation_thread:
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Waiting for generation thread to finish (may take up to 5s)...{Style.RESET_ALL}")
            self.generation_thread.join(timeout=10.0)  # Increased to 10s (clips take ~3.5-4s)
            if self.generation_thread.is_alive():
                print(f"{Fore.RED}[FLOAT_IDLE] WARNING: Generation thread did not stop cleanly{Style.RESET_ALL}")
        self.is_generating = False
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Generation stopped{Style.RESET_ALL}")

    def _generation_loop(self):
        """Main loop that keeps the buffer full"""
        print(f"{Fore.CYAN}[FLOAT_IDLE] Generation loop started{Style.RESET_ALL}")
        
        while not self._stop_generation:
            with self.generation_lock:
                current_buffer_size = len(self.clips_buffer)
            
            # If buffer is full, sleep and wait
            if current_buffer_size >= self.max_clips:
                time.sleep(0.5)
                continue
            
            # Check stop flag again before expensive generation
            if self._stop_generation:
                break
                
            # Generate one clip
            try:
                self._generate_single_clip()
            except Exception as e:
                print(f"{Fore.RED}[FLOAT_IDLE] Generation error: {e}{Style.RESET_ALL}")
                time.sleep(1.0) # Pause on error
                
        print(f"{Fore.YELLOW}[FLOAT_IDLE] Generation loop stopped{Style.RESET_ALL}")

    def _generate_single_clip(self):
        """Generate a single idle clip and add to buffer"""
        # Ensure directories are set
        if not self.output_dir:
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Output directory not set, using default avatar{Style.RESET_ALL}")
            self.set_active_avatar("Darwin")
        
        clip_index = self.clips_generated
        
        print(f"\n{Fore.CYAN}[FLOAT_IDLE] Generating idle clip {clip_index + 1}...{Style.RESET_ALL}")
        
        # 1. Generate Silent Audio
        if self.use_ambient:
            audio_path = self.idle_audio_gen.generate_ambient_audio(self.clip_duration)
        else:
            audio_path = self.idle_audio_gen.generate_silent_audio(self.clip_duration)
            
        if not audio_path:
            print(f"{Fore.RED}[FLOAT_IDLE] Failed to generate audio{Style.RESET_ALL}")
            return

        # 2. Determine Reference Image (Continuity Logic)
        ref_image = self.current_reference_image
        
        # If no reference set (first run), use the one from FLOAT config via subprocess
        if not ref_image:
             # Just a placeholder, the subprocess handles the 'default' if we pass nothing, 
             # but strictly we should pass the last frame if we have it.
             pass 

        # 3. Generate Video using FLOAT Subprocess
        # Filename is simpler now since avatar name is in the directory path
        output_filename = f"idle_{clip_index}.mp4"
        output_path = os.path.join(self.output_dir, output_filename)
        
        print(f"{Fore.CYAN}[FLOAT_IDLE] Running FLOAT generation...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[FLOAT_IDLE] Output path: {output_path}{Style.RESET_ALL}")
        
        # CRITICAL: Log which reference image we're using
        if self.current_reference_image:
            print(f"{Fore.YELLOW}[FLOAT_IDLE] 🖼️  Using reference image: {self.current_reference_image}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[FLOAT_IDLE] 🖼️  Reference exists: {os.path.exists(self.current_reference_image)}{Style.RESET_ALL}")
            
            # DIAGNOSTIC: Check for path corruption
            print(f"{Fore.YELLOW}[FLOAT_IDLE] 🔍  Path repr: {repr(self.current_reference_image)}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[FLOAT_IDLE] 🔍  Path length: {len(self.current_reference_image)}{Style.RESET_ALL}")
            
            # If file doesn't exist, try to diagnose why
            if not os.path.exists(self.current_reference_image):
                print(f"{Fore.RED}[FLOAT_IDLE] ❌  FILE DOES NOT EXIST!{Style.RESET_ALL}")
                print(f"{Fore.RED}[FLOAT_IDLE] 🔍  Directory exists: {os.path.exists(os.path.dirname(self.current_reference_image))}{Style.RESET_ALL}")
                # List files in the directory
                dir_path = os.path.dirname(self.current_reference_image)
                if os.path.exists(dir_path):
                    files = os.listdir(dir_path)
                    print(f"{Fore.RED}[FLOAT_IDLE] 🔍  Files in directory: {files}{Style.RESET_ALL}")
            
            self.float_lipsync.update_reference_image(self.current_reference_image)
        else:
            print(f"{Fore.RED}[FLOAT_IDLE] ⚠️  NO REFERENCE IMAGE SET - using FLOAT default!{Style.RESET_ALL}")
        
        video_path = self.float_lipsync.generate_lipsync(
            audio_path=audio_path,
            output_filename=output_path
        )
        
        if video_path and os.path.exists(video_path):
            # 4. Extract Last Frame for Next Clip
            self._extract_last_frame(video_path, clip_index)
            
            # 5. Add to Buffer - CRITICAL SECTION (very short!)
            # DIAGNOSTIC: Log lock acquisition
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Acquiring lock to update buffer...{Style.RESET_ALL}")
            with self.generation_lock:
                self.clips_buffer.append(video_path)
                self.clips_generated += 1
                print(f"{Fore.YELLOW}[FLOAT_IDLE] Lock released after buffer update{Style.RESET_ALL}")
                
            print(f"{Fore.GREEN}[FLOAT_IDLE] ✓ Clip generated (buffer: {len(self.clips_buffer)}/{self.max_clips}){Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[FLOAT_IDLE] Video generation failed{Style.RESET_ALL}")

    def _extract_last_frame(self, video_path: str, index: int):
        """Extracts the last frame to use as reference for the next clip"""
        try:
            cap = cv2.VideoCapture(video_path)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                # Resize to 512x512 to ensure stability
                frame = cv2.resize(frame, (512, 512))
                
                # Save frame
                frame_filename = f"last_frame_{index}.png"
                frame_path = os.path.join(self.frames_dir, frame_filename)
                cv2.imwrite(frame_path, frame)
                
                # Update current reference for NEXT iteration
                self.current_reference_image = frame_path
                print(f"{Fore.CYAN}[FLOAT_IDLE] Extracted last frame (512x512) → {frame_filename}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[FLOAT_IDLE] Failed to extract last frame{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[FLOAT_IDLE] Frame extraction error: {e}{Style.RESET_ALL}")

    def _cleanup_old_frames(self):
        """Clean up temporary frames and videos for current avatar"""
        try:
            # Clean frames directory for current avatar
            if self.frames_dir and os.path.exists(self.frames_dir):
                for f in os.listdir(self.frames_dir):
                    file_path = os.path.join(self.frames_dir, f)
                    try:
                        os.remove(file_path)
                    except:
                        pass
            
            # Clean video clips for current avatar
            if self.output_dir and os.path.exists(self.output_dir):
                for f in os.listdir(self.output_dir):
                    file_path = os.path.join(self.output_dir, f)
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    
            print(f"{Fore.YELLOW}[FLOAT_IDLE] Temp files cleaned for {self.current_avatar_name}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[FLOAT_IDLE] Cleanup error: {e}{Style.RESET_ALL}")

    def get_next_clip(self) -> Optional[str]:
        """Get the next clip from the buffer (FIFO)"""
        with self.generation_lock:
            if not self.clips_buffer:
                print(f"{Fore.RED}[FLOAT_IDLE] No clips in buffer!{Style.RESET_ALL}")
                return None
            
            # Simple looping logic for now:
            # If we have clips, play them in order.
            # If we run out, maybe loop the last few? 
            # For now, let's just cycle through what we have if generation is slow.
            
            if self.current_index >= len(self.clips_buffer):
                # We reached the end of the buffer. 
                # If generation is working, we should wait? 
                # Or just loop the last one?
                # Let's loop the buffer for safety.
                self.current_index = 0
            
            if self.current_index < len(self.clips_buffer):
                clip_path = self.clips_buffer[self.current_index]
                
                # Check if file actually exists (user might have deleted it)
                if not os.path.exists(clip_path):
                     print(f"{Fore.RED}[FLOAT_IDLE] Clip missing on disk: {clip_path}{Style.RESET_ALL}")
                     # Try next one
                     self.current_index += 1
                     return self.get_next_clip()

                self.current_index += 1
                
                print(f"{Fore.BLUE}[FLOAT_IDLE] Next clip: {os.path.basename(clip_path)} ({self.current_index}/{len(self.clips_buffer)}){Style.RESET_ALL}")
                return clip_path
            
            return None
    
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