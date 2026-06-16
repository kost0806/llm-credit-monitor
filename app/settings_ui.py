"""
Settings dialog — Airbnb design system, Pretendard font.

Design tokens:
  Canvas #ffffff · Ink #222 · Muted #6a6a · Rausch #ff385c
  Hairline #ddd · Surface-soft #f7f7f7 · Body #3f3f3f
"""
import logging
import sys
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_CANVAS       = "#FFFFFF"
_SURFACE_SOFT = "#F7F7F7"
_INK          = "#222222"
_BODY         = "#3F3F3F"
_MUTED        = "#6A6A6A"
_RAUSCH       = "#FF385C"
_HAIRLINE     = "#DDDDDD"
_HAIRLINE_S   = "#EBEBEB"
_ON_RAUSCH    = "#FFFFFF"

DESKTOP_ENTRY_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=LLM Credit Monitor
Exec={exe}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""


# ── Auto-start ────────────────────────────────────────────────────────────────

def _apply_autostart(enabled: bool) -> None:
    if sys.platform == "win32":
        _autostart_windows(enabled)
    else:
        _autostart_linux(enabled)


def _autostart_windows(enabled: bool) -> None:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        name = "LLMCreditMonitor"
        if enabled:
            exe = (
                f'"{sys.executable}"'
                if getattr(sys, "frozen", False)
                else f'"{sys.executable}" "{Path(__file__).resolve().parent.parent / "app" / "main.py"}"'
            )
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.error("Auto-start (Windows) failed: %s", e)


def _autostart_linux(enabled: bool) -> None:
    try:
        path = Path.home() / ".config" / "autostart" / "llmcreditmonitor.desktop"
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            exe = (
                sys.executable
                if getattr(sys, "frozen", False)
                else f"{sys.executable} {Path(__file__).resolve().parent.parent / 'app' / 'main.py'}"
            )
            path.write_text(DESKTOP_ENTRY_TEMPLATE.format(exe=exe))
        else:
            path.unlink(missing_ok=True)
    except Exception as e:
        logger.error("Auto-start (Linux) failed: %s", e)


# ── Widget helpers ────────────────────────────────────────────────────────────

def _hairline(parent, color=_HAIRLINE, pady=(0, 0)):
    import tkinter as tk
    tk.Frame(parent, bg=color, height=1).pack(fill="x", pady=pady)


def _section_title(parent, text: str, font):
    import tkinter as tk
    tk.Label(parent, text=text, bg=_CANVAS, fg=_INK, font=font).pack(
        anchor="w", padx=0, pady=(0, 12)
    )


def _field_label(parent, text: str, font):
    import tkinter as tk
    tk.Label(parent, text=text, bg=_CANVAS, fg=_MUTED, font=font).pack(anchor="w")


def _bordered_entry(parent, textvariable, width: int, font):
    """Entry with 1px hairline border (Airbnb text-input style)."""
    import tkinter as tk
    wrap = tk.Frame(parent, bg=_HAIRLINE, padx=1, pady=1)
    entry = tk.Entry(wrap, textvariable=textvariable, width=width,
                     bg=_CANVAS, fg=_INK, insertbackground=_INK,
                     relief="flat", font=font,
                     highlightthickness=0)
    entry.pack(ipady=7)

    def _focus_in(_):
        wrap.config(bg=_INK)   # 2px ink border on focus (Airbnb spec)

    def _focus_out(_):
        wrap.config(bg=_HAIRLINE)

    entry.bind("<FocusIn>",  _focus_in)
    entry.bind("<FocusOut>", _focus_out)
    return wrap, entry


def _option_menu(parent, textvariable, values: list, font, min_width: int = 120):
    """
    Airbnb-styled OptionMenu — reliable on all platforms (no theme dependency).
    Uses tk.OptionMenu so the OS-native dropdown mechanism handles clicks.
    """
    import tkinter as tk
    # Wrapper gives the 1px hairline border look
    wrap = tk.Frame(parent, bg=_HAIRLINE, padx=1, pady=1)
    menu = tk.OptionMenu(wrap, textvariable, *values)
    menu.config(
        bg=_CANVAS, fg=_INK,
        activebackground=_SURFACE_SOFT, activeforeground=_INK,
        relief="flat", bd=0,
        highlightthickness=0,
        padx=10, pady=6,
        font=font,
        cursor="hand2",
        width=min_width,
        anchor="w",
        indicatoron=True,
    )
    menu["menu"].config(
        bg=_CANVAS, fg=_INK,
        activebackground=_SURFACE_SOFT, activeforeground=_INK,
        font=font,
        relief="flat", bd=1,
    )
    menu.pack(fill="x")
    return wrap, menu


# ── Main window ───────────────────────────────────────────────────────────────

def run_settings_window(
    config_getter: Callable,
    config_setter: Callable,
    worker,
    open_flag: threading.Event,
) -> None:
    import tkinter as tk
    from tkinter import ttk, messagebox
    from app.fonts import ui_font
    from app.presets import TIER_NAMES, CLAUDE_TIERS, CHATGPT_TIERS
    from app.icon import set_window_icon

    root = tk.Tk()
    set_window_icon(root)
    root.title("설정")
    root.configure(bg=_CANVAS)
    root.resizable(False, False)

    F = ui_font()
    FONT_DISPLAY = (F, 15, "bold")
    FONT_TITLE   = (F, 11, "bold")
    FONT_BODY    = (F, 10)
    FONT_BODY_SM = (F, 9)
    FONT_CAPTION = (F, 9, "bold")

    # ttk style — only for Checkbutton; no theme_use() to keep native combobox working
    style = ttk.Style(root)
    style.configure("AB.TCheckbutton",
                    background=_CANVAS, foreground=_BODY, font=FONT_BODY)
    style.map("AB.TCheckbutton",
              background=[("active", _CANVAS)],
              foreground=[("active", _INK)])

    def _close():
        root.destroy()
        open_flag.clear()

    root.protocol("WM_DELETE_WINDOW", _close)

    cfg = config_getter()
    W = 440   # window width in pixels; use as reference for padx

    # ── Title bar ──────────────────────────────────────────────────────────────
    title_bar = tk.Frame(root, bg=_CANVAS, height=56)
    title_bar.pack(fill="x")
    title_bar.pack_propagate(False)
    tk.Label(title_bar, text="설정",
             bg=_CANVAS, fg=_INK, font=FONT_DISPLAY, padx=24).pack(
        side="left", fill="y"
    )
    _hairline(root)

    # Outer content padding
    body = tk.Frame(root, bg=_CANVAS, padx=24, pady=0)
    body.pack(fill="both", expand=True)

    # ── Claude section ─────────────────────────────────────────────────────────
    tk.Frame(body, bg=_CANVAS, height=20).pack()   # spacer
    _section_title(body, "Claude", FONT_TITLE)

    claude_row = tk.Frame(body, bg=_CANVAS)
    claude_row.pack(fill="x", pady=(0, 4))

    # Tier
    tier_col = tk.Frame(claude_row, bg=_CANVAS)
    tier_col.pack(side="left", padx=(0, 20))
    _field_label(tier_col, "티어", FONT_CAPTION)
    claude_tier_var = tk.StringVar(value=cfg.claude_tier)
    claude_limit_var = tk.StringVar(value=f"{cfg.claude_limit:.2f}")  # defined here for trace

    def _on_claude_tier(*_):
        claude_limit_var.set(f"{CLAUDE_TIERS.get(claude_tier_var.get(), 5000.0):.2f}")

    claude_tier_var.trace_add("write", _on_claude_tier)   # fires on any change, not just <<ComboboxSelected>>
    claude_tier_wrap, _ = _option_menu(tier_col, claude_tier_var, TIER_NAMES, FONT_BODY_SM, min_width=10)
    claude_tier_wrap.pack(anchor="w", pady=(4, 0))

    # Limit
    limit_col = tk.Frame(claude_row, bg=_CANVAS)
    limit_col.pack(side="left")
    _field_label(limit_col, "월 크레딧 한도 (USD)", FONT_CAPTION)
    claude_wrap, claude_entry = _bordered_entry(limit_col, claude_limit_var, 12, FONT_BODY_SM)
    claude_wrap.pack(anchor="w", pady=(4, 0))

    _hairline(body, pady=(16, 0))

    # ── ChatGPT section ────────────────────────────────────────────────────────
    tk.Frame(body, bg=_CANVAS, height=16).pack()
    _section_title(body, "ChatGPT", FONT_TITLE)

    chatgpt_row = tk.Frame(body, bg=_CANVAS)
    chatgpt_row.pack(fill="x", pady=(0, 4))

    tier_col2 = tk.Frame(chatgpt_row, bg=_CANVAS)
    tier_col2.pack(side="left", padx=(0, 20))
    _field_label(tier_col2, "티어", FONT_CAPTION)
    chatgpt_tier_var = tk.StringVar(value=cfg.chatgpt_tier)
    chatgpt_limit_var = tk.StringVar(value=f"{cfg.chatgpt_limit:.2f}")

    def _on_chatgpt_tier(*_):
        chatgpt_limit_var.set(f"{CHATGPT_TIERS.get(chatgpt_tier_var.get(), 5000.0):.2f}")

    chatgpt_tier_var.trace_add("write", _on_chatgpt_tier)
    chatgpt_tier_wrap, _ = _option_menu(tier_col2, chatgpt_tier_var, TIER_NAMES, FONT_BODY_SM, min_width=10)
    chatgpt_tier_wrap.pack(anchor="w", pady=(4, 0))

    limit_col2 = tk.Frame(chatgpt_row, bg=_CANVAS)
    limit_col2.pack(side="left")
    _field_label(limit_col2, "월 크레딧 한도 (USD)", FONT_CAPTION)
    chatgpt_wrap, chatgpt_entry = _bordered_entry(limit_col2, chatgpt_limit_var, 12, FONT_BODY_SM)
    chatgpt_wrap.pack(anchor="w", pady=(4, 0))

    _hairline(body, pady=(16, 0))

    # ── Update interval ────────────────────────────────────────────────────────
    tk.Frame(body, bg=_CANVAS, height=16).pack()
    _section_title(body, "업데이트 주기", FONT_TITLE)

    interval_row = tk.Frame(body, bg=_CANVAS)
    interval_row.pack(fill="x")

    interval_var = tk.StringVar(value=str(cfg.update_interval))

    vcmd = (root.register(lambda s: s.isdigit() or s == ""), "%P")

    tk.Label(interval_row, text="주기 (초):", bg=_CANVAS, fg=_INK,
             font=FONT_BODY).pack(side="left")

    interval_entry = tk.Entry(
        interval_row, textvariable=interval_var,
        width=6, font=FONT_BODY,
        bg=_CANVAS, fg=_INK, insertbackground=_INK,
        relief="solid", bd=1,
        validate="key", validatecommand=vcmd,
    )
    interval_entry.pack(side="left", padx=(8, 4))

    tk.Label(interval_row, text="초  (10~600)", bg=_CANVAS, fg=_MUTED,
             font=FONT_BODY).pack(side="left")

    _hairline(body, pady=(16, 0))

    # ── Auto-start ─────────────────────────────────────────────────────────────
    tk.Frame(body, bg=_CANVAS, height=4).pack()
    autostart_var = tk.BooleanVar(value=cfg.auto_start)
    ttk.Checkbutton(body, text="로그인 시 자동 시작",
                    variable=autostart_var,
                    style="AB.TCheckbutton").pack(anchor="w", pady=12)

    _hairline(root)

    # ── Action buttons ─────────────────────────────────────────────────────────
    btn_bar = tk.Frame(root, bg=_CANVAS, padx=24, pady=16)
    btn_bar.pack(fill="x")

    def _save():
        try:
            c_limit = float(claude_limit_var.get())
            g_limit = float(chatgpt_limit_var.get())
        except ValueError:
            messagebox.showerror("입력 오류", "한도는 숫자로 입력해 주세요.", parent=root)
            return
        if c_limit <= 0 or g_limit <= 0:
            messagebox.showerror("입력 오류", "한도는 0보다 커야 합니다.", parent=root)
            return

        from app.config import AppConfig
        new_cfg = AppConfig(
            claude_tier=claude_tier_var.get(),
            claude_limit=c_limit,
            chatgpt_tier=chatgpt_tier_var.get(),
            chatgpt_limit=g_limit,
            update_interval=max(10, min(600, int(interval_var.get()) if interval_var.get().isdigit() else 60)),
            auto_start=autostart_var.get(),
        )
        config_setter(new_cfg)
        _apply_autostart(new_cfg.auto_start)
        worker.request_refresh()
        root.after(0, _close)   # schedule destroy outside the button callback to avoid tk crash

    # Rausch Save — right-aligned; Cancel to its left
    save_btn = tk.Button(
        btn_bar, text="저장", command=_save,
        bg=_RAUSCH, fg=_ON_RAUSCH,
        activebackground="#E00B41", activeforeground=_ON_RAUSCH,
        relief="flat", bd=0, padx=24, pady=10,
        font=(F, 10, "bold"), cursor="hand2",
    )
    save_btn.pack(side="right", padx=(8, 0))

    cancel_btn = tk.Button(
        btn_bar, text="취소", command=_close,
        bg=_CANVAS, fg=_INK,
        activebackground=_SURFACE_SOFT, activeforeground=_INK,
        relief="solid", bd=1,
        highlightbackground=_HAIRLINE, highlightthickness=1,
        padx=24, pady=10,
        font=(F, 10), cursor="hand2",
    )
    cancel_btn.pack(side="right")

    # Centre the window on screen
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    root.mainloop()
