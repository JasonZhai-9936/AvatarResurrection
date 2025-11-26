# final_main.py - Darwin Chatbot with EMOTIONAL lip-sync and FLOAT support
# <<< VERSION: Robust Connection Handling + Error Suppression >>>

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
import socket # Used for handling socket errors

init(autoreset=True)

# Set PROJECT_DIR to be the parent directory of 'scripts'
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

# Import existing modules
from LLM_Groq import generate_darwin_response
from enhanced_tts_groq import generate_complete_audio
from simplified_video_manager import SimplifiedVideoManager
from ui import build_ui
from chat_message_manager import ChatMessageManager
from voice_input_manager import VoiceInputManager
from nicegui import ui as nicegui_ui
from nicegui import app as nicegui_app

# ============================================================================
# CONFIGURATION
# ============================================================================

# Choose lipsync mode: False = Crossfade (default), True = FLOAT
USE_FLOAT_LIPSYNC = True

# Set to False to disable the pre-generated response
USE_PREGENERATED_RESPONSE = False 

# FLOAT model configuration
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


class DarwinChatbot:
    """Main chatbot with emotional lip-sync and FLOAT support"""
    
    def __init__(self):
        self.use_float = USE_FLOAT_LIPSYNC
        self.use_pregenerated = USE_PREGENERATED_RESPONSE
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}DARWIN CHATBOT INITIALIZATION{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[CONFIG] Lipsync mode: {'FLOAT' if self.use_float else 'Crossfade'}{Style.RESET_ALL}")
        
        self.video_manager = SimplifiedVideoManager(avatar_name="Darwin")
        self.voice_manager = VoiceInputManager(PROJECT_DIR)
        
        self.is_recording = False
        self.current_voice_msg_id = None
        self.final_voice_text = ""
        
        self.lipsync_system = self.initialize_lipsync()
        
        self.chat_log = None
        self.message_manager = None
        self.ui_components = None
        
        self.is_processing = False 
        self._shutdown_flag = False
        
        self.video_event_queue = queue.Queue()
        self.current_response_id = 0

        self.chunk_queue = asyncio.Queue()
        self.current_response_id_playing: Optional[str] = None
        self.is_chunk_playing: bool = False
        
        print(f"{Fore.GREEN}[MAIN] Darwin Chatbot initialized{Style.RESET_ALL}")

    def initialize_lipsync(self):
        if self.use_float:
            return self._initialize_float_lipsync()
        else:
            return self._initialize_crossfade_lipsync()
    
    def _initialize_float_lipsync(self):
        try:
            print(f"{Fore.CYAN}[MAIN] Initializing FLOAT lipsync system via subprocess...{Style.RESET_ALL}")
            from float_lipsync_subprocess import FloatLipsync
            float_lipsync = FloatLipsync(PROJECT_DIR, FLOAT_CONFIG)
            
            print(f"{Fore.CYAN}[MAIN] Loading FLOAT model... (This is slow){Style.RESET_ALL}")
            if not float_lipsync.initialize():
                raise RuntimeError("FLOAT daemon failed to initialize.")
            
            print(f"{Fore.GREEN}[MAIN] ✓ FLOAT lipsync system ready{Style.RESET_ALL}\n")
            return float_lipsync
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Failed to initialize FLOAT: {e}{Style.RESET_ALL}")
            self.use_float = False
            return self._initialize_crossfade_lipsync()
    
    def _initialize_crossfade_lipsync(self):
        print(f"{Fore.CYAN}[MAIN] Initializing crossfade lipsync system...{Style.RESET_ALL}")
        from ws_lipsync_crossfade import WhisperAlignedLipSync
        archive_dir = os.path.join(PROJECT_DIR, "archive")
        system = WhisperAlignedLipSync(archive_directory=archive_dir)
        print(f"{Fore.GREEN}[MAIN] ✓ Crossfade lipsync system ready{Style.RESET_ALL}\n")
        return system

    def get_video_duration(self, video_path: str) -> float:
        try:
            cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"{Fore.YELLOW}[MAIN] Could not get video duration: {e}{Style.RESET_ALL}")
            return 5.0

    # --- SAFE JS EXECUTION HELPER ---
    def safe_run_javascript(self, js_code: str):
        """Safely run JS, catching socket disconnect errors."""
        try:
            nicegui_ui.run_javascript(js_code)
        except (socket.error, ConnectionResetError, RuntimeError) as e:
            # Silence specific connection errors to avoid console spam
            # The user likely just refreshed or the tab died.
            print(f"{Fore.YELLOW}[SOCKET] UI Update skipped (Connection dropped): {e}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[JS_ERROR] {e}{Style.RESET_ALL}")

    def setup_ui(self):
        available_mics = self.voice_manager.get_available_microphones()
        
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_ui_interaction,
            voice_change_callback=self.handle_voice_change,
            video_manager=self.video_manager,
            available_mics=available_mics,
            mic_change_callback=self.handle_mic_select
        )
        
        self.chat_log = self.ui_components['chat_log']
        self.message_manager = ChatMessageManager(self.chat_log)
        self.video_manager.set_video_update_callback(self.queue_video_update)
        
        # INCREASED TIMER INTERVAL to 0.2 to reduce loop pressure
        nicegui_ui.timer(0.2, self.process_video_events)
        nicegui_ui.timer(1.0, self.initialize_video_system, once=True)
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete{Style.RESET_ALL}")

    def handle_mic_select(self, device_index):
        try:
            self.voice_manager.set_input_device(device_index)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error setting input device: {e}{Style.RESET_ALL}")

    async def handle_ui_interaction(self, content, mode="text"):
        if mode == "text":
            await self.process_llm_response(content)
        elif mode == "voice_toggle":
            if self.is_recording:
                await self.stop_voice_recording_and_submit()
            else:
                self.start_voice_recording()
        elif mode == "voice_cancel":
            self.cancel_voice_recording()

    def start_voice_recording(self):
        if self.is_recording: return
        self.is_recording = True
        self.final_voice_text = ""
        self.ui_components['prompt_input'].disable()
        self.ui_components['submit_btn'].disable()
        self.ui_components['mic_btn'].props('color=red icon=stop')
        self.ui_components['cancel_btn'].classes(remove='hidden')
        self.current_voice_msg_id = self.message_manager.add_user_message("...")
        
        def update_ui_text(text):
            self.final_voice_text = text
            self.video_event_queue.put(('update_user_bubble', {'id': self.current_voice_msg_id, 'text': text}))
            
        self.voice_manager.start_listening(update_ui_text)
        print(f"{Fore.CYAN}[VOICE] Recording started...{Style.RESET_ALL}")

    async def stop_voice_recording_and_submit(self):
        if not self.is_recording: return
        self.is_recording = False
        self.voice_manager.stop_listening()
        self.ui_components['prompt_input'].enable()
        self.ui_components['submit_btn'].enable()
        self.ui_components['mic_btn'].props('color=blue icon=mic')
        self.ui_components['cancel_btn'].classes(add='hidden')
        
        text_to_process = self.final_voice_text
        print(f"{Fore.CYAN}[VOICE] Final text: {text_to_process}{Style.RESET_ALL}")
        
        if text_to_process and text_to_process.strip():
            await self.process_llm_response(text_to_process)
        else:
            self.cancel_voice_recording()

    def cancel_voice_recording(self):
        self.is_recording = False
        self.voice_manager.stop_listening()
        self.final_voice_text = ""
        if self.current_voice_msg_id:
            self.video_event_queue.put(('remove_bubble', self.current_voice_msg_id))
            self.current_voice_msg_id = None
        self.ui_components['prompt_input'].enable()
        self.ui_components['submit_btn'].enable()
        self.ui_components['mic_btn'].props('color=blue icon=mic')
        self.ui_components['cancel_btn'].classes(add='hidden')
        print(f"{Fore.YELLOW}[VOICE] Recording cancelled{Style.RESET_ALL}")

    # ============================================================================
    # QUEUE & EVENT HANDLING
    # ============================================================================

    def queue_video_update(self, video_url: str):
        self.video_event_queue.put(('update_video', video_url))
    
    def queue_text_stream(self, element_id: str, text: str, duration: float):
        self.video_event_queue.put(('stream_text', {'element_id': element_id, 'text': text, 'duration': duration}))
    
    def queue_typing_indicator(self, element_id: str, show: bool):
        self.video_event_queue.put(('typing_indicator', {'element_id': element_id, 'show': show}))
    
    def queue_video_ended_event(self):
        self.video_event_queue.put(('video_ended', None))
    
    def queue_clear_message_content(self, element_id: str):
        self.video_event_queue.put(('clear_content', element_id))

    def queue_append_message_content(self, element_id: str, text: str):
        self.video_event_queue.put(('append_content', {'id': element_id, 'text': text}))
    
    def process_video_events(self):
        """Process all queued video events with Exception Safety"""
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
                elif event_type == 'clear_content':
                    self.execute_clear_content(data)
                elif event_type == 'append_content':
                    self.execute_append_content(data)
                
                # NEW VOICE EVENTS - Using safe wrapper
                elif event_type == 'update_user_bubble':
                    escaped = data['text'].replace("'", "\\'")
                    self.safe_run_javascript(f"window.updateUserMessage('{data['id']}', '{escaped}');")
                elif event_type == 'remove_bubble':
                    self.safe_run_javascript(f"window.removeMessageElement('{data}');")
                    
            except queue.Empty:
                break
            except Exception as e:
                # Catch generic errors in processing to keep loop alive
                pass
    
    def execute_video_update(self, video_url: str):
        """Execute video update safely"""
        self.safe_run_javascript(f"window.updateVideoSource('{video_url}');")
    
    def execute_text_stream(self, data: dict):
        """Execute text streaming safely"""
        element_id = data['element_id']
        text = data['text']
        duration = data['duration']
        escaped_text = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')
        
        print(f"{Fore.GREEN}[MAIN] Text streaming: {len(text)} chars{Style.RESET_ALL}")
        self.safe_run_javascript(f"window.streamText('{element_id}', '{escaped_text}', {duration});")
    
    def execute_typing_indicator(self, data: dict):
        """Execute typing indicator safely"""
        element_id = data['element_id']
        if data['show']:
            self.safe_run_javascript(f"window.startTypingIndicator('{element_id}');")
        else:
            self.safe_run_javascript(f"window.stopTypingIndicator('{element_id}');")

    def execute_clear_content(self, element_id: str):
        self.safe_run_javascript(f"window.clearMessageContent('{element_id}');")

    def execute_append_content(self, data: dict):
        element_id = data['id']
        text = data['text']
        escaped_text = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')
        self.safe_run_javascript(f"window.appendMessageContent('{element_id}', '{escaped_text}');")

    def handle_video_ended_in_context(self):
        try:
            current_mode = self.video_manager.current_mode
            print(f"{Fore.BLUE}[MAIN] Video ended event. Mode was: {current_mode}{Style.RESET_ALL}")
            if current_mode in ["lipsync", "pregenerated", "idle_chunk"]:
                self.is_chunk_playing = False
                asyncio.create_task(self.play_next_chunk())
                return
            self.video_manager.on_video_ended()
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error handling video ended: {e}{Style.RESET_ALL}")

    def initialize_video_system(self):
        try:
            print(f"{Fore.CYAN}[MAIN] Initializing video system...{Style.RESET_ALL}")
            self.video_manager.play_next_idle_video()
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error initializing video: {e}{Style.RESET_ALL}")

    async def process_llm_response(self, user_text: str):
        if self.is_processing:
            print(f"{Fore.YELLOW}[MAIN] Dropping request, already processing.{Style.RESET_ALL}")
            return
        
        self.is_processing = True
        
        try:
            if not user_text or not user_text.strip():
                self.is_processing = False
                return
            
            print(f"\n{Fore.CYAN}[USER] {user_text}{Style.RESET_ALL}")
            
            if self.use_pregenerated:
                self.video_manager.queue_pregenerated_response()
            
            self.current_response_id += 1
            response_id = f"response_{self.current_response_id}"
            
            if not self.current_voice_msg_id:
                self.message_manager.add_user_message(user_text)
            
            self.current_voice_msg_id = None
            self.message_manager.add_bot_message(response_id)
            self.queue_typing_indicator(response_id, True)
            
            asyncio.create_task(self.generate_response_chunks_task(user_text, response_id))
            
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error in process_llm_response: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.is_processing = False

    async def generate_response_chunks_task(self, user_text: str, response_id: str):
        """Producer task."""
        try:
            print(f"{Fore.BLUE}[MAIN] Generating response...{Style.RESET_ALL}")
            try:
                response_data = await asyncio.to_thread(generate_darwin_response, user_text)
            except AttributeError:
                loop = asyncio.get_event_loop()
                response_data = await loop.run_in_executor(None, generate_darwin_response, user_text)
            
            if self._shutdown_flag: return

            full_text = response_data['text']
            emotion = response_data['emotion']
            print(f"{Fore.GREEN}[MAIN] LLM Response: {full_text}{Style.RESET_ALL}")

            sentences = re.split(r'(?<=[.!?])\s+', full_text)
            chunks = [s.strip() for s in sentences if s.strip()]
            
            if not chunks:
                self.queue_typing_indicator(response_id, False)
                return

            print(f"{Fore.CYAN}[MAIN] Split into {len(chunks)} chunk(s).{Style.RESET_ALL}")

            for i, sentence_text in enumerate(chunks):
                if self._shutdown_flag: return
                
                print(f"{Fore.BLUE}[MAIN] Processing chunk {i+1}/{len(chunks)}: {sentence_text}{Style.RESET_ALL}")
                
                default_voice = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-semaine-medium.onnx")
                try:
                    audio_path = await asyncio.to_thread(generate_complete_audio, sentence_text, None, default_voice)
                except AttributeError:
                    loop = asyncio.get_event_loop()
                    audio_path = await loop.run_in_executor(None, generate_complete_audio, sentence_text, None, default_voice)

                if not audio_path or not os.path.exists(audio_path) or self._shutdown_flag:
                    continue

                if self.use_float:
                    lipsync_video = await self._generate_float_lipsync(audio_path, sentence_text)
                else:
                    lipsync_video = await self._generate_crossfade_lipsync(audio_path, sentence_text, emotion)
                
                if not lipsync_video or not os.path.exists(lipsync_video) or self._shutdown_flag:
                    continue
                
                video_duration = self.get_video_duration(lipsync_video)
                
                chunk_data = {
                    'id': response_id,
                    'text': sentence_text,
                    'video_path': lipsync_video,
                    'duration': video_duration,
                    'is_first': (i == 0),
                }
                
                await self.chunk_queue.put(chunk_data)
                print(f"{Fore.GREEN}[MAIN]   Chunk {i+1} ready and queued.{Style.RESET_ALL}")
                
                asyncio.create_task(self.play_next_chunk())

            try:
                self.video_manager.cleanup_old_lipsync_videos(keep_last=5)
            except:
                pass

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error in generation task: {e}{Style.RESET_ALL}")
            self.queue_typing_indicator(response_id, False)
        finally:
            self.is_processing = False
            
    async def play_next_chunk(self):
        """Consumer task."""
        if self.is_chunk_playing:
            return
            
        try:
            chunk_data = self.chunk_queue.get_nowait()
        except asyncio.QueueEmpty:
            if self.is_processing:
                print(f"{Fore.YELLOW}[MAIN] Chunk queue empty, playing idle_chunk video...{Style.RESET_ALL}")
                self.video_manager.play_next_idle_chunk_video()
            else:
                print(f"{Fore.GREEN}[MAIN] Chunk queue empty and producer finished. Returning to idle.{Style.RESET_ALL}")
                self.is_chunk_playing = False
                self.current_response_id_playing = None
                self.video_manager.play_next_idle_video()
            return

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error getting from chunk queue: {e}{Style.RESET_ALL}")
            self.is_chunk_playing = False
            return

        self.is_chunk_playing = True
        response_id = chunk_data['id']

        try:
            if response_id != self.current_response_id_playing:
                self.current_response_id_playing = response_id
                self.queue_typing_indicator(response_id, False)
                self.queue_clear_message_content(response_id)
            
            self.video_manager.play_lipsync_video(chunk_data['video_path'])
            self.queue_text_stream(response_id, chunk_data['text'], chunk_data['duration'])
            
            print(f"{Fore.GREEN}[MAIN] Playing chunk: {chunk_data['text']}{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error playing chunk: {e}{Style.RESET_ALL}")
            self.is_chunk_playing = False

    async def _generate_float_lipsync(self, audio_path: str, text: str) -> Optional[str]:
        def generate_float():
            try:
                return self.lipsync_system.generate_lipsync(audio_path=audio_path, output_filename=None)
            except Exception as e:
                print(f"{Fore.RED}[FLOAT] Error: {e}{Style.RESET_ALL}")
                return None
        
        try:
            return await asyncio.to_thread(generate_float)
        except AttributeError:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, generate_float)

    async def _generate_crossfade_lipsync(self, audio_path: str, text: str, emotion: str) -> Optional[str]:
        output_dir = os.path.join(PROJECT_DIR, "tempstream")
        def generate_crossfade():
            try:
                return self.lipsync_system.generate_lip_sync_video(
                    audio_file=audio_path, output_file=None, output_dir=output_dir,
                    use_sequential=True, text=text, emotion=emotion
                )
            except Exception as e:
                print(f"{Fore.RED}[CROSSFADE] Error: {e}{Style.RESET_ALL}")
                return None
        
        try:
            return await asyncio.to_thread(generate_crossfade)
        except AttributeError:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, generate_crossfade)

    def handle_voice_change(self, voice_name: str):
        try:
            voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", voice_name + ".onnx")
            from enhanced_tts_piper import set_voice_model
            set_voice_model(voice_path)
            print(f"{Fore.GREEN}[MAIN] Voice changed to: {voice_name}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error changing voice: {e}{Style.RESET_ALL}")

    def cleanup(self):
        print(f"{Fore.YELLOW}[MAIN] Cleaning up...{Style.RESET_ALL}")
        self._shutdown_flag = True
        if self.use_float and self.lipsync_system:
            try:
                self.lipsync_system.cleanup()
            except Exception:
                pass
        if hasattr(self, 'voice_manager'):
            try:
                self.voice_manager.stop_listening()
            except Exception:
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
            return {"status": "ok", "message": "Event queued"}

    def run(self):
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Darwin Chatbot - {'FLOAT' if self.use_float else 'Emotional'} Lip-Sync{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        
        try:
            self.setup_signal_handlers()
            from nicegui import app
            
            # --- START EDIT: Exception Handler for Windows 10054 ---
            def handle_asyncio_exception(loop, context):
                exception = context.get('exception')
                # Ignore ConnectionResetError: [WinError 10054]
                if isinstance(exception, ConnectionResetError):
                    return
                # Also check message string just in case
                msg = context.get('message', '')
                if '10054' in str(exception) or '10054' in msg:
                    return
                # Default behavior for other exceptions
                loop.default_exception_handler(context)

            # Register on startup
            app.on_startup(lambda: asyncio.get_event_loop().set_exception_handler(handle_asyncio_exception))
            # --- END EDIT ---

            from fastapi.staticfiles import StaticFiles
            
            app.mount('/avatars', StaticFiles(directory=os.path.join(PROJECT_DIR, 'avatars')), name='avatars')
            app.mount('/tempstream', StaticFiles(directory=os.path.join(PROJECT_DIR, 'tempstream')), name='tempstream')
            
            self.setup_api_routes()
            self.setup_ui()
            
            if self.use_float:
                print(f"{Fore.GREEN}[MAIN] FLOAT lipsync system pre-loaded and ready{Style.RESET_ALL}")
            else:
                print(f"{Fore.GREEN}[MAIN] Emotional lipsync system ready{Style.RESET_ALL}")
            
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