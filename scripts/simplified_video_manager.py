# simplified_video_manager.py - Python-only video control (FIXED VERSION)

import os
import json
import random
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

class SimplifiedVideoManager:
    """Simplified video manager with Python-only control"""
    
    def __init__(self, avatar_name: str = "Darwin"):
        self.avatar_name = avatar_name
        self.avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        
        # Video directories
        self.idle_videos_dir = os.path.join(self.avatar_dir, "Nodes", "main2main")
        self.pregenerated_dir = os.path.join(self.avatar_dir, "pre-generated responses")
        self.idle_chunks_dir = os.path.join(self.avatar_dir, "idle_chunks") # <<< NEW
        self.lipsync_output_dir = os.path.join(PROJECT_DIR, "tempstream")
        
        # State management - SIMPLIFIED
        self.current_mode = "idle"  # "idle", "pregenerated", "lipsync", or "idle_chunk" # <<< UPDATED
        self.current_video_path = None
        self.video_update_callback = None  # Function to call when video needs updating
        
        # Pre-generated response queue
        self.pregenerated_pending = False
        
        # Ensure output directory exists
        os.makedirs(self.lipsync_output_dir, exist_ok=True)
        
        print(f"{Fore.GREEN}[VIDEO_MANAGER] Initialized Python-only video control{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Idle videos: {self.idle_videos_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Pre-generated: {self.pregenerated_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Idle Chunks: {self.idle_chunks_dir}{Style.RESET_ALL}") # <<< NEW
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Found {len(self.get_idle_videos())} idle videos{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Found {len(self.get_pregenerated_videos())} pre-generated videos{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Found {len(self.get_idle_chunk_videos())} idle chunk videos{Style.RESET_ALL}") # <<< NEW


    def set_video_update_callback(self, callback):
        """Set the callback function for updating video in UI"""
        self.video_update_callback = callback
        print(f"{Fore.GREEN}[VIDEO_MANAGER] Video update callback registered{Style.RESET_ALL}")

    def get_idle_videos(self) -> List[str]:
        """Get all available idle videos from main2main folder"""
        videos = []
        
        if os.path.exists(self.idle_videos_dir):
            for file in os.listdir(self.idle_videos_dir):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(self.idle_videos_dir, file))
        
        return videos

    def get_pregenerated_videos(self) -> List[str]:
        """Get all available pre-generated response videos"""
        videos = []
        
        if os.path.exists(self.pregenerated_dir):
            for file in os.listdir(self.pregenerated_dir):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(self.pregenerated_dir, file))
        
        return videos

    # <<< NEW FUNCTION >>>
    def get_idle_chunk_videos(self) -> List[str]:
        """Get all available idle_chunk videos"""
        videos = []
        
        if os.path.exists(self.idle_chunks_dir):
            for file in os.listdir(self.idle_chunks_dir):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(self.idle_chunks_dir, file))
        
        return videos

    def get_random_idle_video(self) -> Optional[str]:
        """Get a random idle video path"""
        videos = self.get_idle_videos()
        if videos:
            video = random.choice(videos)
            print(f"{Fore.BLUE}[VIDEO_MANAGER] Selected idle video: {os.path.basename(video)}{Style.RESET_ALL}")
            return video
        return None

    def get_random_pregenerated_video(self) -> Optional[str]:
        """Get a random pre-generated response video"""
        videos = self.get_pregenerated_videos()
        if videos:
            video = random.choice(videos)
            print(f"{Fore.MAGENTA}[VIDEO_MANAGER] Selected pre-generated response: {os.path.basename(video)}{Style.RESET_ALL}")
            return video
        return None

    # <<< NEW FUNCTION >>>
    def get_random_idle_chunk_video(self) -> Optional[str]:
        """Get a random idle_chunk video path"""
        videos = self.get_idle_chunk_videos()
        if videos:
            video = random.choice(videos)
            print(f"{Fore.BLUE}[VIDEO_MANAGER] Selected idle_chunk video: {os.path.basename(video)}{Style.RESET_ALL}")
            return video
        return None

    def play_next_idle_video(self):
        """Play the next idle video - PYTHON DECIDES EVERYTHING"""
        self.current_mode = "idle"
        video_path = self.get_random_idle_video()
        
        if video_path:
            self.current_video_path = video_path
            self._update_video_in_ui(video_path)
            return True
        return False

    # <<< NEW FUNCTION >>>
    def play_next_idle_chunk_video(self):
        """Play the next idle_chunk video (the 'thinking' loop)"""
        self.current_mode = "idle_chunk"
        video_path = self.get_random_idle_chunk_video()
        
        if video_path:
            self.current_video_path = video_path
            self._update_video_in_ui(video_path)
            return True
        else:
            # Fallback to normal idle if idle_chunks is empty
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] No idle_chunk videos found, playing normal idle instead{Style.RESET_ALL}")
            return self.play_next_idle_video()

    def queue_pregenerated_response(self):
        """Queue a pre-generated response to play after current video ends"""
        print(f"{Fore.YELLOW}[VIDEO_MANAGER] Pre-generated response queued for next video end{Style.RESET_ALL}")
        self.pregenerated_pending = True

    def play_pregenerated_video(self):
        """Play a random pre-generated response video"""
        video_path = self.get_random_pregenerated_video()
        
        if video_path:
            self.current_mode = "pregenerated"
            self.current_video_path = video_path
            self.pregenerated_pending = False
            self._update_video_in_ui(video_path)
            print(f"{Fore.MAGENTA}[VIDEO_MANAGER] Playing pre-generated response: {os.path.basename(video_path)}{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] No pre-generated videos available, playing idle instead{Style.RESET_ALL}")
            self.pregenerated_pending = False
            return self.play_next_idle_video()

    def play_lipsync_video(self, video_path: str):
        """Play a lip-sync video"""
        if os.path.exists(video_path):
            self.current_mode = "lipsync"
            self.current_video_path = video_path
            self._update_video_in_ui(video_path)
            print(f"{Fore.GREEN}[VIDEO_MANAGER] Playing lipsync: {os.path.basename(video_path)}{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.RED}[VIDEO_MANAGER] Lipsync video not found: {video_path}{Style.RESET_ALL}")
            return False

    def on_video_ended(self):
        """Called when ANY video ends - Python decides what's next"""
        print(f"{Fore.BLUE}[VIDEO_MANAGER] Video ended, mode was: {self.current_mode}{Style.RESET_ALL}")
        
        # Priority 1: Play pre-generated response if queued
        if self.pregenerated_pending:
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] Playing queued pre-generated response{Style.RESET_ALL}")
            self.play_pregenerated_video()
            return
        
        # Priority 2: After pre-generated, lipsync, OR idle_chunk, return to idle
        # Note: The main app's 'handle_video_ended_in_context' will intercept
        # lipsync and idle_chunk modes BEFORE this function is ever called
        # for them. This is just a safety fallback.
        if self.current_mode in ["lipsync", "pregenerated", "idle_chunk"]:
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] {self.current_mode.capitalize()} finished, returning to idle{Style.RESET_ALL}")
        
        # Default: Play idle video
        self.play_next_idle_video()

    def _update_video_in_ui(self, video_path: str):
        """Update the video in the UI using event queue"""
        if self.video_update_callback and video_path:
            try:
                rel_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
                video_url = f"/{rel_path}"
                
                # Use the callback (which will queue the event)
                self.video_update_callback(video_url)
                
            except Exception as e:
                print(f"{Fore.RED}[VIDEO_MANAGER] Error updating UI: {e}{Style.RESET_ALL}")

    def cleanup_old_lipsync_videos(self, keep_last: int = 5):
        """Clean up old lip-sync videos to save space"""
        if not os.path.exists(self.lipsync_output_dir):
            return
        
        try:
            # Get all lip-sync videos
            videos = []
            for file in os.listdir(self.lipsync_output_dir):
                if file.endswith('.mp4') or file.endswith('.wav'):
                    file_path = os.path.join(self.lipsync_output_dir, file)
                    videos.append((file_path, os.path.getmtime(file_path)))
            
            # Sort by modification time (newest first)
            videos.sort(key=lambda x: x[1], reverse=True)
            
            # Delete old files
            for file_path, _ in videos[keep_last:]:
                try:
                    os.remove(file_path)
                    print(f"{Fore.YELLOW}[VIDEO_MANAGER] Cleaned up: {os.path.basename(file_path)}{Style.RESET_ALL}")
                except:
                    pass
                    
        except Exception as e:
            print(f"{Fore.RED}[VIDEO_MANAGER] Error cleaning up files: {e}{Style.RESET_ALL}")

    def get_status(self) -> Dict:
        """Get current system status"""
        return {
            "mode": self.current_mode,
            "current_video": os.path.basename(self.current_video_path) if self.current_video_path else None,
            "idle_videos_count": len(self.get_idle_videos()),
            "pregenerated_pending": self.pregenerated_pending,
            "pregenerated_videos_count": len(self.get_pregenerated_videos()),
            "idle_chunks_count": len(self.get_idle_chunk_videos()) # <<< NEW
        }