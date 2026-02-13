import re
import server
from aiohttp import web
import json
import os
import folder_paths
import shutil
from .sampler_node import SamplerGridTester
from .dashboard_node import SamplerConfigDashboardViewer
from .html_generator import get_html_template
from .config_builder_node import UltimateConfigBuilder
from .json_text_node import SmartJSONTextNode
from .metadata_packer import pack_metadata_into_image


# --- CONFIG MANAGEMENT PATH ---
CONFIGS_DIR = os.path.join(folder_paths.get_output_directory(), "ultimate-configs")
os.makedirs(CONFIGS_DIR, exist_ok=True)

# --- CONFIG BUILDER JS DIRECTORY ---
EXTENSION_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_BUILDER_JS_DIR = os.path.join(EXTENSION_DIR, "js")

# =============================================================================
# SERVE CONFIG BUILDER JS FILES (NOT AUTO-LOADED)
# =============================================================================

@server.PromptServer.instance.routes.get("/ultimate_config_sampler/js/{filename:.*}")
async def serve_config_builder_js(request):
    r"""
    Serve JavaScript files from /js/ directory with cache-busting headers.
    Supports subdirectories with both / and \ (e.g., config-builder/utilities.js)
    """
    try:
        filename = request.match_info['filename']
        print(f"[ConfigBuilder] Request for: {filename}")
        
        # Security: prevent directory traversal with ..
        if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            print(f"[ConfigBuilder] FORBIDDEN: {filename}")
            return web.Response(status=403, text="Forbidden")
        
        # Normalize path separators (convert backslashes to forward slashes)
        filename = filename.replace('\\', '/')
        
        # Build full path and normalize it
        file_path = os.path.normpath(os.path.join(CONFIG_BUILDER_JS_DIR, filename))
        
        # Double-check the resolved path is still within our JS directory
        normalized_base = os.path.normpath(CONFIG_BUILDER_JS_DIR)

        if not file_path.startswith(normalized_base):
            print(f"[ConfigBuilder] FORBIDDEN - Outside base dir: {file_path}")
            return web.Response(status=403, text="Forbidden - path outside base directory")
        
        if not os.path.exists(file_path):
            print(f"[ConfigBuilder] NOT FOUND: {file_path}")
            return web.Response(status=404, text=f"File not found: {filename}")
        
        print(f"[ConfigBuilder] Reading file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"[ConfigBuilder] File read successfully, {len(content)} bytes")
        
        # Return with cache-busting headers
        return web.Response(
            text=content,
            content_type='application/javascript',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
        
    except Exception as e:
        print(f"[ConfigBuilder] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=f"Server error: {str(e)}")


# =============================================================================
# API: CONFIG MANAGEMENT
# =============================================================================

@server.PromptServer.instance.routes.get("/configbuilder/list_configs")
async def list_configs(request):
    try:
        if not os.path.exists(CONFIGS_DIR):
            os.makedirs(CONFIGS_DIR, exist_ok=True)
        
        files = [f for f in os.listdir(CONFIGS_DIR) if f.endswith(".json")]
        files.sort()
        return web.json_response(files)
    except Exception as e:
        return web.Response(status=500, text=str(e))

@server.PromptServer.instance.routes.post("/configbuilder/save_config")
async def save_config(request):
    try:
        data = await request.json()
        filename = data.get("name")
        config_data = data.get("data")
        
        if not filename or not config_data:
            return web.Response(status=400, text="Missing name or data")
        
        if not filename.endswith(".json"):
            filename += ".json"
            
        # Basic sanitization
        filename = os.path.basename(filename)
        filepath = os.path.join(CONFIGS_DIR, filename)
        
        with open(filepath, "w") as f:
            json.dump(config_data, f, indent=4)
            
        return web.Response(status=200, text="Saved")
    except Exception as e:
        print(f"[ConfigBuilder] Error saving config: {e}")
        return web.Response(status=500, text=str(e))

@server.PromptServer.instance.routes.post("/configbuilder/load_config")
async def load_config(request):
    try:
        data = await request.json()
        filename = data.get("name")
        
        if not filename:
             return web.Response(status=400, text="Missing name")
             
        if not filename.endswith(".json"):
            filename += ".json"

        filename = os.path.basename(filename)
        filepath = os.path.join(CONFIGS_DIR, filename)
        
        if not os.path.exists(filepath):
            return web.Response(status=404, text="Config not found")
            
        with open(filepath, "r") as f:
            config_data = json.load(f)
            
        return web.json_response(config_data)
    except Exception as e:
        print(f"[ConfigBuilder] Error loading config: {e}")
        return web.Response(status=500, text=str(e))


# =============================================================================
# API: DELETE SESSION
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/delete_session")
async def delete_session(request):
    try:
        data = await request.json()
        session_name = data.get("session_name")

        # Sanitize
        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)
        
        if not session_name or session_name == "default_session":
             return web.Response(status=400, text="Invalid session name")

        # Path construction
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        
        if os.path.exists(base_dir):
            shutil.rmtree(base_dir) # Deletes the folder and images
            return web.Response(status=200, text="Deleted")
        else:
            return web.Response(status=404, text="Session not found")

    except Exception as e:
        return web.Response(status=500, text=str(e))

# =============================================================================
# API: SAVE CHANGES (Optimized - Only Changed Items)
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/save_changes")
async def save_changes(request):
    """
    OPTIMIZED: Save only changed items instead of full manifest.
    
    This drastically reduces network payload and processing time:
    - Before: ~10MB for 500 images
    - After: ~10KB for 1-5 changed items
    
    Receives:
        - session_name: str
        - changed_items: list of item objects with updates
    
    Process:
        1. Load current manifest from disk
        2. Update only the changed items by ID
        3. Save back to disk
    """
    try:
        data = await request.json()
        session_name = data.get("session_name")
        changed_items = data.get("changed_items", [])
        
        # Sanitize
        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)
        
        if not session_name or not changed_items:
            return web.Response(status=400, text="Missing session_name or changed_items")
        
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        manifest_path = os.path.join(base_dir, "manifest.json")
        
        # Load current manifest
        if not os.path.exists(manifest_path):
            return web.Response(status=404, text=f"Session '{session_name}' not found")
        
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        # Create lookup of changed items by ID
        changed_by_id = {item.get("id"): item for item in changed_items if "id" in item}
        
        # Update items in manifest
        items_updated = 0
        for i, item in enumerate(manifest.get("items", [])):
            item_id = item.get("id")
            if item_id in changed_by_id:
                # Merge changes (preserve fields not sent by client)
                updated_item = changed_by_id[item_id]
                manifest["items"][i].update(updated_item)
                items_updated += 1
        
        # Save updated manifest
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=4)
        
        print(f"[ConfigTester] ⚡ Updated {items_updated} items in {session_name}")
        return web.Response(status=200, text=f"Updated {items_updated} items")
        
    except Exception as e:
        print(f"[ConfigTester] Error saving changes: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))
    
# =============================================================================
# API: SAVE MANIFEST (Legacy - Full Save)
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/save_manifest")
async def save_manifest(request):
    """
    Save manifest from dashboard.
    
    CRITICAL: This is called when users favorite/reject/note images in the dashboard.
    We need to preserve any NEW images that generation added but dashboard doesn't know about yet.
    """
    try:
        data = await request.json()
        session_name = data.get("session_name")
        manifest_data = data.get("manifest")  # This is from dashboard (may be stale)
        
        # --- sanitize ---
        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)

        if not session_name or not manifest_data:
            return web.Response(status=400, text="Missing session_name or manifest")

        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        manifest_path = os.path.join(base_dir, "manifest.json")

        # --- MERGE STRATEGY: Preserve server data ---
        # 1. Load server manifest (has newest images)
        server_manifest = None
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    server_manifest = json.load(f)
            except:
                pass

        if server_manifest:
            # Build lookup of items by ID from dashboard
            dashboard_items = {item.get("id"): item for item in manifest_data.get("items", [])}
            
            # Merge: Update existing items, keep new items
            merged_items = []
            for server_item in server_manifest.get("items", []):
                item_id = server_item.get("id")
                if item_id in dashboard_items:
                    # Item exists in dashboard: merge updates
                    dashboard_item = dashboard_items[item_id]
                    # Preserve server's metadata but update user actions
                    merged_item = server_item.copy()
                    merged_item["favorited"] = dashboard_item.get("favorited", False)
                    merged_item["rejected"] = dashboard_item.get("rejected", False)
                    merged_item["note"] = dashboard_item.get("note", "")
                    merged_items.append(merged_item)
                else:
                    # NEW item from server (generation added it): keep as-is
                    merged_items.append(server_item)
            
            # Update manifest
            manifest_data["items"] = merged_items
            
            # Preserve server's meta
            if "meta" in server_manifest:
                manifest_data["meta"] = server_manifest["meta"]

        # Save merged manifest
        os.makedirs(base_dir, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=4)

        return web.Response(status=200, text="Saved")

    except Exception as e:
        print(f"[ConfigTester] Error saving manifest: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))

# =============================================================================
# API: GET SESSION HTML
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/get_session_html")
async def get_session_html(request):
    """
    Dynamically generate HTML for a session.
    This allows the dashboard to load without triggering a workflow execution.
    """
    try:
        data = await request.json()
        session_name = data.get("session_name")
        node_id = data.get("node_id")

        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)

        if not session_name:
            return web.Response(status=400, text="Missing session_name")

        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        manifest_path = os.path.join(base_dir, "manifest.json")

        if not os.path.exists(manifest_path):
            return web.Response(status=404, text=f"Session '{session_name}' not found")

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Generate HTML on the fly
        html = get_html_template(session_name, manifest, node_id)
        return web.Response(status=200, text=html)

    except Exception as e:
        return web.Response(status=500, text=str(e))

# =============================================================================
# API: EXPORT FAVORITES
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/export_favorites")
async def export_favorites(request):
    """
    Export favorited images to a 'benchmark_favorites/{session_name}' folder.
    Optionally packs metadata into images for CivitAI uploads.
    Optionally organizes into subfolders by unique prompts.
    """
    try:
        data = await request.json()
        session_name = data.get("session_name")
        pack_metadata = data.get("pack_metadata", False)
        organize_by_prompt = data.get("organize_by_prompt", False)
        organize_by_lora = data.get("organize_by_lora", False)
        
        # Sanitize
        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)
        
        if not session_name:
            return web.Response(status=400, text="Missing session_name")
        
        # Paths
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        manifest_path = os.path.join(base_dir, "manifest.json")
        images_dir = os.path.join(base_dir, "images")
        
        # Load manifest
        if not os.path.exists(manifest_path):
            return web.Response(status=404, text=f"Session '{session_name}' not found")
        
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        # Filter favorited items
        favorited = [item for item in manifest.get("items", []) if item.get("favorited", False)]
        
        if not favorited:
            return web.Response(status=200, text="No favorited images to export")
        
        # Build prompt mapping if organizing by prompt
        prompt_to_folder = {}
        if organize_by_prompt:
            unique_prompts = []
            for item in favorited:
                prompt = item.get("positive") or manifest.get("meta", {}).get("positive", "")
                if prompt and prompt not in unique_prompts:
                    unique_prompts.append(prompt)
            
            # Create Prompt1, Prompt2, etc. mapping
            for idx, prompt in enumerate(unique_prompts, 1):
                prompt_to_folder[prompt] = f"Prompt{idx}"
            
            print(f"[Export] Organizing into {len(unique_prompts)} prompt folders")
        
        # Build lora mapping if organizing by lora
        lora_to_folder = {}
        if organize_by_lora:
            unique_loras = []
            for item in favorited:
                lora = item.get("lora_expanded") or manifest.get("meta", {}).get("lora", "")
                if lora and lora not in unique_loras:
                    unique_loras.append(lora)
            
            # Create Lora1, Lora2, etc. mapping
            for idx, lora in enumerate(unique_loras, 1):
                lora_to_folder[lora] = f"Loras{idx}"
            
            print(f"[Export] Organizing into {len(unique_loras)} lora folders")
        
        # Create base export directory
        export_base = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name, "favorites")
        os.makedirs(export_base, exist_ok=True)
        
        exported_count = 0
        
        for item in favorited:
            # Get source image path - handle both URL format and relative paths
            file_path = item.get("file", "")
            
            # Parse filename from URL format: /view?filename=img_123.webp&type=output&subfolder=benchmarks/Session/images
            if file_path.startswith("/view?"):
                # Extract filename from URL
                import urllib.parse
                parsed = urllib.parse.urlparse(file_path)
                params = urllib.parse.parse_qs(parsed.query)
                filename = params.get("filename", [""])[0]
            elif file_path.startswith("./images/"):
                # Relative path format
                filename = file_path[9:]  # Remove ./images/
            else:
                # Just use basename
                filename = os.path.basename(file_path)
            
            if not filename:
                print(f"[Export] Warning: Could not parse filename from: {file_path}")
                continue
            
            # Source path in benchmarks folder
            source_path = os.path.join(images_dir, filename)
            
            if not os.path.exists(source_path):
                print(f"[Export] Warning: Image not found: {source_path}")
                continue
            
            # Determine destination folder
            if organize_by_prompt and organize_by_lora:
                # Both options: create nested folders Prompt/Lora
                prompt = item.get("positive") or manifest.get("meta", {}).get("positive", "")
                lora = item.get("lora") or manifest.get("meta", {}).get("lora", "")
                prompt_folder = prompt_to_folder.get(prompt, "Unknown")
                lora_folder = lora_to_folder.get(lora, "Unknown")
                dest_dir = os.path.join(export_base, prompt_folder, lora_folder)
                os.makedirs(dest_dir, exist_ok=True)
            elif organize_by_prompt:
                prompt = item.get("positive") or manifest.get("meta", {}).get("positive", "")
                folder_name = prompt_to_folder.get(prompt, "Unknown")
                dest_dir = os.path.join(export_base, folder_name)
                os.makedirs(dest_dir, exist_ok=True)
            elif organize_by_lora:
                lora = item.get("lora") or manifest.get("meta", {}).get("lora", "")
                folder_name = lora_to_folder.get(lora, "Unknown")
                dest_dir = os.path.join(export_base, folder_name)
                os.makedirs(dest_dir, exist_ok=True)
            else:
                dest_dir = export_base
            
            # Destination path
            dest_filename = filename
            if pack_metadata:
                # Change extension to .png if packing metadata
                dest_filename = os.path.splitext(filename)[0] + '.png'
            
            dest_path = os.path.join(dest_dir, dest_filename)
            
            # Copy or pack metadata
            if pack_metadata:
                try:
                    pack_metadata_into_image(source_path, dest_path, item, manifest.get("meta", {}))
                    exported_count += 1
                except Exception as e:
                    print(f"[Export] Error packing metadata for {filename}: {e}")
                    # Fallback to simple copy
                    shutil.copy2(source_path, dest_path)
                    exported_count += 1
            else:
                shutil.copy2(source_path, dest_path)
                exported_count += 1
        
        result_msg = f"Exported {exported_count} favorited images to 'benchmarks/{session_name}/favorites/'"
        if organize_by_prompt and organize_by_lora:
            result_msg += f" (organized into {len(prompt_to_folder)} prompt folders with {len(lora_to_folder)} lora subfolders)"
        elif organize_by_prompt:
            result_msg += f" (organized into {len(prompt_to_folder)} prompt folders)"
        elif organize_by_lora:
            result_msg += f" (organized into {len(lora_to_folder)} lora folders)"
        if pack_metadata:
            result_msg += " (with metadata packed)"
        
        print(f"[ConfigTester] ✅ {result_msg}")
        return web.Response(status=200, text=result_msg)
        
    except Exception as e:
        print(f"[ConfigTester] Error exporting favorites: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))

# =============================================================================
# NODE MAPPINGS
# =============================================================================

NODE_CLASS_MAPPINGS = {
    "UltimateSamplerGrid": SamplerGridTester,
    "UltimateGridDashboard": SamplerConfigDashboardViewer,
    "UltimateConfigBuilder": UltimateConfigBuilder,
    "SmartJSONText": SmartJSONTextNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UltimateSamplerGrid": "Ultimate Sampler Grid (Generator)",
    "UltimateGridDashboard": "Ultimate Grid Dashboard (Viewer)",
    "UltimateConfigBuilder": "Ultimate Config Builder",
    "SmartJSONText": "Smart JSON Text",
}

WEB_DIRECTORY = "./web"