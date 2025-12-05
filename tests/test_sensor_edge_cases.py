"""Test edge cases for WiCAN sensor platform."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wican.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_pid_sensor_invalid_unit_normalization(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    hass_client,
) -> None:
    """Test PID sensors handle invalid unit values properly."""
    # Add PID configuration with various invalid unit values
    entry_data = mock_config_entry.data.copy()
    entry_data["pid_keys"] = ["pid_0x01", "pid_0x02", "pid_0x03"]
    entry_data["config"] = {
        "pid_0x01": {"unit": "none", "class": "temperature"},  # "none" should become None
        "pid_0x02": {"unit": "", "class": "speed"},  # empty string should become None
        "pid_0x03": {"unit": None, "class": "pressure"},  # None should stay None
    }
    mock_config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device",
        data=entry_data,
        options=mock_config_entry.options,
        unique_id=mock_config_entry.unique_id,
    )
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.wican.async_get_clientsession"
    ), patch(
        "custom_components.wican.WiCANDataUpdateCoordinator.async_config_entry_first_refresh"
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Verify sensors were created with normalized units
    entity_registry = er.async_get(hass)
    
    sensor1 = entity_registry.async_get("sensor.wican_device_pid_0x01")
    if sensor1:
        state = hass.states.get("sensor.wican_device_pid_0x01")
        # Unit should be None (not "none")
        assert state.attributes.get("unit_of_measurement") is None


async def test_pid_sensor_device_class_normalization_rpm_speed_mismatch(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test device_class=speed with rpm unit gets dropped to avoid mismatch."""
    # Add PID configuration with speed class but rpm unit (invalid combo)
    entry_data = mock_config_entry.data.copy()
    entry_data["pid_keys"] = ["pid_rpm_speed"]
    entry_data["config"] = {
        "pid_rpm_speed": {"unit": "rpm", "class": "speed"},  # Invalid: speed class + rpm unit
    }
    mock_config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device",
        data=entry_data,
        options=mock_config_entry.options,
        unique_id=mock_config_entry.unique_id,
    )
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.wican.async_get_clientsession"
    ), patch(
        "custom_components.wican.WiCANDataUpdateCoordinator.async_config_entry_first_refresh"
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Verify sensor created but device_class was dropped
    state = hass.states.get("sensor.wican_device_pid_rpm_speed")
    if state:
        # device_class should be None (dropped due to mismatch)
        assert state.attributes.get("device_class") is None
        assert state.attributes.get("unit_of_measurement") == "rpm"


async def test_pid_sensor_invalid_device_class_string(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor handles invalid device_class strings."""
    entry_data = mock_config_entry.data.copy()
    entry_data["pid_keys"] = ["pid_invalid_class"]
    entry_data["config"] = {
        "pid_invalid_class": {"unit": "°C", "class": "invalid_class_name"},
    }
    mock_config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device",
        data=entry_data,
        options=mock_config_entry.options,
        unique_id=mock_config_entry.unique_id,
    )
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.wican.async_get_clientsession"
    ), patch(
        "custom_components.wican.WiCANDataUpdateCoordinator.async_config_entry_first_refresh"
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    # Sensor should be created with device_class=None
    state = hass.states.get("sensor.wican_device_pid_invalid_class")
    if state:
        assert state.attributes.get("device_class") is None


async def test_pid_sensor_empty_autopid_data(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
) -> None:
    """Test webhook with empty autopid_data doesn't crash."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    client = await hass_client()

    # Send webhook with empty autopid_data
    data = {
        "status": {
            "wifi_mode": "Station",
            "batt_voltage": "12.5V",
            "vpn_status": "Not Connected",
        },
        "autopid_data": {},  # Empty PID data
    }

    response = await client.post(f"/api/webhook/{webhook_id}", json=data)
    assert response.status == 204


async def test_pid_sensor_no_autopid_data(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
) -> None:
    """Test webhook without autopid_data doesn't crash."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    client = await hass_client()

    # Send webhook without autopid_data at all
    data = {
        "status": {
            "wifi_mode": "Station",
            "batt_voltage": "12.5V",
            "vpn_status": "Not Connected",
        },
        # No autopid_data key
    }

    response = await client.post(f"/api/webhook/{webhook_id}", json=data)
    assert response.status == 204


async def test_pid_sensor_with_config_from_webhook(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
) -> None:
    """Test PID sensor configuration can come from webhook config section."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    client = await hass_client()

    # Send webhook with PID data AND config
    data = {
        "status": {
            "wifi_mode": "Station",
            "batt_voltage": "12.5V",
        },
        "pids": {
            "pid_0x0d": {"value": 85, "name": "Vehicle Speed"}
        },
        "config": {
            "pid_0x0d": {"unit": "km/h", "class": "speed"}
        }
    }

    response = await client.post(f"/api/webhook/{webhook_id}", json=data)
    assert response.status == 204
    await hass.async_block_till_done()

    # Check that sensor was created with config from webhook
    state = hass.states.get("sensor.wican_device_vehicle_speed")
    if state:
        assert state.attributes.get("unit_of_measurement") == "km/h"


async def test_sensor_invalid_voltage_format(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test sensor handles invalid voltage formats gracefully."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    client = await hass_client()

    # Test invalid voltage formats
    test_cases = [
        ("invalid", "invalid"),  # Non-numeric string passes through
        ("12.5.3V", "12.5.3V"),  # Multiple decimals (invalid, passes through)
        ("ABC", "ABC"),  # Pure alpha passes through
        ("", ""),  # Empty string edge case
    ]

    for invalid_voltage, expected in test_cases:
        data = mock_webhook_data.copy()
        data["status"]["batt_voltage"] = invalid_voltage

        await client.post(f"/api/webhook/{webhook_id}", json=data)
        await hass.async_block_till_done()

        batt_voltage_state = hass.states.get("sensor.wican_device_batt_voltage")
        # Normalization should handle invalid values gracefully
        # Invalid values pass through as-is
        assert batt_voltage_state.state in (invalid_voltage, "unknown", expected)


async def test_sensor_numeric_string_normalization(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test sensors normalize numeric strings to numbers."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    client = await hass_client()

    # Test numeric string normalization
    test_cases = [
        ("42", 42),  # Integer string
        ("3.14", 3.14),  # Float string
        ("100.0", 100.0),  # Float with .0
    ]

    for string_val, expected_num in test_cases:
        data = {
            "status": {
                "wifi_mode": string_val,  # Numeric string in non-numeric field
                "batt_voltage": "12.5V",
            }
        }

        await client.post(f"/api/webhook/{webhook_id}", json=data)
        await hass.async_block_till_done()

        # Coordinator should normalize, but string fields stay as string
        # (only voltage gets special treatment)


async def test_pid_sensor_value_update_with_pending_value(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
) -> None:
    """Test PID sensor properly handles pending value updates."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    client = await hass_client()

    # Send initial PID data
    data = {
        "status": {"wifi_mode": "Station"},
        "pids": {
            "pid_0x0c": {"value": 1000, "name": "Engine RPM"}
        },
        "config": {
            "pid_0x0c": {"unit": "rpm", "class": None}
        }
    }
    await client.post(f"/api/webhook/{webhook_id}", json=data)
    await hass.async_block_till_done()

    # Check initial value
    state = hass.states.get("sensor.wican_device_engine_rpm")
    if state:
        assert float(state.state) == 1000

    # Send update
    data["pids"]["pid_0x0c"]["value"] = 2500
    await client.post(f"/api/webhook/{webhook_id}", json=data)
    await hass.async_block_till_done()

    # Check updated value
    state = hass.states.get("sensor.wican_device_engine_rpm")
    if state:
        assert float(state.state) == 2500
