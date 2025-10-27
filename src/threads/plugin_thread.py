import os
import shutil
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    PLUGIN_DIR, PRESET_DIR, PLUGIN_DOWNLOAD_URL, 
    PLUGIN_ZIP_TEMP_NAME
)

class PluginThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    cancelled = pyqtSignal()

    def __init__(self, runner_path, wineprefix_path, zip_file_path=None):
        super().__init__()
        self.runner_path = runner_path
        self.wineprefix_path = wineprefix_path
        self._is_cancelled = False
        self.zip_file_path = zip_file_path
        self.is_local_file = zip_file_path is not None
        
        self.REQUIRED_FOLDERS = ["aex", "CEP", "installer", "preset-backup", "scripts"]

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            self.log_signal.emit("[INFO] Starting plugin installation...")
            self.progress_signal.emit(10)

            if self._is_cancelled:
                self._cleanup_leftovers()
                self.cancelled.emit()
                return

            env = os.environ.copy()
            env['WINEPREFIX'] = self.wineprefix_path
            wine_path = os.path.join(self.runner_path, "bin", "wine")
            
            if not os.path.exists(wine_path):
                self.log_signal.emit(f"[ERROR] Wine not found at: {wine_path}")
                self.finished_signal.emit(False)
                return

            if not shutil.which('zenity'):
                self.log_signal.emit("[INFO] Attempting to install zenity...")
                subprocess.run(['sudo', 'apt', 'install', 'zenity', '-y'], capture_output=True) # Silently try to install

            self.progress_signal.emit(20)

            zip_file_path = PLUGIN_ZIP_TEMP_NAME
            
            if self.is_local_file:
                self.log_signal.emit(f"[INFO] Using local plugin file: {self.zip_file_path}")
                if not os.path.exists(self.zip_file_path):
                    self.log_signal.emit(f"[ERROR] Local file not found: {self.zip_file_path}")
                    self.finished_signal.emit(False)
                    return
                
                shutil.copy2(self.zip_file_path, zip_file_path)
            else:
                missing_folders = [folder for folder in self.REQUIRED_FOLDERS if not os.path.exists(folder)]
                
                if missing_folders:
                    self.log_signal.emit(f"[INFO] Missing folders: {missing_folders}, downloading plugin package...")
                    self.progress_signal.emit(30)
                    
                    if not shutil.which('wget'):
                        self.log_signal.emit("[ERROR] wget is not installed. Please install wget first.")
                        self.finished_signal.emit(False)
                        return
                    
                    result = subprocess.run([
                        'wget', '-O', zip_file_path, PLUGIN_DOWNLOAD_URL
                    ], capture_output=True, text=True)
                    
                    if result.returncode != 0:
                        self.log_signal.emit(f"[ERROR] Download failed: {result.stderr}")
                        self._cleanup_leftovers()
                        self.finished_signal.emit(False)
                        return
                else:
                    self.log_signal.emit("[INFO] All required plugin folders found, skipping download...")

            if os.path.exists(zip_file_path):
                self.log_signal.emit("[DEBUG] Extracting plugin package...")
                result = subprocess.run(['unzip', '-o', zip_file_path], capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.log_signal.emit(f"[ERROR] Extraction failed: {result.stderr}")
                    self._cleanup_leftovers()
                    self.finished_signal.emit(False)
                    return
                
                self.log_signal.emit("[INFO] Plugin package extracted successfully")
                os.remove(zip_file_path)
                self.log_signal.emit("[DEBUG] Removed zip file")

            self.progress_signal.emit(50)

            wine_drive_c_progfiles_x86 = os.path.join(self.wineprefix_path, "drive_c", "Program Files (x86)")
            cep_dst = os.path.join(wine_drive_c_progfiles_x86, "Common Files", "Adobe", "CEP", "extensions")
            
            self.log_signal.emit("[INFO] Installing AEX plugins...")
            self._copy_files("aex", PLUGIN_DIR, dirs_exist_ok=True)
            self.log_signal.emit("[INFO] AEX plugins installed successfully")
            self.progress_signal.emit(60)

            self.log_signal.emit("[INFO] Installing CEP extension...")
            reg_file = os.path.join("CEP", "AddKeys.reg")
            if os.path.exists(reg_file):
                result = subprocess.run([wine_path, "regedit", reg_file], env=env, capture_output=True, text=True)
                if result.returncode == 0:
                    self.log_signal.emit("[INFO] CEP registry keys imported")
                else:
                    self.log_signal.emit(f"[WARNING] CEP registry import failed: {result.stderr}")
            
            self._copy_files("CEP/flowv1.4.2", os.path.join(cep_dst, "flowv1.4.2"), is_single_dir=True)
            self.log_signal.emit("[INFO] CEP extension installed successfully")
            self.progress_signal.emit(70)

            self.log_signal.emit("[INFO] Installing presets...")
            self._copy_files("preset-backup", PRESET_DIR, dirs_exist_ok=True)
            self.log_signal.emit("[INFO] Presets installed successfully")
            self.progress_signal.emit(80)

            installer_src = "installer"
            self.log_signal.emit("[INFO] Running installer executables...")
            if os.path.exists(installer_src):
                original_dir = os.getcwd()
                os.chdir(installer_src)
                
                for exe in os.listdir('.'):
                    if exe.endswith('.exe') and exe not in ['E3D.exe', 'saber.exe']:
                        if self._is_cancelled:
                            os.chdir(original_dir)
                            self._cleanup_leftovers()
                            self.cancelled.emit()
                            return
                            
                        self.log_signal.emit(f"[INFO] Installing: {exe}")
                        # Use /verysilent and /suppressmsgboxes for NSIS installers
                        subprocess.run([wine_path, exe, '/verysilent', '/suppressmsgboxes'], env=env, capture_output=True, text=True)
                
                for exe in ['E3D.exe', 'saber.exe']:
                    if os.path.exists(exe):
                        self.log_signal.emit(f"[INFO] Please manually install: {exe}")
                        subprocess.run([wine_path, exe], env=env) # Run non-silently
                
                os.chdir(original_dir)
                
                video_copilot_dir = os.path.join(PLUGIN_DIR, "VideoCopilot")
                element_files = [("Element.aex", "Element.aex"), ("Element.license", "Element.license")]
                
                if os.path.exists(video_copilot_dir):
                    for src_name, dst_name in element_files:
                        src_path = os.path.join(installer_src, src_name)
                        if os.path.exists(src_path):
                            shutil.copy2(src_path, os.path.join(video_copilot_dir, dst_name))
                            self.log_signal.emit(f"[INFO] {dst_name} copied successfully")
                
                self.log_signal.emit("[INFO] Installers completed")
            else:
                self.log_signal.emit("[WARNING] Installer directory not found")

            self.progress_signal.emit(90)

            self._cleanup_leftovers()
            
            self.progress_signal.emit(100)
            self.log_signal.emit("[INFO] Plugin installation completed successfully!")
            self.finished_signal.emit(True)
            
        except Exception as e:
            self._cleanup_leftovers()
            self.log_signal.emit(f"[ERROR] Plugin installation failed: {str(e)}")
            self.finished_signal.emit(False)

    def _copy_files(self, src_path, dst_path, dirs_exist_ok=False, is_single_dir=False):
        """Helper to copy files/directories with cancellation check"""
        if is_single_dir:
            if os.path.exists(src_path):
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            else:
                 self.log_signal.emit(f"[WARNING] Source directory '{src_path}' not found for single-dir copy.")
            return

        if os.path.exists(src_path) and os.listdir(src_path):
            os.makedirs(dst_path, exist_ok=True)
            for item in os.listdir(src_path):
                if self._is_cancelled:
                    raise InterruptedError("Operation cancelled during file copy.")
                    
                full_src_path = os.path.join(src_path, item)
                full_dst_path = os.path.join(dst_path, item)
                
                if os.path.isdir(full_src_path):
                    shutil.copytree(full_src_path, full_dst_path, dirs_exist_ok=dirs_exist_ok)
                else:
                    shutil.copy2(full_src_path, full_dst_path)
        elif not os.path.exists(src_path):
            self.log_signal.emit(f"[WARNING] Source directory '{src_path}' not found for copy.")

    def _cleanup_leftovers(self):
        """Clean up leftover files"""
        try:
            self.log_signal.emit("[INFO] Cleaning up temporary files...")
            
            for folder in self.REQUIRED_FOLDERS:
                if os.path.exists(folder):
                    shutil.rmtree(folder)
                    self.log_signal.emit(f"[CLEAN] Removed {folder} folder")
                    
        except Exception as e:
            self.log_signal.emit(f"[WARNING] Cleanup failed: {str(e)}")