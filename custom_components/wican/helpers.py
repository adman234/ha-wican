"""Helper functions and decorators for WiCAN integration."""

from __future__ import annotations

from functools import wraps
import logging
from typing import TYPE_CHECKING, Any, Concatenate, TypeVar

from homeassistant.components import webhook
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import NoURLAvailableError, get_url
from yarl import URL

from .const import DOMAIN
from .exceptions import WiCANConnectionError, WiCANError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from homeassistant.core import HomeAssistant

    from .entity import WiCANEntity

_LOGGER = logging.getLogger(__name__)

_WiCANEntityT = TypeVar("_WiCANEntityT", bound="WiCANEntity")
_P = TypeVar("_P")


def build_webhook_url(base_url: str, webhook_id: str) -> str:
    """Build an absolute webhook URL from a base URL and webhook id."""
    return str(URL(base_url) / webhook.async_generate_path(webhook_id).lstrip("/"))


def resolve_webhook_url(
    hass: HomeAssistant,
    webhook_id: str,
    *,
    fallback_url: str | None = None,
    require_current_request: bool = False,
) -> str:
    """Resolve the best available absolute webhook URL.

    Prefer Home Assistant's normal URL resolution with IPs allowed and internal
    addresses favored, then optionally fall back to the active request host.
    Finally, reuse a previously stored webhook URL if one exists.
    """
    try:
        return webhook.async_generate_url(
            hass,
            webhook_id,
            allow_ip=True,
            prefer_external=False,
        )
    except NoURLAvailableError as original_error:
        if require_current_request:
            try:
                current_request_base = get_url(
                    hass,
                    require_current_request=True,
                    allow_cloud=False,
                    allow_ip=True,
                    prefer_external=False,
                )
                return build_webhook_url(current_request_base, webhook_id)
            except NoURLAvailableError:
                pass

        if fallback_url:
            return fallback_url

        raise original_error


def wican_exception_handler[WiCANEntityT: "WiCANEntity"](
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
            _LOGGER.exception("Connection error in %s", func.__name__)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="connection_error",
                translation_placeholders={"error": str(error)},
            ) from error
        except WiCANError as error:
            # Generic WiCAN errors
            _LOGGER.exception("WiCAN error in %s", func.__name__)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="wican_error",
                translation_placeholders={"error": str(error)},
            ) from error
        except Exception:
            # Unexpected errors - log and re-raise
            _LOGGER.exception("Unexpected error in %s", func.__name__)
            raise

    return handler
