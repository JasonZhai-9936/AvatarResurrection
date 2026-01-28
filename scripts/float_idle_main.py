# float_idle_main.py - Fixed Transitions
# UPDATED: Uses ui.py's native crossfader (window.updateVideoSource) instead of hard cuts
# REMOVED: add_video_compatibility_layer (conflicted with ui.py)

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
import re
import socket

init(autoreset=True)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio
from continuous_float_idle import ContinuousFloatIdle
from idle_audio_generator import IdleAudioGenerator
from ui import build_ui
from chat_message_manager import ChatMessageManager
from voice_input_manager import VoiceInputManager
from nicegui import ui as nicegui_ui
from nicegui import app as nicegui_app

# ============================================================================
# CONFIGURATION
# ============================================================================

USE_FLOAT_LIPSYNC = True
USE_PREGENERATED_RESPONSE = False 

FLOAT_CONFIG = {
    "ref_path": "assets/main2.png", 
    "ckpt_path": "./checkpoints/float.pth",
    "wav2vec_model_path": "./checkpoints/wav2vec2-base-960h",
    "audio2emotion_path": "./checkpoints/wav2vec-english-speech-emotion-recognition",
    "nfe": 7,              
    "fps": 25,              
    "a_cfg_scale": 2.0,     
    "r_cfg_scale": 1.0,     
    "e_cfg_scale": 1.0,     
    "seed": 15,             
    "no_crop": False         
}

IDLE_CONFIG = {
    "preload_clips": 1,
    "max_buffer": 100,
    "clip_duration": 5.0,
    "use_ambient": False
}


class FloatIdleVideoManager:
    """Simple video manager for FLOAT idle - works with any UI"""
    
    def __init__(self, continuous_idle_system):
        self.continuous_idle = continuous_idle_system
        self.current_mode = "float_idle"
        self.current_video_path = None
        self.video_update_callback = None
        
        # Speech reaction directory
        self.speech_reaction_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin", "speech_reaction")
        
        print(f"{Fore.GREEN}[VIDEO] Simple video manager initialized{Style.RESET_ALL}")
    
    def set_video_update_callback(self, callback):
        self.video_update_callback = callback
        print(f"{Fore.CYAN}[VIDEO] Video update callback set{Style.RESET_ALL}")
    
    def play_next_float_idle_clip(self):
        """Play next FLOAT idle clip"""
        # print(f"{Fore.CYAN}[VIDEO] play_next_float_idle_clip() called{Style.RESET_ALL}")
        
        if self.continuous_idle:
            video_path = self.continuous_idle.get_next_clip()
            
            if video_path:
                self.current_mode = "float_idle"
                self.current_video_path = video_path
                self._update_video(video_path)
                return True
            else:
                print(f"{Fore.RED}[VIDEO] No clip available from buffer{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[VIDEO] No continuous_idle system{Style.RESET_ALL}")
        
        return False
    
    def play_lipsync_video(self, video_path: str):
        """Play a lip-sync response video"""
        if os.path.exists(video_path):
            self.current_mode = "lipsync"
            self.current_video_path = video_path
            self._update_video(video_path)
            return True
        return False
    
    def on_video_ended(self):
        """Called when video ends"""
        # print(f"{Fore.BLUE}[VIDEO] Video ended, returning to idle{Style.RESET_ALL}")
        self.play_next_float_idle_clip()
    
    def _update_video(self, video_path: str):
        """Update video in UI"""
        # Check if file exists
        if not os.path.exists(video_path):
            print(f"{Fore.RED}[VIDEO] ERROR: Video file does not exist: {video_path}{Style.RESET_ALL}")
            return
        
        if self.video_update_callback:
            rel_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
            video_url = f"/{rel_path}"
            # print(f"{Fore.GREEN}[VIDEO] Calling callback with URL: {video_url}{Style.RESET_ALL}")
            self.video_update_callback(video_url)
        else:
            print(f"{Fore.RED}[VIDEO] No video update callback set!{Style.RESET_ALL}")


class DarwinChatbotComplete:
    """Complete FLOAT idle chatbot - drop-in replacement"""
    
    def __init__(self):
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}DARWIN CHATBOT - FLOAT IDLE (CROSSFADE ENABLED){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        self.voice_manager = VoiceInputManager(PROJECT_DIR)
        self.typing_timer = None
        self.typing_lock = threading.Lock()
        self.TYPING_TIMEOUT = 1.0
        
        # Initialize FLOAT
        self.lipsync_system = self.initialize_lipsync()
        
        # Initialize idle systems
        self.idle_audio_gen = IdleAudioGenerator(PROJECT_DIR)
        self.continuous_idle = ContinuousFloatIdle(
            project_dir=PROJECT_DIR,
            float_lipsync=self.lipsync_system,
            idle_audio_generator=self.idle_audio_gen
        )
        self.continuous_idle.max_clips = IDLE_CONFIG['max_buffer']
        self.continuous_idle.clip_duration = IDLE_CONFIG['clip_duration']
        
        # Simple video manager
        self.video_manager = FloatIdleVideoManager(self.continuous_idle)
        
        # State
        self.is_recording = False
        self.current_voice_msg_id = None
        self.final_voice_text = ""
        self.chat_log = None
        self.message_manager = None
        self.ui_components = None
        self.is_processing = False 
        self._shutdown_flag = False
        
        # Video handling
        self.video_event_queue = queue.Queue()
        self.chunk_queue = asyncio.Queue()
        self.current_response_id_playing = None
        self.is_chunk_playing = False
        
        # Preload state
        self.preload_complete = False
        self.preload_progress = 0
        self.preload_total = IDLE_CONFIG['preload_clips']
        
        print(f"{Fore.GREEN}[MAIN] Chatbot initialized{Style.RESET_ALL}")

    def initialize_lipsync(self):
        try:
            print(f"{Fore.CYAN}[MAIN] Initializing FLOAT...{Style.RESET_ALL}")
            from float_lipsync_subprocess import FloatLipsync
            float_lipsync = FloatLipsync(PROJECT_DIR, FLOAT_CONFIG)
            
            if not float_lipsync.initialize():
                raise RuntimeError("FLOAT failed to initialize")
            
            print(f"{Fore.GREEN}[MAIN] ✓ FLOAT ready{Style.RESET_ALL}")
            return float_lipsync
        except Exception as e:
            print(f"{Fore.RED}[MAIN] FLOAT error: {e}{Style.RESET_ALL}")
            raise

    def preload_clips_async(self):
        """Preload clips in background"""
        def preload():
            try:
                print(f"{Fore.CYAN}[PRELOAD] Starting...{Style.RESET_ALL}")
                for i in range(self.preload_total):
                    if self._shutdown_flag:
                        break
                    self.continuous_idle._generate_single_clip()
                    self.preload_progress = i + 1
                    
                    # Start video after first clip
                    if i == 0:
                        print(f"{Fore.GREEN}[PRELOAD] First clip ready - starting video{Style.RESET_ALL}")
                        self.queue_video_start()
                
                self.preload_complete = True
                self.continuous_idle.start_generation()
                print(f"{Fore.GREEN}[PRELOAD] Complete!{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[PRELOAD] Error: {e}{Style.RESET_ALL}")
        
        threading.Thread(target=preload, daemon=True).start()

    def queue_video_start(self):
        """Queue video to start"""
        self.video_event_queue.put({'type': 'start'})

    def setup_ui(self):
        """Setup UI with video compatibility built-in"""
        available_mics = self.voice_manager.get_available_microphones()
        
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_ui_interaction,
            voice_change_callback=self.handle_voice_change,
            video_manager=self.video_manager,
            available_mics=available_mics,
            mic_change_callback=self.handle_mic_select,
            typing_callback=self.on_typing_detected
        )
        
        self.chat_log = self.ui_components['chat_log']
        self.message_manager = ChatMessageManager(self.chat_log)
        self.video_manager.set_video_update_callback(self.queue_video_update)
        
        # --- FIXED: REMOVED COMPATIBILITY LAYER ---
        # We now rely on ui.py's native window.updateVideoSource for crossfading
        
        # Add status
        with self.chat_log:
            with nicegui_ui.row().classes('w-full justify-center'):
                nicegui_ui.label(
                    f'Generating clips...'
                ).classes('text-lg font-bold text-orange-600').bind_text_from(
                    self, 'status_text'
                )
        
        nicegui_ui.timer(0.2, self.process_video_events)
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete{Style.RESET_ALL}")
    
    @property
    def status_text(self):
        """Status text for UI"""
        if self.preload_complete:
            return f"✓ Ready ({self.continuous_idle.get_buffer_status()['buffer_size']} clips)"
        return f"Loading clips: {self.preload_progress}/{self.preload_total}..."

    def handle_mic_select(self, device_index):
        self.voice_manager.set_input_device(device_index)

    def on_typing_detected(self):
        pass

    def handle_voice_change(self, voice_name: str):
        try:
            voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", voice_name + ".onnx")
            from enhanced_tts_piper import set_voice_model
            set_voice_model(voice_path)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Voice change error: {e}{Style.RESET_ALL}")

    def queue_video_update(self, video_url: str):
        self.video_event_queue.put({'type': 'update', 'url': video_url})

    def queue_video_ended_event(self):
        self.video_event_queue.put({'type': 'ended'})

    def process_video_events(self):
        """Process video events"""
        try:
            while not self.video_event_queue.empty():
                event = self.video_event_queue.get_nowait()
                
                # print(f"{Fore.MAGENTA}[DEBUG] Processing video event: {event['type']}{Style.RESET_ALL}")
                
                if event['type'] == 'update':
                    self.update_video_in_ui(event['url'])
                elif event['type'] == 'ended':
                    self.handle_video_ended()
                elif event['type'] == 'start':
                    # Force start playing first clip
                    print(f"{Fore.GREEN}[DEBUG] Start event received - playing first clip{Style.RESET_ALL}")
                    clip_path = self.video_manager.play_next_float_idle_clip()
                    if clip_path:
                        print(f"{Fore.GREEN}[DEBUG] First clip started successfully{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}[DEBUG] Failed to start first clip{Style.RESET_ALL}")
        except queue.Empty:
            pass
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Event error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()

    def update_video_in_ui(self, video_url: str):
        """Update video in UI using FLASH-FREE CROSSFADE"""
        try:
            # --- FIXED: Use window.updateVideoSource from ui.py ---
            # This triggers the dual-video opacity crossfade instead of a hard src swap
            js = f"""
            if (window.updateVideoSource) {{
                window.updateVideoSource('{video_url}');
            }} else {{
                console.error('[MAIN] window.updateVideoSource not found in UI!');
            }}
            """
            nicegui_ui.run_javascript(js)
        except Exception as e:
            print(f"{Fore.YELLOW}[UI] Update skipped: {e}{Style.RESET_ALL}")

    def handle_video_ended(self):
        """Handle video end"""
        if self.chunk_queue.empty() or not self.is_chunk_playing:
            self.video_manager.on_video_ended()
        else:
            self.is_chunk_playing = False
            asyncio.create_task(self.play_next_chunk())

    async def handle_ui_interaction(self, message: str, mode: str = "text"):
        """Handle user message - async for UI compatibility"""
        if not message or not message.strip():
            return
        
        if not self.preload_complete:
            print(f"{Fore.YELLOW}[MAIN] Still loading...{Style.RESET_ALL}")
            return
        
        if self.is_processing:
            return
        
        # Stop voice recording if active
        if self.is_recording:
            self.is_recording = False
            self.voice_manager.stop_listening()
        
        self.message_manager.add_user_message(message.strip())
        asyncio.create_task(self.generate_and_play_response(message.strip()))

    async def generate_and_play_response(self, user_message: str):
        """Generate and play response"""
        response_id = f"darwin_msg_{self.message_manager.message_counter}"
        self.message_manager.message_counter += 1
        
        self.message_manager.add_typing_indicator(response_id)
        
        try:
            self.is_processing = True
            
            print(f"{Fore.CYAN}[MAIN] Generating response...{Style.RESET_ALL}")
            llm_response = await asyncio.to_thread(generate_darwin_response, user_message)
            
            # Handle dict response from LLM (extract text)
            if isinstance(llm_response, dict):
                full_response = llm_response.get('response', '') or llm_response.get('text', '')
                print(f"{Fore.CYAN}[MAIN] Extracted text from dict response{Style.RESET_ALL}")
            else:
                full_response = llm_response
            
            if not full_response or not full_response.strip():
                self.queue_typing_indicator(response_id, False)
                self.message_manager.add_error_message("Failed to generate response")
                return
            
            sentences = self._split_into_sentences(full_response)
            
            # Remove typing indicator and add bot message
            self.queue_typing_indicator(response_id, False)
            self.message_manager.add_bot_message(response_id)
            
            for idx, sentence in enumerate(sentences):
                if not sentence.strip():
                    continue
                
                print(f"{Fore.CYAN}[MAIN] Processing sentence {idx+1}/{len(sentences)}{Style.RESET_ALL}")
                
                audio_path = await asyncio.to_thread(
                    generate_complete_audio,
                    sentence,
                    f"darwin_sentence_{idx}"
                )
                
                if not audio_path:
                    continue
                
                video_path = await self._generate_float_lipsync(audio_path, sentence)
                
                if video_path:
                    duration = self.get_video_duration(video_path)
                    await self.chunk_queue.put({
                        'id': response_id,
                        'video_path': video_path,
                        'text': sentence,
                        'duration': duration
                    })
                    
                    if not self.is_chunk_playing:
                        asyncio.create_task(self.play_next_chunk())

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.queue_typing_indicator(response_id, False)
        finally:
            self.is_processing = False
            
    async def play_next_chunk(self):
        """Play next response chunk"""
        try:
            chunk_data = self.chunk_queue.get_nowait()
        except asyncio.QueueEmpty:
            if not self.is_processing:
                self.is_chunk_playing = False
                self.current_response_id_playing = None
                self.video_manager.play_next_float_idle_clip()
            return
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Queue error: {e}{Style.RESET_ALL}")
            self.is_chunk_playing = False
            return

        self.is_chunk_playing = True
        response_id = chunk_data['id']

        try:
            if response_id != self.current_response_id_playing:
                self.current_response_id_playing = response_id
                self.queue_clear_message_content(response_id)
            
            # Play the video
            self.video_manager.play_lipsync_video(chunk_data['video_path'])
            
            # Stream the text
            self.queue_text_stream(response_id, chunk_data['text'], chunk_data['duration'])
            
            print(f"{Fore.GREEN}[MAIN] Playing chunk: {chunk_data['text'][:50]}...{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Chunk error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.is_chunk_playing = False

    def _split_into_sentences(self, text: str) -> list:
        text = text.strip()
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    async def _generate_float_lipsync(self, audio_path: str, text: str) -> Optional[str]:
        def generate():
            try:
                return self.lipsync_system.generate_lipsync(audio_path=audio_path)
            except Exception as e:
                print(f"{Fore.RED}[FLOAT] Error: {e}{Style.RESET_ALL}")
                return None
        
        return await asyncio.to_thread(generate)

    def get_video_duration(self, video_path: str) -> float:
        try:
            cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            return 5.0

    def queue_typing_indicator(self, msg_id: str, show: bool):
        """Queue typing indicator update - safe for background threads"""
        def update():
            try:
                js = f"if (window.updateTypingIndicator) {{ window.updateTypingIndicator('{msg_id}', {str(show).lower()}); }}"
                nicegui_ui.run_javascript(js)
            except Exception as e:
                pass
        try:
            update()
        except:
            try:
                nicegui_ui.timer(0.1, update, once=True)
            except:
                pass

    def queue_clear_message_content(self, msg_id: str):
        """Queue message content clear - safe for background threads"""
        def update():
            try:
                js = f"if (window.clearMessageContent) {{ window.clearMessageContent('{msg_id}'); }}"
                nicegui_ui.run_javascript(js)
            except:
                pass
        try:
            update()
        except:
            try:
                nicegui_ui.timer(0.1, update, once=True)
            except:
                pass

    def queue_text_stream(self, msg_id: str, text: str, duration: float):
        """Queue text streaming - safe for background threads"""
        def update():
            try:
                text_escaped = text.replace("'", "\\'").replace("\n", "\\n")
                js = f"if (window.streamText) {{ window.streamText('{msg_id}', '{text_escaped}', {duration}); }}"
                nicegui_ui.run_javascript(js)
            except:
                pass
        try:
            update()
        except:
            try:
                nicegui_ui.timer(0.1, update, once=True)
            except:
                pass

    def cleanup(self):
        print(f"{Fore.YELLOW}[MAIN] Cleaning up...{Style.RESET_ALL}")
        self._shutdown_flag = True
        
        if hasattr(self, 'continuous_idle'):
            self.continuous_idle.stop_generation()
        
        if self.lipsync_system:
            try:
                self.lipsync_system.cleanup()
            except:
                pass

    def setup_signal_handlers(self):
        def signal_handler(signum, frame):
            print(f"\n{Fore.YELLOW}[MAIN] Shutting down...{Style.RESET_ALL}")
            self.cleanup()
            time.sleep(1)
            os._exit(0)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def setup_api_routes(self):
        from nicegui import app
        @app.post('/api/video-ended')
        async def video_ended_api():
            self.queue_video_ended_event()
            return {"status": "ok"}

    def run(self):
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Darwin Chatbot - FLOAT Idle{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        
        try:
            self.setup_signal_handlers()
            from nicegui import app
            
            def handle_asyncio_exception(loop, context):
                exception = context.get('exception')
                if isinstance(exception, ConnectionResetError):
                    return
                loop.default_exception_handler(context)

            app.on_startup(lambda: asyncio.get_event_loop().set_exception_handler(handle_asyncio_exception))

            from fastapi.staticfiles import StaticFiles
            
            app.mount('/avatars', StaticFiles(directory=os.path.join(PROJECT_DIR, 'avatars')), name='avatars')
            app.mount('/tempstream', StaticFiles(directory=os.path.join(PROJECT_DIR, 'tempstream')), name='tempstream')
            
            self.setup_api_routes()
            self.setup_ui()
            self.preload_clips_async()
            
            print(f"{Fore.GREEN}[MAIN] Starting...{Style.RESET_ALL}")
            
            nicegui_ui.run(
                title="Darwin - FLOAT Idle",
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
    chatbot = None
    try:
        chatbot = DarwinChatbotComplete()
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