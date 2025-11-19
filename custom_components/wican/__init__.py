"""WiCAN integration."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp.web import Request, Response
import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN

import logging
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type WiCANConfigEntry = ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: WiCANConfigEntry
) -> bool:
    """Set up WiCAN from a config entry."""

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: Request
    ) -> Response:
        """Handle incoming WiCAN webhook request."""
        _LOGGER.info("Received WiCAN webhook: %s", webhook_id)
        try:
            data = await request.json()
        except vol.MultipleInvalid as error:
            return Response(
                text=error.error_message, status=HTTPStatus.UNPROCESSABLE_ENTITY
            )

        # Extract device info fields from top-level or nested "status"
        device_info_fields = {}
        status = data.get("status", {})
        for key in ("fw_version", "hw_version", "device_id", "git_version", "mdns"):
            # Check top-level first, then status
            if key in status:
                device_info_fields[key] = status[key]

        # Persist device info in config entry
        if device_info_fields:
            new_data = dict(entry.data)
            new_data.update(device_info_fields)
            hass.config_entries.async_update_entry(entry, data=new_data)

        async_dispatcher_send(hass, DOMAIN, webhook_id, data)
        return Response(status=HTTPStatus.NO_CONTENT)

    webhook.async_register(
        hass, DOMAIN, entry.title, entry.data[CONF_WEBHOOK_ID], handle_webhook
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WiCANConfigEntry
) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
