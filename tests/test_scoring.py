"""Tests for the scoring module.

Target module: ``custom_components.xcel_outages.scoring``.

The public API is :func:`compute_risk_context`, which accepts normalised
``OutageEvent`` instances, home coordinates, radius options, material threshold,
and an optional previous customer total, returning a ``RiskContext`` dataclass
as specified in ``docs/scoring-contract.md`` §2.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from custom_components.xcel_outages.models import OutageEvent
from custom_components.xcel_outages.scoring import compute_risk_context


_EARTH_RADIUS_KM = 6371.0


def _offset_lat_for_distance_km(distance_km: float) -> float:
    """Latitude offset (degrees) for a pure north-south displacement."""
    return distance_km / _EARTH_RADIUS_KM * (180.0 / math.pi)


# =========================================================================
# Helper: parse + score shorthand
# =========================================================================


def _score(
    raw_events,
    home_lat: float,
    home_lon: float,
    search_radius: float = 25.0,
    local_radius: float = 10.0,
    material_threshold: int = 25,
    previous_total: int | None = None,
):
    """Shortcut: parse raw events then compute risk context."""
    from custom_components.xcel_outages.parser import parse_events

    events = parse_events(raw_events)
    return compute_risk_context(
        events=events,
        home_lat=home_lat,
        home_lon=home_lon,
        search_radius=search_radius,
        local_radius=local_radius,
        material_threshold=material_threshold,
        previous_total=previous_total,
    )


# =========================================================================
# 1. No material events — baseline
# =========================================================================


class TestNoMaterialEvents:
    """When no material events exist, risk must be 0 and band 'None'."""

    def test_empty_events(self, raw_events_empty, home_golden):
        result = compute_risk_context(
            [], home_golden["lat"], home_golden["lon"]
        )
        assert result.risk == 0
        assert result.band == "None"
        assert result.material_event_count == 0
        assert result.nearby_event_count == 0
        assert result.nearby_customer_total == 0

    def test_only_subthreshold_events(self, raw_events_small_nearby, home_denver):
        """Events exist but are sub-threshold (num_people 1-3)."""
        result = _score(
            raw_events_small_nearby,
            home_denver["lat"], home_denver["lon"],
            search_radius=60,
            material_threshold=25,
        )
        assert result.risk == 0
        assert result.band == "None"
        assert result.material_event_count == 0
        assert result.nearby_event_count == 2


# =========================================================================
# 2. Material nearby — risk 15
# =========================================================================


class TestMaterialNearby:
    """Material nearby events produce at least risk 15."""

    def test_single_material_event(self, home_golden):
        events = [_make_event("e1", 25, 39.85, -105.30)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            material_threshold=25,
        )
        assert result.risk >= 15
        assert result.material_event_count == 1

    def test_material_outside_local_inside_search(self, home_golden):
        events = [_make_event("e1", 30, 39.85, -105.30)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.risk == 15
        assert result.band == "Low"


# =========================================================================
# 3. Local total >= 50 — risk 30
# =========================================================================


class TestLocalTotalThreshold:
    """Local customer total >= 50 → risk 30 (if no higher condition matches)."""

    def test_local_total_exact_50(self, home_golden):
        events = [_make_event("e1", 50, 39.756, -105.222)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            local_radius=10, material_threshold=25,
        )
        assert result.risk == 30
        assert result.band == "Moderate"
        assert result.local_customer_total >= 50

    def test_local_total_49_not_threshold(self, home_golden):
        events = [_make_event("e1", 49, 39.756, -105.222)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            material_threshold=25,
        )
        assert result.risk == 15


# =========================================================================
# 4. Nearby total >= 250 + >= 2 events — risk 35
# =========================================================================


class TestNearbyTotal250:
    """Nearby >= 250 customers with >= 2 material events → risk 35."""

    def test_nearby_250_two_events(self, home_golden):
        events = [
            _make_event("e1", 130, 39.85, -105.30),
            _make_event("e2", 130, 39.65, -105.10),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.risk == 35
        assert result.band == "Moderate"

    def test_negative_gate_250_one_event(self, home_golden):
        """250 customers with only 1 event → NOT risk 35 (needs >= 2)."""
        events = [_make_event("e1", 250, 39.85, -105.30)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        # 250 customers, 1 event: material=true, local total=0 (<50),
        # 5km=0 (<100), so just risk 15
        assert result.risk == 15
        assert result.nearby_customer_total == 250
        assert result.material_event_count == 1


# =========================================================================
# 5. Nearby total >= 1,000 + >= 3 events — risk 50
# =========================================================================


class TestNearbyTotal1000:
    """Nearby >= 1000 customers with >= 3 material events → risk 50."""

    def test_nearby_1000_three_events(self, home_golden):
        events = [
            _make_event("e1", 340, 39.86, -105.30),
            _make_event("e2", 340, 39.64, -105.10),
            _make_event("e3", 340, 39.91, -105.40),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.risk == 50
        assert result.band == "Elevated"

    def test_negative_gate_1000_two_events(self, home_golden):
        """1000 customers with only 2 events → NOT risk 50 (needs >= 3)."""
        events = [
            _make_event("e1", 500, 39.85, -105.30),
            _make_event("e2", 500, 39.65, -105.10),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        # 1000 customers, 2 events: risk 35 (250+ with 2+ events)
        assert result.risk == 35
        assert result.nearby_customer_total == 1000
        assert result.material_event_count == 2


# =========================================================================
# 6. Local total >= 200 + >= 2 local events — risk 60
# =========================================================================


class TestLocalTotal200:
    """Local >= 200 customers with >= 2 local material events → risk 60."""

    def test_local_200_two_events(self, home_golden):
        events = [
            _make_event("e1", 100, 39.82, -105.27),
            _make_event("e2", 100, 39.69, -105.17),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.risk == 60
        assert result.band == "Elevated"

    def test_negative_gate_local200_one_event(self, home_golden):
        """200 local customers with only 1 local event → NOT risk 60 (needs >= 2)."""
        events = [_make_event("e1", 200, 39.756, -105.222)]  # ~0.1 km → local
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        # 200 customers, 1 local event: 5km total = 200 >= 100 → risk 65!
        assert result.risk == 65
        assert result.local_customer_total == 200
        # The 200 customer event is within 5 km, so 5-km condition triggers


# =========================================================================
# 7. Five-km total >= 100 — risk 65
# =========================================================================


class TestFiveKmTotal:
    """Material customer total within 5 km >= 100 → risk 65."""

    def test_five_km_100(self, home_golden):
        events = [_make_event("e1", 100, 39.756, -105.222)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            material_threshold=25,
        )
        assert result.risk == 65
        assert result.band == "High"


# =========================================================================
# 8. Nearby total >= 2,000 + >= 5 events — risk 70
# =========================================================================


class TestNearbyTotal2000:
    """Nearby >= 2000 customers with >= 5 material events → risk 70."""

    def test_nearby_2000_five_events(self, home_golden):
        events = [
            _make_event("e1", 400, 39.86, -105.30),
            _make_event("e2", 400, 39.64, -105.10),
            _make_event("e3", 400, 39.91, -105.42),
            _make_event("e4", 400, 39.62, -105.35),
            _make_event("e5", 400, 39.88, -105.08),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.risk == 70
        assert result.band == "High"

    def test_negative_gate_2000_four_events(self, home_golden):
        """2000 customers with only 4 events → NOT risk 70 (needs >= 5)."""
        events = [
            _make_event("e1", 500, 39.86, -105.30),
            _make_event("e2", 500, 39.64, -105.10),
            _make_event("e3", 500, 39.91, -105.42),
            _make_event("e4", 500, 39.62, -105.35),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        # 2000 customers, 4 events: risk 50 (1000+ with 3+)
        assert result.risk == 50
        assert result.nearby_customer_total == 2000
        assert result.material_event_count == 4


# =========================================================================
# 9. Multiple conditions — maximum score wins
# =========================================================================


class TestMaxScoreWins:
    """When multiple conditions match, the highest score is returned."""

    def test_higher_score_overrides_lower(self, home_golden):
        events = [
            _make_event("e1", 100, 39.756, -105.222),
            _make_event("e2", 50, 39.86, -105.31),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            material_threshold=25,
        )
        assert result.risk == 65


# =========================================================================
# 10. Growth bonus — customer_total_increase
# =========================================================================


class TestGrowthBonus:
    """Customer total increase >= INCREASE_THRESHOLD (250) triggers +15 bonus.

    The RiskContext field is named ``customer_total_increase``.
    """

    def test_growth_bonus_applied(self, home_golden):
        events = [
            _make_event("e1", 130, 39.85, -105.30),
            _make_event("e2", 130, 39.65, -105.10),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
            previous_total=0,
        )
        assert result.customer_total_increase == 260
        assert result.risk == 50
        assert "customer-total increase" in result.reason

    def test_no_bonus_below_threshold(self, home_golden):
        events = [
            _make_event("e1", 130, 39.85, -105.30),
            _make_event("e2", 124, 39.65, -105.10),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            previous_total=5,
            material_threshold=25,
        )
        assert result.customer_total_increase == 249
        assert result.risk == 35
        assert "customer-total increase" not in result.reason

    def test_no_growth_on_first_poll(self, home_golden):
        events = [
            _make_event("e1", 130, 39.85, -105.30),
            _make_event("e2", 130, 39.65, -105.10),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            previous_total=None,
            material_threshold=25,
        )
        assert result.customer_total_increase == 0
        assert result.risk == 35

    def test_no_growth_when_decrease(self, home_golden):
        events = [
            _make_event("e1", 130, 39.85, -105.30),
            _make_event("e2", 130, 39.65, -105.10),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            previous_total=500,
            material_threshold=25,
        )
        assert result.customer_total_increase == 0
        assert result.risk == 35

    def test_bonus_capped_at_100(self, home_golden):
        events = [_make_event("e1", 1000, 39.756, -105.222)]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            previous_total=100,
            material_threshold=25,
        )
        assert result.risk == 80
        assert result.risk <= 100


# =========================================================================
# 11. Inclusive boundary conditions — mathematically precise coordinates
# =========================================================================


class TestInclusiveBoundaries:
    """Thresholds use >= (inclusive).  Exact boundary events are included
    using mathematically computed coordinates (pure north-south offset)."""

    @staticmethod
    def _north_event(eid, num_people, distance_km, h_lat, h_lon):
        """Create an event exactly *distance_km* due north of (h_lat, h_lon)."""
        delta = _offset_lat_for_distance_km(distance_km)
        return _make_event(eid, num_people, h_lat + delta, h_lon)

    def test_exact_material_threshold(self, home_golden):
        events = [self._north_event("e1", 25, 1.0, home_golden["lat"], home_golden["lon"])]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            material_threshold=25,
        )
        assert result.material_event_count == 1

    def test_exact_search_radius_boundary(self, home_golden):
        """Event at approximately search_radius (24.999 km) → nearby inclusive.
        Uses 24.999 km because floating-point rounding may push exact 25.0 km
        slightly over the boundary, causing an exclusive result."""
        events = [self._north_event("e1", 50, 24.999, home_golden["lat"], home_golden["lon"])]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.nearby_event_count == 1
        assert result.risk == 15

    def test_exact_local_radius_boundary(self, home_golden):
        """Event exactly at local_radius (10 km) → local (inclusive)."""
        events = [self._north_event("e1", 50, 10.0, home_golden["lat"], home_golden["lon"])]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.local_customer_total >= 50
        assert result.risk == 30

    def test_exact_5km_high_local_boundary(self, home_golden):
        """Event exactly at 5 km boundary → within 5 km (inclusive)."""
        events = [self._north_event("e1", 100, 5.0, home_golden["lat"], home_golden["lon"])]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            material_threshold=25,
        )
        assert result.risk == 65

    def test_exact_250_customer_boundary(self, home_golden):
        """Exactly 250 customers (threshold) with exactly 2 events → risk 35."""
        events = [
            self._north_event("e1", 125, 12.0, home_golden["lat"], home_golden["lon"]),
            self._north_event("e2", 125, 14.0, home_golden["lat"], home_golden["lon"]),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=10,
            material_threshold=25,
        )
        assert result.nearby_customer_total == 250
        assert result.material_event_count == 2
        assert result.risk == 35


# =========================================================================
# 12. Local radius capping
# =========================================================================


class TestLocalRadiusCapping:
    """local_radius must be capped to search_radius."""

    def test_local_capped_to_search(self, home_golden):
        delta = _offset_lat_for_distance_km(17.0)
        events = [
            _make_event("e1", 100, home_golden["lat"] + delta, home_golden["lon"])
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, local_radius=50,
            material_threshold=25,
        )
        assert result.risk == 30


# =========================================================================
# 13. Output shape and privacy
# =========================================================================


class TestOutputShapeAndPrivacy:
    """RiskContext must contain expected fields and never home coords."""

    def test_is_risk_context_instance(self, raw_events_material_cluster, home_denver):
        from custom_components.xcel_outages.models import RiskContext

        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        assert isinstance(result, RiskContext)

    def test_expected_attributes_present(self, raw_events_material_cluster, home_denver):
        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        assert isinstance(result.risk, int)
        assert isinstance(result.band, str)
        assert isinstance(result.reason, str)
        assert isinstance(result.nearby_event_count, int)
        assert isinstance(result.material_event_count, int)
        assert isinstance(result.nearby_customer_total, int)
        assert isinstance(result.local_customer_total, int)
        assert isinstance(result.customer_total_increase, int)
        assert result.nearest_km is None or isinstance(result.nearest_km, float)
        assert result.nearest_material_km is None or isinstance(
            result.nearest_material_km, float
        )
        assert isinstance(result.largest_nearby_event_customers, int)

    def test_risk_in_range(self, raw_events_material_cluster, home_denver):
        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        assert 0 <= result.risk <= 100

    def test_band_is_valid(self, raw_events_material_cluster, home_denver):
        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        valid_bands = {"None", "Low", "Moderate", "Elevated", "High", "Severe"}
        assert result.band in valid_bands, f"Invalid band: {result.band}"

    def test_no_home_coordinate_attributes(
        self, raw_events_material_cluster, home_denver
    ):
        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        forbidden = {"home_lat", "home_lon", "home_latitude", "home_longitude"}
        assert not any(hasattr(result, attr) for attr in forbidden), (
            f"RiskContext contains home coordinate fields: "
            f"{[a for a in forbidden if hasattr(result, a)]}"
        )

    def test_no_event_summaries_exposed(
        self, raw_events_material_cluster, home_denver
    ):
        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        assert not hasattr(result, "event_summaries"), (
            "RiskContext must not expose an event_summaries field"
        )


# =========================================================================
# 14. Edge: material cluster fixture from disk (full pipeline)
# =========================================================================


class TestMaterialClusterFixture:
    """Run the full parse+score pipeline against the material cluster fixture."""

    def test_denver_home_detects_material_events(
        self, raw_events_material_cluster, home_denver
    ):
        result = _score(
            raw_events_material_cluster,
            home_denver["lat"], home_denver["lon"],
        )
        assert result.material_event_count >= 5
        assert result.nearby_customer_total >= 3000
        assert result.risk == 70
        assert result.band == "High"

    def test_golden_home_reduces_nearby_count(
        self, raw_events_material_cluster, home_golden
    ):
        result = _score(
            raw_events_material_cluster,
            home_golden["lat"], home_golden["lon"],
        )
        assert result.nearby_event_count >= 5
        assert result.material_event_count >= 3


# =========================================================================
# 15. Distance — not state — is the geographic inclusion criterion
# =========================================================================


class TestDistanceIsGeographicCriterion:
    """Scoring includes events based solely on distance from home
    coordinates, not on state/territory boundaries.  An event from
    any location (including non-CO states or missing state data) is
    scored normally as long as it falls within the search radius."""

    def test_non_co_event_scored_when_nearby(self, home_golden):
        """A Minnesota event near Golden, CO is included when within radius."""
        events = [
            _make_event("mn_event", 50, 39.85, -105.30, state="MN"),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, material_threshold=25,
        )
        assert result.nearby_event_count == 1
        assert result.risk >= 15

    def test_event_without_state_scored_when_nearby(self, home_golden):
        """An event with no state field is included when within radius."""
        now = datetime.now(timezone.utc)
        event = OutageEvent(
            identifier="no_state_event",
            start_time=now,
            last_updated_time=now,
            etr_time=None,
            title="No state",
            status="ACTIVE",
            cause="test",
            num_people=100,
            latitude=39.76,
            longitude=-105.20,
            county="Test",
            additional_properties={"city": "Test City"},
        )
        result = compute_risk_context(
            [event], home_golden["lat"], home_golden["lon"],
            search_radius=25, material_threshold=25,
        )
        assert result.nearby_event_count == 1
        assert result.risk >= 15

    def test_event_far_away_not_counted(self, home_golden):
        """An event outside the search radius is excluded regardless of
        state."""
        events = [
            _make_event("far_event", 50, 50.0, -105.0, state="AB"),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, material_threshold=25,
        )
        assert result.nearby_event_count == 0
        assert result.risk == 0

    def test_mixed_state_events_all_included_by_distance(self, home_golden):
        """Events from CO, MN, and without state are all scored when
        within range."""
        now = datetime.now(timezone.utc)
        events = [
            _make_event("co_event", 30, 39.85, -105.30, state="CO"),
            _make_event("mn_event", 40, 39.75, -105.10, state="MN"),
            OutageEvent(
                identifier="no_state_event",
                start_time=now, last_updated_time=now, etr_time=None,
                title="No state", status="ACTIVE", cause="test",
                num_people=50, latitude=39.80, longitude=-105.20,
                county="Test",
                additional_properties={"city": "Test City"},
            ),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, material_threshold=25,
        )
        assert result.nearby_event_count == 3
        assert result.material_event_count == 3

    def test_nearest_km_is_distance_based(self, home_golden):
        """nearest_km reflects the closest event by distance, regardless
        of state/territory."""
        events = [
            _make_event("close_nearby", 10, 39.80, -105.25),
            _make_event("farther", 10, 50.0, -105.0, state="AB"),
        ]
        result = compute_risk_context(
            events, home_golden["lat"], home_golden["lon"],
            search_radius=25, material_threshold=25,
        )
        # Only the close event is counted
        assert result.nearby_event_count == 1
        assert result.nearest_km is not None
        assert result.nearest_km < 25.0


# =========================================================================
# Internal helpers
# =========================================================================


def _make_event(
    identifier: str,
    num_people: int,
    lat: float,
    lon: float,
    status: str = "ACTIVE",
    state: str = "CO",
) -> OutageEvent:
    """Create a minimal ``OutageEvent`` for scoring tests.

    The event is pre-validated (parser is not invoked). Use this for
    scoring-only tests that do not need to exercise the parser.
    """
    now = datetime.now(timezone.utc)
    return OutageEvent(
        identifier=identifier,
        start_time=now,
        last_updated_time=now,
        etr_time=None,
        title=f"Test {identifier}",
        status=status,
        cause="test",
        num_people=num_people,
        latitude=lat,
        longitude=lon,
        county="Test",
        additional_properties={"states": [state], "city": "Test City"},
    )
