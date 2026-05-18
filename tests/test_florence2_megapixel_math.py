"""Tests for compute_target_dims() — megapixel-based image scaling math."""
import math

import pytest

from florence2_hires import compute_target_dims


def test_square_1mp_from_square_source():
    """1024x1024 source @ 1.0 MP → 1024x1024 (already at target)."""
    w, h = compute_target_dims(1024, 1024, 1.0)
    assert w == 1024 and h == 1024


def test_square_1mp_from_small_source_upscales():
    """512x512 source @ 1.0 MP → upscale to ~1024x1024."""
    w, h = compute_target_dims(512, 512, 1.0)
    assert w == 1024 and h == 1024


def test_square_1mp_from_huge_source_downscales():
    """2048x2048 source @ 1.0 MP → downscale to ~1024x1024."""
    w, h = compute_target_dims(2048, 2048, 1.0)
    assert w == 1024 and h == 1024


def test_portrait_aspect_preserved():
    """832x1216 source @ 1.0 MP → preserves AR, dims divisible by 8."""
    w, h = compute_target_dims(832, 1216, 1.0)
    # Source area = 1,011,712 ≈ 1 MP already
    assert abs(w / h - 832 / 1216) < 0.02
    assert w % 8 == 0 and h % 8 == 0


def test_landscape_aspect_preserved():
    """1216x832 source @ 1.5 MP → preserves AR, dims divisible by 8."""
    w, h = compute_target_dims(1216, 832, 1.5)
    assert abs(w / h - 1216 / 832) < 0.02
    assert w % 8 == 0 and h % 8 == 0
    # Should be larger than source (1.5 MP > 1.0 MP)
    assert w * h > 1216 * 832 * 0.95  # within 5% rounding


def test_clamps_to_min_64():
    """Tiny target produces dims at the 64 floor, not below."""
    w, h = compute_target_dims(100, 100, 0.001)
    assert w >= 64 and h >= 64


def test_clamps_to_max_4096():
    """Huge target dims are capped at 4096."""
    w, h = compute_target_dims(512, 512, 20.0)
    assert w <= 4096 and h <= 4096


def test_divisible_by_8():
    """Output is always divisible by 8."""
    for src_w, src_h, mp in [(773, 521, 1.0), (1000, 700, 1.7), (333, 444, 0.5)]:
        w, h = compute_target_dims(src_w, src_h, mp)
        assert w % 8 == 0, f"w={w} not /8 for src=({src_w},{src_h}) mp={mp}"
        assert h % 8 == 0, f"h={h} not /8 for src=({src_w},{src_h}) mp={mp}"


def test_formula_matches_comfy_convention():
    """Uses *1024*1024 (mebipixels), matching ComfyUI's ImageScaleToTotalPixels."""
    src_w, src_h = 1024, 1024
    target_mp = 2.0
    expected_pixels = target_mp * 1024 * 1024
    w, h = compute_target_dims(src_w, src_h, target_mp)
    actual_pixels = w * h
    # Within 1% due to /8 snapping
    assert abs(actual_pixels - expected_pixels) / expected_pixels < 0.01
