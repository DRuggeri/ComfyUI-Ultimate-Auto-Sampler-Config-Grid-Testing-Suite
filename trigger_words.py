"""
LoRA Trigger Word Management
Handles fetching, filtering, and processing of LoRA trigger words from Civitai
"""

from .lora_utils import load_and_save_tags
from .config_utils import parse_lora_definition


def get_filtered_lora_triggers(lora_string, omit_list, lookup_triggers=True):
    """
    Get LoRA trigger words with filtering applied.
    
    Args:
        lora_string: LoRA definition string (e.g., "lora1.safetensors:0.8:0.6 + lora2.safetensors:1.0:1.0")
        omit_list: List of trigger words to omit
        lookup_triggers: Whether to lookup triggers from Civitai
        
    Returns:
        List of filtered trigger words
    """
    if not lookup_triggers or lora_string == "None":
        return []
    
    active_loras = parse_lora_definition(lora_string)
    trigger_list = []
    
    # Normalize omit list: strip whitespace and trailing commas, lowercase
    omit_normalized = []
    for t in omit_list:
        normalized = str(t).lower().strip().rstrip(',').strip()
        omit_normalized.append(normalized)
    
    for lora_def in active_loras:
        lname, lstr_m, lstr_c = lora_def
        try:
            civitai_tags_list = load_and_save_tags(lname, force_fetch=False)
            if len(civitai_tags_list) > 0:
                for tags in civitai_tags_list:
                    # Clean the trigger: strip whitespace and trailing commas
                    cleaned_tags = tags.strip().rstrip(',').strip()
                    
                    # Check if this trigger should be omitted (case-insensitive)
                    if cleaned_tags.lower() not in omit_normalized:
                        trigger_list.append(cleaned_tags)
        except Exception as e:
            pass
    
    return trigger_list


def collect_unique_prompts_with_triggers(expanded_configs, lookup_and_append_lora_triggerwords):
    """
    Collect all unique prompts from configs, applying LoRA trigger words where needed.
    
    Args:
        expanded_configs: List of expanded configuration dictionaries
        lookup_and_append_lora_triggerwords: Whether to append LoRA trigger words
        
    Returns:
        tuple: (unique_positives set, unique_negatives set)
    """
    unique_positives = set()
    unique_negatives = set()
    
    for conf in expanded_configs:
        full_positive = conf["positive"]
         
        if lookup_and_append_lora_triggerwords and conf["lora"] != "None":
            omit_list = conf.get("lora_omit_triggers", [])
            trigger_list = get_filtered_lora_triggers(
                conf["lora"],
                omit_list,
                lookup_triggers=True
            )
            
            if trigger_list:
                lora_triggers = ", ".join(trigger_list)
                full_positive = f"{conf['positive']}, {lora_triggers}"
                
                # Show omitted triggers only once during pre-encoding
                if omit_list:
                    all_triggers = []
                    active_loras = parse_lora_definition(conf["lora"])
                    for lora_def in active_loras:
                        lname, _, _ = lora_def
                        try:
                            tags = load_and_save_tags(lname, force_fetch=False)
                            all_triggers.extend([t.strip().rstrip(',').strip() for t in tags])
                        except:
                            pass
                    
                    omitted = set(all_triggers) - set(trigger_list)
                    if omitted:
                        print(f"[GridTester] 🚫 Omitted triggers: {', '.join(omitted)}")
        
        unique_positives.add(full_positive)
        unique_negatives.add(conf["negative"])
    
    return unique_positives, unique_negatives


def build_prompt_with_triggers(config, lookup_and_append_lora_triggerwords):
    """
    Build final prompt with LoRA triggers applied.
    
    Args:
        config: Configuration dictionary
        lookup_and_append_lora_triggerwords: Whether to append LoRA trigger words
        
    Returns:
        tuple: (final_prompt, trigger_string)
    """
    lora_triggers = ""
    
    if config["lora"] != "None" and lookup_and_append_lora_triggerwords:
        omit_list = config.get("lora_omit_triggers", [])
        trigger_list = get_filtered_lora_triggers(
            config["lora"],
            omit_list,
            lookup_triggers=True
        )
        
        if trigger_list:
            lora_triggers = ", " + ", ".join(trigger_list)
    
    final_prompt = config["positive"] + lora_triggers
    return final_prompt, lora_triggers
