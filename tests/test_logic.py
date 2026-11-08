"""Tests for health, failover and aggregation."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.netatmo_public_weather.logic import (
    FailoverSelector,
    aggregate,
    derive_condition,
    dew_point,
    is_healthy,
)
from custom_components.netatmo_public_weather.model import StationData, WeatherValues

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
STALE = timedelta(minutes=30)
ALL = frozenset({"base", "rain", "wind"})


def _station(ages: dict[str, int], modules=ALL) -> StationData:
    return StationData(
        station_id="70:ee:50:00:00:01",
        lat=52.0,
        lon=7.0,
        altitude=None,
        city=None,
        street=None,
        modules=frozenset(modules),
        timestamps={m: NOW - timedelta(minutes=a) for m, a in ages.items()},
    )


def test_healthy_when_fresh():
    assert is_healthy(_station({"base": 5, "rain": 5, "wind": 9}), ALL, NOW, STALE)


def test_unhealthy_when_one_module_stale():
    assert not is_healthy(_station({"base": 5, "rain": 5, "wind": 31}), ALL, NOW, STALE)


def test_unhealthy_when_expected_module_missing():
    data = _station({"base": 5, "rain": 5}, modules={"base", "rain"})
    assert not is_healthy(data, ALL, NOW, STALE)


def test_unhealthy_when_no_data():
    assert not is_healthy(None, ALL, NOW, STALE)


def test_future_timestamp_is_fresh():
    assert is_healthy(_station({"base": -5, "rain": 1, "wind": 1}), ALL, NOW, STALE)


def test_failover_sequence():
    sel = FailoverSelector(3)
    T, F = True, False
    assert sel.update([T, T, T]) == 0
    assert sel.update([F, T, T]) == 1
    assert sel.update([T, T, T]) == 1  # first good poll of primary
    assert sel.update([T, T, T]) == 0  # second good poll -> fail back
    assert sel.update([F, F, F]) is None
    assert sel.update([F, F, T]) == 2


def test_failover_first_update_picks_first_healthy():
    sel = FailoverSelector(3)
    assert sel.update([False, False, True]) == 2
    assert sel.active == 2


def test_failback_counter_resets_on_bad_poll():
    sel = FailoverSelector(2)
    sel.update([False, True])
    assert sel.update([True, True]) == 1
    assert sel.update([False, True]) == 1
    assert sel.update([True, True]) == 1
    assert sel.update([True, True]) == 0


def test_aggregate_mean_and_max():
    a = WeatherValues(temperature=10, humidity=80, wind_strength=10, gust_strength=20,
                      wind_angle=10, gust_angle=15, rain_24h=0.2)
    b = WeatherValues(temperature=12, humidity=90, wind_strength=30, gust_strength=45,
                      wind_angle=200, gust_angle=210, rain_24h=1.4)
    c = WeatherValues(temperature=None)
    v = aggregate([a, b, c])
    assert v.temperature == pytest.approx(11.0)
    assert v.humidity == pytest.approx(85.0)
    assert v.wind_strength == 30
    assert v.gust_strength == 45
    assert v.wind_angle == 200
    assert v.gust_angle == 210
    assert v.rain_24h == 1.4
    assert v.pressure is None


def test_aggregate_angles_from_max_wind_without_gust():
    a = WeatherValues(wind_strength=5, wind_angle=10)
    b = WeatherValues(wind_strength=9, wind_angle=90)
    v = aggregate([a, b])
    assert v.wind_angle == 90


def test_aggregate_empty():
    assert aggregate([]) == WeatherValues()


@pytest.mark.parametrize(
    ("values", "source", "expected"),
    [
        (WeatherValues(rain_live=0.3), "sunny", "rainy"),
        (WeatherValues(rain_live=0.3), "pouring", "pouring"),
        (WeatherValues(rain_live=0.3), "snowy", "snowy"),
        (WeatherValues(rain_live=0), "cloudy", "cloudy"),
        (WeatherValues(rain_live=None), "cloudy", "cloudy"),
        (WeatherValues(wind_strength=40), None, "windy"),
        (WeatherValues(gust_strength=50), None, "windy"),
        (WeatherValues(wind_strength=10, gust_strength=20), None, None),
        (WeatherValues(rain_live=0.1, wind_strength=60), None, "rainy"),
    ],
)
def test_derive_condition(values, source, expected):
    assert derive_condition(values, source) == expected


def test_dew_point():
    assert dew_point(20, 50) == pytest.approx(9.3, abs=0.1)
    assert dew_point(None, 50) is None
    assert dew_point(20, 0) is None
