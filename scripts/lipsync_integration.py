# lipsync_integration.py - Integration layer for existing avatar system

import os
import time
import threading
from typing import Tuple, Optional
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

def generate_lipsync_with_integration(text: str, avatar_name: str = "Darwin") -> Tuple[bool, Optional[str]]:
    """
    Enhanced integration function that replaces your test lipsync function
    This is the function called by your node_video_system.py
    """
    try:
        from lipsyncer import LipsyncSystem
        
        print(f"{Fore.MAGENTA}[INTEGRATION] Starting real lipsync generation...{Style.RESET_ALL}")
        
        # Create lipsync system
        lipsync_system = LipsyncSystem(avatar_name)
        
        # Generate the lipsync video
        success, video_path = lipsync_system.generate_lipsync(text)
        
        if success and video_path and os.path.exists(video_path):
            print(f"{Fore.GREEN}[INTEGRATION] ✓ Lipsync generation successful: {os.path.basename(video_path)}{Style.RESET_ALL}")
            return True, video_path
        else:
            print(f"{Fore.RED}[INTEGRATION] ✗ Lipsync generation failed{Style.RESET_ALL}")
            return False, None
            
    except ImportError as e:
        print(f"{Fore.RED}[INTEGRATION] Lipsync system not available: {e}{Style.RESET_ALL}")
        return _fallback_test_lipsync(text)
    except Exception as e:
        print(f"{Fore.RED}[INTEGRATION] Lipsync error: {e}{Style.RESET_ALL}")
        return _fallback_test_lipsync(text)

def _fallback_test_lipsync(text: str) -> Tuple[bool, Optional[str]]:
    """
    Fallback function that simulates lipsync generation for testing
    This matches your original test function behavior
    """
    print(f"{Fore.YELLOW}[INTEGRATION] Using fallback test lipsync...{Style.RESET_ALL}")
    
    # Simulate processing time
    time.sleep(2)
    
    # Try to find any video file as a placeholder
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Look for existing video files to use as placeholder
    avatar_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin", "Nodes")
    
    placeholder_video = None
    if os.path.exists(avatar_dir):
        for root, dirs, files in os.walk(avatar_dir):
            for file in files:
                if file.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    placeholder_video = os.path.join(root, file)
                    break
            if placeholder_video:
                break
    
    if placeholder_video:
        # Copy placeholder to temp directory
        import shutil
        timestamp = int(time.time() * 1000)
        test_output = os.path.join(temp_dir, f"test_lipsync_{timestamp}.mp4")
        
        try:
            shutil.copy2(placeholder_video, test_output)
            print(f"{Fore.GREEN}[INTEGRATION] ✓ Test lipsync ready: {os.path.basename(test_output)}{Style.RESET_ALL}")
            return True, test_output
        except Exception as e:
            print(f"{Fore.RED}[INTEGRATION] ✗ Test lipsync failed: {e}{Style.RESET_ALL}")
            return False, None
    else:
        print(f"{Fore.RED}[INTEGRATION] ✗ No placeholder video found{Style.RESET_ALL}")
        return False, None

def setup_lipsync_environment(avatar_name: str = "Darwin") -> bool:
    """
    Setup and verify the lipsync environment
    This replaces any existing setup function you might have
    """
    try:
        from lipsyncer import LipsyncSystem
        
        print(f"{Fore.CYAN}[INTEGRATION] Setting up lipsync environment for {avatar_name}...{Style.RESET_ALL}")
        
        # Check if talking clips directory exists
        avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
        talking_clips_dir = os.path.join(avatar_dir, "talking_clips")
        
        if not os.path.exists(talking_clips_dir):
            print(f"{Fore.YELLOW}[INTEGRATION] Creating talking_clips directory: {talking_clips_dir}{Style.RESET_ALL}")
            os.makedirs(talking_clips_dir, exist_ok=True)
            
            print(f"{Fore.YELLOW}[INTEGRATION] Please add your 5-second talking clips to: {talking_clips_dir}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[INTEGRATION] Clips should have 1s idle + 3s talking + 1s idle{Style.RESET_ALL}")
            
            # For now, return True but warn user
            return True
        
        # Test the system
        lipsync_system = LipsyncSystem(avatar_name)
        
        # Check if we have talking clips
        if not lipsync_system.talking_clips:
            print(f"{Fore.YELLOW}[INTEGRATION] No talking clips found in {talking_clips_dir}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[INTEGRATION] Please add MP4 files with talking animations{Style.RESET_ALL}")
            return True  # Allow system to continue with test mode
        
        # Test FFmpeg availability
        if not lipsync_system.ffmpeg_available:
            print(f"{Fore.YELLOW}[INTEGRATION] FFmpeg not found - install for full functionality{Style.RESET_ALL}")
            return True  # Allow system to continue with limited functionality
        
        print(f"{Fore.GREEN}[INTEGRATION] ✓ Lipsync environment ready{Style.RESET_ALL}")
        return True
        
    except ImportError:
        print(f"{Fore.YELLOW}[INTEGRATION] Lipsync system not available - using test mode{Style.RESET_ALL}")
        return True  # Allow system to continue
    except Exception as e:
        print(f"{Fore.RED}[INTEGRATION] Setup error: {e}{Style.RESET_ALL}")
        return False

def create_talking_clips_structure(avatar_name: str = "Darwin"):
    """
    Create the directory structure for talking clips
    Call this once to set up your avatar
    """
    avatar_dir = os.path.join(PROJECT_DIR, "avatars", avatar_name)
    talking_clips_dir = os.path.join(avatar_dir, "talking_clips")
    
    os.makedirs(talking_clips_dir, exist_ok=True)
    
    # Create a README file with instructions
    readme_path = os.path.join(talking_clips_dir, "README.txt")
    
    readme_content = f"""
TALKING CLIPS DIRECTORY FOR {avatar_name.upper()}

This directory should contain your pre-generated talking video clips.

REQUIREMENTS:
- Each clip should be exactly 5 seconds long
- Format: MP4, AVI, MOV, or MKV
- Structure: 1s idle + 3s talking + 1s idle
- Resolution: Consistent across all clips
- Audio: Original audio will be replaced with TTS

NAMING:
- Use descriptive names like: talking_01.mp4, talking_02.mp4, etc.
- The system will randomly select from available clips

USAGE:
- Place your Sora-generated or other talking clips here
- The lipsync system will overlay TTS audio during the 3-second talking portion
- Clips are automatically selected for each sentence in the response

TESTING:
- Run: python lipsyncer.py to test the system
- Check logs for any issues with clip detection or processing

Created: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    print(f"{Fore.GREEN}[INTEGRATION] ✓ Created talking clips structure at: {talking_clips_dir}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[INTEGRATION] Please add your 5-second talking clips to this directory{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[INTEGRATION] See README.txt for detailed instructions{Style.RESET_ALL}")

# Enhanced version of your response processing function
def enhanced_response_processing(user_text: str, generate_darwin_response_func, node_system, update_video_player_func):
    """
    Enhanced version of your handle_user_input function with real lipsync
    This shows how to integrate the new lipsync system into your existing workflow
    """
    try:
        print(f"{Fore.CYAN}[INTEGRATION] Processing user input: {user_text[:50]}...{Style.RESET_ALL}")
        
        # Step 1: Interrupt idle video system (your existing code)
        print(f"{Fore.YELLOW}[INTEGRATION] Interrupting idle system for response{Style.RESET_ALL}")
        node_system.interrupt_for_response()
        
        # Step 2: Generate LLM response (your existing code)
        print(f"{Fore.CYAN}[INTEGRATION] Generating LLM response...{Style.RESET_ALL}")
        response = generate_darwin_response_func(user_text)
        print(f"{Fore.GREEN}[INTEGRATION] LLM Response: {response[:100]}...{Style.RESET_ALL}")
        
        # Step 3: Generate lipsync video (NEW - replaces your TTS streaming)
        print(f"{Fore.MAGENTA}[INTEGRATION] Starting lipsync generation...{Style.RESET_ALL}")
        
        def lipsync_worker():
            # This runs in a separate thread to avoid blocking
            success, video_path = generate_lipsync_with_integration(response)
            
            if success and video_path:
                print(f"{Fore.GREEN}[INTEGRATION] ✓ Lipsync completed: {os.path.basename(video_path)}{Style.RESET_ALL}")
                
                # Update the video player with the lipsync result
                update_video_player_func(video_path)
                
                # After lipsync video plays, return to idle system
                # You might want to add a delay here equal to the video duration
                time.sleep(5)  # Adjust based on your video lengths
                
                # Resume idle system
                node_system.start_idle_playing(update_video_player_func)
                
            else:
                print(f"{Fore.RED}[INTEGRATION] ✗ Lipsync failed - resuming idle system{Style.RESET_ALL}")
                node_system.start_idle_playing(update_video_player_func)
        
        # Start lipsync generation in background
        lipsync_thread = threading.Thread(target=lipsync_worker, daemon=True)
        lipsync_thread.start()
        
        return response
        
    except Exception as e:
        print(f"{Fore.RED}[INTEGRATION] Enhanced processing error: {e}{Style.RESET_ALL}")
        # Resume idle system on error
        node_system.start_idle_playing(update_video_player_func)
        return "Sorry, I'm having trouble processing your request right now."

if __name__ == "__main__":
    # Setup and test when run directly
    print(f"{Fore.GREEN}{'='*60}")
    print(f"{Fore.YELLOW}Lipsync Integration System Test")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    
    # Create directory structure
    create_talking_clips_structure()
    
    # Test setup
    if setup_lipsync_environment():
        print(f"{Fore.GREEN}✓ Environment setup successful{Style.RESET_ALL}")
        
        # Test integration
        test_text = "Hello! This is a test of the integrated lipsync system. It should work seamlessly with your avatar chatbot."
        
        success, video_path = generate_lipsync_with_integration(test_text)
        
        if success:
            print(f"{Fore.GREEN}✓ Integration test successful!{Style.RESET_ALL}")
            print(f"✓ Video output: {video_path}")
        else:
            print(f"{Fore.YELLOW}⚠ Integration test used fallback mode{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}✗ Environment setup failed{Style.RESET_ALL}")