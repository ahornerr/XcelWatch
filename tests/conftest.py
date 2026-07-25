"""Shared fixtures and helpers for xcel_outages pure-core tests.

This conftest provides fixtures for the pure parser/scoring test suite
(``test_parser.py``, ``test_scoring.py``).  These tests import only pure
modules (``parser``, ``scoring``, ``models``, ``const``) and do **not**
require Home Assistant.

The HA integration tests in ``tests/ha/`` use real ``homeassistant`` and
require it to be installed (see ``requirements_test.txt``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    """Load a JSON fixture from tests/fixtures/."""
    path = FIXTURE_DIR / name
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Parser fixtures — standard JSON
# ---------------------------------------------------------------------------


@pytest.fixture
def raw_events_empty():
    """Fully empty event list."""
    return load_fixture("events_empty.json")


@pytest.fixture
def raw_events_valid_empty():
    """Valid empty list fixture (same data, distinct semantic label)."""
    return load_fixture("events_valid_empty.json")


@pytest.fixture
def raw_events_small_nearby():
    """Two small sub-threshold Colorado events near Boulder."""
    return load_fixture("events_small_nearby.json")


@pytest.fixture
def raw_events_material_cluster():
    """Seven events: five material, two non-material, all Colorado."""
    return load_fixture("events_material_cluster.json")


@pytest.fixture
def raw_events_malformed():
    """Mix of valid event, non-dict entries, missing/bad coords, bad people."""
    return load_fixture("events_malformed.json")


@pytest.fixture
def raw_events_states_string():
    """Events with states as string, list, missing, non-CO, empty."""
    return load_fixture("events_states_string.json")


@pytest.fixture
def raw_events_resolved():
    """Mix of active and resolved/closed/cancelled events."""
    return load_fixture("events_resolved.json")


@pytest.fixture
def raw_events_dedup():
    """Events with duplicate identifier — later instance should win."""
    return load_fixture("events_dedup.json")


@pytest.fixture
def raw_events_growth():
    """Two material events for growth baseline tests."""
    return load_fixture("events_growth.json")


@pytest.fixture
def raw_events_non_list():
    """Non-list top-level response."""
    return load_fixture("events_non_list.json")


@pytest.fixture
def raw_events_outagestatus():
    """Events crossing top-level status and additionalProperties.outagestatus."""
    return load_fixture("events_outagestatus.json")


# ---------------------------------------------------------------------------
# Parser fixtures — inline Python for values JSON cannot represent
# ---------------------------------------------------------------------------


@pytest.fixture
def raw_events_bool_nonfinite():
    """Events with bool, fractional, non-finite coordinate values.

    These edge cases cannot be expressed in JSON fixtures.
    """
    return [
        {
            "identifier": True,
            "status": "ACTIVE",
            "numPeople": 50,
            "latitude": 39.75,
            "longitude": -105.0,
            "county": "Jefferson",
            "additionalProperties": {"states": ["CO"]},
        },
        {
            "identifier": "bool_numpeople",
            "status": "ACTIVE",
            "numPeople": False,
            "latitude": 39.75,
            "longitude": -105.0,
            "county": "Jefferson",
            "additionalProperties": {"states": ["CO"]},
        },
        {
            "identifier": "frac_numpeople",
            "status": "ACTIVE",
            "numPeople": 1.5,
            "latitude": 39.75,
            "longitude": -105.0,
            "county": "Jefferson",
            "additionalProperties": {"states": ["CO"]},
        },
        {
            "identifier": "inf_lat",
            "status": "ACTIVE",
            "numPeople": 50,
            "latitude": float("inf"),
            "longitude": -105.0,
            "county": "Jefferson",
            "additionalProperties": {"states": ["CO"]},
        },
        {
            "identifier": "nan_lon",
            "status": "ACTIVE",
            "numPeople": 50,
            "latitude": 39.75,
            "longitude": float("nan"),
            "county": "Jefferson",
            "additionalProperties": {"states": ["CO"]},
        },
    ]


@pytest.fixture
def raw_events_all_malformed():
    """A payload where every record is malformed → no valid output."""
    return [
        {"identifier": None, "status": "ACTIVE", "numPeople": 10,
         "latitude": 39.75, "longitude": -105.0, "county": "Test",
         "additionalProperties": {"states": ["CO"]}},
        {"identifier": "no_coords", "status": "ACTIVE", "numPeople": 10,
         "county": "Test", "additionalProperties": {"states": ["CO"]}},
        {"identifier": "bad_lat_val", "status": "ACTIVE", "numPeople": 10,
         "latitude": 999.0, "longitude": -105.0, "county": "Test",
         "additionalProperties": {"states": ["CO"]}},
    ]


# ---------------------------------------------------------------------------
# Reference coordinates — Golden, CO area
# ---------------------------------------------------------------------------


@pytest.fixture
def home_golden():
    """Approximate home coordinates near Golden, CO."""
    return {"lat": 39.7555, "lon": -105.2211}


@pytest.fixture
def home_denver():
    """Approximate home coordinates near downtown Denver."""
    return {"lat": 39.7392, "lon": -104.9903}


# ---------------------------------------------------------------------------
# Default scoring options
# ---------------------------------------------------------------------------


@pytest.fixture
def default_options():
    """Default scoring parameters from plan.md."""
    return {
        "search_radius_km": 25,
        "local_radius_km": 10,
        "material_threshold": 25,
    }
