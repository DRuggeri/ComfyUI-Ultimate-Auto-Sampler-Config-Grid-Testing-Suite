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


def parse_mask_select_indices(user_input, detected_count):
    """Parse user's output_mask_select string against detected region count.

    Args:
        user_input: string from UI; "" = use all, "0" = first, "0,2" = specific indices.
        detected_count: how many regions Florence2 actually returned.

    Returns:
        Tuple (indices: list[int], mode: str) where mode is one of:
        - "all": use all detected regions (caller should union)
        - "select": use the listed indices
        - "no_detection": no valid selection possible (caller should treat as miss)
    """
    if detected_count <= 0:
        return [], "no_detection"

    stripped = (user_input or "").strip()
    if not stripped:
        return [], "all"

    raw_tokens = [t.strip() for t in stripped.split(",") if t.strip()]
    if not raw_tokens:
        return [], "all"

    parsed = []
    for tok in raw_tokens:
        try:
            n = int(tok)
        except ValueError:
            return [], "no_detection"
        if n < 0:
            return [], "no_detection"
        if n < detected_count:
            parsed.append(n)
        # OOR indices silently dropped

    if not parsed:
        return [], "no_detection"

    # Stable dedupe preserving order
    seen = set()
    out = []
    for n in parsed:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out, "select"


def _crop_image_by_mask(image, mask, padding, min_crop_resolution, max_crop_resolution):
    """Crop image to the bbox of a mask, with padding and min/max constraints.

    Args:
        image: torch tensor (B, H, W, C) float32 in [0,1]
        mask: torch tensor (B, H, W) float32 in [0,1]
        padding: int, pixels to expand bbox each side before clamping
        min_crop_resolution: int, minimum bbox dim — expands bbox if smaller
        max_crop_resolution: int, maximum bbox dim — shrinks bbox if larger

    Returns:
        Tuple (cropped_image, cropped_mask, bbox) where bbox = (x0, y0, w, h).

    Raises:
        ValueError: mask is empty (sum == 0).
    """
    import torch

    # Caller is responsible for no-detection check; this is defense-in-depth.
    if mask.sum() <= 0:
        raise ValueError("Mask is empty — cannot compute bbox")

    # Find tight bbox via nonzero indices on a 2D view of the first batch.
    # Mask is (B, H, W); we use batch 0 (Florence2Run returns single-batch).
    m2d = mask[0]  # (H, W)
    img_h, img_w = m2d.shape

    nz = torch.nonzero(m2d > 0.5)  # (N, 2) = (y, x)
    if nz.numel() == 0:
        raise ValueError("Mask is empty after thresholding")

    y_min = int(nz[:, 0].min().item())
    y_max = int(nz[:, 0].max().item())
    x_min = int(nz[:, 1].min().item())
    x_max = int(nz[:, 1].max().item())

    # Apply padding
    x0 = max(0, x_min - padding)
    y0 = max(0, y_min - padding)
    x1 = min(img_w, x_max + 1 + padding)
    y1 = min(img_h, y_max + 1 + padding)

    bw = x1 - x0
    bh = y1 - y0

    # Apply min_crop_resolution by expanding around center, clamping to image bounds.
    if bw < min_crop_resolution:
        cx = (x0 + x1) // 2
        half = min_crop_resolution // 2
        x0 = max(0, cx - half)
        x1 = min(img_w, x0 + min_crop_resolution)
        x0 = max(0, x1 - min_crop_resolution)  # second pass in case clamp shifted
        bw = x1 - x0
    if bh < min_crop_resolution:
        cy = (y0 + y1) // 2
        half = min_crop_resolution // 2
        y0 = max(0, cy - half)
        y1 = min(img_h, y0 + min_crop_resolution)
        y0 = max(0, y1 - min_crop_resolution)
        bh = y1 - y0

    # Apply max_crop_resolution by contracting around center.
    if bw > max_crop_resolution:
        cx = (x0 + x1) // 2
        half = max_crop_resolution // 2
        x0 = cx - half
        x1 = x0 + max_crop_resolution
        bw = x1 - x0
    if bh > max_crop_resolution:
        cy = (y0 + y1) // 2
        half = max_crop_resolution // 2
        y0 = cy - half
        y1 = y0 + max_crop_resolution
        bh = y1 - y0

    # Final clamp to image (in case max shrinking pushed us off-bounds)
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(img_w, x1)
    y1 = min(img_h, y1)
    bw = x1 - x0
    bh = y1 - y0

    cropped_image = image[:, y0:y1, x0:x1, :].contiguous()
    cropped_mask = mask[:, y0:y1, x0:x1].contiguous()
    bbox = (x0, y0, bw, bh)
    return cropped_image, cropped_mask, bbox


def _paste_into_image(destination, source, mask, bbox):
    """Paste a cropped image back into the destination using mask for alpha blending.

    Args:
        destination: torch tensor (B, H, W, C) — the full original image to paste into
        source: torch tensor (B, h, w, C) — the cropped (and resized) image to paste
        mask: torch tensor (B, h, w) — alpha mask for the source (0..1)
        bbox: tuple (x0, y0, w, h) — where in destination to paste

    Returns:
        New torch tensor (B, H, W, C) with the blended result.
    """
    x0, y0, bw, bh = bbox
    src_h, src_w = source.shape[1], source.shape[2]

    # If source dims don't match bbox (caller error), use source dims
    if src_h != bh or src_w != bw:
        bh = src_h
        bw = src_w

    result = destination.clone()
    # Broadcast (B, h, w) mask to (B, h, w, C)
    mask_3c = mask.unsqueeze(-1).expand(-1, -1, -1, source.shape[-1])

    dest_slice = destination[:, y0:y0 + bh, x0:x0 + bw, :]
    blended = source * mask_3c + dest_slice * (1.0 - mask_3c)
    result[:, y0:y0 + bh, x0:x0 + bw, :] = blended
    return result


# Required Florence2 node class names (looked up via nodes.NODE_CLASS_MAPPINGS)
REQUIRED_FLORENCE2_NODE_NAMES = [
    "Florence2Run",
    "DownloadAndLoadFlorence2Model",
]


def get_florence2_node_classes():
    """Look up Florence2 nodes in NODE_CLASS_MAPPINGS.

    Returns:
        Dict mapping node name to class.

    Raises:
        RuntimeError: any required node is missing.
    """
    import nodes
    found = {}
    missing = []
    for name in REQUIRED_FLORENCE2_NODE_NAMES:
        cls = nodes.NODE_CLASS_MAPPINGS.get(name)
        if cls is None:
            missing.append(name)
        else:
            found[name] = cls
    if missing:
        raise RuntimeError(
            "Florence2 Hi-Res Fix requires the kijai/ComfyUI-Florence2 custom node.\n"
            "Missing node(s): " + ", ".join(missing) + "\n\n"
            "Install via ComfyUI Manager:\n"
            "  search 'Florence-2' -> install -> restart Comfy\n\n"
            "Or manually:\n"
            "  cd ComfyUI/custom_nodes\n"
            "  git clone https://github.com/kijai/ComfyUI-Florence2\n"
            "  restart Comfy"
        )
    return found


def preflight_florence2():
    """Validate the Florence2 dependencies are installed.

    Call ONCE per job before any image is processed. Raises with a clear
    install hint if either required node is missing.
    """
    get_florence2_node_classes()


# Module-level cache for Florence2 models. Keyed by model name string.
# Cleared on Comfy restart; survives across jobs in the same session.
_FLORENCE2_MODEL_CACHE = {}


def load_florence2_model(model_name):
    """Load a Florence2 model, caching by name across jobs.

    Args:
        model_name: HF Hub id, e.g. "microsoft/Florence-2-base"

    Returns:
        The loaded model handle (whatever the loader node returns at index 0).
    """
    if model_name in _FLORENCE2_MODEL_CACHE:
        return _FLORENCE2_MODEL_CACHE[model_name]

    from ltx_video_generation import _call_node, _unwrap

    classes = get_florence2_node_classes()
    loader_cls = classes["DownloadAndLoadFlorence2Model"]

    print(f"[Florence2HiResFix] Loading {model_name}...")
    result = _call_node(
        loader_cls,
        model=model_name,
        precision="fp16",
        attention="sdpa",
        convert_to_safetensors=False,
    )
    handle = _unwrap(result, 0)
    _FLORENCE2_MODEL_CACHE[model_name] = handle
    return handle
