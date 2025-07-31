# node_video_system.py - Enhanced with multiple duration detection methods

import os
import json
import random
import threading
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

class NodeVideoSystem:
    def __init__(self, avatar_name: str = "Darwin"):
        self.avatar_name = avatar_name
        self.avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        self.nodes_dir = os.path.join(self.avatar_dir, "Nodes")
        self.node_config_path = os.path.join(self.avatar_dir, "node_network.json")
        
        # State management
        self.current_node = "node_1"  # Always start at main (node_1)
        self.nodes_data = {}
        self.is_playing = False
        self.is_interrupted = False
        self.play_thread = None
        self.video_ready_callback = None
        self.current_video_path = None
        
        # Duration cache to avoid repeated calculations
        self.duration_cache = {}
        
        # Load node configuration
        self.load_node_config()
        
        print(f"{Fore.GREEN}[NODE_SYSTEM] Initialized for avatar: {avatar_name}{Style.RESET_ALL}")

    def load_node_config(self):
        """Load node network configuration from JSON file"""
        try:
            with open(self.node_config_path, 'r') as f:
                config = json.load(f)
                self.nodes_data = config.get('nodes', {})
                
            print(f"{Fore.GREEN}[NODE_SYSTEM] Loaded {len(self.nodes_data)} nodes{Style.RESET_ALL}")
                
        except FileNotFoundError:
            print(f"{Fore.RED}[NODE_SYSTEM] Node config not found: {self.node_config_path}{Style.RESET_ALL}")
            # Create basic fallback structure
            self.nodes_data = {
                "node_1": {
                    "id": "node_1",
                    "name": "Main",
                    "connections": ["node_1"],  # Self-loop for main2main
                }
            }
        except json.JSONDecodeError as e:
            print(f"{Fore.RED}[NODE_SYSTEM] Invalid JSON in node config: {e}{Style.RESET_ALL}")
            self.nodes_data = {}

    def get_available_videos(self, from_node: str, to_node: str) -> List[str]:
        """Get all available video files for a specific transition"""
        # Map node IDs to directory names
        node_mapping = {
            "node_1": "main",
            "node_2": "standingMansion",
        }
        
        from_name = node_mapping.get(from_node, from_node.replace("node_", ""))
        to_name = node_mapping.get(to_node, to_node.replace("node_", ""))
        
        # Create transition directory name
        transition_dir = f"{from_name}2{to_name}"
        transition_path = os.path.join(self.nodes_dir, transition_dir)
        
        videos = []
        if os.path.exists(transition_path):
            for file in os.listdir(transition_path):
                if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    videos.append(os.path.join(transition_path, file))
        
        if videos:
            print(f"{Fore.GREEN}[NODE_SYSTEM] Found {len(videos)} videos for {from_name} -> {to_name}{Style.RESET_ALL}")
        
        return videos

    def get_next_node(self, current_node: str) -> str:
        """Determine the next node based on connections"""
        if current_node not in self.nodes_data:
            return "node_1"
        
        connections = self.nodes_data[current_node].get('connections', [])
        if not connections:
            return "node_1"
        
        next_node = random.choice(connections)
        print(f"{Fore.CYAN}[NODE_SYSTEM] {current_node} -> {next_node}{Style.RESET_ALL}")
        return next_node

    def get_next_video(self) -> Optional[str]:
        """Get the next video to play based on current node and transitions"""
        next_node = self.get_next_node(self.current_node)
        videos = self.get_available_videos(self.current_node, next_node)
        
        if videos:
            selected_video = random.choice(videos)
            self.current_node = next_node
            return selected_video
        else:
            print(f"{Fore.RED}[NODE_SYSTEM] No videos available for transition from {self.current_node}{Style.RESET_ALL}")
            return None

    def get_video_duration_opencv(self, video_path: str) -> Optional[float]:
        """Try to get video duration using OpenCV"""
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                
                if fps > 0 and frame_count > 0:
                    duration = frame_count / fps
                    cap.release()
                    return duration
                
                cap.release()
        except ImportError:
            pass
        except Exception as e:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] OpenCV duration failed: {e}{Style.RESET_ALL}")
        
        return None

    def get_video_duration_moviepy(self, video_path: str) -> Optional[float]:
        """Try to get video duration using moviepy"""
        try:
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(video_path)
            duration = clip.duration
            clip.close()
            return duration
        except ImportError:
            pass
        except Exception as e:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] MoviePy duration failed: {e}{Style.RESET_ALL}")
        
        return None

    def get_video_duration_ffprobe(self, video_path: str) -> Optional[float]:
        """Try to get video duration using ffprobe"""
        try:
            # Try different ffprobe paths for Windows
            ffprobe_paths = [
                'ffprobe',
                'ffprobe.exe',
                r'C:\ffmpeg\bin\ffprobe.exe',
                r'C:\Program Files\ffmpeg\bin\ffprobe.exe',
                r'C:\Program Files (x86)\ffmpeg\bin\ffprobe.exe'
            ]
            
            for ffprobe_path in ffprobe_paths:
                try:
                    cmd = [ffprobe_path, '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        import json
                        data = json.loads(result.stdout)
                        duration = float(data.get('format', {}).get('duration', 0))
                        
                        if duration > 0:
                            return duration
                except:
                    continue
                    
        except Exception as e:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] ffprobe failed: {e}{Style.RESET_ALL}")
        
        return None

    def get_video_duration_win32(self, video_path: str) -> Optional[float]:
        """Try to get video duration using Windows COM (Windows only)"""
        if os.name != 'nt':  # Only works on Windows
            return None
            
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            folder_path = os.path.dirname(video_path)
            file_name = os.path.basename(video_path)
            
            folder = shell.Namespace(folder_path)
            file_item = folder.ParseName(file_name)
            
            # Duration is usually property 27
            duration_str = folder.GetDetailsOf(file_item, 27)
            
            if duration_str:
                # Parse duration string (format: "00:00:07" or similar)
                parts = duration_str.split(':')
                if len(parts) >= 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    return total_seconds
                    
        except ImportError:
            pass
        except Exception as e:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] Win32 duration failed: {e}{Style.RESET_ALL}")
        
        return None

    def estimate_duration_from_size(self, video_path: str) -> float:
        """Estimate duration based on file size (last resort)"""
        try:
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            
            # Better estimation based on typical bitrates
            # Assume average bitrate of ~2 Mbps for standard videos
            estimated_bitrate_mbps = 2.0
            estimated_duration = (file_size_mb * 8) / estimated_bitrate_mbps
            
            # Apply reasonable bounds
            estimated_duration = max(1.0, min(30.0, estimated_duration))
            
            return estimated_duration
        except:
            return 5.0  # Default fallback

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration using multiple methods with caching"""
        # Check cache first
        if video_path in self.duration_cache:
            cached_duration = self.duration_cache[video_path]
            print(f"{Fore.GREEN}[NODE_SYSTEM] Cached duration: {cached_duration:.2f}s for {os.path.basename(video_path)}{Style.RESET_ALL}")
            return cached_duration
        
        print(f"{Fore.CYAN}[NODE_SYSTEM] Detecting duration for: {os.path.basename(video_path)}{Style.RESET_ALL}")
        
        # Try multiple methods in order of preference
        methods = [
            ("OpenCV", self.get_video_duration_opencv),
            ("MoviePy", self.get_video_duration_moviepy),
            ("FFprobe", self.get_video_duration_ffprobe),
            ("Win32", self.get_video_duration_win32),
        ]
        
        for method_name, method_func in methods:
            duration = method_func(video_path)
            if duration and duration > 0:
                print(f"{Fore.GREEN}[NODE_SYSTEM] {method_name} duration: {duration:.2f}s for {os.path.basename(video_path)}{Style.RESET_ALL}")
                self.duration_cache[video_path] = duration
                return duration
        
        # Fallback to estimation
        print(f"{Fore.YELLOW}[NODE_SYSTEM] All methods failed, estimating duration{Style.RESET_ALL}")
        estimated = self.estimate_duration_from_size(video_path)
        print(f"{Fore.YELLOW}[NODE_SYSTEM] Estimated duration: {estimated:.2f}s (based on {os.path.getsize(video_path) / (1024*1024):.1f}MB){Style.RESET_ALL}")
        
        # Don't cache estimates
        return estimated

    def start_idle_playing(self, video_callback):
        """Start the idle video playing system"""
        self.video_ready_callback = video_callback
        
        # Stop any existing playback
        if self.is_playing:
            self.stop_playing()
            time.sleep(0.5)
        
        # Reset to main node
        self.current_node = "node_1"
        self.is_playing = True
        self.is_interrupted = False
        
        print(f"{Fore.GREEN}[NODE_SYSTEM] Starting idle video playback from {self.current_node}{Style.RESET_ALL}")
        
        # Start the video playing thread
        self.play_thread = threading.Thread(target=self._video_play_loop, daemon=True)
        self.play_thread.start()

    def _video_play_loop(self):
        """Main video playing loop"""
        while self.is_playing and not self.is_interrupted:
            try:
                video_path = self.get_next_video()
                
                if video_path and os.path.exists(video_path):
                    print(f"{Fore.BLUE}[NODE_SYSTEM] Playing: {os.path.basename(video_path)} (Node: {self.current_node}){Style.RESET_ALL}")
                    
                    self.current_video_path = video_path
                    
                    if self.video_ready_callback:
                        self.video_ready_callback(video_path)
                    
                    # Get duration and wait
                    duration = self.get_video_duration(video_path)
                    total_wait = duration + 0.5  # Add buffer
                    
                    print(f"{Fore.MAGENTA}[NODE_SYSTEM] Waiting {total_wait:.2f}s for video to complete{Style.RESET_ALL}")
                    
                    # Wait with interruption checking
                    start_time = time.time()
                    while time.time() - start_time < total_wait:
                        if self.is_interrupted:
                            print(f"{Fore.YELLOW}[NODE_SYSTEM] Video interrupted{Style.RESET_ALL}")
                            return
                        time.sleep(0.1)
                    
                else:
                    print(f"{Fore.RED}[NODE_SYSTEM] No video available, waiting...{Style.RESET_ALL}")
                    time.sleep(2)
                    
            except Exception as e:
                print(f"{Fore.RED}[NODE_SYSTEM] Error in video loop: {e}{Style.RESET_ALL}")
                time.sleep(1)

    def interrupt_for_response(self):
        """Interrupt idle playing for user response"""
        print(f"{Fore.YELLOW}[NODE_SYSTEM] Interrupting for response{Style.RESET_ALL}")
        self.is_interrupted = True

    def stop_playing(self):
        """Stop all video playing"""
        self.is_playing = False
        self.is_interrupted = True
        
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=2)

    def return_to_main_path(self) -> List[str]:
        """Get videos to return to main node"""
        if self.current_node == "node_1":
            return []  # Already at main
        
        videos = self.get_available_videos(self.current_node, "node_1")
        if videos:
            self.current_node = "node_1"
            return [random.choice(videos)]
        else:
            self.current_node = "node_1"
            return []

    def get_system_status(self) -> Dict:
        """Get current system status"""
        return {
            "current_node": self.current_node,
            "is_playing": self.is_playing,
            "is_interrupted": self.is_interrupted,
            "current_video": os.path.basename(self.current_video_path) if self.current_video_path else None,
            "available_nodes": list(self.nodes_data.keys()),
            "duration_cache_size": len(self.duration_cache),
        }