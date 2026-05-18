"""Tests for preflight validation of Florence2 dependencies."""
import sys
import pytest


def test_preflight_raises_when_florence2run_missing(monkeypatch):
    """Missing Florence2Run -> RuntimeError with install hint."""
    import nodes
    monkeypatch.setattr(nodes, "NODE_CLASS_MAPPINGS", {
        "DownloadAndLoadFlorence2Model": object,
        # Florence2Run absent
    }, raising=False)
    from florence2_hires import preflight_florence2
    with pytest.raises(RuntimeError) as exc:
        preflight_florence2()
    assert "Florence2Run" in str(exc.value)
    assert "ComfyUI-Florence2" in str(exc.value)
    assert "Manager" in str(exc.value)


def test_preflight_raises_when_loader_missing(monkeypatch):
    import nodes
    monkeypatch.setattr(nodes, "NODE_CLASS_MAPPINGS", {
        "Florence2Run": object,
        # DownloadAndLoadFlorence2Model absent
    }, raising=False)
    from florence2_hires import preflight_florence2
    with pytest.raises(RuntimeError) as exc:
        preflight_florence2()
    assert "DownloadAndLoadFlorence2Model" in str(exc.value)


def test_preflight_passes_when_both_present(monkeypatch):
    import nodes
    monkeypatch.setattr(nodes, "NODE_CLASS_MAPPINGS", {
        "Florence2Run": object,
        "DownloadAndLoadFlorence2Model": object,
    }, raising=False)
    from florence2_hires import preflight_florence2
    # Should NOT raise
    preflight_florence2()


def test_get_florence2_node_classes_returns_both(monkeypatch):
    class _DLF:
        pass

    class _F2R:
        pass

    import nodes
    monkeypatch.setattr(nodes, "NODE_CLASS_MAPPINGS", {
        "Florence2Run": _F2R,
        "DownloadAndLoadFlorence2Model": _DLF,
    }, raising=False)
    from florence2_hires import get_florence2_node_classes
    classes = get_florence2_node_classes()
    assert classes["Florence2Run"] is _F2R
    assert classes["DownloadAndLoadFlorence2Model"] is _DLF
