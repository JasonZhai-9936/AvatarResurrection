# main.py - Integrated system with new simplified lip sync

import os
import time
import threading
from pathlib import Path
from nicegui import ui, app
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Import all modules
from scripts.ui import build_ui, load_config
from scripts.LLM_Groq import generate_darwin_response
from scripts.enhanced_tts_piper import generate_complete_audio, set_voice_model
from scripts.node_video_system import NodeVideoSystem
from scripts.simple_final_lipsync import SimplifiedLipSyncSystem

class DarwinAvatarSystem:
    def __init__(self):
        # Initialize components
        self.node_system = NodeVideoSystem(avatar_name="Darwin")
        
        # Initialize lip sync system with Darwin's archive
        archive_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin", "archive")
        
        # Configure clip selection odds for Darwin's personality
        clip_odds = {
            "circle1": 0.8,      # Moderate circular movements
            "eye_look1": 1.2,    # More eye contact
            "idle2": 1.5,        # Natural idle state
            "slight_look1": 1.0, # Occasional looking
            "slight_shake1": 0.5 # Less head shaking
        }
        
        self.lipsync_system = SimplifiedLipSyncSystem(
            archive_directory=archive_dir,
            clip_odds=clip_odds,
            avoid_repeats=True
        )
        
        # Output directories
        self.temp_dir = os.path.join(PROJECT_DIR, "tempstream")
        self.lipsync_output_dir = os.path.join(PROJECT_DIR, "lipsync_output")
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.lipsync_output_dir, exist_ok=True)
        
        # State management
        self.is_processing_response = False
        self.current_mode = "idle"  # idle, thinking, speaking
        self.ui_components = None
        
        print(f"{Fore.GREEN}[MAIN] Darwin Avatar System initialized{Style.RESET_ALL}")

    def handle_video_ready(self, video_path):
        """Callback when node system has a video ready"""
        if self.ui_components:
            ui.run_javascript(f'updateMainVideo("{video_path}")')
            print(f"{Fore.BLUE}[MAIN] Video sent to UI: {os.path.basename(video_path)}{Style.RESET_ALL}")

    def handle_user_input(self, user_text):
        """Main handler for user input"""
        if self.is_processing_response:
            ui.notify("Darwin is still thinking, please wait...", color="warning")
            return
        
        self.is_processing_response = True
        
        # Update UI to show user message
        if self.ui_components and self.ui_components['chat_log']:
            with self.ui_components['chat_log']:
                with ui.card().classes('w-full p-3 mb-2').style('background: #e3f2fd;'):
                    ui.label('You:').classes('font-bold text-blue-800')
                    ui.label(user_text).classes('text-gray-800')
        
        # Process in background thread
        thread = threading.Thread(target=self._process_response, args=(user_text,))
        thread.daemon = True
        thread.start()

    def _process_response(self, user_text):
        """Process response in background thread"""
        try:
            # Step 1: Interrupt idle videos and show thinking state
            self.current_mode = "thinking"
            self.node_system.interrupt_for_response()
            
            # Show thinking state in UI
            app.add_task(self._show_thinking_state)
            
            # Step 2: Generate LLM response
            print(f"{Fore.CYAN}[MAIN] Generating Darwin's response...{Style.RESET_ALL}")
            darwin_response = generate_darwin_response(user_text)
            
            # Step 3: Generate audio from response
            print(f"{Fore.CYAN}[MAIN] Generating audio...{Style.RESET_ALL}")
            audio_path = generate_complete_audio(darwin_response)
            
            if not audio_path:
                print(f"{Fore.RED}[MAIN] Failed to generate audio{Style.RESET_ALL}")
                app.add_task(lambda: ui.notify("Audio generation failed", color="negative"))
                self._return_to_idle()
                return
            
            # Step 4: Generate lip-synced video using new system
            print(f"{Fore.CYAN}[MAIN] Creating lip-synced video...{Style.RESET_ALL}")
            self.current_mode = "speaking"
            
            # Generate unique output filename
            timestamp = int(time.time() * 1000)
            output_filename = f"darwin_lipsync_{timestamp}.mp4"
            output_path = os.path.join(self.lipsync_output_dir, output_filename)
            
            # Use the new simplified lip sync system
            lipsync_video = self.lipsync_system.generate_lip_sync_video(
                audio_file=audio_path,
                output_file=output_path,
                use_sequential=False,
                target_clips=None  # Auto-calculate based on duration
            )
            
            if not lipsync_video:
                print(f"{Fore.RED}[MAIN] Failed to generate lip-synced video{Style.RESET_ALL}")
                app.add_task(lambda: ui.notify("Lip sync generation failed", color="negative"))
                self._return_to_idle()
                return
            
            # Step 5: Play lip-synced video
            print(f"{Fore.GREEN}[MAIN] Playing lip-synced response{Style.RESET_ALL}")
            app.add_task(lambda: self._play_response_video(lipsync_video, darwin_response))
            
            # Step 6: Wait for video to complete (estimate duration)
            video_duration = self._get_video_duration(lipsync_video)
            time.sleep(video_duration + 0.5)  # Add small buffer
            
            # Step 7: Return to idle
            self._return_to_idle()
            
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error processing response: {e}{Style.RESET_ALL}")
            app.add_task(lambda: ui.notify(f"Error: {str(e)}", color="negative"))
            self._return_to_idle()
        finally:
            self.is_processing_response = False

    def _show_thinking_state(self):
        """Show thinking animation or static image"""
        if self.ui_components and self.ui_components['chat_log']:
            with self.ui_components['chat_log']:
                with ui.card().classes('w-full p-3 mb-2').style('background: #f3e5f5;'):
                    ui.label('Darwin is thinking...').classes('text-purple-700 italic')

    def _play_response_video(self, video_path, response_text):
        """Play the lip-synced response video and update chat"""
        # Update video player
        ui.run_javascript(f'updateMainVideo("{video_path}")')
        
        # Update chat with Darwin's response
        if self.ui_components and self.ui_components['chat_log']:
            with self.ui_components['chat_log']:
                # Remove thinking message and add actual response
                with ui.card().classes('w-full p-3 mb-2').style('background: #f0fdf4;'):
                    ui.label('Darwin:').classes('font-bold text-green-800')
                    ui.label(response_text).classes('text-gray-800')

    def _get_video_duration(self, video_path):
        """Get video duration using ffprobe"""
        try:
            import subprocess
            cmd = [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            return 5.0  # Default fallback

    def _return_to_idle(self):
        """Return system to idle state"""
        print(f"{Fore.CYAN}[MAIN] Returning to idle state{Style.RESET_ALL}")
        self.current_mode = "idle"
        
        # Restart idle video loop
        self.node_system.current_node = "node_1"
        self.node_system.is_interrupted = False
        
        # Give a small delay before restarting
        time.sleep(1.0)
        
        # Restart idle playing
        self.node_system.start_idle_playing(self.handle_video_ready)

    def handle_voice_change(self, voice_name):
        """Handle voice model change"""
        voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", voice_name)
        
        # Add .onnx extension if not present
        if not voice_path.endswith('.onnx'):
            voice_path += '.onnx'
        
        print(f"{Fore.CYAN}[MAIN] Changing voice to: {voice_name}{Style.RESET_ALL}")
        set_voice_model(voice_path)

    def start(self):
        """Start the avatar system"""
        print(f"{Fore.GREEN}[MAIN] Starting Darwin Avatar System{Style.RESET_ALL}")
        
        # Build UI with callbacks
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_user_input,
            voice_change_callback=self.handle_voice_change
        )
        
        # Pass video manager to UI
        if 'set_video_manager' in self.ui_components:
            self.ui_components['set_video_manager'](self.node_system)
        
        # Start idle video playing
        self.node_system.start_idle_playing(self.handle_video_ready)
        
        # Add cleanup on app shutdown
        @app.on_shutdown
        def cleanup():
            print(f"{Fore.YELLOW}[MAIN] Shutting down...{Style.RESET_ALL}")
            self.node_system.stop_playing()

# Main execution
if __name__ == "__main__":
    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}   DARWIN AVATAR SYSTEM - With Simplified Lip Sync{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
    
    # Initialize and start the system
    avatar_system = DarwinAvatarSystem()
    avatar_system.start()
    
    # Start the UI
    ui.run(
        title="Darwin Avatar Chat",
        port=8080,
        reload=False,
        dark=None
    )