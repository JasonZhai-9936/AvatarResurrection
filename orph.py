import torch
import soundfile as sf
import numpy as np
import os
from transformers import AutoModelForCausalLM, AutoTokenizer
from snac import SNAC

# --- CONFIGURATION ---
MODEL_ID = "canopylabs/orpheus-3b-0.1-ft"
VOICE = "dan" 

# Updated Emotions list with "Darwin-style" acting
EMOTIONS = [
    {
        "name": "scared",
        "text": "I amn truly terrified <gasp>. I think that something is hunting me. My heart is pounding and I fear for my life."
    },
    

]

# --- SETUP ---
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading {MODEL_ID} on {device}...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16).to(device)
snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").to(device)

# --- HELPER: DYNAMIC NAMING ---
def get_next_filename(base_name, ext="wav"):
    """
    Checks for file_1.wav, file_2.wav etc. and returns the next free slot.
    """
    i = 1
    while True:
        candidate = f"{base_name}_{i}.{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1

def decode_aligned_tokens(token_list):
    # Filter and Align
    codes = [t - 128266 for t in token_list if t >= 128266]
    codes = codes[:(len(codes) // 7) * 7]

    # Reconstruct Layers
    L1, L2, L3 = [], [], []
    for i in range(0, len(codes), 7):
        L1.append(codes[i])
        L2.append(codes[i+1] - 4096)
        L2.append(codes[i+4] - 4096*4)
        L3.append(codes[i+2] - 4096*2)
        L3.append(codes[i+3] - 4096*3)
        L3.append(codes[i+5] - 4096*5)
        L3.append(codes[i+6] - 4096*6)

    layers = [
        torch.tensor(L1).unsqueeze(0).to(device),
        torch.tensor(L2).unsqueeze(0).to(device),
        torch.tensor(L3).unsqueeze(0).to(device)
    ]
    
    with torch.inference_mode():
        audio = snac_model.decode(layers)
    
    # Silence Prepend
    audio_np = audio.squeeze().cpu().numpy()
    silence = np.zeros(2400, dtype=np.float32) 
    return np.concatenate((silence, audio_np))

# --- GENERATE LOOP ---
for emo in EMOTIONS:
    print(f"Generating {emo['name']} clip...")
    
    full_prompt_text = f"{VOICE}: {emo['text']}"
    text_ids = tokenizer.encode(full_prompt_text, add_special_tokens=False)
    
    start_tokens = [tokenizer.bos_token_id, 128259] + text_ids + [128009, 128260, 128261, 128257]
    start_seq = torch.tensor(start_tokens, device=device).unsqueeze(0)
    attention_mask = torch.ones_like(start_seq)

    with torch.no_grad():
        output = model.generate(
            start_seq,
            attention_mask=attention_mask,
            max_new_tokens=1500,
            do_sample=True,
            temperature=2.9,
            top_p=0.9,
            repetition_penalty=1.1,
            eos_token_id=128258 
        )

    # Decode and Save
    output_list = output[0].tolist()
    try:
        audio_start_index = len(start_tokens) - 1 
        generated_part = output_list[audio_start_index+1:]
        audio_data = decode_aligned_tokens(generated_part)
        
        # --- NEW: Dynamic Naming Logic ---
        base_name = f"output_{emo['name']}"
        filename = get_next_filename(base_name)
        
        sf.write(filename, audio_data, 24000)
        print(f" -> Saved to {filename}")
        
    except ValueError:
        print("Error in generation.")

print("Done!")