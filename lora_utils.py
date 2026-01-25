import json
import hashlib
import requests
import folder_paths


def save_dict_to_json(data_dict, file_path):
    """Save dictionary to JSON file"""
    try:
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


def load_and_save_tags(lora_name, force_fetch):
    """
    Load trigger tags for a LoRA, fetching from Civitai API if necessary.
    Caches results to loras_tags.json.
    
    Args:
        lora_name: Name of the LoRA file
        force_fetch: Force fetch from API even if cached
        
    Returns:
        List of trigger words/tags
    """
    json_tags_path = "./loras_tags.json"
    lora_tags = load_json_from_file(json_tags_path)
    output_tags = lora_tags.get(lora_name, None) if lora_tags is not None else None
    if output_tags is not None:
        output_tags_list = output_tags
    else:
        output_tags_list = []

    lora_path = folder_paths.get_full_path("loras", lora_name)
    if lora_tags is None or force_fetch or output_tags is None:  # search on civitai only if no local cache or forced
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
            save_dict_to_json(lora_tags, json_tags_path)

    return output_tags_list


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
    clip_str = float(parts[2]) if len(parts) > 2 else 1.0
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
            civitai_tags_list = load_and_save_tags(lname, force_fetch=False)
            if len(civitai_tags_list) > 0:
                for tags in civitai_tags_list:
                    trigger_list.append(tags)
        except Exception as e:
            print(f"[GridTester] Warning: Could not fetch trigger words for {lname}: {e}")
    
    # Join with ", " - only adds separators between items, not at end
    return ", ".join(trigger_list)


def expand_lora_folder(lora_input):
    """
    Expand folder paths in LoRA input to individual LoRA files.
    
    Args:
        lora_input: String or list of LoRA specifications (can include folders)
        
    Returns:
        list: List of individual LoRA file paths
    """
    if isinstance(lora_input, str):
        lora_input = [lora_input]
    
    expanded = []
    for item in lora_input:
        # Check if it's a folder reference
        if "/" in item and not item.endswith(".safetensors"):
            # This is a folder - expand it
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
    """
    patched_model = model
    patched_clip = clip
    incompatible_loras = {}
    
    for lora_def in lora_definitions:
        lname, lstr_m, lstr_c = lora_def
        lora_path = folder_paths.get_full_path("loras", lname)
        
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
