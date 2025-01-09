import requests
import threading
import subprocess
import os
import time

from modules.utils import get_main_folder


class Updater:
    """
    Handles checking for updates and applying them.
    """
    UPDATE_BASE_URL = "https://github.com/terrafirma2021/MAKCM_v2_files/raw/refs/heads/main/MAKCU.exe"
    DEFAULT_VERSION = "1.1"
    FIRMWARE_LEFT = "1.0"
    FIRMWARE_RIGHT = "1.0"

    def __init__(self, logger, config_manager):
        self.logger = logger
        self.config_manager = config_manager
        self.main_folder = get_main_folder()
        self.update_check_complete = threading.Event()
        self.is_offline = False

    def check_for_updates(self):
        """
        Checks if there is a newer version in config.json; if so, downloads and
        launches the new .exe. Always prints the main version changelog.
        """
        def task():
            try:
                # Ping github.com to check if online
                response = os.system("ping -n 1 github.com > nul 2>&1" if os.name == "nt" else "ping -c 1 github.com > /dev/null 2>&1")
                if response != 0:
                    self.logger.terminal_print("Offline mode detected. Skipping update checks.")
                    self.is_offline = True
                    self.update_check_complete.set()
                    return

                # Check if the configuration file is downloaded or available
                if not self.config_manager.download_complete.is_set():
                    self.logger.terminal_print("Config file not downloaded. Running in offline mode.")
                    self.is_offline = True
                    self.update_check_complete.set()
                    return

                # Ensure config is downloaded
                self.config_manager.wait_until_downloaded()

                # Retrieve latest version and firmware from config
                latest_version = self.config_manager.get_config_value("version")
                main_changelog = self.config_manager.get_config_value("main_aio_changelog", [])
                latest_firmware = self.config_manager.get_config_value("firmware_version", {})
                latest_firmware_left = latest_firmware.get("left", {})
                latest_firmware_right = latest_firmware.get("right", {})

                if not latest_version:
                    self.logger.terminal_print("Latest version not specified in configuration.")
                    self.update_check_complete.set()
                    return

                current_version = self.config_manager.get_config_value("current_version", self.DEFAULT_VERSION)

                current_firmware_left = self.FIRMWARE_LEFT
                current_firmware_right = self.FIRMWARE_RIGHT

                # Always print main version changelog
                self.logger.terminal_print("\n*** Main Version Changelog ***")
                for item in main_changelog:
                    for change in item.get("changes", []):
                        self.logger.terminal_print(f"- {change}")
                self.logger.terminal_print("\n")

                # Check firmware versions
                firmware_update_needed = False

                if self.is_different_version(latest_firmware_left.get("version", ""), current_firmware_left):
                    self.logger.terminal_print("\n*** Left firmware is available ***")
                    self.logger.terminal_print(f"Version: {latest_firmware_left.get('version', 'Unknown')}")
                    self.logger.terminal_print("Changelog:")
                    for change in latest_firmware_left.get("changelog", []):
                        self.logger.terminal_print(f"- {change}\n")
                    firmware_update_needed = True

                if self.is_different_version(latest_firmware_right.get("version", ""), current_firmware_right):
                    self.logger.terminal_print("\n*** Right firmware is available ***")
                    self.logger.terminal_print(f"Version: {latest_firmware_right.get('version', 'Unknown')}")
                    self.logger.terminal_print("Changelog:")
                    for change in latest_firmware_right.get("changelog", []):
                        self.logger.terminal_print(f"- {change}\n")
                    firmware_update_needed = True

                if not firmware_update_needed:
                    self.logger.terminal_print("You are up to date.\n")

                # Check if the software version is different
                if self.is_different_version(latest_version, current_version):
                    self.logger.terminal_print("New version available. Downloading update...")

                    new_exe_name = f"MAKCU_{latest_version.replace('.', '_')}.exe"
                    new_exe_path = os.path.join(self.main_folder, new_exe_name)

                    # Ensure the target file is overwritten if it exists
                    if os.path.exists(new_exe_path):
                        self.logger.terminal_print(f"Existing versioned file found. Removing: {new_exe_path}")
                        os.remove(new_exe_path)

                    # Download the executable
                    self.download_file(self.UPDATE_BASE_URL, new_exe_path)

                    if self.is_offline:
                        self.logger.terminal_print("Offline flashing mode enabled. Please ensure the firmware is available locally.")
                    else:
                        self.logger.terminal_print(f"Launching new version: {new_exe_name}")
                        subprocess.Popen([new_exe_name], shell=True)
                        time.sleep(0.2)  # Delay before shutting down this version
                        self.logger.terminal_print("Exiting current version.")
                        os._exit(0)

            except Exception as e:
                self.logger.terminal_print(f"Update check failed: {e}")
            finally:
                self.update_check_complete.set()

        threading.Thread(target=task, daemon=True).start()







    def is_different_version(self, latest, current):
        """
        Return True if the latest version is different from the current version.
        """
        try:
            return str(latest) != str(current)
        except Exception as e:
            self.logger.terminal_print(f"Version comparison failed: {e}")
            return False

    def download_file(self, url, destination):
        """
        Downloads a file from a URL and saves it directly to the destination.
        """
        # Disable terminal logging temporarily
        original_terminal_log = self.logger.terminal_print
        self.logger.terminal_print = lambda *args, **kwargs: None  # Disable logging

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with open(destination, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            # Re-enable logging
            self.logger.terminal_print = original_terminal_log
            self.logger.terminal_print(f"Downloaded file: {destination}")
        except Exception:
            # Set offline flag if download fails
            self.is_offline = True
            # Re-enable logging
            self.logger.terminal_print = original_terminal_log
            self.logger.terminal_print("Failed to download update. Running offline mode.")
