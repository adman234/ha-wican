"""Test the WiCAN GitHub releases coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiohttp import ClientError, ClientResponseError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.wican.github_releases import GitHubReleasesCoordinator


@pytest.fixture
def mock_github_releases():
    """Return mock GitHub releases data (standard WiCAN)."""
    return [
        {
            "tag_name": "v4.45",
            "name": "WiCAN Firmware v4.45",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.45",
            "body": "Latest stable release with bug fixes",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v4.44",
            "name": "WiCAN Firmware v4.44",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.44",
            "body": "Previous stable release",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v4.46-beta",
            "name": "WiCAN Firmware v4.46-beta",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.46-beta",
            "body": "Beta release - do not use in production",
            "prerelease": True,
            "draft": False,
        },
    ]


@pytest.fixture
def mock_github_releases_mixed():
    """Return mock GitHub releases with both standard and PRO releases."""
    return [
        {
            "tag_name": "v4.45P",
            "name": "WiCAN PRO Firmware v4.45",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.45P",
            "body": "Latest PRO release",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v4.45",
            "name": "WiCAN Firmware v4.45",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.45",
            "body": "Latest standard release",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v4.44P",
            "name": "WiCAN PRO Firmware v4.44",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.44P",
            "body": "Previous PRO release",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "v4.44",
            "name": "WiCAN Firmware v4.44",
            "html_url": "https://github.com/meatpiHQ/wican-fw/releases/tag/v4.44",
            "body": "Previous standard release",
            "prerelease": False,
            "draft": False,
        },
    ]


async def test_github_coordinator_initialization(hass: HomeAssistant) -> None:
    """Test GitHub releases coordinator initialization."""
    coordinator = GitHubReleasesCoordinator(hass, is_pro=False)

    assert coordinator is not None
    assert coordinator.name == "WiCAN GitHub Releases"
    assert coordinator.update_interval.total_seconds() == 3600  # 1 hour
    assert coordinator._is_pro is False

    # Test PRO initialization
    pro_coordinator = GitHubReleasesCoordinator(hass, is_pro=True)
    assert pro_coordinator._is_pro is True


async def test_fetch_latest_stable_release(
    hass: HomeAssistant, mock_github_releases: list
) -> None:
    """Test fetching latest stable release."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_github_releases)
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should get the latest stable release (v4.45), not the beta
        assert coordinator.data is not None
        assert coordinator.data.get("tag_name") == "v4.45"
        assert coordinator.data.get("prerelease") is False


async def test_fetch_filters_prereleases(
    hass: HomeAssistant, mock_github_releases: list
) -> None:
    """Test that prereleases are filtered out."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_github_releases
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Verify prerelease was filtered
        assert coordinator.data.get("tag_name") != "v4.46-beta"
        assert coordinator.data.get("prerelease") is False


async def test_fetch_no_stable_releases(hass: HomeAssistant) -> None:
    """Test when no stable releases are available."""
    coordinator = GitHubReleasesCoordinator(hass)

    prerelease_only = [
        {
            "tag_name": "v5.0-alpha",
            "name": "WiCAN Firmware v5.0-alpha",
            "prerelease": True,
        }
    ]

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response with only prereleases
        mock_response = AsyncMock()
        mock_response.json.return_value = prerelease_only
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should return empty dict when no stable releases found
        assert coordinator.data == {}


async def test_fetch_github_api_timeout(hass: HomeAssistant) -> None:
    """Test handling of GitHub API timeout."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock timeout
        mock_session.return_value.get.side_effect = TimeoutError("Request timed out")

        await coordinator.async_refresh()
        
        # Should handle timeout gracefully
        assert coordinator.last_update_success is False
        assert coordinator.data is None


async def test_fetch_github_api_client_error(hass: HomeAssistant) -> None:
    """Test handling of GitHub API client error."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock client error
        mock_get = AsyncMock(side_effect=ClientError("Network error"))
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()
        
        # Should handle error gracefully
        assert coordinator.last_update_success is False
        assert coordinator.data is None


async def test_fetch_github_api_invalid_json(hass: HomeAssistant) -> None:
    """Test handling of invalid JSON response."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock invalid JSON response
        mock_response = AsyncMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()
        
        # Should handle error gracefully
        assert coordinator.last_update_success is False
        assert coordinator.data is None


async def test_fetch_github_api_rate_limit(hass: HomeAssistant) -> None:
    """Test handling of GitHub API rate limit."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock rate limit (403 Forbidden)
        mock_response = AsyncMock()
        # raise_for_status is synchronous, use MagicMock not AsyncMock
        mock_response.raise_for_status = MagicMock(side_effect=ClientResponseError(
            request_info=MagicMock(), history=(), status=403, message="Rate limit exceeded"
        ))
        mock_response.json = AsyncMock(return_value=[])
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()
        
        # Should handle error gracefully
        assert coordinator.last_update_success is False
        assert coordinator.data is None


async def test_fetch_github_api_404(hass: HomeAssistant) -> None:
    """Test handling of GitHub API 404 error."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock 404 Not Found
        mock_response = AsyncMock()
        # raise_for_status is synchronous, use MagicMock not AsyncMock  
        mock_response.raise_for_status = MagicMock(side_effect=ClientResponseError(
            request_info=MagicMock(), history=(), status=404, message="Not found"
        ))
        mock_response.json = AsyncMock(return_value=[])
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()
        
        # Should handle error gracefully
        assert coordinator.last_update_success is False
        assert coordinator.data is None


async def test_github_api_url_format(hass: HomeAssistant) -> None:
    """Test that correct GitHub API URL is used."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response
        mock_response = AsyncMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Verify correct API URL was called
        mock_session.return_value.get.assert_called_once()
        call_args = mock_session.return_value.get.call_args
        url = call_args[0][0]
        assert url == "https://api.github.com/repos/meatpiHQ/wican-fw/releases"

        # Verify correct headers
        headers = call_args[1]["headers"]
        assert headers["Accept"] == "application/vnd.github.v3+json"


async def test_coordinator_update_interval(hass: HomeAssistant) -> None:
    """Test coordinator update interval is set correctly."""
    coordinator = GitHubReleasesCoordinator(hass)

    # Should update once per hour
    assert coordinator.update_interval.total_seconds() == 3600


async def test_coordinator_caches_data(
    hass: HomeAssistant, mock_github_releases: list
) -> None:
    """Test coordinator caches fetched data."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_github_releases
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        # First fetch
        await coordinator.async_refresh()
        first_data = coordinator.data

        # Data should be cached
        assert first_data is not None
        assert first_data.get("tag_name") == "v4.45"

        # Second access should use cached data
        assert coordinator.data == first_data


async def test_release_data_structure(
    hass: HomeAssistant, mock_github_releases: list
) -> None:
    """Test that release data structure is preserved."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_github_releases
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Verify all expected fields are present
        assert coordinator.data.get("tag_name") is not None
        assert coordinator.data.get("name") is not None
        assert coordinator.data.get("html_url") is not None
        assert coordinator.data.get("body") is not None
        assert "prerelease" in coordinator.data


async def test_empty_releases_list(hass: HomeAssistant) -> None:
    """Test handling of empty releases list."""
    coordinator = GitHubReleasesCoordinator(hass)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response with empty list
        mock_response = AsyncMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should return empty dict
        assert coordinator.data == {}


async def test_fetch_pro_releases_only(
    hass: HomeAssistant, mock_github_releases_mixed: list
) -> None:
    """Test that PRO coordinator only fetches PRO releases."""
    coordinator = GitHubReleasesCoordinator(hass, is_pro=True)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response with mixed releases
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_github_releases_mixed)
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should get the latest PRO release (v4.45P)
        assert coordinator.data is not None
        assert coordinator.data.get("tag_name") == "v4.45P"
        assert "PRO" in coordinator.data.get("name", "")


async def test_fetch_standard_releases_only(
    hass: HomeAssistant, mock_github_releases_mixed: list
) -> None:
    """Test that standard coordinator only fetches standard releases."""
    coordinator = GitHubReleasesCoordinator(hass, is_pro=False)

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response with mixed releases
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_github_releases_mixed)
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should get the latest standard release (v4.45)
        assert coordinator.data is not None
        assert coordinator.data.get("tag_name") == "v4.45"
        assert "PRO" not in coordinator.data.get("name", "")


async def test_fetch_no_matching_device_type(hass: HomeAssistant) -> None:
    """Test when no releases match device type."""
    # PRO coordinator with only standard releases
    coordinator = GitHubReleasesCoordinator(hass, is_pro=True)

    standard_only_releases = [
        {
            "tag_name": "v4.45",
            "name": "WiCAN Firmware v4.45",
            "prerelease": False,
        },
    ]

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response with standard releases only
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=standard_only_releases)
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should return empty dict when no matching releases
        assert coordinator.data == {}


async def test_pro_detection_case_insensitive(hass: HomeAssistant) -> None:
    """Test that PRO detection is case-insensitive."""
    coordinator = GitHubReleasesCoordinator(hass, is_pro=True)

    # Test various PRO naming conventions
    releases_with_various_pro_names = [
        {
            "tag_name": "v4.45p",  # Lowercase P in tag
            "name": "WiCAN pro Firmware v4.45",  # Lowercase PRO in name
            "prerelease": False,
        },
        {
            "tag_name": "v4.44P",  # Uppercase P
            "name": "WiCAN PRO Firmware v4.44",  # Uppercase PRO
            "prerelease": False,
        },
    ]

    with patch(
        "custom_components.wican.github_releases.async_get_clientsession"
    ) as mock_session:
        # Mock GitHub API response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=releases_with_various_pro_names)
        mock_response.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_session.return_value.get = mock_get

        await coordinator.async_refresh()

        # Should match any PRO variant
        assert coordinator.data is not None
        # Should get first (latest) PRO release
        assert "4.45" in coordinator.data.get("tag_name", "")
