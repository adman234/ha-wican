"""Test edge cases for complete coverage."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wican.attributes import get_sensor_attributes
from custom_components.wican.binary_sensor import is_true_status
from custom_components.wican.sensor import SENSOR_DESCRIPTIONS

from tests.conftest import MockConfigEntry


def test_is_true_status_with_non_string():
    """Test is_true_status with non-string values."""
    # Test with integers
    assert is_true_status(1) is True
    assert is_true_status(0) is False
    
    # Test with boolean
    assert is_true_status(True) is True
    assert is_true_status(False) is False
    
    # Test with None
    assert is_true_status(None) is False
    
    # Test with list (any truthy value)
    assert is_true_status([1, 2]) is True
    assert is_true_status([]) is False


def test_get_sensor_attributes_with_none_values():
    """Test get_sensor_attributes when status values are None."""
    from custom_components.wican.sensor import WiCANSensorEntityDescription
    
    # Create entity description with extra_attributes
    entity_desc = WiCANSensorEntityDescription(
        key="test_sensor",
        name="Test Sensor",
        extra_attributes=["attr1", "attr2", "attr3"]
    )
    
    # Test data where some attributes are None
    data = {
        "status": {
            "attr1": "value1",
            "attr2": None,  # This should be skipped (line 80)
            "attr3": "value3"
        }
    }
    
    attrs = get_sensor_attributes(entity_desc, data)
    
    # Only non-None attributes should be included
    assert "attr1" in attrs
    assert "attr2" not in attrs  # Skipped because None
    assert "attr3" in attrs
    assert attrs["attr1"] == "value1"
    assert attrs["attr3"] == "value3"


async def test_binary_sensor_state_restoration_with_none_initial(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test binary sensor state restoration when initial state is None."""
    mock_config_entry.add_to_hass(hass)
    
    # Pre-populate state registry with a saved state
    hass.states.async_set(
        "binary_sensor.wican_device_ble_status",
        "on",
        {"restored": True}
    )
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # State should be restored
    state = hass.states.get("binary_sensor.wican_device_ble_status")
    assert state is not None
    # Initial state should be restored from saved state


async def test_coordinator_first_device_id_acceptance(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator accepts device_id on first webhook (no stored device_id)."""
    # Create config entry without device_id
    config_entry = MockConfigEntry(
        domain="wican",
        data={
            "host": "wican_test.local",
            "webhook_id": "test_webhook_new",
            # No device_id in config
        },
        title="WiCAN Device",
        unique_id="test_unique_new",
    )
    config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Allow webhook registration to complete
    import asyncio
    await asyncio.sleep(0.1)
    
    # Send webhook with device_id for the first time
    webhook_data = {
        "status": {"device_id": "new_device_abc123"},
        "bus": "0",
        "type": "rx",
        "ts": 12345,
        "frame": []
    }
    
    coordinator = config_entry.runtime_data.coordinator
    # This should not raise an error - first time device_id is accepted (lines 109-113)
    coordinator.handle_webhook_data(webhook_data)
    
    # Verify data was stored (device_id is in status dict)
    assert coordinator.data.get("status", {}).get("device_id") == "new_device_abc123"


async def test_coordinator_normalize_numeric_strings(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator normalize_sensor_value with numeric strings."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    coordinator = mock_config_entry.runtime_data.coordinator
    
    # Test integer string
    assert coordinator.normalize_sensor_value("test", "123") == 123
    
    # Test float string  
    assert coordinator.normalize_sensor_value("test", "45.67") == 45.67
    
    # Test negative numbers
    assert coordinator.normalize_sensor_value("test", "-89") == -89
    assert coordinator.normalize_sensor_value("test", "-12.34") == -12.34
    
    # Test non-numeric string (lines 167-168 fallback)
    assert coordinator.normalize_sensor_value("test", "not_a_number") == "not_a_number"
    assert coordinator.normalize_sensor_value("test", "12.34.56") == "12.34.56"


async def test_coordinator_get_sensor_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator get_sensor_value method."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    coordinator = mock_config_entry.runtime_data.coordinator
    
    # Add some data
    webhook_data = {
        "status": {"wifi_mode": "Station", "batt_voltage": "13.2V"},
        "bus": "0",
        "type": "rx",
        "ts": 12345,
        "frame": []
    }
    coordinator.handle_webhook_data(webhook_data)
    
    # Test get_sensor_value method (line 174)
    # get_sensor_value looks in top-level _data, not nested in status
    assert coordinator.get_sensor_value("status") is not None
    assert coordinator.get_sensor_value("bus") == "0"
    assert coordinator.get_sensor_value("nonexistent") is None


async def test_sensor_restoration_with_none_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor state restoration when saved state is None."""
    mock_config_entry.add_to_hass(hass)
    
    # Don't pre-populate any state (or set state to None)
    # This tests line 202 - when state is None or state.native_value is None
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Sensors should be created with unknown state
    state = hass.states.get("sensor.wican_device_wifi_mode")
    assert state is not None
    assert state.state == "unknown"


async def test_pid_sensor_restoration_with_none_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor restoration when state is None."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    
    mock_config_entry.add_to_hass(hass)
    
    # No pre-saved state - this tests line 248 (when state is None)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Create a PID sensor without any prior state
    webhook_data = {
        "autopid_data": {"test_pid_new": 100},
        "config": {"test_pid_new": {"unit": "test_unit", "class": ""}}
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # PID sensor should be created (line 248 covered when state is None)
    entity_reg = er.async_get(hass)
    test_pid_entity = entity_reg.async_get("sensor.wican_device_test_pid_new")
    assert test_pid_entity is not None


async def test_pid_sensor_with_pending_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor async_added_to_hass with pending value."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Send webhook to create PID sensor with data before entity is fully added
    webhook_data = {
        "autopid_data": {"pending_pid": 999},
        "config": {"pending_pid": {"unit": "test", "class": ""}}
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # The pending_value logic (lines 250-252) handles values that arrive
    # before the entity is fully initialized
    state = hass.states.get("sensor.wican_device_pending_pid")
    assert state is not None
    assert state.state == "999"
