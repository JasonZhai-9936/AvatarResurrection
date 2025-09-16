# simple_video_player.py - Simple single video player with Darwin UI

import os
from nicegui import ui, app

# Set project directory (adjust this path to your project)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Path to your video file - change this to the video you want to play
VIDEO_PATH = r"C:\Users\Jason\Downloads\presentation\full_sora_demo.mp4"

@ui.page('/')
def index():
    """Simple video player page with Darwin UI styling"""
    
    # Set page title
    ui.page_title('Darwin Video Player - Simple')

    # Modern tech theme CSS (same as main app)
    ui.add_head_html('''
    <style>
        body {
            background: #1a1a2e;
            margin: 0;
            padding: 0;
            color: #e2e8f0;
        }
        
        .nicegui-content {
            background: transparent !important;
        }

        /* Card styling for modern look */
        .q-card {
            background: rgba(30, 41, 59, 0.8) !important;
            border: 1px solid rgba(100, 116, 139, 0.2) !important;
            backdrop-filter: blur(10px) !important;
        }

        /* Modern text styling */
        .q-field__native,
        .q-field__input,
        textarea {
            color: #e2e8f0 !important;
            background-color: rgba(30, 41, 59, 0.8) !important;
            border-radius: 8px !important;
        }
        
        .q-field__label {
            color: #94a3b8 !important;
        }
        
        .q-field--outlined .q-field__control {
            background: rgba(30, 41, 59, 0.6) !important;
            border: 1px solid rgba(100, 116, 139, 0.3) !important;
            border-radius: 8px !important;
        }
        
        .q-field--outlined.q-field--focused .q-field__control {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
        }
        
        /* Button styling */
        .q-btn {
            text-transform: none !important;
            font-weight: 500 !important;
        }
        
        /* Volume slider styling */
        .volume-slider {
            background: rgba(30, 41, 59, 0.8) !important;
            border: 1px solid rgba(100, 116, 139, 0.2) !important;
            border-radius: 12px !important;
            padding: 16px !important;
            margin: 8px 0 !important;
            backdrop-filter: blur(10px) !important;
        }
        
        .volume-slider .q-slider__track {
            background: rgba(100, 116, 139, 0.3) !important;
        }
        
        .volume-slider .q-slider__track-container--h .q-slider__selection {
            background: linear-gradient(90deg, #3b82f6 0%, #1d4ed8 100%) !important;
        }
        
        /* Sidebar styling */
        .q-separator {
            background: rgba(100, 116, 139, 0.3) !important;
        }
        
        /* Chat log area */
        .chat-area {
            background: rgba(15, 23, 42, 0.6) !important;
            border: 1px solid rgba(100, 116, 139, 0.2) !important;
            backdrop-filter: blur(5px) !important;
        }
        
        /* Scrollbar styling for webkit browsers */
        ::-webkit-scrollbar {
            width: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(30, 41, 59, 0.3);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: rgba(100, 116, 139, 0.5);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(100, 116, 139, 0.7);
        }
        
        /* Selection styling */
        ::selection {
            background: rgba(59, 130, 246, 0.3) !important;
            color: #e2e8f0 !important;
        }
    </style>
    ''')

    # Header with modern styling
    with ui.row().classes('w-full justify-center p-6'):
        ui.label('Darwin Video Player - Simple').classes('text-4xl font-bold').style('color: #f1f5f9; text-shadow: 0 2px 10px rgba(0,0,0,0.3);')

    # === MAIN CONTENT ROW ===
    with ui.row().classes('w-full flex-grow items-start justify-start gap-4 p-4').style('height: calc(100vh - 180px);'):
        
        # === LEFT VIDEO PLAYER (MAIN AVATAR) ===
        with ui.column().classes('items-start shrink-0').style('width: 35%; height: 100%;'):
            with ui.card().classes('p-0 main-video-container').style('width: 100%; aspect-ratio: 2/3; max-height: 80vh; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(100, 116, 139, 0.3);'):
                
                # Create the video element
                main_video = ui.video(
                    src=VIDEO_PATH,
                    autoplay=True,
                    muted=False,  # Unmuted for this simple player
                    loop=True,    # Loop the single video
                    controls=True # Show controls for manual control
                ).classes('w-full h-full').style('object-fit: contain;')

            # Add Volume Slider below video with modern styling
            with ui.card().classes('volume-slider w-full mt-3'):
                ui.label('🔊 Volume').classes('text-sm font-medium mb-2').style('color: #e2e8f0;')
                volume_slider = ui.slider(
                    min=0, max=100, value=75, step=5
                ).props('label-always').classes('w-full')
                ui.label('Adjust video volume').classes('text-xs mt-1').style('color: #94a3b8;')
                
                # Connect volume slider to video
                def update_volume():
                    volume = volume_slider.value / 100
                    ui.run_javascript(f'''
                        const video = document.querySelector('video');
                        if (video) {{
                            video.volume = {volume};
                            console.log('Volume set to:', {volume});
                        }}
                    ''')
                
                volume_slider.on('update:model-value', update_volume)

        # === CENTER PANEL (INFO + CONTROLS) ===
        with ui.column().classes('items-center gap-4 h-full').style('width: 45%;'):
            
            # === INFO AREA ===
            with ui.column().classes('w-full flex-grow p-4 gap-4 overflow-y-auto rounded-lg chat-area').style('max-height: 60vh;'):
                ui.label('Simple Video Player').classes('text-2xl font-bold text-center w-full').style('color: #e2e8f0;')
                ui.separator().style('background: rgba(100, 116, 139, 0.3);')
                
                ui.label('Currently Playing:').classes('text-lg font-medium').style('color: #94a3b8;')
                ui.label(os.path.basename(VIDEO_PATH)).classes('text-base').style('color: #e2e8f0;')
                
                ui.separator().style('background: rgba(100, 116, 139, 0.3);')
                
                ui.label('Controls:').classes('text-lg font-medium').style('color: #94a3b8;')
                ui.label('• Video controls are available on the player').classes('text-sm').style('color: #94a3b8;')
                ui.label('• Use the volume slider to adjust audio').classes('text-sm').style('color: #94a3b8;')
                ui.label('• Video will loop automatically').classes('text-sm').style('color: #94a3b8;')

            # === CONTROL BUTTONS ===
            with ui.column().classes('items-center gap-4 w-full'):
                
                def restart_video():
                    ui.run_javascript('''
                        const video = document.querySelector('video');
                        if (video) {
                            video.currentTime = 0;
                            video.play();
                            console.log('Video restarted');
                        }
                    ''')
                
                def toggle_loop():
                    ui.run_javascript('''
                        const video = document.querySelector('video');
                        if (video) {
                            video.loop = !video.loop;
                            console.log('Loop toggled:', video.loop);
                        }
                    ''')
                
                def toggle_mute():
                    ui.run_javascript('''
                        const video = document.querySelector('video');
                        if (video) {
                            video.muted = !video.muted;
                            console.log('Mute toggled:', video.muted);
                        }
                    ''')

                ui.button('🔄 Restart Video', on_click=restart_video).classes('w-full text-lg py-3 px-6 rounded-lg').style('background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; border: none; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);')
                
                ui.button('🔁 Toggle Loop', on_click=toggle_loop).classes('w-full text-lg py-3 px-6 rounded-lg').style('background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; border: none; box-shadow: 0 4px 15px rgba(245, 158, 11, 0.3);')
                
                ui.button('🔇 Toggle Mute', on_click=toggle_mute).classes('w-full text-lg py-3 px-6 rounded-lg').style('background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; border: none; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);')

        # === RIGHT SIDEBAR ===
        with ui.column().classes('h-full border-l').style('width: 250px; background: rgba(15, 23, 42, 0.8); border-color: rgba(100, 116, 139, 0.3); backdrop-filter: blur(10px);'):
            # Sidebar Header
            with ui.row().classes('w-full items-center justify-between p-4 border-b').style('border-color: rgba(100, 116, 139, 0.3);'):
                ui.label('Info').classes('font-semibold').style('color: #e2e8f0;')

            # Sidebar Content
            with ui.column().classes('w-full p-4 gap-4'):
                
                # Video Info Section
                ui.label('Video Information').classes('font-medium text-sm').style('color: #94a3b8;')
                
                ui.label('Simple Player Mode').classes('text-xs').style('color: #64748b;')
                ui.label('Single Video Loop').classes('text-xs').style('color: #64748b;')
                ui.label('Manual Controls').classes('text-xs').style('color: #64748b;')
                
                ui.separator()
                
                # File Info
                ui.label('File Details').classes('font-medium text-sm mt-4').style('color: #94a3b8;')
                ui.label(f'Path: {VIDEO_PATH}').classes('text-xs break-all').style('color: #64748b;')
                
                ui.separator()
                
                # Instructions
                ui.label('Instructions').classes('font-medium text-sm mt-4').style('color: #94a3b8;')
                ui.label('This is a simple video player that loops a single video file.').classes('text-xs').style('color: #64748b;')
                ui.label('Use the controls to manage playback.').classes('text-xs').style('color: #64748b;')

    # === BOTTOM INFO BAR ===
    ui.separator().classes('w-full').style('background: rgba(100, 116, 139, 0.3);')
    
    with ui.row().classes('w-full p-4 border-t items-center justify-center gap-8').style('background: rgba(15, 23, 42, 0.6); border-color: rgba(100, 116, 139, 0.3); backdrop-filter: blur(5px);'):
        ui.label('Simple Darwin Video Player').classes('text-lg font-semibold').style('color: #e2e8f0;')
        ui.label('Playing one video in loop mode').classes('text-sm').style('color: #94a3b8;')

    # Add JavaScript for enhanced video control
    ui.add_body_html('''
    <script>
    // Enhanced video control and status
    window.addEventListener('load', function() {
        console.log('[SIMPLE] Darwin simple video player loaded');
        
        const video = document.querySelector('video');
        if (video) {
            // Set initial volume
            video.volume = 0.75;
            
            // Log video events
            video.addEventListener('play', () => console.log('[VIDEO] Playing'));
            video.addEventListener('pause', () => console.log('[VIDEO] Paused'));
            video.addEventListener('ended', () => console.log('[VIDEO] Ended'));
            video.addEventListener('loadstart', () => console.log('[VIDEO] Loading started'));
            video.addEventListener('canplay', () => console.log('[VIDEO] Can play'));
            video.addEventListener('error', (e) => console.error('[VIDEO] Error:', e));
            
            console.log('[SIMPLE] Video controls initialized');
        } else {
            console.error('[SIMPLE] No video element found');
        }
    });
    </script>
    ''')

def main():
    """Main function to run the simple video player"""
    
    # Set up static file serving for videos
    avatars_dir = os.path.join(PROJECT_DIR, "avatars")
    if os.path.exists(avatars_dir):
        app.add_static_files('/avatars', avatars_dir)
        print(f"[SIMPLE] Serving videos from: {avatars_dir}")
    else:
        print(f"[SIMPLE] Warning: Avatars directory not found: {avatars_dir}")
    
    print(f"[SIMPLE] Starting simple Darwin video player...")
    print(f"[SIMPLE] Video path: {VIDEO_PATH}")
    
    try:
        # Configure and run NiceGUI
        ui.run(
            title='Darwin Simple Video Player',
            port=8081,  # Different port to avoid conflicts
            show=True,
            reload=False,
            dark=None
        )
        
    except KeyboardInterrupt:
        print(f"\n[SIMPLE] Interrupted by user")
    except Exception as e:
        print(f"[SIMPLE] Error running application: {e}")

if __name__ == '__main__':
    main()