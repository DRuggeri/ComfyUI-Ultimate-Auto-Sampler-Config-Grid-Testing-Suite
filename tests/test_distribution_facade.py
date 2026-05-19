"""Tests for distribution.py facade — companion detection + forwarding."""

import sys
import types
from unittest.mock import MagicMock

import pytest

import distribution


@pytest.fixture
def fake_companion(monkeypatch):
    """Insert a fake companion module into sys.modules; remove after test."""
    fake = types.SimpleNamespace(
        __version__="0.1.0",
        create_manager=MagicMock(return_value="fake_manager"),
        set_active_manager=MagicMock(),
        clear_active_manager=MagicMock(),
        notify_workers_to_start=MagicMock(return_value=[{"url": "http://w1", "ok": True}]),
        stop_all_workers=MagicMock(),
        get_master_url=MagicMock(return_value="http://192.168.1.42:8188"),
    )
    monkeypatch.setitem(sys.modules, "comfyui_uscg_distributed", fake)
    yield fake


@pytest.fixture
def no_companion(monkeypatch):
    monkeypatch.delitem(sys.modules, "comfyui_uscg_distributed", raising=False)


def test_is_available_true_when_companion_installed(fake_companion):
    assert distribution.is_distribution_available() is True


def test_is_available_false_when_companion_missing(no_companion):
    assert distribution.is_distribution_available() is False


def test_create_manager_forwards(fake_companion):
    cb = lambda i, c: False
    result = distribution.create_manager(
        session_name="s", paths={"base": "/tmp"}, unique_id="n1",
        existing_data={"items": []}, job_completed_check=cb,
    )
    assert result == "fake_manager"
    fake_companion.create_manager.assert_called_once()


def test_create_manager_raises_when_missing(no_companion):
    with pytest.raises(RuntimeError) as exc_info:
        distribution.create_manager(
            session_name="s", paths={"base": "/tmp"}, unique_id="n1",
            existing_data={"items": []}, job_completed_check=lambda i, c: False,
        )
    msg = str(exc_info.value)
    assert "Comfy Manager" in msg
    assert "git clone" in msg
    assert "ComfyUI-USCG-Distributed" in msg


def test_create_manager_raises_when_version_too_old(monkeypatch):
    old = types.SimpleNamespace(
        __version__="0.0.5",
        create_manager=MagicMock(return_value="should_not_be_called"),
    )
    monkeypatch.setitem(sys.modules, "comfyui_uscg_distributed", old)
    with pytest.raises(RuntimeError) as exc_info:
        distribution.create_manager(
            session_name="s", paths={"base": "/tmp"}, unique_id="n1",
            existing_data={"items": []}, job_completed_check=lambda i, c: False,
        )
    assert "0.1.0" in str(exc_info.value)
    old.create_manager.assert_not_called()


def test_set_active_manager_forwards(fake_companion):
    distribution.set_active_manager("manager_obj")
    fake_companion.set_active_manager.assert_called_once_with("manager_obj")


def test_clear_active_manager_silent_when_missing(no_companion):
    # Should not raise — cleanup must be safe even if companion uninstalled mid-run.
    distribution.clear_active_manager()


def test_clear_active_manager_forwards_when_present(fake_companion):
    distribution.clear_active_manager()
    fake_companion.clear_active_manager.assert_called_once()


def test_notify_workers_to_start_forwards(fake_companion):
    result = distribution.notify_workers_to_start(
        ["http://w1", "http://w2"], "http://master:8188", "session1",
        sync_models_to_workers=True,
    )
    assert result == [{"url": "http://w1", "ok": True}]
    fake_companion.notify_workers_to_start.assert_called_once_with(
        ["http://w1", "http://w2"], "http://master:8188", "session1",
        sync_models_to_workers=True,
    )


def test_stop_all_workers_forwards(fake_companion):
    distribution.stop_all_workers(["http://w1"])
    fake_companion.stop_all_workers.assert_called_once_with(["http://w1"])


def test_get_master_url_forwards(fake_companion):
    result = distribution.get_master_url()
    assert result == "http://192.168.1.42:8188"
    fake_companion.get_master_url.assert_called_once()
