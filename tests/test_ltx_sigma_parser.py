"""Tests for LTX sigma string parsing."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ltx_video_generation import parse_sigmas


def test_parse_valid_sigmas():
    result = parse_sigmas("1.0, 0.5, 0.0")
    assert result == [1.0, 0.5, 0.0]


def test_parse_strips_whitespace():
    result = parse_sigmas("  0.85,  0.7250,0.4219, 0.0  ")
    assert result == [0.85, 0.725, 0.4219, 0.0]


def test_parse_single_value_raises():
    with pytest.raises(ValueError, match="at least 2"):
        parse_sigmas("1.0")


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_sigmas("")


def test_parse_malformed_raises():
    with pytest.raises(ValueError, match="not a valid float"):
        parse_sigmas("1.0, abc, 0.0")


def test_parse_trailing_comma_raises():
    with pytest.raises(ValueError, match="empty token"):
        parse_sigmas("1.0, 0.5, 0.0,")


def test_parse_leading_comma_raises():
    with pytest.raises(ValueError, match="empty token"):
        parse_sigmas(", 1.0, 0.5, 0.0")


def test_parse_double_comma_raises():
    with pytest.raises(ValueError, match="empty token"):
        parse_sigmas("1.0,, 0.5, 0.0")


def test_preflight_imports():
    """Smoke test: preflight_ltx, get_ltx_node_classes, REQUIRED_LTX_NODE_NAMES are importable."""
    from ltx_video_generation import preflight_ltx, get_ltx_node_classes, REQUIRED_LTX_NODE_NAMES
    assert callable(preflight_ltx)
    assert callable(get_ltx_node_classes)
    assert isinstance(REQUIRED_LTX_NODE_NAMES, list)
    assert len(REQUIRED_LTX_NODE_NAMES) >= 20  # At least all the required nodes
    assert "DiffusionModelLoaderKJ" in REQUIRED_LTX_NODE_NAMES
    assert "SamplerCustomAdvanced" in REQUIRED_LTX_NODE_NAMES
    assert "SaveVideo" in REQUIRED_LTX_NODE_NAMES
