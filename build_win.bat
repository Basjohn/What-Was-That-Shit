@echo off
setlocal enabledelayedexpansion

echo [*] Building WWTS for Windows...
echo [*] This process may take several minutes...

:: Check if running as administrator
net session >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [*] Running with administrator privileges
) else (
    echo [*] Running without administrator privileges (some operations might fail)
)

:: Check Python version
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not in PATH or not installed
    pause
    exit /b 1
)

:: Check and install/upgrade pip
echo [*] Checking pip installation...
python -m ensurepip --upgrade
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to ensure pip is installed
    pause
    exit /b 1
)

:: Install/upgrade build tools
echo [*] Installing/upgrading build tools...
python -m pip install --upgrade pip setuptools wheel
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install/upgrade build tools
    pause
    exit /b 1
)

:: Check if PyInstaller is installed
echo [*] Checking PyInstaller installation...
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [*] PyInstaller not found. Installing...
    pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install PyInstaller
        pause
        exit /b 1
    )
)

:: Clean up old build files
echo [*] Cleaning up old build files...
if exist build\ (
    echo [*] Removing old build directory...
    rmdir /s /q build
)
if exist dist\ (
    echo [*] Removing old dist directory...
    rmdir /s /q dist
)
if exist WWTS.spec (
    echo [*] Removing old spec file...
    del /q WWTS.spec
)

:: Install dependencies
echo [*] Installing dependencies...
pip install -r requirements.txt --upgrade
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

:: Verify resources
echo [*] Verifying resources...
set ICON_PATH=resources\icons\WWTS.ico
if not exist "%ICON_PATH%" (
    echo [WARNING] Icon file not found at: %ICON_PATH%
    echo [*] Attempting to create resources directory...
    mkdir "resources\icons" 2>nul
    if not exist "resources\icons" (
        echo [ERROR] Failed to create resources directory
        pause
        exit /b 1
    )
    echo [*] Please add your icon file to: %CD%\%ICON_PATH%
    pause
    exit /b 1
)

:: Build the executable
echo [*] Building the executable...
pyinstaller --noconfirm --clean --noconsole --onefile --windowed ^
    --specpath=build ^
    --distpath=dist ^
    --workpath=build\temp ^
    --icon="%ICON_PATH%" ^
    --add-data="resources;resources" ^
    --name=WWTS ^
    wwts.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Build failed. Check the build log for details.
    pause
    exit /b 1
)

:: Create output directory
echo [*] Creating output directory...
if not exist output (
    mkdir output
)

:: Copy the final executable
echo [*] Copying final executable...
if exist "dist\WWTS.exe" (
    copy /Y "dist\WWTS.exe" "output\WWTS.exe" >nul
    echo [*] Build successful! Executable is available at: %CD%\output\WWTS.exe
) else (
    echo [ERROR] Failed to find the built executable
    pause
    exit /b 1
)

echo [*] Build completed successfully!
timeout /t 5 >nul

echo Copying executable to output directory...
copy dist\WWTS.exe output\WWTS.exe
if %ERRORLEVEL% NEQ 0 (
    echo Failed to copy executable.
    exit /b 1
)

echo Build completed successfully. You can find the executable in the output directory.
echo Press any key to exit...
pause > nul
