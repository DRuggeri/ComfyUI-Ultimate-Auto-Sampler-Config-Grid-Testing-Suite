import json
import hashlib
from .network_utils import civitai_fetch_by_hash
import folder_paths
import os


class LoRAFileNotFoundError(Exception):
    """
    Critical error raised when a LoRA file cannot be found.
    This should halt all generation jobs to alert the user.
    """
    def __init__(self, lora_name, message=None):
        self.lora_name = lora_name
        if message is None:
            message = f"LoRA file not found: {lora_name}\n\nThis is a critical error. Please check:\n1. The LoRA file exists in your loras folder\n2. The filename is correct (case-sensitive)\n3. The path separators match your system (/ or \\)"
        super().__init__(message)


def save_dict_to_json(data_dict, file_path):
    """Save dictionary to JSON file"""
    try:
        # Ensure parent directory exists (handles first-run on distributed workers
        # where the benchmarks/ folder may not yet exist)
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(file_path, 'w') as json_file:
            json.dump(data_dict, json_file, indent=4)
            print(f"Data saved to {file_path}")
    except Exception as e:
        print(f"Error saving JSON to file: {e}")


def load_json_from_file(file_path):
    """Load JSON data from file"""
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


def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def get_model_version_info(hash_value):
    """Fetch model version info from Civitai API using hash"""
    return civitai_fetch_by_hash(hash_value)


def load_and_save_tags(lora_name, force_fetch, auto_fetch=True):
    """
    Load trigger tags for a LoRA, fetching from Civitai API if necessary.
    Caches results to loras_tags.json.
    
    Args:
        lora_name: Name of the LoRA file (may include path with / or \\)
        force_fetch: Force fetch from API even if cached
        auto_fetch: If False, don't hash uncached LoRAs (just save empty entry)
        
    Returns:
        List of trigger words/tags
    """
    json_tags_path = os.path.join(folder_paths.get_output_directory(), "benchmarks/loras_tags.json")
    # json_tags_path = "./loras_tags.json"
    lora_tags = load_json_from_file(json_tags_path)
    
    # Normalize the lora_name to use forward slashes for cache lookup
    # This handles both "XL/file.safetensors" and "XL\\file.safetensors"
    normalized_name = lora_name.replace("\\", "/")
    
    # Try to find in cache with both the original name and normalized name
    output_tags = None
    found_in_cache = False
    
    if lora_tags is not None:
        # Try original name first
        if lora_name in lora_tags:
            output_tags = lora_tags[lora_name]
            found_in_cache = True
        # If not found, try normalized name
        elif normalized_name != lora_name and normalized_name in lora_tags:
            output_tags = lora_tags[normalized_name]
            found_in_cache = True
        # If still not found, try backslash version
        else:
            backslash_name = normalized_name.replace("/", "\\")
            if backslash_name in lora_tags:
                output_tags = lora_tags[backslash_name]
                found_in_cache = True
    
    # ==== FIX: If found in cache, return immediately without hashing ====
    # This includes empty lists [] - they mean "we already checked and found nothing"
    if found_in_cache:
        # print(f"[Lora-Auto-Trigger] ✅ Found in cache: {lora_name}")
        return output_tags if output_tags is not None else []
    
    # ==== NOT IN CACHE - Need to fetch from API ====
    lora_path = folder_paths.get_full_path("loras", lora_name)
    
    # Check if lora_path is valid before attempting to hash
    if lora_path is None:
        print(f"[Lora-Auto-Trigger] ⚠️ LoRA file not found: {lora_name}")
        print(f"[Lora-Auto-Trigger] 💡 This may be a path issue. The LoRA might exist with a different path separator.")
        return []
    
    # Only hash if force_fetch is True OR (not in cache AND auto_fetch is True)
    if force_fetch or auto_fetch:
        print(f"[Lora-Auto-Trigger] 🔄 {'Force fetch' if force_fetch else 'Auto fetch'} - calculating hash for {lora_name}")
        LORAsha256 = calculate_sha256(lora_path)
        print(f"[Lora-Auto-Trigger] Requesting info from CivitAI...")
        print(LORAsha256)
        model_info = get_model_version_info(LORAsha256)
        if model_info is not None:
            if "trainedWords" in model_info:
                print("[Lora-Auto-Trigger] tags found!")
                if lora_tags is None:
                    lora_tags = {}
                # Save with the normalized name for consistency
                lora_tags[normalized_name] = model_info["trainedWords"]
                save_dict_to_json(lora_tags, json_tags_path)
                return model_info["trainedWords"]
        else:
            print("[Lora-Auto-Trigger] No informations found.")
            if lora_tags is None:
                lora_tags = {}
            lora_tags[normalized_name] = []
            save_dict_to_json(lora_tags, json_tags_path)
            return []
    else:
        # Not in cache and auto_fetch=False - just save empty entry and return
        print(f"[Lora-Auto-Trigger] ⏭️ Not in cache, auto_fetch=False - saving empty entry for {lora_name}")
        if lora_tags is None:
            lora_tags = {}
        lora_tags[normalized_name] = []
        save_dict_to_json(lora_tags, json_tags_path)
        return []



def parse_lora_string(lora_str):
    """
    Parse LoRA string to extract name and strengths.
    
    Format: "name.safetensors:model_strength:clip_strength"
    
    Returns:
        tuple: (name, model_strength, clip_strength)
    """
    parts = lora_str.split(":")
    lora_name = parts[0]
    model_str = float(parts[1]) if len(parts) > 1 else 1.0
    clip_str = float(parts[2]) if len(parts) > 2 else model_str
    return lora_name, model_str, clip_str


def validate_lora_compatibility(model, lora_name, lora_path):
    """
    Validate if a LoRA is compatible with the current model.
    
    Args:
        model: The model to check against
        lora_name: Name of the LoRA
        lora_path: Path to the LoRA file
        
    Returns:
        bool: True if compatible, False otherwise
    """
    try:
        # Try to load the LoRA metadata to check compatibility
        # This is a placeholder - actual implementation would depend on
        # how ComfyUI handles LoRA compatibility checking
        return True
    except Exception as e:
        print(f"[GridTester] ⚠️ LoRA validation failed for {lora_name}: {e}")
        return False


def get_lora_trigger_words(lora_definitions, lookup_triggerwords=False):
    """
    Get trigger words for a list of LoRA definitions.
    
    Args:
        lora_definitions: List of (name, model_str, clip_str) tuples
        lookup_triggerwords: Whether to lookup trigger words from Civitai
        
    Returns:
        str: Comma-separated trigger words
    """
    if not lookup_triggerwords or not lora_definitions:
        return ""
    
    trigger_list = []
    for lora_def in lora_definitions:
        lname, lstr_m, lstr_c = lora_def
        try:
            # ==== FIX: Set auto_fetch=False to skip hashing uncached LoRAs ====
            # This prevents 80+ second delays from SHA256 hashing
            # Only cached LoRAs will get their trigger words
            civitai_tags_list = load_and_save_tags(lname, force_fetch=False, auto_fetch=False)
            if len(civitai_tags_list) > 0:
                for tags in civitai_tags_list:
                    trigger_list.append(tags)
        except Exception as e:
            print(f"[GridTester] Warning: Could not fetch trigger words for {lname}: {e}")
    
    # Join with ", " - only adds separators between items, not at end
    return ", ".join(trigger_list)


def expand_lora_folder(lora_input, seed=None):
    """
    Expand folder paths in LoRA input to individual LoRA files.
    
    Special syntax:
    - "folder/" or "folder" → Expands to separate entries (for iterating over each LoRA)
    - "folder/*" → Returns ALL LoRAs in folder as comma-separated string (for stacking together)
    - "folder/[count,strength]" → Randomly selects 'count' LoRAs from folder at 'strength'
    - "folder/[count,model_str,clip_str]" → Randomly selects with separate model/clip strengths
    
    Args:
        lora_input: String or list of LoRA specifications (can include folders)
        seed: Optional seed for reproducible random selection
        
    Returns:
        list: List of individual LoRA file paths (or comma-separated strings for /* or random syntax)
    """
    import random
    
    if isinstance(lora_input, str):
        lora_input = [lora_input]
    
    expanded = []
    for item in lora_input:
        # Check for random selection syntax FIRST: folder/[count,strength]
        if "[" in item and "]" in item:
            try:
                print(f"[DEBUG] Processing random LoRA syntax: '{item}'")
                # Parse: "XL/Folder/[3,0.35]" or "XL/Folder/[3,1,0.8]"
                base_part = item.split("[")[0]
                print(f"[DEBUG] base_part after split: '{base_part}'")
                random_part = item.split("[")[1].split("]")[0]
                folder_name = base_part.rstrip("/")
                print(f"[DEBUG] folder_name after rstrip: '{folder_name}'")

                print(f"[DEBUG] Looking for LoRAs in folder: '{folder_name}'")

                # Get all LoRAs in folder and subfolders
                lora_files = folder_paths.get_filename_list("loras")
                print(f"[DEBUG] Total LoRAs available: {len(lora_files)}")
                print(f"[DEBUG] Sample LoRA filenames (first 5): {lora_files[:5]}")
                
                # Debug: show files that start with folder name
                xl_files = [f for f in lora_files if f.startswith("XL")]
                print(f"[DEBUG] Files starting with 'XL': {len(xl_files)}")
                if xl_files:
                    print(f"[DEBUG] First 3 XL files: {xl_files[:3]}")
                
                # Handle both forward slash and backslash separators
                # Some systems might use backslashes
                folder_loras = []
                for lora_file in lora_files:
                    # Normalize to forward slashes for comparison
                    normalized_file = lora_file.replace("\\", "/")
                    if normalized_file.startswith(folder_name + "/"):
                        folder_loras.append(lora_file)

                print(f"[DEBUG] LoRAs matching '{folder_name}/': {len(folder_loras)}")
                if len(folder_loras) > 0:
                    print(f"[DEBUG] First 3 matches: {folder_loras[:3]}")
                
                # Parse count and strength
                random_params = random_part.split(",")
                count = int(random_params[0])
                strength = float(random_params[1]) if len(random_params) > 1 else 1.0
                
                # Check for 'random' keyword or dual strength [count,model_str,clip_str]
                use_random_seed = False
                if len(random_params) > 2:
                    third_param = random_params[2].strip().lower()
                    if third_param == "random":
                        # User wants truly random selection (no seed)
                        use_random_seed = False
                        clip_strength = strength
                    else:
                        # It's a clip strength value
                        clip_strength = float(random_params[2])
                        use_random_seed = True  # Still use seed for dual-strength format
                else:
                    clip_strength = strength
                    use_random_seed = True  # Default behavior uses seed
                
                if not folder_loras:
                    print(f"[GridTester] ⚠️ No LoRAs found in folder: {folder_name}")
                    continue
                
                # Randomly select 'count' LoRAs (with seed for reproducibility if requested)
                if use_random_seed and seed is not None:
                    random.seed(seed)
                
                selected_count = min(count, len(folder_loras))
                selected_loras = random.sample(folder_loras, selected_count)
                
                # Format with strength
                if clip_strength != strength:
                    # Dual strength format
                    formatted_loras = [f"{lora}:{strength}:{clip_strength}" for lora in selected_loras]
                else:
                    # Single strength format
                    formatted_loras = [f"{lora}:{strength}" for lora in selected_loras]
                
                # Return as " + " separated string (standard LoRA format)
                stacked_loras = " + ".join(formatted_loras)
                expanded.append(stacked_loras)
                
                print(f"[GridTester] 🎲 Random LoRA selection from: {folder_name}")
                print(f"[GridTester]    Requested: {count} LoRAs at strength {strength}")
                print(f"[GridTester]    Available: {len(folder_loras)} LoRAs")
                print(f"[GridTester]    Selected: {selected_count} LoRAs")
                if use_random_seed and seed is not None:
                    print(f"[GridTester]    Seed: {seed} (reproducible)")
                elif not use_random_seed:
                    print(f"[GridTester]    Mode: Truly random (non-reproducible)")
                
                # Show selected LoRA names
                preview_names = [f.split('/')[-1].replace('.safetensors', '') for f in selected_loras]
                print(f"[GridTester]    LoRAs: {', '.join(preview_names)}")
                
            except Exception as e:
                print(f"[GridTester] ⚠️ Error parsing random LoRA syntax {item}: {e}")
                import traceback
                traceback.print_exc()
                # Don't add to expanded - it's invalid
                continue
        # Check for folder/* syntax - stack all LoRAs in folder together
        elif item.endswith("/*") or (item.endswith("*") and "/" in item):
            try:
                # Remove the /* or * suffix
                folder_name = item.rstrip("/*").rstrip("*")
                
                # Extract strength modifiers if present (e.g., "XL/Folder/*:0.8:0.6")
                strength_suffix = ""
                if ":" in folder_name:
                    parts = folder_name.split(":")
                    folder_name = parts[0]
                    strength_suffix = ":" + ":".join(parts[1:])
                
                lora_files = folder_paths.get_filename_list("loras")
                
                # Collect all files in this folder
                folder_loras = []
                for lora_file in lora_files:
                    if lora_file.startswith(folder_name.rstrip("/") + "/"):
                        folder_loras.append(lora_file + strength_suffix)
                
                # Return as " + " separated string so they're all loaded together
                if folder_loras:
                    stacked_loras = " + ".join(folder_loras)
                    expanded.append(stacked_loras)
                    print(f"[GridTester] 📚 Folder/* syntax detected: Stacking {len(folder_loras)} LoRAs together")
                    print(f"[GridTester]    Folder: {folder_name}")
                    # Show first 5 LoRA names for preview
                    preview_names = [f.split('/')[-1] for f in folder_loras[:5]]
                    preview_text = ', '.join(preview_names)
                    if len(folder_loras) > 5:
                        preview_text += ' ...'
                    print(f"[GridTester]    LoRAs: {preview_text}")
                else:
                    print(f"[GridTester] ⚠️ No LoRAs found in folder: {folder_name}")
                    
            except Exception as e:
                print(f"[GridTester] Warning: Could not expand LoRA folder with /* syntax {item}: {e}")
                expanded.append(item)
        # Check if it's a regular folder reference (without *)
        elif "/" in item and not item.endswith(".safetensors"):
            # This is a folder - expand it to individual entries
            try:
                folder_name = item.split(":")[0] if ":" in item else item
                lora_files = folder_paths.get_filename_list("loras")
                
                # Filter files in this folder
                for lora_file in lora_files:
                    if lora_file.startswith(folder_name + "/"):
                        # Preserve strength modifiers if present
                        if ":" in item:
                            parts = item.split(":")
                            expanded.append(f"{lora_file}:{':'.join(parts[1:])}")
                        else:
                            expanded.append(lora_file)
            except Exception as e:
                print(f"[GridTester] Warning: Could not expand LoRA folder {item}: {e}")
                expanded.append(item)
        else:
            expanded.append(item)
    
    return expanded


def load_loras_to_model(model, clip, lora_definitions):
    """
    Load multiple LoRAs to a model and CLIP.
    
    Args:
        model: Base model to patch
        clip: Base CLIP to patch
        lora_definitions: List of (name, model_str, clip_str) tuples
        
    Returns:
        tuple: (patched_model, patched_clip, incompatible_loras)
        
    Raises:
        LoRAFileNotFoundError: If a LoRA file cannot be found (critical error)
    """
    patched_model = model
    patched_clip = clip
    incompatible_loras = {}
    
    for lora_def in lora_definitions:
        lname, lstr_m, lstr_c = lora_def
        lora_path = folder_paths.get_full_path("loras", lname)
        
        # CRITICAL: Validate that the path exists - if not, STOP EVERYTHING
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
        
        try:
            lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
            patched_model, patched_clip = comfy.sd.load_lora_for_models(
                patched_model, patched_clip, lora, lstr_m, lstr_c
            )
            print(f"[GridTester] ✅ Loaded LoRA: {lname} (model: {lstr_m}, clip: {lstr_c})")
        except Exception as e:
            print(f"[GridTester] ❌ Failed to load LoRA {lname}: {e}")
            incompatible_loras[lname] = (model, lname, str(e))
    
    return patched_model, patched_clip, incompatible_loras


# Import comfy modules for LoRA loading
try:
    import comfy.utils
    import comfy.sd
except ImportError:
    print("[GridTester] Warning: Could not import comfy modules for LoRA loading")