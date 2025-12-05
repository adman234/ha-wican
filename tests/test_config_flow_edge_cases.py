"""Test config_flow edge cases for complete coverage."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wican.const import DOMAIN


async def test_config_flow_zeroconf_discovery(hass: HomeAssistant) -> None:
    """Test config flow via zeroconf discovery."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo
    
    # Use proper WiCAN service name pattern
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        port=80,
        hostname="wican_abc123.local.",
        type="_http._tcp.local.",
        name="WiCAN-WebServer",
        properties={"mac": b"AA:BB:CC:DD:EE:FF", "device_id": b"wican_abc123"},
    )
    
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )
    
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"


async def test_config_flow_user_manual_entry_with_optional_host(
    hass: HomeAssistant,
) -> None:
    """Test manual config entry with optional host field."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    
    # Submit with both mdns and optional host
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "mdns": "wican_test.local",
            "host": "192.168.1.50",  # Optional host field (line 62)
        },
    )
    
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["mdns"] == "http://wican_test.local"
    assert result["data"]["host"] == "http://192.168.1.50"


async def test_config_flow_zeroconf_already_configured(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery of already configured device."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo
    from tests.conftest import MockConfigEntry
    
    # Create existing entry with matching MAC
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"mdns": "http://wican_existing.local", "webhook_id": "webhook_existing"},
        title="Existing WiCAN",
        unique_id="aabbccddeeff",  # Normalized MAC without colons
    )
    entry.add_to_hass(hass)
    
    # Try zeroconf discovery of same device (lines 102-103)
    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        port=80,
        hostname="wican_existing.local.",
        type="_http._tcp.local.",
        name="WiCAN-WebServer",
        properties={"mac": b"AA:BB:CC:DD:EE:FF"},  # Same MAC, will normalize to aabbccddeeff
    )
    
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )
    
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
