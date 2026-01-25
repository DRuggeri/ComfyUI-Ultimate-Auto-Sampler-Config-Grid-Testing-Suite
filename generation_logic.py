"""
Main generation loop for SamplerGridTester
Handles model loading, LoRA application, conditioning, and sampling
"""

import os
import json
import time
import random
import re
import gc
import torch
import folder_paths
import nodes
import comfy.utils
import comfy.sd
import comfy.samplers
import comfy.model_management
from PIL import Image
import numpy as np

from .remote_vae import (
    HF_ENDPOINTS,
    detect_model_type,
    RemoteVAEDecodeWorker
)
from .lora_utils import load_and_save_tags
from .config_utils import (
    parse_json_with_error,
    parse_float_input,
    parse_string_input,
    parse_prompt_input_nested,
    expand_configs,
    prepare_input_jobs,
    sanitize_session_name,
    parse_lora_definition
)
from .html_generator import get_html_template

try:
    from server import PromptServer
except ImportError:
    PromptServer = None


def merge_manifest_user_changes(manifest_path, existing_data):
    """
    Reload manifest and merge user changes (favorites, rejected, notes) to preserve them.
    This prevents losing user modifications when the manifest is saved during generation.
    
    Args:
        manifest_path: Path to the manifest.json file
        existing_data: The current manifest data dictionary to update
    """
    try:
        with open(manifest_path, "r") as f:
            current_manifest = json.load(f)
        
        # Create lookup dict of current items by ID
        current_items_dict = {
            item.get("id"): item 
            for item in current_manifest.get("items", []) 
            if "id" in item
        }
        
        # Update existing_data items with any user modifications
        for item in existing_data["items"]:
            item_id = item.get("id")
            if item_id in current_items_dict:
                current_item = current_items_dict[item_id]
                # Preserve user-modified fields
                if "favorite" in current_item:
                    item["favorite"] = current_item["favorite"]
                if "rejected" in current_item:
                    item["rejected"] = current_item["rejected"]
                if "notes" in current_item:
                    item["notes"] = current_item["notes"]
                    
    except FileNotFoundError:
        # First save, no existing manifest to merge
        pass
    except Exception as e:
        print(f"[GridTester] ⚠️ Warning: Could not merge manifest changes: {e}")


def run_generation_loop(node_instance, ckpt_name, positive_text, negative_text, seed, denoise, vae_batch_size,
                       overwrite_existing, flush_batch_every, configs_json, resolutions_json,
                       session_name, unique_id, add_random_seeds_to_gens, lookup_and_append_lora_triggerwords,
                       remote_vae_endpoint,
                       optional_model=None, optional_clip=None, optional_vae=None,
                       optional_positive=None, optional_negative=None, optional_latent=None):
    """
    Main generation loop that orchestrates the entire grid generation process.
    
    Args:
        node_instance: Reference to the SamplerGridTester instance for accessing helper methods
        ... (all other parameters from run_tests)
        
    Returns:
        Tuple containing the HTML dashboard
    """
    
    # Validation logging
    print(f"\n{'='*80}")
    print(f"[GridTester] 🔍 INPUT VALIDATION")
    print(f"{'='*80}")
    print(f"optional_model: {'✅' if optional_model else '❌'}")
    print(f"optional_clip: {'✅' if optional_clip else '❌'}")
    print(f"optional_vae: {'✅' if optional_vae else '❌'}")
    print(f"optional_positive: {'✅' if optional_positive else '❌'}")
    print(f"optional_negative: {'✅' if optional_negative else '❌'}")
    print(f"optional_latent: {'✅' if optional_latent else '❌'}")
    print(f"ckpt_name dropdown: {ckpt_name}")
    
    # Critical check
    if optional_model and not optional_vae:
        print(f"\n⚠️  WARNING: optional_model is connected but optional_vae is NOT!")
        print(f"   This may cause issues if the model has a non-standard architecture.")
        print(f"   The VAE will be loaded from: {ckpt_name}")
        print(f"   If this fails, connect optional_vae to match your model.\n")
    
    print(f"{'='*80}\n")
    
    incompatible_loras = {}
    skipped_count = 0
    total_generated = 0

    # Parse inputs
    try:
        raw_configs = parse_json_with_error(configs_json, "Configs JSON")
        resolutions = parse_json_with_error(resolutions_json, "Resolutions JSON")
        denoise_values = parse_float_input(str(denoise))
        pos_prompts = parse_prompt_input_nested(positive_text)
        neg_prompts = parse_prompt_input_nested(negative_text)
    except Exception as e: 
        raise ValueError(f"{e}")

    # Setup session directory
    session_name = sanitize_session_name(session_name)
    base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
    img_dir = os.path.join(base_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    manifest_path = os.path.join(base_dir, "manifest.json")

    # Load or create manifest
    existing_data = {"items": [], "meta": {}}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                d = json.load(f)
                if isinstance(d, list):
                    existing_data["items"] = d
                else:
                    existing_data = d
        except:
            pass

    existing_data["meta"] = {
        # Model settings
        "model": ckpt_name,
        "optional_model_connected": optional_model is not None,
        "optional_clip_connected": optional_clip is not None,
        "optional_vae_connected": optional_vae is not None,
        "optional_positive_connected": optional_positive is not None,
        "optional_negative_connected": optional_negative is not None,
        "optional_latent_connected": optional_latent is not None,
        
        # Prompts (full text, not truncated)
        "positive_text": positive_text,  # Full multi-line prompt
        "negative_text": negative_text,  # Full multi-line prompt
        "positive_prompts": pos_prompts,  # Parsed list of prompts
        "negative_prompts": neg_prompts,  # Parsed list of prompts
        
        # For backward compatibility / quick display
        "positive": "Multiple" if len(pos_prompts) > 1 else pos_prompts[0],
        "negative": "Multiple" if len(neg_prompts) > 1 else neg_prompts[0],
        
        # Generation settings
        "seed": seed,
        "denoise": denoise,  # String input (can be "1.0" or "0.8, 1.0")
        "denoise_values": denoise_values,  # Parsed list
        "vae_batch_size": vae_batch_size,
        "flush_batch_every": flush_batch_every,
        "add_random_seeds_to_gens": add_random_seeds_to_gens,
        "lookup_and_append_lora_triggerwords": lookup_and_append_lora_triggerwords,
        "remote_vae_endpoint": remote_vae_endpoint,
        "overwrite_existing": overwrite_existing,
        
        # Config JSONs (raw strings for exact reproducibility)
        "configs_json": configs_json,
        "resolutions_json": resolutions_json,
        
        # Parsed configs (for analysis)
        "raw_configs": raw_configs,  # Parsed config list
        "resolutions": resolutions,  # Parsed resolutions list
        
        # Session info
        "session_name": session_name,
        "updated": int(time.time()),
        "random_seed_map": existing_data.get("meta", {}).get("random_seed_map", {}),
        
        # Version tracking
        "generator_version": "2.0",  # Increment this when you make breaking changes
    }

    # Prepare input jobs
    input_jobs = prepare_input_jobs(optional_latent, resolutions)

    # Generate random seeds
    extra_seeds = []
    if add_random_seeds_to_gens > 0:
        seed_key = f"{seed}_{add_random_seeds_to_gens}"
        saved_seed_map = existing_data.get("meta", {}).get("random_seed_map", {})
        
        if seed_key in saved_seed_map:
            extra_seeds = saved_seed_map[seed_key]
            print(f"[GridTester] ♻️ Reusing {len(extra_seeds)} saved random seeds for base seed {seed}: {extra_seeds}")
        else:
            rng = random.Random(seed)
            for i in range(add_random_seeds_to_gens):
                extra_seeds.append(rng.randint(0, 0xffffffffffffffff))
            
            print(f"[GridTester] 🎲 Generated {len(extra_seeds)} new random seeds for base seed {seed}: {extra_seeds}")
            
            if "random_seed_map" not in existing_data["meta"]:
                existing_data["meta"]["random_seed_map"] = {}
            existing_data["meta"]["random_seed_map"][seed_key] = extra_seeds

    # Expand configurations
    expanded = expand_configs(raw_configs, pos_prompts, neg_prompts, denoise_values, seed, extra_seeds, ckpt_name)
    
    # CRITICAL FIX: If optional_model is connected, override all "model" fields that match ckpt_name to "Default"
    # This ensures that when a user connects optional_model, it takes precedence over the dropdown selection
    if optional_model:
        modified_count = 0
        for conf in expanded:
            # If the config model matches the dropdown value, change it to "Default"
            # This allows optional_model to be used instead of loading from disk
            if conf.get("model") == ckpt_name:
                conf["model"] = "Default"
                modified_count += 1
        
        if modified_count > 0:
            print(f"[GridTester] 🔄 Modified {modified_count} configs: model='{ckpt_name}' → 'Default' (using optional_model)")
    
    expanded.sort(key=lambda x: (x['model'], x['lora'], x['positive'], x['negative']))
    print(f"[GridTester] Processing {len(expanded) * len(input_jobs)} items...")

    # Track Total Job Progress
    total_jobs = len(expanded) * len(input_jobs)
    job_durations = []
    eta_start_time = time.time()

    current_job = 0
    try:
        from comfy.utils import ProgressBar
        pbar = ProgressBar(total_jobs)
    except:
        pbar = None
        
    # Initialize state variables
    cached_model_key, cached_lora_key = None, None
    cached_pos_key, cached_neg_key = None, None
    loaded_model, loaded_clip, loaded_vae = None, None, None
    patched_model, patched_clip = None, None
    final_positive, final_negative = None, None
    pending_batch = []
    latent_channels = 4

    # Define match keys based on whether optional conditioning is used
    if optional_positive or optional_negative:
        pos_hash = node_instance.hash_conditioning(optional_positive)
        neg_hash = node_instance.hash_conditioning(optional_negative)
        print(f"[GridTester] 🔐 Optional conditioning hashes:")
        print(f"  Positive: {pos_hash}")
        print(f"  Negative: {neg_hash}")
        
        MATCH_KEYS = [
            "sampler", "scheduler", "steps", "cfg", "lora", 
            "str_model", "str_clip", "denoise", "seed", 
            "width", "height", "batch_idx", "model",
            "conditioning_pos_hash", "conditioning_neg_hash"
        ]
    else:
        pos_hash = None
        neg_hash = None
        MATCH_KEYS = [
            "sampler", "scheduler", "steps", "cfg", "lora", 
            "str_model", "str_clip", "denoise", "seed", 
            "width", "height", "positive", "negative", "batch_idx", "model"
        ]

    # Setup remote VAE if enabled
    remote_vae_worker = None
    detected_model_type = None
    
    # Determine if remote VAE is enabled and which endpoint to use
    use_remote_vae = remote_vae_endpoint != "None"
    
    if use_remote_vae:
        print(f"[GridTester] 🌐 HuggingFace Remote VAE enabled - decoding will be offloaded")
        print(f"[GridTester] ⚠️ vae_batch_size and flush_batch_every are ignored in remote mode")
        
        # If user selected a specific endpoint, use that directly
        if remote_vae_endpoint in ["SD", "SDXL", "Flux", "HunyuanVideo"]:
            detected_model_type = remote_vae_endpoint
            print(f"[GridTester] 🌐 User selected model type: {detected_model_type}")
        # If Auto, try to detect
        elif remote_vae_endpoint == "Auto (Experimental)":
            if optional_model:
                early_latent_channels = node_instance.get_latent_channels(optional_model, optional_latent)
                detected_model_type = detect_model_type(optional_model, early_latent_channels)
                print(f"[GridTester] 🌐 Auto-detected model type: {detected_model_type}")
            elif optional_latent:
                early_latent_channels = optional_latent["samples"].shape[1]
                if early_latent_channels == 16:
                    detected_model_type = "Flux"
                    print(f"[GridTester] 🌐 Auto-detected Flux from 16 latent channels")
                else:
                    detected_model_type = "SDXL"
                    print(f"[GridTester] 🌐 Auto-detected SDXL from 4 latent channels (heuristic)")
            else:
                detected_model_type = None
                print(f"[GridTester] 🌐 Will auto-detect model type on first generation")

    # Define flush_batch function
    def flush_batch(batch_list):
        nonlocal total_generated, remote_vae_worker, detected_model_type
        
        if not batch_list:
            return
        
        # REMOTE VAE MODE
        if use_remote_vae:
            if remote_vae_worker is None:
                if detected_model_type is None:
                    # Try to detect from loaded_model if available
                    if loaded_model is not None:
                        print(f"[GridTester] 🌐 Detecting model type from loaded_model...")
                        detected_model_type = detect_model_type(loaded_model, latent_channels)
                    else:
                        print(f"[GridTester] 🌐 Lightweight detection from latent_channels={latent_channels}")
                        
                        if latent_channels == 16:
                            detected_model_type = "Flux"
                        else:
                            # Default to SD for 4 channels (SD1.5 is more common than SDXL)
                            detected_model_type = "SD"
                
                endpoint = HF_ENDPOINTS.get(detected_model_type)
                print(f"[GridTester] 🌐 Auto-detected model type: {detected_model_type}")
                print(f"[GridTester] 🌐 Using endpoint: {endpoint}")
                
                remote_vae_worker = RemoteVAEDecodeWorker(
                    endpoint, img_dir, manifest_path, existing_data, session_name, unique_id
                )
            
            # Queue all latents for async decoding
            for latent_batch, meta in batch_list:
                ts = int(time.time() * 100000) + random.randint(0, 1000)
                meta["id"] = ts
                latent_single = latent_batch
                
                print(f"[GridTester] 🌐 Queueing latent: {latent_single.shape}")
                
                remote_vae_worker.add_job(latent_single, meta, meta["height"], meta["width"])
                total_generated += 1
            
            return
        
        # NORMAL LOCAL VAE MODE
        latents_to_decode = torch.cat([x[0] for x in batch_list], dim=0)
        active_vae = optional_vae if optional_vae is not None else loaded_vae
        
        if active_vae is None:
            ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
            out = comfy.sd.load_checkpoint_guess_config(
                ckpt_path, output_vae=True, output_clip=False,
                embedding_directory=folder_paths.get_folder_paths("embeddings")
            )
            active_vae = out[2]

        decoded = active_vae.decode(latents_to_decode)
        new_items = []

        for i, img_tensor in enumerate(decoded):
            img_np = 255. * img_tensor.cpu().numpy()
            img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))
            meta = batch_list[i][1]
            ts = int(time.time() * 100000) + random.randint(0, 1000)
            filename = f"img_{ts}.webp"
            img.save(os.path.join(img_dir, filename), quality=80)
            meta.update({
                "id": ts, 
                "file": f"/view?filename={filename}&type=output&subfolder=benchmarks/{session_name}/images",
                "rejected": False
            })
            existing_data["items"].insert(0, meta)
            new_items.insert(0, meta)
            total_generated += 1

        # Save updated manifest
        # CRITICAL: Reload manifest first to preserve user changes (favorites, rejected) made during generation
        merge_manifest_user_changes(manifest_path, existing_data)
        
        # Now save with merged data
        with open(manifest_path, "w") as f:
            json.dump(existing_data, f, indent=4)
        
        # Send update to dashboard
        if PromptServer:
            PromptServer.instance.send_sync("ultimate_grid.update", {
                "node": unique_id,
                "session_name": session_name,
                "new_items": new_items,
                "meta": existing_data["meta"]
            })

    # Filter jobs to skip already-completed ones BEFORE pre-encoding
    if not overwrite_existing and existing_data["items"]:
        print(f"\n{'='*80}")
        print(f"[GridTester] 🔍 CHECKING FOR EXISTING RESULTS")
        print(f"{'='*80}\n")
        
        original_job_count = len(expanded) * len(input_jobs)
        filtered_expanded = []
        
        for conf in expanded:
            should_keep_config = False
            for job in input_jobs:
                w, h = job["width"], job["height"]
                batch_idx = job["batch_idx"]
                current_seed = conf["seed"]
                
                # Create a modified config that matches what will be saved
                # This includes calculating the full prompt with LoRA trigger words
                check_conf = conf.copy()
                
                # Add conditioning hashes if using optional conditioning
                if optional_positive or optional_negative:
                    check_conf["conditioning_pos_hash"] = pos_hash
                    check_conf["conditioning_neg_hash"] = neg_hash
                
                # Calculate prompt with LoRA triggers if enabled
                if lookup_and_append_lora_triggerwords and conf["lora"] != "None":
                    active_loras = parse_lora_definition(
                        conf["lora"], conf["str_model"], conf["str_clip"]
                    )
                    trigger_list = []
                    
                    for lora_def in active_loras:
                        lname, lstr_m, lstr_c = lora_def
                        try:
                            civitai_tags_list = load_and_save_tags(lname, force_fetch=False)
                            if len(civitai_tags_list) > 0:
                                for tags in civitai_tags_list:
                                    trigger_list.append(tags)
                        except Exception as e:
                            pass
                    
                    if trigger_list:
                        lora_triggers = ", ".join(trigger_list)
                        check_conf["positive"] = f"{conf['positive']}, {lora_triggers}"
                        if False:  # Set to True to enable debug logging
                            print(f"[GridTester] 🔍 Original prompt: {conf['positive'][:80]}...")
                            print(f"[GridTester] 🔍 With triggers: {check_conf['positive'][:80]}...")
                
                # Check if this specific job already exists
                match_index = node_instance.find_existing_match(
                    existing_data["items"], check_conf, w, h, current_seed, batch_idx, MATCH_KEYS
                )
                
                if match_index == -1:
                    # This job needs to be run
                    should_keep_config = True
                    break
            
            if should_keep_config:
                filtered_expanded.append(conf)
        
        skipped_job_count = original_job_count - (len(filtered_expanded) * len(input_jobs))
        print(f"[GridTester] ✂️ Filtered: {original_job_count} → {len(filtered_expanded) * len(input_jobs)} jobs")
        print(f"[GridTester] ⏭️  Skipped {skipped_job_count} already-completed jobs")
        print(f"{'='*80}\n")
        
        # Update expanded list and total_jobs
        expanded = filtered_expanded
        total_jobs = len(expanded) * len(input_jobs)
        
        # Early exit if nothing to do
        if total_jobs == 0:
            print(f"[GridTester] ✅ All jobs already completed! Nothing to generate.")
            print(f"[GridTester] 💡 Use 'overwrite_existing=True' to regenerate everything.")
            html = get_html_template(session_name, existing_data, unique_id)
            return (html,)
        
        # Update progress bar if it exists
        if pbar:
            try:
                pbar = ProgressBar(total_jobs)
            except:
                pass
    
    # Pre-encode conditioning if not using optional conditioning
    conditioning_cache = {"positive": {}, "negative": {}}
    
    if not (optional_positive and optional_negative):
        print(f"\n{'='*80}")
        print(f"[GridTester] 🧠 PRE-ENCODING CONDITIONING")
        print(f"{'='*80}\n")
        
        if len(expanded) > 0:
            first_conf = expanded[0]
            target_model_name = first_conf["model"]
            
            # Load model/clip for encoding
            if target_model_name == "Default":
                if optional_model:
                    print(f"[GridTester] ✅ Using optional_model for pre-encoding")
                    loaded_model = optional_model
                    
                    if optional_clip:
                        print(f"[GridTester] ✅ Using optional_clip for pre-encoding")
                        loaded_clip = optional_clip
                    else:
                        print(f"[GridTester] ⚠️ Loading CLIP from ckpt_name: {ckpt_name}")
                        ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                        out = comfy.sd.load_checkpoint_guess_config(
                            ckpt_path, output_vae=False, output_clip=True,
                            embedding_directory=folder_paths.get_folder_paths("embeddings")
                        )
                        loaded_clip = out[1]
                else:
                    print(f"[GridTester] 📦 Loading model/clip from ckpt_name: {ckpt_name}")
                    ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                    out = comfy.sd.load_checkpoint_guess_config(
                        ckpt_path, output_vae=False, output_clip=True,
                        embedding_directory=folder_paths.get_folder_paths("embeddings")
                    )
                    loaded_model, loaded_clip = out[0], out[1]
            else:
                print(f"[GridTester] 📦 Loading checkpoint for pre-encoding: {target_model_name}")
                ckpt_path = folder_paths.get_full_path("checkpoints", target_model_name)
                out = comfy.sd.load_checkpoint_guess_config(
                    ckpt_path, output_vae=False, output_clip=True,
                    embedding_directory=folder_paths.get_folder_paths("embeddings")
                )
                loaded_model, loaded_clip = out[0], out[1]
            
            # Apply first LoRA if any
            if first_conf["lora"] != "None":
                print(f"[GridTester] 🔧 Applying LoRA for pre-encoding: {first_conf['lora']}")
                curr_m, curr_c = loaded_model, loaded_clip
                active_loras = parse_lora_definition(
                    first_conf["lora"], first_conf["str_model"], first_conf["str_clip"]
                )
                
                for lora_def in active_loras:
                    lname, lstr_m, lstr_c = lora_def
                    path = folder_paths.get_full_path("loras", lname)
                    
                    if not path:
                        print(f"[GridTester] ⚠️ WARNING: LoRA not found: {lname}")
                        continue
                    
                    try:
                        lora_data = comfy.utils.load_torch_file(path)
                        curr_m, curr_c = comfy.sd.load_lora_for_models(
                            curr_m, curr_c, lora_data, lstr_m, lstr_c
                        )
                    except Exception as e:
                        print(f"[GridTester] ⚠️ Failed to load LoRA {lname}: {e}")
                        continue
                
                patched_model = curr_m
                patched_clip = curr_c
            else:
                patched_model = loaded_model
                patched_clip = loaded_clip
            
            # Collect all unique prompts
            print(f"[GridTester] 🧠 Collecting unique prompts...")
            unique_positives = set()
            unique_negatives = set()
            
            for conf in expanded:
                full_positive = conf["positive"]
                 
                if lookup_and_append_lora_triggerwords and conf["lora"] != "None":
                    active_loras = parse_lora_definition(
                        conf["lora"], conf["str_model"], conf["str_clip"]
                    )
                    trigger_list = []
                    
                    for lora_def in active_loras:
                        lname, lstr_m, lstr_c = lora_def
                        try:
                            civitai_tags_list = load_and_save_tags(lname, force_fetch=False)
                            if len(civitai_tags_list) > 0:
                                for tags in civitai_tags_list:
                                    trigger_list.append(tags)
                        except Exception as e:
                            pass
                    
                    if trigger_list:
                        lora_triggers = ", ".join(trigger_list)
                        full_positive = f"{conf['positive']}, {lora_triggers}"
                
                unique_positives.add(full_positive)
                unique_negatives.add(conf["negative"])
            
            print(f"[GridTester] 🧠 Found {len(unique_positives)} unique positive prompts")
            print(f"[GridTester] 🧠 Found {len(unique_negatives)} unique negative prompts")
            
            # Use ComfyUI's model management to prevent memory leak warnings during batch encoding
            # The model needs to stay loaded for the entire encoding loop
            with torch.no_grad():
                # Encode all positive prompts
                print(f"[GridTester] 🧠 Encoding {len(unique_positives)} unique positive prompts...")
                for i, prompt in enumerate(unique_positives):
                    try:
                        tokens = patched_clip.tokenize(prompt)
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        conditioning_cache["positive"][prompt] = [[cond, {"pooled_output": pooled}]]
                        
                        # Clean up intermediate variables to prevent memory buildup
                        del tokens
                        
                        # Periodic cleanup to prevent memory buildup during long encoding loops
                        if (i + 1) % 10 == 0:
                            gc.collect()
                            if torch.cuda.is_available():
                                torch.cuda.empty_cache()
                        
                        if (i + 1) % 10 == 0 or (i + 1) == len(unique_positives):
                            print(f"[GridTester]   Encoded {i+1}/{len(unique_positives)} positive prompts")
                    except Exception as e:
                        print(f"[GridTester] ⚠️ Failed to encode positive prompt: {e}")
                        conditioning_cache["positive"][prompt] = None
                
            # Encode all negative prompts
            print(f"[GridTester] 🧠 Encoding {len(unique_negatives)} unique negative prompts...")
            for i, prompt in enumerate(unique_negatives):
                try:
                    tokens = patched_clip.tokenize(prompt)
                    cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                    conditioning_cache["negative"][prompt] = [[cond, {"pooled_output": pooled}]]
                    
                    # Clean up intermediate variables to prevent memory buildup
                    del tokens
                    
                    # Periodic cleanup to prevent memory buildup during long encoding loops
                    if (i + 1) % 10 == 0:
                        gc.collect()
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    
                    if (i + 1) % 10 == 0 or (i + 1) == len(unique_negatives):
                        print(f"[GridTester]   Encoded {i+1}/{len(unique_negatives)} negative prompts")
                except Exception as e:
                    print(f"[GridTester] ⚠️ Failed to encode negative prompt: {e}")
                    conditioning_cache["negative"][prompt] = None
            
            # Final cleanup after all encoding is complete
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            print(f"[GridTester] ✅ All prompts pre-encoded!")
            print(f"[GridTester] 💾 Cache size: {len(conditioning_cache['positive'])} positive, {len(conditioning_cache['negative'])} negative")
            
            cached_model_key = target_model_name
            cached_lora_key = (first_conf["lora"], first_conf["str_model"], first_conf["str_clip"])
            cached_pos_key = None
            cached_neg_key = None
    else:
        print(f"[GridTester] ℹ️ Using optional conditioning, skipping pre-encoding")

    print(f"\n{'='*80}\n")

    # MAIN GENERATION LOOP
    for job in input_jobs:
        w, h = job["width"], job["height"]
        batch_idx = job["batch_idx"]
        
        for conf in expanded:
            current_seed = conf["seed"]
            
            # Update Progress Bar
            current_job += 1

            # Basic progress bar (just percentage - no custom text)
            if pbar:
                try:
                    pbar.update_absolute(current_job, total_jobs)
                except:
                    pass  # Ignore errors, console is enough

            # Detailed console output (this is what users see)
            progress_pct = int((current_job / total_jobs) * 100)
            print(f"[GridTester] 📊 {current_job}/{total_jobs} ({progress_pct}%) | "
                f"{conf['sampler']} @ {conf['steps']} steps | {w}x{h}")
            # Add conditioning hashes to config if using optional conditioning
            if optional_positive or optional_negative:
                conf["conditioning_pos_hash"] = pos_hash
                conf["conditioning_neg_hash"] = neg_hash
            
            # Track actual prompts used
            actual_positive_prompt = conf["positive"]
            actual_negative_prompt = conf["negative"]
            
            # Overwrite check - delete old item if it exists and we're in overwrite mode
            if overwrite_existing:
                match_index = node_instance.find_existing_match(
                    existing_data["items"], conf, w, h, current_seed, batch_idx, MATCH_KEYS
                )
                if match_index != -1:
                    # Overwrite mode: delete old item
                    old_item = existing_data["items"][match_index]
                    try:
                        old_fname_match = re.search(r'filename=([^&]+)', old_item["file"])
                        if old_fname_match:
                            old_file_path = os.path.join(img_dir, old_fname_match.group(1))
                            if os.path.exists(old_file_path):
                                os.remove(old_file_path)
                                print(f"[GridTester] Deleted old image: {old_fname_match.group(1)}")
                    except Exception as e:
                        print(f"[GridTester] Could not delete old image: {e}")
                    existing_data["items"].pop(match_index)


            # --- MODEL LOADING ---
            target_model_name = conf["model"]

            if target_model_name != cached_model_key:
                if target_model_name == "Default":
                    if optional_model:
                        print(f"[GridTester] ✅ Using optional_model")
                        loaded_model = optional_model
                        
                        if optional_clip:
                            print(f"[GridTester] ✅ Using optional_clip")
                            loaded_clip = optional_clip
                        else:
                            if not (optional_positive and optional_negative):
                                if loaded_clip is None:
                                    print(f"[GridTester] ⚠️ Loading CLIP from ckpt_name: {ckpt_name}")
                                    ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                                    out = comfy.sd.load_checkpoint_guess_config(
                                        ckpt_path, output_vae=False, output_clip=True,
                                        embedding_directory=folder_paths.get_folder_paths("embeddings")
                                    )
                                    loaded_clip = out[1]
                            else:
                                loaded_clip = None
                        
                        if optional_vae:
                            print(f"[GridTester] ✅ Using optional_vae")
                            loaded_vae = optional_vae
                        else:
                            if loaded_vae is None and not use_remote_vae:
                                print(f"[GridTester] ⚠️ Loading VAE from ckpt_name: {ckpt_name}")
                                ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                                out = comfy.sd.load_checkpoint_guess_config(
                                    ckpt_path, output_vae=True, output_clip=False,
                                    embedding_directory=folder_paths.get_folder_paths("embeddings")
                                )
                                loaded_vae = out[2]
                            elif use_remote_vae:
                                loaded_vae = None
                    else:
                        print(f"[GridTester] 📦 Loading from ckpt_name: {ckpt_name}")
                        ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                        if use_remote_vae:
                            out = comfy.sd.load_checkpoint_guess_config(
                                ckpt_path, output_vae=False, output_clip=True,
                                embedding_directory=folder_paths.get_folder_paths("embeddings")
                            )
                            loaded_model, loaded_clip = out[0], out[1]
                            loaded_vae = None
                        else:
                            out = comfy.sd.load_checkpoint_guess_config(
                                ckpt_path, output_vae=True, output_clip=True,
                                embedding_directory=folder_paths.get_folder_paths("embeddings")
                            )
                            loaded_model, loaded_clip, loaded_vae = out[:3]
                else:
                    print(f"[GridTester] 🔄 Switching to checkpoint: {target_model_name}")
                    ckpt_path = folder_paths.get_full_path("checkpoints", target_model_name)
                    if use_remote_vae:
                        out = comfy.sd.load_checkpoint_guess_config(
                            ckpt_path, output_vae=False, output_clip=True,
                            embedding_directory=folder_paths.get_folder_paths("embeddings")
                        )
                        loaded_model, loaded_clip = out[0], out[1]
                        loaded_vae = None
                    else:
                        out = comfy.sd.load_checkpoint_guess_config(
                            ckpt_path, output_vae=True, output_clip=True,
                            embedding_directory=folder_paths.get_folder_paths("embeddings")
                        )
                        loaded_model, loaded_clip, loaded_vae = out[:3]
                
                # Clean up old model references before loading new ones
                # CRITICAL: Must clear conditioning cache as it holds references to old CLIP tensors
                if cached_model_key is not None and cached_model_key != target_model_name:
                    print(f"[GridTester] 🧹 Switching models - clearing old references and cache...")
                    
                    # Clear the conditioning cache - it holds tensors from the old CLIP
                    conditioning_cache["positive"].clear()
                    conditioning_cache["negative"].clear()
                    print(f"[GridTester] 🧹 Cleared {len(conditioning_cache['positive']) + len(conditioning_cache['negative'])} cached encodings")
                    
                    # Delete old patched models
                    if patched_model is not None:
                        del patched_model
                    if patched_clip is not None:
                        del patched_clip
                    patched_model, patched_clip = None, None
                    
                    # Force garbage collection to free memory
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    print(f"[GridTester] 🧹 Memory cleanup complete")
                
                cached_model_key = target_model_name
                cached_lora_key, patched_model, patched_clip = None, None, None
                cached_pos_key, cached_neg_key = None, None
                
                latent_channels = node_instance.get_latent_channels(loaded_model, optional_latent)
                print(f"[GridTester] 📏 Latent channels: {latent_channels}")

            # --- LORA ---
            current_lora_key = (conf["lora"], conf["str_model"], conf["str_clip"])
            
            if current_lora_key != cached_lora_key or patched_model is None:
                patched_model, patched_clip = loaded_model, loaded_clip
                
                if conf["lora"] != "None":
                    active_loras = parse_lora_definition(
                        conf["lora"], conf["str_model"], conf["str_clip"]
                    )
                    
                    skip_config = False
                    for lora_def in active_loras:
                        lname, lstr_m, lstr_c = lora_def
                        lora_path = folder_paths.get_full_path("loras", lname)
                        
                        lora_key = f"{target_model_name}:{lname}"
                        if lora_key in incompatible_loras:
                            skip_config = True
                            break
                        
                        try:
                            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                            patched_model, patched_clip = comfy.sd.load_lora_for_models(
                                patched_model, patched_clip, lora, lstr_m, lstr_c
                            )
                        except Exception as e:
                            print(f"[GridTester] ❌ Failed to load LoRA {lname}: {e}")
                            incompatible_loras[lora_key] = (target_model_name, lname, str(e))
                            skip_config = True
                            break
                    
                    if skip_config:
                        skipped_count += 1
                        continue
                
                cached_lora_key = current_lora_key
            
            # Calculate trigger words OUTSIDE the cache check so they're always available
            lora_triggers = ""
            if conf["lora"] != "None" and lookup_and_append_lora_triggerwords:
                active_loras = parse_lora_definition(
                    conf["lora"], conf["str_model"], conf["str_clip"]
                )
                trigger_list = []
                for lora_def in active_loras:
                    lname, lstr_m, lstr_c = lora_def
                    try:
                        civitai_tags_list = load_and_save_tags(lname, force_fetch=False)
                        if len(civitai_tags_list) > 0:
                            for tags in civitai_tags_list:
                                trigger_list.append(tags)
                    except Exception as e:
                        print(f"[GridTester] Warning: Could not fetch trigger words for {lname}: {e}")
                
                lora_triggers = ", ".join(trigger_list)
                
                if lora_triggers:
                    print(f"[GridTester] Trigger words: {lora_triggers}")

            # --- CONDITIONING ---
            if optional_positive: 
                final_positive = optional_positive
                actual_positive_prompt = conf["positive"]
            else:
                full_positive = conf["positive"]
                if lora_triggers:
                    full_positive = f"{conf['positive']}, {lora_triggers}"
                
                actual_positive_prompt = full_positive
                
                if full_positive in conditioning_cache["positive"]:
                    cached_cond = conditioning_cache["positive"][full_positive]
                    
                    if cached_cond is not None:
                        final_positive = cached_cond
                    else:
                        print(f"[GridTester] ⚠️ Cache had None, encoding now...")
                        tokens = patched_clip.tokenize(full_positive)
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        final_positive = [[cond, {"pooled_output": pooled}]]
                        conditioning_cache["positive"][full_positive] = final_positive
                else:
                    print(f"[GridTester] ⚠️ Cache miss for positive: '{full_positive[:50]}...', encoding now...")
                    tokens = patched_clip.tokenize(full_positive)
                    cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                    final_positive = [[cond, {"pooled_output": pooled}]]
                    conditioning_cache["positive"][full_positive] = final_positive
                    if lora_triggers:
                        print(f"[GridTester] 📝 Prompt with triggers: {full_positive[:100]}...")

            if optional_negative:
                final_negative = optional_negative
                actual_negative_prompt = conf["negative"]
            else:
                actual_negative_prompt = conf["negative"]
                
                if conf["negative"] in conditioning_cache["negative"]:
                    cached_cond = conditioning_cache["negative"][conf["negative"]]
                    
                    if cached_cond is not None:
                        final_negative = cached_cond
                    else:
                        print(f"[GridTester] ⚠️ Cache had None, encoding now...")
                        tokens = patched_clip.tokenize(conf["negative"])
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        final_negative = [[cond, {"pooled_output": pooled}]]
                        conditioning_cache["negative"][conf["negative"]] = final_negative
                else:
                    print(f"[GridTester] ⚠️ Cache miss for negative: '{conf['negative'][:50]}...', encoding now...")
                    tokens = patched_clip.tokenize(conf["negative"])
                    cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                    final_negative = [[cond, {"pooled_output": pooled}]]
                    conditioning_cache["negative"][conf["negative"]] = final_negative

            # --- GENERATE ---
            if job["latent"] is not None: 
                latent_in = {"samples": job["latent"]["samples"].clone()}
            else: 
                latent_in = {"samples": torch.zeros([1, latent_channels, h // 8, w // 8])}

            try:
                t0 = time.time()
                result = nodes.common_ksampler(
                    model=patched_model, 
                    seed=current_seed, 
                    steps=conf["steps"], 
                    cfg=conf["cfg"],
                    sampler_name=conf["sampler"], 
                    scheduler=conf["scheduler"],
                    positive=final_positive, 
                    negative=final_negative, 
                    latent=latent_in, 
                    denoise=conf["denoise"]
                )
                duration = round(time.time() - t0, 3)
                
                # === Track and calculate ETA ===
                job_durations.append(duration)
                avg_duration = sum(job_durations) / len(job_durations)
                remaining_jobs = total_jobs - current_job
                estimated_seconds = avg_duration * remaining_jobs
                
                # Format times
                eta_hours = int(estimated_seconds // 3600)
                eta_minutes = int((estimated_seconds % 3600) // 60)
                eta_seconds = int(estimated_seconds % 60)
                eta_finish_time = time.time() + estimated_seconds
                eta_finish_formatted = time.strftime("%H:%M:%S", time.localtime(eta_finish_time))
                
                # Display with ETA
                progress_pct = int((current_job / total_jobs) * 100)
                print(f"\\n{'='*80}")
                print(f"[GridTester] 📊 Job {current_job}/{total_jobs} ({progress_pct}%)")
                print(f"[GridTester] 🎨 {conf['sampler']} @ {conf['steps']} steps | {w}x{h}")
                print(f"[GridTester] ⏱️  {duration:.1f}s | Avg: {avg_duration:.1f}s/job")
                
                if eta_hours > 0:
                    print(f"[GridTester] 🕒 ETA: {eta_hours}h {eta_minutes}m (finish ~{eta_finish_formatted})")
                elif eta_minutes > 0:
                    print(f"[GridTester] 🕒 ETA: {eta_minutes}m {eta_seconds}s (finish ~{eta_finish_formatted})")
                else:
                    print(f"[GridTester] 🕒 ETA: {eta_seconds}s (finish ~{eta_finish_formatted})")
                print(f"{'='*80}\\n")

                
                print("\n" + "=" * 80)

                meta = conf.copy()
                meta.update({
                    "width": w, 
                    "height": h, 
                    "duration": duration, 
                    "seed": current_seed, 
                    "batch_idx": batch_idx,
                    "positive": actual_positive_prompt,
                    "negative": actual_negative_prompt
                })
                
                if optional_positive or optional_negative:
                    meta["conditioning_pos_hash"] = pos_hash
                    meta["conditioning_neg_hash"] = neg_hash
                
                pending_batch.append((result[0]["samples"], meta))

            except comfy.model_management.InterruptProcessingException:
                raise 
            except Exception as e:
                print(f"[GridTester] Generation Failed (Skipping Config): {e}")
                continue

            # --- FLUSHING ---
            if use_remote_vae:
                flush_batch(pending_batch)
                pending_batch = []
            else:
                threshold = vae_batch_size if flush_batch_every <= 0 else flush_batch_every
                if len(pending_batch) >= threshold:
                    flush_batch(pending_batch)
                    pending_batch = []

    # --- FINAL SUMMARY ---
    if incompatible_loras:
        print(f"\n{'='*80}")
        print(f"[GridTester] 🚨 INCOMPATIBLE LORA SUMMARY")
        print(f"{'='*80}")
        for key, (model, lora, error) in incompatible_loras.items():
            print(f"  ❌ {lora}")
            print(f"     Model: {model}")
            print(f"     Likely cause: LoRA trained for different architecture")
            print(f"     Suggestion: Check if LoRA is SD1.5/SDXL/SD3/Flux compatible")
            print()
        print(f"{'='*80}\n")
    
    if skipped_count > 0:
        print(f"[GridTester] ⏭️ Skipped {skipped_count} configs due to incompatible LoRAs.")
    print(f"[GridTester] ✅ Generated {total_generated} new images.")

    # Flush any remaining items
    flush_batch(pending_batch)
    
    # Wait for remote VAE worker to finish if enabled
    if use_remote_vae and remote_vae_worker:
        print(f"[GridTester] 🌐 Waiting for remote VAE decoding to complete...")
        remote_vae_worker.wait_completion()
        remote_vae_worker.stop()
        print(f"[GridTester] 🌐 Remote VAE decoding complete! Decoded {remote_vae_worker.total_decoded} images")
    
    # Save final manifest
    # CRITICAL: Reload manifest first to preserve user changes (favorites, rejected) made during generation
    merge_manifest_user_changes(manifest_path, existing_data)
    
    # Now save with merged data
    with open(manifest_path, "w") as f:
        json.dump(existing_data, f, indent=4)
    
    # Clean up model references to prevent memory leaks
    # This is critical for ComfyUI's model management system
    print(f"[GridTester] 🧹 Cleaning up model references...")
    loaded_model = None
    loaded_clip = None
    loaded_vae = None
    patched_model = None
    patched_clip = None
    final_positive = None
    final_negative = None
    conditioning_cache.clear()
    
    # Force garbage collection to ensure cleanup
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    html = get_html_template(session_name, existing_data, unique_id)


    if job_durations:
        total_elapsed = time.time() - eta_start_time
        total_hours = int(total_elapsed // 3600)
        total_minutes = int((total_elapsed % 3600) // 60)
        total_seconds = int(total_elapsed % 60)
        avg_per_job = sum(job_durations) / len(job_durations)
        
        print(f"\\n{'='*80}")
        print(f"[GridTester] 🎉 ALL JOBS COMPLETE!")
        print(f"[GridTester] ✅ Generated {total_generated} images")
        print(f"[GridTester] ⏱️  Total: {total_hours}h {total_minutes}m {total_seconds}s")
        print(f"[GridTester] 📊 Average: {avg_per_job:.1f}s per job")
        print(f"{'='*80}\\n")


    return (html,)