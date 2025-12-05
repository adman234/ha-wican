"""Test the WiCAN binary sensor platform."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.const import CONF_WEBHOOK_ID, STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wican.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_binary_sensor_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test binary sensor entities are created."""
    entity_registry = er.async_get(hass)

    # Check binary sensors exist
    ble_status = entity_registry.async_get("binary_sensor.wican_device_ble_status")
    assert ble_status is not None
    assert ble_status.unique_id.endswith("_ble_status")

    ecu_status = entity_registry.async_get("binary_sensor.wican_device_ecu_status")
    assert ecu_status is not None
    assert ecu_status.unique_id.endswith("_ecu_status")


async def test_binary_sensor_states_update_from_webhook(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test binary sensor states update when webhook data arrives."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Post webhook data
    await client.post(f"/api/webhook/{webhook_id}", json=mock_webhook_data)
    await hass.async_block_till_done()

    # Check binary sensor states
    ble_status_state = hass.states.get("binary_sensor.wican_device_ble_status")
    assert ble_status_state is not None
    assert ble_status_state.state == STATE_OFF  # "Disabled" maps to off

    ecu_status_state = hass.states.get("binary_sensor.wican_device_ecu_status")
    assert ecu_status_state is not None
    assert ecu_status_state.state == STATE_ON  # "Online" maps to on


async def test_binary_sensor_bluetooth_on_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test Bluetooth binary sensor on/off states."""
    import copy
    
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Test "enable" (lowercase, as per TRUE_STRINGS) -> ON
    data = copy.deepcopy(mock_webhook_data)
    data["status"]["ble_status"] = "enable"

    await client.post(f"/api/webhook/{webhook_id}", json=data)
    await hass.async_block_till_done()

    ble_state = hass.states.get("binary_sensor.wican_device_ble_status")
    assert ble_state is not None
    assert ble_state.state == STATE_ON

    # Test "disable" -> OFF
    data = copy.deepcopy(mock_webhook_data)
    data["status"]["ble_status"] = "disable"

    await client.post(f"/api/webhook/{webhook_id}", json=data)
    await hass.async_block_till_done()

    ble_state = hass.states.get("binary_sensor.wican_device_ble_status")
    assert ble_state is not None
    assert ble_state.state == STATE_OFF


async def test_binary_sensor_ecu_on_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test ECU binary sensor on/off states."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Test "Online" -> ON
    data = mock_webhook_data.copy()
    data["status"]["ecu_status"] = "Online"

    await client.post(f"/api/webhook/{webhook_id}", json=data)
    await hass.async_block_till_done()

    ecu_state = hass.states.get("binary_sensor.wican_device_ecu_status")
    assert ecu_state.state == STATE_ON

    # Test "Offline" -> OFF
    data["status"]["ecu_status"] = "Offline"

    await client.post(f"/api/webhook/{webhook_id}", json=data)
    await hass.async_block_till_done()

    ecu_state = hass.states.get("binary_sensor.wican_device_ecu_status")
    assert ecu_state.state == STATE_OFF


async def test_binary_sensor_state_restoration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test binary sensor state is restored on startup."""
    # Store states before setup
    hass.states.async_set(
        "binary_sensor.wican_device_ble_status",
        "on",
    )
    hass.states.async_set(
        "binary_sensor.wican_device_ecu_status",
        "off",
    )
    
    # Ensure state is written to restore state storage
    await hass.async_block_till_done()
    
    # Set up the integration - this should restore states
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.wican.async_get_clientsession"
    ), patch(
        "custom_components.wican.WiCANDataUpdateCoordinator.async_config_entry_first_refresh"
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    
    # Check that states were restored
    ble_status = hass.states.get("binary_sensor.wican_device_ble_status")
    assert ble_status is not None
    assert ble_status.state == "on"
    
    ecu_status = hass.states.get("binary_sensor.wican_device_ecu_status")
    assert ecu_status is not None
    assert ecu_status.state == "off"
