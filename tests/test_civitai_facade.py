"""Tests for civitai.py facade — companion detection + forwarding + silent fallback."""

import sys
import types
from unittest.mock import MagicMock

import pytest

import civitai


@pytest.fixture
def fake_companion(monkeypatch):
    fake = types.SimpleNamespace(
        __version__="0.1.0",
        fetch_by_hash=MagicMock(return_value={"trainedWords": ["word1"]}),
        is_available=MagicMock(return_value=True),
    )
    monkeypatch.setitem(sys.modules, "comfyui_uscg_civitai", fake)
    yield fake


@pytest.fixture
def no_companion(monkeypatch):
    monkeypatch.delitem(sys.modules, "comfyui_uscg_civitai", raising=False)


def test_is_civitai_available_true_when_companion_installed(fake_companion):
    assert civitai.is_civitai_available() is True


def test_is_civitai_available_false_when_companion_missing(no_companion):
    assert civitai.is_civitai_available() is False


def test_civitai_fetch_by_hash_returns_companion_result(fake_companion):
    result = civitai.civitai_fetch_by_hash("THEHASH")
    assert result == {"trainedWords": ["word1"]}
    fake_companion.fetch_by_hash.assert_called_once_with("THEHASH")


def test_civitai_fetch_by_hash_returns_none_when_missing(no_companion):
    """Silent fallback — NO RuntimeError, just None.
    This matches the existing pre-extraction behavior on network failure."""
    result = civitai.civitai_fetch_by_hash("anyhash")
    assert result is None
