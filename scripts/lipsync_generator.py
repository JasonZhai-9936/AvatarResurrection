import asyncio
import subprocess
import docker
import os
import time
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LipsyncDockerManager:
    def __init__(self, 
                 container_name="faster_liveportrait",
                 image_name="shaoguo/faster_liveportrait:v3",
                 host_port=9870,
                 container_port=9870,
                 model_root_path=r"E:\Jason\Projects\FasterLivePortrait"):
        
        self.container_name = container_name
        self.image_name = image_name
        self.host_port = host_port
        self.container_port = container_port
        self.model_root_path = Path(model_root_path)
        self.client = docker.from_env()
        self.container = None
        self.is_ready = False
        
        # Create output directories in the project location
        self.output_dir = Path(r"C:\Users\Jason\Desktop\Important\Projects\AvatarResurrection\scripts\lipsync_outputs")
        self.output_dir.mkdir(exist_ok=True)
        
    async def start_container(self):
        """Start the Docker container and load checkpoints"""
        try:
            # Check if container already exists
            try:
                self.container = self.client.containers.get(self.container_name)
                if self.container.status == "running":
                    logger.info(f"Container {self.container_name} is already running")
                    self.is_ready = True
                    return True
                else:
                    logger.info(f"Starting existing container {self.container_name}")
                    self.container.start()
            except docker.errors.NotFound:
                logger.info(f"Creating new container {self.container_name}")
                # Create and start new container with proper entrypoint
                self.container = self.client.containers.run(
                    self.image_name,
                    name=self.container_name,
                    ports={f'{self.container_port}/tcp': self.host_port},
                    volumes={str(self.model_root_path): {'bind': '/root/FasterLivePortrait', 'mode': 'rw'}},
                    device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
                    detach=True,
                    restart_policy={"Name": "always"},
                    command="tail -f /dev/null",
                    tty=True,
                    stdin_open=True
                )
            
            # Wait for container to be ready
            await self._wait_for_container_ready()
            
            self.is_ready = True
            logger.info("Container is ready for lipsync processing")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            return False
    
    async def _wait_for_container_ready(self, timeout=60):
        """Wait for container to be fully ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Check if container is running
                self.container.reload()
                if self.container.status == "running":
                    # Test if we can execute commands
                    result = self.container.exec_run("ls /root/FasterLivePortrait")
                    if result.exit_code == 0:
                        return True
            except Exception as e:
                logger.debug(f"Container not ready yet: {e}")
            
            await asyncio.sleep(2)
        
        raise TimeoutError("Container failed to become ready within timeout")

    async def preload_models(self):
        """Preload all models into memory for faster generation"""
        if not self.is_ready:
            raise RuntimeError("Container is not ready. Call start_container() first.")
            
        logger.info("Preloading models into memory...")
        
        try:
            python_exec = "/root/miniconda3/bin/python"
            
            # Create a model preloading script
            preload_script = '''
import sys
import os
sys.path.append("/root/FasterLivePortrait")

# Set library paths
os.environ["LD_LIBRARY_PATH"] = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"

print("Starting model preload...")

try:
    # Import the main inference modules
    from src.live_portrait_pipeline import LivePortraitPipeline
    from src.config.inference_config import InferenceConfig
    from src.utils.helper import load_model, prepare_paste_back, prepare_retargeting
    
    print("Imported core modules successfully")
    
    # Load configuration
    cfg_path = "configs/onnx_infer.yaml"
    if os.path.exists(cfg_path):
        print(f"Loading config from {cfg_path}")
        inference_cfg = InferenceConfig(cfg_path)
        
        # Initialize the pipeline (this loads all models)
        print("Initializing LivePortrait pipeline...")
        live_portrait_pipeline = LivePortraitPipeline(
            appearance_feature_extractor=None,
            motion_extractor=None,
            warping_module=None,
            spade_generator=None,
            stitching_retargeting_module=None,
            cfg=inference_cfg,
            device_id=0
        )
        
        print("Models preloaded successfully!")
        print("PRELOAD_SUCCESS: Models are ready in memory")
        
    else:
        print(f"Config file not found: {cfg_path}")
        print("PRELOAD_ERROR: Config file missing")
        
except Exception as e:
    print(f"PRELOAD_ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
'''
            
            # Execute the preload script
            trt_lib_path = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"
            cmd = f"/bin/bash -c 'export LD_LIBRARY_PATH={trt_lib_path}:$LD_LIBRARY_PATH && cd /root/FasterLivePortrait && echo \"{preload_script}\" | {python_exec}'"
            
            result = self.container.exec_run(cmd, stream=False)
            
            output = result.output.decode()
            logger.info(f"Preload output: {output}")
            
            if "PRELOAD_SUCCESS" in output:
                logger.info("✓ Models successfully preloaded into memory")
                return True
            else:
                logger.warning("Model preload may have failed, but continuing...")
                return False
                
        except Exception as e:
            logger.error(f"Model preload failed: {e}")
            return False
        """Generate lipsync video with support for both image and video sources"""
        if not self.is_ready:
            raise RuntimeError("Container is not ready. Call start_container() first.")
        
        if output_name is None:
            output_name = f"lipsync_{int(time.time())}.mp4"
        
        # Copy input files to container with appropriate extensions
        timestamp = int(time.time())
        
        if source_type == "image":
            source_container_path = f"/root/FasterLivePortrait/temp_source_{timestamp}.jpg"
        else:  # video
            source_container_path = f"/root/FasterLivePortrait/temp_source_{timestamp}.mp4"
            
        driving_container_path = f"/root/FasterLivePortrait/temp_driving_{timestamp}.mp4"
        
        try:
            python_exec = "/root/miniconda3/bin/python"
            
            # Copy input files to container
            await self._copy_to_container(source_path, source_container_path)
            await self._copy_to_container(driving_video_path, driving_container_path)
            
            # Try different config files (prefer ONNX as it's more stable)
            config_options = [
                "configs/onnx_infer.yaml",
                "configs/trt_infer.yaml",
                "configs/onnx_mp_infer.yaml",
                "configs/trt_mp_infer.yaml"
            ]
            
            # Check which configs exist
            available_configs = []
            for config in config_options:
                check_config = self.container.exec_run(f"/bin/bash -c 'test -f /root/FasterLivePortrait/{config} && echo exists || echo missing'")
                if "exists" in check_config.output.decode():
                    available_configs.append(config)
                    logger.info(f"Found config: {config}")
            
            if not available_configs:
                selected_config = "configs/onnx_infer.yaml"
                logger.warning("No config files found, using default onnx_infer.yaml")
            else:
                selected_config = available_configs[0]
                for config in available_configs:
                    if "onnx_infer.yaml" in config:
                        selected_config = config
                        logger.info(f"Using preferred ONNX config: {config}")
                        break
            
            # Build command based on source type
            if source_type == "image":
                command = [
                    python_exec, "run.py",
                    "--src_image", source_container_path,
                    "--dri_video", driving_container_path,
                    "--cfg", selected_config,
                    "--paste_back",
                    "--flag_write_result_img", "False",  # Disable image output
                    "--flag_write_gif", "False",         # Disable GIF output
                    "--no_video_head"                    # Disable realtime video head mode
                ]
            else:
                command = [
                    python_exec, "run.py",
                    "--src_video", source_container_path,
                    "--dri_video", driving_container_path,
                    "--cfg", selected_config,
                    "--paste_back",
                    "--flag_write_result_img", "False",  # Disable image output
                    "--flag_write_gif", "False",         # Disable GIF output
                    "--no_video_head"                    # Disable realtime video head mode
                ]
            
            logger.info(f"Running lipsync generation: {' '.join(command)}")
            
            # Execute the command in container
            trt_lib_path = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"
            conda_cmd = f"/bin/bash -c 'export LD_LIBRARY_PATH={trt_lib_path}:$LD_LIBRARY_PATH && cd /root/FasterLivePortrait && {python_exec} {' '.join(command[1:])}'"
            
            result = self.container.exec_run(cmd=conda_cmd, stream=False)
            
            logger.info(f"Command exit code: {result.exit_code}")
            logger.info(f"Command output: {result.output.decode()}")
            
            if result.exit_code != 0:
                raise RuntimeError(f"Command failed with exit code {result.exit_code}: {result.output.decode()}")
            
            # Find the output video file
            find_results = self.container.exec_run("/bin/bash -c 'find /root/FasterLivePortrait/results -name \"*.mp4\" -type f | tail -5'")
            
            if find_results.exit_code == 0:
                result_files = find_results.output.decode().strip().split('\n')
                logger.info(f"Found result files: {result_files}")
                
                # Look for the best video file - prioritize org-audio.mp4 (original with audio)
                preferred_files = []
                for result_file in result_files:
                    if result_file and result_file.strip():
                        # HIGHEST PRIORITY: org-audio.mp4 (original resolution with audio - this is what we want!)
                        if "org-audio.mp4" in result_file:
                            preferred_files.insert(0, result_file)  # Always first choice
                            logger.info(f"Found target file (org-audio): {result_file}")
                        # Second choice: crop-audio.mp4 (cropped with audio)
                        elif "crop-audio.mp4" in result_file:
                            preferred_files.append(result_file)
                        # Fallback choices (without audio)
                        elif "org.mp4" in result_file and "audio" not in result_file:
                            preferred_files.append(result_file)
                        elif "crop.mp4" in result_file and "audio" not in result_file:
                            preferred_files.append(result_file)
                
                logger.info(f"Preferred file order: {preferred_files}")
                
                for result_file in preferred_files:
                    logger.info(f"Trying to use result file: {result_file}")
                    
                    # Verify the file exists and has content
                    file_info = self.container.exec_run(f"ls -la '{result_file}'")
                    if file_info.exit_code != 0:
                        logger.warning(f"File not found: {result_file}")
                        continue
                        
                    file_info_output = file_info.output.decode().strip()
                    logger.info(f"File info: {file_info_output}")
                    
                    # Extract file size from ls output
                    try:
                        file_size = int(file_info_output.split()[4])
                        if file_size < 10000:  # Less than 10KB is likely corrupted for video
                            logger.warning(f"File too small ({file_size} bytes), skipping: {result_file}")
                            continue
                    except (IndexError, ValueError):
                        logger.warning(f"Could not parse file size for: {result_file}")
                    
                    # This file looks good, copy it
                    output_host_path = self.output_dir / output_name
                    await self._copy_from_container(result_file, output_host_path)
                    
                    # Verify the copied file
                    if output_host_path.exists():
                        logger.info(f"Successfully copied to: {output_host_path} (size: {output_host_path.stat().st_size} bytes)")
                        
                        # Cleanup temporary files
                        await self._cleanup_temp_files([source_container_path, driving_container_path])
                        
                        return str(output_host_path)
                
                # If we get here, no valid files were found
                raise RuntimeError("No valid output video files found")
            else:
                raise RuntimeError("Could not find results directory")
            
        except Exception as e:
            logger.error(f"Lipsync generation failed: {e}")
            # Cleanup on error
            await self._cleanup_temp_files([source_container_path, driving_container_path])
            raise
    
    async def _copy_to_container(self, host_path, container_path):
        """Copy file from host to container"""
        try:
            with open(host_path, 'rb') as f:
                self.container.put_archive(
                    path=os.path.dirname(container_path),
                    data=self._create_tar_archive(os.path.basename(container_path), f.read())
                )
        except Exception as e:
            logger.error(f"Failed to copy {host_path} to container: {e}")
            raise
    
    async def _copy_from_container(self, container_path, host_path):
        """Copy file from container to host"""
        try:
            logger.info(f"Copying {container_path} to {host_path}")
            
            archive_data, _ = self.container.get_archive(container_path)
            
            import tarfile
            import io
            
            tar_stream = io.BytesIO()
            for chunk in archive_data:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                tar_info = tar.getmembers()[0]
                file_data = tar.extractfile(tar_info).read()
                
            host_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(host_path, 'wb') as f:
                f.write(file_data)
            
            if host_path.exists():
                actual_size = host_path.stat().st_size
                logger.info(f"Successfully copied {actual_size} bytes to {host_path}")
            else:
                raise RuntimeError(f"File not found after copy: {host_path}")
                
        except Exception as e:
            logger.error(f"Failed to copy {container_path} from container: {e}")
            raise
    
    def _create_tar_archive(self, filename, data):
        """Create a tar archive for a single file"""
        import tarfile
        import io
        
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            info = tarfile.TarInfo(name=filename)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        
        tar_stream.seek(0)
        return tar_stream.read()
    
    async def _cleanup_temp_files(self, file_paths):
        """Remove temporary files from container"""
        for file_path in file_paths:
            try:
                self.container.exec_run(f"rm -f {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {file_path}: {e}")
    
    async def stop_container(self):
        """Stop and remove the container"""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
                logger.info(f"Container {self.container_name} stopped and removed")
            except Exception as e:
                logger.error(f"Failed to stop container: {e}")
        self.is_ready = False


# Main function that other programs can import and use
async def generate_lipsync_video(source_path, driving_video_path, output_path=None, 
                               source_type="image", model_root_path=r"E:\Jason\Projects\FasterLivePortrait",
                               preload_models=True):
    """
    Generate a lipsync video using Docker container.
    
    Args:
        source_path (str): Path to source image or video
        driving_video_path (str): Path to driving video (contains audio)
        output_path (str, optional): Output file path. If None, auto-generated
        source_type (str): "image" or "video"
        model_root_path (str): Path to FasterLivePortrait model directory
        preload_models (bool): Whether to preload models for faster inference
    
    Returns:
        str: Path to generated video file
    """
    manager = LipsyncDockerManager(model_root_path=model_root_path)
    
    try:
        # Start container
        success = await manager.start_container()
        if not success:
            raise RuntimeError("Failed to start Docker container")
        
        # Preload models if requested
        if preload_models:
            logger.info("Preloading models for faster inference...")
            await manager.preload_models()
        
        # Generate lipsync
        result_path = await manager.generate_lipsync(
            source_path=source_path,
            driving_video_path=driving_video_path,
            output_name=output_path,
            source_type=source_type
        )
        
        return result_path
        
    finally:
        # Optional: Stop container after use (comment out if you want to keep it running)
        # await manager.stop_container()
        pass


# Synchronous wrapper for easier integration
def generate_lipsync_video_sync(source_path, driving_video_path, output_path=None, 
                               source_type="image", model_root_path=r"E:\Jason\Projects\FasterLivePortrait",
                               preload_models=True):
    """
    Synchronous wrapper for generate_lipsync_video.
    Use this if your calling code doesn't support async/await.
    """
    return asyncio.run(generate_lipsync_video(
        source_path, driving_video_path, output_path, source_type, model_root_path, preload_models
    ))


# Example usage
if __name__ == "__main__":
    # Example async usage
    async def main():
        result = await generate_lipsync_video(
            source_path="./source_image.jpg",
            driving_video_path="./driving_video.mp4",
            source_type="image"
            # model_root_path is now hardcoded, no need to specify
        )
        print(f"Generated video: {result}")
    
    # Example sync usage
    # result = generate_lipsync_video_sync(
    #     source_path="./source_image.jpg",
    #     driving_video_path="./driving_video.mp4",
    #     source_type="image"
    #     # model_root_path is now hardcoded, no need to specify
    # )
    # print(f"Generated video: {result}")
    
    asyncio.run(main())