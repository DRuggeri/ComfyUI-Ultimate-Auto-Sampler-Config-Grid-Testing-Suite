"""
Generation Orchestrator - Main Entry Point
Coordinates the entire grid generation workflow
"""

import os
import json
import time
import re
import gc
import threading
import torch
import hashlib
import folder_paths
import comfy.sd  # Required for async workers
from comfy.model_management import InterruptProcessingException

from .trigger_words import collect_unique_prompts_with_triggers, build_prompt_with_triggers, clear_trigger_caches
from .batch_encoding import batch_encode_prompts, encode_prompt_with_combinators
from .manifest_utils import load_existing_manifest, save_manifest
from .model_loader import (
    load_checkpoint, load_loras, cleanup_model_references,
    get_latent_channels, load_loras_for_preencoding,
    print_incompatible_loras_summary, load_diffusion_model_and_clip,
    load_vae_by_name
)
from .lora_utils import expand_lora_folder
from .image_generation import (
    generate_image, flush_batch_with_vae, flush_batch_with_remote_vae,
    create_image_metadata, decode_latent_with_vae, calculate_eta, print_generation_progress
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
    """Create session directories and return paths."""
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
    """Initialize remote VAE worker if enabled."""
    if not remote_vae_endpoint or remote_vae_endpoint == "None":
        return None
    
    if remote_vae_endpoint in ["SD", "SDXL", "Flux", "HunyuanVideo"]:
        actual_endpoint = HF_ENDPOINTS.get(remote_vae_endpoint)
        print(f"[GridTester] 🌐 Using {remote_vae_endpoint} endpoint: {actual_endpoint}")
    elif remote_vae_endpoint == "Auto (Experimental)":
        print(f"[GridTester] 🌐 Auto mode selected - worker will initialize on first flush")
        return None
    else:
        actual_endpoint = remote_vae_endpoint
        print(f"[GridTester] 🌐 Using custom endpoint: {actual_endpoint}")
    
    worker = RemoteVAEDecodeWorker(
        endpoint=actual_endpoint,
        img_dir=img_dir,
        manifest_path=manifest_path,
        existing_data=existing_data,
        session_name=session_name,
        unique_id=unique_id
    )
    print(f"[GridTester] 🌐 Remote VAE worker started")
    return worker


REMOTE_VAE_PREFIX = "remote:"

def is_remote_vae(vae_string):
    """Check if a VAE value is a per-config remote URL (e.g. 'remote:http://...')."""
    return isinstance(vae_string, str) and vae_string.startswith(REMOTE_VAE_PREFIX)

def extract_remote_vae_url(vae_string):
    """Extract the URL from a remote VAE string like 'remote:http://...'."""
    url = vae_string[len(REMOTE_VAE_PREFIX):]
    if not url:
        raise ValueError(
            "[GridTester] Per-config remote VAE URL is empty.\n"
            "Please provide a valid endpoint URL in the config builder's VAE section."
        )
    return url


def _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                         per_config_remote_workers, use_remote_vae, remote_vae_worker,
                         loaded_vae, paths, existing_data, session_name, manifest_path, unique_id,
                         config_overrides_vae=False):
    """Flush pending batch using the appropriate VAE decode method.

    Handles three-way dispatch:
      1. Per-config remote VAE (current_vae_is_remote) — uses per-config worker
      2. Global remote VAE (use_remote_vae) — uses global remote_vae_worker
         ONLY when config_overrides_vae is False (config VAE is "Default")
      3. Local VAE — uses loaded_vae for local decode

    Config Builder VAE settings take priority over the sampler node's
    remote_vae_endpoint when a config explicitly sets a non-Default VAE.
    """
    if not pending_batch:
        return
    if current_vae_is_remote and current_remote_vae_url:
        worker = per_config_remote_workers.get(current_remote_vae_url)
        if worker:
            flush_batch_with_remote_vae(pending_batch, worker, existing_data, session_name)
        else:
            print(f"[GridTester] ⚠️ No remote worker for {current_remote_vae_url}, falling back to local VAE")
            flush_batch_with_vae(pending_batch, loaded_vae, paths["images"], existing_data, session_name, manifest_path, unique_id)
    elif not config_overrides_vae and use_remote_vae and remote_vae_worker:
        flush_batch_with_remote_vae(pending_batch, remote_vae_worker, existing_data, session_name)
    else:
        flush_batch_with_vae(pending_batch, loaded_vae, paths["images"], existing_data, session_name, manifest_path, unique_id)


def _cleanup_per_config_remote_workers(per_config_remote_workers):
    """Shut down all per-config remote VAE workers."""
    for url, worker in per_config_remote_workers.items():
        try:
            print(f"[GridTester] 🌐 Waiting for per-config remote VAE ({url})...")
            worker.wait_completion()
            worker.stop()
        except Exception as e:
            print(f"[GridTester] ⚠️ Error stopping per-config remote worker ({url}): {e}")


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


def check_if_job_completed(existing_items, conf, seed, width, height, batch_idx, positive_prompt, negative_prompt, has_optional_inputs=False):
    """Independent check to see if a specific generation job already exists.

    When has_optional_inputs is True, we cannot reliably detect changes from
    upstream nodes (models, LoRAs, conditionings, latents), so we disable
    skip detection entirely and return -1 (no match) to force re-generation.
    """
    # When optional inputs are connected, we can't reliably match on model,
    # lora, prompts, or latents because those may come from upstream nodes
    # whose changes we can't detect. Disable skip detection entirely.
    if has_optional_inputs:
        return -1

    FLOAT_TOLERANCE = 0.0001

    for idx, item in enumerate(existing_items):
        if item.get("seed") != seed: continue
        if item.get("width") != width: continue
        if item.get("height") != height: continue
        if item.get("batch_idx", 0) != batch_idx: continue
        if item.get("sampler") != conf["sampler"]: continue
        if item.get("scheduler") != conf["scheduler"]: continue

        # Check attention mode (default = no attention_mode key or "default")
        item_attn = item.get("attention_mode", "default")
        conf_attn = conf.get("attention_mode", "default")
        if item_attn != conf_attn: continue

        try:
            if abs(float(item.get("steps")) - float(conf["steps"])) > FLOAT_TOLERANCE: continue
            if abs(float(item.get("cfg")) - float(conf["cfg"])) > FLOAT_TOLERANCE: continue
            if abs(float(item.get("denoise")) - float(conf["denoise"])) > FLOAT_TOLERANCE: continue
        except (ValueError, TypeError):
            continue

        # Standard matching - check model, lora, and prompts
        if item.get("model") != conf["model"]: continue
        if item.get("positive", "").strip() != positive_prompt.strip(): continue
        if item.get("negative", "").strip() != negative_prompt.strip(): continue

        item_lora = item.get("lora", "None")
        conf_lora = conf.get("lora_expanded", "None")
        if item_lora != conf_lora: continue

        # Check model_type and text_encoders — different text encoders produce
        # different conditioning even with the same model file, so they must
        # NOT be considered duplicate jobs
        item_model_type = item.get("model_type", "checkpoint")
        conf_model_type = conf.get("model_type", "checkpoint")
        if item_model_type != conf_model_type: continue

        item_te = item.get("text_encoders", [])
        conf_te = conf.get("text_encoders", [])
        if item_te != conf_te: continue

        # Check clip_type — different clip types produce different conditioning
        item_clip_type = item.get("clip_type", "stable_diffusion")
        conf_clip_type = conf.get("clip_type", "stable_diffusion")
        if item_clip_type != conf_clip_type: continue

        # Check clip_skip — different clip_skip values produce different conditioning
        item_clip_skip = item.get("clip_skip", 0)
        conf_clip_skip = conf.get("clip_skip", 0)
        if item_clip_skip != conf_clip_skip: continue

        # Check VAE — different VAEs produce different decoded images
        item_vae = item.get("vae", "Default")
        conf_vae = conf.get("vae", "Default")
        if item_vae != conf_vae: continue

        return idx

    return -1


def get_model_cache_key(conf):
    """Generate a cache key that uniquely identifies the model+clip combination."""
    model_type = conf.get("model_type", "checkpoint")
    if model_type == "checkpoint":
        return conf["model"]
    else:
        te_key = "|".join(sorted(conf.get("text_encoders", [])))
        return f"{conf['model']}::{model_type}::{te_key}"


def load_model_by_type(conf, ckpt_name, use_remote_vae, optional_model, optional_clip, optional_vae,
                       optional_positive, optional_negative, loaded_clip, loaded_vae, model_cache):
    """Dispatch to correct loader based on model_type in config."""
    model_type = conf.get("model_type", "checkpoint")
    target = conf["model"]

    if model_type == "checkpoint":
        return load_checkpoint(
            target, ckpt_name, use_remote_vae,
            optional_model, optional_clip, optional_vae,
            optional_positive, optional_negative,
            loaded_clip, loaded_vae, model_cache=model_cache
        )
    else:
        # diffusion_model or gguf
        return load_diffusion_model_and_clip(
            model_name=target,
            model_type=model_type,
            text_encoder_paths=conf.get("text_encoders", []),
            clip_type_str=conf.get("clip_type", "stable_diffusion"),
            gguf_options=conf.get("gguf_options"),
            use_remote_vae=use_remote_vae,
            optional_model=optional_model,
            optional_clip=optional_clip,
            optional_vae=optional_vae,
            model_cache=model_cache
        )


def run_generation_loop(
    self,
    ckpt_name, positive_text, negative_text, seed, denoise, vae_batch_size,
    overwrite_existing, flush_batch_every, configs_json, resolutions_json,
    session_name, unique_id, add_random_seeds_to_gens, lora_triggerwords_mode,
    remote_vae_endpoint, save_conditioning_cache_to_file, enable_model_cache,
    optional_model, optional_clip, optional_vae,
    optional_positive, optional_negative, optional_latent,
    distribution_config=None,
    session_settings=None
):
    """Main generation loop orchestrator."""

    # Clear stale trigger word caches from previous runs (within same ComfyUI session).
    # Without this, @lru_cache and _build_prompt_cache can serve outdated results
    # if loras_tags.json was updated by a CivitAI fetch in a prior run.
    clear_trigger_caches()

    from .model_cache import ModelCache

    # Initialize Model Cache (or disable completely if user requested)
    if enable_model_cache:
        model_cache = ModelCache(
            max_models=1,        # Adjust for your VRAM
            max_lora_sets=2,    # Adjust for your VRAM
            max_lora_files=30,   # Adjust for your VRAM
            enable_preload=True,   # Preloading enabled when cache is on
            async_preload=True,    # Always async when preloading
            cache_device='cpu',
            verbose=True
        )
    else:
        # Completely disable entire cache system
        print("[GridTester] ⚠️ Model cache DISABLED - all models will load from disk (slower but saves RAM/VRAM)")
        model_cache = None

    # ==== SETUP ====
    session_name = sanitize_session_name(session_name)
    paths = setup_session_directories(session_name)
    existing_data = load_existing_manifest(paths["manifest"])
    existing_data["session_name"] = session_name
    
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
    expanded.sort(key=lambda x: (x.get('model_type', 'checkpoint'), x['model'], tuple(x.get('text_encoders', [])), x.get('vae', 'Default'), x['lora'], x.get('attention_mode', 'default'), x['positive'], x['negative']))
    
    # ==== EXPAND LORA FOLDERS ====
    print(f"[GridTester] 🎲 Expanding LoRA folders and random selections...")
    for conf in expanded:
        if conf["lora"] != "None":
            lora_parts = conf["lora"].split(" + ")
            expanded_parts = []
            for part in lora_parts:
                part = part.strip()
                if "[" in part and "]" in part:
                    expanded_lora = expand_lora_folder(part, seed=conf.get("seed"))
                    if expanded_lora:
                        if isinstance(expanded_lora, list):
                            expanded_parts.extend(expanded_lora)
                        else:
                            expanded_parts.append(expanded_lora)
                else:
                    expanded_parts.append(part)
            conf["lora_expanded"] = " + ".join(expanded_parts) if expanded_parts else "None"
            conf["lora"] = conf["lora_expanded"]
        else:
            conf["lora_expanded"] = "None"
    print(f"[GridTester] ✅ LoRA expansion complete")

    # ==== VAE VALIDATION FOR NON-CHECKPOINT MODELS ====
    # Only error if non-checkpoint model has no VAE source (no optional_vae AND no per-config VAE)
    use_remote_vae = remote_vae_endpoint and remote_vae_endpoint != "None"
    needs_vae = any(
        c.get("model_type", "checkpoint") != "checkpoint"
        and c.get("vae", "Default") == "Default"
        for c in expanded
    )
    if needs_vae and not use_remote_vae and optional_vae is None:
        raise ValueError(
            "GGUF and diffusion models do not include a bundled VAE.\n"
            "You must either:\n"
            "  1. Connect a VAE to the optional_vae input on the sampler node, or\n"
            "  2. Enable remote VAE decoding via remote_vae_endpoint, or\n"
            "  3. Set a specific VAE in the config builder for those configs\n"
        )

    # ==== REGISTER SMART CACHE SCHEDULE ====
    if model_cache:
        model_cache.register_schedule(expanded)

    input_jobs = prepare_input_jobs(optional_latent, resolutions)

    # Count total jobs: configs with per-config resolutions provide their own
    # width/height and don't multiply with the global input_jobs.
    configs_with_res = sum(1 for c in expanded if c.get("resolution") is not None)
    configs_without_res = len(expanded) - configs_with_res
    total_jobs = configs_with_res + (configs_without_res * len(input_jobs))

    print(f"{'='*80}")
    print(f"[GridTester] 🚀 GENERATION START")
    if configs_with_res > 0:
        print(f"[GridTester] 📋 {configs_with_res} configs with per-config resolutions + "
              f"{configs_without_res} configs × {len(input_jobs)} resolutions = {total_jobs} total jobs")
    else:
        print(f"[GridTester] 📋 {len(expanded)} configs × {len(input_jobs)} resolutions = {total_jobs} total jobs")
    print(f"{'='*80}")
    
    # ==== OPTIONAL INPUT DETECTION ====
    # Track whether any optional inputs are connected - this affects skip/resume logic
    has_optional_inputs = any([
        optional_model is not None,
        optional_clip is not None,
        optional_vae is not None,
        optional_positive is not None,
        optional_negative is not None,
        optional_latent is not None
    ])

    if has_optional_inputs and not overwrite_existing:
        print(f"[GridTester] ⚠️ Optional inputs connected — job skip/resume DISABLED.")
        print(f"[GridTester] ⚠️ Changes to upstream nodes (models, LoRAs, prompts, latents) connected via optional inputs")
        print(f"[GridTester] ⚠️ cannot be automatically detected, so all jobs will be re-generated.")
        print(f"[GridTester] ⚠️ To use resume mode, disconnect optional inputs and use the built-in config fields instead.")

    # ==== DISTRIBUTED PROCESSING BRANCH ====
    # If distribution_config is provided and enabled, delegate to distributed processing
    # which handles the generation loop, then jump to finalization
    dist_enabled = (
        distribution_config
        and isinstance(distribution_config, dict) 
        and distribution_config.get("enabled")
        and distribution_config.get("worker_urls")
    )

    if distribution_config:
        print(f"[GridTester] 🌐 Distribution check: type={type(distribution_config).__name__}, "
              f"enabled={distribution_config.get('enabled') if isinstance(distribution_config, dict) else 'N/A'}, "
              f"workers={len(distribution_config.get('worker_urls', [])) if isinstance(distribution_config, dict) else 'N/A'}, "
              f"dist_enabled={dist_enabled}")
    else:
        print(f"[GridTester] ℹ️ distribution_config is None/empty, running normal generation")

    if dist_enabled:
        print(f"[GridTester] 🌐 ENTERING DISTRIBUTED MODE with {len(distribution_config.get('worker_urls', []))} worker(s)")
        # Warn if upscaling is enabled — not yet supported in distributed mode
        if session_settings and session_settings.get("upscaling", {}).get("enabled", False):
            print(f"[GridTester] ⚠️ WARNING: Upscaling is enabled but not supported in distributed mode. Workers will generate images without upscaling.")
        return _run_distributed_generation(
            self, distribution_config, expanded, input_jobs, existing_data,
            overwrite_existing, has_optional_inputs, lora_triggerwords_mode,
            session_name, paths, unique_id, total_jobs, seed, ckpt_name,
            positive_text, negative_text, vae_batch_size, configs_json,
            resolutions_json, flush_batch_every, use_remote_vae,
            remote_vae_endpoint, save_conditioning_cache_to_file,
            enable_model_cache, optional_model, optional_clip, optional_vae,
            optional_positive, optional_negative, optional_latent, model_cache,
            session_settings=session_settings
        )

    # ==== OPTIONAL CONDITIONING SETUP ====
    if optional_positive or optional_negative:
        pos_hash = hashlib.md5(str(optional_positive).encode()).hexdigest()[:16] if optional_positive else None
        neg_hash = hashlib.md5(str(optional_negative).encode()).hexdigest()[:16] if optional_negative else None
    else:
        pos_hash, neg_hash = None, None

    # ==== REMOTE VAE SETUP (use_remote_vae already defined above for VAE validation) ====

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
    cached_lora_cache_key = None
    cached_vae_key = None  # Track which VAE is currently loaded
    default_model_vae = None  # Track the model's bundled/default VAE for reverting
    conditioning_cache = {"positive": {}, "negative": {}}
    incompatible_loras = {}
    pending_batch = []
    current_job = 0
    total_generated = 0
    gen_index_offset = len(existing_data.get("items", []))  # Sequential index for deterministic sort ordering
    skipped_count = 0
    job_durations = []
    eta_start_time = time.time()
    
    # Initialize remote VAE worker
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
    
    # Per-config remote VAE state
    per_config_remote_workers = {}   # Keyed by URL, reused across configs
    current_vae_is_remote = False
    current_remote_vae_url = None
    config_overrides_vae = False  # True when config explicitly sets a non-Default VAE (overrides sampler node's remote_vae_endpoint)

    # ==== PRE-ENCODING STAGE ====
    unique_model_keys = set(get_model_cache_key(conf) for conf in expanded)

    if not (optional_positive and optional_negative) and expanded and len(unique_model_keys) == 1:
        first_conf = expanded[0]
        target_model_name = first_conf["model"]

        print(f"[GridTester] ✅ Single model detected ({target_model_name}) - enabling pre-encoding")

        loaded_model, loaded_clip, loaded_vae = load_model_by_type(
            first_conf, ckpt_name, use_remote_vae,
            optional_model, optional_clip, optional_vae,
            optional_positive, optional_negative, None, None, model_cache=model_cache
        )

        # VAE fallback for non-checkpoint models
        if loaded_vae is None and optional_vae is not None:
            loaded_vae = optional_vae
        # Remember this model's default VAE for reverting later
        default_model_vae = loaded_vae

        # Per-config VAE: if first config specifies a VAE, load it
        # Config Builder VAE settings take priority over sampler node's remote_vae_endpoint
        target_vae = first_conf.get("vae", "Default")
        if target_vae != "Default":
            config_overrides_vae = True
            if is_remote_vae(target_vae):
                url = extract_remote_vae_url(target_vae)
                current_vae_is_remote = True
                current_remote_vae_url = url
                print(f"[GridTester] 🌐 Using per-config remote VAE: {url}")
                if url not in per_config_remote_workers:
                    per_config_remote_workers[url] = RemoteVAEDecodeWorker(
                        endpoint=url, img_dir=paths["images"],
                        manifest_path=paths["manifest"],
                        existing_data=existing_data,
                        session_name=session_name, unique_id=unique_id
                    )
            else:
                print(f"[GridTester] 🎨 Loading per-config VAE: {target_vae}")
                loaded_vae = load_vae_by_name(target_vae)
            cached_vae_key = target_vae
        else:
            cached_vae_key = "Default"
        
        if first_conf["lora_expanded"] != "None":
            patched_model, patched_clip = load_loras_for_preencoding(
                loaded_model, loaded_clip, first_conf["lora_expanded"]
            )
        else:
            patched_model, patched_clip = loaded_model, loaded_clip
        
        clip_hash = calculate_clip_hash(patched_clip)
        cond_cache = ConditioningCache(
            cache_dir=paths["base"], 
            clip_hash=clip_hash, 
            enable_disk_cache=save_conditioning_cache_to_file)
        
        # Filter configs to only collect prompts from jobs that actually need to run
        # This avoids wasting time encoding prompts for jobs that will be skipped in resume mode
        print(f"[GridTester] 🧠 Collecting unique prompts...")
        if not overwrite_existing and existing_data.get("items"):
            configs_needing_work = []
            for conf in expanded:
                conf_positive, _ = build_prompt_with_triggers(conf, lora_triggerwords_mode)
                conf_negative = conf["negative"]
                conf_seed = conf["seed"]
                # Check if ANY resolution/batch needs this config
                needs_work = False
                for job in input_jobs:
                    if check_if_job_completed(
                        existing_data["items"], conf, conf_seed,
                        job["width"], job["height"], job["batch_idx"],
                        conf_positive, conf_negative,
                        has_optional_inputs=has_optional_inputs
                    ) == -1:
                        needs_work = True
                        break
                if needs_work:
                    configs_needing_work.append(conf)

            skippable = len(expanded) - len(configs_needing_work)
            if skippable > 0:
                print(f"[GridTester] ⏭️ {skippable}/{len(expanded)} configs already completed, encoding only {len(configs_needing_work)} needed")

            if not configs_needing_work:
                print(f"[GridTester] ⏭️ All configs already completed, skipping encoding entirely")
                unique_positives, unique_negatives = set(), set()
            else:
                unique_positives, unique_negatives = collect_unique_prompts_with_triggers(
                    configs_needing_work, lora_triggerwords_mode
                )
        else:
            unique_positives, unique_negatives = collect_unique_prompts_with_triggers(
                expanded, lora_triggerwords_mode
            )

        # Collect adjusted HiRes prompts for pre-encoding (if hires prompt adjustment is enabled)
        upscale_settings = session_settings.get("upscaling", {}) if session_settings else {}
        if upscale_settings.get("enabled") and upscale_settings.get("hires_prompt_adjust") and upscale_settings.get("hires_prompt_text", "").strip():
            hires_behavior = upscale_settings.get("hires_prompt_behavior", "append_end")
            hires_text = upscale_settings["hires_prompt_text"].strip()
            hires_adjusted_positives = set()
            for base_prompt in unique_positives:
                if hires_behavior == "prepend":
                    adjusted = hires_text + " " + base_prompt
                elif hires_behavior == "append_end":
                    adjusted = base_prompt + " " + hires_text
                elif hires_behavior == "replace":
                    adjusted = hires_text
                else:
                    adjusted = base_prompt
                hires_adjusted_positives.add(adjusted)
            # Add adjusted prompts to unique set so they get batch-encoded
            unique_positives = unique_positives | hires_adjusted_positives
            print(f"[GridTester] 🔍 Added {len(hires_adjusted_positives)} HiRes-adjusted prompts for pre-encoding")

        clip_skip = first_conf.get("clip_skip", 0)
        if clip_skip != 0:
            print(f"[GridTester] 🔧 Using clip_skip={clip_skip}")

        try:
            conditioning_cache = batch_encode_prompts(
                patched_clip, unique_positives, unique_negatives, cond_cache, clip_skip, enable_disk_cache=save_conditioning_cache_to_file
            )
        except InterruptProcessingException:
            print(f"\n[GridTester] 🛑 INTERRUPTED during pre-encoding - Stopping all jobs")
            loaded_model, loaded_clip, loaded_vae = None, None, None
            patched_model, patched_clip = None, None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            # Re-raise so ComfyUI knows execution was interrupted (not completed)
            raise

        cached_model_key = get_model_cache_key(first_conf)
        cached_lora_key = first_conf["lora_expanded"]
        if model_cache:
            cached_lora_cache_key = model_cache._get_lora_cache_key(cached_model_key, first_conf["lora_expanded"])
        else:
            cached_lora_cache_key = None
        latent_channels = get_latent_channels(loaded_model, optional_latent)
    elif len(unique_model_keys) > 1:
        print(f"[GridTester] ⚠️ Multiple models detected ({len(unique_model_keys)} different models) - pre-encoding DISABLED")
        cond_cache = None
        latent_channels = 4
    else:
        print(f"[GridTester] ℹ️ Using optional conditioning, skipping pre-encoding")
        cond_cache = None
        latent_channels = 4
    
    # ==== FULL RUN SEED BEHAVIOR (PRE-RUN) ====
    # Apply "random_before" full run seed behavior: randomize seed before the entire session
    for conf_idx_pre, conf_pre in enumerate(expanded):
        if conf_pre.get("full_run_seed_behavior") == "random_before":
            import random
            conf_pre["seed"] = random.randint(0, 2**63 - 1)
            print(f"[GridTester] 🎲 Full run random_before: config {conf_idx_pre} seed → {conf_pre['seed']}")

    # ==== MAIN GENERATION LOOP ====
    print(f"\n{'='*80}\n")

    for job_idx, job in enumerate(input_jobs):
        w, h = job["width"], job["height"]
        batch_idx = job["batch_idx"]
        
        for conf_idx, conf in enumerate(expanded):
            # Per-config resolution override: if this config has its own resolution,
            # use it instead of the global input_job's resolution. Only process once
            # (at job_idx == 0) to avoid duplicating work across input_jobs.
            if conf.get("resolution") is not None:
                if job_idx > 0:
                    continue  # Already processed at job_idx=0
                w, h = conf["resolution"]
                batch_idx = 0

            # ==== CHECK FOR INTERRUPT ====
            # ==== UPDATE CURRENT STEP ====
            if model_cache:
                model_cache.set_current_step(conf_idx)

            try:
                import comfy.model_management as mm
                if mm.processing_interrupted():
                    print(f"\n[GridTester] 🛑 INTERRUPTED - Stopping all jobs")

                    if pending_batch:
                        _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                                             per_config_remote_workers, use_remote_vae, remote_vae_worker,
                                             loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id,
                                             config_overrides_vae=config_overrides_vae)
                        pending_batch = []

                    _cleanup_per_config_remote_workers(per_config_remote_workers)
                    if remote_vae_worker:
                        remote_vae_worker.wait_completion()
                        remote_vae_worker.stop()

                    existing_data["meta"] = {
                        "positive": positive_text,
                        "negative": negative_text,
                        "model": ckpt_name,
                        "seed": seed,
                        "vae_batch_size": vae_batch_size,
                        "configs_json": configs_json,
                        "resolutions_json": resolutions_json
                    }
                    save_manifest(paths["manifest"], existing_data)

                    loaded_model, loaded_clip, loaded_vae = None, None, None
                    patched_model, patched_clip = None, None
                    conditioning_cache.clear()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                    # Re-raise so ComfyUI knows execution was interrupted (not completed)
                    raise InterruptProcessingException()
            except InterruptProcessingException:
                raise
            except:
                pass
            
            current_seed = conf["seed"]
            if conf.get("seed_behavior") == "randomize":
                import random
                current_seed = random.randint(0, 2**63 - 1)
            current_job += 1
            
            if pbar:
                try:
                    pbar.update_absolute(current_job, total_jobs)
                except:
                    pass
            
            progress_pct = int((current_job / total_jobs) * 100)
            print(f"[GridTester] 📊 {current_job}/{total_jobs} ({progress_pct}%) | "
                  f"{conf['sampler']} @ {conf['steps']} steps | {w}x{h}")
            
            actual_positive_prompt, lora_triggers = build_prompt_with_triggers(
                conf, lora_triggerwords_mode
            )
            actual_negative_prompt = conf["negative"]
            
            # ==== CHECK EXISTING MATCH ====
            match_index = check_if_job_completed(
                existing_data["items"],
                conf,
                current_seed,
                w, h,
                batch_idx,
                actual_positive_prompt,
                actual_negative_prompt,
                has_optional_inputs=has_optional_inputs
            )

            if match_index != -1:
                if not overwrite_existing:
                    skipped_count += 1
                    continue
                else:
                    old_item = existing_data["items"][match_index]
                    try:
                        old_fname_match = re.search(r'filename=([^&]+)', old_item["file"])
                        if old_fname_match:
                            old_file_path = os.path.join(paths["images"], old_fname_match.group(1))
                            if os.path.exists(old_file_path):
                                os.remove(old_file_path)
                    except Exception as e:
                        print(f"[GridTester] ⚠️ Warning: Could not delete old file: {e}")
                    
                    existing_data["items"].pop(match_index)
            
            # ==== MODEL SWITCHING ====
            target_model_name = conf["model"]
            target_model_key = get_model_cache_key(conf)
            if target_model_key != cached_model_key:
                if cached_model_key is not None:
                    patched_model, patched_clip = cleanup_model_references(
                        patched_model, patched_clip, conditioning_cache
                    )
                    # CRITICAL FIX: Restore dict structure after clear
                    conditioning_cache["positive"] = {}
                    conditioning_cache["negative"] = {}

                loaded_model, loaded_clip, loaded_vae = load_model_by_type(
                    conf, ckpt_name, use_remote_vae,
                    optional_model, optional_clip, optional_vae,
                    optional_positive, optional_negative, loaded_clip, loaded_vae, model_cache=model_cache
                )
                # VAE fallback for non-checkpoint models
                if loaded_vae is None and optional_vae is not None:
                    loaded_vae = optional_vae
                # Remember this model's default VAE for reverting later
                default_model_vae = loaded_vae
                cached_vae_key = "Default"
                current_vae_is_remote = False
                current_remote_vae_url = None
                config_overrides_vae = False

                cached_model_key = target_model_key
                cached_lora_key = None
                cached_lora_cache_key = None
                latent_channels = get_latent_channels(loaded_model, optional_latent)
                model_switched = True
            else:
                model_switched = False

            # ==== PER-CONFIG VAE SWITCHING ====
            # Config Builder VAE settings take priority over sampler node's remote_vae_endpoint
            target_vae = conf.get("vae", "Default")
            if target_vae != cached_vae_key:
                # Flush pending batch before switching VAE (they need current VAE for decoding)
                if pending_batch:
                    _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                                         per_config_remote_workers, use_remote_vae, remote_vae_worker,
                                         loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id,
                                         config_overrides_vae=config_overrides_vae)
                    pending_batch = []

                if target_vae == "Default":
                    # Revert to model's bundled/default VAE
                    loaded_vae = default_model_vae
                    current_vae_is_remote = False
                    current_remote_vae_url = None
                    config_overrides_vae = False
                    print(f"[GridTester] 🎨 Reverting to Default VAE")
                elif is_remote_vae(target_vae):
                    url = extract_remote_vae_url(target_vae)
                    current_vae_is_remote = True
                    current_remote_vae_url = url
                    config_overrides_vae = True
                    loaded_vae = None  # No local VAE needed
                    print(f"[GridTester] 🌐 Using per-config remote VAE: {url}")
                    if url not in per_config_remote_workers:
                        per_config_remote_workers[url] = RemoteVAEDecodeWorker(
                            endpoint=url, img_dir=paths["images"],
                            manifest_path=paths["manifest"],
                            existing_data=existing_data,
                            session_name=session_name, unique_id=unique_id
                        )
                else:
                    current_vae_is_remote = False
                    current_remote_vae_url = None
                    config_overrides_vae = True
                    print(f"[GridTester] 🎨 Loading per-config VAE: {target_vae}")
                    loaded_vae = load_vae_by_name(target_vae)
                cached_vae_key = target_vae

            # ==== LORA SWITCHING ====
            current_lora_string = conf["lora_expanded"]
            
            if model_cache:
                current_cache_key = model_cache._get_lora_cache_key(target_model_key, current_lora_string)
                need_to_load = (current_cache_key != cached_lora_cache_key) or patched_model is None
            else:
                need_to_load = (current_lora_string != cached_lora_key) or patched_model is None
            
            if need_to_load:
                patched_model, patched_clip, should_skip = load_loras(
                    loaded_model, loaded_clip, current_lora_string,
                    target_model_key, incompatible_loras, model_cache=model_cache
                )
                
                if should_skip:
                    skipped_count += 1
                    continue
                
                cached_lora_key = current_lora_string
                if model_cache:
                    cached_lora_cache_key = current_cache_key
                
                # Batch encode logic for multi-model switching
                # Because of short-circuit, if model_switched is True, conditioning_cache['positive'] isn't checked initially
                # But inside the loop, we access it.
                if model_switched or not conditioning_cache["positive"]:
                    model_unique_positives = set()
                    model_unique_negatives = set()

                    for future_idx in range(conf_idx, len(expanded)):
                        future_conf = expanded[future_idx]
                        if get_model_cache_key(future_conf) == target_model_key:
                            future_positive, _ = build_prompt_with_triggers(
                                future_conf, lora_triggerwords_mode
                            )
                            # Skip encoding prompts for configs that are already completed
                            # (avoids wasting time on prompts only used by skipped jobs)
                            if not overwrite_existing and existing_data.get("items"):
                                future_seed = future_conf["seed"]
                                all_done = True
                                for fj in input_jobs:
                                    if check_if_job_completed(
                                        existing_data["items"], future_conf, future_seed,
                                        fj["width"], fj["height"], fj["batch_idx"],
                                        future_positive, future_conf["negative"],
                                        has_optional_inputs=has_optional_inputs
                                    ) == -1:
                                        all_done = False
                                        break
                                if all_done:
                                    continue
                            model_unique_positives.add(future_positive)
                            model_unique_negatives.add(future_conf["negative"])

                    if model_unique_positives:
                        print(f"[GridTester] 🧠 Batch encoding {len(model_unique_positives)} prompts for {target_model_name}")
                        import comfy.model_management as mm_batch
                        mm_batch.load_models_gpu([patched_clip.patcher])

                        clip_skip = conf.get("clip_skip", 0)

                        try:
                            for prompt in model_unique_positives:
                                # Check for interrupt before each prompt encoding
                                if mm.processing_interrupted():
                                    print(f"\n[GridTester] 🛑 INTERRUPTED during positive encoding - Stopping all encoding")
                                    raise InterruptProcessingException()

                                if prompt not in conditioning_cache["positive"]:
                                    conditioning_cache["positive"][prompt] = encode_prompt_with_combinators(patched_clip, prompt, clip_skip)

                            for prompt in model_unique_negatives:
                                # Check for interrupt before each prompt encoding
                                if mm.processing_interrupted():
                                    print(f"\n[GridTester] 🛑 INTERRUPTED during negative encoding - Stopping all encoding")
                                    raise InterruptProcessingException()

                                if prompt not in conditioning_cache["negative"]:
                                    conditioning_cache["negative"][prompt] = encode_prompt_with_combinators(patched_clip, prompt, clip_skip)

                        except InterruptProcessingException:
                            print(f"\n[GridTester] 🛑 INTERRUPTED during encoding - Stopping all jobs")

                            if pending_batch:
                                _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                                                     per_config_remote_workers, use_remote_vae, remote_vae_worker,
                                                     loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id,
                                                     config_overrides_vae=config_overrides_vae)
                                pending_batch = []

                            _cleanup_per_config_remote_workers(per_config_remote_workers)
                            if remote_vae_worker:
                                remote_vae_worker.wait_completion()
                                remote_vae_worker.stop()

                            existing_data["meta"] = {
                                "positive": positive_text,
                                "negative": negative_text,
                                "model": ckpt_name,
                                "seed": seed,
                                "vae_batch_size": vae_batch_size,
                                "configs_json": configs_json,
                                "resolutions_json": resolutions_json
                            }
                            save_manifest(paths["manifest"], existing_data)

                            loaded_model, loaded_clip, loaded_vae = None, None, None
                            patched_model, patched_clip = None, None
                            conditioning_cache.clear()
                            gc.collect()
                            if torch.cuda.is_available():
                                torch.cuda.empty_cache()

                            # Re-raise so ComfyUI knows execution was interrupted (not completed)
                            raise

                        print(f"[GridTester] ✅ Encoded {len(conditioning_cache['positive'])} positive, {len(conditioning_cache['negative'])} negative")

                    model_switched = False
                if cond_cache:
                    cond_cache.set_lora_config(conf['lora_expanded'])
            
            # Get conditioning
            if optional_positive:
                final_positive = optional_positive
            else:
                full_positive = actual_positive_prompt
                final_positive = conditioning_cache["positive"].get(full_positive)
                if final_positive is None:
                    cached_keys = list(conditioning_cache["positive"].keys())
                    cached_preview = [k[:40] for k in cached_keys[:5]]
                    raise RuntimeError(
                        f"[GridTester] ❌ BUG: Encoding not found for positive prompt: {full_positive[:80]}...\n"
                        f"  model_key={target_model_key}, lora={current_lora_string}\n"
                        f"  Cache has {len(cached_keys)} entries: {cached_preview}\n"
                        f"  model_switched={model_switched}, need_to_load={need_to_load}"
                    )

            if optional_negative:
                final_negative = optional_negative
            else:
                final_negative = conditioning_cache["negative"].get(conf["negative"])
                if final_negative is None:
                    cached_keys = list(conditioning_cache["negative"].keys())
                    cached_preview = [k[:40] for k in cached_keys[:5]]
                    raise RuntimeError(
                        f"[GridTester] ❌ BUG: Encoding not found for negative prompt: {conf['negative'][:80]}...\n"
                        f"  model_key={target_model_key}, lora={current_lora_string}\n"
                        f"  Cache has {len(cached_keys)} entries: {cached_preview}\n"
                        f"  model_switched={model_switched}, need_to_load={need_to_load}"
                    )
            
            # =========================================================
            # ==== 🚀 ASYNC LOOK-AHEAD PRE-FETCHING (CORRECTED) ====
            # =========================================================
            if model_cache is not None and model_cache.async_preload:
                current_overall_index = (job_idx * len(expanded)) + conf_idx
                
                # Check if next job exists
                if current_overall_index + 1 < total_jobs:
                    next_idx = current_overall_index + 1
                    next_job_idx = next_idx // len(expanded)
                    next_conf_idx = next_idx % len(expanded)
                    
                    if next_job_idx < len(input_jobs):
                        next_conf = expanded[next_conf_idx]
                        
                        # RESOLVE cache keys for next conf
                        next_model_key = get_model_cache_key(next_conf)
                        next_lora = next_conf["lora_expanded"]

                        # CASE 1: Same Base, Different LoRA
                        if next_model_key == target_model_key and next_lora != current_lora_string:
                            def _preload_lora_worker():
                                return load_loras(
                                    loaded_model, loaded_clip, next_lora,
                                    target_model_name, {}, model_cache=None
                                )
                            model_cache.preload_lora_model(target_model_key, next_lora, _preload_lora_worker)

                        # CASE 2: Different Base Model
                        elif next_model_key != target_model_key:
                            next_model_type = next_conf.get("model_type", "checkpoint")
                            next_model_name = next_conf["model"]
                            print(f"[GridTester] 🔮 Pre-loading Base Model: {next_model_name} ({next_model_type})")

                            if next_model_type == "checkpoint":
                                next_model_resolved = ckpt_name if next_model_name == "Default" else next_model_name
                                def _preload_base_worker(path_to_load=next_model_resolved):
                                    try:
                                        import comfy.sd
                                        ckpt_path = folder_paths.get_full_path("checkpoints", path_to_load)
                                        if use_remote_vae:
                                            out = comfy.sd.load_checkpoint_guess_config(
                                                ckpt_path, output_vae=False, output_clip=True,
                                                embedding_directory=folder_paths.get_folder_paths("embeddings")
                                            )
                                            return out[0], out[1], None
                                        else:
                                            out = comfy.sd.load_checkpoint_guess_config(
                                                ckpt_path, output_vae=True, output_clip=True,
                                                embedding_directory=folder_paths.get_folder_paths("embeddings")
                                            )
                                            return out[0], out[1], out[2]
                                    except Exception as e:
                                        print(f"[GridTester] ❌ Async Worker Error: {e}")
                                        return None, None, None
                                model_cache.preload_base_model(next_model_key, _preload_base_worker)
                            else:
                                # GGUF/diffusion model preload
                                def _preload_diff_worker(conf_to_load=next_conf):
                                    try:
                                        return load_diffusion_model_and_clip(
                                            model_name=conf_to_load["model"],
                                            model_type=conf_to_load.get("model_type"),
                                            text_encoder_paths=conf_to_load.get("text_encoders", []),
                                            clip_type_str=conf_to_load.get("clip_type", "stable_diffusion"),
                                            gguf_options=conf_to_load.get("gguf_options"),
                                            use_remote_vae=use_remote_vae,
                                        )
                                    except Exception as e:
                                        print(f"[GridTester] ❌ Async Worker Error: {e}")
                                        return None, None, None
                                model_cache.preload_base_model(next_model_key, _preload_diff_worker)
            # =========================================================

            # Generate image
            if job["latent"] is not None:
                latent_in = {"samples": job["latent"]["samples"].clone()}
            else:
                latent_in = {"samples": torch.zeros([1, latent_channels, h // 8, w // 8])}
            
            result_latent = None
            try:
                attention_mode = conf.get("attention_mode", "default")
                if attention_mode != "default":
                    print(f"[GridTester] 🧠 Using attention mode: {attention_mode}")

                # Log active extra options
                extra_opts = []
                if conf.get("model_sampling_override", "none") != "none":
                    extra_opts.append(f"model_sampling={conf['model_sampling_override']}")
                if conf.get("use_advanced_sampling", False):
                    extra_opts.append(f"advanced({conf.get('advanced_guider','cfg_guider')}/{conf.get('advanced_scheduler','basic')})")
                if conf.get("flux_guidance_value", 0) and float(conf.get("flux_guidance_value", 0)) > 0:
                    extra_opts.append(f"flux_guidance={conf['flux_guidance_value']}")
                if extra_opts:
                    print(f"[GridTester] ⚙️ Extra options: {', '.join(extra_opts)}")

                result_latent, duration = generate_image(
                    patched_model, current_seed, conf["steps"], conf["cfg"],
                    conf["sampler"], conf["scheduler"], final_positive, final_negative,
                    latent_in, conf["denoise"], attention_mode=attention_mode,
                    model_sampling_override=conf.get("model_sampling_override", "none"),
                    model_sampling_shift=conf.get("model_sampling_shift", 1.73),
                    model_sampling_flux_max_shift=conf.get("model_sampling_flux_max_shift", 1.15),
                    model_sampling_flux_base_shift=conf.get("model_sampling_flux_base_shift", 0.5),
                    use_advanced_sampling=conf.get("use_advanced_sampling", False),
                    advanced_guider=conf.get("advanced_guider", "cfg_guider"),
                    advanced_scheduler=conf.get("advanced_scheduler", "basic"),
                    flux_guidance_value=conf.get("flux_guidance_value", 0.0),
                    width=w,
                    height=h
                )

                # ==== UPSCALING (pipeline-based with sequential steps) ====
                upscale_produced = False
                save_pre_upscale = False
                if session_settings and session_settings.get("upscaling", {}).get("enabled", False) and result_latent is not None:
                    from .image_generation import upscale_image
                    import itertools as upscale_itertools
                    import random as upscale_random
                    from PIL import Image as PILImage

                    upscale_settings_rt = session_settings["upscaling"]
                    upscale_pipelines = upscale_settings_rt.get("pipelines", [])
                    upscale_combo_idx = 0
                    save_pre_upscale = upscale_settings_rt.get("save_pre_upscale", False)

                    # Compute HiRes-adjusted conditioning if enabled
                    hires_positive_cond = final_positive  # Default: same as base
                    hires_prompt_active = False
                    hires_prompt_behavior_rt = ""
                    hires_prompt_text_rt = ""
                    if upscale_settings_rt.get("hires_prompt_adjust") and upscale_settings_rt.get("hires_prompt_text", "").strip():
                        hires_prompt_behavior_rt = upscale_settings_rt.get("hires_prompt_behavior", "append_end")
                        hires_prompt_text_rt = upscale_settings_rt["hires_prompt_text"].strip()
                        if hires_prompt_behavior_rt == "prepend":
                            adjusted_prompt = hires_prompt_text_rt + " " + actual_positive_prompt
                        elif hires_prompt_behavior_rt == "append_end":
                            adjusted_prompt = actual_positive_prompt + " " + hires_prompt_text_rt
                        elif hires_prompt_behavior_rt == "replace":
                            adjusted_prompt = hires_prompt_text_rt
                        else:
                            adjusted_prompt = actual_positive_prompt
                        # Look up pre-encoded conditioning from cache
                        hires_cond = conditioning_cache["positive"].get(adjusted_prompt)
                        if hires_cond is not None:
                            hires_positive_cond = hires_cond
                            hires_prompt_active = True
                            print(f"[GridTester] 🔍 Using HiRes-adjusted prompt ({hires_prompt_behavior_rt}): {adjusted_prompt[:80]}...")
                        else:
                            print(f"[GridTester] ⚠️ HiRes-adjusted prompt not found in cache, using original prompt")

                    for pipeline_idx, pipeline in enumerate(upscale_pipelines):
                        # Skip inactive pipelines (safety check — should already be filtered)
                        if pipeline.get("active", True) is False:
                            continue

                        pipeline_name = pipeline.get("name", f"Pipeline {pipeline_idx + 1}")
                        pipeline_steps = pipeline.get("steps", [])
                        if not pipeline_steps:
                            continue

                        # Each pipeline starts from the original base image
                        pipe_latent = result_latent
                        pipe_w = w
                        pipe_h = h
                        pipeline_history = []  # Accumulate per-step metadata for compound manifest entries

                        # Flatten steps with repeat: a step with repeat=3 runs 3 times sequentially
                        expanded_steps = []
                        for step in pipeline_steps:
                            if step.get("active", True) is False:
                                continue
                            repeat = max(1, int(step.get("repeat", 1)))
                            for _ in range(repeat):
                                expanded_steps.append(step)

                        for step_idx, ucfg in enumerate(expanded_steps):
                            mode = ucfg.get("mode", "hires_only")
                            show_hires = mode in ("hires_only", "model_then_hires")
                            show_model = mode in ("model_only", "model_then_hires")

                            # Parse multi-value fields
                            raw_ratios = str(ucfg.get("upscale_ratios", "1.5"))
                            ratios = [float(r.strip()) for r in raw_ratios.split(",") if r.strip()] or [1.5]
                            raw_denoise = str(ucfg.get("hires_denoise", "0.3"))
                            denoises = [float(d.strip()) for d in raw_denoise.split(",") if d.strip()] or [0.3]
                            models = ucfg.get("upscale_models", []) or [""]

                            # Build Cartesian product of multi-value fields
                            if show_hires and show_model:
                                combos = list(upscale_itertools.product(models, ratios, denoises))
                            elif show_hires:
                                combos = list(upscale_itertools.product([""], ratios, denoises))
                            elif show_model:
                                combos = list(upscale_itertools.product(models, [1.0], [0.0]))
                            else:
                                combos = []

                            for combo in combos:
                                up_model_name, up_ratio, up_denoise = combo

                                # Skip combos requiring a model when none is selected
                                if show_model and not up_model_name:
                                    upscale_combo_idx += 1
                                    continue

                                # Build single-value upscaling config for upscale_image()
                                # For model_only mode, use upscale_ratio for upscale_size so the
                                # model's native output is preserved (not resized back to 1x)
                                effective_size = up_ratio if up_ratio > 1.0 else 2.0
                                single_config = {
                                    "mode": mode,
                                    "upscale_ratio": up_ratio,
                                    "hires_denoise": up_denoise,
                                    "hires_steps": ucfg.get("hires_steps", 0),
                                    "tiled_vae": ucfg.get("tiled_vae", False),
                                    "tile_size": ucfg.get("tile_size", 512),
                                    "tile_overlap": ucfg.get("tile_overlap", 64),
                                    "temporal_size": ucfg.get("temporal_size", 512),
                                    "temporal_overlap": ucfg.get("temporal_overlap", 64),
                                    "upscale_model": up_model_name,
                                    "upscale_size": effective_size,
                                    "resize_method": ucfg.get("resize_method", "bilinear"),
                                    "hires_tiled_sampling": ucfg.get("hires_tiled_sampling", False),
                                    "hires_tile_width": ucfg.get("hires_tile_width", 512),
                                    "hires_tile_height": ucfg.get("hires_tile_height", 512),
                                    "hires_mask_blur": ucfg.get("hires_mask_blur", 8),
                                    "hires_tile_padding": ucfg.get("hires_tile_padding", 32),
                                    "hires_force_uniform_tiles": ucfg.get("hires_force_uniform_tiles", False)
                                }

                                # Steps within a pipeline chain sequentially (each feeds into the next)
                                # Use HiRes-adjusted conditioning for modes that involve hires fix
                                up_positive = hires_positive_cond if (show_hires and hires_prompt_active) else final_positive
                                upscale_result, upscale_duration = upscale_image(
                                    pipe_latent, loaded_vae, patched_model, single_config,
                                    conf, up_positive, final_negative, pipe_w, pipe_h
                                )

                                # Determine if this is the final output (only the last step's last combo in the pipeline)
                                is_last_step = step_idx == len(expanded_steps) - 1
                                is_last_combo = combo == combos[-1]
                                is_final_output = is_last_step and is_last_combo

                                # Generate timestamp-based ID (same convention as normal images)
                                upscale_id = int(time.time() * 100000) + upscale_random.randint(0, 1000)
                                upscaled_filename = f"img_{upscale_id}_upscaled.webp"

                                if isinstance(upscale_result, dict) and "samples" in upscale_result:
                                    # HiRes modes return latent — decode to get dimensions
                                    upscaled_pil = decode_latent_with_vae(loaded_vae, upscale_result["samples"])
                                    up_w, up_h = upscaled_pil.size
                                    # Only save to disk if this is a final output
                                    if is_final_output:
                                        upscaled_pil.save(
                                            os.path.join(paths["images"], upscaled_filename),
                                            "WEBP", quality=80
                                        )
                                    # Feed this latent to the next step in the pipeline
                                    pipe_latent = upscale_result
                                    pipe_w = up_w
                                    pipe_h = up_h
                                elif isinstance(upscale_result, PILImage.Image):
                                    # Model-only returns PIL directly
                                    up_w, up_h = upscale_result.size
                                    # Only save to disk if this is a final output
                                    if is_final_output:
                                        upscale_result.save(
                                            os.path.join(paths["images"], upscaled_filename),
                                            "WEBP", quality=80
                                        )
                                    # Encode PIL back to latent for next step in pipeline
                                    import numpy as np_stack
                                    import torch as torch_stack
                                    pil_np = np_stack.array(upscale_result).astype(np_stack.float32) / 255.0
                                    pil_tensor = torch_stack.from_numpy(pil_np).unsqueeze(0)
                                    pipe_latent = {"samples": loaded_vae.encode(pil_tensor[:, :, :, :3])}
                                    pipe_w = up_w
                                    pipe_h = up_h
                                else:
                                    upscale_combo_idx += 1
                                    continue

                                # Collect this step's upscale info for pipeline history
                                step_info = {
                                    "mode": mode,
                                    "ratio": up_ratio,
                                    "denoise": up_denoise,
                                    "model": up_model_name or "",
                                    "resize_method": ucfg.get("resize_method", "bilinear"),
                                    "hires_steps": ucfg.get("hires_steps", 0),
                                    "tiled_vae": ucfg.get("tiled_vae", False),
                                    "tile_size": ucfg.get("tile_size", 512),
                                    "tiled_sampling": ucfg.get("hires_tiled_sampling", False),
                                    "tile_w": ucfg.get("hires_tile_width", 512),
                                    "tile_h": ucfg.get("hires_tile_height", 512),
                                }
                                if mode == "model_only":
                                    step_info["upscale_size"] = ucfg.get("upscale_size", "2.0")
                                pipeline_history.append(step_info)

                                if is_final_output:
                                    upscaled_meta = create_image_metadata(
                                        conf, up_w, up_h, upscale_duration, current_seed, batch_idx,
                                        actual_positive_prompt, actual_negative_prompt,
                                        gen_index=gen_index_offset + total_generated
                                    )
                                    upscaled_meta["id"] = upscale_id
                                    upscaled_meta["upscaled"] = True
                                    upscaled_meta["upscale_pipeline"] = pipeline_name

                                    # Include HiRes prompt adjustment info in manifest
                                    if hires_prompt_active:
                                        upscaled_meta["hires_prompt_behavior"] = hires_prompt_behavior_rt
                                        upscaled_meta["hires_prompt_text"] = hires_prompt_text_rt

                                    # Multiple steps in pipeline: save arrays of all steps
                                    if len(pipeline_history) > 1:
                                        upscaled_meta["upscale_stacked"] = True
                                        upscaled_meta["upscale_mode"] = [s["mode"] for s in pipeline_history]
                                        upscaled_meta["upscale_ratio"] = [s["ratio"] for s in pipeline_history]
                                        upscaled_meta["upscale_denoise"] = [s["denoise"] for s in pipeline_history]
                                        models = [s["model"] for s in pipeline_history if s["model"]]
                                        if models:
                                            upscaled_meta["upscale_model"] = models
                                        upscaled_meta["upscale_resize_method"] = [s["resize_method"] for s in pipeline_history]
                                        upscaled_meta["upscale_hires_steps"] = [s["hires_steps"] for s in pipeline_history]
                                        # Tiling info: only include steps that have it enabled
                                        tiled_vae_steps = [s["tile_size"] for s in pipeline_history if s["tiled_vae"]]
                                        if tiled_vae_steps:
                                            upscaled_meta["upscale_tiled_vae"] = True
                                            upscaled_meta["upscale_tile_size"] = tiled_vae_steps
                                        tiled_sampling_steps = [f'{s["tile_w"]}x{s["tile_h"]}' for s in pipeline_history if s["tiled_sampling"]]
                                        if tiled_sampling_steps:
                                            upscaled_meta["upscale_tiled_sampling"] = True
                                            upscaled_meta["upscale_tile_w"] = [s["tile_w"] for s in pipeline_history if s["tiled_sampling"]]
                                            upscaled_meta["upscale_tile_h"] = [s["tile_h"] for s in pipeline_history if s["tiled_sampling"]]
                                    else:
                                        # Single step pipeline
                                        upscaled_meta["upscale_mode"] = mode
                                        upscaled_meta["upscale_ratio"] = up_ratio
                                        upscaled_meta["upscale_denoise"] = up_denoise
                                        if up_model_name:
                                            upscaled_meta["upscale_model"] = up_model_name
                                        upscaled_meta["upscale_resize_method"] = ucfg.get("resize_method", "bilinear")
                                        upscaled_meta["upscale_hires_steps"] = ucfg.get("hires_steps", 0)
                                        if ucfg.get("tiled_vae", False):
                                            upscaled_meta["upscale_tiled_vae"] = True
                                            upscaled_meta["upscale_tile_size"] = ucfg.get("tile_size", 512)
                                        if ucfg.get("hires_tiled_sampling", False):
                                            upscaled_meta["upscale_tiled_sampling"] = True
                                            upscaled_meta["upscale_tile_w"] = ucfg.get("hires_tile_width", 512)
                                            upscaled_meta["upscale_tile_h"] = ucfg.get("hires_tile_height", 512)
                                        if mode == "model_only":
                                            upscaled_meta["upscale_size"] = ucfg.get("upscale_size", "2.0")

                                    upscaled_meta["file"] = f"/view?filename={upscaled_filename}&type=output&subfolder=benchmarks/{session_name}/images"
                                    upscaled_meta["rejected"] = False
                                    # Insert at beginning (same order as flush_batch_with_vae)
                                    existing_data["items"].insert(0, upscaled_meta)
                                    upscale_produced = True

                                    # Save manifest immediately so dashboard can pick it up
                                    save_manifest(paths["manifest"], existing_data)

                                    # Send live update to dashboard (same as flush_batch_with_vae)
                                    if PromptServer is not None:
                                        try:
                                            manifest_meta = existing_data.get("meta", {})
                                            PromptServer.instance.send_sync("ultimate_grid.update", {
                                                "node": unique_id,
                                                "session_name": session_name,
                                                "new_items": [upscaled_meta],
                                                "meta": manifest_meta
                                            })
                                        except Exception:
                                            pass

                                    print(f"[GridTester] 🔍 Saved upscaled image: {upscaled_filename} "
                                          f"(pipeline={pipeline_name}, mode={mode}, ratio={up_ratio}, denoise={up_denoise}"
                                          f"{', model=' + up_model_name if up_model_name else ''})")
                                else:
                                    print(f"[GridTester] 🔍 Pipeline '{pipeline_name}' intermediate step {step_idx + 1}/{len(expanded_steps)} "
                                          f"(mode={mode}, ratio={up_ratio}, denoise={up_denoise}"
                                          f"{', model=' + up_model_name if up_model_name else ''})")

                                upscale_combo_idx += 1

                    # Save manifest after all pipeline combos
                    if upscale_combo_idx > 0:
                        save_manifest(paths["manifest"], existing_data)

                job_durations.append(duration)
                eta_info = calculate_eta(job_durations, current_job, total_jobs)
                if eta_info:
                    print_generation_progress(current_job, total_jobs, conf, w, h, duration, eta_info)
                    # Send progress to dashboard frontend
                    if PromptServer is not None:
                        try:
                            progress_pct = int((current_job / total_jobs) * 100)
                            if eta_info['hours'] > 0:
                                eta_str = f"{eta_info['hours']}h {eta_info['minutes']}m"
                            elif eta_info['minutes'] > 0:
                                eta_str = f"{eta_info['minutes']}m {eta_info['seconds']}s"
                            else:
                                eta_str = f"{eta_info['seconds']}s"
                            PromptServer.instance.send_sync("ultimate_grid.progress", {
                                "node": unique_id,
                                "session_name": session_name,
                                "current_job": current_job,
                                "total_jobs": total_jobs,
                                "progress_pct": progress_pct,
                                "eta_str": eta_str,
                                "finish_time": eta_info['finish_formatted'],
                                "avg_duration": round(eta_info['avg_duration'], 1),
                                "last_duration": round(duration, 1)
                            })
                        except Exception:
                            pass

                # Skip saving the base (non-upscaled) image when upscaling produced results
                # — only the upscaled final version(s) should appear in the output
                # Unless save_pre_upscale is enabled, in which case save both
                if not upscale_produced or save_pre_upscale:
                    meta = create_image_metadata(
                        conf, w, h, duration, current_seed, batch_idx,
                        actual_positive_prompt, actual_negative_prompt,
                        gen_index=gen_index_offset + total_generated
                    )
                    if pos_hash or neg_hash:
                        meta["conditioning_pos_hash"] = pos_hash
                        meta["conditioning_neg_hash"] = neg_hash

                    pending_batch.append((result_latent["samples"].clone(), meta))
                total_generated += 1

                # ==== GPU COOLDOWN (if enabled in session settings) ====
                if session_settings and session_settings.get("cooldown", {}).get("enabled", False):
                    cooldown_config = session_settings["cooldown"]
                    cooldown_every_n = int(cooldown_config.get("every_n", 1))
                    if total_generated > 0 and total_generated % cooldown_every_n == 0:
                        cooldown_seconds = int(cooldown_config.get("seconds", 5))
                        clear_vram = cooldown_config.get("clear_vram", False)
                        print(f"[GridTester] ❄️ GPU Cooldown: pausing {cooldown_seconds}s after {total_generated} generations")
                        if clear_vram:
                            import comfy.model_management as mm_cooldown
                            mm_cooldown.soft_empty_cache()
                            mm_cooldown.unload_all_models()
                            print(f"[GridTester] ❄️ VRAM cleared")
                            cached_model_key = None  # Force model reload on next iteration
                        import time as time_cooldown
                        time_cooldown.sleep(cooldown_seconds)
                        print(f"[GridTester] ❄️ Cooldown complete, resuming generation")

            except Exception as e:
                import comfy.model_management
                if isinstance(e, InterruptProcessingException):
                    print(f"\n[GridTester] 🛑 INTERRUPTED during generation - Stopping all jobs")
                    if result_latent is not None:
                        del result_latent
                    result_latent = None

                    if pending_batch:
                        _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                                             per_config_remote_workers, use_remote_vae, remote_vae_worker,
                                             loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id,
                                             config_overrides_vae=config_overrides_vae)
                        pending_batch = []

                    _cleanup_per_config_remote_workers(per_config_remote_workers)
                    if remote_vae_worker:
                        remote_vae_worker.wait_completion()
                        remote_vae_worker.stop()

                    existing_data["meta"] = {
                        "positive": positive_text,
                        "negative": negative_text,
                        "model": ckpt_name,
                        "seed": seed,
                        "vae_batch_size": vae_batch_size,
                        "configs_json": configs_json,
                        "resolutions_json": resolutions_json
                    }
                    save_manifest(paths["manifest"], existing_data)

                    loaded_model, loaded_clip, loaded_vae = None, None, None
                    patched_model, patched_clip = None, None
                    conditioning_cache.clear()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                    # Re-raise so ComfyUI knows execution was interrupted (not completed)
                    raise
                else:
                    print(f"[GridTester] ❌ Generation failed: {e}")
                    if result_latent is not None:
                        del result_latent
                    continue
            
            if result_latent is not None:
                del result_latent
            result_latent = None
            del latent_in
            latent_in = None
            
            if current_job % 10 == 0:
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            
            threshold = vae_batch_size if flush_batch_every <= 0 else flush_batch_every
            if len(pending_batch) >= threshold:
                _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                                     per_config_remote_workers, use_remote_vae, remote_vae_worker,
                                     loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id,
                                     config_overrides_vae=config_overrides_vae)
                pending_batch = []

    # ==== FINALIZATION ====
    if pending_batch:
        _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                             per_config_remote_workers, use_remote_vae, remote_vae_worker,
                             loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id,
                             config_overrides_vae=config_overrides_vae)

    # Shut down per-config remote VAE workers
    _cleanup_per_config_remote_workers(per_config_remote_workers)

    if remote_vae_worker:
        print(f"[GridTester] 🌐 Waiting for remote VAE...")
        remote_vae_worker.wait_completion()
        remote_vae_worker.stop()
    
    print_incompatible_loras_summary(incompatible_loras)
    
    if skipped_count > 0:
        print(f"[GridTester] ⏭️ Skipped {skipped_count} configs")

    # ==== FULL RUN SEED BEHAVIOR (POST-RUN) ====
    # These modify the seed for the NEXT queue/run, not the current one.
    # The new seeds are stored in the manifest meta so the user can see/use them.
    next_run_seeds = {}
    for conf_idx_post, conf_post in enumerate(expanded):
        frb = conf_post.get("full_run_seed_behavior", "fixed")
        if frb == "random_after":
            import random
            new_seed = random.randint(0, 2**63 - 1)
            print(f"[GridTester] 🎲 Full run random_after: config {conf_idx_post} next seed → {new_seed}")
            conf_post["seed"] = new_seed
            next_run_seeds[str(conf_idx_post)] = new_seed
        elif frb == "increment_after":
            conf_post["seed"] = conf_post["seed"] + 1
            print(f"[GridTester] ➕ Full run increment_after: config {conf_idx_post} next seed → {conf_post['seed']}")
            next_run_seeds[str(conf_idx_post)] = conf_post["seed"]
        elif frb == "decrement_after":
            conf_post["seed"] = conf_post["seed"] - 1
            print(f"[GridTester] ➖ Full run decrement_after: config {conf_idx_post} next seed → {conf_post['seed']}")
            next_run_seeds[str(conf_idx_post)] = conf_post["seed"]
    # Persist next-run seeds to the node's seed widget via PromptServer
    if next_run_seeds and PromptServer is not None:
        try:
            PromptServer.instance.send_sync("ultimate_grid.next_run_seeds", {
                "node": unique_id,
                "seeds": next_run_seeds
            })
        except Exception:
            pass

    existing_data["meta"] = {
        "positive": positive_text,
        "negative": negative_text,
        "model": ckpt_name,
        "seed": seed,
        "vae_batch_size": vae_batch_size,
        "configs_json": configs_json,
        "resolutions_json": resolutions_json
    }
    save_manifest(paths["manifest"], existing_data)

    print(f"[GridTester] 🧹 Cleaning up...")
    loaded_model, loaded_clip, loaded_vae = None, None, None
    patched_model, patched_clip = None, None
    conditioning_cache.clear()
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
        
        print(f"\n{'='*80}")
        print(f"[GridTester] 🎉 COMPLETE!")
        print(f"[GridTester] ✅ {total_generated} images generated")
        print(f"[GridTester] ⏱️  {total_hours}h {total_minutes}m {total_seconds}s total")
        print(f"[GridTester] 📊 {avg_per_job:.1f}s average per job")
        print(f"{'='*80}\n")

        # Send completion event to dashboard
        if PromptServer is not None:
            try:
                PromptServer.instance.send_sync("ultimate_grid.progress", {
                    "node": unique_id,
                    "session_name": session_name,
                    "current_job": total_jobs,
                    "total_jobs": total_jobs,
                    "progress_pct": 100,
                    "eta_str": "Done",
                    "finish_time": time.strftime("%H:%M:%S"),
                    "avg_duration": round(avg_per_job, 1),
                    "last_duration": 0,
                    "complete": True,
                    "total_elapsed": f"{total_hours}h {total_minutes}m {total_seconds}s",
                    "total_generated": total_generated
                })
            except Exception:
                pass
    
    return (html,)


def _get_master_url():
    """Detect this ComfyUI instance's URL for remote workers to connect to."""
    import socket
    try:
        # Get local IP by connecting to external (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    port = 8188
    try:
        import comfy.cli_args
        port = comfy.cli_args.args.port
    except Exception:
        pass

    return f"http://{local_ip}:{port}"


# === Conditioning Serialization Helpers ===
# These convert ComfyUI conditioning tensors to/from JSON-serializable dicts
# for transmitting pre-encoded conditionings from master to workers.
# Pattern mirrors ConditioningCache._conditioning_to_dict/_dict_to_conditioning
# but handles multi-entry conditionings (AND combinator creates multiple entries).

def _conditioning_to_serializable(conditioning):
    """
    Convert a ComfyUI conditioning to a JSON-serializable list of dicts.

    Args:
        conditioning: ComfyUI format [[cond_tensor, {"pooled_output": pooled_tensor}], ...]
                      May have multiple entries when AND combinator is used.

    Returns:
        list of dicts, each with base64-encoded tensor data:
        [{"cond": {"data": ..., "shape": ..., "dtype": ...}, "pooled": {...}}, ...]
    """
    import base64
    import numpy as np

    entries = []
    for cond_tensor, extra in conditioning:
        cond_np = cond_tensor.cpu().numpy()
        entry = {
            "cond": {
                "data": base64.b64encode(cond_np.tobytes()).decode('utf-8'),
                "shape": list(cond_np.shape),
                "dtype": str(cond_np.dtype)
            }
        }

        # Serialize ALL keys from the extra dict, not just pooled_output.
        # Models like Wan/T5 rely on attention_mask and other keys for proper sampling.
        if isinstance(extra, dict):
            extra_serialized = {}
            for key, val in extra.items():
                if val is None:
                    extra_serialized[key] = {"type": "none"}
                elif isinstance(val, torch.Tensor):
                    val_np = val.cpu().numpy()
                    extra_serialized[key] = {
                        "type": "tensor",
                        "data": base64.b64encode(val_np.tobytes()).decode('utf-8'),
                        "shape": list(val_np.shape),
                        "dtype": str(val_np.dtype)
                    }
                else:
                    # Scalar or other JSON-serializable value
                    extra_serialized[key] = {"type": "value", "data": val}
            entry["extra"] = extra_serialized

        entries.append(entry)

    return entries


def _serializable_to_conditioning(entries):
    """
    Convert a serialized list of dicts back to ComfyUI conditioning format.

    Args:
        entries: list of dicts with base64-encoded tensor data (from _conditioning_to_serializable)

    Returns:
        ComfyUI conditioning format [[cond_tensor, {"pooled_output": pooled_tensor}], ...]
    """
    import base64
    import numpy as np

    conditioning = []
    for entry in entries:
        # Reconstruct main conditioning tensor
        cond_data = entry["cond"]
        cond_bytes = base64.b64decode(cond_data["data"])
        cond_np = np.frombuffer(cond_bytes, dtype=np.dtype(cond_data["dtype"])).reshape(
            tuple(cond_data["shape"])
        )
        # .copy() is required because np.frombuffer returns a read-only array,
        # and torch.from_numpy cannot send read-only arrays to GPU
        cond_tensor = torch.from_numpy(cond_np.copy())

        # Reconstruct ALL extra dict keys (attention_mask, pooled_output, etc.)
        extra_dict = {}
        if "extra" in entry:
            for key, val_info in entry["extra"].items():
                if val_info.get("type") == "none":
                    extra_dict[key] = None
                elif val_info.get("type") == "tensor":
                    val_bytes = base64.b64decode(val_info["data"])
                    val_np = np.frombuffer(val_bytes, dtype=np.dtype(val_info["dtype"])).reshape(
                        tuple(val_info["shape"])
                    )
                    extra_dict[key] = torch.from_numpy(val_np.copy())
                elif val_info.get("type") == "value":
                    extra_dict[key] = val_info["data"]
        elif "pooled" in entry:
            # Backwards compatibility with old serialization format
            pooled_data = entry["pooled"]
            pooled_bytes = base64.b64decode(pooled_data["data"])
            pooled_np = np.frombuffer(pooled_bytes, dtype=np.dtype(pooled_data["dtype"])).reshape(
                tuple(pooled_data["shape"])
            )
            extra_dict["pooled_output"] = torch.from_numpy(pooled_np.copy())

        conditioning.append([cond_tensor, extra_dict])

    return conditioning


def _preencode_all_conditionings(
    expanded, lora_triggerwords_mode, ckpt_name, use_remote_vae,
    optional_model, optional_clip, optional_vae,
    optional_positive, optional_negative, model_cache
):
    """
    Pre-encode all unique prompts across all (model, LoRA) combinations.

    Groups expanded configs by (model_key, lora_key), loads model+LoRA for each group,
    encodes all unique prompts, serializes the conditionings using base64 encoding,
    then cleans up.

    Returns:
        dict: {
            "model_key|lora_key": {
                "positive": {prompt_text: serialized_entries_list, ...},
                "negative": {prompt_text: serialized_entries_list, ...}
            },
            ...
        }
        Empty dict if encoding fails or no configs to encode.
    """
    from collections import defaultdict
    from .model_loader import load_loras_for_preencoding

    # Group configs by (model_key, lora_key)
    groups = defaultdict(list)
    for conf in expanded:
        model_key = get_model_cache_key(conf)
        lora_key = conf.get("lora_expanded", conf.get("lora", "None"))
        group_key = f"{model_key}|{lora_key}"
        groups[group_key].append(conf)

    print(f"[Distribution] 🧠 Found {len(groups)} unique (model, LoRA) group(s) to pre-encode")

    encoded_all = {}

    for group_key, configs in groups.items():
        parts = group_key.split("|", 1)
        lora_key = parts[1] if len(parts) > 1 else "None"
        first_conf = configs[0]

        print(f"[Distribution] 🧠 Pre-encoding group: model={first_conf['model']}, lora={lora_key}")

        # Collect unique prompts for this group
        unique_positives = set()
        unique_negatives = set()
        for conf in configs:
            try:
                actual_positive, _ = build_prompt_with_triggers(conf, lora_triggerwords_mode)
            except Exception:
                actual_positive = conf.get("positive", "")
            actual_negative = conf.get("negative", "")
            unique_positives.add(actual_positive)
            unique_negatives.add(actual_negative)

        print(f"[Distribution] 🧠   {len(unique_positives)} unique positive, "
              f"{len(unique_negatives)} unique negative prompt(s)")

        try:
            # Load model + CLIP for this group
            loaded_model, loaded_clip, loaded_vae = load_model_by_type(
                first_conf, ckpt_name, use_remote_vae,
                optional_model, optional_clip, optional_vae,
                optional_positive, optional_negative, None, None,
                model_cache=model_cache
            )

            # Apply LoRA to get patched CLIP
            if lora_key != "None":
                patched_model, patched_clip = load_loras_for_preencoding(
                    loaded_model, loaded_clip, lora_key
                )
            else:
                patched_model, patched_clip = loaded_model, loaded_clip

            # Force CLIP onto GPU for encoding
            import comfy.model_management as mm_enc
            mm_enc.load_models_gpu([patched_clip.patcher])

            clip_skip = first_conf.get("clip_skip", 0)

            serialized_positive = {}
            serialized_negative = {}

            for prompt in unique_positives:
                cond = encode_prompt_with_combinators(patched_clip, prompt, clip_skip)
                serialized_positive[prompt] = _conditioning_to_serializable(cond)

            for prompt in unique_negatives:
                cond = encode_prompt_with_combinators(patched_clip, prompt, clip_skip)
                serialized_negative[prompt] = _conditioning_to_serializable(cond)

            encoded_all[group_key] = {
                "positive": serialized_positive,
                "negative": serialized_negative
            }

            print(f"[Distribution] 🧠   Encoded {len(serialized_positive)} positive, "
                  f"{len(serialized_negative)} negative conditioning(s)")

            # Cleanup patched references
            del patched_model, patched_clip

        except Exception as e:
            print(f"[Distribution] ⚠️ Pre-encoding failed for group {group_key}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Final cleanup
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return encoded_all


def _run_distributed_generation(
    self, distribution_config, expanded, input_jobs, existing_data,
    overwrite_existing, has_optional_inputs, lora_triggerwords_mode,
    session_name, paths, unique_id, total_jobs, seed, ckpt_name,
    positive_text, negative_text, vae_batch_size, configs_json,
    resolutions_json, flush_batch_every, use_remote_vae,
    remote_vae_endpoint, save_conditioning_cache_to_file,
    enable_model_cache, optional_model, optional_clip, optional_vae,
    optional_positive, optional_negative, optional_latent, model_cache,
    session_settings=None
):
    """
    Run generation in distributed mode.

    The master acts as both coordinator and local worker:
    - Creates a DistributionManager with the full job list
    - Notifies remote workers to start pulling jobs via API
    - Processes jobs locally by claiming from its own manager
    - Waits for all remote workers to finish
    - Returns the final HTML dashboard
    """
    from .distribution_manager import DistributionManager
    from .distribution_routes import (
        set_distribution_manager, notify_workers_to_start,
        stop_all_workers, _send_distribution_status
    )

    worker_urls = distribution_config.get("worker_urls", [])
    claim_timeout = distribution_config.get("claim_timeout", 600)

    # Inject trigger word mode into configs so workers can use it
    for conf in expanded:
        conf["_lora_triggerwords_mode"] = lora_triggerwords_mode

    # === Create and populate distribution manager ===
    manager = DistributionManager(
        session_name=session_name,
        paths=paths,
        unique_id=unique_id,
        existing_data=existing_data,
        claim_timeout_seconds=claim_timeout
    )

    # Pass session-level settings (cooldown, etc.) to manager for worker passthrough
    if session_settings:
        manager._session_settings = session_settings

    manager.populate_jobs(
        expanded, input_jobs, existing_data,
        overwrite_existing, has_optional_inputs, lora_triggerwords_mode
    )

    # Make manager accessible to API endpoints
    set_distribution_manager(manager)
    _send_distribution_status(manager)

    # === Master pre-encoding phase (if enabled) ===
    # When "Use Master Text Encoding" is on, pre-encode ALL unique prompts for all
    # (model, LoRA) combinations. Workers will receive these conditionings with their
    # job claims and skip CLIP encoding entirely.
    use_master_encoding = distribution_config.get("use_master_encoding", False)
    if use_master_encoding and not (optional_positive and optional_negative):
        print(f"[Distribution] 🧠 MASTER PRE-ENCODING: Encoding all unique prompts for workers...")

        encoded_conditionings = _preencode_all_conditionings(
            expanded, lora_triggerwords_mode, ckpt_name, use_remote_vae,
            optional_model, optional_clip, optional_vae,
            optional_positive, optional_negative, model_cache
        )

        if encoded_conditionings:
            manager.set_encoded_conditionings(encoded_conditionings)
            print(f"[Distribution] 🧠 Pre-encoding complete, conditionings will be sent with job claims")
        else:
            print(f"[Distribution] ⚠️ Pre-encoding produced no results, workers will encode locally")
    elif use_master_encoding and (optional_positive and optional_negative):
        print(f"[Distribution] ⚠️ Master encoding disabled: optional conditioning inputs override prompts")

    # Early exit if all jobs were already completed (resume with nothing to do)
    initial_status = manager.get_status()
    if initial_status["total"] == 0:
        print(f"[Distribution] ⏭️ All jobs already completed, nothing to distribute")
        manager.deactivate()
        set_distribution_manager(None)

        existing_data["meta"] = {
            "positive": positive_text, "negative": negative_text,
            "model": ckpt_name, "seed": seed,
            "vae_batch_size": vae_batch_size,
            "configs_json": configs_json, "resolutions_json": resolutions_json
        }
        save_manifest(paths["manifest"], existing_data)

        html = get_html_template(session_name, existing_data, unique_id)
        return (html,)

    # === Notify remote workers ===
    master_url = _get_master_url()
    print(f"[Distribution] 🌐 Master URL: {master_url}")
    print(f"[Distribution] 🌐 Notifying {len(worker_urls)} worker(s)...")

    sync_models = distribution_config.get("sync_models_to_workers", False)
    if sync_models:
        manager.sync_models_to_workers = True
        print(f"[Distribution] ☁️ Model sync enabled — workers will download missing models from master")

    worker_results = notify_workers_to_start(worker_urls, master_url, session_name, sync_models_to_workers=sync_models)
    successful_workers = sum(1 for _, ok, _ in worker_results if ok)
    print(f"[Distribution] ✅ {successful_workers}/{len(worker_urls)} workers started")

    # === Master local processing state ===
    loaded_model, loaded_clip, loaded_vae = None, None, None
    patched_model, patched_clip = None, None
    cached_model_key = None
    cached_lora_key = None
    cached_vae_key = None
    default_model_vae = None
    conditioning_cache = {"positive": {}, "negative": {}}
    incompatible_loras = {}
    pending_batch = []
    pending_job_ids = []  # Track job_ids for items in pending_batch
    total_generated = 0
    gen_index_offset = len(existing_data.get("items", []))
    job_durations = []
    eta_start_time = time.time()
    master_jobs_processed = 0

    # Remote VAE setup for master's local processing
    remote_vae_worker = None
    if use_remote_vae and expanded:
        remote_vae_worker = initialize_remote_vae(
            remote_vae_endpoint, paths["images"], paths["manifest"],
            existing_data, session_name, unique_id
        )
    per_config_remote_workers = {}
    current_vae_is_remote = False
    current_remote_vae_url = None
    config_overrides_vae = False  # True when config explicitly sets a non-Default VAE (overrides sampler node's remote_vae_endpoint)

    try:
        if PromptServer is not None:
            pbar = PromptServer.instance.progress_bar_pool.get_progress_bar(unique_id)
        else:
            pbar = None
    except:
        pbar = None

    dist_total = manager.get_status()["total"]

    # Ensure last_prompt_id exists for sampling callbacks (some ComfyUI versions
    # may not have it set when running inside the distributed code path)
    try:
        if PromptServer is not None and PromptServer.instance is not None:
            if not hasattr(PromptServer.instance, 'last_prompt_id'):
                PromptServer.instance.last_prompt_id = f"dist_master_{unique_id}"
    except Exception:
        pass

    # === Master local processing loop ===
    # Master claims jobs from its own distribution manager and processes them
    # using the same model loading, encoding, and generation code paths as the
    # normal (non-distributed) generation loop.
    try:
        while True:
            # Check for interrupt
            try:
                import comfy.model_management as mm
                if mm.processing_interrupted():
                    print(f"\n[Distribution/Master] 🛑 INTERRUPTED")
                    raise InterruptProcessingException()
            except InterruptProcessingException:
                raise
            except:
                pass

            # Claim next job from manager
            batch = manager.claim_batch_for_local(1)
            if not batch:
                break  # No more pending jobs for master

            claimed_job = batch[0]
            conf = claimed_job["config"]
            input_job = claimed_job["input_job"]
            job_id = claimed_job["job_id"]
            w = input_job["width"]
            h = input_job["height"]
            batch_idx = input_job.get("batch_idx", 0)
            current_seed = conf["seed"]
            if conf.get("seed_behavior") == "randomize":
                import random
                current_seed = random.randint(0, 2**63 - 1)

            master_jobs_processed += 1
            completed_total = manager.total_completed
            print(f"[Distribution/Master] 📊 Processing job {job_id} | "
                  f"{conf['sampler']} @ {conf['steps']} steps | {w}x{h} | "
                  f"Progress: {completed_total}/{dist_total}")

            if pbar:
                try:
                    pbar.update_absolute(completed_total, dist_total)
                except:
                    pass

            # Build prompts with trigger words
            actual_positive_prompt, _ = build_prompt_with_triggers(conf, lora_triggerwords_mode)
            actual_negative_prompt = conf["negative"]

            # --- Model Switching ---
            target_model_key = get_model_cache_key(conf)
            if target_model_key != cached_model_key:
                if cached_model_key is not None:
                    patched_model, patched_clip = cleanup_model_references(
                        patched_model, patched_clip, conditioning_cache
                    )
                    conditioning_cache = {"positive": {}, "negative": {}}

                loaded_model, loaded_clip, loaded_vae = load_model_by_type(
                    conf, ckpt_name, use_remote_vae,
                    optional_model, optional_clip, optional_vae,
                    optional_positive, optional_negative, loaded_clip, loaded_vae,
                    model_cache=model_cache
                )
                if loaded_vae is None and optional_vae is not None:
                    loaded_vae = optional_vae
                default_model_vae = loaded_vae
                cached_model_key = target_model_key
                cached_lora_key = None
                cached_vae_key = "Default"
                current_vae_is_remote = False
                current_remote_vae_url = None
                config_overrides_vae = False

            # --- VAE Switching ---
            # Config Builder VAE settings take priority over sampler node's remote_vae_endpoint
            target_vae = conf.get("vae", "Default")
            if target_vae != cached_vae_key:
                # Flush pending batch before switching VAE
                if pending_batch:
                    _flush_pending_batch(
                        pending_batch, current_vae_is_remote, current_remote_vae_url,
                        per_config_remote_workers, use_remote_vae, remote_vae_worker,
                        loaded_vae, paths, existing_data, session_name,
                        paths["manifest"], unique_id,
                        config_overrides_vae=config_overrides_vae
                    )
                    for jid in pending_job_ids:
                        manager.complete_job(jid)
                    pending_batch = []
                    pending_job_ids = []

                if target_vae == "Default":
                    loaded_vae = default_model_vae
                    current_vae_is_remote = False
                    current_remote_vae_url = None
                    config_overrides_vae = False
                elif is_remote_vae(target_vae):
                    url = extract_remote_vae_url(target_vae)
                    current_vae_is_remote = True
                    current_remote_vae_url = url
                    config_overrides_vae = True
                    loaded_vae = None
                    if url not in per_config_remote_workers:
                        per_config_remote_workers[url] = RemoteVAEDecodeWorker(
                            endpoint=url, img_dir=paths["images"],
                            manifest_path=paths["manifest"],
                            existing_data=existing_data,
                            session_name=session_name, unique_id=unique_id
                        )
                else:
                    current_vae_is_remote = False
                    current_remote_vae_url = None
                    config_overrides_vae = True
                    loaded_vae = load_vae_by_name(target_vae)
                cached_vae_key = target_vae

            # --- LoRA Switching ---
            current_lora_string = conf.get("lora_expanded", conf.get("lora", "None"))
            if current_lora_string != cached_lora_key or patched_model is None:
                patched_model, patched_clip, should_skip = load_loras(
                    loaded_model, loaded_clip, current_lora_string,
                    target_model_key, incompatible_loras, model_cache=model_cache
                )
                if should_skip:
                    manager.fail_job(job_id, "LoRA incompatible")
                    continue
                cached_lora_key = current_lora_string

            # --- Prompt Encoding ---
            if optional_positive:
                final_positive = optional_positive
            else:
                if actual_positive_prompt not in conditioning_cache["positive"]:
                    clip_skip = conf.get("clip_skip", 0)
                    conditioning_cache["positive"][actual_positive_prompt] = \
                        encode_prompt_with_combinators(patched_clip, actual_positive_prompt, clip_skip)
                final_positive = conditioning_cache["positive"][actual_positive_prompt]

            if optional_negative:
                final_negative = optional_negative
            else:
                if actual_negative_prompt not in conditioning_cache["negative"]:
                    clip_skip = conf.get("clip_skip", 0)
                    conditioning_cache["negative"][actual_negative_prompt] = \
                        encode_prompt_with_combinators(patched_clip, actual_negative_prompt, clip_skip)
                final_negative = conditioning_cache["negative"][actual_negative_prompt]

            # --- Create Latent ---
            latent_channels = get_latent_channels(loaded_model, optional_latent)
            if optional_latent is not None:
                latent_in = {"samples": optional_latent["samples"].clone()}
            else:
                latent_in = {"samples": torch.zeros([1, latent_channels, h // 8, w // 8])}

            # --- Generate Image ---
            try:
                attention_mode = conf.get("attention_mode", "default")

                # Log active extra options
                extra_opts = []
                if conf.get("model_sampling_override", "none") != "none":
                    extra_opts.append(f"model_sampling={conf['model_sampling_override']}")
                if conf.get("use_advanced_sampling", False):
                    extra_opts.append(f"advanced({conf.get('advanced_guider','cfg_guider')}/{conf.get('advanced_scheduler','basic')})")
                if conf.get("flux_guidance_value", 0) and float(conf.get("flux_guidance_value", 0)) > 0:
                    extra_opts.append(f"flux_guidance={conf['flux_guidance_value']}")
                if extra_opts:
                    print(f"[GridTester] ⚙️ Extra options: {', '.join(extra_opts)}")

                result_latent, duration = generate_image(
                    patched_model, current_seed, conf["steps"], conf["cfg"],
                    conf["sampler"], conf["scheduler"], final_positive, final_negative,
                    latent_in, conf["denoise"], attention_mode=attention_mode,
                    model_sampling_override=conf.get("model_sampling_override", "none"),
                    model_sampling_shift=conf.get("model_sampling_shift", 1.73),
                    model_sampling_flux_max_shift=conf.get("model_sampling_flux_max_shift", 1.15),
                    model_sampling_flux_base_shift=conf.get("model_sampling_flux_base_shift", 0.5),
                    use_advanced_sampling=conf.get("use_advanced_sampling", False),
                    advanced_guider=conf.get("advanced_guider", "cfg_guider"),
                    advanced_scheduler=conf.get("advanced_scheduler", "basic"),
                    flux_guidance_value=conf.get("flux_guidance_value", 0.0),
                    width=w,
                    height=h
                )

                job_durations.append(duration)
                eta_info = calculate_eta(job_durations, completed_total + 1, dist_total)
                if eta_info:
                    print_generation_progress(
                        completed_total + 1, dist_total, conf, w, h, duration, eta_info
                    )

                meta = create_image_metadata(
                    conf, w, h, duration, current_seed, batch_idx,
                    actual_positive_prompt, actual_negative_prompt,
                    gen_index=gen_index_offset + total_generated
                )

                pending_batch.append((result_latent["samples"].clone(), meta))
                pending_job_ids.append(job_id)
                total_generated += 1

                del result_latent, latent_in

            except InterruptProcessingException:
                raise
            except Exception as e:
                print(f"[Distribution/Master] ❌ Generation failed: {e}")
                manager.fail_job(job_id, str(e))
                del latent_in
                continue

            # --- Flush batch at threshold ---
            threshold = vae_batch_size if flush_batch_every <= 0 else flush_batch_every
            if len(pending_batch) >= threshold:
                _flush_pending_batch(
                    pending_batch, current_vae_is_remote, current_remote_vae_url,
                    per_config_remote_workers, use_remote_vae, remote_vae_worker,
                    loaded_vae, paths, existing_data, session_name,
                    paths["manifest"], unique_id,
                    config_overrides_vae=config_overrides_vae
                )
                for jid in pending_job_ids:
                    manager.complete_job(jid)
                pending_batch = []
                pending_job_ids = []
                _send_distribution_status(manager)

            # Periodic cleanup
            if master_jobs_processed % 10 == 0:
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        # Flush remaining master batch
        if pending_batch:
            _flush_pending_batch(
                pending_batch, current_vae_is_remote, current_remote_vae_url,
                per_config_remote_workers, use_remote_vae, remote_vae_worker,
                loaded_vae, paths, existing_data, session_name,
                paths["manifest"], unique_id,
                config_overrides_vae=config_overrides_vae
            )
            for jid in pending_job_ids:
                manager.complete_job(jid)
            pending_batch = []
            pending_job_ids = []
            _send_distribution_status(manager)

    except InterruptProcessingException:
        # Flush any remaining batch before cleanup
        if pending_batch:
            _flush_pending_batch(
                pending_batch, current_vae_is_remote, current_remote_vae_url,
                per_config_remote_workers, use_remote_vae, remote_vae_worker,
                loaded_vae, paths, existing_data, session_name,
                paths["manifest"], unique_id,
                config_overrides_vae=config_overrides_vae
            )
            for jid in pending_job_ids:
                manager.complete_job(jid)

        # Stop remote workers and deactivate manager
        stop_all_workers(worker_urls)
        manager.deactivate()
        set_distribution_manager(None)

        _cleanup_per_config_remote_workers(per_config_remote_workers)
        if remote_vae_worker:
            remote_vae_worker.wait_completion()
            remote_vae_worker.stop()

        existing_data["meta"] = {
            "positive": positive_text, "negative": negative_text,
            "model": ckpt_name, "seed": seed,
            "vae_batch_size": vae_batch_size,
            "configs_json": configs_json, "resolutions_json": resolutions_json
        }
        save_manifest(paths["manifest"], existing_data)

        loaded_model, loaded_clip, loaded_vae = None, None, None
        patched_model, patched_clip = None, None
        conditioning_cache.clear()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Re-raise so ComfyUI knows execution was interrupted (not completed)
        raise

    # === Wait for remote workers to finish ===
    if manager.has_pending_or_claimed:
        print(f"[Distribution] ⏳ Waiting for remote workers to finish...")
        while manager.has_pending_or_claimed:
            # Check for interrupt while waiting
            try:
                import comfy.model_management as mm
                if mm.processing_interrupted():
                    print(f"\n[Distribution] 🛑 INTERRUPTED while waiting for workers")
                    stop_all_workers(worker_urls)
                    manager.deactivate()
                    set_distribution_manager(None)

                    _cleanup_per_config_remote_workers(per_config_remote_workers)
                    if remote_vae_worker:
                        remote_vae_worker.wait_completion()
                        remote_vae_worker.stop()

                    existing_data["meta"] = {
                        "positive": positive_text, "negative": negative_text,
                        "model": ckpt_name, "seed": seed,
                        "vae_batch_size": vae_batch_size,
                        "configs_json": configs_json, "resolutions_json": resolutions_json
                    }
                    save_manifest(paths["manifest"], existing_data)

                    loaded_model, loaded_clip, loaded_vae = None, None, None
                    patched_model, patched_clip = None, None
                    conditioning_cache.clear()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                    raise InterruptProcessingException()
            except InterruptProcessingException:
                raise
            except:
                pass

            time.sleep(5)
            _send_distribution_status(manager)
            status = manager.get_status()
            print(f"[Distribution] ⏳ Pending: {status['pending']}, "
                  f"Claimed: {status['claimed']}, "
                  f"Completed: {status['completed']}/{status['total']}")

    # === Finalization ===
    stop_all_workers(worker_urls)
    manager.deactivate()

    # Don't set_distribution_manager(None) immediately — a slow worker may still
    # be in the middle of submitting a result. The submit_result route only needs
    # manager != None (it does NOT check is_active). Deactivation already prevents
    # new job claims (claim_job returns 503). Delay the cleanup with a daemon thread
    # so in-flight submissions can still be processed as duplicates.
    def _delayed_manager_cleanup():
        time.sleep(30)
        set_distribution_manager(None)

    threading.Thread(target=_delayed_manager_cleanup, daemon=True).start()

    _cleanup_per_config_remote_workers(per_config_remote_workers)
    if remote_vae_worker:
        print(f"[Distribution] 🌐 Waiting for remote VAE...")
        remote_vae_worker.wait_completion()
        remote_vae_worker.stop()

    print_incompatible_loras_summary(incompatible_loras)

    existing_data["meta"] = {
        "positive": positive_text, "negative": negative_text,
        "model": ckpt_name, "seed": seed,
        "vae_batch_size": vae_batch_size,
        "configs_json": configs_json, "resolutions_json": resolutions_json
    }
    save_manifest(paths["manifest"], existing_data)

    print(f"[Distribution] 🧹 Cleaning up...")
    loaded_model, loaded_clip, loaded_vae = None, None, None
    patched_model, patched_clip = None, None
    conditioning_cache.clear()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    html = get_html_template(session_name, existing_data, unique_id)

    final_status = manager.get_status()
    if job_durations:
        total_elapsed = time.time() - eta_start_time
        total_hours = int(total_elapsed // 3600)
        total_minutes = int((total_elapsed % 3600) // 60)
        total_seconds = int(total_elapsed % 60)
        avg_per_job = sum(job_durations) / len(job_durations)

        print(f"\n{'='*80}")
        print(f"[Distribution] 🎉 DISTRIBUTED GENERATION COMPLETE!")
        print(f"[Distribution] ✅ {final_status.get('completed', total_generated)} total images generated")
        print(f"[Distribution] 📊 Master processed: {total_generated} images ({avg_per_job:.1f}s avg)")
        print(f"[Distribution] ⏱️  {total_hours}h {total_minutes}m {total_seconds}s total")
        if final_status.get('failed', 0) > 0:
            print(f"[Distribution] ❌ {final_status['failed']} jobs failed permanently")

        # Per-worker breakdown
        workers = final_status.get("workers", {})
        if workers:
            print(f"[Distribution] 👥 Worker breakdown:")
            print(f"[Distribution]   📌 master: {total_generated} jobs completed")
            for wid, winfo in workers.items():
                completed = winfo.get("jobs_completed", 0)
                failed = winfo.get("jobs_failed", 0)
                duplicated = winfo.get("jobs_duplicated", 0)
                parts = []
                if failed > 0:
                    parts.append(f"{failed} failed")
                if duplicated > 0:
                    parts.append(f"{duplicated} late/duplicate")
                extra_str = f" ({', '.join(parts)})" if parts else ""
                print(f"[Distribution]   📌 {wid}: {completed} jobs completed{extra_str}")

        print(f"{'='*80}\n")

        # Send completion event to dashboard
        if PromptServer is not None:
            try:
                PromptServer.instance.send_sync("ultimate_grid.progress", {
                    "node": unique_id,
                    "session_name": session_name,
                    "current_job": dist_total,
                    "total_jobs": dist_total,
                    "progress_pct": 100,
                    "eta_str": "Done",
                    "finish_time": time.strftime("%H:%M:%S"),
                    "avg_duration": round(avg_per_job, 1),
                    "last_duration": 0,
                    "complete": True,
                    "total_elapsed": f"{total_hours}h {total_minutes}m {total_seconds}s",
                    "total_generated": final_status.get("completed", total_generated)
                })
            except Exception:
                pass

    return (html,)