import os
import shutil
import subprocess
import tempfile
from PyQt6.QtCore import QThread, pyqtSignal

from config import BASE_DIR


class NvidialibsThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    cancelled = pyqtSignal()

    def __init__(self, runner_path, wineprefix_path):
        super().__init__()
        self.runner_path = runner_path
        self.wineprefix_path = wineprefix_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            self.log_signal.emit("[INFO] Starting NVIDIA libs installation...")
            self.progress_signal.emit(10)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            env = os.environ.copy()
            env['WINEPREFIX'] = self.wineprefix_path
            env['PATH'] = os.path.join(self.runner_path, "bin") + ":" + env.get('PATH', '')

            self.log_signal.emit("[DEBUG] Downloading NVIDIA libs...")
            self.progress_signal.emit(20)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            # Download the tar.xz file
            download_url = "https://github.com/SveSop/nvidia-libs/releases/download/v0.8.5/nvidia-libs-v0.8.5.tar.xz"
            nvidia_libs_dir = os.path.join(self.wineprefix_path, "nvidia-libs")
            os.makedirs(nvidia_libs_dir, exist_ok=True)
            tar_file = os.path.join(nvidia_libs_dir, "nvidia-libs-v0.8.5.tar.xz")

            result = subprocess.run(['wget', '-O', tar_file, download_url], capture_output=True, text=True)
            if result.returncode != 0:
                self.log_signal.emit(f"[ERROR] Download failed. Stderr: {result.stderr}")
                self.finished_signal.emit(False)
                return

            self.log_signal.emit("[DEBUG] Download completed.")
            self.progress_signal.emit(40)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_signal.emit("[DEBUG] Extracting NVIDIA libs...")
            extract_dir = os.path.join(nvidia_libs_dir, "nvidia-libs-v0.8.5")

            result = subprocess.run(['tar', '-xf', tar_file, '-C', nvidia_libs_dir], capture_output=True, text=True)
            if result.returncode != 0:
                self.log_signal.emit(f"[ERROR] Extraction failed. Stderr: {result.stderr}")
                self.finished_signal.emit(False)
                return

            self.log_signal.emit("[DEBUG] Extraction completed.")
            self.progress_signal.emit(60)

            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_signal.emit("[DEBUG] Running setup script...")
            setup_script = os.path.join(extract_dir, "setup_nvlibs.sh")

            if not os.path.exists(setup_script):
                self.log_signal.emit(f"[ERROR] Setup script not found at: {setup_script}")
                self.finished_signal.emit(False)
                return

            # Run setup script without capturing output to avoid hanging
            self.log_signal.emit(f"[DEBUG] Running: {setup_script} install")
            result = subprocess.run([setup_script, 'install'], env=env)
            if result.returncode != 0:
                self.log_signal.emit(f"[ERROR] Setup script failed with return code {result.returncode}.")
                self.finished_signal.emit(False)
                return

            self.log_signal.emit("[DEBUG] Setup completed successfully.")
            self.progress_signal.emit(100)

            self.log_signal.emit("[INFO] NVIDIA libs installation completed!")
            self.finished_signal.emit(True)

        except Exception as e:
            self.log_signal.emit(f"[ERROR] NVIDIA libs installation failed: {str(e)}")
            self.finished_signal.emit(False)
