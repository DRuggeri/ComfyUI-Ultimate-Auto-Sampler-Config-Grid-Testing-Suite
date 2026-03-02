# Sync Models to Workers — Design

**Date:** 2026-03-02
**Status:** Approved

## Summary

Optional feature that automatically transfers models, LoRAs, text encoders,
and VAEs from the master ComfyUI instance to worker instances via HTTP.
Workers save files permanently, preserving the master's directory structure.
Intelligent pre-fetching downloads upcoming models in the background while
current jobs process.

## Architecture

Two new components:

1. **Master File Server** — New endpoints on the master that stream model
   files from the master's local `ComfyUI/models/` folders. Workers request
   files by category + full relative path.

2. **Worker Model Sync** — Logic in the worker thread that checks
   `os.path.exists()` for each required model before processing a job. If
   missing, blocks and downloads from master via HTTP. Background pre-fetch
   thread downloads upcoming models between jobs.

### Flow

```
Job claimed → Extract model paths from config
            → Check each with folder_paths.get_full_path()
            → Missing? → Block + download from master → Process job
                          ↓ (parallel)
                          Background: pre-fetch upcoming_models list
```

## Master File Server

### Endpoint: POST /distribution/check_models

Bulk check which models a worker is missing. Returns missing list with sizes.

```
Request:  {
  "worker_id": "w_abc123",
  "models": [
    {"category": "checkpoints", "filename": "SDXL/Illustrious/Styles/model.safetensors"},
    {"category": "loras", "filename": "XL/detail_enhancer.safetensors"},
    {"category": "vae", "filename": "sdxl_vae.safetensors"}
  ]
}

Response: {
  "missing": [
    {"category": "loras", "filename": "XL/detail_enhancer.safetensors", "size_bytes": 184549376}
  ],
  "total_size": 184549376
}
```

Master resolves each file via `folder_paths.get_full_path(category, filename)`
and returns size for files the worker reports as missing.

### Endpoint: POST /distribution/download_model

Streams a single model file from master to worker.

```
Request:  {
  "worker_id": "w_abc123",
  "category": "checkpoints",
  "filename": "SDXL/Illustrious/Styles/model.safetensors"
}

Response: Streaming file with Content-Length header
```

Security: Validates `worker_id` is registered via `/distribution/register_worker`.

Supported categories: `checkpoints`, `loras`, `text_encoders`, `clip`,
`clip_gguf`, `diffusion_models`, `unet`, `unet_gguf`, `vae`

### Directory Structure Preservation

The `filename` field carries the full relative path including subdirectories.
Workers recreate the same folder hierarchy using `os.makedirs(parent, exist_ok=True)`.

Example: `checkpoints/SDXL/Illustrious/Styles/model.safetensors` on master
becomes `models/checkpoints/SDXL/Illustrious/Styles/model.safetensors` on worker.

## Worker Model Sync Logic

### Pre-job Model Check

When a worker claims a job, before processing it extracts all required model
paths from the job config:

- `config.model` → category from `config.model_type` (checkpoint/diffusion_model/gguf)
- `config.lora` → `loras` category
- `config.vae` → `vae` category (skip `remote:` URLs)
- `config.text_encoders` → `text_encoders` category

For each, `folder_paths.get_full_path(category, filename)` is checked. If it
returns `None`, the worker downloads from master before proceeding.

### Download Process

1. Worker calls `/distribution/check_models` with all needed models
2. Master responds with missing list + sizes
3. Worker downloads each missing file via `/distribution/download_model`
4. File saved to `ComfyUI/models/{category}/{filename}` with full subdirectory
   structure preserved
5. Worker logs progress: `[Worker] Downloading checkpoints/SDXL/.../model.safetensors (6.5 GB)...`

### Background Pre-fetch

After claiming a job, the worker also receives an `upcoming_models` list from
the master (models needed for the next N pending jobs). A background thread
downloads these while the current job processes, prioritized by job order.

Files stay permanently on the worker's disk. Future runs find them via
`folder_paths.get_full_path()` — zero transfer overhead.

## Job Claim Enhancement

### Modified Response: GET /distribution/claim_job

When `sync_models_to_workers` is enabled, the job claim response includes an
`upcoming_models` field:

```json
{
  "job_id": "...",
  "config": { ... },
  "upcoming_models": [
    {"category": "checkpoints", "filename": "SDXL/Illustrious/Styles/model_B.safetensors"},
    {"category": "loras", "filename": "XL/detail_enhancer.safetensors"},
    {"category": "loras", "filename": "XL/style_anime.safetensors"}
  ]
}
```

The master builds this by scanning the next N pending jobs, collecting unique
model references. The worker's background pre-fetch thread works through this
list in priority order.

## UI — Distribution Settings

New checkbox in the Distribution Settings section, below the Master Text
Encoding toggle:

**Label:** "Sync Models to Workers"
**Info text:** "Automatically transfer required models, LoRAs, text encoders,
and VAEs to workers. Files are saved permanently to each worker's ComfyUI
models folder, matching the master's directory structure."

State: `node.state.sync_models_to_workers` (boolean, default `false`)
Config: `distribution_config.sync_models_to_workers` (boolean)

When disabled, workers behave exactly as today — must have models pre-installed.

## Files Changed Summary

| File | Changes |
|------|---------|
| `distribution_routes.py` | New endpoints: `/distribution/check_models`, `/distribution/download_model` |
| `distribution_worker.py` | Pre-job model check, blocking download, background pre-fetch thread |
| `distribution_manager.py` | `upcoming_models` in `_job_to_dict()`, model extraction from pending jobs |
| `conf-builder-distribution.js` | "Sync Models to Workers" checkbox in Distribution Settings |
| `generation_orchestrator.py` | Pass `sync_models_to_workers` flag through to distribution manager |

## What Doesn't Change

Everything else about distributed processing stays the same:
- Pull-based job claiming
- Heartbeats and timeout reclaiming
- Pre-encoded conditionings (Master Text Encoding)
- Result submission
- Worker registration
