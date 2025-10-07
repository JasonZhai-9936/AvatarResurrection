# ui.py - UI with STREAMING text synchronized to video duration

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
    """Settings page for configuration options."""
    config = load_config()
    
    ui.add_head_html('''
    <style>
        body {
            background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
            margin: 0;
            padding: 0;
            color: #e2e8f0;
        }
        .settings-card {
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        .q-field__label {
            color: #94a3b8 !important;
        }
        .q-slider__track-container {
            background: #334155 !important;
        }
    </style>
    ''')
    
    with ui.column().classes('w-full max-w-2xl mx-auto p-8 gap-6'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Settings').classes('text-3xl font-bold text-white')
            ui.button('← Back to Chat', on_click=lambda: ui.navigate.to('/')).classes('bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700')
        
        with ui.card().classes('settings-card p-6 w-full').style('background: rgba(15, 23, 42, 0.95); color: #e2e8f0;'):
            ui.label('Configuration Options').classes('text-xl font-semibold mb-4 text-blue-400')
            
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.column():
                    ui.label('Enable RAG Search').classes('font-medium text-gray-200')
                    ui.label('Use Retrieval-Augmented Generation for enhanced responses').classes('text-sm text-gray-400')
                rag_switch = ui.switch(value=config.get('useRAG', False)).props('color="blue"')
            
            ui.separator().classes('bg-gray-700')
            
            with ui.row().classes('w-full items-center justify-between mb-4'):
                with ui.column():
                    ui.label('Use CUDA Acceleration').classes('font-medium text-gray-200')
                    ui.label('Enable GPU acceleration for faster TTS processing').classes('text-sm text-gray-400')
                cuda_switch = ui.switch(value=config.get('useCuda', True)).props('color="blue"')
            
            ui.separator().classes('bg-gray-700')
            
            with ui.column().classes('w-full mb-4'):
                ui.label('Maximum Words per Response').classes('font-medium mb-2 text-gray-200')
                max_words_slider = ui.slider(
                    min=10, max=200, step=10, value=config.get('maxWords', 50)
                ).props('label-always color="blue"')
                ui.label('Controls the length of Darwin\'s responses').classes('text-sm text-gray-400')
            
            ui.separator().classes('bg-gray-700')
            
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
            
            ui.button('Save Settings', on_click=save_settings).classes('w-full bg-blue-600 text-white py-3 rounded-lg mt-4 hover:bg-blue-700')

def build_ui(trigger_response_callback, voice_change_callback=None, video_manager=None):
    """Build the main UI with STREAMING text synchronized to video."""
    
    ui.add_head_html('''
    <style>
        body {
            background: #0a0f1c;
            color: #e2e8f0;
            margin: 0;
            padding: 0;
        }
        
        .q-field--outlined .q-field__control {
            background: rgba(15, 23, 42, 0.8) !important;
            border-color: rgba(59, 130, 246, 0.3) !important;
        }
        
        .q-field--outlined .q-field__control:hover {
            border-color: rgba(59, 130, 246, 0.5) !important;
        }
        
        .q-field--outlined.q-field--focused .q-field__control {
            border-color: #3b82f6 !important;
        }
        
        .q-field__label {
            color: #94a3b8 !important;
        }
        
        .q-field__native {
            color: #e2e8f0 !important;
        }
        
        .user-message {
            background: linear-gradient(135deg, #1e3a5f, #2563eb);
            color: white;
            border-radius: 12px;
            padding: 12px 16px;
            margin: 8px 0;
            max-width: 70%;
            word-wrap: break-word;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        }
        
        .darwin-message {
            background: rgba(30, 41, 59, 0.9);
            color: #e2e8f0;
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 12px;
            padding: 12px 16px;
            margin: 8px 0;
            max-width: 70%;
            word-wrap: break-word;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            min-height: 40px;
        }
        
        /* Streaming text cursor effect */
        .streaming-cursor::after {
            content: '▊';
            animation: blink 1s infinite;
            margin-left: 2px;
        }
        
        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
        }
        
        /* Character reveal animation */
        .char-reveal {
            display: inline-block;
            animation: charFadeIn 0.1s ease-in;
        }
        
        @keyframes charFadeIn {
            from { 
                opacity: 0;
                transform: translateY(5px);
            }
            to { 
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(15, 23, 42, 0.5);
        }
        
        ::-webkit-scrollbar-thumb {
            background: rgba(59, 130, 246, 0.5);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(59, 130, 246, 0.7);
        }
        
        .q-card {
            background: rgba(15, 23, 42, 0.95) !important;
            border: 1px solid rgba(59, 130, 246, 0.1);
        }
        
        .primary-button {
            background: linear-gradient(135deg, #2563eb, #3b82f6);
            color: white;
            border: none;
            transition: all 0.3s ease;
        }
        
        .primary-button:hover {
            background: linear-gradient(135deg, #3b82f6, #60a5fa);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }
    </style>
    ''')
    
    with ui.column().classes('w-full h-screen gap-0').style('background: #0a0f1c;'):
        with ui.row().classes('w-full flex-grow items-start justify-start gap-4 p-4'):
            
            # === LEFT VIDEO PLAYER ===
            with ui.column().classes('items-start shrink-0').style('width: 35%; height: auto;'):
                video_container = ui.card().classes('p-0 overflow-hidden').style('width: 100%; aspect-ratio: 3/2; background: #000; border: 1px solid rgba(59, 130, 246, 0.2); box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);')
                with video_container:
                    ui.html('''
                    <div id="main-video-container" style="width: 100%; height: 100%; position: relative;">
                        <video id="mainVideo" autoplay muted playsinline 
                            style="width: 100%; height: 100%; object-fit: contain;"
                            onended="notifyPythonVideoEnded()">
                            <source src="" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    ''').classes('w-full h-full')

            # === CENTER PANEL ===
            with ui.column().classes('items-center gap-4 h-full').style('width: 45%;'):
                # === CHAT LOG ===
                chat_log = ui.column().classes('w-full flex-grow p-4 gap-4 overflow-y-auto rounded-lg').style('background: rgba(15, 23, 42, 0.6); max-height: 60vh; border: 1px solid rgba(59, 130, 246, 0.1);')
                with chat_log:
                    with ui.row().classes('w-full justify-center'):
                        ui.label('Ready to chat with Darwin').classes('text-lg text-center').style('color: #64748b;')

                # === TEXT INPUT & BUTTON ===
                with ui.column().classes('items-center gap-4 w-full'):
                    prompt_input = ui.textarea(
                        label='Your question for Darwin', 
                        placeholder='Ask Charles Darwin anything...'
                    ).props('outlined dark').classes('w-full').style('min-height: 120px; font-size: 16px;')

                    def submit_prompt():
                        user_text = prompt_input.value
                        if user_text and user_text.strip():
                            trigger_response_callback(user_text)
                            prompt_input.value = ""
                        else:
                            ui.notify("Please enter a question first", color="warning")

                    ui.button('Ask Darwin', on_click=submit_prompt).classes('w-full text-lg py-3 px-6 rounded-lg primary-button').style('font-weight: 600;')

            # === RIGHT SIDEBAR ===
            with ui.column().classes('h-full').style('width: 250px; background: rgba(15, 23, 42, 0.95); border-left: 1px solid rgba(59, 130, 246, 0.1);'):
                with ui.row().classes('w-full items-center justify-between p-3').style('border-bottom: 1px solid rgba(59, 130, 246, 0.1);'):
                    ui.label('Menu').classes('font-semibold').style('color: #e2e8f0;')
                    ui.button(icon='menu', on_click=lambda: ui.notify('Sidebar toggle placeholder')).props('flat').style('color: #94a3b8;')

                with ui.column().classes('w-full p-3 gap-3'):
                    ui.button('🏠 Main Page', on_click=lambda: ui.navigate.to('/')).classes('w-full justify-start py-2 px-3 rounded').style('background: rgba(59, 130, 246, 0.1); color: #60a5fa;')
                    ui.button('⚙️ Settings', on_click=lambda: ui.navigate.to('/settings')).classes('w-full justify-start py-2 px-3 rounded').style('background: rgba(30, 41, 59, 0.5); color: #94a3b8;')
                    
                    ui.separator().style('background: rgba(59, 130, 246, 0.1);')
                    ui.label('System Status').classes('font-medium text-sm mt-4').style('color: #64748b;')
                    
                    video_status_label = ui.label('Status: Ready').classes('text-xs').style('color: #475569;')
                    state_label = ui.label('State: Idle').classes('text-xs').style('color: #475569;')
                    mode_label = ui.label('Mode: Waiting').classes('text-xs').style('color: #475569;')
                    
                    ui.space()
                    
                    ui.label('Configuration').classes('font-medium text-sm mt-4').style('color: #64748b;')
                    config = load_config()
                    ui.label(f"RAG: {'On' if config.get('useRAG') else 'Off'}").classes('text-xs').style('color: #475569;')
                    ui.label(f"Max Words: {config.get('maxWords', 50)}").classes('text-xs').style('color: #475569;')
                    ui.label(f"CUDA: {'On' if config.get('useCuda') else 'Off'}").classes('text-xs').style('color: #475569;')

        # === VOICE SELECTION ===
        ui.separator().style('background: rgba(59, 130, 246, 0.1);')
        
        with ui.row().classes('w-full p-4 items-center justify-center gap-8').style('background: rgba(15, 23, 42, 0.8); border-top: 1px solid rgba(59, 130, 246, 0.1);'):
            ui.label('Voice Selection').classes('text-lg font-semibold').style('color: #e2e8f0;')
            
            available_voices = get_available_voices()
            current_voice = available_voices[0] if available_voices else 'en_GB-semaine-medium'
            
            voice_dropdown = ui.select(
                options=available_voices,
                value=current_voice,
                label='Choose Voice Model'
            ).props('dark outlined').classes('min-w-64')
            
            def on_voice_change():
                selected_voice = voice_dropdown.value
                ui.notify(f'Voice changed to: {selected_voice}', type='info')
                if voice_change_callback:
                    voice_change_callback(selected_voice)
            
            voice_dropdown.on('update:model-value', on_voice_change)
            ui.label(f'Available voices: {len(available_voices)}').classes('text-sm').style('color: #64748b;')

    # === JAVASCRIPT with STREAMING TEXT SUPPORT ===
    ui.add_body_html('''
    <script>
    console.log('[UI] JavaScript with streaming text support initialized');
    
    // Video control - notify Python when video ends
    function notifyPythonVideoEnded() {
        console.log('[VIDEO] Video ended - notifying Python backend');
        fetch('/api/video-ended', { 
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        })
        .then(response => {
            if (response.ok) {
                console.log('[VIDEO] Python notified successfully');
            }
        })
        .catch(err => console.error('[VIDEO] Error notifying Python:', err));
    }
    
    // Simple video source update
    function updateVideoSource(videoUrl) {
        const video = document.getElementById('mainVideo');
        if (video && videoUrl) {
            console.log('[VIDEO] Updating video:', videoUrl);
            video.src = videoUrl;
            video.load();
            video.onended = notifyPythonVideoEnded;
        }
    }
    
    // STREAMING TEXT FUNCTION - Reveals text over video duration
    function streamText(elementId, fullText, durationSeconds) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error('[STREAM] Element not found:', elementId);
            return;
        }
        
        console.log('[STREAM] Starting text stream:', {
            length: fullText.length,
            duration: durationSeconds
        });
        
        // Calculate delay between characters
        const totalChars = fullText.length;
        const delayPerChar = (durationSeconds * 1000) / totalChars;
        
        // Clear element and add cursor class
        element.innerHTML = '';
        element.classList.add('streaming-cursor');
        
        let currentIndex = 0;
        
        const streamInterval = setInterval(() => {
            if (currentIndex < totalChars) {
                const char = fullText[currentIndex];
                const span = document.createElement('span');
                span.className = 'char-reveal';
                
                // Preserve spaces by using &nbsp; or actual space
                if (char === ' ') {
                    span.innerHTML = '&nbsp;';
                } else {
                    span.textContent = char;
                }
                
                element.appendChild(span);
                currentIndex++;
            } else {
                // Streaming complete - remove cursor
                clearInterval(streamInterval);
                element.classList.remove('streaming-cursor');
                console.log('[STREAM] Text streaming complete');
            }
        }, delayPerChar);
        
        // Store interval ID for potential cancellation
        element.dataset.streamInterval = streamInterval;
    }
    
    // Make functions globally available
    window.updateVideoSource = updateVideoSource;
    window.streamText = streamText;
    
    console.log('[UI] All functions ready');
    </script>
    ''')

    return {
        'chat_log': chat_log,
        'video_status_label': video_status_label if 'video_status_label' in locals() else None,
        'state_label': state_label if 'state_label' in locals() else None,
        'mode_label': mode_label if 'mode_label' in locals() else None,
    }