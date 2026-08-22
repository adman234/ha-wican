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
PRO_DUAL_WEBHOOK_MIN_FW_VERSION = (4, 49)

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

# GitHub API
GITHUB_API_RELEASES_URL = "https://api.github.com/repos/{owner}/{repo}/releases"
GITHUB_OWNER = "meatpiHQ"
GITHUB_REPO = "wican-fw"

# Firmware Update
FIRMWARE_DOWNLOAD_TIMEOUT = 120  # 2 minutes to download from GitHub
FIRMWARE_UPLOAD_TIMEOUT = 180  # 3 minutes to upload to device
GITHUB_API_TIMEOUT = 30  # seconds for GitHub API requests
FIRMWARE_UPDATE_REBOOT_DELAY = 2  # seconds to wait before refreshing after update
OTA_ENDPOINT = "/upload/ota.bin"
OTA_FORM_FIELD = "ota_file"

# Update Coordinator
GITHUB_RELEASES_UPDATE_INTERVAL = 3600  # 1 hour

# WiCAN Data Coordinator (push-based fallback polling)
WICAN_DATA_UPDATE_INTERVAL = 60  # seconds between /check_status polls

# Device status endpoint polled for values the webhook only carries in
# AutoPID mode (12V battery voltage, HV battery temperature).
STATUS_ENDPOINT = "/check_status"
STATUS_POLL_TIMEOUT = 10  # seconds

# /check_status is unauthenticated and returns config_server_get_status_json(false),
# which includes the WiFi PSK and MQTT credentials in plaintext. The webhook path
# strips those; this one does not. Only keys the integration actually consumes are
# copied into coordinator data, so secrets never reach the state machine,
# entity attributes or a diagnostics download.
STATUS_POLL_ALLOWED_KEYS = frozenset(
    {
        # identity / firmware
        "device_id", "fw_version", "hw_version", "git_version", "mdns", "protocol",
        # connectivity
        "wifi_mode", "ap_ch", "ap_auto_disable", "sta_status", "sta_connected", "sta_ip",
        "vpn_status", "vpn_ip",
        # sensors
        "batt_voltage", "battery_temp_valid", "battery_temp_min_c",
        "battery_temp_max_c", "battery_temp_age_ms", "uptime", "uptime_sec",
        "ecu_status", "obd_chip_status", "ble_status", "ble_power",
        # CAN / device config
        "can_datarate", "can_mode", "can_bus_count",
        "can1_datarate", "can1_mode", "can1_en", "can_fwd_mode",
        "sleep_status", "sleep_volt", "sleep_time", "wakeup_volt", "wakeup_time",
        "webhook_en", "mqtt_en", "autopid_enabled", "timestamp",
        # battery alert config (non-secret fields only)
        "batt_alert", "batt_alert_volt", "batt_alert_protocol",
        "batt_alert_topic", "batt_alert_time",
    }
)
