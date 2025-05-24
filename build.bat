@echo off
echo [*] Building single-file WWTS executable...

:: Install required packages if not present
pip install pyinstaller PyQt5 pystray keyboard pillow pywin32

:: Clean previous build
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
if exist "WWTS.spec" del /q "WWTS.spec"

:: Build single executable
echo [*] Creating single executable...
pyinstaller --noconfirm --onefile --windowed ^
    --name "WWTS" ^
    --icon "resources/icons/WWTS.ico" ^
    --add-binary "resources/icons/WWTS.ico;." ^
    --add-data "resources;resources" ^
    --hidden-import PyQt5.QtCore ^
    --hidden-import PyQt5.QtGui ^
    --hidden-import PyQt5.QtWidgets ^
    --hidden-import pystray._win32 ^
    --hidden-import keyboard ^
    --hidden-import PIL ^
    wwts.py

if %ERRORLEVEL% EQU 0 (
    echo [*] Build successful!
    echo [*] Single executable: dist\WWTS.exe
) else (
    echo [*] Build failed with error code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
