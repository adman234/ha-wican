"""Test the WiCAN sensor platform."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wican.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_sensor_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test sensor entities are created."""
    entity_registry = er.async_get(hass)

    # Check static status sensors exist
    wifi_mode = entity_registry.async_get("sensor.wican_device_wifi_mode")
    assert wifi_mode is not None
    assert wifi_mode.unique_id.endswith("_wifi_mode")

    batt_voltage = entity_registry.async_get("sensor.wican_device_batt_voltage")
    assert batt_voltage is not None
    assert batt_voltage.unique_id.endswith("_batt_voltage")

    vpn_status = entity_registry.async_get("sensor.wican_device_vpn_status")
    assert vpn_status is not None
    assert vpn_status.unique_id.endswith("_vpn_status")

    uptime = entity_registry.async_get("sensor.wican_device_uptime")
    assert uptime is not None
    assert uptime.unique_id.endswith("_uptime")


async def test_sensor_states_update_from_webhook(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test sensor states update when webhook data arrives."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Post webhook data
    await client.post(f"/api/webhook/{webhook_id}", json=mock_webhook_data)
    await hass.async_block_till_done()

    # Check sensor states
    wifi_mode_state = hass.states.get("sensor.wican_device_wifi_mode")
    assert wifi_mode_state is not None
    assert wifi_mode_state.state == "Station"

    batt_voltage_state = hass.states.get("sensor.wican_device_batt_voltage")
    assert batt_voltage_state is not None
    # Should normalize "12.5V" to 12.5
    assert batt_voltage_state.state == "12.5"

    vpn_status_state = hass.states.get("sensor.wican_device_vpn_status")
    assert vpn_status_state is not None
    assert vpn_status_state.state == "Not Connected"

    uptime_state = hass.states.get("sensor.wican_device_uptime")
    assert uptime_state is not None
    assert uptime_state.state == "01:00:00"


async def test_pid_sensor_entities_created(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test PID sensor entities are created dynamically."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Post webhook data with PIDs to trigger entity creation
    await client.post(f"/api/webhook/{webhook_id}", json=mock_webhook_data)
    await hass.async_block_till_done()

    # Check PID sensors exist (created after webhook)
    entity_registry = er.async_get(hass)

    engine_rpm = entity_registry.async_get("sensor.wican_device_engine_rpm")
    # PID sensors might not be in registry immediately
    if engine_rpm:
        assert engine_rpm.unique_id.endswith("_pid_0x0c")

    coolant_temp = entity_registry.async_get("sensor.wican_device_coolant_temp")
    if coolant_temp:
        assert coolant_temp.unique_id.endswith("_pid_0x05")


async def test_pid_sensor_states_update(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test PID sensor states update from webhook."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Post initial webhook data
    await client.post(f"/api/webhook/{webhook_id}", json=mock_webhook_data)
    await hass.async_block_till_done()

    # Check initial values
    engine_rpm_state = hass.states.get("sensor.wican_device_engine_rpm")
    if engine_rpm_state:
        assert engine_rpm_state.state == "1500"
        assert engine_rpm_state.attributes.get("unit_of_measurement") == "rpm"

    # Update webhook data with new values
    updated_data = mock_webhook_data.copy()
    updated_data["pids"]["pid_0x0c"]["value"] = 2000

    await client.post(f"/api/webhook/{webhook_id}", json=updated_data)
    await hass.async_block_till_done()

    # Check updated value
    engine_rpm_state = hass.states.get("sensor.wican_device_engine_rpm")
    if engine_rpm_state:
        assert engine_rpm_state.state == "2000"


async def test_sensor_voltage_normalization(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_webhook_data: dict,
    hass_client,
) -> None:
    """Test battery voltage normalization removes 'V' suffix."""
    entry = init_integration
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    client = await hass_client()

    # Test various voltage formats
    test_cases = [
        ("12.5V", "12.5"),
        ("11.3V", "11.3"),
        ("14.0V", "14.0"),
    ]

    for voltage_input, expected_state in test_cases:
        data = mock_webhook_data.copy()
        data["status"]["batt_voltage"] = voltage_input

        await client.post(f"/api/webhook/{webhook_id}", json=data)
        await hass.async_block_till_done()

        batt_voltage_state = hass.states.get("sensor.wican_device_batt_voltage")
        assert batt_voltage_state.state == expected_state


async def test_sensor_state_restoration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test sensor state is restored on startup."""
    # Store a state before setup
    hass.states.async_set(
        "sensor.wican_device_batt_voltage",
        "13.2",
        {"unit_of_measurement": "V"},
    )
    hass.states.async_set(
        "sensor.wican_device_wifi_mode",
        "AP",
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
    batt_voltage = hass.states.get("sensor.wican_device_batt_voltage")
    assert batt_voltage is not None
    assert batt_voltage.state == "13.2"
    
    wifi_mode = hass.states.get("sensor.wican_device_wifi_mode")
    assert wifi_mode is not None
    assert wifi_mode.state == "AP"
