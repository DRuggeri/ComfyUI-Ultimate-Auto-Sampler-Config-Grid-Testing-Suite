"""Thin facade for the ComfyUI-USCG-CivitAI companion plugin.

The CivitAI metadata lookup (urlopen against civitai.com) lives in the
companion plugin. This file just detects companion presence and forwards
calls to it. SILENT fallback (returns None) when companion missing —
NOT a RuntimeError, because:
1. CivitAI lookup is an optional convenience (auto-trigger detection)
2. The LoRA workflow still works without it (user types triggers manually)
3. Pre-extraction behavior was already "return None on any failure"

The Builder UI shows small inline notices in the relevant sections when
companion is missing (calls is_civitai_available() to detect).

See:
- ComfyUI/custom_nodes/ComfyUI-USCG-CivitAI/  (the companion)
- docs/superpowers/plans/2026-05-19-companion-plugin-extraction-civitai.md
"""


def is_civitai_available():
    """Return True if the ComfyUI-USCG-CivitAI companion is loaded."""
    try:
        import comfyui_uscg_civitai  # noqa: F401
        return True
    except ImportError:
        return False


def civitai_fetch_by_hash(hash_value):
    """Look up CivitAI metadata by file hash. Silent fallback to None.

    Returns parsed JSON dict on success, None on any error (network failure,
    404, OR companion not installed). Pre-existing callers already handle
    None for network-failure cases, so this is drop-in compatible.
    """
    try:
        from comfyui_uscg_civitai import fetch_by_hash
    except ImportError:
        return None
    return fetch_by_hash(hash_value)
