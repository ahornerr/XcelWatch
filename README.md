# Xcel Outage Map

Unofficial Home Assistant integration that polls Xcel Energy's public outage-map cache and exposes nearby-outage context at the configured location.

**This integration is not affiliated with, endorsed by, or sponsored by Xcel Energy.**

---

## Installation

### Via HACS (recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. Add this repository as a custom repository in HACS:
   - **URL:** `https://github.com/ahornerr/XcelWatch`
   - **Category:** Integration
3. Click **Install** on the "Xcel Outage Map" integration.
4. Restart Home Assistant.

### Manual

1. Clone or download this repository.
2. Copy the `custom_components/xcel_outages/` directory into your Home Assistant `custom_components/` directory.
3. Restart Home Assistant.

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for "Xcel Outage Map" and select it.
 3. **Location step:**
    - Choose whether to use your Home Assistant home coordinates or enter custom override coordinates.
    - When **"Use Home Assistant home location"** is checked (default), the location step is complete and setup proceeds to parameters.
    - Uncheck **"Use Home Assistant home location"** to reveal the override latitude/longitude fields. These are required when the checkbox is unchecked.
4. **Parameters step:**
   - Set the **search radius** (1–100 km, default 25 km) — the maximum distance from your chosen location to search for outages.
   - Set the **poll interval** (5–60 minutes, default 10 minutes) — how often the endpoint is checked.
   - A test connection is performed before completing setup; if the endpoint is unreachable or returns an unexpected response, setup will fail with a clear message.

### Options

After setup, you can change settings at **Settings → Devices & Services → Xcel Outage Map → Configure**.

Mutable settings:

| Option | Default | Range | Description |
|---|---|---|---|
| Search radius | 25 km | 1–100 km | Max distance for outage search |
| Local radius | 10 km | 1–50 km | Secondary radius for local-density risk scoring |
| Material threshold | 25 customers | 1–10,000 | Minimum affected customers for a "material" outage |
| Poll interval | 10 min | 5–60 min | How often to poll the endpoint |
| Location source | Home | — | Switch between HA home coordinates and overrides |

Changes take effect immediately (the integration reloads automatically).

---

## Entities

A diagnostic device named **Xcel Outage Map** is created per config entry.

| Entity ID (example*) | Type | Description |
|---|---|---|
| `sensor.xcel_nearby_outage_risk` | Sensor | Ordinal nearby-outage risk score (0–100) |
| `sensor.xcel_nearby_outage_customers` | Sensor | Total customers affected in material nearby outages |
| `sensor.xcel_nearest_material_outage_distance` | Sensor | Distance (km) to the closest material outage |
| `sensor.xcel_nearby_outage_count` | Sensor | Count of all nearby outage events |
| `sensor.xcel_last_update_timestamp` | Sensor | Timestamp of the last successful coordinator refresh (remains available across transient failures) |
| `binary_sensor.xcel_material_outage_nearby` | Binary sensor | ON when at least one material outage is within range |

*\* Home Assistant generates entity IDs from the integration's translation keys and may append a numeric suffix (e.g. `sensor.xcel_nearby_outage_risk_2`) when conflicts exist. The exact entity ID visible in your system may differ.*

### Primary sensor attributes

`sensor.xcel_nearby_outage_risk` exposes these attributes:

| Attribute | Description |
|---|---|
| `risk_band` | Human-readable risk band (None/Low/Moderate/Elevated/High/Severe) |
| `reason` | Brief description of why the score is at its current level |
| `nearby_event_count` | Total events within the search radius |
| `material_event_count` | Events meeting the material customer threshold |
| `nearby_customer_total` | Sum of affected customers across all material nearby events |
| `local_customer_total` | Sum of affected customers within the local radius |
| `customer_total_increase` | New customers since the last successful poll |
| `nearest_km` | Distance to the closest event (any size) |
| `nearest_material_km` | Distance to the closest material event |
| `largest_nearby_event_customers` | Customer count of the largest nearby event |
| `last_successful_update` | ISO 8601 timestamp of the last successful data refresh |
| `source_url` | The upstream endpoint URL |

---

## How it works

### Source endpoint

The integration polls Xcel Energy's public outage-map cache:

```
https://xcelenergy.datacapable.com/datacapable/v2/cache/p/xcelenergy/map/events
```

This is the same endpoint that powers the official [Xcel Energy Outage Map](https://www.outagemap-xcelenergy.com/outagemap/).

### Polling behaviour

- The endpoint is polled at the configured interval (default 10 minutes).
- A fixed `User-Agent` header (`XcelOutageMapHA/0.1.0`) is sent with every request.
- On any failed refresh, data entities (risk, customers, distance, count, binary sensor) are marked **unavailable** (the coordinator reports `last_update_success = False`). The last successful data is retained in memory so attributes snap back once the next poll succeeds.
- The **freshness timestamp sensor** (`sensor.xcel_last_update_timestamp`) remains **available** across transient failures — it shows the last successful refresh time so automations can always detect stale data even when other entities are unavailable.

### Event inclusion

Every valid active Xcel Energy outage event returned by the endpoint is considered. The configured location and search radius are the sole geographic criteria for determining which events are nearby. The `states` field (which may arrive as a string or list) is normalised as source metadata but does not filter events.

### Risk scoring

The risk score is an **ordinal** value (0–100) based on:

- **Material outage proximity** — whether any event meeting the customer threshold exists within the search radius
- **Local event density** — customer counts and event counts within the local radius
- **High-local proximity** — customer counts within 5 km
- **Regional event spread** — customer counts and event counts across the full search radius
- **Customer growth** — increase in total nearby customers since the last successful poll

---

## Limitations

### Unofficial and unsupported

This integration uses an undocumented public endpoint that Xcel Energy could change or remove at any time without notice. There is no SLA or guarantee of availability.

### Centroid / radius approximation

Outage coordinates on the map are **centroids** of affected areas, not specific service-address locations. A distance calculation from your configured coordinates to an event centroid is an approximation. An event that appears to be near your chosen location may not actually affect your address, and vice versa.

### Ordinal risk, not probability

The risk score is an **ordinal indicator** based on heuristic rules. It is **not** an outage probability, statistical prediction, or machine-learning forecast. A score of 100 does not mean your home will definitely lose power. A score of 0 does not guarantee that no outage will occur.

### Not proof your home is affected

A "material outage nearby" state of ON means at least one event meeting the material threshold exists within the search radius. This **does not prove** that your home is without power or will lose power. Always verify against official Xcel Energy communications.

### No safety-critical control

This integration is designed for informational and automation-context purposes only. **Do not** use it as the sole input for safety-critical decisions, battery protection, life-safety equipment, or any other system where a failure could cause harm.

---

## Privacy

- The configured home coordinates are **never** exposed in entity attributes, logs, or diagnostics.
- Raw event data (titles, causes, identifiers, comments) is not included in entity attributes.
- The endpoint URL is included as a `source_url` attribute for transparency; no API keys or authentication tokens are used.
- No telemetry, analytics, or external data sharing is performed by this integration.

---

## Development

```bash
# Install development dependencies
pip install -r requirements_test.txt

# Run unit tests (parser, scoring — no Home Assistant dependency)
python -m pytest tests/ --ignore=tests/ha --ignore=tests/hass -v

# Run all tests (requires homeassistant and pytest-homeassistant-custom-component)
python -m pytest tests/ -v
```

See `docs/scoring-contract.md` for the detailed scoring contract.

---

## License

MIT — see [LICENSE](LICENSE).
