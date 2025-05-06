@echo off
echo Building WWTS for Windows...

REM Check if PyInstaller is installed
pip show pyinstaller > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller is not installed. Installing...
    pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install PyInstaller. Please install it manually.
        exit /b 1
    )
)

echo Cleaning up old build files...
if exist build\ rmdir /s /q build
if exist dist\ rmdir /s /q dist
if exist WWTS.spec del WWTS.spec

echo Installing dependencies...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies. Please check requirements.txt
    exit /b 1
)

echo Building the executable...
REM Use the proper icon path from resources directory
set ICON_PATH=resources\icons\WWTS.ico

if not exist %ICON_PATH% (
    echo Error: Icon file %ICON_PATH% not found!
    exit /b 1
)

pyinstaller --noconfirm --onefile --windowed --icon=%ICON_PATH% ^
    --add-data="resources;resources" ^
    --hidden-import=PIL ^
    --hidden-import=win32api ^
    --hidden-import=keyboard ^
    --hidden-import=pystray ^
    --name=WWTS ^
    wwts.py

if %ERRORLEVEL% NEQ 0 (
    echo Build failed.
    exit /b 1
)

echo Creating output directory...
if not exist output\ mkdir output

echo Copying executable to output directory...
copy dist\WWTS.exe output\WWTS.exe
if %ERRORLEVEL% NEQ 0 (
    echo Failed to copy executable.
    exit /b 1
)

echo Build completed successfully. You can find the executable in the output directory.
echo Press any key to exit...
pause > nul
