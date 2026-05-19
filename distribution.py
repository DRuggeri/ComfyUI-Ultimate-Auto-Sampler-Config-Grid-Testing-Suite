"""Thin facade for the ComfyUI-USCG-Distributed companion plugin.

All Distribution code (DistributionManager, WorkerThread, HTTP routes,
LAN socket discovery, urlopen calls) lives in the companion plugin.
This file just detects companion presence and forwards calls to it.

See:
- ComfyUI/custom_nodes/ComfyUI-USCG-Distributed/  (the companion)
- docs/superpowers/specs/2026-05-19-companion-plugin-extraction-distribution-design.md
"""

INSTALL_INSTRUCTIONS = (
    "Distributed multi-machine generation requires the "
    "ComfyUI-USCG-Distributed companion plugin.\n"
    "Install via Comfy Manager (search 'USCG Distributed') or:\n"
    "  git clone https://github.com/JasonHoku/ComfyUI-USCG-Distributed\n"
    "into your ComfyUI/custom_nodes/ directory."
)


def is_distribution_available():
    """Return True if the ComfyUI-USCG-Distributed companion plugin is loaded."""
    try:
        import comfyui_uscg_distributed  # noqa: F401
        return True
    except ImportError:
        return False


def _require_companion():
    """Return the companion module or raise RuntimeError with install instructions.
    Also validates minimum version (0.1.0).
    """
    try:
        import comfyui_uscg_distributed as _c
    except ImportError:
        raise RuntimeError(INSTALL_INSTRUCTIONS)
    if tuple(map(int, _c.__version__.split(".")[:2])) < (0, 1):
        raise RuntimeError(
            f"ComfyUI-USCG-Distributed >= 0.1.0 required (found {_c.__version__}). "
            "Update via Comfy Manager."
        )
    return _c


def create_manager(session_name, paths, unique_id, existing_data,
                   job_completed_check, claim_timeout_seconds=600,
                   build_prompt_with_triggers=None,
                   get_model_cache_key=None):
    """Construct master-side DistributionManager via the companion plugin.

    Args:
        session_name:               str
        paths:                      dict
        unique_id:                  str
        existing_data:              dict
        job_completed_check:        callback for skip-existing logic (required).
        claim_timeout_seconds:      int, default 600.
        build_prompt_with_triggers: optional callback for trigger-word handling
                                    in get_encoded_conditionings_for_job.
        get_model_cache_key:        optional callback for model cache keys
                                    in get_encoded_conditionings_for_job.
                                    Required alongside build_prompt_with_triggers
                                    for pre-encoded conditioning support.

    The three callbacks let the companion's DistributionManager avoid bidirectional
    imports back into main USCG.
    """
    return _require_companion().create_manager(
        session_name=session_name,
        paths=paths,
        unique_id=unique_id,
        existing_data=existing_data,
        job_completed_check=job_completed_check,
        claim_timeout_seconds=claim_timeout_seconds,
        build_prompt_with_triggers=build_prompt_with_triggers,
        get_model_cache_key=get_model_cache_key,
    )


def set_active_manager(manager):
    _require_companion().set_active_manager(manager)


def clear_active_manager():
    """Clear active master. Silent no-op if companion not installed
    (cleanup paths must be safe even if companion gets uninstalled mid-run).
    """
    if is_distribution_available():
        import comfyui_uscg_distributed as _c
        _c.clear_active_manager()


def notify_workers_to_start(worker_urls, master_url, session_name,
                            sync_models_to_workers=False):
    return _require_companion().notify_workers_to_start(
        worker_urls, master_url, session_name,
        sync_models_to_workers=sync_models_to_workers,
    )


def stop_all_workers(worker_urls):
    _require_companion().stop_all_workers(worker_urls)


def get_master_url():
    return _require_companion().get_master_url()
