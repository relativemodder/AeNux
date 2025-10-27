import os
import shutil
import subprocess
import glob
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    AE_NUX_DIR, PATCHED_FILE_FLAG, WINETRICKS_PATH,
    BASE_DIR, AENUX_COLORS_REG_CONTENT
)
from .nvidialibs_thread import NvidialibsThread


class PatchThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    cancelled = pyqtSignal()

    def __init__(self, runner_path, wineprefix_path):
        super().__init__()
        self.runner_path = runner_path
        self.wineprefix_path = wineprefix_path
        self._is_cancelled = False
        self._nvidia_success = False

    def cancel(self):
        self._is_cancelled = True

    def is_nvidia_present(self):
        """Check if NVIDIA is present on the system."""
        # Check for nvidia-smi command
        if shutil.which('nvidia-smi'):
            return True
        # Check for NVIDIA driver files
        if os.path.exists('/proc/driver/nvidia'):
            return True
        # Check for NVIDIA libraries
        try:
            # Use Popen to check lspci output without blocking
            process = subprocess.Popen(
                ['lspci'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=False
            )
            stdout, _ = process.communicate()
            if 'NVIDIA' in stdout.decode('utf-8', errors='ignore').upper():
                return True
        except:
            pass
        return False

    def _handle_nvidia_finished(self, success):
        self._nvidia_success = success

    def _run_and_stream_output(self, cmd_list, env, prefix):
        """
        Helper method to execute a command, stream its stdout/stderr 
        to the log_signal, and return the final returncode.
        """
        self.log_signal.emit(f"[EXEC] {' '.join(cmd_list)}")
        
        try:
            process = subprocess.Popen(
                cmd_list,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False, # Read as bytes
                bufsize=1  # Line buffering
            )

            # Stream stdout line by line
            for line in iter(process.stdout.readline, b''):
                decoded_line = line.decode('utf-8', errors='replace').rstrip()
                if decoded_line:
                    self.log_signal.emit(f"[{prefix}] {decoded_line}")
                
                # Check for cancellation inside the loop
                if self._is_cancelled:
                    process.terminate()
                    return -1 

            # Wait for the process to finish
            process.wait()
            return_code = process.returncode
            
            # Read stderr after the process has finished
            stderr_output = process.stderr.read()
            if stderr_output:
                for line in stderr_output.decode('utf-8', errors='replace').splitlines():
                     self.log_signal.emit(f"[{prefix} STDERR] {line}")
            
            return return_code
            
        except Exception as e:
            self.log_signal.emit(f"[EXEC ERROR] Command failed: {e}")
            return -2 # Custom error code for execution failure


    def run(self):
        try:
            self.log_signal.emit("[INFO] Starting AeNux patch application...")
            self.progress_signal.emit(10)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            env = os.environ.copy()
            env['WINEPREFIX'] = self.wineprefix_path

            wine_path = os.path.join(self.runner_path, "bin", "wine")
            wineserver_path = os.path.join(self.runner_path, "bin", "wineserver")

            if not os.path.exists(wine_path):
                self.log_signal.emit(f"[ERROR] Wine not found at: {wine_path}")
                self.finished_signal.emit(False)
                return

            if not os.path.exists(WINETRICKS_PATH):
                self.log_signal.emit(f"[ERROR] Winetricks not found at: {WINETRICKS_PATH}")
                self.finished_signal.emit(False)
                return

            self.log_signal.emit("[DEBUG] Checking dependencies...")
            self.progress_signal.emit(20)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            if not shutil.which('cabextract'):
                self.log_signal.emit("[ERROR] cabextract is not installed. Please install cabextract first.")
                self.finished_signal.emit(False)
                return

            if os.path.exists(self.wineprefix_path):
                self.log_signal.emit("[WARNING] Wineprefix already exists. It will be used as-is.")
            else:
                self.log_signal.emit("[DEBUG] Initializing wineprefix...")
                
                # Streamed wine boot
                return_code = self._run_and_stream_output([wine_path, "boot"], env, "WINE INIT")
                
                if return_code != 0:
                    self.log_signal.emit(f"[ERROR] Wine initialization failed. Return code: {return_code}")
                    self.finished_signal.emit(False)
                    return
                if return_code == -1: # Check for cancellation
                    self.cancelled.emit()
                    return
                self.log_signal.emit("[DEBUG] Wineprefix initialized.")

            self.progress_signal.emit(30)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_signal.emit("[DEBUG] Configuring registry and visual settings...")
            
            # Fast subprocess.run calls (no streaming needed)
            subprocess.run([wine_path, "reg", "add", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\ThemeManager", 
                          "/v", "ThemeActive", "/t", "REG_SZ", "/d", "0", "/f"], env=env, check=False)
            
            reg_file = os.path.join(BASE_DIR, "aenux-colors.reg")
            with open(reg_file, 'w') as f:
                f.write(AENUX_COLORS_REG_CONTENT)
            
            subprocess.run([wine_path, "regedit", reg_file], env=env, check=False)
            os.remove(reg_file)
            
            subprocess.run([wineserver_path, "-k"], env=env, check=False)
            
            self.progress_signal.emit(50)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            # Run winetricks and pipe output to log_signal
            self.log_signal.emit("[DEBUG] Running winetricks...")
            winetricks_cmd = [WINETRICKS_PATH, "-q", "dxvk", "corefonts", "gdiplus", "fontsmooth=rgb"]
            
            # Streamed winetricks
            winetricks_return_code = self._run_and_stream_output(winetricks_cmd, env, "WINETRICKS")
            
            if winetricks_return_code == -1: # Check for cancellation
                self.cancelled.emit()
                return

            # Check for winetricks failure
            if winetricks_return_code != 0:
                self.log_signal.emit(f"[ERROR] Winetricks failed with return code {winetricks_return_code}. Critical dependencies are missing.")
                self.finished_signal.emit(False)
                return

            self.log_signal.emit("[DEBUG] Winetricks finished successfully.")

            if self._is_cancelled:
                self.cancelled.emit()
                return

            vcr_bat = os.path.join(BASE_DIR, "asset", "vcr", "install_all.bat")
            if os.path.exists(vcr_bat):
                self.log_signal.emit("[DEBUG] Installing VCR dependencies...")
                
                # Streamed VCR installer
                vcr_return_code = self._run_and_stream_output([wine_path, vcr_bat], env, "VCR INSTALL")
                        
                if vcr_return_code == -1: # Check for cancellation
                    self.cancelled.emit()
                    return
                        
                if vcr_return_code != 0:
                    self.log_signal.emit(f"[WARNING] VCR installation failed (code {vcr_return_code}). Proceeding anyway.")
                else:
                    self.log_signal.emit("[DEBUG] VCR installation finished.")

            else:
                self.log_signal.emit("[WARNING] VCR install_all.bat not found, skipping...")

            self.progress_signal.emit(70)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_signal.emit("[DEBUG] Creating shortcuts to Linux folders...")
            wine_drive_c = os.path.join(self.wineprefix_path, "drive_c")
            # Use glob to find the user's Favorites directory (e.g., /users/aenux/Favorites)
            fav_dir = os.path.join(wine_drive_c, "users", "*", "Favorites") 
            
            fav_paths = glob.glob(fav_dir)
            if fav_paths:
                target_fav_dir = fav_paths[0]
                home_dir = os.path.expanduser("~")
                
                folders_to_link = ["Documents", "Downloads", "Pictures", "Videos", "Music"]
                
                for folder in folders_to_link:
                    link_path = os.path.join(target_fav_dir, folder)
                    # Clean up existing links/files
                    if os.path.islink(link_path) or os.path.exists(link_path):
                        try:
                            os.remove(link_path)
                        except OSError as e:
                            self.log_signal.emit(f"[WARNING] Could not remove existing link/file at {link_path}: {e}")
                            
                    try:
                        os.symlink(os.path.join(home_dir, folder), link_path)
                    except FileNotFoundError:
                        self.log_signal.emit(f"[WARNING] Linux folder {folder} not found, skipping link creation.")


                link_path_aenux = os.path.join(target_fav_dir, "AeNux")
                if os.path.exists(link_path_aenux):
                    os.remove(link_path_aenux)
                os.symlink(AE_NUX_DIR, os.path.join(target_fav_dir, "AeNux"))
                
                subprocess.run([wineserver_path, "-k"], env=env, check=False)
            else:
                self.log_signal.emit("[WARNING] Favorites directory not found, skipping shortcuts...")

            self.progress_signal.emit(85)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_signal.emit("[DEBUG] Overriding MSXML3 DLL...")
            wine_drive_c = os.path.join(self.wineprefix_path, "drive_c")
            system32_dir = os.path.join(wine_drive_c, "windows", "system32")
            msxml3_src = os.path.join(BASE_DIR, "asset", "System32", "msxml3.dll")

            if os.path.exists(system32_dir) and os.path.exists(msxml3_src):
                shutil.copy2(msxml3_src, os.path.join(system32_dir, "msxml3.dll"))
                shutil.copy2(msxml3_src, os.path.join(system32_dir, "msxml3r.dll"))
                
                subprocess.run([wine_path, "reg", "add", "HKCU\\Software\\Wine\\DllOverrides", 
                              "/v", "msxml3", "/d", "native,builtin", "/f"], env=env, check=False)
            else:
                self.log_signal.emit("[WARNING] msxml3.dll not found or System32 not available, skipping DLL override...")
            
            # The flag file creation must be the last step before success signal
            with open(PATCHED_FILE_FLAG, 'w') as f:
                f.write("Don't worry, it's patched.")

            # Check for NVIDIA and install libs if present after patching
            if self.is_nvidia_present():
                self.log_signal.emit("[INFO] NVIDIA detected. Installing NVIDIA libs...")
                nvidia_thread = NvidialibsThread(self.runner_path, self.wineprefix_path)
                nvidia_thread.log_signal.connect(self.log_signal.emit)
                nvidia_thread.progress_signal.connect(lambda p: self.progress_signal.emit(90 + int(p * 0.1)))  # Scale to 90-100%
                nvidia_thread.finished_signal.connect(lambda success: self._handle_nvidia_finished(success))
                nvidia_thread.cancelled.connect(self.cancelled.emit)
                nvidia_thread.run()  # Run synchronously

                if not self._nvidia_success:
                    self.log_signal.emit("[ERROR] NVIDIA libs installation failed. Aborting.")
                    self.finished_signal.emit(False)
                    return
                self.log_signal.emit("[INFO] NVIDIA libs installed successfully.")
            else:
                self.log_signal.emit("[INFO] NVIDIA not detected. Skipping NVIDIA libs installation.")

            self.progress_signal.emit(100)
            self.log_signal.emit("[INFO] AeNux patch applied successfully!")
            self.finished_signal.emit(True)
            
        except Exception as e:
            self.log_signal.emit(f"[ERROR] Patch application failed: {str(e)}")
            self.finished_signal.emit(False)