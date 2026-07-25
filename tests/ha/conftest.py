"""Fixtures for Home Assistant integration tests.

Requires ``homeassistant`` and ``pytest-homeassistant-custom-component`` installed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest


def pytest_configure(config):
    """Enable asyncio auto mode for tests under this directory.

    Only activates when pytest-asyncio is installed (HA-test env);
    the pure-core test environment never sees this config key.
    """
    if config.pluginmanager.has_plugin("asyncio"):
        config.option.asyncio_mode = "auto"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Auto-use fixture so all HA tests discover custom_components/xcel_outages."""
    pass


from custom_components.xcel_outages.const import (
    DEFAULT_SEARCH_RADIUS,
    DEFAULT_LOCAL_RADIUS,
    DEFAULT_MATERIAL_THRESHOLD,
)
from custom_components.xcel_outages.models import OutageEvent, RiskContext


# ---------------------------------------------------------------------------
# RiskContext factory — creates specific risk contexts for sensor tests
# ---------------------------------------------------------------------------


def make_risk_context(
    risk: int = 0,
    band: str = "None",
    reason: str = "No material outages nearby",
    nearby_event_count: int = 0,
    material_event_count: int = 0,
    nearby_customer_total: int = 0,
    local_customer_total: int = 0,
    customer_total_increase: int = 0,
    nearest_km: float | None = None,
    nearest_material_km: float | None = None,
    largest_nearby_event_customers: int = 0,
) -> RiskContext:
    """Create a deterministic RiskContext with specified or default values."""
    return RiskContext(
        risk=risk,
        band=band,
        reason=reason,
        nearby_event_count=nearby_event_count,
        material_event_count=material_event_count,
        nearby_customer_total=nearby_customer_total,
        local_customer_total=local_customer_total,
        customer_total_increase=customer_total_increase,
        nearest_km=nearest_km,
        nearest_material_km=nearest_material_km,
        largest_nearby_event_customers=largest_nearby_event_customers,
    )


# ---------------------------------------------------------------------------
# Pre-built RiskContext fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def risk_ctx_zero() -> RiskContext:
    """Zero-risk context — no material outages."""
    return make_risk_context()


@pytest.fixture
def risk_ctx_low() -> RiskContext:
    """Low risk (15) — single material event nearby."""
    return make_risk_context(
        risk=15,
        band="Low",
        reason="Material outage detected nearby",
        nearby_event_count=1,
        material_event_count=1,
        nearby_customer_total=50,
        local_customer_total=50,
        nearest_km=3.5,
        nearest_material_km=3.5,
        largest_nearby_event_customers=50,
    )


@pytest.fixture
def risk_ctx_moderate() -> RiskContext:
    """Moderate risk (35) — regional watch conditions."""
    return make_risk_context(
        risk=35,
        band="Moderate",
        reason="Regional material outage cluster",
        nearby_event_count=3,
        material_event_count=2,
        nearby_customer_total=300,
        local_customer_total=100,
        customer_total_increase=0,
        nearest_km=1.2,
        nearest_material_km=1.2,
        largest_nearby_event_customers=150,
    )


@pytest.fixture
def risk_ctx_elevated() -> RiskContext:
    """Elevated risk (60) — concentrated local activity."""
    return make_risk_context(
        risk=60,
        band="Elevated",
        reason="Concentrated local outage activity",
        nearby_event_count=4,
        material_event_count=3,
        nearby_customer_total=500,
        local_customer_total=250,
        customer_total_increase=0,
        nearest_km=0.8,
        nearest_material_km=0.8,
        largest_nearby_event_customers=200,
    )


@pytest.fixture
def risk_ctx_high() -> RiskContext:
    """High risk (70) — widespread severe activity."""
    return make_risk_context(
        risk=70,
        band="High",
        reason="Widespread severe outage activity",
        nearby_event_count=7,
        material_event_count=5,
        nearby_customer_total=2500,
        local_customer_total=800,
        customer_total_increase=450,
        nearest_km=0.3,
        nearest_material_km=0.3,
        largest_nearby_event_customers=400,
    )


# ---------------------------------------------------------------------------
# Mock coordinator fixture
# ---------------------------------------------------------------------------


class MockCoordinator:
    """Simulates a DataUpdateCoordinator for testing sensor entities.

    Provides the minimal interface expected by ``CoordinatorEntity``:
    - ``data``: the latest ``RiskContext`` (or ``None``)
    - ``last_update_success``: ``bool``
    - ``last_successful_update``: ``datetime | None`` (isoformat string source)
    - ``async_request_refresh()``: no-op for synchronous tests
    """

    def __init__(
        self,
        data: RiskContext | None = None,
        last_update_success: bool = True,
        last_successful_update: datetime | None = None,
        hass=None,
    ) -> None:
        self.data = data
        self.last_update_success = last_update_success
        self.last_successful_update = last_successful_update
        self.hass = hass
        self._async_request_refresh_call_count = 0
        self._config_entry_id = "mock_entry_1"

    async def async_request_refresh(self) -> None:
        """Mock refresh — no-op, counts calls for test assertions."""
        self._async_request_refresh_call_count += 1


@pytest.fixture
def mock_coordinator_no_data() -> MockCoordinator:
    """Coordinator with no data yet (initial state before first poll)."""
    return MockCoordinator(data=None, last_update_success=True)


@pytest.fixture
def mock_coordinator_zero_risk(risk_ctx_zero) -> MockCoordinator:
    """Coordinator with zero-risk context (successful poll, no outages)."""
    return MockCoordinator(data=risk_ctx_zero, last_update_success=True)


@pytest.fixture
def mock_coordinator_low_risk(risk_ctx_low) -> MockCoordinator:
    """Coordinator with low-risk context (single material event)."""
    return MockCoordinator(
        data=risk_ctx_low,
        last_update_success=True,
        last_successful_update=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_coordinator_moderate_risk(risk_ctx_moderate) -> MockCoordinator:
    """Coordinator with moderate-risk context."""
    return MockCoordinator(
        data=risk_ctx_moderate,
        last_update_success=True,
        last_successful_update=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_coordinator_high_risk(risk_ctx_high) -> MockCoordinator:
    """Coordinator with high-risk context."""
    return MockCoordinator(
        data=risk_ctx_high,
        last_update_success=True,
        last_successful_update=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def mock_coordinator_before_after(
    risk_ctx_low, risk_ctx_high
) -> Callable[[], tuple[MockCoordinator, RiskContext, RiskContext]]:
    """Factory: create a coordinator that goes from low to high risk.

    Returns a callable so each test gets fresh instances.
    """
    def _create() -> tuple[MockCoordinator, RiskContext, RiskContext]:
        coord = MockCoordinator(
            data=risk_ctx_low,
            last_update_success=True,
            last_successful_update=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
        )
        return coord, risk_ctx_low, risk_ctx_high
    return _create


@pytest.fixture
def mock_coordinator_after_failure(risk_ctx_low) -> MockCoordinator:
    """Coordinator that previously had data but last update failed.

    ``data`` still holds the last good context.
    """
    return MockCoordinator(
        data=risk_ctx_low,
        last_update_success=False,
        last_successful_update=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Mock API client fixture
# ---------------------------------------------------------------------------


class MockApiClient:
    """Simulates the Xcel Energy outage-map HTTP client.

    Allows injecting response data or failure modes.
    """

    def __init__(
        self,
        response_data: Any = None,
        should_fail: bool = False,
    ) -> None:
        self.response_data = response_data if response_data is not None else []
        self.should_fail = should_fail
        self.call_count = 0
        self.last_headers: dict[str, str] | None = None
        self.last_timeout: float | None = None

    async def fetch_events(self) -> Any:
        """Return the configured response data or raise an exception."""
        self.call_count += 1
        if self.should_fail:
            raise MockApiError("Simulated API unreachable")
        return self.response_data


class MockApiError(Exception):
    """Simulated transport-level error from the API client."""


@pytest.fixture
def mock_api_client_ok() -> MockApiClient:
    """API client returning an empty list (valid but no events)."""
    return MockApiClient(response_data=[], should_fail=False)


@pytest.fixture
def mock_api_client_failing() -> MockApiClient:
    """API client that always fails (simulates unreachable endpoint)."""
    return MockApiClient(response_data=None, should_fail=True)


# ---------------------------------------------------------------------------
# Mock config entry fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_entry_data() -> dict[str, Any]:
    """Standard config entry data (HA location used)."""
    return {
        "lat": 39.7555,
        "lon": -105.2211,
        "use_ha_location": True,
    }


@pytest.fixture
def mock_config_entry_overrides() -> dict[str, Any]:
    """Config entry with override coordinates (no HA location)."""
    return {
        "lat": 39.7392,
        "lon": -104.9903,
        "use_ha_location": False,
    }


@pytest.fixture
def mock_config_entry_options() -> dict[str, Any]:
    """Default config entry options."""
    return {
        "search_radius": DEFAULT_SEARCH_RADIUS,
        "local_radius": DEFAULT_LOCAL_RADIUS,
        "material_threshold": DEFAULT_MATERIAL_THRESHOLD,
    }
