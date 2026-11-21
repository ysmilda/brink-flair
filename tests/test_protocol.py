"""Tests for the Home Assistant independent protocol module."""

from custom_components.brink_flair.flair.device import _bcd, _signed, _temperature, _u32


def test_decoding() -> None:
    """Register values decode as Brink documents them."""
    assert _signed(0xFF9C) == -100
    assert _signed(215) == 215
    assert _bcd(0x4290) == "4290"
    assert _u32(1, 2) == 65538


def test_temperature_not_fitted() -> None:
    """A sensor that is not fitted reads 9999 and decodes as None."""
    assert _temperature(9999) is None
    assert _temperature(125) == 12.5
    assert _temperature(0xFFE2) == -3.0
