"""Data models for WiCAN integration."""

from __future__ import annotations

from dataclasses import dataclass

from .coordinator import WiCANDataUpdateCoordinator


@dataclass
class WiCANRuntimeData:
    """Runtime data for WiCAN config entry."""

    coordinator: WiCANDataUpdateCoordinator
    webhook_id: str
    post_interval: int
    device_host: str | None = None
    device_ip: str | None = None
    cached_resolved_ip: str | None = None
    cache_timestamp: float = 0.0
