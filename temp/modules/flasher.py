# modules/flasher.py

import requests
import threading
import os
import subprocess
import time
import sys
from modules.utils import get_download_path, get_icon_path  # Corrected import


class Flasher:
    FLASH_LEFT_URL = "https://github.com/terrafirma2021/MAKCM_v2_files/raw/main/MAKCU_LEFT.bin"
    FLASH_RIGHT_URL = "https://github.com/terrafirma2021/MAKCM_v2_files/raw/main/MAKCU_RIGHT.bin"

    def __init__(self, logger, serial_handler):
        self.logger = logger
        self.serial_handler = serial_handler
        try:
            self.esptool_path = get_icon_path('esptool.exe')
            if not os.path.exists(self.esptool_path):
                raise FileNotFoundError(f"esptool.exe not found at {self.esptool_path}")
        except FileNotFoundError as e:
            self.logger.terminal_print(f"Esptool not found: {e}")
            raise
        self.is_flashing = False

    def download_and_flash(self, url, bin_filename):
        """Downloads the BIN file and initiates flashing."""
        def task():
            try:
                self.logger.terminal_print(f"Downloading {bin_filename} from {url}...")
                response = requests.get(url, stream=True)
                response.raise_for_status()

                bin_path = get_download_path(bin_filename)
                with open(bin_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                self.logger.terminal_print(f"Downloaded {bin_filename} successfully to {bin_path}.")
                self.flash_firmware(bin_path)
            except Exception as e:
                self.logger.terminal_print(f"Failed to download {bin_filename}: {e}")

        threading.Thread(target=task, daemon=True).start()

    # ----------------------------------------------------------------
    # NEW: Flash a local .bin file without downloading
    # ----------------------------------------------------------------
    def flash_local_bin(self, local_filepath):
        """
        Flash a .bin file that already exists locally (no download).
        """
        def task():
            try:
                if not os.path.isfile(local_filepath):
                    raise FileNotFoundError(f"Local file not found: {local_filepath}")
                self.logger.terminal_print(f"Using local bin for flashing: {local_filepath}")
                self.flash_firmware(local_filepath)
            except Exception as e:
                self.logger.terminal_print(f"Failed to flash local bin: {e}")

        threading.Thread(target=task, daemon=True).start()

    def flash_firmware(self, bin_path):
        """Starts the flashing process in a separate thread."""
        if not bin_path:
            self.logger.terminal_print("No BIN file specified for flashing.")
            return
        try:
            self.logger.terminal_print(f"Initiating flash with {bin_path}...")
            threading.Thread(target=self.flash_firmware_thread, args=(bin_path,), daemon=True).start()
        except Exception as e:
            self.logger.terminal_print(f"Error initiating flashing: {e}")

    def flash_firmware_thread(self, bin_path):
        """Handles the flashing process."""
        if not os.path.isfile(bin_path):
            self.logger.terminal_print(f"BIN file does not exist: {bin_path}")
            return
    
        self.is_flashing = True
        self.serial_handler.set_flashing(True)
        self.logger.terminal_print(f"Loaded file: {bin_path}")
    
        if self.serial_handler.is_connected:
            self.serial_handler.stop_monitoring()
            if self.serial_handler.monitoring_thread and self.serial_handler.monitoring_thread.is_alive():
                self.serial_handler.monitoring_thread.join(timeout=5)
    
        time.sleep(0.5)
    
        process_failed = False
        process = None
        success_detected = False
        bootloader_warning_detected = False
    
        try:
            # Updated baud rate to 921600
            esptool_args = [
                self.esptool_path,
                '--chip', 'esp32s3',
                '--port', self.serial_handler.com_port,
                '--baud', '921600',  # Set baud rate to 921600
                'write_flash', '0x0', bin_path
            ]
    
            if sys.platform.startswith('win'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                process = subprocess.Popen(
                    esptool_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    startupinfo=startupinfo
                )
            else:
                process = subprocess.Popen(
                    esptool_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False
                )
    
            def read_stream(pipe, stream_name):
                nonlocal success_detected, bootloader_warning_detected
                for line in iter(pipe.readline, ''):
                    self.logger.terminal_print(line.strip())
                    if "Leaving... WARNING: ESP32-S3" in line:
                        bootloader_warning_detected = True
                    if "Hash of data verified." in line:
                        success_detected = True
                pipe.close()
    
            stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, 'STDOUT'), daemon=True)
            stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, 'STDERR'), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
    
            process.wait()
    
            stdout_thread.join()
            stderr_thread.join()
    
            if process.returncode == 0 or success_detected or bootloader_warning_detected:
                self.logger.terminal_print("Flashing completed successfully.")
            else:
                process_failed = True
    
        except Exception as e:
            self.logger.terminal_print(f"Flashing error: {e}")
            process_failed = True
    
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            if process_failed and not bootloader_warning_detected:
                self.logger.terminal_print("Flashing encountered errors.")
            self.is_flashing = False
            self.serial_handler.set_flashing(False)
            self.serial_handler.start_monitoring()
