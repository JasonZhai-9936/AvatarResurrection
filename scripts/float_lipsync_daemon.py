"""
Modular FLOAT Lip-Sync System (DAEMON)

This script is run by 'float_lipsync_subprocess.py' inside the 'FLOAT'
conda environment.

It listens for JSON commands on stdin and writes JSON responses to stdout.
"""

import sys
import os

try:
    # Remove the script's own directory (PROJECT_DIR/scripts) from the path
    # This prevents accidental circular imports of the manager script
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    if SCRIPT_DIR in sys.path:
        sys.path.remove(SCRIPT_DIR)

    # Add the project root (one level up) to the path
    # This allows it to find the 'models' directory
    PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
except Exception as e:
    # If this fails, we can't run. Send error as JSON.
    import json
    print(json.dumps({"status": "error", "message": f"Daemon sys.path setup failed: {e}"}), flush=True)
    sys.exit(1)


import json
import types
import time
import datetime
import tempfile
import subprocess

# We must send all errors to stdout as JSON so the manager can see them.
# Regular logs should go to stderr.

def send_response(response):
    """Prints a JSON response to stdout."""
    try:
        print(json.dumps(response), flush=True)
    except Exception as e:
        # Fallback if serialization fails
        print(json.dumps({"status": "error", "message": f"Failed to serialize response: {e}"}), flush=True)

# Add a try-except for imports to give better errors
try:
    import torch
    import random
    import cv2
    import torchvision
    import librosa
    import face_alignment
    import numpy as np
    import albumentations as A
    import albumentations.pytorch.transforms as A_pytorch
    from transformers import Wav2Vec2FeatureExtractor
    
    # Now that the path is correct, we can import this at the top
    from models.float.FLOAT import FLOAT

except ImportError as e:
    send_response({"status": "error", "message": f"Daemon import error: {e}. Please ensure all dependencies (torch, torchvision, librosa, face_alignment, etc.) are installed in the 'FLOAT' conda environment."})
    sys.exit(1)

# This global is set by initialize_system
LIPSYNC_SYSTEM = None

def initialize_system(project_dir, config):
    """
    Initializes the FloatLipSync class.
    This replaces the __init__ logic.
    """
    global LIPSYNC_SYSTEM
    try:
        # The 'models' import is already done at the top
        # Create the lip-sync object
        LIPSYNC_SYSTEM = FloatLipSync(project_dir, config, FLOAT)
        send_response({"status": "ok", "type": "preload_complete"})
    except Exception as e:
        import traceback
        send_response({"status": "error", "message": f"Initialization failed: {traceback.format_exc()}"})

def generate_video(audio_path, res_video_path):
    """Runs the generation process."""
    global LIPSYNC_SYSTEM
    if LIPSYNC_SYSTEM is None:
        send_response({"status": "error", "message": "System not initialized."})
        return

    try:
        video_path = LIPSYNC_SYSTEM.generate(
            audio_path=audio_path,
            res_video_path=res_video_path
        )
        send_response({"status": "ok", "type": "generate_complete", "video_path": video_path})
    except Exception as e:
        import traceback
        send_response({"status": "error", "message": f"Generation failed: {traceback.format_exc()}"})


class FloatLipSync:
    def __init__(self, project_dir: str, config: dict, FLOAT_model_class):
        """
        Initializes the entire lip-sync system.
        This "pre-loads" all models and pre-processes the default reference image.
        """
        init_start = time.time()
        print(f"[DAEMON] Initializing FLOAT System...", file=sys.stderr, flush=True)

        # 1. --- Build options from config ---
        self.opt = types.SimpleNamespace()

        # Paths (relative to project_dir)
        self.opt.ref_path = os.path.abspath(os.path.join(project_dir, config.get("ref_path", "assets/main2.png")))
        self.opt.ckpt_path = os.path.abspath(os.path.join(project_dir, config.get("ckpt_path", "checkpoints/float.pth")))
        self.opt.wav2vec_model_path = os.path.abspath(os.path.join(project_dir, config.get("wav2vec_model_path", "checkpoints/wav2vec2-base-960h")))
        self.opt.audio2emotion_path = os.path.abspath(os.path.join(project_dir, config.get("audio2emotion_path", "checkpoints/wav2vec-english-speech-emotion-recognition")))
        self.opt.res_dir = os.path.abspath(os.path.join(project_dir, "tempstream"))

        # User's command options
        self.opt.seed = config.get("seed", 15)
        self.opt.a_cfg_scale = config.get("a_cfg_scale", 2.0)
        self.opt.e_cfg_scale = config.get("e_cfg_scale", 1.0)
        self.opt.no_crop = config.get("no_crop", False)
        self.opt.nfe = config.get("nfe", 10)
        self.opt.fps = config.get("fps", 25.)
        self.opt.r_cfg_scale = config.get("r_cfg_scale", 1.0)
        
        # Other required options from main script
        self.opt.rank = 0
        self.opt.ngpus = 1
        self.opt.emo = 'S2E'

        # Options from base_options.py
        self.opt.pretrained_dir = os.path.abspath(os.path.join(project_dir, 'checkpoints'))
        
        self.opt.fix_noise_seed = False
        self.opt.input_size = 512
        self.opt.input_nc = 3
        self.opt.sampling_rate = 16000
        self.opt.audio_marcing = 2
        self.opt.wav2vec_sec = 2.0
        self.opt.attention_window = 2
        self.opt.only_last_features = False
        self.opt.average_emotion = False
        self.opt.audio_dropout_prob = 0.1
        self.opt.ref_dropout_prob = 0.1
        self.opt.emotion_dropout_prob = 0.1
        self.opt.style_dim = 512
        self.opt.dim_a = 512
        self.opt.dim_w = 512
        self.opt.dim_h = 1024
        self.opt.dim_m = 20
        self.opt.dim_e = 7
        self.opt.fmt_depth = 8
        self.opt.num_heads = 8
        self.opt.mlp_ratio = 4.0
        self.opt.no_learned_pe = False
        self.opt.num_prev_frames = 10
        self.opt.max_grad_norm = 1.0
        self.opt.ode_atol = 1e-5
        self.opt.ode_rtol = 1e-5
        self.opt.torchdiffeq_ode_method = 'euler'
        self.opt.n_diff_steps = 500
        self.opt.diff_schedule = 'cosine'
        self.opt.diffusion_mode = 'sample'
        
        os.makedirs(self.opt.res_dir, exist_ok=True)

        # 2. --- Initialize DataProcessor components ---
        print(f"[DAEMON] [1/4] Loading data processor models...", file=sys.stderr, flush=True)
        torch.cuda.empty_cache()
        self.device = torch.device(f"cuda:{self.opt.rank}" if torch.cuda.is_available() else "cpu")
        print(f"[DAEMON] Using device: {self.device}", file=sys.stderr, flush=True)

        start = time.time()
        self.fa = face_alignment.FaceAlignment(face_alignment.LandmarksType.TWO_D, flip_input=False, device=str(self.device))
        print(f"[DAEMON]   ✓ Face alignment model loaded: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        start = time.time()
        self.wav2vec_preprocessor = Wav2Vec2FeatureExtractor.from_pretrained(
            self.opt.wav2vec_model_path, local_files_only=True
        )
        print(f"[DAEMON]   ✓ Wav2Vec2 preprocessor loaded: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        self.transform = A.Compose([
            A.Resize(height=self.opt.input_size, width=self.opt.input_size, interpolation=cv2.INTER_AREA),
            A.Normalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5)),
            A_pytorch.ToTensorV2(),
        ])

        # 3. --- Initialize InferenceAgent components ---
        print(f"[DAEMON] [2/4] Loading FLOAT model architecture...", file=sys.stderr, flush=True)
        start = time.time()
        self.G = FLOAT_model_class(self.opt)
        print(f"[DAEMON]   ✓ Model architecture created: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        print(f"[DAEMON] [3/4] Loading checkpoint weights...", file=sys.stderr, flush=True)
        start = time.time()
        self.load_weight(self.opt.ckpt_path, self.device)
        print(f"[DAEMON]   ✓ Checkpoint weights loaded: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        start = time.time()
        self.G.to(self.device)
        self.G.eval()
        print(f"[DAEMON]   ✓ Model moved to device & set to eval: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        # 4. --- Pre-process and cache the reference image ---
        print(f"[DAEMON] [4/4] Pre-processing reference image: {self.opt.ref_path}", file=sys.stderr, flush=True)
        self._preload_reference_image(self.opt.ref_path)

        print(f"\n[DAEMON] ✓✓✓ TOTAL INITIALIZATION TIME: {time.time() - init_start:.3f}s", file=sys.stderr, flush=True)
        print(f"[DAEMON] ✓✓✓ System is ready to generate.", file=sys.stderr, flush=True)

    def _preload_reference_image(self, ref_path: str):
        start_total = time.time()
        
        if not os.path.exists(ref_path):
            raise FileNotFoundError(f"Reference image not found: {ref_path}")

        start = time.time()
        s = self.default_img_loader(ref_path)
        print(f"[DAEMON]   - Image loading: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        if not self.opt.no_crop:
            start = time.time()
            s = self.process_img(s)
            print(f"[DAEMON]   - Face detection & crop: {time.time() - start:.3f}s", file=sys.stderr, flush=True)
        else:
            print(f"[DAEMON]   - Face detection & crop: SKIPPED (no_crop=True)", file=sys.stderr, flush=True)

        start = time.time()
        self.preprocessed_ref_image = self.transform(image=s)['image'].unsqueeze(0)
        print(f"[DAEMON]   - Image transform: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        start = time.time()
        self.preprocessed_ref_image = self.preprocessed_ref_image.to(self.device)
        print(f"[DAEMON]   - Image moved to device: {time.time() - start:.3f}s", file=sys.stderr, flush=True)

        print(f"[DAEMON]   ✓ Total image preprocessing: {time.time() - start_total:.3f}s", file=sys.stderr, flush=True)

    def load_weight(self, checkpoint_path: str, device: torch.device) -> None:
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
            
        load_start = time.time()
        state_dict = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
        print(f"[DAEMON]     - Checkpoint file read: {time.time() - load_start:.3f}s", file=sys.stderr, flush=True)

        copy_start = time.time()
        param_count = 0
        with torch.no_grad():
            for model_name, model_param in self.G.named_parameters():
                if model_name in state_dict:
                    model_param.copy_(state_dict[model_name].to(device))
                    param_count += 1
                elif "wav2vec2" in model_name:
                    pass
                else:
                    print(f"[DAEMON]     ! Warning; {model_name} not in state_dict.", file=sys.stderr, flush=True)
        print(f"[DAEMON]     - Params copied ({param_count} params): {time.time() - copy_start:.3f}s", file=sys.stderr, flush=True)
        del state_dict

    @torch.no_grad()
    def process_img(self, img: np.ndarray) -> np.ndarray:
        mult = 360. / img.shape[0]
        resized_img = cv2.resize(img, dsize=(0, 0), fx=mult, fy=mult, interpolation=cv2.INTER_AREA if mult < 1. else cv2.INTER_CUBIC)
        bboxes = self.fa.face_detector.detect_from_image(resized_img)
        bboxes = [(int(x1 / mult), int(y1 / mult), int(x2 / mult), int(y2 / mult), score) for (x1, y1, x2, y2, score) in bboxes if score > 0.95]
        if not bboxes:
             raise RuntimeError("No face detected in reference image for cropping.")
        bboxes = bboxes[0]
        bsy = int((bboxes[3] - bboxes[1]) / 2)
        bsx = int((bboxes[2] - bboxes[0]) / 2)
        my = int((bboxes[1] + bboxes[3]) / 2)
        mx = int((bboxes[0] + bboxes[2]) / 2)
        bs = int(max(bsy, bsx) * 1.6)
        
        # --- FIX: Changed from BORDER_CONSTANT to BORDER_REPLICATE ---
        img = cv2.copyMakeBorder(img, bs, bs, bs, bs, cv2.BORDER_REPLICATE)
        # -----------------------------------------------------------
        
        my, mx = my + bs, mx + bs
        crop_img = img[my - bs:my + bs, mx - bs:mx + bs]
        crop_img = cv2.resize(crop_img, dsize=(self.opt.input_size, self.opt.input_size), interpolation=cv2.INTER_AREA if mult < 1. else cv2.INTER_CUBIC)
        return crop_img

    def default_img_loader(self, path) -> np.ndarray:
        img = cv2.imread(path)
        if img is None:
            raise IOError(f"Could not read image file: {path}")
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def default_aud_loader(self, path: str) -> torch.Tensor:
        speech_array, sampling_rate = librosa.load(path, sr=self.opt.sampling_rate)
        return self.wav2vec_preprocessor(speech_array, sampling_rate=sampling_rate, return_tensors='pt').input_values[0]

    def save_video(self, vid_target_recon: torch.Tensor, video_path: str, audio_path: str) -> str:
        """
        GPU-ACCELERATED variant: Uses NVIDIA NVENC hardware encoder.
        """
        save_start = time.time()
        
        prep_start = time.time()
        vid = vid_target_recon.permute(0, 2, 3, 1)
        
        # OPTIMIZATION: Ensure tensor is contiguous before converting to bytes
        # This prevents stride issues that can cause diagonal warping/artifacts
        vid = vid.detach().clamp(-1, 1).contiguous()
        vid = ((vid + 1) / 2 * 255).to(torch.uint8)
        vid = vid.cpu().numpy()
        
        print(f"[DAEMON]     - Video tensor prep: {time.time() - prep_start:.3f}s", file=sys.stderr, flush=True)
        
        height, width = vid.shape[1], vid.shape[2]
        
        encode_start = time.time()
        
        if audio_path is not None:
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', f'{width}x{height}', '-pix_fmt', 'rgb24', '-r', str(self.opt.fps),
                '-i', '-',
                '-i', audio_path,
                '-c:v', 'h264_nvenc',
                '-preset', 'p1',
                '-tune', 'll',
                '-cq', '28',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k',
                '-shortest',
                video_path
            ]
        else:
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', f'{width}x{height}', '-pix_fmt', 'rgb24', '-r', str(self.opt.fps),
                '-i', '-',
                '-c:v', 'h264_nvenc',
                '-preset', 'p1',
                '-tune', 'll',
                '-cq', '28',
                '-pix_fmt', 'yuv420p',
                video_path
            ]
        
        try:
            process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            process.stdin.write(vid.tobytes())
            process.stdin.close()
            stderr_output = process.communicate()[1]
            
            if process.returncode != 0:
                print(f"[DAEMON]     ! NVENC failed, falling back to CPU encoding", file=sys.stderr, flush=True)
                return self.save_video_optimized(vid_target_recon, video_path, audio_path)
            
        except Exception as e:
            print(f"[DAEMON]     ! NVENC error: {e}, falling back to CPU encoding", file=sys.stderr, flush=True)
            return self.save_video_optimized(vid_target_recon, video_path, audio_path)
        
        print(f"[DAEMON]     - GPU encode + mux: {time.time() - encode_start:.3f}s", file=sys.stderr, flush=True)
        print(f"[DAEMON]   ✓ Total saving time: {time.time() - save_start:.3f}s", file=sys.stderr, flush=True)
        
        return video_path
        
    def save_video_optimized(self, vid_target_recon: torch.Tensor, video_path: str, audio_path: str) -> str:
        """
        Fallback CPU encoding method.
        """
        import torchvision
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_video:
            temp_filename = temp_video.name
            vid = vid_target_recon.permute(0, 2, 3, 1)
            vid = vid.detach().clamp(-1, 1).cpu()
            vid = ((vid + 1) / 2 * 255).type('torch.ByteTensor')
            torchvision.io.write_video(temp_filename, vid, fps=self.opt.fps)            
            if audio_path is not None:
                with open(os.devnull, 'wb') as f:
                    command =  "ffmpeg -i {} -i {} -c:v copy -c:a aac {} -y".format(temp_filename, audio_path, video_path)
                    subprocess.call(command, shell=True, stdout=f, stderr=f)
                if os.path.exists(video_path):
                    os.remove(temp_filename)
            else:
                os.rename(temp_filename, video_path)
            return video_path

    @torch.no_grad()
    def generate(self, audio_path: str, res_video_path: str = None, emo: str = 'S2E') -> str:
        inference_start = time.time()
        print(f"\n[DAEMON] RUNNING INFERENCE ON: {os.path.basename(audio_path)}", file=sys.stderr, flush=True)

        if res_video_path is None:
            os.makedirs(self.opt.res_dir, exist_ok=True)
            video_name = os.path.splitext(os.path.basename(self.opt.ref_path))[0]
            audio_name = os.path.splitext(os.path.basename(audio_path))[0]
            call_time = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            res_video_path = os.path.join(self.opt.res_dir, f"{call_time}-{video_name}-{audio_name}-float.mp4")

        print(f"[DAEMON] [1/3] PREPROCESSING AUDIO", file=sys.stderr, flush=True)
        start = time.time()
        processed_audio = self.default_aud_loader(audio_path).unsqueeze(0).to(self.device)
        print(f"[DAEMON]   - Audio loading & preprocessing: {time.time() - start:.3f}s", file=sys.stderr, flush=True)
        data = {'s': self.preprocessed_ref_image, 'a': processed_audio, 'p': None, 'e': None}

        print(f"[DAEMON] [2/3] MODEL INFERENCE", file=sys.stderr, flush=True)
        gen_start = time.time()
        d_hat = self.G.inference(
            data=data,
            a_cfg_scale=self.opt.a_cfg_scale,
            r_cfg_scale=self.opt.r_cfg_scale,
            e_cfg_scale=self.opt.e_cfg_scale,
            emo=emo,
            nfe=self.opt.nfe,
            seed=self.opt.seed
        )['d_hat']
        gen_time = time.time() - gen_start
        print(f"[DAEMON]   ✓ Generation complete: {gen_time:.3f}s", file=sys.stderr, flush=True)
        print(f"[DAEMON]   ✓ NFE: {self.opt.nfe}", file=sys.stderr, flush=True)

        print(f"[DAEMON] [3/3] SAVING VIDEO", file=sys.stderr, flush=True)
        res_video_path = self.save_video(d_hat, res_video_path, audio_path)
        
        print(f"\n[DAEMON] ✓ TOTAL INFERENCE TIME: {time.time() - inference_start:.3f}s", file=sys.stderr, flush=True)
        print(f"[DAEMON] ✓ Result saved at: {res_video_path}", file=sys.stderr, flush=True)
        return res_video_path

def main_loop():
    """Listens for commands on stdin and processes them."""
    # Signal readiness
    send_response({"status": "ok", "type": "ready"})
    
    for line in sys.stdin:
        try:
            command = json.loads(line)
            cmd_type = command.get("command")

            if cmd_type == "preload":
                initialize_system(command.get("project_dir"), command.get("config"))
            elif cmd_type == "generate":
                generate_video(command.get("audio_path"), command.get("res_video_path"))
            elif cmd_type == "quit":
                print("[DAEMON] Quit command received. Exiting.", file=sys.stderr, flush=True)
                break
            else:
                send_response({"status": "error", "message": f"Unknown command: {cmd_type}"})
        
        except json.JSONDecodeError:
            send_response({"status": "error", "message": "Invalid JSON command."})
        except Exception as e:
            send_response({"status": "error", "message": f"Main loop error: {e}"})

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("[DAEMON] Interrupted.", file=sys.stderr, flush=True)
    except Exception as e:
        send_response({"status": "error", "message": f"Daemon main loop crashed: {e}"})