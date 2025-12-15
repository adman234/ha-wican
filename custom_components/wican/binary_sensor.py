"""Binary sensor platform for WiCAN integration."""

from __future__ import annotations
import logging

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import WiCANConfigEntry
from .entity import WiCANEntity
from .attributes import WiCANBinarySensorEntityDescription, BINARY_SENSOR_DESCRIPTIONS, get_sensor_attributes

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0

TRUE_STRINGS = {"enable", "true", "online"}

def is_true_status(value: str) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in TRUE_STRINGS
    return bool(value)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WiCANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""

    async_add_entities(
        WiCANBinarySensorEntity(config_entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )

class WiCANBinarySensorEntity(WiCANEntity, BinarySensorEntity, RestoreEntity):
    """A binary sensor entity."""

    __slots__ = ("_attr_is_on", "_attr_extra_state_attributes")

    entity_description: WiCANBinarySensorEntityDescription

    def __init__(self, config_entry, entity_description):
        super().__init__(config_entry, entity_description)
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"
        self._attr_is_on = None
        self._attr_extra_state_attributes = None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        key = self.entity_description.key
        status = self.coordinator.data.get("status", {})

        # If key not present, don't change state. Availability handled below.
        if key in status:
            self._attr_is_on = is_true_status(status[key])
            self._attr_extra_state_attributes = get_sensor_attributes(key, self.coordinator.data)

        # Availability: if we have a status dict, entity is available; if device stopped pushing,
        # HA will keep last state, but we still emit state writes on updates to ensure logbook records.
        # Write state to Home Assistant.
        self.async_write_ha_state()

    @callback
    def _async_handle_event(self, webhook_id: str, data) -> None:
        """Handle webhook event (backward compatibility)."""
        # Coordinator update will trigger _handle_coordinator_update()
        pass

    async def async_added_to_hass(self) -> None:
        """Restore entity state."""
        # Restore last known state so logbook has a baseline before first push
        last_state = await self.async_get_last_state()
        if last_state is not None and self._attr_is_on is None:
            self._attr_is_on = last_state.state == "on"
        await super().async_added_to_hass()