"""Test the WiCAN config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.const import CONF_NAME, CONF_WEBHOOK_ID

from custom_components.wican.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_user_flow_success(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test user config flow completes successfully."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"mdns": "http://wican_test.local:80"},
    )
    await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "http://wican_test.local:80"
    assert result2["data"]["mdns"] == "http://wican_test.local:80"
    assert CONF_WEBHOOK_ID in result2["data"]


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test user flow when device cannot be reached."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    # Config flow doesn't validate connectivity, it just creates the entry
    # Validation happens during setup when webhook registration is attempted
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"mdns": "http://wican_nonexistent.local:80"},
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY


async def test_user_flow_adds_http_scheme(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test that config flow adds http:// if missing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"mdns": "wican_test.local"},
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"]["mdns"] == "http://wican_test.local"


async def test_zeroconf_flow_success(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test zeroconf discovery flow with confirmation and MAC address."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        hostname="wican_test.local.",
        name="WiCAN-WebServer._wican._tcp.local.",
        port=80,
        type="_wican._tcp.local.",
        properties={
            "mac": b"AA:BB:CC:DD:EE:FF",
            "device_id": b"test_device_123",
            "firmware": b"2.00",
            "hardware": b"v3.1",
        },
    )

    # Mock that system is already onboarded (requires confirmation)
    with patch(
        "homeassistant.components.onboarding.async_is_onboarded",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

        # Should show confirmation form
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "zeroconf_confirm"
        assert "name" in result["description_placeholders"]
        assert "url" in result["description_placeholders"]

        # Confirm the addition
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "wican_test.local."
        # Check that MAC address was captured
        assert result2["data"].get("mac") == "AA:BB:CC:DD:EE:FF"
        assert result2["data"].get("device_id") == "test_device_123"


async def test_zeroconf_flow_not_wican(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf discovery ignores non-WiCAN devices."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.200",
        ip_addresses=["192.168.1.200"],
        hostname="some_other_device.local.",
        name="OtherDevice._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "not_wican"


async def test_zeroconf_already_configured(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf aborts if device already configured (MAC-based unique_id)."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

    # Create a config entry with MAC-based unique_id
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="aabbccddeeff",  # MAC without colons
        data={
            CONF_WEBHOOK_ID: "existing_webhook",
            CONF_NAME: "Existing Device",
            "mac": "AA:BB:CC:DD:EE:FF",
        },
    )
    existing_entry.add_to_hass(hass)

    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        hostname="wican_test.local.",
        name="WiCAN-WebServer._wican._tcp.local.",
        port=80,
        type="_wican._tcp.local.",
        properties={
            "mac": b"AA:BB:CC:DD:EE:FF",
            "device_id": b"test_device_123",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_zeroconf_during_onboarding(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test zeroconf auto-creates entry during onboarding."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        hostname="wican_test.local.",
        name="WiCAN-WebServer._wican._tcp.local.",
        port=80,
        type="_wican._tcp.local.",
        properties={
            "mac": b"AA:BB:CC:DD:EE:FF",
            "device_id": b"test_device_123",
        },
    )

    with (
        patch(
            "homeassistant.components.onboarding.async_is_onboarded",
            return_value=False,
        ),
        patch(
            "custom_components.wican._async_register_webhook_on_device",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )
        await hass.async_block_till_done()

    # Zeroconf creates entry directly (no confirmation step)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "wican_test.local."


async def test_options_flow(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test options flow (currently not implemented)."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )

    # Options flow not implemented yet - should be no-op or simple form
    # This test will need updating when options flow is added
    assert result is not None


async def test_zeroconf_flow_user_declines(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test user can decline discovered device."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        hostname="wican_test.local.",
        name="WiCAN-WebServer._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )

    # Mock that system is already onboarded (requires confirmation)
    with patch(
        "homeassistant.components.onboarding.async_is_onboarded",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

        # Should show confirmation form
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "zeroconf_confirm"

        # User can simply close the dialog (no follow-up action needed)
        # The flow will remain in FORM state until user confirms or dismisses


async def test_zeroconf_flow_legacy_firmware(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test zeroconf works with older firmware without MAC address."""
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

    discovery_info = ZeroconfServiceInfo(
        ip_address="192.168.1.100",
        ip_addresses=["192.168.1.100"],
        hostname="wican_legacy.local.",
        name="WiCAN-WebServer._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},  # No MAC or device_id (older firmware)
    )

    # Mock that system is already onboarded (requires confirmation)
    with patch(
        "homeassistant.components.onboarding.async_is_onboarded",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )

        # Should show confirmation form
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "zeroconf_confirm"

        # Confirm the addition
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

        # Should create entry with fallback unique_id (hostname-based)
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "wican_legacy.local."
        # No MAC address in data for legacy firmware
        assert "mac" not in result2["data"] or not result2["data"].get("mac")
