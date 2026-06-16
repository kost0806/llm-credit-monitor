import json
import os
import sys
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from app.presets import get_claude_limit, get_chatgpt_limit

logger = logging.getLogger(__name__)

CONFIG_VERSION = 1

_DEFAULTS = {
    "claude_tier": "Preset 4",
    "claude_limit": 446.0,
    "chatgpt_tier": "Preset 4",
    "chatgpt_limit": 446.0,
    "update_interval": 60,
    "auto_start": False,
    "config_version": CONFIG_VERSION,
}


@dataclass
class AppConfig:
    claude_tier: str
    claude_limit: float
    chatgpt_tier: str
    chatgpt_limit: float
    update_interval: int
    auto_start: bool
    config_version: int = CONFIG_VERSION


def get_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "LLMCreditMonitor" / "config.json"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "llmcreditmonitor" / "config.json"


def load_config() -> AppConfig:
    path = get_config_path()
    data: dict = {}

    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except Exception as e:
            logger.warning("Failed to read config at %s: %s — using defaults", path, e)
            # try recovering from .tmp
            tmp = path.with_suffix(".json.tmp")
            if tmp.exists():
                try:
                    data = json.loads(tmp.read_text(encoding="utf-8"))
                    logger.info("Recovered config from %s", tmp)
                except Exception:
                    data = {}

    merged = {**_DEFAULTS, **{k: v for k, v in data.items() if k in _DEFAULTS}}

    # Clamp update_interval
    merged["update_interval"] = max(10, min(600, int(merged["update_interval"])))

    cfg = AppConfig(**merged)
    logger.debug("Loaded config from %s: %s", path, cfg)
    return cfg


def save_config(cfg: AppConfig) -> None:
    path = get_config_path()
    tmp = path.with_suffix(".json.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(asdict(cfg), indent=2)
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        logger.debug("Saved config to %s", path)
    except Exception as e:
        logger.error("Failed to save config to %s: %s", path, e)
