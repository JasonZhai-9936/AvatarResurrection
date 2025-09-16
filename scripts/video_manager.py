# video_manager.py - Enhanced video management with positional lipsync integration

import os
import random
import time
import threading
import json
from enum import Enum
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from colorama import Fore, Style, init

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Initialize colorama for colored terminal output
init(autoreset=True)

class State(Enum):
    """Avatar states"""
    MAIN = "main"
    NEWSPAPER = "newspaper"
    PHONE = "phone"

class Mode(Enum):
    """Playback modes"""
    IDLE = "idle"
    RETURNING_TO_MAIN = "returning_to_main"
    WAITING_FOR_LIPSYNC = "waiting_for_lipsync"

@dataclass
class TransitionWeights:
    """Weights for state transitions during idle mode"""
    stay_same: float = 0.7
    to_newspaper: float = 0.0
    to_phone: float = 0.0

@dataclass
class VideoClip:
    """Represents a video clip with metadata"""
    path: str
    from_state: State
    to_state: State
    duration: Optional[float] = None
    is_lipsync: bool = False

class VideoQueue:
    """Thread-safe video queue for managing playback sequence"""
    
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()
        self._current_clip = None
    
    def add(self, clip: VideoClip):
        with self._lock:
            self._queue.append(clip)
            print(f"{Fore.CYAN}[QUEUE] Added: {os.path.basename(clip.path)} ({clip.from_state.value}→{clip.to_state.value}){Style.RESET_ALL}")
    
    def get_next(self) -> Optional[VideoClip]:
        with self._lock:
            if self._queue:
                clip = self._queue.pop(0)
                self._current_clip = clip
                return clip
            return None
    
    def clear(self):
        with self._lock:
            self._queue.clear()
            print(f"{Fore.YELLOW}[QUEUE] Cleared all pending clips{Style.RESET_ALL}")
    
    def peek_next(self) -> Optional[VideoClip]:
        with self._lock:
            return self._queue[0] if self._queue else None
    
    def size(self) -> int:
        with self._lock:
            return len(self._queue)
    
    @property
    def current_clip(self) -> Optional[VideoClip]:
        with self._lock:
            return self._current_clip

class VideoManager:
    """Main video management system with positional lipsync integration"""
    
    def __init__(self, ui_update_callback: Callable[[str], None]):
        self.nodes_path = os.path.join(PROJECT_DIR, "avatars", "Darwin", "Nodes")
        self.ui_update_callback = ui_update_callback
        
        # State management
        self.current_state = State.MAIN
        self.current_mode = Mode.IDLE
        self.target_state = State.MAIN
        
        # Video management
        self.video_queue = VideoQueue()
        self.video_catalog = self._build_video_catalog()
        self.transition_weights = TransitionWeights()
        
        # Positional lipsync management
        self.pending_lipsync = None
        self.lipsync_ready = False
        self.lipsync_callback = None
        self.lipsync_generation_thread = None
        
        # Control flags
        self.is_playing = False
        self.stop_playback = False
        
        print(f"{Fore.GREEN}[VIDEO] Video Manager initialized with {len(self.video_catalog)} clips{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[VIDEO] Positional lipsync integration enabled{Style.RESET_ALL}")
        self._start_idle_mode()
    
    def _build_video_catalog(self) -> Dict[str, List[VideoClip]]:
        """Build catalog of all available video clips"""
        catalog = {}
        
        if not os.path.exists(self.nodes_path):
            print(f"{Fore.RED}[VIDEO] Nodes directory not found: {self.nodes_path}{Style.RESET_ALL}")
            return catalog
        
        # Define transition mappings
        transitions = {
            "main2main": (State.MAIN, State.MAIN),
            "main2newspaper": (State.MAIN, State.NEWSPAPER),
            "main2phone": (State.MAIN, State.PHONE),
            "newspaper2main": (State.NEWSPAPER, State.MAIN),
            "newspaper2newspaper": (State.NEWSPAPER, State.NEWSPAPER),
            "phone2main": (State.PHONE, State.MAIN),
            "phone2phone": (State.PHONE, State.PHONE)
        }
        
        for folder_name, (from_state, to_state) in transitions.items():
            folder_path = os.path.join(self.nodes_path, folder_name)
            
            if os.path.exists(folder_path):
                clips = []
                
                # Recursively find all .mp4 files
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        if file.lower().endswith('.mp4'):
                            full_path = os.path.join(root, file)
                            clip = VideoClip(
                                path=full_path,
                                from_state=from_state,
                                to_state=to_state
                            )
                            clips.append(clip)
                
                if clips:
                    catalog[folder_name] = clips
                    print(f"{Fore.BLUE}[VIDEO] Found {len(clips)} clips in {folder_name}{Style.RESET_ALL}")
        
        return catalog
    
    def _get_transition_key(self, from_state: State, to_state: State) -> str:
        """Get the transition key for catalog lookup"""
        return f"{from_state.value}2{to_state.value}"
    
    def _select_random_clip(self, from_state: State, to_state: State) -> Optional[VideoClip]:
        """Select a random clip for the given transition"""
        transition_key = self._get_transition_key(from_state, to_state)
        clips = self.video_catalog.get(transition_key, [])
        
        if not clips:
            print(f"{Fore.RED}[VIDEO] No clips found for {transition_key}{Style.RESET_ALL}")
            return None
        
        clip = random.choice(clips)
        print(f"{Fore.MAGENTA}[VIDEO] Selected: {os.path.basename(clip.path)} for {transition_key}{Style.RESET_ALL}")
        return clip
    
    def _determine_next_state(self) -> State:
        """Determine next state based on current mode and weights"""
        if self.current_mode == Mode.RETURNING_TO_MAIN:
            return State.MAIN
        
        if self.current_mode == Mode.WAITING_FOR_LIPSYNC:
            return State.MAIN  # Stay in main while waiting
        
        # Idle mode - random transitions based on weights
        weights = self.transition_weights
        rand = random.random()
        
        if self.current_state == State.MAIN:
            if rand < weights.stay_same:
                return State.MAIN
            elif rand < weights.stay_same + weights.to_newspaper:
                return State.NEWSPAPER
            else:
                return State.PHONE
        
        elif self.current_state == State.NEWSPAPER:
            if rand < weights.stay_same:
                return State.NEWSPAPER
            else:
                return State.MAIN
        
        elif self.current_state == State.PHONE:
            if rand < weights.stay_same:
                return State.PHONE
            else:
                return State.MAIN
        
        return self.current_state
    
    def _queue_next_clip(self):
        """Queue the next appropriate clip"""
        if self.stop_playback:
            return
        
        # Check if we have a pending positional lipsync clip ready
        if (self.current_mode in [Mode.WAITING_FOR_LIPSYNC, Mode.IDLE] and 
            self.lipsync_ready and 
            self.pending_lipsync and 
            self.current_state == State.MAIN):
            
            print(f"{Fore.GREEN}[VIDEO] Positional lipsync clip ready! Queuing lipsync video{Style.RESET_ALL}")
            self.video_queue.add(self.pending_lipsync)
            
            # Immediately queue a random main2main clip after the lipsync
            follow_up_clip = self._select_random_clip(State.MAIN, State.MAIN)
            if follow_up_clip:
                self.video_queue.add(follow_up_clip)
                print(f"{Fore.CYAN}[VIDEO] Auto-queued follow-up clip: {os.path.basename(follow_up_clip.path)}{Style.RESET_ALL}")
            
            # Reset to idle mode and clear lipsync data
            self.current_mode = Mode.IDLE
            self.pending_lipsync = None
            self.lipsync_ready = False
            
            if self.lipsync_callback:
                self.lipsync_callback()
            
            return
        
        # Determine next state
        next_state = self._determine_next_state()
        
        # Select and queue clip
        clip = self._select_random_clip(self.current_state, next_state)
        if clip:
            self.video_queue.add(clip)
            
            # Update state
            self.current_state = next_state
            
            # Update mode based on transitions
            if self.current_mode == Mode.RETURNING_TO_MAIN and next_state == State.MAIN:
                if self.pending_lipsync and not self.lipsync_ready:
                    print(f"{Fore.YELLOW}[VIDEO] Reached main state, waiting for positional lipsync{Style.RESET_ALL}")
                    self.current_mode = Mode.WAITING_FOR_LIPSYNC
                else:
                    print(f"{Fore.GREEN}[VIDEO] Returned to main state, resuming idle mode{Style.RESET_ALL}")
                    self.current_mode = Mode.IDLE
            
            elif self.current_mode == Mode.WAITING_FOR_LIPSYNC and next_state == State.MAIN:
                # If we're waiting but queuing a regular clip, stay in waiting mode
                print(f"{Fore.YELLOW}[VIDEO] Still waiting for positional lipsync, staying in main{Style.RESET_ALL}")
    
    def _play_next_clip(self):
        """Play the next clip in the queue"""
        if self.stop_playback:
            return
        
        clip = self.video_queue.get_next()
        if not clip:
            print(f"{Fore.YELLOW}[VIDEO] No clips in queue, generating next{Style.RESET_ALL}")
            self._queue_next_clip()
            clip = self.video_queue.get_next()
        
        if clip:
            lipsync_indicator = " [POSITIONAL LIPSYNC]" if clip.is_lipsync else ""
            print(f"{Fore.GREEN}[VIDEO] Playing: {os.path.basename(clip.path)} (Mode: {self.current_mode.value}){lipsync_indicator}{Style.RESET_ALL}")
            
            # Convert absolute path to relative URL for the web interface
            relative_path = os.path.relpath(clip.path, PROJECT_DIR)
            video_url = f"/{relative_path.replace(os.sep, '/')}"
            
            # Update UI
            self.ui_update_callback(video_url)
            
            # Pre-queue next clip while current one plays
            if self.video_queue.size() == 0:
                self._queue_next_clip()
    
    def _start_idle_mode(self):
        """Start the idle video playback"""
        print(f"{Fore.GREEN}[VIDEO] Starting idle mode{Style.RESET_ALL}")
        self.current_mode = Mode.IDLE
        self.is_playing = True
        self._play_next_clip()
    
    def on_video_ended(self):
        """Called when a video ends - triggers next clip"""
        if self.stop_playback:
            return
            
        print(f"{Fore.BLUE}[VIDEO] Video ended, playing next clip{Style.RESET_ALL}")
        self._play_next_clip()
    
    def prepare_for_user_input(self):
        """Called when user starts entering input - begin return to main"""
        if self.current_mode == Mode.IDLE:
            if self.current_state != State.MAIN:
                print(f"{Fore.YELLOW}[VIDEO] User input detected, returning to main state{Style.RESET_ALL}")
                self.current_mode = Mode.RETURNING_TO_MAIN
                self.target_state = State.MAIN
                # Clear queue and force next clip to head toward main
                self.video_queue.clear()
            else:
                print(f"{Fore.YELLOW}[VIDEO] User input detected, already in main - preparing for positional lipsync{Style.RESET_ALL}")
                self.current_mode = Mode.WAITING_FOR_LIPSYNC
    
    def start_lipsync_generation(self, text: str, callback: Optional[Callable] = None):
        """Start positional lipsync video generation"""
        print(f"{Fore.MAGENTA}[VIDEO] Starting positional lipsync generation for: {text[:50]}...{Style.RESET_ALL}")
        
        self.lipsync_callback = callback
        self.lipsync_ready = False
        
        # Cancel any existing lipsync generation
        if self.lipsync_generation_thread and self.lipsync_generation_thread.is_alive():
            print(f"{Fore.YELLOW}[VIDEO] Cancelling previous lipsync generation{Style.RESET_ALL}")
            # Note: Python threading doesn't support cancellation, but the new generation will override
        
        # Start positional lipsync generation in background thread
        def generate_positional_lipsync():
            try:
                # Import here to avoid circular imports
                from positional_lipsync import generate_lipsync_video
                
                print(f"{Fore.CYAN}[VIDEO] Generating Sora lipsync video (with TTS)...{Style.RESET_ALL}")
                # Use silent_tts=True to prevent duplicate audio playback
                lipsync_path = generate_lipsync_video(text, silent_tts=True)
                
                if lipsync_path:
                    # Convert path to absolute for VideoClip
                    if not os.path.isabs(lipsync_path):
                        abs_lipsync_path = os.path.join(PROJECT_DIR, lipsync_path.lstrip('/'))
                    else:
                        abs_lipsync_path = lipsync_path
                    
                    self.pending_lipsync = VideoClip(
                        path=abs_lipsync_path,
                        from_state=State.MAIN,
                        to_state=State.MAIN,
                        is_lipsync=True
                    )
                    self.lipsync_ready = True
                    print(f"{Fore.GREEN}[VIDEO] Positional lipsync video ready: {os.path.basename(abs_lipsync_path)}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[VIDEO] Positional lipsync generation failed{Style.RESET_ALL}")
                    self.current_mode = Mode.IDLE
                    
            except Exception as e:
                print(f"{Fore.RED}[VIDEO] Positional lipsync generation error: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()
                self.current_mode = Mode.IDLE
        
        self.lipsync_generation_thread = threading.Thread(target=generate_positional_lipsync, daemon=True)
        self.lipsync_generation_thread.start()
    
    def stop(self):
        """Stop video playback"""
        print(f"{Fore.RED}[VIDEO] Stopping video playback{Style.RESET_ALL}")
        self.stop_playback = True
        self.is_playing = False
        self.video_queue.clear()
        
        # Cancel any ongoing lipsync generation
        if self.lipsync_generation_thread and self.lipsync_generation_thread.is_alive():
            print(f"{Fore.YELLOW}[VIDEO] Cancelling ongoing lipsync generation{Style.RESET_ALL}")
    
    def get_status(self) -> Dict:
        """Get current status for debugging"""
        return {
            "current_state": self.current_state.value,
            "current_mode": self.current_mode.value,
            "queue_size": self.video_queue.size(),
            "current_clip": os.path.basename(self.video_queue.current_clip.path) if self.video_queue.current_clip else None,
            "lipsync_ready": self.lipsync_ready,
            "lipsync_pending": self.pending_lipsync is not None,
            "lipsync_generating": self.lipsync_generation_thread.is_alive() if self.lipsync_generation_thread else False,
            "is_playing": self.is_playing
        }

def test_video_manager_with_positional_lipsync():
    """Test function for the video manager with positional lipsync"""
    def dummy_ui_callback(video_url: str):
        print(f"[TEST] UI would play: {video_url}")
    
    manager = VideoManager(dummy_ui_callback)
    
    # Test idle mode
    print(f"\n{Fore.CYAN}Testing idle mode for 10 seconds...{Style.RESET_ALL}")
    time.sleep(10)
    
    # Test user input preparation
    print(f"\n{Fore.CYAN}Testing user input preparation...{Style.RESET_ALL}")
    manager.prepare_for_user_input()
    time.sleep(5)
    
    # Test positional lipsync
    print(f"\n{Fore.CYAN}Testing positional lipsync generation...{Style.RESET_ALL}")
    manager.start_lipsync_generation("Hello there! This is a test of the new positional lipsync system with syllable-based matching.")
    time.sleep(15)  # Give more time for lipsync generation
    
    # Print final status
    print(f"\n{Fore.GREEN}Final Status:{Style.RESET_ALL}")
    status = manager.get_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    manager.stop()

if __name__ == "__main__":
    test_video_manager_with_positional_lipsync()