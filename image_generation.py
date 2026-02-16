"""
Image Generation and Sampling Module
Handles the core image generation, decoding, and batch management
"""

import time
import os
import re
import json
import torch
import nodes
import numpy as np
from PIL import Image


def generate_image(
    patched_model,
    seed,
    steps,
    cfg,
    sampler_name,
    scheduler,
    positive_conditioning,
    negative_conditioning,
    latent_input,
    denoise,
    attention_mode="default"
):
    """
    Generate a single image using ComfyUI's KSampler.

    Args:
        patched_model: Model (potentially with LoRAs applied)
        seed: Random seed
        steps: Number of sampling steps
        cfg: CFG scale
        sampler_name: Sampler name (e.g., "euler", "dpmpp_2m")
        scheduler: Scheduler name (e.g., "normal", "karras")
        positive_conditioning: Positive conditioning tensor
        negative_conditioning: Negative conditioning tensor
        latent_input: Input latent tensor dict
        denoise: Denoise strength (0.0-1.0)
        attention_mode: Attention implementation to use ("default", "xformers", "pytorch",
                       "flash", "sage", "sage3", "sub_quad", "split")

    Returns:
        tuple: (result_latent_dict, generation_duration_seconds)
    """
    # Apply attention mode override if not "default"
    original_attn_override = None
    if attention_mode and attention_mode != "default":
        try:
            from comfy.ldm.modules.attention import get_attention_function
            attn_func = get_attention_function(attention_mode, default=None)
            if attn_func is not None:
                # Save original override (if any) and set the new one
                original_attn_override = patched_model.model_options.get("transformer_options", {}).get("optimized_attention_override")
                if "transformer_options" not in patched_model.model_options:
                    patched_model.model_options["transformer_options"] = {}
                patched_model.model_options["transformer_options"]["optimized_attention_override"] = attn_func
            else:
                print(f"[GridTester] ⚠️ Attention mode '{attention_mode}' not available, using default")
        except Exception as e:
            print(f"[GridTester] ⚠️ Could not set attention mode '{attention_mode}': {e}")

    t0 = time.time()

    try:
        result = nodes.common_ksampler(
            model=patched_model,
            seed=seed,
            steps=steps,
            cfg=cfg,
            sampler_name=sampler_name,
            scheduler=scheduler,
            positive=positive_conditioning,
            negative=negative_conditioning,
            latent=latent_input,
            denoise=denoise
        )
    finally:
        # Restore original attention override
        if attention_mode and attention_mode != "default":
            if original_attn_override is not None:
                patched_model.model_options["transformer_options"]["optimized_attention_override"] = original_attn_override
            elif "transformer_options" in patched_model.model_options and "optimized_attention_override" in patched_model.model_options["transformer_options"]:
                del patched_model.model_options["transformer_options"]["optimized_attention_override"]

    duration = round(time.time() - t0, 3)

    return result[0], duration


def decode_latent_with_vae(vae, latent_samples):
    """
    Decode latent samples to pixel space using VAE.
    
    Args:
        vae: VAE model
        latent_samples: Latent tensor to decode
        
    Returns:
        PIL.Image: Decoded image
    """
    decoded = vae.decode(latent_samples)
    
    # Convert to PIL Image
    img_np = decoded.cpu().numpy()
    
    # Remove extra dimensions (handle shapes like (1, 1, H, W, C) or (1, H, W, C))
    while img_np.ndim > 3:
        img_np = img_np[0]
    
    # Now should be (H, W, C) or (C, H, W)
    img_np = np.clip(img_np * 255, 0, 255).astype(np.uint8)
    
    # Handle different channel orders
    if img_np.shape[0] == 3 and img_np.ndim == 3:  # CHW format
        img_np = np.transpose(img_np, (1, 2, 0))
    elif img_np.shape[-1] != 3 and img_np.ndim == 3:  # Not HWC format
        img_np = np.transpose(img_np, (1, 2, 0))
    
    return Image.fromarray(img_np)


def save_image_to_disk(image, output_dir, filename):
    """
    Save PIL Image to disk.
    
    Args:
        image: PIL.Image object
        output_dir: Directory to save in
        filename: Filename (including extension)
        
    Returns:
        str: Full path to saved image
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    image.save(filepath)
    return filepath


def create_image_metadata(config, width, height, duration, seed, batch_idx, actual_positive_prompt, actual_negative_prompt):
    """
    Create metadata dictionary for an image.
    
    Args:
        config: Configuration dictionary
        width: Image width
        height: Image height
        duration: Generation duration in seconds
        seed: Random seed used
        batch_idx: Batch index
        actual_positive_prompt: Final positive prompt (with triggers)
        actual_negative_prompt: Final negative prompt
        
    Returns:
        dict: Metadata dictionary
    """
    meta = config.copy()
    
    # Remove global settings that should only be in manifest.meta, not in individual items
    # These are session-wide settings that don't change per-image
    global_settings_to_remove = [
        "lora_triggerwords_append_settings",
        "lora_omit_triggers",
        "seed_behavior",
        "gguf_options",
        "model_prompt_prefix",
        "model_prompt_suffix"
    ]

    for key in global_settings_to_remove:
        meta.pop(key, None)

    # Remove attention_mode if it's "default" (keep manifest backward-compatible)
    if meta.get("attention_mode") == "default":
        meta.pop("attention_mode", None)

    meta.update({
        "width": width,
        "height": height,
        "duration": duration,
        "seed": seed,
        "batch_idx": batch_idx,
        "positive": actual_positive_prompt,
        "negative": actual_negative_prompt
    })

    return meta


def calculate_eta(job_durations, current_job, total_jobs):
    """
    Calculate ETA based on average job duration.
    
    Args:
        job_durations: List of previous job durations
        current_job: Current job number (1-indexed)
        total_jobs: Total number of jobs
        
    Returns:
        dict: Dictionary with eta info (hours, minutes, seconds, finish_time, finish_formatted)
    """
    if not job_durations:
        return None
    
    avg_duration = sum(job_durations) / len(job_durations)
    remaining_jobs = total_jobs - current_job
    estimated_seconds = avg_duration * remaining_jobs
    
    eta_hours = int(estimated_seconds // 3600)
    eta_minutes = int((estimated_seconds % 3600) // 60)
    eta_seconds = int(estimated_seconds % 60)
    eta_finish_time = time.time() + estimated_seconds
    eta_finish_formatted = time.strftime("%H:%M:%S", time.localtime(eta_finish_time))
    
    return {
        "hours": eta_hours,
        "minutes": eta_minutes,
        "seconds": eta_seconds,
        "finish_time": eta_finish_time,
        "finish_formatted": eta_finish_formatted,
        "avg_duration": avg_duration
    }


def print_generation_progress(current_job, total_jobs, config, width, height, duration, eta_info):
    """
    Print progress information for current generation.
    
    Args:
        current_job: Current job number
        total_jobs: Total jobs
        config: Configuration dict
        width: Image width
        height: Image height
        duration: Generation duration
        eta_info: ETA info dict from calculate_eta()
    """
    progress_pct = int((current_job / total_jobs) * 100)
    
    print(f"{'='*80}")
    print(f"[GridTester] 📊 Job {current_job}/{total_jobs} ({progress_pct}%)")
    print(f"[GridTester] 🎨 {config['sampler']} @ {config['steps']} steps | {width}x{height}")
    print(f"[GridTester] ⏱️  {duration:.1f}s | Avg: {eta_info['avg_duration']:.1f}s/job")
    
    if eta_info['hours'] > 0:
        print(f"[GridTester] 🕒 ETA: {eta_info['hours']}h {eta_info['minutes']}m (finish ~{eta_info['finish_formatted']})")
    elif eta_info['minutes'] > 0:
        print(f"[GridTester] 🕒 ETA: {eta_info['minutes']}m {eta_info['seconds']}s (finish ~{eta_info['finish_formatted']})")
    else:
        print(f"[GridTester] 🕒 ETA: {eta_info['seconds']}s (finish ~{eta_info['finish_formatted']})")
    
    print(f"{'='*80}")


def flush_batch_with_vae(pending_batch, vae, img_dir, existing_data, session_name, manifest_path=None, unique_id=None):
    """
    Flush a batch of latents by decoding them with VAE and saving.
    
    Args:
        pending_batch: List of (latent_samples, metadata) tuples
        vae: VAE model for decoding
        img_dir: Image output directory
        existing_data: Manifest data dict
        session_name: Session name for filenames
        manifest_path: Path to manifest.json file (optional, enables disk syncing)
        unique_id: Node unique ID for dashboard updates (optional, enables dashboard updates)
        
    Returns:
        int: Number of images saved
    """
    if not pending_batch:
        return 0
    
    import random
    
    saved_count = 0
    
    for latent_samples, meta in pending_batch:
        # Decode latent to image
        image = decode_latent_with_vae(vae, latent_samples)
        
        # Generate ID using same format as remote_vae
        ts = int(time.time() * 100000) + random.randint(0, 1000)
        meta["id"] = ts
        
        # Generate filename using webp format (like remote_vae)
        filename = f"img_{meta['id']}.webp"
        
        # Save image as webp
        filepath = os.path.join(img_dir, filename)
        image.save(filepath, quality=80)
        
        # Normalize denoise to int if it's 1.0 (like remote_vae)
        if meta.get("denoise") == 1.0:
            meta["denoise"] = 1
        
        # Update meta with file path and rejected flag
        meta.update({
            "file": f"/view?filename={filename}&type=output&subfolder=benchmarks/{session_name}/images",
            "rejected": False
        })
        
        # Update manifest - insert at beginning (like remote_vae)
        existing_data["items"].insert(0, meta)
        
        # Sync with disk manifest to preserve tags (like remote_vae) - only if manifest_path provided
        if manifest_path and os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    disk_manifest = json.load(f)
                
                # Create a lookup map for items currently in memory
                memory_items_map = {
                    i.get("id"): i 
                    for i in existing_data.get("items", []) 
                    if "id" in i
                }

                # Check every item on disk. If it exists in memory, copy the tags over.
                for disk_item in disk_manifest.get("items", []):
                    d_id = disk_item.get("id")
                    if d_id and d_id in memory_items_map:
                        local_item = memory_items_map[d_id]
                        
                        # PRESERVE TAGS: Copy these keys from disk to memory
                        if "favorited" in disk_item:
                            local_item["favorited"] = disk_item["favorited"]
                        if "rejected" in disk_item:
                            local_item["rejected"] = disk_item["rejected"]

            except Exception as e:
                print(f"[GridTester] ⚠️ Error syncing with disk manifest: {e}")

        # Save manifest to disk (like remote_vae) - only if manifest_path provided
        if manifest_path:
            with open(manifest_path, "w") as f:
                json.dump(existing_data, f, indent=4)
        
        # Send update to dashboard (like remote_vae) - only if unique_id provided
        if unique_id:
            try:
                from server import PromptServer
                if PromptServer:
                    # Get meta, use empty dict if not present
                    manifest_meta = existing_data.get("meta", {})
                    
                    PromptServer.instance.send_sync("ultimate_grid.update", {
                        "node": unique_id,
                        "session_name": session_name,
                        "new_items": [meta],
                        "meta": manifest_meta
                    })
            except (ImportError, KeyError):
                # Silently ignore dashboard update errors
                pass
        
        saved_count += 1
    
    print(f"[GridTester] 💾 Flushed {saved_count} images")
    return saved_count


def flush_batch_with_remote_vae(pending_batch, remote_vae_worker, existing_data, session_name):
    """
    Flush a batch of latents by sending them to remote VAE worker.
    
    Args:
        pending_batch: List of (latent_samples, metadata) tuples
        remote_vae_worker: RemoteVAEDecodeWorker instance
        existing_data: Manifest data dict (not used - worker handles manifest)
        session_name: Session name for filenames
        
    Returns:
        int: Number of images queued
    """
    if not pending_batch:
        return 0
    
    import random
    
    queued_count = 0
    
    for latent_samples, meta in pending_batch:
        # Generate ID using same format as old code
        ts = int(time.time() * 100000) + random.randint(0, 1000)
        meta["id"] = ts  # ← Set ID directly on meta dict
        
        # Queue the job - worker will create manifest entry
        # Pass the original meta dict, not a new one
        remote_vae_worker.add_job(
            latent_samples, 
            meta,  # ← Pass original meta, not a new dict
            meta["height"],
            meta["width"]
        )
        queued_count += 1
    
    print(f"[GridTester] 🌐 Queued {queued_count} images for remote VAE decoding")
    return queued_count