# float_video_manager.py - Video Manager with Continuous FLOAT Idle Support

import os
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

class FloatVideoManager:
    """
    Video manager with continuous FLOAT idle clip generation and playback.
    
    Modes:
    - "float_idle": Continuously playing FLOAT-generated idle clips
    - "speech_reaction": User is typing/speaking
    - "pregenerated": Quick pre-generated response
    - "lipsync": Full lip-sync response
    """
    
    def __init__(self, avatar_name: str = "Darwin", continuous_idle_system=None):
        self.avatar_name = avatar_name
        self.avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        
        # Video directories (kept for backwards compatibility)
        self.pregenerated_dir = os.path.join(self.avatar_dir, "pre-generated responses")
        self.speech_reaction_dir = os.path.join(self.avatar_dir, "speech_reaction")
        self.lipsync_output_dir = os.path.join(PROJECT_DIR, "tempstream")
        
        # Continuous FLOAT idle system
        self.continuous_idle = continuous_idle_system
        
        # State management
        self.current_mode = "float_idle"  # "float_idle", "pregenerated", "lipsync", or "speech_reaction"
        self.current_video_path = None
        self.video_update_callback = None
        
        # Pre-generated response queue
        self.pregenerated_pending = False
        
        # USER ACTIVITY TRACKING
        self.user_is_active = False
        self.activity_start_time = None
        self.activity_timer = None
        self.activity_lock = threading.Lock()
        self.ACTIVITY_DELAY = 2.0  # seconds before triggering reaction
        
        # VIDEO SPEEDUP STATE
        self.speedup_requested = False
        self.speedup_lock = threading.Lock()
        
        # Ensure output directory exists
        os.makedirs(self.lipsync_output_dir, exist_ok=True)
        
        print(f"{Fore.GREEN}[VIDEO_MANAGER] Initialized with continuous FLOAT idle{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Pre-generated: {self.pregenerated_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Speech Reaction: {self.speech_reaction_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Found {len(self.get_pregenerated_videos())} pre-generated videos{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[VIDEO_MANAGER] Found {len(self.get_speech_reaction_videos())} speech reaction videos{Style.RESET_ALL}")

    def set_video_update_callback(self, callback):
        """Set the callback function for updating video in UI"""
        self.video_update_callback = callback
        print(f"{Fore.GREEN}[VIDEO_MANAGER] Video update callback registered{Style.RESET_ALL}")

    def get_pregenerated_videos(self) -> List[str]:
        """Get all available pre-generated response videos"""
        videos = []
        if os.path.exists(self.pregenerated_dir):
            for file in os.listdir(self.pregenerated_dir):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(self.pregenerated_dir, file))
        return videos

    def get_speech_reaction_videos(self) -> List[str]:
        """Get all available speech_reaction videos"""
        videos = []
        if os.path.exists(self.speech_reaction_dir):
            for file in os.listdir(self.speech_reaction_dir):
                if file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(self.speech_reaction_dir, file))
        return videos

    def get_random_pregenerated_video(self) -> Optional[str]:
        """Get a random pre-generated response video"""
        videos = self.get_pregenerated_videos()
        if videos:
            video = random.choice(videos)
            print(f"{Fore.MAGENTA}[VIDEO_MANAGER] Selected pre-generated response: {os.path.basename(video)}{Style.RESET_ALL}")
            return video
        return None

    def get_random_speech_reaction_video(self) -> Optional[str]:
        """Get a random speech_reaction video path"""
        videos = self.get_speech_reaction_videos()
        if videos:
            video = random.choice(videos)
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] Selected speech_reaction video: {os.path.basename(video)}{Style.RESET_ALL}")
            return video
        return None

    # ========== USER ACTIVITY TRACKING ==========
    
    def start_user_activity(self):
        """Called when user starts typing or speaking"""
        with self.activity_lock:
            if not self.user_is_active:
                self.user_is_active = True
                self.activity_start_time = time.time()
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] User activity started{Style.RESET_ALL}")
                
                # Cancel any existing timer
                if self.activity_timer:
                    self.activity_timer.cancel()
                
                # Start 2-second timer
                self.activity_timer = threading.Timer(self.ACTIVITY_DELAY, self._trigger_reaction_mode)
                self.activity_timer.start()

    def stop_user_activity(self):
        """Called when user stops typing or speaking"""
        with self.activity_lock:
            if self.user_is_active:
                self.user_is_active = False
                self.activity_start_time = None
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] User activity stopped{Style.RESET_ALL}")
                
                # Cancel the timer if it hasn't fired yet
                if self.activity_timer:
                    self.activity_timer.cancel()
                    self.activity_timer = None

    def _trigger_reaction_mode(self):
        """Called when activity timer expires (user has been active for ACTIVITY_DELAY seconds)"""
        with self.activity_lock:
            if self.user_is_active and self.current_mode == "float_idle":
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] Triggering speech reaction mode{Style.RESET_ALL}")
                # Only switch if currently in idle mode
                self.play_next_speech_reaction_video()

    # ========== VIDEO SPEEDUP SYSTEM ==========

    def request_speedup(self):
        """Request video speedup (for when content is ready)"""
        with self.speedup_lock:
            if not self.speedup_requested:
                self.speedup_requested = True
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] Video speedup requested{Style.RESET_ALL}")
                
                # Send speedup command to UI
                if self.video_update_callback:
                    try:
                        self.video_update_callback(f"SPEEDUP:1.5")
                    except Exception as e:
                        print(f"{Fore.RED}[VIDEO_MANAGER] Error requesting speedup: {e}{Style.RESET_ALL}")
                        self.speedup_requested = False

    def request_speedup_for_content(self):
        """Request speedup when lipsync content is ready to play (only for float_idle)"""
        if self.current_mode == "float_idle":
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] Content ready - speeding up current idle video{Style.RESET_ALL}")
            self.request_speedup()
        else:
            print(f"{Fore.BLUE}[VIDEO_MANAGER] Content ready but in {self.current_mode} mode - not speeding up{Style.RESET_ALL}")

    # ========== VIDEO PLAYBACK METHODS ==========

    def play_next_float_idle_clip(self):
        """Play the next FLOAT idle clip from the continuous generation system"""
        self.current_mode = "float_idle"
        
        if self.continuous_idle:
            video_path = self.continuous_idle.get_next_clip()
            
            if video_path:
                self.current_video_path = video_path
                self._update_video_in_ui(video_path)
                print(f"{Fore.BLUE}[VIDEO_MANAGER] Playing FLOAT idle clip: {os.path.basename(video_path)}{Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] No FLOAT idle clips available yet{Style.RESET_ALL}")
                return False
        else:
            print(f"{Fore.RED}[VIDEO_MANAGER] Continuous idle system not initialized{Style.RESET_ALL}")
            return False

    def play_next_speech_reaction_video(self):
        """Play a random speech_reaction video"""
        self.current_mode = "speech_reaction"
        video_path = self.get_random_speech_reaction_video()
        
        if video_path:
            self.current_video_path = video_path
            self._update_video_in_ui(video_path)
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] Playing speech_reaction video: {os.path.basename(video_path)}{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] No speech_reaction videos found, playing FLOAT idle instead{Style.RESET_ALL}")
            return self.play_next_float_idle_clip()

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
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] No pre-generated videos available, playing FLOAT idle instead{Style.RESET_ALL}")
            self.pregenerated_pending = False
            return self.play_next_float_idle_clip()

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
        
        # Reset speedup flag
        with self.speedup_lock:
            self.speedup_requested = False
        
        # Cancel any pending activity timer to prevent speedup on wrong video
        with self.activity_lock:
            if self.activity_timer:
                self.activity_timer.cancel()
                self.activity_timer = None
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] Cancelled pending activity timer{Style.RESET_ALL}")
        
        # Priority 1: Play pre-generated response if queued
        if self.pregenerated_pending:
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] Playing queued pre-generated response{Style.RESET_ALL}")
            self.play_pregenerated_video()
            return
        
        # Priority 2: If user is still active, play speech_reaction
        with self.activity_lock:
            if self.user_is_active and self.current_mode in ["float_idle", "speech_reaction"]:
                print(f"{Fore.YELLOW}[VIDEO_MANAGER] User still active, playing speech_reaction{Style.RESET_ALL}")
                self.play_next_speech_reaction_video()
                return
        
        # Priority 3: After lipsync, pregenerated, or speech_reaction, return to FLOAT idle
        if self.current_mode in ["lipsync", "pregenerated", "speech_reaction"]:
            print(f"{Fore.YELLOW}[VIDEO_MANAGER] {self.current_mode.capitalize()} finished, returning to FLOAT idle{Style.RESET_ALL}")
        
        # Default: Play next FLOAT idle clip
        self.play_next_float_idle_clip()

    def _update_video_in_ui(self, video_path: str):
        """Update the video in the UI using event queue"""
        if self.video_update_callback and video_path:
            try:
                rel_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
                video_url = f"/{rel_path}"
                self.video_update_callback(video_url)
            except Exception as e:
                print(f"{Fore.RED}[VIDEO_MANAGER] Error updating UI: {e}{Style.RESET_ALL}")

    def cleanup_old_lipsync_videos(self, keep_last: int = 5):
        """Clean up old lip-sync videos to save space"""
        if not os.path.exists(self.lipsync_output_dir):
            return
        
        try:
            videos = []
            for file in os.listdir(self.lipsync_output_dir):
                if file.endswith('.mp4') or file.endswith('.wav'):
                    file_path = os.path.join(self.lipsync_output_dir, file)
                    videos.append((file_path, os.path.getmtime(file_path)))
            
            videos.sort(key=lambda x: x[1], reverse=True)
            
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
        idle_status = self.continuous_idle.get_buffer_status() if self.continuous_idle else {}
        
        return {
            "mode": self.current_mode,
            "current_video": os.path.basename(self.current_video_path) if self.current_video_path else None,
            "pregenerated_pending": self.pregenerated_pending,
            "pregenerated_videos_count": len(self.get_pregenerated_videos()),
            "speech_reaction_count": len(self.get_speech_reaction_videos()),
            "user_is_active": self.user_is_active,
            "speedup_requested": self.speedup_requested,
            "idle_buffer_size": idle_status.get('buffer_size', 0),
            "idle_clips_generated": idle_status.get('clips_generated', 0),
            "idle_is_generating": idle_status.get('is_generating', False)
        }
