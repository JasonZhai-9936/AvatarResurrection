# voice_input_manager.py
import pyaudio
import json
import threading
import queue
from pathlib import Path
from vosk import Model, KaldiRecognizer
from colorama import Fore, Style

class VoiceInputManager:
    def __init__(self, project_dir):
        self.project_dir = Path(project_dir)
        self.model = self._load_model()
        self.p = pyaudio.PyAudio()
        
        # State
        self.input_device_index = None  # None = Default
        self.is_listening = False
        self.stop_event = threading.Event()
        self.audio_thread = None
        self.stream = None
        self.rec = None
        
        # Callback for real-time text updates
        self.on_partial_result = None
    
    def _load_model(self):
        """Find and load the Vosk model"""
        search_paths = [self.project_dir, self.project_dir.parent]
        print(f"{Fore.CYAN}[VOICE] Searching for Vosk model...{Style.RESET_ALL}")
        
        for path in search_paths:
            for item in path.rglob("vosk-model*"):
                if item.is_dir() and (item / "conf").exists():
                    print(f"{Fore.GREEN}[VOICE] Found model at: {item}{Style.RESET_ALL}")
                    # Suppress Vosk logs by redirecting stderr if needed, 
                    # but usually it's fine to leave them.
                    return Model(str(item))
        
        raise RuntimeError("Vosk model not found! Please download a model to the project root.")

    def get_available_microphones(self):
        """Returns a list of dicts for NiceGUI select: [{'label': 'Name', 'value': index}]"""
        info = self.p.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        devices = []
        
        # Add default option
        devices.append({'label': 'Default Microphone', 'value': None})
        
        for i in range(0, numdevices):
            if (self.p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                name = self.p.get_device_info_by_host_api_device_index(0, i).get('name')
                devices.append({'label': f"{i}: {name}", 'value': i})
                
        return devices

    def set_input_device(self, index):
        """Set the microphone index to use"""
        self.input_device_index = index
        print(f"{Fore.CYAN}[VOICE] Input device set to index: {index}{Style.RESET_ALL}")

    def start_listening(self, callback_function):
        """
        Start the microphone loop in a background thread.
        callback_function(text) will be called with partial updates.
        """
        if self.is_listening:
            return

        self.on_partial_result = callback_function
        self.is_listening = True
        self.stop_event.clear()
        
        # Initialize recognizer
        self.rec = KaldiRecognizer(self.model, 16000)
        
        # Start thread
        self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.audio_thread.start()
        print(f"{Fore.GREEN}[VOICE] Started listening thread{Style.RESET_ALL}")

    def stop_listening(self):
        """Stops the thread and closes the stream"""
        self.is_listening = False
        self.stop_event.set()
        if self.audio_thread:
            self.audio_thread.join(timeout=1.0)
        print(f"{Fore.YELLOW}[VOICE] Stopped listening{Style.RESET_ALL}")

    def _audio_loop(self):
        try:
            self.stream = self.p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=8000
            )
            self.stream.start_stream()
            
            while not self.stop_event.is_set():
                # Read chunk
                data = self.stream.read(4000, exception_on_overflow=False)
                
                if self.rec.AcceptWaveform(data):
                    # We could handle final results here, but partials are usually enough
                    # for the UI stream effect.
                    pass
                else:
                    # Partial result (live transcription)
                    partial_json = self.rec.PartialResult()
                    partial = json.loads(partial_json)
                    text = partial.get('partial', '')
                    
                    if self.on_partial_result:
                        # Send partial text to UI
                        self.on_partial_result(text)
                        
        except Exception as e:
            print(f"{Fore.RED}[VOICE] Error in audio loop: {e}{Style.RESET_ALL}")
        finally:
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except:
                    pass