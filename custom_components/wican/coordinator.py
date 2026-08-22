"""DataUpdateCoordinator for WiCAN integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from yarl import URL

from .const import (
    DOMAIN,
    STATUS_ENDPOINT,
    STATUS_POLL_ALLOWED_KEYS,
    STATUS_POLL_TIMEOUT,
    WICAN_DATA_UPDATE_INTERVAL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import WiCANConfigEntry

_LOGGER = logging.getLogger(__name__)

# Vehicle data arrives by webhook push. Device status (12V battery voltage, HV
# battery temperature) is polled from /check_status instead, because the webhook
# task only posts while the device is in AutoPID mode.
UPDATE_INTERVAL = timedelta(seconds=WICAN_DATA_UPDATE_INTERVAL)


class WiCANDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching WiCAN data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: WiCANConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = config_entry
        self._data: dict[str, Any] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=config_entry,
        )

    def _status_urls(self) -> list[str]:
        """Build the ordered /check_status URLs to try for this device."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        cached_ip = getattr(runtime, "cached_resolved_ip", None)

        candidates: list[str | None] = [
            f"http://{cached_ip}" if cached_ip else None,
            getattr(runtime, "device_host", None),
            self.config_entry.data.get("host"),
            self.config_entry.data.get("mdns"),
        ]

        urls: list[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            raw = str(candidate).strip()
            if not raw.startswith(("http://", "https://")):
                raw = f"http://{raw}"
            try:
                base = URL(raw).with_query(None).with_fragment(None)
                url = str(base.with_path(STATUS_ENDPOINT))
            except ValueError:
                continue
            if url not in urls:
                urls.append(url)
        return urls

    def _status_belongs_to_device(self, payload: dict[str, Any]) -> bool:
        """Return True unless the payload clearly came from a different device."""
        stored = self.config_entry.data.get("device_id")
        incoming = payload.get("device_id")
        if not stored or not incoming:
            return True
        if incoming == stored:
            return True
        _LOGGER.warning(
            "Ignoring status from unexpected device (expected %s, got %s)",
            stored,
            incoming,
        )
        return False

    async def _async_fetch_status(self) -> dict[str, Any] | None:
        """Poll the device's /check_status endpoint, or None if unreachable."""
        session = async_get_clientsession(self.hass)

        for url in self._status_urls():
            try:
                async with asyncio.timeout(STATUS_POLL_TIMEOUT), session.get(url) as resp:
                    if resp.status >= 300:
                        _LOGGER.debug("Status poll %s returned HTTP %s", url, resp.status)
                        continue
                    payload = await resp.json(content_type=None)
            except (TimeoutError, aiohttp.ClientError) as err:
                _LOGGER.debug("Status poll failed for %s: %s", url, err)
                continue
            except ValueError as err:
                _LOGGER.debug("Status poll gave invalid JSON from %s: %s", url, err)
                continue

            if isinstance(payload, dict) and self._status_belongs_to_device(payload):
                _LOGGER.debug("Polled status from %s", url)
                return payload

        _LOGGER.debug("No WiCAN status endpoint responded")
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll device status and merge it into the webhook-pushed data.

        Vehicle parameters still arrive by webhook via handle_webhook_data().
        This poll only refreshes the device's own status block, which the
        webhook cannot deliver unless the device is in AutoPID mode.

        A device that is asleep or off the network is expected, so a failed poll
        keeps the last known values instead of raising UpdateFailed and marking
        every entity unavailable.
        """
        status = await self._async_fetch_status()
        if status:
            # Drop everything not on the allowlist; see STATUS_POLL_ALLOWED_KEYS.
            safe = {k: v for k, v in status.items() if k in STATUS_POLL_ALLOWED_KEYS}
            merged = dict(self._data.get("status") or {})
            merged.update(safe)
            self._data["status"] = merged

        return self._data

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh of the coordinator.

        Polls /check_status once so the device's own sensors have values right
        away. Vehicle parameters still wait for the first webhook push, and a
        device that is unreachable here is not treated as a setup failure.
        """
        _LOGGER.debug(
            "First refresh for WiCAN coordinator (push-based, no polling required)",
        )
        # Initialize with empty data - webhook pushes will populate it
        await self.async_refresh()

    def handle_webhook_data(self, data: dict[str, Any]) -> None:
        """Handle incoming webhook data.

        This is called by the webhook handler when new data arrives.
        It updates the coordinator's data and notifies all listeners.
        """
        # Validate device identity before processing data
        self._validate_device_identity(data)

        # Update internal data store
        self._data.update(data)

        # Notify all entities that data has been updated
        self.async_set_updated_data(self._data)

    def _validate_device_identity(self, data: dict[str, Any]) -> None:
        """Ensure device identity hasn't changed.

        Validates that the device_id in the webhook data matches the stored
        device_id from initial configuration. This prevents a different device
        from impersonating the configured device.

        Raises:
            ConfigEntryError: If device_id mismatch is detected.
        """
        # Extract device_id from webhook data (can be in status dict or top-level)
        status = data.get("status", {})
        incoming_device_id = status.get("device_id") or data.get("device_id")

        if not incoming_device_id:
            # No device_id provided - skip validation
            # This maintains backward compatibility with older firmware
            return

        # Get stored device_id from config entry
        stored_device_id = self.config_entry.data.get("device_id")

        if not stored_device_id:
            # First time seeing device_id - this is okay
            # The webhook handler will store it in the config entry
            _LOGGER.debug(
                "No stored device_id yet, accepting incoming device_id: %s",
                incoming_device_id,
            )
            return

        # Validate device_id matches
        if incoming_device_id != stored_device_id:
            _LOGGER.error(
                "Device ID mismatch detected! Expected %s, got %s",
                stored_device_id,
                incoming_device_id,
            )
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="device_mismatch",
                translation_placeholders={
                    "expected": stored_device_id,
                    "actual": incoming_device_id,
                },
            )

        _LOGGER.debug("Device identity validated: %s", incoming_device_id)

    def normalize_sensor_value(self, key: str, raw_value: Any) -> Any:
        """Normalize raw sensor values.

        Converts string values with unit suffixes to proper numeric types.
        This centralizes value normalization logic for consistency.

        Args:
            key: Sensor key (e.g., "batt_voltage")
            raw_value: Raw value from device

        Returns:
            Normalized value suitable for Home Assistant
        """
        if raw_value is None:
            return None

        # Battery voltage: strip "V" / " V" suffix (any case) and convert to float
        # Handles firmware variants: "12.5V", "12.5 V", "12.5v", " 12.5 V "
        if key == "batt_voltage" and isinstance(raw_value, str):
            _LOGGER.debug("Raw batt_voltage from device: %r", raw_value)
            stripped = raw_value.strip()
            if stripped.upper().endswith("V"):
                numeric_part = stripped[:-1].strip()
                try:
                    return float(numeric_part)
                except ValueError:
                    _LOGGER.warning(
                        "Failed to parse battery voltage: %r (numeric part: %r)",
                        raw_value, numeric_part,
                    )
                    return raw_value

        # Generic numeric string conversion
        if isinstance(raw_value, str):
            # Check if it looks like a number
            cleaned = raw_value.replace(".", "", 1).replace("-", "", 1)
            if cleaned.isdigit():
                try:
                    return float(raw_value) if "." in raw_value else int(raw_value)
                except ValueError:
                    pass

        return raw_value

    def get_sensor_value(self, sensor_key: str) -> Any | None:
        """Get value for a specific sensor."""
        return self._data.get(sensor_key)
