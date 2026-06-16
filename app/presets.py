CLAUDE_PRESETS: dict[str, float] = {
    "Preset 1":   12.0,
    "Preset 2":   26.0,
    "Preset 3":   36.0,
    "Preset 3.5": 223.0,
    "Preset 4":   446.0,
}

CHATGPT_PRESETS: dict[str, float] = {
    "Preset 1":   20.0,
    "Preset 2":   26.0,
    "Preset 3":   36.0,
    "Preset 3.5": 223.0,
    "Preset 4":   446.0,
}

PRESET_NAMES: list[str] = ["Preset 1", "Preset 2", "Preset 3", "Preset 3.5", "Preset 4"]


def get_claude_limit(preset: str) -> float:
    return CLAUDE_PRESETS.get(preset, 446.0)


def get_chatgpt_limit(preset: str) -> float:
    return CHATGPT_PRESETS.get(preset, 446.0)
