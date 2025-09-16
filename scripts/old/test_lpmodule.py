import asyncio
import time
import subprocess
import sys
from pathlib import Path
from nicegui import ui, app
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LipsyncTestUI:
    def __init__(self):
        # HARDCODE YOUR TEST PATHS HERE
        self.source_image_path = r"C:\Users\Jason\Downloads\todo\dh.png"
        self.driving_video_path = r"C:\Users\Jason\Downloads\todo\d34.mp4"
        self.source_type = "image"  # Change to "video" if using video source
        
        # Conda environment settings
        self.conda_env_name = "FasterLP"
        self.conda_base_path = r"C:\Users\Jason\Miniconda3"  # Fixed: Capital M
        self.conda_exe_path = r"C:\Users\Jason\Miniconda3\Scripts\conda.exe"  # Direct path
        
        self.processing = False
        self.result_video_path = None
    
    def find_conda_installation(self, log_area):
        """Find the correct conda installation path - using sync subprocess"""
        # Try the exact path we found first
        conda_paths_to_try = [
            self.conda_exe_path,  # Direct path from $env:CONDA_EXE
            f"{self.conda_base_path}\\Scripts\\conda.exe",
            f"{self.conda_base_path}\\Scripts\\conda.bat"
        ]
        
        log_area.push("Testing known conda paths...")
        
        for conda_path in conda_paths_to_try:
            try:
                log_area.push(f"Trying: {conda_path}")
                
                # First check if file exists
                if not Path(conda_path).exists():
                    log_area.push(f"X File not found: {conda_path}")
                    continue
                
                log_area.push(f"+ File exists, testing execution...")
                
                # Use synchronous subprocess
                result = subprocess.run(
                    [conda_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    version = result.stdout.strip()
                    log_area.push(f"+ Found working conda at {conda_path}: {version}")
                    return conda_path
                else:
                    error_msg = result.stderr.strip()
                    log_area.push(f"X Execution failed (code {result.returncode}): {error_msg}")
                    
            except Exception as e:
                log_area.push(f"X Exception testing {conda_path}: {str(e)}")
                continue
        
        # If all specific paths fail, try a simple approach
        log_area.push("Trying alternative approach with cmd /c conda...")
        try:
            result = subprocess.run(
                ["cmd", "/c", "conda --version"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                version = result.stdout.strip()
                log_area.push(f"+ Found conda via cmd: {version}")
                return "conda"  # Special marker for cmd-based conda
            else:
                log_area.push(f"X cmd conda failed: {result.stderr.strip()}")
        except Exception as e:
            log_area.push(f"X cmd conda exception: {str(e)}")
        
        raise RuntimeError("Could not find conda installation")
    
    def list_conda_environments(self, conda_path, log_area):
        """List available conda environments - using sync subprocess"""
        try:
            if conda_path == "conda":
                # Use cmd /c for the special conda marker
                result = subprocess.run(
                    ["cmd", "/c", "conda env list"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            else:
                # Use direct path
                result = subprocess.run(
                    [conda_path, "env", "list"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
            if result.returncode == 0:
                env_list = result.stdout.strip()
                log_area.push("Available conda environments:")
                environments = []
                for line in env_list.split('\n'):
                    if line.strip() and not line.startswith('#'):
                        env_name = line.split()[0] if line.split() else ""
                        if env_name:
                            environments.append(env_name)
                            log_area.push(f"  - {env_name}")
                
                return environments
            else:
                log_area.push(f"Failed to list environments: {result.stderr.strip()}")
                return []
                
        except Exception as e:
            log_area.push(f"Error listing environments: {str(e)}")
            return []
    
    async def run_lipsync_with_conda(self, log_area):
        """Run the lipsync generation with conda environment activation"""
        def run_in_thread():
            """Run the conda operations in a separate thread"""
            try:
                # First, find conda installation
                conda_path = self.find_conda_installation(log_area)
                
                # List environments and check if target exists
                environments = self.list_conda_environments(conda_path, log_area)
                
                if self.conda_env_name not in environments:
                    log_area.push(f"X Environment '{self.conda_env_name}' not found!")
                    log_area.push(f"Available environments: {', '.join(environments)}")
                    
                    # Try to find similar environment names
                    similar_envs = [env for env in environments if 'faster' in env.lower() or 'lp' in env.lower()]
                    if similar_envs:
                        log_area.push(f"Similar environments found: {', '.join(similar_envs)}")
                        log_area.push("You might need to update self.conda_env_name in the script")
                    
                    raise RuntimeError(f"Conda environment '{self.conda_env_name}' does not exist")
                
                log_area.push(f"+ Environment '{self.conda_env_name}' found")
                
                # Create a temporary Python script to run with conda
                script_content = f'''
import sys
import os

# Add the lipsync module path
lipsync_module_path = r"C:\\Users\\Jason\\Desktop\\Important\\Projects\\AvatarResurrection\\scripts"
sys.path.insert(0, lipsync_module_path)

# Set environment variable to avoid potential GUI issues
os.environ["MPLBACKEND"] = "Agg"

import time

start_time = time.time()
print("Starting lipsync generation...")
print(f"Python executable: {{sys.executable}}")
print(f"Python version: {{sys.version}}")
print(f"Looking for lipsync_generator in: {{lipsync_module_path}}")

# Check if lipsync_generator.py exists
lipsync_file = os.path.join(lipsync_module_path, "lipsync_generator.py")
print(f"Checking for file: {{lipsync_file}}")
print(f"File exists: {{os.path.exists(lipsync_file)}}")

if os.path.exists(lipsync_file):
    print("SUCCESS: lipsync_generator.py found")
else:
    print("ERROR: lipsync_generator.py NOT found")
    print("Files in directory:")
    try:
        for f in os.listdir(lipsync_module_path):
            if f.endswith('.py'):
                print(f"  - {{f}}")
    except Exception as e:
        print(f"  Error listing directory: {{e}}")

try:
    # Import the lipsync generator
    from lipsync_generator import generate_lipsync_video_sync
    print("SUCCESS: Successfully imported lipsync_generator")
    
    result_path = generate_lipsync_video_sync(
        source_path=r"{self.source_image_path}",
        driving_video_path=r"{self.driving_video_path}",
        source_type="{self.source_type}"
    )
    
    end_time = time.time()
    time_taken = end_time - start_time
    
    print(f"SUCCESS: {{result_path}}")
    print(f"TIME_TAKEN: {{time_taken:.2f}}")
    
except ImportError as e:
    print(f"IMPORT_ERROR: {{str(e)}}")
    print("Python path:")
    for p in sys.path:
        print(f"  - {{p}}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {{str(e)}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
                
                # Write temporary script to a different location to avoid auto-reload
                temp_script = Path.cwd().parent / f"temp_lipsync_script_{int(time.time())}.py"
                with open(temp_script, 'w') as f:
                    f.write(script_content)
                
                # Also verify we're actually using the right environment
                log_area.push(f"Checking conda environment activation...")
                env_check_parts = ["cmd", "/c", conda_path, "run", "-n", self.conda_env_name, "python", "-c", "import sys; print(f'CONDA_ENV_CHECK: {sys.executable}')"]
                
                env_process = subprocess.run(
                    env_check_parts,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=Path.cwd()
                )
                
                if env_process.returncode == 0:
                    log_area.push(f"Environment check output: {env_process.stdout.strip()}")
                else:
                    log_area.push(f"Environment check failed: {env_process.stderr.strip()}")
                
                # Prepare conda run command using the appropriate method
                if conda_path == "conda":
                    # For cmd-based conda, use simple command
                    cmd_parts = ["cmd", "/c", "conda", "run", "-n", self.conda_env_name, "python", str(temp_script)]
                else:
                    # For direct path, don't use quotes in the command list
                    cmd_parts = ["cmd", "/c", conda_path, "run", "-n", self.conda_env_name, "python", str(temp_script)]
                
                log_area.push(f"Running: {' '.join(cmd_parts)}")
                
                # Run the command with real-time output
                process = subprocess.Popen(
                    cmd_parts,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    cwd=Path.cwd()
                )
                
                # Read output in real-time
                result_path = None
                time_taken = 0
                output_lines = []  # Store all output
                
                try:
                    for line in process.stdout:
                        line_str = line.strip()
                        if line_str:
                            output_lines.append(line_str)  # Store for debugging
                            log_area.push(line_str)
                            
                            # Parse special output
                            if line_str.startswith("SUCCESS: "):
                                result_path = line_str.replace("SUCCESS: ", "")
                            elif line_str.startswith("TIME_TAKEN: "):
                                time_taken = float(line_str.replace("TIME_TAKEN: ", ""))
                            elif line_str.startswith("ERROR: "):
                                error_msg = line_str.replace("ERROR: ", "")
                                raise RuntimeError(error_msg)
                            elif line_str.startswith("IMPORT_ERROR: "):
                                error_msg = line_str.replace("IMPORT_ERROR: ", "")
                                raise RuntimeError(f"Import failed: {error_msg}")
                
                except Exception as read_error:
                    log_area.push(f"Error reading output: {read_error}")
                    # Still try to get the process result
                
                # Wait for process to complete
                return_code = process.wait()
                
                # Log final status
                log_area.push(f"Process completed with return code: {return_code}")
                
                if len(output_lines) > 0:
                    log_area.push(f"Total output lines: {len(output_lines)}")
                else:
                    log_area.push("No output received from process")
                
                # Clean up temp script
                if temp_script.exists():
                    temp_script.unlink()
                
                if return_code != 0:
                    # Show more details about the failure
                    log_area.push("Process failed. Recent output:")
                    for line in output_lines[-10:]:  # Show last 10 lines
                        log_area.push(f"  > {line}")
                    raise RuntimeError(f"Process failed with return code {return_code}")
                
                if not result_path:
                    log_area.push("No success message found in output")
                    raise RuntimeError("No result path returned from lipsync generation")
                    
                return result_path, time_taken
                
            except Exception as e:
                # Clean up temp script on error
                if 'temp_script' in locals() and temp_script.exists():
                    temp_script.unlink()
                raise e
        
        # Run in a separate thread to avoid asyncio issues
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            # Use asyncio.sleep to yield control while waiting
            while not future.done():
                await asyncio.sleep(0.1)
            return future.result()
        
    def create_ui(self):
        """Create the test UI"""
        
        @ui.page('/')
        def main_page():
            ui.label('Lipsync Generator Test').classes('text-3xl font-bold mb-6')
            
            # Display current settings
            with ui.card().classes('w-full mb-4'):
                ui.label('Test Configuration:').classes('text-lg font-semibold mb-2')
                ui.label(f'Source {self.source_type.title()}: {self.source_image_path}').classes('text-sm mb-1')
                ui.label(f'Driving Video: {self.driving_video_path}').classes('text-sm mb-1')
                ui.label(f'Conda Environment: {self.conda_env_name}').classes('text-sm mb-1')
                ui.label('Update these paths in the test_lipsync_ui.py file').classes('text-xs text-gray-500')
            
            # Status and controls
            status_label = ui.label('Ready to generate').classes('text-lg mb-4')
            progress_bar = ui.linear_progress(value=0).style('display: none')
            time_label = ui.label('').classes('text-sm text-gray-600 mb-4').style('display: none')
            
            # Generate button
            generate_btn = ui.button('Generate Lipsync Video', on_click=lambda: generate_lipsync())
            generate_btn.props('color=primary size=lg').classes('mb-6')
            
            # Result area
            result_card = ui.card().classes('w-full').style('display: none')
            with result_card:
                ui.label('Generated Video:').classes('text-lg font-semibold mb-2')
                result_video = ui.video('').classes('w-full max-w-2xl').props('controls')
                download_btn = ui.button('Download Video', on_click=lambda: None).props('color=secondary')
            
            # Logs area
            with ui.card().classes('w-full mt-4'):
                ui.label('Logs:').classes('text-lg font-semibold mb-2')
                log_area = ui.log().classes('w-full h-40')
            
                # Also create a global manager instance for preloading
                if not hasattr(self, 'lipsync_manager'):
                    self.lipsync_manager = None
                
                # Initialize manager and preload models in startup
                async def initialize_and_preload():
                    """Initialize the lipsync manager and preload models"""
                    try:
                        # Import here to avoid circular imports
                        from lipsync_generator import LipsyncDockerManager
                        
                        log_area.push("Initializing lipsync manager...")
                        self.lipsync_manager = LipsyncDockerManager()
                        
                        log_area.push("Starting Docker container...")
                        success = await self.lipsync_manager.start_container()
                        if not success:
                            raise RuntimeError("Failed to start Docker container")
                        
                        log_area.push("Preloading models into memory...")
                        preload_success = await self.lipsync_manager.preload_models()
                        
                        if preload_success:
                            log_area.push("+ Models successfully preloaded!")
                            log_area.push("+ System ready for fast generation")
                        else:
                            log_area.push("! Model preload had issues, but continuing...")
                            
                        return True
                        
                    except Exception as e:
                        log_area.push(f"X Initialization failed: {str(e)}")
                        return False
                
                # Add initialization button
                init_btn = ui.button('Initialize & Preload Models', on_click=lambda: initialize_and_preload())
                init_btn.props('color=secondary size=md').classes('mb-4')
                
                # Update the main generate function to use the preloaded manager
                async def generate_lipsync():
                    if self.processing:
                        ui.notify('Generation already in progress', type='warning')
                        return
                    
                    # Validate paths
                    if not Path(self.source_image_path).exists():
                        ui.notify(f'Source file not found: {self.source_image_path}', type='negative')
                        log_area.push(f'ERROR: Source file not found: {self.source_image_path}')
                        return
                    
                    if not Path(self.driving_video_path).exists():
                        ui.notify(f'Driving video not found: {self.driving_video_path}', type='negative')
                        log_area.push(f'ERROR: Driving video not found: {self.driving_video_path}')
                        return
                    
                    # Check if models are preloaded
                    if self.lipsync_manager and self.lipsync_manager.is_ready:
                        log_area.push("Using preloaded models for fast generation...")
                        # Use the direct manager instead of the conda wrapper
                        self.processing = True
                        start_time = time.time()
                        
                        try:
                            # Update UI
                            generate_btn.props('loading')
                            status_label.text = 'Generating with preloaded models...'
                            progress_bar.style('display: block')
                            progress_bar.set_value(0.3)
                            result_card.style('display: none')
                            
                            log_area.push('Using fast preloaded generation...')
                            
                            # Generate directly with preloaded manager
                            result_path = await self.lipsync_manager.generate_lipsync(
                                source_path=self.source_image_path,
                                driving_video_path=self.driving_video_path,
                                source_type=self.source_type
                            )
                            
                            # Calculate total time taken
                            end_time = time.time()
                            total_time = end_time - start_time
                            time_minutes = int(total_time // 60)
                            time_seconds = int(total_time % 60)
                            
                            # Update UI with results
                            progress_bar.set_value(1.0)
                            status_label.text = f'Generation completed! Time taken: {time_minutes}m {time_seconds}s'
                            time_label.text = f'Total time: {total_time:.2f} seconds ({time_minutes}m {time_seconds}s)'
                            time_label.style('display: block')
                            
                            # Show result video
                            if Path(result_path).exists():
                                result_video.set_source(result_path)
                                result_card.style('display: block')
                                
                                # Update download button
                                download_btn.on('click', lambda: ui.download(result_path))
                                
                                # Log results
                                file_size = Path(result_path).stat().st_size
                                log_area.push(f'SUCCESS: Video generated at {result_path}')
                                log_area.push(f'File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)')
                                log_area.push(f'Total time: {total_time:.2f} seconds (FAST - using preloaded models!)')
                                
                                ui.notify(f'Video generated successfully in {time_minutes}m {time_seconds}s!', type='positive')
                                
                                self.result_video_path = result_path
                            else:
                                raise FileNotFoundError(f"Generated video not found at {result_path}")
                                
                        except Exception as e:
                            end_time = time.time()
                            time_taken = end_time - start_time
                            
                            error_msg = f'Generation failed after {time_taken:.2f}s: {str(e)}'
                            status_label.text = error_msg
                            log_area.push(f'ERROR: {error_msg}')
                            ui.notify(f'Generation failed: {str(e)}', type='negative')
                            logger.error(f"Generation error: {e}")
                        
                        finally:
                            self.processing = False
                            generate_btn.props(remove='loading')
                            progress_bar.style('display: none')
                            log_area.push("=== Generation process completed ===")
                    
                    else:
                        # Fall back to conda-based generation
                        log_area.push("Models not preloaded, using conda-based generation...")
                        
                        self.processing = True
                        start_time = time.time()
                        
                        try:
                            # Update UI
                            generate_btn.props('loading')
                            status_label.text = 'Initializing...'
                            progress_bar.style('display: block')
                            progress_bar.set_value(0.1)
                            result_card.style('display: none')
                            
                            log_area.push('Starting lipsync generation...')
                            log_area.push(f'Source {self.source_type}: {self.source_image_path}')
                            log_area.push(f'Driving video: {self.driving_video_path}')
                            log_area.push(f'Conda environment: {self.conda_env_name}')
                            
                            # Update progress
                            status_label.text = 'Finding conda installation...'
                            progress_bar.set_value(0.2)
                            
                            # Generate lipsync with conda activation
                            status_label.text = 'Generating lipsync video...'
                            progress_bar.set_value(0.4)
                            
                            # Call the lipsync function with conda
                            result_path, generation_time = await self.run_lipsync_with_conda(log_area)
                            
                            # Calculate total time taken
                            end_time = time.time()
                            total_time = end_time - start_time
                            time_minutes = int(total_time // 60)
                            time_seconds = int(total_time % 60)
                            
                            # Update UI with results
                            progress_bar.set_value(1.0)
                            status_label.text = f'Generation completed! Time taken: {time_minutes}m {time_seconds}s'
                            time_label.text = f'Total time: {total_time:.2f} seconds ({time_minutes}m {time_seconds}s)'
                            time_label.style('display: block')
                            
                            # Show result video
                            if Path(result_path).exists():
                                result_video.set_source(result_path)
                                result_card.style('display: block')
                                
                                # Update download button
                                download_btn.on('click', lambda: ui.download(result_path))
                                
                                # Log results
                                file_size = Path(result_path).stat().st_size
                                log_area.push(f'SUCCESS: Video generated at {result_path}')
                                log_area.push(f'File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)')
                                log_area.push(f'Total time: {total_time:.2f} seconds')
                                log_area.push(f'Generation time: {generation_time:.2f} seconds')
                                
                                ui.notify(f'Video generated successfully in {time_minutes}m {time_seconds}s!', type='positive')
                                
                                self.result_video_path = result_path
                            else:
                                raise FileNotFoundError(f"Generated video not found at {result_path}")
                            
                        except Exception as e:
                            end_time = time.time()
                            time_taken = end_time - start_time
                            
                            error_msg = f'Generation failed after {time_taken:.2f}s: {str(e)}'
                            status_label.text = error_msg
                            log_area.push(f'ERROR: {error_msg}')
                            
                            # Don't clear the log area, just add error info
                            ui.notify(f'Generation failed: {str(e)}', type='negative')
                            logger.error(f"Generation error: {e}")
                        
                        finally:
                            self.processing = False
                            generate_btn.props(remove='loading')
                            progress_bar.style('display: none')
                            
                            # Keep logs visible even after completion
                            log_area.push("=== Generation process completed ===")
                            log_area.push(f"Processing flag reset to: {self.processing}")
                if self.processing:
                    ui.notify('Generation already in progress', type='warning')
                    return
                
                # Validate paths
                if not Path(self.source_image_path).exists():
                    ui.notify(f'Source file not found: {self.source_image_path}', type='negative')
                    log_area.push(f'ERROR: Source file not found: {self.source_image_path}')
                    return
                
                if not Path(self.driving_video_path).exists():
                    ui.notify(f'Driving video not found: {self.driving_video_path}', type='negative')
                    log_area.push(f'ERROR: Driving video not found: {self.driving_video_path}')
                    return
                
                self.processing = True
                start_time = time.time()
                
                try:
                    # Update UI
                    generate_btn.props('loading')
                    status_label.text = 'Initializing...'
                    progress_bar.style('display: block')
                    progress_bar.set_value(0.1)
                    result_card.style('display: none')
                    
                    log_area.push('Starting lipsync generation...')
                    log_area.push(f'Source {self.source_type}: {self.source_image_path}')
                    log_area.push(f'Driving video: {self.driving_video_path}')
                    log_area.push(f'Conda environment: {self.conda_env_name}')
                    
                    # Update progress
                    status_label.text = 'Finding conda installation...'
                    progress_bar.set_value(0.2)
                    
                    # Generate lipsync with conda activation
                    status_label.text = 'Generating lipsync video...'
                    progress_bar.set_value(0.4)
                    
                    # Call the lipsync function with conda
                    result_path, generation_time = await self.run_lipsync_with_conda(log_area)
                    
                    # Calculate total time taken
                    end_time = time.time()
                    total_time = end_time - start_time
                    time_minutes = int(total_time // 60)
                    time_seconds = int(total_time % 60)
                    
                    # Update UI with results
                    progress_bar.set_value(1.0)
                    status_label.text = f'Generation completed! Time taken: {time_minutes}m {time_seconds}s'
                    time_label.text = f'Total time: {total_time:.2f} seconds ({time_minutes}m {time_seconds}s)'
                    time_label.style('display: block')
                    
                    # Show result video
                    if Path(result_path).exists():
                        # Create a cache-busting URL
                        import random
                        cache_buster = random.randint(1000, 9999)
                        
                        result_video.set_source(result_path)
                        result_card.style('display: block')
                        
                        # Update download button
                        download_btn.on('click', lambda: ui.download(result_path))
                        
                        # Log results
                        file_size = Path(result_path).stat().st_size
                        log_area.push(f'SUCCESS: Video generated at {result_path}')
                        log_area.push(f'File size: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)')
                        log_area.push(f'Total time: {total_time:.2f} seconds')
                        log_area.push(f'Generation time: {generation_time:.2f} seconds')
                        
                        ui.notify(f'Video generated successfully in {time_minutes}m {time_seconds}s!', type='positive')
                        
                        self.result_video_path = result_path
                    else:
                        raise FileNotFoundError(f"Generated video not found at {result_path}")
                    
                except Exception as e:
                    end_time = time.time()
                    time_taken = end_time - start_time
                    
                    error_msg = f'Generation failed after {time_taken:.2f}s: {str(e)}'
                    status_label.text = error_msg
                    log_area.push(f'ERROR: {error_msg}')
                    
                    # Don't clear the log area, just add error info
                    ui.notify(f'Generation failed: {str(e)}', type='negative')
                    logger.error(f"Generation error: {e}")
                
                finally:
                    self.processing = False
                    generate_btn.props(remove='loading')
                    progress_bar.style('display: none')
                    
                    # Keep logs visible even after completion
                    log_area.push("=== Generation process completed ===")
                    log_area.push(f"Processing flag reset to: {self.processing}")
            
            # Instructions
            with ui.card().classes('w-full mt-4'):
                ui.label('Instructions:').classes('text-lg font-semibold mb-2')
                instructions = [
                    "1. Make sure Docker container is running",
                    f"2. Verify conda environment '{self.conda_env_name}' exists",
                    "3. Update conda_base_path if your miniconda/anaconda is in different location",
                    "4. Click 'Generate Lipsync Video' to start the process",
                    "5. Watch the logs for progress updates",
                    "6. The result video will play automatically when done"
                ]
                for instruction in instructions:
                    ui.label(instruction).classes('text-sm mb-1')

# Create and run the app
def main():
    app_instance = LipsyncTestUI()
    app_instance.create_ui()
    
    # Run the UI with reload disabled
    ui.run(
        host='localhost', 
        port=8080, 
        title='Lipsync Test UI',
        show=True,  # Auto-open browser
        reload=False  # Disable auto-reload to prevent log clearing
    )

if __name__ in {"__main__", "__mp_main__"}:
    main()