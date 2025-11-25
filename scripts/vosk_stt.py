#!/usr/bin/env python3
"""
Simple Vosk Speech-to-Text Streaming Test
Streams whatever you say into the mic in real-time
"""

import pyaudio
import json
import os
from pathlib import Path
from vosk import Model, KaldiRecognizer

def find_vosk_model():
    """Find Vosk model in project directory"""
    # Get script directory
    script_dir = Path(__file__).parent
    # Go up to project root (AvatarResurrection)
    project_root = script_dir.parent
    
    # Search for vosk model directories
    search_paths = [
        project_root,  # AvatarResurrection
        script_dir,    # scripts directory
    ]
    
    print("\nSearching for Vosk model...")
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
            
        # Look for vosk-model directories
        for item in search_path.rglob("vosk-model*"):
            if item.is_dir():
                # Check if it has the required subdirectories (am, conf, etc.)
                if (item / "am").exists() or (item / "conf").exists():
                    print(f"✓ Found model at: {item}")
                    return str(item)
    
    return None

def list_microphones():
    """List all available microphones"""
    p = pyaudio.PyAudio()
    print("\n=== Available Microphones ===")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:  # Only show input devices
            print(f"{i}: {info['name']} (channels: {info['maxInputChannels']})")
    p.terminate()
    print()

def main():
    # Show available microphones
    list_microphones()
    
    # Let user select microphone
    mic_index = input("Enter microphone number (or press Enter for default): ").strip()
    mic_index = int(mic_index) if mic_index else None
    
    # Find Vosk model automatically
    model_path = find_vosk_model()
    
    if not model_path:
        print("\n❌ Could not find Vosk model!")
        print("Please download a model from: https://alphacephei.com/vosk/models")
        print("Extract it in the AvatarResurrection directory")
        return
    
    # Initialize Vosk model
    print(f"\nLoading model from: {model_path}")
    
    try:
        model = Model(model_path)
    except Exception as e:
        print(f"\n❌ Error loading model: {e}")
        print("Please check that the model directory contains: am, conf, graph, ivector folders")
        return
    
    # Set up recognizer
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)  # Get word-level timestamps
    
    # Set up audio stream
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        input_device_index=mic_index,
        frames_per_buffer=8000
    )
    stream.start_stream()
    
    print("\n🎤 Listening... (Press Ctrl+C to stop)\n")
    print("=" * 60)
    
    try:
        while True:
            data = stream.read(4000, exception_on_overflow=False)
            
            if rec.AcceptWaveform(data):
                # Final result (end of sentence)
                result = json.loads(rec.Result())
                if result.get('text'):
                    print(f"FINAL: {result['text']}")
            else:
                # Partial result (live transcription)
                partial = json.loads(rec.PartialResult())
                if partial.get('partial'):
                    print(f"       {partial['partial']}", end='\r')
    
    except KeyboardInterrupt:
        print("\n\n👋 Stopping...")
    
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        print("Done!")

if __name__ == "__main__":
    main()