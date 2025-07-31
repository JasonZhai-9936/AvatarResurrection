# main.py - Simplified main application with working chat

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
chat_container = None
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

def add_message_to_chat(text: str, message_type: str):
    """Add a message to the chat container."""
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

def handle_user_input(user_text: str):
    """Handle user input, generate Darwin's response, update chat log, and stream TTS."""
    global chat_container, is_first_message, current_voice

    # Clear initial message on first input
    if is_first_message:
        chat_container.clear()
        is_first_message = False

    try:
        print(f"[MAIN] User asked: {user_text}")

        # Add user message
        add_message_to_chat(user_text, 'user')

        # Generate response
        print(f"{Fore.CYAN}[MAIN] Generating LLM response...{Style.RESET_ALL}")
        response = generate_darwin_response(user_text)
        print(f"[MAIN] Darwin responded: {response}")

        # Add Darwin's response
        add_message_to_chat(response, 'darwin')

        # Generate TTS in background
        def tts_thread():
            try:
                print(f"{Fore.MAGENTA}[MAIN] Starting TTS generation with voice: {current_voice}...{Style.RESET_ALL}")
                audio_file = generate_and_stream_audio(response)
                if audio_file:
                    print(f"{Fore.GREEN}[MAIN] TTS completed: {audio_file}{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}[MAIN] TTS generation failed.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[MAIN] TTS Error: {e}{Style.RESET_ALL}")

        tts_worker = threading.Thread(target=tts_thread, daemon=True)
        tts_worker.start()

    except Exception as e:
        print(f"[ERROR] Failed to generate response: {e}")
        add_message_to_chat('Sorry, Darwin is having trouble responding right now.', 'system')
        ui.notify("Error: Could not generate response", type='negative')

@ui.page('/')
def index():
    """Main page"""
    global chat_container

    ui.page_title('Chat with Charles Darwin')

    # Simple header
    with ui.row().classes('w-full justify-center p-4'):
        ui.label('Chat with Charles Darwin').classes('text-4xl font-bold text-white')

    # Build the main UI
    chat_container = build_ui(handle_user_input, handle_voice_change)

def check_dependencies():
    """Check if all required dependencies and files are available."""
    print(f"{Fore.CYAN}[MAIN] Checking dependencies...{Style.RESET_ALL}")
    
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py', 'TTS_Piper.py', 'ui.py']
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"{Fore.RED}[ERROR] Required file not found: {file_path}{Style.RESET_ALL}")
            return False

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
        print(f"{Fore.CYAN}[MAIN] Testing TTS system...{Style.RESET_ALL}")
        from TTS_Piper import test_tts_system
        if not test_tts_system():
            print(f"{Fore.RED}[ERROR] TTS system test failed.{Style.RESET_ALL}")
            return False
        print(f"{Fore.GREEN}[MAIN] TTS system test passed.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR] TTS system test error: {e}{Style.RESET_ALL}")
        return False

    print(f"{Fore.GREEN}[MAIN] All dependencies verified successfully.{Style.RESET_ALL}")
    return True

def main():
    """Main function to start the application"""
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}Starting Darwin Chat Application with TTS")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")
    print(f"[MAIN] Project directory: {PROJECT_DIR}")

    if not check_dependencies():
        print(f"{Fore.RED}[FATAL] Dependency check failed. Please fix the issues above.{Style.RESET_ALL}")
        return

    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    print(f"[MAIN] TTS temp directory: {temp_dir}")

    print(f"{Fore.GREEN}[MAIN] All systems ready. Starting web interface...{Style.RESET_ALL}")

    ui.run(
        title='Darwin Chat with TTS',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()