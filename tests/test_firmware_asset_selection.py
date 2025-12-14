"""Test firmware asset selection logic."""
import pytest


def test_firmware_asset_selection_obd():
    """Test selecting OBD firmware from release assets."""
    # Simulate the logic from update.py _download_firmware
    assets = [
        {
            "name": "wican-fw_obd_v413.bin",
            "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.13/wican-fw_obd_v413.bin",
        },
        {"name": "wican-fw_obd_v413.zip", "browser_download_url": "..."},
        {
            "name": "wican-fw_usb_v413u.bin",
            "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.13/wican-fw_usb_v413u.bin",
        },
        {"name": "wican-fw_usb_v413u.zip", "browser_download_url": "..."},
    ]

    # OBD device (not PRO, not USB)
    hw_version = "WiCAN-OBD"
    is_pro = "pro" in hw_version.lower()
    is_usb = "usb" in hw_version.lower()

    firmware_asset = None
    for asset in assets:
        name = asset.get("name", "").lower()
        if not name.endswith(".bin"):
            continue

        has_pro = "pro" in name
        has_usb = "usb" in name and "pro" not in name
        has_obd = "obd" in name and "usb" not in name and "pro" not in name

        if is_pro and has_pro:
            firmware_asset = asset
            break
        elif is_usb and has_usb:
            firmware_asset = asset
            break
        elif not is_pro and not is_usb and has_obd:
            firmware_asset = asset
            break

    assert firmware_asset is not None
    assert firmware_asset["name"] == "wican-fw_obd_v413.bin"
    assert "obd" in firmware_asset["browser_download_url"]
    assert "usb" not in firmware_asset["browser_download_url"]
    assert "pro" not in firmware_asset["browser_download_url"]


def test_firmware_asset_selection_usb():
    """Test selecting USB firmware from release assets."""
    assets = [
        {
            "name": "wican-fw_obd_v413.bin",
            "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.13/wican-fw_obd_v413.bin",
        },
        {"name": "wican-fw_obd_v413.zip", "browser_download_url": "..."},
        {
            "name": "wican-fw_usb_v413u.bin",
            "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.13/wican-fw_usb_v413u.bin",
        },
        {"name": "wican-fw_usb_v413u.zip", "browser_download_url": "..."},
    ]

    # USB device
    hw_version = "WiCAN-USB"
    is_pro = "pro" in hw_version.lower()
    is_usb = "usb" in hw_version.lower()

    firmware_asset = None
    for asset in assets:
        name = asset.get("name", "").lower()
        if not name.endswith(".bin"):
            continue

        has_pro = "pro" in name
        has_usb = "usb" in name and "pro" not in name
        has_obd = "obd" in name and "usb" not in name and "pro" not in name

        if is_pro and has_pro:
            firmware_asset = asset
            break
        elif is_usb and has_usb:
            firmware_asset = asset
            break
        elif not is_pro and not is_usb and has_obd:
            firmware_asset = asset
            break

    assert firmware_asset is not None
    assert firmware_asset["name"] == "wican-fw_usb_v413u.bin"
    assert "usb" in firmware_asset["browser_download_url"]
    assert "pro" not in firmware_asset["browser_download_url"]


def test_firmware_asset_selection_pro():
    """Test selecting PRO firmware from release assets."""
    assets = [
        {
            "name": "wican-fw_obd_pro_v445p.bin",
            "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.45p/wican-fw_obd_pro_v445p.bin",
        },
        {"name": "wican-fw_obd_pro_v445p.zip", "browser_download_url": "..."},
    ]

    # PRO device
    hw_version = "WiCAN-PRO"
    is_pro = "pro" in hw_version.lower()
    is_usb = "usb" in hw_version.lower()

    firmware_asset = None
    for asset in assets:
        name = asset.get("name", "").lower()
        if not name.endswith(".bin"):
            continue

        has_pro = "pro" in name
        has_usb = "usb" in name and "pro" not in name
        has_obd = "obd" in name and "usb" not in name and "pro" not in name

        if is_pro and has_pro:
            firmware_asset = asset
            break
        elif is_usb and has_usb:
            firmware_asset = asset
            break
        elif not is_pro and not is_usb and has_obd:
            firmware_asset = asset
            break

    assert firmware_asset is not None
    assert firmware_asset["name"] == "wican-fw_obd_pro_v445p.bin"
    assert "pro" in firmware_asset["browser_download_url"]


def test_firmware_asset_selection_no_match():
    """Test when no matching firmware is found."""
    assets = [
        {
            "name": "wican-fw_obd_v413.bin",
            "browser_download_url": "https://github.com/meatpiHQ/wican-fw/releases/download/v4.13/wican-fw_obd_v413.bin",
        },
    ]

    # USB device but only OBD firmware available
    hw_version = "WiCAN-USB"
    is_pro = "pro" in hw_version.lower()
    is_usb = "usb" in hw_version.lower()

    firmware_asset = None
    for asset in assets:
        name = asset.get("name", "").lower()
        if not name.endswith(".bin"):
            continue

        has_pro = "pro" in name
        has_usb = "usb" in name and "pro" not in name
        has_obd = "obd" in name and "usb" not in name and "pro" not in name

        if is_pro and has_pro:
            firmware_asset = asset
            break
        elif is_usb and has_usb:
            firmware_asset = asset
            break
        elif not is_pro and not is_usb and has_obd:
            firmware_asset = asset
            break

    # Should not find a match
    assert firmware_asset is None
