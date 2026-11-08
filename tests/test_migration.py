"""Tests for fixing duplicate station names of existing entries."""

from homeassistant.core import HomeAssistant

from custom_components.netatmo_public_weather import async_fix_station_names
from custom_components.netatmo_public_weather.const import CONF_STATIONS

from .common import FULL, RAIN, WIND, make_entry


async def test_duplicate_names_get_short_id(hass: HomeAssistant):
    entry = make_entry([FULL, WIND, RAIN])
    stations = [dict(s) for s in entry.data[CONF_STATIONS]]
    stations[0]["name"] = stations[1]["name"] = "Rheine"
    stations[2]["name"] = "Kreis Steinfurt"
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_STATIONS: stations})

    async_fix_station_names(hass, entry)
    names = [s["name"] for s in entry.data[CONF_STATIONS]]
    assert names == ["Rheine a9:fc", "Rheine ed:7a", "Kreis Steinfurt"]


async def test_options_stations_are_fixed_too(hass: HomeAssistant):
    entry = make_entry([FULL])
    entry.add_to_hass(hass)
    opt = [dict(s) for s in entry.data[CONF_STATIONS]] * 1
    second = dict(opt[0], id=RAIN, name="Rheine")
    opt[0]["name"] = "Rheine"
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_STATIONS: [opt[0], second]}
    )
    async_fix_station_names(hass, entry)
    assert [s["name"] for s in entry.options[CONF_STATIONS]] == ["Rheine a9:fc", "Rheine 94:7c"]


async def test_unique_names_untouched(hass: HomeAssistant):
    entry = make_entry([FULL, WIND])
    entry.add_to_hass(hass)
    before = [s["name"] for s in entry.data[CONF_STATIONS]]
    async_fix_station_names(hass, entry)
    assert [s["name"] for s in entry.data[CONF_STATIONS]] == before
