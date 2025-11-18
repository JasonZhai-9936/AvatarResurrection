# Darwin Avatar Chatbot

### Verify CUDA Installation
```bash
nvcc --version
# Should show CUDA version 11.8 or 12.x
```
## Installation 

#### Step 1: Prerequisites
Ensure you have:
- [Git](https://git-scm.com/)
- [Miniconda/Anaconda](https://docs.anaconda.com/miniconda/)
- [FFmpeg](https://ffmpeg.org/download.html)
- NVIDIA GPU with CUDA drivers

#### Step 2: Clone Repository
```bash
git clone https://github.com/YourUsername/DarwinChatbot.git
cd DarwinChatbot
```

### Option 1: One-Click Install (Recommended for Windows + CUDA)

1. **Run the one-click installer:**
   ```bash
   python quick_install.py
   ```
  **What it does automatically:**
   - Creates conda environment with Python 3.10
   - Installs all dependencies (PyTorch, FLOAT, Piper, etc.)
   - Downloads FLOAT checkpoints (~2GB)
   - Sets up project structure
   - Configures API keys (interactive)

---

### Option 2: Manual Installation


#### Step 1: Main Environment Setup
```bash
# Create main environment
conda create -n DarwinChatbot python=3.10 -y
conda activate DarwinChatbot

# Install core dependencies
pip install -r requirements.txt
```

#### Step 2: FLOAT Setup

```bash
# A. Create FLOAT environment(Ensure you are inside project root)
git clone https://github.com/deepbrainai-research/float.git
cd float
conda create -n FLOAT python=3.8.5 -y
conda activate FLOAT

# B. Install requirements
sh environments.sh

# or manual installation
pip install torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt

# C. Download FLOAT Checkpoints
sh download_checkpoints.sh
# or download checkpoints manually from https://drive.google.com/file/d/1rvWuM12cyvNvBQNCLmG4Fr2L1rpjQBF0/view

# D. Download both supporting W2V models at
https://huggingface.co/facebook/wav2vec2-base-960h
https://huggingface.co/r-f/wav2vec-english-speech-emotion-recognition

# E. Verify Structure
# The checkpoints should be organized as follows:
./checkpoints/
├── float.pth
├── wav2vec2-base-960h/
│   ├── config.json
│   ├── pytorch_model.bin
│   └── ...
└── wav2vec-english-speech-emotion-recognition/
    ├── config.json
    ├── pytorch_model.bin
    └── ...

```


#### Step 3: API Configuration
1. **Groq API Key** (for Both LLM and TTS):
   - Sign up at [Groq Console](https://console.groq.com/)
   - Create `groq_api_key.txt` in project root
   - Paste your API key

#### Step 4: Launch Application
```bash
conda activate DarwinChatbot
python scripts/final_main.py
```

#### Additional Settings

#### New Avatar Setup
Place your avatar assets in the appropriate directory:
```
avatars/Darwin/
├── Nodes/main2main/          # Idle videos
├── pre-generated responses/   # Pre-generated response videos
├── idle_chunks/              # Thinking loop videos
└── assets/
    └── main2.png            # Reference image for FLOAT
```

## Configuration

### Basic Configuration (`config.json`)
```json
{
  "maxWords": 50,
  "speechSpeed": 1.05,
  "useCuda": true,
  "lipsyncMode": "float",
  "avatarName": "Darwin",
  "webUI": {
    "host": "0.0.0.0",
    "port": 8080,
    "reload": false
  }
}
```

### Avatar Configuration
- **Lipsync Mode**: Toggle between `"float"` and `"crossfade"` in `final_main.py`
- **Pre-generated Responses**: Set `USE_PREGENERATED_RESPONSE` to enable/disable
- **TTS Provider**: Switch between Groq API and Piper TTS


## Project Structure

```
DarwinChatbot/
├── scripts/                    # Main application scripts
│   ├── final_main.py          # Main application entry point
│   ├── ui.py                  # Web interface
│   ├── LLM_Groq.py           # Groq API integration
│   ├── enhanced_tts_groq.py   # Groq TTS
│   ├── enhanced_tts_piper.py  # Piper TTS
│   ├── float_lipsync_daemon.py # FLOAT subprocess
│   └── simplified_video_manager.py # Video control
├── avatars/Darwin/            # Avatar assets
├── checkpoints/               # FLOAT model checkpoints
├── tempstream/                # Generated audio/video files
├── requirements.txt           # Python dependencies
├── config.json               # Application configuration
├── groq_api_key.txt          # API key file
└── quick_install.py          # One-click installer
```

### Performance Optimizations

1. **Float**: Lower NFE



## Acknowledgments

- **FLOAT**: Advanced lip-sync technology
- **Groq**: Fast LLM inference and TTS
- **Piper**: High-quality offline TTS
- **NiceGUI**: Modern web interface framework

