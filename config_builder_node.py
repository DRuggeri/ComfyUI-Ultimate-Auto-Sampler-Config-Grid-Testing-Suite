"""
Ultimate Config Builder with Dynamic LoRA Arrays
Enhanced with session loading that populates all fields
"""

import os
import json
import folder_paths
from typing import List, Dict, Any

class UltimateConfigBuilder:
    """
    Config builder with dynamic LoRA array management and session loading.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        sessions = cls.get_available_sessions()
        
        return {
            "required": {
                # Session Management
                "session_name": ("STRING", {
                    "default": "my_test_session",
                    "multiline": False
                }),
                "load_session": (sessions, {
                    "default": sessions[0] if sessions else "None"
                }),
                
                # Sampler Settings
                "samplers": ("STRING", {
                    "default": "euler, dpmpp_2m",
                    "multiline": False,
                    "tooltip": "Comma-separated samplers"
                }),
                "schedulers": ("STRING", {
                    "default": "normal, karras",
                    "multiline": False,
                    "tooltip": "Comma-separated schedulers"
                }),
                "steps": ("STRING", {
                    "default": "20, 30",
                    "multiline": False,
                    "tooltip": "Comma-separated step counts"
                }),
                "cfg": ("STRING", {
                    "default": "7.0",
                    "multiline": False,
                    "tooltip": "Comma-separated CFG values"
                }),
                
                # Dynamic LoRA Configuration
                "lora_config": ("STRING", {
                    "default": cls.get_default_config(),
                    "multiline": True,
                    "tooltip": "LoRA arrays configuration (managed by UI)"
                }),
                
                # Options
                "include_none": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Include 'None'",
                    "label_off": "Skip 'None'"
                }),
            },
            "optional": {
                "model": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Optional model override"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("configs_json", "session_name", "loaded_samplers", "loaded_schedulers", "loaded_steps", "loaded_cfg", "loaded_lora_config")
    FUNCTION = "generate_config"
    CATEGORY = "sampling/testing"
    OUTPUT_NODE = True
    
    @staticmethod
    def get_default_config():
        """Return default LoRA configuration"""
        config = {
            "arrays": [
                {
                    "name": "Array 1",
                    "combine": False,
                    "loras": [
                        {"type": "lora", "name": "None", "str_model": 1.0, "str_clip": 1.0}
                    ]
                }
            ]
        }
        return json.dumps(config, indent=2)
    
    @staticmethod
    def get_available_sessions() -> List[str]:
        """Scan benchmarks folder for available sessions"""
        sessions = ["None"]
        try:
            output_dir = folder_paths.get_output_directory()
            benchmarks_dir = os.path.join(output_dir, "benchmarks")
            
            if os.path.exists(benchmarks_dir):
                for item in os.listdir(benchmarks_dir):
                    item_path = os.path.join(benchmarks_dir, item)
                    manifest_path = os.path.join(item_path, "manifest.json")
                    
                    if os.path.isdir(item_path) and os.path.exists(manifest_path):
                        sessions.append(item)
        except Exception as e:
            print(f"[ConfigBuilder] Warning: Could not scan sessions: {e}")
        
        return sessions
    
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
    
    def build_lora_string(self, lora_type: str, name: str, str_model: float, str_clip: float) -> str:
        """Build LoRA string"""
        if name == "None" or not name:
            return "None"
        
        if lora_type == "folder":
            return name if name.endswith("/") else name + "/"
        
        return f"{name}:{str_model}:{str_clip}"
    
    def load_session_data(self, session_name: str) -> Dict[str, Any]:
        """Load configuration from an existing session"""
        print("loading session data")
        try:
            output_dir = folder_paths.get_output_directory()
            manifest_path = os.path.join(
                output_dir, 
                "benchmarks", 
                session_name, 
                "manifest.json"
            )
            
            if not os.path.exists(manifest_path):
                print(f"[ConfigBuilder] Session '{session_name}' not found")
                return None
            
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            meta = manifest.get("meta", {})
            
            # Extract raw config data
            raw_configs = meta.get("raw_configs", [])
            configs_json = meta.get("configs_json", "")
            print(raw_configs)
            print(configs_json)
            # Try to parse configs_json first, fall back to raw_configs
            try:
                if configs_json:
                    parsed_configs = json.loads(configs_json)
                    if isinstance(parsed_configs, list) and len(parsed_configs) > 0:
                        raw_configs = parsed_configs
            except:
                pass
            
            # Extract sampler settings - handle both single and list formats
            def extract_value(key, default):
                value = meta.get(key, default)
                if isinstance(value, list):
                    return ", ".join(str(v) for v in value)
                return str(value)
            
            # Extract settings
            loaded_data = {
                "samplers": extract_value("samplers", "euler"),
                "schedulers": extract_value("schedulers", "normal"),
                "steps": extract_value("steps", "20"),
                "cfg": extract_value("cfg", "7.0"),
                "model": meta.get("model", ""),
                "raw_configs": raw_configs
            }
            
            return loaded_data
            
        except Exception as e:
            print(f"[ConfigBuilder] Error loading session: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def convert_raw_configs_to_lora_config(self, raw_configs: List[Dict]) -> str:
        """Convert raw configs from manifest into lora_config format"""
        if not raw_configs:
            return self.get_default_config()
        
        arrays = []
        
        # Process each raw config
        for idx, raw_config in enumerate(raw_configs):
            lora_value = raw_config.get("lora", "None")
            
            # Parse the lora field
            loras_list = []
            
            if isinstance(lora_value, str):
                lora_items = [lora_value]
            elif isinstance(lora_value, list):
                lora_items = lora_value
            else:
                lora_items = ["None"]
            
            # Convert each lora item
            for lora_item in lora_items:
                if lora_item == "None":
                    loras_list.append({
                        "type": "lora",
                        "name": "None",
                        "str_model": 1.0,
                        "str_clip": 1.0
                    })
                elif lora_item.endswith("/"):
                    # Folder
                    loras_list.append({
                        "type": "folder",
                        "name": lora_item,
                        "str_model": 1.0,
                        "str_clip": 1.0
                    })
                elif " + " in lora_item:
                    # Stacked LoRAs - split and parse each
                    stacked = lora_item.split(" + ")
                    for stacked_lora in stacked:
                        if ":" in stacked_lora:
                            parts = stacked_lora.split(":")
                            loras_list.append({
                                "type": "lora",
                                "name": parts[0],
                                "str_model": float(parts[1]) if len(parts) > 1 else 1.0,
                                "str_clip": float(parts[2]) if len(parts) > 2 else 1.0
                            })
                        else:
                            loras_list.append({
                                "type": "lora",
                                "name": stacked_lora,
                                "str_model": 1.0,
                                "str_clip": 1.0
                            })
                elif ":" in lora_item:
                    # Parse lora:str_model:str_clip format
                    parts = lora_item.split(":")
                    loras_list.append({
                        "type": "lora",
                        "name": parts[0],
                        "str_model": float(parts[1]) if len(parts) > 1 else 1.0,
                        "str_clip": float(parts[2]) if len(parts) > 2 else 1.0
                    })
                else:
                    # Just a lora name
                    loras_list.append({
                        "type": "lora",
                        "name": lora_item,
                        "str_model": 1.0,
                        "str_clip": 1.0
                    })
            
            if loras_list:
                arrays.append({
                    "name": f"Loaded Config {idx + 1}",
                    "combine": False,
                    "loras": loras_list
                })
        
        config = {"arrays": arrays}
        return json.dumps(config, indent=2)
    
    def process_lora_config(self, config_data: Dict) -> List[str]:
        """Process the LoRA configuration and return list of LoRA strings"""
        arrays = config_data.get("arrays", [])
        all_configs = []
        
        for i, array in enumerate(arrays):
            array_name = array.get("name", f"Array {i+1}")
            combine = array.get("combine", False)
            loras = array.get("loras", [])
            
            lora_strings = []
            
            for lora in loras:
                lora_type = lora.get("type", "lora")
                name = lora.get("name", "None")
                str_model = lora.get("str_model", 1.0)
                str_clip = lora.get("str_clip", 1.0)
                
                lora_str = self.build_lora_string(lora_type, name, str_model, str_clip)
                lora_strings.append(lora_str)
                all_configs.append(lora_str)
            
            # Add combined version if requested
            if combine and len(lora_strings) > 1:
                stackable = [s for s in lora_strings if s != "None" and not s.endswith("/")]
                if len(stackable) > 1:
                    combined = " + ".join(stackable)
                    all_configs.append(combined)
                    print(f"[ConfigBuilder] {array_name}: Added stacked combo")
            
            print(f"[ConfigBuilder] {array_name}: Processed {len(lora_strings)} LoRAs")
        
        return all_configs
    
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
        """Generate configuration"""
        
        # Store original values for output
        output_samplers = samplers
        output_schedulers = schedulers
        output_steps = steps
        output_cfg = cfg
        output_lora_config = lora_config
        
        # Check if we should load a session
        if load_session and load_session != "None":
            print(f"\n[ConfigBuilder] 🔄 Loading session '{load_session}'...")
            loaded = self.load_session_data(load_session)
            
            if loaded:
                print(f"[ConfigBuilder] ✅ Successfully loaded session '{load_session}'")
                
                # Override parameters with loaded values
                output_samplers = loaded.get("samplers", samplers)
                output_schedulers = loaded.get("schedulers", schedulers)
                output_steps = str(loaded.get("steps", steps))
                output_cfg = str(loaded.get("cfg", cfg))
                model = loaded.get("model", model)
                
                # Convert raw configs to lora_config format
                if loaded.get("raw_configs"):
                    output_lora_config = self.convert_raw_configs_to_lora_config(loaded["raw_configs"])
                    print(f"[ConfigBuilder] 📋 Converted {len(loaded['raw_configs'])} config(s) to LoRA format")
                
                # Update session name to loaded session
                session_name = load_session
                
                print(f"[ConfigBuilder] 📊 Loaded settings:")
                print(f"  Samplers: {output_samplers}")
                print(f"  Schedulers: {output_schedulers}")
                print(f"  Steps: {output_steps}")
                print(f"  CFG: {output_cfg}")
                if model:
                    print(f"  Model: {model}")
            else:
                print(f"[ConfigBuilder] ⚠️ Could not load session '{load_session}', using current values")
        
        # Use the (potentially loaded) values for processing
        sampler_list = self.parse_comma_list(output_samplers)
        scheduler_list = self.parse_comma_list(output_schedulers)
        steps_list = self.parse_number_list(output_steps)
        cfg_list = self.parse_number_list(output_cfg)
        
        # Parse LoRA configuration
        try:
            config_data = json.loads(output_lora_config)
        except json.JSONDecodeError as e:
            print(f"[ConfigBuilder] ⚠️ Error parsing LoRA config: {e}")
            print(f"[ConfigBuilder] Using default configuration")
            config_data = json.loads(self.get_default_config())
        
        # Process LoRA arrays
        all_lora_configs = self.process_lora_config(config_data)
        
        # Add None if requested
        if include_none and "None" not in all_lora_configs:
            all_lora_configs.insert(0, "None")
        
        # Remove duplicates
        seen = set()
        unique_configs = []
        for item in all_lora_configs:
            if item not in seen:
                seen.add(item)
                unique_configs.append(item)
        
        # Build final config
        config = {
            "sampler": sampler_list if len(sampler_list) > 1 else sampler_list[0] if sampler_list else "euler",
            "scheduler": scheduler_list if len(scheduler_list) > 1 else scheduler_list[0] if scheduler_list else "normal",
            "steps": steps_list if len(steps_list) > 1 else steps_list[0] if steps_list else 20,
            "cfg": cfg_list if len(cfg_list) > 1 else cfg_list[0] if cfg_list else 7.0,
            "lora": unique_configs if len(unique_configs) > 1 else unique_configs[0] if unique_configs else "None"
        }
        
        if model and model.strip():
            config["model"] = model.strip()
        
        configs_array = [config]
        json_output = json.dumps(configs_array, indent=2)
        
        # Calculate totals
        total = (
            len(sampler_list or [1]) * 
            len(scheduler_list or [1]) * 
            len(steps_list or [1]) * 
            len(cfg_list or [1]) * 
            len(unique_configs or [1])
        )
        
        print(f"\n{'='*80}")
        print(f"[ConfigBuilder] 📋 Final Config for '{session_name}'")
        print(f"{'='*80}")
        print(f"LoRA Arrays: {len(config_data.get('arrays', []))}")
        print(f"Unique LoRA Configs: {len(unique_configs)}")
        print(f"Total Combinations: {total}")
        print(f"{'='*80}\n")
        
        # Return loaded values so they can update the UI
        return (
            json_output, 
            session_name,
            output_samplers,
            output_schedulers,
            output_steps,
            output_cfg,
            output_lora_config
        )


NODE_CLASS_MAPPINGS = {
    "UltimateConfigBuilder": UltimateConfigBuilder
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UltimateConfigBuilder": "Ultimate Config Builder"
}

WEB_DIRECTORY = "./web"