# main.py - Darwin Chatbot with STREAMING TEXT synchronized to video (FIXED)

import os
import sys
import time
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
from colorama import Fore, Style, init
import threading
import signal
import queue

init(autoreset=True)

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio
from lipsync_crossfade import SimplifiedLipSyncSystem
from simplified_video_manager import SimplifiedVideoManager
from ui import build_ui
from nicegui import ui as nicegui_ui

class DarwinChatbot:
    """Main chatbot class with streaming text synchronized to video duration"""
    
    def __init__(self):
        self.video_manager = SimplifiedVideoManager(avatar_name="Darwin")
        self.lipsync_system = self.initialize_lipsync()
        
        self.chat_log = None
        self.ui_components = None
        
        self.is_processing = False
        self._shutdown_flag = False
        
        # Event queue for video control AND text streaming (thread-safe)
        self.video_event_queue = queue.Queue()
        
        # Track current response for streaming
        self.current_response_id = 0
        
        print(f"{Fore.GREEN}[MAIN] Darwin Chatbot initialized with STREAMING TEXT{Style.RESET_ALL}")

    def initialize_lipsync(self) -> SimplifiedLipSyncSystem:
        """Initialize the lip sync system"""
        archive_dir = os.path.join(PROJECT_DIR, "archive")
        
        clip_odds = {
            "circle1": 0.5,
            "eye_look1": 0.5,
            "idle2": 1.0,
            "slight_look1": 1.0,
            "slight_shake1": 1,
            "slight_shake2": 1.0,
            "nod1": 1.0,
            "main2": 1.0, 
        }
        
        return SimplifiedLipSyncSystem(
            archive_directory=archive_dir,
            clip_odds=clip_odds,
            avoid_repeats=True
        )

    def get_video_duration(self, video_path: str) -> float:
        """Get the duration of a video file using ffprobe"""
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
            return 5.0  # Default fallback duration

    def setup_ui(self):
        """Set up the UI"""
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_user_input,
            voice_change_callback=self.handle_voice_change,
            video_manager=self.video_manager
        )
        
        self.chat_log = self.ui_components['chat_log']
        self.video_manager.set_video_update_callback(self.queue_video_update)
        
        # Process events every 100ms
        nicegui_ui.timer(0.1, self.process_video_events)
        nicegui_ui.timer(1.0, self.initialize_video_system, once=True)
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete with STREAMING TEXT support{Style.RESET_ALL}")

    def queue_video_update(self, video_url: str):
        """Queue a video update"""
        try:
            self.video_event_queue.put(('update_video', video_url))
            print(f"{Fore.CYAN}[MAIN] Queued video update: {video_url.split('/')[-1]}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing video update: {e}{Style.RESET_ALL}")
    
    def queue_text_stream(self, element_id: str, text: str, duration: float):
        """Queue a text streaming event"""
        try:
            self.video_event_queue.put(('stream_text', {
                'element_id': element_id,
                'text': text,
                'duration': duration
            }))
            print(f"{Fore.MAGENTA}[MAIN] Queued text stream: {len(text)} chars over {duration:.2f}s{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing text stream: {e}{Style.RESET_ALL}")

    def process_video_events(self):
        """Process video events AND text streaming from the queue"""
        try:
            while not self.video_event_queue.empty():
                event_type, data = self.video_event_queue.get_nowait()
                
                if event_type == 'update_video':
                    self.execute_video_update(data)
                elif event_type == 'video_ended':
                    self.handle_video_ended_in_context()
                elif event_type == 'stream_text':
                    self.execute_text_stream(data)
                    
        except queue.Empty:
            pass
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error processing video events: {e}{Style.RESET_ALL}")

    def execute_video_update(self, video_url: str):
        """Execute video update in proper UI context"""
        try:
            js_code = f'''
                if (window.updateVideoSource) {{
                    window.updateVideoSource('{video_url}');
                }} else {{
                    console.error('[MAIN] updateVideoSource function not ready');
                }}
            '''
            nicegui_ui.run_javascript(js_code)
            print(f"{Fore.GREEN}[MAIN] Video updated: {video_url.split('/')[-1]}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}[MAIN] Video update failed: {e}{Style.RESET_ALL}")
    
    def execute_text_stream(self, data: dict):
        """Execute text streaming in proper UI context"""
        try:
            element_id = data['element_id']
            text = data['text']
            duration = data['duration']
            
            # Escape the text for JavaScript
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

    def initialize_video_system(self):
        """Initialize the video system"""
        try:
            print(f"{Fore.GREEN}[MAIN] Starting video system{Style.RESET_ALL}")
            self.video_manager.play_next_idle_video()
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error initializing video: {e}{Style.RESET_ALL}")

    def queue_video_ended_event(self):
        """Queue a video ended event"""
        try:
            self.video_event_queue.put(('video_ended', None))
            print(f"{Fore.BLUE}[MAIN] Video ended event queued{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing video ended event: {e}{Style.RESET_ALL}")

    def handle_video_ended_in_context(self):
        """Handle video ended in proper UI context"""
        if self._shutdown_flag:
            return
        print(f"{Fore.BLUE}[MAIN] Processing video ended event{Style.RESET_ALL}")
        self.video_manager.on_video_ended()

    def handle_user_input(self, user_text: str):
        """Handle user input"""
        if self.is_processing:
            nicegui_ui.notify("Please wait for current response", type="warning")
            return
        
        if self._shutdown_flag:
            return
        
        asyncio.create_task(self.process_response_async(user_text))

    async def process_response_async(self, user_text: str):
        """Process user input with STREAMING text effect"""
        if self._shutdown_flag:
            return
            
        self.is_processing = True
        self.current_response_id += 1
        response_id = f"darwin_response_{self.current_response_id}"
        
        try:
            # Display user message
            if self.chat_log:
                with self.chat_log:
                    with nicegui_ui.row().classes('w-full justify-end'):
                        with nicegui_ui.card().classes('user-message'):
                            nicegui_ui.label(user_text)
            
            print(f"{Fore.CYAN}[MAIN] Processing: {user_text}{Style.RESET_ALL}")
            
            # Generate LLM response
            try:
                darwin_response = await asyncio.to_thread(generate_darwin_response, user_text)
            except AttributeError:
                loop = asyncio.get_event_loop()
                darwin_response = await loop.run_in_executor(None, generate_darwin_response, user_text)
            
            if not darwin_response or self._shutdown_flag:
                return
            
            print(f"{Fore.GREEN}[MAIN] Response: {darwin_response}{Style.RESET_ALL}")
            
            # Create EMPTY Darwin message bubble with unique ID
            if self.chat_log and not self._shutdown_flag:
                with self.chat_log:
                    with nicegui_ui.row().classes('w-full justify-start'):
                        with nicegui_ui.card().classes('darwin-message'):
                            # Create empty label with unique ID for streaming
                            nicegui_ui.html(f'<div id="{response_id}" class="text-base"></div>')
            
            # Generate audio
            print(f"{Fore.BLUE}[MAIN] Generating audio...{Style.RESET_ALL}")
            default_voice = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-northern_english_male-medium.onnx")
            
            try:
                audio_path = await asyncio.to_thread(generate_complete_audio, darwin_response, None, default_voice)
            except AttributeError:
                loop = asyncio.get_event_loop()
                audio_path = await loop.run_in_executor(None, generate_complete_audio, darwin_response, None, default_voice)
            
            if not audio_path or not os.path.exists(audio_path) or self._shutdown_flag:
                return
            
            # Generate lipsync video
            print(f"{Fore.BLUE}[MAIN] Creating lip-sync video...{Style.RESET_ALL}")
            output_dir = os.path.join(PROJECT_DIR, "tempstream")
            
            def generate_lipsync():
                try:
                    return self.lipsync_system.generate_lip_sync_video(
                        audio_file=audio_path,
                        output_file=None,
                        output_dir=output_dir,
                        use_sequential=True
                    )
                except Exception as e:
                    print(f"Lipsync error: {e}")
                    return None
            
            try:
                lipsync_video = await asyncio.to_thread(generate_lipsync)
            except AttributeError:
                loop = asyncio.get_event_loop()
                lipsync_video = await loop.run_in_executor(None, generate_lipsync)
            
            if not lipsync_video or not os.path.exists(lipsync_video) or self._shutdown_flag:
                return
            
            print(f"{Fore.GREEN}[MAIN] Lipsync created: {os.path.basename(lipsync_video)}{Style.RESET_ALL}")
            
            # Get video duration for streaming synchronization
            video_duration = self.get_video_duration(lipsync_video)
            
            # Play the lipsync video
            self.video_manager.play_lipsync_video(lipsync_video)
            print(f"{Fore.CYAN}[MAIN] Playing lipsync video{Style.RESET_ALL}")
            
            # QUEUE the streaming text event (instead of running it directly)
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
        finally:
            self.is_processing = False

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

    def setup_signal_handlers(self):
        """Set up signal handlers"""
        def signal_handler(signum, frame):
            print(f"\n{Fore.YELLOW}[MAIN] Shutting down...{Style.RESET_ALL}")
            self.cleanup()
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
        print(f"{Fore.YELLOW}Darwin Chatbot - Streaming Text Edition{Style.RESET_ALL}")
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
            
            print(f"{Fore.GREEN}[MAIN] System ready with STREAMING TEXT{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[MAIN] Text will reveal progressively during video playback{Style.RESET_ALL}")
            
            nicegui_ui.run(
                title="Darwin Chatbot - Streaming Text",
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
    main()