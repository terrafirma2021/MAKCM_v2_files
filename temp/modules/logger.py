# modules/logger.py

import tkinter as tk
import threading
import queue

class Logger:
    def __init__(self, text_widget, root, log_file_path=None):
        print("Initializing Logger with log_file_path:", log_file_path)  # Debugging statement
        """
        Initializes the Logger.

        :param text_widget: The Tkinter Text or CTkTextbox widget where logs will be displayed.
        :param root: The main Tkinter root window, used for scheduling GUI updates.
        :param log_file_path: Optional path to a log file for saving logs.
        """
        self.text_widget = text_widget
        self.root = root
        self.queue = queue.Queue()
        self.running = True
        self.max_lines = 1000  # Maximum lines to keep in the textbox
        self.update_scheduled = False  # Flag to prevent multiple scheduled updates
        self.text_widget.configure(state='disabled')  # Start as read-only
        self.line_count = 0  # Current number of lines in the textbox

        # Optional: Initialize log file
        self.log_file = None
        if log_file_path:
            try:
                self.log_file = open(log_file_path, 'a', encoding='utf-8')
                self.terminal_print(f"Logging to file: {log_file_path}")
            except Exception as e:
                self.terminal_print(f"Failed to open log file: {e}")

    def terminal_print(self, message):
        """
        Thread-safe method to enqueue log messages.

        :param message: The log message to display.
        """
        self.queue.put(message)
        # Schedule the processing if not already scheduled
        if not self.update_scheduled:
            self.update_scheduled = True
            self.root.after(0, self.process_queue)

        # Optional: Write to log file
        if self.log_file:
            try:
                self.log_file.write(message + '\n')
                self.log_file.flush()
            except Exception as e:
                self.terminal_print(f"Failed to write to log file: {e}")

    def process_queue(self):
        """
        Process all messages in the queue and update the Text widget.
        """
        try:
            while not self.queue.empty():
                message = self.queue.get_nowait()
                self.text_widget.configure(state='normal')
                self.text_widget.insert(tk.END, message + '\n')
                self.text_widget.configure(state='disabled')
                self.text_widget.see(tk.END)  # Auto-scroll to the end
                self.line_count += 1

                # Limit the number of lines to prevent slowdown
                if self.line_count > self.max_lines:
                    self.text_widget.configure(state='normal')
                    self.text_widget.delete('1.0', '2.0')  # Delete the first line
                    self.text_widget.configure(state='disabled')
                    self.line_count -= 1
        except Exception as e:
            print(f"Logger update error: {e}")
        finally:
            self.update_scheduled = False
            # If new messages arrived during processing, schedule another update
            if not self.queue.empty() and self.running:
                self.update_scheduled = True
                self.root.after(0, self.process_queue)

    def stop(self):
        """
        Stop the logger's update loop and close the log file if it's open.
        """
        self.running = False
        if self.log_file:
            try:
                self.log_file.close()
            except Exception as e:
                print(f"Failed to close log file: {e}")
