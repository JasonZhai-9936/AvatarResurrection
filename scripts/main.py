# main.py - Enhanced main application with voice selection

import sys
import os
import threading

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui
from ui import build_ui
from LLM_Groq import generate_darwin_response
from TTS_Piper import generate_and_stream_audio, set_voice_model
from colorama import Fore, Style, init

# Initialize colorama for colored terminal output
init(autoreset=True)

# Global references for UI elements that need to be updated
chat_log = None
is_first_message = True  # Used to clear the initial "Ready" message
current_voice = "en_GB-semaine-medium"  # Default voice

def handle_voice_change(voice_name: str):
    """Handle voice model change."""
    global current_voice
    current_voice = voice_name
    
    voice_path = os.path.join(PROJECT_DIR, "Piper_Voices", f"{voice_name}.onnx")
    
    if os.path.exists(voice_path):
        print(f"{Fore.CYAN}[MAIN] Voice changed to: {voice_name}{Style.RESET_ALL}")
        # Reset the voice instance so it loads the new model on next use
        set_voice_model(voice_path)
        ui.notify(f'Voice successfully changed to {voice_name}', type='positive')
    else:
        print(f"{Fore.RED}[MAIN] Voice model not found: {voice_path}{Style.RESET_ALL}")
        ui.notify(f'Voice model not found: {voice_name}', type='negative')

def handle_user_input(user_text: str):
    """Handle user input, generate Darwin's response, update chat log, and stream TTS."""
    global chat_log, is_first_message, current_voice

    # On the very first input, clear the initial "Ready to chat" message.
    if is_first_message:
        chat_log.clear()
        is_first_message = False

    try:
        print(f"[MAIN] User asked: {user_text}")

        # Add the user's question to the chat log
        with chat_log:
            ui.chat_message(text=user_text, name='You', sent=True)

        # Generate response using the LLM (UI will wait here as it's synchronous)
        print(f"{Fore.CYAN}[MAIN] Generating LLM response...{Style.RESET_ALL}")
        response = generate_darwin_response(user_text)
        print(f"[MAIN] Darwin responded: {response}")

        # Add Darwin's response to the chat log
        with chat_log:
            ui.chat_message(text=response, name='Darwin', sent=False)

        # Generate and stream TTS audio in a separate thread to avoid blocking the UI
        def tts_thread():
            try:
                print(f"{Fore.MAGENTA}[MAIN] Starting TTS generation and streaming with voice: {current_voice}...{Style.RESET_ALL}")
                audio_file = generate_and_stream_audio(response)
                if audio_file:
                    print(f"{Fore.GREEN}[MAIN] TTS completed successfully. Audio saved to: {audio_file}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[MAIN] TTS generation failed.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[MAIN] TTS Error: {e}{Style.RESET_ALL}")

        # Start TTS in background thread
        tts_worker = threading.Thread(target=tts_thread, daemon=True)
        tts_worker.start()

    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        error_message = 'Sorry, Darwin is having trouble responding right now.'

        # Add an error message to the chat log
        with chat_log:
            ui.chat_message(text=error_message, name='System', sent=False)

        # Show a notification for the error
        ui.notify("Error: Could not generate response", type='negative')

@ui.page('/')
def index():
    """Main page"""
    global chat_log

    # Set page title and styling
    ui.page_title('Chat with Charles Darwin')

    # Add custom CSS for better styling
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
        .q-message-text--sent .q-message-text-content {
            color: black !important;
            background-color: #e0f2fe !important;
        }
        .q-message-text--received .q-message-text-content {
            color: black !important;
            background-color: #f1f5f9 !important;
        }
        
        /* Enhanced sidebar styling */
        .sidebar-button {
            transition: all 0.2s ease;
        }
        .sidebar-button:hover {
            transform: translateX(2px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Voice selection styling */
        .voice-section {
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            border-top: 2px solid #cbd5e0;
        }
    </style>
    ''')

    # Header
    with ui.row().classes('w-full justify-center p-4'):
        ui.label('Chat with Charles Darwin').classes('text-4xl font-bold text-white')

    # Build the main UI and get the chat log reference
    chat_log = build_ui(handle_user_input, handle_voice_change)

def check_dependencies():
    """Check if all required dependencies and files are available."""
    print(f"{Fore.CYAN}[MAIN] Checking dependencies...{Style.RESET_ALL}")
    
    # Check if required Python files exist in scripts directory
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py', 'TTS_Piper.py', 'ui.py']
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"{Fore.RED}[ERROR] Required file not found: {file_path}{Style.RESET_ALL}")
            return False

    # Check if config files exist in project directory
    config_path = os.path.join(PROJECT_DIR, 'config.json')
    api_key_path = os.path.join(PROJECT_DIR, 'groq_api_key.txt')
    
    # Check for Piper_Voices directory and at least one voice model
    voices_dir = os.path.join(PROJECT_DIR, 'Piper_Voices')
    if not os.path.exists(voices_dir):
        print(f"{Fore.RED}[ERROR] Piper_Voices directory not found at: {voices_dir}{Style.RESET_ALL}")
        return False
    
    # Check for at least one .onnx voice model
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

    # Test TTS system
    try:
        print(f"{Fore.CYAN}[MAIN] Testing TTS system...{Style.RESET_ALL}")
        from TTS_Piper import test_tts_system
        if not test_tts_system():
            print(f"{Fore.RED}[ERROR] TTS system test failed.{Style.RESET_ALL}")
            return False
        print(f"{Fore.GREEN}[MAIN] TTS system test passed.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR] TTS system test error: {e}{Style.RESET_ALL}")
        return False

    print(f"{Fore.GREEN}[MAIN] All dependencies and systems verified successfully.{Style.RESET_ALL}")
    return True

def main():
    """Main function to start the application"""
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}Starting Enhanced Darwin Chat Application with TTS")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")
    print(f"[MAIN] Project directory: {PROJECT_DIR}")

    # Check all dependencies first
    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependency check failed. Please fix the issues above.{Style.RESET_ALL}")
        return

    # Ensure temp directory exists
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    print(f"[MAIN] TTS temp directory: {temp_dir}")

    print(f"{Fore.GREEN}[MAIN] All systems ready. Starting enhanced web interface...{Style.RESET_ALL}")

    # Configure NiceGUI
    ui.run(
        title='Enhanced Darwin Chat with TTS',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()