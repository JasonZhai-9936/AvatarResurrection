import asyncio
import random
import os
from pathlib import Path
from nicegui import ui, app
import glob

class AsyncVideoPlayer:
    def __init__(self, idle_clips_dir: str, priority_clips_dir: str):
        # Communication channels
        self.priority_queue = asyncio.Queue()
        self.current_idle_task = None
        
        # Video file directories
        self.idle_clips_dir = Path(idle_clips_dir)
        self.priority_clips_dir = Path(priority_clips_dir)
        
        # Load video files
        self.idle_clips = self._load_video_files(self.idle_clips_dir)
        self.priority_clips = self._load_video_files(self.priority_clips_dir)
        
        # Shared state
        self.video_element = None
        self.is_playing_priority = False
        self.current_video_future = None
        self.is_running = False
        self.pending_priority_clips = []  # Queue for priority clips waiting for seamless transition
        
        # Status info
        self.status_label = None
        self.current_clip_label = None
        
    def _load_video_files(self, directory: Path) -> list:
        """Load all video files from a directory"""
        if not directory.exists():
            print(f"Warning: Directory {directory} does not exist")
            return []
        
        video_extensions = ['*.mp4', '*.avi', '*.mov', '*.mkv', '*.webm', '*.m4v']
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(glob.glob(str(directory / ext)))
        
        print(f"Found {len(video_files)} video files in {directory}")
        return video_files
    
    def create_ui(self):
        """Create the NiceGUI interface"""
        with ui.card().style('width: 800px; margin: 0 auto;'):
            ui.label('Async Video Player').style('font-size: 24px; font-weight: bold;')
            
            # Video player with autoplay for seamless experience - NO CONTROLS
            self.video_element = ui.video(src="").style("width: 100%; height: 400px; background: black;")
            
            # Set autoplay, muted, and REMOVE controls to prevent user interference
            self.video_element._props['autoplay'] = True
            self.video_element._props['muted'] = True
            self.video_element._props['playsinline'] = True
            self.video_element._props['preload'] = 'auto'
            self.video_element._props['controls'] = False  # This hides the controls
            
            # Also disable right-click context menu and other interactions via CSS
            self.video_element.style('''
                width: 100%; 
                height: 400px; 
                background: black;
                pointer-events: none;  /* Disables all mouse interactions */
                -webkit-user-select: none;  /* Prevents text selection */
                -moz-user-select: none;
                -ms-user-select: none;
                user-select: none;
            ''')
            self.video_element.on('ended', self.on_video_ended)
            self.video_element.on('loadstart', self.on_video_loadstart)
            
            # Status display
            with ui.row():
                ui.label('Status:')
                self.status_label = ui.label('Stopped').style('color: red;')
            
            with ui.row():
                ui.label('Current:')
                self.current_clip_label = ui.label('None')
            
            # Control buttons
            with ui.row():
                ui.button('Start Player', on_click=self.start_player).style('background: green;')
                ui.button('Stop Player', on_click=self.stop_player).style('background: red;')
            
            # Priority clip buttons (random selection from priority folder)
            ui.separator()
            ui.label('Trigger Priority Clips:').style('font-weight: bold;')
            
            with ui.row():
                ui.button('Play Random Priority Clip', 
                         on_click=self.play_random_priority_clip).style('background: orange;')
                
                if len(self.priority_clips) > 0:
                    ui.button('Play Specific Priority Clip', 
                             on_click=lambda: self.queue_priority_clip(self.priority_clips[0])
                             ).style('background: purple;')
            
            # Info display
            ui.separator()
            with ui.column():
                ui.label(f'Idle clips found: {len(self.idle_clips)}')
                ui.label(f'Priority clips found: {len(self.priority_clips)}')
                
                if len(self.idle_clips) == 0:
                    ui.label('⚠️ No idle clips found! Check your idle clips directory.').style('color: orange;')
                
                if len(self.priority_clips) == 0:
                    ui.label('⚠️ No priority clips found! Check your priority clips directory.').style('color: orange;')
    
    async def on_video_ended(self):
        """Handle video completion events and check for pending priority clips"""
        print("Video ended event received")
        
        # Complete the current video future
        if self.current_video_future and not self.current_video_future.done():
            self.current_video_future.set_result(True)
        
        # Only handle pending priority clips if we're NOT currently playing priority clips
        # This prevents double-handling when a priority clip itself ends
        if self.pending_priority_clips and not self.is_playing_priority:
            print("📋 Handling pending priority clips from video end")
            await self.handle_pending_priority_clips()
        else:
            print(f"📋 No action needed: pending={len(self.pending_priority_clips)}, is_priority={self.is_playing_priority}")
    
    async def handle_pending_priority_clips(self):
        """Handle seamless transition to priority clips"""
        if not self.pending_priority_clips:
            return
        
        print(f"🎬 Starting seamless transition to priority clips")
        
        # Cancel idle loop to prevent new idle clips from starting
        if self.current_idle_task and not self.current_idle_task.done():
            print("⏸️ Pausing idle loop for priority clips")
            self.current_idle_task.cancel()
            try:
                await self.current_idle_task
            except asyncio.CancelledError:
                pass
        
        # Play all pending priority clips in order
        while self.pending_priority_clips:
            priority_clip = self.pending_priority_clips.pop(0)
            
            # Update state
            self.is_playing_priority = True
            self.update_status_safe('Playing Priority', 'orange')
            
            # Play priority clip
            print(f"🎯 Playing priority clip: {Path(priority_clip).name}")
            await self.play_video_and_wait(priority_clip)
            print(f"✅ Priority clip completed: {Path(priority_clip).name}")
        
        # All priority clips done, return to idle
        print("🏁 All priority clips completed, returning to idle")
        self.is_playing_priority = False
        self.update_status_safe('Playing Idle', 'blue')
        
        # Restart idle loop - THIS IS THE KEY FIX
        print(f"🔄 Restarting idle loop after priority clips (is_running: {self.is_running})")
        if self.is_running:
            print("✅ Creating new idle task...")
            self.current_idle_task = asyncio.create_task(self.idle_loop())
            print("✅ New idle task created and should start soon...")
            
            # Give it a moment and then check if it started
            await asyncio.sleep(0.2)
            if self.current_idle_task.done():
                print("❌ Idle task completed immediately - checking for errors")
                try:
                    await self.current_idle_task
                except Exception as e:
                    print(f"❌ Idle task error: {e}")
            else:
                print("✅ Idle task is running properly")
        else:
            print("❌ Cannot restart idle - player is not running")
    
    async def on_video_loadstart(self):
        """Handle video load start events"""
        print("Video load started")
    
    def update_status_safe(self, text: str, color: str):
        """Safely update status from background tasks"""
        try:
            self.status_label.set_text(text)
            self.status_label.style(f'color: {color};')
        except Exception as e:
            print(f"UI update error: {e}")
    
    def update_current_clip_safe(self, text: str):
        """Safely update current clip label from background tasks"""
        try:
            self.current_clip_label.set_text(text)
        except Exception as e:
            print(f"UI update error: {e}")
    
    def set_video_source_safe(self, video_path: str):
        """Safely set video source from background tasks"""
        try:
            self.video_element.set_source(video_path)
        except Exception as e:
            print(f"Video source update error: {e}")
    
    def run_javascript_safe(self, code: str):
        """Safely run JavaScript from background tasks"""
        try:
            ui.run_javascript(code)
        except Exception as e:
            print(f"JavaScript execution error: {e}")
    
    async def play_video_and_wait(self, video_path: str):
        """Play a video and wait for it to complete"""
        video_name = Path(video_path).name
        print(f"Starting video: {video_name}")
        
        # Update UI safely
        self.update_current_clip_safe(video_name)
        
        # Create a future to wait for video completion
        self.current_video_future = asyncio.Future()
        
        # Start the video with autoplay
        self.set_video_source_safe(video_path)
        
        # Force play via JavaScript to ensure seamless playback
        self.run_javascript_safe('''
            setTimeout(() => {
                const video = document.querySelector('video');
                if (video && video.paused) {
                    console.log("Attempting to play video...");
                    video.play().then(() => {
                        console.log("Video play successful");
                    }).catch(e => {
                        console.log("Autoplay failed:", e);
                        // If autoplay fails, we could show a play button or handle it differently
                    });
                }
            }, 100);
        ''')
        
        # Wait for video to complete (or be cancelled)
        try:
            await self.current_video_future
        except asyncio.CancelledError:
            print(f"Video {video_name} was cancelled")
            raise
        finally:
            self.current_video_future = None
    
    async def priority_monitor(self):
        """Monitor for priority clips and handle seamless transitions"""
        print("🎬 Priority monitor starting")
        try:
            while self.is_running:
                try:
                    # Wait for priority clip with timeout to check if still running
                    try:
                        priority_clip = await asyncio.wait_for(self.priority_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    
                    print(f"🎬 Priority clip queued: {Path(priority_clip).name}")
                    
                    # Add to pending list instead of immediate interruption
                    self.pending_priority_clips.append(priority_clip)
                    
                    # Update status to show priority is pending
                    if not self.is_playing_priority:
                        self.update_status_safe('Priority Pending (finishing current clip)', 'orange')
                    
                    print(f"📋 Priority clips pending: {len(self.pending_priority_clips)}")
                    
                except Exception as e:
                    print(f"Error in priority monitor inner loop: {e}")
                    import traceback
                    traceback.print_exc()
                    if self.is_running:
                        await asyncio.sleep(1)
        
        except Exception as e:
            print(f"Error in priority monitor outer: {e}")
            import traceback
            traceback.print_exc()
        
        print("🔴 Priority monitor ending")
    
    async def idle_loop(self):
        """Continuous idle video playback"""
        print("🔄 Starting idle loop")
        
        while self.is_running:
            try:
                # Check if we should continue
                if self.is_playing_priority:
                    print("Priority clip is playing, stopping idle loop")
                    break
                
                if len(self.idle_clips) == 0:
                    print("No idle clips available, waiting...")
                    await asyncio.sleep(5)
                    continue
                
                # Play random idle clip
                idle_clip = random.choice(self.idle_clips)
                print(f"🎵 Playing idle: {Path(idle_clip).name}")
                
                await self.play_video_and_wait(idle_clip)
                
                # Brief pause between clips
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                print("🛑 Idle loop cancelled")
                raise
            except Exception as e:
                print(f"Error in idle loop: {e}")
                await asyncio.sleep(1)
    
    async def idle_manager(self):
        """Manage idle playback lifecycle"""
        print("🚀 Starting idle manager")
        
        # Start first idle loop
        if self.is_running:
            self.current_idle_task = asyncio.create_task(self.idle_loop())
        
        # Keep manager alive and restart idle loops as needed
        while self.is_running:
            try:
                if self.current_idle_task and not self.current_idle_task.done():
                    await self.current_idle_task
                    print("🏁 Idle task completed naturally")
                
                # Restart if not playing priority and still running
                if not self.is_playing_priority and self.is_running:
                    print("🔁 Restarting idle loop from manager")
                    self.current_idle_task = asyncio.create_task(self.idle_loop())
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"Idle manager error: {e}")
                import traceback
                traceback.print_exc()
                if self.is_running:
                    await asyncio.sleep(1)
        
        print("🔴 Idle manager ending")
    
    async def start_playback(self):
        """Start the video system"""
        print("🎯 Starting video player system")
        self.is_running = True
        print(f"✅ Set is_running = {self.is_running}")
        
        # Update UI
        self.update_status_safe('Playing Idle', 'blue')
        
        # Start both processes but don't wait for them to complete together
        # This prevents one process ending from stopping the other
        priority_task = asyncio.create_task(self.priority_monitor())
        idle_task = asyncio.create_task(self.idle_manager())
        
        try:
            # Keep the system alive as long as is_running is True
            while self.is_running:
                # Check if either task has died unexpectedly
                if priority_task.done():
                    print("⚠️ Priority task ended, restarting...")
                    priority_task = asyncio.create_task(self.priority_monitor())
                
                if idle_task.done():
                    print("⚠️ Idle task ended, restarting...")
                    idle_task = asyncio.create_task(self.idle_manager())
                
                await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"Error in start_playback: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("🔴 start_playback ending - setting is_running = False")
            self.is_running = False
            
            # Clean up tasks
            if not priority_task.done():
                priority_task.cancel()
            if not idle_task.done():
                idle_task.cancel()
    
    # Public interface methods
    def queue_priority_clip(self, clip_path: str):
        """Queue a priority clip (thread-safe)"""
        if self.is_running:
            asyncio.create_task(self.priority_queue.put(clip_path))
            print(f"Queued priority clip: {Path(clip_path).name}")
        else:
            print("Player is not running!")
    
    def play_random_priority_clip(self):
        """Play a random priority clip"""
        if len(self.priority_clips) == 0:
            print("No priority clips available!")
            return
        
        random_clip = random.choice(self.priority_clips)
        self.queue_priority_clip(random_clip)
    
    def start_player(self):
        """Start the video player"""
        if not self.is_running:
            self.player_task = asyncio.create_task(self.start_playback())
    
    def stop_player(self):
        """Stop the video player"""
        print("🔴 STOP PLAYER CALLED - setting is_running = False")
        self.is_running = False
        self.update_status_safe('Stopped', 'red')
        self.update_current_clip_safe('None')
        
        if self.current_idle_task and not self.current_idle_task.done():
            print("🔴 Cancelling idle task from stop_player")
            self.current_idle_task.cancel()
            

# Main application setup
def main():
    # Configure these paths to your absolute video directories
    IDLE_CLIPS_DIR = r"C:\Users\Jason\Documents\DarwinChatbot\avatars\Darwin\Nodes\main2main"  
    PRIORITY_CLIPS_DIR = r"C:\Users\Jason\Documents\DarwinChatbot\avatars\Darwin\lipsync_responses\main2main"
    
    print(f"Looking for idle clips in: {IDLE_CLIPS_DIR}")
    print(f"Looking for priority clips in: {PRIORITY_CLIPS_DIR}")
    
    # Create the video player
    player = AsyncVideoPlayer(IDLE_CLIPS_DIR, PRIORITY_CLIPS_DIR)
    
    # Create the UI
    @ui.page('/')
    def index():
        player.create_ui()
    
    # Make player accessible globally for testing
    app.player = player


if __name__ in {"__main__", "__mp_main__"}:
    # Update these paths before running!
    main()
    ui.run(port=8080)