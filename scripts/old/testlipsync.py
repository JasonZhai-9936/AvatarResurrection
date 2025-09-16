# lipsync.py - Test lip-sync video generator with 3-second delay

import os
import time
import random
import shutil
from colorama import Fore, Style, init

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Initialize colorama for colored terminal output
init(autoreset=True)

def generate_lipsync_video(text: str) -> str:
    """
    Test function that simulates lip-sync video generation.
    Waits 3 seconds then returns a random main2main video.
    
    Args:
        text: The text to "generate" lip-sync for
        
    Returns:
        str: Path to the generated lip-sync video
    """
    print(f"{Fore.MAGENTA}[LIPSYNC] Starting generation for: {text[:50]}...{Style.RESET_ALL}")
    
    # Simulate processing time
    print(f"{Fore.YELLOW}[LIPSYNC] Processing... (3 seconds){Style.RESET_ALL}")
    time.sleep(3)
    
    # Direct path to specific video
    source_video = r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\sora1.mp4"
    
    # Check if the video exists
    if not os.path.exists(source_video):
        print(f"{Fore.RED}[LIPSYNC] Video not found: {source_video}{Style.RESET_ALL}")
        return None
    
    # Create lipsync output directory
    lipsync_dir = os.path.join(PROJECT_DIR, "temp_lipsync")
    os.makedirs(lipsync_dir, exist_ok=True)
    
    # Generate output filename with timestamp
    timestamp = int(time.time() * 1000)
    output_filename = f"lipsync_{timestamp}.mp4"
    output_path = os.path.join(lipsync_dir, output_filename)
    
    try:
        # Copy the specific video to simulate "generation"
        print(f"{Fore.CYAN}[LIPSYNC] Using specific video: {os.path.basename(source_video)} as lip-sync video{Style.RESET_ALL}")
        shutil.copy2(source_video, output_path)
        
        print(f"{Fore.GREEN}[LIPSYNC] Generation complete! Output: {output_path}{Style.RESET_ALL}")
        return output_path
        
    except Exception as e:
        print(f"{Fore.RED}[LIPSYNC] Error generating lip-sync video: {e}{Style.RESET_ALL}")
        return None

def test_lipsync_generation():
    """Test the lip-sync generation function"""
    print(f"{Fore.GREEN}{'=' * 50}")
    print(f"{Fore.YELLOW}Testing Lip-Sync Generation")
    print(f"{Fore.GREEN}{'=' * 50}{Style.RESET_ALL}")
    
    test_texts = [
        "Hello, I am Charles Darwin.",
        "The theory of evolution by natural selection.",
        "This is a longer test message to simulate a more complex response from Darwin about his theories and observations."
    ]
    
    for i, text in enumerate(test_texts, 1):
        print(f"\n{Fore.CYAN}Test {i}/{len(test_texts)}:{Style.RESET_ALL}")
        print(f"Text: {text}")
        
        start_time = time.time()
        result = generate_lipsync_video(text)
        end_time = time.time()
        
        if result:
            print(f"{Fore.GREEN}✓ Success! Generated: {os.path.basename(result)}{Style.RESET_ALL}")
            print(f"  Generation time: {end_time - start_time:.2f} seconds")
            print(f"  File size: {os.path.getsize(result) / (1024*1024):.2f} MB")
        else:
            print(f"{Fore.RED}✗ Failed to generate lip-sync video{Style.RESET_ALL}")
        
        print("-" * 50)

if __name__ == "__main__":
    test_lipsync_generation()