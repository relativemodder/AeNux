import os
import shutil
import subprocess
import threading
from typing import Optional, List
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    PLUGIN_DIR, PRESET_DIR, PLUGIN_DOWNLOAD_URL,
    PLUGIN_ZIP_TEMP_NAME
)

class PluginThread(QThread):
    """
    QThread subclass for handling plugin installation process.

    This thread manages the download, extraction, and installation of plugins
    for a Wine-based environment, providing progress updates and logging.
    """
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    cancelled = pyqtSignal()

    def __init__(self, runner_path: str, wineprefix_path: str, zip_file_path: Optional[str] = None):
        """
        Initialize the PluginThread.

        Args:
            runner_path: Path to the Wine runner directory.
            wineprefix_path: Path to the Wine prefix.
            zip_file_path: Optional path to a local zip file for installation.
        """
        super().__init__()
        self.runner_path = runner_path
        self.wineprefix_path = wineprefix_path
        self._is_cancelled = False
        self.zip_file_path = zip_file_path
        self.is_local_file = zip_file_path is not None

        self.REQUIRED_FOLDERS = ["aex", "CEP", "installer", "preset-backup", "scripts"]

    def cancel(self) -> None:
        """Cancel the ongoing operation."""
        self._is_cancelled = True

    def _run_subprocess_with_logging(self, cmd: List[str], env: Optional[dict] = None) -> bool:
        """
        Run a subprocess command and stream its output to log_signal.

        Args:
            cmd: List of command arguments.
            env: Optional environment variables.

        Returns:
            True if successful, False otherwise.
        """
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            for line in iter(process.stdout.readline, ''):
                if self._is_cancelled:
                    process.terminate()
                    return False
                if line.strip():
                    self.log_signal.emit(f"[SUBPROCESS] {line.strip()}")
            process.stdout.close()
            return process.wait() == 0
        except Exception as e:
            self.log_signal.emit(f"[ERROR] Subprocess failed: {str(e)}")
            return False

    def run(self) -> None:
        """
        Execute the plugin installation process.

        This method orchestrates the entire installation workflow, including
        setup, download/extraction, and component installation.
        """
        try:
            self.log_signal.emit("[INFO] Starting plugin installation...")
            self.progress_signal.emit(10)

            if self._is_cancelled:
                self._cleanup_leftovers()
                self.cancelled.emit()
                return

            if not self._setup_environment():
                self.finished_signal.emit(False)
                return

            self.progress_signal.emit(20)

            zip_file_path = PLUGIN_ZIP_TEMP_NAME

            if not self._prepare_plugin_zip(zip_file_path):
                self.finished_signal.emit(False)
                return

            if not self._extract_plugin(zip_file_path):
                self.finished_signal.emit(False)
                return

            self.progress_signal.emit(50)

            if not self._install_components():
                self.finished_signal.emit(False)
                return

            self.progress_signal.emit(90)

            self._cleanup_leftovers()

            self.progress_signal.emit(100)
            self.log_signal.emit("[INFO] Plugin installation completed successfully!")
            self.finished_signal.emit(True)

        except Exception as e:
            self._cleanup_leftovers()
            self.log_signal.emit(f"[ERROR] Plugin installation failed: {str(e)}")
            self.finished_signal.emit(False)

    def _setup_environment(self) -> bool:
        """
        Set up the environment for plugin installation.

        Checks for Wine existence and installs zenity if needed.

        Returns:
            True if setup successful, False otherwise.
        """
        env = os.environ.copy()
        env['WINEPREFIX'] = self.wineprefix_path
        wine_path = os.path.join(self.runner_path, "bin", "wine")

        if not os.path.exists(wine_path):
            self.log_signal.emit(f"[ERROR] Wine not found at: {wine_path}")
            return False

        if not shutil.which('zenity'):
            self.log_signal.emit("[INFO] Attempting to install zenity...")
            if not self._run_subprocess_with_logging(['sudo', 'apt', 'install', 'zenity', '-y']):
                self.log_signal.emit("[WARNING] Failed to install zenity, proceeding...")

        return True

    def _prepare_plugin_zip(self, zip_file_path: str) -> bool:
        """
        Prepare the plugin zip file, either by copying local file or downloading.

        Args:
            zip_file_path: Path where the zip file should be placed.

        Returns:
            True if preparation successful, False otherwise.
        """
        if self.is_local_file:
            self.log_signal.emit(f"[INFO] Using local plugin file: {self.zip_file_path}")
            if not os.path.exists(self.zip_file_path):
                self.log_signal.emit(f"[ERROR] Local file not found: {self.zip_file_path}")
                return False
            shutil.copy2(self.zip_file_path, zip_file_path)
            return True
        else:
            missing_folders = [folder for folder in self.REQUIRED_FOLDERS if not os.path.exists(folder)]

            if missing_folders:
                self.log_signal.emit(f"[INFO] Missing folders: {missing_folders}, downloading plugin package...")
                self.progress_signal.emit(30)

                if not shutil.which('wget'):
                    self.log_signal.emit("[ERROR] wget is not installed. Please install wget first.")
                    return False

                # Use streaming wget to log progress
                if not self._run_subprocess_with_logging(['wget', '-O', zip_file_path, PLUGIN_DOWNLOAD_URL]):
                    self.log_signal.emit("[ERROR] Download failed")
                    return False
            else:
                self.log_signal.emit("[INFO] All required plugin folders found, skipping download...")

            return True

    def _extract_plugin(self, zip_file_path: str) -> bool:
        """
        Extract the plugin zip file.

        Args:
            zip_file_path: Path to the zip file to extract.

        Returns:
            True if extraction successful, False otherwise.
        """
        if os.path.exists(zip_file_path):
            self.log_signal.emit("[DEBUG] Extracting plugin package...")
            if not self._run_subprocess_with_logging(['unzip', '-o', zip_file_path]):
                self.log_signal.emit("[ERROR] Extraction failed")
                return False

            self.log_signal.emit("[INFO] Plugin package extracted successfully")
            os.remove(zip_file_path)
            self.log_signal.emit("[DEBUG] Removed zip file")
        return True

    def _install_components(self) -> bool:
        """
        Install the various plugin components (AEX, CEP, presets, installers).

        Returns:
            True if installation successful, False otherwise.
        """
        wine_drive_c_progfiles_x86 = os.path.join(self.wineprefix_path, "drive_c", "Program Files (x86)")
        cep_dst = os.path.join(wine_drive_c_progfiles_x86, "Common Files", "Adobe", "CEP", "extensions")
        env = os.environ.copy()
        env['WINEPREFIX'] = self.wineprefix_path
        wine_path = os.path.join(self.runner_path, "bin", "wine")

        # Install AEX
        self.log_signal.emit("[INFO] Installing AEX plugins...")
        self._copy_files("aex", PLUGIN_DIR, dirs_exist_ok=True)
        self.log_signal.emit("[INFO] AEX plugins installed successfully")
        self.progress_signal.emit(60)

        # Install CEP
        self.log_signal.emit("[INFO] Installing CEP extension...")
        reg_file = os.path.join("CEP", "AddKeys.reg")
        if os.path.exists(reg_file):
            if self._run_subprocess_with_logging([wine_path, "regedit", reg_file], env=env):
                self.log_signal.emit("[INFO] CEP registry keys imported")
            else:
                self.log_signal.emit("[WARNING] CEP registry import failed")

        self._copy_files("CEP/flowv1.4.2", os.path.join(cep_dst, "flowv1.4.2"), is_single_dir=True)
        self.log_signal.emit("[INFO] CEP extension installed successfully")
        self.progress_signal.emit(70)

        # Install presets
        self.log_signal.emit("[INFO] Installing presets...")
        self._copy_files("preset-backup", PRESET_DIR, dirs_exist_ok=True)
        self.log_signal.emit("[INFO] Presets installed successfully")
        self.progress_signal.emit(80)

        # Run installers
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
                        return False

                    self.log_signal.emit(f"[INFO] Installing: {exe}")
                    # Use streaming for installers too
                    if not self._run_subprocess_with_logging([wine_path, exe, '/verysilent', '/suppressmsgboxes'], env=env):
                        self.log_signal.emit(f"[WARNING] Installation of {exe} may have failed")

            for exe in ['E3D.exe', 'saber.exe']:
                if os.path.exists(exe):
                    self.log_signal.emit(f"[INFO] Please manually install: {exe}")
                    # For manual ones, run without streaming as they are interactive
                    subprocess.run([wine_path, exe], env=env)

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

        return True

    def _copy_files(self, src_path: str, dst_path: str, dirs_exist_ok: bool = False, is_single_dir: bool = False) -> None:
        """
        Helper to copy files/directories with cancellation check.

        Args:
            src_path: Source path to copy from.
            dst_path: Destination path to copy to.
            dirs_exist_ok: Whether to allow overwriting existing directories.
            is_single_dir: Whether src_path is a single directory to copy entirely.
        """
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

    def _cleanup_leftovers(self) -> None:
        """Clean up leftover files and directories."""
        try:
            self.log_signal.emit("[INFO] Cleaning up temporary files...")

            for folder in self.REQUIRED_FOLDERS:
                if os.path.exists(folder):
                    shutil.rmtree(folder)
                    self.log_signal.emit(f"[CLEAN] Removed {folder} folder")

        except Exception as e:
            self.log_signal.emit(f"[WARNING] Cleanup failed: {str(e)}")
