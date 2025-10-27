import os
import shutil
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    AE_NUX_DIR, AE_NUX_DOWNLOAD_URL, AE_NUX_ZIP_TEMP_NAME,
    AE_NUX_EXTRACT_DIR
)


class InstallThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    cancelled = pyqtSignal()

    def __init__(self, zip_file_path=None):
        super().__init__()
        self._is_cancelled = False
        self.zip_file_path = zip_file_path

        self.is_local_file = zip_file_path is not None

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            temp_zip_name = AE_NUX_ZIP_TEMP_NAME
            extract_dir = AE_NUX_EXTRACT_DIR
            
            if self.is_local_file:
                self.log_signal.emit("[INFO] Installing AeNux from local file...")
                self.progress_signal.emit(10)
                
                if not os.path.exists(self.zip_file_path):
                    self.log_signal.emit(f"[ERROR] Local file not found: {self.zip_file_path}")
                    self.finished_signal.emit(False)
                    return
                
                self.log_signal.emit("[DEBUG] Copying local file...")
                shutil.copy2(self.zip_file_path, temp_zip_name)
                
            else:
                if not shutil.which('wget'):
                    self.log_signal.emit("[ERROR] wget is not installed. Please install wget first.")
                    self.finished_signal.emit(False)
                    return

                self.log_signal.emit("[INFO] Installing AeNux from download...")
                self.progress_signal.emit(10)
                
                if self._is_cancelled:
                    self._cleanup_partial_install(temp_zip_name, extract_dir)
                    self.cancelled.emit()
                    return
                
                self.log_signal.emit("[DEBUG] Downloading AeNux package, around 1.3gb...")
                result = subprocess.run([
                    'wget', '-O', temp_zip_name, 
                    AE_NUX_DOWNLOAD_URL
                ], capture_output=True, text=True)
                
                if self._is_cancelled:
                    self._cleanup_partial_install(temp_zip_name, extract_dir)
                    self.cancelled.emit()
                    return
                
                if result.returncode != 0:
                    self.log_signal.emit(f"[ERROR] Download failed: {result.stderr}")
                    self.finished_signal.emit(False)
                    return
                
                self.log_signal.emit("[DEBUG] Download completed successfully")
            
            self.progress_signal.emit(40)
            
            if self._is_cancelled:
                self._cleanup_partial_install(temp_zip_name, extract_dir)
                self.cancelled.emit()
                return
            
            self.log_signal.emit("[DEBUG] Extracting files...")
            result = subprocess.run([
                'unzip', '-o', temp_zip_name, '-d', extract_dir
            ], capture_output=True, text=True)
            
            if self._is_cancelled:
                self._cleanup_partial_install(temp_zip_name, extract_dir)
                self.cancelled.emit()
                return
            
            if result.returncode != 0:
                self.log_signal.emit(f"[ERROR] Extraction failed: {result.stderr}")
                self.finished_signal.emit(False)
                return
            
            self.log_signal.emit("[DEBUG] Extraction completed")
            self.progress_signal.emit(60)
            
            self.log_signal.emit("[DEBUG] Cleaning up temporary files...")
            if os.path.exists(temp_zip_name):
                os.remove(temp_zip_name)
            
            if self._is_cancelled:
                self._cleanup_partial_install(temp_zip_name, extract_dir)
                self.cancelled.emit()
                return
            
            self.log_signal.emit(f"[DEBUG] Creating directory: {AE_NUX_DIR}")
            os.makedirs(AE_NUX_DIR, exist_ok=True)
            self.progress_signal.emit(70)
            
            source_dir = os.path.join(extract_dir, 'Support Files')
            if os.path.exists(source_dir):
                self.log_signal.emit("[DEBUG] Copying files to installation directory...")
                
                for item in os.listdir(source_dir):
                    if self._is_cancelled:
                        self._cleanup_partial_install(temp_zip_name, extract_dir)
                        self.cancelled.emit()
                        return
                        
                    src_path = os.path.join(source_dir, item)
                    dst_path = os.path.join(AE_NUX_DIR, item)
                    
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src_path, dst_path)
                
                self.log_signal.emit("[DEBUG] Files copied successfully")
                self.progress_signal.emit(90)
            else:
                self.log_signal.emit(f"[ERROR] Source directory '{source_dir}' not found after extraction")
                self.finished_signal.emit(False)
                return
            
            if self._is_cancelled:
                self._cleanup_partial_install(temp_zip_name, extract_dir)
                self.cancelled.emit()
                return
            
            self.log_signal.emit("[DEBUG] Final cleanup...")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            
            self.progress_signal.emit(100)
            self.log_signal.emit("[INFO] AeNux installation completed successfully!")
            self.finished_signal.emit(True)
            
        except Exception as e:
            self.log_signal.emit(f"[ERROR] Installation failed: {str(e)}")
            self.finished_signal.emit(False)

    def _cleanup_partial_install(self, zip_file, extract_dir):
        """Clean up partially installed files"""
        self.log_signal.emit("[CANCEL] Cleaning up partially installed files...")
        
        if os.path.exists(zip_file):
            os.remove(zip_file)
            self.log_signal.emit("[CANCEL] Removed downloaded zip file")
        
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
            self.log_signal.emit("[CANCEL] Removed extraction directory")
        
        if os.path.exists(AE_NUX_DIR):
            try:
                if len(os.listdir(AE_NUX_DIR)) < 5: 
                    shutil.rmtree(AE_NUX_DIR)
                    self.log_signal.emit("[CANCEL] Removed partially installed AeNux directory")
            except OSError:
                pass
