# final_main.py - Darwin Chatbot with SPEECH REACTION support
# Added: User activity tracking for typing and voice input

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
from simplified_video_manager import SimplifiedVideoManager
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


class DarwinChatbot:
    """Main chatbot with emotional lip-sync, FLOAT support, and speech reaction"""
    
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
        
        # USER ACTIVITY TRACKING
        self.typing_timer = None
        self.typing_lock = threading.Lock()
        self.TYPING_TIMEOUT = 1.0  # seconds of inactivity before stopping
        
        self.lipsync_system = self.initialize_lipsync()
        
        self.chat_log = None
        self.message_manager = None
        self.ui_components = None
        
        self.is_processing = False 
        self._shutdown_flag = False
        
        self.video_event_queue = queue.Queue()

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

    def safe_run_javascript(self, js_code: str):
        """Safely run JS, catching socket disconnect errors."""
        try:
            nicegui_ui.run_javascript(js_code)
        except (socket.error, ConnectionResetError, RuntimeError) as e:
            print(f"{Fore.YELLOW}[SOCKET] UI Update skipped (Connection dropped): {e}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[JS_ERROR] {e}{Style.RESET_ALL}")

    # ========== USER ACTIVITY TRACKING ==========
    
    def on_typing_detected(self):
        """Called when user is typing in the chat box"""
        with self.typing_lock:
            # Start activity in video manager
            self.video_manager.start_user_activity()
            
            # Cancel existing timer
            if self.typing_timer:
                self.typing_timer.cancel()
            
            # Start new timer - stops activity after TYPING_TIMEOUT seconds of no typing
            self.typing_timer = threading.Timer(self.TYPING_TIMEOUT, self._stop_typing_activity)
            self.typing_timer.start()

    def _stop_typing_activity(self):
        """Called when typing timeout expires"""
        with self.typing_lock:
            self.video_manager.stop_user_activity()
            self.typing_timer = None

    def on_voice_partial(self, text: str):
        """Called when voice input is detected - already integrated with voice system"""
        # Voice activity automatically starts user activity
        self.video_manager.start_user_activity()

    # ===========================================

    def setup_ui(self):
        available_mics = self.voice_manager.get_available_microphones()
        
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_ui_interaction,
            voice_change_callback=self.handle_voice_change,
            video_manager=self.video_manager,
            available_mics=available_mics,
            mic_change_callback=self.handle_mic_select,
            typing_callback=self.on_typing_detected  # NEW
        )
        
        self.chat_log = self.ui_components['chat_log']
        self.message_manager = ChatMessageManager(self.chat_log)
        self.video_manager.set_video_update_callback(self.queue_video_update)
        
        nicegui_ui.timer(0.2, self.process_video_events)
        nicegui_ui.timer(1.0, self.initialize_video_system, once=True)
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete{Style.RESET_ALL}")

    def handle_mic_select(self, device_index):
        try:
            self.voice_manager.set_input_device(device_index)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error setting input device: {e}{Style.RESET_ALL}")

    async def handle_ui_interaction(self, content, mode="text"):
        # When user submits, stop activity tracking
        if mode == "text":
            with self.typing_lock:
                if self.typing_timer:
                    self.typing_timer.cancel()
                    self.typing_timer = None
            self.video_manager.stop_user_activity()
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
        self.ui_components['cancel_btn'].props('remove-hidden')
        
        # Start activity tracking for voice
        self.video_manager.start_user_activity()
        
        self.current_voice_msg_id = self.message_manager.add_user_message("...")
        
        def update_partial_text(text):
            self.final_voice_text = text
            self.safe_run_javascript(f'window.updateUserMessage("{self.current_voice_msg_id}", "{text}")')
            # Each partial update restarts the activity
            self.on_voice_partial(text)
        
        self.voice_manager.start_listening(update_partial_text)

    async def stop_voice_recording_and_submit(self):
        self.is_recording = False
        self.voice_manager.stop_listening()
        
        # Stop activity tracking
        self.video_manager.stop_user_activity()
        
        self.ui_components['prompt_input'].enable()
        self.ui_components['submit_btn'].enable()
        self.ui_components['mic_btn'].props('color=primary icon=mic')
        self.ui_components['cancel_btn'].props('add-hidden')
        
        if self.final_voice_text.strip():
            await self.process_llm_response(self.final_voice_text)
        else:
            self.safe_run_javascript(f'window.removeMessageElement("{self.current_voice_msg_id}")')
            self.current_voice_msg_id = None

    def cancel_voice_recording(self):
        self.is_recording = False
        self.voice_manager.stop_listening()
        
        # Stop activity tracking
        self.video_manager.stop_user_activity()
        
        self.ui_components['prompt_input'].enable()
        self.ui_components['submit_btn'].enable()
        self.ui_components['mic_btn'].props('color=primary icon=mic')
        self.ui_components['cancel_btn'].props('add-hidden')
        
        if self.current_voice_msg_id:
            self.safe_run_javascript(f'window.removeMessageElement("{self.current_voice_msg_id}")')
            self.current_voice_msg_id = None

    def queue_video_update(self, video_url: str):
        self.video_event_queue.put(('update', video_url))

    def queue_video_ended_event(self):
        self.video_event_queue.put(('ended', None))

    def queue_typing_indicator(self, element_id: str, show: bool):
        self.video_event_queue.put(('typing', (element_id, show)))

    def queue_text_stream(self, element_id: str, text: str, duration: float):
        self.video_event_queue.put(('stream', (element_id, text, duration)))

    def queue_clear_message_content(self, element_id: str):
        self.video_event_queue.put(('clear', element_id))

    def process_video_events(self):
        try:
            while not self.video_event_queue.empty():
                event_type, data = self.video_event_queue.get_nowait()
                
                if event_type == 'update':
                    # Check if it's a speedup command
                    if data.startswith("SPEEDUP:"):
                        speed = data.split(":")[1]
                        self.safe_run_javascript(f'window.setVideoSpeed({speed})')
                    else:
                        self.safe_run_javascript(f'window.updateVideoSource("{data}")')
                elif event_type == 'ended':
                    self.handle_video_ended_in_context()
                elif event_type == 'typing':
                    element_id, show = data
                    action = 'startTypingIndicator' if show else 'stopTypingIndicator'
                    self.safe_run_javascript(f'window.{action}("{element_id}")')
                elif event_type == 'stream':
                    element_id, text, duration = data
                    text_escaped = text.replace('"', '\\"').replace('\n', '\\n')
                    self.safe_run_javascript(f'window.streamText("{element_id}", "{text_escaped}", {duration})')
                elif event_type == 'clear':
                    self.safe_run_javascript(f'window.clearMessageContent("{data}")')
        except queue.Empty:
            pass
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error processing video events: {e}{Style.RESET_ALL}")

    def initialize_video_system(self):
        print(f"{Fore.CYAN}[MAIN] Initializing video system...{Style.RESET_ALL}")
        self.video_manager.play_next_idle_video()

    def handle_video_ended_in_context(self):
        current_mode = self.video_manager.current_mode
        
        if current_mode == "lipsync":
            asyncio.create_task(self.play_next_chunk())
        elif current_mode == "idle_chunk":
            asyncio.create_task(self.play_next_chunk())
        else:
            self.video_manager.on_video_ended()

    async def process_llm_response(self, user_input: str):
        if not user_input.strip() or self.is_processing:
            return
        
        self.is_processing = True
        
        try:
            if not self.is_recording:
                self.message_manager.add_user_message(user_input)
                self.ui_components['prompt_input'].value = ""
            
            response_id = self.message_manager.add_bot_message()
            self.queue_typing_indicator(response_id, True)
            
            if self.use_pregenerated and not self.video_manager.pregenerated_pending:
                self.video_manager.queue_pregenerated_response()
            
            print(f"{Fore.CYAN}[MAIN] User: {user_input}{Style.RESET_ALL}")
            
            llm_response = await asyncio.to_thread(generate_darwin_response, user_input)
            llm_text = llm_response['text']
            emotion = llm_response.get('emotion', 'neutral')
            
            sentences = self._split_into_sentences(llm_text)
            print(f"{Fore.GREEN}[MAIN] Darwin: {llm_text}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[MAIN] Split into {len(sentences)} sentences{Style.RESET_ALL}")
            
            for i, sentence in enumerate(sentences):
                # Use response_id for unique chunk filenames (e.g., "darwin_msg_1_0.wav")
                chunk_audio_path = os.path.join(PROJECT_DIR, "tempstream", f"chunk_{response_id}_{i}.wav")
                
                try:
                    # Generate TTS audio
                    await asyncio.to_thread(generate_complete_audio, sentence, chunk_audio_path)
                    
                    # Verify audio file was created before proceeding
                    if not os.path.exists(chunk_audio_path):
                        print(f"{Fore.RED}[MAIN] TTS failed - audio file not created: {chunk_audio_path}{Style.RESET_ALL}")
                        continue
                    
                    # Generate lipsync video
                    if self.use_float:
                        video_path = await self._generate_float_lipsync(chunk_audio_path, sentence)
                    else:
                        video_path = await self._generate_crossfade_lipsync(chunk_audio_path, sentence, emotion)
                    
                    if video_path:
                        chunk_duration = self.get_video_duration(video_path)
                        
                        # If this is the first chunk and queue is empty, speed up current video
                        if i == 0 and self.chunk_queue.empty():
                            print(f"{Fore.CYAN}[MAIN] First chunk ready - requesting speedup of current video{Style.RESET_ALL}")
                            self.video_manager.request_speedup_for_content()
                        
                        await self.chunk_queue.put({
                            'id': response_id,
                            'text': sentence,
                            'video_path': video_path,
                            'duration': chunk_duration
                        })
                except Exception as e:
                    print(f"{Fore.RED}[MAIN] Error processing chunk {i}: {e}{Style.RESET_ALL}")
                    import traceback
                    traceback.print_exc()
            
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

    def _split_into_sentences(self, text: str) -> list:
        text = text.strip()
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

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
        
        # Cancel typing timer
        with self.typing_lock:
            if self.typing_timer:
                self.typing_timer.cancel()
                self.typing_timer = None
        
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
            
            def handle_asyncio_exception(loop, context):
                exception = context.get('exception')
                if isinstance(exception, ConnectionResetError):
                    return
                msg = context.get('message', '')
                if '10054' in str(exception) or '10054' in msg:
                    return
                loop.default_exception_handler(context)

            app.on_startup(lambda: asyncio.get_event_loop().set_exception_handler(handle_asyncio_exception))

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