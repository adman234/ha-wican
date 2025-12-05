"""Test PID sensor dynamic configuration from webhook data."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.wican.const import DOMAIN

from tests.conftest import MockConfigEntry


async def test_pid_sensor_dynamic_creation_from_webhook(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensors are created dynamically from webhook data."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Simulate webhook with PID data
    webhook_data = {
        "bus": "0",
        "type": "rx",
        "ts": 12345,
        "frame": [{"id": 2015, "dlc": 8, "rtr": False, "extd": False, "data": [1, 2, 3, 4, 5, 6, 7, 8]}],
        "autopid_data": {
            "rpm": 1500,
            "speed": 65,
            "coolant_temp": 85
        },
        "config": {
            "rpm": {"unit": "rpm", "class": ""},
            "speed": {"unit": "km/h", "class": "speed"},
            "coolant_temp": {"unit": "°C", "class": "temperature"}
        }
    }

    # Send webhook via dispatcher (simulates webhook handler)
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # Verify PID sensors were created
    entity_reg = er.async_get(hass)
    
    rpm_entity = entity_reg.async_get("sensor.wican_device_rpm")
    assert rpm_entity is not None
    assert hass.states.get("sensor.wican_device_rpm").state == "1500"
    
    speed_entity = entity_reg.async_get("sensor.wican_device_speed")
    assert speed_entity is not None
    assert hass.states.get("sensor.wican_device_speed").state == "65"
    
    coolant_entity = entity_reg.async_get("sensor.wican_device_coolant_temp")
    assert coolant_entity is not None
    assert hass.states.get("sensor.wican_device_coolant_temp").state == "85"


async def test_pid_sensor_unit_normalization(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor handles unit normalization (none, empty string, None)."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Test with various "no unit" values
    webhook_data = {
        "autopid_data": {
            "pid_none": 100,
            "pid_empty": 200,
            "pid_null": 300
        },
        "config": {
            "pid_none": {"unit": "none", "class": ""},
            "pid_empty": {"unit": "", "class": ""},
            "pid_null": {"unit": None, "class": ""}
        }
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # All should have None as unit
    state_none = hass.states.get("sensor.wican_device_pid_none")
    assert state_none is not None
    assert state_none.attributes.get("unit_of_measurement") is None
    
    state_empty = hass.states.get("sensor.wican_device_pid_empty")
    assert state_empty is not None
    assert state_empty.attributes.get("unit_of_measurement") is None
    
    state_null = hass.states.get("sensor.wican_device_pid_null")
    assert state_null is not None
    assert state_null.attributes.get("unit_of_measurement") is None


async def test_pid_sensor_device_class_normalization(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor device_class normalization."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    webhook_data = {
        "autopid_data": {
            "temp": 25,
            "pressure": 101.3,
            "custom": 42
        },
        "config": {
            "temp": {"unit": "°C", "class": "temperature"},
            "pressure": {"unit": "kPa", "class": "pressure"},
            "custom": {"unit": "custom", "class": "invalid_class"}
        }
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # Valid device classes
    temp_state = hass.states.get("sensor.wican_device_temp")
    assert temp_state.attributes.get("device_class") == "temperature"
    
    pressure_state = hass.states.get("sensor.wican_device_pressure")
    assert pressure_state.attributes.get("device_class") == "pressure"
    
    # Invalid device class should be None
    custom_state = hass.states.get("sensor.wican_device_custom")
    assert custom_state.attributes.get("device_class") is None


async def test_pid_sensor_config_persistence(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor config is persisted to config entry."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    webhook_data = {
        "autopid_data": {
            "new_pid": 123
        },
        "config": {
            "new_pid": {"unit": "unit", "class": ""}
        }
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # Check config was saved
    entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert "config" in entry.data
    assert "new_pid" in entry.data["config"]
    assert entry.data["config"]["new_pid"]["unit"] == "unit"
    assert "pid_keys" in entry.data
    assert "new_pid" in entry.data["pid_keys"]


async def test_pid_sensor_update_existing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test updating existing PID sensor values."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Create initial PID sensor
    webhook_data_1 = {
        "autopid_data": {"test_pid": 100},
        "config": {"test_pid": {"unit": "unit", "class": ""}}
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data_1)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data_1)
    await hass.async_block_till_done()
    
    assert hass.states.get("sensor.wican_device_test_pid").state == "100"
    
    # Update with new value
    webhook_data_2 = {
        "autopid_data": {"test_pid": 200},
        "config": {"test_pid": {"unit": "unit", "class": ""}}
    }
    
    coordinator.handle_webhook_data(webhook_data_2)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data_2)
    await hass.async_block_till_done()
    
    # Value should be updated
    assert hass.states.get("sensor.wican_device_test_pid").state == "200"


async def test_pid_sensor_multiple_webhooks(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test multiple webhooks adding different PID sensors."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    
    # First webhook with some PIDs
    webhook_data_1 = {
        "autopid_data": {"pid1": 10, "pid2": 20},
        "config": {
            "pid1": {"unit": "u1", "class": ""},
            "pid2": {"unit": "u2", "class": ""}
        }
    }
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data_1)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data_1)
    await hass.async_block_till_done()
    
    # Second webhook with additional PIDs
    webhook_data_2 = {
        "autopid_data": {"pid2": 25, "pid3": 30},
        "config": {
            "pid2": {"unit": "u2", "class": ""},
            "pid3": {"unit": "u3", "class": ""}
        }
    }
    coordinator.handle_webhook_data(webhook_data_2)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data_2)
    await hass.async_block_till_done()
    
    # All PIDs should exist
    assert hass.states.get("sensor.wican_device_pid1").state == "10"
    assert hass.states.get("sensor.wican_device_pid2").state == "25"  # Updated
    assert hass.states.get("sensor.wican_device_pid3").state == "30"  # New


async def test_pid_sensor_no_config_section(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensors work when config section is missing."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Webhook without config section
    webhook_data = {
        "autopid_data": {"test_pid": 42}
        # No "config" key
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # Should still create sensor with default config
    state = hass.states.get("sensor.wican_device_test_pid")
    assert state is not None
    assert state.state == "42"
    assert state.attributes.get("unit_of_measurement") is None
    assert state.attributes.get("device_class") is None


async def test_pid_sensor_partial_config(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensor handles partial config (some PIDs configured, some not)."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    webhook_data = {
        "autopid_data": {
            "configured_pid": 100,
            "unconfigured_pid": 200
        },
        "config": {
            "configured_pid": {"unit": "unit", "class": "temperature"}
            # unconfigured_pid has no config
        }
    }
    
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # Configured PID
    configured_state = hass.states.get("sensor.wican_device_configured_pid")
    assert configured_state.state == "100"
    assert configured_state.attributes.get("unit_of_measurement") == "unit"
    assert configured_state.attributes.get("device_class") == "temperature"
    
    # Unconfigured PID (defaults)
    unconfigured_state = hass.states.get("sensor.wican_device_unconfigured_pid")
    assert unconfigured_state.state == "200"
    assert unconfigured_state.attributes.get("unit_of_measurement") is None
    assert unconfigured_state.attributes.get("device_class") is None


async def test_pid_sensor_empty_pids_dict(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test webhook with empty pids dict doesn't crash."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Empty pids
    webhook_data = {
        "autopid_data": {},
        "config": {}
    }
    
    # Should not crash
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()


async def test_pid_sensor_real_world_data_format(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test PID sensors with real-world WiCAN webhook data format."""
    mock_config_entry.add_to_hass(hass)
    
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Real-world data format from actual WiCAN device
    webhook_data = {
        "config": {
            "ENGINE_RPM": {"class": "frequency", "unit": "RPM"},
            "SPEED": {"class": "speed", "unit": "km/h"},
            "COOLANT_TMP": {"class": "temperature", "unit": "°C"},
            "FUEL": {"class": "none", "unit": "%"},
            "INTAKE_AIR_TMP": {"class": "temperature", "unit": "°C"},
            "THROTTLE": {"class": "none", "unit": "%"},
            "MAF": {"class": "none", "unit": "g/s"},
            "FUEL_PRESSURE": {"class": "pressure", "unit": "kPa"},
            "0C-EngineRPM": {"class": "speed", "unit": "rpm"},
            "0D-VehicleSpeed": {"class": "speed", "unit": "km/h"},
        },
        "autopid_data": {
            "ENGINE_RPM": 4300,
            "SPEED": 26,
            "COOLANT_TMP": 162,
            "FUEL": 62.35,
            "INTAKE_AIR_TMP": -40,
            "THROTTLE": 53.33,
            "MAF": 12.28,
            "FUEL_PRESSURE": 300,
            "0C-EngineRPM": 4300,
            "0D-VehicleSpeed": 26,
        }
    }
    
    # Send webhook
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, "wican", "test_webhook_id", webhook_data)
    await hass.async_block_till_done()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    
    # Verify critical sensors were created with correct values
    entity_reg = er.async_get(hass)
    
    # ENGINE_RPM sensor
    rpm_entity = entity_reg.async_get("sensor.wican_device_engine_rpm")
    assert rpm_entity is not None
    rpm_state = hass.states.get("sensor.wican_device_engine_rpm")
    assert rpm_state.state == "4300"
    assert rpm_state.attributes.get("unit_of_measurement") == "RPM"
    # Note: "frequency" class should be normalized to None or valid HA device class
    
    # SPEED sensor
    speed_entity = entity_reg.async_get("sensor.wican_device_speed")
    assert speed_entity is not None
    speed_state = hass.states.get("sensor.wican_device_speed")
    assert speed_state.state == "26"
    assert speed_state.attributes.get("unit_of_measurement") == "km/h"
    assert speed_state.attributes.get("device_class") == "speed"
    
    # COOLANT_TMP sensor
    coolant_entity = entity_reg.async_get("sensor.wican_device_coolant_tmp")
    assert coolant_entity is not None
    coolant_state = hass.states.get("sensor.wican_device_coolant_tmp")
    assert coolant_state.state == "162"
    assert coolant_state.attributes.get("unit_of_measurement") == "°C"
    assert coolant_state.attributes.get("device_class") == "temperature"
    
    # FUEL sensor (class="none" should normalize to None)
    fuel_entity = entity_reg.async_get("sensor.wican_device_fuel")
    assert fuel_entity is not None
    fuel_state = hass.states.get("sensor.wican_device_fuel")
    assert fuel_state.state == "62.35"
    assert fuel_state.attributes.get("unit_of_measurement") == "%"
    # device_class should be None since "none" is not a valid HA device class
    
    # FUEL_PRESSURE sensor
    pressure_entity = entity_reg.async_get("sensor.wican_device_fuel_pressure")
    assert pressure_entity is not None
    pressure_state = hass.states.get("sensor.wican_device_fuel_pressure")
    assert pressure_state.state == "300"
    assert pressure_state.attributes.get("unit_of_measurement") == "kPa"
    assert pressure_state.attributes.get("device_class") == "pressure"
    
    # 0C-EngineRPM sensor (with special chars in name)
    # Note: device_class="speed" with unit="rpm" is invalid, so it gets normalized to None
    obd_rpm_entity = entity_reg.async_get("sensor.wican_device_0c_enginerpm")
    assert obd_rpm_entity is not None
    obd_rpm_state = hass.states.get("sensor.wican_device_0c_enginerpm")
    assert obd_rpm_state.state == "4300"
    assert obd_rpm_state.attributes.get("unit_of_measurement") == "rpm"
    # device_class is None because speed+rpm is an invalid combination
    assert obd_rpm_state.attributes.get("device_class") is None
    
    # Verify config was persisted to entry
    updated_entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert "ENGINE_RPM" in updated_entry.data.get("pid_keys", [])
    assert "SPEED" in updated_entry.data.get("pid_keys", [])
    assert "COOLANT_TMP" in updated_entry.data.get("pid_keys", [])
    assert "0C-EngineRPM" in updated_entry.data.get("pid_keys", [])
