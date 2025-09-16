# simplified_video_manager.py - Simplified playlist-based video system

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
    """Simplified video manager using playlist approach"""
    
    def __init__(self, avatar_name: str = "Darwin"):
        self.avatar_name = avatar_name
        self.avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        
        # Video directories
        self.idle_videos_dir = os.path.join(self.avatar_dir, "Nodes", "main2main")
        self.lipsync_output_dir = os.path.join(PROJECT_DIR, "tempstream")
        
        # State management
        self.current_mode = "idle"  # "idle" or "lipsync"
        self.is_playing = False
        self.current_video_path = None
        self.next_video_path = None  # Queue next video
        
        # Ensure output directory exists
        os.makedirs(self.lipsync_output_dir, exist_ok=True)
        
        print(f"{Fore.GREEN}[VIDEO_MANAGER] Initialized simplified video system{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Idle videos: {self.idle_videos_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Found {len(self.get_idle_videos())} idle videos{Style.RESET_ALL}")

    def get_idle_videos(self) -> List[str]:
        """Get all available idle videos from main2main folder"""
        videos = []
        
        if os.path.exists(self.idle_videos_dir):
            for file in os.listdir(self.idle_videos_dir):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(self.idle_videos_dir, file))
        
        return videos

    def get_random_idle_video(self) -> Optional[str]:
        """Get a random idle video path"""
        videos = self.get_idle_videos()
        if videos:
            video = random.choice(videos)
            print(f"{Fore.BLUE}[VIDEO_MANAGER] Selected idle video: {os.path.basename(video)}{Style.RESET_ALL}")
            return video
        return None

    def get_next_idle_video(self) -> Optional[str]:
        """Get the next idle video to play"""
        self.current_mode = "idle"
        return self.get_random_idle_video()

    def queue_lipsync_video(self, video_path: str):
        """Queue a lip-sync video to play next"""
        if os.path.exists(video_path):
            self.current_mode = "lipsync"
            self.next_video_path = video_path
            print(f"{Fore.GREEN}[VIDEO_MANAGER] Queued lipsync video: {os.path.basename(video_path)}{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.RED}[VIDEO_MANAGER] Lipsync video not found: {video_path}{Style.RESET_ALL}")
            return False

    def get_current_video_url(self) -> Optional[str]:
        """Get the current video URL for the UI"""
        # If there's a queued lipsync video, return it and clear the queue
        if self.next_video_path and self.current_mode == "lipsync":
            video_path = self.next_video_path
            self.current_video_path = video_path
            self.next_video_path = None
            
            # Convert to relative path for web serving
            rel_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
            return f"/{rel_path}"
        
        # Otherwise return current video
        if self.current_video_path:
            rel_path = os.path.relpath(self.current_video_path, PROJECT_DIR).replace('\\', '/')
            return f"/{rel_path}"
        
        return None

    def should_return_to_idle(self) -> bool:
        """Check if we should return to idle mode"""
        return self.current_mode == "lipsync" and self.next_video_path is None

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
            "queued_video": os.path.basename(self.next_video_path) if self.next_video_path else None,
            "idle_videos_count": len(self.get_idle_videos())
        }