"""Tests for the Home Assistant independent protocol module."""

from custom_components.brink_flair.flair.device import _bcd, _signed, _u32


def test_decoding() -> None:
    """Register values decode as Brink documents them."""
    assert _signed(0xFF9C) == -100
    assert _signed(215) == 215
    assert _bcd(0x4290) == "4290"
    assert _u32(1, 2) == 65538
