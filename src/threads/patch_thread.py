import os
import shutil
import subprocess
import glob
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    AE_NUX_DIR, WINETRICKS_PATH,
    BASE_DIR, AENUX_COLORS_REG_CONTENT
)


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

    def cancel(self):
        self._is_cancelled = True

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

            # Run winetricks
            self.log_signal.emit("[DEBUG] Running winetricks...")
            subprocess.run([WINETRICKS_PATH, "-q", "dxvk", "corefonts", "gdiplus", "fontsmooth=rgb"], env=env)
            
            vcr_bat = os.path.join(BASE_DIR, "asset", "vcr", "install_all.bat")
            if os.path.exists(vcr_bat):
                self.log_signal.emit("[DEBUG] Installing VCR dependencies...")
                subprocess.run([wine_path, vcr_bat], env=env)
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
                    if os.path.exists(link_path):
                        os.remove(link_path)
                    os.symlink(os.path.join(home_dir, folder), os.path.join(target_fav_dir, folder))

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
            system32_dir = os.path.join(wine_drive_c, "windows", "system32")
            msxml3_src = os.path.join(BASE_DIR, "asset", "System32", "msxml3.dll")

            if os.path.exists(system32_dir) and os.path.exists(msxml3_src):
                shutil.copy2(msxml3_src, os.path.join(system32_dir, "msxml3.dll"))
                shutil.copy2(msxml3_src, os.path.join(system32_dir, "msxml3r.dll"))
                
                subprocess.run([wine_path, "reg", "add", "HKCU\\Software\\Wine\\DllOverrides", 
                              "/v", "msxml3", "/d", "native,builtin", "/f"], env=env)
            else:
                self.log_signal.emit("[WARNING] msxml3.dll not found or System32 not available, skipping DLL override...")

            self.progress_signal.emit(100)
            self.log_signal.emit("[INFO] AeNux patch applied successfully!")
            self.finished_signal.emit(True)
            
        except Exception as e:
            self.log_signal.emit(f"[ERROR] Patch application failed: {str(e)}")
            self.finished_signal.emit(False)
