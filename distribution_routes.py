"""
Distribution API Routes
Endpoints for master (coordination) and worker (job processing) roles.
All routes registered via PromptServer decorators.
"""

import json
import os
import time
import uuid
import threading

import server
from aiohttp import web
from .network_utils import distribution_get, distribution_post_json


# =============================================================================
# GLOBAL STATE
# =============================================================================

# The active DistributionManager instance (set by generation_orchestrator when distribution is enabled)
_distribution_manager = None
_manager_lock = threading.Lock()

# The active WorkerThread instance (set when this instance acts as a worker)
_worker_thread = None
_worker_lock = threading.Lock()


def get_distribution_manager():
    """Get the current DistributionManager (master mode)."""
    with _manager_lock:
        return _distribution_manager


def set_distribution_manager(manager):
    """Set/clear the active DistributionManager (called by orchestrator)."""
    global _distribution_manager
    with _manager_lock:
        _distribution_manager = manager


def get_worker_thread():
    """Get the current WorkerThread (worker mode)."""
    with _worker_lock:
        return _worker_thread


def set_worker_thread(thread):
    """Set/clear the active WorkerThread."""
    global _worker_thread
    with _worker_lock:
        _worker_thread = thread


# =============================================================================
# MASTER ENDPOINTS - Job distribution coordination
# =============================================================================

@server.PromptServer.instance.routes.get("/distribution/claim_job")
async def claim_job(request):
    """
    Worker claims next pending job. Atomic operation.

    Query params:
        worker_id: Unique worker identifier

    Returns:
        200 + JSON job dict if job available
        204 if no pending jobs
        503 if distribution not active
    """
    manager = get_distribution_manager()
    if not manager or not manager.is_active:
        return web.Response(status=503, text="Distribution not active")

    worker_id = request.query.get("worker_id", "unknown")
    job = manager.claim_job(worker_id)

    if job is None:
        return web.Response(status=204)  # No content = no jobs left

    return web.json_response(job)


@server.PromptServer.instance.routes.post("/distribution/submit_result")
async def submit_result(request):
    """
    Worker submits completed image + metadata.

    Multipart form data:
        - 'metadata': JSON string with {job_id, meta}
        - 'image': image file bytes (webp)

    The master saves the image, updates manifest, and sends a dashboard update.
    This follows the same pattern as RemoteVAEDecodeWorker in remote_vae.py.
    """
    manager = get_distribution_manager()
    if not manager:
        return web.Response(status=503, text="Distribution not active")

    try:
        reader = await request.multipart()

        metadata_json = None
        image_data = None

        async for part in reader:
            if part.name == 'metadata':
                raw = await part.read()
                metadata_json = json.loads(raw.decode('utf-8'))
            elif part.name == 'image':
                image_data = await part.read()

        if not metadata_json or not image_data:
            return web.Response(status=400, text="Missing metadata or image")

        job_id = metadata_json.get("job_id")
        meta = metadata_json.get("meta")

        if not job_id or not meta:
            return web.Response(status=400, text="Missing job_id or meta in metadata")

        # Save image to session images folder
        paths = manager.paths
        session_name = manager.session_name

        # Ensure images directory exists (defensive - should already be created by orchestrator)
        os.makedirs(paths["images"], exist_ok=True)

        filename = f"img_{meta['id']}.webp"
        filepath = os.path.join(paths["images"], filename)

        with open(filepath, "wb") as f:
            f.write(image_data)

        # Update meta with ComfyUI-compatible file path
        meta["file"] = (
            f"/view?filename={filename}&type=output"
            f"&subfolder=benchmarks/{session_name}/images"
        )
        if "rejected" not in meta:
            meta["rejected"] = False

        # Mark job as completed in the distribution manager
        # complete_job returns False if already completed (double-submit guard)
        was_completed = manager.complete_job(job_id, meta)

        if not was_completed:
            # Job was already completed (duplicate submission after timeout+reclaim)
            # Clean up the duplicate image file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            # Track that this worker did real work (even though result was a duplicate)
            submit_worker_id = metadata_json.get("worker_id")
            if submit_worker_id:
                manager.record_late_submission(submit_worker_id)
                print(f"[Distribution] ℹ️ Late submission from worker {submit_worker_id} "
                      f"for job {job_id} (already completed, duplicate cleaned up)")
            return web.Response(status=200, text="Duplicate (ignored)")

        # Update manifest on disk (thread-safe)
        from .manifest_utils import save_manifest

        with manager._lock:
            manager.existing_data["items"].insert(0, meta)

        save_manifest(paths["manifest"], manager.existing_data)

        # Send dashboard update (same pattern as remote_vae.py and image_generation.py)
        try:
            manifest_meta = manager.existing_data.get("meta", {})
            server.PromptServer.instance.send_sync("ultimate_grid.update", {
                "node": manager.unique_id,
                "session_name": session_name,
                "new_items": [meta],
                "meta": manifest_meta
            })
        except Exception as e:
            print(f"[Distribution] ⚠️ Dashboard update failed: {e}")

        # Send distribution status update
        _send_distribution_status(manager)

        print(f"[Distribution] ✅ Result received for job {job_id} "
              f"from worker {metadata_json.get('worker_id', 'unknown')}")

        return web.Response(status=200, text="OK")

    except Exception as e:
        print(f"[Distribution] ❌ Error processing result: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))


@server.PromptServer.instance.routes.get("/distribution/status")
async def distribution_status(request):
    """
    Overall progress status.

    Returns JSON with:
        total, pending, claimed, completed, failed counts
        workers dict with per-worker stats
    """
    manager = get_distribution_manager()
    if not manager:
        return web.json_response({
            "active": False,
            "total": 0, "pending": 0, "claimed": 0,
            "completed": 0, "failed": 0, "workers": {}
        })

    status = manager.get_status()
    status["active"] = manager.is_active
    return web.json_response(status)


@server.PromptServer.instance.routes.post("/distribution/heartbeat")
async def heartbeat(request):
    """Worker heartbeat to prevent timeout."""
    manager = get_distribution_manager()
    if not manager:
        return web.Response(status=503, text="Distribution not active")

    try:
        data = await request.json()
        worker_id = data.get("worker_id")
        if worker_id:
            manager.heartbeat(worker_id)
        return web.Response(status=200)
    except Exception as e:
        return web.Response(status=400, text=str(e))


@server.PromptServer.instance.routes.post("/distribution/register_worker")
async def register_worker(request):
    """
    Worker self-registers with master.

    Request body:
        worker_id: Unique worker ID (optional, generated if missing)
        worker_url: Worker's base URL (for display only)

    Returns:
        worker_id and session_name
    """
    manager = get_distribution_manager()
    if not manager:
        return web.Response(status=503, text="Distribution not active")

    try:
        data = await request.json()
        worker_id = data.get("worker_id", str(uuid.uuid4())[:8])
        worker_url = data.get("worker_url", "")

        manager.register_worker(worker_id, worker_url)

        return web.json_response({
            "worker_id": worker_id,
            "session_name": manager.session_name
        })
    except Exception as e:
        return web.Response(status=500, text=str(e))


@server.PromptServer.instance.routes.post("/distribution/fail_job")
async def fail_job(request):
    """
    Worker reports job failure. Job will be re-queued (up to MAX_FAIL_COUNT).

    Request body:
        job_id: The failed job's ID
        error: Error description string
    """
    manager = get_distribution_manager()
    if not manager:
        return web.Response(status=503, text="Distribution not active")

    try:
        data = await request.json()
        job_id = data.get("job_id")
        error = data.get("error", "Unknown error")

        if not job_id:
            return web.Response(status=400, text="Missing job_id")

        manager.fail_job(job_id, error)

        # Send updated distribution status
        _send_distribution_status(manager)

        return web.Response(status=200, text="OK")
    except Exception as e:
        return web.Response(status=500, text=str(e))


# =============================================================================
# WORKER ENDPOINTS - Run on worker ComfyUI instances
# =============================================================================

@server.PromptServer.instance.routes.post("/distribution/start_worker")
async def start_worker(request):
    """
    Master tells this ComfyUI instance to start working as a distributed worker.

    Request body:
        master_url: Master's base URL (e.g., "http://192.168.1.1:8188")

    Returns:
        200 + {status, worker_id} on success
        409 if worker is already running
    """
    from .distribution_worker import WorkerThread

    print(f"[Distribution] 📥 start_worker endpoint called")

    existing = get_worker_thread()
    if existing and existing.is_alive():
        print(f"[Distribution] ℹ️ Worker already running: {existing.worker_id}")
        return web.json_response({
            "status": "already_running",
            "worker_id": existing.worker_id,
            "jobs_processed": existing.jobs_processed
        }, status=409)

    try:
        data = await request.json()
        master_url = data.get("master_url")
        print(f"[Distribution] 📥 master_url={master_url}")

        if not master_url:
            return web.Response(status=400, text="Missing master_url")

        thread = WorkerThread(master_url)
        # Pass sync models flag to worker
        thread._sync_models = data.get("sync_models_to_workers", False)
        set_worker_thread(thread)
        thread.start()

        return web.json_response({
            "status": "started",
            "worker_id": thread.worker_id
        })
    except Exception as e:
        return web.Response(status=500, text=str(e))


@server.PromptServer.instance.routes.get("/distribution/worker_status")
async def worker_status(request):
    """Check if this instance is running as a worker."""
    thread = get_worker_thread()
    if thread and thread.is_alive():
        return web.json_response({
            "status": "busy",
            "worker_id": thread.worker_id,
            "jobs_processed": thread.jobs_processed,
            "current_model": thread.current_model
        })
    return web.json_response({"status": "idle"})


@server.PromptServer.instance.routes.post("/distribution/stop_worker")
async def stop_worker(request):
    """Tell the worker to stop after completing its current job."""
    thread = get_worker_thread()
    if thread and thread.is_alive():
        thread.stop()
        return web.json_response({"status": "stopping"})
    return web.json_response({"status": "not_running"})


# =============================================================================
# PROXY ENDPOINT - Avoids CORS when browser tests worker connections
# =============================================================================

@server.PromptServer.instance.routes.post("/distribution/test_worker")
async def test_worker_connection(request):
    """
    Proxy endpoint for the Config Builder UI to test if a remote worker is reachable.
    The browser cannot fetch cross-origin worker URLs directly (CORS), so this
    server-side route makes the request on behalf of the frontend.

    Request body:
        worker_url: The worker's base URL to test (e.g., "http://192.168.1.10:8188")

    Returns:
        200 + JSON with worker status on success
        200 + JSON with error info on failure (so the UI always gets a parseable response)
    """
    try:
        data = await request.json()
        worker_url = data.get("worker_url", "").strip().rstrip("/")

        if not worker_url:
            return web.json_response({"reachable": False, "error": "Empty URL"})

        status, resp_data = distribution_get(
            f"{worker_url}/distribution/worker_status",
            timeout=5
        )
        result = json.loads(resp_data.decode("utf-8"))
        return web.json_response({
            "reachable": True,
            "status": result.get("status", "unknown"),
            "worker_id": result.get("worker_id", ""),
            "jobs_processed": result.get("jobs_processed", 0)
        })

    except Exception as e:
        error_msg = f"HTTP {e.code}" if hasattr(e, 'code') else str(e)
        return web.json_response({
            "reachable": False,
            "error": error_msg
        })


# =============================================================================
# MODEL SYNC ENDPOINTS
# =============================================================================

@server.PromptServer.instance.routes.post("/distribution/check_models")
async def check_models(request):
    """
    Bulk check which model files exist on this instance.
    Workers call this to find out what they need to download.

    Request body:
        worker_id: Registered worker ID
        models: List of {category, filename} dicts

    Returns:
        available: List of {category, filename, size_bytes} for files that exist
        total_size: Total bytes of all available files
    """
    try:
        data = await request.json()
        worker_id = data.get("worker_id", "")
        models = data.get("models", [])

        import folder_paths

        available = []
        total_size = 0
        for m in models:
            category = m.get("category", "")
            filename = m.get("filename", "")
            if not category or not filename:
                continue

            full_path = folder_paths.get_full_path(category, filename)
            if full_path and os.path.exists(full_path):
                size = os.path.getsize(full_path)
                available.append({
                    "category": category,
                    "filename": filename,
                    "size_bytes": size
                })
                total_size += size

        print(f"[Distribution] 📋 Model check from worker {worker_id}: {len(models)} requested, {len(available)} available ({total_size / (1024**3):.2f} GB)")
        return web.json_response({
            "available": available,
            "total_size": total_size
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@server.PromptServer.instance.routes.post("/distribution/download_model")
async def download_model(request):
    """
    Stream a model file to a worker.

    Request body:
        worker_id: Registered worker ID
        category: Model category (checkpoints, loras, vae, etc.)
        filename: Relative path including subdirectories

    Returns:
        Streaming file response with Content-Length header
    """
    try:
        data = await request.json()
        worker_id = data.get("worker_id", "")
        category = data.get("category", "")
        filename = data.get("filename", "")

        if not category or not filename:
            return web.Response(status=400, text="Missing category or filename")

        import folder_paths
        full_path = folder_paths.get_full_path(category, filename)

        if not full_path or not os.path.exists(full_path):
            return web.Response(status=404, text=f"File not found: {category}/{filename}")

        file_size = os.path.getsize(full_path)
        print(f"[Distribution] 📤 Serving {category}/{filename} ({file_size / (1024**3):.2f} GB) to worker {worker_id}")

        response = web.StreamResponse()
        response.content_type = "application/octet-stream"
        response.content_length = file_size
        response.headers["X-Filename"] = filename
        response.headers["X-Category"] = category
        await response.prepare(request)

        chunk_size = 8 * 1024 * 1024  # 8 MB chunks
        with open(full_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                await response.write(chunk)

        await response.write_eof()
        print(f"[Distribution] ✅ Finished serving {category}/{filename} to worker {worker_id}")
        return response
    except Exception as e:
        print(f"[Distribution] ❌ Error serving model: {e}")
        return web.Response(status=500, text=str(e))


# =============================================================================
# HELPERS
# =============================================================================

def _send_distribution_status(manager):
    """Send distribution status update to the dashboard."""
    try:
        status = manager.get_status()
        status["active"] = manager.is_active
        server.PromptServer.instance.send_sync("ultimate_grid.distribution_status", {
            "node": manager.unique_id,
            "session_name": manager.session_name,
            **status
        })
    except Exception:
        pass


def notify_workers_to_start(worker_urls, master_url, session_name, sync_models_to_workers=False):
    """
    Notify remote worker ComfyUI instances to start processing.
    Sends POST /distribution/start_worker to each worker URL.

    Uses network_utils.py gateway for all outbound requests.

    Args:
        worker_urls: List of worker base URLs
        master_url: This master's base URL
        session_name: Current session name
        sync_models_to_workers: Whether workers should download missing models from master

    Returns:
        List of (url, success, message) tuples
    """
    results = []

    for url in worker_urls:
        url = url.strip().rstrip("/")
        if not url:
            continue

        try:
            status, resp_data = distribution_post_json(
                f"{url}/distribution/start_worker",
                {
                    "master_url": master_url,
                    "session_name": session_name,
                    "sync_models_to_workers": sync_models_to_workers
                },
                timeout=10
            )
            result = json.loads(resp_data.decode("utf-8"))
            worker_id = result.get("worker_id", "unknown")
            print(f"[Distribution] ✅ Worker started at {url} (id: {worker_id})")
            results.append((url, True, f"Started (id: {worker_id})"))

        except Exception as e:
            if hasattr(e, 'code') and e.code == 409:
                print(f"[Distribution] ℹ️ Worker at {url} already running")
                results.append((url, True, "Already running"))
            elif hasattr(e, 'code'):
                print(f"[Distribution] ❌ Failed to start worker at {url}: HTTP {e.code}")
                results.append((url, False, f"HTTP {e.code}"))
            else:
                print(f"[Distribution] ❌ Failed to contact worker at {url}: {e}")
                results.append((url, False, str(e)))

    return results


def stop_all_workers(worker_urls):
    """
    Tell all remote workers to stop.

    Args:
        worker_urls: List of worker base URLs
    """
    for url in worker_urls:
        url = url.strip().rstrip("/")
        if not url:
            continue

        try:
            distribution_post_json(
                f"{url}/distribution/stop_worker",
                {},
                timeout=5
            )
            print(f"[Distribution] 🛑 Stopped worker at {url}")
        except Exception:
            pass
