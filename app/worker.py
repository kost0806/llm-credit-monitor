import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderStats:
    today_usd: float
    monthly_usd: float
    limit_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.monthly_usd)

    @property
    def percent_of_limit(self) -> float:
        if self.limit_usd <= 0:
            return 0.0
        return (self.monthly_usd / self.limit_usd) * 100.0


@dataclass
class UsageSnapshot:
    claude: ProviderStats
    chatgpt: ProviderStats
    fetched_at: datetime
    error: Optional[str] = None

    @property
    def combined_percent(self) -> float:
        total_used = self.claude.monthly_usd + self.chatgpt.monthly_usd
        total_limit = self.claude.limit_usd + self.chatgpt.limit_usd
        if total_limit <= 0:
            return 0.0
        return (total_used / total_limit) * 100.0

    @property
    def icon_label(self) -> str:
        pct = self.combined_percent
        if pct >= 100.0:
            return "OC"
        return f"{int(pct):02d}"


def _make_mock_snapshot(tick: int) -> "UsageSnapshot":
    """Cycles through 0% → 50% → 75% → 99% → OC for UI testing."""
    states = [
        (0.0, 1000.0),    # 0%
        (500.0, 1000.0),  # 50%
        (750.0, 1000.0),  # 75%
        (990.0, 1000.0),  # 99%
        (1001.0, 1000.0), # OC
    ]
    used, limit = states[tick % len(states)]
    half = used / 2
    half_limit = limit / 2
    return UsageSnapshot(
        claude=ProviderStats(today_usd=half * 0.1, monthly_usd=half, limit_usd=half_limit),
        chatgpt=ProviderStats(today_usd=half * 0.1, monthly_usd=half, limit_usd=half_limit),
        fetched_at=datetime.now(),
    )


class UsageWorker:
    def __init__(self, config_getter: Callable, mock: bool = False):
        self._config_getter = config_getter
        self._mock = mock
        self._mock_tick = 0

        self._snapshot: Optional[UsageSnapshot] = None
        self._snapshot_lock = threading.Lock()

        # Monthly cost cache: (provider, "YYYY-MM") -> {day_str: total_cost}
        self._monthly_cache: dict[tuple[str, str], dict[str, float]] = {}
        # Breakdown cache: (provider, "YYYY-MM-DD") -> {model: stats}
        self._breakdown_cache: dict[tuple[str, str], dict] = {}
        self._cache_lock = threading.Lock()

        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="UsageWorker", daemon=True)

    def start(self) -> None:
        self._thread.start()
        logger.debug("UsageWorker started")

    def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()  # unblock the wait
        self._thread.join(timeout=5)
        logger.debug("UsageWorker stopped")

    def request_refresh(self) -> None:
        self._refresh_event.set()

    def get_snapshot(self) -> Optional[UsageSnapshot]:
        with self._snapshot_lock:
            return self._snapshot

    def get_monthly_breakdown(self, provider: str) -> dict[str, float]:
        """Returns a copy of day->cost for the current month. Thread-safe."""
        today = date.today()
        month_key = (provider, today.strftime("%Y-%m"))
        with self._cache_lock:
            return dict(self._monthly_cache.get(month_key, {}))

    def get_period_daily_totals(
        self, provider: str, start: date, end: date
    ) -> dict[str, float]:
        """Returns {day_str: cost} for [start, end]. Blocking — uses cache then falls back to core."""
        from ccusage import credit_usage

        result: dict[str, float] = {}
        current = start
        while current <= end:
            day_str = current.strftime("%Y-%m-%d")
            month_key = (provider, current.strftime("%Y-%m"))

            with self._cache_lock:
                cached = self._monthly_cache.get(month_key, {}).get(day_str)

            if cached is not None:
                result[day_str] = cached
            else:
                try:
                    result[day_str] = credit_usage(provider, day_str)
                except Exception as e:
                    logger.warning("Failed to fetch %s %s: %s", provider, day_str, e)
                    result[day_str] = 0.0

            current += timedelta(days=1)
        return result

    def get_period_model_breakdown(
        self, provider: str, start: date, end: date
    ) -> dict[str, dict]:
        """Aggregates per-model stats across a date range. Blocking — uses breakdown cache when available."""
        from ccusage import credit_usage_per_model

        aggregated: dict[str, dict] = {}
        current = start
        while current <= end:
            day_str = current.strftime("%Y-%m-%d")

            with self._cache_lock:
                daily = self._breakdown_cache.get((provider, day_str))

            if daily is None:
                try:
                    daily = credit_usage_per_model(provider, day_str)
                except Exception as e:
                    logger.warning("Failed to fetch model breakdown %s %s: %s", provider, day_str, e)
                    daily = {}

            for model, stats in daily.items():
                if model not in aggregated:
                    aggregated[model] = {k: 0 for k in stats}
                for k, v in stats.items():
                    aggregated[model][k] = aggregated[model].get(k, 0) + v
            current += timedelta(days=1)
        return aggregated

    # -------------------------------------------------------------------------
    # Internal

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._poll()
            interval = self._config_getter().update_interval
            self._refresh_event.wait(timeout=interval)
            self._refresh_event.clear()

    def _poll(self) -> None:
        if self._mock:
            snap = _make_mock_snapshot(self._mock_tick)
            self._mock_tick += 1
            with self._snapshot_lock:
                self._snapshot = snap
            logger.debug("[POLL] mock tick=%d label=%s", self._mock_tick, snap.icon_label)
            return

        try:
            cfg = self._config_getter()
            today = date.today()
            today_str = today.strftime("%Y-%m-%d")

            # Bulk-load past days on cold start; then only refresh today each poll
            self._ensure_monthly_cache(today)
            claude_today = self._refresh_today("claude", today_str)
            chatgpt_today = self._refresh_today("chatgpt", today_str)
            claude_monthly = self._sum_monthly("claude", today)
            chatgpt_monthly = self._sum_monthly("chatgpt", today)

            snap = UsageSnapshot(
                claude=ProviderStats(
                    today_usd=claude_today,
                    monthly_usd=claude_monthly,
                    limit_usd=cfg.claude_limit,
                ),
                chatgpt=ProviderStats(
                    today_usd=chatgpt_today,
                    monthly_usd=chatgpt_monthly,
                    limit_usd=cfg.chatgpt_limit,
                ),
                fetched_at=datetime.now(),
            )
            with self._snapshot_lock:
                self._snapshot = snap

            logger.debug(
                "[POLL] claude today=$%.4f monthly=$%.4f | chatgpt today=$%.4f monthly=$%.4f | label=%s",
                claude_today, claude_monthly, chatgpt_today, chatgpt_monthly, snap.icon_label,
            )
        except Exception as e:
            logger.error("[POLL] error: %s", e, exc_info=True)
            with self._snapshot_lock:
                prev = self._snapshot
                if prev is not None:
                    self._snapshot = UsageSnapshot(
                        claude=prev.claude,
                        chatgpt=prev.chatgpt,
                        fetched_at=datetime.now(),
                        error=str(e),
                    )

    def _ensure_monthly_cache(self, today: date) -> None:
        """Bulk-loads current + previous month via credit_usage_last_n_days if cache is cold."""
        import calendar
        from ccusage import credit_usage_last_n_days

        month_str = today.strftime("%Y-%m")
        for provider in ("claude", "chatgpt"):
            with self._cache_lock:
                if self._monthly_cache.get((provider, month_str)):
                    continue  # already warm — skip bulk fetch

            # n = all days in the previous month + days elapsed in the current month
            first_of_month = today.replace(day=1)
            prev_month_end = first_of_month - timedelta(days=1)
            days_in_prev_month = calendar.monthrange(prev_month_end.year, prev_month_end.month)[1]
            n = days_in_prev_month + today.day

            try:
                logger.debug("[BULK] fetching %s last %d days (prev month + current)", provider, n)
                bulk = credit_usage_last_n_days(provider, n)
            except Exception as e:
                logger.warning("Bulk fetch failed for %s: %s", provider, e)
                bulk = {}

            with self._cache_lock:
                for day_str, data in bulk.items():
                    m_key = (provider, day_str[:7])
                    self._monthly_cache.setdefault(m_key, {})[day_str] = data["total_cost"]
                    self._breakdown_cache[(provider, day_str)] = data.get("breakdown", {})
            logger.debug("[BULK] %s: cached %d days", provider, len(bulk))

    def _refresh_today(self, provider: str, today_str: str) -> float:
        """Re-fetches today's cost (always fresh) and updates both caches."""
        from ccusage import credit_usage, credit_usage_per_model
        try:
            cost = credit_usage(provider, today_str)
        except Exception as e:
            logger.warning("Failed fetch %s %s: %s", provider, today_str, e)
            cost = 0.0
        try:
            breakdown = credit_usage_per_model(provider, today_str)
        except Exception:
            breakdown = {}
        month_key = (provider, today_str[:7])
        with self._cache_lock:
            self._monthly_cache.setdefault(month_key, {})[today_str] = cost
            self._breakdown_cache[(provider, today_str)] = breakdown
        return cost

    def _sum_monthly(self, provider: str, today: date) -> float:
        month_key = (provider, today.strftime("%Y-%m"))
        with self._cache_lock:
            return sum(self._monthly_cache.get(month_key, {}).values())
