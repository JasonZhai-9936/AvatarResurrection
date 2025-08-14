# ui.py - Enhanced UI with integrated video management

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
                # Remove .onnx extension for display
                voice_name = file.replace('.onnx', '')
                voices.append(voice_name)
    
    return sorted(voices) if voices else ['en_GB-semaine-medium']

@ui.page('/settings')
def settings_page():
    """Settings page for configuration options."""
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
        with ui.card().classes('settings-card p-6 w-full'):
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

def build_ui(trigger_response_callback, voice_change_callback=None):
    """Build the main UI with enhanced video integration."""
    
    # Global reference to video manager (will be set by main.py)
    video_manager = None
    
    def set_video_manager(manager):
        nonlocal video_manager
        video_manager = manager
    
    with ui.column().classes('w-full h-screen gap-0'):
        # === MAIN CONTENT ROW ===
        with ui.row().classes('w-full flex-grow items-start justify-start gap-4 p-4'):
            
            # === LEFT VIDEO PLAYER (MAIN AVATAR) ===
            with ui.column().classes('items-start shrink-0').style('width: 35%; height: 100%;'):
                video_container = ui.card().classes('p-0 overflow-hidden').style('width: 100%; aspect-ratio: 2/3; background: black;')
                with video_container:
                    ui.html('''
                    <div id="main-video-container" style="width: 100%; height: 100%; position: relative;">
                        <video id="mainVideo" autoplay muted playsinline 
                            style="width: 100%; height: 100%; object-fit: contain;"
                            onended="handleVideoEnded()">
                            <source src="" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                        <div id="video-status" style="position: absolute; top: 10px; left: 10px; 
                             background: rgba(0,0,0,0.7); color: white; padding: 5px 10px; 
                             border-radius: 5px; font-size: 12px; z-index: 10;">
                            Initializing...
                        </div>
                    </div>
                    ''').classes('w-full h-full')

            # === CENTER PANEL ===
            with ui.column().classes('items-center gap-4 h-full').style('width: 45%;'):
                # === BACKGROUND VIDEO PLAYER ===
                background_container = ui.card().classes('p-0 overflow-hidden').style('width: 100%; aspect-ratio: 16/9; background: black;')
                with background_container:
                    ui.html('''
                    <div id="background-video-container" style="width: 100%; height: 100%; position: relative;">
                        <video id="backgroundVideo" autoplay muted loop
                            style="width: 100%; height: 100%; object-fit: cover;">
                            <source src="" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    ''').classes('w-full h-full')

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
                            # Notify video manager about user input
                            if video_manager:
                                video_manager.prepare_for_user_input()
                            
                            # Trigger the main response callback
                            trigger_response_callback(user_text)
                            prompt_input.value = ""
                        else:
                            ui.notify("Please enter a question first", color="warning")

                    ui.button('Ask Darwin', on_click=submit_prompt).classes('w-full text-lg py-3 px-6 rounded-lg').style('background-color: #2563eb; color: white;')

            # === RIGHT SIDEBAR ===
            with ui.column().classes('h-full bg-gray-100 border-l border-gray-300').style('width: 250px;'):
                # Sidebar Header
                with ui.row().classes('w-full items-center justify-between p-3 border-b border-gray-300'):
                    ui.label('Menu').classes('font-semibold text-gray-700')
                    ui.button(icon='menu', on_click=lambda: ui.notify('Sidebar toggle placeholder')).props('flat').classes('text-gray-600')

                # Sidebar Content
                with ui.column().classes('w-full p-3 gap-3'):
                    # Main Page Button
                    ui.button('🏠 Main Page', on_click=lambda: ui.navigate.to('/')).classes('w-full justify-start bg-blue-100 text-blue-800 py-2 px-3 rounded')
                    
                    # Settings Button
                    ui.button('⚙️ Settings', on_click=lambda: ui.navigate.to('/settings')).classes('w-full justify-start bg-gray-200 text-gray-700 py-2 px-3 rounded')
                    
                    # Video Controls Section
                    ui.separator()
                    ui.label('Video Controls').classes('font-medium text-gray-600 text-sm mt-4')
                    
                    # Video status display
                    video_status_label = ui.label('Status: Initializing...').classes('text-xs text-gray-500')
                    state_label = ui.label('State: Unknown').classes('text-xs text-gray-500')
                    mode_label = ui.label('Mode: Unknown').classes('text-xs text-gray-500')
                    
                    # Spacer
                    ui.space()
                    
                    # Quick Info
                    ui.label('Quick Info').classes('font-medium text-gray-600 text-sm mt-4')
                    config = load_config()
                    ui.label(f"RAG: {'On' if config.get('useRAG') else 'Off'}").classes('text-xs text-gray-500')
                    ui.label(f"Max Words: {config.get('maxWords', 50)}").classes('text-xs text-gray-500')
                    ui.label(f"CUDA: {'On' if config.get('useCuda') else 'Off'}").classes('text-xs text-gray-500')

        # === VOICE SELECTION SECTION ===
        ui.separator().classes('w-full')
        
        with ui.row().classes('w-full p-4 bg-gray-50 border-t border-gray-200 items-center justify-center gap-8'):
            ui.label('Voice Selection').classes('text-lg font-semibold text-gray-700')
            
            # Get available voices
            available_voices = get_available_voices()
            current_voice = available_voices[0] if available_voices else 'en_GB-semaine-medium'
            
            voice_dropdown = ui.select(
                options=available_voices,
                value=current_voice,
                label='Choose Voice Model'
            ).classes('min-w-64')
            
            def on_voice_change():
                selected_voice = voice_dropdown.value
                ui.notify(f'Voice changed to: {selected_voice}', type='info')
                if voice_change_callback:
                    voice_change_callback(selected_voice)
            
            voice_dropdown.on('update:model-value', on_voice_change)
            
            # Voice info
            ui.label(f'Available voices: {len(available_voices)}').classes('text-sm text-gray-500')

    # Add enhanced JavaScript with video management
    ui.add_body_html('''
    <script>
    let videoManager = {
        currentVideo: null,
        statusDisplay: null,
        isReady: false
    };

    // Video ended handler - communicates with Python backend
    function handleVideoEnded() {
        console.log('[VIDEO] Video ended, requesting next clip');
        if (window.videoEndedCallback) {
            window.videoEndedCallback();
        }
    }

    // Update video source
    function updateMainVideo(videoUrl) {
        const video = document.getElementById('mainVideo');
        const statusDiv = document.getElementById('video-status');
        
        if (video && videoUrl) {
            console.log('[VIDEO] Loading new video:', videoUrl);
            
            if (statusDiv) {
                statusDiv.textContent = 'Loading...';
            }
            
            video.src = videoUrl;
            video.load();
            
            video.onloadstart = function() {
                if (statusDiv) statusDiv.textContent = 'Loading...';
            };
            
            video.oncanplay = function() {
                if (statusDiv) statusDiv.textContent = 'Ready';
                console.log('[VIDEO] Video ready to play');
            };
            
            video.onplay = function() {
                if (statusDiv) statusDiv.textContent = 'Playing';
                console.log('[VIDEO] Video started playing');
            };
            
            video.onerror = function(e) {
                console.error('[VIDEO] Error loading video:', e);
                if (statusDiv) statusDiv.textContent = 'Error';
            };
        }
    }

    // Update video status display
    function updateVideoStatus(status) {
        const elements = {
            'video-status': `Status: ${status.is_playing ? 'Playing' : 'Stopped'}`,
            'state-display': `State: ${status.current_state}`,
            'mode-display': `Mode: ${status.current_mode}`
        };
        
        Object.entries(elements).forEach(([id, text]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = text;
        });
    }

    // Update status displays in sidebar
    function updateSidebarStatus(status) {
        // This would update the sidebar labels - implementation depends on NiceGUI structure
        console.log('[UI] Status update:', status);
    }

    // Initialize when page loads
    window.addEventListener('load', function() {
        console.log('[UI] Darwin Chat UI with video management loaded');
        videoManager.isReady = true;
        
        // Set up global functions for Python callback
        window.updateMainVideo = updateMainVideo;
        window.updateVideoStatus = updateVideoStatus;
        window.updateSidebarStatus = updateSidebarStatus;
        
        // Function to load background videos
        window.loadBackgroundVideo = function(source) {
            const video = document.getElementById('backgroundVideo');
            if (video && source) {
                video.src = source;
                video.load();
            }
        };
        
        console.log('[UI] Video management system ready');
    });
    </script>
    ''')

    # Return necessary references for main.py
    return {
        'chat_log': chat_log,
        'set_video_manager': set_video_manager,
        'video_status_label': video_status_label if 'video_status_label' in locals() else None,
        'state_label': state_label if 'state_label' in locals() else None,
        'mode_label': mode_label if 'mode_label' in locals() else None
    }