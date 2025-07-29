#ui.py - Simplified UI with video displays and chat interface

from nicegui import ui

def build_ui(trigger_response_callback):
    with ui.row().classes('w-full h-screen items-start justify-start gap-4 p-4'):
        # === LEFT VIDEO PLAYER ===
        with ui.column().classes('items-start shrink-0').style('width: 45%; height: 100%;'):
            video_container = ui.card().classes('p-0 overflow-hidden').style('width: 100%; aspect-ratio: 2/3; background: black;')
            with video_container:
                ui.html('''
                <div id="main-video-container" style="width: 100%; height: 100%; position: relative;">
                    <video id="mainVideo" autoplay playsinline controls 
                        style="width: 100%; height: 100%; object-fit: contain;">
                        <source src="" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                </div>
                ''').classes('w-full h-full')

        # === RIGHT SIDE PANEL ===
        with ui.column().classes('items-center gap-4 h-full').style('width: 50%;'):
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
            # Replaces the old status_display card with a scrollable column for conversation history.
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
                        # The callback in main.py will now handle adding messages to the log.
                        trigger_response_callback(user_text)
                        prompt_input.value = ""
                    else:
                        ui.notify("Please enter a question first", color="warning")

                ui.button('Ask Darwin', on_click=submit_prompt).classes('w-full text-lg py-3 px-6 rounded-lg').style('background-color: #2563eb; color: white;')

    # Add some basic JavaScript for video handling if needed
    ui.add_body_html('''
    <script>
    window.addEventListener('load', function() {
        console.log('Darwin Chat UI loaded');
        
        // Function to update status display (can be called from Python)
        window.updateStatus = function(message) {
            // This could be enhanced to update the status from JavaScript if needed
            console.log('Status update:', message);
        };
        
        // Function to load videos if needed in the future
        window.loadVideo = function(videoId, source) {
            const video = document.getElementById(videoId);
            if (video && source) {
                video.src = source;
                video.load();
            }
        };
    });
    </script>
    ''')

    # Return the chat_log so main.py can update it
    return chat_log