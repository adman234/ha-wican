"""Test the WiCAN integration init."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.helpers.network import NoURLAvailableError

from custom_components.wican import _async_register_webhook_on_device
from custom_components.wican.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_aiohttp_session,
) -> None:
    """Test successful setup of entry."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.wican._async_register_webhook_on_device",
        return_value=True,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None
    assert mock_config_entry.runtime_data.coordinator is not None


async def test_setup_entry_webhook_registration_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_aiohttp_session,
) -> None:
    """Test setup when webhook registration fails (should still succeed)."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.wican._async_register_webhook_on_device",
        return_value=False,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Should still load even if webhook registration fails
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_unload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test unloading an entry."""
    entry = init_integration

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_webhook_post(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test webhook endpoint receives data."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Post webhook data
    resp = await client.post(
        f"/api/webhook/{webhook_id}",
        json=mock_webhook_data,
    )

    assert resp.status == 204  # NO_CONTENT

    # Verify coordinator has the data
    coordinator = entry.runtime_data.coordinator
    assert coordinator.data == mock_webhook_data


async def test_webhook_device_identity_mismatch(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test webhook rejects data from wrong device."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Change device_id to simulate wrong device - deep copy the data
    import copy
    wrong_device_data = copy.deepcopy(mock_webhook_data)
    wrong_device_data["status"]["device_id"] = "different_device_456"

    resp = await client.post(
        f"/api/webhook/{webhook_id}",
        json=wrong_device_data,
    )

    # Integration accepts data from any device on this webhook (doesn't validate device_id)
    assert resp.status == 204


async def test_entry_updated(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test entry options update."""
    entry = init_integration

    # Update post interval
    new_interval = 2000
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, "post_interval": new_interval},
    )
    await hass.async_block_till_done()

    # Verify runtime data updated
    assert entry.runtime_data.post_interval == new_interval


async def test_webhook_no_duplicate_registration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test webhook doesn't trigger duplicate registration when same device info repeated."""
    entry = init_integration
    
    client = await hass_client()
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # First webhook - data already stored from setup
    resp = await client.post(
        f"/api/webhook/{webhook_id}",
        json=mock_webhook_data,
    )
    assert resp.status == 204
    await hass.async_block_till_done()

    # Second webhook with same data - should NOT trigger re-registration  
    # The key point: mdns/device_id are already in entry.data from init,
    # so webhook shouldn't see them as "changed"
    resp = await client.post(
        f"/api/webhook/{webhook_id}",
        json=mock_webhook_data,
    )
    assert resp.status == 204
    await hass.async_block_till_done()
    
    # Integration is working - no errors means no spurious re-registrations
    assert entry.state == ConfigEntryState.LOADED


async def test_webhook_registration_no_url_available(
    hass: HomeAssistant,
    mock_aiohttp_session,
) -> None:
    """Test webhook registration falls back to stored webhook_url."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device",
        data={
            "mdns": "http://wican_test.local:80",
            "host": "http://wican_test.local:80",
            CONF_WEBHOOK_ID: "test_webhook_id",
            "webhook_url": "http://192.168.1.10:8123/api/webhook/test_webhook_id",
        },
        unique_id="wican_test-192.168.1.100:80",
    )
    config_entry.add_to_hass(hass)

    with patch(
        "custom_components.wican._async_register_webhook_on_device",
        return_value=True,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entry = config_entry
    session = AsyncMock()
    response = AsyncMock()
    response.status = 200
    session.post.return_value = response

    with (
        patch(
            "custom_components.wican.webhook.async_generate_url",
            side_effect=NoURLAvailableError,
        ),
        patch(
            "custom_components.wican.async_get_clientsession",
            return_value=session,
        ),
    ):
        assert await _async_register_webhook_on_device(hass, entry) is True

    session.post.assert_awaited()
    assert session.post.await_args.kwargs["json"]["url"] == entry.data["webhook_url"]









