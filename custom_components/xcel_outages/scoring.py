"""Pure risk-context calculation for the Xcel Outage Map integration.

All functions are deterministic, pure, and dependency-free (standard library
only).  The primary public API is :func:`compute_risk_context`, which is the
main unit-test target of the pure-core layer.
"""

from __future__ import annotations

import dataclasses
import math
from .const import (
    BASE_SCORE_HIGH_LOCAL,
    BASE_SCORE_LOCAL_ELEVATED,
    BASE_SCORE_LOCAL_WATCH,
    BASE_SCORE_MATERIAL,
    BASE_SCORE_REGIONAL_ELEVATED,
    BASE_SCORE_REGIONAL_HIGH,
    BASE_SCORE_REGIONAL_WATCH,
    HIGH_LOCAL_DISTANCE_KM,
    INCREASE_BONUS,
    INCREASE_THRESHOLD,
    MAX_RISK,
    RISK_BANDS,
)
from .models import OutageEvent, RiskContext

# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0


def haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Compute the great-circle distance between two points in kilometres.

    Uses the Haversine formula.  Input is decimal degrees, output is km.
    """
    # Convert to radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_KM * c


# ---------------------------------------------------------------------------
# Internal annotated-event representation
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _AnnotatedEvent:
    """Internal pairing of an :class:`OutageEvent` with its computed distance.

    ``distance_km`` is **never** stored on the event model itself and is
    **never** exposed in any :class:`RiskContext` output — it exists only
    during the body of :func:`compute_risk_context`.
    """

    event: OutageEvent
    distance_km: float


# ---------------------------------------------------------------------------
# Risk-band resolution
# ---------------------------------------------------------------------------


def _resolve_band(risk: int) -> str:
    """Map a numeric *risk* score (0..100) to its human-readable band name."""
    for upper, label in RISK_BANDS:
        if risk <= upper:
            return label
    return RISK_BANDS[-1][1]  # fallback to highest band


def _resolve_reason(
    base_score: int, increase_bonus_applied: bool
) -> str:
    """Return a concise human-readable explanation for the computed score.

    The base-score table is deterministic, so the reason is derived from the
    highest-contributing base condition.
    """
    reasons: dict[int, str] = {
        0: "No material outages nearby",
        BASE_SCORE_MATERIAL: "Material outage detected nearby",
        BASE_SCORE_LOCAL_WATCH: "Local customer impact detected",
        BASE_SCORE_REGIONAL_WATCH: "Regional material outage cluster",
        BASE_SCORE_REGIONAL_ELEVATED: "Major regional outage cluster",
        BASE_SCORE_LOCAL_ELEVATED: "Concentrated local outage activity",
        BASE_SCORE_HIGH_LOCAL: "High-impact outage within 5 km",
        BASE_SCORE_REGIONAL_HIGH: "Widespread severe outage activity",
    }
    reason = reasons.get(base_score, "Unknown")
    if increase_bonus_applied:
        reason += "; customer-total increase detected"
    return reason


# ---------------------------------------------------------------------------
# Base-score computation
# ---------------------------------------------------------------------------


def _compute_base_score(
    material_event_count: int,
    nearby_customer_total: int,
    local_customer_total: int,
    local_material_event_count: int,
    material_customer_total_within_5km: int,
) -> int:
    """Determine the highest-matching base risk score from the rule table.

    Each condition is evaluated against the current aggregate values.  The
    **highest** qualifying score is returned (all conditions are checked; ties
    are broken by the fixed priority ordering defined by the rule sequence).
    """
    candidates: list[int] = [0]

    if material_event_count > 0:
        candidates.append(BASE_SCORE_MATERIAL)

    if local_customer_total >= 50:
        candidates.append(BASE_SCORE_LOCAL_WATCH)

    if nearby_customer_total >= 250 and material_event_count >= 2:
        candidates.append(BASE_SCORE_REGIONAL_WATCH)

    if nearby_customer_total >= 1000 and material_event_count >= 3:
        candidates.append(BASE_SCORE_REGIONAL_ELEVATED)

    if local_customer_total >= 200 and local_material_event_count >= 2:
        candidates.append(BASE_SCORE_LOCAL_ELEVATED)

    if material_customer_total_within_5km >= 100:
        candidates.append(BASE_SCORE_HIGH_LOCAL)

    if nearby_customer_total >= 2000 and material_event_count >= 5:
        candidates.append(BASE_SCORE_REGIONAL_HIGH)

    return max(candidates)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_risk_context(
    events: list[OutageEvent],
    home_lat: float,
    home_lon: float,
    *,
    search_radius: float = 25.0,
    local_radius: float = 10.0,
    material_threshold: int = 25,
    previous_total: int | None = None,
) -> RiskContext:
    """Compute a full risk-context result for a set of normalised events.

    This is the primary unit-test target of the pure-core layer.  All input
    events are expected to be pre-filtered to **active** events
    (see :func:`parser.parse_events`).

    Processing steps:

    1. Compute the Haversine distance from home to every event.
    2. Partition events into **nearby** (within ``search_radius``) and
       **material** (``num_people >= material_threshold``).
    3. Compute aggregate counts / totals from the material subset.
    4. Evaluate the base-score rule table, picking the highest qualifying
       condition.
    5. Apply the customer-total-increase bonus when ``previous_total`` is
       provided and the increase is at least :obj:`~const.INCREASE_THRESHOLD`.
    6. Assemble a :class:`~models.RiskContext` result.

    Parameters
    ----------
    events:
        Normalised, active-only outage events.
    home_lat:
        Home latitude in decimal degrees.
    home_lon:
        Home longitude in decimal degrees.
    search_radius:
        Maximum distance in km to consider an event "nearby".
    local_radius:
        Radius in km for "local" classification.  The effective local radius
        is ``min(local_radius, search_radius)``.
    material_threshold:
        Minimum ``num_people`` for an event to be considered "material".
    previous_total:
        The ``nearby_customer_total`` from the previous successful poll.
        When provided, the customer-total-increase bonus may be applied.

    Returns
    -------
    RiskContext:
        A frozen dataclass with all computed risk and aggregate fields.

    **Privacy guarantee**: No home coordinates appear in the returned context.
    """
    # --- 1. Compute distances (internal annotation — never leaks) ----------
    annotated: list[_AnnotatedEvent] = []
    for event in events:
        d = haversine_km(home_lat, home_lon, event.latitude, event.longitude)
        annotated.append(_AnnotatedEvent(event=event, distance_km=d))

    # --- 2. Filter by distance and material status -------------------------
    nearby_all: list[_AnnotatedEvent] = [
        ae for ae in annotated if ae.distance_km <= search_radius
    ]
    nearby_material: list[_AnnotatedEvent] = [
        ae for ae in nearby_all if ae.event.is_material(material_threshold)
    ]

    effective_local_radius = min(local_radius, search_radius)
    local_material: list[_AnnotatedEvent] = [
        ae for ae in nearby_material if ae.distance_km <= effective_local_radius
    ]

    material_within_5km: list[_AnnotatedEvent] = [
        ae for ae in nearby_material if ae.distance_km <= HIGH_LOCAL_DISTANCE_KM
    ]

    # --- 3. Aggregate counts / totals --------------------------------------
    nearby_event_count = len(nearby_all)
    material_event_count = len(nearby_material)

    nearby_customer_total = sum(ae.event.num_people for ae in nearby_material)
    local_customer_total = sum(ae.event.num_people for ae in local_material)
    material_customer_total_within_5km = sum(
        ae.event.num_people for ae in material_within_5km
    )
    local_material_event_count = len(local_material)

    # --- Nearest distances -------------------------------------------------
    nearest_km: float | None = (
        min(ae.distance_km for ae in nearby_all) if nearby_all else None
    )
    nearest_material_km: float | None = (
        min(ae.distance_km for ae in nearby_material) if nearby_material else None
    )

    # --- Largest material event --------------------------------------------
    largest_nearby_event_customers = (
        max(ae.event.num_people for ae in nearby_material) if nearby_material else 0
    )

    # --- 4. Base score -----------------------------------------------------
    base_score = _compute_base_score(
        material_event_count=material_event_count,
        nearby_customer_total=nearby_customer_total,
        local_customer_total=local_customer_total,
        local_material_event_count=local_material_event_count,
        material_customer_total_within_5km=material_customer_total_within_5km,
    )

    # --- 5. Customer-total-increase bonus ----------------------------------
    increase = 0
    if previous_total is not None:
        increase = max(0, nearby_customer_total - previous_total)
    increase_bonus_applied = increase >= INCREASE_THRESHOLD
    risk = min(MAX_RISK, base_score + (INCREASE_BONUS if increase_bonus_applied else 0))

    return RiskContext(
        risk=risk,
        band=_resolve_band(risk),
        reason=_resolve_reason(base_score, increase_bonus_applied),
        nearby_event_count=nearby_event_count,
        material_event_count=material_event_count,
        nearby_customer_total=nearby_customer_total,
        local_customer_total=local_customer_total,
        customer_total_increase=increase,
        nearest_km=nearest_km,
        nearest_material_km=nearest_material_km,
        largest_nearby_event_customers=largest_nearby_event_customers,
    )
