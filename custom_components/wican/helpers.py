"""Helper functions and decorators for WiCAN integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import wraps
import logging
from typing import Any, Concatenate, TypeVar

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .exceptions import WiCANConnectionError, WiCANError

_LOGGER = logging.getLogger(__name__)

_WiCANEntityT = TypeVar("_WiCANEntityT", bound="WiCANEntity")
_P = TypeVar("_P")


def wican_exception_handler(
    func: Callable[Concatenate[_WiCANEntityT, ...], Coroutine[Any, Any, Any]],
) -> Callable[Concatenate[_WiCANEntityT, ...], Coroutine[Any, Any, None]]:
    """Decorate WiCAN calls to handle exceptions consistently.

    This decorator provides centralized error handling for entity methods,
    converting WiCAN-specific exceptions into HomeAssistant exceptions with
    proper translation support.

    Usage:
        @wican_exception_handler
        async def async_turn_on(self, **kwargs) -> None:
            # Implementation that may raise WiCANError
    """

    @wraps(func)
    async def handler(self: _WiCANEntityT, *args: Any, **kwargs: Any) -> None:
        """Handle exceptions from WiCAN operations."""
        try:
            await func(self, *args, **kwargs)
            # Update coordinator listeners after successful operation
            if hasattr(self, "coordinator"):
                self.coordinator.async_update_listeners()
        except WiCANConnectionError as error:
            # Connection errors - mark coordinator as failed
            if hasattr(self, "coordinator"):
                self.coordinator.last_update_success = False
                self.coordinator.async_update_listeners()
            _LOGGER.error("Connection error in %s: %s", func.__name__, error)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="connection_error",
                translation_placeholders={"error": str(error)},
            ) from error
        except WiCANError as error:
            # Generic WiCAN errors
            _LOGGER.error("WiCAN error in %s: %s", func.__name__, error)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="wican_error",
                translation_placeholders={"error": str(error)},
            ) from error
        except Exception as error:
            # Unexpected errors - log and re-raise
            _LOGGER.exception("Unexpected error in %s", func.__name__)
            raise

    return handler
