"""Florence2 Hi-Res Fix — targeted-region inpaint via Florence2 referring-expression segmentation.

Soft dependency: kijai/ComfyUI-Florence2 (checked at job start, not at import).
Required ComfyUI built-ins: GrowMask, FeatherMask (always present).
Crop / uncrop / resize-back are pure Python (no kjnodes dep).

Pipeline (per image, per Florence2 step):
  1. Pre-flight (once per job, cached)
  2. Load Florence2 model (cached per job)
  3. Detect via Florence2Run(task=referring_expression_segmentation)
  4. GrowMask
  5. Crop by mask (pure Python)
  6. Megapixel resize
  7. VAE encode -> generate_image (project's known-working sampling path)
  8. VAE decode -> resize back to crop dims
  9. FeatherMask
 10. Paste back (pure Python)
 11. Save + manifest entry (handled by upscale_runner)
"""

import builtins
import math
import sys


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


def compute_target_dims(src_w, src_h, target_megapixels):
    """Compute target (width, height) for a megapixel-based resize.

    Uses mebipixel convention (1 MP = 1024 * 1024 pixels), matching ComfyUI core's
    ImageScaleToTotalPixels. Output dims are snapped to multiples of 8, floored at 64,
    capped at 4096.

    Args:
        src_w: source width in pixels (int)
        src_h: source height in pixels (int)
        target_megapixels: target area in MP (float, e.g. 1.0 = ~1024x1024)

    Returns:
        Tuple (target_w, target_h) of ints, both divisible by 8.
    """
    target_pixels = target_megapixels * 1024 * 1024
    src_pixels = src_w * src_h
    if src_pixels <= 0:
        raise ValueError(f"Source dimensions invalid: {src_w}x{src_h}")
    scale = math.sqrt(target_pixels / src_pixels)
    new_w = max(64, min(4096, int(round(src_w * scale)) // 8 * 8))
    new_h = max(64, min(4096, int(round(src_h * scale)) // 8 * 8))
    return new_w, new_h
