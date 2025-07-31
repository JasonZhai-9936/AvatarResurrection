# ui.py - Simplified UI with working chat messages

from nicegui import ui
import os
import json

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

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

def get_available_voices():
    """Get list of available voice models from Piper_Voices directory."""
    voices_dir = os.path.join(PROJECT_DIR, "Piper_Voices")
    voices = []
    
    if os.path.exists(voices_dir):
        for file in os.listdir(voices_dir):
            if file.endswith('.onnx'):
                voice_name = file.replace('.onnx', '')
                voices.append(voice_name)
    
    return sorted(voices) if voices else ['en_GB-semaine-medium']

@ui.page('/settings')
def settings_page():
    """Modern settings page for voice configuration."""
    
    ui.add_head_html('''
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
        }
    </style>
    ''')
    
    with ui.column().classes('w-full max-w-3xl mx-auto p-8 gap-6').style('min-height: 100vh;'):
        with ui.row().classes('w-full items-center justify-between mb-6'):
            ui.label('Voice Settings').classes('text-4xl font-bold text-white')
            ui.button('← Back to Chat', on_click=lambda: ui.navigate.to('/')).classes('bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg')
        
        with ui.card().classes('p-8 w-full'):
            ui.label('Choose Your Voice').classes('text-2xl font-semibold mb-6')
            
            available_voices = get_available_voices()
            current_voice = available_voices[0] if available_voices else 'en_GB-semaine-medium'
            
            voice_dropdown = ui.select(
                options=available_voices,
                value=current_voice,
                label='Voice Model'
            ).classes('w-full mb-6')
            
            def apply_voice_settings():
                selected_voice = voice_dropdown.value
                ui.notify(f'Voice set to: {selected_voice}', type='positive')
            
            ui.button('Apply Settings', on_click=apply_voice_settings).classes('w-full bg-green-600 hover:bg-green-700 text-white py-4 rounded-lg mt-6')

def build_ui(trigger_response_callback, voice_change_callback=None):
    """Build the UI with working chat interface."""
    
    # Minimal CSS that doesn't interfere with NiceGUI
    ui.add_head_html('''
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
        }
        
        .main-layout {
            display: flex;
            height: 100vh;
            padding: 20px;
            gap: 20px;
            box-sizing: border-box;
        }
        
        .video-section {
            flex: 1;
            background: black;
            border-radius: 12px;
            overflow: hidden;
        }
        
        .chat-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        
        .chat-messages {
            flex: 1;
            background: white;
            border-radius: 12px;
            padding: 20px;
            overflow-y: auto;
            min-height: 400px;
        }
        
        .input-area {
            background: white;
            border-radius: 12px;
            padding: 20px;
        }
        
        .settings-bar {
            background: rgba(30, 41, 59, 0.9);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: white;
        }
        
        .message-item {
            margin: 10px 0;
            padding: 12px 16px;
            border-radius: 18px;
            max-width: 70%;
            word-wrap: break-word;
            display: block;
        }
        
        .user-message {
            background: #3b82f6;
            color: white;
            margin-left: auto;
            margin-right: 0;
            text-align: right;
            width: fit-content;
            max-width: 70%;
        }
        
        .darwin-message {
            background: #10b981;
            color: white;
            margin-right: auto;
            margin-left: 0;
            width: fit-content;
            max-width: 70%;
        }
        
        .system-message {
            background: #f1f5f9;
            color: #374151;
            text-align: center;
            margin: 0 auto;
            width: fit-content;
        }
        
        /* Input text styling - make text black */
        .q-field__native, .q-field__input, textarea {
            color: #000000 !important;
        }
        
        .q-field__label {
            color: #6b7280 !important;
        }
        
        /* Volume slider styling */
        .volume-control {
            display: flex;
            align-items: center;
            gap: 12px;
            flex: 1;
        }
        
        .volume-slider {
            flex: 1;
            max-width: 120px;
            height: 4px;
            background: #64748b;
            border-radius: 2px;
            outline: none;
            -webkit-appearance: none;
            appearance: none;
        }
        
        .volume-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 16px;
            height: 16px;
            background: #3b82f6;
            border-radius: 50%;
            cursor: pointer;
        }
        
        .volume-slider::-moz-range-thumb {
            width: 16px;
            height: 16px;
            background: #3b82f6;
            border-radius: 50%;
            cursor: pointer;
            border: none;
        }
    </style>
    ''')
    
    with ui.element('div').classes('main-layout'):
        
        # LEFT SIDE - Video Player
        with ui.element('div').classes('video-section'):
            ui.html('''
            <video id="mainVideo" autoplay playsinline controls 
                style="width: 100%; height: 100%; object-fit: contain;">
                <source src="" type="video/mp4">
                Your browser does not support the video tag.
            </video>
            ''')

        # RIGHT SIDE - Chat Interface
        with ui.element('div').classes('chat-section'):
            
            # Chat Messages Area
            chat_container = ui.element('div').classes('chat-messages')
            with chat_container:
                ui.element('div').classes('message-item system-message').add_slot('default', 'Ready to chat with Darwin')
            
            # Input Area
            with ui.element('div').classes('input-area'):
                prompt_input = ui.textarea(
                    label='Your question for Darwin', 
                    placeholder='Ask Charles Darwin anything...'
                ).classes('w-full mb-4').style('min-height: 100px;')

                def submit_prompt():
                    user_text = prompt_input.value
                    if user_text and user_text.strip():
                        trigger_response_callback(user_text.strip())
                        prompt_input.value = ""
                    else:
                        ui.notify("Please enter a question first", color="warning")

                ui.button('Ask Darwin', on_click=submit_prompt).classes('w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg')

            # Settings Bar
            with ui.element('div').classes('settings-bar'):
                with ui.element('div').classes('volume-control'):
                    ui.html('<i class="fas fa-volume-up" style="color: white; font-size: 16px;"></i>')
                    ui.html('<input type="range" class="volume-slider" min="0" max="100" value="75">')
                    ui.label('75%').style('color: white; font-size: 14px; min-width: 30px;')
                
                ui.button(icon='settings', on_click=lambda: ui.navigate.to('/settings')).props('flat').style('color: white;')

    # Simple JavaScript
    ui.add_body_html('''
    <script>
        window.loadVideo = function(videoId, source) {
            const video = document.getElementById(videoId);
            if (video && source) {
                video.src = source;
                video.load();
            }
        };
    </script>
    ''')

    return chat_container