# TTS_Clip_Generator.py - Generate individual word audio files for lip sync clips
"""
Modified TTS system to generate individual word audio files with proper clip names.
Uses the lip sync categorization system to name files correctly.

Main functions:
    generate_clip_audio(word: str, output_dir: str = None) -> str
    generate_clips_for_word_list(words: list, output_dir: str = None) -> dict
    generate_all_needed_clips(word_list: list, output_dir: str = None) -> dict
"""

import time
import os
import json
import threading
import pyphen
import pronouncing
import nltk
from nltk.corpus import cmudict
import re
from piper import PiperVoice, SynthesisConfig
from colorama import Fore, Style, init

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Initialize colorama for colored terminal output
init(autoreset=True)

# Default voice model path
DEFAULT_VOICE_PATH = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-semaine-medium.onnx")

# Global voice instance and path for reuse
_voice_instance = None
_current_voice_path = None
_voice_load_lock = threading.Lock()

class LipSyncClipGenerator:
    def __init__(self):
        # Initialize syllable counter
        self.dic = pyphen.Pyphen(lang='en')
        
        # Initialize CMU dictionary for phonemes
        try:
            self.cmu_dict = cmudict.dict()
        except LookupError:
            print(f"{Fore.YELLOW}[CLIP GEN] CMU dictionary not found. Run: nltk.download('cmudict'){Style.RESET_ALL}")
            self.cmu_dict = {}
        
        # 8-viseme system mapping
        self.phoneme_to_viseme = {
            # 0: Neutral/Rest
            'AH0': 0, 'AH1': 0, 'AH2': 0, 'ER0': 0, 'ER1': 0, 'ER2': 0,
            'UH0': 0, 'UH1': 0, 'UH2': 0,
            
            # 1: Wide (A, E sounds)
            'AA0': 1, 'AA1': 1, 'AA2': 1, 'AE0': 1, 'AE1': 1, 'AE2': 1,
            'EH0': 1, 'EH1': 1, 'EH2': 1, 'AW0': 1, 'AW1': 1, 'AW2': 1,
            
            # 2: Round (O, U sounds)
            'AO0': 2, 'AO1': 2, 'AO2': 2, 'OW0': 2, 'OW1': 2, 'OW2': 2,
            'UW0': 2, 'UW1': 2, 'UW2': 2, 'OY0': 2, 'OY1': 2, 'OY2': 2,
            
            # 3: Small (I, E sounds)
            'IH0': 3, 'IH1': 3, 'IH2': 3, 'IY0': 3, 'IY1': 3, 'IY2': 3,
            'EY0': 3, 'EY1': 3, 'EY2': 3, 'AY0': 3, 'AY1': 3, 'AY2': 3,
            
            # 4: Closed (P, B, M)
            'P': 4, 'B': 4, 'M': 4,
            
            # 5: Lip-Teeth (F, V)
            'F': 5, 'V': 5,
            
            # 6: Tongue (T, D, N, L, S, Z, TH, R)
            'T': 6, 'D': 6, 'N': 6, 'L': 6, 'S': 6, 'Z': 6, 'TH': 6, 
            'DH': 6, 'R': 6, 'SH': 6, 'ZH': 6, 'CH': 6, 'JH': 6,
            
            # 7: Open (K, G, H, W, Y, NG)
            'K': 7, 'G': 7, 'HH': 7, 'W': 7, 'Y': 7, 'NG': 7,
        }
        
        self.viseme_names = ["Neutral", "Wide", "Round", "Small", "Closed", "Lip-Teeth", "Tongue", "Open"]
        self.max_syllables = 6

    def get_syllables(self, word):
        """Get syllable count, capped at max_syllables"""
        count = len(self.dic.inserted(word).split('-'))
        return min(count, self.max_syllables)
    
    def get_phonemes(self, word):
        """Get phonemes for a word"""
        word_lower = word.lower()
        if word_lower in self.cmu_dict:
            return self.cmu_dict[word_lower][0]
        
        phones_list = pronouncing.phones_for_word(word)
        if phones_list:
            return phones_list[0].split()
        return []
    
    def phoneme_to_viseme_id(self, phoneme):
        """Convert phoneme to viseme ID"""
        base_phoneme = re.sub(r'\d', '', phoneme)
        return self.phoneme_to_viseme.get(phoneme, 
               self.phoneme_to_viseme.get(base_phoneme, 0))
    
    def get_start_end_visemes(self, word):
        """Get starting and ending visemes for a word"""
        phonemes = self.get_phonemes(word)
        if not phonemes:
            return 0, 0
        
        start_viseme = self.phoneme_to_viseme_id(phonemes[0])
        end_viseme = self.phoneme_to_viseme_id(phonemes[-1])
        
        return start_viseme, end_viseme
    
    def get_clip_name(self, word):
        """Get the base clip name for this word"""
        syllables = self.get_syllables(word)
        start_vis, end_vis = self.get_start_end_visemes(word)
        
        return f"{syllables}syl_s{start_vis}_e{end_vis}"

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
        print(f"{Fore.YELLOW}[CLIP GEN] config.json not found or invalid. Using defaults.{Style.RESET_ALL}")
        return {'use_cuda': True, 'max_words': 50}

def set_voice_model(voice_path: str):
    """Set a new voice model path and reset the voice instance."""
    global _voice_instance, _current_voice_path
    
    with _voice_load_lock:
        if voice_path != _current_voice_path:
            print(f"{Fore.CYAN}[CLIP GEN] Switching to voice model: {voice_path}{Style.RESET_ALL}")
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
                
                print(f"{Fore.CYAN}[CLIP GEN] Loading Piper voice model: {os.path.basename(voice_path)}...{Style.RESET_ALL}")
                
                if not os.path.exists(voice_path):
                    print(f"{Fore.RED}[CLIP GEN] Voice model not found: {voice_path}{Style.RESET_ALL}")
                    # Fallback to default voice
                    if voice_path != DEFAULT_VOICE_PATH and os.path.exists(DEFAULT_VOICE_PATH):
                        print(f"{Fore.YELLOW}[CLIP GEN] Falling back to default voice: {DEFAULT_VOICE_PATH}{Style.RESET_ALL}")
                        voice_path = DEFAULT_VOICE_PATH
                    else:
                        raise FileNotFoundError(f"Voice model not found at: {voice_path}")
                
                t0 = time.time()
                _voice_instance = PiperVoice.load(voice_path, use_cuda=use_cuda)
                _current_voice_path = voice_path
                load_time = time.time() - t0
                print(f"{Fore.GREEN}[CLIP GEN] Voice model loaded in {load_time:.2f}s{Style.RESET_ALL}")
    
    return _voice_instance

def ensure_output_directory(output_dir: str = None):
    """Ensure the clip output directory exists."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_DIR, "lip_sync_clips")
    
    os.makedirs(output_dir, exist_ok=True)
    print(f"{Fore.CYAN}[CLIP GEN] Output directory: {output_dir}{Style.RESET_ALL}")
    return output_dir

def generate_clip_audio(word: str, output_dir: str = None, voice_path: str = None) -> str:
    """
    Generate audio file for a single word with proper clip naming.
    
    Args:
        word: Word to convert to speech
        output_dir: Directory to save audio files
        voice_path: Optional specific voice model to use
    
    Returns:
        str: Path to the generated audio file
    """
    if not word or not word.strip():
        print(f"{Fore.YELLOW}[CLIP GEN] No word provided{Style.RESET_ALL}")
        return None
    
    # Initialize clip generator
    clip_gen = LipSyncClipGenerator()
    
    # Get clip name
    base_clip_name = clip_gen.get_clip_name(word.strip())
    
    # Prepare output directory and file
    output_dir = ensure_output_directory(output_dir)
    
    # Check if base file exists, if so create variant
    base_file_path = os.path.join(output_dir, f"{base_clip_name}.wav")
    
    if os.path.exists(base_file_path):
        # Find next available variant number
        variant_num = 1
        while True:
            variant_path = os.path.join(output_dir, f"{base_clip_name} ({variant_num}).wav")
            if not os.path.exists(variant_path):
                output_path = variant_path
                break
            variant_num += 1
    else:
        output_path = base_file_path
    
    try:
        # Get voice instance
        voice = get_voice_instance(voice_path)
        
        # Configure synthesis for clear word pronunciation
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=0.9,  # Slightly faster for clearer pronunciation
            noise_scale=0.8,   # Less noise for cleaner audio
            noise_w_scale=0.8,
            normalize_audio=True
        )
        
        print(f"{Fore.BLUE}[CLIP GEN] Generating: '{word}' → {os.path.basename(output_path)}{Style.RESET_ALL}")
        
        # Generate audio
        audio_chunks = []
        
        for chunk in voice.synthesize(word.strip(), syn_config=syn_config):
            audio_chunks.append(chunk)
        
        # Write complete audio to file
        if audio_chunks:
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
            
            print(f"{Fore.GREEN}[CLIP GEN] Generated: {os.path.basename(output_path)}{Style.RESET_ALL}")
            return output_path
        else:
            print(f"{Fore.RED}[CLIP GEN] No audio chunks generated for: {word}{Style.RESET_ALL}")
            return None
        
    except Exception as e:
        print(f"{Fore.RED}[CLIP GEN] Error generating audio for '{word}': {e}{Style.RESET_ALL}")
        return None

def generate_clips_for_word_list(words: list, output_dir: str = None, voice_path: str = None) -> dict:
    """
    Generate audio clips for a list of words.
    
    Args:
        words: List of words to generate clips for
        output_dir: Directory to save audio files
        voice_path: Optional specific voice model to use
    
    Returns:
        dict: Results with success/failure information
    """
    if not words:
        print(f"{Fore.YELLOW}[CLIP GEN] No words provided{Style.RESET_ALL}")
        return {"success": [], "failed": []}
    
    output_dir = ensure_output_directory(output_dir)
    
    print(f"{Fore.CYAN}[CLIP GEN] Generating clips for {len(words)} words...{Style.RESET_ALL}")
    
    results = {"success": [], "failed": []}
    
    for i, word in enumerate(words, 1):
        print(f"{Fore.MAGENTA}[CLIP GEN] Progress: {i}/{len(words)} - Processing '{word}'{Style.RESET_ALL}")
        
        try:
            result_path = generate_clip_audio(word, output_dir, voice_path)
            if result_path:
                results["success"].append({"word": word, "file": result_path})
            else:
                results["failed"].append({"word": word, "error": "No audio generated"})
        except Exception as e:
            results["failed"].append({"word": word, "error": str(e)})
    
    print(f"{Fore.GREEN}[CLIP GEN] Completed: {len(results['success'])} success, {len(results['failed'])} failed{Style.RESET_ALL}")
    
    if results["failed"]:
        print(f"{Fore.YELLOW}[CLIP GEN] Failed words:{Style.RESET_ALL}")
        for failed in results["failed"]:
            print(f"  - {failed['word']}: {failed['error']}")
    
    return results

def generate_all_needed_clips(word_list: list, output_dir: str = None, voice_path: str = None) -> dict:
    """
    Generate clips for all unique clip types needed by the word list.
    Creates one example word per clip type to minimize file count.
    
    Args:
        word_list: List of words that will be used
        output_dir: Directory to save audio files  
        voice_path: Optional specific voice model to use
    
    Returns:
        dict: Results with clip type mapping
    """
    clip_gen = LipSyncClipGenerator()
    output_dir = ensure_output_directory(output_dir)
    
    # Group words by clip type
    clip_types = {}
    for word in word_list:
        clip_name = clip_gen.get_clip_name(word)
        if clip_name not in clip_types:
            clip_types[clip_name] = []
        clip_types[clip_name].append(word)
    
    print(f"{Fore.CYAN}[CLIP GEN] Found {len(clip_types)} unique clip types from {len(word_list)} words{Style.RESET_ALL}")
    
    # Generate one example per clip type
    results = {"clip_types": {}, "success": [], "failed": []}
    
    for i, (clip_name, example_words) in enumerate(clip_types.items(), 1):
        # Use the first word as the example
        example_word = example_words[0]
        
        print(f"{Fore.MAGENTA}[CLIP GEN] {i}/{len(clip_types)} - Generating {clip_name} using '{example_word}'{Style.RESET_ALL}")
        print(f"{Fore.BLUE}  └─ This clip will be used for: {', '.join(example_words[:5])}{'...' if len(example_words) > 5 else ''}{Style.RESET_ALL}")
        
        try:
            result_path = generate_clip_audio(example_word, output_dir, voice_path)
            if result_path:
                results["clip_types"][clip_name] = {
                    "file": result_path,
                    "example_word": example_word,
                    "used_for_words": example_words
                }
                results["success"].append(clip_name)
            else:
                results["failed"].append({"clip": clip_name, "word": example_word, "error": "No audio generated"})
        except Exception as e:
            results["failed"].append({"clip": clip_name, "word": example_word, "error": str(e)})
    
    print(f"{Fore.GREEN}[CLIP GEN] Completed: {len(results['success'])} clips generated, {len(results['failed'])} failed{Style.RESET_ALL}")
    
    return results

def print_clip_summary(word_list: list):
    """Print a summary of what clips will be needed."""
    clip_gen = LipSyncClipGenerator()
    
    clip_usage = {}
    for word in word_list:
        clip_name = clip_gen.get_clip_name(word)
        if clip_name not in clip_usage:
            clip_usage[clip_name] = []
        clip_usage[clip_name].append(word)
    
    print(f"{Fore.CYAN}[CLIP SUMMARY] Clip types needed for {len(word_list)} words:{Style.RESET_ALL}")
    print("=" * 60)
    
    for clip_name, words in sorted(clip_usage.items()):
        syllables = int(clip_name.split('_')[0].replace('syl', ''))
        start_vis = int(clip_name.split('_')[1][1:])
        end_vis = int(clip_name.split('_')[2][1:])
        
        start_name = clip_gen.viseme_names[start_vis]
        end_name = clip_gen.viseme_names[end_vis]
        
        print(f"{clip_name:15} ({syllables} syl, {start_name} → {end_name}) - {len(words)} words")
        print(f"  └─ Examples: {', '.join(words[:3])}{'...' if len(words) > 3 else ''}")
        print()

def get_complete_word_database():
    """Get the complete word database for all 384 possible clips."""
    return {
        # 1 SYLLABLE WORDS
        '1syl_s0_e0': ['the', 'a', 'uh'],
        '1syl_s0_e1': ['up', 'us', 'of'],
        '1syl_s0_e2': ['oh', 'awe', 'owe'],
        '1syl_s0_e3': ['I', 'eye', 'aye'],
        '1syl_s0_e4': ['am', 'um'],
        '1syl_s0_e5': ['of', 'have'],
        '1syl_s0_e6': ['at', 'it', 'and'],
        '1syl_s0_e7': ['ah', 'huh'],
        
        '1syl_s1_e0': ['are', 'her'],
        '1syl_s1_e1': ['cat', 'hat', 'bat'],
        '1syl_s1_e2': ['how', 'now', 'cow'],
        '1syl_s1_e3': ['my', 'by', 'hi'],
        '1syl_s1_e4': ['ham', 'jam', 'ram'],
        '1syl_s1_e5': ['half', 'laugh'],
        '1syl_s1_e6': ['hand', 'land', 'sand'],
        '1syl_s1_e7': ['ask', 'hang'],
        
        '1syl_s2_e0': ['or', 'for', 'more'],
        '1syl_s2_e1': ['was', 'what'],
        '1syl_s2_e2': ['too', 'do', 'you'],
        '1syl_s2_e3': ['boy', 'toy', 'joy'],
        '1syl_s2_e4': ['room', 'boom', 'zoom'],
        '1syl_s2_e5': ['love', 'dove'],
        '1syl_s2_e6': ['out', 'old', 'word'],
        '1syl_s2_e7': ['oak', 'work', 'walk'],
        
        '1syl_s3_e0': ['if', 'in', 'is'],
        '1syl_s3_e1': ['eat', 'each'],
        '1syl_s3_e2': ['new', 'few'],
        '1syl_s3_e3': ['see', 'be', 'me'],
        '1syl_s3_e4': ['seem', 'beam', 'team'],
        '1syl_s3_e5': ['live', 'give'],
        '1syl_s3_e6': ['it', 'sit', 'hit'],
        '1syl_s3_e7': ['ink', 'think'],
        
        '1syl_s4_e0': ['per'],
        '1syl_s4_e1': ['pat', 'bat', 'mat'],
        '1syl_s4_e2': ['put', 'book', 'look'],
        '1syl_s4_e3': ['bee', 'pee'],
        '1syl_s4_e4': ['bomb', 'mom', 'pop'],
        '1syl_s4_e5': ['proof'],
        '1syl_s4_e6': ['put', 'pet', 'pot'],
        '1syl_s4_e7': ['pick', 'pack', 'poke'],
        
        '1syl_s5_e0': ['fur', 'far'],
        '1syl_s5_e1': ['fat', 'fast', 'van'],
        '1syl_s5_e2': ['few', 'view', 'vow'],
        '1syl_s5_e3': ['fee', 'free', 'flee'],
        '1syl_s5_e4': ['from', 'foam'],
        '1syl_s5_e5': ['five'],
        '1syl_s5_e6': ['fit', 'foot'],
        '1syl_s5_e7': ['fake', 'folk', 'funk'],
        
        '1syl_s6_e0': ['there', 'sure'],
        '1syl_s6_e1': ['that', 'than', 'ran'],
        '1syl_s6_e2': ['true', 'through'],
        '1syl_s6_e3': ['tree', 'three', 'knee'],
        '1syl_s6_e4': ['time', 'some', 'come'],
        '1syl_s6_e5': ['save', 'leave'],
        '1syl_s6_e6': ['that', 'this', 'then'],
        '1syl_s6_e7': ['think', 'thank', 'thing'],
        
        '1syl_s7_e0': ['where', 'were'],
        '1syl_s7_e1': ['what', 'had', 'gas'],
        '1syl_s7_e2': ['who', 'go', 'know'],
        '1syl_s7_e3': ['he', 'key', 'way'],
        '1syl_s7_e4': ['game', 'home', 'came'],
        '1syl_s7_e5': ['have', 'wave', 'gave'],
        '1syl_s7_e6': ['get', 'got', 'good'],
        '1syl_s7_e7': ['young', 'hang', 'king'],
        
        # 2 SYLLABLE WORDS  
        '2syl_s0_e0': ['another', 'other', 'under'],
        '2syl_s0_e1': ['upon', 'about', 'again'],
        '2syl_s0_e2': ['into', 'unto'],
        '2syl_s0_e3': ['only', 'any'],
        '2syl_s0_e4': ['awesome', 'autumn'],
        '2syl_s0_e5': ['above', 'achieve'],
        '2syl_s0_e6': ['after', 'almost'],
        '2syl_s0_e7': ['along', 'among'],
        
        '2syl_s1_e0': ['answer', 'rather'],
        '2syl_s1_e1': ['happy', 'family'],
        '2syl_s1_e2': ['also', 'auto'],
        '2syl_s1_e3': ['many', 'carry'],
        '2syl_s1_e4': ['handsome'],
        '2syl_s1_e5': ['active', 'massive'],
        '2syl_s1_e6': ['acted', 'added'],
        '2syl_s1_e7': ['asking', 'laughing'],
        
        '2syl_s2_e0': ['over', 'older', 'order'],
        '2syl_s2_e1': ['open', 'ocean'],
        '2syl_s2_e2': ['outdoor'],
        '2syl_s2_e3': ['okay', 'away'],
        '2syl_s2_e4': ['broken', 'hoping'],
        '2syl_s2_e5': ['observe'],
        '2syl_s2_e6': ['other', 'mother', 'brother'],
        '2syl_s2_e7': ['working', 'walking'],
        
        '2syl_s3_e0': ['inner', 'enter', 'either'],
        '2syl_s3_e1': ['indeed', 'instead'],
        '2syl_s3_e2': ['issue'],
        '2syl_s3_e3': ['easy', 'early'],
        '2syl_s3_e4': ['item', 'income'],
        '2syl_s3_e5': ['believe', 'receive'],
        '2syl_s3_e6': ['inside'],
        '2syl_s3_e7': ['evening', 'feeling'],
        
        '2syl_s4_e0': ['paper', 'proper'],
        '2syl_s4_e1': ['perhaps', 'because'],
        '2syl_s4_e2': ['people', 'purpose'],
        '2syl_s4_e3': ['pretty', 'party'],
        '2syl_s4_e4': ['problem', 'program'],
        '2syl_s4_e5': ['prove', 'behave'],
        '2syl_s4_e6': ['present', 'moment'],
        '2syl_s4_e7': ['playing', 'making'],
        
        '2syl_s5_e0': ['further', 'future'],
        '2syl_s5_e1': ['final', 'female'],
        '2syl_s5_e2': ['follow', 'photo'],
        '2syl_s5_e3': ['fifty', 'friendly'],
        '2syl_s5_e4': ['freedom'],
        '2syl_s5_e5': ['fifteen', 'office'],
        '2syl_s5_e6': ['forest', 'fastest'],
        '2syl_s5_e7': ['feeling', 'falling'],
        
        '2syl_s6_e0': ['teacher', 'neither'],
        '2syl_s6_e1': ['started', 'wanted'],
        '2syl_s6_e2': ['taken', 'spoken'],
        '2syl_s6_e3': ['story', 'study'],
        '2syl_s6_e4': ['system', 'listen'],
        '2syl_s6_e5': ['native'],
        '2syl_s6_e6': ['student', 'different'],
        '2syl_s6_e7': ['trying', 'talking'],
        
        '2syl_s7_e0': ['water', 'weather'],
        '2syl_s7_e1': ['wanted', 'walked'],
        '2syl_s7_e2': ['window', 'yellow', 'hello'],
        '2syl_s7_e3': ['working', 'walking'],
        '2syl_s7_e4': ['welcome'],
        '2syl_s7_e5': ['yourself', 'herself'],
        '2syl_s7_e6': ['without', 'within'],
        '2syl_s7_e7': ['thinking'],
        
        # 3 SYLLABLE WORDS
        '3syl_s0_e0': ['however', 'together'],
        '3syl_s0_e1': ['understand', 'elephant'],
        '3syl_s0_e2': ['autograph'],
        '3syl_s0_e3': ['area', 'idea'],
        '3syl_s0_e4': ['umbrella'],
        '3syl_s0_e5': ['objective'],
        '3syl_s0_e6': ['afternoon'],
        '3syl_s0_e7': ['anything', 'everything'],
        
        '3syl_s1_e0': ['average', 'animal'],
        '3syl_s1_e1': ['natural'],
        '3syl_s1_e2': ['although', 'already'],
        '3syl_s1_e3': ['actually'],
        '3syl_s1_e4': ['amazing'],
        '3syl_s1_e5': ['analyze', 'advertise'],
        '3syl_s1_e6': ['accident'],
        '3syl_s1_e7': ['anything'],
        
        '3syl_s2_e0': ['over'],
        '3syl_s2_e1': ['obvious', 'popular'],
        '3syl_s2_e2': ['overdo'],
        '3syl_s2_e3': ['usually'],
        '3syl_s2_e4': ['opinion', 'opening'],
        '3syl_s2_e5': ['observe'],
        '3syl_s2_e6': ['opposite', 'operating'],
        '3syl_s2_e7': ['offering'],
        
        '3syl_s3_e0': ['easier', 'earlier'],
        '3syl_s3_e1': ['interview'],
        '3syl_s3_e2': ['easily'],
        '3syl_s3_e3': ['really'],
        '3syl_s3_e4': ['economy'],
        '3syl_s3_e5': ['easily'],
        '3syl_s3_e6': ['investment'],
        '3syl_s3_e7': ['everything'],
        
        '3syl_s4_e0': ['probably', 'property'],
        '3syl_s4_e1': ['particular'],
        '3syl_s4_e2': ['beautiful'],
        '3syl_s4_e3': ['policy'],
        '3syl_s4_e4': ['program'],
        '3syl_s4_e5': ['probably'],
        '3syl_s4_e6': ['president'],
        '3syl_s4_e7': ['planning'],
        
        '3syl_s5_e0': ['forever'],
        '3syl_s5_e1': ['fantastic'],
        '3syl_s5_e2': ['following'],
        '3syl_s5_e3': ['family'],
        '3syl_s5_e4': ['freedom'],
        '3syl_s5_e5': ['fifteen'],
        '3syl_s5_e6': ['festival'],
        '3syl_s5_e7': ['finishing'],
        
        '3syl_s6_e0': ['together'],
        '3syl_s6_e1': ['September'],
        '3syl_s6_e2': ['tomorrow'],
        '3syl_s6_e3': ['seriously'],
        '3syl_s6_e4': ['tomorrow'],
        '3syl_s6_e5': ['sensitive'],
        '3syl_s6_e6': ['telephone'],
        '3syl_s6_e7': ['something'],
        
        '3syl_s7_e0': ['whatever'],
        '3syl_s7_e1': ['wonderful'],
        '3syl_s7_e2': ['whoever'],
        '3syl_s7_e3': ['willingly'],
        '3syl_s7_e4': ['welcome'],
        '3syl_s7_e5': ['whatever'],
        '3syl_s7_e6': ['wonderful'],
        '3syl_s7_e7': ['washing'],
        
        # 4 SYLLABLE WORDS
        '4syl_s0_e0': ['America'],
        '4syl_s0_e1': ['American'],
        '4syl_s0_e2': ['umbrella'],
        '4syl_s0_e3': ['understandably'],
        '4syl_s0_e4': ['umbrella'],
        '4syl_s0_e5': ['unbelievable'],
        '4syl_s0_e6': ['understand'],
        '4syl_s0_e7': ['understanding'],
        
        '4syl_s1_e0': ['actually'],
        '4syl_s1_e1': ['absolutely'],
        '4syl_s1_e2': ['Alabama'],
        '4syl_s1_e3': ['activity'],
        '4syl_s1_e4': ['Amsterdam'],
        '4syl_s1_e5': ['alternative'],
        '4syl_s1_e6': ['accidentally'],
        '4syl_s1_e7': ['analyzing'],
        
        '4syl_s2_e0': ['obviously'],
        '4syl_s2_e1': ['original'],
        '4syl_s2_e2': ['Ohio'],
        '4syl_s2_e3': ['obviously'],
        '4syl_s2_e4': ['Oklahoma'],
        '4syl_s2_e5': ['objective'],
        '4syl_s2_e6': ['operation'],
        '4syl_s2_e7': ['organizing'],
        
        '4syl_s3_e0': ['information'],
        '4syl_s3_e1': ['education'],
        '4syl_s3_e2': ['intimidate'],
        '4syl_s3_e3': ['immediately'],
        '4syl_s3_e4': ['intermediate'],
        '4syl_s3_e5': ['initiative'],
        '4syl_s3_e6': ['intelligent'],
        '4syl_s3_e7': ['interesting'],
        
        '4syl_s4_e0': ['particularly'],
        '4syl_s4_e1': ['participation'],
        '4syl_s4_e2': ['Philadelphia'],
        '4syl_s4_e3': ['possibility'],
        '4syl_s4_e4': ['problem'],
        '4syl_s4_e5': ['probability'],
        '4syl_s4_e6': ['personality'],
        '4syl_s4_e7': ['planning'],
        
        '4syl_s5_e0': ['photographer'],
        '4syl_s5_e1': ['favorable'],
        '4syl_s5_e2': ['philosophy'],
        '4syl_s5_e3': ['facility'],
        '4syl_s5_e4': ['fundamental'],
        '4syl_s5_e5': ['philosophy'],
        '4syl_s5_e6': ['fantastic'],
        '4syl_s5_e7': ['fascinating'],
        
        '4syl_s6_e0': ['technology'],
        '4syl_s6_e1': ['television'],
        '4syl_s6_e2': ['tornado'],
        '4syl_s6_e3': ['testimony'],
        '4syl_s6_e4': ['tomato'],
        '4syl_s6_e5': ['terrific'],
        '4syl_s6_e6': ['traditional'],
        '4syl_s6_e7': ['thanksgiving'],
        
        '4syl_s7_e0': ['geography'],
        '4syl_s7_e1': ['graduation'],
        '4syl_s7_e2': ['gymnasium'],
        '4syl_s7_e3': ['generosity'],
        '4syl_s7_e4': ['gymnasium'],
        '4syl_s7_e5': ['generative'],
        '4syl_s7_e6': ['government'],
        '4syl_s7_e7': ['going'],
        
        # 5 SYLLABLE WORDS
        '5syl_s0_e0': ['opportunity'],
        '5syl_s0_e1': ['understanding'],
        '5syl_s0_e2': ['automobile'],
        '5syl_s0_e3': ['immediately'],
        '5syl_s0_e4': ['ultimatum'],
        '5syl_s0_e5': ['unbelievable'],
        '5syl_s0_e6': ['unfortunately'],
        '5syl_s0_e7': ['understanding'],
        
        '5syl_s1_e0': ['automatically'],
        '5syl_s1_e1': ['agricultural'],
        '5syl_s1_e2': ['Australia'],
        '5syl_s1_e3': ['actually'],
        '5syl_s1_e4': ['academically'],
        '5syl_s1_e5': ['alternative'],
        '5syl_s1_e6': ['accidentally'],
        '5syl_s1_e7': ['analyzing'],
        
        '5syl_s2_e0': ['obviously'],
        '5syl_s2_e1': ['organization'],
        '5syl_s2_e2': ['outstanding'],
        '5syl_s2_e3': ['obviously'],
        '5syl_s2_e4': ['optimization'],
        '5syl_s2_e5': ['objective'],
        '5syl_s2_e6': ['operation'],
        '5syl_s2_e7': ['organizing'],
        
        '5syl_s3_e0': ['immediately'],
        '5syl_s3_e1': ['international'],
        '5syl_s3_e2': ['imagination'],
        '5syl_s3_e3': ['immediately'],
        '5syl_s3_e4': ['intermediate'],
        '5syl_s3_e5': ['initiative'],
        '5syl_s3_e6': ['intelligent'],
        '5syl_s3_e7': ['interesting'],
        
        '5syl_s4_e0': ['personality'],
        '5syl_s4_e1': ['particularly'],
        '5syl_s4_e2': ['Philadelphia'],
        '5syl_s4_e3': ['possibility'],
        '5syl_s4_e4': ['preliminary'],
        '5syl_s4_e5': ['probability'],
        '5syl_s4_e6': ['personality'],
        '5syl_s4_e7': ['preparing'],
        
        '5syl_s5_e0': ['unfortunately'],
        '5syl_s5_e1': ['fundamentally'],
        '5syl_s5_e2': ['photography'],
        '5syl_s5_e3': ['facility'],
        '5syl_s5_e4': ['fundamental'],
        '5syl_s5_e5': ['fifty'],
        '5syl_s5_e6': ['fortunately'],
        '5syl_s5_e7': ['fascinating'],
        
        '5syl_s6_e0': ['especially'],
        '5syl_s6_e1': ['educational'],
        '5syl_s6_e2': ['traditional'],
        '5syl_s6_e3': ['testimony'],
        '5syl_s6_e4': ['television'],
        '5syl_s6_e5': ['sensitive'],
        '5syl_s6_e6': ['traditional'],
        '5syl_s6_e7': ['thanksgiving'],
        
        '5syl_s7_e0': ['geographical'],
        '5syl_s7_e1': ['graduation'],
        '5syl_s7_e2': ['gymnasium'],
        '5syl_s7_e3': ['generosity'],
        '5syl_s7_e4': ['graduation'],
        '5syl_s7_e5': ['generative'],
        '5syl_s7_e6': ['government'],
        '5syl_s7_e7': ['going'],
        
        # 6 SYLLABLE WORDS
        '6syl_s0_e0': ['unfortunately'],
        '6syl_s0_e1': ['understanding'],
        '6syl_s0_e2': ['automobile'],
        '6syl_s0_e3': ['unfortunately'],
        '6syl_s0_e4': ['ultimatum'],
        '6syl_s0_e5': ['unbelievable'],
        '6syl_s0_e6': ['unfortunately'],
        '6syl_s0_e7': ['understanding'],
        
        '6syl_s1_e0': ['automatically'],
        '6syl_s1_e1': ['agricultural'],
        '6syl_s1_e2': ['automatically'],
        '6syl_s1_e3': ['actually'],
        '6syl_s1_e4': ['academically'],
        '6syl_s1_e5': ['alternative'],
        '6syl_s1_e6': ['accidentally'],
        '6syl_s1_e7': ['analyzing'],
        
        '6syl_s2_e0': ['obviously'],
        '6syl_s2_e1': ['organization'],
        '6syl_s2_e2': ['obviously'],
        '6syl_s2_e3': ['obviously'],
        '6syl_s2_e4': ['optimization'],
        '6syl_s2_e5': ['obviously'],
        '6syl_s2_e6': ['operation'],
        '6syl_s2_e7': ['organizing'],
        
        '6syl_s3_e0': ['immediately'],
        '6syl_s3_e1': ['international'],
        '6syl_s3_e2': ['imagination'],
        '6syl_s3_e3': ['immediately'],
        '6syl_s3_e4': ['intermediate'],
        '6syl_s3_e5': ['initiative'],
        '6syl_s3_e6': ['intelligent'],
        '6syl_s3_e7': ['interesting'],
        
        '6syl_s4_e0': ['personality'],
        '6syl_s4_e1': ['particularly'],
        '6syl_s4_e2': ['personality'],
        '6syl_s4_e3': ['possibility'],
        '6syl_s4_e4': ['preliminary'],
        '6syl_s4_e5': ['probability'],
        '6syl_s4_e6': ['personality'],
        '6syl_s4_e7': ['preparing'],
        
        '6syl_s5_e0': ['unfortunately'],
        '6syl_s5_e1': ['fundamentally'],
        '6syl_s5_e2': ['unfortunately'],
        '6syl_s5_e3': ['unfortunately'],
        '6syl_s5_e4': ['fundamental'],
        '6syl_s5_e5': ['unfortunately'],
        '6syl_s5_e6': ['fortunately'],
        '6syl_s5_e7': ['fascinating'],
        
        '6syl_s6_e0': ['especially'],
        '6syl_s6_e1': ['educational'],
        '6syl_s6_e2': ['especially'],
        '6syl_s6_e3': ['especially'],
        '6syl_s6_e4': ['television'],
        '6syl_s6_e5': ['especially'],
        '6syl_s6_e6': ['traditional'],
        '6syl_s6_e7': ['thanksgiving'],
        
        '6syl_s7_e0': ['geographical'],
        '6syl_s7_e1': ['geographical'],
        '6syl_s7_e2': ['geographical'],
        '6syl_s7_e3': ['geographical'],
        '6syl_s7_e4': ['graduation'],
        '6syl_s7_e5': ['generative'],
        '6syl_s7_e6': ['government'],
        '6syl_s7_e7': ['geographical'],
    }

def generate_all_384_clips(output_dir: str = None, voice_path: str = None) -> dict:
    """
    Generate audio clips for all 384 possible clip combinations.
    Uses the best example word for each clip type.
    
    Args:
        output_dir: Directory to save audio files
        voice_path: Optional specific voice model to use
    
    Returns:
        dict: Results with detailed information
    """
    word_db = get_complete_word_database()
    output_dir = ensure_output_directory(output_dir)
    
    print(f"{Fore.CYAN}[COMPLETE GEN] Generating all 384 possible clip types...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}[COMPLETE GEN] This will take a while - generating one example per clip type{Style.RESET_ALL}")
    
    results = {"success": [], "failed": [], "total": len(word_db)}
    
    for i, (clip_name, example_words) in enumerate(word_db.items(), 1):
        # Use the first (best) example word
        example_word = example_words[0]
        
        print(f"{Fore.MAGENTA}[COMPLETE GEN] {i}/384 - Generating {clip_name} using '{example_word}'{Style.RESET_ALL}")
        
        try:
            # Force the exact clip name (don't let the system auto-detect)
            output_path = os.path.join(output_dir, f"{clip_name}.wav")
            
            # Generate audio using the example word
            voice = get_voice_instance(voice_path)
            
            syn_config = SynthesisConfig(
                volume=1.0,
                length_scale=0.9,
                noise_scale=0.8,
                noise_w_scale=0.8,
                normalize_audio=True
            )
            
            # Generate audio
            audio_chunks = []
            for chunk in voice.synthesize(example_word.strip(), syn_config=syn_config):
                audio_chunks.append(chunk)
            
            # Write to file
            if audio_chunks:
                import wave
                with wave.open(output_path, 'wb') as wav_file:
                    first_chunk = audio_chunks[0]
                    wav_file.setnchannels(first_chunk.sample_channels)
                    wav_file.setsampwidth(first_chunk.sample_width)
                    wav_file.setframerate(first_chunk.sample_rate)
                    
                    for chunk in audio_chunks:
                        wav_file.writeframes(chunk.audio_int16_bytes)
                
                results["success"].append({
                    "clip_name": clip_name,
                    "example_word": example_word,
                    "file_path": output_path,
                    "all_examples": example_words
                })
                
                if i % 50 == 0:  # Progress update every 50 clips
                    print(f"{Fore.GREEN}[COMPLETE GEN] Progress: {i}/384 clips completed{Style.RESET_ALL}")
            else:
                results["failed"].append({"clip": clip_name, "word": example_word, "error": "No audio generated"})
                
        except Exception as e:
            results["failed"].append({"clip": clip_name, "word": example_word, "error": str(e)})
            print(f"{Fore.RED}[COMPLETE GEN] Failed {clip_name}: {e}{Style.RESET_ALL}")
    
    print(f"{Fore.GREEN}[COMPLETE GEN] Completed: {len(results['success'])}/384 clips generated{Style.RESET_ALL}")
    
    if results["failed"]:
        print(f"{Fore.YELLOW}[COMPLETE GEN] Failed clips: {len(results['failed'])}{Style.RESET_ALL}")
        for failed in results["failed"][:5]:  # Show first 5 failures
            print(f"  - {failed['clip']} ('{failed['word']}'): {failed['error']}")
        if len(results["failed"]) > 5:
            print(f"  ... and {len(results['failed']) - 5} more")
    
    return results

if __name__ == "__main__":
    print(f"{Fore.GREEN}{'=' * 60}")
    print(f"{Fore.YELLOW}TTS Clip Generator for Lip Sync System")
    print(f"{Fore.GREEN}{'=' * 60}{Style.RESET_ALL}")
    
    # Show available options
    word_db = get_complete_word_database()
    print(f"{Fore.CYAN}[MAIN] Complete word database loaded: {len(word_db)} clip types{Style.RESET_ALL}")
    
    # Show what clips will be needed
    print(f"\n{Fore.CYAN}Example clip breakdown:{Style.RESET_ALL}")
    sample_clips = list(word_db.items())[:10]
    for clip_name, words in sample_clips:
        print(f"  {clip_name:15} → {words[0]:12} (examples: {', '.join(words[:3])})")
    print(f"  ... and {len(word_db) - 10} more clip types")
    
    print(f"\n{Fore.CYAN}Generation Options:{Style.RESET_ALL}")
    print(f"  1. Generate ALL 384 clips (complete coverage)")
    print(f"  2. Generate clips for custom word list")  
    print(f"  3. Show detailed clip database")
    
    try:
        choice = input(f"\n{Fore.CYAN}Enter choice (1-3): {Style.RESET_ALL}")
        
        if choice == "1":
            print(f"\n{Fore.YELLOW}WARNING: This will generate 384 audio files and may take 10-30 minutes!{Style.RESET_ALL}")
            confirm = input(f"{Fore.CYAN}Continue? (y/N): {Style.RESET_ALL}")
            
            if confirm.lower() == 'y':
                print(f"\n{Fore.CYAN}Generating all 384 clips...{Style.RESET_ALL}")
                results = generate_all_384_clips()
                
                print(f"\n{Fore.GREEN}Generation complete!{Style.RESET_ALL}")
                print(f"Successfully generated: {len(results['success'])}/384 clips")
                print(f"Failed: {len(results['failed'])}")
                
                # Save results log
                output_dir = ensure_output_directory()
                log_file = os.path.join(output_dir, "generation_log.json")
                import json
                with open(log_file, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"Generation log saved to: {log_file}")
            else:
                print(f"{Fore.YELLOW}Generation cancelled{Style.RESET_ALL}")
                
        elif choice == "2":
            print(f"\n{Fore.CYAN}Enter words separated by commas:{Style.RESET_ALL}")
            word_input = input("Words: ")
            custom_words = [w.strip() for w in word_input.split(',') if w.strip()]
            
            if custom_words:
                results = generate_clips_for_word_list(custom_words)
                print(f"\n{Fore.GREEN}Generation complete!{Style.RESET_ALL}")
                print(f"Generated {len(results['success'])} audio files")
            else:
                print(f"{Fore.RED}No valid words provided{Style.RESET_ALL}")
                
        elif choice == "3":
            print(f"\n{Fore.CYAN}Detailed Clip Database (showing first 20):{Style.RESET_ALL}")
            print("=" * 60)
            for i, (clip_name, words) in enumerate(list(word_db.items())[:20], 1):
                syllables = int(clip_name.split('_')[0].replace('syl', ''))
                start_vis = int(clip_name.split('_')[1][1:])
                end_vis = int(clip_name.split('_')[2][1:])
                
                clip_gen = LipSyncClipGenerator()
                start_name = clip_gen.viseme_names[start_vis]
                end_name = clip_gen.viseme_names[end_vis]
                
                print(f"{i:2}. {clip_name:15} ({syllables} syl, {start_name} → {end_name})")
                print(f"    Examples: {', '.join(words)}")
                print()
            
            print(f"... and {len(word_db) - 20} more clip types")
            
        else:
            print(f"{Fore.RED}Invalid choice{Style.RESET_ALL}")
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Cancelled by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
    
    print(f"{Fore.CYAN}Choose generation mode:{Style.RESET_ALL}")
    print(f"  1. Generate one clip per unique type (recommended)")
    print(f"  2. Generate clip for every word (creates variants)")
    print(f"  3. Just show summary (no generation)")
    
    try:
        choice = input(f"\n{Fore.CYAN}Enter choice (1-3): {Style.RESET_ALL}")
        
        if choice == "1":
            print(f"\n{Fore.CYAN}Generating unique clip types...{Style.RESET_ALL}")
            results = generate_all_needed_clips(test_words)
            
            print(f"\n{Fore.GREEN}Generation complete!{Style.RESET_ALL}")
            print(f"Generated {len(results['success'])} clip files")
            
        elif choice == "2":
            print(f"\n{Fore.CYAN}Generating clips for all words...{Style.RESET_ALL}")
            results = generate_clips_for_word_list(test_words)
            
            print(f"\n{Fore.GREEN}Generation complete!{Style.RESET_ALL}")
            print(f"Generated {len(results['success'])} audio files")
            
        elif choice == "3":
            print(f"\n{Fore.GREEN}Summary complete - no files generated{Style.RESET_ALL}")
            
        else:
            print(f"{Fore.RED}Invalid choice{Style.RESET_ALL}")
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Cancelled by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")