"""Test version normalization logic."""
import pytest


def normalize_version(version: str | None) -> str | None:
    """Normalize version string by removing device-specific suffixes."""
    if not version:
        return version
    return version.rstrip("pu")


@pytest.mark.parametrize(
    "input_version,expected",
    [
        # PRO versions with 'p' suffix
        ("4.45p", "4.45"),
        ("4.46p", "4.46"),
        ("v4.45p", "v4.45"),  # With 'v' prefix
        
        # USB versions with 'u' suffix
        ("4.13u", "4.13"),
        ("4.14u", "4.14"),
        ("v4.13u", "v4.13"),  # With 'v' prefix
        
        # Standard versions (no suffix)
        ("4.46", "4.46"),
        ("4.13", "4.13"),
        ("v4.13", "v4.13"),
        
        # Edge cases
        ("", ""),
        (None, None),
        
        # Multiple trailing suffixes (strip all)
        ("4.45pu", "4.45"),
        ("4.45up", "4.45"),
    ],
)
def test_normalize_version(input_version, expected):
    """Test version normalization removes device-specific suffixes."""
    assert normalize_version(input_version) == expected


def test_version_comparison_after_normalization():
    """Test that normalized versions compare correctly."""
    # Device reports "4.46", GitHub has "4.45p"
    installed = normalize_version("4.46")
    latest = normalize_version("4.45p")
    
    assert installed == "4.46"
    assert latest == "4.45"
    assert installed > latest  # 4.46 is newer than 4.45
    
    # Device reports "4.45", GitHub has "4.45p" (same version)
    installed = normalize_version("4.45")
    latest = normalize_version("4.45p")
    
    assert installed == "4.45"
    assert latest == "4.45"
    assert installed == latest  # Same version, no update needed
    
    # Device reports "4.44", GitHub has "4.45p" (update available)
    installed = normalize_version("4.44")
    latest = normalize_version("4.45p")
    
    assert installed == "4.44"
    assert latest == "4.45"
    assert installed < latest  # Update available


def test_usb_version_normalization():
    """Test USB device version normalization."""
    # Device reports "4.13", GitHub has "4.13u"
    installed = normalize_version("4.13")
    latest = normalize_version("4.13u")
    
    assert installed == "4.13"
    assert latest == "4.13"
    assert installed == latest  # Same version
