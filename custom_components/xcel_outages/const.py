"""Constants for the Xcel Outage Map integration."""

DOMAIN = "xcel_outages"

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
ENDPOINT_URL = (
    "https://xcelenergy.datacapable.com/datacapable/v2/cache/p/xcelenergy/map/events"
)
USER_AGENT = "XcelOutageMapHA/0.1.0"

# ---------------------------------------------------------------------------
# Default configuration option values and bounds
# ---------------------------------------------------------------------------
DEFAULT_SEARCH_RADIUS = 25  # km
MIN_SEARCH_RADIUS = 1
MAX_SEARCH_RADIUS = 100

DEFAULT_POLL_INTERVAL = 10  # minutes
MIN_POLL_INTERVAL = 5
MAX_POLL_INTERVAL = 60

DEFAULT_MATERIAL_THRESHOLD = 25  # customers
MIN_MATERIAL_THRESHOLD = 1
MAX_MATERIAL_THRESHOLD = 10_000

DEFAULT_LOCAL_RADIUS = 10  # km
MIN_LOCAL_RADIUS = 1
MAX_LOCAL_RADIUS = 50

# ---------------------------------------------------------------------------
# Status values considered resolved / closed / cancelled
# ---------------------------------------------------------------------------
EXCLUDED_STATUSES = frozenset(
    {"resolved", "closed", "cancelled", "complete", "completed"}
)

# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------
BASE_SCORE_MATERIAL = 15
BASE_SCORE_LOCAL_WATCH = 30
BASE_SCORE_REGIONAL_WATCH = 35
BASE_SCORE_REGIONAL_ELEVATED = 50
BASE_SCORE_LOCAL_ELEVATED = 60
BASE_SCORE_HIGH_LOCAL = 65
BASE_SCORE_REGIONAL_HIGH = 70

INCREASE_BONUS = 15
INCREASE_THRESHOLD = 250
MAX_RISK = 100

# ---------------------------------------------------------------------------
# Special distance thresholds
# ---------------------------------------------------------------------------
HIGH_LOCAL_DISTANCE_KM = 5.0

# ---------------------------------------------------------------------------
# Risk-band boundaries (inclusive upper bound)
# ---------------------------------------------------------------------------
RISK_BANDS: list[tuple[int, str]] = [
    (0, "None"),
    (15, "Low"),
    (35, "Moderate"),
    (60, "Elevated"),
    (70, "High"),
    (100, "Severe"),
]

# ---------------------------------------------------------------------------
# HTTP request
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# Config flow keys — stored in entry.data (immutable after setup)
# ---------------------------------------------------------------------------
CONF_USE_HOME_LOCATION = "use_home_location"
CONF_LATITUDE_OVERRIDE = "latitude_override"
CONF_LONGITUDE_OVERRIDE = "longitude_override"

# ---------------------------------------------------------------------------
# Config flow keys — stored in entry.options (mutable)
# ---------------------------------------------------------------------------
CONF_SEARCH_RADIUS = "search_radius"
CONF_LOCAL_RADIUS = "local_radius"
CONF_MATERIAL_THRESHOLD = "material_threshold"
CONF_POLL_INTERVAL = "poll_interval"

# ---------------------------------------------------------------------------
# Config flow error strings (referenced in strings.json)
# ---------------------------------------------------------------------------
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UNSUPPORTED_RESPONSE = "unsupported_response"
ERROR_INVALID_COORDINATES = "invalid_coordinates"
ERROR_MISSING_COORDINATES = "missing_coordinates"

# ---------------------------------------------------------------------------
# Entity naming
# ---------------------------------------------------------------------------
DEVICE_NAME = "Xcel Outage Map"

SENSOR_RISK = "xcel_nearby_outage_risk"
SENSOR_CUSTOMERS = "xcel_nearby_outage_customers"
SENSOR_DISTANCE = "xcel_nearest_material_outage_distance"
SENSOR_COUNT = "xcel_nearby_outage_count"
BINARY_SENSOR_MATERIAL = "xcel_material_outage_nearby"

SENSOR_FRESHNESS = "xcel_last_update_timestamp"
