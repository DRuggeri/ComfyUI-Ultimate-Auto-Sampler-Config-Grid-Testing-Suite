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
        empty_video = nodes_map["EmptyLTXVLatentVideo"].execute(
            width=width // 2, height=height // 2, length=frames, batch_size=1
        )
        empty_video_latent = empty_video.output[0] if hasattr(empty_video, "output") else empty_video[0]

        # 2. Empty audio latent
        empty_audio = nodes_map["LTXVEmptyLatentAudio"].execute(
            frames_number=frames, frame_rate=frame_rate, batch_size=1, audio_vae=audio_vae
        )
        empty_audio_latent = empty_audio.output[0] if hasattr(empty_audio, "output") else empty_audio[0]

        # 3. Concat AV (stage 1 input). For t2v-only Phase A, no img inplace.
        stage1_input = nodes_map["LTXVConcatAVLatent"].execute(
            video_latent=empty_video_latent, audio_latent=empty_audio_latent
        )
        stage1_input_latent = stage1_input.output[0] if hasattr(stage1_input, "output") else stage1_input[0]

        # 4. Stage 1 sampling
        sampler1 = nodes_map["KSamplerSelect"].execute(sampler_name=sampler_stage1)
        sampler1_obj = sampler1.output[0] if hasattr(sampler1, "output") else sampler1[0]

        sigmas1_node = nodes_map["ManualSigmas"].execute(sigmas=sigmas1)
        sigmas1_tensor = sigmas1_node.output[0] if hasattr(sigmas1_node, "output") else sigmas1_node[0]

        noise1 = nodes_map["RandomNoise"].execute(noise_seed=seed_stage1)
        noise1_obj = noise1.output[0] if hasattr(noise1, "output") else noise1[0]

        guider1 = nodes_map["CFGGuider"].execute(
            model=diff_model, positive=cond_pos, negative=cond_neg, cfg=cfg_scale
        )
        guider1_obj = guider1.output[0] if hasattr(guider1, "output") else guider1[0]

        sampled1 = nodes_map["SamplerCustomAdvanced"].execute(
            noise=noise1_obj, guider=guider1_obj, sampler=sampler1_obj,
            sigmas=sigmas1_tensor, latent_image=stage1_input_latent,
        )
        sampled1_latent = sampled1.output[0] if hasattr(sampled1, "output") else sampled1[0]

        # 5. Separate AV
        sep1 = nodes_map["LTXVSeparateAVLatent"].execute(av_latent=sampled1_latent)
        if hasattr(sep1, "output"):
            video1, audio1 = sep1.output[0], sep1.output[1]
        else:
            video1, audio1 = sep1[0], sep1[1]

        # 6. Spatial upscale of video latent
        ups = nodes_map["LTXVLatentUpsampler"].execute(
            samples=video1, upscale_model=upscaler, vae=video_vae
        )
        upscaled_video = ups.output[0] if hasattr(ups, "output") else ups[0]

        # 7. Phase A skips LTXVImgToVideoInplace stage 2 (t2v + no upscale-input
        #    refinement image). The upscaled latent goes straight to crop guides.
        # 8. Crop guides on the upscaled latent
        crop = nodes_map["LTXVCropGuides"].execute(
            positive=cond_pos, negative=cond_neg, latent=upscaled_video
        )
        if hasattr(crop, "output"):
            crop_pos, crop_neg = crop.output[0], crop.output[1]
        else:
            crop_pos, crop_neg = crop[0], crop[1]

        # 9. Reconcat AV for stage 2
        stage2_input = nodes_map["LTXVConcatAVLatent"].execute(
            video_latent=upscaled_video, audio_latent=audio1
        )
        stage2_input_latent = stage2_input.output[0] if hasattr(stage2_input, "output") else stage2_input[0]

        # 10. Stage 2 sampling
        sampler2 = nodes_map["KSamplerSelect"].execute(sampler_name=sampler_stage2)
        sampler2_obj = sampler2.output[0] if hasattr(sampler2, "output") else sampler2[0]

        sigmas2_node = nodes_map["ManualSigmas"].execute(sigmas=sigmas2)
        sigmas2_tensor = sigmas2_node.output[0] if hasattr(sigmas2_node, "output") else sigmas2_node[0]

        noise2 = nodes_map["RandomNoise"].execute(noise_seed=seed_stage2)
        noise2_obj = noise2.output[0] if hasattr(noise2, "output") else noise2[0]

        guider2 = nodes_map["CFGGuider"].execute(
            model=diff_model, positive=crop_pos, negative=crop_neg, cfg=cfg_scale
        )
        guider2_obj = guider2.output[0] if hasattr(guider2, "output") else guider2[0]

        sampled2 = nodes_map["SamplerCustomAdvanced"].execute(
            noise=noise2_obj, guider=guider2_obj, sampler=sampler2_obj,
            sigmas=sigmas2_tensor, latent_image=stage2_input_latent,
        )
        sampled2_latent = sampled2.output[0] if hasattr(sampled2, "output") else sampled2[0]

        # 11. Separate AV final
        sep2 = nodes_map["LTXVSeparateAVLatent"].execute(av_latent=sampled2_latent)
        if hasattr(sep2, "output"):
            video2, audio2 = sep2.output[0], sep2.output[1]
        else:
            video2, audio2 = sep2[0], sep2[1]

        # 12. Decode video (tiled - non-tiled OOMs at typical durations)
        dec = nodes_map["VAEDecodeTiled"].execute(
            samples=video2, vae=video_vae,
            tile_size=768, overlap=64, temporal_size=4096, temporal_overlap=4,
        )
        frames_tensor = dec.output[0] if hasattr(dec, "output") else dec[0]

        # 13. Decode audio (Phase A: always on)
        adec = nodes_map["LTXVAudioVAEDecode"].execute(samples=audio2, audio_vae=audio_vae)
        audio_waveform = adec.output[0] if hasattr(adec, "output") else adec[0]

        # 14. Create video container
        cv = nodes_map["CreateVideo"].execute(
            fps=frame_rate, images=frames_tensor, audio=audio_waveform
        )
        video_obj = cv.output[0] if hasattr(cv, "output") else cv[0]

        # 15. Save mp4
        if not output_path.lower().endswith(".mp4"):
            output_path = output_path + ".mp4"
        out_dir = os.path.dirname(output_path)
        out_name = os.path.splitext(os.path.basename(output_path))[0]
        os.makedirs(out_dir, exist_ok=True)

        # SaveVideo's "filename_prefix" can be a path. The node appends a
        # timestamp/index by default - we control naming so we strip those.
        # Use a temporary save then rename to enforce our exact filename.
        nodes_map["SaveVideo"].execute(
            filename_prefix=os.path.join(out_dir, out_name + "_tmp"),
            format="mp4",
            codec="auto",
            video=video_obj,
        )
        # SaveVideo doesn't reliably return the written path in all versions -
        # find it on disk.
        import glob
        candidates = sorted(glob.glob(os.path.join(out_dir, out_name + "_tmp*.mp4")))
        if not candidates:
            raise RuntimeError("SaveVideo did not produce an mp4 in " + out_dir)
        actual = candidates[-1]  # newest if multiple
        if actual != output_path:
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(actual, output_path)
            except Exception as e:
                raise RuntimeError("Failed to rename SaveVideo output to " + output_path + ": " + str(e))

    duration = round(time.time() - t0, 2)

    return {
        "video_path": output_path,
        "frames": frames,
        "fps": frame_rate,
        "duration_seconds": duration_seconds,
        "width": width,
        "height": height,
        "duration": duration,  # gen wall time
    }
