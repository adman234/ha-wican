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
from homeassistant.helpers.network import get_url
from aiohttp import ClientSession
from yarl import URL

from .const import DOMAIN

import logging
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

WiCANConfigEntry = ConfigEntry


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

    # Ensure webhook_id exists (older entries may lack it); generate if missing
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        try:
            from uuid import uuid4
            webhook_id = uuid4().hex
            new_data = dict(entry.data)
            new_data[CONF_WEBHOOK_ID] = webhook_id
            hass.config_entries.async_update_entry(entry, data=new_data)
            _LOGGER.info("Generated missing webhook_id for entry %s", entry.title)
        except Exception:
            _LOGGER.warning("Failed to generate webhook_id; setup may fail")

    webhook.async_register(
        hass, DOMAIN, entry.title, webhook_id, handle_webhook
    )

    # Attempt to push webhook URL to device if mdns/host is known
    try:
        mdns = entry.data.get("mdns")
        if mdns:
            # Construct HA webhook URL
            base_url: str = get_url(hass)
            webhook_path = webhook.async_generate_url(hass, entry.data[CONF_WEBHOOK_ID])
            # async_generate_url returns full URL in recent HA; fall back if needed
            if webhook_path.startswith("http"):
                webhook_url = webhook_path
            else:
                webhook_url = str(URL(base_url) / webhook_path.lstrip("/"))

            _LOGGER.info("Attempting to register webhook URL on WiCAN device: %s -> %s", mdns, webhook_url)
            async with ClientSession() as session:
                # Placeholder endpoint; to be confirmed with device API
                endpoint = URL(mdns) / "api" / "webhook"
                try:
                    resp = await session.post(str(endpoint), json={"url": webhook_url})
                    if resp.status < 300:
                        _LOGGER.info("WiCAN webhook registered successfully at %s", endpoint)
                    else:
                        text = await resp.text()
                        _LOGGER.warning("WiCAN webhook registration failed (%s): %s", resp.status, text)
                except Exception as e:
                    _LOGGER.warning("Error registering webhook on WiCAN device: %s", e)
    except Exception:
        # Never break setup on webhook push attempts
        pass

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WiCANConfigEntry
) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
