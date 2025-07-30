# main.py - Main application launcher with TTS integration

import sys
import os
import threading

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui
from ui import build_ui
from LLM_Groq import generate_darwin_response
from TTS_Piper import generate_and_stream_audio
from colorama import Fore, Style, init

# Initialize colorama for colored terminal output
init(autoreset=True)

# Global references for UI elements that need to be updated
chat_log = None
is_first_message = True  # Used to clear the initial "Ready" message

def handle_user_input(user_text: str):
    """Handle user input, generate Darwin's response, update chat log, and stream TTS."""
    global chat_log, is_first_message

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
                print(f"{Fore.MAGENTA}[MAIN] Starting TTS generation and streaming...{Style.RESET_ALL}")
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
    </style>
    ''')

    # Header
    with ui.row().classes('w-full justify-center p-4'):
        ui.label('Chat with Charles Darwin').classes('text-4xl font-bold text-white')

    # Build the main UI and get the chat log reference
    chat_log = build_ui(handle_user_input)

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
    voice_model_path = os.path.join(PROJECT_DIR, 'en_GB-semaine-medium.onnx')

    if not os.path.exists(config_path):
        print(f"{Fore.RED}[ERROR] Config file not found at: {config_path}{Style.RESET_ALL}")
        return False

    if not os.path.exists(api_key_path):
        print(f"{Fore.RED}[ERROR] API key file not found at: {api_key_path}{Style.RESET_ALL}")
        return False
        
    if not os.path.exists(voice_model_path):
        print(f"{Fore.RED}[ERROR] Voice model file not found at: {voice_model_path}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[INFO] Please ensure the Piper voice model is in the project root.{Style.RESET_ALL}")
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
    print(f"{Fore.YELLOW}Starting Darwin Chat Application with TTS")
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

    print(f"{Fore.GREEN}[MAIN] All systems ready. Starting web interface...{Style.RESET_ALL}")

    # Configure NiceGUI
    ui.run(
        title='Darwin Chat with TTS',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()