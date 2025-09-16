# main.py - Simplified Darwin Chatbot with integrated video and lipsync

import os
import sys
import time
import asyncio
from pathlib import Path
from typing import Optional
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

# Import modules
from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio
from simple_final_lipsync import SimplifiedLipSyncSystem
from simplified_video_manager import SimplifiedVideoManager
from ui import build_ui
from nicegui import ui as nicegui_ui

class DarwinChatbot:
    """Main chatbot class integrating all components"""
    
    def __init__(self):
        # Initialize components
        self.video_manager = SimplifiedVideoManager(avatar_name="Darwin")
        self.lipsync_system = self.initialize_lipsync()
        
        # UI references
        self.chat_log = None
        self.ui_components = None
        self.video_element = None  # Store reference to video element
        
        # Processing state
        self.is_processing = False
        
        # Timer for idle video rotation
        self.idle_timer = None
        self.last_idle_change = time.time()  # Track last idle video change
        self.idle_video_duration = 8.0  # How long each idle video plays
        
        print(f"{Fore.GREEN}[MAIN] Darwin Chatbot initialized{Style.RESET_ALL}")

    def initialize_lipsync(self) -> SimplifiedLipSyncSystem:
        """Initialize the lip sync system"""
        archive_dir = os.path.join(PROJECT_DIR, "archive")
        
        # Configure clip selection odds
        clip_odds = {
            "circle1": 0.5,
            "eye_look1": 0.5,
            "idle2": 1.0,
            "slight_look1": 1.0,
            "slight_shake1": 1,
            "slight_shake2": 1.0,  # Added
            "nod1": 1.0,           # Added
            "main2": 1.0, 
        }
        
        return SimplifiedLipSyncSystem(
            archive_directory=archive_dir,
            clip_odds=clip_odds,
            avoid_repeats=True
        )

    def setup_ui(self):
        """Set up the UI with callbacks"""
        # Build UI with callbacks
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_user_input,
            voice_change_callback=self.handle_voice_change
        )
        
        # Get references
        self.chat_log = self.ui_components['chat_log']
        
        # Defer video initialization until after UI is ready
        # Use a timer with 0.5 second delay to ensure UI is fully loaded
        nicegui_ui.timer(0.5, self.start_idle_videos, once=True)
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete{Style.RESET_ALL}")

    def start_idle_videos(self):
        """Start the idle video rotation"""
        # Play first idle video
        self.play_next_idle_video()
        
        # Set up timer to check for video updates every 0.2 seconds for smoother transitions
        if self.idle_timer:
            self.idle_timer.cancel()
        
        self.idle_timer = nicegui_ui.timer(0.2, self.check_and_play_video)
        print(f"{Fore.GREEN}[MAIN] Started idle video rotation{Style.RESET_ALL}")

    def check_and_play_video(self):
        """Check if we should play a new video - runs every 0.2 seconds"""
        current_time = time.time()
        
        # Check if there's a queued lipsync video that needs to play
        if self.video_manager.current_mode == "lipsync" and self.video_manager.next_video_path:
            video_path = self.video_manager.current_video_path
            rel_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
            video_url = f"/{rel_path}"
            
            print(f"{Fore.CYAN}[MAIN] Playing lipsync video: {os.path.basename(video_path)}{Style.RESET_ALL}")
            
            # Get the next idle video ready
            next_idle = self.video_manager.get_random_idle_video()
            next_idle_url = ""
            if next_idle:
                next_idle_rel = os.path.relpath(next_idle, PROJECT_DIR).replace('\\', '/')
                next_idle_url = f"/{next_idle_rel}"
            
            # Update video using JavaScript with onended event
            nicegui_ui.run_javascript(f'''
                const video = document.getElementById('mainVideo');
                if (video) {{
                    video.src = '{video_url}';
                    video.load();
                    video.play();
                    const statusDiv = document.getElementById('video-status');
                    if (statusDiv) {{
                        statusDiv.textContent = 'Playing Lipsync';
                    }}
                    
                    // When lipsync ends, immediately play an idle video
                    video.onended = function() {{
                        console.log('[MAIN] Lipsync ended, playing idle');
                        if ('{next_idle_url}') {{
                            video.src = '{next_idle_url}';
                            video.load();
                            video.play();
                            if (statusDiv) {{
                                statusDiv.textContent = 'Playing Idle';
                            }}
                        }}
                    }};
                }}
            ''')
            
            # Clear the queue flag and reset mode
            self.video_manager.next_video_path = None
            self.video_manager.current_mode = "idle"  # Set back to idle immediately
            self.last_idle_change = current_time
            return
        
        # For idle videos, check if we need to refresh the chain
        # This handles the case where an idle video ends but doesn't have a next one set
        if self.video_manager.current_mode == "idle":
            # Only refresh if enough time has passed (safety check)
            if current_time - self.last_idle_change >= 20.0:  # Safety timeout
                print(f"{Fore.YELLOW}[MAIN] Idle chain may have broken, refreshing{Style.RESET_ALL}")
                self.play_next_idle_video()
                self.last_idle_change = current_time

    def play_next_idle_video(self):
        """Play the next idle video"""
        video_path = self.video_manager.get_next_idle_video()
        if video_path:
            self.video_manager.current_video_path = video_path
            self.update_video_display(video_path)

    def update_video_display(self, video_path: str):
        """Update the video display with a new video"""
        if not video_path or not os.path.exists(video_path):
            return
        
        # Convert to relative path for web serving
        rel_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
        video_url = f"/{rel_path}"
        
        # Determine if this is an idle video
        is_idle = self.video_manager.current_mode == "idle"
        
        if is_idle:
            # For idle videos, prepare the next one
            next_idle = self.video_manager.get_random_idle_video()
            next_idle_url = ""
            if next_idle:
                next_idle_rel = os.path.relpath(next_idle, PROJECT_DIR).replace('\\', '/')
                next_idle_url = f"/{next_idle_rel}"
            
            # Update video with automatic next video on end
            nicegui_ui.run_javascript(f'''
                const video = document.getElementById('mainVideo');
                if (video) {{
                    video.src = '{video_url}';
                    video.load();
                    video.play();
                    const statusDiv = document.getElementById('video-status');
                    if (statusDiv) {{
                        statusDiv.textContent = 'Playing: {os.path.basename(video_path)}';
                    }}
                    
                    // When this idle video ends, immediately play the next one
                    video.onended = function() {{
                        console.log('Idle video ended, playing next');
                        video.src = '{next_idle_url}';
                        video.load();
                        video.play();
                        if (statusDiv) {{
                            statusDiv.textContent = 'Playing: {os.path.basename(next_idle) if next_idle else "idle"}';
                        }}
                        // Set up the next video after this one
                        setTimeout(() => {{
                            video.onended = null;  // Clear to prevent loop
                        }}, 100);
                    }};
                }}
            ''')
            # Update tracking
            self.last_idle_change = time.time()
            
        else:
            # For non-idle videos, just play normally
            nicegui_ui.run_javascript(f'''
                const video = document.getElementById('mainVideo');
                if (video) {{
                    video.src = '{video_url}';
                    video.load();
                    video.play();
                    const statusDiv = document.getElementById('video-status');
                    if (statusDiv) {{
                        statusDiv.textContent = 'Playing: {os.path.basename(video_path)}';
                    }}
                    video.onended = null;  // Clear any previous handlers
                }}
            ''')

    def handle_user_input(self, user_text: str):
        """Handle user input from UI"""
        if self.is_processing:
            nicegui_ui.notify("Please wait for the current response to complete", type="warning")
            return
        
        # Process response asynchronously
        asyncio.create_task(self.process_response_async(user_text))

    async def process_response_async(self, user_text: str):
        """Process user input and generate response (async)"""
        self.is_processing = True
        
        try:
            # Update chat log with user message
            if self.chat_log:
                with self.chat_log:
                    with nicegui_ui.row().classes('w-full justify-end'):
                        with nicegui_ui.card().classes('bg-blue-100 p-3 rounded-lg max-w-lg').style('word-wrap: break-word;'):
                            nicegui_ui.label(user_text)
            
            print(f"{Fore.CYAN}[MAIN] Processing: {user_text}{Style.RESET_ALL}")
            
            # Step 1: Generate LLM response (run in executor to not block)
            print(f"{Fore.BLUE}[MAIN] Generating Darwin's response...{Style.RESET_ALL}")
            darwin_response = await asyncio.get_event_loop().run_in_executor(None, generate_darwin_response, user_text)
            
            if not darwin_response:
                print(f"{Fore.RED}[MAIN] No response generated{Style.RESET_ALL}")
                return
            
            print(f"{Fore.GREEN}[MAIN] Response: {darwin_response}{Style.RESET_ALL}")
            
            # Update chat log with Darwin's response
            if self.chat_log:
                with self.chat_log:
                    with nicegui_ui.row().classes('w-full justify-start'):
                        with nicegui_ui.card().classes('bg-gray-100 p-3 rounded-lg max-w-lg').style('word-wrap: break-word;'):
                            nicegui_ui.label(f"🎩 Darwin: {darwin_response}")
            
            # Step 2: Generate TTS audio
            print(f"{Fore.BLUE}[MAIN] Generating audio...{Style.RESET_ALL}")
            
            # Ensure we have the correct voice path
            default_voice = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-northern_english_male-medium.onnx")
            audio_path = await asyncio.get_event_loop().run_in_executor(None, generate_complete_audio, darwin_response, None, default_voice)
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"{Fore.RED}[MAIN] Audio generation failed{Style.RESET_ALL}")
                return
            
            print(f"{Fore.GREEN}[MAIN] Audio saved: {audio_path}{Style.RESET_ALL}")
            
            # Step 3: Generate lip-sync video
            print(f"{Fore.BLUE}[MAIN] Creating lip-sync video...{Style.RESET_ALL}")
            
            output_dir = os.path.join(PROJECT_DIR, "tempstream")
            
            # Run lipsync generation in executor
            def generate_lipsync():
                return self.lipsync_system.generate_lip_sync_video(
                    audio_file=audio_path,
                    output_file=None,
                    output_dir=output_dir,
                    use_sequential=True,
                    target_clips=None  # auto-calculate
                )
            
            lipsync_video = await asyncio.get_event_loop().run_in_executor(None, generate_lipsync)
            
            if not lipsync_video or not os.path.exists(lipsync_video):
                print(f"{Fore.RED}[MAIN] Lip-sync generation failed{Style.RESET_ALL}")
                return
            
            print(f"{Fore.GREEN}[MAIN] Lip-sync video created: {lipsync_video}{Style.RESET_ALL}")
            
            # Step 4: Play lip-sync video
            self.video_manager.current_mode = "lipsync"
            self.video_manager.current_video_path = lipsync_video
            self.video_manager.next_video_path = True  # Flag that we have a new video to play
            
            print(f"{Fore.GREEN}[MAIN] Lipsync video queued for playback{Style.RESET_ALL}")
            
            # Clean up old files periodically
            self.video_manager.cleanup_old_lipsync_videos(keep_last=5)
            
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error processing response: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.is_processing = False

    def handle_voice_change(self, voice_name: str):
        """Handle voice model change"""
        try:
            # Voice files are .onnx files directly in Piper_Voices
            voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", voice_name + ".onnx")
            
            # Import and set voice
            from enhanced_tts_piper import set_voice_model
            set_voice_model(voice_path)
            
            print(f"{Fore.GREEN}[MAIN] Voice changed to: {voice_name}{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error changing voice: {e}{Style.RESET_ALL}")

    def run(self):
        """Run the chatbot application"""
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Darwin Chatbot - Simplified Version{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        
        # Add static file serving for the project directory
        from nicegui import app
        from fastapi.staticfiles import StaticFiles
        
        # Mount the project directory to serve video files
        app.mount('/avatars', StaticFiles(directory=os.path.join(PROJECT_DIR, 'avatars')), name='avatars')
        app.mount('/tempstream', StaticFiles(directory=os.path.join(PROJECT_DIR, 'tempstream')), name='tempstream')
        
        # Setup UI
        self.setup_ui()
        
        # Run the UI
        print(f"{Fore.GREEN}[MAIN] Starting web interface...{Style.RESET_ALL}")
        nicegui_ui.run(
            title="Darwin Chatbot",
            favicon="🎩",
            dark=False,
            reload=False,
            show=True,
            port=8080
        )

def main():
    """Main entry point"""
    try:
        # Create and run chatbot
        chatbot = DarwinChatbot()
        chatbot.run()
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[MAIN] Shutting down...{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[MAIN] Fatal error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()