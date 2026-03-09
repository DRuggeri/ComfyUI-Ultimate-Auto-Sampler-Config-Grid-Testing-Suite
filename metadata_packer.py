"""
Metadata Packer for PNG Images
Packs ComfyUI generation parameters into PNG metadata for CivitAI compatibility
"""

from PIL import Image
from PIL.PngImagePlugin import PngInfo
import json
import hashlib
import os
import threading
import piexif
import piexif.helper

# Global cache for model hashes
_hash_cache = {}
_hash_cache_dirty = False
_cache_lock = threading.Lock()
_cache_file = None

workflow_raw_string = r'''{"id":"45fadf35-ff07-4f8a-944d-040bb9aa66d4","revision":0,"last_node_id":4,"last_link_id":4,"nodes":[{"id":4,"type":"UltimateGridDashboard","pos":[10738.192160985536,4835.035782643685],"size":[1700,1060],"flags":{"collapsed":false},"order":3,"mode":0,"inputs":[{"localized_name":"dashboard_html","name":"dashboard_html","shape":7,"type":"STRING","link":3},{"localized_name":"session_name","name":"session_name","type":"STRING","widget":{"name":"session_name"},"link":null}],"outputs":[],"properties":{"cnr_id":"ultimate-auto-sampler-config-grid-testing-suite","ver":"926798a412df24e753c3bfd1009c6d61b4567f0a","Node name for S&R":"UltimateGridDashboard","ue_properties":{"widget_ue_connectable":{},"input_ue_unconnectable":{},"version":"7.5.2"},"aux_id":"JasonHoku/ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite"},"widgets_values":["SmexyTrendy12",null,"",""]},{"id":1,"type":"UltimateSamplerGrid","pos":[10260,4870],"size":[420,1182.6153846153848],"flags":{},"order":2,"mode":0,"inputs":[{"localized_name":"optional_model","name":"optional_model","shape":7,"type":"MODEL","link":null},{"localized_name":"optional_clip","name":"optional_clip","shape":7,"type":"CLIP","link":null},{"localized_name":"optional_vae","name":"optional_vae","shape":7,"type":"VAE","link":null},{"localized_name":"optional_positive","name":"optional_positive","shape":7,"type":"CONDITIONING","link":null},{"localized_name":"optional_negative","name":"optional_negative","shape":7,"type":"CONDITIONING","link":null},{"localized_name":"optional_latent","name":"optional_latent","shape":7,"type":"LATENT","link":null},{"localized_name":"ckpt_name","name":"ckpt_name","type":"COMBO","widget":{"name":"ckpt_name"},"link":null},{"localized_name":"positive_text","name":"positive_text","type":"STRING","widget":{"name":"positive_text"},"link":null},{"localized_name":"negative_text","name":"negative_text","type":"STRING","widget":{"name":"negative_text"},"link":null},{"localized_name":"seed","name":"seed","type":"INT","widget":{"name":"seed"},"link":null},{"localized_name":"denoise","name":"denoise","type":"STRING","widget":{"name":"denoise"},"link":null},{"localized_name":"vae_batch_size","name":"vae_batch_size","type":"INT","widget":{"name":"vae_batch_size"},"link":null},{"localized_name":"configs_json","name":"configs_json","type":"STRING","widget":{"name":"configs_json"},"link":4},{"localized_name":"resolutions_json","name":"resolutions_json","type":"STRING","widget":{"name":"resolutions_json"},"link":null},{"localized_name":"session_name","name":"session_name","type":"STRING","widget":{"name":"session_name"},"link":null},{"localized_name":"overwrite_existing","name":"overwrite_existing","type":"BOOLEAN","widget":{"name":"overwrite_existing"},"link":null},{"localized_name":"flush_batch_every","name":"flush_batch_every","type":"INT","widget":{"name":"flush_batch_every"},"link":null},{"localized_name":"add_random_seeds_to_gens","name":"add_random_seeds_to_gens","type":"INT","widget":{"name":"add_random_seeds_to_gens"},"link":null},{"localized_name":"lora_triggerwords_mode","name":"lora_triggerwords_mode","type":"COMBO","widget":{"name":"lora_triggerwords_mode"},"link":null},{"localized_name":"remote_vae_endpoint","name":"remote_vae_endpoint","type":"COMBO","widget":{"name":"remote_vae_endpoint"},"link":null},{"localized_name":"save_conditioning_cache_to_file","name":"save_conditioning_cache_to_file","type":"BOOLEAN","widget":{"name":"save_conditioning_cache_to_file"},"link":null}],"outputs":[{"localized_name":"dashboard_html","name":"dashboard_html","type":"STRING","links":[3]}],"properties":{"cnr_id":"ultimate-auto-sampler-config-grid-testing-suite","ver":"926798a412df24e753c3bfd1009c6d61b4567f0a","Node name for S&R":"UltimateSamplerGrid","ue_properties":{"widget_ue_connectable":{},"input_ue_unconnectable":{},"version":"7.5.2"},"aux_id":"JasonHoku/ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite"},"widgets_values":["XL\\IL\\New\\waiIllustriousSDXL_v160.safetensors","","worst quality, bad quality, text, words, font, blurry, blur",43,"fixed","1",-1,"","[[832, 1216]]","SmexyTrendy12",false,1,0,"Append To End","SDXL",false]},{"id":2,"type":"SmartJSONText","pos":[9587.203247321488,4587.304138002992],"size":[520,560],"flags":{},"order":0,"mode":0,"inputs":[{"localized_name":"json_text","name":"json_text","type":"STRING","widget":{"name":"json_text"},"link":null},{"localized_name":"validate_on_input","name":"validate_on_input","shape":7,"type":"BOOLEAN","widget":{"name":"validate_on_input"},"link":null}],"outputs":[{"localized_name":"json_text","name":"json_text","type":"STRING","links":[]},{"localized_name":"parsed_json","name":"parsed_json","type":"STRING","links":null}],"properties":{"cnr_id":"ultimate-auto-sampler-config-grid-testing-suite","ver":"4c2ce478f49c05206d374f0a97cabd4681c83fb7","Node name for S&R":"SmartJSONText","ue_properties":{"widget_ue_connectable":{},"input_ue_unconnectable":{},"version":"7.5.2"}},"widgets_values":["[\n    [\n        \"semirealistic, modern anime, 8k, smooth, \",\n        \"Test pre-append prompts here, or use this to pre-append a prompt to all, \"\n    ],\n    [\n        \"Nested JSON Prompt Array Example\",\n        \"This example would create 4 prompts total through nested JSON iteration\"\n    ],\n    [\n        \"This will be apppended to the end of all prompts \"\n    ]\n]",true]},{"id":3,"type":"UltimateConfigBuilder","pos":[8870.136925369541,5300.75413741907],"size":[1250,1680],"flags":{},"order":1,"mode":0,"inputs":[{"localized_name":"session_name","name":"session_name","type":"STRING","widget":{"name":"session_name"},"link":null},{"localized_name":"load_session","name":"load_session","type":"COMBO","widget":{"name":"load_session"},"link":null},{"localized_name":"samplers","name":"samplers","type":"STRING","widget":{"name":"samplers"},"link":null},{"localized_name":"schedulers","name":"schedulers","type":"STRING","widget":{"name":"schedulers"},"link":null},{"localized_name":"steps","name":"steps","type":"STRING","widget":{"name":"steps"},"link":null},{"localized_name":"cfg","name":"cfg","type":"STRING","widget":{"name":"cfg"},"link":null},{"localized_name":"lora_config","name":"lora_config","type":"STRING","widget":{"name":"lora_config"},"link":null},{"localized_name":"include_none","name":"include_none","type":"BOOLEAN","widget":{"name":"include_none"},"link":null},{"localized_name":"model","name":"model","shape":7,"type":"STRING","widget":{"name":"model"},"link":null}],"outputs":[{"localized_name":"configs_json","name":"configs_json","type":"STRING","links":[4]},{"localized_name":"session_name","name":"session_name","type":"STRING","links":null}],"properties":{"cnr_id":"ultimate-auto-sampler-config-grid-testing-suite","ver":"b23e4c8db69e7086945c444d3a0cd1ec5775dff1","Node name for S&R":"UltimateConfigBuilder","ue_properties":{"widget_ue_connectable":{},"input_ue_unconnectable":{},"version":"7.5.2"}},"widgets_values":["my_test_session","None","euler, dpmpp_2m","normal, karras","20, 30","7.0","{\n  \"session_name\": \"\",\n  \"include_none\": true,\n  \"config_arrays\": [],\n \n  \"config_name\": \"\",\n  \"auto_save\": false\n}",true,"",""]}],"links":[[3,1,0,4,0,"STRING"],[4,3,0,1,12,"STRING"]],"groups":[],"config":{},"extra":{"workflowRendererVersion":"LG","ds":{"scale":0.779645346653729,"offset":[-8597.11226526943,-5252.748644871856]}},"version":0.4}'''

try:
    workflowExample = json.loads(workflow_raw_string)
except json.JSONDecodeError as e:
    print(f"Error parsing JSON: {e}")
    workflowExample = None
    
def get_cache_file_path():
    """Get the path to the hash cache file."""
    global _cache_file
    if _cache_file is None:
        try:
            import folder_paths
            output_dir = folder_paths.get_output_directory()
            benchmarks_dir = os.path.join(output_dir, "benchmarks")
            os.makedirs(benchmarks_dir, exist_ok=True)
            _cache_file = os.path.join(benchmarks_dir, "model_hashes.json")
        except:
            # Fallback if folder_paths not available
            _cache_file = "model_hashes.json"
    return _cache_file


def load_hash_cache():
    """Load hash cache from disk."""
    global _hash_cache
    cache_path = get_cache_file_path()
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                _hash_cache = json.load(f)
            print(f"[MetadataPacker] Loaded {len(_hash_cache)} cached hashes from {cache_path}")
        except Exception as e:
            print(f"[MetadataPacker] Warning: Could not load hash cache: {e}")
            _hash_cache = {}
    else:
        _hash_cache = {}


def save_hash_cache():
    """Save hash cache to disk."""
    global _hash_cache_dirty
    
    if not _hash_cache_dirty:
        return
    
    cache_path = get_cache_file_path()
    
    try:
        # Atomic write using temp file
        temp_path = cache_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(_hash_cache, f, indent=2)
        os.replace(temp_path, cache_path)
        _hash_cache_dirty = False
        print(f"[MetadataPacker] Saved hash cache with {len(_hash_cache)} entries")
    except Exception as e:
        print(f"[MetadataPacker] Warning: Could not save hash cache: {e}")


def calculate_file_hash(filepath, defer_save=False):
    """
    Calculate SHA256 hash of a file (first 10 chars).
    Uses cache to avoid recalculating for unchanged files.
    Returns empty string if file not found.
    
    Args:
        filepath: Path to file to hash
        defer_save: If True, don't save cache to disk immediately (batch optimization)
    """
    global _hash_cache_dirty
    
    if not filepath or not os.path.isfile(filepath):
        return ""
    
    # Get file modification time
    try:
        mod_time = os.path.getmtime(filepath)
    except:
        return ""
    
    # Use filename as cache key
    cache_key = os.path.basename(filepath)
    
    with _cache_lock:
        # Check if we have a valid cached hash
        if cache_key in _hash_cache:
            cached_entry = _hash_cache[cache_key]
            if cached_entry.get("mod_time") == mod_time:
                # print(f"[MetadataPacker] Using cached hash for {cache_key}")
                return cached_entry["hash"]
    
    # Calculate hash if not cached or file changed
    try:
        print(f"[MetadataPacker] Calculating hash for {cache_key}...")
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        file_hash = sha256_hash.hexdigest()[:10]
        
        # Update cache
        with _cache_lock:
            _hash_cache[cache_key] = {
                "hash": file_hash,
                "mod_time": mod_time,
                "filepath": filepath
            }
            _hash_cache_dirty = True
        
        # Save cache after calculating new hash (unless deferred)
        if not defer_save:
            save_hash_cache()
        
        return file_hash
    except Exception as e:
        print(f"[MetadataPacker] Warning: Could not hash {filepath}: {e}")
        return ""


def find_model_file(model_path, search_paths=None):
    """
    Try to find the actual model file on disk.
    
    Args:
        model_path: Path from manifest (e.g. "XL\\model.safetensors")
        search_paths: List of base directories to search in
        
    Returns:
        Full path to file if found, None otherwise
    """
    if search_paths is None:
        # Try common ComfyUI model directories
        import folder_paths
        search_paths = []
        for folder_type in ["checkpoints", "loras", "diffusion_models", "unet"]:
            try:
                paths = folder_paths.get_folder_paths(folder_type)
                if paths:
                    search_paths.extend(paths)
            except Exception:
                pass
    
    # Normalize path separators
    model_path_normalized = model_path.replace("\\", os.sep).replace("/", os.sep)
    
    for base_path in search_paths:
        if not base_path:
            continue
        full_path = os.path.join(base_path, model_path_normalized)
        if os.path.isfile(full_path):
            return full_path
    
    return None


def pack_metadata_into_image(source_path, dest_path, item_data, meta_data, workflow_json_path=None, workflow_data=None):
    """
    Pack generation metadata into a PNG image for CivitAI compatibility.
    
    Args:
        source_path: Path to source image
        dest_path: Path to save image with metadata
        item_data: Item dictionary from manifest (contains sampler, cfg, etc.)
        meta_data: Meta dictionary from manifest (fallback for missing data)
        workflow_json_path: Optional path to workflow JSON file to embed in metadata.
                           If None and workflow_data is None, will automatically search for:
                           1. <source_name>.json (e.g., image_00001.png -> image_00001.json)
                           2. <source_base>.json (e.g., image_00001.png -> image.json)
        workflow_data: Optional workflow dict to embed directly (takes precedence over workflow_json_path).
                      Can be the workflow dict, prompt dict, or extra_pnginfo dict from ComfyUI.
    """
    # Load hash cache if not already loaded
    if not _hash_cache:
        load_hash_cache()
    
    # Auto-detect workflow JSON path if workflow_data not provided
    if workflow_data is None and workflow_json_path is None:
        # Try to find JSON file with same name as source image
        # e.g., image_00001.png -> image_00001.json
        base_path = os.path.splitext(source_path)[0]
        potential_json = base_path + ".json"
        
        if os.path.exists(potential_json):
            workflow_json_path = potential_json
            print(f"[MetadataPacker] Auto-detected workflow JSON: {potential_json}")
        else:
            # Also try without the batch number suffix
            # e.g., image_00001.png -> image.json
            import re
            source_dir = os.path.dirname(source_path)
            source_filename = os.path.basename(source_path)
            
            # Remove _00001 pattern from filename
            base_name = re.sub(r'_\d{5}$', '', os.path.splitext(source_filename)[0])
            potential_json_alt = os.path.join(source_dir, base_name + ".json")
            
            if os.path.exists("./TestWorkflow.json"):
                workflow_json_path = potential_json_alt
                print(f"[MetadataPacker] Auto-detected workflow JSON: {potential_json_alt}")
            else:
                print("Path Doesn't Exist")
    try:
        print(f"[MetadataPacker] Starting to pack metadata for {source_path}")
        
        # Open the source image
        img = Image.open(source_path)
        print(f"[MetadataPacker] Opened image: {img.format} {img.size} {img.mode}")
        
        # Create PNG metadata object
        metadata = PngInfo()
        
        # Extract data from item (use meta only as fallback)
        model = item_data.get("model", meta_data.get("model", "Unknown"))
        positive = item_data.get("positive", meta_data.get("positive", ""))
        negative = item_data.get("negative", meta_data.get("negative", ""))
        sampler = item_data.get("sampler", "euler")
        scheduler = item_data.get("scheduler", "normal")
        steps = item_data.get("steps", 20)
        cfg = item_data.get("cfg", 7.0)
        seed = item_data.get("seed", 0)
        denoise = item_data.get("denoise", 1.0)
        width = item_data.get("width", img.width)
        height = item_data.get("height", img.height)
        lora = item_data.get("lora", "None")
        clip_skip = item_data.get("clip_skip", -1)
        
        print(f"[MetadataPacker] Extracted metadata - Model: {model}, Sampler: {sampler}, Steps: {steps}")
        
        # Try to import folder_paths for finding model files
        try:
            import folder_paths
            checkpoint_paths = folder_paths.get_folder_paths("checkpoints")
            lora_paths = folder_paths.get_folder_paths("loras")
        except:
            checkpoint_paths = []
            lora_paths = []
        
        # Calculate model hash
        model_hash = ""
        if model:
            model_file = find_model_file(model, checkpoint_paths)
            if not model_file:
                # Try folder_paths.get_full_path for various model types
                import folder_paths as fp
                for model_type in ["checkpoints", "diffusion_models", "unet"]:
                    try:
                        resolved = fp.get_full_path(model_type, model)
                        if resolved and os.path.isfile(resolved):
                            model_file = resolved
                            break
                    except Exception:
                        pass
            if model_file:
                print(f"[MetadataPacker] Found model file: {model_file}")
                model_hash = calculate_file_hash(model_file, defer_save=True)

            # Fallback: use filename-based hash if file not found
            if not model_hash:
                model_filename = model.replace("\\", "/").split("/")[-1].replace(".safetensors", "")
                model_hash = hashlib.sha256(model_filename.encode()).hexdigest()[:10]
                print(f"[MetadataPacker] Using fallback hash for model: {model_hash}")
        
    except Exception as e:
        print(f"[MetadataPacker] ERROR during initial processing: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    # Format sampler name for A1111 style
    sampler_formatted = sampler.replace("_", " ").title()
    if scheduler and scheduler != "normal":
        sampler_formatted += f" {scheduler.capitalize()}"
    
    # Parse and format LoRA information - ADD TO PROMPT
    lora_tags = []
    lora_hashes_display = []  # For "Lora hashes: " line
    lora_hashes_dict = {}     # For "Hashes: " JSON section
    
    if lora and lora != "None":
        # Split by " + " to get individual LoRAs
        loras = [l.strip() for l in lora.split(" + ")]
        
        for lora_entry in loras:
            if not lora_entry:
                continue
                
            # Parse format: "path/to/lora.safetensors:strength" or "path:strength1:strength2"
            parts = lora_entry.rsplit(":", 1)
            if len(parts) == 2:
                lora_path = parts[0]
                strength = parts[1]
                
                # Handle double strength format (model_strength:clip_strength)
                if ":" in lora_path:
                    # This might be path:model_strength, and current is clip_strength
                    # Reconstruct: take everything before last : as path
                    path_parts = lora_entry.rsplit(":", 2)
                    if len(path_parts) == 3:
                        lora_path = path_parts[0]
                        strength = path_parts[1]  # Use model strength
            else:
                lora_path = lora_entry
                strength = "1.0"
            
            # Clean up path and get name
            lora_name = lora_path.replace("\\", "/").split("/")[-1].replace(".safetensors", "")
            
            # Calculate real hash from LoRA file
            lora_hash = ""
            lora_file = find_model_file(lora_path, lora_paths)
            if lora_file:
                lora_hash = calculate_file_hash(lora_file, defer_save=True)
                # print(f"[MetadataPacker] Calculated hash for LoRA {lora_name}: {lora_hash}")
            
            # Fallback: use filename-based hash if file not found
            if not lora_hash:
                lora_hash = hashlib.sha256(lora_name.encode()).hexdigest()[:8]
                print(f"[MetadataPacker] Using fallback hash for LoRA {lora_name}: {lora_hash}")
            
            # For Lora hashes display (format: "Name: hash")
            lora_hashes_display.append(f"{lora_name}: {lora_hash}")
            
            # For Hashes JSON dict (format: "lora:Name": "hash")
            lora_hashes_dict[f"lora:{lora_name}"] = lora_hash
            
            # Add to prompt
            lora_tags.append(f"<lora:{lora_name}:{strength}>")
    
    # Build positive prompt with LoRA tags appended
    full_positive = positive
    if lora_tags:
        full_positive = positive + " " + " ".join(lora_tags)
    
    # Build parameters string (A1111/CivitAI compatible format)
    # Line 1: Positive prompt with LoRA tags
    params_lines = [full_positive]
    
    # Line 2: Negative prompt (on separate line)
    if negative:
        params_lines.append(f"Negative prompt: {negative}")
    
    # Line 3: Generation parameters (all on one line, comma-separated)
    param_parts = [
        f"Steps: {steps}",
        f"Sampler: {sampler_formatted}",
        f"CFG scale: {cfg}",
        f"Seed: {seed}"
    ]
    
    # Add clip skip if present and not -1
    if clip_skip != -1:
        param_parts.append(f"Clip skip: {abs(clip_skip)}")
    
    # Add size
    param_parts.append(f"Size: {width}x{height}")
    
    # Add model name (with path but without .safetensors)
    model_display = model.replace(".safetensors", "")
    param_parts.append(f"Model: {model_display}")
    
    # Use the model_hash we calculated earlier
    param_parts.append(f"Model hash: {model_hash}")
    
    # Add LoRA hashes (format: "Name: hash, Name2: hash2")
    if lora_hashes_display:
        lora_hashes_str = ", ".join(lora_hashes_display)
        param_parts.append(f'Lora hashes: "{lora_hashes_str}"')
    
    # Add Hashes dict (format: {"model": "hash", "lora:Name": "hash"})
    hashes_dict = {"model": model_hash}
    hashes_dict.update(lora_hashes_dict)
    hashes_json = json.dumps(hashes_dict)
    param_parts.append(f"Hashes: {hashes_json}")
    
    # Add denoising if not 1.0
    if denoise < 1.0:
        param_parts.append(f"Denoising strength: {denoise}")
    
    # Join param parts with ", " for line 3
    params_lines.append(", ".join(param_parts))
    
    # Final format: Join lines with newline
    parameters_text = "\n".join(params_lines)
    
    # Add to PNG metadata
    metadata.add_text("parameters", parameters_text)
    
    # Handle workflow data (either from dict or file)
    workflow_data_full = None
    
    # Priority 1: Use workflow_data if provided directly
    if workflow_data is not None:
        workflow_data_full = workflow_data
        print(f"[MetadataPacker] Using provided workflow data dict")
    # Priority 2: Load from workflow_json_path if provided
    elif workflow_json_path and os.path.exists(workflow_json_path):
        try:
            with open(workflow_json_path, "r", encoding="utf-8") as f:
                workflow_data_full = json.load(f)
            print(f"[MetadataPacker] Loaded workflow from {workflow_json_path}")
        except Exception as e:
            print(f"[MetadataPacker] Warning: Could not load workflow JSON: {e}")
    
    if not workflow_data_full:
        workflow_data_full = workflowExample
    # Add workflow to metadata if we have it
    if workflow_data_full:
        # Add workflow to metadata
        metadata.add_text("workflow", json.dumps(workflow_data_full))
        
        # If there's a prompt structure in the workflow, add it too
        # (ComfyUI format compatibility)
        if isinstance(workflow_data_full, dict) and "prompt" in workflow_data_full:
            metadata.add_text("prompt", json.dumps(workflow_data_full["prompt"]))
    
        print("Workflow added!")
    # Also add raw workflow data as JSON for basic compatibility
    workflow_data_basic = {
        "model": model,
        "positive": positive,
        "negative": negative,
        "sampler": sampler,
        "scheduler": scheduler,
        "steps": steps,
        "cfg": cfg,
        "seed": seed,
        "denoise": denoise,
        "width": width,
        "height": height,
        "lora": lora,
        "clip_skip": clip_skip
    }
    
    # Only add basic workflow if we didn't load a full one
    if not workflow_data_full:
        metadata.add_text("workflow", json.dumps(workflow_data_basic, indent=2))
    
    # Determine output format from dest_path extension
    dest_ext = dest_path.lower().split('.')[-1]
    
    # Convert to RGB if necessary for JPG (JPG doesn't support transparency)
    if dest_ext in ['jpg', 'jpeg']:
        if img.mode in ('RGBA', 'LA', 'P'):
            # Convert RGBA to RGB with white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
    elif dest_ext == 'webp':
        # WebP supports both RGB and RGBA
        if img.mode == 'P':
            img = img.convert('RGBA')
        elif img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
    elif dest_ext == 'png':
        # PNG - keep mode as is, but convert palette if needed
        if img.mode == 'P':
            img = img.convert('RGBA')
    
    # Save based on format
    if dest_ext == 'png':
        # Save as PNG with metadata
        img.save(dest_path, format='PNG', pnginfo=metadata, optimize=False)
    elif dest_ext in ['jpg', 'jpeg']:
        # Save as JPG first without metadata
        img.save(dest_path, format='JPEG', quality=95, optimize=True)
        
        # Insert EXIF metadata for JPG
        exif_bytes = piexif.dump({
            "Exif": {
                piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(
                    parameters_text, encoding="unicode"
                )
            }
        })
        piexif.insert(exif_bytes, dest_path)
    elif dest_ext == 'webp':
        # Save as WebP first
        img.save(dest_path, format='WEBP', quality=95, method=6)
        
        # Insert EXIF metadata for WebP
        exif_bytes = piexif.dump({
            "Exif": {
                piexif.ExifIFD.UserComment: piexif.helper.UserComment.dump(
                    parameters_text, encoding="unicode"
                )
            }
        })
        piexif.insert(exif_bytes, dest_path)
    else:
        # Fallback - force PNG extension for metadata compatibility
        if not dest_path.lower().endswith('.png'):
            dest_path = dest_path.rsplit('.', 1)[0] + '.png'
        
        # Convert to RGBA for PNG if necessary
        if img.mode in ('LA', 'P'):
            img = img.convert('RGBA')
        elif img.mode != 'RGB' and img.mode != 'RGBA':
            img = img.convert('RGB')
        
        # Save as PNG with metadata
        img.save(dest_path, format='PNG', pnginfo=metadata, optimize=False)
    
    # Save hash cache if there were any new hashes calculated
    save_hash_cache()
    
    print(f"[MetadataPacker] ✅ Packed metadata into {dest_path}")


def extract_metadata_from_image(image_path):
    """
    Extract metadata from a PNG image.
    
    Args:
        image_path: Path to image file
        
    Returns:
        dict: Dictionary with 'parameters' and 'workflow' keys if found
    """
    img = Image.open(image_path)
    
    result = {}
    
    # Get PNG text chunks
    if hasattr(img, 'text'):
        if 'parameters' in img.text:
            result['parameters'] = img.text['parameters']
        if 'workflow' in img.text:
            try:
                result['workflow'] = json.loads(img.text['workflow'])
            except:
                result['workflow'] = img.text['workflow']
    
    return result