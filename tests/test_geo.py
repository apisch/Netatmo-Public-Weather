"""Tests for geo helpers."""

import pytest

from custom_components.netatmo_public_weather.geo import (
    bbox_around,
    bbox_from_radius,
    haversine_km,
)


def _contains(b, lat, lon) -> bool:
    return b.lat_sw <= lat <= b.lat_ne and b.lon_sw <= lon <= b.lon_ne


def test_haversine():
    assert haversine_km(52.28, 7.44, 52.29, 7.44) == pytest.approx(1.11, abs=0.01)


def test_bbox_from_radius():
    b = bbox_from_radius(52.0, 7.0, 3)
    dlat = 2.9 / 111.2
    dlon = 2.9 / (111.2 * 0.6157)  # cos(52°)
    assert _contains(b, 52.0 + dlat, 7.0)
    assert _contains(b, 52.0 - dlat, 7.0)
    assert _contains(b, 52.0, 7.0 + dlon)
    assert _contains(b, 52.0, 7.0 - dlon)
    assert not _contains(b, 52.0 + 3.5 / 111.2, 7.0)
    assert not _contains(b, 52.0, 7.0 + 3.5 / (111.2 * 0.6157))


def test_bbox_around():
    b = bbox_around([(52.0, 7.0), (52.01, 7.02)], 0.3)
    assert b.lat_ne > 52.01
    assert b.lat_sw < 52.0
    assert b.lon_ne > 7.02
    assert b.lon_sw < 7.0
