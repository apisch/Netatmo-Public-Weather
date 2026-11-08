"""Shared fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration in every test."""
    yield


@pytest.fixture
def public_body() -> list[dict]:
    """Return the body of the getpublicdata fixture."""
    return json.loads((FIXTURES / "getpublicdata.json").read_text())["body"]
