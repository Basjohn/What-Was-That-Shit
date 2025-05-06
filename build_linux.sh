#!/bin/bash

echo "Building WWTS for Linux..."

# Check for required tools
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Installing pip..."
    sudo apt-get update
    sudo apt-get install -y python3-pip
    if [ $? -ne 0 ]; then
        echo "Failed to install pip. Please install it manually."
        exit 1
    fi
fi

# Check if PyInstaller is installed
if ! pip3 show pyinstaller &> /dev/null; then
    echo "PyInstaller is not installed. Installing..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "Failed to install PyInstaller. Please install it manually."
        exit 1
    fi
fi

# Check for required system dependencies
echo "Checking for required system packages..."
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    sudo apt-get update
    sudo apt-get install -y python3-dev python3-tk python3-pil.imagetk x11-utils
elif command -v dnf &> /dev/null; then
    # Fedora
    sudo dnf install -y python3-devel python3-tkinter python3-pillow python3-pillow-tk xorg-x11-utils
elif command -v pacman &> /dev/null; then
    # Arch Linux
    sudo pacman -S --noconfirm python-pillow tk xorg-utils
else
    echo "Warning: Unsupported package manager. You may need to install Python development tools, Tkinter, and PIL manually."
fi

# Clean up old build files
echo "Cleaning up old build files..."
rm -rf build dist WWTS.spec

# Install Python dependencies
echo "Installing dependencies..."
if [ -f "requirements_linux.txt" ]; then
    pip3 install -r requirements_linux.txt
else
    echo "Creating Linux requirements file..."
    cat > requirements_linux.txt << EOF
Pillow>=8.0.0
PyQt5>=5.15.0
pynput>=1.7.0
EOF
    pip3 install -r requirements_linux.txt
fi

if [ $? -ne 0 ]; then
    echo "Failed to install dependencies. Please check requirements_linux.txt"
    exit 1
fi

# Build the executable
echo "Building the executable..."
ICON_PATH="resources/icons/WWTS.ico"

if [ ! -f "$ICON_PATH" ]; then
    echo "Error: Icon file $ICON_PATH not found!"
    exit 1
fi

pyinstaller --noconfirm --onefile --windowed \
    --icon="$ICON_PATH" \
    --add-data="resources:resources" \
    --hidden-import=PIL \
    --hidden-import=pynput \
    --name=WWTS \
    wwts.py

if [ $? -ne 0 ]; then
    echo "Build failed."
    exit 1
fi

# Create output directory
echo "Creating output directory..."
mkdir -p output

# Copy executable to output directory
echo "Copying executable to output directory..."
cp dist/WWTS output/WWTS
if [ $? -ne 0 ]; then
    echo "Failed to copy executable."
    exit 1
fi

# Make it executable
chmod +x output/WWTS

echo "Build completed successfully. You can find the executable in the output directory."
echo "Run the application with: ./output/WWTS"
