import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path


def setup_core_path() -> None:
    """Add core/ to sys.path so ccusage imports work in both dev and frozen modes."""
    if getattr(sys, "frozen", False):
        core_dir = Path(sys._MEIPASS) / "core"
    else:
        core_dir = Path(__file__).resolve().parent.parent / "core"
    if str(core_dir) not in sys.path:
        sys.path.insert(0, str(core_dir))


def _headless_loop(worker, config_getter) -> None:
    """Headless mode: print snapshots to stdout without launching a tray."""
    print("Running in headless mode. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            snapshot = worker.get_snapshot()
            if snapshot:
                cfg = config_getter()
                print(
                    f"[{snapshot.fetched_at.strftime('%H:%M:%S')}] "
                    f"Claude: today=${snapshot.claude.today_usd:.4f} "
                    f"monthly=${snapshot.claude.monthly_usd:.4f} "
                    f"limit=${cfg.claude_limit:.2f} | "
                    f"ChatGPT: today=${snapshot.chatgpt.today_usd:.4f} "
                    f"monthly=${snapshot.chatgpt.monthly_usd:.4f} "
                    f"limit=${cfg.chatgpt_limit:.2f} | "
                    f"icon={snapshot.icon_label}",
                    flush=True,
                )
            time.sleep(5)
    except KeyboardInterrupt:
        pass


def main() -> None:
    setup_core_path()

    if sys.platform == "win32":
        import ctypes
        try:
            # Tell Windows that this process has a custom App ID so it doesn't group
            # taskbar icons under Python's default taskbar icon.
            myappid = "com.llmcreditmonitor.app"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="LLM Credit Monitor")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging to stdout")
    parser.add_argument("--mock", action="store_true", help="Use mock data (no real log parsing)")
    parser.add_argument("--headless", action="store_true", help="Run without tray UI (print snapshots to stdout)")
    args = parser.parse_args()

    if args.debug or os.getenv("LLM_DEBUG"):
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
            stream=sys.stdout,
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    from app.fonts import load_pretendard
    load_pretendard()   # register Pretendard from assets/ before any Tk window opens

    from app.config import load_config, save_config, AppConfig
    from app.worker import UsageWorker
    from app.tray import TrayApp

    cfg_lock = threading.Lock()
    _cfg: list[AppConfig] = [load_config()]

    def get_cfg() -> AppConfig:
        with cfg_lock:
            return _cfg[0]

    def set_cfg(new_cfg: AppConfig) -> None:
        with cfg_lock:
            _cfg[0] = new_cfg
        save_config(new_cfg)

    worker = UsageWorker(config_getter=get_cfg, mock=args.mock)
    worker.start()

    if args.headless:
        _headless_loop(worker, get_cfg)
        worker.stop()
        return

    tray = TrayApp(worker=worker, config_getter=get_cfg, config_setter=set_cfg)
    tray.run()


if __name__ == "__main__":
    main()
