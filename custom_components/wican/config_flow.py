"""Config flow for the WiCAN integration."""

from __future__ import annotations

from homeassistant.helpers import config_entry_flow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import callback
from homeassistant import config_entries
import logging
import voluptuous as vol
from uuid import uuid4

from .const import (
    DOMAIN,
    CONF_POST_INTERVAL,
    DEFAULT_POST_INTERVAL,
    MIN_POST_INTERVAL,
    MAX_POST_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

config_entry_flow.register_webhook_flow(
    DOMAIN,
    "WiCAN",
    {"docs_url": "https://meatpihq.github.io/wican-fw/"},
    allow_multiple=True,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WiCAN discovery via Zeroconf."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle manual setup initiated by the user."""
        if user_input is not None:
            mdns = user_input.get("mdns")
            title = mdns or "WiCAN"
            webhook_id = uuid4().hex
            return self.async_create_entry(title=title, data={"mdns": mdns, CONF_WEBHOOK_ID: webhook_id} )

        data_schema = vol.Schema({vol.Required("mdns"): str})
        return self.async_show_form(step_id="user", data_schema=data_schema)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> FlowResult:
        """Handle zeroconf discovery."""
        name = discovery_info.name or ""
        properties = discovery_info.properties or {}
        host = discovery_info.host
        hostname = getattr(discovery_info, "hostname", "") or ""
        port = discovery_info.port

        if not host:
            return self.async_abort(reason="no_host")

        # Accept WiCAN based on provided mDNS: instance name or hostname
        is_wican_instance = name == "WiCAN-WebServer"
        is_wican_host = hostname.lower().startswith("wican_")
        if not (is_wican_instance or is_wican_host):
            _LOGGER.debug("Ignoring zeroconf service not matching WiCAN: name=%s hostname=%s", name, hostname)
            return self.async_abort(reason="not_wican")

        # Create a unique id based on host:port or service name
        base_id = hostname if hostname else name
        unique_id = f"{base_id}-{host}:{port}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Store mdns/host for setup to attempt webhook registration later
        mdns_url = f"http://{host}:{port}" if port else f"http://{host}"

        _LOGGER.info("WiCAN discovered via Zeroconf: name=%s hostname=%s url=%s", name, hostname, mdns_url)

        webhook_id = uuid4().hex
        return self.async_create_entry(
            title=hostname or name,
            data={
                "mdns": mdns_url,
                CONF_WEBHOOK_ID: webhook_id,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WiCANOptionsFlow(config_entry)


class WiCANOptionsFlow(config_entries.OptionsFlow):
    """Options flow to configure WiCAN settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._initial_options = dict(config_entry.options)

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        if self.hass is not None:
            options = dict(self.config_entry.options)
        else:
            options = self._initial_options
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_POST_INTERVAL,
                    default=options.get(CONF_POST_INTERVAL, DEFAULT_POST_INTERVAL),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_POST_INTERVAL, max=MAX_POST_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
