"""
Font utilities for Pretendard loading across tkinter and matplotlib.

Usage:
  1. Call load_pretendard() once before any Tk() root is created.
  2. Call ui_font() inside a window function (after Tk() exists) to get the
     best available font name.
  3. Call configure_mpl_font() inside a details thread to set matplotlib font.
"""
import logging
import sys
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_NAME = "Pretendard"
_FALLBACKS_WIN   = ["Malgun Gothic", "맑은 고딕", "Arial Unicode MS", "Arial", "DejaVu Sans"]
_FALLBACKS_LINUX = ["NanumGothic", "Noto Sans KR", "Noto CJK KR", "UnDotum", "DejaVu Sans"]


def _asset_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).parent.parent / "assets"


def load_pretendard() -> bool:
    """
    Register Pretendard TTF files from assets/ with the OS so that tkinter
    and matplotlib can reference the font by name.
    Call once at startup, before any Tk() root is created.
    """
    asset_dir = _asset_dir()
    font_files = sorted(asset_dir.glob("Pretendard*.ttf"))
    if not font_files:
        logger.debug("No Pretendard font files found in %s", asset_dir)
        return False

    if sys.platform == "win32":
        return _load_windows(font_files)
    else:
        return _load_linux(font_files)


def _load_windows(font_files: list[Path]) -> bool:
    try:
        import ctypes
        loaded = 0
        for p in font_files:
            if ctypes.windll.gdi32.AddFontResourceExW(str(p), 0x10, 0) > 0:
                loaded += 1
        if loaded:
            # Broadcast font-change so running apps (including this process) see it
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
            logger.debug("Loaded %d Pretendard files (Windows)", loaded)
        return loaded > 0
    except Exception as e:
        logger.warning("Pretendard Windows load failed: %s", e)
        return False


def _load_linux(font_files: list[Path]) -> bool:
    try:
        import shutil, subprocess
        fonts_dir = Path.home() / ".local" / "share" / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        for p in font_files:
            shutil.copy(p, fonts_dir / p.name)
        subprocess.run(["fc-cache", "-f", str(fonts_dir)],
                       capture_output=True, timeout=15)
        logger.debug("Copied %d Pretendard files to ~/.local/share/fonts", len(font_files))
        return True
    except Exception as e:
        logger.warning("Pretendard Linux load failed: %s", e)
        return False


@lru_cache(maxsize=None)
def ui_font() -> str:
    """
    Return the best available font name for tkinter.
    Must be called AFTER a Tk() root exists so tkinter.font.families() is populated.
    Result is cached after the first successful call.
    """
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families())
    except Exception:
        available = set()

    if _NAME in available:
        logger.debug("UI font: %s", _NAME)
        return _NAME

    fallbacks = _FALLBACKS_WIN if sys.platform == "win32" else _FALLBACKS_LINUX
    for name in fallbacks:
        if name in available:
            logger.debug("UI font (fallback): %s", name)
            return name

    logger.warning("No suitable Korean font found; using system default")
    return "TkDefaultFont"


def configure_mpl_font() -> None:
    """
    Set Pretendard (or best fallback) for matplotlib and fix unicode minus.
    Call inside the details window thread, after matplotlib.use() but before
    importing pyplot.
    """
    import os
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    # Directly register font files so matplotlib sees them without fc-cache
    for p in _asset_dir().glob("Pretendard*.ttf"):
        fm.fontManager.addfont(str(p))

    # Windows: also try loading malgun directly into fontManager
    if sys.platform == "win32":
        for p in [Path("C:/Windows/Fonts/malgun.ttf"),
                  Path("C:/Windows/Fonts/malgunbd.ttf")]:
            if p.exists():
                fm.fontManager.addfont(str(p))

    available = {f.name for f in fm.fontManager.ttflist}

    # DejaVu Sans is always bundled with matplotlib — set it first as a safe base
    plt.rcParams["font.family"] = "DejaVu Sans"

    candidates = [_NAME] + (
        _FALLBACKS_WIN if sys.platform == "win32" else _FALLBACKS_LINUX
    )
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            logger.debug("matplotlib font: %s", name)
            break
    else:
        logger.debug("No Korean font found; using DejaVu Sans")

    plt.rcParams["axes.unicode_minus"] = False
