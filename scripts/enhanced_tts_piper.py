# enhanced_tts_piper.py - Enhanced TTS with both streaming and complete audio generation

import time
import os
import json
import threading
import simpleaudio as sa
from piper import PiperVoice, SynthesisConfig
from colorama import Fore, Style, init
import wave

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Initialize colorama for colored terminal output
init(autoreset=True)

# Default voice model path
DEFAULT_VOICE_PATH = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-northern_english_male-medium")

# Global voice instance and path for reuse
_voice_instance = None
_current_voice_path = None
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

def set_voice_model(voice_path: str):
    """Set a new voice model path and reset the voice instance."""
    global _voice_instance, _current_voice_path
    
    with _voice_load_lock:
        if voice_path != _current_voice_path:
            print(f"{Fore.CYAN}[TTS] Switching to voice model: {voice_path}{Style.RESET_ALL}")
            _voice_instance = None  # Reset instance to force reload
            _current_voice_path = voice_path

def get_voice_instance(voice_path: str = None):
    """Get or create a voice instance (thread-safe singleton)."""
    global _voice_instance, _current_voice_path
    
    # Use provided path or default
    if voice_path is None:
        voice_path = _current_voice_path or DEFAULT_VOICE_PATH
    
    # Check if we need to load/reload the voice
    if _voice_instance is None or _current_voice_path != voice_path:
        with _voice_load_lock:
            # Double-check pattern
            if _voice_instance is None or _current_voice_path != voice_path:
                config = load_config()
                use_cuda = config['use_cuda']
                
                print(f"{Fore.CYAN}[TTS] Loading Piper voice model: {os.path.basename(voice_path)}...{Style.RESET_ALL}")
                print(f"{Fore.CYAN}[TTS] Using CUDA: {use_cuda}{Style.RESET_ALL}")
                
                if not os.path.exists(voice_path):
                    print(f"{Fore.RED}[TTS] Voice model not found: {voice_path}{Style.RESET_ALL}")
                    # Fallback to default voice
                    if voice_path != DEFAULT_VOICE_PATH and os.path.exists(DEFAULT_VOICE_PATH):
                        print(f"{Fore.YELLOW}[TTS] Falling back to default voice: {DEFAULT_VOICE_PATH}{Style.RESET_ALL}")
                        voice_path = DEFAULT_VOICE_PATH
                    else:
                        raise FileNotFoundError(f"Voice model not found at: {voice_path}")
                
                t0 = time.time()
                _voice_instance = PiperVoice.load(voice_path, use_cuda=use_cuda)
                _current_voice_path = voice_path
                load_time = time.time() - t0
                print(f"{Fore.GREEN}[TTS] Voice model loaded in {load_time:.2f}s{Style.RESET_ALL}")
    
    return _voice_instance

def ensure_temp_directory():
    """Ensure the temporary audio directory exists."""
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def generate_complete_audio(text: str, output_filename: str = None, voice_path: str = None) -> str:
    """
    Generate complete audio file without streaming/playback - for lipsync integration.
    
    Args:
        text: Text to convert to speech
        output_filename: Optional custom filename (without extension)
        voice_path: Optional specific voice model to use
    
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
        output_filename = f"darwin_complete_{timestamp}"
    
    output_path = os.path.join(temp_dir, f"{output_filename}.wav")
    
    try:
        # Get voice instance (with optional specific voice)
        voice = get_voice_instance(voice_path)
        
        # Configure synthesis
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=1.0,  # Normal speed
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True
        )
        
        current_voice_name = os.path.basename(_current_voice_path or "unknown")
        print(f"{Fore.BLUE}[TTS] Starting complete audio generation with {current_voice_name}...{Style.RESET_ALL}")
        print(f"{Fore.BLUE}[TTS] Text: {text[:50]}{'...' if len(text) > 50 else ''}{Style.RESET_ALL}")
        
        generation_start = time.time()
        audio_chunks = []  # Store all chunks
        
        # Generate all audio chunks without playback
        for i, chunk in enumerate(voice.synthesize(text, syn_config=syn_config), start=1):
            audio_chunks.append(chunk)
            elapsed = time.time() - generation_start
            duration = len(chunk.audio_int16_bytes) / (
                chunk.sample_rate * chunk.sample_channels * chunk.sample_width
            )
            print(f"{Fore.MAGENTA}[TTS] Generated chunk {i}: {duration:.2f}s (Total: {elapsed:.2f}s){Style.RESET_ALL}")
        
        # Write complete audio to file
        if audio_chunks:
            print(f"{Fore.CYAN}[TTS] Writing complete audio to file: {output_path}{Style.RESET_ALL}")
            
            with wave.open(output_path, 'wb') as wav_file:
                # Use properties from first chunk
                first_chunk = audio_chunks[0]
                wav_file.setnchannels(first_chunk.sample_channels)
                wav_file.setsampwidth(first_chunk.sample_width)
                wav_file.setframerate(first_chunk.sample_rate)
                
                # Write all chunks
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk.audio_int16_bytes)
        
        total_time = time.time() - generation_start
        print(f"{Fore.GREEN}[TTS] Complete audio generation finished in {total_time:.2f}s{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[TTS] Audio saved to: {output_path}{Style.RESET_ALL}")
        
        return output_path
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error in complete audio generation: {e}{Style.RESET_ALL}")
        return None

def generate_and_stream_audio(text: str, output_filename: str = None, voice_path: str = None) -> str:
    """
    Generate and stream audio from text using Piper TTS (original streaming version).
    
    Args:
        text: Text to convert to speech
        output_filename: Optional custom filename (without extension)
        voice_path: Optional specific voice model to use
    
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
        # Get voice instance (with optional specific voice)
        voice = get_voice_instance(voice_path)
        
        # Configure synthesis
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=1.0,  # Normal speed
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True
        )
        
        current_voice_name = os.path.basename(_current_voice_path or "unknown")
        print(f"{Fore.BLUE}[TTS] Starting streaming synthesis and playback with {current_voice_name}...{Style.RESET_ALL}")
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
        
        # Check available voices
        voices_dir = os.path.join(PROJECT_DIR, "Piper_Voices")
        available_voices = []
        
        if os.path.exists(voices_dir):
            for file in os.listdir(voices_dir):
                if file.endswith('.onnx'):
                    available_voices.append(os.path.join(voices_dir, file))
        
        if not available_voices:
            print(f"{Fore.RED}[TTS TEST] No voice models found in Piper_Voices directory{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.GREEN}[TTS TEST] Found {len(available_voices)} voice model(s){Style.RESET_ALL}")
        
        # Test with default voice
        default_voice = available_voices[0] if available_voices else DEFAULT_VOICE_PATH
        if not os.path.exists(default_voice):
            print(f"{Fore.RED}[TTS TEST] Default voice model not found at: {default_voice}{Style.RESET_ALL}")
            return False
        
        # Try to load voice instance
        try:
            voice = get_voice_instance(default_voice)
            print(f"{Fore.GREEN}[TTS TEST] Voice model loaded successfully: {os.path.basename(default_voice)}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[TTS TEST] Failed to load voice model: {e}{Style.RESET_ALL}")
            return False
        
        # Test complete audio generation (no playback in test)
        temp_dir = ensure_temp_directory()
        print(f"{Fore.GREEN}[TTS TEST] Temp directory ready: {temp_dir}{Style.RESET_ALL}")
        
        # Test the complete audio generation function
        test_audio_path = generate_complete_audio(test_text, "test_complete")
        if test_audio_path and os.path.exists(test_audio_path):
            print(f"{Fore.GREEN}[TTS TEST] Complete audio generation test passed: {test_audio_path}{Style.RESET_ALL}")
            # Clean up test file
            try:
                os.remove(test_audio_path)
            except:
                pass
        else:
            print(f"{Fore.RED}[TTS TEST] Complete audio generation test failed{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.GREEN}[TTS TEST] All TTS components verified successfully.{Style.RESET_ALL}")
        return True
        
    except Exception as e:
        print(f"{Fore.RED}[TTS TEST] Test failed with error: {e}{Style.RESET_ALL}")
        return False

def get_available_voices():
    """Get list of available voice models from Piper_Voices directory."""
    voices_dir = os.path.join(PROJECT_DIR, "Piper_Voices")
    voices = []
    
    if os.path.exists(voices_dir):
        for file in os.listdir(voices_dir):
            if file.endswith('.onnx'):
                voices.append(os.path.join(voices_dir, file))
    
    return voices

if __name__ == "__main__":
    print(f"{Fore.GREEN}{'=' * 50}")
    print(f"{Fore.YELLOW}Enhanced Piper TTS with Complete Audio Generation")
    print(f"{Fore.GREEN}{'=' * 50}{Style.RESET_ALL}")
    
    # Test the system
    success = test_tts_system()
    
    if success:
        print(f"\n{Fore.GREEN}Enhanced TTS system is working correctly!{Style.RESET_ALL}")
        
        # Interactive test
        print(f"\n{Fore.CYAN}Choose test mode:{Style.RESET_ALL}")
        print(f"1. Complete audio generation (for lipsync)")
        print(f"2. Streaming audio with playback (original)")
        print(f"3. Exit")
        
        try:
            choice = input(f"\n{Fore.CYAN}Enter choice (1-3): {Style.RESET_ALL}")
            
            if choice == "1":
                test_text = input(f"{Fore.CYAN}Enter text for complete audio generation: {Style.RESET_ALL}")
                if test_text.strip():
                    result = generate_complete_audio(test_text)
                    if result:
                        print(f"{Fore.GREEN}Complete audio generated successfully: {result}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}Complete audio generation failed.{Style.RESET_ALL}")
            
            elif choice == "2":
                test_text = input(f"{Fore.CYAN}Enter text for streaming audio: {Style.RESET_ALL}")
                if test_text.strip():
                    result = generate_and_stream_audio(test_text)
                    if result:
                        print(f"{Fore.GREEN}Streaming audio completed: {result}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}Streaming audio failed.{Style.RESET_ALL}")
            
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Goodbye!{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}Enhanced TTS system test failed. Please check your configuration.{Style.RESET_ALL}")