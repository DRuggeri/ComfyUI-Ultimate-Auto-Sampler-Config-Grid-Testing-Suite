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

# --- API: DELETE SESSION ---
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

# --- API: SAVE CHANGES (Optimized - Only Changed Items) ---
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
    
# --- API: SAVE MANIFEST (Legacy - Full Save) ---
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
        os.makedirs(base_dir, exist_ok=True)
        manifest_path = os.path.join(base_dir, "manifest.json")

        # CRITICAL FIX: Merge with disk version to preserve generation's new items
        try:
            if os.path.exists(manifest_path):
                # Load what's currently on disk (may have new items from generation)
                with open(manifest_path, "r") as f:
                    disk_manifest = json.load(f)
                
                # Create lookup of dashboard items by ID
                dashboard_items_dict = {
                    item.get("id"): item 
                    for item in manifest_data.get("items", []) 
                    if "id" in item
                }
                
                # Find items on disk that aren't in dashboard (newly generated)
                new_items = []
                for disk_item in disk_manifest.get("items", []):
                    item_id = disk_item.get("id")
                    if item_id and item_id not in dashboard_items_dict:
                        # This item was generated after dashboard loaded
                        new_items.append(disk_item)
                
                # Add new items to dashboard's manifest
                if new_items:
                    print(f"[ConfigTester] 📄 Preserving {len(new_items)} newly generated items not in dashboard")
                    manifest_data["items"] = new_items + manifest_data.get("items", [])
                
                # Preserve meta from disk (has latest settings)
                if "meta" in disk_manifest:
                    # Keep user's changes but preserve generation settings
                    manifest_data["meta"] = disk_manifest["meta"]
                    
        except Exception as e:
            print(f"[ConfigTester] ⚠️ Could not merge with disk manifest: {e}")
            # Continue with save anyway - dashboard data is more important than merge

        # Save the merged manifest
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=4)
            
        print("Save Manifest at init")
        return web.Response(status=200, text="Saved")
    except Exception as e:
        print(f"[ConfigTester] Error saving manifest: {e}")
        return web.Response(status=500, text=str(e))

# --- API: FETCH SESSION HTML ---
@server.PromptServer.instance.routes.post("/config_tester/get_session_html")
async def get_session_html(request):
    try:
        data = await request.json()
        session_name = data.get("session_name")
        node_id = data.get("node_id", "0") # Fallback ID

        # --- sanitize ---
        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)
            
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)
        manifest_path = os.path.join(base_dir, "manifest.json")

        if not os.path.exists(manifest_path):
             return web.Response(status=404, text=f"Session '{session_name}' not found.")

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Generate HTML on the fly
        html = get_html_template(session_name, manifest, node_id)
        return web.Response(status=200, text=html)

    except Exception as e:
        return web.Response(status=500, text=str(e))

# --- API: EXPORT FAVORITES ---
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
            if organize_by_prompt:
                prompt = item.get("positive") or manifest.get("meta", {}).get("positive", "")
                folder_name = prompt_to_folder.get(prompt, "Unknown")
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
        if organize_by_prompt:
            result_msg += f" (organized into {len(prompt_to_folder)} prompt folders)"
        if pack_metadata:
            result_msg += " (with metadata packed)"
        
        print(f"[ConfigTester] ✅ {result_msg}")
        return web.Response(status=200, text=result_msg)
        
    except Exception as e:
        print(f"[ConfigTester] Error exporting favorites: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))

# --- MAPPINGS ---
NODE_CLASS_MAPPINGS = {
    "UltimateSamplerGrid": SamplerGridTester,
    "UltimateGridDashboard": SamplerConfigDashboardViewer,
    "UltimateConfigBuilder": UltimateConfigBuilder,
    "SmartJSONText": SmartJSONTextNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UltimateSamplerGrid": "Ultimate Sampler Grid (Generator)",
    "UltimateGridDashboard": "Ultimate Grid Dashboard (Viewer)",
    "UltimateConfigBuilder": "Ultimate Config Builder (WIP)",
    "SmartJSONText": "Smart JSON Text",
}

WEB_DIRECTORY = "./web"