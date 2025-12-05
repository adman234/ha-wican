"""WiCAN integration."""

from __future__ import annotations

from http import HTTPStatus
import asyncio

from aiohttp.web import Request, Response
from aiohttp import ClientError, ClientResponseError
import async_timeout
import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import get_url
from yarl import URL

from .const import (
    DOMAIN,
    CONF_POST_INTERVAL,
    DEFAULT_POST_INTERVAL,
)
from .coordinator import WiCANDataUpdateCoordinator
from .models import WiCANRuntimeData

import logging
from .exceptions import WiCANConnectionError, WiCANWebhookError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Type alias for config entry with runtime data
WiCANConfigEntry = ConfigEntry[WiCANRuntimeData]


class _WebhookEndpointsFailed(WiCANWebhookError):
    """Raised when all webhook endpoints failed for this attempt."""


def _ensure_http_scheme(value: str | None) -> str | None:
    """Return value with http:// if no scheme is provided."""
    if not value:
        return value
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}"


def _http_url_from_host(host: str | None, port: int | None = None) -> str | None:
    """Build an http URL from a bare host/ip string."""
    if not host:
        return None
    try:
        return str(URL.build(scheme="http", host=host, port=port))
    except ValueError:
        return None


def _build_webhook_endpoint(base: str | None) -> URL | None:
    """Return the device webhook endpoint URL constructed from a base URL."""
    if not base:
        return None

    candidate = base.strip()
    try:
        url = URL(candidate)
    except ValueError:
        return None

    if not url.scheme:
        try:
            url = URL(_ensure_http_scheme(candidate))
        except ValueError:
            return None

    # Drop any path/query/fragment parts before appending the webhook path
    url = url.with_path("").with_query(None).with_fragment(None)
    return url / "api" / "webhook"


def _normalize_ip(ip: str | None) -> str | None:
    """Normalize IPv4-mapped IPv6 strings into IPv4 when possible."""
    if not ip:
        return None
    if ip.startswith("::ffff:") and ip.count(":") >= 2:
        return ip.split("::ffff:", maxsplit=1)[-1]
    return ip


def _extract_request_ip(request: Request) -> str | None:
    """Best-effort extraction of the originating peer IP address."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return _normalize_ip(first)

    transport = request.transport
    if transport is not None:
        peername = transport.get_extra_info("peername")
        if isinstance(peername, (tuple, list)) and peername:
            return _normalize_ip(peername[0])

    if request.remote:
        return _normalize_ip(request.remote)

    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: WiCANConfigEntry
) -> bool:
    """Set up WiCAN from a config entry."""
    # Ensure webhook_id exists (older entries may lack it); generate if missing
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        try:
            from uuid import uuid4
            webhook_id = uuid4().hex
            new_data = dict(entry.data)
            new_data[CONF_WEBHOOK_ID] = webhook_id
            hass.config_entries.async_update_entry(entry, data=new_data)
            _LOGGER.info("Generated missing webhook_id for entry %s", entry.title)
        except Exception:
            _LOGGER.warning("Failed to generate webhook_id; setup may fail")
            return False

    # Get post interval from options
    post_interval = entry.options.get(CONF_POST_INTERVAL, DEFAULT_POST_INTERVAL)

    # Create coordinator for this entry
    coordinator = WiCANDataUpdateCoordinator(
        hass,
        entry,
    )

    # Set runtime_data with all necessary data
    entry.runtime_data = WiCANRuntimeData(
        coordinator=coordinator,
        webhook_id=webhook_id,
        post_interval=post_interval,
        device_host=entry.data.get("host"),
        device_ip=entry.data.get("ip"),
    )

    # Perform first refresh to initialize coordinator
    # For push-based WiCAN, this succeeds immediately with empty data
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "First refresh failed for %s (push-based integration will retry): %s",
            entry.title,
            err,
        )
        # Don't fail setup - entities will update when first webhook arrives

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: Request
    ) -> Response:
        """Handle incoming WiCAN webhook request."""
        _LOGGER.info("Received WiCAN webhook: %s", webhook_id)
        try:
            data = await request.json()
        except vol.MultipleInvalid as error:
            return Response(
                text=error.error_message, status=HTTPStatus.UNPROCESSABLE_ENTITY
            )

        # Extract device info fields from top-level or nested "status"
        device_info_fields = {}
        status = data.get("status", {})
        for key in ("fw_version", "hw_version", "device_id", "git_version", "mdns", "host", "ip"):
            # Check top-level first, then status
            if key in status:
                device_info_fields[key] = status[key]

        # Capture device IP from the inbound request as an authoritative source
        remote_ip = _extract_request_ip(request)
        if remote_ip:
            entry.runtime_data.device_ip = remote_ip
            device_info_fields["ip"] = remote_ip
            host_from_ip = _http_url_from_host(remote_ip)
            if host_from_ip:
                entry.runtime_data.device_host = host_from_ip
                device_info_fields["host"] = host_from_ip

        # Persist device info in config entry
        if device_info_fields:
            new_data = dict(entry.data)
            connection_field_changed = False
            data_changed = False
            for key, value in device_info_fields.items():
                if value is None:
                    continue
                if new_data.get(key) == value:
                    continue
                new_data[key] = value
                data_changed = True
                if key in {"host", "ip", "mdns"}:
                    connection_field_changed = True

            if data_changed:
                hass.config_entries.async_update_entry(entry, data=new_data)
                if connection_field_changed:
                    entry.runtime_data.device_host = new_data.get("host") or entry.runtime_data.device_host
                    entry.runtime_data.device_ip = new_data.get("ip") or entry.runtime_data.device_ip
                    # Refresh registration out-of-band so future retries use the new address
                    hass.async_create_task(
                        _async_register_webhook_on_device(hass, entry)
                    )

        # Update coordinator with new data
        try:
            coordinator.handle_webhook_data(data)
        except ConfigEntryError as err:
            # Device identity mismatch - log error and reject webhook
            _LOGGER.error(
                "Rejecting webhook due to device identity validation failure: %s",
                err,
            )
            return Response(
                text="Device identity mismatch",
                status=HTTPStatus.FORBIDDEN,
            )

        # Keep dispatcher for backward compatibility during migration
        async_dispatcher_send(hass, DOMAIN, webhook_id, data)
        return Response(status=HTTPStatus.NO_CONTENT)

    webhook.async_register(
        hass, DOMAIN, entry.title, webhook_id, handle_webhook
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _schedule_webhook_registration(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WiCANConfigEntry
) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.runtime_data.webhook_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _schedule_webhook_registration(hass: HomeAssistant, entry: WiCANConfigEntry) -> None:
    async def _register(_: object | None = None) -> None:
        await _async_register_webhook_on_device(hass, entry)

    if hass.is_running:
        hass.async_create_task(_register())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register)


async def _async_register_webhook_on_device(
    hass: HomeAssistant, entry: WiCANConfigEntry, max_retries: int = 3
) -> bool:
    """Push webhook URL and interval to the WiCAN device with retry."""
    # Prefer direct IP/host if available (similar to WLED), fallback to mDNS
    host = entry.runtime_data.device_host or entry.data.get("host")
    ip = entry.runtime_data.device_ip or entry.data.get("ip")
    mdns = entry.data.get("mdns")

    if not host and ip:
        host = _http_url_from_host(ip)
        entry.runtime_data.device_host = host

    if not host and not mdns:
        _LOGGER.debug(
            "Entry %s missing host/mdns; cannot register webhook",
            entry.entry_id,
        )
        return False

    # Normalize schemes on available addresses
    if mdns:
        normalized_mdns = _ensure_http_scheme(mdns)
        if normalized_mdns != mdns:
            updated_data = dict(entry.data)
            updated_data["mdns"] = normalized_mdns
            hass.config_entries.async_update_entry(entry, data=updated_data)
            mdns = normalized_mdns
    if host:
        normalized_host = _ensure_http_scheme(host)
        if normalized_host != host:
            updated_data = dict(entry.data)
            updated_data["host"] = normalized_host
            hass.config_entries.async_update_entry(entry, data=updated_data)
            host = normalized_host
        entry.runtime_data.device_host = host
    elif ip:
        # Ensure we persist the derived host for future reloads
        derived_host = _http_url_from_host(ip)
        if derived_host:
            updated_data = dict(entry.data)
            updated_data["host"] = derived_host
            hass.config_entries.async_update_entry(entry, data=updated_data)
            host = derived_host
            entry.runtime_data.device_host = derived_host

    try:
        base_url: str = get_url(hass)
        webhook_path = webhook.async_generate_url(hass, entry.runtime_data.webhook_id)
        if webhook_path.startswith("http"):
            webhook_url = webhook_path
        else:
            webhook_url = str(URL(base_url) / webhook_path.lstrip("/"))
    except Exception as err:
        _LOGGER.warning("Cannot generate webhook URL for %s: %s", entry.entry_id, err)
        return False

    # Get post interval from runtime_data
    post_interval = entry.runtime_data.post_interval

    _LOGGER.info(
        "Registering WiCAN webhook %s with interval %ss", webhook_url, post_interval
    )

    # Use HA's shared session (reuses connections)
    session = async_get_clientsession(hass)
    payload = {"url": webhook_url, "enabled": True, "interval": post_interval}

    # Build endpoint candidates: prefer direct host/IP over mDNS
    endpoints: list[URL] = []
    for candidate in (host, mdns):
        endpoint = _build_webhook_endpoint(candidate)
        if endpoint:
            endpoints.append(endpoint)

    if not endpoints:
        _LOGGER.debug(
            "Entry %s has no valid device endpoints after normalization",
            entry.entry_id,
        )
        return False
    _LOGGER.debug(
        "Entry %s will register webhook against endpoints: %s",
        entry.entry_id,
        ", ".join(str(ep) for ep in endpoints),
    )

    # Retry loop with exponential backoff
    for attempt in range(max_retries):
        try:
            # Add timeout protection (10 seconds)
            async with async_timeout.timeout(10):
                # Try each endpoint candidate until one succeeds
                for ep in endpoints:
                    try:
                        resp = await session.post(
                            str(ep),
                            json=payload,
                            headers={"Content-Type": "application/json"},
                        )

                        if resp.status < 300:
                            _LOGGER.info(
                                "WiCAN webhook registered successfully at %s (attempt %d/%d)",
                                ep,
                                attempt + 1,
                                max_retries,
                            )
                            return True

                        text = await resp.text()
                        _LOGGER.warning(
                            "WiCAN webhook registration failed with HTTP %d at %s: %s (attempt %d/%d)",
                            resp.status,
                            ep,
                            text,
                            attempt + 1,
                            max_retries,
                        )
                    except ClientError as err:
                        # Keep trying other endpoints if one fails to resolve/connect
                        _LOGGER.warning(
                            "WiCAN webhook registration connection error at %s: %s (attempt %d/%d)",
                            ep,
                            err,
                            attempt + 1,
                            max_retries,
                        )

                # No endpoint succeeded during this attempt
                raise _WebhookEndpointsFailed()

        except asyncio.TimeoutError:
            _LOGGER.warning(
                "WiCAN webhook registration timeout after 10s (attempt %d/%d)",
                attempt + 1,
                max_retries,
            )
        except _WebhookEndpointsFailed:
            _LOGGER.debug(
                "All WiCAN endpoints failed for entry %s on attempt %d/%d",
                entry.entry_id,
                attempt + 1,
                max_retries,
            )
        except ClientResponseError as err:
            _LOGGER.warning(
                "WiCAN webhook registration HTTP error: %s (attempt %d/%d)",
                err,
                attempt + 1,
                max_retries,
            )
        except ClientError as err:
            _LOGGER.warning(
                "WiCAN webhook registration connection error: %s (attempt %d/%d)",
                err,
                attempt + 1,
                max_retries,
            )
        except Exception as err:
            _LOGGER.error(
                "WiCAN webhook registration unexpected error: %s (attempt %d/%d)",
                err,
                attempt + 1,
                max_retries,
            )

        # Exponential backoff before retry (except on last attempt)
        if attempt < max_retries - 1:
            backoff_seconds = 2 ** attempt  # 1s, 2s, 4s
            _LOGGER.debug("Retrying in %ds...", backoff_seconds)
            await asyncio.sleep(backoff_seconds)

    # All retries failed
    _LOGGER.error(
        "Failed to register webhook after %d attempts. "
        "Device may not send updates to Home Assistant. "
        "Please check: 1) Device is powered on and connected to network, "
        "2) Home Assistant can reach device at %s, "
        "3) Device firewall allows connections on port 80",
        max_retries,
        ", ".join(str(ep) for ep in endpoints),
    )
    return False


async def _async_entry_updated(hass: HomeAssistant, entry: WiCANConfigEntry) -> None:
    """Handle config entry updates (options) by re-registering the webhook."""
    # Update post_interval in runtime_data
    new_post_interval = entry.options.get(CONF_POST_INTERVAL, DEFAULT_POST_INTERVAL)
    entry.runtime_data.post_interval = new_post_interval

    # Re-register webhook with new interval
    await _async_register_webhook_on_device(hass, entry)
