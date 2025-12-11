"""Constants for the WiCAN integration."""

DOMAIN = "wican"

# Configuration
CONF_POST_INTERVAL = "post_interval"
DEFAULT_POST_INTERVAL = 15  # seconds
MIN_POST_INTERVAL = 1
MAX_POST_INTERVAL = 3600

# Webhook Registration
WEBHOOK_REGISTRATION_TIMEOUT = 10  # seconds
WEBHOOK_RETRY_DELAY_BASE = 2  # seconds for exponential backoff
WEBHOOK_MAX_RETRIES = 3

# IP Caching
IP_CACHE_DURATION = 300  # 5 minutes in seconds

# mDNS Resolution
MDNS_RESOLUTION_TIMEOUT = 5  # seconds

# GPS / Location Tracking
GPS_ACCURACY_THRESHOLD = 200  # meters - filter out low accuracy GPS fixes
MIN_GPS_LATITUDE = -90.0
MAX_GPS_LATITUDE = 90.0
MIN_GPS_LONGITUDE = -180.0
MAX_GPS_LONGITUDE = 180.0
