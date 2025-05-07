import os
import sys
import subprocess
import logging
from pathlib import Path

def main():
    """Build the WWTS executable with PyInstaller"""
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        logging.info("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Check for icon file
    icon_path = Path(__file__).parent / "resources" / "icons" / "WWTS.ico"
    if not icon_path.exists():
        logging.error(f"Icon file not found: {icon_path}")
        return 1
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=WWTS",
        "--onefile",
        f"--icon={icon_path}",
        "--windowed",
        "--add-data", f"{icon_path};resources/icons",
        "wwts.py"
    ]
    
    # Run PyInstaller
    logging.info("Building executable...")
    logging.info(" ".join(cmd))
    subprocess.check_call(cmd)
    
    logging.info("\nBuild complete! Executable is in the 'dist' folder.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
