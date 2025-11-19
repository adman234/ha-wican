"""Base entity for WiCAN integration."""

from __future__ import annotations

from abc import abstractmethod

from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity, EntityDescription

from . import WiCANConfigEntry
from .const import DOMAIN


class WiCANEntity(Entity):
    """Base entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        config_entry: WiCANConfigEntry,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        self.config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"
        self.entity_description = entity_description
        self.webhook_id = config_entry.data[CONF_WEBHOOK_ID]
        self._attr_name = entity_description.key
        self._attr_device_info = DeviceInfo(
            connections={(DOMAIN, config_entry.entry_id)},
            manufacturer="MeatPi",
            model="WiCAN",
            name=config_entry.title,
        )

    @abstractmethod
    def _async_handle_event(self, webhook_id: str, data: dict[str, str]) -> None:
        """Handle the WiCAN event."""

    async def async_added_to_hass(self) -> None:
        """Register event callback."""

        self.async_on_remove(
            async_dispatcher_connect(self.hass, DOMAIN, self._async_handle_event)
        )

    @property
    def device_info(self) -> DeviceInfo:
        info = self.config_entry.data
        config_url = info.get("mdns")
        if config_url is not str(config_url).startswith("http"):
            config_url = None
        return DeviceInfo({
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "connections": {(DOMAIN, self.config_entry.entry_id)},
            "manufacturer": "MeatPi",
            "model": info.get("hw_version", "Unknown"),
            "name": "WiCAN Device",
            "sw_version": info.get("fw_version", "Unknown"),
            "serial_number": info.get("device_id", "Unknown"),
            "configuration_url": config_url,
            "suggested_area": "Garage",
        })