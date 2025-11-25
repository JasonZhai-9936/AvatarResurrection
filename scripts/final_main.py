# final_main.py - Darwin Chatbot with EMOTIONAL lip-sync and FLOAT support
# <<< VERSION: Chunking + Idle_Chunk "Thinking" Loop + VOICE INPUT >>>

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
import re  # For splitting sentences

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
from voice_input_manager import VoiceInputManager # <<< NEW IMPORT
from nicegui import ui as nicegui_ui

# ============================================================================
# CONFIGURATION - Edit these settings directly
# ============================================================================

# Choose lipsync mode: False = Crossfade (default), True = FLOAT
USE_FLOAT_LIPSYNC = True

# <<< NEW: Set this to False to disable the pre-generated response >>>
# The avatar will idle until the first chunk is ready.
USE_PREGENERATED_RESPONSE = False 
# Set this back to True if you want the pre-gen video to play again.

# FLOAT model configuration (only used if USE_FLOAT_LIPSYNC = True)
# This config is passed to the daemon.
FLOAT_CONFIG = {
    "ref_path": "assets/main2.png", # Default reference image
    "ckpt_path": "./checkpoints/float.pth",
    "wav2vec_model_path": "./checkpoints/wav2vec2-base-960h",
    "audio2emotion_path": "./checkpoints/wav2vec-english-speech-emotion-recognition",
    "nfe": 7,              # Number of function evaluations (higher = better quality, slower)
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
        self.use_pregenerated = USE_PREGENERATED_RESPONSE
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}DARWIN CHATBOT INITIALIZATION{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[CONFIG] Lipsync mode: {'FLOAT' if self.use_float else 'Crossfade'}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[CONFIG] Pre-generated response: {'ENABLED' if self.use_pregenerated else 'DISABLED'}{Style.RESET_ALL}\n")
        
        self.video_manager = SimplifiedVideoManager(avatar_name="Darwin")
        
        # Initialize Voice Manager
        self.voice_manager = VoiceInputManager(PROJECT_DIR)
        self.is_recording = False
        self.current_voice_msg_id = None
        self.final_voice_text = ""
        
        # This will call either _initialize_float_lipsync or _initialize_crossfade_lipsync
        # based on the USE_FLOAT_LIPSYNC flag.
        self.lipsync_system = self.initialize_lipsync()
        
        self.chat_log = None
        self.message_manager = None  # Will be initialized in setup_ui
        self.ui_components = None
        
        # This flag means "the producer task is still generating chunks"
        self.is_processing = False 
        self._shutdown_flag = False
        
        self.video_event_queue = queue.Queue()
        self.current_response_id = 0

        # State for chunked playback
        self.chunk_queue = asyncio.Queue()
        self.current_response_id_playing: Optional[str] = None
        # This flag means "the consumer is currently playing a video chunk"
        self.is_chunk_playing: bool = False
        
        print(f"{Fore.GREEN}[MAIN] Darwin Chatbot initialized{Style.RESET_ALL}")

    def initialize_lipsync(self):
        """Initialize lip-sync system based on config"""
        if self.use_float:
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
            
            from float_lipsync_subprocess import FloatLipsync
            
            float_lipsync = FloatLipsync(PROJECT_DIR, FLOAT_CONFIG)
            
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
            return duration
        except Exception as e:
            print(f"{Fore.YELLOW}[MAIN] Could not get video duration: {e}{Style.RESET_ALL}")
            return 5.0 # Default duration on error

    def setup_ui(self):
        """Set up UI"""
        # Get microphones for dropdown
        available_mics = self.voice_manager.get_available_microphones()
        
        self.ui_components = build_ui(
            trigger_response_callback=self.handle_ui_interaction, # <<< Router for UI events
            voice_change_callback=self.handle_voice_change,
            video_manager=self.video_manager,
            available_mics=available_mics,       # <<< Pass mics
            mic_change_callback=self.handle_mic_select # <<< Pass callback
        )
        
        self.chat_log = self.ui_components['chat_log']
        
        self.message_manager = ChatMessageManager(self.chat_log)
        
        self.video_manager.set_video_update_callback(self.queue_video_update)
        
        nicegui_ui.timer(0.1, self.process_video_events)
        nicegui_ui.timer(1.0, self.initialize_video_system, once=True)
        
        self.add_custom_javascript()
        
        print(f"{Fore.GREEN}[MAIN] UI setup complete{Style.RESET_ALL}")

    def add_custom_javascript(self):
        """Adds JS functions to the page for clearing/appending text."""
        # Note: Most logic is now in ui.py, but this is kept for redundancy or specific extra scripts
        pass

    # ============================================================================
    # VOICE & MIC HANDLERS (NEW)
    # ============================================================================

    def handle_mic_select(self, device_index):
        """Handle microphone selection from UI"""
        try:
            self.voice_manager.set_input_device(device_index)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error setting input device: {e}{Style.RESET_ALL}")

    async def handle_ui_interaction(self, content, mode="text"):
        """Router for UI events (Text Submit, Mic Toggle, Cancel)"""
        if mode == "text":
            # Standard text input
            await self.process_llm_response(content)
            
        elif mode == "voice_toggle":
            # Mic button clicked
            if self.is_recording:
                await self.stop_voice_recording_and_submit()
            else:
                self.start_voice_recording()
                
        elif mode == "voice_cancel":
            # Cancel button clicked
            self.cancel_voice_recording()

    def start_voice_recording(self):
        """Start listening and create a placeholder bubble"""
        if self.is_recording: return
        
        self.is_recording = True
        self.final_voice_text = ""
        
        # 1. Disable text input
        self.ui_components['prompt_input'].disable()
        self.ui_components['submit_btn'].disable()
        
        # 2. Update Buttons: Make Mic Red (Stop), Show Cancel
        self.ui_components['mic_btn'].props('color=red icon=stop')
        self.ui_components['cancel_btn'].classes(remove='hidden')
        
        # 3. Create the User Bubble immediately
        # We pass an empty string first, then update it live
        self.current_voice_msg_id = self.message_manager.add_user_message("...")
        
        # 4. Start the thread with a lambda to handle partials
        def update_ui_text(text):
            self.final_voice_text = text
            # Queue the JS update
            self.video_event_queue.put(('update_user_bubble', {
                'id': self.current_voice_msg_id,
                'text': text
            }))
            
        self.voice_manager.start_listening(update_ui_text)
        print(f"{Fore.CYAN}[VOICE] Recording started...{Style.RESET_ALL}")

    async def stop_voice_recording_and_submit(self):
        """Stop listening and submit the text to LLM"""
        if not self.is_recording: return
        
        self.is_recording = False
        self.voice_manager.stop_listening()
        
        # Reset UI
        self.ui_components['prompt_input'].enable()
        self.ui_components['submit_btn'].enable()
        self.ui_components['mic_btn'].props('color=blue icon=mic')
        self.ui_components['cancel_btn'].classes(add='hidden')
        
        text_to_process = self.final_voice_text
        print(f"{Fore.CYAN}[VOICE] Final text: {text_to_process}{Style.RESET_ALL}")
        
        if text_to_process and text_to_process.strip():
            # Process exactly like text input
            await self.process_llm_response(text_to_process)
        else:
            # If nothing was said, remove the bubble
            self.cancel_voice_recording()

    def cancel_voice_recording(self):
        """Cancel recording and delete the bubble"""
        self.is_recording = False
        self.voice_manager.stop_listening()
        self.final_voice_text = ""
        
        # Remove the bubble from UI
        if self.current_voice_msg_id:
            self.video_event_queue.put(('remove_bubble', self.current_voice_msg_id))
            self.current_voice_msg_id = None
            
        # Reset UI
        self.ui_components['prompt_input'].enable()
        self.ui_components['submit_btn'].enable()
        self.ui_components['mic_btn'].props('color=blue icon=mic')
        self.ui_components['cancel_btn'].classes(add='hidden')
        
        print(f"{Fore.YELLOW}[VOICE] Recording cancelled{Style.RESET_ALL}")

    # ============================================================================
    # QUEUE & EVENT HANDLING
    # ============================================================================

    def queue_video_update(self, video_url: str):
        """Queue video update"""
        try:
            self.video_event_queue.put(('update_video', video_url))
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing video update: {e}{Style.RESET_ALL}")
    
    def queue_text_stream(self, element_id: str, text: str, duration: float):
        """Queue text streaming (Word-by-word) to match video duration"""
        try:
            self.video_event_queue.put(('stream_text', {
                'element_id': element_id,
                'text': text,
                'duration': duration
            }))
            print(f"{Fore.CYAN}[MAIN] Queued text stream (word-by-word){Style.RESET_ALL}")
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
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing video ended event: {e}{Style.RESET_ALL}")
    
    def queue_clear_message_content(self, element_id: str):
        """Queues a JS call to clear the message bubble content."""
        try:
            self.video_event_queue.put(('clear_content', element_id))
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing clear content: {e}{Style.RESET_ALL}")

    def queue_append_message_content(self, element_id: str, text: str):
        """Queues a JS call to append text to the message bubble."""
        try:
            self.video_event_queue.put(('append_content', {'id': element_id, 'text': text}))
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error queueing append content: {e}{Style.RESET_ALL}")
    
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
                elif event_type == 'clear_content':
                    self.execute_clear_content(data)
                elif event_type == 'append_content':
                    self.execute_append_content(data)
                
                # NEW VOICE EVENTS
                elif event_type == 'update_user_bubble':
                    escaped = data['text'].replace("'", "\\'")
                    nicegui_ui.run_javascript(f"window.updateUserMessage('{data['id']}', '{escaped}');")
                elif event_type == 'remove_bubble':
                    nicegui_ui.run_javascript(f"window.removeMessageElement('{data}');")
                    
            except queue.Empty:
                break
            except Exception as e:
                print(f"{Fore.RED}[MAIN] Error processing event: {e}{Style.RESET_ALL}")
    
    def execute_video_update(self, video_url: str):
        """Execute video update"""
        try:
            js_code = f"window.updateVideoSource('{video_url}');"
            nicegui_ui.run_javascript(js_code)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Video update failed: {e}{Style.RESET_ALL}")
    
    def execute_text_stream(self, data: dict):
        """Execute text streaming"""
        try:
            element_id = data['element_id']
            text = data['text']
            duration = data['duration']
            
            escaped_text = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')
            js_code = f"window.streamText('{element_id}', '{escaped_text}', {duration});"
            
            nicegui_ui.run_javascript(js_code)
            print(f"{Fore.GREEN}[MAIN] Text streaming (word-by-word) started: {len(text)} chars{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Text streaming failed: {e}{Style.RESET_ALL}")
    
    def execute_typing_indicator(self, data: dict):
        """Execute typing indicator animation"""
        try:
            element_id = data['element_id']
            show = data['show']
            
            if show:
                js_code = f"window.startTypingIndicator('{element_id}');"
            else:
                js_code = f"window.stopTypingIndicator('{element_id}');"
            
            nicegui_ui.run_javascript(js_code)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Typing indicator failed: {e}{Style.RESET_ALL}")

    def execute_clear_content(self, element_id: str):
        """Executes the JS to clear a message bubble."""
        try:
            js_code = f"window.clearMessageContent('{element_id}');"
            nicegui_ui.run_javascript(js_code)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Clear content failed: {e}{Style.RESET_ALL}")

    def execute_append_content(self, data: dict):
        """Executes the JS to append text to a message bubble."""
        try:
            element_id = data['id']
            text = data['text']
            escaped_text = text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')
            
            js_code = f"window.appendMessageContent('{element_id}', '{escaped_text}');"
            nicegui_ui.run_javascript(js_code)
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Append content failed: {e}{Style.RESET_ALL}")

    def handle_video_ended_in_context(self):
        """
        Handle video ended event.
        This is the main driver for the chunked playback loop.
        """
        try:
            current_mode = self.video_manager.current_mode
            print(f"{Fore.BLUE}[MAIN] Video ended event. Mode was: {current_mode}{Style.RESET_ALL}")

            # If a lipsync, pre-gen, or "thinking" video just finished,
            # we must check if a lipsync chunk is waiting to be played.
            if current_mode in ["lipsync", "pregenerated", "idle_chunk"]:
                self.is_chunk_playing = False
                # We must schedule the next check, not call it directly
                # This will try to play the next chunk.
                asyncio.create_task(self.play_next_chunk())
                return  # Stop here, play_next_chunk() will handle what's next

            # If it was a normal "idle" video, just run the default logic.
            # (This will play another idle, or a pending pre-gen video)
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

    async def process_llm_response(self, user_text: str):
        """
        [RENAMED] The core logic: LLM -> TTS -> Video
        Previously called 'handle_user_input'
        """
        if self.is_processing:
            print(f"{Fore.YELLOW}[MAIN] Dropping request, already processing.{Style.RESET_ALL}")
            return
        
        self.is_processing = True # This flag now means "generation is happening"
        
        try:
            if not user_text or not user_text.strip():
                self.is_processing = False
                return
            
            print(f"\n{Fore.CYAN}[USER] {user_text}{Style.RESET_ALL}")
            
            # <<< MODIFIED: Only queue pre-gen if enabled in config >>>
            if self.use_pregenerated:
                # Queue pre-generated response IMMEDIATELY after user input
                self.video_manager.queue_pregenerated_response()
            
            # Create unique response ID
            self.current_response_id += 1
            response_id = f"response_{self.current_response_id}"
            
            # IMPORTANT: ONLY add message if it wasn't already added by voice logic
            if not self.current_voice_msg_id:
                self.message_manager.add_user_message(user_text)
            
            # Reset voice ID tracking for next turn
            self.current_voice_msg_id = None
            
            self.message_manager.add_bot_message(response_id)
            
            # Start typing indicator
            self.queue_typing_indicator(response_id, True)
            
            # Start the background task to generate all chunks
            # We don't await this; it runs in the background
            asyncio.create_task(self.generate_response_chunks_task(user_text, response_id))
            
        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error in process_llm_response: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.is_processing = False # Ensure this is reset on error

    async def generate_response_chunks_task(self, user_text: str, response_id: str):
        """
        [PRODUCER] Runs in background. Gets LLM text, splits it,
        and generates TTS/Lipsync for each chunk, adding them to the queue.
        """
        try:
            # 1. Generate LLM response
            print(f"{Fore.BLUE}[MAIN] Generating response...{Style.RESET_ALL}")
            try:
                response_data = await asyncio.to_thread(generate_darwin_response, user_text)
            except AttributeError:
                loop = asyncio.get_event_loop()
                response_data = await loop.run_in_executor(None, generate_darwin_response, user_text)
            
            if self._shutdown_flag: return

            full_text = response_data['text']
            emotion = response_data['emotion'] # Used for crossfade fallback
            print(f"{Fore.GREEN}[MAIN] LLM Response: {full_text}{Style.RESET_ALL}")

            # 2. Split response into sentences (chunks)
            # This regex splits *after* punctuation, keeping the punctuation.
            sentences = re.split(r'(?<=[.!?])\s+', full_text)
            chunks = [s.strip() for s in sentences if s.strip()]
            
            if not chunks:
                print(f"{Fore.YELLOW}[MAIN] No text chunks to process.{Style.RESET_ALL}")
                self.queue_typing_indicator(response_id, False)
                return

            print(f"{Fore.CYAN}[MAIN] Split into {len(chunks)} chunk(s).{Style.RESET_ALL}")

            # 3. Loop and generate each chunk
            for i, sentence_text in enumerate(chunks):
                if self._shutdown_flag: return
                
                print(f"{Fore.BLUE}[MAIN] Processing chunk {i+1}/{len(chunks)}: {sentence_text}{Style.RESET_ALL}")
                
                # a. Generate audio
                print(f"{Fore.BLUE}[MAIN]   Generating audio for chunk...{Style.RESET_ALL}")
                default_voice = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-semaine-medium.onnx")
                try:
                    audio_path = await asyncio.to_thread(generate_complete_audio, sentence_text, None, default_voice)
                except AttributeError:
                    loop = asyncio.get_event_loop()
                    audio_path = await loop.run_in_executor(None, generate_complete_audio, sentence_text, None, default_voice)

                if not audio_path or not os.path.exists(audio_path) or self._shutdown_flag:
                    print(f"{Fore.RED}[MAIN] Audio generation failed for chunk.{Style.RESET_ALL}")
                    continue

                # b. Generate lipsync
                print(f"{Fore.BLUE}[MAIN]   Generating lipsync for chunk...{Style.RESET_ALL}")
                if self.use_float:
                    lipsync_video = await self._generate_float_lipsync(audio_path, sentence_text)
                else:
                    lipsync_video = await self._generate_crossfade_lipsync(audio_path, sentence_text, emotion)
                
                if not lipsync_video or not os.path.exists(lipsync_video) or self._shutdown_flag:
                    print(f"{Fore.RED}[MAIN] Lipsync generation failed for chunk.{Style.RESET_ALL}")
                    continue
                
                # c. Get duration
                video_duration = self.get_video_duration(lipsync_video)
                
                # d. Create chunk data and add to queue
                chunk_data = {
                    'id': response_id,
                    'text': sentence_text,
                    'video_path': lipsync_video,
                    'duration': video_duration,
                    'is_first': (i == 0),
                }
                
                await self.chunk_queue.put(chunk_data)
                print(f"{Fore.GREEN}[MAIN]   Chunk {i+1} ready and queued.{Style.RESET_ALL}")
                
                # Kickstart the player *every time* a chunk is ready.
                asyncio.create_task(self.play_next_chunk())


            # 4. Cleanup old videos
            try:
                self.video_manager.cleanup_old_lipsync_videos(keep_last=5)
            except:
                pass

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error in generation task: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.queue_typing_indicator(response_id, False) # Stop typing on error
        finally:
            self.is_processing = False # Generation is finished
            
    async def play_next_chunk(self):
        """
        [CONSUMER] Checks the queue for a video chunk and plays it.
        """
        # Prevent two play calls from running at once
        if self.is_chunk_playing:
            return
            
        try:
            # Try to get the next chunk
            chunk_data = self.chunk_queue.get_nowait()
        
        except asyncio.QueueEmpty:
            # self.is_processing is True if generate_response_chunks_task is still running.
            if self.is_processing:
                # The producer is still working. Play a "thinking" video.
                print(f"{Fore.YELLOW}[MAIN] Chunk queue empty, playing idle_chunk video...{Style.RESET_ALL}")
                self.video_manager.play_next_idle_chunk_video()
                
            else:
                # The queue is empty AND the producer is finished.
                print(f"{Fore.GREEN}[MAIN] Chunk queue empty and producer finished. Returning to idle.{Style.RESET_ALL}")
                self.is_chunk_playing = False
                self.current_response_id_playing = None
                self.video_manager.play_next_idle_video() # Return to idle
            
            return # Stop execution here

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error getting from chunk queue: {e}{Style.RESET_ALL}")
            self.is_chunk_playing = False
            return

        # We have a chunk!
        self.is_chunk_playing = True
        response_id = chunk_data['id']

        try:
            # Check if this is the first chunk of a *new* response
            if response_id != self.current_response_id_playing:
                self.current_response_id_playing = response_id
                # Stop the typing indicator
                self.queue_typing_indicator(response_id, False)
                # Clear the "typing..." text from the bubble
                self.queue_clear_message_content(response_id)
            
            # Play the video
            self.video_manager.play_lipsync_video(chunk_data['video_path'])
            
            # Stream this sentence's text to the message bubble
            self.queue_text_stream(response_id, chunk_data['text'], chunk_data['duration'])
            
            print(f"{Fore.GREEN}[MAIN] Playing chunk: {chunk_data['text']}{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}[MAIN] Error playing chunk: {e}{Style.RESET_ALL}")
            self.is_chunk_playing = False # Allow next attempt

    async def _generate_float_lipsync(self, audio_path: str, text: str) -> Optional[str]:
        """
        Generate lipsync using the new FLOAT subprocess manager.
        """
        
        def generate_float():
            try:
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
        if self.use_float and self.lipsync_system:
            try:
                self.lipsync_system.cleanup()
            except Exception as e:
                print(f"{Fore.RED}[MAIN] Error during lipsync cleanup: {e}{Style.RESET_ALL}")
        
        # Cleanup voice manager
        if hasattr(self, 'voice_manager'):
            try:
                self.voice_manager.stop_listening()
            except Exception as e:
                print(f"{Fore.RED}[MAIN] Error stopping voice manager: {e}{Style.RESET_ALL}")


    def setup_signal_handlers(self):
        """Set up signal handlers"""
        def signal_handler(signum, frame):
            print(f"\n{Fore.YELLOW}[MAIN] Shutting down...{Style.RESET_ALL}")
            self.cleanup()
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
    main()