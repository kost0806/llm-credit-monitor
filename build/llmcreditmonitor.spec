# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None


def _tray_font() -> str | None:
    """
    Locate a scalable DejaVuSansMono-Bold.ttf to bundle as the tray-icon font.

    The tray icon draws the usage percentage with this font; without a scalable
    TTF, app/icon.py falls back to PIL's fixed bitmap font, which becomes
    invisible after the Linux tray downscale.  Resolve it from a source that is
    guaranteed to exist at build time so every build (standalone, .deb, Windows)
    bundles it regardless of build order or the host's system fonts:
      1. assets/ (e.g. copied by build_linux.sh)
      2. matplotlib's bundled copy (matplotlib is a hard dependency)
      3. common system font paths
    """
    candidates = [Path('../assets/DejaVuSansMono-Bold.ttf')]
    try:
        import matplotlib
        candidates.append(
            Path(matplotlib.get_data_path()) / 'fonts' / 'ttf' / 'DejaVuSansMono-Bold.ttf'
        )
    except Exception:
        pass
    candidates += [
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'),
        Path('/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf'),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


_datas = [
    ('../core/ccusage.py', 'core'),
    ('../core/ccusage_pricing.py', 'core'),
    ('../core/ccusage_db.py', 'core'),
    ('../assets', 'assets'),
]

_font = _tray_font()
if _font:
    # Place it directly under assets/ so app/icon._font_path() finds it first.
    _datas.append((_font, 'assets'))
else:
    print('WARNING: DejaVuSansMono-Bold.ttf not found; tray icon will use the '
          'bitmap-font fallback', file=sys.stderr)

a = Analysis(
    ['../app/main.py'],
    pathex=[str(Path('..').resolve())],
    binaries=[],
    datas=_datas,
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
        # pystray backends — all three included; PyInstaller silently skips unavailable ones
        'pystray._win32',
        'pystray._darwin',
        'pystray._xorg',
        'pystray._appindicator',  # AppIndicator3 / AyatanaAppIndicator3 (Linux GTK tray)
        'pystray._gtk',
        # gi.repository — needed by pystray._appindicator on Linux
        'gi',
        'gi.repository.GLib',
        'gi.repository.GObject',
        'gi.repository.Gtk',
        'gi.repository.Gdk',
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
