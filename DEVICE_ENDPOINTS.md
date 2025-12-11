# WiCAN Device Endpoint Implementation Guide

- Overview: Implement simple REST endpoints on the WiCAN device so Home Assistant (HA) can auto-register a webhook and receive status updates.

## Endpoints

- POST `/api/webhook`
  - Purpose: Set or update HA webhook target and enable posting.
  - Request: `Content-Type: application/json`
    - Body:
      ```json
      { "url": "http://<ha_host>:8123/api/webhook/<id>", "enabled": true, "interval": 15 }
      ```
    - `interval` is the desired posting cadence in seconds (1–3600) provided from the HA options dialog.
  - Responses:
    - `201 Created` on first set:
      ```json
      { "url": "http://<ha_host>:8123/api/webhook/<id>", "enabled": true }
      ```
    - `200 OK` on update
    - `400 Bad Request` if invalid URL (non-http/https)

- GET `/api/webhook`
  - Purpose: Inspect current webhook configuration.
  - Response:
    ```json
    { "url": "http://<ha_host>:8123/api/webhook/<id>", "enabled": true, "last_post": "2025-12-03T21:34:00Z", "status": "ok", "retries": 0 }
    ```

- DELETE `/api/webhook`
  - Purpose: Disable and clear webhook target.
  - Response: `204 No Content`


- GET `/api/pids` (optional)
  - Purpose: Provide AutoPID summary for HA dynamic sensors.
  - Response:
    ```json
    {
      "config": { "RPM": { "class": "speed", "unit": "rpm" } },
      "keys": ["RPM"]
    }
    ```

## Behavior

- Idempotent: Multiple `POST /api/webhook` with same URL returns `200 OK`.
- Persist: Save `webhook_url` and `webhook_enabled` to NVS; survive reboots.
- Validate: Reject invalid URLs; do not block device operation.
- Posting: When enabled, POST to HA webhook periodically and on updates:
  - Request:
    ```json
    {
      "status": { /* same keys as GET /api/status */ },
      "autopid_data": { /* PID values */ },
      "config": { /* PID config */ },
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
  - GPS fields (all optional):
    - `latitude` (float, -90 to 90): Latitude in decimal degrees
    - `longitude` (float, -180 to 180): Longitude in decimal degrees
    - `accuracy` (int): GPS fix accuracy in meters
    - `altitude` (float): Altitude above sea level in meters
    - `speed` (float): Ground speed in meters per second
    - `heading` (float): Heading/bearing in degrees (0-360)
  - Update metrics: `last_post`, `status` ("ok" or error), `retries`.

## Security (optional)

- Shared secret: Support `Authorization: Bearer <token>` when posting to HA, or include `?token=...` in URL.
- HTTPS: Prefer HTTPS if feasible.

## ESP-IDF Implementation Sketch

- Include:
  - `#include "esp_http_server.h"`
  - `#include "cJSON.h"`
  - `#include "nvs.h"`
  - `#include "esp_http_client.h"`
- NVS keys:
  - `webhook_url` (string), `webhook_enabled` (bool)
- Handlers:
  - `POST /api/webhook`:
    1. Read body → parse JSON with `cJSON`.
    2. Validate `url` starts with `http://` or `https://`.
    3. Save `webhook_url`, `webhook_enabled` in NVS.
    4. Return `201` if previously empty; else `200`.
  - `GET /api/webhook`:
    1. Load config + runtime metrics.
    2. Build JSON with `cJSON` and return `200`.
  - `DELETE /api/webhook`:
    1. Clear NVS keys or set `enabled=false`.
    2. Return `204`.
  - `GET /api/status`:
    1. Build JSON from existing device info and runtime status.
    2. Return `200`.
- Posting task:
  - FreeRTOS task or timer that checks `webhook_enabled`, builds payload JSON, uses `esp_http_client` to POST to HA.
  - Short timeouts, exponential backoff, update `last_post`, `status`, `retries`.

## mDNS

- Service: `_http._tcp.local`
- Instance: `WiCAN-WebServer`
- Hostname: `wican_<id>.local`
- TXT: `firmware=<fw>`, `hardware=<hw>`, `path=/`

## Quick Test

- Configure webhook:
  ```bash
  curl -i -X POST http://wican_<id>.local/api/webhook \
    -H 'Content-Type: application/json' \
    -d '{ "url": "http://<ha_host>:8123/api/webhook/<id>", "enabled": true }'
  ```
- Inspect:
  ```bash
  curl -s http://wican_<id>.local/api/webhook
  curl -s http://wican_<id>.local/api/status
  ```

## Notes

- HA already attempts `POST /api/webhook`; once implemented, it should succeed.
- HA expects numeric values for voltage; device can send numeric (e.g., `11.3`) with unit `V` separately, or continue sending `"11.3V"` which HA normalizes on receipt.
