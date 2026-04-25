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

# comfy.model_management needs InterruptProcessingException for generation_orchestrator
if "comfy.model_management" in sys.modules:
    if not hasattr(sys.modules["comfy.model_management"], "InterruptProcessingException"):
        sys.modules["comfy.model_management"].InterruptProcessingException = type(
            "InterruptProcessingException", (Exception,), {}
        )

# Ensure the custom node root is on sys.path so `ltx_video_generation` is importable
_NODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _NODE_ROOT not in sys.path:
    sys.path.insert(0, _NODE_ROOT)

# ── Package stub so generation_orchestrator's relative imports resolve ────────
# generation_orchestrator.py uses `from .trigger_words import ...` etc.
# When imported as a top-level module (sys.path.insert approach), relative
# imports fail unless we set up a minimal package context in sys.modules.
_PKG_NAME = os.path.basename(_NODE_ROOT)
if _PKG_NAME not in sys.modules:
    _pkg = types.ModuleType(_PKG_NAME)
    _pkg.__path__ = [_NODE_ROOT]
    _pkg.__package__ = _PKG_NAME
    sys.modules[_PKG_NAME] = _pkg

# Stub the sub-modules that generation_orchestrator imports via relative paths
_GEN_ORCH_DEPS = {
    "trigger_words": {
        "collect_unique_prompts_with_triggers": lambda *a, **kw: [],
        "build_prompt_with_triggers": lambda *a, **kw: ("", ""),
        "clear_trigger_caches": lambda *a, **kw: None,
    },
    "batch_encoding": {
        "batch_encode_prompts": lambda *a, **kw: None,
        "encode_prompt_with_combinators": lambda *a, **kw: None,
    },
    "manifest_utils": {
        "load_existing_manifest": lambda *a, **kw: {},
        "save_manifest": lambda *a, **kw: None,
    },
    "model_loader": {
        "load_checkpoint": lambda *a, **kw: None,
        "load_loras": lambda *a, **kw: None,
        "cleanup_model_references": lambda *a, **kw: None,
        "get_latent_channels": lambda *a, **kw: 4,
        "load_loras_for_preencoding": lambda *a, **kw: None,
        "print_incompatible_loras_summary": lambda *a, **kw: None,
        "load_diffusion_model_and_clip": lambda *a, **kw: (None, None),
        "load_vae_by_name": lambda *a, **kw: None,
    },
    "lora_utils": {
        "expand_lora_folder": lambda *a, **kw: [],
    },
    "image_generation": {
        "generate_image": lambda *a, **kw: None,
        "flush_batch_with_vae": lambda *a, **kw: None,
        "flush_batch_with_remote_vae": lambda *a, **kw: None,
        "create_image_metadata": lambda *a, **kw: {},
        "decode_latent_with_vae": lambda *a, **kw: None,
        "calculate_eta": lambda *a, **kw: 0.0,
        "print_generation_progress": lambda *a, **kw: None,
    },
    "html_generator": {
        "get_html_template": lambda *a, **kw: "",
    },
    "conditioning_cache": {
        "ConditioningCache": type("ConditioningCache", (), {}),
    },
    "remote_vae": {
        "RemoteVAEDecodeWorker": type("RemoteVAEDecodeWorker", (), {}),
        "HF_ENDPOINTS": {},
    },
}

for _bare, _attrs in _GEN_ORCH_DEPS.items():
    _fq = f"{_PKG_NAME}.{_bare}"
    if _bare not in sys.modules:
        _s = types.ModuleType(_bare)
        sys.modules[_bare] = _s
    if _fq not in sys.modules:
        sys.modules[_fq] = sys.modules[_bare]
    for _k, _v in _attrs.items():
        setattr(sys.modules[_bare], _k, _v)
        setattr(sys.modules[_fq], _k, _v)
    # Also wire as package attribute
    setattr(sys.modules[_PKG_NAME], _bare, sys.modules[_bare])

# Pre-load generation_orchestrator as part of the package so that relative
# imports (`from .trigger_words import ...`) resolve correctly.  Once loaded
# under the package name it is also registered as a top-level alias so
# `from generation_orchestrator import get_model_cache_key` works.
import importlib.util as _ilu
_GO_PATH = os.path.join(_NODE_ROOT, "generation_orchestrator.py")
_GO_FQ = f"{_PKG_NAME}.generation_orchestrator"
if "generation_orchestrator" not in sys.modules:
    _spec = _ilu.spec_from_file_location(_GO_FQ, _GO_PATH,
                                         submodule_search_locations=[])
    _spec.submodule_search_locations = None  # it is a module, not a package
    _go_mod = _ilu.module_from_spec(_spec)
    _go_mod.__package__ = _PKG_NAME
    sys.modules[_GO_FQ] = _go_mod
    sys.modules["generation_orchestrator"] = _go_mod
    _spec.loader.exec_module(_go_mod)
