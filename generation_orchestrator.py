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
import comfy.sd  # Required for async workers
from comfy.model_management import InterruptProcessingException

from .trigger_words import collect_unique_prompts_with_triggers, build_prompt_with_triggers
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
                         loaded_vae, paths, existing_data, session_name, manifest_path, unique_id):
    """Flush pending batch using the appropriate VAE decode method.

    Handles three-way dispatch:
      1. Per-config remote VAE (current_vae_is_remote) — uses per-config worker
      2. Global remote VAE (use_remote_vae) — uses global remote_vae_worker
      3. Local VAE — uses loaded_vae for local decode
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
    elif use_remote_vae and remote_vae_worker:
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

    When has_optional_inputs is True, we skip the model/lora/prompt matching since
    those values came from upstream nodes whose changes we cannot reliably track.
    We still match on seed/resolution/sampler/scheduler/steps/cfg/denoise so that
    if the user is ONLY changing upstream model/conditioning, old jobs get re-run.
    """
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

        if has_optional_inputs:
            # When optional inputs are connected, we can't reliably match on model,
            # lora, or prompts because those may come from upstream nodes whose
            # changes we can't detect. Skip these checks entirely so the job
            # is always re-run when optional inputs are connected (unless the user
            # explicitly sets overwrite_existing=False, handled by the caller).
            pass
        else:
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
    optional_positive, optional_negative, optional_latent
):
    """Main generation loop orchestrator."""

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
    total_jobs = len(expanded) * len(input_jobs)
    
    print(f"{'='*80}")
    print(f"[GridTester] 🚀 GENERATION START")
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
        print(f"[GridTester] ⚠️ Optional inputs connected with Resume mode (overwrite_existing=False).")
        print(f"[GridTester] ⚠️ Changes to upstream nodes (models, LoRAs, prompts) connected via optional inputs")
        print(f"[GridTester] ⚠️ CANNOT be automatically detected. Jobs matching sampler/scheduler/steps/cfg/denoise/seed")
        print(f"[GridTester] ⚠️ will be SKIPPED even if upstream model/conditioning changed.")
        print(f"[GridTester] ⚠️ Set overwrite_existing=True to force re-generation of all jobs.")

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
        target_vae = first_conf.get("vae", "Default")
        if target_vae != "Default":
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
    
    # ==== MAIN GENERATION LOOP ====
    print(f"\n{'='*80}\n")
    
    for job_idx, job in enumerate(input_jobs):
        w, h = job["width"], job["height"]
        batch_idx = job["batch_idx"]
        
        for conf_idx, conf in enumerate(expanded):
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
                                             loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id)
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

                cached_model_key = target_model_key
                cached_lora_key = None
                cached_lora_cache_key = None
                latent_channels = get_latent_channels(loaded_model, optional_latent)
                model_switched = True
            else:
                model_switched = False

            # ==== PER-CONFIG VAE SWITCHING ====
            target_vae = conf.get("vae", "Default")
            if target_vae != cached_vae_key:
                # Flush pending batch before switching VAE (they need current VAE for decoding)
                if pending_batch:
                    _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                                         per_config_remote_workers, use_remote_vae, remote_vae_worker,
                                         loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id)
                    pending_batch = []

                if target_vae == "Default":
                    # Revert to model's bundled/default VAE
                    loaded_vae = default_model_vae
                    current_vae_is_remote = False
                    current_remote_vae_url = None
                    print(f"[GridTester] 🎨 Reverting to Default VAE")
                elif is_remote_vae(target_vae):
                    url = extract_remote_vae_url(target_vae)
                    current_vae_is_remote = True
                    current_remote_vae_url = url
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
                        mm_batch.load_models_gpu([patched_clip.patcher], force_patch_weights=True)

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
                                                     loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id)
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

                result_latent, duration = generate_image(
                    patched_model, current_seed, conf["steps"], conf["cfg"],
                    conf["sampler"], conf["scheduler"], final_positive, final_negative,
                    latent_in, conf["denoise"], attention_mode=attention_mode
                )
                
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
                                             loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id)
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
                                     loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id)
                pending_batch = []
    
    # ==== FINALIZATION ====
    if pending_batch:
        _flush_pending_batch(pending_batch, current_vae_is_remote, current_remote_vae_url,
                             per_config_remote_workers, use_remote_vae, remote_vae_worker,
                             loaded_vae, paths, existing_data, session_name, paths["manifest"], unique_id)

    # Shut down per-config remote VAE workers
    _cleanup_per_config_remote_workers(per_config_remote_workers)

    if remote_vae_worker:
        print(f"[GridTester] 🌐 Waiting for remote VAE...")
        remote_vae_worker.wait_completion()
        remote_vae_worker.stop()
    
    print_incompatible_loras_summary(incompatible_loras)
    
    if skipped_count > 0:
        print(f"[GridTester] ⏭️ Skipped {skipped_count} configs")

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