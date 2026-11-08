"""Tests for the API client and coordinator."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.netatmo_public_weather.api import NetatmoPublicClient
from custom_components.netatmo_public_weather.const import API_PUBLIC_DATA, DOMAIN
from custom_components.netatmo_public_weather.coordinator import NetatmoPublicCoordinator
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .common import FIXTURE_NOW, FULL, RAIN, WIND, load_payload, make_entry, set_wind_age


async def _token() -> str:
    return "mock-access"


def _coordinator(hass: HomeAssistant, ids: list[str]) -> NetatmoPublicCoordinator:
    entry = make_entry(ids)
    entry.add_to_hass(hass)
    client = NetatmoPublicClient(async_get_clientsession(hass), _token)
    return NetatmoPublicCoordinator(hass, entry, client)


@pytest.fixture(autouse=True)
def _frozen(freezer):
    freezer.move_to(FIXTURE_NOW)


async def test_all_present(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    coord = _coordinator(hass, [FULL, WIND, RAIN])
    snap = await coord._async_update_data()
    assert aioclient_mock.call_count == 1
    assert snap.active_station == FULL
    assert snap.views["primary"] == snap.views[f"station:{FULL}"]
    assert snap.used_stations == [FULL, WIND, RAIN]
    assert snap.views["average"].gust_strength == 31
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Authorization"] == "Bearer mock-access"


async def test_stale_wind_fails_over(hass, aioclient_mock):
    payload = load_payload()
    set_wind_age(payload, FULL, 31 * 60)
    aioclient_mock.post(API_PUBLIC_DATA, json=payload)
    coord = _coordinator(hass, [FULL, WIND])
    snap = await coord._async_update_data()
    assert snap.healthy == {FULL: False, WIND: True}
    assert snap.active_station == WIND
    assert snap.views[f"station:{FULL}"] is None
    assert snap.views["primary"] == snap.views[f"station:{WIND}"]
    assert snap.views["average"] == snap.views[f"station:{WIND}"]


async def test_single_station_has_no_average(hass, aioclient_mock):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    snap = await _coordinator(hass, [FULL])._async_update_data()
    assert "average" not in snap.views


async def test_missing_station_gets_extra_call(hass, aioclient_mock):
    full = load_payload()
    without_rain = load_payload()
    without_rain["body"] = [s for s in without_rain["body"] if s["_id"] != RAIN]
    responses = [without_rain, full]

    async def _side_effect(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        return AiohttpClientMockResponse(method, url, json=responses.pop(0))

    aioclient_mock.post(API_PUBLIC_DATA, side_effect=_side_effect)
    snap = await _coordinator(hass, [FULL, RAIN])._async_update_data()
    assert aioclient_mock.call_count == 2
    assert snap.stations[RAIN] is not None
    second = aioclient_mock.mock_calls[1][2]
    assert float(second["lat_ne"]) - float(second["lat_sw"]) < 0.01


async def test_rate_limit_backs_off(hass, aioclient_mock):
    aioclient_mock.post(API_PUBLIC_DATA, status=429, json={"error": {"code": 26, "message": "User usage reached"}})
    coord = _coordinator(hass, [FULL])
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.update_interval == timedelta(minutes=20)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.update_interval == timedelta(minutes=60)

    aioclient_mock.clear_requests()
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    await coord._async_update_data()
    assert coord.update_interval == timedelta(minutes=10)


async def test_revoked_token_triggers_auth_failed(hass, aioclient_mock):
    aioclient_mock.post(
        API_PUBLIC_DATA,
        status=403,
        json={"error": {"code": 3, "message": "Access token expired"}},
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await _coordinator(hass, [FULL])._async_update_data()


async def test_error_with_http_200(hass, aioclient_mock):
    aioclient_mock.post(API_PUBLIC_DATA, json={"error": {"code": 2, "message": "Invalid access token"}})
    with pytest.raises(ConfigEntryAuthFailed):
        await _coordinator(hass, [FULL])._async_update_data()


async def test_garbage_response(hass, aioclient_mock):
    aioclient_mock.post(API_PUBLIC_DATA, text="<html>oops</html>")
    with pytest.raises(UpdateFailed):
        await _coordinator(hass, [FULL])._async_update_data()


async def test_station_gone_creates_issue(hass, aioclient_mock, hass_storage):
    payload = load_payload()
    payload["body"] = [s for s in payload["body"] if s["_id"] != RAIN]
    aioclient_mock.post(API_PUBLIC_DATA, json=payload)
    coord = _coordinator(hass, [FULL, RAIN])
    hass_storage[f"{DOMAIN}.{coord.config_entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{coord.config_entry.entry_id}",
        "data": {RAIN: (FIXTURE_NOW - timedelta(days=8)).isoformat()},
    }
    await coord._async_update_data()
    issue_id = "station_gone_70ee5036947c"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    aioclient_mock.clear_requests()
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    await coord._async_update_data()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
