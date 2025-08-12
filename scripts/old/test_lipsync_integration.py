# test_lipsync_integration.py - Clean test lipsync that waits 3s and returns hardcoded video

import os
import time
import shutil
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

def generate_lipsync_with_integration(text: str, output_filename: str = None) -> tuple[bool, str]:
    """
    Test lipsync function - waits 3s then returns hardcoded video from tempstream
    
    Args:
        text: Text for lipsync (ignored in test)
        output_filename: Output filename (ignored in test)
    
    Returns:
        tuple: (success: bool, video_path: str)
    """
    print(f"{Fore.MAGENTA}[TEST_LIPSYNC] Starting for text: {text[:30]}...{Style.RESET_ALL}")
    
    # Wait 3 seconds to simulate lipsync generation
    print(f"{Fore.YELLOW}[TEST_LIPSYNC] Simulating processing (3 seconds)...{Style.RESET_ALL}")
    time.sleep(3)
    
    # Return hardcoded video from tempstream
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    test_video_path = os.path.join(temp_dir, "s1.mp4")  # Your hardcoded test video
    
    # Ensure tempstream exists
    os.makedirs(temp_dir, exist_ok=True)
    
    # Check if test video exists
    if os.path.exists(test_video_path):
        file_size = os.path.getsize(test_video_path)
        print(f"{Fore.GREEN}[TEST_LIPSYNC] Test video ready: {test_video_path} ({file_size} bytes){Style.RESET_ALL}")
        return True, test_video_path
    else:
        print(f"{Fore.YELLOW}[TEST_LIPSYNC] s1.mp4 not found, creating from existing video...{Style.RESET_ALL}")
        
        # Try to copy an existing video as test
        try:
            nodes_dir = os.path.join(PROJECT_DIR, "avatars", "Darwin", "Nodes")
            
            # Look for a good source video
            source_video = None
            if os.path.exists(nodes_dir):
                # Try main2main first
                main2main_dir = os.path.join(nodes_dir, "main2main")
                if os.path.exists(main2main_dir):
                    for file in os.listdir(main2main_dir):
                        if file.endswith('.mp4'):
                            source_video = os.path.join(main2main_dir, file)
                            break
                
                # If no main2main, find any video
                if not source_video:
                    for root, dirs, files in os.walk(nodes_dir):
                        for file in files:
                            if file.endswith('.mp4'):
                                source_video = os.path.join(root, file)
                                break
                        if source_video:
                            break
            
            if source_video and os.path.exists(source_video):
                shutil.copy2(source_video, test_video_path)
                print(f"{Fore.GREEN}[TEST_LIPSYNC] Created s1.mp4 from: {os.path.basename(source_video)}{Style.RESET_ALL}")
                return True, test_video_path
            else:
                print(f"{Fore.RED}[TEST_LIPSYNC] No source video found{Style.RESET_ALL}")
                return False, None
                
        except Exception as e:
            print(f"{Fore.RED}[TEST_LIPSYNC] Error creating test video: {e}{Style.RESET_ALL}")
            return False, None

def setup_lipsync_environment():
    """Setup test environment"""
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    try:
        os.makedirs(temp_dir, exist_ok=True)
        print(f"{Fore.GREEN}[TEST_LIPSYNC] Environment ready{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}[TEST_LIPSYNC] Setup failed: {e}{Style.RESET_ALL}")
        return False

if __name__ == "__main__":
    print("Testing lipsync integration...")
    
    if setup_lipsync_environment():
        test_text = "Hello, this is a test."
        success, video_path = generate_lipsync_with_integration(test_text)
        
        if success:
            print(f"✅ Test passed: {video_path}")
        else:
            print("❌ Test failed")
    else:
        print("❌ Environment setup failed")