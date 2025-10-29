"""
FLOAT Lipsync Subprocess Manager

This class runs in the main Python environment and manages a persistent
daemon process running in the 'FLOAT' conda environment.

It communicates with 'float_lipsync_daemon.py' via JSON on stdin/stdout.
"""
import subprocess
import sys
import os
import json
import threading
import queue
from colorama import Fore, Style, init
from typing import Optional, Dict

init(autoreset=True)

class FloatLipsync:
    """
    Manages a persistent subprocess running 'float_lipsync_daemon.py'
    in the 'FLOAT' conda environment.
    Communicates via JSON over stdin/stdout.
    """
    def __init__(self, project_dir: str, config: Dict):
        self.project_dir = project_dir
        self.config = config
        self.proc = None
        self.read_thread = None
        self.response_queue = queue.Queue()
        self.daemon_ready = False
        self.lock = threading.Lock()

        self._start_daemon()

    def _get_float_python_exe(self) -> Optional[str]:
        """
        Tries to dynamically find the python.exe inside the 'FLOAT' conda env.
        This is more reliable than 'conda run'.
        """
        try:
            # 1. Find the base directory of the conda installation
            # Using shell=True for Windows compatibility with conda commands
            result = subprocess.run(['conda', 'info', '--base'], capture_output=True, text=True, check=True, shell=True)
            conda_base = result.stdout.strip()
            
            # 2. Construct the expected path to the FLOAT env's python.exe
            python_exe = os.path.join(conda_base, 'envs', 'FLOAT', 'python.exe')
            
            if os.path.exists(python_exe):
                print(f"{Fore.GREEN}[SUBPROCESS] Found FLOAT Python executable at: {python_exe}{Style.RESET_ALL}")
                return python_exe
            else:
                print(f"{Fore.YELLOW}[SUBPROCESS] FLOAT Python not found at expected path: {python_exe}{Style.RESET_ALL}")
                return None
        except FileNotFoundError:
             print(f"{Fore.RED}[SUBPROCESS] 'conda' command not found. Cannot find FLOAT env path.{Style.RESET_ALL}")
             return None
        except Exception as e:
            print(f"{Fore.RED}[SUBPROCESS] Error finding conda base path: {e}{Style.RESET_ALL}")
            return None

    def _start_daemon(self):
        daemon_script = os.path.join(self.project_dir, "scripts", "float_lipsync_daemon.py")
        
        # Check if daemon script exists
        if not os.path.exists(daemon_script):
            print(f"{Fore.RED}[SUBPROCESS] FATAL ERROR: Daemon script not found at: {daemon_script}{Style.RESET_ALL}")
            raise FileNotFoundError(f"Daemon script not found: {daemon_script}")

        # --- MODIFIED STARTUP LOGIC ---
        
        # 1. Try to find the specific python.exe first
        python_exe = self._get_float_python_exe()
        
        if python_exe:
            # Method 1: Direct executable call (most reliable)
            cmd = [python_exe, '-u', daemon_script]
            print(f"{Fore.CYAN}[SUBPROCESS] Starting daemon via direct path: {' '.join(cmd)}{Style.RESET_ALL}")
        else:
            # Method 2: Fallback to 'conda run' (what we used before)
            print(f"{Fore.YELLOW}[SUBPROCESS] Falling back to 'conda run'. This may fail if paths are not set correctly.{Style.RESET_ALL}")
            cmd = ['conda', 'run', '-n', 'FLOAT', 'python', '-u', daemon_script]
            print(f"{Fore.CYAN}[SUBPROCESS] Starting daemon via 'conda run': {' '.join(cmd)}{Style.RESET_ALL}")
        
        # --- END OF MODIFIED LOGIC ---

        try:
            # Use shell=True for Windows compatibility, especially with 'conda run'
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.project_dir, # Run from project root
                text=True,
                encoding='utf-8',
                bufsize=1, # Line-buffered
                shell=True 
            )
        except FileNotFoundError:
             print(f"{Fore.RED}[SUBPROCESS] FATAL ERROR: 'conda' command not found.{Style.RESET_ALL}")
             print(f"{Fore.YELLOW}[SUBPROCESS] Please ensure conda is installed and in your system's PATH.{Style.RESET_ALL}")
             raise
        except Exception as e:
             print(f"{Fore.RED}[SUBPROCESS] FATAL ERROR: Failed to start daemon: {e}{Style.RESET_ALL}")
             raise
        
        # Start threads to read stdout and stderr
        self.read_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self.read_thread.start()
        
        err_thread = threading.Thread(target=self._read_stderr, daemon=True)
        err_thread.start()

    def _read_stdout(self):
        """Reads JSON responses from the daemon's stdout."""
        try:
            for line in iter(self.proc.stdout.readline, ''):
                try:
                    response = json.loads(line)
                    if response.get("status") == "ok":
                        if response.get("type") == "ready":
                            self.daemon_ready = True
                        self.response_queue.put(response)
                    else:
                        print(f"{Fore.RED}[DAEMON_OUT] Error: {response.get('message')}{Style.RESET_ALL}")
                        self.response_queue.put(response) # Propagate error
                except json.JSONDecodeError:
                    # Might be other print statements, log them
                    print(f"{Fore.YELLOW}[DAEMON_OUT] (non-JSON): {line.strip()}{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}[DAEMON_OUT] Read thread error: {e}{Style.RESET_ALL}")
        except IOError:
            print(f"{Fore.YELLOW}[SUBPROCESS] Daemon stdout pipe closed.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[SUBPROCESS] Error in stdout read thread: {e}{Style.RESET_ALL}")

    def _read_stderr(self):
        """Reads and prints the daemon's stderr."""
        try:
            for line in iter(self.proc.stderr.readline, ''):
                print(f"{Fore.RED}[DAEMON_ERR] {line.strip()}{Style.RESET_ALL}")
        except IOError:
            print(f"{Fore.YELLOW}[SUBPROCESS] Daemon stderr pipe closed.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[SUBPROCESS] Error in stderr read thread: {e}{Style.RESET_ALL}")


    def _send_command(self, command: Dict) -> Dict:
        """Sends a JSON command to the daemon and waits for a response."""
        with self.lock:
            try:
                if not self.proc or self.proc.poll() is not None:
                    raise IOError("Daemon process is not running.")
                
                cmd_str = json.dumps(command) + '\n'
                self.proc.stdin.write(cmd_str)
                self.proc.stdin.flush()
                
                # Wait for the corresponding response
                # Add a timeout
                response = self.response_queue.get(timeout=120) # 2 min timeout
                return response
            except queue.Empty:
                print(f"{Fore.RED}[SUBPROCESS] Timeout waiting for daemon response to command: {command.get('command')}{Style.RESET_ALL}")
                return {"status": "error", "message": "Timeout waiting for daemon"}
            except Exception as e:
                print(f"{Fore.RED}[SUBPROCESS] Failed to send/receive command: {e}{Style.RESET_ALL}")
                return {"status": "error", "message": str(e)}

    def initialize(self):
        """Sends the 'initialize' command to the daemon."""
        print(f"{Fore.CYAN}[SUBPROCESS] Waiting for daemon to report ready...{Style.RESET_ALL}")
        # Wait for the very first "ready" message
        try:
            response = self.response_queue.get(timeout=300) # 5 min for model loading
            if response.get("type") == "ready" and response.get("status") == "ok":
                 print(f"{Fore.GREEN}[SUBPROCESS] Daemon reported ready.{Style.RESET_ALL}")
            else:
                 print(f"{Fore.RED}[SUBPROCESS] Daemon reported error on startup: {response.get('message')}{Style.RESET_ALL}")
                 return False
        except queue.Empty:
            print(f"{Fore.RED}[SUBPROCESS] Timeout waiting for daemon to start.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}[SUBPROCESS] Hint: Check if 'FLOAT' conda env exists and has dependencies.{Style.RESET_ALL}")
            return False

        # Now send the actual config and pre-analysis command
        print(f"{Fore.CYAN}[SUBPROCESS] Sending 'preload' command to daemon...{Style.RESET_ALL}")
        cmd = {
            "command": "preload",
            "project_dir": self.project_dir,
            "config": self.config
        }
        response = self._send_command(cmd)
        
        if response.get("status") == "ok":
            print(f"{Fore.GREEN}[SUBPROCESS] Daemon 'preload' complete.{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.RED}[SUBPROCESS] Daemon 'preload' failed: {response.get('message')}{Style.RESET_ALL}")
            return False

    def generate_lipsync(self, audio_path: str, output_filename: Optional[str] = None) -> Optional[str]:
        """Sends the 'generate' command to the daemon."""
        print(f"{Fore.CYAN}[SUBPROCESS] Sending 'generate' command for: {audio_path}{Style.RESET_ALL}")
        cmd = {
            "command": "generate",
            "audio_path": audio_path,
            "res_video_path": output_filename # Can be None
        }
        response = self._send_command(cmd)
        
        if response.get("status") == "ok":
            video_path = response.get("video_path")
            print(f"{Fore.GREEN}[SUBPROCESS] Daemon 'generate' complete. Video: {video_path}{Style.RESET_ALL}")
            return video_path
        else:
            print(f"{Fore.RED}[SUBPROCESS] Daemon 'generate' failed: {response.get('message')}{Style.RESET_ALL}")
            return None

    def cleanup(self):
        """Terminates the daemon subprocess."""
        if self.proc:
            print(f"{Fore.YELLOW}[SUBPROCESS] Terminating daemon...{Style.RESET_ALL}")
            try:
                # Send a quit command to stdin
                if self.proc.poll() is None:
                    self.proc.stdin.write(json.dumps({"command": "quit"}) + '\n')
                    self.proc.stdin.flush()
                
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception as e:
                print(f"{Fore.RED}[SUBPROCESS] Error during daemon termination: {e}{Style.RESET_ALL}")
            self.proc = None

