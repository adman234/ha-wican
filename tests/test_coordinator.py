"""Test the WiCAN coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util

from custom_components.wican.coordinator import WiCANDataUpdateCoordinator

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)


async def test_coordinator_initialization(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator initializes correctly."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)

    assert coordinator.config_entry == mock_config_entry
    # Coordinator name is the domain (lowercase)
    assert coordinator.name == "wican"
    assert coordinator.update_interval == timedelta(minutes=5)
    # Data is None until first update
    assert coordinator.data is None


async def test_coordinator_first_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test coordinator first refresh succeeds."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)

    await coordinator.async_config_entry_first_refresh()

    # Should succeed with empty data (push-based integration)
    assert coordinator.data == {}
    assert coordinator.last_update_success is True


async def test_coordinator_handle_webhook_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webhook_data: dict,
) -> None:
    """Test coordinator handles webhook data."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)

    await coordinator.async_config_entry_first_refresh()

    # Simulate webhook data
    coordinator.handle_webhook_data(mock_webhook_data)

    assert coordinator.data == mock_webhook_data
    assert coordinator.last_update_success is True


async def test_coordinator_device_identity_validation_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webhook_data: dict,
) -> None:
    """Test device identity validation passes for correct device."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)
    await coordinator.async_config_entry_first_refresh()

    # Device ID matches config entry
    coordinator.handle_webhook_data(mock_webhook_data)

    assert coordinator.data == mock_webhook_data


async def test_coordinator_device_identity_validation_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webhook_data: dict,
) -> None:
    """Test device identity validation rejects wrong device."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)
    await coordinator.async_config_entry_first_refresh()

    # Change device_id to simulate wrong device
    wrong_device_data = mock_webhook_data.copy()
    wrong_device_data["status"]["device_id"] = "different_device_456"

    with pytest.raises(ConfigEntryError):
        coordinator.handle_webhook_data(wrong_device_data)


async def test_coordinator_device_identity_validation_no_device_id(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webhook_data: dict,
) -> None:
    """Test device identity validation skipped when no device_id."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)
    await coordinator.async_config_entry_first_refresh()

    # Remove device_id from webhook data
    no_device_id_data = mock_webhook_data.copy()
    del no_device_id_data["status"]["device_id"]

    # Should not raise exception (backward compatibility)
    coordinator.handle_webhook_data(no_device_id_data)

    assert coordinator.data == no_device_id_data


async def test_coordinator_normalize_sensor_value_voltage(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor value normalization for voltage."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)

    # Battery voltage with "V" suffix
    assert coordinator.normalize_sensor_value("batt_voltage", "12.5V") == 12.5
    assert coordinator.normalize_sensor_value("batt_voltage", "11.3V") == 11.3

    # Invalid voltage format
    assert coordinator.normalize_sensor_value("batt_voltage", "invalid") == "invalid"

    # Non-voltage key
    assert coordinator.normalize_sensor_value("other_key", "12.5V") == "12.5V"


async def test_coordinator_normalize_sensor_value_numeric_strings(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor value normalization for numeric strings."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)

    # Integer strings
    assert coordinator.normalize_sensor_value("some_key", "42") == 42
    assert coordinator.normalize_sensor_value("some_key", "1500") == 1500

    # Float strings
    assert coordinator.normalize_sensor_value("some_key", "3.14") == 3.14
    assert coordinator.normalize_sensor_value("some_key", "90.5") == 90.5

    # Negative numbers
    assert coordinator.normalize_sensor_value("some_key", "-10") == -10
    assert coordinator.normalize_sensor_value("some_key", "-3.5") == -3.5

    # Non-numeric strings
    assert coordinator.normalize_sensor_value("some_key", "text") == "text"
    assert coordinator.normalize_sensor_value("some_key", "Online") == "Online"


async def test_coordinator_normalize_sensor_value_none(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor value normalization handles None."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)

    assert coordinator.normalize_sensor_value("any_key", None) is None


async def test_coordinator_update_listeners_called(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webhook_data: dict,
) -> None:
    """Test coordinator notifies listeners on data update."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)
    await coordinator.async_config_entry_first_refresh()

    listener_called = False

    def listener():
        nonlocal listener_called
        listener_called = True

    unsub = coordinator.async_add_listener(listener)

    # Update data should trigger listener
    coordinator.handle_webhook_data(mock_webhook_data)

    assert listener_called is True
    
    # Clean up to avoid lingering timer errors
    unsub()
    # Cancel the coordinator's refresh timer
    if hasattr(coordinator, "_unsub_refresh") and coordinator._unsub_refresh:
        coordinator._unsub_refresh()


async def test_coordinator_fallback_polling(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webhook_data: dict,
) -> None:
    """Test coordinator handles fallback polling (keeps last data)."""
    coordinator = WiCANDataUpdateCoordinator(hass, mock_config_entry)
    await coordinator.async_config_entry_first_refresh()

    # Set initial data via webhook
    coordinator.handle_webhook_data(mock_webhook_data)
    initial_data = coordinator.data

    # Simulate time passing (trigger polling update)
    future = dt_util.utcnow() + timedelta(minutes=6)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()

    # Data should remain the same (push-based, no polling fetch)
    assert coordinator.data == initial_data
