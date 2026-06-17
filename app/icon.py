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


def _char_advance(draw: ImageDraw.ImageDraw, ch: str, font) -> float:
    """Advance width of a single glyph.

    Measured one character at a time on purpose: some PyInstaller/libfreetype
    builds under-report the advance of a *multi-character* string (returning
    roughly the first glyph's width only), which is exactly what made the tray
    icon show a single digit.  Single-glyph measurement is unaffected by that
    layout bug.
    """
    try:
        return draw.textlength(ch, font=font)
    except Exception:
        pass
    try:
        b = draw.textbbox((0, 0), ch, font=font)
        return b[2] - b[0]
    except Exception:
        pass
    if hasattr(font, "getsize"):
        try:
            return font.getsize(ch)[0]
        except Exception:
            pass
    return 8.0


def _vertical_extent(draw: ImageDraw.ImageDraw, label: str, font) -> tuple[float, float]:
    """(top, bottom) of the tallest glyph extent in label, relative to a y=0 origin."""
    tops: list[float] = []
    bottoms: list[float] = []
    for ch in label:
        try:
            b = draw.textbbox((0, 0), ch, font=font)
            tops.append(b[1])
            bottoms.append(b[3])
        except Exception:
            pass
    if tops and bottoms:
        return min(tops), max(bottoms)
    if hasattr(font, "getsize"):
        try:
            return 0.0, float(font.getsize(label)[1])
        except Exception:
            pass
    return 0.0, 12.0


def _measure(draw: ImageDraw.ImageDraw, label: str, font) -> tuple[int, int]:
    """Returns (width, height) of label rendered with font.

    Width is the sum of per-glyph advances rather than a single multi-character
    measurement, so it stays correct even where the bundled Pillow/libfreetype
    mis-reports multi-character width.
    """
    w = sum(_char_advance(draw, ch, font) for ch in label)
    top, bottom = _vertical_extent(draw, label, font)
    h = bottom - top
    if h <= 0:
        h = 12
    return round(w), round(h)


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


def _draw_centered(draw: ImageDraw.ImageDraw, label: str, font, cx: float, cy: float) -> None:
    """Draw label centered at (cx, cy), placing each glyph by hand.

    ``anchor="mm"`` centers the whole string using Pillow's internal
    multi-character layout, which is the same path that mis-reports width in
    some PyInstaller bundles — so it would push a digit off-canvas even when the
    font size is right.  Laying out each glyph from its own advance keeps the
    number centered regardless of that bug.
    """
    advances = [_char_advance(draw, ch, font) for ch in label]
    total_w = sum(advances)
    top, bottom = _vertical_extent(draw, label, font)
    # Default text anchor is "la" (left / ascender top): a glyph drawn at y has
    # its measured box at [y+top, y+bottom], so this y centers that box on cy.
    y = cy - (top + bottom) / 2
    x = cx - total_w / 2
    for ch, adv in zip(label, advances):
        draw.text((x, y), ch, fill="white", font=font)
        x += adv


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
        _draw_centered(draw, label, font, ICON_SIZE / 2, ICON_SIZE / 2)
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

