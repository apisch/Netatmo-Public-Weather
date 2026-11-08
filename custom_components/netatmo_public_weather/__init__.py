"""Netatmo Public Weather integration."""

from __future__ import annotations

import aiohttp

from collections import Counter
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NetatmoApiError, NetatmoAuthError, NetatmoPublicClient
from .const import CONF_STATIONS
from .coordinator import NetatmoPublicConfigEntry, NetatmoPublicCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.WEATHER]


def _distinct_names(stations: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Append the short id to duplicate names; None if nothing changes."""
    counts = Counter(s.get("name") for s in stations)
    if all(n == 1 for n in counts.values()):
        return None
    return [
        {**s, "name": f"{s.get('name')} {s['id'][-5:]}"} if counts[s.get("name")] > 1 else s
        for s in stations
    ]


@callback
def async_fix_station_names(hass: HomeAssistant, entry: NetatmoPublicConfigEntry) -> None:
    """Fix entries created by v0.1.0, where stations could share a name."""
    data_fix = _distinct_names(entry.data.get(CONF_STATIONS, []))
    options_fix = _distinct_names(entry.options.get(CONF_STATIONS, []))
    if data_fix is None and options_fix is None:
        return
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_STATIONS: data_fix} if data_fix else entry.data,
        options=(
            {**entry.options, CONF_STATIONS: options_fix} if options_fix else entry.options
        ),
    )


async def async_setup_entry(hass: HomeAssistant, entry: NetatmoPublicConfigEntry) -> bool:
    """Set up Netatmo Public Weather from a config entry."""
    async_fix_station_names(hass, entry)
    try:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
        )
    except ValueError as err:
        raise ConfigEntryNotReady("Application credentials are missing") from err
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    async def _get_token() -> str:
        try:
            await session.async_ensure_token_valid()
        except aiohttp.ClientResponseError as err:
            if 400 <= err.status < 500:
                raise NetatmoAuthError(f"Token refresh rejected: {err.status}") from err
            raise NetatmoApiError(f"Token refresh failed: {err.status}") from err
        except aiohttp.ClientError as err:
            raise NetatmoApiError(f"Token refresh failed: {err}") from err
        return session.token["access_token"]

    client = NetatmoPublicClient(async_get_clientsession(hass), _get_token)
    coordinator = NetatmoPublicCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: NetatmoPublicConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NetatmoPublicConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
