# modules/gui.py

import tkinter as tk
import customtkinter as ctk
from PIL import Image
from customtkinter import CTkImage
import threading
import webbrowser
import subprocess
import os
import time
import sys
from tkinter import filedialog
from tkinter import font as tkfont

from .logger import Logger
from .serial_handler import SerialHandler
from .flasher import Flasher
from .updater import Updater
from .config_manager import ConfigManager  # New import
from .utils import get_icon_path, get_main_folder


class GUI:
    def __init__(self, root):
        """
        Initialize the GUI.
        """
        self.root = root
        self.root.title("MAKCU v2.1")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        self.root.minsize(800, 600)  # **Set minimum window size**
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)

        # Internal state
        self.is_connected = False
        self.current_mode = "Normal"
        self.theme_is_dark = True
        self.command_history = []
        self.history_position = -1
        self.available_ports = []
        self.port_mapping = {}
        self.is_devkit_mode = False
        self.is_online = True
        self.logging_on = False
        self.host_logging_on = False  # State for host logging

        # Configure grid weights for the main window
        # Define rows: 0 to 6
        self.root.grid_rowconfigure(0, weight=0)  # Marquee row
        self.root.grid_rowconfigure(1, weight=0)  # MCU status row
        self.root.grid_rowconfigure(2, weight=0)  # Buttons row
        self.root.grid_rowconfigure(3, weight=0)  # Flash buttons row
        self.root.grid_rowconfigure(4, weight=0)  # Icons row
        self.root.grid_rowconfigure(5, weight=0)  # Text input row
        self.root.grid_rowconfigure(6, weight=1)  # Output terminal row (expands)

        # Define columns: 0 to 2
        self.root.grid_columnconfigure(0, weight=1)  # Left buttons
        self.root.grid_columnconfigure(1, weight=1)  # Central content
        self.root.grid_columnconfigure(2, weight=1)  # Right buttons

        # Create output logger
        log_file_path = os.path.join(get_main_folder(), 'log.txt')
        self.output_text = self.create_output_box()
        self.logger = Logger(self.output_text, self.root, log_file_path=log_file_path)

        # Set theme
        if self.theme_is_dark:
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")

        self.define_theme_colors()

        # Build GUI components
        self.create_marquee_label()       # Row 0
        self.create_mcu_status_label()    # Row 1
        self.create_buttons()             # Row 2
        self.create_flash_buttons()       # Row 3
        self.update_flash_buttons_text()  # **Initialize flash buttons' text based on the initial mode**
        self.create_icons()               # Row 4
        self.create_text_input()          # Row 5

        self.make_window_draggable()

        # Hide buttons initially
        self.enable_log_button.grid_remove()
        self.control_button.grid_remove()
        self.host_log_button.grid_remove()  
        self.makcu_button.grid_remove() 
        

        # Initialize ConfigManager and download config
        self.config_manager = ConfigManager(self.logger)
        self.config_manager.download_config()

        # Handlers
        self.serial_handler = SerialHandler(self.logger, self.update_mcu_status)
        self.flasher = Flasher(self.logger, self.serial_handler)
        self.main_folder = get_main_folder()

        # Create Updater and run check after config is downloaded
        self.updater = Updater(self.logger, self.config_manager)
        self.updater.check_for_updates()
        self.updater.update_check_complete.wait()

        # Set initial online/offline state from updater
        self.is_offline = self.updater.is_offline
        if self.is_offline:
            self.online_offline_button.configure(text="Offline")
        else:
            self.online_offline_button.configure(text="Online")

        # Start serial monitoring
        self.serial_handler.start_monitoring()

        # Fetch marquee text from the configuration
        self.fetch_and_display_welcome_message()

        # Bind the window resize event to adjust the marquee
        self.root.bind("<Configure>", self.on_window_resize)

    # -------------------------------------------------------------
    # Output terminal
    # -------------------------------------------------------------
    def create_output_box(self):
        output_text = ctk.CTkTextbox(self.root, state="disabled", font=("Helvetica", 12))
        output_text.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")
        return output_text

    # -------------------------------------------------------------
    # Marquee label at row=0
    # -------------------------------------------------------------
    def create_marquee_label(self):
        """
        Create the marquee label that spans all three columns in row 0.
        """
        self.marquee_label = ctk.CTkLabel(
            self.root,
            text="",
            text_color="white",
            bg_color="black",
            font=("Courier", 12),  # Changed to monospace font for consistency
            anchor="w"  # Anchor to the West (left)
        )
        # Ensure the label spans all three columns
        self.marquee_label.grid(row=0, column=0, columnspan=3, padx=0, pady=0, sticky="ew")

        # Initialize marquee variables
        self.marquee_text = ""
        self.full_message = ""
        self.marquee_position = 0
        self.display_length = 20  # Default display length
        self.marquee_speed = 50  # Adjust speed for smoother scrolling

    # -------------------------------------------------------------
    # MCU Status Label at row=1
    # -------------------------------------------------------------
    def create_mcu_status_label(self):
        """
        Create the MCU status label positioned in row 1, column 1.
        """
        self.label_mcu = ctk.CTkLabel(
            self.root,
            text="MCU disconnected",
            text_color="blue",
            font=("Helvetica", 12),
            anchor="w"
        )
        self.label_mcu.grid(row=1, column=1, padx=10, pady=5, sticky="w")

    # -------------------------------------------------------------
    # Buttons at row=2
    # -------------------------------------------------------------
    def create_buttons(self):
        """
        Create the left and right button frames in row 2.
        """
        # Left button frame remains unchanged...
        self.left_button_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.left_button_frame.grid(row=2, column=0, padx=5, pady=5, sticky="nw")
        for i in range(4):  # Only rows 0 to 3 are used
            self.left_button_frame.grid_rowconfigure(i, weight=0, minsize=40)
        self.left_button_frame.grid_columnconfigure(0, weight=1)

        self.logging_button = ctk.CTkButton(
            self.left_button_frame,
            text="Logging",
            command=self.enable_logging,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.logging_button.grid(row=0, column=0, padx=0, pady=(0, 5), sticky="w")
        self.logging_button.grid_remove()  # hidden by default

        initial_theme_text = "Light Mode" if self.theme_is_dark else "Dark Mode"
        self.theme_button = ctk.CTkButton(
            self.left_button_frame,
            text=initial_theme_text,
            command=self.change_theme,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.theme_button.grid(row=0, column=0, padx=0, pady=5, sticky="w")

        self.enable_log_button = ctk.CTkButton(
            self.left_button_frame,
            text="Main PC Log",
            command=self.enable_logging,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.enable_log_button.grid(row=1, column=0, padx=0, pady=5, sticky="w")

        self.host_log_button = ctk.CTkButton(
            self.left_button_frame,
            text="Mouse Log",
            command=self.toggle_host_logging,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.host_log_button.grid(row=2, column=0, padx=0, pady=5, sticky="w")

        self.clear_log_button = ctk.CTkButton(
            self.left_button_frame,
            text="Clear Log",
            command=self.clear_terminal,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.clear_log_button.grid(row=3, column=0, padx=0, pady=5, sticky="w")


        # Right button frame with an extra row for the new button
        self.right_button_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.right_button_frame.grid(row=2, column=2, padx=5, pady=5, sticky="ne")
        # Configure five rows to accommodate the new button
        for i in range(5):
            self.right_button_frame.grid_rowconfigure(i, weight=0, minsize=40)
        self.right_button_frame.grid_columnconfigure(0, weight=1)

        # NEW: Online/Offline toggle button at row 0
        self.online_offline_button = ctk.CTkButton(
            self.right_button_frame,
            text="Online",  # Default text; will update based on state later
            command=self.toggle_online_offline,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.online_offline_button.grid(row=0, column=0, padx=0, pady=5, sticky="e")

        # Shift existing buttons down by one row
        self.makcu_button = ctk.CTkButton(
            self.right_button_frame,
            text="MAKCU",
            command=self.toggle_makcu_mode,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.makcu_button.grid(row=1, column=0, padx=0, pady=5, sticky="e")

        self.control_button = ctk.CTkButton(
            self.right_button_frame,
            text="Test",
            command=self.test_button_function,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.control_button.grid(row=2, column=0, padx=0, pady=5, sticky="e")

        self.open_log_button = ctk.CTkButton(
            self.right_button_frame,
            text="User Logs",
            command=self.open_log,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.open_log_button.grid(row=3, column=0, padx=0, pady=5, sticky="e")

        self.quit_button = ctk.CTkButton(
            self.right_button_frame,
            text="Quit",
            command=self.quit_application,
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.quit_button.grid(row=4, column=0, padx=0, pady=5, sticky="e")





    # -------------------------------------------------------------
    # Flash buttons at row=3
    # -------------------------------------------------------------
    def create_flash_buttons(self):
        """
        Create the flash buttons in row 3.
        """
        # Flash buttons are placed in row=3
        self.left_flash_button = ctk.CTkButton(
            self.root,
            text="Flash Left",
            command=lambda: self.handle_flash('left'),
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.left_flash_button.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.left_flash_button.grid_remove()

        self.right_flash_button = ctk.CTkButton(
            self.root,
            text="Flash Right",
            command=lambda: self.handle_flash('right'),
            fg_color="transparent",
            font=("Helvetica", 12)
        )
        self.right_flash_button.grid(row=3, column=2, padx=5, pady=5, sticky="e")
        self.right_flash_button.grid_remove()

    # -------------------------------------------------------------
    # Update Flash Buttons Text
    # -------------------------------------------------------------
    def update_flash_buttons_text(self):
        """
        Update the flash buttons' text based on Devkit mode.
        """
        if self.is_devkit_mode:
            self.left_flash_button.configure(text="Flash Top Right")
            self.right_flash_button.configure(text="Flash Bottom Right")
        else:
            self.left_flash_button.configure(text="Flash Left")
            self.right_flash_button.configure(text="Flash Right")

    # -------------------------------------------------------------
    # Discord/GitHub icons at row=4
    # -------------------------------------------------------------
    def create_icons(self):
        """
        Create Discord and GitHub icons in row 3.
        """
        icon_size = (20, 20)
        discord_icon_path = get_icon_path("Discord.png")
        github_icon_path = get_icon_path("GitHub.png")

        if not os.path.exists(discord_icon_path):
            self.logger.terminal_print(f"Discord icon not found at {discord_icon_path}")
        if not os.path.exists(github_icon_path):
            self.logger.terminal_print(f"GitHub icon not found at {github_icon_path}")

        try:
            discord_pil_image = Image.open(discord_icon_path).resize(icon_size)
            github_pil_image = Image.open(github_icon_path).resize(icon_size)
        except Exception as e:
            self.logger.terminal_print(f"Error loading icons: {e}")
            discord_pil_image = Image.new('RGBA', icon_size, (255, 255, 255, 0))
            github_pil_image = Image.new('RGBA', icon_size, (255, 255, 255, 0))

        self.discord_icon = CTkImage(discord_pil_image, size=icon_size)
        self.github_icon = CTkImage(github_pil_image, size=icon_size)

        self.github_icon_label = ctk.CTkLabel(self.root, image=self.github_icon, text="")
        self.github_icon_label.grid(row=4, column=0, padx=(70, 0), pady=5, sticky="w")
        self.github_icon_label.bind("<Button-1>", lambda event: webbrowser.open("https://github.com/terrafirma2021/MAKCM"))
        self.github_icon_label.bind("<Enter>", lambda event: self.github_icon_label.configure(cursor="hand2"))
        self.github_icon_label.bind("<Leave>", lambda event: self.github_icon_label.configure(cursor=""))

        self.discord_icon_label = ctk.CTkLabel(self.root, image=self.discord_icon, text="")
        self.discord_icon_label.grid(row=4, column=2, padx=(0, 70), pady=5, sticky="e")
        self.discord_icon_label.bind("<Button-1>", lambda event: webbrowser.open("https://discord.gg/6TJBVtdZbq"))
        self.discord_icon_label.bind("<Enter>", lambda event: self.discord_icon_label.configure(cursor="hand2"))
        self.discord_icon_label.bind("<Leave>", lambda event: self.discord_icon_label.configure(cursor=""))

        # Prevent garbage collection
        self.discord_icon_label.image = self.discord_icon
        self.github_icon_label.image = self.github_icon

    # -------------------------------------------------------------
    # Text input at row=5
    # -------------------------------------------------------------
    def create_text_input(self):
        """
        Create the text input field in row 5 with built-in placeholder text.
        """
        input_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        input_frame.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.text_input = ctk.CTkEntry(
            input_frame,
            font=("Helvetica", 12),
            placeholder_text="Press up arrow to view input history",
            placeholder_text_color="gray"
        )
        self.text_input.grid(row=0, column=0, padx=(0, 5), pady=0, sticky="ew")

        # Bindings for placeholder text
        self.text_input.bind("<FocusIn>", self.clear_placeholder)
        self.text_input.bind("<FocusOut>", self.add_placeholder)

        # Bind Enter key to send_input
        self.text_input.bind("<Return>", self.send_input)
        self.text_input.bind("<KP_Enter>", self.send_input)  # Optional: Numpad Enter

        # **New Bindings for Up and Down Arrow Keys**
        self.text_input.bind("<Up>", self.handle_history)
        self.text_input.bind("<Down>", self.handle_history)

    def clear_placeholder(self, event=None):
        """
        Clear the placeholder text when the input field gains focus.
        """
        if self.text_input.get() == "Press up arrow to view input history":
            self.text_input.delete(0, ctk.END)
            self.text_input.configure(text_color="black")  # Set text color to normal

    def add_placeholder(self, event=None):
        """
        Add the placeholder text back if the input field is empty when it loses focus.
        """
        if not self.text_input.get():
            self.text_input.insert(0, "Press up arrow to view input history")
            self.text_input.configure(text_color="gray")  # Set placeholder text color

    # -------------------------------------------------------------
    # Define theme colors
    # -------------------------------------------------------------
    def define_theme_colors(self):
        """
        Define and apply theme colors based on the current theme setting.
        """
        if self.theme_is_dark:
            root_bg = "black"
            button_bg = "black"
            button_fg = "white"
            marquee_bg = "black"
            marquee_fg = "white"
            dropdown_bg = "black"
            dropdown_fg = "white"
            dropdown_selected_bg = "#333333"
        else:
            root_bg = "white"
            button_bg = "white"
            button_fg = "black"
            marquee_bg = "white"
            marquee_fg = "black"
            dropdown_bg = "white"
            dropdown_fg = "black"
            dropdown_selected_bg = "#d3d3d3"

        self.root.configure(bg=root_bg)

        if hasattr(self, 'marquee_label'):
            self.marquee_label.configure(bg_color=marquee_bg, text_color=marquee_fg)

        self.dropdown_bg = dropdown_bg
        self.dropdown_fg = dropdown_fg
        self.dropdown_selected_bg = dropdown_selected_bg

        buttons = [
            getattr(self, 'theme_button', None),
            getattr(self, 'quit_button', None),
            getattr(self, 'control_button', None),
            getattr(self, 'open_log_button', None),
            getattr(self, 'left_flash_button', None),
            getattr(self, 'right_flash_button', None),
            getattr(self, 'clear_log_button', None),
            getattr(self, 'enable_log_button', None),
            getattr(self, 'logging_button', None),
            getattr(self, 'makcu_button', None),
            # getattr(self, 'move_button', None),  # Removed or commented out as it doesn't exist
        ]
        for btn in buttons:
            if btn:
                btn.configure(fg_color=button_bg, text_color=button_fg)

        self.output_text.configure(fg_color=root_bg, text_color=button_fg)

    # -------------------------------------------------------------
    # Toggle theme
    # -------------------------------------------------------------
    def change_theme(self):
        """
        Toggle between dark and light themes.
        """
        if self.theme_is_dark:
            ctk.set_appearance_mode("light")
            self.theme_button.configure(text="Dark Mode")
        else:
            ctk.set_appearance_mode("dark")
            self.theme_button.configure(text="Light Mode")

        self.theme_is_dark = not self.theme_is_dark
        self.define_theme_colors()

    # -------------------------------------------------------------
    # Update MCU status
    # -------------------------------------------------------------
    def update_mcu_status(self):
        """
        Update the MCU status label based on the connection status
        and show/hide buttons appropriately.
        """
        if self.serial_handler.is_connected:
            # If connected, show/hide buttons depending on current mode
            if self.serial_handler.current_mode == "Normal":
                status_color = "#0acc1e"  # Green
                mode_text = "Normal"

                # Show normal-mode buttons
                self.root.after(0, self.enable_log_button.grid)
                self.root.after(0, self.control_button.grid)
                self.root.after(0, self.clear_log_button.grid)
                self.root.after(0, self.makcu_button.grid)
                self.root.after(0, self.host_log_button.grid)  # Show Mouse Log in Normal mode

            else:
                status_color = "#bf0a37"  # Red
                mode_text = "Flash"

                # In Flash mode, hide these:
                self.root.after(0, self.enable_log_button.grid_remove)
                self.root.after(0, self.control_button.grid_remove)
                self.root.after(0, self.host_log_button.grid_remove)  # Hide Mouse Log in Flash mode
                # The Clear Log and MAKCU/Devkit button can remain visible or not—up to you:
                self.root.after(0, self.clear_log_button.grid)
                self.root.after(0, self.makcu_button.grid)

            mcu_status = (
                f"MCU connected in {mode_text} mode on {self.serial_handler.com_port} "
                f"at {self.serial_handler.com_speed} baud"
            )

            # Show/hide flash buttons if connected or devkit is on
            if self.serial_handler.current_mode == "Flash" or self.is_devkit_mode:
                self.root.after(0, self.show_flash_buttons)
            else:
                self.root.after(0, self.hide_flash_buttons)

        else:
            # MCU disconnected
            mcu_status = "MCU disconnected"
            status_color = "#1860db"

            # Hide everything you want hidden while disconnected
            self.root.after(0, self.enable_log_button.grid_remove)
            self.root.after(0, self.control_button.grid_remove)
            self.root.after(0, self.clear_log_button.grid_remove)
            self.root.after(0, self.makcu_button.grid_remove)
            self.root.after(0, self.host_log_button.grid_remove)  # Hide Mouse Log while disconnected

            # Always hide both flash buttons if disconnected (even if Devkit)
            self.root.after(0, self.hide_flash_buttons)

        self.root.after(0, lambda: self.label_mcu.configure(text=mcu_status, text_color=status_color))


     
    # -------------------------------------------------------------
    # Toggle offline online mode
    # -------------------------------------------------------------
    def toggle_online_offline(self):
        """
        Toggle the online/offline mode manually.
        """
        # Toggle the boolean value
        self.is_offline = not self.is_offline

        # Synchronize the updater's offline flag with the new state
        self.updater.is_offline = self.is_offline

        # Update the button text based on the new state
        if self.is_offline:
            self.online_offline_button.configure(text="Offline")
        else:
            self.online_offline_button.configure(text="Online")

    # -------------------------------------------------------------
    # Send text input
    # -------------------------------------------------------------
    def send_input(self, event=None):
        """
        Send the entered command via the serial connection.
        """
        command = self.text_input.get().strip()
        if command:
            if not self.serial_handler.is_connected or not self.serial_handler.serial_open:
                self.logger.terminal_print("Connect to Device first")
            else:
                # Append \r to the command
                command += "\r"

                # Clear the text input box
                self.text_input.delete(0, ctk.END)

                try:
                    # Send the command via serial connection
                    self.serial_handler.serial_connection.write(command.encode())

                    # Log the sent command
                    self.logger.terminal_print(f"Sent command: {command.strip()}")

                    # Update command history
                    if len(self.command_history) >= 20:  # Limit history to 20 commands
                        self.command_history.pop(0)
                    self.command_history.append(command.strip())

                    # **Reset history_position after sending a new command**
                    self.history_position = -1

                except Exception as e:
                    self.logger.terminal_print(f"Failed to send command: {e}")
        return "break"  # Optional: Prevent further handling if needed

    def clear_terminal(self):
        """
        Clear the output terminal.
        """
        self.output_text.configure(state="normal")
        self.output_text.delete('1.0', tk.END)
        self.output_text.configure(state="disabled")

    def open_log(self):
        """
        Open the log file in the system's file explorer.
        """
        log_file_path = os.path.join(self.main_folder, 'log.txt')
        self.open_file_explorer(log_file_path)

    def open_file_explorer(self, file_path):
        """
        Open the system's file explorer at the given file path.
        """
        if os.path.exists(file_path):
            try:
                if sys.platform == "win32":
                    subprocess.Popen(['explorer', '/select,', file_path])
                elif sys.platform == "darwin":
                    subprocess.Popen(['open', '-R', file_path])
                else:
                    subprocess.Popen(['xdg-open', os.path.dirname(file_path)])
            except Exception as e:
                self.logger.terminal_print(f"Failed to open file explorer: {e}")
        else:
            self.logger.terminal_print("File does not exist.")

    # -------------------------------------------------------------
    # Flash logic
    # -------------------------------------------------------------
    def handle_flash(self, direction):
        """
        Attempts an online flash first (if we're not offline).
        If the GitHub download fails (e.g. DNS error), 
        silently switch to offline mode and show a single "Offline mode detected" message.
        """
        if not self.updater.is_offline:
            try:
                # Attempt to download firmware from GitHub
                if direction == 'left':
                    self.flasher.download_and_flash(self.flasher.FLASH_LEFT_URL, "MAKCM_LEFT.bin")
                elif direction == 'right':
                    self.flasher.download_and_flash(self.flasher.FLASH_RIGHT_URL, "MAKCM_RIGHT.bin")
            except:
                # Do NOT log the raw exception or mention "online" checks here
                self.updater.is_offline = True
                self.logger.terminal_print("Offline mode detected. Please select your .bin file.")
                self.offline_flash_dialog()
        else:
            # If we were already offline, just prompt for local .bin
            self.offline_flash_dialog()


    def offline_flash_dialog(self):
        """
        Prompts the user for a local .bin firmware file and flashes it.
        """
        # Remove folder creation as it's not needed:
        # folder_path = os.path.join(self.main_folder, 'manual_flashing')
        # os.makedirs(folder_path, exist_ok=True)
    
        # Log the prompt for user
        self.logger.terminal_print("Offline mode: Select your local firmware .bin file.")
    
        selected_file = filedialog.askopenfilename(
            title="Select .bin file for flashing",
            initialdir=self.main_folder,  # Open the dialog in the directory where the exe was run
            filetypes=[("Firmware Binary", "*.bin"), ("All Files", "*.*")]
        )
    
        if selected_file:
            self.logger.terminal_print(f"Selected firmware: {selected_file}")
            self.flasher.flash_local_bin(selected_file)
        else:
            self.logger.terminal_print("No firmware file selected. Aborting flash.")
    


    # -------------------------------------------------------------
    # Test button
    # -------------------------------------------------------------
    def test_button_function(self):
        """
        Perform test actions based on the current mode.
        """
        if self.serial_handler.current_mode == "Normal":
            self.test_normal_mode()
        elif self.serial_handler.current_mode == "Flash":
            self.test_flash_mode()

    def test_normal_mode(self):
        """
        Test function in Normal mode.
        """
        if self.serial_handler.is_connected:
            if self.serial_handler.serial_connection and self.serial_handler.serial_connection.is_open:
                try:
                    serial_command = "km.move(50,50)\r"
                    self.serial_handler.serial_connection.write(serial_command.encode())
                    self.logger.terminal_print("Mouse move command sent, did mouse move?")
                except Exception as e:
                    self.logger.terminal_print(f"Error sending command: {e}")
            else:
                self.logger.terminal_print("Serial connection is not open.")
        else:
            self.logger.terminal_print("Serial connection is not established. Please connect first.")

    def test_flash_mode(self):
        """
        Test function in Flash mode.
        """
        self.logger.terminal_print("Test function is disabled in Flash mode.")

    # -------------------------------------------------------------
    # Logging enable/disable
    # -------------------------------------------------------------
    def enable_logging(self):
        """
        Enable or disable logging based on the current state using the new log level functions.
        """
        if self.logging_on:
            # Disable logging
            self.serial_handler.set_device_log_level(0)
            self.logger.terminal_print("Debug mode disabled")
            self.enable_log_button.configure(text="Main PC Log")
            self.logging_on = False
            # Show host log button if in normal mode
            if self.serial_handler.current_mode == "Normal":
                self.host_log_button.grid()
        else:
            # Enable logging
            self.serial_handler.set_device_log_level(4)
            self.logger.terminal_print("Debug mode enabled")
            self.enable_log_button.configure(text="Disable Log")
            self.logging_on = True
            # Hide host log button while logging is active
            self.host_log_button.grid_remove()

    # -------------------------------------------------------------
    # Toggle MAKCU/Devkit mode
    # -------------------------------------------------------------
    def toggle_makcu_mode(self):
        """
        Toggle between MAKCU and Devkit modes.
        """
        if self.is_devkit_mode:
            # devkit => switch to MAKCU
            if self.serial_handler.is_connected:
                try:
                    self.serial_handler.request_4mbps_baud_rate()
                    time.sleep(0.0004)
                    self.serial_handler.serial_connection.baudrate = 4000000
                    self.serial_handler.com_speed = 4000000
                except Exception as e:
                    self.logger.terminal_print(f"Error switching to 4Mbps: {e}")

            self.is_devkit_mode = False
            self.makcu_button.configure(text="MAKCU")
            self.hide_flash_buttons()
        else:
            # MAKCU => switch to devkit
            if self.serial_handler.is_connected:
                try:
                    self.serial_handler.serial_connection.baudrate = 115200
                    self.serial_handler.com_speed = 115200
                except Exception as e:
                    self.logger.terminal_print(f"Error switching to 115200: {e}")

            self.is_devkit_mode = True
            self.makcu_button.configure(text="Devkit")
            self.show_flash_buttons()

        # Update the flash buttons' text based on the new mode
        self.update_flash_buttons_text()

    # -------------------------------------------------------------
    # Show and Hide Flash Buttons
    # -------------------------------------------------------------
    def show_flash_buttons(self):
        """
        Show the flash buttons and update their texts.
        """
        self.left_flash_button.grid()
        self.right_flash_button.grid()
        self.update_flash_buttons_text()  # Ensure text is updated when shown

    def hide_flash_buttons(self):
        """
        Hide the flash buttons.
        """
        self.left_flash_button.grid_remove()
        self.right_flash_button.grid_remove()

    # -------------------------------------------------------------
    # Fetch marquee
    # -------------------------------------------------------------
    def fetch_and_display_welcome_message(self):
        """
        Fetch the welcome message and start the marquee.
        """
        def fetch_message():
            try:
                # Ensure config is downloaded
                if not self.config_manager.download_complete.is_set():
                    self.logger.terminal_print("Waiting for configuration to be downloaded for marquee...")
                    self.config_manager.wait_until_downloaded()

                # Check if config was successfully downloaded
                if not self.config_manager.download_successful:
                    self.logger.terminal_print("Configuration download failed. Setting offline marquee.")
                    self.is_online = False
                    self.set_offline_marquee()
                    return

                # Retrieve the "message" key from the config
                marquee_message = self.config_manager.get_config_value("message", "Welcome to MAKCU!")
                # self.logger.terminal_print(f"Message for marquee: {marquee_message}")

                self.marquee_text = marquee_message + "    "  # Add spaces for separation
                self.start_marquee()

            except Exception as e:
                self.logger.terminal_print(f"Error fetching welcome message: {e}")
                self.set_offline_marquee()

        threading.Thread(target=fetch_message, daemon=True).start()

    # -------------------------------------------------------------
    # Start marquee scrolling
    # -------------------------------------------------------------
    def start_marquee(self):
        """
        Initialize the marquee to start scrolling.
        """
        if not self.marquee_text:
            return

        self.update_full_message()
        self.marquee_position = 0  # Start from the beginning of the full message
        self.animate_marquee()

    def animate_marquee(self):
        """
        Scroll the marquee text from right to left smoothly.
        """
        if not self.marquee_text:
            return

        # Calculate the visible message based on current position
        visible_message = self.full_message[self.marquee_position:self.marquee_position + self.display_length]

        # Wrap around if the visible part is shorter than display length
        if len(visible_message) < self.display_length:
            visible_message += self.full_message[:self.display_length - len(visible_message)]

        # Update the label text
        self.marquee_label.configure(text=visible_message)

        # Update position using modulo for smooth continuous scrolling
        self.marquee_position = (self.marquee_position + 1) % len(self.full_message)

        # Schedule the next update
        self.root.after(self.marquee_speed, self.animate_marquee)

    def update_full_message(self):
        """
        Recalculate the full message without padding for debugging purposes.
        """
        self.display_length = self.get_display_length()
        if self.display_length is None:
            self.display_length = 50  # Default value

        # Set the full message directly to the marquee text
        self.full_message = self.marquee_text

        # Initialize position to start scrolling from the beginning
        self.marquee_position = 0


    def get_display_length(self):
        """
        Calculate the number of characters that can be displayed in the marquee label
        based on the fixed window size (800x600).
        """
        # Use the fixed window width to calculate the label width
        label_width = 800  # Fixed window width in pixels

        # Get font metrics
        font = tkfont.Font(font=self.marquee_label.cget("font"))
        avg_char_width = font.measure("W")  # 'W' is typically the widest character in monospace fonts

        if avg_char_width == 0:
            # Fallback to a default if font metrics aren't ready
            print("Font metrics not available. Defaulting to 50 characters.")
            return 50

        # Calculate the number of characters that fit within the label width
        calculated_length = max(int(label_width / avg_char_width), 10)  # Minimum of 10 characters

        return calculated_length

    def set_offline_marquee(self):
        """
        Set the marquee to display an offline message.
        """
        offline_message = "You are offline, manual flashing supported    "
        self.marquee_text = offline_message
        self.start_marquee()

    # -------------------------------------------------------------
    # History up/down & dropdown
    # -------------------------------------------------------------
    def handle_history(self, event):
        """
        Navigate through the command history using up/down arrows.
        """
        if not self.command_history:
            return "break"  # Prevent further handling

        if event.keysym == "Up":
            if self.history_position < len(self.command_history) - 1:
                self.history_position += 1
                command = self.command_history[-self.history_position - 1]
                self.text_input.delete(0, ctk.END)
                self.text_input.insert(0, command)
        elif event.keysym == "Down":
            if self.history_position > 0:
                self.history_position -= 1
                command = self.command_history[-self.history_position - 1]
                self.text_input.delete(0, ctk.END)
                self.text_input.insert(0, command)
            elif self.history_position == 0:
                self.history_position = -1
                self.text_input.delete(0, ctk.END)
        return "break"  # Prevent further handling

    def show_history_menu(self):
        """
        Show a dropdown menu of command history.
        """
        if not self.command_history:
            return

        if self.history_dropdown and tk.Toplevel.winfo_exists(self.history_dropdown):
            return

        self.history_dropdown = tk.Toplevel(self.root)
        self.history_dropdown.wm_overrideredirect(True)
        self.history_dropdown.configure(bg=self.dropdown_bg)

        self.root.update_idletasks()
        input_x = self.text_input.winfo_rootx()
        input_y = self.text_input.winfo_rooty() + self.text_input.winfo_height()
        input_width = self.text_input.winfo_width()

        self.history_dropdown.wm_geometry(f"{input_width}x200+{input_x}+{input_y}")

        frame = tk.Frame(self.history_dropdown, bg=self.dropdown_bg, bd=1, relief="solid")
        frame.pack(fill="both", expand=True)

        self.history_listbox = tk.Listbox(
            frame,
            selectmode=tk.SINGLE,
            height=10,
            bg=self.dropdown_bg,
            fg=self.dropdown_fg,
            selectbackground=self.dropdown_selected_bg,
            font=("Helvetica", 12)
        )
        for cmd in reversed(self.command_history):  # Populate with up to 20 commands
            self.history_listbox.insert(tk.END, cmd)
        self.history_listbox.pack(side="left", fill="both", expand=True)

        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)
        self.history_listbox.bind("<MouseWheel>", lambda event: self.history_listbox.yview_scroll(int(-1*(event.delta/120)), "units"))
        self.history_listbox.bind("<Button-4>", lambda event: self.history_listbox.yview_scroll(-1, "units"))
        self.history_listbox.bind("<Button-5>", lambda event: self.history_listbox.yview_scroll(1, "units"))

        self.root.bind("<Button-1>", self.on_click_outside)
        self.history_listbox.focus_set()

    def update_history_dropdown(self):
        """
        Update the history dropdown with the latest commands.
        """
        if self.history_dropdown and tk.Toplevel.winfo_exists(self.history_dropdown):
            self.history_listbox.delete(0, tk.END)
            for cmd in reversed(self.command_history):  # Update with up to 20 commands
                self.history_listbox.insert(tk.END, cmd)

    def on_history_select(self, event):
        """
        Handle selection of a command from the history dropdown.
        """
        selected_indices = self.history_listbox.curselection()
        if selected_indices:
            selected_command = self.history_listbox.get(selected_indices[0])
            self.select_history_command(selected_command)
            self.hide_history_dropdown()

    def on_click_outside(self, event):
        """
        Hide the history dropdown if clicked outside.
        """
        if self.history_dropdown:
            x1 = self.history_dropdown.winfo_rootx()
            y1 = self.history_dropdown.winfo_rooty()
            x2 = x1 + self.history_dropdown.winfo_width()
            y2 = y1 + self.history_dropdown.winfo_height()
            if not (x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2):
                self.hide_history_dropdown()

    def hide_history_dropdown(self):
        """
        Hide and destroy the history dropdown.
        """
        if self.history_dropdown and tk.Toplevel.winfo_exists(self.history_dropdown):
            self.history_dropdown.destroy()
            self.history_dropdown = None
            self.root.unbind("<Button-1>")

    def select_history_command(self, command):
        """
        Insert the selected command into the text input.
        """
        self.text_input.delete(0, ctk.END)
        self.text_input.insert(0, command)

    # -------------------------------------------------------------
    # Drag gui
    # -------------------------------------------------------------

    def make_window_draggable(self):
        """
        Enable dragging the window by clicking and holding only on the marquee label.
        """
        def start_drag(event):
            # Store the offset of the mouse click relative to the window's top-left corner
            self.start_x = event.x
            self.start_y = event.y

        def drag_window(event):
            # Calculate the new top-left position of the window
            x = event.x_root - self.start_x
            y = event.y_root - self.start_y
            self.root.geometry(f"+{x}+{y}")

        # Bind drag start and motion events to the marquee label only
        self.marquee_label.bind("<Button-1>", start_drag)
        self.marquee_label.bind("<B1-Motion>", drag_window)

    # -------------------------------------------------------------
    # Toggle Host Logging
    # -------------------------------------------------------------
    def toggle_host_logging(self):
        """
        Toggle between enabling and disabling host logging.
        """
        if self.host_logging_on:
            # Disabling host logging
            self.serial_handler.send_command(self.serial_handler.LOG_HOST_TOGGLE, payload=bytes([0x00]))
            self.host_log_button.configure(text="Mouse log")
            self.host_logging_on = False
            # Show enable log button when host logging is disabled
            self.enable_log_button.grid()
            self.logger.terminal_print("Host logging disabled.")
        else:
            # Enabling host logging
            self.serial_handler.send_command(self.serial_handler.LOG_HOST_TOGGLE, payload=bytes([0x01]))
            self.host_log_button.configure(text="Disable Log")
            self.host_logging_on = True
            # Hide enable log button while host logging is active
            self.enable_log_button.grid_remove()
            self.logger.terminal_print("Host logging enabled.")

    # -------------------------------------------------------------
    # Safe exit
    # -------------------------------------------------------------
    def quit_application(self):
        """
        Safely exit the application, ensuring all threads and connections are closed.
        """
        try:
            # Check if flashing is in progress first
            if self.flasher.is_flashing:
                self.logger.terminal_print("Flashing in progress. Please wait...")
                while self.flasher.is_flashing:
                    time.sleep(0.1)
            
            # Call MCU reset instead of adjusting the baud rate
            if self.serial_handler.is_connected and self.serial_handler.serial_connection:
                self.serial_handler.reset_mcu()  # Reset MCU to ensure proper shutdown
            
            # Stop monitoring and clean up
            self.serial_handler.stop_monitoring()
            self.logger.stop()
        
        except Exception as e:
            self.logger.terminal_print(f"Error during shutdown: {e}")
        finally:
            self.root.quit()
            self.root.destroy()

    # -------------------------------------------------------------
    # Window resize handler
    # -------------------------------------------------------------
    def on_window_resize(self, event):
        """
        Handle window resize events to adjust marquee display length.
        """
        # Update display length and full message only if the label width has changed
        new_display_length = self.get_display_length()
        if new_display_length != self.display_length:
            self.display_length = new_display_length
            self.update_full_message()
