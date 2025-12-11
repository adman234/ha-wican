# GPS Location Tracking Feature

## Overview

WiCAN now supports GPS location tracking via the `device_tracker` platform. This allows you to track the physical location of your WiCAN device (typically mounted in a vehicle) on Home Assistant's map.

## Architecture

The implementation follows Home Assistant's best practices and is similar to how ESPHome and OwnTracks handle GPS tracking:

```
WiCAN Device → Webhook → Coordinator → device_tracker Entity → HA Map
  (GPS data)     (HTTP)     (validates)    (displays)
```

### Key Features

- ✅ **Standard device_tracker Platform**: Shows on HA map, works with zones
- ✅ **GPS Source Type**: Properly identifies as GPS-based tracking
- ✅ **Zone Matching**: Automatically matches to home/other zones
- ✅ **State Restoration**: Preserves last known location across restarts
- ✅ **Validation**: Validates GPS coordinates (lat: -90 to 90, lon: -180 to 180)
- ✅ **Optional Attributes**: Altitude, speed, heading included when available
- ✅ **Graceful Degradation**: Works without GPS, entity shows as unavailable

## Webhook Payload Format

### Minimal GPS Data (Required Fields Only)

```json
{
  "status": { 
    "device_id": "WiCAN-12345"
  },
  "gps": {
    "latitude": 37.7749,
    "longitude": -122.4194
  }
}
```

### Full GPS Data (All Fields)

```json
{
  "status": { 
    "device_id": "WiCAN-12345",
    "fw_version": "2.00"
  },
  "autopid_data": { ... },
  "gps": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "accuracy": 10,
    "altitude": 25.5,
    "speed": 15.3,
    "heading": 180
  }
}
```

### GPS Field Specifications

| Field | Type | Range | Required | Description |
|-------|------|-------|----------|-------------|
| `latitude` | float | -90 to 90 | ✅ Yes | Latitude in decimal degrees |
| `longitude` | float | -180 to 180 | ✅ Yes | Longitude in decimal degrees |
| `accuracy` | int | 0+ | ⭕ Optional | GPS fix accuracy in meters (default: 0) |
| `altitude` | float | any | ⭕ Optional | Altitude above sea level in meters |
| `speed` | float | 0+ | ⭕ Optional | Ground speed in meters per second |
| `heading` | float | 0-360 | ⭕ Optional | Heading/bearing in degrees |

## Home Assistant Entity

### Entity Details

- **Entity ID**: `device_tracker.wican_device_location`
- **Name**: "WiCAN Device Location"
- **Device Class**: GPS tracker
- **Icon**: `mdi:map-marker`
- **Unique ID**: `{entry_id}_device_tracker`

### Entity States

| State | Description |
|-------|-------------|
| `home` | Device is in the home zone |
| `{zone_name}` | Device is in a custom zone (e.g., "work", "school") |
| `not_home` | Device has GPS coordinates but not in any zone |
| `unavailable` | No GPS data received yet |

### Attributes

**Standard Attributes:**
- `latitude` (float): Current latitude
- `longitude` (float): Current longitude
- `gps_accuracy` (int): GPS accuracy in meters
- `source_type` (string): Always "gps"

**Extra Attributes** (when available):
- `altitude` (float): Altitude in meters
- `speed` (float): Speed in m/s
- `heading` (float): Direction in degrees

## Device Firmware Implementation

### GPS Data Sources

The WiCAN device can obtain GPS data from:

1. **External GPS Module** (recommended)
   - UART GPS modules (e.g., NEO-6M, NEO-M8N)
   - Parse NMEA sentences for coordinates
   - Best accuracy and reliability

2. **Cellular Modem GPS** (if equipped)
   - Use AT commands to query GPS
   - Example: `AT+CGPSINFO` for SIM7600

3. **OBD-II GPS PIDs** (if available)
   - Some vehicles broadcast GPS via CAN
   - Parse vehicle-specific CAN messages

### Example ESP-IDF Code

```c
#include "cJSON.h"

// GPS state (update from your GPS source)
typedef struct {
    double latitude;
    double longitude;
    int accuracy;
    double altitude;
    double speed;
    double heading;
    bool valid;
} gps_data_t;

gps_data_t gps_data = {0};

// Build webhook payload with GPS data
cJSON* build_webhook_payload(void) {
    cJSON* root = cJSON_CreateObject();
    
    // Add status
    cJSON* status = cJSON_CreateObject();
    cJSON_AddStringToObject(status, "device_id", "WiCAN-12345");
    cJSON_AddItemToObject(root, "status", status);
    
    // Add GPS data if valid
    if (gps_data.valid) {
        cJSON* gps = cJSON_CreateObject();
        cJSON_AddNumberToObject(gps, "latitude", gps_data.latitude);
        cJSON_AddNumberToObject(gps, "longitude", gps_data.longitude);
        
        if (gps_data.accuracy > 0) {
            cJSON_AddNumberToObject(gps, "accuracy", gps_data.accuracy);
        }
        if (gps_data.altitude != 0) {
            cJSON_AddNumberToObject(gps, "altitude", gps_data.altitude);
        }
        if (gps_data.speed > 0) {
            cJSON_AddNumberToObject(gps, "speed", gps_data.speed);
        }
        if (gps_data.heading >= 0) {
            cJSON_AddNumberToObject(gps, "heading", gps_data.heading);
        }
        
        cJSON_AddItemToObject(root, "gps", gps);
    }
    
    // Add other data (autopid, config, etc.)
    // ...
    
    return root;
}

// GPS update task (called when new GPS fix available)
void update_gps_from_nmea(const char* nmea_sentence) {
    // Parse NMEA sentence (GGA, RMC, etc.)
    // Update gps_data structure
    
    // Example for $GPGGA sentence:
    // $GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
    
    if (strstr(nmea_sentence, "$GPGGA") != NULL) {
        // Parse latitude, longitude, altitude, accuracy
        // Set gps_data.valid = true when fix is valid
    }
}
```

### UART GPS Module Connection

```
ESP32 Pin    GPS Module
---------    ----------
TX (GPIO17)  → RX
RX (GPIO16)  ← TX
GND          → GND
3.3V         → VCC
```

## Usage Examples

### Automation: Notify when vehicle arrives home

```yaml
automation:
  - alias: "Vehicle Arrived Home"
    trigger:
      - platform: zone
        entity_id: device_tracker.wican_device_location
        zone: zone.home
        event: enter
    action:
      - service: notify.mobile_app
        data:
          message: "Vehicle has arrived home"
```

### Automation: Alert if vehicle leaves zone

```yaml
automation:
  - alias: "Vehicle Left Work"
    trigger:
      - platform: zone
        entity_id: device_tracker.wican_device_location
        zone: zone.work
        event: leave
    action:
      - service: notify.mobile_app
        data:
          message: "Vehicle left work at {{ now().strftime('%H:%M') }}"
```

### Template: Distance from home

```yaml
sensor:
  - platform: template
    sensors:
      vehicle_distance_from_home:
        friendly_name: "Vehicle Distance from Home"
        unit_of_measurement: "km"
        value_template: >
          {% set tracker = states.device_tracker.wican_device_location %}
          {% if tracker.state != 'unavailable' %}
            {{ distance(tracker) | round(1) }}
          {% else %}
            unknown
          {% endif %}
```

### Lovelace Map Card

```yaml
type: map
entities:
  - entity: device_tracker.wican_device_location
default_zoom: 13
hours_to_show: 24
```

## Testing

### Manual Webhook Test

Send a test GPS update to Home Assistant:

```bash
curl -X POST "http://homeassistant.local:8123/api/webhook/YOUR_WEBHOOK_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "status": {
      "device_id": "WiCAN-12345"
    },
    "gps": {
      "latitude": 37.7749,
      "longitude": -122.4194,
      "accuracy": 10
    }
  }'
```

### Verify Entity State

```bash
# Check entity state
ha-cli state get device_tracker.wican_device_location

# Watch for updates
ha-cli state watch device_tracker.wican_device_location
```

## Troubleshooting

### Entity shows "unavailable"

**Cause**: No GPS data received from device
**Solutions**:
1. Verify GPS module is connected and powered
2. Check GPS has valid satellite fix (needs clear sky view)
3. Verify webhook is receiving data: Developer Tools → Events → `wican_event`
4. Check logs: Settings → System → Logs

### Invalid coordinates warning

**Symptom**: Log shows "Invalid GPS coordinates: lat=X, lon=Y (out of range)"
**Cause**: GPS data outside valid range
**Solutions**:
1. Check GPS module is parsing NMEA correctly
2. Verify coordinate conversion (degrees vs degrees+minutes)
3. Ensure latitude is -90 to 90, longitude is -180 to 180

### Entity not updating

**Cause**: Webhook not delivering GPS data
**Solutions**:
1. Verify `gps` key is in webhook payload (check with curl test)
2. Ensure latitude and longitude fields are present
3. Check coordinator logs for GPS data validation errors

### GPS accuracy concerns

**Best Practices**:
1. Use GPS modules with external antenna for vehicle installations
2. Mount antenna with clear view of sky (on roof/dashboard)
3. Allow 1-2 minutes for initial GPS fix after power-on
4. Filter low-accuracy fixes on device side (accuracy > 200m)

## Performance Considerations

### Update Frequency

- **Recommended**: Update every 10-30 seconds when moving
- **Stationary**: Reduce to 1-5 minutes when parked
- **Power Saving**: Only send updates when location changes significantly

### Data Usage

- **Typical GPS payload**: ~200 bytes per update
- **With full data**: ~300 bytes (including status, autopid, GPS)
- **Network impact**: Minimal (< 1KB/min at 30s interval)

## Privacy & Security

### Data Handling

- GPS data is processed locally in Home Assistant
- No external cloud services involved (local push only)
- Location data stays on your network

### Zone Privacy

- Use zones to abstract precise locations in automations
- Example: "at_home" instead of exact coordinates

### Webhook Security

- Webhook ID acts as authentication token
- Keep webhook URL secure (don't share publicly)
- Consider HTTPS for webhook communication

## Future Enhancements

### Potential Features

- ⭕ GPS accuracy filtering (ignore fixes > 200m accuracy)
- ⭕ Speed-based update intervals (faster updates when moving)
- ⭕ Geofence events (separate from zone matching)
- ⭕ Trip tracking and distance calculations
- ⭕ Parking location memory

### Advanced Options

- Config flow option to enable/disable GPS tracking
- GPS accuracy threshold configuration
- Update interval based on movement detection

## Technical Details

### Implementation

- **Platform**: `custom_components/wican/device_tracker.py`
- **Entity Type**: `TrackerEntity` (HA core)
- **Source Type**: `SourceType.GPS`
- **Restoration**: `RestoreEntity` mixin for state persistence
- **Updates**: Via `DataUpdateCoordinator` pattern

### Test Coverage

- ✅ 12 comprehensive tests in `tests/test_device_tracker.py`
- ✅ Tests cover: setup, updates, validation, restoration, zones
- ✅ Edge cases: invalid coords, missing data, partial data

### Code Quality

- ✅ Full type hints throughout
- ✅ Proper error handling and logging
- ✅ Translation keys for localization
- ✅ Follows HA coding standards
- ✅ Comprehensive docstrings

## References

### Home Assistant Documentation

- [Device Tracker](https://www.home-assistant.io/integrations/device_tracker/)
- [TrackerEntity](https://developers.home-assistant.io/docs/core/entity/device-tracker/)
- [Zones](https://www.home-assistant.io/integrations/zone/)

### Similar Integrations

- [OwnTracks](https://www.home-assistant.io/integrations/owntracks/) - Smartphone GPS tracking
- [GPSLogger](https://www.home-assistant.io/integrations/gpslogger/) - Android GPS logger
- [iCloud](https://www.home-assistant.io/integrations/icloud/) - Apple device tracking

### GPS Resources

- [NMEA Sentence Reference](https://www.gpsinformation.org/dale/nmea.htm)
- [ESP32 UART GPS Example](https://github.com/espressif/esp-idf/tree/master/examples/peripherals/uart)
- [Neo-6M GPS Module Guide](https://randomnerdtutorials.com/esp32-neo-6m-gps-module-arduino/)
