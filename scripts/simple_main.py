# simple_main.py - Simplified approach with clean lipsync coordination

import sys
import os
import threading
import time
from pathlib import Path

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui, app
from ui import build_ui
from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio, set_voice_model
from node_video_system import NodeVideoSystem
from test_lipsync_generation import generate_lipsync_with_integration, setup_lipsync_environment
from colorama import Fore, Style, init
import queue

# Initialize colorama for colored terminal output
init(autoreset=True)

# Global references
chat_container = None
is_first_message = True
current_voice = "en_GB-semaine-medium"
node_system = NodeVideoSystem("Darwin")
ui_update_queue = queue.Queue()

# Simple state management
class SystemState:
    def __init__(self):
        self.is_processing_response = False
        self.lipsync_video_ready = False
        self.lipsync_video_path = None

system_state = SystemState()

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
        
        with chat_container:
            message_element = ui.element('div').classes(css_class)
            message_element.add_slot('default', text)
        
        ui.run_javascript('''
            const chatContainer = document.querySelector('.chat-messages');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        ''')
    
    ui_update_queue.put(('add_message', add_message))

def update_video_player(video_path: str):
    """Update the video player - thread-safe version"""
    print(f"{Fore.BLUE}[VIDEO] Queuing video update: {os.path.basename(video_path)}{Style.RESET_ALL}")
    
    def video_update():
        relative_path = os.path.relpath(video_path, PROJECT_DIR).replace('\\', '/')
        video_url = f"/{relative_path}"
        
        print(f"{Fore.BLUE}[VIDEO] Executing video update: {video_url}{Style.RESET_ALL}")
        
        ui.run_javascript(f'''
            const video = document.getElementById('mainVideo');
            if (video) {{
                video.src = '{video_url}';
                video.load();
                video.play().catch(e => console.log('Video play failed:', e));
            }}
        ''')
    
    ui_update_queue.put(('video_update', video_update))

def process_ui_updates():
    """Process queued UI updates in the main thread"""
    try:
        while True:
            try:
                update_type, update_func = ui_update_queue.get_nowait()
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

def handle_user_input(user_text: str):
    """Simplified input handler"""
    global chat_container, is_first_message, system_state

    if is_first_message:
        def clear_chat():
            chat_container.clear()
        ui_update_queue.put(('clear_chat', clear_chat))
        is_first_message = False

    try:
        print(f"[MAIN] User asked: {user_text}")
        system_state.is_processing_response = True

        # Add user message
        add_message_to_chat(user_text, 'user')

        # Interrupt idle system
        print(f"{Fore.YELLOW}[MAIN] Interrupting idle system for response{Style.RESET_ALL}")
        node_system.interrupt_for_response()

        # Generate LLM response
        print(f"{Fore.CYAN}[MAIN] Generating LLM response...{Style.RESET_ALL}")
        response = generate_darwin_response(user_text)
        print(f"[MAIN] Darwin responded: {response}")

        # Add Darwin's response to chat
        add_message_to_chat(response, 'darwin')

        # Generate complete TTS
        print(f"{Fore.MAGENTA}[MAIN] Generating complete TTS audio...{Style.RESET_ALL}")
        audio_file = generate_complete_audio(response)
        
        if not audio_file:
            print(f"{Fore.RED}[MAIN] TTS generation failed{Style.RESET_ALL}")
            system_state.is_processing_response = False
            start_idle_video_system()
            return

        # Simple approach: Start lipsync generation and return to main in sequence
        def response_handler():
            """Handle response processing in background thread"""
            
            # Step 1: Return to main quickly
            print(f"{Fore.CYAN}[RESPONSE] Returning to main node...{Style.RESET_ALL}")
            return_videos = node_system.return_to_main_path()
            
            for video_path in return_videos:
                if os.path.exists(video_path):
                    print(f"{Fore.BLUE}[RESPONSE] Return video: {os.path.basename(video_path)}{Style.RESET_ALL}")
                    update_video_player(video_path)
                    duration = node_system._get_video_duration(video_path)
                    time.sleep(duration + 0.5)
            
            # Step 2: Start lipsync generation
            print(f"{Fore.MAGENTA}[RESPONSE] Starting lipsync generation...{Style.RESET_ALL}")
            lipsync_start_time = time.time()
            ready, lipsync_path = generate_lipsync_with_integration(response)
            lipsync_time = time.time() - lipsync_start_time
            
            if ready and lipsync_path and os.path.exists(lipsync_path):
                print(f"{Fore.GREEN}[RESPONSE] Lipsync ready after {lipsync_time:.2f}s: {lipsync_path}{Style.RESET_ALL}")
                
                # Step 3: Play lipsync video
                print(f"{Fore.GREEN}[RESPONSE] Playing lipsync video{Style.RESET_ALL}")
                update_video_player(lipsync_path)
                duration = node_system._get_video_duration(lipsync_path)
                time.sleep(duration + 0.5)
                
                # Step 4: Resume idle system
                print(f"{Fore.GREEN}[RESPONSE] Lipsync complete, resuming idle system{Style.RESET_ALL}")
                system_state.is_processing_response = False
                start_idle_video_system()
                
            else:
                print(f"{Fore.RED}[RESPONSE] Lipsync failed, resuming idle system{Style.RESET_ALL}")
                system_state.is_processing_response = False
                start_idle_video_system()

        # Start response handling in background
        response_thread = threading.Thread(target=response_handler, daemon=True)
        response_thread.start()

    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        add_message_to_chat('Sorry, Darwin is having trouble responding right now.', 'system')
        system_state.is_processing_response = False
        start_idle_video_system()

@ui.page('/')
def index():
    """Main page with simplified coordination"""
    global chat_container

    ui.page_title('Chat with Charles Darwin - Enhanced Avatar')

    # Header with status
    with ui.row().classes('w-full justify-between items-center p-4'):
        ui.label('Chat with Charles Darwin - Enhanced Avatar').classes('text-4xl font-bold text-white')
        
        status_label = ui.label('Initializing...').classes('text-sm text-white bg-blue-600 px-3 py-1 rounded')
        
        def update_status():
            """Update status based on system state"""
            if system_state.is_processing_response:
                status_label.text = "Processing Response..."
                status_label.classes(remove='bg-green-600 bg-red-600', add='bg-blue-600')
            elif node_system.is_playing and not node_system.is_interrupted:
                current_video = node_system.current_video_path
                video_name = os.path.basename(current_video) if current_video else "Loading..."
                status_label.text = f"Playing: {video_name}"
                status_label.classes(remove='bg-blue-600 bg-red-600', add='bg-green-600')
            else:
                status_label.text = "System Ready"
                status_label.classes(remove='bg-green-600 bg-blue-600', add='bg-red-600')
        
        def timer_update():
            process_ui_updates()
            update_status()
        
        ui.timer(0.5, timer_update)

    # Build UI
    chat_container = build_ui(handle_user_input, handle_voice_change)
    
    # Enhanced video setup
    ui.run_javascript('''
        setTimeout(function() {
            const video = document.getElementById('mainVideo');
            if (video) {
                video.muted = false;
                video.autoplay = true;
                
                video.addEventListener('loadstart', function() {
                    this.play().catch(e => console.log('Autoplay attempt:', e));
                });
                
                console.log('Video autoplay configured');
            }
        }, 500);
    ''')
    
    # Start idle system
    ui.timer(2.0, start_idle_video_system, once=True)

def check_dependencies():
    """Basic dependency check"""
    print(f"{Fore.CYAN}[MAIN] Checking dependencies...{Style.RESET_ALL}")
    
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py', 'enhanced_tts_piper.py', 'ui.py', 'node_video_system.py', 'test_lipsync_generation.py']
    
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"{Fore.RED}[ERROR] Required file not found: {file_path}{Style.RESET_ALL}")
            return False

    # Check avatar structure
    avatar_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin")
    nodes_dir = os.path.join(avatar_dir, "Nodes")
    
    if not os.path.exists(nodes_dir):
        print(f"{Fore.RED}[ERROR] Nodes directory not found: {nodes_dir}{Style.RESET_ALL}")
        return False

    print(f"{Fore.GREEN}[MAIN] Dependencies verified{Style.RESET_ALL}")
    return True

def main():
    """Simplified main function"""
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}Darwin Chat - Simplified Coordination")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")

    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependency check failed{Style.RESET_ALL}")
        return

    # Setup directories
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)

    # Static file serving
    try:
        app.add_static_files('/avatars', os.path.join(PROJECT_DIR, 'avatars'))
        app.add_static_files('/tempstream', temp_dir)
        print(f"{Fore.GREEN}[MAIN] Static file serving configured{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[WARNING] Static file serving failed: {e}{Style.RESET_ALL}")

    print(f"{Fore.GREEN}[MAIN] Starting application...{Style.RESET_ALL}")

    ui.run(
        title='Darwin Chat - Simplified',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()