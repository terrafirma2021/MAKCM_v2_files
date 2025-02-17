# modules/utils.py

import os
import sys
import shutil

def get_main_folder():
    """
    Returns the base folder:
    - If frozen, uses the same path as the executable.
    - If running as a script, uses the directory containing 'main.py'.
    """
    if getattr(sys, 'frozen', False):
        # If frozen, use the directory of the executable
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Use the directory of the main script (main.py)
        return os.path.dirname(os.path.abspath(sys.argv[0]))

def setup_custom_temp_folder():
    """
    Ensures resources are extracted to a `temp` folder next to the executable
    when running as a PyInstaller-packed executable.
    """
    base_folder = get_main_folder()
    temp_dir = os.path.join(base_folder, 'temp')

    # Ensure the `temp` directory exists
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir, exist_ok=True)

    # Move contents of the PyInstaller temp folder to the custom temp folder
    if getattr(sys, 'frozen', False):
        pyinstaller_temp = sys._MEIPASS
        for item in os.listdir(pyinstaller_temp):
            src = os.path.join(pyinstaller_temp, item)
            dst = os.path.join(temp_dir, item)
            if os.path.isdir(src):
                if not os.path.exists(dst):
                    shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    return temp_dir

def get_download_path(filename):
    """
    Returns the path where downloaded files should be stored.
    Uses `temp` when frozen, or the base folder otherwise.
    """
    if getattr(sys, 'frozen', False):
        temp_folder = setup_custom_temp_folder()
        return os.path.join(temp_folder, filename)
    else:
        base_folder = get_main_folder()
        return os.path.join(base_folder, filename)

def get_icon_path(filename):
    """
    Returns the full path to an icon or resource file.
    Handles both script and PyInstaller-packed executable paths, unpacking into `temp`.
    """
    if getattr(sys, 'frozen', False):
        # Ensure the temp folder is ready and use it as the base
        temp_folder = setup_custom_temp_folder()
        base_path = os.path.join(temp_folder, 'assets')
    else:
        # Use the project root during development
        base_path = os.path.join(get_main_folder(), 'assets')

    # Build the full path to the icon file
    resource_path = os.path.join(base_path, filename)

    # Verify the file exists
    if not os.path.exists(resource_path):
        raise FileNotFoundError(f"Resource not found: {resource_path}")

    return resource_path
