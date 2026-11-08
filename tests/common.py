"""Test helpers."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
import json
from typing import Any

from custom_components.netatmo_public_weather.const import (
    CONF_SOURCE_ENTITY,
    CONF_STALE_MINUTES,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import FIXTURES

RAIN = "70:ee:50:36:94:7c"
WIND = "70:ee:50:04:ed:7a"
FULL = "70:ee:50:36:a9:fc"
# Shortly after the newest timestamp in the fixture.
FIXTURE_NOW = datetime.fromtimestamp(1560248400, UTC)


def load_payload() -> dict[str, Any]:
    """Return a fresh copy of the full fixture payload."""
    return copy.deepcopy(json.loads((FIXTURES / "getpublicdata.json").read_text()))


def station_conf(station_id: str) -> dict[str, Any]:
    """Return a station config dict as the config flow stores it."""
    for raw in load_payload()["body"]:
        if raw["_id"] == station_id:
            lon, lat = raw["place"]["location"]
            modules = {"base"}
            for m in raw["measures"].values():
                if "rain_live" in m:
                    modules.add("rain")
                if "wind_strength" in m:
                    modules.add("wind")
            return {
                "id": station_id,
                "lat": lat,
                "lon": lon,
                "name": f"Station {station_id[-5:]}",
                "modules": sorted(modules),
            }
    raise KeyError(station_id)


def make_entry(station_ids: list[str], source: str | None = None) -> MockConfigEntry:
    """Return a config entry for the given stations in priority order."""
    options: dict[str, Any] = {CONF_UPDATE_INTERVAL: 10, CONF_STALE_MINUTES: 30}
    if source:
        options[CONF_SOURCE_ENTITY] = source
    return MockConfigEntry(
        domain=DOMAIN,
        title="Netatmo Test",
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": "mock-access",
                "refresh_token": "mock-refresh",
                "expires_at": 4102444800,
                "expires_in": 10800,
                "token_type": "Bearer",
            },
            CONF_STATIONS: [station_conf(s) for s in station_ids],
        },
        options=options,
    )


def set_wind_age(payload: dict[str, Any], station_id: str, seconds_before_now: int) -> None:
    """Make a station's wind module report at a given age."""
    for raw in payload["body"]:
        if raw["_id"] == station_id:
            for m in raw["measures"].values():
                if "wind_timeutc" in m:
                    m["wind_timeutc"] = int(FIXTURE_NOW.timestamp()) - seconds_before_now
