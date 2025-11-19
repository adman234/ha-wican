"""Diagnostics platform for WiCAN integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import WiCANConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: WiCANConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    return {
        
    }
