# Plan: Xcel Outage Map Home Assistant Integration

## Goal

Build an unofficial, read-only Home Assistant custom integration distributed through HACS. It polls Xcel Energy's public outage-map cache, considers every valid active Xcel outage event using the configured location and search radius as the sole geographic inclusion criteria, and exposes normalized outage context for dashboards and automations.

The integration must not control the inverter, change utility settings, or claim to know whether the home itself is affected. It provides nearby-outage context only.

## Source and Constraints

Primary source endpoint:

```text
https://xcelenergy.datacapable.com/datacapable/v2/cache/p/xcelenergy/map/events
```

Observed event fields include:

```text
identifier, startTime, lastUpdatedTime, etrTime, title, status, cause,
numPeople, latitude, longitude, county, additionalProperties
```

`additionalProperties` contains fields such as `states`, `city`,
`outageimpact`, `outagestatus`, and `comments`.

Constraints:

- The endpoint is undocumented and may change without notice.
- The response covers all Xcel Energy service areas; events are included based on the configured location and search radius.
- Outage coordinates are map-area centroids, not affected-service-address locations.
- Poll conservatively; default to 10 minutes and never rely on this source for safety-critical control.
- Do not store or publish the exact home coordinates in entity attributes, logs, diagnostics, or issue reports.

## Product Decisions

### Location

Use Home Assistant's configured location by default:

```python
hass.config.latitude
hass.config.longitude
```

Do not look up `zone.home` to obtain coordinates.

The config flow should offer an optional location override for a second property or an intentionally approximate HA home location.

### Defaults

| Option | Default | Bounds |
|---|---:|---:|
| Search radius | 25 km | 1-100 km |
| Poll interval | 10 minutes | 5-60 minutes |
| Material outage threshold | 25 customers | 1-10,000 |
| Local radius | 10 km | 1-50 km |

### Risk Semantics

Expose an ordinal `nearby outage risk` score from 0 to 100. It is not an outage probability.

Use the existing Node-RED scoring rules as the initial reference implementation:

| Condition | Initial risk |
|---|---:|
| No material nearby outage | 0 |
| Material nearby outage | 15 |
| At least 50 customers within local radius | 30 |
| At least 250 customers across several material events | 35 |
| At least 1,000 customers across 3+ material events | 50 |
| At least 100 customers within 5 km | 65 |
| At least 2,000 customers across 5+ material events | 70 |
| At least 200 customers and 2+ material events within local radius | 60 |
| At least 250 new nearby customers since prior successful poll | +15, capped at 100 |

Keep the scoring logic isolated in one pure module with tests. It is expected to be tuned over time.

## Repository Layout

Create a dedicated HACS repository, not a subdirectory of the ESPHome configuration repository.

```text
ha-xcel-outages/
  custom_components/
    xcel_outages/
      __init__.py
      api.py
      config_flow.py
      const.py
      coordinator.py
      entity.py
      manifest.json
      models.py
      sensor.py
      binary_sensor.py
      strings.json
      translations/
        en.json
  tests/
    __init__.py
    conftest.py
    fixtures/
      events_empty.json
      events_small_nearby.json
      events_material_cluster.json
      events_malformed.json
    test_api.py
    test_config_flow.py
    test_coordinator.py
    test_scoring.py
  hacs.json
  README.md
  LICENSE
  pyproject.toml
  requirements_test.txt
```

Use domain `xcel_outages`. Confirm the domain is unused before publishing.

## Integration Architecture

### API Client

Implement an `XcelOutageApi` client using Home Assistant's shared `aiohttp` session.

Responsibilities:

- Fetch the endpoint with a descriptive User-Agent and JSON Accept header.
- Enforce a request timeout.
- Validate that the response is a list of event objects.
- Normalize `additionalProperties` into a dictionary.
- Normalize `states` whether it arrives as a string or list.
- Include every valid active event; the configured location and search radius are the sole geographic inclusion criteria.
- Exclude resolved/closed/cancelled events when the source supplies such a status.
- Never log raw full responses at normal log levels.

### DataUpdateCoordinator

Use one `DataUpdateCoordinator` per config entry.

Responsibilities:

- Read coordinates from HA config or the saved override.
- Fetch and normalize events every configured interval.
- Calculate distances with a Haversine helper.
- Retain the last successful data through transient HTTP failures according to coordinator behavior.
- Mark entities unavailable when no successful response can be obtained.
- Store the previous nearby-customer total in coordinator state to calculate new customers since the prior poll.
- Surface endpoint/schema failures through standard integration logging and a repair issue only after repeated failures.

### Pure Scoring Module

Keep geographic filtering and risk calculation deterministic and independent of Home Assistant objects.

Inputs:

```text
normalized events, home coordinates, radius options, previous customer total
```

Outputs:

```text
risk, band, reason, nearby event count, material event count,
nearby customer total, local customer total, customer total increase,
nearest distance, nearest material distance, largest event
```

**Event summaries are removed from the MVP output.**  They are deferred to
Phase 2.  See `docs/scoring-contract.md` §3 for the privacy rationale.

This module is the main unit-test target.

## Entity Contract

Create a device named `Xcel Outage Map` with one service/diagnostic device entry per config entry.

### Primary Sensor

```text
sensor.xcel_nearby_outage_risk
```

- State: 0-100 ordinal nearby-outage risk
- Icon: `mdi:transmission-tower`
- Entity category: diagnostic
- No `device_class` or `state_class`

Attributes:

```text
risk_band
reason
nearby_event_count
material_event_count
nearby_customer_total
local_customer_total
new_customers_since_last_poll
nearest_km
nearest_material_km
largest_nearby_event_customers
last_successful_update
source_url
```

Do not include home coordinates. **Event summaries are removed from Phase 1 / MVP** (see `docs/scoring-contract.md` §3). They are deferred to Phase 2, where concise normalised event summaries may be added as a bounded-count attribute.

### Supporting Sensors

```text
sensor.xcel_nearby_outage_customers
sensor.xcel_nearest_material_outage_distance
sensor.xcel_nearby_outage_count
```

- Customers: unit `customers`, diagnostic
- Distance: unit `km`, device class `distance`, diagnostic
- Count: unit `outages`, diagnostic

### Binary Sensor

```text
binary_sensor.xcel_material_outage_nearby
```

State is on when at least one material event exists inside the configured search radius. This is informational, not a claim that the home is affected.

## Config Flow and Options Flow

### Initial Setup

1. Verify Home Assistant has valid configured latitude and longitude.
2. Offer `Use Home Assistant location` enabled by default.
3. If disabled, require latitude and longitude override values.
4. Configure search radius and poll interval.
5. Perform a test fetch before creating the entry; present a clear failure if the endpoint is unavailable or its response shape is unsupported.

### Options

Support updates without reauthentication:

- Search radius
- Local radius
- Material customer threshold
- Poll interval
- Location source / override

Reload the config entry after options change.

## Error Handling and Privacy

- HTTP timeout, 429, 5xx, malformed JSON, and unexpected schema must not crash the integration.
- Avoid frequent retry loops; rely on the next scheduled coordinator refresh.
- Include a `source available` diagnostic attribute or sensor state timestamp so automations can detect stale data.
- Do not reveal exact home coordinates in logs, diagnostics, entity attributes, or exceptions.
- Document that map-event distance is approximate and no event proves the home is affected.

## HACS Packaging

Add `hacs.json`:

```json
{
  "name": "Xcel Outage Map",
  "domains": ["xcel_outages"],
  "homeassistant": ">=2026.7.0"
}
```

Add `manifest.json` with:

- Domain, name, version, documentation URL, issue tracker URL
- `config_flow: true`
- `iot_class: cloud_polling`
- No extra Python dependency unless it is unavoidable

README requirements:

- Explicitly describe the integration as unofficial.
- State the endpoint and polling behavior.
- Explain radius/centroid limitations.
- State that the risk score is ordinal, not an outage probability.
- Explain that it is not proof of an outage at the configured home.
- Include screenshots only after entity names and UI are stable.

## Test Plan

### Unit Tests

- Empty list returns zero risk and no material outage.
- One-customer event within 5 km returns zero risk.
- A 62-customer event within 10 km returns local watch-level risk.
- A 100-customer event within 5 km reaches the expected high-local risk.
- Regional scattered events require both customer and material-event thresholds.
- String and list forms of `states` are normalised as source metadata but do not filter events.
- Malformed coordinates/properties are ignored without failing the update.
- Resolved events are excluded.
- Customer-growth bonus applies only after a prior successful update.
- No entity attribute includes the configured home coordinates.

### Coordinator Tests

- Successful fetch creates expected normalized data.
- Timeout and malformed response are handled cleanly.
- Options changes trigger coordinator reconfiguration/reload.
- Last successful update is reflected after a failed refresh.

### Manual Validation

1. Install through a local custom-components checkout.
2. Configure it with HA home location and a 25 km radius.
3. Compare entity values with the live outage map for the same location and the existing Node-RED function.
4. Change radius and confirm the entities update as expected.
5. Confirm no raw coordinates appear in entity attributes, logs, or diagnostics.
6. Run it for at least several weeks before making it part of any battery-control automation.

## Delivery Phases

### Phase 1: Read-Only MVP

- API client, coordinator, config flow, primary risk sensor, binary sensor.
- Core scoring tests and fixture-based parsing tests.
- Local manual validation against the Node-RED implementation.

### Phase 2: Diagnostics and Options

- Supporting sensors, bounded event-summary attributes (if added), options flow.
- Source freshness reporting and robust unavailable behavior.

### Phase 3: HACS Release

- README, screenshots, versioning, CI, HACS validation.
- Publish repository and test installation through HACS.

### Phase 4: Automation Consumption

- Keep battery policy outside this integration.
- Feed its risk sensor into the existing Node-RED/HA storm-risk merger only after observed behavior is tuned and trusted.
