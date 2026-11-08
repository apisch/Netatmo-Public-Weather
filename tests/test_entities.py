"""Tests for setup, sensors, binary sensors, weather entities and diagnostics."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.netatmo_public_weather.const import API_PUBLIC_DATA, DOMAIN
from custom_components.netatmo_public_weather.diagnostics import (
    async_get_config_entry_diagnostics,
)
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import FIXTURE_NOW, FULL, RAIN, WIND, load_payload, make_entry, set_wind_age


@pytest.fixture(autouse=True)
def _frozen(freezer):
    freezer.move_to(FIXTURE_NOW)


@pytest.fixture
async def credentials(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("client-id", "client-secret"), DOMAIN
    )


async def _setup(hass, ids, source=None):
    entry = make_entry(ids, source)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _eid(hass, platform: str, entry, device: str, key: str) -> str | None:
    unique = f"{entry.entry_id}_{device.replace(':', '')}_{key}"
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique)


async def test_setup_creates_entities(hass, aioclient_mock, credentials):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = await _setup(hass, [FULL, RAIN])

    for device in (FULL, RAIN, "primary", "average"):
        eid = _eid(hass, "weather", entry, device, "weather")
        assert eid, device
        assert hass.states.get(eid).state != STATE_UNAVAILABLE

    # gust only where a wind module exists
    assert _eid(hass, "sensor", entry, FULL, "gust_strength")
    assert _eid(hass, "sensor", entry, RAIN, "gust_strength") is None
    assert _eid(hass, "sensor", entry, "primary", "gust_strength")
    assert _eid(hass, "sensor", entry, "average", "stations_used")
    assert _eid(hass, "sensor", entry, "primary", "active_station")
    assert _eid(hass, "binary_sensor", entry, "average", "healthy") is None

    gust = hass.states.get(_eid(hass, "sensor", entry, "primary", "gust_strength"))
    assert float(gust.state) == 31
    assert gust.attributes["unit_of_measurement"] == "km/h"
    temp = hass.states.get(_eid(hass, "sensor", entry, "average", "temperature"))
    assert float(temp.state) == pytest.approx((20.1 + 21.4) / 2, abs=0.01)
    weather = hass.states.get(_eid(hass, "weather", entry, "primary", "weather"))
    assert weather.attributes["temperature"] == 20.1
    assert weather.attributes["dew_point"] is not None


async def test_failover_and_stale_entities(hass, aioclient_mock, credentials):
    payload = load_payload()
    set_wind_age(payload, FULL, 31 * 60)
    aioclient_mock.post(API_PUBLIC_DATA, json=payload)
    entry = await _setup(hass, [FULL, WIND])

    primary_temp = hass.states.get(_eid(hass, "sensor", entry, "primary", "temperature"))
    wind_temp = hass.states.get(_eid(hass, "sensor", entry, WIND, "temperature"))
    assert primary_temp.state == wind_temp.state == "19.8"

    assert hass.states.get(_eid(hass, "sensor", entry, FULL, "temperature")).state == STATE_UNAVAILABLE
    assert hass.states.get(_eid(hass, "weather", entry, FULL, "weather")).state == STATE_UNAVAILABLE
    assert hass.states.get(_eid(hass, "binary_sensor", entry, FULL, "healthy")).state == STATE_OFF
    assert hass.states.get(_eid(hass, "binary_sensor", entry, WIND, "healthy")).state == STATE_ON
    active = hass.states.get(_eid(hass, "sensor", entry, "primary", "active_station"))
    assert active.attributes["priority"] == 2


async def test_network_error_marks_unhealthy(hass, aioclient_mock, credentials):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = await _setup(hass, [FULL])
    aioclient_mock.clear_requests()
    aioclient_mock.post(API_PUBLIC_DATA, status=500)
    async_fire_time_changed(hass, FIXTURE_NOW + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert hass.states.get(_eid(hass, "binary_sensor", entry, "primary", "healthy")).state == STATE_OFF
    assert hass.states.get(_eid(hass, "sensor", entry, "primary", "temperature")).state == STATE_UNAVAILABLE


@pytest.fixture
async def source_weather(hass: HomeAssistant) -> str:
    assert await async_setup_component(
        hass,
        "template",
        {
            "template": [
                {
                    "weather": [
                        {
                            "name": "src",
                            "condition_template": "{{ 'sunny' }}",
                            "temperature_template": "{{ 5 }}",
                            "humidity_template": "{{ 50 }}",
                            "uv_index_template": "{{ 3 }}",
                            "forecast_daily_template": (
                                "{{ [{'datetime': '2019-06-12T00:00:00+00:00', "
                                "'condition': 'rainy', 'temperature': 12, 'templow': 5}] }}"
                            ),
                        }
                    ]
                }
            ]
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("weather.src") is not None
    return "weather.src"


async def test_weather_with_source(hass, aioclient_mock, credentials, source_weather):
    payload = load_payload()
    aioclient_mock.post(API_PUBLIC_DATA, json=payload)
    entry = await _setup(hass, [FULL], source=source_weather)
    eid = _eid(hass, "weather", entry, FULL, "weather")

    state = hass.states.get(eid)
    assert state.state == "sunny"  # FULL measures rain_live 0
    assert state.attributes["uv_index"] == 3
    assert state.attributes["temperature"] == 20.1  # measured, not from source

    resp = await hass.services.async_call(
        "weather", "get_forecasts", {"entity_id": eid, "type": "daily"},
        blocking=True, return_response=True,
    )
    forecast = resp[eid]["forecast"]
    assert forecast[0]["temperature"] == 12
    assert forecast[0]["condition"] == "rainy"


async def test_measured_rain_overrides_source(hass, aioclient_mock, credentials, source_weather):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = await _setup(hass, [RAIN], source=source_weather)  # rain_live 0.5
    assert hass.states.get(_eid(hass, "weather", entry, RAIN, "weather")).state == "rainy"


async def test_missing_source_keeps_entity_available(hass, aioclient_mock, credentials):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = await _setup(hass, [FULL], source="weather.does_not_exist")
    eid = _eid(hass, "weather", entry, FULL, "weather")
    state = hass.states.get(eid)
    assert state.state != STATE_UNAVAILABLE
    assert state.attributes["supported_features"] == 0


async def test_diagnostics_redacts_tokens(hass, aioclient_mock, credentials):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = await _setup(hass, [FULL])
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    assert "mock-access" not in text
    assert "mock-refresh" not in text
    assert diag["snapshot"]["active_station"] == FULL


async def test_unload(hass, aioclient_mock, credentials):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = await _setup(hass, [FULL])
    assert await hass.config_entries.async_unload(entry.entry_id)
