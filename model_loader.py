"""
Model, CLIP, VAE, and LoRA Loading Module
Handles loading and patching of models with LoRAs
"""

import gc
import torch
import folder_paths
import comfy.sd
import comfy.utils

from .lora_utils import LoRAFileNotFoundError
from .config_utils import parse_lora_definition


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
    loaded_vae=None
):
    """
    Load a checkpoint (model, CLIP, VAE) based on configuration.
    
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
        
    Returns:
        tuple: (loaded_model, loaded_clip, loaded_vae)
    """
    # ==== CRITICAL FIX: Check for optional inputs FIRST ====
    # Priority 1: All optional inputs provided - skip checkpoint loading entirely
    if optional_model is not None and optional_clip is not None and optional_vae is not None:
        print(f"[GridTester] 🔌 Using optional MODEL, CLIP, and VAE (skipping checkpoint load)")
        return optional_model, optional_clip, optional_vae
    
    # Priority 2: Some optional inputs provided - load checkpoint for missing pieces
    if optional_model is not None or optional_clip is not None or (optional_vae is not None and not use_remote_vae):
        print(f"[GridTester] 🔌 Using optional inputs (Model: {optional_model is not None}, "
              f"CLIP: {optional_clip is not None}, VAE: {optional_vae is not None})")
        
        # Determine which checkpoint to use
        actual_ckpt = ckpt_name if target_model_name == "Default" else target_model_name
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
            print(f"[GridTester] 📦 Loading from {actual_ckpt} (need - Model: {need_model}, CLIP: {need_clip}, VAE: {need_vae})")
            
            # Load checkpoint with appropriate outputs
            output_vae = need_vae
            output_clip = need_clip or need_model  # We need clip if we need model
            
            out = comfy.sd.load_checkpoint_guess_config(
                ckpt_path, 
                output_vae=output_vae, 
                output_clip=output_clip,
                embedding_directory=folder_paths.get_folder_paths("embeddings")
            )
            
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
        
        print(f"[GridTester] ✅ Loaded {actual_ckpt} with optional overrides")
        return loaded_model, loaded_clip_temp, loaded_vae_temp
    
    # ==== Priority 3: No optional inputs - standard checkpoint loading ====
    if target_model_name == "Default":
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
    
    return loaded_model, loaded_clip, loaded_vae


def load_loras(base_model, base_clip, lora_string, target_model_name, incompatible_loras):
    """
    Load and patch LoRAs onto model and CLIP.
    
    Args:
        base_model: Base model to patch
        base_clip: Base CLIP to patch
        lora_string: LoRA definition string (e.g., "lora1:0.8:0.6 + lora2:1.0:1.0")
        target_model_name: Name of the current model (for incompatibility tracking)
        incompatible_loras: Dict tracking incompatible LoRAs
        
    Returns:
        tuple: (patched_model, patched_clip, should_skip_config)
        
    Raises:
        LoRAFileNotFoundError: If a LoRA file is not found (critical error)
    """
    patched_model = base_model
    patched_clip = base_clip
    
    if lora_string == "None":
        return patched_model, patched_clip, False
    
    active_loras = parse_lora_definition(lora_string)
    
    for lora_def in active_loras:
        lname, lstr_m, lstr_c = lora_def
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
        
        lora_key = f"{target_model_name}:{lname}"
        if lora_key in incompatible_loras:
            return patched_model, patched_clip, True  # Skip this config
        
        try:
            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
            patched_model, patched_clip = comfy.sd.load_lora_for_models(
                patched_model, patched_clip, lora, lstr_m, lstr_c
            )
            print(f"[GridTester] ✅ Loaded LoRA: {lname} (model: {lstr_m}, clip: {lstr_c})")
        except Exception as e:
            print(f"[GridTester] ❌ Failed to load LoRA {lname}: {e}")
            incompatible_loras[lora_key] = (target_model_name, lname, str(e))
            return patched_model, patched_clip, True  # Skip this config
    
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