"""
Configuration & Settings Unit Test Suite

Verifies:
1. Valid environment variable type parsing (str, int, float, bool, list).
2. Malformed input error handling (e.g. invalid floats like '10.010.0' or invalid ints).
3. Boolean parsing variations (true/false, 1/0, yes/no).
"""

import os
import pytest
from tripmate.config.settings import (
    Settings,
    _parse_str,
    _parse_int,
    _parse_float,
    _parse_bool,
    _parse_list,
)


def test_parse_helpers_valid():
    """Tests valid parsing helper behavior."""
    os.environ["TEST_STR"] = " hello "
    os.environ["TEST_INT"] = " 42 "
    os.environ["TEST_FLOAT"] = " 10.5 "
    os.environ["TEST_BOOL_TRUE"] = "yes"
    os.environ["TEST_BOOL_FALSE"] = "0"
    os.environ["TEST_LIST"] = " a , b , c "

    assert _parse_str("TEST_STR") == "hello"
    assert _parse_int("TEST_INT", 0) == 42
    assert _parse_float("TEST_FLOAT", 0.0) == 10.5
    assert _parse_bool("TEST_BOOL_TRUE", False) is True
    assert _parse_bool("TEST_BOOL_FALSE", True) is False
    assert _parse_list("TEST_LIST", []) == ["a", "b", "c"]


def test_parse_helpers_malformed_float():
    """Tests that malformed float values (such as '10.010.0') raise descriptive ValueError."""
    os.environ["TEST_MALFORMED_FLOAT"] = "10.010.0"
    with pytest.raises(ValueError) as exc_info:
        _parse_float("TEST_MALFORMED_FLOAT", 10.0)

    assert "Invalid configuration for 'TEST_MALFORMED_FLOAT'" in str(exc_info.value)
    assert "10.010.0" in str(exc_info.value)


def test_parse_helpers_malformed_int():
    """Tests that malformed integer values raise descriptive ValueError."""
    os.environ["TEST_MALFORMED_INT"] = "abc42"
    with pytest.raises(ValueError) as exc_info:
        _parse_int("TEST_MALFORMED_INT", 10)

    assert "Invalid configuration for 'TEST_MALFORMED_INT'" in str(exc_info.value)


def test_parse_helpers_malformed_bool():
    """Tests that malformed boolean values raise descriptive ValueError."""
    os.environ["TEST_MALFORMED_BOOL"] = "maybe"
    with pytest.raises(ValueError) as exc_info:
        _parse_bool("TEST_MALFORMED_BOOL", False)

    assert "Invalid configuration for 'TEST_MALFORMED_BOOL'" in str(exc_info.value)


def test_settings_initialization_defaults():
    """Tests that Settings initializes cleanly with safe defaults."""
    # Ensure invalid env vars are removed for default initialization
    os.environ.pop("TEST_MALFORMED_FLOAT", None)
    os.environ.pop("TEST_MALFORMED_INT", None)
    os.environ.pop("TEST_MALFORMED_BOOL", None)

    s = Settings()
    assert s.APP_NAME == "TripMate AI Multi-Agent Backend Engine"
    assert isinstance(s.EXTERNAL_API_TIMEOUT_SECONDS, float)
    assert isinstance(s.RATE_LIMIT_REQUESTS, int)
