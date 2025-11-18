# generate_word_library.py - Generate individual audio files for word library

import time
import os
import json
import wave
from piper import PiperVoice, SynthesisConfig
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Set project directory (one folder above scripts)
PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))

# Default voice model path
DEFAULT_VOICE_PATH = os.path.join(PROJECT_DIR, "Piper_Voices", "en_GB-northern_english_male-medium.onnx")

# Common words list
COMMON_WORDS = [
    "the","be","to","of","and","a","in","that","have","I","it","for","not","on","with","he","as","you","do","at",
    "this","but","his","by","from","they","we","say","her","she","or","an","will","my","one","all","would","there","their",
    "what","so","up","out","if","about","who","get","which","go","me","when","make","can","like","time","no","just","him","know",
    "take","people","into","year","your","good","some","could","them","see","other","than","then","now","look","only","come","its",
    "over","think","also","back","after","use","two","how","our","work","first","well","way","even","new","want","because","any",
    "these","give","day","most","us","is","are","was","were","been","had","has","did","said","made","may","might","must","shall",
    "should","being","does","done","each","few","many","every","more","less","very","here","where","why","there","their","them",
    "again","against","always","another","around","away","before","below","between","both","during","each","enough","ever","far",
    "found","great","high","home","important","large","last","long","lot","mean","much","never","next","old","place","right","same",
    "small","something","still","such","sure","thing","those","through","under","until","while","without","woman","man","life",
    "child","world","school","state","family","student","group","country","problem","hand","part","eye","fact","case","week",
    "company","system","program","question","work","government","number","night","point","home","water","room","mother","area",
    "money","story","issue","side","kind","head","house","service","friend","father","power","hour","game","line","end","member",
    "law","car","city","community","name","president","team","minute","idea","kid","body","information","back","parent","face",
    "others","level","office","door","health","person","art","war","history","party","result","change","morning","reason","research",
    "girl","guy","moment","air","teacher","force","education","foot","boy","age","policy","everything","process","music","market",
    "sense","service","area","activity","road","table","center","couple","field","project","ground","class","college","amount",
    "development","role","society","effect","rate","order","value","practice","building","court","situation","cost","industry",
    "figure","data","material","letter","idea","color","language","animal","story","meeting","energy","paper","form","piece",
    "example","month","truth","study","book","film","food","door","nature","parent","window","sound","light","fire","sea","tree",
    "river","mountain","heart","mind","voice","word","moment","question","answer","move","help","show","run","play","live","believe",
    "bring","happen","write","provide","sit","stand","lose","pay","meet","include","continue","set","learn","change","lead","watch",
    "follow","stop","create","speak","read","allow","add","spend","grow","open","walk","offer","remember","love","consider","buy",
    "wait","serve","die","send","expect","build","stay","fall","cut","reach","kill","remain","suggest","raise","pass","sell",
    "require","report","decide","explain","hope","develop","carry","break","receive","support","agree","produce","cover","apply",
    "avoid","prepare","discuss","reduce","appear","listen","share","measure","choose","design","plan","improve","focus","teach",
    "return","experience","visit","draw","build","save","control","protect","accept","understand","describe","discover","recognize",
    "express","handle","imagine","prefer","realize","travel","use","win","work","write","act","affect","argue","arrive","ask",
    "belong","bring","call","catch","change","check","choose","close","come","compare","complain","consider","contain","continue",
    "cost","count","decide","deliver","depend","describe","develop","die","discuss","draw","drive","eat","encourage","enjoy",
    "explain","fail","fall","feel","fill","find","finish","follow","forget","form","get","give","go","grow","happen","hear","help",
    "hold","hope","imagine","improve","include","increase","keep","know","learn","leave","let","like","listen","live","look","lose",
    "love","make","mean","meet","move","need","notice","offer","open","pay","play","prefer","prepare","produce","provide","put",
    "reach","read","receive","remember","return","run","say","see","seem","sell","send","set","show","sit","speak","spend","stand",
    "start","stay","stop","study","succeed","take","talk","teach","tell","think","travel","try","turn","understand","use","wait",
    "walk","want","watch","win","work","worry","write","above","across","after","against","along","among","around","at","before",
    "behind","below","beneath","beside","between","beyond","by","down","during","except","for","from","in","inside","into","near",
    "of","off","on","out","outside","over","through","to","toward","under","until","up","upon","with","within","without",
    "about","across","after","along","around","before","behind","below","beneath","beside","between","beyond","by","down",
    "during","except","for","from","in","inside","into","near","of","off","on","out","outside","over","through","to","toward",
    "under","until","up","upon","with","within","without","above","among","around","as","because","before","but","if","since",
    "so","than","though","until","when","where","while","a","an","the","and","but","or","as","because","although","though","while",
    "if","unless","until","since","whereas","that","which","who","whom","whose","what","whatever","when","whenever","where",
    "wherever","why","how","all","another","any","both","each","either","enough","every","few","fewer","less","little","many",
    "more","most","much","neither","no","none","other","several","some","such","that","these","those","what","whatever","which",
    "whichever","who","whoever","whom","whose","my","your","his","her","its","our","their","mine","yours","hers","ours","theirs",
    "this","that","these","those","anybody","anyone","anything","each","either","everybody","everyone","everything","neither",
    "nobody","no one","nothing","somebody","someone","something","both","few","many","several","all","any","most","none","some",
    "able","bad","best","better","big","black","certain","clear","different","early","easy","economic","entire","far","free",
    "full","good","great","hard","high","human","important","international","large","late","little","local","long","low","major",
    "military","national","new","old","only","other","political","possible","public","real","recent","right","small","social",
    "special","strong","sure","true","white","whole","young","happy","sad","angry","beautiful","cold","hot","nice","poor","rich",
    "short","slow","fast","soft","tall","tiny","ugly","warm","wrong","yes","no","maybe","really","very","quite","almost","already",
    "always","around","away","back","down","enough","even","ever","far","here","just","late","long","much","near","never","now",
    "often","once","only","perhaps","quickly","rather","really","recently","right","slowly","sometimes","soon","still","then",
    "today","together","too","usually","well","yet"
]

# Common numbers (0-100, plus common larger numbers)
COMMON_NUMBERS = [
    "zero","one","two","three","four","five","six","seven","eight","nine","ten",
    "eleven","twelve","thirteen","fourteen","fifteen","sixteen","seventeen","eighteen","nineteen","twenty",
    "twenty-one","twenty-two","twenty-three","twenty-four","twenty-five","twenty-six","twenty-seven","twenty-eight","twenty-nine","thirty",
    "thirty-one","thirty-two","thirty-three","thirty-four","thirty-five","thirty-six","thirty-seven","thirty-eight","thirty-nine","forty",
    "forty-one","forty-two","forty-three","forty-four","forty-five","forty-six","forty-seven","forty-eight","forty-nine","fifty",
    "fifty-one","fifty-two","fifty-three","fifty-four","fifty-five","fifty-six","fifty-seven","fifty-eight","fifty-nine","sixty",
    "sixty-one","sixty-two","sixty-three","sixty-four","sixty-five","sixty-six","sixty-seven","sixty-eight","sixty-nine","seventy",
    "seventy-one","seventy-two","seventy-three","seventy-four","seventy-five","seventy-six","seventy-seven","seventy-eight","seventy-nine","eighty",
    "eighty-one","eighty-two","eighty-three","eighty-four","eighty-five","eighty-six","eighty-seven","eighty-eight","eighty-nine","ninety",
    "ninety-one","ninety-two","ninety-three","ninety-four","ninety-five","ninety-six","ninety-seven","ninety-eight","ninety-nine","hundred",
    "thousand","million","billion","trillion","first","second","third","fourth","fifth","sixth","seventh","eighth","ninth","tenth"
]

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

def load_voice(voice_path: str = None):
    """Load voice model"""
    if voice_path is None:
        voice_path = DEFAULT_VOICE_PATH
    
    config = load_config()
    use_cuda = config['use_cuda']
    
    print(f"{Fore.CYAN}[TTS] Loading voice: {os.path.basename(voice_path)}{Style.RESET_ALL}")
    
    if not os.path.exists(voice_path):
        raise FileNotFoundError(f"Voice model not found: {voice_path}")
    
    voice = PiperVoice.load(voice_path, use_cuda=use_cuda)
    print(f"{Fore.GREEN}[TTS] Voice loaded successfully{Style.RESET_ALL}")
    return voice

def sanitize_filename(word: str) -> str:
    """Convert word to safe filename"""
    # Replace spaces and special characters
    safe_name = word.lower().replace(" ", "_").replace("-", "_")
    # Remove any other problematic characters
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
    return safe_name

def generate_word_audio(voice, word: str, output_dir: str) -> bool:
    """Generate audio file for a single word"""
    try:
        syn_config = SynthesisConfig(
            volume=1.0,
            length_scale=1.0,
            noise_scale=1.0,
            noise_w_scale=1.0,
            normalize_audio=True
        )
        
        # Generate filename
        safe_word = sanitize_filename(word)
        output_path = os.path.join(output_dir, f"{safe_word}.wav")
        
        # Skip if already exists
        if os.path.exists(output_path):
            return True
        
        # Generate audio
        audio_chunks = []
        for chunk in voice.synthesize(word, syn_config=syn_config):
            audio_chunks.append(chunk)
        
        # Write to file
        if audio_chunks:
            with wave.open(output_path, 'wb') as wav_file:
                first_chunk = audio_chunks[0]
                wav_file.setnchannels(first_chunk.sample_channels)
                wav_file.setsampwidth(first_chunk.sample_width)
                wav_file.setframerate(first_chunk.sample_rate)
                
                for chunk in audio_chunks:
                    wav_file.writeframes(chunk.audio_int16_bytes)
            
            return True
        return False
        
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to generate '{word}': {e}{Style.RESET_ALL}")
        return False

def generate_word_library(output_dir: str = None, voice_path: str = None):
    """Generate audio files for entire word library"""
    # Setup output directory
    if output_dir is None:
        output_dir = os.path.join(PROJECT_DIR, "word_library")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Combine words and numbers
    all_words = list(set(COMMON_WORDS + COMMON_NUMBERS))  # Remove duplicates
    all_words.sort()  # Sort alphabetically
    
    total_words = len(all_words)
    
    print(f"\n{Fore.YELLOW}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Word Library Audio Generator{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}\n")
    print(f"{Fore.CYAN}Total words to generate: {total_words}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Output directory: {output_dir}{Style.RESET_ALL}\n")
    
    # Load voice model once
    try:
        voice = load_voice(voice_path)
    except Exception as e:
        print(f"{Fore.RED}Failed to load voice model: {e}{Style.RESET_ALL}")
        return
    
    # Generate audio for each word
    start_time = time.time()
    success_count = 0
    failed_words = []
    
    for idx, word in enumerate(all_words, 1):
        # Progress indicator
        if idx % 50 == 0 or idx == 1:
            print(f"{Fore.MAGENTA}Progress: {idx}/{total_words} ({idx*100//total_words}%){Style.RESET_ALL}")
        
        if generate_word_audio(voice, word, output_dir):
            success_count += 1
        else:
            failed_words.append(word)
    
    elapsed_time = time.time() - start_time
    
    # Summary
    print(f"\n{Fore.YELLOW}{'='*60}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}✓ Generation Complete!{Style.RESET_ALL}\n")
    print(f"{Fore.CYAN}Statistics:{Style.RESET_ALL}")
    print(f"  Total words: {total_words}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {len(failed_words)}")
    print(f"  Time elapsed: {elapsed_time:.2f} seconds")
    print(f"  Average time per word: {elapsed_time/total_words:.3f} seconds")
    print(f"\n{Fore.WHITE}Output location: {output_dir}{Style.RESET_ALL}")
    
    if failed_words:
        print(f"\n{Fore.YELLOW}Failed words:{Style.RESET_ALL}")
        for word in failed_words[:10]:  # Show first 10
            print(f"  - {word}")
        if len(failed_words) > 10:
            print(f"  ... and {len(failed_words) - 10} more")
    
    print(f"{Fore.YELLOW}{'='*60}{Style.RESET_ALL}\n")

# Standalone execution
if __name__ == "__main__":
    generate_word_library()