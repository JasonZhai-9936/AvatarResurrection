# main.py - Main application launcher

import sys
import os

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

from nicegui import ui
from ui import build_ui
from LLM_Groq import generate_darwin_response

# Global references for UI elements that need to be updated
chat_log = None
is_first_message = True # Used to clear the initial "Ready" message

def handle_user_input(user_text: str):
    """Handle user input, generate Darwin's response, and update the chat log."""
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
        response = generate_darwin_response(user_text)
        print(f"[MAIN] Darwin responded: {response}")

        # Add Darwin's response to the chat log
        with chat_log:
            ui.chat_message(text=response, name='Darwin', sent=False)

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

def main():
    """Main function to start the application"""
    print("[MAIN] Starting Darwin Chat Application...")
    print(f"[MAIN] Project directory: {PROJECT_DIR}")

    # Check if required files exist in scripts directory (current directory)
    scripts_dir = os.path.dirname(__file__)
    required_files = ['LLM_Groq.py']
    for file in required_files:
        file_path = os.path.join(scripts_dir, file)
        if not os.path.exists(file_path):
            print(f"[ERROR] Required file not found: {file_path}")
            return

    # Check if config files exist in project directory
    config_path = os.path.join(PROJECT_DIR, 'config.json')
    api_key_path = os.path.join(PROJECT_DIR, 'groq_api_key.txt')

    if not os.path.exists(config_path):
        print(f"[WARNING] Config file not found at: {config_path}")

    if not os.path.exists(api_key_path):
        print(f"[ERROR] API key file not found at: {api_key_path}")
        return

    print("[MAIN] All required files found. Starting UI...")

    # Configure NiceGUI
    ui.run(
        title='Darwin Chat',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()