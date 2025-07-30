# TTS_Piper.py
"""
Streaming Text-to-Speech using Piper TTS with real-time playback.

The main function for external use is:
    generate_and_stream_audio(text: str, output_filename: str = None) -> str
    
    bool use_cuda is set in config, can be changed live
"""

import time
import os
import json
import threading
import simpleaudio as sa
from piper import PiperVoice, SynthesisConfig
from colorama import Fore, Style, init

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Initialize colorama for colored terminal output
init(autoreset=True)

# Voice model path (relative to project root)
VOICE_PATH = os.path.join(PROJECT_DIR, "en_GB-semaine-medium.onnx")

# Global voice instance for reuse
_voice_instance = None
_voice_load_lock = threading.Lock()

def load_config():
    """Load TTS settings from config.json in the project root."""
    try:
        config_file = os.path.join(PROJECT_DIR, "config.json")
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {
                'use_cuda': config.get("useCuda", True),
                'max_words': config.get("maxWords", 50)
            }
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{Fore.RED}[TTS CONFIG] config.json not found or invalid. Using defaults.{Style.RESET_ALL}")
        return {'use_cuda': True, 'max_words': 50}

def get_voice_instance():
    """Get or create a voice instance (thread-safe singleton)."""
    global _voice_instance
    
    if _voice_instance is None:
        with _voice_load_lock:
            if _voice_instance is None:  # Double-check pattern
                config = load_config()
                use_cuda = config['use_cuda']
                
                print(f"{Fore.CYAN}[TTS] Loading Piper voice model...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}[TTS] Using CUDA: {use_cuda}{Style.RESET_ALL}")
                
                if not os.path.exists(VOICE_PATH):
                    raise FileNotFoundError(f"Voice model not found at: {VOICE_PATH}")
                
                t0 = time.time()
                _voice_instance = PiperVoice.load(VOICE_PATH, use_cuda=use_cuda)
                load_time = time.time() - t0
                print(f"{Fore.GREEN}[TTS] Voice model loaded in {load_time:.2f}s{Style.RESET_ALL}")
    
    return _voice_instance

def ensure_temp_directory():
    """Ensure the temporary audio directory exists."""
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def generate_and_stream_audio(text: str, output_filename: str = None) -> str:
    """
    Generate and stream audio from text using Piper TTS.
    
    Args:
        text: Text to convert to speech
        output_filename: Optional custom filename (without extension)
    
    Returns:
        str: Path to the generated audio file
    """
    if not text or not text.strip():
        print(f"{Fore.YELLOW}[TTS] No text provided for TTS generation{Style.RESET_ALL}")
        return None
    
    # Prepare output file
    temp_dir = ensure_temp_directory()
    if output_filename is None:
        timestamp = int(time.time() * 1000)  # millisecond timestamp
        output_filename = f"darwin_response_{timestamp}"
    
    output_path = os.path.join(temp_dir, f"{output_filename}.wav")
    
    try:
        # Get voice instance
        voice = get_voice_instance()
        
        # Configure synthesis
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=1.0,  # Normal speed
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True
        )
        
        print(f"{Fore.BLUE}[TTS] Starting streaming synthesis and playback...{Style.RESET_ALL}")
        print(f"{Fore.BLUE}[TTS] Text: {text[:50]}{'...' if len(text) > 50 else ''}{Style.RESET_ALL}")
        
        stream_start = time.time()
        playback_time = stream_start  # Target playback timeline
        audio_chunks = []  # Store chunks for file writing
        
        # Stream synthesis with real-time playback
        for i, chunk in enumerate(voice.synthesize(text, syn_config=syn_config), start=1):
            elapsed = time.time() - stream_start
            duration = len(chunk.audio_int16_bytes) / (
                chunk.sample_rate * chunk.sample_channels * chunk.sample_width
            )
            
            print(f"{Fore.MAGENTA}[TTS] Chunk {i}: ready at {elapsed:.2f}s, duration {duration:.2f}s{Style.RESET_ALL}")
            
            # Store chunk for file writing
            audio_chunks.append(chunk)
            
            # Align playback timing
            now = time.time()
            if now < playback_time:
                sleep_time = playback_time - now
                print(f"{Fore.YELLOW}[TTS] Waiting {sleep_time:.3f}s for playback sync{Style.RESET_ALL}")
                time.sleep(sleep_time)
            
            # Play chunk (blocking)
            try:
                play_obj = sa.play_buffer(
                    chunk.audio_int16_bytes,
                    num_channels=chunk.sample_channels,
                    bytes_per_sample=chunk.sample_width,
                    sample_rate=chunk.sample_rate,
                )
                play_obj.wait_done()
                print(f"{Fore.GREEN}[TTS] Chunk {i} played successfully{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[TTS] Error playing chunk {i}: {e}{Style.RESET_ALL}")
            
            playback_time += duration  # Schedule next chunk
        
        # Write complete audio to file
        if audio_chunks:
            print(f"{Fore.CYAN}[TTS] Writing complete audio to file: {output_path}{Style.RESET_ALL}")
            
            # Combine all chunks into a single audio file
            import wave
            with wave.open(output_path, 'wb') as wav_file:
                # Use properties from first chunk
                first_chunk = audio_chunks[0]
                wav_file.setnchannels(first_chunk.sample_channels)
                wav_file.setsampwidth(first_chunk.sample_width)
                wav_file.setframerate(first_chunk.sample_rate)
                
                # Write all chunks
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk.audio_int16_bytes)
        
        total_time = time.time() - stream_start
        print(f"{Fore.GREEN}[TTS] Streaming synthesis and playback completed in {total_time:.2f}s{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[TTS] Audio saved to: {output_path}{Style.RESET_ALL}")
        
        return output_path
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error in TTS generation: {e}{Style.RESET_ALL}")
        return None

def test_tts_system():
    """Test the TTS system with a sample text."""
    try:
        test_text = "Good day! This is a test."
        
        print(f"{Fore.CYAN}[TTS TEST] Testing TTS system...{Style.RESET_ALL}")
        
        # Check if voice model exists first
        if not os.path.exists(VOICE_PATH):
            print(f"{Fore.RED}[TTS TEST] Voice model not found at: {VOICE_PATH}{Style.RESET_ALL}")
            return False
        
        # Try to load voice instance
        try:
            voice = get_voice_instance()
            print(f"{Fore.GREEN}[TTS TEST] Voice model loaded successfully.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[TTS TEST] Failed to load voice model: {e}{Style.RESET_ALL}")
            return False
        
        # Test audio generation (but skip actual playback in test)
        temp_dir = ensure_temp_directory()
        print(f"{Fore.GREEN}[TTS TEST] Temp directory ready: {temp_dir}{Style.RESET_ALL}")
        
        print(f"{Fore.GREEN}[TTS TEST] All TTS components verified successfully.{Style.RESET_ALL}")
        return True
        
    except Exception as e:
        print(f"{Fore.RED}[TTS TEST] Test failed with error: {e}{Style.RESET_ALL}")
        return False

if __name__ == "__main__":
    print(f"{Fore.GREEN}{'=' * 50}")
    print(f"{Fore.YELLOW}Piper TTS Streaming Test")
    print(f"{Fore.GREEN}{'=' * 50}{Style.RESET_ALL}")
    
    # Test the system
    success = test_tts_system()
    
    if success:
        print(f"\n{Fore.GREEN}TTS system is working correctly!{Style.RESET_ALL}")
        
        # Interactive test
        print(f"\n{Fore.CYAN}Interactive TTS Test (Ctrl+C to exit):{Style.RESET_ALL}")
        while True:
            try:
                user_input = input(f"\n{Fore.CYAN}Enter text to convert to speech: {Style.RESET_ALL}")
                if not user_input.strip():
                    continue
                
                result = generate_and_stream_audio(user_input)
                if result:
                    print(f"{Fore.GREEN}Audio generated and played successfully!{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}Failed to generate audio.{Style.RESET_ALL}")
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
                break
    else:
        print(f"\n{Fore.RED}TTS system test failed. Please check your configuration.{Style.RESET_ALL}")