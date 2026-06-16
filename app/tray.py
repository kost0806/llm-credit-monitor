import logging
import threading
import time
from typing import Callable, Optional

import pystray
from pystray import MenuItem, Menu

from app.icon import make_icon
from app.worker import UsageSnapshot, UsageWorker

logger = logging.getLogger(__name__)


def _bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def _format_tooltip(snapshot: UsageSnapshot) -> str:
    c = snapshot.claude
    g = snapshot.chatgpt
    err = f"\n[!] {snapshot.error}" if snapshot.error else ""
    return (
        f"[Claude]  ${c.today_usd:.2f} / ${c.monthly_usd:.2f} / ${c.remaining_usd:.2f}\n"
        f"[ChatGPT] ${g.today_usd:.2f} / ${g.monthly_usd:.2f} / ${g.remaining_usd:.2f}"
        f"{err}"
    )


def _menu_claude_header(snapshot: Optional[UsageSnapshot]) -> str:
    if snapshot is None:
        return "Claude   ░░░░░░░░░░   —"
    pct = snapshot.claude.percent_of_limit
    return f"Claude   {_bar(pct)}  {pct:5.1f}%"


def _menu_claude_detail(snapshot: Optional[UsageSnapshot]) -> str:
    if snapshot is None:
        return "  불러오는 중..."
    c = snapshot.claude
    return f"  오늘 ${c.today_usd:.2f}  이번달 ${c.monthly_usd:.2f} / ${c.limit_usd:.2f}  잔여 ${c.remaining_usd:.2f}"


def _menu_chatgpt_header(snapshot: Optional[UsageSnapshot]) -> str:
    if snapshot is None:
        return "ChatGPT  ░░░░░░░░░░   —"
    pct = snapshot.chatgpt.percent_of_limit
    return f"ChatGPT  {_bar(pct)}  {pct:5.1f}%"


def _menu_chatgpt_detail(snapshot: Optional[UsageSnapshot]) -> str:
    if snapshot is None:
        return "  불러오는 중..."
    g = snapshot.chatgpt
    return f"  오늘 ${g.today_usd:.2f}  이번달 ${g.monthly_usd:.2f} / ${g.limit_usd:.2f}  잔여 ${g.remaining_usd:.2f}"


class TrayApp:
    def __init__(
        self,
        worker: UsageWorker,
        config_getter: Callable,
        config_setter: Callable,
    ):
        self._worker = worker
        self._config_getter = config_getter
        self._config_setter = config_setter
        self._icon: Optional[pystray.Icon] = None

        self._settings_open = threading.Event()
        self._details_open = threading.Event()

        self._last_label: str = "--"

    def run(self) -> None:
        """Blocking. Must be called from the main thread."""
        initial_image = make_icon("--")
        self._icon = pystray.Icon(
            "LLMCreditMonitor",
            icon=initial_image,
            title="LLM Credit Monitor — 불러오는 중...",
            menu=self._build_menu(),
        )
        update_thread = threading.Thread(
            target=self._update_loop, name="IconUpdater", daemon=True
        )
        update_thread.start()
        logger.debug("Starting pystray icon")
        self._icon.run()

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self) -> Menu:
        return Menu(
            MenuItem(lambda item: _menu_claude_header(self._worker.get_snapshot()), None, enabled=False),
            MenuItem(lambda item: _menu_claude_detail(self._worker.get_snapshot()), None, enabled=False),
            MenuItem(lambda item: _menu_chatgpt_header(self._worker.get_snapshot()), None, enabled=False),
            MenuItem(lambda item: _menu_chatgpt_detail(self._worker.get_snapshot()), None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("갱신 (Refresh)", self._on_refresh),
            MenuItem("설정 (Settings)", self._on_settings),
            MenuItem("자세히 보기 (Details)", self._on_details),
            Menu.SEPARATOR,
            MenuItem("종료 (Exit)", self._on_exit),
        )

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_refresh(self, icon, item) -> None:
        logger.debug("Manual refresh requested")
        self._worker.request_refresh()

    def _on_settings(self, icon, item) -> None:
        if self._settings_open.is_set():
            logger.debug("Settings window already open")
            return
        self._settings_open.set()
        t = threading.Thread(
            target=self._run_settings,
            name="SettingsUI",
            daemon=True,
        )
        t.start()

    def _on_details(self, icon, item) -> None:
        if self._details_open.is_set():
            logger.debug("Details window already open")
            return
        self._details_open.set()
        t = threading.Thread(
            target=self._run_details,
            name="DetailsUI",
            daemon=True,
        )
        t.start()

    def _on_exit(self, icon, item) -> None:
        logger.debug("Exit requested")
        self._worker.stop()
        icon.stop()

    # ── Window launchers ─────────────────────────────────────────────────────

    def _run_settings(self) -> None:
        from app.settings_ui import run_settings_window
        try:
            run_settings_window(
                self._config_getter,
                self._config_setter,
                self._worker,
                self._settings_open,
            )
        except Exception as e:
            logger.error("Settings window error: %s", e, exc_info=True)
            self._settings_open.clear()

    def _run_details(self) -> None:
        from app.details_ui import run_details_window
        try:
            run_details_window(self._worker, self._details_open)
        except Exception as e:
            logger.error("Details window error: %s", e, exc_info=True)
            self._details_open.clear()

    # ── Icon update loop ──────────────────────────────────────────────────────

    def _update_loop(self) -> None:
        while self._icon is not None:
            snapshot = self._worker.get_snapshot()
            if snapshot is not None:
                label = snapshot.icon_label
                if label != self._last_label:
                    logger.debug("[ICON] %s → %s", self._last_label, label)
                    self._last_label = label
                    try:
                        self._icon.icon = make_icon(label)
                    except Exception as e:
                        logger.warning("Icon update failed: %s", e)
                try:
                    self._icon.title = _format_tooltip(snapshot)
                except Exception:
                    pass
            time.sleep(1)
