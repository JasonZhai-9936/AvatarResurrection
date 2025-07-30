import asyncio
import subprocess
import docker
import os
import time
from pathlib import Path
from nicegui import ui, app
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
                 model_root_path="/path/to/your/FasterLivePortrait"):
        
        self.container_name = container_name
        self.image_name = image_name
        self.host_port = host_port
        self.container_port = container_port
        self.model_root_path = Path(model_root_path)
        self.client = docker.from_env()
        self.container = None
        self.is_ready = False
        
        # Create output directories
        self.output_dir = Path("./lipsync_outputs")
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
                    # Don't override the entrypoint, let the container set up its environment
                    command="tail -f /dev/null",  # Keep container running after setup
                    tty=True,
                    stdin_open=True
                )
            
            # Wait for container to be ready
            await self._wait_for_container_ready()
            
            # Debug container state
            await self.debug_container()
            
            # Pre-load model (optional warm-up)
            await self._warm_up_model()
            
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
    
    async def _warm_up_model(self):
        """Optional: Warm up the model by running a test inference"""
        try:
            logger.info("Warming up model...")
            # Check available Python executables
            python_check = self.container.exec_run("which python3")
            if python_check.exit_code == 0:
                logger.info(f"Found python3 at: {python_check.output.decode().strip()}")
            else:
                python_check = self.container.exec_run("which python")
                if python_check.exit_code == 0:
                    logger.info(f"Found python at: {python_check.output.decode().strip()}")
                else:
                    # Try common conda paths
                    conda_check = self.container.exec_run("ls /opt/conda/bin/python*")
                    logger.info(f"Conda python check: {conda_check.output.decode()}")
                    
            # Check if run.py exists
            run_py_check = self.container.exec_run("ls -la run.py", workdir="/root/FasterLivePortrait")
            logger.info(f"run.py check: {run_py_check.output.decode()}")
            
        except Exception as e:
            logger.warning(f"Model warm-up failed: {e}")
    
    async def debug_container(self):
        """Debug method to check container state"""
        logger.info("=== Container Debug Information ===")
        
        if not self.container:
            logger.error("No container available")
            return
            
        try:
            self.container.reload()
            logger.info(f"Container status: {self.container.status}")
            logger.info(f"Container ID: {self.container.id}")
            
            # Test basic commands
            test_commands = [
                "whoami",
                "pwd", 
                "ls -la /",
                "ls -la /opt",
                "ls -la /usr/bin | grep python",
                "echo $CONDA_DEFAULT_ENV",
                "conda --version",
                "/opt/conda/bin/python --version"
            ]
            
            for cmd in test_commands:
                try:
                    result = self.container.exec_run(cmd)
                    logger.info(f"'{cmd}' -> Exit: {result.exit_code}, Output: {result.output.decode().strip()}")
                except Exception as e:
                    logger.error(f"'{cmd}' failed: {e}")
                    
        except Exception as e:
            logger.error(f"Debug failed: {e}")
    
    async def _find_python_executable(self):
        """Find the correct Python executable in the container"""
        # First, let's do a comprehensive search
        logger.info("Searching for Python executables in container...")
        
        # Check what's in common directories
        search_commands = [
            "find /usr -name 'python*' -type f",
            "find /opt -name 'python*' -type f", 
            "find /root -name 'python*' -type f",
            "ls -la /usr/bin/python* || echo 'No python in /usr/bin'",
            "which python3 || echo 'python3 not in PATH'",
            "which python || echo 'python not in PATH'",
            "echo $PATH"
        ]
        
        for cmd in search_commands:
            try:
                # Use bash -c for proper shell execution
                result = self.container.exec_run(f"/bin/bash -c '{cmd}'", workdir="/root/FasterLivePortrait")
                logger.info(f"Command '{cmd}': {result.output.decode().strip()}")
            except Exception as e:
                logger.info(f"Command '{cmd}' failed: {e}")
        
        # Now try the standard paths with proper shell, including miniconda
        python_paths = [
            "/root/miniconda3/bin/python",
            "/root/miniconda3/bin/python3",
            "/root/miniconda3/bin/python3.10",
            "python3",
            "python",
            "/usr/bin/python3",
            "/usr/bin/python"
        ]
        
        for python_path in python_paths:
            try:
                # Use bash -c to ensure proper environment
                result = self.container.exec_run(f"/bin/bash -c '{python_path} --version'")
                if result.exit_code == 0:
                    logger.info(f"Found working Python: {python_path} - {result.output.decode().strip()}")
                    return python_path
                else:
                    logger.info(f"Python path {python_path} failed with exit code {result.exit_code}: {result.output.decode().strip()}")
            except Exception as e:
                logger.info(f"Error testing {python_path}: {e}")
        
        # If no Python found, let's check if we can enter the container differently
        logger.info("No Python found with standard methods. Checking container details...")
        
        # Get container info
        self.container.reload()
        logger.info(f"Container status: {self.container.status}")
        logger.info(f"Container image: {self.container.image}")
        
        # Try to check what's actually running in the container
        try:
            ps_result = self.container.exec_run("ps aux")
            logger.info(f"Running processes: {ps_result.output.decode()}")
        except Exception as e:
            logger.info(f"Could not check processes: {e}")
        # If no Python found, try to install it or check if it needs setup
        logger.info("No Python found. Attempting to install or setup Python...")
        
        # Try common Python installation commands
        install_commands = [
            "apt-get update && apt-get install -y python3 python3-pip",
            "yum install -y python3 python3-pip",
            "apk add python3 py3-pip"
        ]
        
        for install_cmd in install_commands:
            try:
                logger.info(f"Trying: {install_cmd}")
                result = self.container.exec_run(f"/bin/bash -c '{install_cmd}'")
                if result.exit_code == 0:
                    logger.info(f"Successfully ran: {install_cmd}")
                    # Try to find python3 again
                    python_test = self.container.exec_run("/bin/bash -c 'python3 --version'")
                    if python_test.exit_code == 0:
                        logger.info(f"Python3 now available: {python_test.output.decode().strip()}")
                        return "python3"
                    break
                else:
                    logger.info(f"Command failed: {install_cmd}")
            except Exception as e:
                logger.info(f"Install attempt failed: {e}")
                
        raise RuntimeError("No working Python executable found in container")
    
    async def debug_tensorrt(self):
        """Debug TensorRT installation in the container"""
        logger.info("=== TensorRT Debug Information ===")
        
        debug_commands = [
            "find /usr -name '*tensorrt*' -type d 2>/dev/null || echo 'No tensorrt dirs in /usr'",
            "find /opt -name '*tensorrt*' -type d 2>/dev/null || echo 'No tensorrt dirs in /opt'",
            "find /usr/local -name '*tensorrt*' -type d 2>/dev/null || echo 'No tensorrt dirs in /usr/local'",
            "find / -name 'libnvinfer.so*' 2>/dev/null | head -10 || echo 'libnvinfer.so not found'",
            "ls -la /usr/local/cuda/lib64/ | grep libnvinfer || echo 'No libnvinfer in cuda lib64'",
            "echo $LD_LIBRARY_PATH",
            "ldconfig -p | grep tensorrt || echo 'No tensorrt in ldconfig'",
            "ldconfig -p | grep nvinfer || echo 'No nvinfer in ldconfig'",
            "/root/miniconda3/bin/python -c \"import tensorrt; print('TensorRT version:', tensorrt.__version__)\" 2>&1 || echo 'TensorRT import failed'"
        ]
        
        for cmd in debug_commands:
            try:
                result = self.container.exec_run(f"/bin/bash -c '{cmd}'")
                logger.info(f"'{cmd}' -> {result.output.decode().strip()}")
            except Exception as e:
                logger.error(f"Debug command failed: {e}")

    async def fix_tensorrt_libs(self):
        """Try to fix TensorRT library issues"""
        logger.info("Attempting to fix TensorRT library paths...")
        
        fix_commands = [
            # Update library cache
            "ldconfig",
            # Create symlinks if libraries exist but with different names
            "find /usr -name 'libnvinfer.so*' -exec ln -sf {} /usr/local/lib/libnvinfer.so.8 \\; 2>/dev/null || echo 'No libnvinfer found to link'",
            # Check if TensorRT is installed via apt and install if needed
            "apt-get update && apt-get install -y libnvinfer8 libnvinfer-dev || echo 'Could not install TensorRT via apt'"
        ]
        
        for cmd in fix_commands:
            try:
                result = self.container.exec_run(f"/bin/bash -c '{cmd}'")
                logger.info(f"Fix command '{cmd}' -> Exit: {result.exit_code}")
                if result.exit_code != 0:
                    logger.info(f"Output: {result.output.decode().strip()}")
            except Exception as e:
                logger.error(f"Fix command failed: {e}")

    async def generate_lipsync(self, source_image_path, driving_video_path, output_name=None):
        """Generate lipsync video"""
        if not self.is_ready:
            raise RuntimeError("Container is not ready. Call start_container() first.")
        
        if output_name is None:
            output_name = f"lipsync_{int(time.time())}.mp4"
        
        # Copy input files to container
        source_container_path = f"/root/FasterLivePortrait/temp_source_{int(time.time())}.jpg"
        driving_container_path = f"/root/FasterLivePortrait/temp_driving_{int(time.time())}.mp4"
        output_container_path = f"/root/FasterLivePortrait/output_{output_name}"
        
        try:
            # Use the miniconda python directly - we found it in the logs
            python_exec = "/root/miniconda3/bin/python"
            
            # Test if this python works
            test_result = self.container.exec_run(f"/bin/bash -c '{python_exec} --version'")
            if test_result.exit_code != 0:
                # Try python3
                python_exec = "/root/miniconda3/bin/python3"
                test_result = self.container.exec_run(f"/bin/bash -c '{python_exec} --version'")
                if test_result.exit_code != 0:
                    # Try python3.10
                    python_exec = "/root/miniconda3/bin/python3.10"
                    test_result = self.container.exec_run(f"/bin/bash -c '{python_exec} --version'")
            
            if test_result.exit_code == 0:
                logger.info(f"Using Python: {python_exec} - {test_result.output.decode().strip()}")
            else:
                raise RuntimeError("Miniconda Python not working")
            
            # Debug and try to fix TensorRT issues
            await self.debug_tensorrt()
            await self.fix_tensorrt_libs()
            
            # Copy input files to container
            await self._copy_to_container(source_image_path, source_container_path)
            await self._copy_to_container(driving_video_path, driving_container_path)
            
            # Try different config files (prefer ONNX as it's more stable)
            config_options = [
                "configs/onnx_infer.yaml",   # ONNX config (more stable)
                "configs/trt_infer.yaml",    # TensorRT config
                "configs/onnx_mp_infer.yaml", # ONNX multiprocessing
                "configs/trt_mp_infer.yaml"   # TensorRT multiprocessing
            ]
            
            # Check which configs exist
            available_configs = []
            for config in config_options:
                check_config = self.container.exec_run(f"/bin/bash -c 'test -f /root/FasterLivePortrait/{config} && echo exists || echo missing'")
                if "exists" in check_config.output.decode():
                    available_configs.append(config)
                    logger.info(f"Found config: {config}")
            
            if not available_configs:
                # Default to ONNX if no configs found (safer)
                selected_config = "configs/onnx_infer.yaml"
                logger.warning("No config files found, using default onnx_infer.yaml")
            else:
                # Prefer ONNX config as it's more stable than TensorRT
                selected_config = available_configs[0]  # Start with first available
                for config in available_configs:
                    if "onnx_infer.yaml" in config:
                        selected_config = config
                        logger.info(f"Using preferred ONNX config: {config}")
                        break
                    elif "trt_infer.yaml" in config:
                        selected_config = config
                        logger.info(f"Using TensorRT config: {config}")
                        break
            
            logger.info(f"Selected config: {selected_config}")
            
            # Test TensorRT import with the proper environment if using TRT config
            if "trt" in selected_config:
                logger.info("Testing TensorRT import with proper library paths...")
                trt_lib_path = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"
                test_trt_cmd = f"/bin/bash -c 'export LD_LIBRARY_PATH={trt_lib_path}:$LD_LIBRARY_PATH && {python_exec} -c \"import tensorrt; print(f\\\"TensorRT version: {{tensorrt.__version__}}\\\")\""
                test_result = self.container.exec_run(test_trt_cmd)
                
                if test_result.exit_code != 0:
                    logger.warning(f"TensorRT test failed: {test_result.output.decode()}")
                    # Fall back to ONNX if available
                    for config in available_configs:
                        if "onnx" in config:
                            selected_config = config
                            logger.info(f"Falling back to ONNX config: {config}")
                            break
                else:
                    logger.info(f"TensorRT test successful: {test_result.output.decode().strip()}")
            
            # Run lipsync generation
            command = [
                python_exec, "run.py",
                "--src_image", source_container_path,
                "--dri_video", driving_container_path,
                "--cfg", selected_config,
                "--paste_back"  # Add paste_back for better quality and remove output param since it's ignored
            ]
            
            logger.info(f"Running lipsync generation: {' '.join(command)}")
            
            # Execute the command in container with proper TensorRT environment
            # Set up TensorRT library paths - we found TensorRT at /opt/TensorRT-8.6.1.6/
            trt_lib_path = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"
            
            conda_cmd = f"/bin/bash -c 'export LD_LIBRARY_PATH={trt_lib_path}:$LD_LIBRARY_PATH && cd /root/FasterLivePortrait && {python_exec} {' '.join(command[1:])}'"
            result = self.container.exec_run(
                cmd=conda_cmd,
                stream=False
            )
            
            logger.info(f"Command exit code: {result.exit_code}")
            logger.info(f"Command output: {result.output.decode()}")
            
            # Check if command was successful
            if result.exit_code != 0:
                raise RuntimeError(f"Command failed with exit code {result.exit_code}: {result.output.decode()}")
            
            # The model generates files in results directory instead of the specified output path
            # Let's find the actual output files
            find_results = self.container.exec_run("/bin/bash -c 'find /root/FasterLivePortrait/results -name \"*.mp4\" -type f | tail -5'")
            
            if find_results.exit_code == 0:
                result_files = find_results.output.decode().strip().split('\n')
                logger.info(f"Found result files: {result_files}")
                
                # Look for the most recent files that match our input
                # Priority: non-audio versions first (since audio processing seems to fail)
                preferred_files = []
                for result_file in result_files:
                    if result_file:
                        if "org.mp4" in result_file and "audio" not in result_file:
                            preferred_files.insert(0, result_file)  # High priority
                        elif "crop.mp4" in result_file and "audio" not in result_file:
                            preferred_files.append(result_file)
                        elif "org-audio.mp4" in result_file:
                            preferred_files.append(result_file)  # Lower priority
                        elif "crop-audio.mp4" in result_file:
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
                        if file_size < 1000:  # Less than 1KB is likely corrupted
                            logger.warning(f"File too small ({file_size} bytes), skipping: {result_file}")
                            continue
                    except (IndexError, ValueError):
                        logger.warning(f"Could not parse file size for: {result_file}")
                    
                    # Check if it's a valid video file with ffprobe
                    video_info = self.container.exec_run(f"/bin/bash -c 'ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,r_frame_rate -of csv=p=0 \"{result_file}\" 2>/dev/null || echo \"PROBE_FAILED\"'")
                    video_info_output = video_info.output.decode().strip()
                    
                    if "PROBE_FAILED" in video_info_output or not video_info_output:
                        logger.warning(f"Video validation failed for: {result_file}")
                        continue
                    
                    logger.info(f"Video validation passed: {video_info_output}")
                    
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
                raise RuntimeError("No valid output files found in results directory")
            
            # If we can't find result files, check the original output location
            check_result = self.container.exec_run(f"ls -la {output_container_path}")
            if check_result.exit_code == 0:
                # Copy result back to host
                output_host_path = self.output_dir / output_name
                await self._copy_from_container(output_container_path, output_host_path)
            else:
                # Check if there's any output in the results directory
                check_results_dir = self.container.exec_run("ls -la /root/FasterLivePortrait/results/")
                logger.info(f"Results directory contents: {check_results_dir.output.decode()}")
                raise RuntimeError(f"No output file found. Checked: {output_container_path} and results directory")
            
            # Cleanup temporary files
            await self._cleanup_temp_files([source_container_path, driving_container_path])
            
            return str(output_host_path)
            
        except Exception as e:
            logger.error(f"Lipsync generation failed: {e}")
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
            
            # Get file size for progress tracking
            size_result = self.container.exec_run(f"stat -c%s '{container_path}'")
            if size_result.exit_code == 0:
                file_size = int(size_result.output.decode().strip())
                logger.info(f"File size: {file_size} bytes")
            
            archive_data, _ = self.container.get_archive(container_path)
            
            # Extract and save file
            import tarfile
            import io
            
            tar_stream = io.BytesIO()
            for chunk in archive_data:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                # Get the file from the tar
                tar_info = tar.getmembers()[0]  # Should be one file
                file_data = tar.extractfile(tar_info).read()
                
            # Ensure parent directory exists
            host_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            with open(host_path, 'wb') as f:
                f.write(file_data)
            
            # Verify the file was written correctly
            if host_path.exists():
                actual_size = host_path.stat().st_size
                logger.info(f"Successfully copied {actual_size} bytes to {host_path}")
                
                if 'file_size' in locals() and actual_size != file_size:
                    logger.warning(f"File size mismatch! Expected {file_size}, got {actual_size}")
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

# Main NiceGUI Application
class LipsyncApp:
    def __init__(self):
        self.lipsync_manager = LipsyncDockerManager(
            model_root_path="/path/to/your/FasterLivePortrait"  # Update this path
        )
        self.processing = False
        
    async def startup(self):
        """Initialize the application"""
        logger.info("Starting Lipsync Docker container...")
        success = await self.lipsync_manager.start_container()
        if success:
            ui.notify("Lipsync model loaded and ready!", type="positive")
        else:
            ui.notify("Failed to start lipsync container", type="negative")
    
    def create_ui(self):
        """Create the NiceGUI interface"""
        
        @ui.page('/')
        def main_page():
            ui.label('Lipsync Video Generator').classes('text-2xl font-bold mb-4')
            
            # File upload areas
            with ui.row().classes('w-full gap-4'):
                with ui.card().classes('w-1/2'):
                    ui.label('Source Image').classes('text-lg font-semibold')
                    source_upload = ui.upload(
                        on_upload=lambda e: handle_source_upload(e),
                        auto_upload=True,
                        max_file_size=10_000_000
                    ).props('accept=image/*')
                    source_preview = ui.image().classes('max-w-xs').style('display: none')
                
                with ui.card().classes('w-1/2'):
                    ui.label('Driving Video').classes('text-lg font-semibold')
                    video_upload = ui.upload(
                        on_upload=lambda e: handle_video_upload(e),
                        auto_upload=True,
                        max_file_size=100_000_000
                    ).props('accept=video/*')
                    video_preview = ui.video('').classes('max-w-xs').style('display: none')
            
            # Progress and results
            progress = ui.linear_progress(value=0).style('display: none')
            result_area = ui.column().classes('mt-4')
            
            # State variables
            source_file_path = None
            video_file_path = None
            
            def handle_source_upload(e):
                nonlocal source_file_path
                try:
                    # Generate a safe filename based on timestamp and original extension
                    import time
                    timestamp = int(time.time())
                    
                    # Try to get file extension from the original name if possible
                    original_name = getattr(e, 'name', '')
                    if original_name and '.' in original_name:
                        ext = os.path.splitext(original_name)[1]
                    else:
                        ext = '.jpg'  # default for images
                    
                    filename = f"source_image_{timestamp}{ext}"
                    source_file_path = filename
                    upload_path = os.path.join('./uploads', filename)
                    
                    # Ensure uploads directory exists
                    os.makedirs('./uploads', exist_ok=True)
                    
                    # Save uploaded file
                    with open(upload_path, 'wb') as f:
                        f.write(e.content.read())
                    
                    source_preview.set_source(upload_path)
                    source_preview.style('display: block')
                    ui.notify(f'Source image uploaded: {filename}', type='positive')
                    
                except Exception as ex:
                    ui.notify(f'Upload failed: {str(ex)}', type='negative')
                    logger.error(f"Source upload error: {ex}")
            
            def handle_video_upload(e):
                nonlocal video_file_path
                try:
                    # Generate a safe filename based on timestamp and original extension
                    import time
                    timestamp = int(time.time())
                    
                    # Try to get file extension from the original name if possible
                    original_name = getattr(e, 'name', '')
                    if original_name and '.' in original_name:
                        ext = os.path.splitext(original_name)[1]
                    else:
                        ext = '.mp4'  # default for videos
                    
                    filename = f"driving_video_{timestamp}{ext}"
                    video_file_path = filename
                    upload_path = os.path.join('./uploads', filename)
                    
                    # Ensure uploads directory exists
                    os.makedirs('./uploads', exist_ok=True)
                    
                    # Save uploaded file
                    with open(upload_path, 'wb') as f:
                        f.write(e.content.read())
                    
                    video_preview.set_source(upload_path)
                    video_preview.style('display: block')
                    ui.notify(f'Driving video uploaded: {filename}', type='positive')
                    
                except Exception as ex:
                    ui.notify(f'Upload failed: {str(ex)}', type='negative')
                    logger.error(f"Video upload error: {ex}")
            
            async def generate_lipsync():
                if not source_file_path or not video_file_path:
                    ui.notify('Please upload both source image and driving video', type='warning')
                    return
                
                if self.processing:
                    ui.notify('Generation already in progress', type='warning')
                    return
                
                self.processing = True
                generate_btn.props('loading')
                progress.style('display: block')
                progress.set_value(0.1)
                
                try:
                    ui.notify('Starting lipsync generation...', type='info')
                    progress.set_value(0.3)
                    
                    # Generate lipsync
                    output_path = await self.lipsync_manager.generate_lipsync(
                        f"./uploads/{source_file_path}",
                        f"./uploads/{video_file_path}"
                    )
                    
                    progress.set_value(1.0)
                    
                    # Display result
                    with result_area:
                        ui.label('Generated Lipsync Video:').classes('text-lg font-semibold mt-4')
                        
                        # Create a unique identifier for cache busting
                        import time
                        cache_buster = int(time.time())
                        video_url = f"{output_path}?v={cache_buster}"
                        
                        result_video = ui.video(video_url).classes('max-w-md').props('controls')
                        
                        # Add download button
                        ui.button('Download Video', 
                                on_click=lambda: ui.download(output_path, 
                                                            filename=f"lipsync_result_{cache_buster}.mp4"))
                        
                        # Add file info
                        try:
                            file_size = os.path.getsize(output_path)
                            ui.label(f'File size: {file_size:,} bytes').classes('text-sm text-gray-600')
                        except:
                            SyntaxError('Failed to get file size')
                    
                    ui.notify('Lipsync generation completed!', type='positive')
                    
                except Exception as e:
                    ui.notify(f'Generation failed: {str(e)}', type='negative')
                    logger.error(f"Generation error: {e}")
                
                finally:
                    self.processing = False
                    generate_btn.props(remove='loading')
                    progress.style('display: none')
            
            # Generate button (defined after the function) 
            generate_btn = ui.button('Generate Lipsync Video', on_click=generate_lipsync)
            generate_btn.props('color=primary size=lg')
        
        # Create uploads directory
        os.makedirs('./uploads', exist_ok=True)

# Application entry point
async def main():
    # Initialize app
    app_instance = LipsyncApp()
    
    # Create UI
    app_instance.create_ui()
    
    # Handle startup
    app.on_startup(app_instance.startup)
    
    # Handle cleanup on shutdown
    app.on_shutdown(lambda: app_instance.lipsync_manager.stop_container())
    
    # Run the app
    ui.run(host='0.0.0.0', port=8080, title='Lipsync Generator')

if __name__ in {"__main__", "__mp_main__"}:
    asyncio.run(main())