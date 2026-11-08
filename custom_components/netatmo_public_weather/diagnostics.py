"""Diagnostics for Netatmo Public Weather."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import NetatmoPublicConfigEntry

TO_REDACT = {"token", "access_token", "refresh_token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NetatmoPublicConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    snapshot = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "update_interval": str(coordinator.update_interval),
        "last_update_success": coordinator.last_update_success,
        "snapshot": asdict(snapshot) if snapshot else None,
        "last_raw_body": coordinator.client.last_body,
    }
