# DarwinChatbot

Requirements
- Windows/Linux   
- NVIDIA GPU  
  Check your CUDA version:  
  ```bash
  nvcc -V  #To avoid issues, v12.6 is ideal, but any v12.x should work. 11.8 may also work
  ```

Installation Guide

1. Make sure your system has Git, [conda](https://www.anaconda.com/docs/getting-started/miniconda/install), and FFmpeg installed ([HOW TO INSTALL FFMPEG](FFMPEGInstall.md))


```bash
# 2. Clone the code and prepare the environment 
git clone https://github.com/JasonZhai-9936/DarwinChatbot.git
cd DarwinChatbot

***groq key

# 3. Make a new miniconda environment
conda create -n DarwinChatbot python=3.10 -y
conda activate DarwinChatbot

# 4. Install base project dependencies
pip install -r requirements.txt

#5. Run the installation script:
python install_requirements.py

#OR run each separately

  a. python install_ollama_model.py
  b. python install_LivePortrait.py
  c. python install_latentsync.py
  d. python install_sparktts.py
  e. python move_assets.py

```

Quickstart 
```bash
# 1. Start env if not already open
conda activate DarwinChatbot

# 2. Run app.py
python ./scripts/app.py

```




