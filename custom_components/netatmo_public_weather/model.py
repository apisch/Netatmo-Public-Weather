"""Data model and parser for the Netatmo getpublicdata response.

This module has no Home Assistant imports so it can be tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from typing import Any

from .const import MODULE_BASE, MODULE_RAIN, MODULE_WIND
from .geo import haversine_km

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeatherValues:
    """Measured values of one station (or a derived view). Native units."""

    temperature: float | None = None  # °C
    humidity: float | None = None  # %
    pressure: float | None = None  # hPa
    rain_live: float | None = None  # mm/h
    rain_60min: float | None = None  # mm
    rain_24h: float | None = None  # mm
    wind_strength: float | None = None  # km/h
    wind_angle: float | None = None  # °
    gust_strength: float | None = None  # km/h
    gust_angle: float | None = None  # °


@dataclass(frozen=True)
class StationData:
    """One public station as reported by Netatmo."""

    station_id: str
    lat: float
    lon: float
    altitude: int | None
    city: str | None
    street: str | None
    modules: frozenset[str]
    timestamps: dict[str, datetime] = field(default_factory=dict)
    values: WeatherValues = field(default_factory=WeatherValues)


def _ts(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _latest_res(measure: dict[str, Any]) -> tuple[datetime | None, list[Any]]:
    """Return (timestamp, values) of the newest entry in a measure's res."""
    res = measure.get("res")
    if not isinstance(res, dict) or not res:
        return None, []
    try:
        key = max(res, key=lambda k: int(k))
    except (TypeError, ValueError):
        return None, []
    values = res[key] if isinstance(res[key], list) else []
    return _ts(key), values


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _parse_station(raw: dict[str, Any]) -> StationData | None:
    station_id = raw.get("_id")
    place = raw.get("place") or {}
    location = place.get("location")
    measures = raw.get("measures")
    if (
        not isinstance(station_id, str)
        or not isinstance(location, list)
        or len(location) != 2
        or not isinstance(measures, dict)
    ):
        return None

    modules: set[str] = set()
    timestamps: dict[str, datetime] = {}
    vals: dict[str, float | None] = {}
    base_ts: list[datetime] = []
    base_silent = False

    for measure in measures.values():
        if not isinstance(measure, dict):
            continue
        types = measure.get("type")
        if isinstance(types, list) and "res" in measure:
            ts, values = _latest_res(measure)
            if "temperature" in types:
                modules.add(MODULE_BASE)
                # Outdoor module present but silent: no base timestamp at
                # all, so the station counts as stale.
                base_silent = base_silent or ts is None
            elif "pressure" not in types:
                continue
            if ts is not None:
                base_ts.append(ts)
            for name, value in zip(types, values, strict=False):
                if name in ("temperature", "humidity", "pressure"):
                    vals[name] = _num(value)
        elif "rain_timeutc" in measure or "rain_live" in measure:
            modules.add(MODULE_RAIN)
            if (ts := _ts(measure.get("rain_timeutc"))) is not None:
                timestamps[MODULE_RAIN] = ts
            for key in ("rain_live", "rain_60min", "rain_24h"):
                vals[key] = _num(measure.get(key))
        elif "wind_timeutc" in measure or "wind_strength" in measure:
            modules.add(MODULE_WIND)
            if (ts := _ts(measure.get("wind_timeutc"))) is not None:
                timestamps[MODULE_WIND] = ts
            for key in ("wind_strength", "wind_angle", "gust_strength", "gust_angle"):
                vals[key] = _num(measure.get(key))

    if base_ts and MODULE_BASE in modules and not base_silent:
        timestamps[MODULE_BASE] = min(base_ts)

    try:
        lon, lat = float(location[0]), float(location[1])
    except (TypeError, ValueError):
        return None

    altitude = place.get("altitude")
    return StationData(
        station_id=station_id,
        lat=lat,
        lon=lon,
        altitude=altitude if isinstance(altitude, int) else None,
        city=place.get("city") if isinstance(place.get("city"), str) else None,
        street=place.get("street") if isinstance(place.get("street"), str) else None,
        modules=frozenset(modules),
        timestamps=timestamps,
        values=WeatherValues(**vals),
    )


def parse_public_data(body: list[dict[str, Any]]) -> dict[str, StationData]:
    """Parse the body of a getpublicdata response, keyed by station id."""
    result: dict[str, StationData] = {}
    if not isinstance(body, list):
        return result
    for raw in body:
        if not isinstance(raw, dict):
            continue
        try:
            station = _parse_station(raw)
        except Exception:  # noqa: BLE001 - never let one odd station break all
            _LOGGER.debug("Skipping unparsable station %s", raw.get("_id"))
            continue
        if station is not None:
            result[station.station_id] = station
    return result


_FAVORITE_MODULES = {"NAModule1": MODULE_BASE, "NAModule2": MODULE_WIND, "NAModule3": MODULE_RAIN}


def _parse_favorite(raw: dict[str, Any]) -> StationData | None:
    station_id = raw.get("_id")
    place = raw.get("place") or {}
    location = place.get("location")
    if not isinstance(station_id, str) or not isinstance(location, list) or len(location) != 2:
        return None
    try:
        lon, lat = float(location[0]), float(location[1])
    except (TypeError, ValueError):
        return None

    modules: set[str] = set()
    timestamps: dict[str, datetime] = {}
    for module in raw.get("modules") or []:
        if not isinstance(module, dict):
            continue
        kind = _FAVORITE_MODULES.get(module.get("type"))
        if kind is None:
            continue  # indoor modules are irrelevant for public weather
        modules.add(kind)
        dash = module.get("dashboard_data")
        if isinstance(dash, dict) and (ts := _ts(dash.get("time_utc"))) is not None:
            timestamps[kind] = ts

    altitude = place.get("altitude")
    city = place.get("city")
    return StationData(
        station_id=station_id,
        lat=lat,
        lon=lon,
        altitude=altitude if isinstance(altitude, int) else None,
        city=city if isinstance(city, str) else None,
        street=None,
        modules=frozenset(modules),
        timestamps=timestamps,
    )


def parse_favorites(devices: Any) -> dict[str, StationData]:
    """Parse getstationsdata devices, keeping only favourite stations.

    The account's own stations are skipped: they are often private and
    would then never appear in getpublicdata, which is used at runtime.
    """
    result: dict[str, StationData] = {}
    if not isinstance(devices, list):
        return result
    for raw in devices:
        if not isinstance(raw, dict) or raw.get("favorite") is not True:
            continue
        try:
            station = _parse_favorite(raw)
        except Exception:  # noqa: BLE001 - never let one odd station break all
            _LOGGER.debug("Skipping unparsable favourite %s", raw.get("_id"))
            continue
        if station is not None:
            result[station.station_id] = station
    return result


def short_id(station_id: str) -> str:
    """Return the last two bytes of a station MAC, e.g. '48:8c'."""
    return station_id[-5:]


def place_name(station: StationData) -> str:
    """Return a human readable, distinct place name without distance.

    Netatmo usually reports only a city, so the short station id is added
    unless a street makes the name specific enough.
    """
    if station.street and station.city:
        return f"{station.street}, {station.city}"
    if station.street:
        return station.street
    if station.city:
        return f"{station.city} {short_id(station.station_id)}"
    return f"Station {station.station_id[-11:]}"


def station_label(station: StationData, home: tuple[float, float] | None) -> str:
    """Return the label shown in the station picker."""
    name = place_name(station)
    if home is None:
        return name
    dist = haversine_km(home[0], home[1], station.lat, station.lon)
    return f"{name} · {dist:.1f} km"
