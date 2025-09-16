import shutil
import subprocess

def test_ffmpeg_setup():
    """Test if FFmpeg tools are properly available"""
    
    print("Testing FFmpeg setup...")
    print("=" * 40)
    
    # Test ffmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    print(f"FFmpeg path: {ffmpeg_path}")
    
    if ffmpeg_path:
        try:
            result = subprocess.run([ffmpeg_path, "-version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("✓ FFmpeg is working")
                # Show first line of version info
                first_line = result.stdout.split('\n')[0]
                print(f"  Version: {first_line}")
            else:
                print("✗ FFmpeg command failed")
                print(f"  Error: {result.stderr}")
        except Exception as e:
            print(f"✗ FFmpeg test failed: {e}")
    else:
        print("✗ FFmpeg not found in PATH")
    
    print()
    
    # Test ffprobe
    ffprobe_path = shutil.which("ffprobe")
    print(f"FFprobe path: {ffprobe_path}")
    
    if ffprobe_path:
        try:
            result = subprocess.run([ffprobe_path, "-version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("✓ FFprobe is working")
                # Show first line of version info
                first_line = result.stdout.split('\n')[0]
                print(f"  Version: {first_line}")
            else:
                print("✗ FFprobe command failed")
                print(f"  Error: {result.stderr}")
        except Exception as e:
            print(f"✗ FFprobe test failed: {e}")
    else:
        print("✗ FFprobe not found in PATH")
    
    print()
    print("System PATH FFmpeg entries:")
    import os
    path_entries = os.environ.get('PATH', '').split(os.pathsep)
    ffmpeg_paths = [p for p in path_entries if 'ffmpeg' in p.lower()]
    if ffmpeg_paths:
        for path in ffmpeg_paths:
            print(f"  {path}")
    else:
        print("  No FFmpeg-related paths found in PATH")

# Run the test
if __name__ == "__main__":
    test_ffmpeg_setup()