"""Tests for WiCAN exception classes."""

from __future__ import annotations

import pytest

from custom_components.wican.exceptions import (
    WiCANConnectionError,
    WiCANDataError,
    WiCANDeviceNotFoundError,
    WiCANError,
    WiCANWebhookError,
)


def test_wican_error_base_exception():
    """Test WiCANError base exception."""
    error = WiCANError("Base error message")
    assert str(error) == "Base error message"
    assert isinstance(error, Exception)


def test_wican_error_inheritance():
    """Test WiCANError can be caught as Exception."""
    with pytest.raises(Exception) as exc_info:
        raise WiCANError("Test error")
    
    assert "Test error" in str(exc_info.value)


def test_wican_connection_error():
    """Test WiCANConnectionError for connection failures."""
    error = WiCANConnectionError("Failed to connect to device")
    assert str(error) == "Failed to connect to device"
    assert isinstance(error, WiCANError)
    assert isinstance(error, Exception)


def test_wican_connection_error_inheritance():
    """Test WiCANConnectionError can be caught as WiCANError."""
    with pytest.raises(WiCANError) as exc_info:
        raise WiCANConnectionError("Connection timeout")
    
    assert isinstance(exc_info.value, WiCANConnectionError)
    assert "Connection timeout" in str(exc_info.value)


def test_wican_device_not_found_error():
    """Test WiCANDeviceNotFoundError for device discovery failures."""
    error = WiCANDeviceNotFoundError("Device not found on network")
    assert str(error) == "Device not found on network"
    assert isinstance(error, WiCANError)
    assert isinstance(error, Exception)


def test_wican_device_not_found_error_inheritance():
    """Test WiCANDeviceNotFoundError can be caught as WiCANError."""
    with pytest.raises(WiCANError) as exc_info:
        raise WiCANDeviceNotFoundError("Device unreachable")
    
    assert isinstance(exc_info.value, WiCANDeviceNotFoundError)
    assert "Device unreachable" in str(exc_info.value)


def test_wican_webhook_error():
    """Test WiCANWebhookError for webhook-related issues."""
    error = WiCANWebhookError("Webhook registration failed")
    assert str(error) == "Webhook registration failed"
    assert isinstance(error, WiCANError)
    assert isinstance(error, Exception)


def test_wican_webhook_error_inheritance():
    """Test WiCANWebhookError can be caught as WiCANError."""
    with pytest.raises(WiCANError) as exc_info:
        raise WiCANWebhookError("Invalid webhook payload")
    
    assert isinstance(exc_info.value, WiCANWebhookError)
    assert "Invalid webhook payload" in str(exc_info.value)


def test_wican_data_error():
    """Test WiCANDataError for data validation failures."""
    error = WiCANDataError("Invalid data format")
    assert str(error) == "Invalid data format"
    assert isinstance(error, WiCANError)
    assert isinstance(error, Exception)


def test_wican_data_error_inheritance():
    """Test WiCANDataError can be caught as WiCANError."""
    with pytest.raises(WiCANError) as exc_info:
        raise WiCANDataError("Malformed JSON")
    
    assert isinstance(exc_info.value, WiCANDataError)
    assert "Malformed JSON" in str(exc_info.value)


def test_exception_hierarchy():
    """Test exception hierarchy allows catching by base class."""
    exceptions = [
        WiCANConnectionError("Connection error"),
        WiCANDeviceNotFoundError("Device not found"),
        WiCANWebhookError("Webhook error"),
        WiCANDataError("Data error"),
    ]
    
    for exc in exceptions:
        # All specific exceptions should be catchable as WiCANError
        assert isinstance(exc, WiCANError)
        # All should ultimately be Exception
        assert isinstance(exc, Exception)


def test_exception_with_empty_message():
    """Test exceptions can be raised with no message."""
    error = WiCANError()
    assert str(error) == ""
    
    # Should still be catchable
    with pytest.raises(WiCANError):
        raise WiCANError()


def test_exception_with_args():
    """Test exceptions support multiple arguments."""
    error = WiCANConnectionError("Connection failed", "192.168.1.100", 80)
    assert error.args == ("Connection failed", "192.168.1.100", 80)


def test_multiple_exceptions_catchable():
    """Test catching multiple exception types."""
    # Test that we can catch either specific or base exception
    with pytest.raises((WiCANConnectionError, WiCANDeviceNotFoundError)):
        raise WiCANConnectionError("Test")
    
    with pytest.raises((WiCANConnectionError, WiCANDeviceNotFoundError)):
        raise WiCANDeviceNotFoundError("Test")


def test_exception_repr():
    """Test exception representations."""
    error = WiCANError("Test error")
    # Exception repr typically shows the class and message
    repr_str = repr(error)
    assert "WiCANError" in repr_str or "Test error" in repr_str


def test_reraise_preserves_traceback():
    """Test that re-raising exceptions preserves context."""
    try:
        try:
            raise ValueError("Original error")
        except ValueError as err:
            raise WiCANDataError("Wrapped error") from err
    except WiCANDataError as exc:
        assert exc.__cause__ is not None
        assert isinstance(exc.__cause__, ValueError)
        assert str(exc.__cause__) == "Original error"


def test_exception_equality():
    """Test exception instances with same message are not equal."""
    error1 = WiCANError("Same message")
    error2 = WiCANError("Same message")
    # Exception instances are compared by identity, not value
    assert error1 is not error2
    assert str(error1) == str(error2)


def test_all_exceptions_exported():
    """Test that all exception classes are properly defined."""
    # Verify all expected exceptions exist and are classes
    assert isinstance(WiCANError, type)
    assert isinstance(WiCANConnectionError, type)
    assert isinstance(WiCANDeviceNotFoundError, type)
    assert isinstance(WiCANWebhookError, type)
    assert isinstance(WiCANDataError, type)
    
    # Verify they're all Exception subclasses
    assert issubclass(WiCANError, Exception)
    assert issubclass(WiCANConnectionError, WiCANError)
    assert issubclass(WiCANDeviceNotFoundError, WiCANError)
    assert issubclass(WiCANWebhookError, WiCANError)
    assert issubclass(WiCANDataError, WiCANError)
