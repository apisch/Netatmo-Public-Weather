"""Tests for the config, options and reauth flows."""

from __future__ import annotations

import copy
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from homeassistant import config_entries
from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.setup import async_setup_component

from custom_components.netatmo_public_weather.const import (
    API_PUBLIC_DATA,
    CONF_SOURCE_ENTITY,
    CONF_STALE_MINUTES,
    CONF_STATIONS,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    OAUTH2_AUTHORIZE,
    OAUTH2_TOKEN,
)

from .common import FIXTURE_NOW, FULL, RAIN, WIND, load_payload, make_entry

CENTRE = {"latitude": 50.19596, "longitude": 8.80116}  # at the FULL station


@pytest.fixture(autouse=True)
def _frozen(freezer):
    freezer.move_to(FIXTURE_NOW)


@pytest.fixture
async def credentials(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "application_credentials", {})
    await async_import_client_credential(
        hass, DOMAIN, ClientCredential("client-id", "client-secret"), DOMAIN
    )


def _token(access: str = "flow-access") -> dict[str, Any]:
    return {
        "access_token": access,
        "refresh_token": "flow-refresh",
        "expires_in": 10800,
        "token_type": "Bearer",
        "scope": ["read_station"],
    }


async def _oauth(hass, result, hass_client_no_auth, aioclient_mock, access="flow-access"):
    """Run the external OAuth step and return the next flow result."""
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    url = urlparse(result["url"])
    assert result["url"].startswith(OAUTH2_AUTHORIZE)
    query = parse_qs(url.query)
    assert query["scope"] == ["read_station"]
    state = config_entry_oauth2_flow._encode_jwt(
        hass, {"flow_id": result["flow_id"], "redirect_uri": query["redirect_uri"][0]}
    )
    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    aioclient_mock.post(OAUTH2_TOKEN, json=_token(access))
    return await hass.config_entries.flow.async_configure(result["flow_id"])


async def _start(hass, hass_client_no_auth, aioclient_mock, payload=None):
    aioclient_mock.post(API_PUBLIC_DATA, json=payload or load_payload())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await _oauth(hass, result, hass_client_no_auth, aioclient_mock)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "area"
    return result


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_full_flow(hass, hass_client_no_auth, aioclient_mock):
    result = await _start(hass, hass_client_no_auth, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    assert result["step_id"] == "stations"
    assert result["description_placeholders"]["count"] == "3"
    labels = [o["label"] for o in result["data_schema"].schema["stations"].config["options"]]
    assert labels[0].startswith("Example Street, Sampletown · 0.0 km · 🌡 🌧 💨")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stations": [FULL, WIND]}
    )
    assert result["step_id"] == "order"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"primary": FULL, "fallback_1": WIND}
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SOURCE_ENTITY: "weather.home", CONF_UPDATE_INTERVAL: 15, CONF_STALE_MINUTES: 45},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Netatmo Example Street, Sampletown"
    data = result["data"]
    assert data["token"]["access_token"] == "flow-access"
    assert [s["id"] for s in data[CONF_STATIONS]] == [FULL, WIND]
    assert data[CONF_STATIONS][1]["modules"] == ["base", "wind"]
    assert result["options"][CONF_UPDATE_INTERVAL] == 15
    assert result["options"][CONF_STALE_MINUTES] == 45
    assert result["options"][CONF_SOURCE_ENTITY] == "weather.home"


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_single_station_skips_order(hass, hass_client_no_auth, aioclient_mock):
    result = await _start(hass, hass_client_no_auth, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stations": [RAIN]})
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 10, CONF_STALE_MINUTES: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_SOURCE_ENTITY not in result["options"]


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_no_stations(hass, hass_client_no_auth, aioclient_mock):
    empty = load_payload()
    empty["body"] = []
    result = await _start(hass, hass_client_no_auth, aioclient_mock, payload=empty)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    assert result["step_id"] == "area"
    assert result["errors"] == {"base": "no_stations"}


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_too_few_and_too_many(hass, hass_client_no_auth, aioclient_mock):
    payload = load_payload()
    extra = copy.deepcopy(payload["body"][0])
    extra["_id"] = "70:ee:50:00:00:99"
    payload["body"].append(extra)
    result = await _start(hass, hass_client_no_auth, aioclient_mock, payload=payload)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stations": []})
    assert result["errors"] == {"base": "too_few"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stations": [FULL, WIND, RAIN, "70:ee:50:00:00:99"]}
    )
    assert result["errors"] == {"base": "too_many"}


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_manual_ids(hass, hass_client_no_auth, aioclient_mock):
    result = await _start(hass, hass_client_no_auth, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stations": [], "manual_ids": "not-a-mac"}
    )
    assert result["errors"] == {"manual_ids": "invalid_id"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stations": [], "manual_ids": "70:EE:50:36:94:7C"}
    )
    assert result["step_id"] == "settings"


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_order_validation(hass, hass_client_no_auth, aioclient_mock):
    result = await _start(hass, hass_client_no_auth, aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"stations": [FULL, RAIN]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"primary": FULL, "fallback_1": FULL}
    )
    assert result["errors"] == {"base": "duplicate_order"}
    # RAIN has no wind module: warn once, accept on second submit
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"primary": RAIN, "fallback_1": FULL}
    )
    assert result["errors"] == {"base": "primary_missing_modules"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"primary": RAIN, "fallback_1": FULL}
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 10, CONF_STALE_MINUTES: 30}
    )
    assert [s["id"] for s in result["data"][CONF_STATIONS]] == [RAIN, FULL]


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_options_flow_reorders(hass, aioclient_mock):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = make_entry([FULL, WIND])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "area"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"location": CENTRE, "radius_km": 3}
    )
    assert result["step_id"] == "stations"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"stations": [FULL, WIND]}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"primary": WIND, "fallback_1": FULL}
    )
    assert result["errors"] == {"base": "primary_missing_modules"}  # WIND has no rain
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"primary": WIND, "fallback_1": FULL}
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 20, CONF_STALE_MINUTES: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert [s["id"] for s in entry.options[CONF_STATIONS]] == [WIND, FULL]
    assert entry.runtime_data.stations[0].id == WIND  # reloaded
    assert entry.runtime_data.data.active_station == WIND


@pytest.mark.usefixtures("current_request_with_host", "credentials")
async def test_reauth(hass, hass_client_no_auth, aioclient_mock):
    aioclient_mock.post(API_PUBLIC_DATA, json=load_payload())
    entry = make_entry([FULL])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await _oauth(hass, result, hass_client_no_auth, aioclient_mock, access="new-access")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"]["access_token"] == "new-access"
    assert entry.data[CONF_STATIONS][0]["id"] == FULL
