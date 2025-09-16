# thread_safe_enhanced_main.py - Thread-safe version with real lipsync integration

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
from enhanced_tts_piper import generate_complete_audio, set_voice_model
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
        
        # Special handling for lipsync videos in tempstream
        if 'tempstream' in video_path:
            # For tempstream files, use the tempstream route
            temp_relative = os.path.relpath(video_path, os.path.join(PROJECT_DIR, 'tempstream')).replace('\\', '/')
            video_url = f"/tempstream/{temp_relative}"
        
        print(f"{Fore.BLUE}[VIDEO] Executing video update: {video_url}{Style.RESET_ALL}")
        
        # Update video player via JavaScript with better error handling
        ui.run_javascript(f'''
            const video = document.getElementById('mainVideo');
            if (video) {{
                console.log('Updating video source to: {video_url}');
                video.src = '{video_url}';
                video.load();
                
                // Add event listeners for debugging
                video.addEventListener('loadstart', () => console.log('Video loadstart'));
                video.addEventListener('loadeddata', () => console.log('Video loadeddata'));
                video.addEventListener('canplay', () => console.log('Video canplay'));
                video.addEventListener('error', (e) => console.error('Video error:', e));
                
                video.play().then(() => {{
                    console.log('Video playing successfully');
                }}).catch(e => {{
                    console.error('Video play failed:', e);
                    // Try again after a short delay
                    setTimeout(() => {{
                        video.play().catch(e2 => console.error('Retry failed:', e2));
                    }}, 500);
                }});
            }} else {{
                console.error('Video element not found');
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
    """Generate lipsync using the real lipsync system and handle playback"""
    global lipsync_ready, lipsync_video_path, lipsync_thread
    
    def lipsync_worker():
        global lipsync_ready, lipsync_video_path
        
        try:
            print(f"{Fore.MAGENTA}[LIPSYNC] Starting real lipsync generation...{Style.RESET_ALL}")
            
            # Use the new integrated lipsync system
            ready, video_path = generate_lipsync_with_integration(text)
            
            if ready and video_path and os.path.exists(video_path):
                lipsync_video_path = video_path
                lipsync_ready = True
                
                print(f"{Fore.GREEN}[LIPSYNC] Real lipsync generation completed: {video_path}{Style.RESET_ALL}")
                
                # Add a small delay to ensure video is fully written
                time.sleep(0.5)
                
                # Play the lipsync video immediately
                print(f"{Fore.BLUE}[LIPSYNC] Playing lipsync video...{Style.RESET_ALL}")
                update_video_player(video_path)
                
                # Calculate actual video duration for proper timing
                try:
                    from lipsyncer import LipsyncSystem
                    lipsync_sys = LipsyncSystem()
                    
                    # Estimate duration based on sentence count and clip duration
                    sentences = lipsync_sys.split_text_into_sentences(text)
                    estimated_duration = len(sentences) * lipsync_sys.clip_duration
                    
                    print(f"{Fore.CYAN}[LIPSYNC] Estimated video duration: {estimated_duration:.1f}s{Style.RESET_ALL}")
                    
                    # Wait for the lipsync video to finish playing
                    time.sleep(estimated_duration + 1)  # Add 1s buffer
                    
                except Exception as e:
                    print(f"{Fore.YELLOW}[LIPSYNC] Duration estimation failed, using default: {e}{Style.RESET_ALL}")
                    time.sleep(10)  # Default fallback
                
                # Resume idle system after lipsync completes
                print(f"{Fore.CYAN}[LIPSYNC] Lipsync playback complete, resuming idle system{Style.RESET_ALL}")
                start_idle_video_system()
                
            else:
                print(f"{Fore.RED}[LIPSYNC] Real lipsync generation failed - resuming idle system{Style.RESET_ALL}")
                start_idle_video_system()
                
        except Exception as e:
            print(f"{Fore.RED}[LIPSYNC] Real lipsync generation error: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[LIPSYNC] Resuming idle system after error{Style.RESET_ALL}")
            start_idle_video_system()
    
    # Reset lipsync state
    lipsync_ready = False
    lipsync_video_path = None
    
    # Start lipsync generation in background
    lipsync_thread = threading.Thread(target=lipsync_worker, daemon=True)
    lipsync_thread.start()

def handle_user_input(user_text: str):
    """Enhanced input handler with node system and real lipsync integration"""
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

        # Step 3: Start real lipsync generation
        print(f"{Fore.MAGENTA}[MAIN] Starting real lipsync generation...{Style.RESET_ALL}")
        generate_lipsync_async(response)

        print(f"{Fore.GREEN}[MAIN] Response processing initiated with real lipsync{Style.RESET_ALL}")

    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        add_message_to_chat('Sorry, Darwin is having trouble responding right now.', 'system')
        
        def show_error():
            ui.notify("Error: Could not generate response", type='negative')
        ui_update_queue.put(('error_notify', show_error))
        
        # Resume idle system on error
        start_idle_video_system()

@ui.page('/')
def index():
    """Main page with enhanced video system"""
    global chat_container

    ui.page_title('Chat with Charles Darwin - Enhanced Avatar with Real Lipsync')

    # Enhanced header with status
    with ui.row().classes('w-full justify-between items-center p-4'):
        ui.label('Chat with Charles Darwin - Enhanced Avatar with Real Lipsync').classes('text-4xl font-bold text-white')
        
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
                if lipsync_ready:
                    status_label.text = "Playing Lipsync Video..."
                    status_label.classes(remove='bg-green-600 bg-red-600', add='bg-purple-600')
                else:
                    status_label.text = "Generating Lipsync..."
                    status_label.classes(remove='bg-green-600 bg-red-600', add='bg-blue-600')
            else:
                status_label.text = "System Ready"
                status_label.classes(remove='bg-green-600 bg-blue-600', add='bg-red-600')
        
        # Update status every 500ms and process UI updates
        def update_and_process():
            process_ui_updates()  # Process queued UI updates
            update_status()       # Update status
        
        ui.timer(0.5, update_and_process)  # More frequent for responsive UI updates

    # Build the main UI (video player + chat)
    chat_container = build_ui(handle_user_input, handle_voice_change)
    
    # Start the idle video system after UI is built
    ui.timer(1.0, start_idle_video_system, once=True)

def check_dependencies():
    """Enhanced dependency check including node system and real lipsync"""
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
    talking_clips_dir = os.path.join(avatar_dir, "talking_clips")
    
    if not os.path.exists(avatar_dir):
        print(f"{Fore.RED}[ERROR] Avatar directory not found: {avatar_dir}{Style.RESET_ALL}")
        return False
    
    if not os.path.exists(nodes_dir):
        print(f"{Fore.RED}[ERROR] Nodes directory not found: {nodes_dir}{Style.RESET_ALL}")
        return False
    
    if not os.path.exists(node_config):
        print(f"{Fore.YELLOW}[WARNING] Node config not found: {node_config}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] System will use fallback configuration{Style.RESET_ALL}")
    
    # Check talking clips directory
    if not os.path.exists(talking_clips_dir):
        print(f"{Fore.YELLOW}[WARNING] Talking clips directory not found: {talking_clips_dir}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] Will be created automatically - add your 5s talking clips there{Style.RESET_ALL}")
    else:
        talking_clips = [f for f in os.listdir(talking_clips_dir) if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        if talking_clips:
            print(f"{Fore.GREEN}[MAIN] Found {len(talking_clips)} talking clips for lipsync{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[WARNING] No talking clips found - system will use fallback mode{Style.RESET_ALL}")
    
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

    # Test real lipsync system
    try:
        print(f"{Fore.CYAN}[MAIN] Testing real lipsync integration system...{Style.RESET_ALL}")
        if setup_lipsync_environment():
            print(f"{Fore.GREEN}[MAIN] Real lipsync system test passed.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[WARNING] Real lipsync system test failed - using fallback mode{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[WARNING] Add talking clips to avatars/Darwin/talking_clips/ for full functionality{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[WARNING] Real lipsync system test error: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] Application will continue with fallback lipsync functionality{Style.RESET_ALL}")

    print(f"{Fore.GREEN}[MAIN] All critical dependencies verified successfully.{Style.RESET_ALL}")
    return True

def main():
    """Enhanced main function with real lipsync integration"""
    print(f"{Fore.GREEN}{'=' * 80}")
    print(f"{Fore.YELLOW}Starting Enhanced Darwin Chat Application (Thread-Safe + Real Lipsync)")
    print(f"{Fore.YELLOW}Features: LLM + Real Lipsync + Node-based Idle Videos + Advanced TTS")
    print(f"{Fore.GREEN}{'=' * 80}{Style.RESET_ALL}")
    print(f"[MAIN] Project directory: {PROJECT_DIR}")

    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependency check failed. Please fix the issues above.{Style.RESET_ALL}")
        return

    # Ensure temp directories exist
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    lipsync_temp_dir = os.path.join(temp_dir, "lipsync")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(lipsync_temp_dir, exist_ok=True)
    print(f"[MAIN] TTS temp directory: {temp_dir}")
    print(f"[MAIN] Lipsync temp directory: {lipsync_temp_dir}")

    # Static file serving for video files
    try:
        app.add_static_files('/avatars', os.path.join(PROJECT_DIR, 'avatars'))
        app.add_static_files('/tempstream', temp_dir)
        print(f"{Fore.GREEN}[MAIN] Static file serving configured{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[WARNING] Static file serving failed: {e}{Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}[MAIN] All systems ready. Starting enhanced web interface with real lipsync...{Style.RESET_ALL}")

    # Show system information
    status = node_system.get_system_status()
    print(f"{Fore.CYAN}[MAIN] Node System Status:{Style.RESET_ALL}")
    for key, value in status.items():
        print(f"  {key}: {value}")

    # Show lipsync status
    talking_clips_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin", "talking_clips")
    if os.path.exists(talking_clips_dir):
        clips = [f for f in os.listdir(talking_clips_dir) if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        print(f"{Fore.CYAN}[MAIN] Lipsync System Status:{Style.RESET_ALL}")
        print(f"  talking_clips_directory: {talking_clips_dir}")
        print(f"  available_clips: {len(clips)}")
        print(f"  lipsync_mode: {'REAL' if clips else 'FALLBACK'}")
    else:
        print(f"{Fore.CYAN}[MAIN] Lipsync System Status: FALLBACK MODE{Style.RESET_ALL}")

    ui.run(
        title='Enhanced Darwin Chat with Real Lipsync Avatar System',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()