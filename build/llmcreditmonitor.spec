# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['../app/main.py'],
    pathex=[str(Path('..').resolve())],
    binaries=[],
    datas=[
        ('../core/ccusage.py', 'core'),
        ('../core/ccusage_pricing.py', 'core'),
        ('../core/ccusage_db.py', 'core'),
        ('../assets', 'assets'),
    ],
    hiddenimports=[
        'ccusage',
        'ccusage_pricing',
        'ccusage_db',
        'app',
        'app.config',
        'app.presets',
        'app.worker',
        'app.icon',
        'app.tray',
        'app.settings_ui',
        'app.details_ui',
        'pystray._win32',
        'pystray._xorg',
        'pystray._darwin',
        'pystray._appindicator',
        'PIL._tkinter_finder',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends._backend_tk',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'wx', 'PySide2', 'PySide6'],
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
    name='LLMCreditMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../assets/tray_icon.ico' if sys.platform == 'win32' else None,
)
