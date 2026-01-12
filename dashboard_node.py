import re
import os
import json
import folder_paths
from .html_generator import get_html_template

class SamplerConfigDashboardViewer:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "session_name": ("STRING", {"default": "my_session"}),
            },
            "optional": {
                "dashboard_html": ("STRING", {"forceInput": True}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ()
    FUNCTION = "view"
    OUTPUT_NODE = True
    CATEGORY = "sampling/testing"

    def view(self, session_name, unique_id, dashboard_html=None):
        # 1. If connected to Sampler (Fresh Generation)
        if dashboard_html:
            # --- MAGIC: EXTRACT SESSION NAME FROM HTML ---
            match = re.search(r'id="session-input" class="session-input" value="(.*?)"', dashboard_html)
            found_session = match.group(1) if match else None
            
            # --- CRITICAL FIX: INJECT CORRECT DASHBOARD NODE ID ---
            # The HTML coming from Sampler might have the Sampler's ID or a placeholder.
            # We must overwrite it with THIS dashboard node's ID so listeners work.
            # We look for the const TARGET_NODE_ID = "..." line in the JS.
            fixed_html = re.sub(
                r'const TARGET_NODE_ID = ".*?";', 
                f'const TARGET_NODE_ID = "{unique_id}";', 
                dashboard_html
            )
            
            return {
                "ui": {
                    "html": [fixed_html],
                    "update_session_name": [found_session] if found_session else []
                }
            }
        
        # 2. View Mode (Load from Disk)
        session_name = re.sub(r'[^\w\-]', '', session_name)
        if not session_name: session_name = "default_session"

        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        manifest_path = os.path.join(base_dir, "manifest.json")
        
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)
                # Pass unique_id here, which get_html_template uses correctly
                html = get_html_template(session_name, manifest, unique_id) 
                return {"ui": {"html": [html]}}
            except Exception as e:
                return {"ui": {"html": [f"Error loading session: {e}"]}}
        
        return {"ui": {"html": ["<h3>No session found.</h3>"]}}