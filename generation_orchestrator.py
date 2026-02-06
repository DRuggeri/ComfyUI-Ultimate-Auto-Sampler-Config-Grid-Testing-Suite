"""
Generation Orchestrator - Main Entry Point
Coordinates the entire grid generation workflow
"""

import os
import json
import time
import re
import gc
import torch
import hashlib
import folder_paths

from .trigger_words import collect_unique_prompts_with_triggers, build_prompt_with_triggers
from .batch_encoding import batch_encode_prompts
from .manifest_utils import load_existing_manifest, save_manifest
from .model_loader import (
    load_checkpoint, load_loras, cleanup_model_references,
    get_latent_channels, load_loras_for_preencoding,
    print_incompatible_loras_summary
)
from .lora_utils import expand_lora_folder
from .image_generation import (
    generate_image, flush_batch_with_vae, flush_batch_with_remote_vae,
    create_image_metadata, calculate_eta, print_generation_progress
)
from .config_utils import sanitize_session_name
from .html_generator import get_html_template
from .conditioning_cache import ConditioningCache
from .remote_vae import RemoteVAEDecodeWorker, HF_ENDPOINTS

try:
    from server import PromptServer
except ImportError:
    PromptServer = None


def setup_session_directories(session_name):
    """
    Create session directories and return paths.
    
    Returns:
        dict: Paths dictionary with 'base', 'images', 'manifest'
    """
    # base_dir = os.path.join("benchmarks", session_name)
    # img_dir = os.path.join(base_dir, "images")
    
    base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
    img_dir = os.path.join(base_dir, "images")
    manifest_path = os.path.join(base_dir, "manifest.json")
    
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)
    
    return {
        "base": base_dir,
        "images": img_dir,
        "manifest": manifest_path
    }


def initialize_remote_vae(remote_vae_endpoint, img_dir, manifest_path, existing_data, session_name, unique_id):
    """
    Initialize remote VAE worker if enabled.
    
    Args:
        remote_vae_endpoint: Remote VAE endpoint URL OR model type (SD/SDXL/Flux/HunyuanVideo)
        img_dir: Image output directory
        manifest_path: Path to manifest file
        existing_data: Existing manifest data
        session_name: Session name
        unique_id: Unique ID for this node
    
    Returns:
        RemoteVAEDecodeWorker or None
    """
    if not remote_vae_endpoint or remote_vae_endpoint == "None":
        return None
    
    # ==== FIX: Convert model type to actual endpoint URL ====
    # If user selected a model type (SD/SDXL/Flux/HunyuanVideo), convert to URL
    if remote_vae_endpoint in ["SD", "SDXL", "Flux", "HunyuanVideo"]:
        actual_endpoint = HF_ENDPOINTS.get(remote_vae_endpoint)
        print(f"[GridTester] 🌐 Using {remote_vae_endpoint} endpoint: {actual_endpoint}")
    elif remote_vae_endpoint == "Auto (Experimental)":
        # For Auto mode, we can't initialize worker yet - return None
        # Worker will be initialized lazily in flush_batch when model type is detected
        print(f"[GridTester] 🌐 Auto mode selected - worker will initialize on first flush")
        return None
    else:
        # Assume it's a direct URL
        actual_endpoint = remote_vae_endpoint
        print(f"[GridTester] 🌐 Using custom endpoint: {actual_endpoint}")
    
    # ==== Create worker with actual endpoint URL ====
    worker = RemoteVAEDecodeWorker(
        endpoint=actual_endpoint,  # ← FIXED: Use resolved URL, not model type string
        img_dir=img_dir,
        manifest_path=manifest_path,
        existing_data=existing_data,
        session_name=session_name,
        unique_id=unique_id
    )
    print(f"[GridTester] 🌐 Remote VAE worker started")
    return worker


def calculate_clip_hash(clip_model):
    """Calculate a hash of the CLIP model for cache validation."""
    try:
        if hasattr(clip_model, 'state_dict'):
            state_dict = clip_model.state_dict()
            model_signature = str([(k, tuple(v.shape)) for k, v in list(state_dict.items())[:10]])
        elif hasattr(clip_model, 'cond_stage_model'):
            model_signature = str(type(clip_model.cond_stage_model))
        else:
            model_signature = str(type(clip_model))
        return hashlib.md5(model_signature.encode()).hexdigest()[:16]
    except:
        return "unknown"


def run_generation_loop(
    node_instance, ckpt_name, positive_text, negative_text, seed, denoise, vae_batch_size,
    overwrite_existing, flush_batch_every, configs_json, resolutions_json,
    session_name, unique_id, add_random_seeds_to_gens, lookup_and_append_lora_triggerwords,
    remote_vae_endpoint,
    optional_model=None, optional_clip=None, optional_vae=None,
    optional_positive=None, optional_negative=None, optional_latent=None
):
    """
    Main generation loop orchestrator.
    
    Coordinates:
    - Session setup
    - Config expansion  
    - Model/LoRA loading
    - Batch encoding
    - Image generation
    - Progress tracking
    - Manifest management
    
    Returns:
        tuple: (html_dashboard,)
    """
    # ==== SETUP ====
    session_name = sanitize_session_name(session_name)
    paths = setup_session_directories(session_name)
    existing_data = load_existing_manifest(paths["manifest"])
    existing_data["session_name"] = session_name
    
    # Parse configs and expand
    from .config_utils import (
        parse_json_with_error, parse_float_input, parse_prompt_input_nested,
        expand_configs, prepare_input_jobs
    )
    
    raw_configs = parse_json_with_error(configs_json, "configs")
    denoise_values = parse_float_input(denoise)
    resolutions = parse_json_with_error(resolutions_json, "resolutions")
    
    pos_prompts = parse_prompt_input_nested(positive_text)
    neg_prompts = parse_prompt_input_nested(negative_text)
    
    extra_seeds = []
    if add_random_seeds_to_gens > 0:
        import random
        extra_seeds = [random.randint(0, 2**32 - 1) for _ in range(add_random_seeds_to_gens)]
    
    expanded = expand_configs(raw_configs, pos_prompts, neg_prompts, denoise_values, seed, extra_seeds, ckpt_name)
    expanded.sort(key=lambda x: (x['model'], x['lora'], x['positive'], x['negative']))
    
    # ==== EXPAND LORA FOLDERS AND RANDOM SELECTIONS ====
    # Process all LoRA random syntax ONCE before generation loop
    # This ensures consistent LoRA selection and allows trigger words to be included
    print(f"[GridTester] 🎲 Expanding LoRA folders and random selections...")
    for conf in expanded:
        if conf["lora"] != "None":
            lora_parts = conf["lora"].split(" + ")
            expanded_parts = []
            
            for part in lora_parts:
                part = part.strip()
                # Check if this part uses random syntax: "folder/[count,strength]" or "folder/[count,strength,random]"
                if "[" in part and "]" in part:
                    # Expand using the config's seed for reproducibility (unless 'random' keyword is used)
                    expanded_lora = expand_lora_folder(part, seed=conf.get("seed"))
                    if expanded_lora:
                        # expand_lora_folder returns a string or list
                        if isinstance(expanded_lora, list):
                            expanded_parts.extend(expanded_lora)
                        else:
                            expanded_parts.append(expanded_lora)
                else:
                    # Regular LoRA path - keep as-is
                    expanded_parts.append(part)
            
            # Store expanded version in config
            conf["lora_expanded"] = " + ".join(expanded_parts) if expanded_parts else "None"
            # Also update the original lora field so trigger word lookup uses expanded version
            conf["lora"] = conf["lora_expanded"]
        else:
            conf["lora_expanded"] = "None"
    print(f"[GridTester] ✅ LoRA expansion complete")
    
    input_jobs = prepare_input_jobs(optional_latent, resolutions)
    total_jobs = len(expanded) * len(input_jobs)
    
    print(f"\n{'='*80}")
    print(f"[GridTester] 🚀 GENERATION START")
    print(f"[GridTester] 📋 {len(expanded)} configs × {len(input_jobs)} resolutions = {total_jobs} total jobs")
    print(f"{'='*80}\n")
    
    # ==== OPTIONAL CONDITIONING SETUP ====
    if optional_positive or optional_negative:
        pos_hash = hashlib.md5(str(optional_positive).encode()).hexdigest()[:16] if optional_positive else None
        neg_hash = hashlib.md5(str(optional_negative).encode()).hexdigest()[:16] if optional_negative else None
        MATCH_KEYS = [
            "sampler", "scheduler", "steps", "cfg", "lora", "denoise", "seed",
            "width", "height", "batch_idx", "model", "conditioning_pos_hash", "conditioning_neg_hash"
        ]
    else:
        pos_hash, neg_hash = None, None
        MATCH_KEYS = [
            "sampler", "scheduler", "steps", "cfg", "lora", "denoise", "seed",
            "width", "height", "positive", "negative", "batch_idx", "model"
        ]
    
    # ==== REMOTE VAE SETUP ====
    use_remote_vae = remote_vae_endpoint and remote_vae_endpoint != "None"
    
    # ==== PROGRESS BAR ====
    try:
        if PromptServer is not None:
            pbar = PromptServer.instance.progress_bar_pool.get_progress_bar(unique_id)
        else:
            pbar = None
    except:
        pbar = None
    
    # ==== STATE VARIABLES ====
    loaded_model, loaded_clip, loaded_vae = None, None, None
    patched_model, patched_clip = None, None
    cached_model_key = None
    cached_lora_key = None
    conditioning_cache = {"positive": {}, "negative": {}}
    incompatible_loras = {}
    pending_batch = []
    current_job = 0
    total_generated = 0
    skipped_count = 0
    job_durations = []
    eta_start_time = time.time()
    
    # Initialize remote VAE worker if needed (before pre-encoding stage)
    # This needs to happen regardless of pre-encoding status
    remote_vae_worker = None
    if use_remote_vae and expanded:
        remote_vae_worker = initialize_remote_vae(
            remote_vae_endpoint, 
            paths["images"], 
            paths["manifest"],
            existing_data,
            session_name,
            unique_id
        )
        if remote_vae_worker:
            print(f"[GridTester] 🌐 Remote VAE initialized")
    
    # ==== PRE-ENCODING STAGE ====
    # CRITICAL: Only pre-encode if all configs use the SAME model
    # Different models have different CLIP models, so we can't reuse encodings
    unique_models = set(conf["model"] for conf in expanded)
    
    if not (optional_positive and optional_negative) and expanded and len(unique_models) == 1:
        first_conf = expanded[0]
        target_model_name = first_conf["model"]
        
        print(f"[GridTester] ✅ Single model detected ({target_model_name}) - enabling pre-encoding")
        
        # Load model for pre-encoding
        loaded_model, loaded_clip, loaded_vae = load_checkpoint(
            target_model_name, ckpt_name, use_remote_vae,
            optional_model, optional_clip, optional_vae,
            optional_positive, optional_negative, None, None
        )
        
        # Load LoRAs if needed (use expanded version)
        if first_conf["lora_expanded"] != "None":
            patched_model, patched_clip = load_loras_for_preencoding(
                loaded_model, loaded_clip, first_conf["lora_expanded"]
            )
        else:
            patched_model, patched_clip = loaded_model, loaded_clip
        
        # Initialize conditioning cache
        clip_hash = calculate_clip_hash(patched_clip)
        cond_cache = ConditioningCache(paths["base"], clip_hash)
        
        # Collect unique prompts with triggers
        print(f"[GridTester] 🧠 Collecting unique prompts...")
        unique_positives, unique_negatives = collect_unique_prompts_with_triggers(
            expanded, lookup_and_append_lora_triggerwords
        )
        
        # Batch encode all prompts with clip_skip from first config
        clip_skip = first_conf.get("clip_skip", 0)
        if clip_skip != 0:
            print(f"[GridTester] 🔧 Using clip_skip={clip_skip}")
        
        conditioning_cache = batch_encode_prompts(
            patched_clip, unique_positives, unique_negatives, cond_cache, clip_skip
        )
        
        cached_model_key = target_model_name
        cached_lora_key = first_conf["lora_expanded"]
        latent_channels = get_latent_channels(loaded_model, optional_latent)
    elif len(unique_models) > 1:
        print(f"[GridTester] ⚠️ Multiple models detected ({len(unique_models)} different models) - pre-encoding DISABLED")
        print(f"[GridTester] ℹ️  Each model has a different CLIP - encoding will happen per-generation")
        print(f"[GridTester] ℹ️  This is slower but ensures correct CLIP encodings for each model")
        cond_cache = None
        latent_channels = 4
    else:
        print(f"[GridTester] ℹ️ Using optional conditioning, skipping pre-encoding")
        cond_cache = None
        latent_channels = 4
    
    # ==== MAIN GENERATION LOOP ====
    print(f"\n{'='*80}\n")
    
    for job in input_jobs:
        w, h = job["width"], job["height"]
        batch_idx = job["batch_idx"]
        
        for conf_idx, conf in enumerate(expanded):
            # ==== CHECK FOR INTERRUPT AT START OF EACH ITERATION ====
            try:
                import comfy.model_management as mm
                if mm.processing_interrupted():
                    print(f"\n[GridTester] 🛑 INTERRUPTED - Stopping all jobs")
                    print(f"[GridTester] ✅ Completed {total_generated}/{total_jobs} images before interrupt")
                    
                    # Flush any pending images
                    if pending_batch:
                        if use_remote_vae:
                            flush_batch_with_remote_vae(pending_batch, remote_vae_worker, existing_data, session_name)
                        else:
                            flush_batch_with_vae(pending_batch, loaded_vae, paths["images"], existing_data, session_name)
                        pending_batch = []
                    
                    # Wait for remote VAE if active
                    if remote_vae_worker:
                        print(f"[GridTester] 🌐 Waiting for remote VAE...")
                        remote_vae_worker.wait_completion()
                        remote_vae_worker.stop()
                    
                    # Save manifest
                    save_manifest(paths["manifest"], existing_data)
                    
                    # Cleanup
                    loaded_model, loaded_clip, loaded_vae = None, None, None
                    patched_model, patched_clip = None, None
                    conditioning_cache.clear()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    # Generate HTML with what we have
                    html = get_html_template(session_name, existing_data, unique_id)
                    return (html,)
            except:
                pass  # If interrupt checking fails, continue normally
            
            current_seed = conf["seed"]
            current_job += 1
            
            # Update progress bar
            if pbar:
                try:
                    pbar.update_absolute(current_job, total_jobs)
                except:
                    pass
            
            # Console progress
            progress_pct = int((current_job / total_jobs) * 100)
            print(f"[GridTester] 📊 {current_job}/{total_jobs} ({progress_pct}%) | "
                  f"{conf['sampler']} @ {conf['steps']} steps | {w}x{h}")
            
            # Build prompt with triggers
            actual_positive_prompt, lora_triggers = build_prompt_with_triggers(
                conf, lookup_and_append_lora_triggerwords
            )
            actual_negative_prompt = conf["negative"]
            
            # Check for existing match (overwrite mode)
            if overwrite_existing:
                match_index = node_instance.find_existing_match(
                    existing_data["items"], conf, w, h, current_seed, batch_idx, MATCH_KEYS
                )
                if match_index != -1:
                    old_item = existing_data["items"][match_index]
                    try:
                        old_fname_match = re.search(r'filename=([^&]+)', old_item["file"])
                        if old_fname_match:
                            old_file_path = os.path.join(paths["images"], old_fname_match.group(1))
                            if os.path.exists(old_file_path):
                                os.remove(old_file_path)
                    except:
                        pass
                    existing_data["items"].pop(match_index)
                    continue  # Skip generation, we're overwriting
            
            # Load model if switching
            target_model_name = conf["model"]
            if target_model_name != cached_model_key:
                if cached_model_key is not None:
                    patched_model, patched_clip = cleanup_model_references(
                        patched_model, patched_clip, conditioning_cache
                    )
                
                loaded_model, loaded_clip, loaded_vae = load_checkpoint(
                    target_model_name, ckpt_name, use_remote_vae,
                    optional_model, optional_clip, optional_vae,
                    optional_positive, optional_negative, loaded_clip, loaded_vae
                )
                
                cached_model_key = target_model_name
                cached_lora_key = None
                latent_channels = get_latent_channels(loaded_model, optional_latent)
                
                # Flag to trigger batch encoding after LoRAs are loaded
                model_switched = True
            else:
                model_switched = False
            
            # Load LoRAs if switching (use expanded version)
            current_lora_key = conf["lora_expanded"]
            if current_lora_key != cached_lora_key or patched_model is None:
                patched_model, patched_clip, should_skip = load_loras(
                    loaded_model, loaded_clip, conf["lora_expanded"],
                    target_model_name, incompatible_loras
                )
                
                if should_skip:
                    skipped_count += 1
                    continue
                
                cached_lora_key = current_lora_key
                
                # ==== FIX: Batch encode for THIS model when switching models/LoRAs ====
                # Even in multi-model mode, batch encode all prompts for the current
                # model to avoid encoding during the hot path (which causes CLIP thrashing)
                if model_switched or not conditioning_cache["positive"]:
                    # Collect all unique prompts for THIS model from remaining configs
                    model_unique_positives = set()
                    model_unique_negatives = set()
                    
                    # Look ahead at remaining configs for this model
                    for future_idx in range(conf_idx, len(expanded)):
                        future_conf = expanded[future_idx]
                        if future_conf["model"] == target_model_name:
                            # Build prompt with triggers
                            future_positive, _ = build_prompt_with_triggers(
                                future_conf, lookup_and_append_lora_triggerwords
                            )
                            model_unique_positives.add(future_positive)
                            model_unique_negatives.add(future_conf["negative"])
                    
                    if model_unique_positives:
                        print(f"[GridTester] 🧠 Batch encoding {len(model_unique_positives)} prompts for {target_model_name}")
                        
                        # Keep CLIP in VRAM during batch encoding
                        import comfy.model_management as mm_batch
                        mm_batch.load_models_gpu([patched_clip.patcher], force_patch_weights=True)
                        
                        # Get clip_skip from current config
                        clip_skip = conf.get("clip_skip", 0)
                        
                        # Batch encode all prompts for this model
                        for prompt in model_unique_positives:
                            if prompt not in conditioning_cache["positive"]:
                                # Apply clip_skip if needed
                                original_layer = None
                                if clip_skip != 0 and hasattr(patched_clip.cond_stage_model, 'clip_layer'):
                                    original_layer = patched_clip.cond_stage_model.clip_layer
                                    patched_clip.cond_stage_model.set_clip_options({"layer": clip_skip})
                                
                                tokens = patched_clip.tokenize(prompt)
                                cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                                conditioning_cache["positive"][prompt] = [[cond, {"pooled_output": pooled}]]
                                
                                # Restore layer
                                if original_layer is not None:
                                    patched_clip.cond_stage_model.set_clip_options({"layer": original_layer})
                        
                        for prompt in model_unique_negatives:
                            if prompt not in conditioning_cache["negative"]:
                                # Apply clip_skip if needed
                                original_layer = None
                                if clip_skip != 0 and hasattr(patched_clip.cond_stage_model, 'clip_layer'):
                                    original_layer = patched_clip.cond_stage_model.clip_layer
                                    patched_clip.cond_stage_model.set_clip_options({"layer": clip_skip})
                                
                                tokens = patched_clip.tokenize(prompt)
                                cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                                conditioning_cache["negative"][prompt] = [[cond, {"pooled_output": pooled}]]
                                
                                # Restore layer
                                if original_layer is not None:
                                    patched_clip.cond_stage_model.set_clip_options({"layer": original_layer})
                        
                        print(f"[GridTester] ✅ Encoded {len(conditioning_cache['positive'])} positive, {len(conditioning_cache['negative'])} negative")
                    
                    model_switched = False
                if cond_cache:
                    cond_cache.set_lora_config(conf['lora_expanded'])
            
            # Get conditioning (should always be in cache after batch encoding)
            if optional_positive:
                final_positive = optional_positive
            else:
                full_positive = actual_positive_prompt
                final_positive = conditioning_cache["positive"].get(full_positive)
                if final_positive is None:
                    # This should never happen since we batch encoded all prompts
                    raise RuntimeError(f"[GridTester] ❌ BUG: Encoding not found for: {full_positive[:50]}...")
            
            if optional_negative:
                final_negative = optional_negative
            else:
                final_negative = conditioning_cache["negative"].get(conf["negative"])
                if final_negative is None:
                    # This should never happen since we batch encoded all prompts
                    raise RuntimeError(f"[GridTester] ❌ BUG: Encoding not found for: {conf['negative'][:50]}...")
            
            # Generate image
            if job["latent"] is not None:
                latent_in = {"samples": job["latent"]["samples"].clone()}
            else:
                latent_in = {"samples": torch.zeros([1, latent_channels, h // 8, w // 8])}
            
            # ==== GENERATION WITH PROPER INTERRUPT HANDLING ====
            result_latent = None
            try:
                result_latent, duration = generate_image(
                    patched_model, current_seed, conf["steps"], conf["cfg"],
                    conf["sampler"], conf["scheduler"], final_positive, final_negative,
                    latent_in, conf["denoise"]
                )
                
                # Track ETA
                job_durations.append(duration)
                eta_info = calculate_eta(job_durations, current_job, total_jobs)
                if eta_info:
                    print_generation_progress(current_job, total_jobs, conf, w, h, duration, eta_info)
                
                # Create metadata
                meta = create_image_metadata(
                    conf, w, h, duration, current_seed, batch_idx,
                    actual_positive_prompt, actual_negative_prompt
                )
                if pos_hash or neg_hash:
                    meta["conditioning_pos_hash"] = pos_hash
                    meta["conditioning_neg_hash"] = neg_hash
                
                # Clone tensor to break reference chain
                pending_batch.append((result_latent["samples"].clone(), meta))
                total_generated += 1
            
            # ==== FIX: CATCH INTERRUPT SEPARATELY ====
            except Exception as e:
                # Check if this is an interrupt exception
                import comfy.model_management
                if isinstance(e, comfy.model_management.InterruptProcessingException):
                    print(f"\n[GridTester] 🛑 INTERRUPTED during generation - Stopping all jobs")
                    
                    # Clean up current generation
                    if result_latent is not None:
                        del result_latent
                    result_latent = None
                    
                    # Flush pending batch
                    if pending_batch:
                        if use_remote_vae:
                            flush_batch_with_remote_vae(pending_batch, remote_vae_worker, existing_data, session_name)
                        else:
                            flush_batch_with_vae(pending_batch, loaded_vae, paths["images"], existing_data, session_name)
                        pending_batch = []
                    
                    # Wait for remote VAE
                    if remote_vae_worker:
                        print(f"[GridTester] 🌐 Waiting for remote VAE...")
                        remote_vae_worker.wait_completion()
                        remote_vae_worker.stop()
                    
                    # Save manifest
                    save_manifest(paths["manifest"], existing_data)
                    
                    # Cleanup all models
                    loaded_model, loaded_clip, loaded_vae = None, None, None
                    patched_model, patched_clip = None, None
                    conditioning_cache.clear()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    # Generate HTML and return - this stops everything
                    html = get_html_template(session_name, existing_data, unique_id)
                    return (html,)
                else:
                    # Regular error - just skip this config
                    print(f"[GridTester] ❌ Generation failed: {e}")
                    if result_latent is not None:
                        del result_latent
                    continue
            # ==== END FIX ====
            
            # Clean up after each generation
            if result_latent is not None:
                del result_latent
            result_latent = None
            del latent_in
            latent_in = None
            
            # Periodic garbage collection
            if current_job % 10 == 0:
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            
            # Flush batch if needed
            threshold = vae_batch_size if flush_batch_every <= 0 else flush_batch_every
            if len(pending_batch) >= threshold:
                if use_remote_vae:
                    flush_batch_with_remote_vae(pending_batch, remote_vae_worker, existing_data, session_name)
                else:
                    flush_batch_with_vae(pending_batch, loaded_vae, paths["images"], existing_data, session_name)
                pending_batch = []
    
    # ==== FINALIZATION ====
    # Flush remaining
    if pending_batch:
        if use_remote_vae:
            flush_batch_with_remote_vae(pending_batch, remote_vae_worker, existing_data, session_name)
        else:
            flush_batch_with_vae(pending_batch, loaded_vae, paths["images"], existing_data, session_name)
    
    # Wait for remote VAE
    if remote_vae_worker:
        print(f"[GridTester] 🌐 Waiting for remote VAE...")
        remote_vae_worker.wait_completion()
        remote_vae_worker.stop()
    
    # Print summaries
    print_incompatible_loras_summary(incompatible_loras)
    
    if skipped_count > 0:
        print(f"[GridTester] ⏭️ Skipped {skipped_count} configs")
    
    # Save manifest
    save_manifest(paths["manifest"], existing_data)
    
    # Cleanup
    print(f"[GridTester] 🧹 Cleaning up...")
    loaded_model, loaded_clip, loaded_vae = None, None, None
    patched_model, patched_clip = None, None
    conditioning_cache.clear()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    # Generate HTML
    html = get_html_template(session_name, existing_data, unique_id)
    
    # Final summary
    if job_durations:
        total_elapsed = time.time() - eta_start_time
        total_hours = int(total_elapsed // 3600)
        total_minutes = int((total_elapsed % 3600) // 60)
        total_seconds = int(total_elapsed % 60)
        avg_per_job = sum(job_durations) / len(job_durations)
        
        print(f"\n{'='*80}")
        print(f"[GridTester] 🎉 COMPLETE!")
        print(f"[GridTester] ✅ {total_generated} images generated")
        print(f"[GridTester] ⏱️  {total_hours}h {total_minutes}m {total_seconds}s total")
        print(f"[GridTester] 📊 {avg_per_job:.1f}s average per job")
        print(f"{'='*80}\n")
    
    return (html,)