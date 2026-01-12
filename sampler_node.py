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

    def run_tests(self, ckpt_name, positive_text, negative_text, seed, denoise, vae_batch_size, overwrite_existing, flush_batch_every, configs_json, resolutions_json, session_name, unique_id, add_random_seeds_to_gens, optional_model=None, optional_clip=None, optional_vae=None, optional_positive=None, optional_negative=None, optional_latent=None):
        
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
        MATCH_KEYS = ["sampler", "scheduler", "steps", "cfg", "lora", "str_model", "str_clip", "denoise", "seed", "width", "height", "positive", "negative", "batch_idx", "model"]
        
        skipped_count = 0
        total_generated = 0

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
                
                # --- CRITICAL FIX: CHECK FOR SKIP FIRST, BEFORE ANY WORK ---
                match_index = self.find_existing_match(existing_data["items"], conf, w, h, current_seed, batch_idx, MATCH_KEYS)
                
                if match_index != -1:
                    if not overwrite_existing:
                        skipped_count += 1
                        continue  # Skip this config entirely
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
                if target_model_name != cached_model_key:
                    if target_model_name == "Default":
                        if optional_model and optional_clip:
                            loaded_model, loaded_clip = optional_model, optional_clip
                            if optional_vae: loaded_vae = optional_vae
                            else:
                                ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                                out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=False, embedding_directory=folder_paths.get_folder_paths("embeddings"))
                                loaded_vae = out[2]
                        else:
                            ckpt_path = folder_paths.get_full_path("checkpoints", ckpt_name)
                            out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))
                            loaded_model, loaded_clip, loaded_vae = out[:3]
                    else:
                        print(f"[GridTester] Switching Checkpoint to: {target_model_name}")
                        ckpt_path = folder_paths.get_full_path("checkpoints", target_model_name)
                        out = comfy.sd.load_checkpoint_guess_config(ckpt_path, output_vae=True, output_clip=True, embedding_directory=folder_paths.get_folder_paths("embeddings"))
                        loaded_model, loaded_clip, loaded_vae = out[:3]
                    cached_model_key = target_model_name
                    cached_lora_key, patched_model, patched_clip = None, None, None
                    cached_pos_key, cached_neg_key = None, None

                # --- 2. LORA ---
                current_lora_key = (conf["lora"], conf["str_model"], conf["str_clip"])
                if current_lora_key != cached_lora_key or patched_model is None:
                    curr_m, curr_c = loaded_model, loaded_clip
                    active_loras = self.parse_lora_definition(conf["lora"], conf["str_model"], conf["str_clip"])
                    for lora_def in active_loras:
                        lname, lstr_m, lstr_c = lora_def
                        path = folder_paths.get_full_path("loras", lname)
                        if path:
                            lora_data = comfy.utils.load_torch_file(path)
                            curr_m, curr_c = comfy.sd.load_lora_for_models(curr_m, curr_c, lora_data, lstr_m, lstr_c)
                        else:
                             print(f"[GridTester] WARNING: LoRA not found: {lname}")
                    patched_model, patched_clip = curr_m, curr_c
                    cached_lora_key = current_lora_key
                    cached_pos_key, cached_neg_key = None, None

                # --- 3. CONDITIONING ---
                if optional_positive: final_positive = optional_positive
                else:
                    if conf["positive"] == cached_pos_key and final_positive: pass
                    else:
                        tokens = patched_clip.tokenize(conf["positive"])
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        final_positive = [[cond, {"pooled_output": pooled}]]
                        cached_pos_key = conf["positive"]

                if optional_negative: final_negative = optional_negative
                else:
                    if conf["negative"] == cached_neg_key and final_negative: pass
                    else:
                        tokens = patched_clip.tokenize(conf["negative"])
                        cond, pooled = patched_clip.encode_from_tokens(tokens, return_pooled=True)
                        final_negative = [[cond, {"pooled_output": pooled}]]
                        cached_neg_key = conf["negative"]

                # --- 4. GENERATE ---
                if job["latent"] is not None: latent_in = {"samples": job["latent"]["samples"].clone()}
                else: latent_in = {"samples": torch.zeros([1, 4, h // 8, w // 8])}

                try:
                    t0 = time.time()
                    result = nodes.common_ksampler(
                        model=patched_model, seed=current_seed, steps=conf["steps"], cfg=conf["cfg"],
                        sampler_name=conf["sampler"], scheduler=conf["scheduler"],
                        positive=final_positive, negative=final_negative, latent=latent_in, 
                        denoise=conf["denoise"]
                    )
                    duration = round(time.time() - t0, 3)
                    meta = conf.copy()
                    meta.update({"width": w, "height": h, "duration": duration, "seed": current_seed, "batch_idx": batch_idx})
                    pending_batch.append((result[0]["samples"], meta))

                except comfy.model_management.InterruptProcessingException:
                    raise 
                except Exception as e:
                    print(f"[GridTester] Generation Failed (Skipping Config): {e}")
                    continue
                
                # --- 5. FLUSHING ---
                threshold = vae_batch_size if flush_batch_every <= 0 else flush_batch_every
                if len(pending_batch) >= threshold:
                    flush_batch(pending_batch)
                    pending_batch = []

        # --- FINAL SUMMARY ---
        if skipped_count > 0:
            print(f"[GridTester] ✅ Skipped {skipped_count} previously generated items.")
        print(f"[GridTester] ✅ Generated {total_generated} new images.")

        # Flush any remaining items
        flush_batch(pending_batch)
        
        # Save final manifest
        with open(manifest_path, "w") as f: json.dump(existing_data, f, indent=4)
        
        html = get_html_template(session_name, existing_data, unique_id)
        return (html,)