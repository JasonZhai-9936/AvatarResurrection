# enhanced_ui.py - Clean UI with no-controls video player

from nicegui import ui
import os
import json

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

def build_ui(trigger_response_callback, voice_change_callback=None):
    """Build the UI with enhanced no-controls video player"""
    
    # CSS styling
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
            position: relative;
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
        
        /* Video styling - no controls, no interaction */
        #mainVideo {
            width: 100% !important;
            height: 100% !important;
            object-fit: contain !important;
            pointer-events: none !important;
            user-select: none !important;
            outline: none !important;
            border: none !important;
            background: black;
        }
        
        /* Hide all browser video controls */
        #mainVideo::-webkit-media-controls {
            display: none !important;
        }
        
        #mainVideo::-webkit-media-controls-panel {
            display: none !important;
        }
        
        /* Input text styling */
        .q-field__native, .q-field__input, textarea {
            color: #000000 !important;
        }
        
        .q-field__label {
            color: #6b7280 !important;
        }
    </style>
    ''')
    
    with ui.element('div').classes('main-layout'):
        
        # LEFT SIDE - Video Player (No Controls)
        with ui.element('div').classes('video-section'):
            ui.html('''
            <video id="mainVideo" 
                   autoplay 
                   muted="false"
                   playsinline 
                   disablepictureinpicture
                   style="width: 100%; height: 100%; object-fit: contain;">
                <source src="" type="video/mp4">
                Your browser does not support the video tag.
            </video>
            ''')

        # RIGHT SIDE - Chat Interface
        with ui.element('div').classes('chat-section'):
            
            # Chat Messages
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
                ui.label('Darwin Avatar System').style('color: white; font-weight: bold;')
                ui.button(icon='settings', on_click=lambda: ui.navigate.to('/settings')).props('flat').style('color: white;')

    # JavaScript for video control and autoplay
    ui.add_body_html('''
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Setting up video player...');
            
            const video = document.getElementById('mainVideo');
            if (video) {
                // Configure video element
                video.removeAttribute('controls');
                video.setAttribute('autoplay', 'true');
                video.setAttribute('playsinline', 'true');
                video.muted = false;  // Allow audio
                
                // Disable all interactions
                video.addEventListener('click', function(e) { e.preventDefault(); });
                video.addEventListener('dblclick', function(e) { e.preventDefault(); });
                video.addEventListener('contextmenu', function(e) { e.preventDefault(); });
                video.addEventListener('keydown', function(e) { e.preventDefault(); });
                
                // Global autoplay enforcement
                video.addEventListener('loadstart', function() {
                    console.log('Video loadstart - preparing autoplay');
                });
                
                video.addEventListener('loadeddata', function() {
                    console.log('Video loadeddata - forcing play');
                    this.currentTime = 0;  // Ensure start from beginning
                    this.play().catch(e => {
                        console.log('Loadeddata play failed:', e);
                        // Try again after short delay
                        setTimeout(() => {
                            this.play().catch(e2 => console.log('Retry also failed:', e2));
                        }, 200);
                    });
                });
                
                video.addEventListener('canplaythrough', function() {
                    console.log('Video canplaythrough - ensuring playback');
                    if (this.paused) {
                        this.play().catch(e => console.log('Canplaythrough play failed:', e));
                    }
                });
                
                // Monitor playback state
                video.addEventListener('playing', function() {
                    console.log('✓ Video is playing');
                });
                
                video.addEventListener('pause', function() {
                    console.log('⚠ Video paused - attempting to resume');
                    this.play().catch(e => console.log('Resume failed:', e));
                });
                
                video.addEventListener('ended', function() {
                    console.log('✓ Video ended normally');
                });
                
                video.addEventListener('error', function(e) {
                    console.error('✗ Video error:', this.error);
                });
                
                console.log('✓ Video player configured with enhanced autoplay');
            } else {
                console.error('✗ Video element not found during setup');
            }
        });
        
        // Disable spacebar for video control globally
        document.addEventListener('keydown', function(e) {
            if (e.code === 'Space' && document.activeElement.tagName !== 'TEXTAREA') {
                e.preventDefault();
                console.log('Spacebar blocked');
            }
        });
        
        console.log('✓ Video control system initialized');
    </script>
    ''')

    return chat_container