"""Test specific version installation feature."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.update import (
    ATTR_VERSION,
    DOMAIN as UPDATE_DOMAIN,
    SERVICE_INSTALL,
)
from homeassistant.const import ATTR_ENTITY_ID
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wican.const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def mock_params_update():
    """Mock async_update_params_from_github to prevent blocking I/O in tests."""
    with patch(
        "custom_components.wican.param_loader.async_update_params_from_github",
        new_callable=AsyncMock,
        return_value=False,
    ):
        yield


@pytest.fixture
def mock_github_releases_list():
    """Return mock GitHub releases list with multiple versions."""
    return [
        {
            "tag_name": "v4.45p",
            "name": "WiCAN-PRO v4.45",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.45p",
            "body": "Bug fixes",
            "prerelease": False,
            "assets": [
                {
                    "name": "wican-fw_obd_pro_v445p.bin",
                    "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.45p/wican-fw_obd_pro_v445p.bin",
                    "size": 3342336,
                },
            ],
        },
        {
            "tag_name": "v4.44p",
            "name": "WiCAN-PRO v4.44",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.44p",
            "body": "Previous version",
            "prerelease": False,
            "assets": [
                {
                    "name": "wican-fw_obd_pro_v444p.bin",
                    "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.44p/wican-fw_obd_pro_v444p.bin",
                    "size": 3342336,
                },
            ],
        },
        {
            "tag_name": "v4.13",
            "name": "WiCAN v4.13",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.13",
            "body": "Standard version",
            "prerelease": False,
            "assets": [
                {
                    "name": "wican-fw_obd_v413.bin",
                    "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.13/wican-fw_obd_v413.bin",
                    "size": 1646592,
                },
            ],
        },
    ]


async def test_install_specific_version(
    hass: HomeAssistant,
    mock_github_releases_list: list[dict],
) -> None:
    """Test installing a specific firmware version."""
    # Setup config entry for PRO device
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN PRO Device",
        data={
            "mdns": "http://wican_pro.local:80",
            "webhook_id": "test_webhook_id_pro",
            "fw_version": "4.46p",
            "hw_version": "WiCAN-PRO",
            "device_id": "test_device_pro",
            "host": "wican_pro.local",
            "ip": "192.168.1.101",
        },
        options={"post_interval": 1000},
        unique_id="wican_pro-192.168.1.101:80",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.wican._async_register_webhook_on_device",
            return_value=True,
        ),
        patch(
            "custom_components.wican.github_releases.async_get_clientsession",
        ) as mock_gh_session,
        patch(
            "custom_components.wican.update.async_get_clientsession",
        ) as mock_update_session,
    ):
        # Mock GitHub API response with latest release (4.45p)
        latest_release = mock_github_releases_list[0]
        mock_gh_response = AsyncMock()
        mock_gh_response.status = 200
        mock_gh_response.json = AsyncMock(return_value=[latest_release])
        mock_gh_response.raise_for_status = MagicMock()
        mock_gh_session.return_value.get = AsyncMock(return_value=mock_gh_response)

        # Setup integration
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Mock firmware download for specific version (4.44p)
        mock_firmware_data = b"fake_firmware_data_v444"
        mock_download_response = AsyncMock()
        mock_download_response.read.return_value = mock_firmware_data
        mock_download_response.raise_for_status = MagicMock()

        # Mock firmware upload
        mock_upload_response = AsyncMock()
        mock_upload_response.raise_for_status = MagicMock()

        # Mock GitHub API call for fetching specific version
        mock_specific_version_response = AsyncMock()
        mock_specific_version_response.status = 200
        mock_specific_version_response.json = AsyncMock(return_value=mock_github_releases_list)
        mock_specific_version_response.raise_for_status = MagicMock()

        # Setup mock to return different responses
        async def get_side_effect(url, **kwargs):
            if "api.github.com" in url and "releases" in url:
                # Return list of all releases for specific version lookup
                return mock_specific_version_response
            # Return firmware download
            return mock_download_response

        mock_update_session.return_value.get = AsyncMock(side_effect=get_side_effect)
        mock_update_session.return_value.post = AsyncMock(return_value=mock_upload_response)

        # Install specific version 4.44 (older than latest 4.45)
        await hass.services.async_call(
            UPDATE_DOMAIN,
            SERVICE_INSTALL,
            {
                ATTR_ENTITY_ID: "update.wican_pro_device_firmware",
                ATTR_VERSION: "4.44",  # Specific older version
            },
            blocking=True,
        )

        # Verify GitHub API was called to fetch releases list
        get_calls = mock_update_session.return_value.get.call_args_list
        assert any("api.github.com" in str(call) for call in get_calls), (
            "Should have fetched releases from GitHub API"
        )

        # Verify correct firmware was downloaded (v4.44p asset)
        download_calls = [call for call in get_calls if "api.github.com" not in str(call)]
        assert len(download_calls) > 0, "Should have downloaded firmware"
        download_url = str(download_calls[0][0][0])
        assert "v444p" in download_url or "4.44" in download_url, \
            f"Should download v4.44 firmware, got: {download_url}"


async def test_install_latest_version_uses_cache(
    hass: HomeAssistant,
    mock_github_releases_list: list[dict],
) -> None:
    """Test that installing latest version uses cached coordinator data."""
    # Setup config entry for PRO device
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WiCAN PRO Device",
        data={
            "mdns": "http://wican_pro.local:80",
            "webhook_id": "test_webhook_id_pro",
            "fw_version": "4.44p",
            "hw_version": "WiCAN-PRO",
            "device_id": "test_device_pro",
            "host": "wican_pro.local",
            "ip": "192.168.1.101",
        },
        options={"post_interval": 1000},
        unique_id="wican_pro-192.168.1.101:80",
    )
    config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.wican._async_register_webhook_on_device",
            return_value=True,
        ),
        patch(
            "custom_components.wican.github_releases.async_get_clientsession",
        ) as mock_gh_session,
        patch(
            "custom_components.wican.update.async_get_clientsession",
        ) as mock_update_session,
    ):
        # Mock GitHub API response with latest release (4.45p)
        latest_release = mock_github_releases_list[0]
        mock_gh_response = AsyncMock()
        mock_gh_response.status = 200
        mock_gh_response.json = AsyncMock(return_value=[latest_release])
        mock_gh_response.raise_for_status = MagicMock()
        mock_gh_session.return_value.get = AsyncMock(return_value=mock_gh_response)

        # Setup integration
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Mock firmware download
        mock_firmware_data = b"fake_firmware_data_v445"
        mock_download_response = AsyncMock()
        mock_download_response.read.return_value = mock_firmware_data
        mock_download_response.raise_for_status = MagicMock()

        # Mock firmware upload
        mock_upload_response = AsyncMock()
        mock_upload_response.raise_for_status = MagicMock()

        mock_update_session.return_value.get = AsyncMock(return_value=mock_download_response)
        mock_update_session.return_value.post = AsyncMock(return_value=mock_upload_response)

        # Install latest version (no version specified)
        await hass.services.async_call(
            UPDATE_DOMAIN,
            SERVICE_INSTALL,
            {
                ATTR_ENTITY_ID: "update.wican_pro_device_firmware",
                # No version specified = latest
            },
            blocking=True,
        )

        # Verify GitHub API was NOT called for releases list
        # (should use cached coordinator data)
        get_calls = mock_update_session.return_value.get.call_args_list
        api_calls = [call for call in get_calls if "api.github.com" in str(call)]
        assert len(api_calls) == 0, (
            "Should NOT fetch releases from GitHub API when installing latest (use cache)"
        )

        # Verify firmware was downloaded
        download_calls = [call for call in get_calls if "api.github.com" not in str(call)]
        assert len(download_calls) > 0, "Should have downloaded firmware"
