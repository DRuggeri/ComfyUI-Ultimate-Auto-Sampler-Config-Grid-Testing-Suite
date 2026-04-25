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
