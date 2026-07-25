"""Pure-domain data models for the Xcel Outage Map integration.

All models are typed dataclasses using only the standard library.  No Home
Assistant or third-party dependencies.
"""

from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Mapping
from typing import Any


@dataclasses.dataclass(frozen=True, order=False)
class OutageEvent:
    """A single normalized outage event.

    Every field is validated and coerced from the raw API representation.
    The model is fully immutable — ``additional_properties`` is a read-only
    :class:`~collections.abc.Mapping` with ``states`` normalised to a
    ``tuple[str, ...]``.
    """

    # ---- core identifiers -------------------------------------------------
    identifier: str
    """Unique outage identifier supplied by the source."""

    # ---- timestamps -------------------------------------------------------
    start_time: datetime.datetime | None
    """When the outage was first reported (ISO-8601), if available."""

    last_updated_time: datetime.datetime | None
    """Most recent source update timestamp, if available.

    Used for deterministic deduplication — the event with the most recent
    ``last_updated_time`` wins when two events share the same ``identifier``.
    """

    etr_time: datetime.datetime | None
    """Estimated time of restoration, if supplied by the source."""

    # ---- descriptive fields -----------------------------------------------
    title: str
    """Short outage title / description."""

    status: str
    """Outage status string from the source (e.g. ``"Active"``)."""

    cause: str
    """Root-cause description when provided; empty string otherwise."""

    # ---- impact -----------------------------------------------------------
    num_people: int
    """Number of affected customers reported by the source.

    A value of zero is valid — the event may be non-material for scoring.
    """

    # ---- geography --------------------------------------------------------
    latitude: float
    """Centroid latitude of the outage area (decimal degrees)."""

    longitude: float
    """Centroid longitude of the outage area (decimal degrees)."""

    county: str
    """County name, if provided by the source."""

    additional_properties: Mapping[str, Any]
    """Read-only supplemental mapping from the source.

    The ``states`` key is normalised to a ``tuple[str, ...]``.  Other
    commonly-present keys include ``city``, ``outageimpact``,
    ``outagestatus``, and ``comments``.

    This mapping is **immutable** — it is backed by
    :class:`types.MappingProxyType` so values cannot be mutated in-place.
    """

    def is_material(self, threshold: int) -> bool:
        """Return ``True`` when the affected-customer count >= *threshold*."""
        return self.num_people >= threshold

@dataclasses.dataclass(frozen=True)
class RiskContext:
    """Complete risk-assessment result for a single poll cycle.

    Returned by :func:`scoring.compute_risk_context` — the primary unit-test
    target of the pure-core layer.
    """

    risk: int
    """Ordinal nearby-outage risk score in 0..100."""

    band: str
    """Human-readable risk band (None / Low / Moderate / Elevated / High /
    Severe)."""

    reason: str
    """Concise human-readable explanation for the current score."""

    nearby_event_count: int
    """Total number of events (any customer count) within the search radius."""

    material_event_count: int
    """Number of **material** events (``num_people >= threshold``) within the
    search radius."""

    nearby_customer_total: int
    """Sum of affected customers from **material** events within the search
    radius."""

    local_customer_total: int
    """Sum of affected customers from **material** events within the effective
    local radius (``min(local_radius, search_radius)``)."""

    customer_total_increase: int
    """Growth in the nearby-customer total since the previous successful poll
    (``max(0, current - previous)``).  Zero when no prior total is available.
    """

    nearest_km: float | None
    """Distance in km to the closest event (any customer count) within the
    search radius.  ``None`` when no events are nearby."""

    nearest_material_km: float | None
    """Distance in km to the closest **material** event within the search
    radius.  ``None`` when no material events are nearby."""

    largest_nearby_event_customers: int
    """Customer count of the largest **material** event within the search
    radius.  Zero when no material events are nearby."""


@dataclasses.dataclass(frozen=True)
class ParseOutcome:
    """Structured result of parsing a raw API payload.

    Returned by :func:`parser.parse_payload`.  Distinguishes non-list payloads
    (schema failure) from valid-empty, filtered-empty, and normal data through
    the combination of ``is_valid_payload`` and the count fields.
    """

    events: tuple[OutageEvent, ...]
    """Successfully parsed, deduplicated events after terminal-status filtering."""

    is_valid_payload: bool
    """``True`` when the top-level JSON value was a ``list``."""

    raw_count: int
    """Number of items in the payload list (0 for non-list payloads)."""

    parsed_count: int
    """Number of raw items that passed :func:`parser.parse_event` successfully
    (before status filtering)."""

    malformed_count: int
    """Number of raw items that failed :func:`parser.parse_event`."""

    filtered_status_count: int
    """Number of successfully-parsed items excluded for a resolved/closed/
    cancelled ``status`` or ``outagestatus``."""
