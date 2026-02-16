import json
import re
import copy
import itertools
import folder_paths
import comfy.samplers

 

def parse_prompt_input_nested(prompt_input: str):
    """
    Parse prompt input that supports plain text and arbitrarily deep nested arrays.
    Recursively creates Cartesian products from nested lists.

    Rules:
        - A plain string is a single prompt option
        - A flat list of strings ["a", "b"] = multiple OPTIONS (OR logic)
        - A list containing sub-lists = SEQUENCE (AND logic, Cartesian product)
        - Nesting can be arbitrarily deep

    Args:
        prompt_input: Plain text string OR JSON string containing prompts

    Returns:
        List of final prompt strings

    Examples:
        Plain text:     "my prompt"                                          -> ["my prompt"]
        Simple options: '["a", "b", "c"]'                                    -> ["a", "b", "c"]
        Cartesian:      '[["a", "b"], ["1", "2"]]'                           -> ["a, 1", "a, 2", "b, 1", "b, 2"]
        Recursive:      '["Photo of", ["a cat", "a dog"], ["in space", ["eating pizza", "sleeping"]]]'
                        -> ["Photo of, a cat, in space, eating pizza",
                            "Photo of, a cat, in space, sleeping",
                            "Photo of, a dog, in space, eating pizza",
                            "Photo of, a dog, in space, sleeping"]
    """

    def recursive_cartesian(item):
        """Recursively expand nested prompt structures into flat string options."""
        # Base Case: string/primitive -> single option
        if not isinstance(item, list):
            return [str(item)]

        # Check if this list contains any sub-lists
        has_nested = any(isinstance(sub, list) for sub in item)

        # Flat list of strings -> OPTIONS (OR logic)
        if not has_nested:
            return [str(x) for x in item]

        # List containing sub-lists -> SEQUENCE (AND logic, Cartesian product)
        # Each element is recursively resolved into its options, then we take the product
        normalized_groups = []
        for sub in item:
            normalized_groups.append(recursive_cartesian(sub))

        # Generate Cartesian product across the resolved groups
        combinations = itertools.product(*normalized_groups)
        return [", ".join(combo) for combo in combinations]

    # Handle None or empty string
    if not prompt_input or prompt_input.strip() == "":
        return [""]

    prompt_input = prompt_input.strip()

    # Try parsing as JSON
    try:
        parsed = json.loads(prompt_input)
    except (json.JSONDecodeError, ValueError):
        # Not valid JSON - treat as plain text
        if (prompt_input.startswith('"') and prompt_input.endswith('"')) or \
           (prompt_input.startswith("'") and prompt_input.endswith("'")):
            prompt_input = prompt_input[1:-1]
        return [prompt_input]

    # Handle empty parsed result
    if not parsed:
        return [""]

    # Start the recursion
    return recursive_cartesian(parsed)


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


def parse_lora_definition(lora_string):
    """
    Parse LoRA definition string into list of (name, model_str, clip_str) tuples.
    
    Format: "lora1.safetensors:1.0:0.8 + lora2.safetensors:0.5:0.5"
    
    If no strength is specified, defaults to 1.0 for both model and CLIP.
    
    Args:
        lora_string: String defining LoRAs with optional strengths
        
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
            c_str = float(segments[2]) if len(segments) > 2 else m_str  # Default CLIP to same as model
            definitions.append((name, m_str, c_str))
        else:
            # No strength specified, default to 1.0 for both
            definitions.append((part, 1.0, 1.0))
    return definitions


def _expand_lora_weight_arrays(lora_string):
    """
    Expand LoRA weight arrays into individual LoRA strings.

    Supports array notation in strength values for grid searching:
    - "lora.safetensors:[0.5, 0.8]:1.0" -> ["lora.safetensors:0.5:1.0", "lora.safetensors:0.8:1.0"]
    - "lora.safetensors:1.0:[0.5, 0.8]" -> ["lora.safetensors:1.0:0.5", "lora.safetensors:1.0:0.8"]
    - "lora.safetensors:[0.5, 0.8]:[0.6, 1.0]" -> 4 combinations via Cartesian product
    - "lora1:[0.5, 0.8]:1.0 + lora2:1.0:1.0" -> expands lora1 weights, keeps lora2 fixed in each

    Args:
        lora_string: Single LoRA definition (may contain " + " for stacked LoRAs)

    Returns:
        List of expanded LoRA strings with concrete weight values
    """
    if lora_string == "None":
        return ["None"]

    # Split stacked LoRAs
    stack_parts = lora_string.split(" + ")

    # For each part, check if it has array weights
    parts_expansions = []
    has_arrays = False

    for part in stack_parts:
        part = part.strip()

        # Check for bracket notation in strength values
        # Match pattern: name:[array_or_value]:[array_or_value] or name:[array_or_value]
        bracket_match = re.search(r'\[[\d.,\s]+\]', part)
        if not bracket_match:
            # No arrays in this part, keep as-is
            parts_expansions.append([part])
            continue

        has_arrays = True

        # Parse the part: split on ":" but respect brackets
        # Strategy: find the name (everything before first ":"), then parse strength fields
        segments = []
        current = ""
        depth = 0
        for ch in part:
            if ch == '[':
                depth += 1
                current += ch
            elif ch == ']':
                depth -= 1
                current += ch
            elif ch == ':' and depth == 0:
                segments.append(current)
                current = ""
            else:
                current += ch
        if current:
            segments.append(current)

        name = segments[0]

        # Parse each strength segment - could be "[0.5, 0.8]" or just "1.0"
        strength_lists = []
        for i in range(1, len(segments)):
            seg = segments[i].strip()
            if seg.startswith('[') and seg.endswith(']'):
                # Array notation - parse values
                inner = seg[1:-1]
                values = [v.strip() for v in inner.split(',') if v.strip()]
                strength_lists.append(values)
            else:
                strength_lists.append([seg])

        # Generate all combinations of strengths for this LoRA
        if strength_lists:
            combos = list(itertools.product(*strength_lists))
            expanded = [f"{name}:{':'.join(combo)}" for combo in combos]
            parts_expansions.append(expanded)
        else:
            parts_expansions.append([part])

    if not has_arrays:
        return [lora_string]

    # Cartesian product across stacked LoRAs
    result = []
    for combo in itertools.product(*parts_expansions):
        result.append(" + ".join(combo))

    if len(result) > 1:
        print(f"[GridTester] 🎛️ LoRA weight arrays expanded to {len(result)} combinations")

    return result


def expand_lora_stack(lora_input):
    """
    Expand LoRA stacks with folder support and weight array expansion.

    Handles formats like:
    - "lora.safetensors"
    - "lora.safetensors:0.8:0.6"
    - "lora.safetensors:[0.5, 0.8]:1.0" (weight array - grid searches strengths)
    - "lora1:0.8:0.6 + lora2:1.0:1.0"
    - "folder/ + lora.safetensors" (expands each LoRA individually)
    - "folder/* + lora.safetensors" (stacks ALL LoRAs in folder together)
    - "folder/:0.8:0.6 + lora.safetensors"
    - "folder/*:0.8:0.6" (stacks ALL LoRAs with same strength)

    Args:
        lora_input: LoRA specification string or list

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

            # Check for folder/* syntax (stack all together)
            if norm_path.endswith("/*") or (norm_path.endswith("*") and "/" in norm_path):
                # Remove the /* or * suffix
                folder_path = norm_path.rstrip("/*").rstrip("*").rstrip("/")
                found_files = get_files_from_folder(folder_path + "/", "loras")

                if found_files:
                    # Stack ALL files together as a single entry (not separate combinations)
                    stacked = " + ".join([f"{f}{args}" for f in found_files])
                    expanded_parts.append([stacked])
                    print(f"[GridTester] 📚 Folder/* syntax: Stacking {len(found_files)} LoRAs from '{folder_path}' together")
                else:
                    print(f"[GridTester] ⚠️ No LoRAs found in folder: {folder_path}")
                    expanded_parts.append([])

            # Check for regular folder/ syntax (expand individually)
            elif norm_path.endswith("/"):
                found_files = get_files_from_folder(base_path, "loras")
                expanded_parts.append([f"{f}{args}" for f in found_files])
            else:
                expanded_parts.append([part])

        # Skip if any part expanded to empty
        if not all(expanded_parts):
            continue

        for combo in itertools.product(*expanded_parts):
            joined = " + ".join(combo)
            # Now expand any weight arrays in the joined result
            weight_expanded = _expand_lora_weight_arrays(joined)
            expanded_loras.extend(weight_expanded)

    return expanded_loras


def expand_configs(raw_configs, pos_prompts, neg_prompts, denoise_values, seed, extra_seeds, ckpt_name=None):
    """
    Expand raw config entries into full configuration combinations.

    Supports per-config prompts: if a config entry has "positive" and/or "negative" keys,
    those override the external pos_prompts/neg_prompts for that entry. This allows each
    config to define its own nested array prompts for Cartesian product expansion.

    Args:
        raw_configs: List of config dictionaries with potentially wildcarded values
        pos_prompts: List of positive prompts (fallback when config doesn't define prompts)
        neg_prompts: List of negative prompts (fallback when config doesn't define prompts)
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

    # Default prompt pairing strategy (used when config doesn't define its own prompts)
    if len(pos_prompts) > 1 and len(neg_prompts) > 1 and len(pos_prompts) == len(neg_prompts):
        print("[GridTester] Detected matching prompt lists. Using 1-to-1 Pairing.")
        default_prompt_pairs = list(zip(pos_prompts, neg_prompts))
    else:
        default_prompt_pairs = list(itertools.product(pos_prompts, neg_prompts))

    def to_list(x):
        return x if isinstance(x, list) else [x]

    for entry in raw_configs:
        # ==== PER-CONFIG PROMPT HANDLING ====
        # If this config defines its own prompts, parse them and use instead of defaults
        if "positive" in entry or "negative" in entry:
            raw_positive = entry.get("positive", "")
            raw_negative = entry.get("negative", "")

            # Handle both string and already-parsed list/nested-list formats
            if isinstance(raw_positive, (list, tuple)):
                # Already a list/nested structure - pass as JSON string for parse_prompt_input_nested
                config_pos = parse_prompt_input_nested(json.dumps(raw_positive))
            elif isinstance(raw_positive, str) and raw_positive.strip():
                config_pos = parse_prompt_input_nested(raw_positive)
            else:
                config_pos = pos_prompts  # Fallback to external

            if isinstance(raw_negative, (list, tuple)):
                config_neg = parse_prompt_input_nested(json.dumps(raw_negative))
            elif isinstance(raw_negative, str) and raw_negative.strip():
                config_neg = parse_prompt_input_nested(raw_negative)
            else:
                config_neg = neg_prompts  # Fallback to external

            # Build prompt pairs for this config entry
            if len(config_pos) > 1 and len(config_neg) > 1 and len(config_pos) == len(config_neg):
                entry_prompt_pairs = list(zip(config_pos, config_neg))
            else:
                entry_prompt_pairs = list(itertools.product(config_pos, config_neg))

            if entry_prompt_pairs:
                print(f"[GridTester] Config defines {len(entry_prompt_pairs)} prompt combinations (overriding node inputs)")
        else:
            entry_prompt_pairs = default_prompt_pairs

        # Expand wildcards
        samplers = ALL_SAMPLERS if entry.get("sampler") == "*" else to_list(entry.get("sampler", "euler"))
        schedulers = ALL_SCHEDULERS if entry.get("scheduler") == "*" else to_list(entry.get("scheduler", "normal"))
        steps_l = to_list(entry.get("steps", 20))
        cfgs = to_list(entry.get("cfg", 7.0))
        clip_skips = to_list(entry.get("clip_skip", 0))

        # Extract model type and related fields for non-checkpoint models
        model_type = entry.get("model_type", "checkpoint")
        clip_type_str = entry.get("clip_type", "stable_diffusion")
        text_encoders = entry.get("text_encoders", [])
        gguf_options = entry.get("gguf_options", {})

        # Expand model folders (using correct folder type based on model_type)
        raw_models = to_list(entry.get("model", "Default"))
        expanded_models = []
        if model_type == "gguf":
            model_folder = "unet_gguf"
        elif model_type == "diffusion_model":
            model_folder = "diffusion_models"
        else:
            model_folder = "checkpoints"

        for m in raw_models:
            if m == "Default":
                # Use the checkpoint name from node input instead of "Default"
                if ckpt_name:
                    expanded_models.append(ckpt_name)
                else:
                    expanded_models.append("Default")
            else:
                expanded_models.extend(get_files_from_folder(m, model_folder))

        # Expand VAE list
        raw_vaes = to_list(entry.get("vae", "Default"))

        # Expand LoRA stacks (strengths are now in the lora string itself)
        expanded_loras = expand_lora_stack(entry.get("lora", "None"))

        # Get LoRA trigger word omissions (if specified)
        lora_omit_triggers = entry.get("lora_omit_triggers", [])
        if not isinstance(lora_omit_triggers, list):
            lora_omit_triggers = [lora_omit_triggers]

        # Get LoRA trigger word append settings (if specified)
        lora_triggerwords_append_settings = entry.get("lora_triggerwords_append_settings", {})
        if not isinstance(lora_triggerwords_append_settings, dict):
            lora_triggerwords_append_settings = {}

        # Get model-specific prompt prefix/suffix (quality tags for specific model families)
        model_prompt_prefix = entry.get("model_prompt_prefix", "")
        model_prompt_suffix = entry.get("model_prompt_suffix", "")
        if not isinstance(model_prompt_prefix, str):
            model_prompt_prefix = str(model_prompt_prefix)
        if not isinstance(model_prompt_suffix, str):
            model_prompt_suffix = str(model_prompt_suffix)

        # Get attention mode(s) for testing different attention implementations
        # Valid: "default", "xformers", "pytorch", "flash", "sage", "sage3", "sub_quad", "split", "*"
        VALID_ATTENTION_MODES = ["default", "xformers", "pytorch", "flash", "sage", "sage3", "sub_quad", "split"]
        raw_attention = to_list(entry.get("attention_mode", "default"))
        if raw_attention == ["*"]:
            attention_modes = VALID_ATTENTION_MODES
        else:
            attention_modes = [a for a in raw_attention if a in VALID_ATTENTION_MODES] or ["default"]

        # Build all combinations
        base_combos = []
        for combo in itertools.product(samplers, schedulers, steps_l, cfgs, clip_skips, expanded_loras,
                                      denoise_values, entry_prompt_pairs, expanded_models, raw_vaes,
                                      attention_modes):
            base_combos.append({
                "sampler": combo[0],
                "scheduler": combo[1],
                "steps": combo[2],
                "cfg": combo[3],
                "clip_skip": combo[4],
                "lora": combo[5],
                "denoise": combo[6],
                "positive": combo[7][0],
                "negative": combo[7][1],
                "model": combo[8],
                "vae": combo[9],
                "attention_mode": combo[10],
                "seed": seed,
                "seed_behavior": entry.get("seed_behavior", "fixed"),
                "model_type": model_type,
                "clip_type": clip_type_str,
                "text_encoders": list(text_encoders),
                "gguf_options": dict(gguf_options) if gguf_options else {},
                "lora_omit_triggers": list(lora_omit_triggers),
                "lora_triggerwords_append_settings": dict(lora_triggerwords_append_settings),
                "model_prompt_prefix": model_prompt_prefix.strip(),
                "model_prompt_suffix": model_prompt_suffix.strip()
            })

        # Apply base seed and extra seeds
        for c in base_combos:
            expanded.append(c)
            for extra_seed in extra_seeds:
                new_c = copy.deepcopy(c)
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