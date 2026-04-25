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
        sys.modules[_mod_name] = _stub

# Ensure the custom node root is on sys.path so `ltx_video_generation` is importable
_NODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NODE_ROOT not in sys.path:
    sys.path.insert(0, _NODE_ROOT)
