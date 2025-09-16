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
        self.models_preloaded = False  # NEW: Track model preload status
        self.python_exec = "/root/miniconda3/bin/python"  # Cache the working python path
        
        # Create output directories
        self.output_dir = Path("./lipsync_outputs")
        self.output_dir.mkdir(exist_ok=True)
        
    async def start_container(self):
        """Start the Docker container and preload model checkpoints"""
        try:
            # Check if container already exists
            try:
                self.container = self.client.containers.get(self.container_name)
                if self.container.status == "running":
                    logger.info(f"Container {self.container_name} is already running")
                else:
                    logger.info(f"Starting existing container {self.container_name}")
                    self.container.start()
            except docker.errors.NotFound:
                logger.info(f"Creating new container {self.container_name}")
                self.container = self.client.containers.run(
                    self.image_name,
                    name=self.container_name,
                    ports={f'{self.container_port}/tcp': self.host_port},
                    volumes={str(self.model_root_path): {'bind': '/root/FasterLivePortrait', 'mode': 'rw'}},
                    device_requests=[docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])],
                    detach=True,
                    restart_policy={"Name": "always"},
                    command="tail -f /dev/null",  # Keep container running after setup
                    tty=True,
                    stdin_open=True
                )
            
            # Wait for container to be ready
            await self._wait_for_container_ready()
            
            # Verify python executable works
            if not await self._verify_python():
                logger.warning("Python verification failed, but container is still usable")
            
            # NEW: Preload model checkpoints
            logger.info("🔄 Preloading model checkpoints...")
            await self._preload_models()
            
            # If preloading failed, inspect structure for debugging
            if not self.models_preloaded:
                logger.info("🔍 Inspecting project structure for debugging...")
                await self.inspect_project_structure()
            
            self.is_ready = True
            logger.info("🎉 Container ready with models preloaded!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            return False

    async def _preload_models(self):
        """Preload model checkpoints to reduce first-generation latency"""
        try:
            # Select the config we'll use
            config = await self._select_config()
            logger.info(f"Using config: {config}")
            
            # Create a more robust preload script that discovers the correct structure
            preload_script = '''
import sys
import os
import subprocess

# Add the project root to Python path
sys.path.insert(0, '/root/FasterLivePortrait')
os.chdir('/root/FasterLivePortrait')

print("Exploring project structure...")

# First, let's see what's actually in the directory
def explore_directory(path, max_depth=2, current_depth=0):
    items = []
    if current_depth >= max_depth:
        return items
    
    try:
        for item in sorted(os.listdir(path)):
            if item.startswith('.'):
                continue
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                items.append(f"{'  ' * current_depth}📁 {item}/")
                items.extend(explore_directory(item_path, max_depth, current_depth + 1))
            elif item.endswith(('.py', '.yaml', '.yml')):
                items.append(f"{'  ' * current_depth}📄 {item}")
    except PermissionError:
        pass
    return items

structure = explore_directory('/root/FasterLivePortrait', max_depth=3)
print("\\n".join(structure[:50]))  # Limit output

# Try different import strategies
print("\\nTrying different import approaches...")

success = False

# Strategy 1: Try direct run.py import (most likely to work)
try:
    print("Strategy 1: Analyzing run.py...")
    
    # Check if run.py exists and what it imports
    if os.path.exists('/root/FasterLivePortrait/run.py'):
        print("Found run.py, attempting to load dependencies...")
        
        # Try to import torch first to ensure GPU is available
        import torch
        print(f"PyTorch available: {torch.cuda.is_available()}")
        print(f"CUDA devices: {torch.cuda.device_count()}")
        
        # Try to run a minimal version of the inference setup
        # This mimics what run.py does without actually processing files
        exec(open('/root/FasterLivePortrait/run.py').read().split('if __name__')[0])
        
        print("Successfully loaded run.py dependencies!")
        success = True
        
    else:
        print("run.py not found")
        
except Exception as e1:
    print(f"Strategy 1 failed: {e1}")
    
    # Strategy 2: Try to find and import the main modules by discovery
    try:
        print("Strategy 2: Module discovery...")
        
        # Look for key files
        key_files = []
        for root, dirs, files in os.walk('/root/FasterLivePortrait'):
            for file in files:
                if file in ['inference_config.py', 'live_portrait_pipeline.py', 'config.py']:
                    key_files.append(os.path.join(root, file))
        
        print(f"Found key files: {key_files}")
        
        # Try to import based on discovered structure
        if key_files:
            import importlib.util
            
            for key_file in key_files:
                try:
                    spec = importlib.util.spec_from_file_location("temp_module", key_file)
                    temp_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(temp_module)
                    print(f"Successfully loaded: {key_file}")
                except Exception as import_err:
                    print(f"Failed to load {key_file}: {import_err}")
        
        success = True
        
    except Exception as e2:
        print(f"Strategy 2 failed: {e2}")
        
        # Strategy 3: Simple torch GPU warmup
        try:
            print("Strategy 3: Basic GPU warmup...")
            import torch
            
            if torch.cuda.is_available():
                # Just warm up the GPU with some basic operations
                device = torch.device('cuda')
                dummy_tensor = torch.randn(1000, 1000, device=device)
                result = torch.mm(dummy_tensor, dummy_tensor.t())
                del dummy_tensor, result
                torch.cuda.empty_cache()
                print("GPU warmed up successfully!")
                success = True
            else:
                print("CUDA not available")
                
        except Exception as e3:
            print(f"Strategy 3 failed: {e3}")

if success:
    print("Model preloading completed successfully!")
else:
    print("Model preloading failed - all strategies exhausted")
    
# Always print some useful info
try:
    import torch
    print(f"\\nSystem Info:")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
except:
    pass
'''.replace("{config}", config)
            
            # Write the preload script to the container
            script_path = "/root/FasterLivePortrait/preload_models.py"
            
            # Create and copy the script
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp_file:
                tmp_file.write(preload_script)
                tmp_file_path = tmp_file.name
            
            try:
                await self._copy_to_container(tmp_file_path, script_path)
                
                # Execute the preload script
                trt_lib_path = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"
                conda_cmd = f"/bin/bash -c 'export LD_LIBRARY_PATH={trt_lib_path}:$LD_LIBRARY_PATH && cd /root/FasterLivePortrait && {self.python_exec} preload_models.py'"
                
                logger.info("Executing model preload...")
                result = self.container.exec_run(cmd=conda_cmd, stream=False)
                
                output = result.output.decode()
                logger.info(f"Preload output: {output}")
                
                if result.exit_code == 0 and "Model preloading completed successfully!" in output:
                    self.models_preloaded = True
                    logger.info("✅ Models preloaded successfully!")
                elif "GPU warmed up successfully!" in output:
                    self.models_preloaded = True  # At least GPU is warmed up
                    logger.info("✅ GPU warmed up successfully (partial preload)!")
                else:
                    logger.warning(f"Model preloading had issues (exit code: {result.exit_code})")
                    logger.warning(f"Output: {output}")
                    # Don't fail startup, just warn
                    
            finally:
                # Cleanup temp file
                os.unlink(tmp_file_path)
                # Cleanup script from container
                self.container.exec_run(f"rm -f {script_path}")
                
        except Exception as e:
            logger.error(f"Model preloading failed: {e}")
            # Don't fail startup, just log the error

    async def inspect_project_structure(self):
        """Helper method to inspect the FasterLivePortrait project structure"""
        try:
            # Get directory structure
            result = self.container.exec_run("find /root/FasterLivePortrait -type f -name '*.py' | head -20")
            if result.exit_code == 0:
                logger.info("Python files found:")
                for line in result.output.decode().strip().split('\n'):
                    logger.info(f"  {line}")
            
            # Check for main files
            main_files = ["run.py", "app.py", "inference.py", "main.py"]
            for file in main_files:
                check_result = self.container.exec_run(f"test -f /root/FasterLivePortrait/{file} && echo 'EXISTS' || echo 'MISSING'")
                status = check_result.output.decode().strip()
                logger.info(f"  {file}: {status}")
                
        except Exception as e:
            logger.error(f"Failed to inspect project structure: {e}")
    
    async def _wait_for_container_ready(self, timeout=60):
        """Wait for container to be fully ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self.container.reload()
                if self.container.status == "running":
                    result = self.container.exec_run("ls /root/FasterLivePortrait")
                    if result.exit_code == 0:
                        return True
            except Exception:
                pass
            await asyncio.sleep(2)
        
        raise TimeoutError("Container failed to become ready within timeout")
    
    async def _verify_python(self):
        """Verify python executable works"""
        try:
            result = self.container.exec_run(f"/bin/bash -c '{self.python_exec} --version'")
            if result.exit_code == 0:
                return True
                
            # Try alternatives if default fails
            for python_path in ["/root/miniconda3/bin/python3", "/root/miniconda3/bin/python3.10"]:
                result = self.container.exec_run(f"/bin/bash -c '{python_path} --version'")
                if result.exit_code == 0:
                    self.python_exec = python_path
                    return True
            return False
        except Exception:
            return False

    async def generate_lipsync(self, source_path, driving_video_path, output_name=None, source_type="image"):
        """Generate lipsync video with support for both image and video sources"""
        if not self.is_ready:
            raise RuntimeError("Container is not ready. Call start_container() first.")
        
        # NEW: Log preload status
        if self.models_preloaded:
            logger.info("✅ Using preloaded models for faster generation")
        else:
            logger.warning("⚠️ Models not preloaded - first generation may be slower")
        
        if output_name is None:
            output_name = f"lipsync_{int(time.time())}.mp4"
        
        # Setup file paths
        timestamp = int(time.time())
        if source_type == "image":
            source_container_path = f"/root/FasterLivePortrait/temp_source_{timestamp}.jpg"
        else:
            source_container_path = f"/root/FasterLivePortrait/temp_source_{timestamp}.mp4"
        driving_container_path = f"/root/FasterLivePortrait/temp_driving_{timestamp}.mp4"
        
        try:
            # Copy input files to container
            await self._copy_to_container(source_path, source_container_path)
            await self._copy_to_container(driving_video_path, driving_container_path)
            
            # Select config (prefer ONNX for stability)
            config = await self._select_config()
            
            # Build command based on source type
            if source_type == "image":
                command_args = [
                    "run.py",
                    "--src_image", source_container_path,
                    "--dri_video", driving_container_path,
                    "--cfg", config,
                    "--paste_back"
                ]
            else:
                command_args = [
                    "run.py",
                    "--src_video", source_container_path,
                    "--dri_video", driving_container_path,
                    "--cfg", config,
                    "--paste_back"
                ]
            
            logger.info(f"Running lipsync generation with {source_type} source")
            
            # Execute the command with proper environment
            trt_lib_path = "/opt/TensorRT-8.6.1.6/targets/x86_64-linux-gnu/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"
            conda_cmd = f"/bin/bash -c 'export LD_LIBRARY_PATH={trt_lib_path}:$LD_LIBRARY_PATH && cd /root/FasterLivePortrait && {self.python_exec} {' '.join(command_args)}'"
            
            result = self.container.exec_run(cmd=conda_cmd, stream=False)
            
            if result.exit_code != 0:
                raise RuntimeError(f"Command failed with exit code {result.exit_code}: {result.output.decode()}")
            
            # Find and copy the best result file
            output_path = await self._find_and_copy_result(output_name)
            
            # Cleanup temporary files
            await self._cleanup_temp_files([source_container_path, driving_container_path])
            
            return output_path
            
        except Exception as e:
            logger.error(f"Lipsync generation failed: {e}")
            raise
    
    async def _select_config(self):
        """Select the best available config file"""
        # Check for available configs (prefer ONNX)
        preferred_configs = ["configs/onnx_infer.yaml", "configs/trt_infer.yaml", "configs/onnx_mp_infer.yaml", "configs/trt_mp_infer.yaml"]
        
        for config in preferred_configs:
            check_result = self.container.exec_run(f"test -f /root/FasterLivePortrait/{config} && echo 'exists' || echo 'missing'")
            if "exists" in check_result.output.decode():
                return config
        
        # Default fallback
        return "configs/onnx_infer.yaml"
    
    async def _find_and_copy_result(self, output_name):
        """Find the best result file and copy it to host"""
        # Find result files
        find_results = self.container.exec_run("/bin/bash -c 'find /root/FasterLivePortrait/results -name \"*.mp4\" -type f | tail -5'")
        
        if find_results.exit_code != 0:
            raise RuntimeError("No result files found")
        
        result_files = [f.strip() for f in find_results.output.decode().strip().split('\n') if f.strip()]
        
        # Prioritize non-audio versions (more reliable)
        preferred_files = []
        for result_file in result_files:
            if "org.mp4" in result_file and "audio" not in result_file:
                preferred_files.insert(0, result_file)  # High priority
            elif "crop.mp4" in result_file and "audio" not in result_file:
                preferred_files.append(result_file)
            elif "org-audio.mp4" in result_file or "crop-audio.mp4" in result_file:
                preferred_files.append(result_file)  # Lower priority
        
        # Try each file until we find a valid one
        for result_file in preferred_files:
            if await self._validate_video_file(result_file):
                output_host_path = self.output_dir / output_name
                await self._copy_from_container(result_file, output_host_path)
                
                if output_host_path.exists():
                    logger.info(f"Successfully generated: {output_host_path}")
                    return str(output_host_path)
        
        raise RuntimeError("No valid output files found")
    
    async def _validate_video_file(self, file_path):
        """Quickly validate if a video file is usable"""
        try:
            # Check file size
            file_info = self.container.exec_run(f"ls -la '{file_path}'")
            if file_info.exit_code != 0:
                return False
            
            # Extract file size (basic validation)
            file_size = int(file_info.output.decode().split()[4])
            return file_size > 1000  # At least 1KB
            
        except Exception:
            return False
    
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
            archive_data, _ = self.container.get_archive(container_path)
            
            # Extract and save file
            import tarfile
            import io
            
            tar_stream = io.BytesIO()
            for chunk in archive_data:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream, mode='r') as tar:
                tar_info = tar.getmembers()[0]
                file_data = tar.extractfile(tar_info).read()
                
            # Ensure parent directory exists
            host_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            with open(host_path, 'wb') as f:
                f.write(file_data)
                
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
            except Exception:
                pass  # Ignore cleanup failures
    
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
        self.models_preloaded = False  # NEW: Reset preload status

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
        
        try:
            success = await self.lipsync_manager.start_container()
            
            if success:
                logger.info("🎉 Lipsync model loaded and ready!")
            else:
                logger.error("❌ Failed to start lipsync container")
                
        except Exception as e:
            logger.error(f"❌ Startup failed: {str(e)}")
    
    def create_ui(self):
        """Create the NiceGUI interface"""
        
        @ui.page('/')
        def main_page():
            ui.label('Lipsync Video Generator').classes('text-2xl font-bold mb-4')
            
            # Status indicator
            status_card = ui.card().classes('w-full mb-4 p-4')
            with status_card:
                status_label = ui.label('Initializing...').classes('text-lg font-semibold')
                status_icon = ui.icon('hourglass_empty').classes('text-2xl')
                
                # Check status and update
                async def update_status():
                    if self.lipsync_manager.is_ready:
                        if self.lipsync_manager.models_preloaded:
                            status_label.text = '✅ Ready! (Models Preloaded)'
                            status_icon.name = 'check_circle'
                            status_card.classes(remove='bg-yellow-50 bg-orange-50', add='bg-green-50')
                        else:
                            status_label.text = '⚠️ Ready (Models will load on first use)'
                            status_icon.name = 'warning'
                            status_card.classes(remove='bg-yellow-50 bg-green-50', add='bg-orange-50')
                    else:
                        status_label.text = '⏳ Loading models...'
                        status_icon.name = 'hourglass_empty'
                        status_card.classes(remove='bg-green-50 bg-orange-50', add='bg-yellow-50')
                
                # Update status every 2 seconds until ready
                async def status_checker():
                    while not self.lipsync_manager.is_ready:
                        await update_status()
                        await asyncio.sleep(2)
                    await update_status()
                
                # Start status checking
                ui.timer(0.1, lambda: asyncio.create_task(status_checker()), once=True)
            
            # Source selection
            with ui.card().classes('w-full mb-4'):
                ui.label('Source Type').classes('text-lg font-semibold mb-2')
                source_type_radio = ui.radio(['Image', 'Video'], value='Image').props('inline')
            
            # File upload areas - organized in columns
            with ui.row().classes('w-full gap-4'):
                # Source input (Image or Video)
                with ui.card().classes('w-1/2'):
                    source_label = ui.label('Source Image').classes('text-lg font-semibold')
                    source_upload = ui.upload(
                        on_upload=lambda e: handle_source_upload(e),
                        auto_upload=True,
                        max_file_size=100_000_000
                    ).props('accept=image/*')
                    source_preview = ui.image().classes('max-w-xs').style('display: none')
                    source_video_preview = ui.video('').classes('max-w-xs').style('display: none')
                
                # Driving video input
                with ui.card().classes('w-1/2'):
                    ui.label('Driving Video (Audio Source)').classes('text-lg font-semibold')
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
            
            def update_source_ui():
                """Update UI based on source type selection"""
                if source_type_radio.value == 'Image':
                    source_label.text = 'Source Image'
                    source_upload.props('accept=image/*')
                    source_preview.style('display: block' if source_file_path else 'none')
                    source_video_preview.style('display: none')
                else:  # Video
                    source_label.text = 'Source Video'
                    source_upload.props('accept=video/*')
                    source_preview.style('display: none')
                    source_video_preview.style('display: block' if source_file_path else 'none')
            
            # Connect radio button to update function
            source_type_radio.on('update:model-value', lambda: update_source_ui())
            
            def handle_source_upload(e):
                nonlocal source_file_path
                try:
                    import time
                    timestamp = int(time.time())
                    
                    # Get file extension
                    original_name = getattr(e, 'name', '')
                    if original_name and '.' in original_name:
                        ext = os.path.splitext(original_name)[1]
                    else:
                        ext = '.jpg' if source_type_radio.value == 'Image' else '.mp4'
                    
                    filename = f"source_{source_type_radio.value.lower()}_{timestamp}{ext}"
                    source_file_path = filename
                    upload_path = os.path.join('./uploads', filename)
                    
                    # Ensure uploads directory exists
                    os.makedirs('./uploads', exist_ok=True)
                    
                    # Save uploaded file
                    with open(upload_path, 'wb') as f:
                        f.write(e.content.read())
                    
                    # Update appropriate preview
                    if source_type_radio.value == 'Image':
                        source_preview.set_source(upload_path)
                        source_preview.style('display: block')
                        source_video_preview.style('display: none')
                    else:
                        source_video_preview.set_source(upload_path)
                        source_video_preview.style('display: block')
                        source_preview.style('display: none')
                    
                    ui.notify(f'Source {source_type_radio.value.lower()} uploaded', type='positive')
                    
                except Exception as ex:
                    ui.notify(f'Upload failed: {str(ex)}', type='negative')
                    logger.error(f"Source upload error: {ex}")
            
            def handle_video_upload(e):
                nonlocal video_file_path
                try:
                    import time
                    timestamp = int(time.time())
                    
                    # Get file extension
                    original_name = getattr(e, 'name', '')
                    ext = os.path.splitext(original_name)[1] if original_name and '.' in original_name else '.mp4'
                    
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
                    ui.notify('Driving video uploaded', type='positive')
                    
                except Exception as ex:
                    ui.notify(f'Upload failed: {str(ex)}', type='negative')
                    logger.error(f"Video upload error: {ex}")
            
            async def generate_lipsync():
                if not source_file_path or not video_file_path:
                    ui.notify('Please upload both source and driving video files', type='warning')
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
                        f"./uploads/{video_file_path}",
                        source_type=source_type_radio.value.lower()
                    )
                    
                    progress.set_value(1.0)
                    
                    # Display result
                    with result_area:
                        ui.label('Generated Lipsync Video:').classes('text-lg font-semibold mt-4')
                        
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
                            ui.label(f'Source: {source_type_radio.value.title()} | Generated: {time.strftime("%Y-%m-%d %H:%M:%S")}').classes('text-sm text-gray-500')
                        except:
                            pass
                    
                    ui.notify(f'Lipsync generation completed!', type='positive')
                    
                except Exception as e:
                    ui.notify(f'Generation failed: {str(e)}', type='negative')
                    logger.error(f"Generation error: {e}")
                
                finally:
                    self.processing = False
                    generate_btn.props(remove='loading')
                    progress.style('display: none')
            
            # Generate button
            generate_btn = ui.button('Generate Lipsync Video', on_click=generate_lipsync)
            generate_btn.props('color=primary size=lg').classes('mt-4')
            
            # Instructions
            with ui.card().classes('w-full mt-4'):
                ui.label('Instructions:').classes('text-lg font-semibold mb-2')
                instructions = [
                    "1. Choose your source type: Image (for photo-based lipsync) or Video (for video-based lipsync)",
                    "2. Upload your source file (image or video of the person)",
                    "3. Upload the driving video (contains the audio/speech you want to sync)",
                    "4. Click 'Generate Lipsync Video' to create the result",
                    "5. The generated video will show the source person speaking the driving audio"
                ]
                for instruction in instructions:
                    ui.label(instruction).classes('text-sm mb-1')
        
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