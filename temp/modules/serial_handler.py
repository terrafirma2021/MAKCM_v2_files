import serial
import serial.tools.list_ports
import threading
import time
import struct

class SerialHandler:
    KNOWN_DEVICES = [
        {"vid": "1A86", "pid": "55D3", "mode": "Normal"},
        {"vid": "303A", "pid": "0009", "mode": "Flash"},
    ]

    GET_BAUD_RATE    = 0xA4
    SET_BAUD_RATE    = 0xA5
    GET_DEV_LOG      = 0xA6
    SET_DEV_LOG      = 0xA7
    LOG_HOST_TOGGLE  = 0x96

    def __init__(self, logger, update_mcu_status_callback):
        self.logger = logger
        self.update_mcu_status = update_mcu_status_callback
        self.is_connected = False
        self.serial_open = False
        self.serial_connection = None
        self.current_mode = "Normal"
        self.com_port = ""
        self.com_speed = 115200
        self.print_serial_data = True
        self.monitoring_active = False
        self.monitoring_thread = None
        self.serial_thread = None  # To handle serial communication
        self.buffer = bytearray()
        self.lock = threading.Lock()  # To prevent race conditions
        self.is_flashing = False      # Flag to indicate flashing status

    def find_com_port(self, vid, pid):
        """Finds the COM port matching the given VID and PID."""
        for port in serial.tools.list_ports.comports():
            hwid = port.hwid.upper()
            vid_pid = f"VID:PID={vid.upper()}:{pid.upper()}"
            if vid_pid in hwid:
                return port.device
        return None

    def start_monitoring(self):
        """Starts monitoring for a serial connection."""
        with self.lock:
            if self.monitoring_active:
                self.logger.terminal_print("Serial monitoring is already active.")
                return

            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(target=self.monitor_ports, daemon=True)
            self.monitoring_thread.start()
            self.logger.terminal_print("Started serial monitoring.")

    def stop_monitoring(self):
        """Stops monitoring and disconnects if connected."""
        with self.lock:
            if not self.monitoring_active:
                self.logger.terminal_print("Serial monitoring is not active.")
                return

            self.monitoring_active = False
            self.logger.terminal_print("Stopping serial monitoring...")

        if self.serial_connection and self.serial_connection.is_open:
            self.close_connection()

        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
            if self.monitoring_thread.is_alive():
                self.logger.terminal_print("Failed to fully stop monitoring thread.")
            else:
                self.logger.terminal_print("Serial monitoring stopped.")

    def monitor_ports(self):
        """Continuously scans for known devices and connects to them."""
        while self.monitoring_active:
            if not self.is_connected and not self.is_flashing:  # Check flashing status
                for device in self.KNOWN_DEVICES:
                    vid, pid, mode = device["vid"], device["pid"], device["mode"]
                    com_port = self.find_com_port(vid, pid)
                    if com_port:
                        self.auto_connect(com_port, mode)
                        break  # Exit loop once connected
            time.sleep(1)  # Avoid busy-waiting

    def auto_connect(self, com_port, mode, baudrate=115200, retry_attempts=5, retry_delay=2):
        """Attempts to connect to the specified COM port with retries."""
        attempt = 0
        while attempt < retry_attempts and not self.is_connected and self.monitoring_active:
            try:
                self.serial_connection = serial.Serial(
                    port=com_port,
                    baudrate=baudrate,
                    timeout=0.5,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
                self.serial_connection.flushInput()
                self.serial_connection.flushOutput()
                time.sleep(0.5)

                self.is_connected = True
                self.serial_open = True
                self.com_speed = baudrate
                self.current_mode = mode
                self.com_port = com_port

                self.logger.terminal_print(f"Connected to {com_port} at {baudrate} baud.")

                # Additional logic for setting baud rate in "Normal" mode
                if mode == "Normal":
                    try:
                        # 1) Send a command to the MCU to switch to 4 Mbps
                        self.request_4mbps_baud_rate()

                        # 2) Delay 0.4 ms to let the MCU switch
                        time.sleep(0.0004)  # 0.4 ms

                        # 3) Now switch our local side to 4 Mbps
                        self.serial_connection.baudrate = 4000000
                        self.com_speed = 4000000
                        self.logger.terminal_print("Switched baud rate to 4 Mbps.")
                    except Exception as e:
                        self.logger.terminal_print(f"Failed to switch baud rate: {e}")

                self.serial_thread = threading.Thread(target=self.serial_communication_thread, daemon=True)
                self.serial_thread.start()

                self.update_mcu_status()
                return  # Exit after successful connection
            except PermissionError as pe:
                self.logger.terminal_print(f"PermissionError while accessing {com_port}: {pe}")
            except Exception as e:
                self.logger.terminal_print(f"Failed to auto-connect to {com_port}: {e}")

            self.logger.terminal_print(f"Retrying to connect to {com_port} in {retry_delay} seconds...")
            time.sleep(retry_delay)
            attempt += 1

        if not self.is_connected:
            self.logger.terminal_print(f"Unable to connect to {com_port} after {retry_attempts} attempts.")

    def serial_communication_thread(self):
        """Handles serial communication while connected."""
        while self.monitoring_active and self.is_connected and self.serial_open:
            try:
                if self.serial_connection and self.serial_connection.is_open:
                    bytes_to_read = self.serial_connection.in_waiting
                    if bytes_to_read > 0:
                        data = self.serial_connection.read(bytes_to_read)
                        if data:
                            # Uncomment the following lines to enable incoming data logging
                            # decoded_data = data.decode("utf-8", errors="replace")
                            # self.logger.terminal_print(f"RX (UTF-8): {decoded_data}")
                            
                            self.handle_incoming_data(data)
            except Exception as e:
                self.logger.terminal_print(f"Serial communication error: {e}")
                self.handle_disconnect()
                break
            time.sleep(0.1)

    def parse_uart_frames(self, data):
        """
        Parses incoming UART data to handle frames starting with 'km.' or 0xDE, 0xAD.

        Args:
            data (bytearray): Incoming UART data stream.
        """
        index = 0
        while index < len(data):
            # Handle 'km.' frames
            if data[index:index + 3] == b'km.':
                end_index = data.find(b'\r', index)
                if end_index != -1:  # Full frame found
                    frame = data[index:end_index + 1]  # Include '\r'
                    self.logger.terminal_print(frame.decode('utf-8', errors='ignore'))
                    index = end_index + 1  # Move past the end of the frame
                else:
                    break  # Incomplete frame, wait for more data
                
            # Handle 0xDE, 0xAD frames
            elif data[index:index + 2] == b'\xDE\xAD':
                if index + 4 <= len(data):
                    size = struct.unpack('<H', data[index + 2:index + 4])[0]  # Frame size
                    end_index = index + 4 + size
                    if end_index <= len(data):  # Full frame available
                        frame = data[index + 4:end_index]  # Extract the actual payload
                        try:
                            # Decode the payload as UTF-8 and print as characters without a label
                            decoded_frame = frame.decode('utf-8', errors='ignore')
                            self.logger.terminal_print(decoded_frame)
                        except Exception as e:
                            self.logger.terminal_print(f"Error decoding frame: {e}")
                        index = end_index  # Move past the end of the frame
                    else:
                        break  # Incomplete frame, wait for more data
                else:
                    break  # Incomplete frame header, wait for more data
                
            else:
                # Skip to the next potential header
                next_km = data.find(b'km.', index + 1)
                next_dead = data.find(b'\xDE\xAD', index + 1)

                if next_km == -1 and next_dead == -1:
                    break  # No more potential headers
                
                # Jump to the closest header
                if next_km == -1:
                    index = next_dead
                elif next_dead == -1:
                    index = next_km
                else:
                    index = min(next_km, next_dead)

    def handle_incoming_data(self, data):
        """
        Handles incoming UART data by appending it to a buffer and parsing frames.

        Args:
            data (bytes): Incoming UART data.
        """
        with self.lock:
            self.buffer.extend(data)  # Add new data to the buffer
            try:
                self.parse_uart_frames(self.buffer)
            except Exception as e:
                self.logger.terminal_print(f"Error parsing UART frames: {e}")
            finally:
                # Reset the buffer after parsing
                self.buffer = bytearray()

    def handle_disconnect(self):
        """Handles disconnection and updates the status without restarting monitoring."""
        self.logger.terminal_print("Device disconnected.")
        self.is_connected = False
        self.serial_open = False

        if self.serial_connection:
            try:
                if self.serial_connection.is_open:
                    self.serial_connection.close()
                    self.logger.terminal_print("Serial connection closed.")
            except Exception as e:
                self.logger.terminal_print(f"Error closing serial connection: {e}")
            finally:
                self.serial_connection = None

        self.update_mcu_status()

    def close_connection(self):
        """Closes the current serial connection."""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                time.sleep(0.5)
                self.serial_connection.close()
                self.logger.terminal_print("Serial connection closed.")
        except Exception as e:
            self.logger.terminal_print(f"Error while closing serial connection: {e}")
        finally:
            self.serial_connection = None
            self.is_connected = False
            self.serial_open = False
            self.update_mcu_status()

    def toggle_serial_printing(self, state):
        """Enables or disables printing of serial data to the terminal."""
        self.print_serial_data = state

    def set_flashing(self, status: bool):
        """Sets the flashing status."""
        self.is_flashing = status

    def write_to_serial(self, data):
        """
        Enforces a header frame of [0xDE, 0xAD],
        followed by a 16-bit payload size (LSB then MSB),
        and then the actual data payload (UTF-8 encoded if str).
        Also logs the hex bytes being sent.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            self.logger.terminal_print("Attempted to write but serial is not open.")
            return

        if isinstance(data, str):
            data = data.encode("utf-8")

        # Prepare header + size + data
        header = bytes([0xDE, 0xAD])
        size = len(data)
        lsb = size & 0xFF
        msb = (size >> 8) & 0xFF
        payload = header + bytes([lsb, msb]) + data

        # Log the hex being sent
        payload_hex = " ".join(f"{b:02X}" for b in payload)
        self.logger.terminal_print(f"TX (auto-size) => {payload_hex}")

        try:
            self.serial_connection.write(payload)
        except Exception as e:
            self.logger.terminal_print(f"Error while writing to serial: {e}")

    def write_to_serial_with_size(self, size, data):
        """
        Like write_to_serial, but here 'size' is provided explicitly
        (e.g. if the MCU requires a specific length different from
        the actual data length). We still prepend the 0xDE,0xAD
        header and the 16-bit size (LSB, MSB) before sending.
        Also logs the hex bytes being sent.
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            self.logger.terminal_print("Attempted to write but serial is not open.")
            return

        if isinstance(data, str):
            data = data.encode("utf-8")

        header = bytes([0xDE, 0xAD])
        lsb = size & 0xFF
        msb = (size >> 8) & 0xFF
        payload = header + bytes([lsb, msb]) + data

        try:
            # Log raw bytes as hex (without 0x)
            hex_string = " ".join(f"{byte:02X}" for byte in payload)
            self.logger.terminal_print(f"TX (explicit-size) => {hex_string}")
            self.serial_connection.write(payload)
        except Exception as e:
            self.logger.terminal_print(f"Error while writing to serial: {e}")

    def send_command(self, command, payload=b""):
        """
        Generalized method to send a command with optional payload.
        """
        size = len(payload) + 1  # 1 byte for the command itself
        data = bytes([command]) + payload
        self.write_to_serial_with_size(size, data)

    def get_baud_rate(self):
        """
        Sends a command to retrieve the current baud rate.
        """
        self.logger.terminal_print("Requesting current baud rate...")
        self.send_command(self.GET_BAUD_RATE)

    def set_baud_rate(self, baud_rate):
        """
        Sends a command to set the baud rate.
        Baud rate should be provided in LSB format.
        """
        if baud_rate not in [115200, 4000000]:
            self.logger.terminal_print("Invalid baud rate. Only 115200 and 4000000 are supported.")
            return

        # Prepare payload specific to MCU requirements
        payload = bytes([0x00, 0x09, 0x3D, 0x00]) if baud_rate == 4000000 else bytes([0x00, 0x00, 0xC2, 0x01])

        self.send_command(self.SET_BAUD_RATE, payload=payload)

        # Wait for 300ms to ensure the device switches baud rate
        time.sleep(0.3)

        # Change the baud rate on the Python side
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.baudrate = baud_rate
            self.com_speed = baud_rate
            self.logger.terminal_print(f"Local baud rate changed to {baud_rate}.")

    def get_device_log_level(self):
        """
        Sends a command to retrieve the current device log level.
        """
        self.logger.terminal_print("Requesting current device log level...")
        self.send_command(self.GET_DEV_LOG)

    def set_device_log_level(self, log_level):
        """
        Sends a command to set the device log level.
        Log level should be between 0 (disabled) and 4 (debug).
        If log_level is 0, restarts the auto-connect logic.
        """
        if not (0 <= log_level <= 4):
            self.logger.terminal_print("Invalid log level. Must be between 0 (disabled) and 4 (debug).")
            return

        self.logger.terminal_print(f"Setting device log level to {log_level}...")
        self.send_command(self.SET_DEV_LOG, payload=bytes([log_level]))

        # Restart auto-connect logic only if log_level is 0
        if log_level == 0:
            self.restart_auto_connect()

    def request_4mbps_baud_rate(self):
        """
        Sends a command telling the MCU to switch its UART to 4 Mbps.
        """
        self.set_baud_rate(4000000)

    # -------------------------------------------------------------
    # Reset MCU
    # -------------------------------------------------------------
    def reset_mcu(self):
        """
        Call a MCU reset to catch enumeration when logging.
        """
        RESET = 0x81
        self.logger.terminal_print("Sending MCU reset command...")
        self.send_command(RESET)

    def restart_auto_connect(self):
        """
        Restarts the auto-connect logic by closing the current connection
        and allowing the monitoring thread to reconnect with the initial settings.
        """
        with self.lock:
            if self.is_connected:
                self.logger.terminal_print("Restarting auto-connect logic...")
                self.close_connection()
                # Allow some time for the monitoring thread to detect the disconnection
                time.sleep(1)
                self.logger.terminal_print("Auto-connect logic restarted. Attempting to reconnect...")
            else:
                self.logger.terminal_print("Auto-connect is not currently connected. Monitoring thread will handle connection.")

        # The monitoring thread will automatically attempt to reconnect
