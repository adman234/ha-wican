"""Test exception handler decorator."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import NoURLAvailableError

from custom_components.wican.exceptions import WiCANConnectionError, WiCANError
from custom_components.wican.helpers import resolve_device_webhook_urls, wican_exception_handler


class MockEntity:
    """Mock WiCAN entity for testing decorator."""

    def __init__(self):
        """Initialize mock entity."""
        self.coordinator = Mock()
        self.coordinator.last_update_success = True
        self.coordinator.async_update_listeners = Mock()


async def test_decorator_success_updates_coordinator():
    """Test decorator updates coordinator on success."""
    entity = MockEntity()

    @wican_exception_handler
    async def test_func(self):
        """Test function that succeeds."""
        return "success"

    result = await test_func(entity)
    
    # Should update listeners after success
    assert entity.coordinator.async_update_listeners.called


async def test_decorator_connection_error():
    """Test decorator handles WiCANConnectionError."""
    entity = MockEntity()

    @wican_exception_handler
    async def test_func(self):
        """Test function that raises connection error."""
        raise WiCANConnectionError("Device unreachable")

    with pytest.raises(HomeAssistantError) as exc_info:
        await test_func(entity)
    
    # Should mark coordinator as failed
    assert entity.coordinator.last_update_success is False
    assert entity.coordinator.async_update_listeners.called
    
    # Should convert to HomeAssistantError with translation key
    assert exc_info.value.translation_key == "connection_error"


async def test_decorator_wican_error():
    """Test decorator handles generic WiCANError."""
    entity = MockEntity()

    @wican_exception_handler
    async def test_func(self):
        """Test function that raises WiCAN error."""
        raise WiCANError("Invalid response")

    with pytest.raises(HomeAssistantError) as exc_info:
        await test_func(entity)
    
    # Should not mark coordinator as failed for generic errors
    assert entity.coordinator.last_update_success is True
    
    # Should convert to HomeAssistantError with translation key
    assert exc_info.value.translation_key == "wican_error"


async def test_decorator_unexpected_error():
    """Test decorator re-raises unexpected errors."""
    entity = MockEntity()

    @wican_exception_handler
    async def test_func(self):
        """Test function that raises unexpected error."""
        raise ValueError("Unexpected issue")

    with pytest.raises(ValueError) as exc_info:
        await test_func(entity)
    
    # Should re-raise the original exception
    assert "Unexpected issue" in str(exc_info.value)


async def test_decorator_without_coordinator():
    """Test decorator works with entities that have no coordinator."""
    entity_no_coordinator = Mock()
    # Explicitly remove coordinator attribute
    del entity_no_coordinator.coordinator

    @wican_exception_handler
    async def test_func(self):
        """Test function that succeeds."""
        return "success"

    # Should not crash when coordinator is missing
    result = await test_func(entity_no_coordinator)


async def test_decorator_connection_error_without_coordinator():
    """Test decorator handles connection error without coordinator."""
    entity_no_coordinator = Mock()
    del entity_no_coordinator.coordinator

    @wican_exception_handler
    async def test_func(self):
        """Test function that raises connection error."""
        raise WiCANConnectionError("Device unreachable")

    with pytest.raises(HomeAssistantError):
        await test_func(entity_no_coordinator)
    
    # Should not crash even without coordinator


async def test_decorator_preserves_function_metadata():
    """Test decorator preserves original function metadata."""
    entity = MockEntity()

    @wican_exception_handler
    async def test_func_with_docs(self):
        """This is a test function with documentation."""
        return "result"

    # Decorator should preserve function name and docstring
    assert test_func_with_docs.__name__ == "test_func_with_docs"
    assert "test function with documentation" in test_func_with_docs.__doc__


async def test_decorator_with_function_arguments():
    """Test decorator works with functions that take arguments."""
    entity = MockEntity()

    @wican_exception_handler
    async def test_func_with_args(self, arg1, arg2, kwarg1=None):
        """Test function with arguments."""
        return f"{arg1}-{arg2}-{kwarg1}"

    result = await test_func_with_args(entity, "a", "b", kwarg1="c")
    
    # Should not interfere with function arguments
    # (function returns None due to decorator, but shouldn't crash)
    assert entity.coordinator.async_update_listeners.called


def test_resolve_device_webhook_urls_prefers_local_http_and_external_https(
    hass: HomeAssistant,
) -> None:
    """Test devices prefer local HTTP and append external HTTPS when available."""
    with (
        patch(
            "custom_components.wican.helpers.resolve_local_webhook_url",
            return_value="http://homeassistant.local:8123/api/webhook/test",
        ),
        patch(
            "custom_components.wican.helpers.resolve_external_https_webhook_url",
            return_value="https://example.ui.nabu.casa/api/webhook/test",
        ),
    ):
        urls = resolve_device_webhook_urls(
            hass,
            "test",
            allow_external_https_fallback=True,
        )

    assert urls == [
        "http://homeassistant.local:8123/api/webhook/test",
        "https://example.ui.nabu.casa/api/webhook/test",
    ]


def test_resolve_device_webhook_urls_falls_back_to_external_https(
    hass: HomeAssistant,
) -> None:
    """Test Pro devices can fall back to external HTTPS when local HTTP is unavailable."""
    with (
        patch(
            "custom_components.wican.helpers.resolve_local_webhook_url",
            side_effect=NoURLAvailableError,
        ),
        patch(
            "custom_components.wican.helpers.resolve_external_https_webhook_url",
            return_value="https://example.ui.nabu.casa/api/webhook/test",
        ),
    ):
        urls = resolve_device_webhook_urls(
            hass,
            "test",
            allow_external_https_fallback=True,
        )

    assert urls == ["https://example.ui.nabu.casa/api/webhook/test"]


def test_resolve_device_webhook_urls_requires_local_http_without_fallback(
    hass: HomeAssistant,
) -> None:
    """Test non-Pro devices still require a local HTTP webhook URL."""
    with patch(
        "custom_components.wican.helpers.resolve_local_webhook_url",
        side_effect=NoURLAvailableError,
    ):
        with pytest.raises(NoURLAvailableError):
            resolve_device_webhook_urls(hass, "test")
