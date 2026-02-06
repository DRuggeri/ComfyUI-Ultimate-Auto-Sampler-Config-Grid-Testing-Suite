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

# Global cache for model hashes
_hash_cache = {}
_hash_cache_dirty = False
_cache_lock = threading.Lock()
_cache_file = None


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
        search_paths = [
            folder_paths.get_folder_paths("checkpoints")[0] if folder_paths.get_folder_paths("checkpoints") else None,
            folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else None,
        ]
        search_paths = [p for p in search_paths if p]
    
    # Normalize path separators
    model_path_normalized = model_path.replace("\\", os.sep).replace("/", os.sep)
    
    for base_path in search_paths:
        if not base_path:
            continue
        full_path = os.path.join(base_path, model_path_normalized)
        if os.path.isfile(full_path):
            return full_path
    
    return None


def pack_metadata_into_image(source_path, dest_path, item_data, meta_data):
    """
    Pack generation metadata into a PNG image for CivitAI compatibility.
    
    Args:
        source_path: Path to source image
        dest_path: Path to save image with metadata
        item_data: Item dictionary from manifest (contains sampler, cfg, etc.)
        meta_data: Meta dictionary from manifest (fallback for missing data)
    """
    # Load hash cache if not already loaded
    if not _hash_cache:
        load_hash_cache()
    
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
    
    # Also add raw workflow data as JSON for full compatibility
    workflow_data = {
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
    
    metadata.add_text("workflow", json.dumps(workflow_data, indent=2))
    
    # Convert to PNG if needed and save with metadata
    # Force PNG extension for metadata compatibility
    if not dest_path.lower().endswith('.png'):
        dest_path = dest_path.rsplit('.', 1)[0] + '.png'
    
    # Convert to RGB if necessary (WebP might be RGBA)
    if img.mode in ('RGBA', 'LA', 'P'):
        # Keep RGBA for transparency
        pass
    elif img.mode != 'RGB':
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