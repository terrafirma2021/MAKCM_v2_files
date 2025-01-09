# modules/config_manager.py

import requests
import threading
import os
import time
import json

from modules.utils import get_main_folder

class ConfigManager:
    """
    Handles downloading, storing, and accessing configuration data.
    """
    CONFIG_URL = "https://raw.githubusercontent.com/terrafirma2021/MAKCM_v2_files/main/config.json"
    LOCAL_CONFIG_PATH = os.path.join(get_main_folder(), 'config.json')

    def __init__(self, logger):
        self.logger = logger
        self.config_data = {}
        self.config_lock = threading.Lock()
        self.download_complete = threading.Event()
        self.download_successful = False  # Indicates if download was successful

    def download_config(self):
        """
        Downloads the config.json from the remote URL with cache-busting.
        """
        def task():
            try:
                cache_bust_url = f"{self.CONFIG_URL}?t={int(time.time())}"
                response = requests.get(cache_bust_url, timeout=10)
                response.raise_for_status()

                with self.config_lock:
                    self.config_data = response.json()
                    self.download_successful = True
                    #self.logger.terminal_print("Configuration downloaded and parsed successfully.")

                # Save the config locally
                with open(self.LOCAL_CONFIG_PATH, 'w', encoding="utf-8") as f:
                    json.dump(self.config_data, f, indent=4)
                #self.logger.terminal_print(f"Configuration saved to {self.LOCAL_CONFIG_PATH}.")

            except requests.RequestException as e:
                self.logger.terminal_print(f"Failed to download config: {e}")
                # Attempt to load from local if available
                if os.path.exists(self.LOCAL_CONFIG_PATH):
                    try:
                        with open(self.LOCAL_CONFIG_PATH, 'r', encoding="utf-8") as f:
                            with self.config_lock:
                                self.config_data = json.load(f)
                                self.download_successful = True
                        self.logger.terminal_print("Loaded configuration from local file.")
                    except Exception as ex:
                        self.logger.terminal_print(f"Failed to load local config: {ex}")
                else:
                    self.logger.terminal_print("No local configuration available.")

            except json.JSONDecodeError as e:
                self.logger.terminal_print(f"Invalid JSON format in config: {e}")
                # Handle invalid JSON as needed

            finally:
                self.download_complete.set()

        threading.Thread(target=task, daemon=True).start()

    def get_config_value(self, key, default=None):
        """
        Retrieves a value from the configuration data.
        """
        with self.config_lock:
            return self.config_data.get(key, default)

    def wait_until_downloaded(self):
        """
        Blocks until the configuration has been downloaded.
        """
        self.download_complete.wait()
