"""
Build script for the WWTS (What Was That Screenshot) application.
Creates a standalone Windows executable using PyInstaller.
"""
import os
import subprocess
import shutil
import sys

def main():
    print("Building WWTS for Windows...")
    
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Create directory for build artifacts
    build_dir = "build"
    dist_dir = "dist"
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)
    
    # Create default_settings.json if it doesn't exist
    default_settings_path = "default_settings.json"
    if not os.path.exists(default_settings_path):
        with open(default_settings_path, "w") as f:
            f.write("""{
    "opacity": 80,
    "theme": "dark",
    "auto_hide": true,
    "clickthrough": false,
    "always_on_top": true,
    "show_pin_button": true,
    "pin_to_corner": "None",
    "use_custom_pin_position": false,
    "enable_middle_click": true,
    "double_shift_capture": true,
    "scroll_wheel_resize": true,
    "save_history": true,
    "capture_height": 400,
    "capture_width": 500
}""")
        print(f"Created {default_settings_path}")
    
    # Define PyInstaller command with appropriate options
    pyinstaller_cmd = [
        "pyinstaller",
        "--name=WWTS",
        "--onefile",
        "--windowed",
        "--icon=resources/icons/WWTS.ico",
        "--add-data=resources;resources",
        "--add-data=default_settings.json;.",
        "wwts.py"
    ]
    
    # Run PyInstaller
    print("Running PyInstaller...")
    subprocess.check_call(pyinstaller_cmd)
    
    # Create a distribution directory with the executable and any other required files
    if os.path.exists(dist_dir):
        # Copy readme and license if they exist
        for file in ["README.md", "LICENSE"]:
            if os.path.exists(file):
                shutil.copy(file, os.path.join(dist_dir, file))
        
        # Create empty history directory
        history_dir = os.path.join(dist_dir, "history")
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)
        
        print(f"Build completed. Executable is in the {dist_dir} directory.")
    else:
        print("Build failed. Check the logs for errors.")

if __name__ == "__main__":
    main()
