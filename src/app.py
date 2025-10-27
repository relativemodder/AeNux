# app.py

import os
import subprocess
import json
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QCheckBox, QMessageBox, QProgressBar, QFileDialog
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer

from config import (
    CONFIG_PATH, AE_NUX_DIR, WINE_PREFIX_DIR, PLUGIN_DIR, PRESET_DIR, 
    ICON_PATH, RUNNER_BASE_DIR
)
from threads import InstallThread, PatchThread, PluginThread


class AeNuxApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeNux Halloween Edition")
        self.resize(520, 350)
        self.config = self._load_config()
        
        # Thread references
        self.install_thread = None
        self.patch_thread = None
        self.plugin_thread = None
        
        # UI state variables
        self.buttons_disabled = False
        self.button_cooldown_timer = QTimer()
        self.button_cooldown_timer.setSingleShot(True)
        self.button_cooldown_timer.timeout.connect(self._enable_buttons)
        
        # Save reference to main buttons for easy state management
        self.main_buttons = []

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self._setup_ui()
        
        # Initial setup calls
        self._populate_runner_dropdown()
        self.runner_dropdown.currentIndexChanged.connect(self._runner_changed)

        self._apply_saved_config()
        self._check_installation_status()
        self._check_runner_support()

    def _setup_ui(self):
        """Sets up the layout and widgets."""
        root = QVBoxLayout(self)
        
        # --- Status Row ---
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Checking...")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self._install_aenux)
        status_row.addWidget(self.install_button)
        self.main_buttons.append(self.install_button)
        
        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.clicked.connect(self._uninstall_aenux)
        self.uninstall_button.hide()
        status_row.addWidget(self.uninstall_button)
        self.main_buttons.append(self.uninstall_button)
        root.addLayout(status_row)

        # --- Logs ---
        root.addWidget(QLabel("Logs:"))
        self.logs_box = QTextEdit()
        self.logs_box.setReadOnly(True)
        self.logs_box.setFixedHeight(140)
        root.addWidget(self.logs_box)

        # --- Progress Bar with Cancel button ---
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        progress_layout.addWidget(self.progress_bar)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_operation)
        self.cancel_button.setStyleSheet("QPushButton { background-color: #ff6b6b; color: white; }")
        progress_layout.addWidget(self.cancel_button)
        self.main_buttons.append(self.cancel_button)
        
        root.addLayout(progress_layout)

        # --- Runner row ---
        runner_row = QHBoxLayout()
        runner_row.addWidget(QLabel("Runner:"))
        self.runner_dropdown = QComboBox()
        runner_row.addWidget(self.runner_dropdown)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh_runner_list)
        runner_row.addWidget(self.btn_refresh)
        self.main_buttons.append(self.btn_refresh)
        
        root.addLayout(runner_row)

        # --- Checkboxes and Plugin button ---
        cb_row = QHBoxLayout()
        
        self.btn_install_plugin = QPushButton("Install Plugin")
        self.btn_install_plugin.clicked.connect(self._install_plugin)
        self.btn_install_plugin.setEnabled(False)
        cb_row.addWidget(self.btn_install_plugin)
        self.main_buttons.append(self.btn_install_plugin)
        
        root.addLayout(cb_row)

        # --- Execution buttons ---
        exec_row = QHBoxLayout()
        self.btn_run = QPushButton("Run AfterFX")
        self.btn_kill = QPushButton("Kill AfterFX")
        self.btn_run.clicked.connect(self._run_aenux)
        self.btn_kill.clicked.connect(self._kill_aenux)
        exec_row.addWidget(self.btn_run)
        exec_row.addWidget(self.btn_kill)
        self.main_buttons.extend([self.btn_run, self.btn_kill])
        root.addLayout(exec_row)

        # --- Folders ---
        folder_row = QHBoxLayout()
        self.folder_buttons = []
        for name in ["Runner", "Plugin", "Preset", "Wineprefix"]:
            btn = QPushButton(f"{name} Folder")
            btn.clicked.connect(lambda checked, n=name.lower(): self._open_folder(n))
            folder_row.addWidget(btn)
            self.folder_buttons.append(btn)
        self.main_buttons.extend(self.folder_buttons)
        root.addLayout(folder_row)

        # --- Footer ---
        footer = QLabel('Made with 🎃 by cutefishaep')
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    # --- UI State Management Methods ---

    def _disable_buttons_temporarily(self, duration=1500):
        """Temporarily disable all main buttons"""
        if self.buttons_disabled:
            return
            
        self.buttons_disabled = True
        for button in self.main_buttons:
            button.setEnabled(False)
        
        # Also disable dropdown and checkbox
        self.runner_dropdown.setEnabled(False)
        
        self.button_cooldown_timer.start(duration)

    def _enable_buttons(self):
        """Re-enable all buttons"""
        self.buttons_disabled = False
        for button in self.main_buttons:
            button.setEnabled(True)
        
        # Re-enable dropdown and update states based on current context
        self.runner_dropdown.setEnabled(True)
        self._check_runner_support()
        self._check_installation_status()

    def _check_installation_status(self):
        """Check if AeNux is installed and update UI accordingly"""
        is_installed = False
        if os.path.exists(AE_NUX_DIR):
            try:
                # Check for non-hidden files to confirm a proper install
                contents = [f for f in os.listdir(AE_NUX_DIR) if not f.startswith('.')]
                if contents:
                    is_installed = True
            except OSError:
                pass
        
        if is_installed:
            self.status_label.setText("AeNux **installed**")
            self.install_button.hide()
            self.uninstall_button.show()
            # Only enable plugin button if the runner is supported
            self.btn_install_plugin.setEnabled(not self._is_proton_runner())
            self.logs_box.append("[STATUS] AeNux is installed and ready to use.")
        else:
            self.status_label.setText("AeNux is **not installed**")
            self.install_button.show()
            self.uninstall_button.hide()
            self.btn_install_plugin.setEnabled(False)

    def _is_proton_runner(self):
        """Helper to check if the current runner is Proton"""
        runner = self.runner_dropdown.currentText()
        return "proton" in runner.lower()

    def _load_config(self):
        """Load configuration from JSON file."""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_config(self):
        """Save current configuration to JSON file."""
        config = {
            "runner": self.runner_dropdown.currentText()
        }
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def _apply_saved_config(self):
        """Set UI elements based on loaded config."""
        if "runner" in self.config:
            idx = self.runner_dropdown.findText(self.config["runner"])
            if idx >= 0:
                self.runner_dropdown.setCurrentIndex(idx)

    def _populate_runner_dropdown(self):
        """Populate the dropdown with runners found in the runner directory."""
        self.runner_dropdown.clear()
        self.runner_dropdown.addItem("Select your runner")
        try:
            dirs = [d for d in os.listdir(RUNNER_BASE_DIR) if os.path.isdir(os.path.join(RUNNER_BASE_DIR, d))]
            if dirs:
                self.runner_dropdown.addItems(dirs)
            else:
                self.runner_dropdown.addItem("No runners found")
        except FileNotFoundError:
            self.runner_dropdown.addItem("No runners found")

    def _runner_changed(self, index):
        """Handle runner selection change."""
        runner = self.runner_dropdown.currentText()
        self._check_runner_support()
        
        if not runner.lower().startswith("select") and runner.lower() != "no runners found":
            self.logs_box.append(f"[INFO] Selected runner: {runner}")
        
        self._save_config()

    def _check_runner_support(self):
        """Disable buttons if the selected runner is Proton."""
        is_proton = self._is_proton_runner()
        
        self.btn_run.setEnabled(not is_proton)
        self.btn_kill.setEnabled(not is_proton)
        
        self.btn_install_plugin.setEnabled(os.path.exists(AE_NUX_DIR) and not is_proton)
        
        if is_proton:
            self.logs_box.append("[ERROR] Proton is not supported! Please select a Wine runner.")


    def _show_install_method_dialog(self, title, message):
        """Show dialog to choose installation method (Download/Local File/Cancel)."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        
        download_btn = dialog.addButton("Download", QMessageBox.ButtonRole.AcceptRole)
        choose_file_btn = dialog.addButton("Choose Local File", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        
        dialog.exec()
        
        clicked_button = dialog.clickedButton()
        
        if clicked_button == download_btn:
            return "download"
        elif clicked_button == choose_file_btn:
            return "local_file"
        else:
            return "cancel"

    def _choose_local_zip_file(self, file_type="AeNux"):
        """Open file dialog to choose local zip file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {file_type} Zip File",
            "",
            "Zip Files (*.zip);;All Files (*)"
        )
        return file_path

    # --- Operation Execution Methods ---

    def _install_aenux(self):
        """Initiate the AeNux installation process."""
        if self.buttons_disabled: return
        if self.install_thread and self.install_thread.isRunning():
            self.logs_box.append("[INFO] Installation already in progress...")
            return

        if QMessageBox.question(self, "Confirm Installation", f"This will install AeNux to **{AE_NUX_DIR}**. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            
            method = self._show_install_method_dialog("Installation Method", "How would you like to install AeNux?")
            
            if method == "cancel":
                self.logs_box.append("[USER] Installation cancelled.")
                return
            
            zip_file_path = None
            if method == "local_file":
                zip_file_path = self._choose_local_zip_file("AeNux")
                if not zip_file_path:
                    self.logs_box.append("[USER] No file selected. Installation cancelled.")
                    return

            self._disable_buttons_temporarily(500)
            self.install_button.setEnabled(False)
            self.install_button.setText("Installing...")
            self.progress_bar.setVisible(True)
            self.cancel_button.setVisible(True)
            self.progress_bar.setValue(0)
            
            if zip_file_path: self.logs_box.append(f"[INFO] Using local file: {zip_file_path}")
            
            self.install_thread = InstallThread(zip_file_path)
            self.install_thread.log_signal.connect(self.logs_box.append)
            self.install_thread.progress_signal.connect(self.progress_bar.setValue)
            self.install_thread.finished_signal.connect(self._installation_finished)
            self.install_thread.cancelled.connect(self._installation_cancelled)
            self.install_thread.start()

    def _installation_finished(self, success):
        """Handle installation completion."""
        self._enable_buttons() # Re-enables all buttons
        self.install_button.setText("Install")
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        
        if success:
            self._create_shortcut()
            self._check_installation_status() # Update status and plugin button
        else:
            self.logs_box.append("[ERROR] Installation failed. Please check the logs above.")

    def _installation_cancelled(self):
        """Handle installation cancellation."""
        self._enable_buttons()
        self.install_button.setText("Install")
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.logs_box.append("[INFO] Installation was cancelled and cleaned up.")

    def _uninstall_aenux(self):
        """Uninstall AeNux and all its associated data."""
        if self.buttons_disabled: return
            
        reply = QMessageBox.question(self, "Confirm Uninstall",
                                     "This will remove **AeNux, Wineprefix, and shortcuts**. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self._disable_buttons_temporarily(2000)
            try:
                for path, name in [(AE_NUX_DIR, "AeNux directory"), (WINE_PREFIX_DIR, "Wineprefix")]:
                    if os.path.exists(path):
                        shutil.rmtree(path)
                        self.logs_box.append(f"[UNINSTALL] {name} removed.")
                
                self._remove_shortcut()
                self.logs_box.clear()
                self._check_installation_status()
                self.logs_box.append("[UNINSTALL] AeNux has been completely uninstalled.")
                
            except Exception as e:
                self.logs_box.append(f"[ERROR] Uninstall failed: {str(e)}")
                QMessageBox.critical(self, "Uninstall Error", f"Failed to uninstall AeNux: {str(e)}")

    def _install_plugin(self):
        """Initiate the plugin installation process."""
        if self.buttons_disabled: return
        if not os.path.exists(AE_NUX_DIR) or self._is_proton_runner():
            QMessageBox.warning(self, "Error", "AeNux must be installed and a non-Proton runner selected.")
            return

        method = self._show_install_method_dialog("Plugin Installation Method", "How would you like to install plugins?")
        
        if method == "cancel": return
        
        zip_file_path = None
        if method == "local_file":
            zip_file_path = self._choose_local_zip_file("Plugin")
            if not zip_file_path: return

        if QMessageBox.question(self, "Confirm Plugin Installation",
                                "This will install additional plugins. Continue?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            
            self._disable_buttons_temporarily(500)
            self.btn_install_plugin.setEnabled(False)
            self.btn_install_plugin.setText("Installing...")
            self.progress_bar.setVisible(True)
            self.cancel_button.setVisible(True)
            self.progress_bar.setValue(0)
            
            runner = self.runner_dropdown.currentText()
            runner_path = os.path.join(RUNNER_BASE_DIR, runner)
            
            self.plugin_thread = PluginThread(runner_path, WINE_PREFIX_DIR, zip_file_path)
            self.plugin_thread.log_signal.connect(self.logs_box.append)
            self.plugin_thread.progress_signal.connect(self.progress_bar.setValue)
            self.plugin_thread.finished_signal.connect(self._plugin_installation_finished)
            self.plugin_thread.cancelled.connect(self._plugin_installation_cancelled)
            self.plugin_thread.start()

    def _plugin_installation_finished(self, success):
        """Handle plugin installation completion."""
        self._enable_buttons()
        self.btn_install_plugin.setText("Install Plugin")
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        
        if success:
            self.logs_box.append("[INFO] Plugin installation completed successfully!")
        else:
            self.logs_box.append("[ERROR] Plugin installation failed. Please check the logs above.")

    def _plugin_installation_cancelled(self):
        """Handle plugin installation cancellation."""
        self._enable_buttons()
        self.btn_install_plugin.setText("Install Plugin")
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.logs_box.append("[INFO] Plugin installation was cancelled.")

    def _run_aenux(self):
        """Run AeNux with optional patch application."""
        if self.buttons_disabled: return
        if not os.path.exists(AE_NUX_DIR) or self._is_proton_runner():
            QMessageBox.warning(self, "Error", "AeNux must be installed and a non-Proton runner selected.")
            return

        runner = self.runner_dropdown.currentText()
        runner_path = os.path.join(RUNNER_BASE_DIR, runner)
        afterfx_path = os.path.join(AE_NUX_DIR, "AfterFX.exe")

        if not os.path.exists(afterfx_path):
            QMessageBox.warning(self, "AfterFX Not Found", f"AfterFX.exe not found at: {afterfx_path}")
            return
        
        os.makedirs(WINE_PREFIX_DIR, exist_ok=True)

        self._disable_buttons_temporarily(1000)
        self.logs_box.append("[INFO] Applying AeNux patch before running...")
        self.progress_bar.setVisible(True)
        self.cancel_button.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.patch_thread = PatchThread(runner_path, WINE_PREFIX_DIR)
        self.patch_thread.log_signal.connect(self.logs_box.append)
        self.patch_thread.progress_signal.connect(self.progress_bar.setValue)
        self.patch_thread.finished_signal.connect(lambda success: self._patch_finished(success, runner_path, WINE_PREFIX_DIR, afterfx_path))
        self.patch_thread.cancelled.connect(self._patch_cancelled)
        self.patch_thread.start()

    def _patch_finished(self, success, runner_path, wineprefix_path, afterfx_path):
        """Handle patch completion and proceed to run AfterFX if successful."""
        self._enable_buttons()
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        
        if success:
            self.logs_box.append("[INFO] Patch applied successfully, now running AfterFX...")
            self._run_afterfx(runner_path, wineprefix_path, afterfx_path)
        else:
            self.logs_box.append("[ERROR] Patch failed. AfterFX will not be run.")

    def _patch_cancelled(self):
        """Handle patch cancellation."""
        self._enable_buttons()
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.logs_box.append("[INFO] Patch application was cancelled.")

    def _run_afterfx(self, runner_path, wineprefix_path, afterfx_path):
        """Execute AfterFX.exe using the selected Wine runner."""
        try:
            wine_path = os.path.join(runner_path, "bin", "wine")
            env = os.environ.copy()
            env['WINEPREFIX'] = wineprefix_path
            
            self.logs_box.append(f"[RUN] Starting AfterFX.exe with {os.path.basename(runner_path)}...")
            
            # Start the process without waiting
            subprocess.Popen([wine_path, afterfx_path], env=env)
            self.logs_box.append("[RUN] AfterFX started with Wine.")
                
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to run AfterFX: {str(e)}")
            QMessageBox.critical(self, "Execution Error", f"Failed to run AfterFX: {str(e)}")

    def _kill_aenux(self):
        """Kill Wine and AfterFX processes."""
        if self.buttons_disabled: return
            
        self._disable_buttons_temporarily(1000)
        try:
            # Kill processes by name
            for proc in ["AfterFX.exe", "wine", "wineserver"]:
                subprocess.run(["pkill", "-f", proc], check=False, stderr=subprocess.DEVNULL)
            self.logs_box.append("[KILL] AeNux processes terminated.")
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to kill processes: {str(e)}")

    def _cancel_operation(self):
        """Cancel the currently running thread."""
        if self.buttons_disabled: return
            
        self._disable_buttons_temporarily(1000)
        
        thread_to_cancel = self.install_thread or self.patch_thread or self.plugin_thread
        thread_name = ""
        if self.install_thread and self.install_thread.isRunning(): thread_name = "installation"
        elif self.patch_thread and self.patch_thread.isRunning(): thread_name = "patch application"
        elif self.plugin_thread and self.plugin_thread.isRunning(): thread_name = "plugin installation"

        if thread_to_cancel:
            if QMessageBox.question(self, "Confirm Cancel", 
                                    f"Are you sure you want to cancel the {thread_name}?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                thread_to_cancel.cancel()
                self.logs_box.append(f"[USER] {thread_name.capitalize()} cancelled by user.")
                self.cancel_button.setVisible(False)
                self.progress_bar.setVisible(False)

    def _create_shortcut(self):
        """Create desktop shortcut and icon for the application loader."""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            icons_dir = os.path.expanduser("~/.local/share/icons")
            os.makedirs(icons_dir, exist_ok=True)
            shutil.copy2(ICON_PATH, os.path.join(icons_dir, "AeNux.png"))
            self.logs_box.append("[SHORTCUT] Icon copied successfully.")
            
            applications_dir = os.path.expanduser("~/.local/share/applications")
            os.makedirs(applications_dir, exist_ok=True)
            desktop_file = os.path.join(applications_dir, "AeNux.desktop")
            run_script = os.path.join(current_dir, "app.py")
            
            venv_python = os.path.join(current_dir, "venv", "bin", "python")
            python_exec = venv_python if os.path.exists(venv_python) else "python3"
            if python_exec == "python3": self.logs_box.append("[INFO] Using system python instead of venv")
            
            desktop_content = f"""[Desktop Entry]
Name=AeNux Loader
Comment=Run AeNux using Wine
Exec={python_exec} {run_script}
Path={current_dir}
Type=Application
Icon=AeNux
Terminal=false
Categories=AudioVideo;Video;
"""
            with open(desktop_file, 'w') as f:
                f.write(desktop_content)
            
            os.chmod(desktop_file, 0o755)
            subprocess.run(["update-desktop-database", applications_dir], capture_output=True)
            
            self.logs_box.append("[SHORTCUT] Desktop shortcut created successfully.")
            return True
            
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to create shortcut: {str(e)}")
            return False

    def _remove_shortcut(self):
        """Remove desktop shortcut and icon."""
        try:
            for path in [os.path.expanduser("~/.local/share/icons/AeNux.png"),
                         os.path.expanduser("~/.local/share/applications/AeNux.desktop")]:
                if os.path.exists(path):
                    os.remove(path)
                    self.logs_box.append(f"[SHORTCUT] Removed {os.path.basename(path)}.")
            
            applications_dir = os.path.expanduser("~/.local/share/applications")
            subprocess.run(["update-desktop-database", applications_dir], capture_output=True)
            return True
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to remove shortcut: {str(e)}")
            return False
        
    def _refresh_runner_list(self):
        """Refresh the list of available runners."""
        if self.buttons_disabled: return
            
        self._disable_buttons_temporarily(1000)
        self.logs_box.append("[INFO] Refreshing runner list...")
        self._populate_runner_dropdown()
        self._check_runner_support()

    def _open_folder(self, name):
        """Open the specified folder in the default file manager."""
        if self.buttons_disabled: return
            
        self._disable_buttons_temporarily(1000)
        
        path_map = {
            "wineprefix": WINE_PREFIX_DIR,
            "runner": RUNNER_BASE_DIR,
            "plugin": PLUGIN_DIR,
            "preset": PRESET_DIR,
        }
        
        path = path_map.get(name)
        
        if not path:
            self.logs_box.append(f"[ERROR] Unknown folder type: {name}")
            return

        if name in ["plugin", "preset"] and not os.path.exists(AE_NUX_DIR):
            QMessageBox.warning(self, "Not Installed", "You need to install AeNux first to open this folder.")
            return

        os.makedirs(path, exist_ok=True)

        try:
            subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to open folder: {str(e)}")
            QMessageBox.critical(self, "Error", f"Could not open folder: {path}")

        self.logs_box.append(f"[OPEN] {name} folder opened.")