"""
Pytest configuration for standalone testing outside ComfyUI.

The custom node's __init__.py requires ComfyUI internals (server, folder_paths,
torch, etc.) that are not available in a plain Python environment.
We stub those out here so pytest can collect and run unit tests without ComfyUI.
"""
import sys
import types
import os

# ── Stub out ComfyUI-only modules before any test or __init__.py import ──────
_COMFY_STUBS = [
    "server",
    "folder_paths",
    "nodes",
    "torch",
    "aiohttp",
    "aiohttp.web",
    "comfy",
    "comfy.utils",
    "comfy.sd",
    "comfy.model_management",
    "comfy.samplers",
]

for _mod_name in _COMFY_STUBS:
    if _mod_name not in sys.modules:
        _stub = types.ModuleType(_mod_name)
        # aiohttp.web needs a minimal RouteTableDef stub used by distribution_routes
        if _mod_name == "aiohttp.web":
            class _RouteTableDef:  # noqa: N801
                def get(self, *a, **kw):
                    return lambda fn: fn
                def post(self, *a, **kw):
                    return lambda fn: fn
                def delete(self, *a, **kw):
                    return lambda fn: fn
                def put(self, *a, **kw):
                    return lambda fn: fn
            _stub.RouteTableDef = _RouteTableDef
        # comfy.samplers needs KSampler with SCHEDULERS and SAMPLERS lists
        if _mod_name == "comfy.samplers":
            class _KSampler:  # noqa: N801
                SCHEDULERS = ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform"]
                SAMPLERS = ["euler", "euler_ancestral", "heun", "dpm_2", "dpm_2_ancestral",
                            "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral",
                            "dpmpp_sde", "dpmpp_2m", "dpmpp_2m_sde", "ddim", "uni_pc",
                            "uni_pc_bh2"]
            _stub.KSampler = _KSampler
        sys.modules[_mod_name] = _stub

# Wire comfy.samplers as an attribute of the comfy stub so
# `import comfy.samplers` and `comfy.samplers.KSampler` both resolve
if hasattr(sys.modules.get("comfy"), "__name__"):
    sys.modules["comfy"].samplers = sys.modules["comfy.samplers"]

# Ensure the custom node root is on sys.path so `ltx_video_generation` is importable
_NODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NODE_ROOT not in sys.path:
    sys.path.insert(0, _NODE_ROOT)
