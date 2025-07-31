# main.py - Clean main application with simple workflow

import sys
import os
import threading
import time
import queue

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui, app
from enhanced_ui import build_ui
from LLM_Groq import generate_darwin_response
from enhanced_tts_piper import generate_complete_audio, set_voice_model
from node_video_system import NodeVideoSystem
from test_lipsync_integration import generate_lipsync_with_integration, setup_lipsync_environment
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Global variables
chat_container = None
is_first_message = True
node_system = NodeVideoSystem("Darwin")
ui_update_queue = queue.Queue()
is_processing_response = False

def add_message_to_chat(text: str, message_type: str):
    """Add message to chat - thread-safe"""
    def add_message():
        global chat_container
        
        css_classes = {
            'user': 'message-item user-message',
            'darwin': 'message-item darwin-message',
            'system': 'message-item system-message'
        }
        
        css_class = css_classes.get(message_type, 'message-item system-message')
        
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
    
    ui_update_queue.put(('add_message', add_message))

def update_video_player(video_path: str):
    """Update video player - thread-safe with better autoplay"""
    print(f"{Fore.BLUE}[VIDEO] Loading: {os.path.basename(video_path)}{Style.RESET_ALL}")
    
    def video_update():
        # Convert to web-accessible path
        if video_path.startswith(os.path.join(PROJECT_DIR, "tempstream")):
            # Tempstream file
            filename = os.path.basename(video_path)
            video_url = f'/tempstream/{filename}'
        else:
            # Avatar file
            relative_path = os.path.relpath(video_path, os.path.join(PROJECT_DIR, 'avatars'))
            video_url = f'/avatars/{relative_path.replace(os.sep, "/")}'
        
        print(f"{Fore.CYAN}[VIDEO] URL: {video_url}{Style.RESET_ALL}")
        
        ui.run_javascript(f'''
            console.log('Loading video: {video_url}');
            
            const video = document.getElementById('mainVideo');
            if (video) {{
                // Remove all existing event listeners to avoid conflicts
                video.replaceWith(video.cloneNode(true));
                const newVideo = document.getElementById('mainVideo');
                
                // Set up fresh event listeners
                newVideo.addEventListener('loadeddata', function() {{
                    console.log('Video loaded, attempting to play...');
                    this.currentTime = 0;  // Start from beginning
                    this.play().then(() => {{
                        console.log('✓ Video playing successfully');
                    }}).catch(e => {{
                        console.error('✗ Play failed:', e);
                        // Force play after brief delay
                        setTimeout(() => {{
                            this.play().catch(e2 => console.error('Retry play failed:', e2));
                        }}, 100);
                    }});
                }});
                
                newVideo.addEventListener('error', function(e) {{
                    console.error('✗ Video error:', this.error);
                }});
                
                newVideo.addEventListener('playing', function() {{
                    console.log('✓ Video is now playing');
                }});
                
                newVideo.addEventListener('ended', function() {{
                    console.log('✓ Video ended');
                }});
                
                // Ensure video properties
                newVideo.autoplay = true;
                newVideo.muted = false;
                newVideo.controls = false;
                newVideo.playsInline = true;
                
                // Set source and load
                newVideo.src = '{video_url}';
                newVideo.load();
                
                // Force immediate play attempt
                setTimeout(() => {{
                    newVideo.play().catch(e => console.log('Initial play attempt:', e));
                }}, 50);
                
            }} else {{
                console.error('✗ Video element not found');
            }}
        ''')
    
    ui_update_queue.put(('video_update', video_update))

def process_ui_updates():
    """Process queued UI updates"""
    try:
        while True:
            try:
                update_type, update_func = ui_update_queue.get_nowait()
                update_func()
                ui_update_queue.task_done()
            except queue.Empty:
                break
    except Exception as e:
        print(f"{Fore.RED}[UI] Error processing updates: {e}{Style.RESET_ALL}")

def handle_user_input(user_text: str):
    """Handle user input with simple sequential workflow"""
    global chat_container, is_first_message, is_processing_response

    # Prevent multiple simultaneous responses
    if is_processing_response:
        print(f"{Fore.YELLOW}[MAIN] Already processing response, ignoring input{Style.RESET_ALL}")
        return

    # Clear initial message
    if is_first_message:
        def clear_chat():
            chat_container.clear()
        ui_update_queue.put(('clear_chat', clear_chat))
        is_first_message = False

    try:
        print(f"{Fore.CYAN}[MAIN] User: {user_text}{Style.RESET_ALL}")
        is_processing_response = True

        # Add user message
        add_message_to_chat(user_text, 'user')

        # Interrupt idle system
        node_system.interrupt_for_response()

        # Generate LLM response
        print(f"{Fore.YELLOW}[MAIN] Generating response...{Style.RESET_ALL}")
        response = generate_darwin_response(user_text)
        print(f"{Fore.GREEN}[MAIN] Response: {response}{Style.RESET_ALL}")

        # Add response to chat
        add_message_to_chat(response, 'darwin')

        # Start response processing in background
        def process_response():
            global is_processing_response
            
            try:
                # Step 1: Return to main if needed
                print(f"{Fore.CYAN}[WORKFLOW] Step 1: Returning to main{Style.RESET_ALL}")
                return_videos = node_system.return_to_main_path()
                
                for video_path in return_videos:
                    if os.path.exists(video_path):
                        print(f"{Fore.BLUE}[WORKFLOW] Return video: {os.path.basename(video_path)}{Style.RESET_ALL}")
                        update_video_player(video_path)
                        duration = node_system.get_video_duration(video_path)
                        time.sleep(duration + 0.5)
                
                # Step 2: Generate lipsync
                print(f"{Fore.CYAN}[WORKFLOW] Step 2: Generating lipsync{Style.RESET_ALL}")
                success, lipsync_path = generate_lipsync_with_integration(response)
                
                if success and lipsync_path and os.path.exists(lipsync_path):
                    # Step 3: Play lipsync
                    print(f"{Fore.CYAN}[WORKFLOW] Step 3: Playing lipsync{Style.RESET_ALL}")
                    update_video_player(lipsync_path)
                    duration = node_system.get_video_duration(lipsync_path)
                    
                    print(f"{Fore.MAGENTA}[WORKFLOW] Waiting {duration + 0.5:.2f}s for lipsync to complete{Style.RESET_ALL}")
                    time.sleep(duration + 0.5)
                    
                    print(f"{Fore.GREEN}[WORKFLOW] Lipsync complete{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[WORKFLOW] Lipsync failed{Style.RESET_ALL}")
                
                # Step 4: Resume idle (ONLY after lipsync is completely done)
                print(f"{Fore.CYAN}[WORKFLOW] Step 4: Resuming idle{Style.RESET_ALL}")
                is_processing_response = False
                
                # Small delay to ensure clean transition
                time.sleep(0.5)
                node_system.start_idle_playing(update_video_player)
                
            except Exception as e:
                print(f"{Fore.RED}[WORKFLOW] Error: {e}{Style.RESET_ALL}")
                is_processing_response = False
                node_system.start_idle_playing(update_video_player)

        # Start background processing
        response_thread = threading.Thread(target=process_response, daemon=True)
        response_thread.start()

    except Exception as e:
        print(f"{Fore.RED}[MAIN] Error handling input: {e}{Style.RESET_ALL}")
        add_message_to_chat('Sorry, Darwin is having trouble.', 'system')
        is_processing_response = False
        node_system.start_idle_playing(update_video_player)

def start_idle_system():
    """Start the idle video system only if not processing"""
    if not is_processing_response:
        print(f"{Fore.GREEN}[MAIN] Starting idle system{Style.RESET_ALL}")
        node_system.start_idle_playing(update_video_player)
    else:
        print(f"{Fore.YELLOW}[MAIN] Skipping idle start - response in progress{Style.RESET_ALL}")

@ui.page('/')
def index():
    """Main page"""
    global chat_container

    ui.page_title('Darwin Chat - Clean Version')

    # Header
    with ui.row().classes('w-full justify-between items-center p-4'):
        ui.label('Chat with Charles Darwin').classes('text-4xl font-bold text-white')
        
        # Status
        status_label = ui.label('Initializing...').classes('text-sm text-white bg-blue-600 px-3 py-1 rounded')
        
        def update_status():
            if is_processing_response:
                status_label.text = "Processing..."
                status_label.classes(remove='bg-green-600 bg-red-600', add='bg-blue-600')
            elif node_system.is_playing and not node_system.is_interrupted:
                video_name = os.path.basename(node_system.current_video_path) if node_system.current_video_path else "Loading"
                status_label.text = f"Playing: {video_name}"
                status_label.classes(remove='bg-blue-600 bg-red-600', add='bg-green-600')
            else:
                status_label.text = "Ready"
                status_label.classes(remove='bg-green-600 bg-blue-600', add='bg-red-600')
        
        def timer_function():
            process_ui_updates()
            update_status()
        
        ui.timer(0.5, timer_function)

    # Build main UI
    chat_container = build_ui(handle_user_input)
    
    # Configure video player with enhanced autoplay
    ui.run_javascript('''
        setTimeout(function() {
            console.log('Configuring video player for autoplay...');
            
            const video = document.getElementById('mainVideo');
            if (video) {
                // Force unmute and autoplay
                video.muted = false;
                video.autoplay = true;
                video.playsInline = true;
                
                // Add aggressive autoplay enforcement
                function forcePlay() {
                    if (video.paused && video.readyState >= 2) {
                        video.play().then(() => {
                            console.log('✓ Forced play successful');
                        }).catch(e => {
                            console.log('Force play failed:', e);
                            // Try again in 500ms
                            setTimeout(forcePlay, 500);
                        });
                    }
                }
                
                // Set up autoplay triggers
                video.addEventListener('loadstart', forcePlay);
                video.addEventListener('loadeddata', forcePlay);
                video.addEventListener('canplay', forcePlay);
                video.addEventListener('canplaythrough', forcePlay);
                
                // Prevent pausing
                video.addEventListener('pause', function() {
                    console.log('Video paused - forcing resume');
                    setTimeout(() => {
                        this.play().catch(e => console.log('Resume failed:', e));
                    }, 100);
                });
                
                console.log('✓ Enhanced autoplay system configured');
            } else {
                console.error('✗ Video element not found');
            }
        }, 1000);
    ''')
    
    # Start idle system after longer delay to ensure video is ready
    ui.timer(3.0, start_idle_system, once=True)

def check_dependencies():
    """Check all required files and directories"""
    print(f"{Fore.CYAN}[MAIN] Checking dependencies...{Style.RESET_ALL}")
    
    # Check script files
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py', 'enhanced_tts_piper.py', 'enhanced_ui.py', 'node_video_system.py', 'test_lipsync_integration.py']
    
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"{Fore.RED}[ERROR] Missing: {file_path}{Style.RESET_ALL}")
            return False

    # Check directories
    avatar_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin")
    nodes_dir = os.path.join(avatar_dir, "Nodes")
    
    if not os.path.exists(nodes_dir):
        print(f"{Fore.RED}[ERROR] Nodes directory not found: {nodes_dir}{Style.RESET_ALL}")
        return False

    # Check config files
    config_path = os.path.join(PROJECT_DIR, 'config.json')
    api_key_path = os.path.join(PROJECT_DIR, 'groq_api_key.txt')
    
    if not os.path.exists(config_path):
        print(f"{Fore.RED}[ERROR] Config not found: {config_path}{Style.RESET_ALL}")
        return False

    if not os.path.exists(api_key_path):
        print(f"{Fore.RED}[ERROR] API key not found: {api_key_path}{Style.RESET_ALL}")
        return False

    # Check voice models
    voices_dir = os.path.join(PROJECT_DIR, 'Piper_Voices')
    if not os.path.exists(voices_dir):
        print(f"{Fore.RED}[ERROR] Voices directory not found: {voices_dir}{Style.RESET_ALL}")
        return False
    
    voice_files = [f for f in os.listdir(voices_dir) if f.endswith('.onnx')]
    if not voice_files:
        print(f"{Fore.RED}[ERROR] No voice models found{Style.RESET_ALL}")
        return False

    print(f"{Fore.GREEN}[MAIN] All dependencies verified{Style.RESET_ALL}")
    return True

def main():
    """Main function"""
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}Darwin Chat - Clean Version")
    print(f"{Fore.YELLOW}Workflow: Idle → Response → Lipsync → Idle")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")

    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependencies check failed{Style.RESET_ALL}")
        return

    # Setup directories
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)

    # Configure static file serving
    try:
        app.add_static_files('/avatars', os.path.join(PROJECT_DIR, 'avatars'))
        app.add_static_files('/tempstream', temp_dir)
        print(f"{Fore.GREEN}[MAIN] Static files configured{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[MAIN] Static files failed: {e}{Style.RESET_ALL}")
        return

    # Test systems
    try:
        from enhanced_tts_piper import test_tts_system
        if not test_tts_system():
            print(f"{Fore.RED}[MAIN] TTS test failed{Style.RESET_ALL}")
            return
        print(f"{Fore.GREEN}[MAIN] TTS system ready{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[MAIN] TTS test error: {e}{Style.RESET_ALL}")
        return

    if not setup_lipsync_environment():
        print(f"{Fore.RED}[MAIN] Lipsync setup failed{Style.RESET_ALL}")
        return

    print(f"{Fore.GREEN}[MAIN] All systems ready{Style.RESET_ALL}")

    ui.run(
        title='Darwin Chat - Clean',
        port=8080,
        show=True,
        reload=False
    )

if __name__ == '__main__':
    main()