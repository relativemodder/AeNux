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
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            if 'NVIDIA' in result.stdout.upper():
                return True
        except:
            pass
        return False

    def _handle_nvidia_finished(self, success):
        self._nvidia_success = success

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
                result = subprocess.run([wine_path, "boot"], env=env, capture_output=True, text=True)
                if result.returncode != 0:
                    self.log_signal.emit(f"[ERROR] Wine initialization failed. Stderr: {result.stderr}")
                    self.finished_signal.emit(False)
                    return
                self.log_signal.emit("[DEBUG] Wineprefix initialized.")

            self.progress_signal.emit(30)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_signal.emit("[DEBUG] Configuring registry and visual settings...")
            
            subprocess.run([wine_path, "reg", "add", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\ThemeManager", 
                          "/v", "ThemeActive", "/t", "REG_SZ", "/d", "0", "/f"], env=env)
            
            reg_file = os.path.join(BASE_DIR, "aenux-colors.reg")
            with open(reg_file, 'w') as f:
                f.write(AENUX_COLORS_REG_CONTENT)
            
            subprocess.run([wine_path, "regedit", reg_file], env=env)
            os.remove(reg_file)
            
            subprocess.run([wineserver_path, "-k"], env=env)
            
            self.progress_signal.emit(50)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            # Run winetricks and pipe output to log_signal
            self.log_signal.emit("[DEBUG] Running winetricks...")
            winetricks_cmd = [WINETRICKS_PATH, "-q", "dxvk", "corefonts", "gdiplus", "fontsmooth=rgb"]
            
            # Use subprocess.run to capture the output
            result = subprocess.run(winetricks_cmd, env=env, capture_output=True, text=True)
            
            # Log stdout and stderr line-by-line
            if result.stdout:
                for line in result.stdout.splitlines():
                    self.log_signal.emit(f"[WINETRICKS] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    self.log_signal.emit(f"[WINETRICKS STDERR] {line}")
            
            # Check for winetricks failure
            if result.returncode != 0:
                self.log_signal.emit(f"[ERROR] Winetricks failed with return code {result.returncode}. Critical dependencies are missing.")
                self.finished_signal.emit(False)
                return

            self.log_signal.emit("[DEBUG] Winetricks finished successfully.")

            if self._is_cancelled:
                self.cancelled.emit()
                return

            vcr_bat = os.path.join(BASE_DIR, "asset", "vcr", "install_all.bat")
            if os.path.exists(vcr_bat):
                self.log_signal.emit("[DEBUG] Installing VCR dependencies...")
                
                vcr_result = subprocess.run([wine_path, vcr_bat], env=env, capture_output=True, text=True)

                # Log the VCR installer output
                if vcr_result.stdout:
                    for line in vcr_result.stdout.splitlines():
                        self.log_signal.emit(f"[VCR INSTALL] {line}")
                if vcr_result.stderr:
                    for line in vcr_result.stderr.splitlines():
                        self.log_signal.emit(f"[VCR STDERR] {line}")
                        
                if vcr_result.returncode != 0:
                    self.log_signal.emit(f"[WARNING] VCR installation failed (code {vcr_result.returncode}). Proceeding anyway.")
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
            fav_dir = os.path.join(wine_drive_c, "users", "*", "Favorites") 
            
            fav_paths = glob.glob(fav_dir)
            if fav_paths:
                target_fav_dir = fav_paths[0]
                home_dir = os.path.expanduser("~")
                
                folders_to_link = ["Documents", "Downloads", "Pictures", "Videos", "Music"]
                
                for folder in folders_to_link:
                    link_path = os.path.join(target_fav_dir, folder)
                    # Use os.path.islink and os.path.exists for safer removal
                    if os.path.islink(link_path) or os.path.exists(link_path):
                         # If it's a symlink, os.remove is correct. If it's a directory (unlikely but safe), os.rmdir would be needed, but we expect a link.
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
                
                subprocess.run([wineserver_path, "-k"], env=env)
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
                              "/v", "msxml3", "/d", "native,builtin", "/f"], env=env)
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
