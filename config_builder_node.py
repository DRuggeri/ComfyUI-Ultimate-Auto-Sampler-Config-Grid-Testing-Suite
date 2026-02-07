"""
Ultimate Config Builder - Complete HTML UI Version
ALL data stored in single widget (lora_config)
Python reads everything from that widget
"""

import os
import json
import folder_paths
from typing import List, Dict, Any
import server
from aiohttp import web
import hashlib
import requests




# =============================================================================
# INLINE LORA_UTILS FUNCTIONS (for compatibility)
# =============================================================================

def load_json_from_file(file_path):
    """Load JSON data from file"""
    try:
        with open(file_path, 'r') as json_file:
            data = json.load(json_file)
            return data
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        print(f"[ConfigBuilder] Error decoding JSON in file: {file_path}")
        return None


def save_dict_to_json(data_dict, file_path):
    """Save dictionary to JSON file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as json_file:
            json.dump(data_dict, json_file, indent=4)
            print(f"[ConfigBuilder] Data saved to {file_path}")
    except Exception as e:
        print(f"[ConfigBuilder] Error saving JSON to file: {e}")


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
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"[ConfigBuilder] Error fetching from CivitAI: {e}")
        return None


def load_and_save_tags(lora_name, force_fetch=False, auto_fetch=True):
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
    output_dir = folder_paths.get_output_directory()
    json_tags_path = os.path.join(output_dir, "benchmarks", "loras_tags.json")
    
    lora_tags = load_json_from_file(json_tags_path)
    
    # Normalize the lora_name to use forward slashes for cache lookup
    normalized_name = lora_name.replace("\\", "/")
    
    # Try to find in cache
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
    
    # If found in cache, return immediately
    if found_in_cache:
        return output_tags if output_tags is not None else []
    
    # NOT IN CACHE - Need to fetch from API
    lora_path = folder_paths.get_full_path("loras", lora_name)
    
    # Check if lora_path is valid before attempting to hash
    if lora_path is None:
        print(f"[ConfigBuilder] ⚠️ LoRA file not found: {lora_name}")
        return []
    
    # Only hash if force_fetch is True OR (not in cache AND auto_fetch is True)
    if force_fetch or auto_fetch:
        print(f"[ConfigBuilder] 🔄 Fetching tags for {lora_name}")
        try:
            LORAsha256 = calculate_sha256(lora_path)
            model_info = get_model_version_info(LORAsha256)
            
            if model_info is not None and "trainedWords" in model_info:
                print(f"[ConfigBuilder] ✅ Tags found for {lora_name}")
                if lora_tags is None:
                    lora_tags = {}
                lora_tags[normalized_name] = model_info["trainedWords"]
                save_dict_to_json(lora_tags, json_tags_path)
                return model_info["trainedWords"]
            else:
                print(f"[ConfigBuilder] No tags found for {lora_name}")
                if lora_tags is None:
                    lora_tags = {}
                lora_tags[normalized_name] = []
                save_dict_to_json(lora_tags, json_tags_path)
                return []
        except Exception as e:
            print(f"[ConfigBuilder] Error processing {lora_name}: {e}")
            return []
    else:
        # Not in cache and auto_fetch=False
        if lora_tags is None:
            lora_tags = {}
        lora_tags[normalized_name] = []
        save_dict_to_json(lora_tags, json_tags_path)
        return []


class UltimateConfigBuilder:
    """
    Config builder with complete HTML UI.
    All data is stored in the lora_config widget as a single JSON object.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        sessions = cls.get_available_sessions()
        
        return {
            "required": {
                # Session Management (hidden, controlled by HTML)
                "session_name": ("STRING", {
                    "default": "my_test_session",
                    "multiline": False
                }),
                "load_session": (sessions, {
                    "default": sessions[0] if sessions else "None"
                }),
                
                # Sampler Settings (hidden, controlled by HTML)
                "samplers": ("STRING", {
                    "default": "euler, dpmpp_2m",
                    "multiline": False
                }),
                "schedulers": ("STRING", {
                    "default": "normal, karras",
                    "multiline": False
                }),
                "steps": ("STRING", {
                    "default": "20, 30",
                    "multiline": False
                }),
                "cfg": ("STRING", {
                    "default": "7.0",
                    "multiline": False
                }),
                
                # LoRA Configuration (ACTUAL DATA STORAGE - contains EVERYTHING)
                "lora_config": ("STRING", {
                    "default": cls.get_default_config(),
                    "multiline": True
                }),
                
                # Options (hidden, controlled by HTML)
                "include_none": ("BOOLEAN", {
                    "default": False
                }),
            },
            "optional": {
                "model": ("STRING", {
                    "default": "",
                    "multiline": False
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("configs_json", "session_name")
    FUNCTION = "generate_config"
    CATEGORY = "sampling/testing"
    OUTPUT_NODE = True
    
    @staticmethod
    def get_default_config():
        """Return default complete configuration"""
        config = {
            "session_name": "my_test_session",
            "include_none": False,
            "config_arrays": [
                {
                    "name": "Config 1",
                    "samplers": "euler, dpmpp_2m",
                    "schedulers": "normal, karras",
                    "steps": "20, 30",
                    "cfg": "7.0",
                    "model": "",
                    "loras": ["None"],
                    "lora_omit_triggers": [],
                    "combine": False
                }
            ]
        }
        return json.dumps(config, indent=2, ensure_ascii=False)
    
    @staticmethod
    def get_available_sessions() -> List[str]:
        """Scan benchmarks folder for available sessions, sorted by newest first"""
        sessions = ["None"]
        try:
            output_dir = folder_paths.get_output_directory()
            benchmarks_dir = os.path.join(output_dir, "benchmarks")
            
            if os.path.exists(benchmarks_dir):
                session_items = []
                for item in os.listdir(benchmarks_dir):
                    item_path = os.path.join(benchmarks_dir, item)
                    manifest_path = os.path.join(item_path, "manifest.json")
                    
                    if os.path.isdir(item_path) and os.path.exists(manifest_path):
                        # Get modification time for sorting
                        mtime = os.path.getmtime(item_path)
                        session_items.append((item, mtime))
                
                # Sort by modification time (newest first)
                session_items.sort(key=lambda x: x[1], reverse=True)
                sessions.extend([item[0] for item in session_items])
        except Exception as e:
            print(f"[ConfigBuilder] Warning: Could not scan sessions: {e}")
        
        return sessions
    
    @staticmethod
    def expand_lora_folders(lora_list: List[str]) -> List[str]:
        """
        Expand folder references to individual LoRA files.
        
        Args:
            lora_list: List of LoRA strings (may include folders)
            
        Returns:
            List with folders expanded to individual files
        """
        expanded = []
        available_loras = folder_paths.get_filename_list("loras")
        
        for lora_str in lora_list:
            if not lora_str or lora_str == "None":
                continue
            
            # Parse out the name (before any : strength modifiers)
            lora_name = lora_str.split(":")[0]
            
            # Check if it's a folder reference
            is_folder = lora_name.endswith("/") or lora_name.endswith("/*")
            
            if is_folder:
                # Remove trailing / or /*
                folder_name = lora_name.rstrip("/*").rstrip("/")
                
                # Normalize to forward slashes for comparison
                folder_prefix = folder_name.replace("\\", "/") + "/"
                
                # Find all LoRAs in this folder
                for lora_file in available_loras:
                    normalized_file = lora_file.replace("\\", "/")
                    if normalized_file.startswith(folder_prefix):
                        expanded.append(lora_file)
                
                print(f"[ConfigBuilder] Expanded folder '{lora_name}' to {len([l for l in available_loras if l.replace('\\', '/').startswith(folder_prefix)])} LoRAs")
            else:
                # Regular LoRA file
                expanded.append(lora_str)
        
        return expanded
    
    @staticmethod
    def lookup_lora_triggers(lora_list: List[str]) -> Dict[str, List[str]]:
        """
        Lookup trigger words for a list of LoRAs.
        
        Args:
            lora_list: List of LoRA strings (may include strengths and folders)
            
        Returns:
            Dict mapping lora name to list of trigger words
        """
        # First, expand any folder references
        expanded_list = UltimateConfigBuilder.expand_lora_folders(lora_list)
        
        trigger_map = {}
        
        for lora_str in expanded_list:
            if not lora_str or lora_str == "None":
                continue
                
            # Handle combined LoRAs (e.g., "lora1 + lora2")
            if " + " in lora_str:
                parts = lora_str.split(" + ")
                for part in parts:
                    part = part.strip()
                    if part and part != "None":
                        lora_name = part.split(":")[0]
                        if lora_name not in trigger_map:
                            try:
                                triggers = load_and_save_tags(
                                    lora_name, 
                                    force_fetch=False,
                                    auto_fetch=True
                                )
                                trigger_map[lora_name] = triggers if triggers else []
                            except Exception as e:
                                print(f"[ConfigBuilder] Error fetching triggers for {lora_name}: {e}")
                                trigger_map[lora_name] = []
            else:
                # Single LoRA
                lora_name = lora_str.split(":")[0]
                if lora_name and lora_name != "None" and lora_name not in trigger_map:
                    try:
                        triggers = load_and_save_tags(
                            lora_name,
                            force_fetch=False,
                            auto_fetch=True
                        )
                        trigger_map[lora_name] = triggers if triggers else []
                    except Exception as e:
                        print(f"[ConfigBuilder] Error fetching triggers for {lora_name}: {e}")
                        trigger_map[lora_name] = []
        
        return trigger_map
    
    def parse_int_list(self, value: str) -> List[int]:
        """Parse comma-separated integers"""
        items = self.parse_comma_list(value)
        result = []
        for item in items:
            try:
                # Cast to float first to handle strings like "20.0", then to int
                result.append(int(float(item)))
            except ValueError:
                print(f"[ConfigBuilder] Warning: Could not parse integer '{item}'")
        return result
    
    def parse_comma_list(self, value: str) -> List[str]:
        """Parse comma-separated string"""
        if not value or value.strip() == "":
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    
    def parse_number_list(self, value: str) -> List[float]:
        """Parse comma-separated numbers"""
        items = self.parse_comma_list(value)
        result = []
        for item in items:
            try:
                result.append(float(item))
            except ValueError:
                print(f"[ConfigBuilder] Warning: Could not parse '{item}'")
        return result
    
    def process_lora_array(self, config_array: Dict, include_none: bool) -> List[str]:
        """
        Process a SINGLE config array and return its lora strings.
        
        Args:
            config_array: Single config array dict from config_arrays
            include_none: Whether to include "None" in results
            
        Returns:
            List of lora strings for this config array
        """
        array_name = config_array.get("name", "Unnamed Config")
        combine = config_array.get("combine", False)
        loras = config_array.get("loras", [])
        
        # Loras are already strings
        lora_strings = [str(lora) for lora in loras if lora and lora != "None"]
        
        # Add combined version if requested
        if combine and len(lora_strings) > 1:
            stackable = [s for s in lora_strings if not s.endswith("/")]
            if len(stackable) > 1:
                # When combine is true, ONLY return the combined version
                combined = " + ".join(stackable)
                lora_strings = [combined]
                print(f"[ConfigBuilder] {array_name}: Using combined version only")
        
        # Handle None option
        # if include_none:
        #     lora_strings.insert(0, "None")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_strings = []
        for item in lora_strings:
            if item not in seen:
                seen.add(item)
                unique_strings.append(item)
        
        print(f"[ConfigBuilder] {array_name}: Processed {len(unique_strings)} LoRA configs")
        return unique_strings
    
    def generate_config(
        self,
        session_name,
        load_session,
        samplers,
        schedulers,
        steps,
        cfg,
        lora_config,
        include_none,
        model=""
    ):
        """
        Generate configuration.
        
        NOTE: All widget parameters are IGNORED!
        The actual data comes from the lora_config widget which contains everything.
        """
        
        print(f"\n{'='*80}")
        print(f"[ConfigBuilder] 🎯 Generating Configuration")
        print(f"{'='*80}")
        
        # Parse the COMPLETE state from lora_config widget
        try:
            state = json.loads(lora_config)
        except json.JSONDecodeError as e:
            print(f"[ConfigBuilder] ⚠️ Error parsing lora_config: {e}")
            print(f"[ConfigBuilder] Using default config")
            state = json.loads(self.get_default_config())
        
        # Extract values from state
        actual_session_name = state.get("session_name", session_name)
        actual_include_none = state.get("include_none", include_none)
        config_arrays = state.get("config_arrays", [])
        
        if not config_arrays:
            config_arrays = [{
                "name": "Config 1",
                "samplers": "euler",
                "schedulers": "normal",
                "steps": "20",
                "cfg": "7.0",
                "model": "",
                "loras": ["None"],
                "lora_omit_triggers": [],
                "combine": False
            }]
        
        configs_output = []
        total_lora_configs = 0
        
        for config_array in config_arrays:
            # Parse values from this config array
            sampler_list = self.parse_comma_list(config_array.get("samplers", "euler"))
            scheduler_list = self.parse_comma_list(config_array.get("schedulers", "normal"))
            steps_list = self.parse_int_list(config_array.get("steps", "20"))
            cfg_list = self.parse_number_list(config_array.get("cfg", "7.0"))
            models = config_array.get("models", ["None"])
            omit_triggers = config_array.get("lora_omit_triggers", [])
            
            # Process models
            model_strings = [str(m) for m in models if m and m != "None"]
            
            # Process loras for this config
            lora_strings = self.process_lora_array(config_array, actual_include_none)
            total_lora_configs += len(lora_strings)
            
            # Create ONE config for this array
            config = {
                "sampler": sampler_list if len(sampler_list) > 1 else sampler_list[0] if sampler_list else "euler",
                "scheduler": scheduler_list if len(scheduler_list) > 1 else scheduler_list[0] if scheduler_list else "normal",
                "steps": steps_list if len(steps_list) > 1 else steps_list[0] if steps_list else 20,
                "cfg": cfg_list if len(cfg_list) > 1 else cfg_list[0] if cfg_list else 7.0,
                "lora": lora_strings if len(lora_strings) > 1 else lora_strings[0] if lora_strings else "None",
                "model": model_strings if len(model_strings) > 1 else model_strings[0] if model_strings else "None"
            }
            
            # Add omit triggers if present
            if omit_triggers:
                config["lora_omit_triggers"] = omit_triggers
            
            configs_output.append(config)
        
        json_output = json.dumps(configs_output, indent=2, ensure_ascii=False)
        
        # Calculate totals
        total_combinations = 0
        for config in configs_output:
            lora_count = len(config["lora"]) if isinstance(config["lora"], list) else 1
            sampler_count = len(config["sampler"]) if isinstance(config["sampler"], list) else 1
            scheduler_count = len(config["scheduler"]) if isinstance(config["scheduler"], list) else 1
            steps_count = len(config["steps"]) if isinstance(config["steps"], list) else 1
            cfg_count = len(config["cfg"]) if isinstance(config["cfg"], list) else 1
            
            total_combinations += (sampler_count * scheduler_count * steps_count * cfg_count * lora_count)
        
        print(f"[ConfigBuilder] 📊 Configuration Summary:")
        print(f"  Session: {actual_session_name}")
        print(f"  Config Arrays: {len(config_arrays)}")
        print(f"  Total LoRA Configs: {total_lora_configs}")
        print(f"  Total Combinations: {total_combinations}")
        print(f"{'='*80}\n")
        
        # Return just the essentials
        return (json_output, actual_session_name)


# API endpoint for trigger word lookup
@server.PromptServer.instance.routes.post("/configbuilder/lookup_triggers")
async def lookup_triggers_endpoint(request):
    """API endpoint to lookup trigger words for LoRAs"""
    try:
        data = await request.json()
        lora_list = data.get("loras", [])
        
        print(f"[ConfigBuilder] 🔍 Lookup request for {len(lora_list)} LoRAs")
        
        trigger_map = UltimateConfigBuilder.lookup_lora_triggers(lora_list)
        
        print(f"[ConfigBuilder] ✅ Found triggers for {len(trigger_map)} LoRAs")
        
        return web.json_response({
            "triggers": trigger_map
        })
    except Exception as e:
        print(f"[ConfigBuilder] ❌ Error in lookup_triggers endpoint: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({
            "error": str(e)
        }, status=500)


NODE_CLASS_MAPPINGS = {
    "UltimateConfigBuilder": UltimateConfigBuilder
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UltimateConfigBuilder": "Ultimate Config Builder"
}

WEB_DIRECTORY = "./web"