# enhanced_tts_groq.py - TTS using Groq API with Fritz-PlayAI voice

import time
import os
import json
from groq import Groq
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Global Groq client
_groq_client = None

def load_groq_api_key():
    """Load Groq API key from file in project root"""
    api_key_file = os.path.join(PROJECT_DIR, "groq_api_key.txt")
    
    try:
        with open(api_key_file, 'r', encoding='utf-8') as f:
            api_key = f.read().strip()
            return api_key
    except FileNotFoundError:
        raise FileNotFoundError(f"API key file not found: {api_key_file}")

def load_config():
    """Load TTS settings from config.json"""
    try:
        config_file = os.path.join(PROJECT_DIR, "config.json")
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {
                'max_words': config.get("maxWords", 50)
            }
    except (FileNotFoundError, json.JSONDecodeError):
        return {'max_words': 50}

def get_groq_client():
    """Get or create Groq client instance"""
    global _groq_client
    
    if _groq_client is None:
        api_key = load_groq_api_key()
        _groq_client = Groq(api_key=api_key)
        print(f"{Fore.GREEN}[TTS] Groq client initialized{Style.RESET_ALL}")
    
    return _groq_client

def ensure_temp_directory():
    """Ensure temp directory exists"""
    temp_dir = os.path.join(PROJECT_DIR, "tempstream")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def set_voice_model(voice_name: str):
    """Set voice model (for compatibility - Groq uses Basil-PlayAI)"""
    print(f"{Fore.CYAN}[TTS] Voice setting: {voice_name} (using Basil-PlayAI){Style.RESET_ALL}")

def generate_complete_audio(text: str, output_filename: str = None, voice_path: str = None) -> str:
    """Generate complete audio file using Groq TTS API"""
    if not text or not text.strip():
        return None
    
    temp_dir = ensure_temp_directory()
    if output_filename is None:
        timestamp = int(time.time() * 1000)
        output_filename = f"darwin_complete_{timestamp}"
    
    # Ensure .wav extension
    if not output_filename.endswith('.wav'):
        output_path = os.path.join(temp_dir, f"{output_filename}.wav")
    else:
        output_path = os.path.join(temp_dir, output_filename)
    
    try:
        client = get_groq_client()
        
        print(f"{Fore.BLUE}[TTS] Generating audio with Groq API (Basil-PlayAI)...{Style.RESET_ALL}")
        
        # Call Groq TTS API
        response = client.audio.speech.create(
            model="playai-tts",
            voice="Basil-PlayAI",
            input=text,
            response_format="wav"
        )
        
        # Write audio to file using the response method
        response.write_to_file(output_path)
        
        print(f"{Fore.GREEN}[TTS] Audio saved: {output_path}{Style.RESET_ALL}")
        return output_path
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error generating audio: {e}{Style.RESET_ALL}")
        return None

def test_tts_system():
    """Test the TTS system"""
    try:
        client = get_groq_client()
        print(f"{Fore.GREEN}[TTS] Groq client initialized{Style.RESET_ALL}")
        
        # Try a simple test generation
        test_text = "Testing Groq TTS system with Fritz voice."
        result = generate_complete_audio(test_text, "test_audio")
        
        if result and os.path.exists(result):
            print(f"{Fore.GREEN}[TTS] System test passed - audio generated at {result}{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}[TTS] System test failed - no audio file created{Style.RESET_ALL}")
            return False
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] System test failed: {e}{Style.RESET_ALL}")
        return False


# For backward compatibility with the original module
def get_voice_instance(voice_path: str = None):
    """Get Groq client (for compatibility with original interface)"""
    return get_groq_client()


if __name__ == "__main__":
    """Test the TTS system when run directly"""
    print(f"\n{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}Testing Groq TTS with Fritz-PlayAI voice")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}\n")
    
    # Sample sentence for testing
    test_sentence = "Hmmm...That's a good question."
    
    print(f"{Fore.CYAN}Test sentence: {test_sentence}{Style.RESET_ALL}\n")
    
    try:
        # Generate audio
        audio_file = generate_complete_audio(test_sentence, "darwin_test")
        
        if audio_file and os.path.exists(audio_file):
            print(f"\n{Fore.GREEN}{'=' * 60}")
            print(f"{Fore.GREEN}✓ Success! Audio file created:{Style.RESET_ALL}")
            print(f"{Fore.CYAN}  {audio_file}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}\n")
        else:
            print(f"\n{Fore.RED}✗ Failed to create audio file{Style.RESET_ALL}\n")
    
    except Exception as e:
        print(f"\n{Fore.RED}✗ Error during test: {e}{Style.RESET_ALL}\n")
        import traceback
        traceback.print_exc()