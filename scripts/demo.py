# simple_ui_display.py - Basic UI display with static video

from nicegui import ui
import os

# Base directory for video files - you can change this path
BASE_DIR = r"C:\Users\Jason\Documents\Projects\AvatarResurrection"
VIDEO_FILE = os.path.join(BASE_DIR, "avatars", "Darwin", "sample_video.mp4")  # Change this to your video file

def build_simple_ui():
    """Build a simple UI display without any functionality."""
    
    # Add CSS styling
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
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .video-placeholder {
            color: white;
            font-size: 24px;
            text-align: center;
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
        
        .q-field__native, .q-field__input, textarea {
            color: #000000 !important;
        }
        
        .q-field__label {
            color: #6b7280 !important;
        }
        
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
        
        /* Custom dropdown styling */
        .settings-dropdown {
            background: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
            border-radius: 8px !important;
            backdrop-filter: blur(10px) !important;
        }
        
        .settings-dropdown .q-field__control {
            height: 56px !important;
            min-height: 56px !important;
            max-height: 56px !important;
        }
        
        .settings-dropdown .q-field__native {
            color: white !important;
            font-size: 12px !important;
            line-height: 1.3 !important;
            padding: 12px 16px !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
        }
        
        .settings-dropdown .q-field__label {
            color: rgba(255, 255, 255, 0.7) !important;
            font-size: 14px !important;
        }
        
        .settings-dropdown .q-field__append {
            color: white !important;
        }
        
        /* Settings popup styling */
        .settings-popup {
            background: #1f2937 !important;
            color: white !important;
        }
        
        .settings-popup .q-field__native {
            color: white !important;
        }
        
        .settings-popup .q-field__label {
            color: rgba(255, 255, 255, 0.7) !important;
        }
        
        .settings-popup .q-select__dropdown .q-item {
            color: white !important;
        }
        
        .settings-popup input::placeholder {
            color: rgba(255, 255, 255, 0.5) !important;
        }
        
        .settings-popup .q-field__control {
            background: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
        }
        
        .settings-popup .text-gray-600 {
            color: rgba(255, 255, 255, 0.8) !important;
        }
        
        .settings-popup .q-tab {
            color: rgba(255, 255, 255, 0.7) !important;
        }
        
        .settings-popup .q-tab--active {
            color: white !important;
        }
    </style>
    ''')
    
    return ui.element('div').classes('main-layout')

def dummy_submit():
    """Dummy function for button clicks."""
    ui.notify("This is just a UI display - no functionality enabled", type='info')

def dummy_settings():
    """Dummy function for settings."""
    show_settings_popup()

def show_settings_popup():
    """Show the settings popup dialog."""
    with ui.dialog() as settings_dialog, ui.card().classes('w-full max-w-4xl p-6 settings-popup'):
        # Header
        with ui.row().classes('w-full items-center justify-between mb-6'):
            ui.label('Settings').classes('text-2xl font-bold')
            ui.button(icon='close', on_click=settings_dialog.close).props('flat round')
        
        # Settings content in tabs
        with ui.tabs().classes('w-full') as tabs:
            tab1 = ui.tab('General')
            tab2 = ui.tab('API Keys') 
            tab3 = ui.tab('Install Models')
        
        with ui.tab_panels(tabs, value=tab1).classes('w-full'):
            # General Tab
            with ui.tab_panel(tab1):
                with ui.column().classes('gap-4'):
                    ui.label('General Settings').classes('text-lg font-semibold mb-2')
                    
                    # Switch Avatar
                    with ui.row().classes('w-full items-center gap-4'):
                        ui.label('Switch Avatar:').classes('min-w-32')
                        ui.select(
                            options=['Charles Darwin', 'Dorothy Hodgkin'],
                            value='Charles Darwin',
                            label='Avatar'
                        ).classes('flex-1')
            
            # API Keys Tab
            with ui.tab_panel(tab2):
                with ui.column().classes('gap-4'):
                    ui.label('API Configuration').classes('text-lg font-semibold mb-2')
                    
                    # Groq API Key input
                    with ui.column().classes('gap-2'):
                        ui.label('Groq API Key:').classes('font-medium')
                        groq_input = ui.input(
                            placeholder='Enter your Groq API key...',
                            password=True,
                            password_toggle_button=True
                        ).classes('w-full')
                        
                        with ui.row().classes('w-full gap-2'):
                            ui.button('Save Key', on_click=dummy_submit).classes('bg-blue-600 text-white')
                            ui.button('Test Connection', on_click=dummy_submit).classes('bg-green-600 text-white')
                    
                    ui.separator()
                    
                    # Previously used keys
                    ui.label('Previously Used Keys:').classes('font-medium mt-4')
                    with ui.column().classes('gap-2 mt-2'):
                        # Sample censored key
                        with ui.row().classes('w-full items-center justify-between bg-gray-100 p-3 rounded'):
                            ui.label('gsk_••••••••••••••••••••••••••••••••••••••••••••7a2b').classes('font-mono text-sm')
                            with ui.row().classes('gap-2'):
                                ui.button('Use', on_click=dummy_submit).props('size=sm color=primary')
                                ui.button('Delete', on_click=dummy_submit).props('size=sm color=negative')
            
            # Install Models Tab
            with ui.tab_panel(tab3):
                with ui.column().classes('gap-6'):
                    ui.label('Install Models').classes('text-lg font-semibold mb-2')
                    
                    # Model installation cards
                    models = [
                        {
                            'name': 'Llama 3.1',
                            'description': 'Local LLM for offline processing',
                            'status': 'Not Installed',
                            'color': 'orange'
                        },
                        {
                            'name': 'SparkTTS',
                            'description': 'Advanced text-to-speech model',
                            'status': 'Not Installed', 
                            'color': 'blue'
                        },
                        {
                            'name': 'LivePortrait',
                            'description': 'Real-time lip-sync generation',
                            'status': 'Not Installed',
                            'color': 'purple'
                        }
                    ]
                    
                    for model in models:
                        with ui.card().classes('p-4'):
                            with ui.row().classes('w-full items-center justify-between'):
                                with ui.column().classes('gap-1'):
                                    ui.label(model['name']).classes('text-lg font-semibold text-white')
                                    ui.label(model['description']).classes('text-sm text-white opacity-80')
                                    ui.badge(model['status'], color=model['color']).classes('w-fit')
                                
                                with ui.column().classes('gap-2 items-end'):
                                    ui.button('Install', on_click=dummy_submit).classes('bg-green-600 text-white')
                                    ui.button('Details', on_click=dummy_submit).props('outline')
    
    settings_dialog.open()

@ui.page('/')
def index():
    """Main page with simple UI display."""
    
    ui.page_title('Chat with Charles Darwin - UI Display')

    # Header
    with ui.row().classes('w-full justify-between items-center p-4'):
        ui.label('Chat with Charles Darwin - Enhanced Avatar').classes('text-4xl font-bold text-white')
        ui.label('UI Display Mode').classes('text-sm text-white bg-blue-600 px-3 py-1 rounded')

    # Main layout
    with build_simple_ui():
        
        # LEFT SIDE - Video Player Area
        with ui.element('div').classes('video-section'):
            # Check if video file exists
            if os.path.exists(VIDEO_FILE):
                ui.html(f'''
                <video id="mainVideo" autoplay loop muted playsinline controls 
                    style="width: 100%; height: 100%; object-fit: contain;">
                    <source src="/static/video.mp4" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
                ''')
            else:
                with ui.element('div').classes('video-placeholder'):
                    ui.html('<i class="fas fa-video" style="font-size: 48px; margin-bottom: 16px;"></i>')
                    ui.label('Video Player Area').style('font-size: 18px;')
                    ui.label(f'Video not found: {VIDEO_FILE}').style('font-size: 12px; opacity: 0.7;')

        # RIGHT SIDE - Chat Interface
        with ui.element('div').classes('chat-section'):
            
            # Chat Messages Area
            chat_messages = ui.element('div').classes('chat-messages')
            
            # Input Area
            with ui.element('div').classes('input-area'):
                prompt_input = ui.textarea(
                    label='Your question for Darwin', 
                    placeholder='Ask Charles Darwin anything...'
                ).classes('w-full mb-4').style('min-height: 100px;')

                ui.button('Ask Darwin', on_click=dummy_submit).classes('w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg')

            # Settings Bar
            with ui.element('div').classes('settings-bar'):
                with ui.column().classes('w-full gap-3'):
                    # Volume Control Row
                    with ui.row().classes('w-full items-center justify-between'):
                        with ui.element('div').classes('volume-control'):
                            ui.html('<i class="fas fa-volume-up" style="color: white; font-size: 16px;"></i>')
                            ui.html('<input type="range" class="volume-slider" min="0" max="100" value="75">')
                            ui.label('75%').style('color: white; font-size: 14px; min-width: 30px;')
                        
                        ui.button(icon='settings', on_click=dummy_settings).props('flat').style('color: white;')
                    
                    # Settings Dropdowns Row
                    with ui.row().classes('w-full gap-4'):
                        # LLM Option
                        ui.select(
                            options=[
                                "Groq API",
                                "Local Llama 3.1"
                            ],
                            value="Groq API",
                            label='LLM'
                        ).classes('flex-1 settings-dropdown')
                        
                        # Voice Selector
                        ui.select(
                            options=[
                                "PiperTTS(Fast)",
                                "SparkTTS(Charles Darwin)",
                                "SparkTTS(Dorothy Hodgkin)"
                            ],
                            value="PiperTTS(Fast)",
                            label='Voice'
                        ).classes('flex-1 settings-dropdown')
                        
                        # Lipsync Module
                        ui.select(
                            options=[
                                "Simple",
                                "LivePortrait"
                            ],
                            value="Simple",
                            label='Lipsync'
                        ).classes('flex-1 settings-dropdown')

@ui.page('/settings')
def settings_page():
    """Simple settings page."""
    
    with ui.column().classes('w-full max-w-3xl mx-auto p-8 gap-6').style('min-height: 100vh; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);'):
        with ui.row().classes('w-full items-center justify-between mb-6'):
            ui.label('Voice Settings').classes('text-4xl font-bold text-white')
            ui.button('← Back to Chat', on_click=lambda: ui.navigate.to('/')).classes('bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg')
        
        with ui.card().classes('p-8 w-full'):
            ui.label('Choose Your Voice').classes('text-2xl font-semibold mb-6')
            
            voice_dropdown = ui.select(
                options=['en_GB-semaine-medium', 'en_US-amy-medium', 'en_US-ryan-high'],
                value='en_GB-semaine-medium',
                label='Voice Model'
            ).classes('w-full mb-6')
            
            ui.button('Apply Settings', on_click=dummy_submit).classes('w-full bg-green-600 hover:bg-green-700 text-white py-4 rounded-lg mt-6')

def main():
    """Main function to run the simple UI display."""
    print("Starting Simple UI Display...")
    print(f"Looking for video file at: {VIDEO_FILE}")
    
    if os.path.exists(VIDEO_FILE):
        print("Video file found - will be served statically")
        # Serve the video file statically
        ui.add_static_files('/static', os.path.dirname(VIDEO_FILE))
    else:
        print("Video file not found - will show placeholder")
    
    print("UI will be available at http://localhost:8080")
    
    ui.run(
        title='Darwin Chat UI Display',
        port=8080,
        show=True,
        reload=False,
        dark=None
    )

if __name__ == '__main__':
    main()