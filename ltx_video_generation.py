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
