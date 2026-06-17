"""
Details dashboard — Airbnb design system, Pretendard font.

Design tokens sourced from DESIGN.md:
  Canvas   #ffffff · Ink #222222 · Body #3f3f3f · Muted #6a6a6a
  Rausch   #ff385c (active tab indicator, totals highlight)
  Hairline #dddddd · Hairline-soft #ebebeb
  Surface-soft #f7f7f7
  Shadow: rgba(0,0,0,.02) 0 0 0 1px, rgba(0,0,0,.04) 0 2px 6px,
          rgba(0,0,0,.1) 0 4px 8px  → simulated with 1px border + offset frame
  Spacing base 8px, body-sm 14px/400, title-md 16px/600, display-sm 20px/600
"""
import logging
import threading
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# ── Airbnb design tokens ──────────────────────────────────────────────────────
_CANVAS       = "#FFFFFF"
_SURFACE_SOFT = "#F7F7F7"
_INK          = "#222222"
_BODY         = "#3F3F3F"
_MUTED        = "#6A6A6A"
_RAUSCH       = "#FF385C"
_HAIRLINE     = "#DDDDDD"
_HAIRLINE_S   = "#EBEBEB"
_ON_RAUSCH    = "#FFFFFF"

# Brand colours per provider
_BAR_CLAUDE  = "#FF385C"   # Rausch — Claude
_BAR_CHATGPT = "#222222"   # Ink    — ChatGPT


def _get_period_dates(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "이번 달":
        return today.replace(day=1), today
    elif period == "지난 달":
        first = today.replace(day=1)
        last = first - timedelta(days=1)
        return last.replace(day=1), last
    else:  # 최근 30일
        return today - timedelta(days=29), today


# ── Reusable widget helpers ───────────────────────────────────────────────────

def _hairline(parent, *, color=_HAIRLINE, padx=0, pady=(0, 0)):
    import tkinter as tk
    sep = tk.Frame(parent, bg=color, height=1)
    sep.pack(fill="x", padx=padx, pady=pady)


def _card(parent, *, padx: int = 16, pady: int = 16):
    import tkinter as tk
    shadow = tk.Frame(parent, bg="#E0E0E0")
    border = tk.Frame(shadow, bg=_HAIRLINE, padx=1, pady=1)
    border.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
    surface = tk.Frame(border, bg=_CANVAS, padx=padx, pady=pady)
    surface.pack(fill="both", expand=True)
    return shadow, surface


# ── Main window ───────────────────────────────────────────────────────────────

def run_details_window(worker, open_flag: threading.Event) -> None:
    import tkinter as tk
    from tkinter import ttk
    from app.fonts import ui_font, configure_mpl_font

    import matplotlib
    matplotlib.use("TkAgg")
    configure_mpl_font()

    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.ticker import FuncFormatter
    import numpy as np

    root = tk.Tk()
    from app.icon import set_window_icon
    set_window_icon(root)
    root.title("자세히 보기")
    root.geometry("960x680")
    root.configure(bg=_CANVAS)
    root.minsize(720, 540)

    F            = ui_font()
    FONT_DISPLAY = (F, 18, "bold")
    FONT_TITLE   = (F, 11, "bold")
    FONT_BODY    = (F, 10)
    FONT_BODY_SM = (F, 9)
    FONT_CAPTION = (F, 9, "bold")

    def _close():
        plt.close("all")
        root.destroy()
        open_flag.clear()

    root.protocol("WM_DELETE_WINDOW", _close)

    # ── ttk styles ─────────────────────────────────────────────────────────────
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure("AB.Treeview",
                    background=_CANVAS, foreground=_BODY,
                    fieldbackground=_CANVAS, rowheight=30, font=FONT_BODY_SM)
    style.configure("AB.Treeview.Heading",
                    background=_SURFACE_SOFT, foreground=_INK,
                    relief="flat", font=FONT_CAPTION)
    style.map("AB.Treeview",
              background=[("selected", "#FFF0F3")],
              foreground=[("selected", _INK)])
    style.configure("AB.TCombobox",
                    fieldbackground=_CANVAS, background=_CANVAS,
                    foreground=_INK, selectbackground=_SURFACE_SOFT,
                    relief="flat")

    # ── Title bar ──────────────────────────────────────────────────────────────
    title_bar = tk.Frame(root, bg=_CANVAS, height=64)
    title_bar.pack(fill="x")
    title_bar.pack_propagate(False)
    tk.Label(title_bar, text="자세히 보기",
             bg=_CANVAS, fg=_INK, font=FONT_DISPLAY,
             padx=24).pack(side="left", fill="y")
    _hairline(root)

    # ── Toolbar ────────────────────────────────────────────────────────────────
    PERIODS = ["이번 달", "지난 달", "최근 30일"]
    toolbar = tk.Frame(root, bg=_CANVAS)
    toolbar.pack(fill="x", padx=24, pady=(16, 8))

    tk.Label(toolbar, text="기간", bg=_CANVAS, fg=_MUTED,
             font=FONT_CAPTION).pack(side="left")
    period_var = tk.StringVar(value=PERIODS[0])
    period_cb = ttk.Combobox(toolbar, textvariable=period_var,
                              values=PERIODS, state="readonly", width=9,
                              style="AB.TCombobox", font=FONT_BODY_SM)
    period_cb.pack(side="left", padx=(6, 0))

    status_var = tk.StringVar(value="불러오는 중…")
    tk.Label(toolbar, textvariable=status_var, bg=_CANVAS, fg=_MUTED,
             font=FONT_BODY_SM).pack(side="left", padx=16)

    # ── Chart card ─────────────────────────────────────────────────────────────
    chart_shadow, chart_surface = _card(root, padx=16, pady=12)
    chart_shadow.pack(fill="x", padx=24, pady=(0, 12))

    chart_header = tk.Frame(chart_surface, bg=_CANVAS)
    chart_header.pack(fill="x", anchor="w")
    tk.Label(chart_header, text="일별 사용량",
             bg=_CANVAS, fg=_MUTED, font=FONT_CAPTION).pack(side="left")

    # Legend chips
    for color, label in ((_BAR_CLAUDE, "Claude"), (_BAR_CHATGPT, "ChatGPT")):
        chip = tk.Frame(chart_header, bg=color, width=10, height=10)
        chip.pack(side="right", padx=(0, 2), pady=3)
        chip.pack_propagate(False)
        tk.Label(chart_header, text=label, bg=_CANVAS, fg=_MUTED,
                 font=FONT_BODY_SM).pack(side="right", padx=(8, 2))

    fig, ax = plt.subplots(figsize=(8.8, 2.6), dpi=72,
                           constrained_layout=True)
    fig.patch.set_facecolor(_CANVAS)
    ax.set_facecolor(_CANVAS)

    canvas = FigureCanvasTkAgg(fig, master=chart_surface)
    canvas.get_tk_widget().pack(fill="both", expand=True, pady=(6, 0))

    # ── Model table card ───────────────────────────────────────────────────────
    table_shadow, table_surface = _card(root, padx=16, pady=12)
    table_shadow.pack(fill="both", expand=True, padx=24, pady=(0, 24))

    tk.Label(table_surface, text="모델별 사용량",
             bg=_CANVAS, fg=_MUTED, font=FONT_CAPTION).pack(anchor="w")

    cols    = ("제공사", "모델", "입력 토큰", "출력 토큰", "캐시 읽기", "비용 (USD)")
    col_w   = [80, 210, 110, 110, 110, 120]
    col_anc = ["w", "w", "e", "e", "e", "e"]

    table_wrap = tk.Frame(table_surface, bg=_CANVAS)
    table_wrap.pack(fill="both", expand=True, pady=(8, 0))

    tree = ttk.Treeview(table_wrap, columns=cols, show="headings",
                         height=7, style="AB.Treeview", selectmode="browse")
    for col, w, anc in zip(cols, col_w, col_anc):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor=anc, stretch=(col == "모델"))

    tree.tag_configure("odd",  background=_CANVAS)
    tree.tag_configure("even", background=_SURFACE_SOFT)

    vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    # ── Render helpers ─────────────────────────────────────────────────────────

    def _render_chart(claude_daily: dict, chatgpt_daily: dict, start: date, end: date):
        ax.clear()
        ax.set_facecolor(_CANVAS)

        all_days = sorted(set(claude_daily) | set(chatgpt_daily))
        claude_vals  = [claude_daily.get(d, 0.0)  for d in all_days]
        chatgpt_vals = [chatgpt_daily.get(d, 0.0) for d in all_days]

        if not all_days or (all(v == 0 for v in claude_vals) and
                            all(v == 0 for v in chatgpt_vals)):
            ax.text(0.5, 0.5, "사용 데이터가 없습니다",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=10, color=_MUTED)
        else:
            n   = len(all_days)
            xs  = np.arange(n)
            bw  = 0.38   # bar half-width

            ax.bar(xs - bw / 2, claude_vals,  width=bw, color=_BAR_CLAUDE,  zorder=3, label="Claude")
            ax.bar(xs + bw / 2, chatgpt_vals, width=bw, color=_BAR_CHATGPT, zorder=3, label="ChatGPT")

            max_val = max(max(claude_vals), max(chatgpt_vals), 0.001)
            if n <= 16:
                for x, cv, gv in zip(xs, claude_vals, chatgpt_vals):
                    if cv > 0:
                        ax.text(x - bw / 2, cv + max_val * 0.025, f"${cv:.2f}",
                                ha="center", va="bottom", fontsize=5.5, color=_MUTED)
                    if gv > 0:
                        ax.text(x + bw / 2, gv + max_val * 0.025, f"${gv:.2f}",
                                ha="center", va="bottom", fontsize=5.5, color=_MUTED)

            step = max(1, n // 10)
            ax.set_xticks(xs[::step])
            ax.set_xticklabels([all_days[i][5:] for i in range(0, n, step)],
                                rotation=30, ha="right", fontsize=7.5, color=_MUTED)
            ax.tick_params(axis="y", labelsize=7.5, colors=_MUTED)
            ax.tick_params(axis="x", colors=_MUTED)
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.2f}"))

            for spine in ax.spines.values():
                spine.set_color(_HAIRLINE)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.set_axisbelow(True)
            ax.yaxis.grid(True, color=_HAIRLINE_S, linewidth=0.8)
            ax.set_xlim(-0.5, n - 0.5)
            ax.margins(y=0.18)

        fig.tight_layout(pad=1.0)
        try:
            canvas.draw()
        except RuntimeError as e:
            logger.warning("Chart render failed: %s", e)

    def _render_table(claude_models: dict, chatgpt_models: dict):
        for item in tree.get_children():
            tree.delete(item)

        rows = []
        for model, s in claude_models.items():
            rows.append(("Claude", model, s))
        for model, s in chatgpt_models.items():
            rows.append(("ChatGPT", model, s))

        if not rows:
            tree.insert("", "end",
                        values=("–", "(데이터 없음)", "–", "–", "–", "–"),
                        tags=("odd",))
            return

        rows.sort(key=lambda r: -r[2].get("cost", 0))
        for i, (provider, model, s) in enumerate(rows):
            tree.insert("", "end", values=(
                provider,
                model,
                f"{s.get('input_tokens', 0):,}",
                f"{s.get('output_tokens', 0):,}",
                f"{s.get('cache_read_tokens', 0):,}",
                f"${s.get('cost', 0.0):.4f}",
            ), tags=("even" if i % 2 == 0 else "odd",))

    # ── Async fetch ────────────────────────────────────────────────────────────

    def _fetch(period: str):
        start, end = _get_period_dates(period)
        try:
            claude_daily   = worker.get_period_daily_totals("claude",   start, end)
            chatgpt_daily  = worker.get_period_daily_totals("chatgpt",  start, end)
            claude_models  = worker.get_period_model_breakdown("claude",  start, end)
            chatgpt_models = worker.get_period_model_breakdown("chatgpt", start, end)

            total_c = sum(claude_daily.values())
            total_g = sum(chatgpt_daily.values())
            total   = total_c + total_g

            root.after(0, lambda: _render_chart(claude_daily, chatgpt_daily, start, end))
            root.after(0, lambda: _render_table(claude_models, chatgpt_models))
            root.after(0, lambda: status_var.set(
                f"Claude ${total_c:.4f}  +  ChatGPT ${total_g:.4f}  =  합계 ${total:.4f}  ·  {start} ~ {end}"
            ))
        except Exception as e:
            logger.error("Details fetch error: %s", e, exc_info=True)
            root.after(0, lambda: status_var.set(f"오류: {e}"))

    def _load(period: str):
        status_var.set("불러오는 중…")
        threading.Thread(target=_fetch, args=(period,), daemon=True).start()

    period_cb.bind("<<ComboboxSelected>>", lambda _: _load(period_var.get()))
    _load(period_var.get())

    root.mainloop()
