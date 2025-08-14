# main.py - Complete main application with proper video event handling and no duplicate TTS

import sys
import os
import threading
import time

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui, app
from LLM_Groq import generate_darwin_response
from TTS_Piper import generate_and_stream_audio, set_voice_model
from video_manager import VideoManager
from positional_lipsync import generate_lipsync_video  # Using the new Sora-based system
from colorama import Fore, Style, init

# Initialize colorama for colored terminal output
init(autoreset=True)

# Global references for UI elements and systems
chat_log = None
video_manager = None
main_video_element = None
is_first_message = True
current_voice = "en_GB-semaine-medium"

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

def video_ui_callback(video_url: str):
    """Callback to update the main video in the UI"""
    global main_video_element
    
    print(f"{Fore.GREEN}[UI] Updating video: {video_url}{Style.RESET_ALL}")
    
    if main_video_element:
        # Update the video source directly
        main_video_element.props(f'src="{video_url}"')
        print(f"{Fore.BLUE}[UI] Video element updated with new source{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}[UI] Video element not available{Style.RESET_ALL}")

def video_ended_callback():
    """Called when a video ends"""
    global video_manager
    if video_manager:
        print(f"{Fore.BLUE}[MAIN] Video ended - requesting next clip{Style.RESET_ALL}")
        video_manager.on_video_ended()

def handle_user_input(user_text: str):
    """Enhanced user input handler with video and lip-sync integration - NO DUPLICATE TTS."""
    global chat_log, is_first_message, current_voice, video_manager

    # On the very first input, clear the initial "Ready to chat" message
    if is_first_message:
        chat_log.clear()
        is_first_message = False

    try:
        print(f"[MAIN] User asked: {user_text}")

        # Add the user's question to the chat log
        with chat_log:
            ui.chat_message(text=user_text, name='You', sent=True)

        # Notify video manager about user input
        if video_manager:
            video_manager.prepare_for_user_input()
        
        # Generate response using the LLM
        print(f"{Fore.CYAN}[MAIN] Generating LLM response...{Style.RESET_ALL}")
        response = generate_darwin_response(user_text)
        print(f"[MAIN] Darwin responded: {response}")

        # Add Darwin's response to the chat log
        with chat_log:
            ui.chat_message(text=response, name='Darwin', sent=False)

        # Start lip-sync generation if video manager is available
        # The positional lipsync system will handle TTS generation internally
        if video_manager:
            def lipsync_complete_callback():
                print(f"{Fore.GREEN}[MAIN] Lip-sync playback completed{Style.RESET_ALL}")
            
            print(f"{Fore.CYAN}[MAIN] Starting Sora lipsync (includes TTS generation){Style.RESET_ALL}")
            video_manager.start_lipsync_generation(response, lipsync_complete_callback)
        else:
            print(f"{Fore.YELLOW}[MAIN] Video manager not available, generating standalone TTS{Style.RESET_ALL}")
            
            # Only generate TTS if no video manager (fallback)
            def tts_thread():
                try:
                    print(f"{Fore.MAGENTA}[MAIN] Fallback TTS generation with voice: {current_voice}...{Style.RESET_ALL}")
                    audio_file = generate_and_stream_audio(response)
                    if audio_file:
                        print(f"{Fore.GREEN}[MAIN] Fallback TTS completed successfully.{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}[MAIN] Fallback TTS generation failed.{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}[MAIN] Fallback TTS Error: {e}{Style.RESET_ALL}")

            # Start fallback TTS in background thread
            tts_worker = threading.Thread(target=tts_thread, daemon=True)
            tts_worker.start()

    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        error_message = 'Sorry, Darwin is having trouble responding right now.'

        # Add an error message to the chat log
        with chat_log:
            ui.chat_message(text=error_message, name='System', sent=False)

        ui.notify("Error: Could not generate response", type='negative')

def setup_video_system():
    """Initialize the video management system"""
    global video_manager
    
    print(f"{Fore.CYAN}[MAIN] Initializing video management system...{Style.RESET_ALL}")
    
    try:
        video_manager = VideoManager(video_ui_callback)
        print(f"{Fore.GREEN}[MAIN] Video management system initialized successfully{Style.RESET_ALL}")
        return True
        
    except Exception as e:
        print(f"{Fore.RED}[MAIN] Failed to initialize video system: {e}{Style.RESET_ALL}")
        return False

def update_status_displays():
    """Periodically update video status displays"""
    global video_manager
    
    while video_manager and video_manager.is_playing:
        try:
            if video_manager:
                status = video_manager.get_status()
                
                # Simple status update without complex JavaScript
                print(f"[STATUS] State: {status['current_state']} | Mode: {status['current_mode']} | Queue: {status['queue_size']}")
                
            time.sleep(3)  # Update every 3 seconds
            
        except Exception as e:
            print(f"{Fore.RED}[STATUS] Error updating status: {e}{Style.RESET_ALL}")
            break

@ui.page('/')
def index():
    """Main page with clean video integration and volume slider"""
    global chat_log, video_manager, main_video_element

    # Set page title and styling
    ui.page_title('Chat with Charles Darwin - Enhanced Video')

    # Add the final corrected CSS
    ui.add_head_html('''
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
        }
        
        .nicegui-content {
            background: transparent !important;
        }

        /* Styles the outer bubble for SENT messages (User) */
        .q-message--sent .q-message-text {
            background-color: #3b82f6 !important; /* Blue */
            color: white !important;
            border-radius: 18px !important;
            padding: 10px 16px !important;
            max-width: 80%;
            margin-left: auto; /* Aligns bubble to the right */
            margin-right: 0;
        }
        
        /* Styles the outer bubble for RECEIVED messages (Darwin) */
        .q-message--received .q-message-text {
            background-color: #10b981 !important; /* Green */
            color: white !important;
            border-radius: 18px !important;
            padding: 10px 16px !important;
            max-width: 80%;
            margin-right: auto; /* Aligns bubble to the left */
            margin-left: 0;
        }

        /* This rule for inner content ensures no highlighting */
        .q-message-text-content,
        .q-message-text-content * {
            text-shadow: none !important;
            box-shadow: none !important;
            font-weight: normal !important;
            font-style: normal !important;
            background: transparent !important;
        }
        
        /* Styles the name labels ('You', 'Darwin') */
        .q-message-name {
            color: black !important;
            font-weight: 600 !important; /* semi-bold */
        }
        
        /* Make text input black */
        .q-field__native,
        .q-field__input,
        textarea {
            color: #1f2937 !important;
            background-color: white !important;
        }
        
        .q-field__label {
            color: #6b7280 !important;
        }
        
        /* Volume slider styling */
        .volume-slider {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 8px;
            padding: 12px 16px;
            margin: 8px 0;
        }
    </style>
    ''')


    # Header
    with ui.row().classes('w-full justify-center p-4'):
        ui.label('Chat with Charles Darwin - Enhanced Video').classes('text-4xl font-bold text-white')

    with ui.column().classes('w-full h-screen gap-0'):
        # === MAIN CONTENT ROW ===
        with ui.row().classes('w-full flex-grow items-start justify-start gap-4 p-4'):
            
            # === LEFT VIDEO PLAYER (MAIN AVATAR) ===
            with ui.column().classes('items-start shrink-0').style('width: 35%; height: 100%;'):
                with ui.card().classes('p-0 main-video-container').style('width: 100%; aspect-ratio: 2/3;'):
                    
                    # Create the main video element with proper event handling
                    main_video_element = ui.video(
                        src='',  # Will be set by video manager
                        autoplay=True,
                        muted=True,  # START MUTED for autoplay policy, unmute when needed
                        controls=False
                    ).classes('w-full h-full').style('object-fit: contain;')
                    
                    # Set up the video ended event handler
                    main_video_element.on('ended', video_ended_callback)
                    
                    # Status overlay
                    with ui.element('div').style('position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); color: white; padding: 5px 10px; border-radius: 5px; font-size: 12px; z-index: 10;'):
                        status_label = ui.label('Initializing...').classes('video-status')

                # Add Volume Slider below video
                with ui.card().classes('volume-slider w-full mt-2'):
                    ui.label('🔊 Volume').classes('text-sm font-medium text-gray-700 mb-2')
                    volume_slider = ui.slider(
                        min=0, max=100, value=75, step=5
                    ).props('label-always').classes('w-full')
                    ui.label('Adjust Darwin\'s voice volume').classes('text-xs text-gray-500 mt-1')

            # === CENTER PANEL ===
            with ui.column().classes('items-center gap-4 h-full').style('width: 45%;'):
                # === BACKGROUND VIDEO PLAYER ===
                with ui.card().classes('p-0 overflow-hidden').style('width: 100%; aspect-ratio: 16/9; background: black;'):
                    ui.video(
                        src='',  # Can be set to a background video
                        autoplay=True,
                        muted=True,  # Background video can stay muted
                        loop=True,
                        controls=False
                    ).classes('w-full h-full').style('object-fit: cover;')

                # === CHAT LOG (SCROLLABLE) ===
                chat_log = ui.column().classes('w-full flex-grow p-4 gap-4 overflow-y-auto rounded-lg').style('background: #f0f0f0;')
                with chat_log:
                    ui.label('Ready to chat with Darwin').classes('text-lg text-center w-full').style('color: #6b7280;')

                # === TEXT INPUT & BUTTON ===
                with ui.column().classes('items-center gap-4 w-full'):
                    prompt_input = ui.textarea(
                        label='Your question for Darwin', 
                        placeholder='Ask Charles Darwin anything...'
                    ).props('outlined').classes('w-full').style('min-height: 120px; font-size: 16px;')

                    def submit_prompt():
                        user_text = prompt_input.value
                        if user_text and user_text.strip():
                            handle_user_input(user_text)
                            prompt_input.value = ""
                        else:
                            ui.notify("Please enter a question first", color="warning")

                    ui.button('Ask Darwin', on_click=submit_prompt).classes('w-full text-lg py-3 px-6 rounded-lg').style('background-color: #2563eb; color: white;')

            # === RIGHT SIDEBAR ===
            with ui.column().classes('h-full bg-gray-100 border-l border-gray-300').style('width: 250px;'):
                # Sidebar Header
                with ui.row().classes('w-full items-center justify-between p-3 border-b border-gray-300'):
                    ui.label('Menu').classes('font-semibold text-gray-700')

                # Sidebar Content
                with ui.column().classes('w-full p-3 gap-3'):
                    # Settings Button
                    ui.button('⚙️ Settings', on_click=lambda: ui.navigate.to('/settings')).classes('w-full justify-start bg-gray-200 text-gray-700 py-2 px-3 rounded')
                    
                    # Video Status Section
                    ui.separator()
                    ui.label('Video Status').classes('font-medium text-gray-600 text-sm mt-4')
                    
                    state_label = ui.label('State: Unknown').classes('text-xs text-gray-500')
                    mode_label = ui.label('Mode: Unknown').classes('text-xs text-gray-500')
                    
                    # Quick Info
                    ui.separator()
                    ui.label('Configuration').classes('font-medium text-gray-600 text-sm mt-4')
                    
                    # Load config for display
                    import json
                    try:
                        config_file = os.path.join(PROJECT_DIR, "config.json")
                        with open(config_file, 'r') as f:
                            config = json.load(f)
                    except:
                        config = {'useRAG': False, 'maxWords': 50, 'useCuda': True}
                    
                    ui.label(f"RAG: {'On' if config.get('useRAG') else 'Off'}").classes('text-xs text-gray-500')
                    ui.label(f"Max Words: {config.get('maxWords', 50)}").classes('text-xs text-gray-500')
                    ui.label(f"CUDA: {'On' if config.get('useCuda') else 'Off'}").classes('text-xs text-gray-500')

        # === VOICE SELECTION SECTION ===
        ui.separator().classes('w-full')
        
        with ui.row().classes('w-full p-4 bg-gray-50 border-t border-gray-200 items-center justify-center gap-8'):
            ui.label('Voice Selection').classes('text-lg font-semibold text-gray-700')
            
            # Get available voices
            def get_available_voices():
                voices_dir = os.path.join(PROJECT_DIR, "Piper_Voices")
                voices = []
                
                if os.path.exists(voices_dir):
                    for file in os.listdir(voices_dir):
                        if file.endswith('.onnx'):
                            voice_name = file.replace('.onnx', '')
                            voices.append(voice_name)
                
                return sorted(voices) if voices else ['en_GB-semaine-medium']
            
            available_voices = get_available_voices()
            current_voice_default = available_voices[0] if available_voices else 'en_GB-semaine-medium'
            
            voice_dropdown = ui.select(
                options=available_voices,
                value=current_voice_default,
                label='Choose Voice Model'
            ).classes('min-w-64')
            
            def on_voice_change():
                selected_voice = voice_dropdown.value
                ui.notify(f'Voice changed to: {selected_voice}', type='info')
                handle_voice_change(selected_voice)
            
            voice_dropdown.on('update:model-value', on_voice_change)
            
            # Voice info
            ui.label(f'Available voices: {len(available_voices)}').classes('text-sm text-gray-500')
    
    # Add enhanced JavaScript with video management and smart audio control
    ui.add_body_html('''
    <script>
    let videoManager = {
        currentVideo: null,
        statusDisplay: null,
        isReady: false,
        isLipsyncVideo: false
    };

    // Update video source and handle audio intelligently
    function updateMainVideo(videoUrl) {
        const video = document.querySelector('video[autoplay]:not([loop])');
        
        if (video && videoUrl) {
            console.log('[VIDEO] Loading new video:', videoUrl);
            
            // Check if this is a lipsync video (contains temp_lipsync in path)
            videoManager.isLipsyncVideo = videoUrl.includes('temp_lipsync') || videoUrl.includes('lipsync');
            
            if (videoManager.isLipsyncVideo) {
                console.log('[VIDEO] Lipsync video detected - will unmute');
                video.muted = false;
                video.volume = 1.0;
            } else {
                console.log('[VIDEO] Regular video - staying muted');
                video.muted = true;
                video.volume = 0.0;
            }
            
            video.src = videoUrl;
            video.load();
            
            video.onloadstart = function() {
                if (videoManager.isLipsyncVideo) {
                    video.muted = false;
                    video.volume = 1.0;
                }
            };
            
            video.oncanplay = function() {
                if (videoManager.isLipsyncVideo) {
                    video.muted = false;
                    video.volume = 1.0;
                    console.log('[VIDEO] Lipsync video ready to play (unmuted)');
                } else {
                    console.log('[VIDEO] Regular video ready to play (muted)');
                }
            };
            
            video.onplay = function() {
                if (videoManager.isLipsyncVideo) {
                    video.muted = false;
                    video.volume = 1.0;
                    console.log('[VIDEO] Lipsync video started playing (unmuted)');
                } else {
                    console.log('[VIDEO] Regular video started playing (muted)');
                }
            };
            
            video.onerror = function(e) {
                console.error('[VIDEO] Error loading video:', e);
            };
        }
    }

    // Smart unmute function - only unmute lipsync videos
    function ensureCorrectAudioState() {
        const videos = document.querySelectorAll('video');
        videos.forEach(video => {
            if (!video.hasAttribute('loop')) {  // Don't touch background videos
                // Check current video source
                const isLipsync = video.src && (video.src.includes('temp_lipsync') || video.src.includes('lipsync'));
                
                if (isLipsync) {
                    video.muted = false;
                    video.volume = 1.0;
                } else {
                    video.muted = true;
                    video.volume = 0.0;
                }
            }
        });
    }

    // Initialize when page loads
    window.addEventListener('load', function() {
        console.log('[UI] Darwin Chat UI with video management loaded');
        videoManager.isReady = true;
        
        // Set correct audio state
        ensureCorrectAudioState();
        
        // Set up global functions for Python callback
        window.updateMainVideo = updateMainVideo;
        window.ensureCorrectAudioState = ensureCorrectAudioState;
        
        // Periodically ensure correct audio state
        setInterval(ensureCorrectAudioState, 2000);
        
        console.log('[UI] Video management system ready (smart audio control)');
    });
    
    // Also check audio state when user interacts
    document.addEventListener('click', ensureCorrectAudioState);
    </script>
    ''')
    
    # Initialize video system after UI is built
    def delayed_init():
        time.sleep(0.5)  # Small delay to ensure UI is fully loaded
        success = setup_video_system()
        if success and video_manager:
            # Start status update thread
            status_thread = threading.Thread(target=update_status_displays, daemon=True)
            status_thread.start()
            
            print(f"{Fore.GREEN}[MAIN] Video system fully integrated{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[MAIN] Running without video system{Style.RESET_ALL}")
    
    # Initialize video system in a separate thread
    init_thread = threading.Thread(target=delayed_init, daemon=True)
    init_thread.start()

@ui.page('/settings')
def settings_page():
    """Settings page for configuration options."""
    import json
    
    def load_config():
        """Load settings from config.json in the project root."""
        try:
            config_file = os.path.join(PROJECT_DIR, "config.json")
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {'useRAG': False, 'useCuda': True, 'maxWords': 50}

    def save_config(config):
        """Save settings to config.json in the project root."""
        try:
            config_file = os.path.join(PROJECT_DIR, "config.json")
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    config = load_config()
    
    # Page styling
    ui.add_head_html('''
        <style>
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 0;
            }
            .settings-card {
                background: rgba(255, 255, 255, 0.95);
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            }
        </style>
        ''')
    
    with ui.column().classes('w-full max-w-2xl mx-auto p-8 gap-6'):
        # Header
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Settings').classes('text-3xl font-bold text-white')
            ui.button('← Back to Chat', on_click=lambda: ui.navigate.to('/')).classes('bg-blue-600 text-white px-4 py-2 rounded-lg')
        
        # Settings Card
        with ui.card().classes('p-6 w-full').classes('settings-card'):
            ui.label('Configuration Options').classes('text-xl font-semibold mb-4')
            
            # RAG Setting
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.column():
                    ui.label('Enable RAG Search').classes('font-medium')
                    ui.label('Use Retrieval-Augmented Generation for enhanced responses').classes('text-sm text-gray-600')
                rag_switch = ui.switch(value=config.get('useRAG', False))
            
            ui.separator()
            
            # CUDA Setting
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.column():
                    ui.label('Use CUDA Acceleration').classes('font-medium')
                    ui.label('Enable GPU acceleration for faster TTS processing').classes('text-sm text-gray-600')
                cuda_switch = ui.switch(value=config.get('useCuda', True))
            
            ui.separator()
            
            # Max Words Setting
            with ui.column().classes('w-full mb-4'):
                ui.label('Maximum Words per Response').classes('font-medium mb-2')
                max_words_slider = ui.slider(
                    min=10, max=200, step=10, value=config.get('maxWords', 50)
                ).props('label-always')
                ui.label('Controls the length of Darwin\'s responses').classes('text-sm text-gray-600')
            
            ui.separator()
            
            # Save Button
            def save_settings():
                new_config = {
                    'useRAG': rag_switch.value,
                    'useCuda': cuda_switch.value,
                    'maxWords': int(max_words_slider.value)
                }
                
                if save_config(new_config):
                    ui.notify('Settings saved successfully!', type='positive')
                else:
                    ui.notify('Failed to save settings', type='negative')
            
            ui.button('Save Settings', on_click=save_settings).classes('w-full bg-green-600 text-white py-3 rounded-lg mt-4')

def check_dependencies():
    """Enhanced dependency check including video system"""
    print(f"{Fore.CYAN}[MAIN] Checking dependencies...{Style.RESET_ALL}")
    
    # Check if required Python files exist
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py', 'TTS_Piper.py', 'video_manager.py', 'positional_lipsync.py']
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"{Fore.RED}[ERROR] Required file not found: {file_path}{Style.RESET_ALL}")
            return False

    # Check video nodes directory
    nodes_path = os.path.join(PROJECT_DIR, "avatars", "Darwin", "Nodes")
    if not os.path.exists(nodes_path):
        print(f"{Fore.RED}[ERROR] Video nodes directory not found: {nodes_path}{Style.RESET_ALL}")
        return False
    
    # Count video files
    video_count = 0
    for root, dirs, files in os.walk(nodes_path):
        video_count += len([f for f in files if f.lower().endswith('.mp4')])
    
    if video_count == 0:
        print(f"{Fore.RED}[ERROR] No video files found in nodes directory{Style.RESET_ALL}")
        return False
    
    print(f"{Fore.GREEN}[MAIN] Found {video_count} video files in nodes directory{Style.RESET_ALL}")

    # Check Sora clips directory
    sora_clips_path = os.path.join(PROJECT_DIR, "avatars", "Darwin", "sora", "all")
    if not os.path.exists(sora_clips_path):
        print(f"{Fore.YELLOW}[WARNING] Sora clips directory not found: {sora_clips_path}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[WARNING] Positional lipsync may not work properly{Style.RESET_ALL}")
    else:
        sora_count = len([f for f in os.listdir(sora_clips_path) if f.lower().endswith('.mp4')])
        print(f"{Fore.GREEN}[MAIN] Found {sora_count} Sora lipsync clips{Style.RESET_ALL}")

    # Check config files
    config_path = os.path.join(PROJECT_DIR, 'config.json')
    api_key_path = os.path.join(PROJECT_DIR, 'groq_api_key.txt')
    
    for path, name in [(config_path, 'config.json'), (api_key_path, 'groq_api_key.txt')]:
        if not os.path.exists(path):
            print(f"{Fore.RED}[ERROR] {name} not found at: {path}{Style.RESET_ALL}")
            return False

    # Check Piper voices
    voices_dir = os.path.join(PROJECT_DIR, 'Piper_Voices')
    if not os.path.exists(voices_dir):
        print(f"{Fore.RED}[ERROR] Piper_Voices directory not found: {voices_dir}{Style.RESET_ALL}")
        return False
    
    voice_files = [f for f in os.listdir(voices_dir) if f.endswith('.onnx')]
    if not voice_files:
        print(f"{Fore.RED}[ERROR] No voice models (.onnx files) found in: {voices_dir}{Style.RESET_ALL}")
        return False
    
    print(f"{Fore.GREEN}[MAIN] Found {len(voice_files)} voice model(s){Style.RESET_ALL}")

    # Test TTS system
    try:
        print(f"{Fore.CYAN}[MAIN] Testing TTS system...{Style.RESET_ALL}")
        from TTS_Piper import test_tts_system
        if not test_tts_system():
            print(f"{Fore.RED}[ERROR] TTS system test failed{Style.RESET_ALL}")
            return False
        print(f"{Fore.GREEN}[MAIN] TTS system test passed{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR] TTS system test error: {e}{Style.RESET_ALL}")
        return False

    print(f"{Fore.GREEN}[MAIN] All dependencies verified successfully{Style.RESET_ALL}")
    return True

def cleanup():
    """Cleanup function called on shutdown"""
    global video_manager
    
    print(f"{Fore.YELLOW}[MAIN] Cleaning up...{Style.RESET_ALL}")
    
    if video_manager:
        video_manager.stop()
    
    print(f"{Fore.GREEN}[MAIN] Cleanup completed{Style.RESET_ALL}")

def main():
    """Enhanced main function with video system"""
    print(f"{Fore.GREEN}{'=' * 70}")
    print(f"{Fore.YELLOW}Starting Enhanced Darwin Chat with Video & TTS")
    print(f"{Fore.GREEN}{'=' * 70}{Style.RESET_ALL}")
    print(f"[MAIN] Project directory: {PROJECT_DIR}")

    # Check all dependencies
    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependency check failed. Please fix the issues above.{Style.RESET_ALL}")
        return

    # Ensure temp directories exist
    temp_dirs = [
        os.path.join(PROJECT_DIR, "tempstream"),
        os.path.join(PROJECT_DIR, "temp_lipsync")
    ]
    
    for temp_dir in temp_dirs:
        os.makedirs(temp_dir, exist_ok=True)
        print(f"[MAIN] Temp directory ready: {temp_dir}")

    # Set up static file serving for videos
    avatars_dir = os.path.join(PROJECT_DIR, "avatars")
    lipsync_dir = os.path.join(PROJECT_DIR, "temp_lipsync")
    
    if os.path.exists(avatars_dir):
        app.add_static_files('/avatars', avatars_dir)
        print(f"[MAIN] Serving avatars from: {avatars_dir}")
    
    if os.path.exists(lipsync_dir):
        app.add_static_files('/temp_lipsync', lipsync_dir)
        print(f"[MAIN] Serving lip-sync from: {lipsync_dir}")

    print(f"{Fore.GREEN}[MAIN] All systems ready. Starting enhanced web interface with video...{Style.RESET_ALL}")

    try:
        # Configure and run NiceGUI
        ui.run(
            title='Enhanced Darwin Chat with Video & TTS',
            port=8080,
            show=True,
            reload=False,
            dark=None,
            storage_secret='darwin_chat_secret_key'
        )
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}[MAIN] Interrupted by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[MAIN] Error running application: {e}{Style.RESET_ALL}")
    finally:
        cleanup()

if __name__ == '__main__':
    main()