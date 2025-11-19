"""Sensor platform for Sleep as Android integration."""

from __future__ import annotations
import logging

from datetime import datetime
from enum import StrEnum
from functools import partial

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import WiCANConfigEntry
from .entity import WiCANEntity
from .const import DOMAIN
from .attributes import SENSOR_DESCRIPTIONS, get_sensor_attributes, WiCANSensorEntityDescription

LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


DYNAMIC_PID_SENSORS = {}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""

    async_add_entities(
        WiCANSensorEntity(config_entry, description)
        for description in SENSOR_DESCRIPTIONS
    )

    DYNAMIC_PID_SENSORS[config_entry.entry_id] = {}

    # Restore PID sensors from config entry
    pid_keys = config_entry.data.get("pid_keys", [])
    restored_entities = []
    for pid_key in pid_keys:
        # Try to get config for this PID key if available
        pid_config = config_entry.data.get("config", {})
        config = pid_config.get(pid_key, {})
        device_class = config.get("class")
        unit = config.get("unit")
        if unit == "none":
            unit = None
        entity_description = WiCANSensorEntityDescription(
            key=pid_key,
            name=pid_key,
            device_class=device_class,
            native_unit_of_measurement=unit,
        )
        entity = WiCANPidSensorEntity(config_entry, pid_key, entity_description)
        DYNAMIC_PID_SENSORS[config_entry.entry_id][pid_key] = entity
        restored_entities.append(entity)
    if restored_entities:
        async_add_entities(restored_entities)

    def handle_pid_update(webhook_id, data):
        pid_data = data.get("autopid_data", {})
        pid_config = data.get("config", {})
        new_entities = []
        for pid_key, value in pid_data.items():
            sensors = DYNAMIC_PID_SENSORS[config_entry.entry_id]
            if pid_key not in sensors:
                config = pid_config.get(pid_key, {})
                device_class = config.get("class")
                unit = config.get("unit")
                if unit == "none":
                    unit = None
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
            new_data = dict(config_entry.data)
            new_data["pid_keys"] = list(pid_keys)
            hass.async_add_job(
                partial(hass.config_entries.async_update_entry, config_entry, data=new_data)
            )
            hass.async_add_job(async_add_entities, new_entities)

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
        LOGGER.warning(data)

        LOGGER.warning(data.get('status').get('wifi_mode'))

        key = self.entity_description.key

        if webhook_id != self.webhook_id:
            return
        if data.get('status') is None:
            return
        if data['status'].get(key) is None:
            return

        self._attr_native_value = data['status'][key]
        self._attr_extra_state_attributes = get_sensor_attributes(key, data)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore entity state."""
        state = await self.async_get_last_sensor_data()
        if state:
            self._attr_native_value = state.native_value

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
                self.hass.async_add_job(self.async_write_ha_state)

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