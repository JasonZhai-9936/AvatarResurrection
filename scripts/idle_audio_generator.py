# idle_audio_generator.py - Generates silent/minimal audio for FLOAT idle clips

import os
import wave
import numpy as np
from colorama import Fore, Style, init
from typing import Optional

init(autoreset=True)

class IdleAudioGenerator:
    """
    Generates silent or near-silent audio files for FLOAT idle animation.
    The audio is essentially silent but has the proper format for FLOAT to process.
    """
    
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.temp_dir = os.path.join(project_dir, "tempstream")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Audio settings
        self.sample_rate = 16000  # Match FLOAT's expected sample rate
        self.channels = 1  # Mono
        self.sample_width = 2  # 16-bit
        
        print(f"{Fore.GREEN}[IDLE_AUDIO] Idle audio generator initialized{Style.RESET_ALL}")
    
    def generate_silent_audio(self, duration: float = 5.0, output_filename: Optional[str] = None) -> str:
        """
        Generate a silent audio file.
        
        Args:
            duration: Duration in seconds (default 5.0)
            output_filename: Optional output filename (auto-generated if None)
            
        Returns:
            Path to the generated audio file
        """
        if output_filename is None:
            import time
            timestamp = int(time.time() * 1000)
            output_filename = f"idle_silent_{timestamp}.wav"
        
        # Ensure .wav extension
        if not output_filename.endswith('.wav'):
            output_filename += '.wav'
        
        output_path = os.path.join(self.temp_dir, output_filename)
        
        try:
            # Generate silent audio (all zeros)
            num_samples = int(self.sample_rate * duration)
            silent_audio = np.zeros(num_samples, dtype=np.int16)
            
            # Write to WAV file
            with wave.open(output_path, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.sample_width)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(silent_audio.tobytes())
            
            print(f"{Fore.CYAN}[IDLE_AUDIO] Generated silent audio: {output_filename} ({duration}s){Style.RESET_ALL}")
            return output_path
            
        except Exception as e:
            print(f"{Fore.RED}[IDLE_AUDIO] Error generating silent audio: {e}{Style.RESET_ALL}")
            return None
    
    def generate_ambient_audio(self, duration: float = 5.0, amplitude: float = 0.0001, 
                               output_filename: Optional[str] = None) -> str:
        """
        Generate very quiet ambient noise (optional - can make FLOAT animation more natural).
        
        Args:
            duration: Duration in seconds (default 5.0)
            amplitude: Noise amplitude (very low, default 0.0001)
            output_filename: Optional output filename (auto-generated if None)
            
        Returns:
            Path to the generated audio file
        """
        if output_filename is None:
            import time
            timestamp = int(time.time() * 1000)
            output_filename = f"idle_ambient_{timestamp}.wav"
        
        # Ensure .wav extension
        if not output_filename.endswith('.wav'):
            output_filename += '.wav'
        
        output_path = os.path.join(self.temp_dir, output_filename)
        
        try:
            # Generate very quiet white noise
            num_samples = int(self.sample_rate * duration)
            noise = np.random.normal(0, amplitude, num_samples)
            
            # Convert to 16-bit PCM
            audio_int16 = (noise * 32767).astype(np.int16)
            
            # Write to WAV file
            with wave.open(output_path, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.sample_width)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_int16.tobytes())
            
            print(f"{Fore.CYAN}[IDLE_AUDIO] Generated ambient audio: {output_filename} ({duration}s){Style.RESET_ALL}")
            return output_path
            
        except Exception as e:
            print(f"{Fore.RED}[IDLE_AUDIO] Error generating ambient audio: {e}{Style.RESET_ALL}")
            return None
    
    def cleanup_old_files(self, keep_last: int = 10):
        """Clean up old idle audio files to save space"""
        try:
            files = []
            for file in os.listdir(self.temp_dir):
                if file.startswith('idle_') and file.endswith('.wav'):
                    file_path = os.path.join(self.temp_dir, file)
                    files.append((file_path, os.path.getmtime(file_path)))
            
            # Sort by modification time (newest first)
            files.sort(key=lambda x: x[1], reverse=True)
            
            # Delete old files
            for file_path, _ in files[keep_last:]:
                try:
                    os.remove(file_path)
                    print(f"{Fore.YELLOW}[IDLE_AUDIO] Cleaned up: {os.path.basename(file_path)}{Style.RESET_ALL}")
                except:
                    pass
                    
        except Exception as e:
            print(f"{Fore.RED}[IDLE_AUDIO] Error cleaning up files: {e}{Style.RESET_ALL}")


# Test the generator
if __name__ == "__main__":
    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Testing Idle Audio Generator{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
    
    # Create generator (using temp directory for testing)
    import tempfile
    test_dir = tempfile.mkdtemp()
    generator = IdleAudioGenerator(test_dir)
    
    # Test silent audio
    print(f"{Fore.CYAN}Generating silent audio...{Style.RESET_ALL}")
    silent_path = generator.generate_silent_audio(duration=5.0)
    
    if silent_path and os.path.exists(silent_path):
        print(f"{Fore.GREEN}✓ Silent audio created: {silent_path}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}  Size: {os.path.getsize(silent_path)} bytes{Style.RESET_ALL}")
    
    # Test ambient audio
    print(f"\n{Fore.CYAN}Generating ambient audio...{Style.RESET_ALL}")
    ambient_path = generator.generate_ambient_audio(duration=5.0)
    
    if ambient_path and os.path.exists(ambient_path):
        print(f"{Fore.GREEN}✓ Ambient audio created: {ambient_path}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}  Size: {os.path.getsize(ambient_path)} bytes{Style.RESET_ALL}")
    
    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Test complete!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
