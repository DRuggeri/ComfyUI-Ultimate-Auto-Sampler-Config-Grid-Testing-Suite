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


def test_load_ltx_models_imports():
    """Smoke test: load_ltx_models is importable."""
    from ltx_video_generation import load_ltx_models
    assert callable(load_ltx_models)


def test_clear_ltx_caches_imports():
    """Smoke test: clear_ltx_caches and the 5 cache dicts are importable."""
    from model_cache import (
        clear_ltx_caches,
        ltx_diffusion_model_cache,
        ltx_dual_clip_cache,
        ltx_video_vae_cache,
        ltx_audio_vae_cache,
        ltx_latent_upscaler_cache,
        _evict_to_max,
    )
    assert callable(clear_ltx_caches)
    assert isinstance(ltx_diffusion_model_cache, dict)
    assert callable(_evict_to_max)


def test_encode_ltx_prompts_imports():
    """Smoke test: encode_ltx_prompts is importable and callable."""
    from ltx_video_generation import encode_ltx_prompts
    assert callable(encode_ltx_prompts)


def test_ltx_video_generate_imports():
    """Smoke test: ltx_video_generate is importable and callable."""
    from ltx_video_generation import ltx_video_generate
    assert callable(ltx_video_generate)
