"""Sensor platform for Sleep as Android integration."""

from __future__ import annotations
import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import WiCANConfigEntry
from .entity import WiCANEntity
from .const import DOMAIN
from .attributes import SENSOR_DESCRIPTIONS, get_sensor_attributes, WiCANSensorEntityDescription

LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


def _normalize_device_class(device_class: str | SensorDeviceClass | None, unit: str | None) -> SensorDeviceClass | None:
    """Convert string device_class to enum and drop invalid combos (e.g. rpm + speed).

    TODO(meatpi): This is a temporary guard to avoid mismatched unit/device_class
    combinations leaking into HA. Replace with a canonical unit-to-device-class
    validation map and stricter config validation so we can surface clear errors
    and avoid silently dropping classes.
    """
    normalized = device_class
    if isinstance(device_class, str):
        try:
            normalized = SensorDeviceClass(device_class)
        except ValueError:
            normalized = None
    if (
        normalized == SensorDeviceClass.SPEED
        and unit is not None
        and unit.lower().endswith("rpm")
    ):
        return None
    return normalized


DYNAMIC_PID_SENSORS = {}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""

    async_add_entities(
        WiCANSensorEntity(config_entry, description)
        for description in SENSOR_DESCRIPTIONS
    )

    DYNAMIC_PID_SENSORS[config_entry.entry_id] = {}

    # Restore PID sensors from config entry
    pid_keys = config_entry.data.get("pid_keys", [])
    pid_config = config_entry.data.get("config", {})
    restored_entities = []
    for pid_key in pid_keys:
        config = pid_config.get(pid_key, {})
        unit = config.get("unit")
        if unit == "none":
            unit = None
        device_class = _normalize_device_class(config.get("class"), unit)
        entity_description = WiCANSensorEntityDescription(
            key=pid_key,
            name=pid_key,
            device_class=device_class,
            native_unit_of_measurement=unit,
            state_class="measurement",
        )
        entity = WiCANPidSensorEntity(config_entry, pid_key, entity_description)
        DYNAMIC_PID_SENSORS[config_entry.entry_id][pid_key] = entity
        restored_entities.append(entity)
    if restored_entities:
        async_add_entities(restored_entities)

    async def _async_process_pid_update(webhook_id, data):
        pid_data = data.get("autopid_data", {})
        if not pid_data:
            return

        pid_config = data.get("config", {})
        new_entities = []
        sensors = DYNAMIC_PID_SENSORS[config_entry.entry_id]

        for pid_key in pid_data:
            if pid_key not in sensors:
                config = pid_config.get(pid_key, {})
                unit = config.get("unit")
                if unit == "none":
                    unit = None
                device_class = _normalize_device_class(config.get("class"), unit)
                entity_description = WiCANSensorEntityDescription(
                    key=pid_key,
                    name=pid_key,
                    device_class=device_class,
                    native_unit_of_measurement=unit,
                )
                entity = WiCANPidSensorEntity(config_entry, pid_key, entity_description)
                new_entities.append(entity)
                sensors[pid_key] = entity

            sensors[pid_key]._async_handle_event(webhook_id, data)

        if new_entities:
            pid_keys = set(sensors.keys())
            existing_config = dict(config_entry.data.get("config", {}))
            for pid_key in pid_data:
                if pid_key in pid_config:
                    existing_config[pid_key] = pid_config[pid_key]
            new_data = dict(config_entry.data)
            new_data["pid_keys"] = list(pid_keys)
            new_data["config"] = existing_config
            hass.config_entries.async_update_entry(config_entry, data=new_data)
            async_add_entities(new_entities)

    def handle_pid_update(webhook_id, data):
        hass.loop.call_soon_threadsafe(
            hass.async_create_task,
            _async_process_pid_update(webhook_id, data),
        )

    # Connect the dispatcher signal to handle_pid_update
    async_dispatcher_connect(
        hass,
        DOMAIN,
        handle_pid_update
    )

class WiCANSensorEntity(WiCANEntity, RestoreSensor):
    """A sensor entity."""

    entity_description: WiCANSensorEntityDescription

    @callback
    def _async_handle_event(self, webhook_id: str, data) -> None:
        # Be defensive: data may not include a 'status' section
        try:
            LOGGER.debug("WiCAN event received for %s: %s", self.entity_description.key, data)
            wifi_mode = (data.get('status') or {}).get('wifi_mode')
            if wifi_mode is not None:
                LOGGER.debug("WiCAN wifi_mode: %s", wifi_mode)
        except Exception:  # logging should never break entity updates
            pass

        key = self.entity_description.key

        if webhook_id != self.webhook_id:
            return
        if data.get('status') is None:
            return
        if data['status'].get(key) is None:
            return

        value = data['status'][key]
        # Normalize numeric strings with unit suffix (e.g., "11.3V") for numeric device classes
        try:
            if self.entity_description.device_class == SensorDeviceClass.VOLTAGE and isinstance(value, str):
                if value.endswith("V"):
                    value = value[:-1]
            if isinstance(value, str):
                # Attempt to convert to float if numeric
                if value.replace(".", "", 1).isdigit():
                    value = float(value)
        except Exception:
            # Be defensive; if parsing fails, keep original value
            pass
        self._attr_native_value = value
        self._attr_extra_state_attributes = get_sensor_attributes(key, data)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore entity state."""
        state = await self.async_get_last_sensor_data()
        if state:
            value = state.native_value
            try:
                if self.entity_description.device_class == SensorDeviceClass.VOLTAGE and isinstance(value, str):
                    if value.endswith("V"):
                        value = value[:-1]
                if isinstance(value, str):
                    if value.replace(".", "", 1).isdigit():
                        value = float(value)
            except Exception:
                pass
            self._attr_native_value = value

        await super().async_added_to_hass()

class WiCANPidSensorEntity(WiCANEntity, RestoreSensor):
    """Dynamic PID sensor entity."""

    entity_description: WiCANSensorEntityDescription

    def __init__(self, config_entry, pid_key, entity_description):
        LOGGER.warning(f"Creating WiCANPidSensorEntity for PID: {pid_key}")
        super().__init__(config_entry, entity_description)
        self._pid_key = pid_key
        self._attr_unique_id = f"{config_entry.entry_id}_pid_{pid_key}"
        self._attr_entity_category = None  # Regular sensor
        self._pending_value = None

    @callback
    def _async_handle_event(self, webhook_id: str, data) -> None:
        pid_data = data.get("autopid_data", {})
        if self._pid_key in pid_data:
            if self.hass is None:
                self._pending_value = pid_data[self._pid_key]
            else:
                self._attr_native_value = pid_data[self._pid_key]
                self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore entity state and set pending value if present."""
        state = await self.async_get_last_sensor_data()
        if state:
            self._attr_native_value = state.native_value
        if self._pending_value is not None:
            self._attr_native_value = self._pending_value
            self.async_write_ha_state()
            self._pending_value = None
        await super().async_added_to_hass()