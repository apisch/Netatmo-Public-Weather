"""Health, failover and aggregation rules (no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import math
from statistics import fmean

from .const import FAILBACK_POLLS
from .model import StationData, WeatherValues

WINDY_WIND_KMH = 39.0  # Beaufort 6
WINDY_GUST_KMH = 50.0
WET_CONDITIONS = frozenset(
    {"rainy", "pouring", "lightning-rainy", "snowy", "snowy-rainy"}
)

_MEAN_FIELDS = ("temperature", "humidity", "pressure")
_MAX_FIELDS = ("rain_live", "rain_60min", "rain_24h", "wind_strength", "gust_strength")


def is_healthy(
    data: StationData | None,
    expected_modules: frozenset[str],
    now: datetime,
    stale_after: timedelta,
) -> bool:
    """Return True if every expected module reported recently.

    A station that lost a module it had at setup time counts as down as a
    whole, so a fallback never mixes values of two stations.
    """
    if data is None:
        return False
    for module in expected_modules:
        if module not in data.modules:
            return False
        ts = data.timestamps.get(module)
        if ts is None or now - ts > stale_after:
            return False
    return True


class FailoverSelector:
    """Pick the active station by priority, with hysteresis on failback."""

    def __init__(self, count: int, failback_polls: int = FAILBACK_POLLS) -> None:
        """Initialize for `count` stations in priority order."""
        self._count = count
        self._failback_polls = failback_polls
        self._good_streak = [0] * count
        self.active: int | None = None

    def update(self, healthy: list[bool]) -> int | None:
        """Feed the health of all stations, return the active index."""
        for i in range(self._count):
            ok = i < len(healthy) and healthy[i]
            self._good_streak[i] = self._good_streak[i] + 1 if ok else 0

        first_healthy = next(
            (i for i in range(self._count) if self._good_streak[i] > 0), None
        )
        if first_healthy is None:
            self.active = None
        elif self.active is None or self._good_streak[self.active] == 0:
            # Initial pick or the active station failed: switch at once.
            self.active = first_healthy
        else:
            # Fail back only to a better station that is stable again.
            for i in range(self.active):
                if self._good_streak[i] >= self._failback_polls:
                    self.active = i
                    break
        return self.active


def _pick(values: list[WeatherValues], key: Callable[[WeatherValues], float | None]):
    candidates = [v for v in values if key(v) is not None]
    if not candidates:
        return None
    return max(candidates, key=key)


def aggregate(values: list[WeatherValues]) -> WeatherValues:
    """Combine several stations: mean for climate, max for wind and rain."""
    if not values:
        return WeatherValues()
    out: dict[str, float | None] = {}
    for name in _MEAN_FIELDS:
        items = [getattr(v, name) for v in values if getattr(v, name) is not None]
        out[name] = round(fmean(items), 2) if items else None
    for name in _MAX_FIELDS:
        items = [getattr(v, name) for v in values if getattr(v, name) is not None]
        out[name] = max(items) if items else None

    # Directions follow the strongest gust (or wind) so they match the
    # reported strength.
    leader = _pick(values, lambda v: v.gust_strength) or _pick(
        values, lambda v: v.wind_strength
    )
    out["wind_angle"] = leader.wind_angle if leader else None
    out["gust_angle"] = leader.gust_angle if leader else None
    return WeatherValues(**out)


def derive_condition(values: WeatherValues, source_condition: str | None) -> str | None:
    """Return the weather condition. Measured rain beats any model."""
    raining = values.rain_live is not None and values.rain_live > 0
    if source_condition:
        if raining and source_condition not in WET_CONDITIONS:
            return "rainy"
        return source_condition
    if raining:
        return "rainy"
    if (values.wind_strength or 0) >= WINDY_WIND_KMH or (
        values.gust_strength or 0
    ) >= WINDY_GUST_KMH:
        return "windy"
    return None


def dew_point(temp_c: float | None, humidity: float | None) -> float | None:
    """Return the dew point in °C (Magnus formula)."""
    if temp_c is None or humidity is None or humidity <= 0:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(humidity / 100.0) + a * temp_c / (b + temp_c)
    return round(b * gamma / (a - gamma), 1)
