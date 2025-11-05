# final_main.py - Darwin Chatbot with EMOTIONAL lip-sync and FLOAT support

import os
import sys
import time
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict
from colorama import Fore, Style, init
import threading
import signal
import queue

init(autoreset=True)

# Set PROJECT_DIR to be the parent directory of 'scripts'
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

# Import existing modules
from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio
from simplified_video_manager import SimplifiedVideoManager
from ui import build_ui
from chat_message_manager import ChatMessageManager
from nicegui import ui as nicegui_ui

# ============================================================================
# CONFIGURATION - Edit these settings directly
# ============================================================================

# Choose lipsync mode: False = Crossfade (default), True = FLOAT
# <<<<< THIS IS THE NEW CONFIGURATION VARIABLE >>>>>
USE_FLOAT_LIPSYNC = True

# FLOAT model configuration (only used if USE_FLOAT_LIPSYNC = True)
# This config is passed to the daemon.
FLOAT_CONFIG = {
    "ref_path": "assets/main2.png", # Default reference image
    "ckpt_path": "./checkpoints/float.pth",
    "wav2vec_model_path": "./checkpoints/wav2vec2-base-960h",
    "audio2emotion_path": "./checkpoints/wav2vec-english-speech-emotion-recognition",
    "nfe": 10,              # Number of function evaluations (higher = better quality, slower)
    "fps": 25,              # Frames per second
    "a_cfg_scale": 2.0,     # Audio guidance scale
    "r_cfg_scale": 1.0,     # Reference image guidance scale
    "e_cfg_scale": 1.0,     # Emotion guidance scale
    "seed": 15,             # Random seed
    "no_crop": False         # Use no_crop
}


class DarwinChatbot:
    """Main chatbot with emotional lip-sync and FLOAT support"""
    
    def __init__(self):
        # Use configuration from constants above
        self.use_float = USE_FLOAT_LIPSYNC
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}DARWIN CHATBOT INITIALIZATION{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[CONFIG] Lipsync mode: {'FLOAT' if self.use_float else 'Crossfade'}{Style.RESET_ALL}\n")
        
        self.video_manager = SimplifiedVideoManager(avatar_name="Darwin")
        
        # This will call either _initialize_float_lipsync or _initialize_crossfade_lipsync
        # based on the USE_FLOAT_LIPSYNC flag.
        self.lipsync_system = self.initialize_lipsync()
        
        self.chat_log = None
        self.message_manager = None  # Will be initialized in setup_ui
        self.ui_components = None
        
        self.is_processing = False
        self._shutdown_flag = False
        
        self.video_event_queue = queue.Queue()
        self.current_response_id = 0
        
        print(f"{Fore.GREEN}[MAIN] Darwin Chatbot initialized{Style.RESET_ALL}")

    def initialize_lipsync(self):
        """Initialize lip-sync system based on config"""
        if self.use_float:
            # <<<<< MODIFIED to call new subprocess-based FLOAT initializer >>>>>
            return self._initialize_float_lipsync()
        else:
            return self._initialize_crossfade_lipsync()
    
    def _initialize_float_lipsync(self):
        """
        Initialize FLOAT lipsync system using the subprocess manager.
        This starts the daemon in the 'FLOAT' conda env.
        """
        try:
            print(f"{Fore.CYAN}[MAIN] Initializing FLOAT lipsync system via subprocess...{Style.RESET_ALL}")
            
            # Import FLOAT module (subprocess-based)
            from float_lipsync_subprocess import FloatLipsync
            
            # Create instance of the subprocess manager
            # Pass the project dir and the config dict
            float_lipsync = FloatLipsync(PROJECT_DIR, FLOAT_CONFIG)
            
            # Pre-initialize model and preprocess image in the daemon
            # This will block until the daemon is ready
            print(f"{Fore.CYAN}[MAIN] Loading FLOAT model in conda environment... (This is slow){Style.RESET_ALL}")
            if not float_lipsync.initialize():
                raise RuntimeError("FLOAT daemon failed to initialize.")
            
            print(f"{Fore.GREEN}[MAIN] ✓ FLOAT lipsync system ready{Style.RESET_ALL}\n")
            return float_lipsync
            
        except ImportError as e:
            print(f"{Fore.RED}[MAIN] Failed to import 'float_lipsync_subprocess'. Make sure 'float_lipsync_subprocess.py' is in the 'scripts' directory.{Style.RESET_ALL}")
            print(f"{Fore.RED}[MAIN] Error details: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[MAIN] Falling back to crossfade lipsync{Style.RESET_ALL}")
            self.use_float = False # Force fallback
            return self._initialize_crossfade_lipsync()
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Failed to initialize FLOAT: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            print(f"{Fore.YELLOW}[MAIN] Falling back to crossfade lipsync{Style.RESET_ALL}")
            self.use_float = False # Force fallback
            return self._initialize_crossfade_lipsync()
    
    def _initialize_crossfade_lipsync(self):
        """Initialize crossfade lipsync system"""
        print(f"{Fore.CYAN}[MAIN] Initializing crossfade lipsync system...{Style.RESET_ALL}")
        
        from ws_lipsync_crossfade import WhisperAlignedLipSync
        
        archive_dir = os.path.join(PROJECT_DIR, "archive")
        
        system = WhisperAlignedLipSync(
            archive_directory=archive_dir
            # Add other config from ws_lipsync_crossfade.py __main__ if needed
        )
        
        print(f"{Fore.GREEN}[MAIN] ✓ Crossfade lipsync system ready{Style.RESET_ALL}\n")
        return system

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration"""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            print(f"{Fore.CYAN}[MAIN] Video duration: {duration:.2f}s{Style.RESET_ALL}")
            return duration
        except Exception as e:
            print(f"{Fore.YELLOW}[MAIN] Could not get video duration: {e}{Style.RESET_ALL}")
            return 5.0

    def setup_ui(self):
        """Set up UI"""
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_user_input,
            voice_change_callback=self.handle_voice_change,
            video_manager=self.video_manager
        )
        
        self.chat_log = self.ui_components['chat_log']
        
        # Initialize the ChatMessageManager
        self.message_manager = ChatMessageManager(self.chat_log)
        
        self.video_manager.set_video_update_callback(self.queue_video_update)
        
        nicegui_ui.timer(0.1, self.process_video_events)
        nicegui_ui.timer(1.0, self.initialize_video_system, once=True)
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete{Style.RESET_ALL}")

    def queue_video_update(self, video_url: str):
        """Queue video update"""
        try:
            self.video_event_queue.put(('update_video', video_url))
            print(f"{Fore.CYAN}[MAIN] Queued video update: {video_url.split('/')[-1]}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing video update: {e}{Style.RESET_ALL}")
    
    def queue_text_stream(self, element_id: str, text: str, duration: float):
        """Queue text streaming"""
        try:
            self.video_event_queue.put(('stream_text', {
                'element_id': element_id,
                'text': text,
                'duration': duration
            }))
            print(f"{Fore.CYAN}[MAIN] Queued text stream{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing text stream: {e}{Style.RESET_ALL}")
    
    def queue_typing_indicator(self, element_id: str, show: bool):
        """Queue typing indicator update"""
        try:
            self.video_event_queue.put(('typing_indicator', {
                'element_id': element_id,
                'show': show
            }))
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing typing indicator: {e}{Style.RESET_ALL}")
    
    def queue_video_ended_event(self):
        """Queue video ended event"""
        try:
            self.video_event_queue.put(('video_ended', None))
            print(f"{Fore.BLUE}[MAIN] Video ended event queued{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing video ended event: {e}{Style.RESET_ALL}")
    
    def process_video_events(self):
        """Process all queued video events"""
        while not self.video_event_queue.empty():
            try:
                event_type, data = self.video_event_queue.get_nowait()
                
                if event_type == 'update_video':
                    self.execute_video_update(data)
                elif event_type == 'stream_text':
                    self.execute_text_stream(data)
                elif event_type == 'typing_indicator':
                    self.execute_typing_indicator(data)
                elif event_type == 'video_ended':
                    self.handle_video_ended_in_context()
                    
            except queue.Empty:
                break
            except Exception as e:
                print(f"{Fore.RED}[MAIN] Error processing event: {e}{Style.RESET_ALL}")
    
    def execute_video_update(self, video_url: str):
        """Execute video update"""
        try:
            js_code = f'''
                if (window.updateVideoSource) {{
                    window.updateVideoSource('{video_url}');
                }} else {{
                    console.error('[MAIN] updateVideoSource not ready');
                }}
            '''
            nicegui_ui.run_javascript(js_code)
            print(f"{Fore.GREEN}[MAIN] Video updated: {video_url.split('/')[-1]}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Video update failed: {e}{Style.RESET_ALL}")
    
    def execute_text_stream(self, data: dict):
        """Execute text streaming"""
        try:
            element_id = data['element_id']
            text = data['text']
            duration = data['duration']
            
            escaped_text = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')
            
            js_code = f'''
                if (window.streamText) {{
                    window.streamText('{element_id}', '{escaped_text}', {duration});
                }} else {{
                    console.error('[MAIN] streamText function not ready');
                    const element = document.getElementById('{element_id}');
                    if (element) element.textContent = '{escaped_text}';
                }}
            '''
            
            nicegui_ui.run_javascript(js_code)
            print(f"{Fore.GREEN}[MAIN] Text streaming started: {len(text)} chars{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Text streaming failed: {e}{Style.RESET_ALL}")
    
    def execute_typing_indicator(self, data: dict):
        """Execute typing indicator animation"""
        try:
            element_id = data['element_id']
            show = data['show']
            
            if show:
                js_code = f'''
                    if (window.startTypingIndicator) {{
                        window.startTypingIndicator('{element_id}');
                    }} else {{
                        console.error('[MAIN] startTypingIndicator not ready');
                    }}
                '''
            else:
                js_code = f'''
                    if (window.stopTypingIndicator) {{
                        window.stopTypingIndicator('{element_id}');
                    }} else {{
                        console.error('[MAIN] stopTypingIndicator not ready');
                    }}
                '''
            
            nicegui_ui.run_javascript(js_code)
            print(f"{Fore.GREEN}[MAIN] Typing indicator {'started' if show else 'stopped'}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Typing indicator failed: {e}{Style.RESET_ALL}")

    def handle_video_ended_in_context(self):
        """Handle video ended event"""
        try:
            self.video_manager.on_video_ended()
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error handling video ended: {e}{Style.RESET_ALL}")

    def initialize_video_system(self):
        """Initialize video system"""
        try:
            print(f"{Fore.CYAN}[MAIN] Initializing video system...{Style.RESET_ALL}")
            self.video_manager.play_next_idle_video()
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error initializing video: {e}{Style.RESET_ALL}")

    async def handle_user_input(self, user_text: str):
        """Handle user input and generate response"""
        if self.is_processing:
            return
        
        self.is_processing = True
        response_id = f"response_{self.current_response_id + 1}" # Define here for finally block
        
        try:
            if not user_text or not user_text.strip():
                return
            
            print(f"\n{Fore.CYAN}[USER] {user_text}{Style.RESET_ALL}")
            
            # Queue pre-generated response IMMEDIATELY after user input
            self.video_manager.queue_pregenerated_response()
            
            # Create unique response ID
            self.current_response_id += 1
            
            # Use ChatMessageManager for consistent message structure
            self.message_manager.add_user_message(user_text)
            response_id = self.message_manager.add_bot_message(response_id)
            
            # Start typing indicator
            self.queue_typing_indicator(response_id, True)
            
            # Generate response
            print(f"{Fore.BLUE}[MAIN] Generating response...{Style.RESET_ALL}")
            
            try:
                response_data = await asyncio.to_thread(generate_darwin_response, user_text)
            except AttributeError:
                loop = asyncio.get_event_loop()
                response_data = await loop.run_in_executor(None, generate_darwin_response, user_text)
            
            # Extract text and emotion
            if isinstance(response_data, dict):
                darwin_response = response_data['text']
                emotion = response_data['emotion']
            else:
                darwin_response = response_data
                emotion = 'neutral'
            
            if not darwin_response or self._shutdown_flag:
                self.queue_typing_indicator(response_id, False)
                return
            
            print(f"{Fore.GREEN}[MAIN] Response: {darwin_response}{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}[MAIN] Emotion: {emotion}{Style.RESET_ALL}")
            
            # Generate audio
            print(f"{Fore.BLUE}[MAIN] Generating audio...{Style.RESET_ALL}")
            default_voice = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-semaine-medium.onnx")
            
            try:
                audio_path = await asyncio.to_thread(generate_complete_audio, darwin_response, None, default_voice)
            except AttributeError:
                loop = asyncio.get_event_loop()
                audio_path = await loop.run_in_executor(None, generate_complete_audio, darwin_response, None, default_voice)
            
            if not audio_path or not os.path.exists(audio_path) or self._shutdown_flag:
                self.queue_typing_indicator(response_id, False)
                return
            
            print(f"{Fore.GREEN}[MAIN] Audio generated: {audio_path}{Style.RESET_ALL}")
            
            # Generate lipsync
            if self.use_float:
                lipsync_video = await self._generate_float_lipsync(audio_path, darwin_response)
            else:
                lipsync_video = await self._generate_crossfade_lipsync(audio_path, darwin_response, emotion)
            
            if not lipsync_video or not os.path.exists(lipsync_video) or self._shutdown_flag:
                self.queue_typing_indicator(response_id, False)
                return
            
            print(f"{Fore.GREEN}[MAIN] Lipsync video: {lipsync_video}{Style.RESET_ALL}")
            
            # Get video duration
            video_duration = self.get_video_duration(lipsync_video)
            
            # Play the lipsync video
            self.video_manager.play_lipsync_video(lipsync_video)
            print(f"{Fore.CYAN}[MAIN] Playing lipsync video{Style.RESET_ALL}")
            
            # Stop typing indicator and start text streaming
            self.queue_typing_indicator(response_id, False)
            
            # Queue text streaming
            print(f"{Fore.MAGENTA}[MAIN] Queueing text stream over {video_duration:.2f}s{Style.RESET_ALL}")
            self.queue_text_stream(response_id, darwin_response, video_duration)
            
            # Cleanup old files
            try:
                self.video_manager.cleanup_old_lipsync_videos(keep_last=5)
            except:
                pass
                
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error processing response: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.queue_typing_indicator(response_id, False)
        finally:
            self.is_processing = False

    async def _generate_float_lipsync(self, audio_path: str, text: str) -> Optional[str]:
        """
        Generate lipsync using the new FLOAT subprocess manager.
        'text' is unused but kept for consistent signature.
        """
        print(f"{Fore.BLUE}[MAIN] Creating FLOAT lipsync...{Style.RESET_ALL}")
        
        def generate_float():
            try:
                # self.lipsync_system is our FloatLipsync (subprocess manager) instance
                # The generate_lipsync() method takes audio_path
                return self.lipsync_system.generate_lipsync(
                    audio_path=audio_path,
                    output_filename=None # Daemon will auto-name
                )
            except Exception as e:
                print(f"{Fore.RED}[FLOAT] Error: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()
                return None
        
        try:
            # Run the blocking generation in a separate thread
            return await asyncio.to_thread(generate_float)
        except AttributeError:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, generate_float)

    async def _generate_crossfade_lipsync(self, audio_path: str, text: str, emotion: str) -> Optional[str]:
        """Generate lipsync using crossfade"""
        print(f"{Fore.BLUE}[MAIN] Creating emotional lipsync (emotion: {emotion})...{Style.RESET_ALL}")
        output_dir = os.path.join(PROJECT_DIR, "tempstream")
        
        def generate_crossfade():
            try:
                return self.lipsync_system.generate_lip_sync_video(
                    audio_file=audio_path,
                    output_file=None,
                    output_dir=output_dir,
                    use_sequential=True,
                    text=text,
                    emotion=emotion
                )
            except Exception as e:
                print(f"{Fore.RED}[CROSSFADE] Error: {e}{Style.RESET_ALL}")
                return None
        
        try:
            # Note: Fixed typo here, was generate__crossfade
            return await asyncio.to_thread(generate_crossfade)
        except AttributeError:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, generate_crossfade)

    def handle_voice_change(self, voice_name: str):
        """Handle voice change"""
        try:
            voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", voice_name + ".onnx")
            from enhanced_tts_piper import set_voice_model
            set_voice_model(voice_path)
            print(f"{Fore.GREEN}[MAIN] Voice changed to: {voice_name}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error changing voice: {e}{Style.RESET_ALL}")

    def cleanup(self):
        """Clean up resources"""
        print(f"{Fore.YELLOW}[MAIN] Cleaning up...{Style.RESET_ALL}")
        self._shutdown_flag = True
        # <<<<< ADDED CLEANUP FOR SUBPROCESS >>>>>
        if self.use_float and self.lipsync_system:
            try:
                self.lipsync_system.cleanup()
            except Exception as e:
                print(f"{Fore.RED}[MAIN] Error during lipsync cleanup: {e}{Style.RESET_ALL}")


    def setup_signal_handlers(self):
        """Set up signal handlers"""
        def signal_handler(signum, frame):
            print(f"\n{Fore.YELLOW}[MAIN] Shutting down...{Style.RESET_ALL}")
            self.cleanup()
            # Give a moment for cleanup to try
            time.sleep(1)
            os._exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def setup_api_routes(self):
        """Set up API routes for video ended notifications"""
        from nicegui import app
        
        @app.post('/api/video-ended')
        async def video_ended_api():
            """API endpoint called by JavaScript when video ends"""
            self.queue_video_ended_event()
            return {"status": "ok", "message": "Event queued"}

    def run(self):
        """Run the application"""
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Darwin Chatbot - {'FLOAT' if self.use_float else 'Emotional'} Lip-Sync{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        
        try:
            self.setup_signal_handlers()
            
            from nicegui import app
            from fastapi.staticfiles import StaticFiles
            
            # Mount static directories
            app.mount('/avatars', StaticFiles(directory=os.path.join(PROJECT_DIR, 'avatars')), name='avatars')
            app.mount('/tempstream', StaticFiles(directory=os.path.join(PROJECT_DIR, 'tempstream')), name='tempstream')
            
            # Set up API routes
            self.setup_api_routes()
            
            # Set up UI
            self.setup_ui()
            
            if self.use_float:
                print(f"{Fore.GREEN}[MAIN] FLOAT lipsync system pre-loaded and ready{Style.RESET_ALL}")
            else:
                print(f"{Fore.GREEN}[MAIN] Emotional lipsync system ready{Style.RESET_ALL}")
                print(f"{Fore.CYAN}[MAIN] Emotions: neutral, emphatic, contrastive, positive, negative{Style.RESET_ALL}")
            
            nicegui_ui.run(
                title=f"Darwin Chatbot - {'FLOAT' if self.use_float else 'Emotional'}",
                favicon="🎩",
                dark=False,
                reload=False,
                show=True,
                port=8080
            )
            
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error: {e}{Style.RESET_ALL}")
            raise
        finally:
            self.cleanup()

def main():
    """Main entry point"""
    chatbot = None
    try:
        chatbot = DarwinChatbot()
        chatbot.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[MAIN] Interrupted{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[MAIN] Fatal error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
    finally:
        if chatbot:
            chatbot.cleanup()
        print(f"{Fore.YELLOW}[MAIN] Shutdown complete{Style.RESET_ALL}")

if __name__ == "__main__":
    # This ensures that when running 'python scripts/final_main.py',
    # the PROJECT_DIR is set correctly before anything else runs.
    main()