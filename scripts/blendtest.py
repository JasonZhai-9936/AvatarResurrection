#!/usr/bin/env python3
import os
import subprocess
import json
from pathlib import Path

def get_video_duration(video_path):
    """Get video duration using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', str(video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except (subprocess.CalledProcessError, KeyError, ValueError):
        print(f"Warning: Could not get duration for {video_path}")
        return None

def get_video_files(directory):
    """Get all video files from directory"""
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
    video_files = []
    
    for file_path in Path(directory).iterdir():
        if file_path.is_file() and file_path.suffix.lower() in video_extensions:
            video_files.append(file_path)
    
    return sorted(video_files)

def create_fade_transition(video1, video2, output_path, transition_type, duration=1.0):
    """Create a transition between two videos using various fade/blend effects"""
    
    # First, let's get video duration to calculate proper offset
    video1_duration = get_video_duration(video1)
    if video1_duration is None or video1_duration < 6:
        print(f"Video {video1} is too short or duration unknown")
        return False
    
    # Calculate offset (start transition 1 second before video1 ends)
    offset = max(0, min(video1_duration - duration - 1, 5))
    
    transitions = {
        'crossfade': f'[0:v][1:v]xfade=transition=fade:duration={duration}:offset={offset}[v]',
        'dissolve': f'[0:v][1:v]xfade=transition=dissolve:duration={duration}:offset={offset}[v]',
        'wipeleft': f'[0:v][1:v]xfade=transition=wipeleft:duration={duration}:offset={offset}[v]',
        'wiperight': f'[0:v][1:v]xfade=transition=wiperight:duration={duration}:offset={offset}[v]',
        'fadeblack': f'[0:v][1:v]xfade=transition=fadeblack:duration={duration}:offset={offset}[v]',
        'fadewhite': f'[0:v][1:v]xfade=transition=fadewhite:duration={duration}:offset={offset}[v]',
        'smoothleft': f'[0:v][1:v]xfade=transition=smoothleft:duration={duration}:offset={offset}[v]',
        'smoothright': f'[0:v][1:v]xfade=transition=smoothright:duration={duration}:offset={offset}[v]',
        # Simple blend transition as fallback
        'blend': f'[0:v][1:v]blend=all_mode=overlay:all_opacity=0.5[v]',
    }
    
    if transition_type not in transitions:
        print(f"Unknown transition type: {transition_type}")
        return False
    
    # Use shorter clips (6 seconds each) to avoid issues
    clip_duration = offset + duration + 2
    
    cmd = [
        'ffmpeg', '-y',  # Overwrite output files
        '-i', str(video1), '-t', str(clip_duration),  # First video
        '-i', str(video2), '-t', str(clip_duration),  # Second video
        '-filter_complex', transitions[transition_type],
        '-map', '[v]',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-pix_fmt', 'yuv420p',  # Ensure compatibility
        str(output_path)
    ]
    
    # Add audio handling if first video has audio
    try:
        # Check if video has audio
        probe_cmd = ['ffprobe', '-v', 'quiet', '-select_streams', 'a', '-show_entries', 'stream=codec_type', str(video1)]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
        
        if 'codec_type=audio' in probe_result.stdout:
            # Insert audio mapping before codec options
            cmd.insert(-4, '-map')
            cmd.insert(-4, '0:a')
            cmd.insert(-2, '-c:a')
            cmd.insert(-2, 'aac')
    except:
        pass  # Continue without audio if probe fails
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating transition {transition_type}:")
        print(f"  Command: {' '.join(cmd)}")
        print(f"  Error: {e.stderr if e.stderr else str(e)}")
        return False

def create_best_transitions_compilation(output_dir, best_transitions, final_output):
    """Combine the best transitions into a single compilation video"""
    if not best_transitions:
        print("No successful transitions to compile")
        return False
    
    # Create a text file listing all the best transition videos
    file_list_path = output_dir / 'best_transitions_list.txt'
    with open(file_list_path, 'w') as f:
        for transition_file in best_transitions:
            f.write(f"file '{transition_file}'\n")
    
    # Concatenate all best transitions
    cmd = [
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', str(file_list_path),
        '-c', 'copy',
        str(final_output)
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Best transitions compilation created: {final_output}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating compilation: {e}")
        return False

def main():
    # Hardcoded paths - modify these as needed
    VIDEO1_PATH = r"C:\Users\Jason\Documents\DarwinChatbot\avatars\Darwin\Nodes\main2main\idle3.mp4"
    VIDEO2_PATH = r"C:\Users\Jason\Documents\DarwinChatbot\avatars\Darwin\Nodes\main2main\smile.mp4"
    OUTPUT_DIR = "transitions_output"
    TRANSITION_DURATION = 1.0
    
    # Validate input files
    video1 = Path(VIDEO1_PATH)
    video2 = Path(VIDEO2_PATH)
    
    if not video1.exists() or not video1.is_file():
        print(f"Error: {video1} is not a valid video file")
        return
    
    if not video2.exists() or not video2.is_file():
        print(f"Error: {video2} is not a valid video file")
        return
    
    # Create output directory
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(exist_ok=True)
    
    print(f"Testing transitions between:")
    print(f"  Video 1: {video1.name}")
    print(f"  Video 2: {video2.name}")
    print(f"  Output directory: {output_dir}")
    
    # Best transition types for smooth results (simplified list)
    best_transitions_types = [
        'crossfade', 'dissolve', 'fadeblack', 'fadewhite',
        'smoothleft', 'smoothright', 'blend'
    ]
    
    successful_transitions = []
    
    # Test all transition types between the two videos
    print(f"\nTesting transitions: {video1.stem} -> {video2.stem}")
    
    for transition_type in best_transitions_types:
        output_filename = f"transition_{transition_type}_{video1.stem}_to_{video2.stem}.mp4"
        output_path = output_dir / output_filename
        
        print(f"  Creating {transition_type} transition...")
        
        if create_fade_transition(video1, video2, output_path, transition_type, TRANSITION_DURATION):
            print(f"    ✓ Success: {output_filename}")
            successful_transitions.append(output_path)
        else:
            print(f"    ✗ Failed: {output_filename}")
    
    print(f"\n=== Summary ===")
    print(f"Total successful transitions: {len(successful_transitions)}")
    print(f"Output directory: {output_dir}")
    
    # Create a compilation of the best transitions
    if successful_transitions:
        final_compilation = output_dir / "best_transitions_compilation.mp4"
        
        print(f"\nCreating compilation of {len(successful_transitions)} transitions...")
        if create_best_transitions_compilation(output_dir, successful_transitions, final_compilation):
            print(f"✓ Compilation created successfully!")
        else:
            print("✗ Failed to create compilation")
    
    print(f"\nAll individual transition files are available in: {output_dir}")
    print("\nRecommended smooth transitions to review:")
    for transition in ['crossfade', 'dissolve', 'smoothleft', 'smoothright']:
        matching_files = [f for f in successful_transitions if transition in f.name]
        if matching_files:
            print(f"  - {transition.capitalize()}: {len(matching_files)} files")

if __name__ == "__main__":
    main()