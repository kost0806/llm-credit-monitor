CLAUDE_TIERS: dict[str, float] = {
    "Tier1": 100.0,
    "Tier2": 500.0,
    "Tier3": 1000.0,
    "Tier4": 5000.0,
    "Tier4 Half": 2500.0,
}

CHATGPT_TIERS: dict[str, float] = {
    "Tier1": 100.0,
    "Tier2": 500.0,
    "Tier3": 1000.0,
    "Tier4": 5000.0,
    "Tier4 Half": 2500.0,
}

TIER_NAMES: list[str] = ["Tier1", "Tier2", "Tier3", "Tier4", "Tier4 Half"]


def get_claude_limit(tier: str) -> float:
    return CLAUDE_TIERS.get(tier, 5000.0)


def get_chatgpt_limit(tier: str) -> float:
    return CHATGPT_TIERS.get(tier, 5000.0)
