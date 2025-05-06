import json
import os
import sys
from pathlib import Path
from enum import Enum
import logging

def get_application_path():
    """Get the application base path, handling both script and PyInstaller executable"""
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))

class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"

class Settings:
    def __init__(self):
        # Get the correct application directory
        self.app_dir = get_application_path()
        self.settings_file = os.path.join(self.app_dir, "settings.json")
        
        # Create history folder
        self.history_folder = os.path.join(self.app_dir, "History")
        os.makedirs(self.history_folder, exist_ok=True)
        
        self.default_settings = {
            "always_on_top": True,
            "clickthrough": False,
            "auto_refresh": True,
            "minimize_on_startup": False,
            "resize_image_to_fit": True,
            "save_history": False,
            "opacity": 77,
            "theme": Theme.DARK.value,
            "monitor_print_screen": True,
            "monitor_ctrl_c": True,
            "double_shift_capture": True,
            "capture_width": 720,
            "capture_height": 480,
            "overlay_width": 500,
            "overlay_height": 500,
            "overlay_x": 0,
            "overlay_y": 0,
            "history_folder": self.history_folder
        }
        self.settings = self.load_settings()
        
        # Always save settings after loading to ensure the file exists
        self.save_settings()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    settings = json.load(f)
                # Ensure all default settings are present
                for key, value in self.default_settings.items():
                    if key not in settings:
                        settings[key] = value
                return settings
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error loading settings: {e}")
                return self.default_settings.copy()
        else:
            return self.default_settings.copy()

    def save_settings(self):
        try:
            with open(self.settings_file, "w") as f:
                json.dump(self.settings, f, indent=4)
            return True
        except IOError as e:
            logging.error(f"Error saving settings: {e}")
            return False

    def reset_to_defaults(self):
        self.settings = self.default_settings.copy()
        self.save_settings()

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        return self.save_settings()

    def update(self, settings_dict):
        self.settings.update(settings_dict)
        return self.save_settings()
