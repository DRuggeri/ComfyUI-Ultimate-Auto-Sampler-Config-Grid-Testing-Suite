"""Tests for remote_vae.py facade functions added during companion extraction.

These functions detect whether the ComfyUI-USCG-RemoteVAE companion plugin is
installed and forward the actual decode call to it via lazy try-import.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

import remote_vae


@pytest.fixture
def fake_companion(monkeypatch):
    """Insert a fake companion module into sys.modules; remove it after the test."""
    fake = types.SimpleNamespace(
        __version__="0.1.0",
        decode=MagicMock(return_value="mocked_decode_result"),
        list_endpoints=lambda: [("SD", "https://x.huggingface.cloud/"),
                                 ("SDXL", "https://y.huggingface.cloud/")],
    )
    monkeypatch.setitem(sys.modules, "comfyui_uscg_remote_vae", fake)
    yield fake


@pytest.fixture
def no_companion(monkeypatch):
    """Ensure the companion module is NOT in sys.modules."""
    monkeypatch.delitem(sys.modules, "comfyui_uscg_remote_vae", raising=False)


def test_is_remote_vae_available_true_when_companion_installed(fake_companion):
    assert remote_vae.is_remote_vae_available() is True


def test_is_remote_vae_available_false_when_companion_missing(no_companion):
    assert remote_vae.is_remote_vae_available() is False


def test_get_endpoint_names_returns_list_when_companion_installed(fake_companion):
    names = remote_vae.get_endpoint_names()
    assert names == ["SD", "SDXL"]


def test_get_endpoint_names_returns_empty_when_companion_missing(no_companion):
    assert remote_vae.get_endpoint_names() == []


def test_companion_decode_returns_companion_result(fake_companion):
    result = remote_vae._companion_decode("SD", tensor="t", height=512, width=512)
    assert result == "mocked_decode_result"
    fake_companion.decode.assert_called_once_with("SD", "t", 512, 512)


def test_companion_decode_raises_runtime_error_when_missing(no_companion):
    with pytest.raises(RuntimeError) as exc_info:
        remote_vae._companion_decode("SD", tensor="t", height=512, width=512)
    msg = str(exc_info.value)
    assert "Comfy Manager" in msg
    assert "git clone" in msg
    assert "ComfyUI-USCG-RemoteVAE" in msg


def test_companion_decode_raises_when_version_too_old(monkeypatch):
    """If companion's __version__ < 0.1.0, raise with version requirement."""
    old_companion = types.SimpleNamespace(
        __version__="0.0.5",
        decode=MagicMock(return_value="should_not_be_called"),
        list_endpoints=lambda: [],
    )
    monkeypatch.setitem(sys.modules, "comfyui_uscg_remote_vae", old_companion)
    with pytest.raises(RuntimeError) as exc_info:
        remote_vae._companion_decode("SD", tensor="t", height=512, width=512)
    assert "0.1.0" in str(exc_info.value)
    old_companion.decode.assert_not_called()
