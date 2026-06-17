import logging
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

ICON_SIZE = 64
# Linux system trays typically expect 22-24 px icons.  Rendering at full size
# and then downsampling gives better quality than rendering small directly.
_LINUX_TRAY_SIZE = 22

_COLORS = {
    "low":    "#2ecc71",  # 0–49%
    "mid":    "#f1c40f",  # 50–74%
    "high":   "#e67e22",  # 75–99%
    "over":   "#e74c3c",  # OC
    "init":   "#7f8c8d",  # loading / unknown
}


def _asset_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).parent.parent / "assets"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        _asset_dir() / "DejaVuSansMono-Bold.ttf",
    ]
    if sys.platform == "win32":
        candidates += [
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("C:/Windows/Fonts/cour.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
        ]
    else:
        candidates += [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"),
        ]

    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue

    logger.warning("No TTF font found; falling back to PIL bitmap font")
    return ImageFont.load_default()


def _pick_bg(label: str) -> str:
    if label == "OC":
        return _COLORS["over"]
    if label == "--":
        return _COLORS["init"]
    try:
        pct = int(label)
    except ValueError:
        return _COLORS["init"]
    if pct < 50:
        return _COLORS["low"]
    if pct < 75:
        return _COLORS["mid"]
    return _COLORS["high"]


def _measure(draw: ImageDraw.ImageDraw, label: str, font) -> tuple[int, int]:
    """Returns (width, height) of label rendered with font."""
    if hasattr(draw, "textbbox"):
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            pass
    if hasattr(font, "getsize"):
        try:
            return font.getsize(label)
        except Exception:
            pass
    return len(label) * 8, 12


def _best_font_size(draw: ImageDraw.ImageDraw, label: str, max_w: int, max_h: int) -> int:
    """Binary-search the largest font size where label fits within max_w × max_h."""
    lo, hi = 8, 200
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        font = _load_font(mid)
        w, h = _measure(draw, label, font)
        if w <= max_w and h <= max_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def make_icon(label: str) -> Image.Image:
    """
    Renders a 64×64 RGBA image with the given label centered on a colored background.
    label: "00"–"99", "OC", or "--" (loading).
    """
    bg = _pick_bg(label)
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), bg)
    draw = ImageDraw.Draw(img)

    # Leave a margin so the text doesn't bleed to the edge or look cut off on high-DPI scaling
    margin = 10 if sys.platform == "win32" else 15
    max_w = ICON_SIZE - margin * 2
    max_h = ICON_SIZE - margin * 2

    size = _best_font_size(draw, label, max_w, max_h)
    font = _load_font(size)

    w, h = _measure(draw, label, font)

    # Calculate starting x and y offsets
    offset_x, offset_y = 0, 0
    if hasattr(draw, "textbbox"):
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            offset_x, offset_y = bbox[0], bbox[1]
        except Exception:
            pass
    elif hasattr(font, "getoffset"):
        try:
            offset_x, offset_y = font.getoffset(label)
        except Exception:
            pass

    # Safeguard against weird font metrics offsets (preventing off-screen shift)
    if not (-20 < offset_x < 20):
        offset_x = 0
    if not (-20 < offset_y < 20):
        offset_y = 0

    x = (ICON_SIZE - w) / 2 - offset_x
    y = (ICON_SIZE - h) / 2 - offset_y

    draw.text((x, y), label, fill="white", font=font)

    if sys.platform != "win32":
        img = img.resize((_LINUX_TRAY_SIZE, _LINUX_TRAY_SIZE), Image.LANCZOS)
    return img


def set_window_icon(root) -> None:
    """Sets the window icon using assets/app_icon.png to display in taskbar/titlebar."""
    import tkinter as tk
    icon_path = _asset_dir() / "app_icon.png"
    if not icon_path.exists():
        logger.warning("Window icon file not found: %s", icon_path)
        return
    try:
        photo = tk.PhotoImage(file=str(icon_path))
        root.iconphoto(True, photo)
        root._icon_photo_ref = photo  # Keep reference to avoid garbage collection
    except Exception as e:
        logger.error("Failed to set window icon: %s", e, exc_info=True)

