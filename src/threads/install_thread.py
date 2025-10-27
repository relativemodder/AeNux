import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    AE_NUX_DIR, AE_NUX_DOWNLOAD_URL, AE_NUX_ZIP_TEMP_NAME,
    AE_NUX_EXTRACT_DIR
)


class InstallThread(QThread):
    """
    Thread for installing AeNux package.

    Handles downloading (if needed), extracting, and installing AeNux files.
    Supports local file installation and remote download with progress reporting.
    """
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    cancelled = pyqtSignal()

    def __init__(self, zip_file_path: Optional[str] = None):
        super().__init__()
        self._is_cancelled = False
        self.zip_file_path = zip_file_path
        self.is_local_file = zip_file_path is not None

    def cancel(self):
        self._is_cancelled = True

    def run(self) -> None:
        """
        Main execution method for the installation thread.
        """
        try:
            temp_zip_path = Path(AE_NUX_ZIP_TEMP_NAME)
            extract_path = Path(AE_NUX_EXTRACT_DIR)

            if self.is_local_file:
                self._install_from_local_file(temp_zip_path)
            else:
                self._download_and_install(temp_zip_path, extract_path)

            if not self._is_cancelled:
                self._extract_and_install(temp_zip_path, extract_path)
                self._finalize_installation(extract_path)

        except Exception as e:
            self.log_signal.emit(f"[ERROR] Installation failed: {str(e)}")
            self.finished_signal.emit(False)

    def _install_from_local_file(self, temp_zip_path: Path) -> None:
        """
        Install AeNux from a local zip file.
        """
        self.log_signal.emit("[INFO] Installing AeNux from local file...")
        self.progress_signal.emit(10)

        if not Path(self.zip_file_path).exists():
            self.log_signal.emit(f"[ERROR] Local file not found: {self.zip_file_path}")
            self.finished_signal.emit(False)
            return

        self.log_signal.emit("[DEBUG] Copying local file...")
        shutil.copy2(self.zip_file_path, temp_zip_path)

    def _download_and_install(self, temp_zip_path: Path, extract_path: Path) -> None:
        """
        Download AeNux package using wget with progress reporting.
        """
        if not shutil.which('wget'):
            self.log_signal.emit("[ERROR] wget is not installed. Please install wget first.")
            self.finished_signal.emit(False)
            return

        self.log_signal.emit("[INFO] Installing AeNux from download...")
        self.progress_signal.emit(10)

        if self._is_cancelled:
            self._cleanup_partial_install(temp_zip_path, extract_path)
            self.cancelled.emit()
            return

        self.log_signal.emit("[DEBUG] Downloading AeNux package, around 1.3gb...")

        # Use Popen to allow real-time output reading for progress
        process = subprocess.Popen([
            'wget', '--progress=bar:force', '-O', str(temp_zip_path),
            AE_NUX_DOWNLOAD_URL
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

        # Read output in real-time
        for line in iter(process.stdout.readline, ''):
            if self._is_cancelled:
                process.terminate()
                self._cleanup_partial_install(temp_zip_path, extract_path)
                self.cancelled.emit()
                return
            self.log_signal.emit(f"[WGET] {line.strip()}")

        process.stdout.close()
        process.wait()

        if process.returncode != 0:
            self.log_signal.emit("[ERROR] Download failed")
            self.finished_signal.emit(False)
            return

        self.log_signal.emit("[DEBUG] Download completed successfully")

    def _extract_and_install(self, temp_zip_path: Path, extract_path: Path) -> None:
        """
        Extract the downloaded zip and install files.
        """
        self.progress_signal.emit(40)

        if self._is_cancelled:
            self._cleanup_partial_install(temp_zip_path, extract_path)
            self.cancelled.emit()
            return

        self.log_signal.emit("[DEBUG] Extracting files...")
        result = subprocess.run([
            'unzip', '-o', str(temp_zip_path), '-d', str(extract_path)
        ], capture_output=True, text=True)

        if self._is_cancelled:
            self._cleanup_partial_install(temp_zip_path, extract_path)
            self.cancelled.emit()
            return

        if result.returncode != 0:
            self.log_signal.emit(f"[ERROR] Extraction failed: {result.stderr}")
            self.finished_signal.emit(False)
            return

        self.log_signal.emit("[DEBUG] Extraction completed")
        self.progress_signal.emit(60)

        self.log_signal.emit("[DEBUG] Cleaning up temporary files...")
        if temp_zip_path.exists():
            temp_zip_path.unlink()

        if self._is_cancelled:
            self._cleanup_partial_install(temp_zip_path, extract_path)
            self.cancelled.emit()
            return

        install_path = Path(AE_NUX_DIR)
        self.log_signal.emit(f"[DEBUG] Creating directory: {install_path}")
        install_path.mkdir(parents=True, exist_ok=True)
        self.progress_signal.emit(70)

        source_dir = extract_path / 'Support Files'
        if source_dir.exists():
            self.log_signal.emit("[DEBUG] Copying files to installation directory...")

            for item in source_dir.iterdir():
                if self._is_cancelled:
                    self._cleanup_partial_install(temp_zip_path, extract_path)
                    self.cancelled.emit()
                    return

                dst_path = install_path / item.name

                if item.is_dir():
                    shutil.copytree(item, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst_path)

            self.log_signal.emit("[DEBUG] Files copied successfully")
            self.progress_signal.emit(90)
        else:
            self.log_signal.emit(f"[ERROR] Source directory '{source_dir}' not found after extraction")
            self.finished_signal.emit(False)
            return

    def _finalize_installation(self, extract_path: Path) -> None:
        """
        Finalize the installation by cleaning up and signaling completion.
        """
        if self._is_cancelled:
            self.cancelled.emit()
            return

        self.log_signal.emit("[DEBUG] Final cleanup...")
        if extract_path.exists():
            shutil.rmtree(extract_path)

        self.progress_signal.emit(100)
        self.log_signal.emit("[INFO] AeNux installation completed successfully!")
        self.finished_signal.emit(True)

    def _cleanup_partial_install(self, zip_file: Path, extract_dir: Path) -> None:
        """
        Clean up partially installed files.

        Args:
            zip_file: Path to the temporary zip file.
            extract_dir: Path to the extraction directory.
        """
        self.log_signal.emit("[CANCEL] Cleaning up partially installed files...")

        if zip_file.exists():
            zip_file.unlink()
            self.log_signal.emit("[CANCEL] Removed downloaded zip file")

        if extract_dir.exists():
            shutil.rmtree(extract_dir)
            self.log_signal.emit("[CANCEL] Removed extraction directory")

        install_path = Path(AE_NUX_DIR)
        if install_path.exists():
            try:
                if len(list(install_path.iterdir())) < 5:
                    shutil.rmtree(install_path)
                    self.log_signal.emit("[CANCEL] Removed partially installed AeNux directory")
            except OSError:
                pass
