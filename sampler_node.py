import re
import torch
import json
import os
import time
import random
import itertools
import folder_paths
import nodes
import comfy.utils
import comfy.sd
import comfy.samplers
import comfy.model_management
from PIL import Image
import numpy as np
import hashlib
import requests


try:
    from server import PromptServer
except ImportError:
    PromptServer = None
from .html_generator import get_html_template


def save_dict_to_json(data_dict, file_path):
    try:
        with open(file_path, 'w') as json_file:
            json.dump(data_dict, json_file, indent=4)
            print(f"Data saved to {file_path}")
    except Exception as e:
        print(f"Error saving JSON to file: {e}")



def get_model_version_info(hash_value):
    api_url = f"https://civitai.com/api/v1/model-versions/by-hash/{hash_value}"
    try:
        response = requests.get(api_url)
    except Exception as e:
        print(f"[Lora-Auto-Trigger] {e}")
        return None
    if response.status_code == 200:
        return response.json()
    else:
        return None
    
def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def load_json_from_file(file_path):
    try:
        with open(file_path, 'r') as json_file:
            data = json.load(json_file)
            return data
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON in file: {file_path}")
        raise



def load_and_save_tags(lora_name, force_fetch):
    json_tags_path = "./loras_tags.json"
    lora_tags = load_json_from_file(json_tags_path)
    output_tags = lora_tags.get(lora_name, None) if lora_tags is not None else None
    if output_tags is not None:
        output_tags_list = output_tags
    else:
        output_tags_list = []

    lora_path = folder_paths.get_full_path("loras", lora_name)
    if lora_tags is None or force_fetch or output_tags is None: # search on civitai only if no local cache or forced
        print("[Lora-Auto-Trigger] calculating lora hash")
        LORAsha256 = calculate_sha256(lora_path)
        print("[Lora-Auto-Trigger] requesting infos")
        print(LORAsha256)
        model_info = get_model_version_info(LORAsha256)
        if model_info is not None:
            if "trainedWords" in model_info:
                print("[Lora-Auto-Trigger] tags found!")
                if lora_tags is None:
                    lora_tags = {}
                lora_tags[lora_name] = model_info["trainedWords"]
                save_dict_to_json(lora_tags, json_tags_path)
                output_tags_list = model_info["trainedWords"]
        else:
            print("[Lora-Auto-Trigger] No informations found.")
            if lora_tags is None:
                    lora_tags = {}
            lora_tags[lora_name] = []
            save_dict_to_json(lora_tags,json_tags_path)

    return output_tags_list



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




    # --- HELPER: ROBUST FLOAT COMPARISON ---
    def is_float_equal(self, a, b, tolerance=1e-5):
        try:
            return abs(float(a) - float(b)) < tolerance
        except:
            return str(a) == str(b)


    def hash_conditioning(self, conditioning):
        """
        Create a hash of conditioning tensor for change detection.
        Returns a string hash that uniquely identifies this conditioning.
        """
        if conditioning is None:
            return "none"
        
        try:
            # Conditioning format: [[tensor, dict], ...]
            # Hash the actual tensor data
            tensor = conditioning[0][0]
            
            # Convert to bytes and hash
            tensor_bytes = tensor.cpu().numpy().tobytes()
            hash_obj = hashlib.md5(tensor_bytes)
            return hash_obj.hexdigest()[:16]  # First 16 chars of hash
        except Exception as e:
            print(f"[GridTester] Warning: Could not hash conditioning: {e}")
            return "unknown"



    def get_latent_channels(self, model, optional_latent):
        """
        Detect the correct number of latent channels for the model.
        Returns 16 for SD3/Flux, 4 for SD1.5/SDXL
        """
        # First, check if we have an optional_latent to extract from
        if optional_latent is not None:
            channels = optional_latent["samples"].shape[1]
            print(f"[GridTester] 📏 Detected {channels} latent channels from optional_latent")
            return channels
        
        # Try to detect from model
        if model is not None:
            try:
                # Check model config for latent format
                if hasattr(model, 'model') and hasattr(model.model, 'latent_format'):
                    latent_format = model.model.latent_format
                    if hasattr(latent_format, 'latent_channels'):
                        channels = latent_format.latent_channels
                        print(f"[GridTester] 📏 Detected {channels} latent channels from model.latent_format")
                        return channels
                
                # Alternative: Check diffusion_model
                if hasattr(model, 'model') and hasattr(model.model, 'diffusion_model'):
                    diff_model = model.model.diffusion_model
                    if hasattr(diff_model, 'in_channels'):
                        channels = diff_model.in_channels
                        print(f"[GridTester] 📏 Detected {channels} latent channels from diffusion_model.in_channels")
                        return channels
            except Exception as e:
                print(f"[GridTester] ⚠️ Could not detect latent channels: {e}")
        
        # Default to 4 (SD1.5/SDXL)
        print(f"[GridTester] 📏 Using default 4 latent channels (SD1.5/SDXL)")
        return 4


    # --- HELPER: NORMALIZE PATHS ---
    def normalize_str(self, s):
        if isinstance(s, str):
            return s.replace("\\", "/").strip()
        return s

    def get_files_from_folder(self, input_string, type_key):
        input_norm = input_string.replace("\\", "/")
        if ":" in input_norm: input_norm = input_norm.split(":")[0]
        if not input_norm.endswith("/"): return [input_string]
        
        target_folder = input_norm.rstrip("/")
        all_files = folder_paths.get_filename_list(type_key)
        found = []
        for f in all_files:
            f_norm = f.replace("\\", "/")
            if f_norm.startswith(target_folder + "/"):
                found.append(f)
        if not found: 
            print(f"[GridTester] Warning: No files found in folder '{input_string}' for type '{type_key}'")
            return []
        return found

    def parse_lora_definition(self, lora_string, global_model_strength, global_clip_strength):
        if lora_string == "None": return []
        definitions = []
        parts = lora_string.split(" + ")
        for part in parts:
            part = part.strip()
            if ":" in part:
                segments = part.split(":")
                name = segments[0].strip()
                m_str = float(segments[1]) if len(segments) > 1 else 1.0
                c_str = float(segments[2]) if len(segments) > 2 else 1.0
                definitions.append((name, m_str, c_str))
            else:
                definitions.append((part, global_model_strength, global_clip_strength))
        return definitions

    def parse_float_input(self, input_str):
        try:
            val = json.loads(input_str)
            if isinstance(val, list): return [float(x) for x in val]
            return [float(val)]
        except:
            try:
                if "," in input_str: return [float(x.strip()) for x in input_str.split(",")]
                return [float(input_str)]
            except:
                return [1.0]

    def parse_string_input(self, input_str):
        try:
            val = json.loads(input_str.strip())
            if isinstance(val, list): return [str(x) for x in val]
            return [str(val)]
        except:
            return [input_str]
    
    # --- HELPER: CHECK IF CONFIG ALREADY EXISTS ---
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
                    if self.normalize_str(val_conf) != self.normalize_str(val_item):
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
                optional_model=None, optional_clip=None, optional_vae=None, 
                optional_positive=None, optional_negative=None, optional_latent=None):
        
        
        # ADD THIS AT THE VERY START - VALIDATION
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
        
        # CRITICAL CHECK
        if optional_model and not optional_vae:
            print(f"\n⚠️  WARNING: optional_model is connected but optional_vae is NOT!")
            print(f"   This may cause issues if the model has a non-standard architecture.")
            print(f"   The VAE will be loaded from: {ckpt_name}")
            print(f"   If this fails, connect optional_vae to match your model.\n")
        
        print(f"{'='*80}\n")
        
        incompatible_loras = {}
        skipped_count = 0
        total_generated = 0
    
        def parse_json_with_error(json_str, name):
            try:
                return json.loads(json_str.strip())
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON Error in {name}: {e}")

        try:
            raw_configs = parse_json_with_error(configs_json, "Configs JSON")
            resolutions = parse_json_with_error(resolutions_json, "Resolutions JSON")
            denoise_values = self.parse_float_input(str(denoise))
            pos_prompts = self.parse_string_input(positive_text)
            neg_prompts = self.parse_string_input(negative_text)
        except Exception as e: 
            raise ValueError(f"{e}")

        session_name = re.sub(r'[^\w\-]', '', session_name)
        if not session_name: session_name = "default_session"
        
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        img_dir = os.path.join(base_dir, "images")
        os.makedirs(img_dir, exist_ok=True)
        manifest_path = os.path.join(base_dir, "manifest.json")

        existing_data = {"items": [], "meta": {}}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    d = json.load(f)
                    if isinstance(d, list): existing_data["items"] = d
                    else: existing_data = d
            except: pass

        existing_data["meta"] = {
            "model": "Multi-Model Session",
            "positive": "Multiple" if len(pos_prompts) > 1 else pos_prompts[0],
            "negative": "Multiple" if len(neg_prompts) > 1 else neg_prompts[0],
            "updated": int(time.time()),
            "random_seed_map": existing_data.get("meta", {}).get("random_seed_map", {})  # Preserve seed map
        }

        # --- PREPARE JOBS ---
        input_jobs = [] 
        if optional_latent is not None:
            batch_count = optional_latent["samples"].shape[0]
            for i in range(batch_count):
                single_sample = optional_latent["samples"][i].unsqueeze(0) 
                input_jobs.append({
                    "label": f"Input {i+1}",
                    "width": single_sample.shape[3] * 8,
                    "height": single_sample.shape[2] * 8,
                    "latent": {"samples": single_sample},
                    "batch_idx": i
                })
        else:
            for res in resolutions:
                input_jobs.append({
                    "label": f"{res[0]}x{res[1]}",
                    "width": res[0], "height": res[1],
                    "latent": None, "batch_idx": 0
                })

        # --- GENERATE RANDOM SEED LIST ---
        extra_seeds = []
        if add_random_seeds_to_gens > 0:
            # Use base seed to generate deterministic random seeds
            # This way: same base seed = same random seeds, different base seed = different random seeds
            seed_key = f"{seed}_{add_random_seeds_to_gens}"
            saved_seed_map = existing_data.get("meta", {}).get("random_seed_map", {})
            
            if seed_key in saved_seed_map:
                # Reuse seeds for this base seed
                extra_seeds = saved_seed_map[seed_key]
                print(f"[GridTester] ♻️ Reusing {len(extra_seeds)} saved random seeds for base seed {seed}: {extra_seeds}")
            else:
                # Generate new deterministic random seeds based on base seed
                rng = random.Random(seed)  # Deterministic RNG seeded with base seed
                for i in range(add_random_seeds_to_gens):
                    # Add offset to ensure we don't accidentally match the base seed
                    extra_seeds.append(rng.randint(0, 0xffffffffffffffff))
                
                print(f"[GridTester] 🎲 Generated {len(extra_seeds)} new random seeds for base seed {seed}: {extra_seeds}")
                
                # Save to manifest
                if "random_seed_map" not in existing_data["meta"]:
                    existing_data["meta"]["random_seed_map"] = {}
                existing_data["meta"]["random_seed_map"][seed_key] = extra_seeds

        # --- EXPAND CONFIGS ---
        ALL_SCHEDULERS = comfy.samplers.KSampler.SCHEDULERS
        ALL_SAMPLERS = comfy.samplers.KSampler.SAMPLERS
        expanded = []
        
        if len(pos_prompts) > 1 and len(neg_prompts) > 1 and len(pos_prompts) == len(neg_prompts):
            print("[GridTester] Detected matching prompt lists. Using 1-to-1 Pairing.")
            prompt_pairs = list(zip(pos_prompts, neg_prompts))
        else:
            prompt_pairs = list(itertools.product(pos_prompts, neg_prompts))

        for entry in raw_configs:
            def to_list(x): return x if isinstance(x, list) else [x]
            samplers = ALL_SAMPLERS if entry.get("sampler") == "*" else to_list(entry.get("sampler", "euler"))
            schedulers = ALL_SCHEDULERS if entry.get("scheduler") == "*" else to_list(entry.get("scheduler", "normal"))
            steps_l = to_list(entry.get("steps", 20))
            cfgs = to_list(entry.get("cfg", 7.0))
            str_m = to_list(entry.get("str_model", 1.0))
            str_c = to_list(entry.get("str_clip", 1.0))
            
            raw_models = to_list(entry.get("model", "Default"))
            expanded_models = []
            for m in raw_models:
                if m == "Default": expanded_models.append("Default")
                else: expanded_models.extend(self.get_files_from_folder(m, "checkpoints"))

            # --- LORA STACK EXPANSION ---
            raw_loras = to_list(entry.get("lora", "None"))
            expanded_loras = []
            
            for l in raw_loras:
                if l == "None":
                    expanded_loras.append("None")
                    continue
                
                stack_parts = l.split(" + ")
                expanded_parts = []
                
                for part in stack_parts:
                    if ":" in part:
                        p_split = part.split(":", 1)
                        base_path = p_split[0].strip()
                        args = ":" + p_split[1].strip()
                    else:
                        base_path = part.strip()
                        args = ""
                    
                    norm_path = base_path.replace("\\", "/")
                    if norm_path.endswith("/"):
                        found_files = self.get_files_from_folder(base_path, "loras")
                        expanded_parts.append([f"{f}{args}" for f in found_files])
                    else:
                        expanded_parts.append([part])
                
                for combo in itertools.product(*expanded_parts):
                    expanded_loras.append(" + ".join(combo))

            # --- BUILD BASE CONFIGS ---
            base_combos = []
            for combo in itertools.product(samplers, schedulers, steps_l, cfgs, expanded_loras, str_m, str_c, denoise_values, prompt_pairs, expanded_models):
                base_combos.append({
                    "sampler": combo[0], "scheduler": combo[1], "steps": combo[2],
                    "cfg": combo[3], "lora": combo[4], "str_model": combo[5], "str_clip": combo[6],
                    "denoise": combo[7], 
                    "positive": combo[8][0], 
                    "negative": combo[8][1],
                    "model": combo[9],
                    "seed": seed 
                })

            # --- APPLY SEEDS ---
            for c in base_combos:
                expanded.append(c)
                for extra_seed in extra_seeds:
                    new_c = c.copy()
                    new_c["seed"] = extra_seed
                    expanded.append(new_c)

        expanded.sort(key=lambda x: (x['model'], x['lora'], x['positive'], x['negative']))
        print(f"[GridTester] Processing {len(expanded) * len(input_jobs)} items...")

        cached_model_key, cached_lora_key = None, None
        cached_pos_key, cached_neg_key = None, None
        loaded_model, loaded_clip, loaded_vae = None, None, None
        patched_model, patched_clip = None, None
        final_positive, final_negative = None, None

        pending_batch = []

        # Define match keys based on whether optional conditioning is used

        # --- HANDLE OPTIONAL CONDITIONING ---
        # If optional conditioning is provided, compute hashes for change detection
        if optional_positive or optional_negative:
            pos_hash = self.hash_conditioning(optional_positive)
            neg_hash = self.hash_conditioning(optional_negative)
            print(f"[GridTester] 🔐 Optional conditioning hashes:")
            print(f"  Positive: {pos_hash}")
            print(f"  Negative: {neg_hash}")
            
            # Add hashes to match keys
            MATCH_KEYS = [
                "sampler", "scheduler", "steps", "cfg", "lora", 
                "str_model", "str_clip", "denoise", "seed", 
                "width", "height", "batch_idx", "model",
                "conditioning_pos_hash", "conditioning_neg_hash"  # NEW!
            ]
        else:
            pos_hash = None
            neg_hash = None
            # Use regular prompt matching
            MATCH_KEYS = [
                "sampler", "scheduler", "steps", "cfg", "lora", 
                "str_model", "str_clip", "denoise", "seed", 
                "width", "height", "positive", "negative", "batch_idx", "model"
            ]
        


        def flush_batch(batch_list):
            nonlocal total_generated
            if not batch_list: return
            latents_to_decode = torch.cat([x[0] for x in batch_list], dim=0)
            active_vae = optional_vae if optional_vae is not None else loaded_vae
            
            if active_vae is None:
                ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=False, embedding_directory=folder_paths.get_folder_paths("embeddings"))
                active_vae = out[2]

            decoded = active_vae.decode(latents_to_decode)
            new_items = [] # Only track new items

            for i, img_tensor in enumerate(decoded):
                img_np = 255. * img_tensor.cpu().numpy()
                img = Image.fromarray(np.clip(img_np, 0, 255).astype(np.uint8))
                meta = batch_list[i][1]
                ts = int(time.time() * 100000) + random.randint(0,1000)
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
            
            with open(manifest_path, "w") as f: json.dump(existing_data, f, indent=4)
            
            if PromptServer:
                # --- OPTIMIZATION: Send ONLY new_items, not the whole manifest ---
                PromptServer.instance.send_sync("ultimate_grid.update", {
                    "node": unique_id,
                    "session_name": session_name,
                    "new_items": new_items, 
                    "meta": existing_data["meta"]
                })


        # --- MAIN GENERATION LOOP ---
        for job in input_jobs:
            w, h = job["width"], job["height"]
            batch_idx = job["batch_idx"]
            
            for conf in expanded:
                current_seed = conf["seed"]
                
                # Add conditioning hashes to config if using optional conditioning
                if optional_positive or optional_negative:
                    conf["conditioning_pos_hash"] = pos_hash
                    conf["conditioning_neg_hash"] = neg_hash
                
                # Track actual prompts used (for saving to manifest)
                actual_positive_prompt = conf["positive"]
                actual_negative_prompt = conf["negative"]
                
                # --- SKIP CHECK ---
                match_index = self.find_existing_match(
                    existing_data["items"], 
                    conf, 
                    w, h, 
                    current_seed, 
                    batch_idx, 
                    MATCH_KEYS
                )
                
                if match_index != -1:
                    if not overwrite_existing:
                        skipped_count += 1
                        continue
                    else:
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

                # --- NOW DO THE ACTUAL WORK (only if not skipped) ---
                
                # --- 1. MODEL LOADING ---
                target_model_name = conf["model"]
                
                # ADD DEBUGGING
                print(f"\n[GridTester] 🔧 Model Loading Check:")
                print(f"  target_model_name: {target_model_name}")
                print(f"  cached_model_key: {cached_model_key}")
                print(f"  optional_model exists: {optional_model is not None}")
                print(f"  optional_clip exists: {optional_clip is not None}")
                print(f"  optional_vae exists: {optional_vae is not None}")
                
                
                if target_model_name != cached_model_key:
                    if target_model_name == "Default":
                        # FIXED: Check optional_model FIRST, optional_clip is optional
                        if optional_model:
                            print(f"[GridTester] ✅ Using optional_model")
                            loaded_model = optional_model
                            
                            # CLIP: Use optional if available, otherwise load from ckpt
                            if optional_clip:
                                print(f"[GridTester] ✅ Using optional_clip")
                                loaded_clip = optional_clip
                            else:
                                print(f"[GridTester] ⚠️  Loading CLIP from ckpt_name: {ckpt_name}")
                                # Only load CLIP if we need it (no optional_positive/negative)
                                if not (optional_positive and optional_negative):
                                    ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                                    out = comfy.sd.load_checkpoint_guess_config(
                                        ckpt_path, 
                                        output_vae=False,
                                        output_clip=True, 
                                        embedding_directory=folder_paths.get_folder_paths("embeddings")
                                    )
                                    loaded_clip = out[1]
                                else:
                                    # Don't need CLIP if conditioning is provided
                                    loaded_clip = None
                            
                            # VAE: Use optional if available, otherwise load from ckpt
                            if optional_vae:
                                print(f"[GridTester] ✅ Using optional_vae")
                                loaded_vae = optional_vae
                            else:
                                print(f"[GridTester] ⚠️  Loading VAE from ckpt_name: {ckpt_name}")
                                ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                                out = comfy.sd.load_checkpoint_guess_config(
                                    ckpt_path, 
                                    output_vae=True,
                                    output_clip=False, 
                                    embedding_directory=folder_paths.get_folder_paths("embeddings")
                                )
                                loaded_vae = out[2]
                        
                        else:
                            # NO optional_model - load everything from ckpt_name
                            print(f"[GridTester] 📦 Loading from ckpt_name: {ckpt_name}")
                            ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                            out = comfy.sd.load_checkpoint_guess_config(
                                ckpt_path, 
                                output_vae=True, 
                                output_clip=True, 
                                embedding_directory=folder_paths.get_folder_paths("embeddings")
                            )
                            loaded_model, loaded_clip, loaded_vae = out[:3]
                    
                    else:
                        # Config specifies a model name - load that
                        print(f"[GridTester] 🔄 Switching to checkpoint: {target_model_name}")
                        ckpt_path = folder_paths.get_full_path("checkpoints", target_model_name)
                        out = comfy.sd.load_checkpoint_guess_config(
                            ckpt_path, 
                            output_vae=True, 
                            output_clip=True, 
                            embedding_directory=folder_paths.get_folder_paths("embeddings")
                        )
                        loaded_model, loaded_clip, loaded_vae = out[:3]
                    
                    cached_model_key = target_model_name
                    cached_lora_key, patched_model, patched_clip = None, None, None
                    cached_pos_key, cached_neg_key = None, None
                    
                    # Detect latent channels
                    latent_channels = self.get_latent_channels(loaded_model, optional_latent)
                    print(f"[GridTester] 📏 Latent channels: {latent_channels}")



                # --- 2. LORA ---
                current_lora_key = (conf["lora"], conf["str_model"], conf["str_clip"])
                
                # Always recalculate trigger words for current LoRA config
                lora_triggers = ""
                
                if current_lora_key != cached_lora_key or patched_model is None:
                    curr_m, curr_c = loaded_model, loaded_clip
                    active_loras = self.parse_lora_definition(conf["lora"], conf["str_model"], conf["str_clip"])
                    
                    lora_load_failed = False
                    failed_lora_name = None
                    
                    for lora_def in active_loras:
                        lname, lstr_m, lstr_c = lora_def
                        path = folder_paths.get_full_path("loras", lname)
                        
                        if not path:
                            print(f"[GridTester] ⚠️ WARNING: LoRA not found: {lname}")
                            continue
                        
                        # Check if this LoRA is already known to be incompatible with this model
                        lora_model_key = f"{lname}|{target_model_name}"
                        if lora_model_key in incompatible_loras:
                            print(f"[GridTester] ⏭️ Skipping known incompatible LoRA: {lname}")
                            lora_load_failed = True
                            failed_lora_name = lname
                            break
                        
                        try:
                            lora_data = comfy.utils.load_torch_file(path)
                            curr_m, curr_c = comfy.sd.load_lora_for_models(curr_m, curr_c, lora_data, lstr_m, lstr_c)
                            # print(f"[GridTester] ✅ Loaded LoRA: {lname}")
                        
                        except RuntimeError as e:
                            error_msg = str(e)
                            
                            # Check if it's an incompatibility error
                            if "shape" in error_msg and "invalid for input" in error_msg:
                                # Log once per LoRA+Model combination
                                if lora_model_key not in incompatible_loras:
                                    incompatible_loras[lora_model_key] = (target_model_name, lname, error_msg)
                                    print(f"\n{'='*80}")
                                    print(f"[GridTester] ❌ INCOMPATIBLE LORA DETECTED")
                                    print(f"  LoRA: {lname}")
                                    print(f"  Model: {target_model_name}")
                                    print(f"  Error: {error_msg[:150]}...")
                                    print(f"  This LoRA will be SKIPPED for all remaining configs with this model.")
                                    print(f"{'='*80}\n")
                                
                                lora_load_failed = True
                                failed_lora_name = lname
                                break
                            else:
                                # Other error - re-raise
                                raise
                        
                        except Exception as e:
                            print(f"[GridTester] ❌ Unexpected error loading LoRA {lname}: {e}")
                            lora_load_failed = True
                            failed_lora_name = lname
                            break
                    
                    # If LoRA loading failed, skip this entire config
                    if lora_load_failed:
                        print(f"[GridTester] ⏭️ Skipping config due to failed LoRA: {failed_lora_name}")
                        skipped_count += 1
                        continue  # Skip to next config
                    
                    patched_model, patched_clip = curr_m, curr_c
                    cached_lora_key = current_lora_key
                    # Clear conditioning cache when LoRA changes
                    cached_pos_key, cached_neg_key = None, None
                
                # Fetch trigger words EVERY TIME (even if LoRA cached)
                # This ensures triggers are available for every prompt variation
                if lookup_and_append_lora_triggerwords and conf["lora"] != "None":
                    active_loras = self.parse_lora_definition(conf["lora"], conf["str_model"], conf["str_clip"])
                    trigger_list = []  # Use list instead of string concatenation
                    
                    for lora_def in active_loras:
                        lname, lstr_m, lstr_c = lora_def
                        try:
                            civitai_tags_list = load_and_save_tags(lname, force_fetch=False)
                            if len(civitai_tags_list) > 0:
                                for tags in civitai_tags_list:
                                    trigger_list.append(tags)  # Preserve original format
                        except Exception as e:
                            print(f"[GridTester] Warning: Could not fetch trigger words for {lname}: {e}")
                    
                    # Join with ", " - only adds separators between items, not at end
                    lora_triggers = ", ".join(trigger_list)
                    
                    if lora_triggers:
                        print(f"[GridTester] Trigger words: {lora_triggers}")




                # --- 3. CONDITIONING ---
                if optional_positive: 
                    final_positive = optional_positive
                    actual_positive_prompt = conf["positive"]  # Can't know what optional contains
                else:
                    # Build the full prompt with trigger words
                    full_positive = conf["positive"]
                    if lora_triggers:
                        full_positive = f"{lora_triggers}, {conf['positive']}"
                    
                    actual_positive_prompt = full_positive  # Track for metadata
                    
                    # Use the FULL prompt (with triggers) as cache key
                    if full_positive == cached_pos_key and final_positive:
                        pass  # Use cached conditioning
                    else:
                        tokens = patched_clip.tokenize(full_positive)
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        final_positive = [[cond, {"pooled_output": pooled}]]
                        cached_pos_key = full_positive
                        if lora_triggers:
                            print(f"[GridTester] 📝 Prompt with triggers: {full_positive[:100]}...")

                if optional_negative:
                    final_negative = optional_negative
                    actual_negative_prompt = conf["negative"]
                else:
                    actual_negative_prompt = conf["negative"]
                    if conf["negative"] == cached_neg_key and final_negative:
                        pass  # Use cached
                    else:
                        tokens = patched_clip.tokenize(conf["negative"])
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        final_negative = [[cond, {"pooled_output": pooled}]]
                        cached_neg_key = conf["negative"]


                #4 --- GENERATE ---
                if job["latent"] is not None: 
                    latent_in = {"samples": job["latent"]["samples"].clone()}
                else: 
                    # FIXED: Use detected channel count instead of hardcoded 4
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
                    
                    # Create metadata with actual prompts
                    
                    # When saving metadata:
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
                    
                    # If using optional conditioning, also save the hashes
                    if optional_positive or optional_negative:
                        meta["conditioning_pos_hash"] = pos_hash
                        meta["conditioning_neg_hash"] = neg_hash
                    
                    pending_batch.append((result[0]["samples"], meta))


                except comfy.model_management.InterruptProcessingException:
                    raise 
                except Exception as e:
                    print(f"[GridTester] Generation Failed (Skipping Config): {e}")
                    continue
                

                # --- 5. FLUSHING ---
                # THIS WAS MISSING! Without this, pending_batch never gets saved!
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
        
        # Save final manifest
        with open(manifest_path, "w") as f: json.dump(existing_data, f, indent=4)
        
        html = get_html_template(session_name, existing_data, unique_id)
        return (html,)