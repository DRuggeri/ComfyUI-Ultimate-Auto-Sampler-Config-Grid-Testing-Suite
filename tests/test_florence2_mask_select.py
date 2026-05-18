"""Tests for parse_mask_select_indices() — converts user string to (indices, mode)."""
import pytest

from florence2_hires import parse_mask_select_indices


def test_empty_string_means_all():
    """Empty string -> mode='all', indices=[]."""
    indices, mode = parse_mask_select_indices("", detected_count=3)
    assert mode == "all"
    assert indices == []


def test_whitespace_only_means_all():
    indices, mode = parse_mask_select_indices("   ", detected_count=3)
    assert mode == "all"


def test_single_index():
    indices, mode = parse_mask_select_indices("0", detected_count=3)
    assert mode == "select"
    assert indices == [0]


def test_multiple_indices():
    indices, mode = parse_mask_select_indices("0,2", detected_count=3)
    assert mode == "select"
    assert indices == [0, 2]


def test_spaces_between_indices():
    indices, mode = parse_mask_select_indices("0, 1 , 2", detected_count=3)
    assert mode == "select"
    assert indices == [0, 1, 2]


def test_out_of_range_index_returns_no_detection():
    """Index >= detected_count -> mode='no_detection' (don't crash)."""
    indices, mode = parse_mask_select_indices("5", detected_count=3)
    assert mode == "no_detection"


def test_some_in_range_some_out_keeps_in_range():
    """Partial OOR -> keep the valid ones."""
    indices, mode = parse_mask_select_indices("0,5,1", detected_count=3)
    assert mode == "select"
    assert indices == [0, 1]


def test_negative_index_treated_as_invalid():
    indices, mode = parse_mask_select_indices("-1", detected_count=3)
    assert mode == "no_detection"


def test_garbage_input_returns_no_detection():
    indices, mode = parse_mask_select_indices("foo", detected_count=3)
    assert mode == "no_detection"


def test_zero_detected_with_empty_request():
    """Empty request + no detections -> no_detection."""
    indices, mode = parse_mask_select_indices("", detected_count=0)
    assert mode == "no_detection"
