# thread_safe_enhanced_main.py - Thread-safe version with proper UI updates

import sys
import os
import threading
import time
import asyncio
import queue
from pathlib import Path

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui, app
from ui import build_ui
from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio, generate_and_stream_audio, set_voice_model
from node_video_system import NodeVideoSystem
from lipsync_integration import generate_lipsync_with_integration, setup_lipsync_environment
from colorama import Fore, Style, init

# Initialize colorama for colored terminal output
init(autoreset=True)

# Global references for UI elements and systems
chat_container = None
is_first_message = True
current_voice = "en_GB-semaine-medium"

# Initialize the node video system
node_system = NodeVideoSystem("Darwin")

# Lipsync state management
lipsync_ready = False
lipsync_video_path = None
lipsync_thread = None

# Thread-safe UI update queue
ui_update_queue = queue.Queue()

def handle_voice_change(voice_name: str):
    """Handle voice model change."""
    global current_voice
    current_voice = voice_name
    
    voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", f"{voice_name}.onnx")
    
    if os.path.exists(voice_path):
        print(f"{Fore.CYAN}[MAIN] Voice changed to: {voice_name}{Style.RESET_ALL}")
        set_voice_model(voice_path)
        ui.notify(f'Voice successfully changed to {voice_name}', type='positive')
    else:
        print(f"{Fore.RED}[MAIN] Voice model not found: {voice_path}{Style.RESET_ALL}")
        ui.notify(f'Voice model not found: {voice_name}', type='negative')

def add_message_to_chat(text: str, message_type: str):
    """Add a message to the chat container - thread-safe version."""
    def add_message():
        global chat_container
        
        if message_type == 'user':
            css_class = 'message-item user-message'
        elif message_type == 'darwin':
            css_class = 'message-item darwin-message'
        else:
            css_class = 'message-item system-message'
        
        # Create the message element
        with chat_container:
            message_element = ui.element('div').classes(css_class)
            message_element.add_slot('default', text)
        
        # Scroll to bottom
        ui.run_javascript('''
            const chatContainer = document.querySelector('.chat-messages');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        ''')
    
    # Queue the UI update
    ui_update_queue.put(('add_message', add_message))

def update_video_player(video_path: str):
    """Update the video player with a new video - thread-safe version"""
    print(f"{Fore.BLUE}[VIDEO] Queuing video update: {os.path.basename(video_path)}{Style.RESET_ALL}")
    
    def video_update():
        # Convert to relative path for web serving
        relative_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
        video_url = f"/{relative_path}"
        
        print(f"{Fore.BLUE}[VIDEO] Executing video update: {video_url}{Style.RESET_ALL}")
        
        # Update video player via JavaScript
        ui.run_javascript(f'''
            const video = document.getElementById('mainVideo');
            if (video) {{
                video.src = '{video_url}';
                video.load();
                video.play().catch(e => console.log('Video play failed:', e));
            }}
        ''')
    
    # Queue the UI update
    ui_update_queue.put(('video_update', video_update))

def process_ui_updates():
    """Process queued UI updates in the main thread"""
    try:
        while True:
            try:
                update_type, update_func = ui_update_queue.get_nowait()
                print(f"{Fore.CYAN}[UI_QUEUE] Processing {update_type}{Style.RESET_ALL}")
                update_func()
                ui_update_queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                print(f"{Fore.RED}[UI_QUEUE] Error processing {update_type}: {e}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[UI_QUEUE] Error in UI update processor: {e}{Style.RESET_ALL}")

def start_idle_video_system():
    """Start the idle video playing system"""
    print(f"{Fore.GREEN}[MAIN] Starting idle video system{Style.RESET_ALL}")
    node_system.start_idle_playing(update_video_player)

def lipsync_ready_check():
    """Check if lipsync is ready - used by node system"""
    return lipsync_ready

def generate_lipsync_async(text: str):
    """Generate lipsync in background thread using real lipsync integration"""
    global lipsync_ready, lipsync_video_path, lipsync_thread
    
    def lipsync_worker():
        global lipsync_ready, lipsync_video_path
        
        try:
            print(f"{Fore.MAGENTA}[LIPSYNC] Starting real lipsync generation...{Style.RESET_ALL}")
            
            # Use the integrated lipsync function
            ready, video_path = generate_lipsync_with_integration(text)
            
            if ready and video_path and os.path.exists(video_path):
                lipsync_video_path = video_path
                lipsync_ready = True
                print(f"{Fore.GREEN}[LIPSYNC] Real lipsync generation completed: {video_path}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[LIPSYNC] Real lipsync generation failed{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Real lipsync generation error: {e}{Style.RESET_ALL}")
    
    # Reset lipsync state
    lipsync_ready = False
    lipsync_video_path = None
    
    # Start lipsync generation in background
    lipsync_thread = threading.Thread(target=lipsync_worker, daemon=True)
    lipsync_thread.start()

def handle_user_input(user_text: str):
    """Enhanced input handler with node system and lipsync integration"""
    global chat_container, is_first_message, current_voice, lipsync_ready

    # Clear initial message on first input
    if is_first_message:
        def clear_chat():
            chat_container.clear()
        ui_update_queue.put(('clear_chat', clear_chat))
        is_first_message = False

    try:
        print(f"[MAIN] User asked: {user_text}")

        # Add user message
        add_message_to_chat(user_text, 'user')

        # Step 1: Interrupt idle video system
        print(f"{Fore.YELLOW}[MAIN] Interrupting idle system for response{Style.RESET_ALL}")
        node_system.interrupt_for_response()

        # Step 2: Generate LLM response
        print(f"{Fore.CYAN}[MAIN] Generating LLM response...{Style.RESET_ALL}")
        response = generate_darwin_response(user_text)
        print(f"[MAIN] Darwin responded: {response}")

        # Add Darwin's response to chat
        add_message_to_chat(response, 'darwin')

        # Step 3: Generate complete TTS (not streamed chunks)
        print(f"{Fore.MAGENTA}[MAIN] Generating complete TTS audio...{Style.RESET_ALL}")
        audio_file = generate_tts_complete(response)
        
        if not audio_file:
            print(f"{Fore.RED}[MAIN] TTS generation failed{Style.RESET_ALL}")
            # Resume idle system if TTS fails
            start_idle_video_system()
            return

        # Step 4a: Start return to main node sequence
        print(f"{Fore.CYAN}[MAIN] Starting return to main sequence...{Style.RESET_ALL}")
        node_system.return_to_main_and_wait(lipsync_ready_check)

        # Step 4b: Start lipsync generation in parallel
        print(f"{Fore.MAGENTA}[MAIN] Starting lipsync generation...{Style.RESET_ALL}")
        generate_lipsync_async(response)

        # The node system will handle the coordination automatically
        print(f"{Fore.GREEN}[MAIN] Response processing initiated{Style.RESET_ALL}")

    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        add_message_to_chat('Sorry, Darwin is having trouble responding right now.', 'system')
        
        def show_error():
            ui.notify("Error: Could not generate response", type='negative')
        ui_update_queue.put(('error_notify', show_error))
        
        # Resume idle system on error
        start_idle_video_system()

def generate_tts_complete(text: str) -> str:
    """Generate complete TTS audio file (not streamed chunks)"""
    try:
        print(f"{Fore.BLUE}[TTS] Generating complete audio for: {text[:50]}...{Style.RESET_ALL}")
        
        # Use the enhanced TTS function for complete audio generation
        audio_file = generate_complete_audio(text)
        
        if audio_file and os.path.exists(audio_file):
            print(f"{Fore.GREEN}[TTS] Complete audio generated: {audio_file}{Style.RESET_ALL}")
            return audio_file
        else:
            print(f"{Fore.RED}[TTS] Audio generation failed{Style.RESET_ALL}")
            return None
            
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error generating complete audio: {e}{Style.RESET_ALL}")
        return None

@ui.page('/')
def index():
    """Main page with enhanced video system"""
    global chat_container

    ui.page_title('Chat with Charles Darwin - Enhanced Avatar')

    # Enhanced header with status
    with ui.row().classes('w-full justify-between items-center p-4'):
        ui.label('Chat with Charles Darwin - Enhanced Avatar').classes('text-4xl font-bold text-white')
        
        # Status indicator
        status_label = ui.label('Initializing...').classes('text-sm text-white bg-blue-600 px-3 py-1 rounded')
        
        def update_status():
            """Update status based on system state"""
            system_status = node_system.get_system_status()
            
            if system_status['is_playing'] and not system_status['is_interrupted']:
                status_text = f"Playing: {system_status['current_video'] or 'Loading...'}"
                status_label.text = status_text
                status_label.classes(remove='bg-blue-600 bg-red-600', add='bg-green-600')
            elif system_status['is_interrupted']:
                status_label.text = "Processing Response..."
                status_label.classes(remove='bg-green-600 bg-red-600', add='bg-blue-600')
            else:
                status_label.text = "System Ready"
                status_label.classes(remove='bg-green-600 bg-blue-600', add='bg-red-600')
        
        # Update status every 2 seconds and process UI updates
        def update_and_process():
            process_ui_updates()  # Process queued UI updates
            update_status()       # Update status
        
        ui.timer(0.5, update_and_process)  # More frequent for responsive UI updates

    # Build the main UI (video player + chat)
    chat_container = build_ui(handle_user_input, handle_voice_change)
    
    # Start the idle video system after UI is built
    ui.timer(1.0, start_idle_video_system, once=True)

def check_dependencies():
    """Enhanced dependency check including node system and lipsync"""
    print(f"{Fore.CYAN}[MAIN] Checking dependencies...{Style.RESET_ALL}")
    
    # Original dependency checks
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py', 'enhanced_tts_piper.py', 'ui.py', 'node_video_system.py', 'lipsync_integration.py']
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"{Fore.RED}[ERROR] Required file not found: {file_path}{Style.RESET_ALL}")
            return False

    # Check avatar directory structure
    avatar_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin")
    nodes_dir = os.path.join(avatar_dir, "Nodes")
    node_config = os.path.join(avatar_dir, "node_network.json")
    
    if not os.path.exists(avatar_dir):
        print(f"{Fore.RED}[ERROR] Avatar directory not found: {avatar_dir}{Style.RESET_ALL}")
        return False
    
    if not os.path.exists(nodes_dir):
        print(f"{Fore.RED}[ERROR] Nodes directory not found: {nodes_dir}{Style.RESET_ALL}")
        return False
    
    if not os.path.exists(node_config):
        print(f"{Fore.YELLOW}[WARNING] Node config not found: {node_config}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] System will use fallback configuration{Style.RESET_ALL}")
    
    # Count available video files
    video_count = 0
    if os.path.exists(nodes_dir):
        for root, dirs, files in os.walk(nodes_dir):
            for file in files:
                if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    video_count += 1
    
    print(f"{Fore.GREEN}[MAIN] Found {video_count} video files in nodes directory{Style.RESET_ALL}")
    
    if video_count == 0:
        print(f"{Fore.RED}[ERROR] No video files found in nodes directory{Style.RESET_ALL}")
        return False

    # Original checks
    config_path = os.path.join(PROJECT_DIR, 'config.json')
    api_key_path = os.path.join(PROJECT_DIR, 'groq_api_key.txt')
    
    voices_dir = os.path.join(PROJECT_DIR, 'Piper_Voices')
    if not os.path.exists(voices_dir):
        print(f"{Fore.RED}[ERROR] Piper_Voices directory not found at: {voices_dir}{Style.RESET_ALL}")
        return False
    
    voice_files = [f for f in os.listdir(voices_dir) if f.endswith('.onnx')]
    if not voice_files:
        print(f"{Fore.RED}[ERROR] No voice models (.onnx files) found in: {voices_dir}{Style.RESET_ALL}")
        return False
    
    print(f"{Fore.GREEN}[MAIN] Found {len(voice_files)} voice model(s): {', '.join(voice_files)}{Style.RESET_ALL}")

    if not os.path.exists(config_path):
        print(f"{Fore.RED}[ERROR] Config file not found at: {config_path}{Style.RESET_ALL}")
        return False

    if not os.path.exists(api_key_path):
        print(f"{Fore.RED}[ERROR] API key file not found at: {api_key_path}{Style.RESET_ALL}")
        return False

    try:
        print(f"{Fore.CYAN}[MAIN] Testing enhanced TTS system...{Style.RESET_ALL}")
        from enhanced_tts_piper import test_tts_system
        if not test_tts_system():
            print(f"{Fore.RED}[ERROR] Enhanced TTS system test failed.{Style.RESET_ALL}")
            return False
        print(f"{Fore.GREEN}[MAIN] Enhanced TTS system test passed.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Enhanced TTS system test error: {e}{Style.RESET_ALL}")
        return False

    # Test node system
    try:
        print(f"{Fore.CYAN}[MAIN] Testing node video system...{Style.RESET_ALL}")
        test_video = node_system.get_next_video()
        if test_video:
            print(f"{Fore.GREEN}[MAIN] Node system test passed - found video: {os.path.basename(test_video)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[WARNING] Node system test - no videos immediately available{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Node system test error: {e}{Style.RESET_ALL}")
        return False

    # Test lipsync system
    try:
        print(f"{Fore.CYAN}[MAIN] Testing lipsync integration system...{Style.RESET_ALL}")
        if setup_lipsync_environment():
            print(f"{Fore.GREEN}[MAIN] Lipsync system test passed.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[WARNING] Lipsync system test failed - lipsync features will be disabled{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[WARNING] Application will continue with test lipsync function{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[WARNING] Lipsync system test error: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] Application will continue with limited lipsync functionality{Style.RESET_ALL}")

    print(f"{Fore.GREEN}[MAIN] All critical dependencies verified successfully.{Style.RESET_ALL}")
    return True

def main():
    """Enhanced main function with node system integration"""
    print(f"{Fore.GREEN}{'=' * 70}")
    print(f"{Fore.YELLOW}Starting Enhanced Darwin Chat Application (Thread-Safe)")
    print(f"{Fore.YELLOW}Features: LLM + TTS + Node-based Idle Videos + Lipsync")
    print(f"{Fore.GREEN}{'=' * 70}{Style.RESET_ALL}")
    print(f"[MAIN] Project directory: {PROJECT_DIR}")

    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependency check failed. Please fix the issues above.{Style.RESET_ALL}")
        return

    # Ensure temp directories exist
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    print(f"[MAIN] TTS temp directory: {temp_dir}")

    # Static file serving for video files
    try:
        app.add_static_files('/avatars', os.path.join(PROJECT_DIR, 'avatars'))
        app.add_static_files('/tempstream', temp_dir)
        print(f"{Fore.GREEN}[MAIN] Static file serving configured{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[WARNING] Static file serving failed: {e}{Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}[MAIN] All systems ready. Starting enhanced web interface...{Style.RESET_ALL}")

    # Show system information
    status = node_system.get_system_status()
    print(f"{Fore.CYAN}[MAIN] Node System Status:{Style.RESET_ALL}")
    for key, value in status.items():
        print(f"  {key}: {value}")

    ui.run(
        title='Enhanced Darwin Chat with Avatar System',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()