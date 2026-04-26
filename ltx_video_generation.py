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


def _call_node(node_cls, **kwargs):
    """Call a Comfy node regardless of V1/V3 API. Returns whatever the node returns
    (typically a tuple, but V3 nodes return an object with .output).

    V3 (io.ComfyNode subclass): class-level .execute() classmethod — must be inside
        a CurrentNodeContext block.
    V1 (legacy): node has a FUNCTION attribute naming an instance method; instantiate
        the class then call that method on the instance. KJ nodes and most core ComfyUI
        nodes work this way.
    """
    # Try V3 first via subclass check (avoids triggering AttributeError noise on V1 nodes
    # that may also happen to have an unrelated `execute` attribute somewhere).
    try:
        from comfy_api.latest import io
        if isinstance(node_cls, type) and issubclass(node_cls, io.ComfyNode):
            return node_cls.execute(**kwargs)
    except (ImportError, TypeError):
        pass

    # V1 path: FUNCTION attribute names the instance method to invoke
    fn_name = getattr(node_cls, "FUNCTION", None)
    if fn_name:
        inst = node_cls()
        return getattr(inst, fn_name)(**kwargs)

    # Last-resort fallback: try class-level .execute()
    if hasattr(node_cls, "execute"):
        return node_cls.execute(**kwargs)

    raise RuntimeError("Cannot determine entry method for node " + repr(node_cls))


def _unwrap(result, idx=0):
    """Normalize a node's return value to a single positional output by index.

    V3 io.NodeOutput stores positional outputs in `.args` (a tuple) and supports
    `result[idx]` via __getitem__. V1 nodes return plain tuples/lists. A few helpers
    return a single object directly.
    """
    # V3 io.NodeOutput
    if hasattr(result, "args") and isinstance(getattr(result, "args"), tuple):
        return result.args[idx]
    # Some legacy helpers used a `.output` attribute (e.g. SeedVR2-style returns)
    if hasattr(result, "output"):
        out = result.output
        if isinstance(out, (tuple, list)):
            return out[idx]
        return out
    # V1 plain tuple/list
    if isinstance(result, (tuple, list)):
        return result[idx]
    # Single bare value (unusual but possible)
    return result


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
    # Note: latent_upscaler lives in `latent_upscale_models/` (consumed by
    # LatentUpscaleModelLoader), NOT `upscale_models/` (which is for image upscalers).
    checks = [
        ("diffusion_models", config["model"]),
        ("text_encoders", config["clip_models"][0]),
        ("text_encoders", config["clip_models"][1]),
        ("vae", config["vae_video"]),
        ("vae", config["vae_audio"]),
        ("latent_upscale_models", config["latent_upscaler"]),
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
        # Resolve via ComfyUI's input-dir lookup if it's not an absolute path
        # (drag-drop and clipboard-paste uploads land there as bare filenames).
        resolved = img
        if not os.path.isabs(img) and not os.path.isfile(img):
            try:
                import folder_paths as _fp
                candidate = _fp.get_annotated_filepath(img)
                if candidate and os.path.isfile(candidate):
                    resolved = candidate
            except Exception:
                pass
        if not os.path.isfile(resolved):
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

    # --- Diffusion model (V1 API: DiffusionModelLoaderKJ.patch_and_load) ---
    if diff_key in model_cache.ltx_diffusion_model_cache:
        out["diffusion_model"] = model_cache.ltx_diffusion_model_cache[diff_key]
    else:
        with CurrentNodeContext(prompt_id=dummy_prompt_id, node_id="uscg_ltx_diff", list_index=0):
            r = _call_node(
                nodes_map["DiffusionModelLoaderKJ"],
                model_name=config["model"],
                weight_dtype=weight_dtype,
                compute_dtype=compute_dtype,
                patch_cublaslinear=False,
                sage_attention="disabled",
                enable_fp16_accumulation=False,
            )
        m = _unwrap(r, 0)
        model_cache.ltx_diffusion_model_cache[diff_key] = m
        model_cache._evict_to_max(model_cache.ltx_diffusion_model_cache, 1)
        out["diffusion_model"] = m

    # --- Dual CLIP (V1 API: DualCLIPLoader().load_clip) ---
    if clip_key in model_cache.ltx_dual_clip_cache:
        out["dual_clip"] = model_cache.ltx_dual_clip_cache[clip_key]
    else:
        r = _call_node(
            nodes_map["DualCLIPLoader"],
            clip_name1=config["clip_models"][0],
            clip_name2=config["clip_models"][1],
            type="ltxv",
            device="default",
        )
        c = _unwrap(r, 0)
        model_cache.ltx_dual_clip_cache[clip_key] = c
        model_cache._evict_to_max(model_cache.ltx_dual_clip_cache, 2)
        out["dual_clip"] = c

    # --- Video VAE (V1 API: VAELoaderKJ.load_vae) ---
    if vvae_key in model_cache.ltx_video_vae_cache:
        out["video_vae"] = model_cache.ltx_video_vae_cache[vvae_key]
    else:
        with CurrentNodeContext(prompt_id=dummy_prompt_id, node_id="uscg_ltx_vvae", list_index=0):
            r = _call_node(
                nodes_map["VAELoaderKJ"],
                vae_name=config["vae_video"],
                device=device,
                weight_dtype="bf16",
            )
        v = _unwrap(r, 0)
        model_cache.ltx_video_vae_cache[vvae_key] = v
        model_cache._evict_to_max(model_cache.ltx_video_vae_cache, 1)
        out["video_vae"] = v

    # --- Audio VAE (V1 API: VAELoaderKJ.load_vae) ---
    if avae_key in model_cache.ltx_audio_vae_cache:
        out["audio_vae"] = model_cache.ltx_audio_vae_cache[avae_key]
    else:
        with CurrentNodeContext(prompt_id=dummy_prompt_id, node_id="uscg_ltx_avae", list_index=0):
            r = _call_node(
                nodes_map["VAELoaderKJ"],
                vae_name=config["vae_audio"],
                device=device,
                weight_dtype="bf16",
            )
        v = _unwrap(r, 0)
        model_cache.ltx_audio_vae_cache[avae_key] = v
        model_cache._evict_to_max(model_cache.ltx_audio_vae_cache, 1)
        out["audio_vae"] = v

    # --- Latent upscaler (V1 API: LatentUpscaleModelLoader().load_model) ---
    if upsc_key in model_cache.ltx_latent_upscaler_cache:
        out["latent_upscaler"] = model_cache.ltx_latent_upscaler_cache[upsc_key]
    else:
        r = _call_node(nodes_map["LatentUpscaleModelLoader"], model_name=config["latent_upscaler"])
        u = _unwrap(r, 0)
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

    pos = _unwrap(_call_node(encoder, clip=dual_clip, text=positive_text), 0)
    neg = _unwrap(_call_node(encoder, clip=dual_clip, text=negative_text), 0)

    # LTXVConditioning wraps with frame_rate (V3 API: ComfyNode subclass)
    from comfy_execution.utils import CurrentNodeContext
    with CurrentNodeContext(prompt_id=str(uuid.uuid4()), node_id="uscg_ltx_cond", list_index=0):
        r = _call_node(nodes_map["LTXVConditioning"], positive=pos, negative=neg, frame_rate=int(frame_rate))

    return _unwrap(r, 0), _unwrap(r, 1)


def ltx_video_generate(config, ltx_models, output_path):
    """Run the two-stage LTX pipeline and write an mp4.

    Phase A: text-to-video only. `input_image` is ignored.
    `audio_mode` is always treated as "on".

    Args:
        config: Per-config dict (single config from cartesian expansion).
        ltx_models: Output of load_ltx_models().
        output_path: Absolute path for the mp4 output (no extension required;
            ".mp4" appended if missing).

    Returns:
        Dict with manifest fields: video_path, frames, fps, duration, etc.

    Raises:
        Bubbles RuntimeError / OOM exceptions to caller.
    """
    from comfy_execution.utils import CurrentNodeContext
    import torch

    t0 = time.time()
    nodes_map = get_ltx_node_classes()
    prompt_id = str(uuid.uuid4())

    width = int(config["width"])
    height = int(config["height"])
    duration_seconds = int(config["duration_seconds"])
    frame_rate = int(config["frame_rate"])
    cfg_scale = float(config.get("cfg", 1.0))
    seed_stage1 = int(config["seed"])
    seed_stage2 = seed_stage1 + 1

    sigmas1 = config["sigmas_stage1"]
    sigmas2 = config["sigmas_stage2"]
    sampler_stage1 = config.get("sampler_stage1", "euler_ancestral_cfg_pp")
    sampler_stage2 = config.get("sampler_stage2", "euler_cfg_pp")

    frames = duration_seconds * frame_rate + 1

    print("[GridTester] LTX gen: " + str(width) + "x" + str(height) +
          ", dur=" + str(duration_seconds) + "s, fps=" + str(frame_rate) +
          ", frames=" + str(frames) + ", seed=" + str(seed_stage1))

    # Encode prompts
    cond_pos, cond_neg = encode_ltx_prompts(
        ltx_models["dual_clip"],
        config.get("positive", ""),
        config.get("negative", ""),
        frame_rate,
    )

    diff_model = ltx_models["diffusion_model"]
    video_vae = ltx_models["video_vae"]
    audio_vae = ltx_models["audio_vae"]
    upscaler = ltx_models["latent_upscaler"]

    # Run all node executions inside a single mock V3 context
    with CurrentNodeContext(prompt_id=prompt_id, node_id="uscg_ltx_gen", list_index=0):
        # 1. Empty video latent (dimensions /2 for latent space)
        empty_video_latent = _unwrap(_call_node(
            nodes_map["EmptyLTXVLatentVideo"],
            width=width // 2, height=height // 2, length=frames, batch_size=1,
        ), 0)

        # 2. Empty audio latent
        empty_audio_latent = _unwrap(_call_node(
            nodes_map["LTXVEmptyLatentAudio"],
            frames_number=frames, frame_rate=frame_rate, batch_size=1, audio_vae=audio_vae,
        ), 0)

        # 2.5. If i2v: preprocess input image and run LTXVImgToVideoInplace stage 1.
        # The preprocessed image tensor is reused for stage 2 (post-upscale refinement).
        input_image_path = config.get("input_image")
        is_i2v = bool(input_image_path)
        i2v_preprocessed_image = None
        if is_i2v:
            from PIL import Image as PILImage
            import numpy as np
            import torch as _torch
            import os as _os

            # Resolve the input_image. If it's an absolute path, use as-is. Otherwise
            # try resolving via ComfyUI's standard input-dir lookup (drag-drop and
            # clipboard-paste uploads land there as bare filenames).
            resolved_image_path = input_image_path
            if not _os.path.isabs(input_image_path) and not _os.path.isfile(input_image_path):
                try:
                    import folder_paths
                    candidate = folder_paths.get_annotated_filepath(input_image_path)
                    if candidate and _os.path.isfile(candidate):
                        resolved_image_path = candidate
                except Exception:
                    pass  # fall back to original; PIL will raise if truly missing

            pil = PILImage.open(resolved_image_path).convert("RGB")
            # Resize to target dims (matches reference workflow's ResizeImageMaskNode)
            pil = pil.resize((width, height), PILImage.LANCZOS)
            img_np = np.array(pil).astype(np.float32) / 255.0
            img_tensor = _torch.from_numpy(img_np).unsqueeze(0)  # [1, H, W, 3]

            i2v_preprocessed_image = _unwrap(_call_node(
                nodes_map["LTXVPreprocess"],
                image=img_tensor,
                img_compression=int(config.get("img_compression", 18)),
            ), 0)

            # Apply ImgToVideoInplace stage 1 (strength_stage1)
            video_pre = _unwrap(_call_node(
                nodes_map["LTXVImgToVideoInplace"],
                strength=float(config.get("image_strength_stage1", 0.8)),
                bypass=False,
                vae=video_vae,
                image=i2v_preprocessed_image,
                latent=empty_video_latent,
            ), 0)
        else:
            video_pre = empty_video_latent

        # 3. Concat AV (stage 1 input)
        stage1_input_latent = _unwrap(_call_node(
            nodes_map["LTXVConcatAVLatent"],
            video_latent=video_pre, audio_latent=empty_audio_latent,
        ), 0)

        # 4. Stage 1 sampling
        sampler1_obj = _unwrap(_call_node(nodes_map["KSamplerSelect"], sampler_name=sampler_stage1), 0)

        sigmas1_tensor = _unwrap(_call_node(nodes_map["ManualSigmas"], sigmas=sigmas1), 0)

        noise1_obj = _unwrap(_call_node(nodes_map["RandomNoise"], noise_seed=seed_stage1), 0)

        guider1_obj = _unwrap(
            _call_node(nodes_map["CFGGuider"],
                       model=diff_model, positive=cond_pos, negative=cond_neg, cfg=cfg_scale),
            0,
        )

        sampled1_latent = _unwrap(
            _call_node(nodes_map["SamplerCustomAdvanced"],
                       noise=noise1_obj, guider=guider1_obj, sampler=sampler1_obj,
                       sigmas=sigmas1_tensor, latent_image=stage1_input_latent),
            0,
        )

        # 5. Separate AV
        sep1 = _call_node(nodes_map["LTXVSeparateAVLatent"], av_latent=sampled1_latent)
        video1, audio1 = _unwrap(sep1, 0), _unwrap(sep1, 1)

        # 6. Spatial upscale of video latent
        upscaled_video = _unwrap(
            _call_node(nodes_map["LTXVLatentUpsampler"],
                       samples=video1, upscale_model=upscaler, vae=video_vae),
            0,
        )

        # 7. If i2v: apply LTXVImgToVideoInplace stage 2 to the upscaled latent for refinement
        if is_i2v and i2v_preprocessed_image is not None:
            upscaled_video = _unwrap(_call_node(
                nodes_map["LTXVImgToVideoInplace"],
                strength=float(config.get("image_strength_stage2", 1.0)),
                bypass=False,
                vae=video_vae,
                image=i2v_preprocessed_image,
                latent=upscaled_video,
            ), 0)

        # 8. Crop guides on the (possibly i2v-refined) upscaled latent
        crop = _call_node(nodes_map["LTXVCropGuides"],
                          positive=cond_pos, negative=cond_neg, latent=upscaled_video)
        crop_pos, crop_neg = _unwrap(crop, 0), _unwrap(crop, 1)

        # 9. Reconcat AV for stage 2
        stage2_input_latent = _unwrap(
            _call_node(nodes_map["LTXVConcatAVLatent"],
                       video_latent=upscaled_video, audio_latent=audio1),
            0,
        )

        # 10. Stage 2 sampling
        sampler2_obj = _unwrap(_call_node(nodes_map["KSamplerSelect"], sampler_name=sampler_stage2), 0)

        sigmas2_tensor = _unwrap(_call_node(nodes_map["ManualSigmas"], sigmas=sigmas2), 0)

        noise2_obj = _unwrap(_call_node(nodes_map["RandomNoise"], noise_seed=seed_stage2), 0)

        guider2_obj = _unwrap(
            _call_node(nodes_map["CFGGuider"],
                       model=diff_model, positive=crop_pos, negative=crop_neg, cfg=cfg_scale),
            0,
        )

        sampled2_latent = _unwrap(
            _call_node(nodes_map["SamplerCustomAdvanced"],
                       noise=noise2_obj, guider=guider2_obj, sampler=sampler2_obj,
                       sigmas=sigmas2_tensor, latent_image=stage2_input_latent),
            0,
        )

        # 11. Separate AV final
        sep2 = _call_node(nodes_map["LTXVSeparateAVLatent"], av_latent=sampled2_latent)
        video2, audio2 = _unwrap(sep2, 0), _unwrap(sep2, 1)

        # 12. Decode video (tiled - non-tiled OOMs at typical durations)
        frames_tensor = _unwrap(
            _call_node(nodes_map["VAEDecodeTiled"],
                       samples=video2, vae=video_vae,
                       tile_size=768, overlap=64, temporal_size=4096, temporal_overlap=4),
            0,
        )

        # 13. Decode audio (Phase A: always on)
        audio_waveform = _unwrap(
            _call_node(nodes_map["LTXVAudioVAEDecode"], samples=audio2, audio_vae=audio_vae),
            0,
        )

        # 14. Create video container
        video_obj = _unwrap(
            _call_node(nodes_map["CreateVideo"], fps=frame_rate, images=frames_tensor, audio=audio_waveform),
            0,
        )

        # 15. Save mp4 — call video.save_to() directly instead of going through
        # the SaveVideo node. SaveVideo accesses cls.hidden.extra_pnginfo/prompt
        # which the normal Comfy executor populates but we don't (and we don't
        # need pnginfo metadata for video files anyway). save_to() is what
        # SaveVideo.execute() calls internally — same code path, no hidden deps.
        if not output_path.lower().endswith(".mp4"):
            output_path = output_path + ".mp4"
        out_dir = os.path.dirname(output_path)
        os.makedirs(out_dir, exist_ok=True)

        try:
            from comfy_api.latest._input_impl import VideoContainer as _VideoContainerEnum
        except ImportError:
            try:
                from comfy_api.latest._input.video_types import VideoContainer as _VideoContainerEnum
            except ImportError:
                _VideoContainerEnum = None

        save_kwargs = {"codec": "auto", "metadata": None}
        if _VideoContainerEnum is not None:
            try:
                save_kwargs["format"] = _VideoContainerEnum("mp4")
            except Exception:
                save_kwargs["format"] = "mp4"
        else:
            save_kwargs["format"] = "mp4"

        try:
            video_obj.save_to(output_path, **save_kwargs)
        except TypeError:
            # Older Comfy: positional or differently-named kwargs
            video_obj.save_to(output_path)

    # Preview thumbnail: middle frame as PNG for fast dashboard previews
    preview_path = None
    try:
        from PIL import Image as PILImage
        import numpy as np
        # frames_tensor shape: [N_frames, H, W, 3] float32 in [0, 1]
        n = frames_tensor.shape[0]
        mid_idx = n // 2
        mid_np = (frames_tensor[mid_idx].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        preview_path = output_path[:-4] + ".preview.png" if output_path.lower().endswith(".mp4") else output_path + ".preview.png"
        PILImage.fromarray(mid_np, "RGB").save(preview_path)
    except Exception as e:
        print("[GridTester] Preview thumbnail write failed: " + str(e))
        preview_path = None

    duration = round(time.time() - t0, 2)

    return {
        "video_path": output_path,
        "preview_path": preview_path,
        "frames": frames,
        "fps": frame_rate,
        "duration_seconds": duration_seconds,
        "width": width,
        "height": height,
        "duration": duration,  # gen wall time
    }
