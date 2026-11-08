"""Tests for response parsing."""

from datetime import UTC, datetime

from custom_components.netatmo_public_weather.model import (
    parse_public_data,
    station_label,
)

RAIN = "70:ee:50:36:94:7c"
WIND = "70:ee:50:04:ed:7a"
FULL = "70:ee:50:36:a9:fc"


def test_parse_modules(public_body):
    data = parse_public_data(public_body)
    assert set(data) == {RAIN, WIND, FULL}
    assert data[RAIN].modules == {"base", "rain"}
    assert data[WIND].modules == {"base", "wind"}
    assert data[FULL].modules == {"base", "rain", "wind"}


def test_parse_values(public_body):
    data = parse_public_data(public_body)
    full = data[FULL]
    assert full.values.gust_strength == 31
    assert full.values.temperature == 20.1
    assert full.values.humidity == 67
    assert full.values.pressure == 1010
    assert full.values.rain_24h == 11.009
    assert full.timestamps["wind"] == datetime.fromtimestamp(1560248190, UTC)
    # location is [lon, lat] in the API
    assert round(full.lat, 3) == 50.196
    assert round(full.lon, 3) == 8.801
    assert full.city == "Sampletown"
    assert full.street == "Example Street"


def test_base_timestamp_is_oldest_of_temperature_and_pressure(public_body):
    data = parse_public_data(public_body)
    assert data[FULL].timestamps["base"] == datetime.fromtimestamp(1560248145, UTC)


def test_empty_res_gives_no_value_and_no_timestamp(public_body):
    station = public_body[0]
    for measure in station["measures"].values():
        if "type" in measure and "temperature" in measure["type"]:
            measure["res"] = {}
    data = parse_public_data(public_body)
    rain = data[RAIN]
    assert rain.values.temperature is None
    assert "base" in rain.modules
    assert "base" not in rain.timestamps


def test_unknown_layout_is_skipped(public_body):
    public_body[0]["measures"]["zz"] = {"foo": "bar"}
    public_body.append({"_id": "broken"})
    data = parse_public_data(public_body)
    assert RAIN in data
    assert "broken" not in data


def test_station_label(public_body):
    data = parse_public_data(public_body)
    full = data[FULL]
    assert station_label(full, None) == "Example Street, Sampletown"
    label = station_label(full, (full.lat, full.lon + 0.0117))
    assert label == "Example Street, Sampletown · 0.8 km"
    assert station_label(data[RAIN], None) == "Station 50:36:94:7c"
