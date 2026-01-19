"""Tests for multi-device isolation.

WiCAN is push-based (webhooks). Multiple config entries share a dispatcher signal
(`DOMAIN`), so we must ensure dispatcher consumers filter by `webhook_id`.

These tests verify that dynamic PID sensor creation is isolated per entry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.wican.const import DOMAIN

from tests.conftest import MockConfigEntry


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.wican._async_register_webhook_on_device",
            return_value=True,
        ),
        patch(
            "custom_components.wican._schedule_webhook_registration",
            return_value=None,
        ),
        patch(
            "custom_components.wican.github_releases.GitHubReleasesCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_dynamic_pid_sensors_are_isolated_per_webhook_id(hass: HomeAssistant) -> None:
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device A",
        data={
            "mdns": "http://wican_a.local:80",
            "host": "http://wican_a.local:80",
            "device_id": "device_a",
            "hw_version": "v3.1",
            "fw_version": "2.00",
            "ip": "192.168.1.10",
            "webhook_id": "wh_a",
        },
        unique_id="wican-a",
    )

    entry2 = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device B",
        data={
            "mdns": "http://wican_b.local:80",
            "host": "http://wican_b.local:80",
            "device_id": "device_b",
            "hw_version": "v3.1",
            "fw_version": "2.00",
            "ip": "192.168.1.11",
            "webhook_id": "wh_b",
        },
        unique_id="wican-b",
    )

    await _setup_entry(hass, entry1)
    await _setup_entry(hass, entry2)

    # Send PID webhook for entry1 only
    webhook_data_1 = {
        "status": {"device_id": "device_a"},
        "autopid_data": {"rpm": 1500},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }
    entry1.runtime_data.coordinator.handle_webhook_data(webhook_data_1)
    async_dispatcher_send(hass, DOMAIN, "wh_a", webhook_data_1)
    await hass.async_block_till_done()

    # The entity is created by the dispatcher callback; trigger another coordinator
    # update so the newly-created entity gets an update cycle.
    entry1.runtime_data.coordinator.handle_webhook_data(webhook_data_1)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)

    # PID entity exists for entry1
    pid_unique_id_1 = f"{entry1.entry_id}_pid_rpm"
    e1 = next((e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_1), None)
    assert e1 is not None

    # And does NOT exist for entry2 yet (proves dispatcher filtering)
    pid_unique_id_2 = f"{entry2.entry_id}_pid_rpm"
    e2 = next((e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_2), None)
    assert e2 is None

    # Now send PID webhook for entry2; it should create its own entity
    webhook_data_2 = {
        "status": {"device_id": "device_b"},
        "autopid_data": {"rpm": 2200},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }
    entry2.runtime_data.coordinator.handle_webhook_data(webhook_data_2)
    async_dispatcher_send(hass, DOMAIN, "wh_b", webhook_data_2)
    await hass.async_block_till_done()

    entry2.runtime_data.coordinator.handle_webhook_data(webhook_data_2)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    e2 = next((e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_2), None)
    assert e2 is not None

    # Make sure both entities can coexist and keep distinct states
    state1 = hass.states.get(e1.entity_id)
    state2 = hass.states.get(e2.entity_id)
    assert state1 is not None
    assert state2 is not None
    assert state1.state == "1500"
    assert state2.state == "2200"


@pytest.mark.asyncio
async def test_unload_removes_pid_dispatcher_listener(hass: HomeAssistant) -> None:
    """Regression: unloading an entry must unsubscribe PID dispatcher listeners.

    Without this, a stale listener can fire later and access a ConfigEntry
    without runtime_data during reload/unload sequences.
    """

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Device",
        data={
            "mdns": "http://wican_test.local:80",
            "host": "http://wican_test.local:80",
            "device_id": "device_test",
            "webhook_id": "wh_test",
        },
        unique_id="wican-test",
    )

    await _setup_entry(hass, entry)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # If the PID handler wasn't unsubscribed, this could raise/log a task exception.
    async_dispatcher_send(hass, DOMAIN, "wh_test", {"autopid_data": {"rpm": 1}})
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_reload_does_not_leave_stale_pid_listener(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Reloading an entry should not leave stale PID listeners behind.

    This simulates a common real-world scenario: options changes or integration
    reload while webhooks are still arriving. We primarily assert that no
    AttributeError about missing runtime_data is logged, and that the PID entity
    continues to update after reload.
    """

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN Reload Test",
        data={
            "mdns": "http://wican_reload.local:80",
            "host": "http://wican_reload.local:80",
            "device_id": "device_reload",
            "webhook_id": "wh_reload",
        },
        unique_id="wican-reload",
    )

    await _setup_entry(hass, entry)

    # Create the PID entity.
    webhook_data = {
        "status": {"device_id": "device_reload"},
        "autopid_data": {"rpm": 1111},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }
    entry.runtime_data.coordinator.handle_webhook_data(webhook_data)
    async_dispatcher_send(hass, DOMAIN, "wh_reload", webhook_data)
    await hass.async_block_till_done()
    entry.runtime_data.coordinator.handle_webhook_data(webhook_data)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    pid_unique_id = f"{entry.entry_id}_pid_rpm"
    pid_entry = next(
        (e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id),
        None,
    )
    assert pid_entry is not None

    # Kick off reload and simulate webhook traffic during that window.
    reload_task = hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
    async_dispatcher_send(hass, DOMAIN, "wh_reload", webhook_data)
    await hass.async_block_till_done()
    await reload_task
    await hass.async_block_till_done()

    # After reload, the PID entity should still update and there should not be
    # any runtime_data attribute errors in logs.
    webhook_data_2 = {
        "status": {"device_id": "device_reload"},
        "autopid_data": {"rpm": 2222},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }

    # Find the reloaded entry instance (HA may recreate the object).
    reloaded_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert reloaded_entry is not None
    reloaded_entry.runtime_data.coordinator.handle_webhook_data(webhook_data_2)
    async_dispatcher_send(hass, DOMAIN, "wh_reload", webhook_data_2)
    await hass.async_block_till_done()
    reloaded_entry.runtime_data.coordinator.handle_webhook_data(webhook_data_2)
    await hass.async_block_till_done()

    # Ensure only one PID entity exists for this entry id + pid key.
    entity_reg = er.async_get(hass)
    matches = [e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id]
    assert len(matches) == 1

    state = hass.states.get(pid_entry.entity_id)
    assert state is not None
    assert state.state == "2222"

    assert "has no attribute 'runtime_data'" not in caplog.text


@pytest.mark.asyncio
async def test_two_devices_reload_one_does_not_affect_other(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """With two entries, reloading one must not break the other.

    This is the closest approximation of the real-world report: two WiCAN devices
    on the network, and one entry reload (options change / restart / reload).
    We assert:
    - dispatcher + dynamic PID creation remains isolated by webhook_id
    - the non-reloaded entry continues receiving updates
    - no duplicate PID entities are created across reload
    - no runtime_data AttributeError is logged
    """

    entry_a = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN A",
        data={
            "mdns": "http://wican_a.local:80",
            "host": "http://wican_a.local:80",
            "device_id": "device_a",
            "webhook_id": "wh_a",
        },
        unique_id="wican-a",
    )

    entry_b = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN B",
        data={
            "mdns": "http://wican_b.local:80",
            "host": "http://wican_b.local:80",
            "device_id": "device_b",
            "webhook_id": "wh_b",
        },
        unique_id="wican-b",
    )

    await _setup_entry(hass, entry_a)
    await _setup_entry(hass, entry_b)

    # Create PID entities on both entries.
    data_a_1 = {
        "status": {"device_id": "device_a"},
        "autopid_data": {"rpm": 1000},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }
    data_b_1 = {
        "status": {"device_id": "device_b"},
        "autopid_data": {"rpm": 3000},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }

    entry_a.runtime_data.coordinator.handle_webhook_data(data_a_1)
    async_dispatcher_send(hass, DOMAIN, "wh_a", data_a_1)
    await hass.async_block_till_done()
    entry_a.runtime_data.coordinator.handle_webhook_data(data_a_1)
    await hass.async_block_till_done()

    entry_b.runtime_data.coordinator.handle_webhook_data(data_b_1)
    async_dispatcher_send(hass, DOMAIN, "wh_b", data_b_1)
    await hass.async_block_till_done()
    entry_b.runtime_data.coordinator.handle_webhook_data(data_b_1)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    pid_unique_id_a = f"{entry_a.entry_id}_pid_rpm"
    pid_unique_id_b = f"{entry_b.entry_id}_pid_rpm"
    ent_a = next((e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_a), None)
    ent_b = next((e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_b), None)
    assert ent_a is not None
    assert ent_b is not None

    state_a = hass.states.get(ent_a.entity_id)
    state_b = hass.states.get(ent_b.entity_id)
    assert state_a is not None
    assert state_b is not None
    assert state_a.state == "1000"
    assert state_b.state == "3000"

    # Reload entry A while sending updates for entry B.
    reload_task = hass.async_create_task(hass.config_entries.async_reload(entry_a.entry_id))

    data_b_2 = {
        "status": {"device_id": "device_b"},
        "autopid_data": {"rpm": 4000},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }
    entry_b.runtime_data.coordinator.handle_webhook_data(data_b_2)
    async_dispatcher_send(hass, DOMAIN, "wh_b", data_b_2)
    entry_b.runtime_data.coordinator.handle_webhook_data(data_b_2)
    await hass.async_block_till_done()

    await reload_task
    await hass.async_block_till_done()

    # Entry B must have updated during/around the reload.
    state_b = hass.states.get(ent_b.entity_id)
    assert state_b is not None
    assert state_b.state == "4000"

    # After reload, entry A should still update and not duplicate entities.
    reloaded_a = hass.config_entries.async_get_entry(entry_a.entry_id)
    assert reloaded_a is not None

    data_a_2 = {
        "status": {"device_id": "device_a"},
        "autopid_data": {"rpm": 2000},
        "config": {"rpm": {"unit": "rpm", "class": ""}},
    }
    reloaded_a.runtime_data.coordinator.handle_webhook_data(data_a_2)
    async_dispatcher_send(hass, DOMAIN, "wh_a", data_a_2)
    reloaded_a.runtime_data.coordinator.handle_webhook_data(data_a_2)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    matches_a = [e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_a]
    matches_b = [e for e in entity_reg.entities.values() if e.unique_id == pid_unique_id_b]
    assert len(matches_a) == 1
    assert len(matches_b) == 1

    state_a = hass.states.get(matches_a[0].entity_id)
    assert state_a is not None
    assert state_a.state == "2000"

    assert "has no attribute 'runtime_data'" not in caplog.text
