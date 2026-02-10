# orpheus_tts_groq.py - Groq Orpheus TTS Implementation
"""
Drop-in replacement for enhanced_tts_piper.py using Groq's Orpheus API.

Main function for external use:
    generate_complete_audio(text: str, output_filename: str) -> str
    
Usage:
    from orpheus_tts_groq import generate_complete_audio
    
    audio_path = generate_complete_audio("Hello world", "output.wav")
"""

import os
import sys
from pathlib import Path
from colorama import Fore, Style, init
from groq import Groq

init(autoreset=True)

# Set project directory
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "tempstream")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- CONFIGURATION ---
ORPHEUS_MODEL = "canopylabs/orpheus-v1-english"
ORPHEUS_VOICE = "austin"  # Options: autumn, diana, hannah, austin, daniel, troy
ORPHEUS_FORMAT = "wav"

# Global voice setting (can be changed with set_voice_model)
CURRENT_VOICE = ORPHEUS_VOICE

# Load Groq API key
def load_groq_api_key():
    """Load Groq API key from groq_api_key.txt"""
    api_key_file = os.path.join(PROJECT_DIR, "groq_api_key.txt")
    try:
        with open(api_key_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"{Fore.RED}[ORPHEUS_TTS] ERROR: groq_api_key.txt not found at {api_key_file}{Style.RESET_ALL}")
        raise
    except Exception as e:
        print(f"{Fore.RED}[ORPHEUS_TTS] ERROR loading API key: {e}{Style.RESET_ALL}")
        raise

# Initialize Groq client
groq_api_key = load_groq_api_key()
client = Groq(api_key=groq_api_key)

def set_voice_model(voice_identifier: str):
    """
    Set the voice for TTS generation.
    
    For Orpheus, this expects a voice name like 'austin', 'hannah', etc.
    The original Piper system used .onnx file paths, so this extracts the voice name.
    
    Args:
        voice_identifier: Either a voice name ('austin') or path ending in voice name
    """
    global CURRENT_VOICE
    
    # Extract voice name if it's a path
    if os.path.sep in voice_identifier or '/' in voice_identifier:
        # Extract filename without extension
        voice_name = Path(voice_identifier).stem
        # Remove common prefixes like 'en_GB-' or 'en_US-'
        if '-' in voice_name:
            parts = voice_name.split('-')
            # Try to find a valid Orpheus voice name in the parts
            orpheus_voices = ['autumn', 'diana', 'hannah', 'austin', 'daniel', 'troy']
            for part in parts:
                if part.lower() in orpheus_voices:
                    voice_name = part.lower()
                    break
    else:
        voice_name = voice_identifier.lower()
    
    # Validate voice
    valid_voices = ['autumn', 'diana', 'hannah', 'austin', 'daniel', 'troy']
    if voice_name not in valid_voices:
        print(f"{Fore.YELLOW}[ORPHEUS_TTS] Warning: '{voice_name}' not a valid Orpheus voice. Using default '{ORPHEUS_VOICE}'.{Style.RESET_ALL}")
        voice_name = ORPHEUS_VOICE
    
    CURRENT_VOICE = voice_name
    print(f"{Fore.GREEN}[ORPHEUS_TTS] Voice set to: {CURRENT_VOICE}{Style.RESET_ALL}")

def add_vocal_directions(text: str) -> str:
    """
    Add vocal directions to text for more expressive speech.
    
    Darwin's responses already contain filler words (umm, ah, er),
    so we add subtle directions to make it sound more natural and Victorian.
    
    Args:
        text: Raw text from LLM
        
    Returns:
        Text with vocal directions added
    """
    # Add a gentle, thoughtful tone at the start
    if not text.startswith('['):
        text = f"[thoughtful] {text}"
    
    # Add pauses and emphasis based on punctuation
    # You can customize this based on how you want Darwin to sound
    
    return text

def split_text_for_api(text: str, max_chars: int = 200) -> list:
    """
    Split text into chunks that fit within Orpheus's 200 character limit.
    Tries to split at sentence boundaries when possible.
    
    Args:
        text: Full text to split
        max_chars: Maximum characters per chunk (200 for Orpheus)
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by sentences
    sentences = text.replace('!', '.').replace('?', '.').split('.')
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If adding this sentence would exceed limit
        if len(current_chunk) + len(sentence) + 2 > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + "."
            else:
                # Single sentence is too long, split it by words
                words = sentence.split()
                temp_chunk = ""
                for word in words:
                    if len(temp_chunk) + len(word) + 1 <= max_chars:
                        temp_chunk += word + " "
                    else:
                        chunks.append(temp_chunk.strip())
                        temp_chunk = word + " "
                if temp_chunk:
                    current_chunk = temp_chunk
        else:
            current_chunk += sentence + ". "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def generate_complete_audio(text: str, output_filename: str) -> str:
    """
    Generate TTS audio using Groq's Orpheus API.
    
    This is a drop-in replacement for the Piper TTS generate_complete_audio function.
    
    Args:
        text: Text to convert to speech
        output_filename: Desired output filename (e.g., "chunk_darwin_msg_1_0.wav")
        
    Returns:
        str: Full path to the generated audio file, or None if failed
    """
    try:
        # Construct full output path
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        print(f"{Fore.CYAN}[TTS] Generating: {output_filename}{Style.RESET_ALL}")
        
        # Add vocal directions for more expressive speech
        enhanced_text = add_vocal_directions(text)
        
        # Split text if it exceeds 200 character limit
        text_chunks = split_text_for_api(enhanced_text, max_chars=200)
        
        if len(text_chunks) > 1:
            print(f"{Fore.YELLOW}[TTS] Text split into {len(text_chunks)} chunks due to length{Style.RESET_ALL}")
            
            # Generate audio for each chunk and concatenate
            import wave
            import io
            
            combined_frames = []
            params = None
            
            for i, chunk in enumerate(text_chunks):
                print(f"{Fore.CYAN}[TTS] Generating chunk {i+1}/{len(text_chunks)}: '{chunk[:50]}...'{Style.RESET_ALL}")
                
                response = client.audio.speech.create(
                    model=ORPHEUS_MODEL,
                    voice=CURRENT_VOICE,
                    input=chunk,
                    response_format=ORPHEUS_FORMAT
                )
                
                # Read the WAV data
                chunk_data = response.read()
                
                # Parse WAV file
                with wave.open(io.BytesIO(chunk_data), 'rb') as wav:
                    if params is None:
                        params = wav.getparams()
                    combined_frames.append(wav.readframes(wav.getnframes()))
            
            # Write combined audio
            with wave.open(output_path, 'wb') as output_wav:
                output_wav.setparams(params)
                for frames in combined_frames:
                    output_wav.writeframes(frames)
                    
        else:
            # Single chunk - direct write
            response = client.audio.speech.create(
                model=ORPHEUS_MODEL,
                voice=CURRENT_VOICE,
                input=enhanced_text,
                response_format=ORPHEUS_FORMAT
            )
            
            # Write audio to file
            response.write_to_file(output_path)
        
        print(f"{Fore.GREEN}[TTS] Audio saved: {output_filename}{Style.RESET_ALL}")
        
        # Verify file was created
        if not os.path.exists(output_path):
            print(f"{Fore.RED}[TTS] ERROR: File was not created at {output_path}{Style.RESET_ALL}")
            return None
            
        return output_path
        
    except Exception as e:
        print(f"{Fore.RED}[TTS] Error generating audio: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        return None

# --- COMPATIBILITY FUNCTIONS ---

def get_available_voices():
    """
    Return list of available Orpheus voices.
    
    Returns:
        list: Available voice names
    """
    return ['autumn', 'diana', 'hannah', 'austin', 'daniel', 'troy']

def get_current_voice():
    """
    Get the currently selected voice.
    
    Returns:
        str: Current voice name
    """
    return CURRENT_VOICE

# --- TESTING ---

if __name__ == "__main__":
    # Test the TTS system
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Orpheus TTS Test{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    test_text = "Good day to you, my dear fellow. Ah, yes, umm, it's quite fascinating to be in this digital realm."
    test_output = "test_orpheus_output.wav"
    
    print(f"\n{Fore.YELLOW}Testing with voice: {CURRENT_VOICE}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Text: {test_text}{Style.RESET_ALL}\n")
    
    result = generate_complete_audio(test_text, test_output)
    
    if result:
        print(f"\n{Fore.GREEN}✓ Test successful!{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Audio saved to: {result}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}✗ Test failed{Style.RESET_ALL}")