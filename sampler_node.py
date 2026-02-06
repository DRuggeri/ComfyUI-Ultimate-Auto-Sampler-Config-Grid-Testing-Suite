"""
Main SamplerGridTester Node for ComfyUI
Orchestrates grid generation across multiple configurations
"""

import re
import torch
import json
import os
import time
import random
import hashlib
import folder_paths
import nodes
import comfy.utils
import comfy.sd
import comfy.samplers
import comfy.model_management
from PIL import Image
import numpy as np

# Import from split modules
from .remote_vae import (
    HF_ENDPOINTS, 
    detect_model_type, 
    remote_decode_hf, 
    RemoteVAEDecodeWorker
)
from .lora_utils import load_and_save_tags
from .config_utils import (
    parse_json_with_error,
    parse_float_input,
    parse_string_input,
    expand_configs,
    prepare_input_jobs,
    sanitize_session_name,
    normalize_str,
    get_files_from_folder,
    parse_lora_definition
)

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

from .html_generator import get_html_template


class SamplerGridTester:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "ckpt_name": (folder_paths.get_filename_list("checkpoints"), ),
                "positive_text": ("STRING", {"multiline": True, "default": "masterpiece, best quality, 1girl"}),
                "negative_text": ("STRING", {"multiline": True, "default": "bad quality, worst quality, lowres"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "denoise": ("STRING", {"default": "1.0", "multiline": False}), 
                "vae_batch_size": ("INT", {"default": 4, "min": -1, "max": 64}),
                "configs_json": ("STRING", {"multiline": True, "default": '[{"sampler": "euler", "scheduler": "normal", "steps": 20, "cfg": 7.0}]'}),
                "resolutions_json": ("STRING", {"default": '[[1024, 1024]]'}),
                "session_name": ("STRING", {"default": "my_session"}),
                "overwrite_existing": ("BOOLEAN", {"default": False, "tooltip": "True = Re-run everything. False = Skip already generated images (Resume)."}),
                "flush_batch_every": ("INT", {"default": 4, "min": 0, "max": 64, "tooltip": "Update dashboard every X images. 0 = Use VAE Batch Size."}),
                "add_random_seeds_to_gens": ("INT", {"default": 0, "min": 0, "max": 100, "tooltip": "Generate X extra images per config using consistent random seeds."}),
                "lookup_and_append_lora_triggerwords": ("BOOLEAN", {"default": False, "tooltip": "Calculates sha256, uses hash to call Civitai API to get triggerwords for loras, caches results to JSON, and appends them to end of prompt."}),
                "remote_vae_endpoint": (["None", "Auto (Experimental)", "SD", "SDXL", "Flux", "HunyuanVideo"], {
                    "default": "None",
                    "tooltip": "Offload VAE decoding to HuggingFace remote endpoints. Auto detects model type, or manually select endpoint. Ignores vae_batch_size and flush_batch_every when enabled."
                }),
  
            },
            "optional": {
                "optional_model": ("MODEL",),
                "optional_clip": ("CLIP",),
                "optional_vae": ("VAE",),
                "optional_positive": ("CONDITIONING",),
                "optional_negative": ("CONDITIONING",),
                "optional_latent": ("LATENT",),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("dashboard_html",)
    FUNCTION = "run_tests"
    CATEGORY = "sampling/testing"


    # --- HELPER METHODS ---
    def is_float_equal(self, a, b, tolerance=1e-5):
        """Robust float comparison"""
        try:
            return abs(float(a) - float(b)) < tolerance
        except:
            return str(a) == str(b)


    def hash_conditioning(self, conditioning):
        """Create a hash of conditioning tensor for change detection"""
        if conditioning is None:
            return "none"
        
        try:
            tensor = conditioning[0][0]
            tensor_bytes = tensor.cpu().numpy().tobytes()
            hash_obj = hashlib.md5(tensor_bytes)
            return hash_obj.hexdigest()[:16]
        except Exception as e:
            print(f"[GridTester] Warning: Could not hash conditioning: {e}")
            return "unknown"


    def get_latent_channels(self, model, optional_latent):
        """Detect the correct number of latent channels for the model"""
        # First, check if we have an optional_latent to extract from
        if optional_latent is not None:
            channels = optional_latent["samples"].shape[1]
            print(f"[GridTester] 🔍 Detected {channels} latent channels from optional_latent")
            return channels
        
        # Try to detect from model
        if model is not None:
            try:
                if hasattr(model, 'model') and hasattr(model.model, 'latent_format'):
                    latent_format = model.model.latent_format
                    if hasattr(latent_format, 'latent_channels'):
                        channels = latent_format.latent_channels
                        print(f"[GridTester] 🔍 Detected {channels} latent channels from model.latent_format")
                        return channels
                
                if hasattr(model, 'model') and hasattr(model.model, 'diffusion_model'):
                    diff_model = model.model.diffusion_model
                    if hasattr(diff_model, 'in_channels'):
                        channels = diff_model.in_channels
                        print(f"[GridTester] 🔍 Detected {channels} latent channels from diffusion_model.in_channels")
                        return channels
            except Exception as e:
                print(f"[GridTester] ⚠️ Could not detect latent channels: {e}")
        
        # Default to 4 (SD1.5/SDXL)
        print(f"[GridTester] 🔍 Using default 4 latent channels (SD1.5/SDXL)")
        return 4


    def find_existing_match(self, existing_items, conf, w, h, current_seed, batch_idx, match_keys):
        """Returns the index of matching item, or -1 if not found"""
        for idx, item in enumerate(existing_items):
            is_match = True
            for k in match_keys:
                val_conf = conf.get(k)
                
                # Override with current job values
                if k == "width": 
                    val_conf = w
                elif k == "height": 
                    val_conf = h
                elif k == "seed": 
                    val_conf = current_seed
                elif k == "batch_idx": 
                    val_conf = batch_idx
                
                val_item = item.get(k)
                
                # Handle model defaults
                if k == "model":
                    if val_item is None:
                        if val_conf != "Default":
                            is_match = False
                            break
                    elif val_conf == "Default" and val_item is None:
                        continue
                
                # Float comparison
                if isinstance(val_conf, float) or isinstance(val_item, float):
                    if not self.is_float_equal(val_conf, val_item):
                        is_match = False
                        break
                
                # String comparison
                elif isinstance(val_conf, str) and isinstance(val_item, str):
                    if normalize_str(val_conf) != normalize_str(val_item):
                        is_match = False
                        break
                
                # Direct comparison
                elif val_item != val_conf:
                    is_match = False
                    break
            
            if is_match:
                return idx
        
        return -1


    def run_tests(self, ckpt_name, positive_text, negative_text, seed, denoise, vae_batch_size, 
                overwrite_existing, flush_batch_every, configs_json, resolutions_json, 
                session_name, unique_id, add_random_seeds_to_gens, lookup_and_append_lora_triggerwords,
                remote_vae_endpoint,
                optional_model=None, optional_clip=None, optional_vae=None, 
                optional_positive=None, optional_negative=None, optional_latent=None):

        # Import the generation logic from the separate module
        from .generation_orchestrator import run_generation_loop
        
        return run_generation_loop(
            self,
            ckpt_name, positive_text, negative_text, seed, denoise, vae_batch_size,
            overwrite_existing, flush_batch_every, configs_json, resolutions_json,
            session_name, unique_id, add_random_seeds_to_gens, lookup_and_append_lora_triggerwords,
            remote_vae_endpoint,
            optional_model, optional_clip, optional_vae,
            optional_positive, optional_negative, optional_latent
        )


# Node class mappings for ComfyUI
NODE_CLASS_MAPPINGS = {
    "SamplerGridTester": SamplerGridTester
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SamplerGridTester": "Sampler Grid Tester"
}