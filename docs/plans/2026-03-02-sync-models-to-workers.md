# Sync Models to Workers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional HTTP-based model file transfer from master to workers, with intelligent background pre-fetching and permanent local storage.

**Architecture:** Master exposes two new endpoints for model file checking and streaming. Workers check for missing models before each job, download what's needed, and pre-fetch upcoming models in the background. A new UI checkbox enables the feature. The `sync_models_to_workers` flag flows through `distribution_config` JSON from Config Builder to orchestrator to manager to worker.

**Tech Stack:** Python (aiohttp server routes, threading, urllib), Vanilla JS (ComfyUI widget), ComfyUI `folder_paths` API

**Critical Constraint:** DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

## Task 1: UI Checkbox + Config Passthrough

Add the "Sync Models to Workers" checkbox in Distribution Settings and pass
the flag through the config pipeline.

**Files:**
- Modify: `web/conf_builder/conf-builder-distribution.js:393-416`
- Modify: `config_builder_node.py:662-670`

**Step 1: Add checkbox to Distribution Settings UI**

In `web/conf_builder/conf-builder-distribution.js`, find the Master Text
Encoding info text block at lines ~393-416. After the `encodingInfo` div
(around line 416), add a new checkbox following the exact same pattern:

```javascript
    // Sync Models to Workers toggle
    const syncRow = document.createElement("div");
    syncRow.style.cssText = "display: flex; align-items: flex-start; gap: 10px; margin-top: 10px;";

    const syncLabel = document.createElement("label");
    syncLabel.className = "cb-toggle";
    syncLabel.style.fontSize = "12px";
    const syncCheckbox = document.createElement("input");
    syncCheckbox.type = "checkbox";
    syncCheckbox.checked = node.state.sync_models_to_workers || false;
    syncCheckbox.onchange = () => {
        node.state.sync_models_to_workers = syncCheckbox.checked;
        node.saveState();
    };
    syncLabel.appendChild(syncCheckbox);
    syncLabel.appendChild(document.createTextNode(" ☁️ Sync Models to Workers"));
    syncRow.appendChild(syncLabel);
    detailsContainer.appendChild(syncRow);

    const syncInfo = document.createElement("div");
    syncInfo.style.cssText = "font-size: 10px; color: #666; margin-top: 4px; line-height: 1.3; padding-left: 2px;";
    syncInfo.textContent = "Automatically transfer required models, LoRAs, text encoders, "
        + "and VAEs to workers via HTTP. Files are saved permanently to each worker's "
        + "ComfyUI models folder, matching the master's directory structure.";
    detailsContainer.appendChild(syncInfo);
```

**Step 2: Add flag to distribution_config JSON output**

In `config_builder_node.py`, find the dist_config JSON assembly at line ~665-670:

```python
            dist_config = json.dumps({
                "enabled": True,
                "worker_urls": [u for u in state["worker_urls"] if u and u.strip()],
                "claim_timeout": state.get("claim_timeout", 600),
                "use_master_encoding": state.get("use_master_encoding", False)
            })
```

Add the new field:

```python
            dist_config = json.dumps({
                "enabled": True,
                "worker_urls": [u for u in state["worker_urls"] if u and u.strip()],
                "claim_timeout": state.get("claim_timeout", 600),
                "use_master_encoding": state.get("use_master_encoding", False),
                "sync_models_to_workers": state.get("sync_models_to_workers", False)
            })
```

**Step 3: Commit**

```bash
git add web/conf_builder/conf-builder-distribution.js config_builder_node.py
git commit -m "Add Sync Models to Workers checkbox and config passthrough

New toggle in Distribution Settings section. Flag flows through
distribution_config JSON as sync_models_to_workers boolean."
```

---

## Task 2: Master File Server Endpoints

Add two new endpoints on the master for model file checking and streaming.

**Files:**
- Modify: `distribution_routes.py` (add after line ~400, after existing endpoints)

**Step 1: Add /distribution/check_models endpoint**

In `distribution_routes.py`, after the last endpoint (around line 400+),
add the `check_models` endpoint. This uses `folder_paths` to resolve each
file and returns which ones exist with their sizes:

```python
@server.PromptServer.instance.routes.post("/distribution/check_models")
async def check_models(request):
    """
    Bulk check which model files exist on this instance.
    Workers call this to find out what they need to download.

    Request body:
        worker_id: Registered worker ID
        models: List of {category, filename} dicts

    Returns:
        missing: List of {category, filename, size_bytes} for files that exist here
        total_size: Total bytes of all files in the list
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

        return web.json_response({
            "available": available,
            "total_size": total_size
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
```

**Step 2: Add /distribution/download_model endpoint**

Add the streaming file download endpoint right after `check_models`:

```python
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
```

**Step 3: Commit**

```bash
git add distribution_routes.py
git commit -m "Add master file server endpoints for model sync

POST /distribution/check_models - bulk check which models exist
POST /distribution/download_model - stream model file to worker
Both endpoints use folder_paths for path resolution."
```

---

## Task 3: Worker Model Sync — Download Helper

Add a helper method to the WorkerThread that downloads a single model file
from the master, preserving directory structure.

**Files:**
- Modify: `distribution_worker.py:40-60` (add to WorkerThread class)

**Step 1: Add sync_models flag and download helper**

In `distribution_worker.py`, in the `WorkerThread.__init__` method (around
line 40-60), add the sync flag after `self._incompatible_loras`:

```python
        self._sync_models = False  # Set by master when sync_models_to_workers enabled
        self._prefetch_thread = None
        self._prefetch_queue = []  # List of {category, filename} to pre-fetch
        self._prefetch_lock = threading.Lock()
```

Then add the download helper methods to the WorkerThread class. Find a good
location (after `__init__` but before `run()`). Add:

```python
    def _download_model_from_master(self, category, filename):
        """
        Download a single model file from the master instance.
        Preserves full subdirectory structure.

        Args:
            category: Model category (checkpoints, loras, vae, etc.)
            filename: Relative path including subdirs (e.g. SDXL/Illustrious/model.safetensors)

        Returns:
            str: Local path where file was saved, or None on failure
        """
        import folder_paths
        import json

        # Determine target directory
        # folder_paths stores base directories per category
        base_dirs = folder_paths.get_folder_paths(category)
        if not base_dirs:
            print(f"[Worker {self.worker_id}] ❌ Unknown model category: {category}")
            return None
        target_dir = base_dirs[0]  # Use first (primary) directory
        target_path = os.path.join(target_dir, filename.replace("/", os.sep))

        # Skip if already exists
        if os.path.exists(target_path):
            return target_path

        # Create subdirectories
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # Download from master
        url = f"{self.master_url}/distribution/download_model"
        payload = json.dumps({
            "worker_id": self.worker_id,
            "category": category,
            "filename": filename
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            print(f"[Worker {self.worker_id}] ⬇️ Downloading {category}/{filename}...")
            with urllib.request.urlopen(req, timeout=3600) as resp:
                file_size = int(resp.headers.get("Content-Length", 0))
                if file_size > 0:
                    size_str = f"{file_size / (1024**3):.2f} GB" if file_size > 1024**3 else f"{file_size / (1024**2):.0f} MB"
                    print(f"[Worker {self.worker_id}] ⬇️ Size: {size_str}")

                # Stream to temp file, then rename (atomic-ish)
                temp_path = target_path + ".downloading"
                downloaded = 0
                last_progress = 0
                with open(temp_path, "wb") as f:
                    while True:
                        chunk = resp.read(8 * 1024 * 1024)  # 8 MB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if file_size > 0:
                            progress = int(downloaded / file_size * 100)
                            if progress >= last_progress + 10:
                                print(f"[Worker {self.worker_id}] ⬇️ {category}/{filename}: {progress}%")
                                last_progress = progress

                os.replace(temp_path, target_path)
                print(f"[Worker {self.worker_id}] ✅ Downloaded {category}/{filename}")
                return target_path

        except Exception as e:
            print(f"[Worker {self.worker_id}] ❌ Failed to download {category}/{filename}: {e}")
            # Clean up partial download
            temp_path = target_path + ".downloading"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None

    def _extract_required_models(self, config):
        """
        Extract all model file references from a job config.

        Returns:
            List of {category, filename} dicts
        """
        models = []

        # Main model/checkpoint
        model_name = config.get("model", "None")
        if model_name and model_name != "None":
            model_type = config.get("model_type", "checkpoint")
            if model_type == "checkpoint":
                category = "checkpoints"
            elif model_type == "gguf":
                category = "unet_gguf"
            elif model_type == "diffusion_model":
                category = "diffusion_models"
            else:
                category = "checkpoints"
            models.append({"category": category, "filename": model_name})

        # LoRA
        lora = config.get("lora_expanded", config.get("lora", "None"))
        if lora and lora != "None":
            models.append({"category": "loras", "filename": lora})

        # VAE (skip remote URLs and "Default")
        vae = config.get("vae", "Default")
        if vae and vae != "Default" and not vae.startswith("remote:"):
            models.append({"category": "vae", "filename": vae})

        # Text encoders
        text_encoders = config.get("text_encoders", [])
        for te in text_encoders:
            if te and te != "None":
                models.append({"category": "text_encoders", "filename": te})

        return models

    def _ensure_models_available(self, config):
        """
        Check all required models exist locally, download missing ones from master.
        Blocks until all models are available.
        """
        import folder_paths

        required = self._extract_required_models(config)
        if not required:
            return

        missing = []
        for m in required:
            path = folder_paths.get_full_path(m["category"], m["filename"])
            if path is None:
                missing.append(m)

        if not missing:
            return

        print(f"[Worker {self.worker_id}] 📦 Missing {len(missing)} model(s), downloading from master...")
        for m in missing:
            result = self._download_model_from_master(m["category"], m["filename"])
            if result is None:
                raise RuntimeError(
                    f"Failed to download required model: {m['category']}/{m['filename']}. "
                    f"Check that the file exists on the master instance."
                )
```

**Step 2: Commit**

```bash
git add distribution_worker.py
git commit -m "Add worker model download helpers

_download_model_from_master streams files from master via HTTP.
_extract_required_models parses job config for all model references.
_ensure_models_available checks local paths and downloads missing."
```

---

## Task 4: Wire Sync Into Worker Job Processing

Call `_ensure_models_available()` before `_process_job()` when sync is enabled.
Also add background pre-fetch thread for upcoming models.

**Files:**
- Modify: `distribution_worker.py` (run loop and _process_job)

**Step 1: Set sync flag from master's start_worker call**

In `distribution_routes.py`, find the `/distribution/start_worker` handler
(line ~305). The request body is sent by the master when starting workers.
Find where `WorkerThread` is instantiated. After creating the thread, set
the sync flag. The master passes `sync_models_to_workers` in the start request.

Find the start_worker handler and read its implementation to see how the
WorkerThread is created. Then add:

```python
        # Pass sync models flag to worker
        worker_thread._sync_models = data.get("sync_models_to_workers", False)
```

**Step 2: Add sync check before _process_job in worker run loop**

In `distribution_worker.py`, find the main run loop where `_process_job(job)`
is called. It's inside the `run()` method. Find the call to `_process_job`
and add the sync check just before it:

```python
                # Sync missing models from master if enabled
                if self._sync_models:
                    self._ensure_models_available(job["config"])
```

**Step 3: Add background pre-fetch logic**

In `distribution_worker.py`, add a pre-fetch method and start it after
claiming a job:

```python
    def _start_prefetch(self, upcoming_models):
        """Start background thread to pre-fetch upcoming models."""
        if not upcoming_models:
            return

        with self._prefetch_lock:
            self._prefetch_queue = list(upcoming_models)

        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return  # Already running

        def _prefetch_worker():
            while True:
                with self._prefetch_lock:
                    if not self._prefetch_queue:
                        break
                    model = self._prefetch_queue.pop(0)
                try:
                    self._download_model_from_master(model["category"], model["filename"])
                except Exception as e:
                    print(f"[Worker {self.worker_id}] ⚠️ Pre-fetch failed: {e}")

        self._prefetch_thread = threading.Thread(target=_prefetch_worker, daemon=True)
        self._prefetch_thread.start()
```

In the run loop, after claiming a job and before processing, start pre-fetch:

```python
                # Start background pre-fetch for upcoming models
                if self._sync_models and job.get("upcoming_models"):
                    self._start_prefetch(job["upcoming_models"])
```

**Step 4: Pass sync flag when master starts workers**

In `generation_orchestrator.py`, find where workers are started (search for
`/distribution/start_worker`). Add `sync_models_to_workers` to the request
payload sent to each worker.

**Step 5: Commit**

```bash
git add distribution_worker.py distribution_routes.py generation_orchestrator.py
git commit -m "Wire model sync into worker job processing

Workers check for missing models before processing when sync enabled.
Background pre-fetch thread downloads upcoming models during job execution.
Master passes sync flag to workers via start_worker request."
```

---

## Task 5: Upcoming Models in Job Claim Response

Modify the distribution manager to include upcoming model references in
job claim responses when sync is enabled.

**Files:**
- Modify: `distribution_manager.py:162-184` (claim_job)
- Modify: `distribution_manager.py:518-549` (_job_to_dict)

**Step 1: Add sync flag to distribution manager**

In `distribution_manager.py`, find the `__init__` method and add:

```python
        self.sync_models_to_workers = False
```

**Step 2: Add upcoming models extraction helper**

Add a method to the DistributionManager class:

```python
    def _get_upcoming_models(self, exclude_job_id=None, limit=10):
        """
        Scan pending jobs and collect unique model references for pre-fetching.
        Returns list of {category, filename} dicts.
        """
        seen = set()
        upcoming = []

        for job_id in self._pending_queue:
            if job_id == exclude_job_id:
                continue
            job = self._jobs.get(job_id)
            if not job:
                continue

            config = job.config
            # Extract models from config (same logic as worker)
            model_name = config.get("model", "None")
            if model_name and model_name != "None":
                model_type = config.get("model_type", "checkpoint")
                if model_type == "checkpoint":
                    cat = "checkpoints"
                elif model_type == "gguf":
                    cat = "unet_gguf"
                elif model_type == "diffusion_model":
                    cat = "diffusion_models"
                else:
                    cat = "checkpoints"
                key = f"{cat}:{model_name}"
                if key not in seen:
                    seen.add(key)
                    upcoming.append({"category": cat, "filename": model_name})

            lora = config.get("lora_expanded", config.get("lora", "None"))
            if lora and lora != "None":
                key = f"loras:{lora}"
                if key not in seen:
                    seen.add(key)
                    upcoming.append({"category": "loras", "filename": lora})

            vae = config.get("vae", "Default")
            if vae and vae != "Default" and not vae.startswith("remote:"):
                key = f"vae:{vae}"
                if key not in seen:
                    seen.add(key)
                    upcoming.append({"category": "vae", "filename": vae})

            text_encoders = config.get("text_encoders", [])
            for te in text_encoders:
                if te and te != "None":
                    key = f"text_encoders:{te}"
                    if key not in seen:
                        seen.add(key)
                        upcoming.append({"category": "text_encoders", "filename": te})

            if len(upcoming) >= limit:
                break

        return upcoming
```

**Step 3: Add upcoming_models to _job_to_dict**

In `_job_to_dict()` (line ~518-549), find the return at the end. Before
`return result`, add:

```python
        # Attach upcoming models list if sync is enabled (for pre-fetching)
        if self.sync_models_to_workers:
            result["upcoming_models"] = self._get_upcoming_models(
                exclude_job_id=job.job_id, limit=10
            )
```

**Step 4: Set flag from orchestrator**

In `generation_orchestrator.py`, find where the distribution manager is
created or configured (search for `sync_models` or where `use_master_encoding`
is read at line ~1532). After the `use_master_encoding` line, add:

```python
        sync_models = distribution_config.get("sync_models_to_workers", False)
        if sync_models:
            manager.sync_models_to_workers = True
            print(f"[Distribution] ☁️ Model sync enabled — workers will download missing models from master")
```

**Step 5: Commit**

```bash
git add distribution_manager.py generation_orchestrator.py
git commit -m "Add upcoming models to job claim response

Distribution manager scans pending queue for unique model references.
When sync_models_to_workers is enabled, job claim responses include
upcoming_models list for worker background pre-fetching."
```

---

## Verification Checklist

After all tasks are complete, verify each piece:

1. **UI checkbox:** Open Builder UI → Distribution Settings → verify "Sync
   Models to Workers" toggle appears below Master Text Encoding
2. **Config passthrough:** Enable the toggle, check JSON Preview — verify
   `sync_models_to_workers: true` appears in distribution_config
3. **Master endpoints:** Start ComfyUI, test endpoints with curl:
   - `curl -X POST http://localhost:8188/distribution/check_models -H "Content-Type: application/json" -d '{"worker_id":"test","models":[{"category":"checkpoints","filename":"v1-5-pruned-emaonly.safetensors"}]}'`
   - Verify it returns file size for models that exist
4. **Worker sync:** With two ComfyUI instances, enable sync, run a grid test
   with a model the worker doesn't have — verify it downloads and processes
5. **Pre-fetch:** Verify worker logs show background downloads for upcoming
   models while current job processes
6. **Directory structure:** Verify subdirectories are preserved on the worker
   (e.g., `models/checkpoints/SDXL/Illustrious/model.safetensors`)
