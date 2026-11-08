"""Data update coordinator: one Netatmo call per poll for all stations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import NetatmoApiError, NetatmoAuthError, NetatmoPublicClient, NetatmoRateLimitError
from .const import (
    CONF_STALE_MINUTES,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_STALE_MINUTES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    GONE_AFTER,
    MAX_BACKOFF,
    VIEW_AVERAGE,
    VIEW_PRIMARY,
    station_view,
)
from .geo import bbox_around
from .logic import FailoverSelector, aggregate, is_healthy
from .model import StationData, WeatherValues, parse_public_data

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


@dataclass(frozen=True)
class StationConfig:
    """A configured station, in priority order."""

    id: str
    lat: float
    lon: float
    name: str
    modules: frozenset[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StationConfig:
        """Build from the stored config entry dict."""
        return cls(
            id=raw["id"],
            lat=float(raw["lat"]),
            lon=float(raw["lon"]),
            name=raw.get("name") or raw["id"],
            modules=frozenset(raw.get("modules", [])),
        )


@dataclass(frozen=True)
class Snapshot:
    """Immutable result of one poll."""

    stations: dict[str, StationData | None]
    healthy: dict[str, bool]
    views: dict[str, WeatherValues | None]
    active_station: str | None
    used_stations: list[str]
    fetched_at: datetime


def configured_stations(entry: ConfigEntry) -> list[StationConfig]:
    """Return the configured stations; options win over data."""
    raw = entry.options.get(CONF_STATIONS) or entry.data.get(CONF_STATIONS, [])
    return [StationConfig.from_dict(s) for s in raw]


type NetatmoPublicConfigEntry = ConfigEntry[NetatmoPublicCoordinator]


class NetatmoPublicCoordinator(DataUpdateCoordinator[Snapshot]):
    """Fetch and evaluate the configured public stations."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: NetatmoPublicClient
    ) -> None:
        """Initialize."""
        self._base_interval = timedelta(
            minutes=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=self._base_interval,
        )
        self.client = client
        self.stations = configured_stations(entry)
        self._stale_after = timedelta(
            minutes=entry.options.get(CONF_STALE_MINUTES, DEFAULT_STALE_MINUTES)
        )
        self._selector = FailoverSelector(len(self.stations))
        self._store: Store[dict[str, str]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._last_seen: dict[str, datetime] | None = None
        self._rate_limited = False

    async def _async_load_last_seen(self) -> dict[str, datetime]:
        if self._last_seen is None:
            stored = await self._store.async_load() or {}
            now = dt_util.utcnow()
            self._last_seen = {}
            for station in self.stations:
                parsed = dt_util.parse_datetime(stored.get(station.id, ""))
                self._last_seen[station.id] = parsed or now
        return self._last_seen

    async def _async_fetch(self) -> dict[str, StationData]:
        found = parse_public_data(
            await self.client.async_get_public_data(
                bbox_around([(s.lat, s.lon) for s in self.stations])
            )
        )
        # Netatmo may leave stations out of a box; ask for each missing one.
        for station in self.stations:
            if station.id not in found:
                extra = parse_public_data(
                    await self.client.async_get_public_data(
                        bbox_around([(station.lat, station.lon)], 0.2)
                    )
                )
                if station.id in extra:
                    found[station.id] = extra[station.id]
        return found

    async def _async_update_data(self) -> Snapshot:
        try:
            found = await self._async_fetch()
        except NetatmoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NetatmoRateLimitError as err:
            self.update_interval = min(
                (self.update_interval or self._base_interval) * 2, MAX_BACKOFF
            )
            if not self._rate_limited:
                _LOGGER.warning(
                    "Netatmo rate limit reached, next update in %s", self.update_interval
                )
            self._rate_limited = True
            raise UpdateFailed(f"Netatmo rate limit: {err}") from err
        except NetatmoApiError as err:
            raise UpdateFailed(str(err)) from err

        if self._rate_limited:
            _LOGGER.info("Netatmo updates are back to normal")
        self._rate_limited = False
        self.update_interval = self._base_interval
        now = dt_util.utcnow()
        await self._async_track_presence(found, now)
        return self._build_snapshot(found, now)

    def _build_snapshot(self, found: dict[str, StationData], now: datetime) -> Snapshot:
        stations: dict[str, StationData | None] = {}
        healthy: dict[str, bool] = {}
        views: dict[str, WeatherValues | None] = {}
        for station in self.stations:
            data = found.get(station.id)
            stations[station.id] = data
            ok = is_healthy(data, station.modules, now, self._stale_after)
            healthy[station.id] = ok
            views[station_view(station.id)] = data.values if ok and data else None

        index = self._selector.update([healthy[s.id] for s in self.stations])
        active = self.stations[index].id if index is not None else None
        views[VIEW_PRIMARY] = views[station_view(active)] if active else None

        used = [s.id for s in self.stations if healthy[s.id]]
        if len(self.stations) >= 2:
            views[VIEW_AVERAGE] = (
                aggregate([views[station_view(s)] for s in used]) if used else None
            )
        return Snapshot(
            stations=stations,
            healthy=healthy,
            views=views,
            active_station=active,
            used_stations=used,
            fetched_at=now,
        )

    async def _async_track_presence(self, found: dict[str, StationData], now: datetime) -> None:
        last_seen = await self._async_load_last_seen()
        changed = False
        for station in self.stations:
            issue_id = f"station_gone_{station.id.replace(':', '')}"
            if station.id in found:
                last_seen[station.id] = now
                changed = True
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            elif now - last_seen[station.id] >= GONE_AFTER:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="station_gone",
                    translation_placeholders={"station": station.name},
                )
        if changed:
            self._store.async_delay_save(
                lambda: {k: v.isoformat() for k, v in last_seen.items()}, 60
            )
