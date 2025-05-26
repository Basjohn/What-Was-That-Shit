# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all necessary data files
datas = []

# Add resources directory
if os.path.exists('resources'):
    datas = [('resources', 'resources')]

# Add any additional data files (icons, images, etc.)
if os.path.exists('icons'):
    datas.append(('icons', 'icons'))

# Add any other data directories as needed
# datas.append(('path/to/additional/data', 'destination/in/app'))

a = Analysis(
    ['wwts.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'pystray._win32',
        'keyboard._winkeyboard',
        'PIL',
        'win32api',
        'win32con',
        'pystray',
        'keyboard',
        'PIL._imaging',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL._imagingtk',
        'PIL._imagingft',
        'PIL._webp'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WWTS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('resources', 'icons', 'WWTS.ico') if os.path.exists(os.path.join('resources', 'icons', 'WWTS.ico')) else None,
    version='file_version_info.txt' if os.path.exists('file_version_info.txt') else None
)

# Optional: Create a directory for additional files
# if not os.path.exists('dist/WWTS'):
#     os.makedirs('dist/WWTS')

# Copy additional files to the dist directory
# if os.path.exists('config.ini'):
#     import shutil
#     shutil.copy2('config.ini', 'dist/WWTS/')

# Add any post-build steps here
