#!/usr/bin/env python3
"""
Single script for MuseTalk lipsync - handles everything internally
"""

import os
import sys
import cv2
import torch
import glob
import pickle
import time
import copy
import json
import queue
import threading
import subprocess
import shutil
import numpy as np
from tqdm import tqdm
from transformers import WhisperModel

# Import MuseTalk modules (adjust imports based on your actual module structure)
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.utils import datagen
from musetalk.utils.preprocessing import get_landmark_and_bbox, read_imgs
from musetalk.utils.blending import get_image_prepare_material, get_image_blending
from musetalk.utils.utils import load_all_model
from musetalk.utils.audio_processor import AudioProcessor


class MuseTalkLipsync:
    def __init__(self):
        # Configuration - modify these paths according to your setup
        self.config = {
            'version': 'v15',
            'gpu_id': 0,
            'vae_type': 'sd-vae',
            'unet_config': './models/musetalkV15/musetalk.json',
            'unet_model_path': './models/musetalkV15/unet.pth',
            'whisper_dir': './models/whisper',
            'ffmpeg_path': 'C:/ffmpeg/bin',
            'result_dir': './results',
            'bbox_shift': 0,  # v15 uses 0, v1 uses bbox_shift from config
            'extra_margin': 10,
            'fps': 25,
            'audio_padding_length_left': 2,
            'audio_padding_length_right': 2,
            'batch_size': 20,
            'parsing_mode': 'jaw',
            'left_cheek_width': 90,
            'right_cheek_width': 90,
            'skip_save_images': False
        }
        
        self.device = None
        self.models_loaded = False
        self.vae = None
        self.unet = None
        self.pe = None
        self.whisper = None
        self.audio_processor = None
        self.fp = None
        self.timesteps = None
        
    def setup_ffmpeg(self):
        """Setup ffmpeg path"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except:
            print("Adding ffmpeg to PATH")
            path_separator = ';' if sys.platform == 'win32' else ':'
            os.environ["PATH"] = f"{self.config['ffmpeg_path']}{path_separator}{os.environ['PATH']}"
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
                return True
            except:
                print("Warning: Unable to find ffmpeg, please ensure ffmpeg is properly installed")
                return False
    
    def load_models(self):
        """Load all required models"""
        if self.models_loaded:
            return
            
        print("Loading models...")
        
        # Set device
        self.device = torch.device(f"cuda:{self.config['gpu_id']}" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        
        # Load models
        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=self.config['unet_model_path'],
            vae_type=self.config['vae_type'],
            unet_config=self.config['unet_config'],
            device=self.device
        )
        
        self.timesteps = torch.tensor([0], device=self.device)
        
        # Convert to half precision for faster inference
        self.pe = self.pe.half().to(self.device)
        self.vae.vae = self.vae.vae.half().to(self.device)
        self.unet.model = self.unet.model.half().to(self.device)
        
        # Initialize audio processor and Whisper
        self.audio_processor = AudioProcessor(feature_extractor_path=self.config['whisper_dir'])
        weight_dtype = self.unet.model.dtype
        self.whisper = WhisperModel.from_pretrained(self.config['whisper_dir'])
        self.whisper = self.whisper.to(device=self.device, dtype=weight_dtype).eval()
        self.whisper.requires_grad_(False)
        
        # Initialize face parser
        if self.config['version'] == "v15":
            self.fp = FaceParsing(
                left_cheek_width=self.config['left_cheek_width'],
                right_cheek_width=self.config['right_cheek_width']
            )
        else:
            self.fp = FaceParsing()
        
        self.models_loaded = True
        print("Models loaded successfully!")
    
    def video2imgs(self, vid_path, save_path, ext='.png', cut_frame=10000000):
        """Extract frames from video"""
        cap = cv2.VideoCapture(vid_path)
        count = 0
        while True:
            if count > cut_frame:
                break
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(f"{save_path}/{count:08d}.png", frame)
                count += 1
            else:
                break
        cap.release()
    
    def prepare_avatar(self, avatar_id, video_path, force_recreate=False):
        """Prepare avatar materials"""
        print(f"Preparing avatar: {avatar_id}")
        
        # Setup paths
        if self.config['version'] == "v15":
            base_path = f"{self.config['result_dir']}/{self.config['version']}/avatars/{avatar_id}"
        else:
            base_path = f"{self.config['result_dir']}/avatars/{avatar_id}"
            
        full_imgs_path = f"{base_path}/full_imgs"
        coords_path = f"{base_path}/coords.pkl"
        latents_path = f"{base_path}/latents.pt"
        mask_path = f"{base_path}/mask"
        mask_coords_path = f"{base_path}/mask_coords.pkl"
        avatar_info_path = f"{base_path}/avator_info.json"
        
        # Create directories
        os.makedirs(base_path, exist_ok=True)
        os.makedirs(full_imgs_path, exist_ok=True)
        os.makedirs(mask_path, exist_ok=True)
        
        # Check if avatar already exists
        if os.path.exists(coords_path) and not force_recreate:
            print(f"Avatar {avatar_id} already prepared, loading existing data...")
            return self.load_avatar_data(base_path)
        
        # Save avatar info
        avatar_info = {
            "avatar_id": avatar_id,
            "video_path": video_path,
            "bbox_shift": self.config['bbox_shift'],
            "version": self.config['version']
        }
        with open(avatar_info_path, "w") as f:
            json.dump(avatar_info, f)
        
        # Extract frames
        if os.path.isfile(video_path):
            self.video2imgs(video_path, full_imgs_path, ext='png')
        else:
            # Copy existing images
            files = sorted([f for f in os.listdir(video_path) if f.endswith('.png')])
            for filename in files:
                shutil.copyfile(f"{video_path}/{filename}", f"{full_imgs_path}/{filename}")
        
        input_img_list = sorted(glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]')))
        
        print("Extracting landmarks...")
        coord_list, frame_list = get_landmark_and_bbox(input_img_list, self.config['bbox_shift'])
        
        # Process latents
        input_latent_list = []
        coord_placeholder = (0.0, 0.0, 0.0, 0.0)
        
        for idx, (bbox, frame) in enumerate(zip(coord_list, frame_list)):
            if bbox == coord_placeholder:
                continue
            x1, y1, x2, y2 = bbox
            if self.config['version'] == "v15":
                y2 = y2 + self.config['extra_margin']
                y2 = min(y2, frame.shape[0])
                coord_list[idx] = [x1, y1, x2, y2]
            
            crop_frame = frame[y1:y2, x1:x2]
            resized_crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents = self.vae.get_latents_for_unet(resized_crop_frame)
            input_latent_list.append(latents)
        
        # Create cycles (forward + backward)
        frame_list_cycle = frame_list + frame_list[::-1]
        coord_list_cycle = coord_list + coord_list[::-1]
        input_latent_list_cycle = input_latent_list + input_latent_list[::-1]
        
        # Process masks
        mask_coords_list_cycle = []
        mask_list_cycle = []
        
        print("Processing masks...")
        for i, frame in enumerate(tqdm(frame_list_cycle)):
            cv2.imwrite(f"{full_imgs_path}/{str(i).zfill(8)}.png", frame)
            
            x1, y1, x2, y2 = coord_list_cycle[i]
            mode = self.config['parsing_mode'] if self.config['version'] == "v15" else "raw"
            mask, crop_box = get_image_prepare_material(frame, [x1, y1, x2, y2], fp=self.fp, mode=mode)
            
            cv2.imwrite(f"{mask_path}/{str(i).zfill(8)}.png", mask)
            mask_coords_list_cycle.append(crop_box)
            mask_list_cycle.append(mask)
        
        # Save processed data
        with open(mask_coords_path, 'wb') as f:
            pickle.dump(mask_coords_list_cycle, f)
        with open(coords_path, 'wb') as f:
            pickle.dump(coord_list_cycle, f)
        torch.save(input_latent_list_cycle, latents_path)
        
        return {
            'base_path': base_path,
            'frame_list_cycle': frame_list_cycle,
            'coord_list_cycle': coord_list_cycle,
            'input_latent_list_cycle': input_latent_list_cycle,
            'mask_list_cycle': mask_list_cycle,
            'mask_coords_list_cycle': mask_coords_list_cycle
        }
    
    def load_avatar_data(self, base_path):
        """Load existing avatar data"""
        coords_path = f"{base_path}/coords.pkl"
        latents_path = f"{base_path}/latents.pt"
        mask_coords_path = f"{base_path}/mask_coords.pkl"
        full_imgs_path = f"{base_path}/full_imgs"
        mask_path = f"{base_path}/mask"
        
        # Load data
        input_latent_list_cycle = torch.load(latents_path)
        with open(coords_path, 'rb') as f:
            coord_list_cycle = pickle.load(f)
        with open(mask_coords_path, 'rb') as f:
            mask_coords_list_cycle = pickle.load(f)
        
        # Load images
        input_img_list = sorted(glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]')),
                               key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
        frame_list_cycle = read_imgs(input_img_list)
        
        input_mask_list = sorted(glob.glob(os.path.join(mask_path, '*.[jpJP][pnPN]*[gG]')),
                                key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
        mask_list_cycle = read_imgs(input_mask_list)
        
        return {
            'base_path': base_path,
            'frame_list_cycle': frame_list_cycle,
            'coord_list_cycle': coord_list_cycle,
            'input_latent_list_cycle': input_latent_list_cycle,
            'mask_list_cycle': mask_list_cycle,
            'mask_coords_list_cycle': mask_coords_list_cycle
        }
    
    def process_frames_worker(self, res_frame_queue, avatar_data, video_len, output_dir):
        """Worker thread for processing frames"""
        idx = 0
        while idx < video_len:
            try:
                res_frame = res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue
            
            bbox = avatar_data['coord_list_cycle'][idx % len(avatar_data['coord_list_cycle'])]
            ori_frame = copy.deepcopy(avatar_data['frame_list_cycle'][idx % len(avatar_data['frame_list_cycle'])])
            x1, y1, x2, y2 = bbox
            
            try:
                res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
            except:
                idx += 1
                continue
            
            mask = avatar_data['mask_list_cycle'][idx % len(avatar_data['mask_list_cycle'])]
            mask_crop_box = avatar_data['mask_coords_list_cycle'][idx % len(avatar_data['mask_coords_list_cycle'])]
            combine_frame = get_image_blending(ori_frame, res_frame, bbox, mask, mask_crop_box)
            
            if not self.config['skip_save_images']:
                cv2.imwrite(f"{output_dir}/{str(idx).zfill(8)}.png", combine_frame)
            
            idx += 1
    
    @torch.no_grad()
    def generate_lipsync(self, avatar_id, video_path, audio_path, output_name=None, force_recreate_avatar=False):
        """Main function to generate lipsync video"""
        
        # Setup
        self.setup_ffmpeg()
        self.load_models()
        
        # Prepare avatar
        avatar_data = self.prepare_avatar(avatar_id, video_path, force_recreate_avatar)
        
        print("Starting lipsync generation...")
        
        # Create temporary output directory
        temp_dir = f"{avatar_data['base_path']}/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Extract audio features
        start_time = time.time()
        weight_dtype = self.unet.model.dtype
        whisper_input_features, librosa_length = self.audio_processor.get_audio_feature(
            audio_path, weight_dtype=weight_dtype)
        
        whisper_chunks = self.audio_processor.get_whisper_chunk(
            whisper_input_features,
            self.device,
            weight_dtype,
            self.whisper,
            librosa_length,
            fps=self.config['fps'],
            audio_padding_length_left=self.config['audio_padding_length_left'],
            audio_padding_length_right=self.config['audio_padding_length_right'],
        )
        print(f"Audio processing took {(time.time() - start_time) * 1000:.0f}ms")
        
        # Inference
        video_num = len(whisper_chunks)
        res_frame_queue = queue.Queue()
        
        # Start frame processing thread
        process_thread = threading.Thread(
            target=self.process_frames_worker,
            args=(res_frame_queue, avatar_data, video_num, temp_dir)
        )
        process_thread.start()
        
        # Generate frames
        gen = datagen(whisper_chunks, avatar_data['input_latent_list_cycle'], self.config['batch_size'])
        start_time = time.time()
        
        for i, (whisper_batch, latent_batch) in enumerate(
            tqdm(gen, total=int(np.ceil(float(video_num) / self.config['batch_size'])))
        ):
            audio_feature_batch = self.pe(whisper_batch.to(self.device))
            latent_batch = latent_batch.to(device=self.device, dtype=self.unet.model.dtype)
            
            pred_latents = self.unet.model(
                latent_batch,
                self.timesteps,
                encoder_hidden_states=audio_feature_batch
            ).sample
            
            pred_latents = pred_latents.to(device=self.device, dtype=self.vae.vae.dtype)
            recon = self.vae.decode_latents(pred_latents)
            
            for res_frame in recon:
                res_frame_queue.put(res_frame)
        
        # Wait for processing to complete
        process_thread.join()
        
        processing_time = time.time() - start_time
        if self.config['skip_save_images']:
            print(f'Total process time of {video_num} frames without saving images = {processing_time:.2f}s')
        else:
            print(f'Total process time of {video_num} frames including saving images = {processing_time:.2f}s')
        
        # Create final video
        if output_name and not self.config['skip_save_images']:
            output_dir = f"{avatar_data['base_path']}/vid_output"
            os.makedirs(output_dir, exist_ok=True)
            
            # Create video from frames
            temp_video = f"{avatar_data['base_path']}/temp.mp4"
            cmd_img2video = f"ffmpeg -y -v warning -r {self.config['fps']} -f image2 -i {temp_dir}/%08d.png -vcodec libx264 -vf format=yuv420p -crf 18 {temp_video}"
            print("Creating video from frames...")
            os.system(cmd_img2video)
            
            # Combine with audio
            output_path = f"{output_dir}/{output_name}.mp4"
            cmd_combine_audio = f"ffmpeg -y -v warning -i {audio_path} -i {temp_video} {output_path}"
            print("Adding audio to video...")
            os.system(cmd_combine_audio)
            
            # Cleanup
            os.remove(temp_video)
            shutil.rmtree(temp_dir)
            
            print(f"Result saved to: {output_path}")
            return output_path
        
        return None


def main():
    """Example usage"""
    # Initialize the lipsync generator
    lipsync = MuseTalkLipsync()
    
    # Example configuration - modify these paths
    avatar_id = "avatar_1"
    video_path = "data/video/d5.mp4"  # Your input video
    audio_path = "data/audio/d123.wav"  # Your input audio
    output_name = "result"  # Output filename (without extension)
    
    # Generate lipsync video
    try:
        output_path = lipsync.generate_lipsync(
            avatar_id=avatar_id,
            video_path=video_path,
            audio_path=audio_path,
            output_name=output_name,
            force_recreate_avatar=False  # Set to True to recreate avatar data
        )
        
        if output_path:
            print(f"\nLipsync generation completed successfully!")
            print(f"Output saved to: {output_path}")
        else:
            print("\nLipsync generation completed (no video saved)")
            
    except Exception as e:
        print(f"Error during lipsync generation: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()