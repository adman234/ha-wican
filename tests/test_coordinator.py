"""Test the WiCAN coordinator."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
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

    # Standard format (no space before unit)
    assert coordinator.normalize_sensor_value("batt_voltage", "12.5V") == 12.5
    assert coordinator.normalize_sensor_value("batt_voltage", "11.3V") == 11.3

    # Format with space before unit — reported firmware variant: "12 V"
    assert coordinator.normalize_sensor_value("batt_voltage", "12.5 V") == 12.5
    assert coordinator.normalize_sensor_value("batt_voltage", "12 V") == 12.0

    # Lowercase unit suffix
    assert coordinator.normalize_sensor_value("batt_voltage", "12.5v") == 12.5
    assert coordinator.normalize_sensor_value("batt_voltage", "12.5 v") == 12.5

    # Leading/trailing whitespace in the whole string
    assert coordinator.normalize_sensor_value("batt_voltage", " 12.5V ") == 12.5

    # Invalid voltage format — should return raw string
    assert coordinator.normalize_sensor_value("batt_voltage", "invalid") == "invalid"

    # Non-voltage key — should not strip "V"
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
    # This should not raise an error - first time device_id is accepted
    coordinator.handle_webhook_data(webhook_data)
    
    # Verify data was stored
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
    
    # Test non-numeric string fallback
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
    
    # Test get_sensor_value method
    assert coordinator.get_sensor_value("status") is not None
    assert coordinator.get_sensor_value("bus") == "0"
    assert coordinator.get_sensor_value("nonexistent") is None


async def test_coordinator_numeric_string_conversion_edge_cases(
    hass: HomeAssistant,
    hass_client,
) -> None:
    """Test coordinator handles numeric string edge cases."""
    from unittest.mock import patch
    from homeassistant.const import CONF_WEBHOOK_ID
    from custom_components.wican.const import DOMAIN
    from tests.conftest import MockConfigEntry
    
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "mdns": "http://wican_test.local",
            CONF_WEBHOOK_ID: "test_webhook",
        },
        title="WiCAN Test",
    )
    entry.add_to_hass(hass)
    
    with patch("custom_components.wican._async_register_webhook_on_device", return_value=True):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    
    client = await hass_client()
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    
    # Test invalid numeric string conversion
    await client.post(
        f"/api/webhook/{webhook_id}",
        json={
            "status": {
                "wifi_mode": "123.456.789",  # Looks numeric but invalid float
                "batt_voltage": "12.5"  # Valid float
            }
        }
    )
    await hass.async_block_till_done()
    
    # Verify entities handled the data
    state = hass.states.get("sensor.wican_test_wifi_mode")
    assert state is not None





def _coordinator_for(hass: HomeAssistant, data: dict) -> WiCANDataUpdateCoordinator:
    """Build a coordinator against a MockConfigEntry with the given data."""
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(cached_resolved_ip=None, device_host=None)
    return WiCANDataUpdateCoordinator(hass, entry)


async def test_status_urls_order_and_dedup(hass: HomeAssistant) -> None:
    """Cached IP is tried first, mDNS last, and duplicates collapse."""
    coordinator = _coordinator_for(
        hass, {"host": "http://192.168.1.100", "mdns": "http://wican_test.local"},
    )
    coordinator.config_entry.runtime_data.cached_resolved_ip = "192.168.1.100"

    assert coordinator._status_urls() == [
        "http://192.168.1.100/check_status",
        "http://wican_test.local/check_status",
    ]


async def test_status_urls_adds_missing_scheme(hass: HomeAssistant) -> None:
    """A bare host gains an http:// scheme."""
    coordinator = _coordinator_for(hass, {"host": "192.168.1.100"})
    assert coordinator._status_urls() == ["http://192.168.1.100/check_status"]


async def test_status_poll_strips_credentials(hass: HomeAssistant) -> None:
    """/check_status returns the WiFi PSK and MQTT credentials; none may be kept.

    The endpoint is unauthenticated and calls config_server_get_status_json(false),
    so the payload carries secrets the webhook path strips. Only allowlisted keys
    may reach coordinator data.
    """
    coordinator = _coordinator_for(hass, {"host": "http://192.168.1.100"})

    payload = {
        "batt_voltage": "13.9V",
        "battery_temp_min_c": 31,
        "battery_temp_max_c": 31,
        "sta_ssid": "my-network",
        "sta_pass": "hunter2",
        "mqtt_user": "user",
        "mqtt_pass": "secret",
        "batt_alert_pass": "secret",
        "batt_mqtt_pass": "secret",
        "batt_alert_url": "mqtt://example",
    }

    with patch.object(
        WiCANDataUpdateCoordinator, "_async_fetch_status", return_value=payload,
    ):
        data = await coordinator._async_update_data()

    status = data["status"]
    assert status["batt_voltage"] == "13.9V"
    assert status["battery_temp_min_c"] == 31
    for secret in (
        "sta_ssid", "sta_pass", "mqtt_user", "mqtt_pass",
        "batt_alert_pass", "batt_mqtt_pass", "batt_alert_url",
    ):
        assert secret not in status


async def test_status_poll_failure_keeps_last_values(hass: HomeAssistant) -> None:
    """A sleeping device must not blank out every entity."""
    coordinator = _coordinator_for(hass, {"host": "http://192.168.1.100"})
    coordinator._data["status"] = {"batt_voltage": "12.1V"}

    with patch.object(
        WiCANDataUpdateCoordinator, "_async_fetch_status", return_value=None,
    ):
        data = await coordinator._async_update_data()

    assert data["status"]["batt_voltage"] == "12.1V"


async def test_status_poll_preserves_webhook_data(hass: HomeAssistant) -> None:
    """Polling device status must not clobber webhook-pushed vehicle data."""
    coordinator = _coordinator_for(hass, {"host": "http://192.168.1.100"})
    coordinator._data["autopid_data"] = {"SOC": 72}

    with patch.object(
        WiCANDataUpdateCoordinator,
        "_async_fetch_status",
        return_value={"batt_voltage": "13.9V"},
    ):
        data = await coordinator._async_update_data()

    assert data["autopid_data"] == {"SOC": 72}
    assert data["status"]["batt_voltage"] == "13.9V"
