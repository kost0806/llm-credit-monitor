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


def _font_candidates() -> list[Path]:
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
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"),
        ]
    return candidates


def _font_path() -> Path | None:
    """First existing TTF from the candidate list, or None if none is available."""
    for path in _font_candidates():
        if path.exists():
            return path
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _font_path()
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            logger.warning("Failed to load TTF font %s; falling back", path)

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
    w = None
    h = None
    try:
        w = round(draw.textlength(label, font=font))
    except Exception:
        pass
    try:
        bbox = draw.textbbox((0, 0), label, font=font)
        bh = bbox[3] - bbox[1]
        if bh > 0:
            h = bh
        if w is None:
            bw = bbox[2] - bbox[0]
            if bw > 0:
                w = bw
    except Exception:
        pass
    if w is not None and h is not None:
        return w, h
    if hasattr(font, "getsize"):
        try:
            gw, gh = font.getsize(label)
            if w is None:
                w = gw
            if h is None:
                h = gh
        except Exception:
            pass
    return (w if w is not None else len(label) * 8), (h if h is not None else 12)


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


def _draw_label_scaled(img: Image.Image, label: str, max_w: int, max_h: int) -> None:
    """
    Draw label using the non-scalable PIL bitmap font, enlarged to fill
    (max_w × max_h) centered on img.

    The bitmap font is a fixed ~10 px and cannot be grown via font size, so
    drawing it directly onto the 64 px canvas and then downscaling to tray size
    (Linux) makes the digits disappear.  Rendering it once and scaling the glyph
    pixels up keeps the number legible even when no TTF font is available.
    """
    font = ImageFont.load_default()
    draw = ImageDraw.Draw(img)
    try:
        bbox = draw.textbbox((0, 0), label, font=font)
        ox, oy = bbox[0], bbox[1]
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        ox, oy, w, h = 0, 0, len(label) * 6, 11

    if w <= 0 or h <= 0:
        draw.text((ICON_SIZE / 2, ICON_SIZE / 2), label, fill="white", font=font, anchor="mm")
        return

    glyph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((-ox, -oy), label, fill="white", font=font)

    scale = min(max_w / w, max_h / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    glyph = glyph.resize((nw, nh), Image.NEAREST)
    img.paste(glyph, ((ICON_SIZE - nw) // 2, (ICON_SIZE - nh) // 2), glyph)


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

    if _font_path() is not None:
        size = _best_font_size(draw, label, max_w, max_h)
        font = _load_font(size)
        draw.text((ICON_SIZE / 2, ICON_SIZE / 2), label, fill="white", font=font, anchor="mm")
    else:
        # No scalable TTF available — keep the digits visible with the bitmap font.
        _draw_label_scaled(img, label, max_w, max_h)

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

