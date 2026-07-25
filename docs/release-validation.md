# Release Validation — XcelWatch (Xcel Outage Map)

> **Integration:** `xcel_outages` &nbsp;·&nbsp; **Version:** `0.1.0`
> **Target:** Python 3.14 / Home Assistant 2026.7
> **Repository:** https://github.com/ahornerr/XcelWatch

---

## Verified (local evidence)

All checks below were run in an isolated environment matching the target HA/Python versions.

### Test suite — pure-core (74 passed)

| File | Tests | Status |
|---|---|---|
| `tests/test_parser.py` | Parser edge cases, malformed input, deduplication, status filtering, state parsing | ✅ Pass |
| `tests/test_scoring.py` | Risk scoring contract, fixture-based scenarios, privacy invariants | ✅ Pass |

Run: `pytest tests/ --ignore=tests/ha --ignore=tests/hass -v` — **74/74 passed**.

### Test suite — HA integration (150 passed)

| File | Tests | Coverage |
|---|---|---|
| `tests/ha/test_api.py` | HTTP client headers, timeout, error mapping, schema validation (17) | ✅ Pass |
| `tests/ha/test_config_flow.py` | User/override location, params, options flow, validation (27) | ✅ Pass |
| `tests/ha/test_coordinator.py` | Refresh cycle, failure recovery, location switching, schema errors (15) | ✅ Pass |
| `tests/ha/test_integration.py` | Setup/unload/reload, platform registration, entity lifecycle (19) | ✅ Pass |
| `tests/ha/test_sensor.py` | Risk/binary sensor values, attributes, availability, privacy (27) | ✅ Pass |
| `tests/ha/test_sensor_supporting.py` | Supporting sensors (customers, distance, count), device info, privacy (45) | ✅ Pass |

Run: `pytest tests/ha/ -v` (requires `homeassistant>=2026.7.0` and `pytest-homeassistant-custom-component`) — **150/150 passed**.

### Compilation / import validation

```text
python -c "import ast; ast.parse(open('custom_components/xcel_outages/__init__.py').read())"  →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/parser.py').read())"   →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/scoring.py').read())"  →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/models.py').read())"   →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/api.py').read())"      →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/coordinator.py').read())" → OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/config_flow.py').read())" → OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/sensor.py').read())"   →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/binary_sensor.py').read())" → OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/entity.py').read())"   →  OK
python -c "import ast; ast.parse(open('custom_components/xcel_outages/const.py').read())"    →  OK
```

All Python source files compile without syntax errors.

### JSON / manifest validation

```text
python -c "import json; json.load(open('custom_components/xcel_outages/manifest.json'))"  →  OK
python -c "import json; json.load(open('custom_components/xcel_outages/strings.json'))"   →  OK
python -c "import json; json.load(open('custom_components/xcel_outages/translations/en.json'))" → OK
python -c "import json; json.load(open('hacs.json'))" → OK
```

All JSON files are well-formed.

### CI workflow definitions

| Workflow | File | Trigger |
|---|---|---|
| **Tests** (pure + HA) | `.github/workflows/tests.yml` | Push/PR to `main`; matrix Python 3.14 |
| **HACS Validation** | `.github/workflows/hacs-validation.yml` | Push/PR to `main` + weekly schedule |
| **Hassfest** | `.github/workflows/hassfest.yml` | Push/PR to `main` + weekly schedule |

Workflows are present and correctly configured. Their **passing status** must be confirmed on the target branch before release (see external gates below).

### Config entry / manifest structure

- `manifest.json` declares `domain: xcel_outages`, `version: 0.1.0`, `config_flow: true`, `iot_class: cloud_polling`, codeowner `@ahornerr`.
- `hacs.json` declares `"name": "Xcel Outage Map"`, `"homeassistant": "2026.7.0"`, `"render_readme": true`.
- `strings.json` and `translations/en.json` present.
- No external Python dependencies (`requirements: []`).

---

## External / manual gates (not yet verified)

The following must be confirmed **outside** the local development environment. They are listed in recommended execution order.

### 1. CI — HACS Validation Action

- Action: Verify the **HACS Validation** workflow (`hacs/action@main`, category `integration`) passes on the target branch.
- Location: GitHub Actions UI → HACS Validation run for the latest commit on `main`.

### 2. CI — Hassfest Action

- Action: Verify the **Hassfest** workflow (`home-assistant/actions/hassfest@master`) passes on the target branch.
- Location: GitHub Actions UI → Hassfest run for the latest commit on `main`.

### 3. CI — Test suite run

- Action: Verify the **Tests** workflow completes with **224/224 passed** (74 pure + 150 HA) on the target branch.
- Location: GitHub Actions UI → Tests run for the latest commit on `main`.

### 4. Tagged release

- Action: Create a **signed or annotated Git tag** matching the version in `manifest.json`:
  ```bash
  git tag -a v0.1.0 -m "v0.1.0 — initial release"
  git push origin v0.1.0
  ```
- Verify:
  - The tag appears on GitHub under **Releases** (or create a Release from the tag).
  - The release notes summarise the integration purpose, entities, and any known limitations.
  - The tag commit matches the commit that passed all CI gates.

### 5. Custom repository installation (HACS)

- Action: After the release tag is published, add the repository as a **custom HACS repository** in a test Home Assistant instance:
  - **URL:** `https://github.com/ahornerr/XcelWatch`
  - **Category:** Integration
- Verify:
  - The integration appears as "Xcel Outage Map" in HACS.
  - HACS resolves the version from the published Git tag and does not report validation errors.
  - Download and install succeeds.
  - Home Assistant restart does not produce integration-related errors.

### 6. Live endpoint / Node-RED comparison

- Action: Configure the integration with home or override coordinates in a location served by Xcel Energy.
- Verify:
  - The integration polls successfully (entities populate within 1–2 poll cycles).
  - Sensor values are reasonable for the configured location when compared against the official Xcel Energy outage map (https://www.xcelenergy.com/outages_and_emergencies/outage_map) or a simultaneous Node-RED flow using the same endpoint.

### 7. HA entity / flow UI smoke test

- Action: Navigate **Settings → Devices & Services → Xcel Outage Map** in Home Assistant.
- Verify:
  - Device appears with all 6 entities (five sensors plus one binary sensor).
  - Config flow re-run (`Configure`) opens and accepts modified options (radius, threshold, interval, location source).
  - Entities update in real time when the poll interval elapses or on manual `homeassistant.update_entity` call.
  - The integration can be **reloaded** via Settings → Devices & Services without error.
  - The integration can be **deleted** and re-added cleanly.

### 8. Privacy inspection

- **Entity state / attributes:**
  - Verify **no** home coordinates appear in any entity state or attribute.
  - Verify **no** raw event data (titles, causes, identifiers, comments, `additionalProperties`) appears in any entity attribute.
  - Verify the binary sensor exposes no extra attributes beyond the privacy contract.
  - Verify supporting sensors (customers, distance, count) expose no extra attributes.
- **HA logs:**
  - Verify no coordinate or event detail leakage at `info` or `debug` log levels.
  - Verify no PII in error/warning messages (paths, identifiers, coordinates).
- **Diagnostics download:** N/A — this integration does **not** implement a custom `async_get_config_entry_diagnostics` endpoint. Default HA framework diagnostics may include config entry data (including override coordinates when in use) and should not be relied upon for privacy assurance with override locations.

### 9. (Optional) Default HACS catalog submission

- If the integration is intended to appear in the default HACS integration catalog without requiring custom-repository installation:
  - Submit a pull request adding the repository to the [HACS default repository list](https://github.com/hacs/default) following [HACS integration submission guidelines](https://hacs.xyz/docs/publish/start/).
  - HACS maintainers will review manifest compliance, code quality, and documentation.
  - This step is **not required** for use via custom repository.

### 10. (Optional) HA brand/icons

- If custom icons or branding are desired in the Home Assistant frontend:
  - Submit the integration domain to the [home-assistant/brands](https://github.com/home-assistant/brands) repository following their contribution guidelines.
  - This step is **not** a prerequisite for functionality or HACS availability.

---

## Version compatibility matrix

| Component | Minimum | Tested |
|---|---|---|
| Python | 3.14 | 3.14 |
| Home Assistant | 2026.7.0 | 2026.7.0 |
| pytest | 8.0 | ✓ |
| pytest-asyncio | 0.21 | ✓ |
| pytest-homeassistant-custom-component | 0.13.0 | ✓ |
| aiohttp | 3.9.0 | ✓ |

---

## Artefacts

| File | Purpose |
|---|---|
| `custom_components/xcel_outages/manifest.json` | HA integration manifest |
| `hacs.json` | HACS metadata |
| `custom_components/xcel_outages/strings.json` | UI strings (en) |
| `custom_components/xcel_outages/translations/en.json` | Full English translation |
| `.github/workflows/tests.yml` | CI test workflow |
| `.github/workflows/hacs-validation.yml` | HACS validation workflow |
| `.github/workflows/hassfest.yml` | Hassfest validation workflow |
| `README.md` | User-facing documentation |
| `docs/scoring-contract.md` | Risk scoring contract |

---

*Last updated: 2026-07-24*
