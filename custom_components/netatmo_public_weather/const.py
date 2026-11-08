"""Constants for Netatmo Public Weather."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "netatmo_public_weather"

OAUTH2_AUTHORIZE: Final = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN: Final = "https://api.netatmo.com/oauth2/token"
API_PUBLIC_DATA: Final = "https://api.netatmo.com/api/getpublicdata"
SCOPE: Final = "read_station"

CONF_STATIONS: Final = "stations"  # ordered list of {id, lat, lon, name, modules}
CONF_SOURCE_ENTITY: Final = "source_entity"
CONF_UPDATE_INTERVAL: Final = "update_interval"  # minutes
CONF_STALE_MINUTES: Final = "stale_minutes"
CONF_RADIUS_KM: Final = "radius_km"

DEFAULT_RADIUS_KM: Final = 3.0
MIN_RADIUS_KM: Final = 0.5
MAX_RADIUS_KM: Final = 20.0
DEFAULT_UPDATE_INTERVAL: Final = 10
MIN_UPDATE_INTERVAL: Final = 5
MAX_UPDATE_INTERVAL: Final = 60
DEFAULT_STALE_MINUTES: Final = 30
MIN_STALE_MINUTES: Final = 15
MAX_STALE_MINUTES: Final = 120
MAX_LISTED_STATIONS: Final = 20
MIN_STATIONS: Final = 1
MAX_STATIONS: Final = 3

MAX_BACKOFF: Final = timedelta(minutes=60)
FAILBACK_POLLS: Final = 2
GONE_AFTER: Final = timedelta(days=7)

MODULE_BASE: Final = "base"
MODULE_RAIN: Final = "rain"
MODULE_WIND: Final = "wind"

VIEW_PRIMARY: Final = "primary"
VIEW_AVERAGE: Final = "average"


WEATHERMAP_URL: Final = "https://weathermap.netatmo.com/"
MAP_ZOOM_STATION: Final = 15
MAP_ZOOM_OVERVIEW: Final = 13


def weathermap_url(station_id: str, zoom: int = MAP_ZOOM_STATION) -> str:
    """Return the Netatmo weathermap link that opens one station."""
    return f"{WEATHERMAP_URL}?stationid={station_id}&zoom={zoom}"


def station_view(station_id: str) -> str:
    """Return the view key of a single station."""
    return f"station:{station_id}"
