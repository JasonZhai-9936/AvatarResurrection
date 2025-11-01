# ui.py - UI with TYPING INDICATOR and streaming text
# FIXED: Proper aspect ratio handling for FLOAT 1:1 videos

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
    """Build the main UI with TYPING INDICATOR and streaming text."""
    
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
        
        /* ===== UNIFIED CHAT MESSAGE SYSTEM ===== */
        
        /* Chat Message Wrappers - Control alignment and positioning */
        .chat-message-wrapper {
            width: 100% !important;
            display: flex !important;
            margin: 8px 0 !important;
            padding: 0 16px !important;
            clear: both !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
        }
        
        .user-wrapper {
            justify-content: flex-end !important;
            align-items: flex-end !important;
            flex-direction: row !important;
        }
        
        .darwin-wrapper {
            justify-content: flex-start !important;
            align-items: flex-start !important;
            flex-direction: row !important;
        }
        
        .system-wrapper {
            justify-content: center;  /* Center system messages */
        }
        
        /* Message Bubbles - Control sizing and appearance */
        .message-bubble {
            display: block;  /* Changed from inline-block */
            max-width: 70%;
            min-width: 200px;
            width: fit-content;  /* Shrink to content size */
            padding: 12px 16px;
            border-radius: 12px;
            word-wrap: break-word;
            overflow-wrap: break-word;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            white-space: pre-wrap;  /* Preserve line breaks and wrap text */
        }
        
        /* Darwin messages get consistent starting width */
        .darwin-bubble {
            background: rgba(30, 41, 59, 0.9);
            color: #e2e8f0;
            border: 1px solid rgba(59, 130, 246, 0.2);
            min-height: 40px;
            min-width: 300px;  /* Wider minimum for consistency */
        }
        
        /* User bubble styling */
        .user-bubble {
            background: linear-gradient(135deg, #1e3a5f, #2563eb);
            color: white;
            min-width: 100px;  /* Smaller min for short messages */
        }
        
        /* Darwin bubble styling */
        .darwin-bubble {
            background: rgba(30, 41, 59, 0.9);
            color: #e2e8f0;
            border: 1px solid rgba(59, 130, 246, 0.2);
            min-height: 40px;
        }
        
        /* Typing indicator bubble */
        .typing-bubble {
            background: rgba(30, 41, 59, 0.9);
            border: 1px solid rgba(59, 130, 246, 0.2);
            padding: 12px 20px;
            min-width: 80px;
        }
        
        .typing-dots {
            color: #94a3b8;
            font-style: italic;
        }
        
        /* Error bubble styling */
        .error-bubble {
            background: rgba(239, 68, 68, 0.2);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }
        
        /* System message bubble */
        .system-bubble {
            background: rgba(100, 116, 139, 0.2);
            color: #cbd5e1;
            border: 1px solid rgba(100, 116, 139, 0.3);
            text-align: center;
            font-size: 0.9em;
        }
        
        /* Legacy class support (for backward compatibility) */
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
        
        .primary-button {
            background: linear-gradient(135deg, #2563eb, #1e40af);
            transition: all 0.3s ease;
        }
        
        .primary-button:hover {
            background: linear-gradient(135deg, #1d4ed8, #1e3a8a);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
        }
    </style>
    ''')
    
    with ui.column().classes('w-full h-screen gap-0').style('background: #0a0f1c;'):
        with ui.row().classes('w-full flex-grow items-start justify-start gap-4 p-4'):
            
            # === LEFT VIDEO PLAYER (FIXED FOR 1:1 ASPECT RATIO) ===
            with ui.column().classes('items-start shrink-0').style('width: 35%; height: auto;'):
                # CRITICAL FIX: Use aspect-ratio: 1/1 AND object-fit: contain
                video_container = ui.card().classes('p-0 overflow-hidden').style(
                    'width: 100%; aspect-ratio: 1/1; background: #000; '
                    'border: 1px solid rgba(59, 130, 246, 0.2); '
                    'box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);'
                )
                with video_container:
                    ui.html('''
                    <div id="main-video-container" style="width: 100%; height: 100%; position: relative; background: #000;">
                        <video id="mainVideo" autoplay muted playsinline 
                            style="width: 100%; height: 100%; object-fit: contain; background: #000;"
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

                    async def submit_prompt():
                        user_text = prompt_input.value
                        if user_text and user_text.strip():
                            await trigger_response_callback(user_text)
                            prompt_input.value = ""
                        else:
                            ui.notify("Please enter a question first", color="warning")

                    ui.button('Ask Darwin', on_click=submit_prompt).classes('w-full text-lg py-3 px-6 rounded-lg primary-button').style('font-weight: 600;')
                    
                    # Clear chat button
                    def clear_chat():
                        chat_log.clear()
                        with chat_log:
                            with ui.row().classes('w-full justify-center'):
                                ui.label('Chat cleared - Ready for new conversation').classes('text-lg text-center').style('color: #64748b;')
                        ui.notify('Chat history cleared', type='info')
                    
                    ui.button('🗑️ Clear Chat', on_click=clear_chat).classes('w-full text-sm py-2 px-4 rounded-lg').style('background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); font-weight: 500;')

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

    # === JAVASCRIPT with TYPING INDICATOR & STREAMING TEXT ===
    ui.add_body_html('''
    <script>
    console.log('[UI] JavaScript with typing indicator initialized');
    
    // Typing indicator state
    const typingIntervals = {};
    
    // Start typing indicator animation
    window.startTypingIndicator = function(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error('[TYPING] Element not found:', elementId);
            return;
        }
        
        // Stop any existing interval
        if (typingIntervals[elementId]) {
            clearInterval(typingIntervals[elementId]);
        }
        
        let dots = 0;
        element.innerHTML = '<span style="color: #94a3b8;">typing</span>';
        
        typingIntervals[elementId] = setInterval(() => {
            dots = (dots + 1) % 4;
            const dotString = '.'.repeat(dots);
            element.innerHTML = `<span style="color: #94a3b8;">typing${dotString}</span>`;
        }, 400);
        
        console.log('[TYPING] Started indicator for:', elementId);
    }
    
    // Stop typing indicator
    window.stopTypingIndicator = function(elementId) {
        if (typingIntervals[elementId]) {
            clearInterval(typingIntervals[elementId]);
            delete typingIntervals[elementId];
            const element = document.getElementById(elementId);
            if (element) {
                element.innerHTML = ''; // Clear typing text
            }
            console.log('[TYPING] Stopped indicator for:', elementId);
        }
    }
    
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
    window.updateVideoSource = function(videoUrl) {
        const video = document.getElementById('mainVideo');
        if (video && videoUrl) {
            console.log('[VIDEO] Updating video:', videoUrl);
            video.src = videoUrl;
            video.load();
            video.onended = notifyPythonVideoEnded;
        }
    }
    
    // STREAMING TEXT FUNCTION - Reveals text over video duration
    window.streamText = function(elementId, fullText, durationSeconds) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error('[STREAM] Element not found:', elementId);
            return;
        }
        
        // Stop typing indicator first
        window.stopTypingIndicator(elementId);
        
        console.log('[STREAM] Starting text stream:', {
            length: fullText.length,
            duration: durationSeconds
        });
        
        // Set initial space to establish width
        element.textContent = fullText;
        element.style.visibility = 'hidden';
        const initialWidth = element.offsetWidth;
        element.style.width = initialWidth + 'px';
        element.style.visibility = 'visible';
        element.textContent = '';
        
        // Calculate delay between characters
        const totalChars = fullText.length;
        const delayPerChar = (durationSeconds * 1000) / totalChars;
        
        // Add cursor class
        element.classList.add('streaming-cursor');
        
        let currentIndex = 0;
        let displayedText = '';
        
        const streamInterval = setInterval(() => {
            if (currentIndex < totalChars) {
                const char = fullText[currentIndex];
                displayedText += char;
                
                // Update the entire text at once (no individual spans)
                element.textContent = displayedText;
                
                currentIndex++;
            } else {
                // Streaming complete - remove cursor and width constraint
                clearInterval(streamInterval);
                element.classList.remove('streaming-cursor');
                element.style.width = 'fit-content';
                console.log('[STREAM] Text streaming complete');
            }
        }, delayPerChar);
        
        // Store interval ID
        element.dataset.streamInterval = streamInterval;
    }
    
    console.log('[UI] All functions ready');
    </script>
    ''')

    return {
        'chat_log': chat_log,
        'video_status_label': video_status_label if 'video_status_label' in locals() else None,
        'state_label': state_label if 'state_label' in locals() else None,
        'mode_label': mode_label if 'mode_label' in locals() else None,
    }