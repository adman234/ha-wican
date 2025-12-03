"""WiCAN integration."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp.web import Request, Response
import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import get_url
from aiohttp import ClientSession
from yarl import URL

from .const import (
    DOMAIN,
    CONF_POST_INTERVAL,
    DEFAULT_POST_INTERVAL,
)

import logging
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

WiCANConfigEntry = ConfigEntry


def _ensure_http_scheme(value: str | None) -> str | None:
    """Return value with http:// if no scheme is provided."""
    if not value:
        return value
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}"


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

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "post_interval": entry.options.get(CONF_POST_INTERVAL, DEFAULT_POST_INTERVAL)
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _schedule_webhook_registration(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WiCANConfigEntry
) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _schedule_webhook_registration(hass: HomeAssistant, entry: WiCANConfigEntry) -> None:
    async def _register(_: object | None = None) -> None:
        await _async_register_webhook_on_device(hass, entry)

    if hass.is_running:
        hass.async_create_task(_register())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register)


async def _async_register_webhook_on_device(hass: HomeAssistant, entry: WiCANConfigEntry) -> None:
    """Push webhook URL and interval to the WiCAN device."""
    mdns = entry.data.get("mdns")
    if not mdns:
        _LOGGER.debug("Entry %s missing mdns; cannot register webhook", entry.entry_id)
        return

    normalized_mdns = _ensure_http_scheme(mdns)
    if normalized_mdns != mdns:
        updated_data = dict(entry.data)
        updated_data["mdns"] = normalized_mdns
        hass.config_entries.async_update_entry(entry, data=updated_data)
        mdns = normalized_mdns

    try:
        base_url: str = get_url(hass)
        webhook_path = webhook.async_generate_url(hass, entry.data[CONF_WEBHOOK_ID])
        if webhook_path.startswith("http"):
            webhook_url = webhook_path
        else:
            webhook_url = str(URL(base_url) / webhook_path.lstrip("/"))
    except Exception as err:
        _LOGGER.warning("Cannot generate webhook URL for %s: %s", entry.entry_id, err)
        return

    post_interval = entry.options.get(CONF_POST_INTERVAL, DEFAULT_POST_INTERVAL)
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is not None:
        entry_data["post_interval"] = post_interval

    _LOGGER.info(
        "Registering WiCAN webhook %s with interval %ss", webhook_url, post_interval
    )

    endpoint_host = await hass.async_add_executor_job(_resolve_mdns_host, mdns)
    if not endpoint_host:
        _LOGGER.warning("Unable to resolve WiCAN host %s", mdns)
        return

    async with ClientSession() as session:
        endpoint = URL(endpoint_host) / "api" / "webhook"
        payload = {"url": webhook_url, "enabled": True, "interval": post_interval}
        try:
            resp = await session.post(str(endpoint), json=payload)
            if resp.status < 300:
                _LOGGER.info("WiCAN webhook registered successfully at %s", endpoint)
            else:
                text = await resp.text()
                _LOGGER.warning(
                    "WiCAN webhook registration failed (%s): %s", resp.status, text
                )
        except Exception as err:
            _LOGGER.warning("Error registering webhook on WiCAN device: %s", err)


def _resolve_mdns_host(host: str) -> str | None:
    """Resolve hostname to IP (fallback to original value)."""
    from urllib.parse import urlparse
    import socket

    parsed = urlparse(host)
    if parsed.scheme:
        hostname = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme
    else:
        hostname = host
        port = None
        scheme = "http"

    if not hostname:
        return host

    try:
        resolved = socket.gethostbyname(hostname)
    except socket.gaierror:
        return host

    netloc = f"{resolved}:{port}" if port else resolved
    return f"{scheme}://{netloc}"


async def _async_entry_updated(hass: HomeAssistant, entry: WiCANConfigEntry) -> None:
    """Handle config entry updates (options) by re-registering the webhook."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data is None:
        return

    entry_data["post_interval"] = entry.options.get(
        CONF_POST_INTERVAL, DEFAULT_POST_INTERVAL
    )
    await _async_register_webhook_on_device(hass, entry)
