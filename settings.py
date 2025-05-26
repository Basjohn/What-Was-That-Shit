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
        
        # Set default history folder relative to application directory
        default_history_folder = os.path.join(self.app_dir, "History")
        
        self.default_settings = {
            "always_on_top": True,
            "clickthrough": False,
            "auto_refresh": True,
            "minimize_on_startup": False,
            "resize_image_to_fit": True,
            "save_history": False,
            "theme": "dark",
            "opacity": 74,
            "opacity_toggled": False,
            "monitor_print_screen": True,
            "monitor_ctrl_c": True,
            "double_shift_capture": True,
            "video_aware_capture": False,
            "draw_capture_frame": True,
            "capture_width": 800,
            "capture_height": 800,
            "capture_frame_color": "#FF0000",  # Bright red for better visibility
            "capture_frame_opacity": 255,      # Full opacity
            "capture_frame_duration": 5000,    # 5 seconds for testing
            "overlay_width": 694,
            "overlay_height": 508,
            "overlay_x": 0,
            "overlay_y": 0,
            "overlay_visible": True,
            "overlay_position_x": 0,
            "overlay_position_y": 0,
            "settings_window_x": 100,
            "settings_window_y": 100,
            "sneaky_bitch_mode": False
        }
        
        # Ensure history folder exists
        os.makedirs(default_history_folder, exist_ok=True)
        self.settings = self.load_settings()
        
        # Always save settings after loading to ensure the file exists
        self.save_settings()

    def load_settings(self):
        # Start with default settings
        settings = self.default_settings.copy()
        
        # These are legacy settings that we want to ignore
        legacy_settings = {
            'resize_frame_to_image',
            'last_snapped_to',
            'scroll_wheel_resize',
            'history_folder'  # We'll handle this separately
        }
        
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    user_settings = json.load(f)
                
                # Update defaults with user settings
                for key, value in user_settings.items():
                    if key in settings:
                        settings[key] = value
                    elif key in legacy_settings:
                        logging.debug(f"Ignoring legacy setting: {key}")
                    else:
                        logging.warning(f"Unknown setting: {key}")
                        
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error loading settings: {e}")
                # Continue with defaults on error
        
        # Ensure required settings exist
        if 'capture_frame_duration' not in settings:
            settings['capture_frame_duration'] = 1000  # ms
            
        return settings

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
        
    @property
    def history_folder(self):
        """Get the history folder path, creating it if it doesn't exist."""
        history_dir = os.path.join(self.app_dir, "History")
        os.makedirs(history_dir, exist_ok=True)
        return history_dir
