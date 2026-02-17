import re
import asyncio
import server
from aiohttp import web
import json
import os
import urllib.parse
import folder_paths
import shutil
from .sampler_node import SamplerGridTester
from .dashboard_node import SamplerConfigDashboardViewer
from .html_generator import get_html_template
from .config_builder_node import UltimateConfigBuilder
from .json_text_node import SmartJSONTextNode
from .metadata_packer import pack_metadata_into_image
from .directory_scanner import scan_directory_for_images


# --- PATH SECURITY HELPERS ---
def _get_benchmarks_base():
    """Return the canonical benchmarks base directory."""
    return os.path.realpath(os.path.join(folder_paths.get_output_directory(), "benchmarks"))

def _is_path_within(path, base):
    """Check that *path* is contained within *base* after resolving symlinks."""
    real_path = os.path.realpath(path)
    real_base = os.path.realpath(base)
    return real_path == real_base or real_path.startswith(real_base + os.sep)


# --- CONFIG MANAGEMENT PATH ---
CONFIGS_DIR = os.path.join(folder_paths.get_output_directory(), "ultimate-configs")
os.makedirs(CONFIGS_DIR, exist_ok=True)


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
            
        # Sanitize: strip to basename to prevent directory traversal
        filename = os.path.basename(filename)
        filepath = os.path.join(CONFIGS_DIR, filename)

        if not _is_path_within(filepath, CONFIGS_DIR):
            return web.Response(status=403, text="Forbidden")

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

        if not _is_path_within(filepath, CONFIGS_DIR):
            return web.Response(status=403, text="Forbidden")

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

        # Path construction with containment check
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.Response(status=403, text="Forbidden: path outside benchmarks directory")

        if os.path.exists(base_dir):
            shutil.rmtree(base_dir)
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

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.Response(status=403, text="Forbidden: path outside benchmarks directory")

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

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.Response(status=403, text="Forbidden: path outside benchmarks directory")

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

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.Response(status=403, text="Forbidden: path outside benchmarks directory")

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

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.Response(status=403, text="Forbidden: path outside benchmarks directory")

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
                # Extract filename and subfolder from URL
                parsed_url = urllib.parse.urlparse(file_path)
                url_params = urllib.parse.parse_qs(parsed_url.query)
                filename = url_params.get("filename", [""])[0]
                subfolder = url_params.get("subfolder", [""])[0]
                if subfolder:
                    source_path = os.path.join(folder_paths.get_output_directory(), subfolder, filename)
                else:
                    source_path = os.path.join(images_dir, filename)
            elif file_path.startswith("./images/"):
                # Relative path format
                filename = file_path[9:]  # Remove ./images/
                source_path = os.path.join(images_dir, filename)
            else:
                # Just use basename
                filename = os.path.basename(file_path)
                source_path = os.path.join(images_dir, filename)

            if not filename:
                print(f"[Export] Warning: Could not parse filename from: {file_path}")
                continue
            
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
# API: SCAN EXTERNAL DIRECTORY
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/scan_directory")
async def scan_directory_route(request):
    """
    Scan an external directory for images, extract PNG metadata,
    and generate a manifest compatible with the dashboard.
    Creates symlinks in the output directory so ComfyUI's built-in
    /view endpoint can serve the images (no custom file serving needed).
    """
    try:
        data = await request.json()
        directory_path = data.get("directory_path", "").strip()
        session_name = data.get("session_name", "").strip()

        if not directory_path:
            return web.json_response({"error": "Missing directory_path"}, status=400)

        # Normalize path
        directory_path = os.path.normpath(directory_path)

        if not os.path.isabs(directory_path):
            return web.json_response({"error": "Path must be absolute"}, status=400)

        if not os.path.isdir(directory_path):
            return web.json_response({"error": f"Directory not found: {directory_path}"}, status=404)

        # Auto-generate session name from directory if not provided
        if not session_name:
            dir_basename = os.path.basename(directory_path)
            session_name = "scan-" + re.sub(r'[^\w\-]', '', dir_basename)

        # Sanitize session name
        session_name = re.sub(r'[^\w\-]', '', session_name)
        if not session_name:
            session_name = "scan-unnamed"

        print(f"[DirScanner] Scanning directory: {directory_path}")
        print(f"[DirScanner] Session name: {session_name}")

        # Prepare the symlink directory within the output folder
        # so ComfyUI's built-in /view endpoint can serve the images
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.json_response({"error": "Forbidden: path outside benchmarks directory"}, status=403)

        link_dir = os.path.join(base_dir, "external_images")
        os.makedirs(link_dir, exist_ok=True)

        # The subfolder path for /view URLs (relative to output dir)
        view_subfolder = f"benchmarks/{session_name}/external_images"

        # Run the scan in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        items, stats = await loop.run_in_executor(
            None, scan_directory_for_images, directory_path, 5000, view_subfolder
        )

        from_manifest = stats.get("from_manifest", 0)
        manifest_info = f", {from_manifest} from existing manifest" if from_manifest > 0 else ""
        print(f"[DirScanner] Found {stats['total']} images ({stats['with_metadata']} with metadata, {stats['skipped']} skipped{manifest_info})")

        # Create symlinks (or copy on Windows if symlinks not available)
        # for each image so /view can serve them
        _create_image_links(directory_path, link_dir, items)

        # Build manifest
        manifest = {
            "session_name": session_name,
            "items": items,
            "meta": {
                "source_directory": directory_path,
                "scan_type": "directory",
                "total_scanned": stats["total"],
                "with_metadata": stats["with_metadata"],
            }
        }

        # Save manifest to benchmarks session directory
        manifest_path = os.path.join(base_dir, "manifest.json")

        # If manifest already exists, preserve user tags (favorited/rejected/notes)
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    old_manifest = json.load(f)
                # Build lookup of old items by source_file for tag preservation
                old_by_source = {}
                for old_item in old_manifest.get("items", []):
                    src = old_item.get("source_file")
                    if src:
                        old_by_source[src] = old_item
                # Merge user tags into new items
                for item in items:
                    src = item.get("source_file")
                    if src and src in old_by_source:
                        old = old_by_source[src]
                        item["favorited"] = old.get("favorited", False)
                        item["rejected"] = old.get("rejected", False)
                        if old.get("notes"):
                            item["notes"] = old["notes"]
            except Exception as e:
                print(f"[DirScanner] Warning: Could not merge old tags: {e}")

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"[DirScanner] Created image links in: {link_dir}")

        from_manifest = stats.get("from_manifest", 0)
        return web.json_response({
            "session_name": session_name,
            "item_count": len(items),
            "with_metadata": stats["with_metadata"],
            "without_metadata": len(items) - stats["with_metadata"],
            "skipped": stats["skipped"],
            "from_manifest": from_manifest,
        })

    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        print(f"[DirScanner] Error: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"error": str(e)}, status=500)


def _create_image_links(source_dir, link_dir, items):
    """
    Create symlinks (or copies on Windows) from source images into
    the output directory so ComfyUI's built-in /view endpoint can serve them.
    """
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

    # Collect all source files referenced by items
    filenames = set()
    for item in items:
        src = item.get("source_file")
        if src:
            filenames.add(src)

    # Scan source directory and subdirectories for matching files
    scan_dirs = [source_dir]
    images_subdir = os.path.join(source_dir, "images")
    if os.path.isdir(images_subdir):
        scan_dirs.append(images_subdir)

    for scan_dir in scan_dirs:
        try:
            for entry in os.scandir(scan_dir):
                if not entry.is_file():
                    continue
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue
                if entry.name not in filenames:
                    continue

                link_path = os.path.join(link_dir, entry.name)
                if os.path.exists(link_path):
                    continue

                try:
                    os.symlink(entry.path, link_path)
                except (OSError, NotImplementedError):
                    # Windows may need admin privileges for symlinks; fall back to copy
                    shutil.copy2(entry.path, link_path)
        except PermissionError:
            print(f"[DirScanner] Warning: Permission denied scanning {scan_dir}")


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