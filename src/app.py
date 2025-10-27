import os
import subprocess
import json
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTextEdit, QCheckBox, QMessageBox, QProgressBar, QFileDialog,
    QSpacerItem, QSizePolicy
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer

from config import (
    CONFIG_PATH, AE_NUX_DIR, WINE_PREFIX_DIR, PLUGIN_DIR, PRESET_DIR, 
    ICON_PATH, RUNNER_BASE_DIR, PATCHED_FILE_FLAG
)
from threads import InstallThread, PatchThread, PluginThread


class AeNuxApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeNux")
        self.resize(520, 350)
        self.config = self._load_config()
        
        self.install_thread = None
        self.patch_thread = None
        self.plugin_thread = None
        
        self.buttons_disabled = False
        
        # Cooldown timer is kept only for quick, single-action buttons (like Kill)
        self.button_cooldown_timer = QTimer() 
        self.button_cooldown_timer.setSingleShot(True)
        self.button_cooldown_timer.timeout.connect(self._enable_buttons)
        
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
        
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.status_label = QLabel("Checking...")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        self.install_button = QPushButton("Install")
        self.install_button.clicked.connect(self._install_aenux)
        status_row.addWidget(self.install_button)
        self.main_buttons.append(self.install_button)

        self.install_button.setObjectName('install_button')
        self.install_button.setStyleSheet('#install_button { font-weight: bold; }')
        
        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.clicked.connect(self._uninstall_aenux)
        self.uninstall_button.hide()
        status_row.addWidget(self.uninstall_button)
        self.main_buttons.append(self.uninstall_button)
        root.addLayout(status_row)

        root.addWidget(QLabel("Logs:"))
        self.logs_box = QTextEdit()
        self.logs_box.setReadOnly(True)
        self.setStyleSheet("QTextEdit{padding: 10px;}")
        self.logs_box.setFixedHeight(140)
        root.addWidget(self.logs_box)

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

        runner_row = QHBoxLayout()
        runner_row.addWidget(QLabel("Runner:"))
        self.runner_dropdown = QComboBox()
        runner_row.addWidget(self.runner_dropdown)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh_runner_list)
        runner_row.addWidget(self.btn_refresh)
        self.main_buttons.append(self.btn_refresh)
        
        root.addLayout(runner_row)

        spacer_row = QSpacerItem(1, 30, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        root.addItem(spacer_row)

        exec_row = QHBoxLayout()
        self.btn_run = QPushButton("Patch first and run AfterFX")
        self.btn_run.setObjectName('btn_run')
        self.btn_run.setStyleSheet('#btn_run { font-weight: bold; }')

        self.btn_kill = QPushButton("Kill AfterFX")
        self.btn_run.clicked.connect(self._run_aenux)
        self.btn_kill.clicked.connect(self._kill_aenux)
        exec_row.addWidget(self.btn_run)
        exec_row.addWidget(self.btn_kill)
        self.main_buttons.extend([self.btn_run, self.btn_kill])
        root.addLayout(exec_row)

        cb_row = QHBoxLayout()
        
        self.btn_install_plugin = QPushButton("Install some plugins")
        self.btn_install_plugin.clicked.connect(self._install_plugin)
        self.btn_install_plugin.setEnabled(False)
        cb_row.addWidget(self.btn_install_plugin)
        self.main_buttons.append(self.btn_install_plugin)
        
        root.addLayout(cb_row)

        spacer_row = QSpacerItem(1, 30, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        root.addItem(spacer_row)

        fm_label = QLabel('AE Folder management')
        fm_label.setObjectName('fm_management_label')
        fm_label.setStyleSheet('#fm_management_label { margin-top: 10px; }')
        fm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(fm_label)

        folder_row = QHBoxLayout()
        self.folder_buttons = []
        for name in ["Runners", "Plugins", "Presets", "Wine Prefix"]:
            btn = QPushButton(f"{name}")
            btn.clicked.connect(lambda checked, n=name.lower(): self._open_folder(n))
            folder_row.addWidget(btn)
            self.folder_buttons.append(btn)
        self.main_buttons.extend(self.folder_buttons)
        root.addLayout(folder_row)

        footer = QLabel('Made with 🎃 by cutefishaep')
        footer.setObjectName('footer')
        footer.setStyleSheet('#footer { margin-top: 30px; }')
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(footer)

    def _disable_buttons_persistent(self):
        """Persistently disable all main buttons until a thread finishes/enables them."""
        if self.buttons_disabled:
            return
            
        self.buttons_disabled = True
        for button in self.main_buttons:
            button.setEnabled(False)
        
        self.runner_dropdown.setEnabled(False)

    def _disable_buttons_cooldown(self, duration=1500):
        """Temporarily disable buttons using the cooldown timer for quick actions."""
        if self.buttons_disabled:
            return
            
        self._disable_buttons_persistent()
        self.button_cooldown_timer.start(duration)

    def _enable_buttons(self):
        """Re-enable all buttons and reset the disabled flag."""
        if not self.buttons_disabled:
            return 
            
        self.buttons_disabled = False
        self._check_installation_status() 
        self._check_runner_support()
        self.runner_dropdown.setEnabled(True)

    def _update_progress(self, value):
        """Update progress bar and manage button state based on progress."""
        self.progress_bar.setValue(value)
        
        if value > 0 and value < 100:
            self._disable_buttons_persistent()
            
        if value == 100:
            self._enable_buttons()

    def _check_installation_status(self):
        """Check if AeNux is installed and update UI accordingly"""
        is_installed = False
        if os.path.exists(AE_NUX_DIR):
            try:
                contents = [f for f in os.listdir(AE_NUX_DIR) if not f.startswith('.')]
                if contents:
                    is_installed = True
            except OSError:
                pass
        
        if is_installed:
            self.status_label.setText("AeNux installed")
            self.install_button.hide()
            self.uninstall_button.show()
            self.btn_install_plugin.setEnabled(not self._is_proton_runner() and not self.buttons_disabled)
            
            # Check if buttons are currently disabled by an operation
            if not self.buttons_disabled:
                self.uninstall_button.setEnabled(True)
                
            self.logs_box.append("[STATUS] AeNux is installed and ready to use.")

            if os.path.exists(PATCHED_FILE_FLAG):
                self.btn_run.setText('Run AfterFX')
            else:
                self.btn_run.setText('Patch first and run AfterFX')
        else:
            self.status_label.setText("AeNux is not installed")
            self.install_button.show()
            self.uninstall_button.hide()
            self.btn_install_plugin.setEnabled(False)
            
            # Check if buttons are currently disabled by an operation
            if not self.buttons_disabled:
                self.install_button.setEnabled(True)


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
        """Disable buttons if the selected runner is Proton or if they are already persistently disabled."""
        is_proton = self._is_proton_runner()
        is_installed = os.path.exists(AE_NUX_DIR)
        
        # Only set enabled state if not currently disabled by a thread operation
        if not self.buttons_disabled:
            self.btn_run.setEnabled(is_installed and not is_proton)
            self.btn_kill.setEnabled(is_installed and not is_proton)
            self.btn_install_plugin.setEnabled(is_installed and not is_proton)
        else:
            # If persistently disabled, ensure they stay disabled until _enable_buttons is called
            self.btn_run.setEnabled(False)
            self.btn_kill.setEnabled(False)
            self.btn_install_plugin.setEnabled(False)
            

        if is_proton:
            self.logs_box.append("[ERROR] Proton is not fully supported! Please select a Wine runner for patch/plugin functions.")

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

    def _install_aenux(self):
        """Initiate the AeNux installation process."""
        if self.buttons_disabled: return
        if self.install_thread and self.install_thread.isRunning():
            self.logs_box.append("[INFO] Installation already in progress...")
            return

        if QMessageBox.question(self, "Confirm Installation", f"This will install AeNux to {AE_NUX_DIR}. Continue?",
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

            self._disable_buttons_persistent()
            self.install_button.setEnabled(False)
            self.install_button.setText("Installing...")
            self.progress_bar.setVisible(True)
            self.cancel_button.setVisible(True)
            self.progress_bar.setValue(0)
            
            if zip_file_path: self.logs_box.append(f"[INFO] Using local file: {zip_file_path}")
            
            self.install_thread = InstallThread(zip_file_path)
            self.install_thread.log_signal.connect(self.logs_box.append)
            self.install_thread.progress_signal.connect(self._update_progress) # Connect to progress handler
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
            reply = QMessageBox.question(self, "Create Shortcut",
                                     "Do you want to create AeNux shortcut?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
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
                                     "This will remove AeNux, Wineprefix, and shortcuts. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # --- Use Cooldown disable for this quick, single action ---
            self._disable_buttons_cooldown(2000) 
            try:
                for path, name in [(AE_NUX_DIR, "AeNux directory"), (WINE_PREFIX_DIR, "Wineprefix")]:
                    if os.path.exists(path):
                        shutil.rmtree(path)
                        self.logs_box.append(f"[UNINSTALL] {name} removed.")
                
                os.system(f"rm -rf ~/cutefishaep")
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
            
            self._disable_buttons_persistent()
            self.btn_install_plugin.setEnabled(False)
            self.btn_install_plugin.setText("Installing...")
            self.progress_bar.setVisible(True)
            self.cancel_button.setVisible(True)
            self.progress_bar.setValue(0)
            
            runner = self.runner_dropdown.currentText()
            runner_path = os.path.join(RUNNER_BASE_DIR, runner)
            
            self.plugin_thread = PluginThread(runner_path, WINE_PREFIX_DIR, zip_file_path)
            self.plugin_thread.log_signal.connect(self.logs_box.append)
            self.plugin_thread.progress_signal.connect(self._update_progress) # Connect to progress handler
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

        if not os.path.exists(PATCHED_FILE_FLAG):
            self._disable_buttons_persistent()
            self.logs_box.append("[INFO] Applying AeNux patch before running...")
            self.progress_bar.setVisible(True)
            self.cancel_button.setVisible(True)
            self.progress_bar.setValue(0)
            
            self.patch_thread = PatchThread(runner_path, WINE_PREFIX_DIR)
            self.patch_thread.log_signal.connect(self.logs_box.append)
            self.patch_thread.progress_signal.connect(self._update_progress) # Connect to progress handler
            self.patch_thread.finished_signal.connect(lambda success: self._patch_finished(success, runner_path, WINE_PREFIX_DIR, afterfx_path))
            self.patch_thread.cancelled.connect(self._patch_cancelled)
            self.patch_thread.start()
        else:
            self.logs_box.append("[INFO] Running AfterFX...") 
            self._run_afterfx(runner_path, WINE_PREFIX_DIR, afterfx_path)
            self._disable_buttons_cooldown(1000) # Short cooldown to prevent spamming the button

    def _patch_finished(self, success, runner_path, wineprefix_path, afterfx_path):
        """Handle patch completion and proceed to run AfterFX if successful."""
        self._enable_buttons()
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        
        if success:
            self.logs_box.append("[INFO] Patch applied successfully, now running AfterFX...")
            self._run_afterfx(runner_path, wineprefix_path, afterfx_path)
            self._disable_buttons_cooldown(1000)
            
            self.btn_run.setText('Run AfterFX')
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
            
            subprocess.Popen([wine_path, afterfx_path], env=env)
            self.logs_box.append("[RUN] AfterFX started with Wine.")
                
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to run AfterFX: {str(e)}")
            QMessageBox.critical(self, "Execution Error", f"Failed to run AfterFX: {str(e)}")
    
    def _kill_aenux(self):
        """Kill Wine and AfterFX processes."""
        if self.buttons_disabled: return
            
        self._disable_buttons_cooldown(1000) # Use cooldown disable
        try:
            # Kill processes by name
            for proc in ["AfterFX.exe", "wine", "wineserver"]:
                subprocess.run(["pkill", "-f", proc], check=False, stderr=subprocess.DEVNULL)
            self.logs_box.append("[KILL] AeNux processes terminated.")
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to kill processes: {str(e)}")

    def _cancel_operation(self):
        """Cancel the currently running thread."""
        if self.buttons_disabled: 
            # If buttons are disabled by a persistent operation, allow cancel
            pass
        
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
                # The thread's 'cancelled' signal handler will call _enable_buttons
                self.cancel_button.setVisible(False)
                self.progress_bar.setVisible(False)
                self._disable_buttons_cooldown(1000) # Cooldown after cancel press
            else:
                self._disable_buttons_cooldown(500) # Cooldown if cancel press was rejected

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
            
            venv_python = os.path.join(current_dir, ".venv", "bin", "python")
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
            
        self._disable_buttons_cooldown(1000) # Use cooldown disable
        self.logs_box.append("[INFO] Refreshing runner list...")
        self._populate_runner_dropdown()
        self._check_runner_support()

    def _open_folder(self, name):
        """Open the specified folder in the default file manager."""
        if self.buttons_disabled: return
            
        self._disable_buttons_cooldown(1000) # Use cooldown disable
        
        path_map = {
            "wine prefix": WINE_PREFIX_DIR,
            "runners": RUNNER_BASE_DIR,
            "plugins": PLUGIN_DIR,
            "presets": PRESET_DIR,
        }
        
        path = path_map.get(name)
        
        if not path:
            self.logs_box.append(f"[ERROR] Unknown folder type: {name}")
            return

        if name in ["plugins", "presets"] and not os.path.exists(AE_NUX_DIR):
            QMessageBox.warning(self, "Not Installed", "You need to install AeNux first to open this folder.")
            return

        os.makedirs(path, exist_ok=True)

        try:
            subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self.logs_box.append(f"[ERROR] Failed to open folder: {str(e)}")
            QMessageBox.critical(self, "Error", f"Could not open folder: {path}")

        self.logs_box.append(f"[OPEN] {name} folder opened.")
    
    def closeEvent(self, event):
        """
        Overrides the close event handler to ask for confirmation before closing.
        Checks for running threads and warns the user if an operation is active.
        """
        # Check for any running thread
        if (self.install_thread and self.install_thread.isRunning()) or \
           (self.patch_thread and self.patch_thread.isRunning()) or \
           (self.plugin_thread and self.plugin_thread.isRunning()):
            
            reply = QMessageBox.question(
                self, 'Operation in Progress',
                "An operation is currently running. Are you sure you want to exit? Cancelling may lead to an unstable state.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.install_thread and self.install_thread.isRunning():
                    self.install_thread.cancel()
                if self.patch_thread and self.patch_thread.isRunning():
                    self.patch_thread.cancel()
                if self.plugin_thread and self.plugin_thread.isRunning():
                    self.plugin_thread.cancel()
                event.accept()
            else:
                event.ignore()
                return

        reply = QMessageBox.question(
            self, 'Confirm Exit',
            "Are you sure you want to quit AeNux?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()