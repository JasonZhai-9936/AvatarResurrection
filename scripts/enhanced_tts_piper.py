# enhanced_tts_piper.py - Clean TTS with complete audio generation

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

# Default voice model path
DEFAULT_VOICE_PATH = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-northern_english_male-medium")

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

def set_voice_model(voice_path: str):
    """Set a new voice model path"""
    global _voice_instance, _current_voice_path
    
    with _voice_load_lock:
        if voice_path != _current_voice_path:
            print(f"{Fore.CYAN}[TTS] Switching to voice model: {voice_path}{Style.RESET_ALL}")
            _voice_instance = None
            _current_voice_path = voice_path

def get_voice_instance(voice_path: str = None):
    """Get or create a voice instance"""
    global _voice_instance, _current_voice_path
    
    if voice_path is None:
        voice_path = _current_voice_path or DEFAULT_VOICE_PATH
    
    if _voice_instance is None or _current_voice_path != voice_path:
        with _voice_load_lock:
            if _voice_instance is None or _current_voice_path != voice_path:
                config = load_config()
                use_cuda = config['use_cuda']
                
                print(f"{Fore.CYAN}[TTS] Loading voice: {os.path.basename(voice_path)}{Style.RESET_ALL}")
                
                if not os.path.exists(voice_path):
                    if voice_path != DEFAULT_VOICE_PATH and os.path.exists(DEFAULT_VOICE_PATH):
                        voice_path = DEFAULT_VOICE_PATH
                    else:
                        raise FileNotFoundError(f"Voice model not found: {voice_path}")
                
                _voice_instance = PiperVoice.load(voice_path, use_cuda=use_cuda)
                _current_voice_path = voice_path
                print(f"{Fore.GREEN}[TTS] Voice loaded successfully{Style.RESET_ALL}")
    
    return _voice_instance

def ensure_temp_directory():
    """Ensure temp directory exists"""
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def generate_complete_audio(text: str, output_filename: str = None, voice_path: str = None) -> str:
    """Generate complete audio file for lipsync"""
    if not text or not text.strip():
        return None
    
    temp_dir = ensure_temp_directory()
    if output_filename is None:
        timestamp = int(time.time() * 1000)
        output_filename = f"darwin_complete_{timestamp}"
    
    output_path = os.path.join(temp_dir, f"{output_filename}.wav")
    
    try:
        voice = get_voice_instance(voice_path)
        
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=1.0,
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True
        )
        
        print(f"{Fore.BLUE}[TTS] Generating complete audio...{Style.RESET_ALL}")
        
        audio_chunks = []
        for chunk in voice.synthesize(text, syn_config=syn_config):
            audio_chunks.append(chunk)
        
        # Write complete audio to file
        if audio_chunks:
            with wave.open(output_path, 'wb') as wav_file:
                first_chunk = audio_chunks[0]
                wav_file.setnchannels(first_chunk.sample_channels)
                wav_file.setsampwidth(first_chunk.sample_width)
                wav_file.setframerate(first_chunk.sample_rate)
                
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk.audio_int16_bytes)
        
        print(f"{Fore.GREEN}[TTS] Complete audio saved: {output_path}{Style.RESET_ALL}")
        return output_path
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error generating audio: {e}{Style.RESET_ALL}")
        return None

def test_tts_system():
    """Test the TTS system"""
    try:
        voices_dir = os.path.join(PROJECT_DIR, "Piper_Voices")
        if not os.path.exists(voices_dir):
            return False
        
        voice_files = [f for f in os.listdir(voices_dir) if f.endswith('.onnx')]
        if not voice_files:
            return False
        
        # Try to load a voice
        test_voice = os.path.join(voices_dir, voice_files[0])
        voice = get_voice_instance(test_voice)
        
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
    test_message = "Everything in your life is a reflection of a choice you have made. If you want a different result, make a different choice"
    
    print(f"{Fore.CYAN}Test Message: {test_message}{Style.RESET_ALL}\n")
    
    # Run system test first
    print(f"{Fore.MAGENTA}Running system diagnostics...{Style.RESET_ALL}")
    if test_tts_system():
        print(f"{Fore.GREEN}✓ System check passed{Style.RESET_ALL}\n")
        
        # Generate audio
        print(f"{Fore.MAGENTA}Generating audio file...{Style.RESET_ALL}")
        output_file = generate_complete_audio(test_message, output_filename="standalone_test")
        
        if output_file:
            print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}✓ Success! Audio file generated:{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  {output_file}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}✗ Failed to generate audio file{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}✗ System check failed{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please ensure voice models are installed in the Piper_Voices directory{Style.RESET_ALL}")