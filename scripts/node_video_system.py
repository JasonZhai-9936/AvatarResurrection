# node_video_system.py - Node-based video system for avatar idle animations and transitions

import os
import json
import random
import threading
import time
import asyncio
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
        self.video_queue = []
        self.play_thread = None
        self.video_ready_callback = None
        self.current_video_path = None
        
        # Load node configuration
        self.load_node_config()
        
        print(f"{Fore.GREEN}[NODE_SYSTEM] Initialized for avatar: {avatar_name}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[NODE_SYSTEM] Nodes directory: {self.nodes_dir}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}[NODE_SYSTEM] Starting node: {self.current_node}{Style.RESET_ALL}")

    def load_node_config(self):
        """Load node network configuration from JSON file"""
        try:
            with open(self.node_config_path, 'r') as f:
                config = json.load(f)
                self.nodes_data = config.get('nodes', {})
                
            print(f"{Fore.GREEN}[NODE_SYSTEM] Loaded {len(self.nodes_data)} nodes{Style.RESET_ALL}")
            
            # Debug: Print available nodes
            for node_id, node_data in self.nodes_data.items():
                connections = node_data.get('connections', [])
                print(f"{Fore.YELLOW}[NODE_SYSTEM] {node_id}: {node_data.get('name')} -> {connections}{Style.RESET_ALL}")
                
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
        # Map node IDs to directory names (based on your structure)
        node_mapping = {
            "node_1": "main",
            "node_2": "standingMansion",
            # Add more mappings based on your actual nodes
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
        
        if not videos:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] No videos found for {from_name} -> {to_name} in {transition_path}{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}[NODE_SYSTEM] Found {len(videos)} videos for {from_name} -> {to_name}{Style.RESET_ALL}")
        
        return videos

    def get_next_node(self, current_node: str) -> str:
        """Determine the next node based on connections and probabilities"""
        if current_node not in self.nodes_data:
            print(f"{Fore.RED}[NODE_SYSTEM] Node {current_node} not found, returning to main{Style.RESET_ALL}")
            return "node_1"
        
        connections = self.nodes_data[current_node].get('connections', [])
        if not connections:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] No connections for {current_node}, returning to main{Style.RESET_ALL}")
            return "node_1"
        
        # For now, use random selection. You can add weighted probabilities later
        next_node = random.choice(connections)
        print(f"{Fore.CYAN}[NODE_SYSTEM] {current_node} -> {next_node}{Style.RESET_ALL}")
        return next_node

    def get_next_video(self) -> Optional[str]:
        """Get the next video to play based on current node and transitions"""
        next_node = self.get_next_node(self.current_node)
        videos = self.get_available_videos(self.current_node, next_node)
        
        if videos:
            selected_video = random.choice(videos)
            # Update current node after selecting video
            self.current_node = next_node
            return selected_video
        else:
            # Fallback: try to stay in current node (self-loop)
            self_videos = self.get_available_videos(self.current_node, self.current_node)
            if self_videos:
                return random.choice(self_videos)
            else:
                print(f"{Fore.RED}[NODE_SYSTEM] No videos available for any transition from {self.current_node}{Style.RESET_ALL}")
                return None

    def return_to_main_path(self) -> List[str]:
        """Calculate the fastest path back to main node and return video sequence"""
        if self.current_node == "node_1":
            return []  # Already at main
        
        # For now, implement a simple direct path
        # In a more complex system, you'd use pathfinding algorithms
        videos = self.get_available_videos(self.current_node, "node_1")
        
        if videos:
            # Direct path available
            self.current_node = "node_1"
            return [random.choice(videos)]
        else:
            # No direct path, might need multi-step (implement if needed)
            print(f"{Fore.YELLOW}[NODE_SYSTEM] No direct path to main from {self.current_node}{Style.RESET_ALL}")
            # Force return to main for now
            self.current_node = "node_1"
            return []

    def start_idle_playing(self, video_callback):
        """Start the idle video playing system"""
        self.video_ready_callback = video_callback
        
        # Stop any existing playback
        if self.is_playing:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] Stopping existing playback before starting new session{Style.RESET_ALL}")
            self.stop_playing()
            time.sleep(0.5)  # Brief pause
        
        # Reset to main node (node_1) to ensure consistent starting point
        self.current_node = "node_1"
        self.is_playing = True
        self.is_interrupted = False
        
        print(f"{Fore.GREEN}[NODE_SYSTEM] Starting idle video playback from {self.current_node}{Style.RESET_ALL}")
        
        # Start the video playing thread
        self.play_thread = threading.Thread(target=self._video_play_loop, daemon=True)
        self.play_thread.start()

    def _video_play_loop(self):
        """Main video playing loop (runs in separate thread)"""
        while self.is_playing and not self.is_interrupted:
            try:
                video_path = self.get_next_video()
                
                if video_path and os.path.exists(video_path):
                    print(f"{Fore.BLUE}[NODE_SYSTEM] Playing: {os.path.basename(video_path)} (Node: {self.current_node}){Style.RESET_ALL}")
                    
                    # Store current video path
                    self.current_video_path = video_path
                    
                    # Call the callback to update UI
                    if self.video_ready_callback:
                        self.video_ready_callback(video_path)
                    
                    # Get video duration and wait
                    duration = self._get_video_duration(video_path)
                    
                    # Add a small buffer to ensure video completes
                    buffer_time = 0.5  # 500ms buffer
                    total_wait_time = duration + buffer_time
                    
                    print(f"{Fore.MAGENTA}[NODE_SYSTEM] Waiting {total_wait_time:.2f}s for video to complete (duration: {duration:.2f}s + buffer: {buffer_time}s){Style.RESET_ALL}")
                    
                    # Wait for video to complete, but check for interruption frequently
                    start_time = time.time()
                    while time.time() - start_time < total_wait_time:
                        if self.is_interrupted:
                            print(f"{Fore.YELLOW}[NODE_SYSTEM] Video playback interrupted after {time.time() - start_time:.2f}s{Style.RESET_ALL}")
                            return
                        time.sleep(0.1)  # Check every 100ms
                    
                    print(f"{Fore.GREEN}[NODE_SYSTEM] Video completed after {total_wait_time:.2f}s{Style.RESET_ALL}")
                    
                else:
                    print(f"{Fore.RED}[NODE_SYSTEM] No video available, waiting...{Style.RESET_ALL}")
                    time.sleep(2)  # Wait before trying again
                    
            except Exception as e:
                print(f"{Fore.RED}[NODE_SYSTEM] Error in video play loop: {e}{Style.RESET_ALL}")
                time.sleep(1)

    def _get_video_duration(self, video_path: str) -> float:
        """Get actual video duration in seconds using ffprobe"""
        try:
            import subprocess
            import json
            
            # Use ffprobe to get video duration
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data.get('format', {}).get('duration', 0))
                
                if duration > 0:
                    print(f"{Fore.GREEN}[NODE_SYSTEM] Detected duration: {duration:.2f}s for {os.path.basename(video_path)}{Style.RESET_ALL}")
                    return duration
                else:
                    print(f"{Fore.YELLOW}[NODE_SYSTEM] Could not detect duration for {os.path.basename(video_path)}, using default{Style.RESET_ALL}")
                    
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] ffprobe failed for {os.path.basename(video_path)}: {e}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}[NODE_SYSTEM] Error getting duration for {os.path.basename(video_path)}: {e}{Style.RESET_ALL}")
        
        # Fallback: try to estimate based on file size or use a reasonable default
        try:
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            # Rough estimate: assume 1MB per second of video (very rough)
            estimated_duration = max(2.0, min(10.0, file_size_mb))
            print(f"{Fore.CYAN}[NODE_SYSTEM] Estimated duration: {estimated_duration:.2f}s based on file size{Style.RESET_ALL}")
            return estimated_duration
        except:
            # Ultimate fallback
            default_duration = 5.0
            print(f"{Fore.YELLOW}[NODE_SYSTEM] Using default duration: {default_duration}s{Style.RESET_ALL}")
            return default_duration

    def interrupt_for_response(self):
        """Interrupt idle playing for user response processing"""
        print(f"{Fore.YELLOW}[NODE_SYSTEM] Interrupting idle playback for response{Style.RESET_ALL}")
        self.is_interrupted = True

    def return_to_main_and_wait(self, lipsync_ready_callback):
        """Return to main node and wait for lipsync to be ready"""
        print(f"{Fore.CYAN}[NODE_SYSTEM] Initiating return to main...{Style.RESET_ALL}")
        
        # Get path back to main
        return_videos = self.return_to_main_path()
        
        # Start return sequence in separate thread
        return_thread = threading.Thread(
            target=self._return_to_main_sequence, 
            args=(return_videos, lipsync_ready_callback), 
            daemon=True
        )
        return_thread.start()

    def _return_to_main_sequence(self, return_videos: List[str], lipsync_ready_callback):
        """Execute the return to main sequence"""
        # Play return videos if any
        for video_path in return_videos:
            if os.path.exists(video_path):
                print(f"{Fore.BLUE}[NODE_SYSTEM] Return sequence: {os.path.basename(video_path)}{Style.RESET_ALL}")
                
                if self.video_ready_callback:
                    self.video_ready_callback(video_path)
                
                duration = self._get_video_duration(video_path)
                time.sleep(duration)
        
        # Now we're at main, wait for lipsync or play main2main clips
        while True:
            # Check if lipsync is ready
            if lipsync_ready_callback():
                print(f"{Fore.GREEN}[NODE_SYSTEM] Lipsync ready! Breaking wait loop.{Style.RESET_ALL}")
                break
            
            # Play a main2main clip while waiting
            main_videos = self.get_available_videos("node_1", "node_1")
            if main_videos:
                video_path = random.choice(main_videos)
                print(f"{Fore.YELLOW}[NODE_SYSTEM] Waiting for lipsync, playing: {os.path.basename(video_path)}{Style.RESET_ALL}")
                
                if self.video_ready_callback:
                    self.video_ready_callback(video_path)
                
                duration = self._get_video_duration(video_path)
                time.sleep(duration)
            else:
                # No main2main videos, just wait
                print(f"{Fore.YELLOW}[NODE_SYSTEM] No main2main videos, waiting for lipsync...{Style.RESET_ALL}")
                time.sleep(1)

    def play_lipsync_and_resume(self, lipsync_video_path: str):
        """Play the lipsync video and then resume idle playing"""
        print(f"{Fore.GREEN}[NODE_SYSTEM] Playing lipsync video: {os.path.basename(lipsync_video_path)}{Style.RESET_ALL}")
        
        # Play lipsync video
        if self.video_ready_callback:
            self.video_ready_callback(lipsync_video_path)
        
        # Wait for lipsync video to finish
        duration = self._get_video_duration(lipsync_video_path)
        time.sleep(duration)
        
        # Resume idle playing from main
        print(f"{Fore.GREEN}[NODE_SYSTEM] Lipsync finished, resuming idle playback{Style.RESET_ALL}")
        self.current_node = "node_1"  # Ensure we're at main
        self.is_interrupted = False
        
        # Restart idle playing
        self.start_idle_playing(self.video_ready_callback)

    def stop_playing(self):
        """Stop all video playing"""
        print(f"{Fore.RED}[NODE_SYSTEM] Stopping video playback{Style.RESET_ALL}")
        self.is_playing = False
        self.is_interrupted = True
        
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=2)

    def get_system_status(self) -> Dict:
        """Get current system status for debugging"""
        return {
            "current_node": self.current_node,
            "is_playing": self.is_playing,
            "is_interrupted": self.is_interrupted,
            "current_video": os.path.basename(self.current_video_path) if self.current_video_path else None,
            "available_nodes": list(self.nodes_data.keys()),
        }


# Test function for lipsync (as requested)
def test_lipsync_function(text: str, output_filename: str = None) -> Tuple[bool, str]:
    """
    Test lipsync function that waits 3 seconds then returns a test file path
    Returns: (is_ready, file_path)
    """
    print(f"{Fore.MAGENTA}[TEST_LIPSYNC] Starting lipsync generation for: {text[:50]}...{Style.RESET_ALL}")
    
    # Simulate processing time
    time.sleep(3)
    
    # Return a test file path (you would replace this with actual lipsync generation)
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    if output_filename is None:
        output_filename = f"test_lipsync_{int(time.time())}.mp4"
    
    test_file_path = os.path.join(temp_dir, output_filename)
    
    # For testing, just create an empty file or copy an existing one
    os.makedirs(temp_dir, exist_ok=True)
    
    # Create a dummy file for testing (replace with actual lipsync generation)
    with open(test_file_path, 'w') as f:
        f.write("dummy lipsync file")
    
    print(f"{Fore.GREEN}[TEST_LIPSYNC] Lipsync ready: {test_file_path}{Style.RESET_ALL}")
    return True, test_file_path


if __name__ == "__main__":
    # Test the node system
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}Testing Node Video System")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")
    
    def test_video_callback(video_path):
        print(f"{Fore.BLUE}[TEST] Would play video: {video_path}{Style.RESET_ALL}")
    
    # Initialize system
    node_system = NodeVideoSystem("Darwin")
    
    # Test getting videos
    print(f"\n{Fore.CYAN}Testing video retrieval:{Style.RESET_ALL}")
    for i in range(5):
        video = node_system.get_next_video()
        if video:
            print(f"  Next video: {os.path.basename(video)} (Node: {node_system.current_node})")
        else:
            print(f"  No video available (Node: {node_system.current_node})")
    
    # Test return to main
    print(f"\n{Fore.CYAN}Testing return to main:{Style.RESET_ALL}")
    return_videos = node_system.return_to_main_path()
    print(f"  Return videos: {[os.path.basename(v) for v in return_videos]}")
    
    # Test status
    print(f"\n{Fore.CYAN}System Status:{Style.RESET_ALL}")
    status = node_system.get_system_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    print(f"\n{Fore.GREEN}Node system test completed!{Style.RESET_ALL}")