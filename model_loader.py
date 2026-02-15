"""
Model, CLIP, VAE, and LoRA Loading Module (WITH CACHING)
Handles loading and patching of models with LoRAs using intelligent caching
"""

import gc
import time
import torch
import folder_paths
import comfy.sd
import comfy.utils

from .lora_utils import LoRAFileNotFoundError
from .config_utils import parse_lora_definition


def load_vae_by_name(vae_name):
    """
    Load a VAE by filename from the vae folder.
    Follows the pattern of ComfyUI's VAELoader.load_vae().

    Args:
        vae_name: Filename of the VAE model

    Returns:
        comfy.sd.VAE: Loaded VAE instance
    """
    vae_path = folder_paths.get_full_path_or_raise("vae", vae_name)
    sd, metadata = comfy.utils.load_torch_file(vae_path, return_metadata=True)
    vae = comfy.sd.VAE(sd=sd, metadata=metadata)
    vae.throw_exception_if_invalid()
    return vae


def load_checkpoint(
    target_model_name,
    ckpt_name,
    use_remote_vae,
    optional_model=None,
    optional_clip=None,
    optional_vae=None,
    optional_positive=None,
    optional_negative=None,
    loaded_clip=None,
    loaded_vae=None,
    model_cache=None  # NEW: Model cache instance
):
    """
    Load a checkpoint (model, CLIP, VAE) based on configuration.
    NOW WITH CACHING SUPPORT!
    
    Args:
        target_model_name: Name of the checkpoint to load (or "Default")
        ckpt_name: Default checkpoint name from node input
        use_remote_vae: Whether to use remote VAE
        optional_model: Optional pre-loaded model
        optional_clip: Optional pre-loaded CLIP
        optional_vae: Optional pre-loaded VAE
        optional_positive: Optional pre-encoded positive conditioning
        optional_negative: Optional pre-encoded negative conditioning
        loaded_clip: Currently loaded CLIP (to avoid reloading)
        loaded_vae: Currently loaded VAE (to avoid reloading)
        model_cache: ModelCache instance (optional, for caching)
        
    Returns:
        tuple: (loaded_model, loaded_clip, loaded_vae)
    """
    # Determine actual checkpoint name
    actual_ckpt = ckpt_name if target_model_name == "Default" else target_model_name
    
    # ==== PRIORITY 1: Check cache first (if available) ====
    if model_cache is not None:
        cached = model_cache.get_base_model(actual_ckpt)
        if cached is not None:
            cached_model, cached_clip, cached_vae = cached
            
            # Use cached values, but respect optional overrides
            final_model = optional_model if optional_model is not None else cached_model
            final_clip = optional_clip if optional_clip is not None else cached_clip
            final_vae = optional_vae if optional_vae is not None and not use_remote_vae else (None if use_remote_vae else cached_vae)
            
            return final_model, final_clip, final_vae
    
    # ==== PRIORITY 2: Check for optional inputs ====
    # All optional inputs provided - skip checkpoint loading entirely
    if optional_model is not None and optional_clip is not None and optional_vae is not None:
        print(f"[GridTester] 🔌 Using optional MODEL, CLIP, and VAE (skipping checkpoint load)")
        return optional_model, optional_clip, optional_vae
    
    # Some optional inputs provided - load checkpoint for missing pieces
    if optional_model is not None or optional_clip is not None or (optional_vae is not None and not use_remote_vae):
        print(f"[GridTester] 🔌 Using optional inputs (Model: {optional_model is not None}, "
              f"CLIP: {optional_clip is not None}, VAE: {optional_vae is not None})")
        
        ckpt_path = folder_paths.get_full_path("checkpoints", actual_ckpt)
        
        # Determine what we need to load from checkpoint
        need_model = optional_model is None
        need_clip = optional_clip is None and not (optional_positive and optional_negative)
        need_vae = optional_vae is None and not use_remote_vae
        
        # Load from checkpoint only what we need
        loaded_model = optional_model
        loaded_clip_temp = optional_clip
        loaded_vae_temp = optional_vae
        
        if need_model or need_clip or need_vae:
            start_time = time.time()
            print(f"[GridTester] 💿 LOADING FROM DISK: {actual_ckpt}")
            print(f"[GridTester]    (need - Model: {need_model}, CLIP: {need_clip}, VAE: {need_vae})")
            
            # Load checkpoint with appropriate outputs
            output_vae = need_vae
            output_clip = need_clip or need_model  # We need clip if we need model
            
            out = comfy.sd.load_checkpoint_guess_config(
                ckpt_path, 
                output_vae=output_vae, 
                output_clip=output_clip,
                embedding_directory=folder_paths.get_folder_paths("embeddings")
            )
            
            elapsed = time.time() - start_time
            print(f"[GridTester] ✅ Loaded from disk in {elapsed:.2f}s")
            
            # Record disk load in cache
            if model_cache is not None:
                model_cache.record_disk_load(is_base_model=True, load_time=elapsed)
            
            # Extract what we need
            if need_model:
                loaded_model = out[0]
            if need_clip:
                loaded_clip_temp = out[1]
            if need_vae and output_vae:
                loaded_vae_temp = out[2]
        
        # Handle special cases
        if loaded_clip_temp is None and (optional_positive and optional_negative):
            loaded_clip_temp = None  # Using optional conditioning, don't need CLIP
        
        if use_remote_vae:
            loaded_vae_temp = None  # Remote VAE mode
        
        # Store in cache if available
        if model_cache is not None and loaded_model is not None:
            model_cache.put_base_model(actual_ckpt, loaded_model, loaded_clip_temp, loaded_vae_temp)
        
        return loaded_model, loaded_clip_temp, loaded_vae_temp
    
    # ==== PRIORITY 3: No optional inputs and no cache - standard checkpoint loading ====
    start_time = time.time()
    
    if target_model_name == "Default":
        print(f"[GridTester] 💿 LOADING FROM DISK: {ckpt_name} (default)")
    else:
        print(f"[GridTester] 💿 LOADING FROM DISK: {target_model_name}")
    
    ckpt_path = folder_paths.get_full_path("checkpoints", actual_ckpt)
    
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
    
    elapsed = time.time() - start_time
    print(f"[GridTester] ✅ Loaded from disk in {elapsed:.2f}s")
    
    # Record disk load in cache
    if model_cache is not None:
        model_cache.record_disk_load(is_base_model=True, load_time=elapsed)
        # Store in cache
        model_cache.put_base_model(actual_ckpt, loaded_model, loaded_clip, loaded_vae)
    
    return loaded_model, loaded_clip, loaded_vae


def _import_gguf():
    """
    Lazy import of ComfyUI-GGUF modules.
    Returns (GGMLOps, gguf_sd_loader, gguf_clip_loader, GGUFModelPatcher).
    Raises RuntimeError if ComfyUI-GGUF is not installed.
    """
    try:
        from ComfyUI_GGUF.ops import GGMLOps
        from ComfyUI_GGUF.loader import gguf_sd_loader, gguf_clip_loader
        from ComfyUI_GGUF.nodes import GGUFModelPatcher
        return GGMLOps, gguf_sd_loader, gguf_clip_loader, GGUFModelPatcher
    except ImportError:
        raise RuntimeError(
            "ComfyUI-GGUF is required for GGUF model loading but is not installed.\n"
            "Install it from: https://github.com/city96/ComfyUI-GGUF"
        )


def resolve_text_encoder_path(filename):
    """
    Resolve a text encoder filename to its full path.
    Searches text_encoders, clip, and clip_gguf folder paths.
    """
    for folder_key in ["text_encoders", "clip", "clip_gguf"]:
        try:
            path = folder_paths.get_full_path(folder_key, filename)
            if path:
                return path
        except (KeyError, Exception):
            continue
    raise FileNotFoundError(f"Text encoder not found: {filename}")


def load_diffusion_model_and_clip(
    model_name,
    model_type,
    text_encoder_paths,
    clip_type_str,
    gguf_options=None,
    use_remote_vae=False,
    optional_model=None,
    optional_clip=None,
    optional_vae=None,
    model_cache=None
):
    """
    Load a diffusion model (unet) + separate CLIP text encoders.
    Used for GGUF and standalone diffusion models.

    Args:
        model_name: Filename of the diffusion model / GGUF model
        model_type: "diffusion_model" or "gguf"
        text_encoder_paths: List of text encoder filenames
        clip_type_str: CLIPType string (e.g. "flux", "sdxl", "stable_diffusion")
        gguf_options: Dict with dequant_dtype, patch_dtype, patch_on_device (GGUF only)
        use_remote_vae: Whether remote VAE is enabled
        optional_model: Optional pre-loaded model override
        optional_clip: Optional pre-loaded CLIP override
        optional_vae: Optional pre-loaded VAE override
        model_cache: ModelCache instance (optional)

    Returns:
        tuple: (loaded_model, loaded_clip, loaded_vae)
        Note: loaded_vae is always optional_vae or None (no bundled VAE)
    """
    import comfy.model_management

    # Build cache key for this model+text_encoder combo
    te_key = "|".join(sorted(text_encoder_paths)) if text_encoder_paths else ""
    cache_key = f"{model_name}::{model_type}::{te_key}"

    # Check cache first
    if model_cache is not None:
        cached = model_cache.get_base_model(cache_key)
        if cached is not None:
            cached_model, cached_clip, cached_vae = cached
            final_model = optional_model if optional_model is not None else cached_model
            final_clip = optional_clip if optional_clip is not None else cached_clip
            final_vae = optional_vae if optional_vae is not None else cached_vae
            return final_model, final_clip, final_vae

    # Use optional overrides if all provided
    if optional_model is not None and optional_clip is not None:
        print(f"[GridTester] 🔌 Using optional MODEL and CLIP (skipping {model_type} load)")
        return optional_model, optional_clip, optional_vae

    start_time = time.time()

    # ---- Load the UNet / diffusion model ----
    loaded_model = optional_model
    if loaded_model is None:
        print(f"[GridTester] 💿 LOADING {model_type.upper()}: {model_name}")

        if model_type == "gguf":
            GGMLOps, gguf_sd_loader, _, GGUFModelPatcher = _import_gguf()

            # Resolve path - try unet_gguf first, then unet/diffusion_models
            unet_path = None
            for folder_key in ["unet_gguf", "unet", "diffusion_models"]:
                try:
                    unet_path = folder_paths.get_full_path(folder_key, model_name)
                    if unet_path:
                        break
                except (KeyError, Exception):
                    continue
            if unet_path is None:
                raise FileNotFoundError(f"GGUF model not found: {model_name}")

            ops = GGMLOps()
            if gguf_options:
                dequant = gguf_options.get("dequant_dtype", "default")
                if dequant not in ("default", None):
                    if dequant == "target":
                        ops.Linear.dequant_dtype = "target"
                    else:
                        ops.Linear.dequant_dtype = getattr(torch, dequant)
                patch = gguf_options.get("patch_dtype", "default")
                if patch not in ("default", None):
                    if patch == "target":
                        ops.Linear.patch_dtype = "target"
                    else:
                        ops.Linear.patch_dtype = getattr(torch, patch)

            sd, extra = gguf_sd_loader(unet_path)
            loaded_model = comfy.sd.load_diffusion_model_state_dict(
                sd, model_options={"custom_operations": ops}
            )
            if loaded_model is None:
                raise RuntimeError(f"Could not detect model type of GGUF: {model_name}")
            loaded_model = GGUFModelPatcher.clone(loaded_model)
            if gguf_options and gguf_options.get("patch_on_device"):
                loaded_model.patch_on_device = True

        elif model_type == "diffusion_model":
            unet_path = folder_paths.get_full_path("diffusion_models", model_name)
            if unet_path is None:
                # Also try "unet" folder key
                unet_path = folder_paths.get_full_path("unet", model_name)
            if unet_path is None:
                raise FileNotFoundError(f"Diffusion model not found: {model_name}")

            loaded_model = comfy.sd.load_diffusion_model(unet_path, model_options={})

        print(f"[GridTester] ✅ Model loaded in {time.time() - start_time:.2f}s")

    # ---- Load CLIP text encoders ----
    loaded_clip = optional_clip
    if loaded_clip is None and text_encoder_paths:
        clip_start = time.time()
        print(f"[GridTester] 💿 LOADING TEXT ENCODERS: {text_encoder_paths}")

        clip_type = getattr(comfy.sd.CLIPType, clip_type_str.upper(), comfy.sd.CLIPType.STABLE_DIFFUSION)
        resolved_paths = [resolve_text_encoder_path(p) for p in text_encoder_paths]
        is_any_gguf = any(p.endswith(".gguf") for p in text_encoder_paths)

        if is_any_gguf:
            GGMLOps, _, gguf_clip_loader, GGUFModelPatcher = _import_gguf()

            clip_data = []
            for p in resolved_paths:
                if p.endswith(".gguf"):
                    clip_data.append(gguf_clip_loader(p))
                else:
                    sd_te = comfy.utils.load_torch_file(p, safe_load=True)
                    clip_data.append(sd_te)

            loaded_clip = comfy.sd.load_text_encoder_state_dicts(
                clip_type=clip_type,
                state_dicts=clip_data,
                model_options={
                    "custom_operations": GGMLOps,
                    "initial_device": comfy.model_management.text_encoder_offload_device()
                },
                embedding_directory=folder_paths.get_folder_paths("embeddings")
            )
            loaded_clip.patcher = GGUFModelPatcher.clone(loaded_clip.patcher)
        else:
            loaded_clip = comfy.sd.load_clip(
                ckpt_paths=resolved_paths,
                embedding_directory=folder_paths.get_folder_paths("embeddings"),
                clip_type=clip_type
            )

        print(f"[GridTester] ✅ Text encoders loaded in {time.time() - clip_start:.2f}s")

    elapsed = time.time() - start_time
    print(f"[GridTester] ✅ Total {model_type} loading: {elapsed:.2f}s")

    # VAE: non-checkpoint models have no bundled VAE
    loaded_vae = optional_vae  # Could be None

    # Cache the loaded model
    if model_cache is not None and loaded_model is not None:
        model_cache.record_disk_load(is_base_model=True, load_time=elapsed)
        model_cache.put_base_model(cache_key, loaded_model, loaded_clip, loaded_vae)

    return loaded_model, loaded_clip, loaded_vae


def load_loras(base_model, base_clip, lora_string, target_model_name, incompatible_loras, model_cache=None):
    """
    Load and patch LoRAs onto model and CLIP.
    NOW WITH THREE-TIER CACHING SUPPORT!
    
    Tier 1: LoRA File Cache - Caches individual LoRA files (A, B, C)
    Tier 2: Incremental State - Reuses partial patched states (A+B+C when need A+B+C+D)
    Tier 3: Complete Result Cache - Caches final combinations (A+B+C)
    
    Args:
        base_model: Base model to patch
        base_clip: Base CLIP to patch
        lora_string: LoRA definition string (e.g., "lora1:0.8:0.6 + lora2:1.0:1.0")
        target_model_name: Name of the current model (for incompatibility tracking)
        incompatible_loras: Dict tracking incompatible LoRAs
        model_cache: ModelCache instance (optional, for caching)
        
    Returns:
        tuple: (patched_model, patched_clip, should_skip_config)
        
    Raises:
        LoRAFileNotFoundError: If a LoRA file is not found (critical error)
    """
    # ==== TIER 3: Check complete result cache first ====
    if model_cache is not None and lora_string != "None":
        cached = model_cache.get_lora_model(target_model_name, lora_string)
        if cached is not None:
            patched_model, patched_clip = cached
            return patched_model, patched_clip, False
    
    # ==== Handle "None" case ====
    if lora_string == "None":
        return base_model, base_clip, False
    
    # ==== TIER 2: Check incremental cache (can we reuse partial state?) ====
    start_model = base_model
    start_clip = base_clip
    start_index = 0  # Which LoRA to start applying from
    
    if model_cache is not None and hasattr(model_cache, 'enable_incremental') and model_cache.enable_incremental:
        incremental = model_cache.check_incremental_cache(target_model_name, lora_string)
        
        if incremental is not None:
            partial_model, partial_clip, num_applied = incremental
            
            # Start from the partial state!
            start_model = partial_model
            start_clip = partial_clip
            start_index = num_applied
            
            lora_parts = lora_string.split(" + ")
            remaining = len(lora_parts) - num_applied
            
            print(f"[GridTester] ⚡ INCREMENTAL: Reusing {num_applied} cached LoRAs, applying {remaining} new")
    
    # ==== Parse LoRA string ====
    start_time = time.time()
    active_loras = parse_lora_definition(lora_string)
    
    # Display what we're doing
    if start_index == 0:
        # Loading from scratch
        lora_display = lora_string[:60] + "..." if len(lora_string) > 60 else lora_string
        print(f"[GridTester] 🔧 LOADING LORAS: {lora_display}")
    else:
        # Incremental - show what we're adding
        remaining_loras = active_loras[start_index:]
        remaining_str = " + ".join([lname for lname, _, _ in remaining_loras])
        remaining_display = remaining_str[:60] + "..." if len(remaining_str) > 60 else remaining_str
        print(f"[GridTester] 🔧 APPLYING REMAINING LORAS: {remaining_display}")
    
    # ==== TIER 1: Apply LoRAs (with file caching) ====
    patched_model = start_model
    patched_clip = start_clip
    
    # Start from start_index (may skip already-applied LoRAs from incremental cache)
    for i in range(start_index, len(active_loras)):
        lora_def = active_loras[i]
        lname, lstr_m, lstr_c = lora_def
        
        # Get full path
        lora_path = folder_paths.get_full_path("loras", lname)
        
        # CRITICAL: Check if lora_path is valid - if not, STOP EVERYTHING
        if lora_path is None:
            error_msg = (
                f"LoRA file not found: {lname}\n\n"
                f"❌ CRITICAL ERROR - All jobs stopped!\n\n"
                f"Please check:\n"
                f"  1. The LoRA file exists in your ComfyUI/models/loras folder\n"
                f"  2. The filename is correct (case-sensitive): {lname}\n"
                f"  3. Path separators are correct (/ vs \\)\n\n"
                f"Searched for: {lname}\n"
                f"Result: File not found in loras directory"
            )
            print(f"\n{'='*80}")
            print(f"[GridTester] 🚨 {error_msg}")
            print(f"{'='*80}\n")
            raise LoRAFileNotFoundError(lname, error_msg)
        
        # Check for known incompatibilities
        lora_key = f"{target_model_name}:{lname}"
        if lora_key in incompatible_loras:
            elapsed = time.time() - start_time
            if model_cache is not None:
                model_cache.record_disk_load(is_base_model=False, load_time=elapsed)
            return patched_model, patched_clip, True  # Skip this config
        
        # ==== NEW: Check file cache before loading from disk ====
        lora_data = None
        if model_cache is not None and hasattr(model_cache, 'get_lora_file'):
            # Create LoRA part string for cache (path:model_str:clip_str)
            lora_part = f"{lname}:{lstr_m}:{lstr_c}"
            lora_data = model_cache.get_lora_file(lora_part)
        
        # Load from disk if not in cache
        if lora_data is None:
            load_start = time.time()
            
            try:
                lora_data = comfy.utils.load_torch_file(lora_path, safe_load=True)
                
                load_elapsed = time.time() - load_start
                
                # Store in file cache for next time
                if model_cache is not None and hasattr(model_cache, 'put_lora_file'):
                    lora_part = f"{lname}:{lstr_m}:{lstr_c}"
                    model_cache.put_lora_file(lora_part, lora_data)
                    
                    # Record individual file disk load
                    if hasattr(model_cache, 'record_lora_file_disk_load'):
                        model_cache.record_lora_file_disk_load(load_elapsed)
                
            except Exception as e:
                print(f"[GridTester]    ❌ Failed to load: {lname}: {e}")
                incompatible_loras[lora_key] = (target_model_name, lname, str(e))
                elapsed = time.time() - start_time
                if model_cache is not None:
                    model_cache.record_disk_load(is_base_model=False, load_time=elapsed)
                return patched_model, patched_clip, True  # Skip this config
        
        # Apply the LoRA
        try:
            patched_model, patched_clip = comfy.sd.load_lora_for_models(
                patched_model, patched_clip, lora_data, lstr_m, lstr_c
            )
            # print(f"[GridTester]    ✅ Applied: {lname} (model: {lstr_m}, clip: {lstr_c})")
        except Exception as e:
            print(f"[GridTester]    ❌ Failed to apply: {lname}: {e}")
            incompatible_loras[lora_key] = (target_model_name, lname, str(e))
            elapsed = time.time() - start_time
            if model_cache is not None:
                model_cache.record_disk_load(is_base_model=False, load_time=elapsed)
            return patched_model, patched_clip, True  # Skip this config
    
    elapsed = time.time() - start_time
    
    if start_index == 0:
        print(f"[GridTester] ✅ All LoRAs loaded in {elapsed:.2f}s")
    else:
        print(f"[GridTester] ✅ Remaining LoRAs applied in {elapsed:.2f}s")
    
    # ==== Store in caches ====
    if model_cache is not None:
        # Record the operation time
        model_cache.record_disk_load(is_base_model=False, load_time=elapsed)
        
        # Store complete result in result cache
        model_cache.put_lora_model(target_model_name, lora_string, patched_model, patched_clip)
        
        # Update incremental state (for next incremental check)
        if hasattr(model_cache, 'update_incremental_cache'):
            model_cache.update_incremental_cache(target_model_name, lora_string, patched_model, patched_clip)
    
    return patched_model, patched_clip, False


def cleanup_model_references(patched_model, patched_clip, conditioning_cache):
    """
    Clean up old model references to free memory.
    
    Args:
        patched_model: Patched model to delete
        patched_clip: Patched CLIP to delete
        conditioning_cache: Conditioning cache to clear
    """
    print(f"[GridTester] 🧹 Switching models - clearing old references and cache...")
    
    # Clear the conditioning cache - it holds tensors from the old CLIP
    cleared_count = len(conditioning_cache["positive"]) + len(conditioning_cache["negative"])
    conditioning_cache["positive"].clear()
    conditioning_cache["negative"].clear()
    print(f"[GridTester] 🧹 Cleared {cleared_count} cached encodings")
    
    # Delete old patched models
    if patched_model is not None:
        del patched_model
    if patched_clip is not None:
        del patched_clip
    
    # Force garbage collection to free memory
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"[GridTester] 🧹 Memory cleanup complete")
    
    return None, None


def get_latent_channels(model, optional_latent):
    """
    Get the number of latent channels from the model.
    
    Args:
        model: The model to query
        optional_latent: Optional latent tensor
        
    Returns:
        int: Number of latent channels
    """
    if optional_latent is not None:
        return optional_latent["samples"].shape[1]
    
    # Try to get from model
    try:
        if hasattr(model.model, 'latent_format'):
            return model.model.latent_format.latent_channels
        elif hasattr(model.model, 'model_config'):
            return model.model.model_config.latent_format.latent_channels
    except:
        pass
    
    # Default to 4 for SD1.5/SDXL
    return 4


def load_loras_for_preencoding(base_model, base_clip, lora_string):
    """
    Load LoRAs specifically for the pre-encoding stage.
    Simpler version without error tracking since pre-encoding uses first config only.
    
    Args:
        base_model: Base model to patch
        base_clip: Base CLIP to patch
        lora_string: LoRA definition string
        
    Returns:
        tuple: (patched_model, patched_clip)
    """
    if lora_string == "None":
        return base_model, base_clip
    
    print(f"[GridTester] 🔧 Applying LoRA for pre-encoding: {lora_string}")
    
    curr_m, curr_c = base_model, base_clip
    active_loras = parse_lora_definition(lora_string)
    
    for lora_def in active_loras:
        lname, lstr_m, lstr_c = lora_def
        path = folder_paths.get_full_path("loras", lname)
        
        if path is None:
            print(f"[GridTester] ⚠️ LoRA not found for pre-encoding: {lname}")
            continue
        
        try:
            lora_data = comfy.utils.load_torch_file(path, safe_load=True)
            curr_m, curr_c = comfy.sd.load_lora_for_models(
                curr_m, curr_c, lora_data, lstr_m, lstr_c
            )
            print(f"[GridTester] ✅ Pre-encoding LoRA loaded: {lname}")
        except Exception as e:
            print(f"[GridTester] ⚠️ Failed to load LoRA for pre-encoding: {lname} - {e}")
    
    return curr_m, curr_c


def print_incompatible_loras_summary(incompatible_loras):
    """
    Print a summary of all incompatible LoRAs encountered.
    
    Args:
        incompatible_loras: Dict of incompatible LoRA information
    """
    if not incompatible_loras:
        return
    
    print(f"\n{'='*80}")
    print(f"[GridTester] 🚨 INCOMPATIBLE LORA SUMMARY")
    print(f"{'='*80}")
    for key, (model, lora, error) in incompatible_loras.items():
        print(f"  ❌ {lora}")
        print(f"     Model: {model}")
        print(f"     Error: {error}")
        print(f"     Likely cause: LoRA trained for different architecture")
        print(f"     Suggestion: Check if LoRA is SD1.5/SDXL/SD3/Flux compatible")
        print()
    print(f"{'='*80}\n")