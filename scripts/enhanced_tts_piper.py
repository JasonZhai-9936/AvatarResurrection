# enhanced_tts_piper.py - Clean TTS with complete audio generation
# FIXED: Robust .wav extension handling to prevent .wav.wav duplicates
# FIXED: Prevents double .wav extensions (e.g., .wav.wav)
# FIXED: Robust voice model loading from Piper_Voices directory

import time
import os
import json
import threading
import wave
from piper import PiperVoice, SynthesisConfig
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Default voice model path - Pointing explicitly to Piper_Voices
DEFAULT_VOICE_PATH = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-northern_english_male-medium.onnx")

# Global voice instance
_voice_instance = None
_current_voice_path = None
_voice_load_lock = threading.Lock()

def load_config():
    """Load TTS settings from config.json"""
    try:
        config_file = os.path.join(PROJECT_DIR, "config.json")
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {
                'use_cuda': config.get("useCuda", True),
                'max_words': config.get("maxWords", 50)
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {'use_cuda': True, 'max_words': 50}

def get_voice_instance(voice_path: str = None):
    """Get or create a voice instance"""
    global _voice_instance, _current_voice_path
    
    # Use default if none provided or if it's just a generic name request
    if voice_path is None:
        voice_path = _current_voice_path or DEFAULT_VOICE_PATH
    
    # If the path is just a filename (not a full path), look in Piper_Voices
    if not os.path.isabs(voice_path) and not os.path.exists(voice_path):
        potential_path = os.path.join(PROJECT_DIR, "Piper_Voices", os.path.basename(voice_path))
        if os.path.exists(potential_path):
            voice_path = potential_path
    
    if _voice_instance is None or _current_voice_path != voice_path:
        with _voice_load_lock:
            # Double-check inside lock
            if _voice_instance is None or _current_voice_path != voice_path:
                config = load_config()
                use_cuda = config['use_cuda']
                
                print(f"{Fore.CYAN}[TTS] Loading voice: {os.path.basename(voice_path)}{Style.RESET_ALL}")
                
                if not os.path.exists(voice_path):
                    # Final fallback to default if specific request fails
                    if voice_path != DEFAULT_VOICE_PATH and os.path.exists(DEFAULT_VOICE_PATH):
                        print(f"{Fore.YELLOW}[TTS] Requested voice not found, falling back to default.{Style.RESET_ALL}")
                        voice_path = DEFAULT_VOICE_PATH
                    else:
                        raise FileNotFoundError(f"Voice model not found: {voice_path}")
                
                try:
                    # Check for config file (.json)
                    config_path = voice_path + ".json"
                    # Handle case where file is .onnx but config is just .json (without .onnx in name)
                    if not os.path.exists(config_path):
                        alt_config = voice_path.replace(".onnx", ".json")
                        if os.path.exists(alt_config):
                            config_path = alt_config
                            
                    _voice_instance = PiperVoice.load(voice_path, config_path=config_path if os.path.exists(config_path) else None, use_cuda=use_cuda)
                    _current_voice_path = voice_path
                    print(f"{Fore.GREEN}[TTS] Voice loaded successfully{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}[TTS] Failed to load voice model: {e}{Style.RESET_ALL}")
                    _voice_instance = None
                    raise e
    
    return _voice_instance

def ensure_temp_directory():
    """Ensure temp directory exists"""
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def normalize_filename(filename: str) -> str:
    """
    Normalize filename to ensure exactly one .wav extension
    Handles cases like:
    - "file" -> "file.wav"
    - "file.wav" -> "file.wav"
    - "file.wav.wav" -> "file.wav"
    """
    # Remove all .wav extensions
    while filename.lower().endswith('.wav'):
        filename = filename[:-4]
    
    # Add exactly one .wav extension
    return filename + '.wav'

def generate_complete_audio(text: str, output_filename: str = None, voice_path: str = None) -> str:
    """Generate complete audio file for lipsync"""
    if not text or not text.strip():
        return None
    
    temp_dir = ensure_temp_directory()
    if output_filename is None:
        timestamp = int(time.time() * 1000)
        output_filename = f"darwin_complete_{timestamp}"
    
    # === ROBUST FIX: Normalize filename to have exactly one .wav extension ===
    output_filename = normalize_filename(output_filename)
    output_path = os.path.join(temp_dir, output_filename)
    
    print(f"{Fore.CYAN}[TTS] Generating: {output_filename}{Style.RESET_ALL}")
    
    try:
        voice = get_voice_instance(voice_path)
        
        # REMOVED sentence_silence to fix crash
        syn_config = SynthesisConfig(
            length_scale=1.0,
            noise_scale=0.667, 
            noise_w_scale=0.8
        )
        
        # Open wave file
        with wave.open(output_path, 'wb') as wav_file:
            wav_file.setnchannels(1) # Mono
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(22050) # Standard Piper sample rate (will be updated by first chunk)
            
            first_chunk_received = False
            
            for chunk in voice.synthesize(text, syn_config=syn_config):
                if not first_chunk_received:
                    wav_file.setframerate(chunk.sample_rate)
                    first_chunk_received = True
                wav_file.writeframes(chunk.audio_int16_bytes)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"{Fore.GREEN}[TTS] Audio saved: {output_filename}{Style.RESET_ALL}")
            return output_path
        else:
            print(f"{Fore.RED}[TTS] Audio file created but is empty.{Style.RESET_ALL}")
            return None
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error generating audio: {e}{Style.RESET_ALL}")
        return None

def test_tts_system():
    """Test the TTS system"""
    try:
        voices_dir = os.path.join(PROJECT_DIR, "Piper_Voices")
        if not os.path.exists(voices_dir):
            print(f"{Fore.RED}[TTS] Piper_Voices directory missing at {voices_dir}{Style.RESET_ALL}")
            return False
        
        voice_files = [f for f in os.listdir(voices_dir) if f.endswith('.onnx')]
        if not voice_files:
            print(f"{Fore.RED}[TTS] No .onnx voice files found in Piper_Voices{Style.RESET_ALL}")
            return False
        
        # Try to load the first available voice
        test_voice_path = os.path.join(voices_dir, voice_files[0])
        print(f"{Fore.CYAN}[TTS] Testing with voice: {voice_files[0]}{Style.RESET_ALL}")
        
        voice = get_voice_instance(test_voice_path)
        
        print(f"{Fore.GREEN}[TTS] System test passed{Style.RESET_ALL}")
        return True
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] System test failed: {e}{Style.RESET_ALL}")
        return False


# Standalone execution
if __name__ == "__main__":
    print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}TTS System - Standalone Test Mode{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}\n")
    
    # Custom test message
    test_message = "That's a good question."
    
    print(f"{Fore.CYAN}Test Message: {test_message}{Style.RESET_ALL}\n")
    
    # Run system test first
    print(f"{Fore.MAGENTA}Running system diagnostics...{Style.RESET_ALL}")
    if test_tts_system():
        print(f"{Fore.GREEN}✓ System check passed{Style.RESET_ALL}\n")
        
        # Generate audio - test with various extension scenarios
        print(f"{Fore.MAGENTA}Testing extension handling...{Style.RESET_ALL}")
        
        # Test 1: No extension
        test1 = generate_complete_audio(test_message, output_filename="test_no_ext")
        print(f"Test 1 (no ext): {test1}")
        
        # Test 2: With .wav
        test2 = generate_complete_audio(test_message, output_filename="test_with_ext.wav")
        print(f"Test 2 (with .wav): {test2}")
        
        # Test 3: With .wav.wav (should fix)
        test3 = generate_complete_audio(test_message, output_filename="test_double.wav.wav")
        print(f"Test 3 (double .wav): {test3}")
        
        if all([test1, test2, test3]):
            print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}✓ All tests passed!{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}✗ Some tests failed{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}✗ System check failed{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please ensure voice models are installed in the Piper_Voices directory{Style.RESET_ALL}")