"""Exceptions for WiCAN integration."""

from __future__ import annotations


class WiCANError(Exception):
    """Base exception for WiCAN integration."""


class WiCANConnectionError(WiCANError):
    """Exception raised when connection to device fails."""


class WiCANDeviceNotFoundError(WiCANError):
    """Exception raised when device is not reachable."""


class WiCANWebhookError(WiCANError):
    """Exception raised for webhook-related errors."""


class WiCANDataError(WiCANError):
    """Exception raised when data from device is invalid or malformed."""
