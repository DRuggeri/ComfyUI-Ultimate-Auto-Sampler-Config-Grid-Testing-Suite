"""
Ultimate Config Builder - Complete HTML UI Version
ALL data stored in single widget (lora_config)
Python reads everything from that widget
"""

import os
import json
import folder_paths
from typing import List, Dict, Any

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
                    "default": True
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
            "include_none": True,
            "config_arrays": [
                {
                    "name": "Config 1",
                    "samplers": "euler, dpmpp_2m",
                    "schedulers": "normal, karras",
                    "steps": "20, 30",
                    "cfg": "7.0",
                    "model": "",
                    "loras": ["None"],
                    "combine": False
                }
            ]
        }
        return json.dumps(config, indent=2, ensure_ascii=False)
    
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
        if include_none:
            lora_strings.insert(0, "None")
        
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
                "combine": False
            }]
        
        configs_output = []
        total_lora_configs = 0
        
        for config_array in config_arrays:
            # Parse values from this config array
            sampler_list = self.parse_comma_list(config_array.get("samplers", "euler"))
            scheduler_list = self.parse_comma_list(config_array.get("schedulers", "normal"))
            steps_list = self.parse_number_list(config_array.get("steps", "20"))
            cfg_list = self.parse_number_list(config_array.get("cfg", "7.0"))
            config_model = config_array.get("model", "")
            
            # Process loras for this config
            lora_strings = self.process_lora_array(config_array, actual_include_none)
            total_lora_configs += len(lora_strings)
            
            # Create ONE config for this array
            config = {
                "sampler": sampler_list if len(sampler_list) > 1 else sampler_list[0] if sampler_list else "euler",
                "scheduler": scheduler_list if len(scheduler_list) > 1 else scheduler_list[0] if scheduler_list else "normal",
                "steps": steps_list if len(steps_list) > 1 else steps_list[0] if steps_list else 20,
                "cfg": cfg_list if len(cfg_list) > 1 else cfg_list[0] if cfg_list else 7.0,
                "lora": lora_strings if len(lora_strings) > 1 else lora_strings[0] if lora_strings else "None"
            }
            
            if config_model and config_model.strip():
                config["model"] = config_model.strip()
            
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


NODE_CLASS_MAPPINGS = {
    "UltimateConfigBuilder": UltimateConfigBuilder
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UltimateConfigBuilder": "Ultimate Config Builder"
}

WEB_DIRECTORY = "./web"