import json
import re
import itertools
import folder_paths
import comfy.samplers
import itertools

 

def parse_prompt_input_nested(prompt_input: str):
    """
    Parse prompt input that supports plain text, single-level, and nested arrays.
    Creates Cartesian products from nested arrays.
    
    Args:
        prompt_input: Plain text string OR JSON string containing prompts
        
    Returns:
        List of final prompt strings
        
    Examples:
        Plain text: "my prompt" -> ["my prompt"]
        Plain text with quotes: '"my prompt"' -> ["my prompt"]
        Simple: '["a", "b", "c"]' -> ["a", "b", "c"]
        Nested: '[["a", "b"], ["1", "2"]]' -> ["a, 1", "a, 2", "b, 1", "b, 2"]
    """
    import json
    import itertools
    
    # Handle None or empty string input
    if not prompt_input or prompt_input.strip() == "":
        return [""]
    
    # Strip whitespace
    prompt_input = prompt_input.strip()
    
    # Try to parse as JSON first
    try:
        parsed = json.loads(prompt_input)
    except (json.JSONDecodeError, ValueError):
        # Not valid JSON - treat as plain text
        # Remove quotes if they exist (user might have typed "my prompt")
        if (prompt_input.startswith('"') and prompt_input.endswith('"')) or \
           (prompt_input.startswith("'") and prompt_input.endswith("'")):
            prompt_input = prompt_input[1:-1]
        return [prompt_input]
    
    # Handle empty parsed result
    if not parsed:
        return [""]
    
    # If it's a single string from JSON
    if isinstance(parsed, str):
        return [parsed]
    
    # Check if this is a nested structure (has any lists inside)
    has_nested = any(isinstance(item, list) for item in parsed)
    
    if not has_nested:
        # Simple list of strings: ["a", "b", "c"]
        return [str(item) for item in parsed]
    
    # Nested structure - expand to Cartesian product
    normalized = []
    for item in parsed:
        if isinstance(item, list):
            normalized.append([str(x) for x in item])
        else:
            normalized.append([str(item)])
    
    # Generate Cartesian product
    combinations = list(itertools.product(*normalized))
    
    # Join each combination with ", "
    result = [", ".join(combo) for combo in combinations]
    
    return result


def normalize_str(s):
    """Normalize string paths by replacing backslashes with forward slashes"""
    if isinstance(s, str):
        return s.replace("\\", "/").strip()
    return s


def parse_json_with_error(json_str, name):
    """Parse JSON string with helpful error messages"""
    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON Error in {name}: {e}")


def parse_float_input(input_str):
    """Parse float input that could be JSON array, comma-separated, or single value"""
    try:
        val = json.loads(input_str)
        if isinstance(val, list):
            return [float(x) for x in val]
        return [float(val)]
    except:
        try:
            if "," in input_str:
                return [float(x.strip()) for x in input_str.split(",")]
            return [float(input_str)]
        except:
            return [1.0]


def parse_string_input(input_str):
    """Parse string input that could be JSON array or single value"""
    try:
        val = json.loads(input_str.strip())
        if isinstance(val, list):
            return [str(x) for x in val]
        return [str(val)]
    except:
        return [input_str]


def get_files_from_folder(input_string, type_key):
    """
    Get files from a folder path, or return the input if it's a single file.
    
    Args:
        input_string: Path to file or folder (folder ends with /)
        type_key: Type of files to search for (e.g., "checkpoints", "loras")
        
    Returns:
        List of file paths
    """
    input_norm = input_string.replace("\\", "/")
    if ":" in input_norm:
        input_norm = input_norm.split(":")[0]
    if not input_norm.endswith("/"):
        return [input_string]
    
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


def parse_lora_definition(lora_string, global_model_strength, global_clip_strength):
    """
    Parse LoRA definition string into list of (name, model_str, clip_str) tuples.
    
    Format: "lora1.safetensors:1.0:0.8 + lora2.safetensors"
    
    Args:
        lora_string: String defining LoRAs
        global_model_strength: Default model strength if not specified
        global_clip_strength: Default CLIP strength if not specified
        
    Returns:
        List of (name, model_strength, clip_strength) tuples
    """
    if lora_string == "None":
        return []
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


def expand_lora_stack(lora_input, str_model, str_clip):
    """
    Expand LoRA stacks with folder support.
    
    Handles formats like:
    - "lora.safetensors"
    - "lora1 + lora2"
    - "folder/ + lora.safetensors"
    - "folder/:1.0:0.8 + lora.safetensors"
    
    Args:
        lora_input: LoRA specification string or list
        str_model: Default model strength
        str_clip: Default CLIP strength
        
    Returns:
        List of expanded LoRA stack strings
    """
    def to_list(x):
        return x if isinstance(x, list) else [x]
    
    raw_loras = to_list(lora_input)
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
                found_files = get_files_from_folder(base_path, "loras")
                expanded_parts.append([f"{f}{args}" for f in found_files])
            else:
                expanded_parts.append([part])
        
        for combo in itertools.product(*expanded_parts):
            expanded_loras.append(" + ".join(combo))
    
    return expanded_loras


def expand_configs(raw_configs, pos_prompts, neg_prompts, denoise_values, seed, extra_seeds, ckpt_name=None):
    """
    Expand raw config entries into full configuration combinations.
    
    Args:
        raw_configs: List of config dictionaries with potentially wildcarded values
        pos_prompts: List of positive prompts
        neg_prompts: List of negative prompts
        denoise_values: List of denoise values
        seed: Base seed value
        extra_seeds: List of additional random seeds
        ckpt_name: Checkpoint name from node input (used as default when model is "Default")
        
    Returns:
        List of fully expanded config dictionaries
    """
    ALL_SCHEDULERS = comfy.samplers.KSampler.SCHEDULERS
    ALL_SAMPLERS = comfy.samplers.KSampler.SAMPLERS
    expanded = []
    
    # Determine prompt pairing strategy
    if len(pos_prompts) > 1 and len(neg_prompts) > 1 and len(pos_prompts) == len(neg_prompts):
        print("[GridTester] Detected matching prompt lists. Using 1-to-1 Pairing.")
        prompt_pairs = list(zip(pos_prompts, neg_prompts))
    else:
        prompt_pairs = list(itertools.product(pos_prompts, neg_prompts))
    
    def to_list(x):
        return x if isinstance(x, list) else [x]
    
    for entry in raw_configs:
        # Expand wildcards
        samplers = ALL_SAMPLERS if entry.get("sampler") == "*" else to_list(entry.get("sampler", "euler"))
        schedulers = ALL_SCHEDULERS if entry.get("scheduler") == "*" else to_list(entry.get("scheduler", "normal"))
        steps_l = to_list(entry.get("steps", 20))
        cfgs = to_list(entry.get("cfg", 7.0))
        str_m = to_list(entry.get("str_model", 1.0))
        str_c = to_list(entry.get("str_clip", 1.0))
        
        # Expand model folders
        raw_models = to_list(entry.get("model", "Default"))
        expanded_models = []
        for m in raw_models:
            if m == "Default":
                # Use the checkpoint name from node input instead of "Default"
                if ckpt_name:
                    expanded_models.append(ckpt_name)
                else:
                    expanded_models.append("Default")
            else:
                expanded_models.extend(get_files_from_folder(m, "checkpoints"))
        
        # Expand LoRA stacks
        expanded_loras = expand_lora_stack(entry.get("lora", "None"), str_m[0], str_c[0])
        
        # Build all combinations
        base_combos = []
        for combo in itertools.product(samplers, schedulers, steps_l, cfgs, expanded_loras, 
                                      str_m, str_c, denoise_values, prompt_pairs, expanded_models):
            base_combos.append({
                "sampler": combo[0],
                "scheduler": combo[1],
                "steps": combo[2],
                "cfg": combo[3],
                "lora": combo[4],
                "str_model": combo[5],
                "str_clip": combo[6],
                "denoise": combo[7],
                "positive": combo[8][0],
                "negative": combo[8][1],
                "model": combo[9],
                "seed": seed
            })
        
        # Apply base seed and extra seeds
        for c in base_combos:
            expanded.append(c)
            for extra_seed in extra_seeds:
                new_c = c.copy()
                new_c["seed"] = extra_seed
                expanded.append(new_c)
    
    return expanded


def prepare_input_jobs(optional_latent, resolutions):
    """
    Prepare input jobs from either optional latent or resolution list.
    
    Args:
        optional_latent: Optional latent tensor input
        resolutions: List of [width, height] pairs
        
    Returns:
        List of job dictionaries with label, width, height, latent, batch_idx
    """
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
                "width": res[0],
                "height": res[1],
                "latent": None,
                "batch_idx": 0
            })
    
    return input_jobs


def sanitize_session_name(session_name):
    """Sanitize session name to be filesystem-safe"""
    session_name = re.sub(r'[^\w\-]', '', session_name)
    if not session_name:
        session_name = "default_session"
    return session_name