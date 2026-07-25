# Scoring Contract — Xcel Outage Map

This document is the **normative contract** between the source implementation lane
and the independent test/documentation lane. Both lanes satisfy the requirements
encoded here. Any change to scoring or parsing semantics must update this contract
first.

---

## 1. Parsing Contract (`custom_components.xcel_outages.parser`)

### 1.1 Public API
```
parse_events(raw_list: list[Any]) -> list[OutageEvent]
```

### 1.2 Input
A raw JSON-decoded value from the Xcel Energy outage-map cache endpoint.

### 1.3 Structured Parse Outcomes

| Input | Outcome | Classification |
|-------|---------|---------------|
| Non-list (`None`, `dict`, etc.) | Return `[]` | **Invalid top-level** |
| Empty list `[]` | Return `[]` | **Valid empty list** |
| List where every record fails validation/filtering | Return `[]` | **All-malformed records** |
| List with at least one passing record | Return filtered `list[OutageEvent]` | **Valid filtered records** |

All four outcomes are distinguished at the semantic level and covered by tests.

### 1.4 Per-Event Validation (`parse_event`)

Each element must be a `dict`. Non-dict elements are silently skipped.

Required fields (must be present as keys):
- `identifier` — must be a non-empty string; **bool** values (even `True`) are rejected.
- `latitude` — must parse as a finite float in [-90, 90]; **non-finite** values (inf, NaN) are rejected.
- `longitude` — must parse as a finite float in [-180, 180]; **non-finite** values are rejected.
- `numPeople` — must be a non-negative **integer**; **bool**, **fractional**, and **non-finite** values are rejected.

If any required field is missing or invalid, the event is **skipped** (returns
`None`). No exception is raised.

### 1.5 Field Normalisation

| Source Field | Normalisation |
|---|---|
| `additionalProperties` | Promoted as a `dict`; missing → `{}`. Non-dict causes skip. |
| `states` (inside `additionalProperties`) | Normalised to an **immutable tuple** of strings. String → `(string,)`. Missing → `()`. List → `tuple(list)`. |
| `startTime`, `lastUpdatedTime`, `etrTime` | Parsed as ISO-8601 `datetime` (optional; parse failure → `None`). |
| `title`, `status`, `cause`, `county` | String, defaults to `""`. |

### 1.6 States Field Handling
The `states` field inside `additionalProperties` is normalised as source
metadata (see §1.5) but **does not** filter events. Every valid active
event is included regardless of its `states` value.

### 1.7 Status Exclusion — Terminal Status Precedence

An event is excluded when **either** of these fields indicates a terminal status:

1. The top-level `status` field; OR
2. The `outagestatus` field inside `additionalProperties`

A terminal status is any value (case-insensitive, stripped) in:
```
{"resolved", "closed", "cancelled", "complete", "completed"}
```

If the top-level `status` is `"ACTIVE"` but `additionalProperties.outagestatus`
is `"Resolved"`, the event is excluded (and vice versa).

### 1.8 Deduplication
Deduplicate by `identifier`. When two events share the same `identifier`,
the event with the most recent `last_updated_time` wins. If both timestamps
are `None` (or equal), the first-encountered event wins (stable).

### 1.9 Output
A `list[OutageEvent]` — instances of a frozen dataclass with these fields:

```
identifier: str
start_time: datetime | None
last_updated_time: datetime | None
etr_time: datetime | None
title: str
status: str
cause: str
num_people: int
latitude: float
longitude: float
county: str
additional_properties: dict[str, Any]
```

No `distance_km` field exists on `OutageEvent` — this is a computed value
internal to the scoring module.

The output order is **not guaranteed** to be sorted.

---

## 2. Scoring Contract (`custom_components.xcel_outages.scoring`)

### 2.1 Public API
```
compute_risk_context(
    events: list[OutageEvent],
    home_lat: float,
    home_lon: float,
    *,
    search_radius: float = 25.0,
    local_radius: float = 10.0,
    material_threshold: int = 25,
    previous_total: int | None = None,
) -> RiskContext
```

### 2.2 Inputs

| Parameter | Default | Description |
|-----------|---------|-------------|
| `events` | — | Pre-filtered (active-only) `OutageEvent` instances |
| `home_lat` | — | Home latitude (decimal degrees) |
| `home_lon` | — | Home longitude (decimal degrees) |
| `search_radius` | 25.0 | Max distance in km for "nearby" classification |
| `local_radius` | 10.0 | Radius in km for "local" classification |
| `material_threshold` | 25 | Minimum `num_people` for "material" status |
| `previous_total` | `None` | Prior poll's `nearby_customer_total`; `None` on first run |

### 2.3 Definitions

| Term | Definition |
|------|------------|
| **Nearby event** | Event whose Haversine distance from home is `<= search_radius`. |
| **Material event** | Nearby event with `num_people >= material_threshold`. |
| **Effective local radius** | `min(local_radius, search_radius)`. |
| **Local event** | Material nearby event with distance `<= effective local radius`. |
| **Nearby customer total** | Sum of `num_people` across material nearby events. |
| **Local customer total** | Sum of `num_people` across material local events. |
| **5-km customer total** | Sum of `num_people` across material events with distance `<= 5.0 km`. |
| **Customer total increase** | `max(0, nearby_customer_total - previous_total)` when `previous_total` is not `None`; otherwise `0`. |

### 2.4 Score Computation

#### 2.4.1 Base Risk

All conditions are evaluated and the **maximum** score is returned. The
condition order in the list below is the tie-breaking priority (first match
wins for equal scores).

| Priority | Condition | Score |
|----------|-----------|------:|
| 1 | At least one material nearby event | **15** |
| 2 | Local customer total >= 50 | **30** |
| 3 | Nearby customer total >= 250 AND material event count >= 2 | **35** |
| 4 | Nearby customer total >= 1,000 AND material event count >= 3 | **50** |
| 5 | Local customer total >= 200 AND local material event count >= 2 | **60** |
| 6 | 5-km customer total >= 100 | **65** |
| 7 | Nearby customer total >= 2,000 AND material event count >= 5 | **70** |
| — | No material event | **0** |

**Negative gate tests** verify that meeting the customer total without the
corresponding event count does **not** trigger the higher score:

| Gate | Customer total | Event count | Expected score |
|------|---------------|-------------|---------------:|
| 250/one | >= 250 | 1 | 15 (material only) |
| 1,000/two | >= 1,000 | 2 | 35 (250+ with 2+) |
| 2,000/four | >= 2,000 | 4 | 50 (1,000+ with 3+) |
| Local 200/one | >= 200 (local) | 1 (local) | 65 (5-km 100+) or 15 |

#### 2.4.2 Growth Bonus

When `customer_total_increase >= 250`, add **+15** to the base risk, capped
at a maximum of **100**.

The `previous_total` is an in-memory value held by the coordinator. It resets
on: Home Assistant restart, config entry reload, or options flow save. It does
**not** persist across restarts.

### 2.5 Output (`RiskContext` dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `risk` | `int` | Final score 0–100 |
| `band` | `str` | Descriptive band (see below) |
| `reason` | `str` | Human-readable explanation |
| `nearby_event_count` | `int` | Count of all nearby events (any `num_people`) |
| `material_event_count` | `int` | Count of material nearby events |
| `nearby_customer_total` | `int` | Sum `num_people` of material nearby events |
| `local_customer_total` | `int` | Sum `num_people` of material local events |
| `customer_total_increase` | `int` | Increase since prior poll (`0` if no prior) |
| `nearest_km` | `float \| None` | Distance to nearest nearby event |
| `nearest_material_km` | `float \| None` | Distance to nearest material event |
| `largest_nearby_event_customers` | `int` | Max `num_people` among material nearby events |

No `event_summaries` or `EventSummary`-typed field is exposed in the MVP.

### 2.6 Risk Bands

| Score Range | Band |
|------------|------|
| 0 | `None` |
| 1–15 | `Low` |
| 16–35 | `Moderate` |
| 36–60 | `Elevated` |
| 61–70 | `High` |
| 71–100 | `Severe` |

### 2.7 Bands mapped to plan.md rules

| Plan.md rule | Base score | Band (≤ that score) |
|---|---|---|
| No material nearby outage | 0 | None |
| Material nearby outage | 15 | Low |
| At least 50 customers within local radius | 30 | Moderate |
| At least 250 customers across several material events | 35 | Moderate |
| At least 1,000 customers across 3+ material events | 50 | Elevated |
| At least 200 customers and 2+ events within local radius | 60 | Elevated |
| At least 100 customers within 5 km | 65 | High |
| At least 2,000 customers across 5+ material events | 70 | High |
| At least 250 new nearby customers since prior poll | +15 bonus (≤100) | Severe at 71+ |

---

## 3. Privacy Contract

The following **must never** appear in entity attributes, log messages,
diagnostics payloads, repair issue data, or exception messages:

- `home_lat`, `home_lon`, `home_latitude`, `home_longitude`
- The raw configured coordinates
- Any value trivially derivable to the configured home location

Home coordinates are stored only in the config entry data for optional
location overrides. The coordinator may load them into memory for the
Haversine calculation but must **not** pass them into the scoring output
or expose them through entities.

**Allowed**: Relative distances in kilometres (`nearest_km`,
`nearest_material_km`) and aggregate counts.

**No event summaries are exposed** in the MVP. The ``RiskContext`` output
must not contain an ``event_summaries`` field or any ``EventSummary``-typed
attribute. Event summaries are deferred to a later phase (see ``plan.md``
Phase 2).

---

## 4. Version History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-07-24 | Initial normative contract from architecture review and source implementation |
| 1.1 | 2026-07-24 | Removed EventSummary/event_summaries per privacy remediation |
| 1.2 | 2026-07-24 | Renamed `new_customers` → `customer_total_increase`; immutable states; structured parse outcomes; terminal status precedence (top-level + outagestatus); bool/nonfinite/fractional rejection; negative count gates; precise inclusive boundary coordinates; removed `distance_km` from OutageEvent |
