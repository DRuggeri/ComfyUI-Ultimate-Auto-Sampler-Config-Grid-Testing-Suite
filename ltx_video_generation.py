"""
LTX 2.3 Video Generation Module
Two-stage SamplerCustomAdvanced pipeline with parallel audio rail.

Pinned LTX node pack version: TBD — set during first smoke test.
Required nodes (looked up via nodes.NODE_CLASS_MAPPINGS):
- DiffusionModelLoaderKJ
- DualCLIPLoader (built-in)
- VAELoaderKJ
- LatentUpscaleModelLoader
- LTXVPreprocess, LTXVImgToVideoInplace, LTXVConditioning,
- LTXVCropGuides, LTXVConcatAVLatent, LTXVSeparateAVLatent,
- LTXVEmptyLatentAudio, LTXVAudioVAEDecode,
- EmptyLTXVLatentVideo, LTXVLatentUpsampler,
- ManualSigmas, KSamplerSelect, RandomNoise, CFGGuider,
- SamplerCustomAdvanced, VAEDecodeTiled, CreateVideo, SaveVideo
"""

import os
import sys
import time
import builtins
import uuid
from typing import List


def safe_print(*args, **kwargs):
    """Windows-safe print mirroring config_builder_node.safe_print."""
    try:
        builtins.print(*args, **kwargs)
    except (OSError, ValueError):
        try:
            msg = " ".join(str(a) for a in args) + kwargs.get("end", "\n")
            sys.__stdout__.write(msg)
            sys.__stdout__.flush()
        except Exception:
            pass


print = safe_print


def parse_sigmas(sigma_str):
    """Parse a comma-separated sigma string into a list of floats.

    Args:
        sigma_str: e.g. "0.85, 0.7250, 0.4219, 0.0"

    Returns:
        List of floats.

    Raises:
        ValueError: empty string, fewer than 2 values, or any token not a valid float.
    """
    if not sigma_str or not sigma_str.strip():
        raise ValueError("Sigma string is empty")

    tokens = [t.strip() for t in sigma_str.split(",")]
    # Reject empty tokens (catches trailing/leading/double commas)
    for tok in tokens:
        if not tok:
            raise ValueError(
                "Sigma string has an empty token (trailing/leading/double comma): " + repr(sigma_str)
            )
    if len(tokens) < 2:
        raise ValueError(
            "Sigma string must contain at least 2 comma-separated values, got: " + repr(sigma_str)
        )

    result = []
    for tok in tokens:
        try:
            result.append(float(tok))
        except ValueError:
            raise ValueError("Sigma token " + repr(tok) + " is not a valid float (in " + repr(sigma_str) + ")")
    return result


import shutil


# Required LTX node class names — looked up via nodes.NODE_CLASS_MAPPINGS
REQUIRED_LTX_NODE_NAMES = [
    "DiffusionModelLoaderKJ",
    "DualCLIPLoader",
    "VAELoaderKJ",
    "LatentUpscaleModelLoader",
    "LTXVPreprocess",
    "LTXVImgToVideoInplace",
    "LTXVConditioning",
    "LTXVCropGuides",
    "LTXVConcatAVLatent",
    "LTXVSeparateAVLatent",
    "LTXVEmptyLatentAudio",
    "LTXVAudioVAEDecode",
    "EmptyLTXVLatentVideo",
    "LTXVLatentUpsampler",
    "ManualSigmas",
    "KSamplerSelect",
    "RandomNoise",
    "CFGGuider",
    "SamplerCustomAdvanced",
    "VAEDecodeTiled",
    "CreateVideo",
    "SaveVideo",
]


def get_ltx_node_classes():
    """Look up all required LTX nodes in NODE_CLASS_MAPPINGS.

    Returns:
        Dict mapping node name to class.

    Raises:
        RuntimeError: any required node is missing.
    """
    import nodes
    found = {}
    missing = []
    for name in REQUIRED_LTX_NODE_NAMES:
        cls = nodes.NODE_CLASS_MAPPINGS.get(name)
        if cls is None:
            missing.append(name)
        else:
            found[name] = cls
    if missing:
        raise RuntimeError(
            "LTX 2.3 video generation requires the following ComfyUI nodes "
            "(install via Comfy Manager - search 'LTXVideo' and 'KJNodes'):\n"
            + "\n".join("  - " + n for n in missing)
        )
    return found


def preflight_ltx(config):
    """Validate that LTX gen can run for this config. Raises RuntimeError on any
    missing node, missing model file, or missing ffmpeg.

    Call ONCE per LTX grid run before any gen, and once more per-config for
    things that vary per-config (i2v image existence, sigma string parses).
    """
    import folder_paths

    # 1. LTX node pack installed?
    get_ltx_node_classes()

    # 2. ffmpeg available?
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg required for LTX video output. Install ffmpeg and ensure "
            "it's on your system PATH."
        )

    # 3. Model files exist?
    checks = [
        ("diffusion_models", config["model"]),
        ("text_encoders", config["clip_models"][0]),
        ("text_encoders", config["clip_models"][1]),
        ("vae", config["vae_video"]),
        ("vae", config["vae_audio"]),
        ("upscale_models", config["latent_upscaler"]),
    ]
    missing_files = []
    for folder_key, name in checks:
        path = folder_paths.get_full_path(folder_key, name)
        if path is None:
            missing_files.append(folder_key + "/" + name)
    if missing_files:
        raise RuntimeError(
            "LTX model files not found:\n" + "\n".join("  - " + m for m in missing_files)
        )

    # 4. Sigma strings parse?
    parse_sigmas(config["sigmas_stage1"])
    parse_sigmas(config["sigmas_stage2"])

    # 5. i2v image exists if set?
    img = config.get("input_image")
    if img:
        if not os.path.isfile(img):
            raise RuntimeError("Input image not found: " + img)

    # 6. Even dimensions (LTX divides by 2 for latent space)?
    w = int(config["width"])
    h = int(config["height"])
    if w % 2 != 0 or h % 2 != 0:
        raise RuntimeError("LTX requires even width/height, got " + str(w) + "x" + str(h))


def load_ltx_models(config):
    """Load all 5 LTX model files. Cached individually by file path.

    Returns:
        Dict with keys: diffusion_model, dual_clip, video_vae, audio_vae,
        latent_upscaler.

    Raises:
        RuntimeError: on missing nodes (caught earlier in preflight) or load failure.
    """
    from comfy_execution.utils import CurrentNodeContext
    from . import model_cache

    nodes_map = get_ltx_node_classes()

    weight_dtype = config.get("weight_dtype", "default")
    compute_dtype = config.get("compute_dtype", "default")
    device = config.get("device", "main_device")

    # Cache keys
    diff_key = config["model"] + "::" + weight_dtype + "::" + compute_dtype
    clip_key = config["clip_models"][0] + "::" + config["clip_models"][1] + "::ltxv::default"
    vvae_key = config["vae_video"] + "::" + device + "::bf16"
    avae_key = config["vae_audio"] + "::" + device + "::bf16"
    upsc_key = config["latent_upscaler"]

    dummy_prompt_id = str(uuid.uuid4())

    out = {}

    # --- Diffusion model (V3 API: DiffusionModelLoaderKJ.execute) ---
    if diff_key in model_cache.ltx_diffusion_model_cache:
        out["diffusion_model"] = model_cache.ltx_diffusion_model_cache[diff_key]
    else:
        with CurrentNodeContext(prompt_id=dummy_prompt_id, node_id="uscg_ltx_diff", list_index=0):
            r = nodes_map["DiffusionModelLoaderKJ"].execute(
                model_name=config["model"],
                weight_dtype=weight_dtype,
                compute_dtype=compute_dtype,
                patch_cublaslinear=False,
                sage_attention="disabled",
                enable_fp16_accumulation=False,
            )
        m = r.output[0] if hasattr(r, "output") else r[0]
        model_cache.ltx_diffusion_model_cache[diff_key] = m
        model_cache._evict_to_max(model_cache.ltx_diffusion_model_cache, 1)
        out["diffusion_model"] = m

    # --- Dual CLIP (V1 API: DualCLIPLoader().load_clip) ---
    if clip_key in model_cache.ltx_dual_clip_cache:
        out["dual_clip"] = model_cache.ltx_dual_clip_cache[clip_key]
    else:
        clip_loader_cls = nodes_map["DualCLIPLoader"]
        clip_loader = clip_loader_cls()
        # Verify load_clip is the right method name; if not, find it by introspection.
        if hasattr(clip_loader, "load_clip"):
            r = clip_loader.load_clip(
                clip_name1=config["clip_models"][0],
                clip_name2=config["clip_models"][1],
                type="ltxv",
                device="default",
            )
        else:
            # Fallback: find the first non-dunder callable method that's not from object
            method_name = next(
                (n for n in dir(clip_loader)
                 if not n.startswith("_") and callable(getattr(clip_loader, n))
                 and n not in ("INPUT_TYPES",)),
                None
            )
            if method_name is None:
                raise RuntimeError("Could not find DualCLIPLoader entry method")
            r = getattr(clip_loader, method_name)(
                clip_name1=config["clip_models"][0],
                clip_name2=config["clip_models"][1],
                type="ltxv",
                device="default",
            )
        c = r[0] if isinstance(r, tuple) else r
        model_cache.ltx_dual_clip_cache[clip_key] = c
        model_cache._evict_to_max(model_cache.ltx_dual_clip_cache, 2)
        out["dual_clip"] = c

    # --- Video VAE (V3 API: VAELoaderKJ.execute) ---
    if vvae_key in model_cache.ltx_video_vae_cache:
        out["video_vae"] = model_cache.ltx_video_vae_cache[vvae_key]
    else:
        with CurrentNodeContext(prompt_id=dummy_prompt_id, node_id="uscg_ltx_vvae", list_index=0):
            r = nodes_map["VAELoaderKJ"].execute(
                vae_name=config["vae_video"],
                device=device,
                weight_dtype="bf16",
            )
        v = r.output[0] if hasattr(r, "output") else r[0]
        model_cache.ltx_video_vae_cache[vvae_key] = v
        model_cache._evict_to_max(model_cache.ltx_video_vae_cache, 1)
        out["video_vae"] = v

    # --- Audio VAE (V3 API: VAELoaderKJ.execute) ---
    if avae_key in model_cache.ltx_audio_vae_cache:
        out["audio_vae"] = model_cache.ltx_audio_vae_cache[avae_key]
    else:
        with CurrentNodeContext(prompt_id=dummy_prompt_id, node_id="uscg_ltx_avae", list_index=0):
            r = nodes_map["VAELoaderKJ"].execute(
                vae_name=config["vae_audio"],
                device=device,
                weight_dtype="bf16",
            )
        v = r.output[0] if hasattr(r, "output") else r[0]
        model_cache.ltx_audio_vae_cache[avae_key] = v
        model_cache._evict_to_max(model_cache.ltx_audio_vae_cache, 1)
        out["audio_vae"] = v

    # --- Latent upscaler (V1 API: LatentUpscaleModelLoader().load_model) ---
    if upsc_key in model_cache.ltx_latent_upscaler_cache:
        out["latent_upscaler"] = model_cache.ltx_latent_upscaler_cache[upsc_key]
    else:
        ld_cls = nodes_map["LatentUpscaleModelLoader"]
        ld = ld_cls()
        if hasattr(ld, "load_model"):
            r = ld.load_model(model_name=config["latent_upscaler"])
        else:
            method_name = next(
                (n for n in dir(ld)
                 if not n.startswith("_") and callable(getattr(ld, n))
                 and n not in ("INPUT_TYPES",)),
                None
            )
            if method_name is None:
                raise RuntimeError("Could not find LatentUpscaleModelLoader entry method")
            r = getattr(ld, method_name)(model_name=config["latent_upscaler"])
        u = r[0] if isinstance(r, tuple) else r
        model_cache.ltx_latent_upscaler_cache[upsc_key] = u
        model_cache._evict_to_max(model_cache.ltx_latent_upscaler_cache, 1)
        out["latent_upscaler"] = u

    return out


def encode_ltx_prompts(dual_clip, positive_text, negative_text, frame_rate):
    """Dual-CLIP encode positive and negative prompts, then wrap with LTXVConditioning.

    Returns:
        Tuple (cond_pos, cond_neg) - LTXVConditioning-wrapped pair ready for
        CFGGuider or LTXVCropGuides.
    """
    nodes_map = get_ltx_node_classes()

    # Standard CLIPTextEncode (built-in V1)
    encoder = nodes_map.get("CLIPTextEncode")
    if encoder is None:
        import nodes
        encoder = nodes.NODE_CLASS_MAPPINGS["CLIPTextEncode"]
    enc = encoder()

    pos = enc.encode(clip=dual_clip, text=positive_text)[0]
    neg = enc.encode(clip=dual_clip, text=negative_text)[0]

    # LTXVConditioning wraps with frame_rate
    cond_node = nodes_map["LTXVConditioning"]()
    if hasattr(cond_node, "execute"):
        # V3 API
        from comfy_execution.utils import CurrentNodeContext
        with CurrentNodeContext(prompt_id=str(uuid.uuid4()), node_id="uscg_ltx_cond", list_index=0):
            r = cond_node.execute(positive=pos, negative=neg, frame_rate=int(frame_rate))
        out = r.output if hasattr(r, "output") else r
    else:
        # V1 API - find the actual method (may be `apply` or similar)
        method_name = next(n for n in dir(cond_node) if not n.startswith("_") and callable(getattr(cond_node, n)))
        out = getattr(cond_node, method_name)(positive=pos, negative=neg, frame_rate=int(frame_rate))

    return out[0], out[1]
