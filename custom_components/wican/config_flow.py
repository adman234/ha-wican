"""Config flow for the WiCAN integration."""

from __future__ import annotations

from homeassistant.helpers import config_entry_flow

from .const import DOMAIN

config_entry_flow.register_webhook_flow(
    DOMAIN,
    "WiCAN",
    {"docs_url": "https://meatpihq.github.io/wican-fw/"},
    allow_multiple=True,
)
