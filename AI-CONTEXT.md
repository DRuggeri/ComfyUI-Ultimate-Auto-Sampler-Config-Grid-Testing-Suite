# AI Development Context — ComfyUI Ultimate Auto Sampler Config Grid Testing Suite

> **Paste this at the start of any new Claude conversation to provide full project context.**
> **GOLDEN RULE: DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.**

## What This Is

A ComfyUI custom node extension for automated image generation grid testing. Users configure combinations of samplers, schedulers, steps, CFG, models, LoRAs, prompts, and resolutions — the system generates all Cartesian products, saves results, and displays them in a virtualized dashboard for comparison. Supports distributed multi-machine generation, upscaling, and CivitAI metadata export.

## Project Location

```
Z:\comfy_v0.12.3\ComfyUI\custom_nodes\ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite\
```

Read `ProjectStructure.md` in this directory for the full reference (file structure, all API routes with line numbers, data shapes, communication patterns, dependency graph, and 28 development gotchas).

## Architecture (3 Layers)

1. **Python Backend** (runs inside ComfyUI server) — nodes, orchestration, generation, API endpoints
2. **JS Frontend Bridge** (`web/`) — registers nodes in ComfyUI browser tab, served at `/extensions/`
3. **Dashboard SPA** (`resources/`) — standalone app inlined into iframe by `html_generator.py`, zero external requests

## Critical Files & Their Roles

| File | Lines | Role |
|------|-------|------|
| `__init__.py` | ~1000 | API endpoints (config CRUD, dashboard save/export/delete, scan, upscale presets, config presets, async upscale), node mappings, path security |
| `sampler_node.py` | 314 | Main node class. Unwraps configs, extracts `_distribution` + `_session_settings`, delegates to orchestrator |
| `config_builder_node.py` | ~1200 | Config builder node. `generate_config()` reads ALL state from `lora_config` widget. API endpoints for model lists, trigger lookups |
| `generation_orchestrator.py` | ~2600 | **Largest file.** Main generation loop, smart skip, upscaling pipelines, deferred upscales (`run_deferred_upscales()`), GPU cooldown, distribution, ETA tracking, Start At Job # |
| `image_generation.py` | ~780 | KSampler wrapper, VAE decode, `flush_batch_with_vae()` (saves images + updates manifest), `upscale_image()`, `create_image_metadata()`, rolling ETA |
| `network_utils.py` | 280 | **All outbound network requests.** CivitAI API, HuggingFace Remote VAE (allowlisted), Distribution LAN calls. No other file imports urllib. |
| `upscale_runner.py` | 371 | Dashboard async upscaling. Background thread loads models, runs pipeline chains, updates manifests, sends progress events. |
| `config_utils.py` | 674 | Config expansion (Cartesian products), nested prompt parsing, job preparation |
| `model_loader.py` | 805 | Checkpoint/LoRA/VAE/GGUF loading |
| `model_cache.py` | 900 | 3-tier cache: LoRA files → incremental states → patched models. Async preloading |
| `manifest_utils.py` | 120 | Load/save/merge manifest. `save_manifest()` reloads from disk first to preserve concurrent user edits |
| `metadata_packer.py` | 561 | PNG metadata embedding for CivitAI. `pack_metadata_into_image()` accepts `workflow_data` kwarg |
| `web/conf_builder/conf-builder-main.js` | 608 | Node registration. Default state (lines 80-147) defines ALL fields including upscaling/cooldown |
| `web/conf_builder/conf-builder-utilities.js` | 958 | `convertStateToConfigs()` (line 497) — **MUST stay in sync with Python `generate_config()`** |
| `web/conf_builder/conf-builder-config-management.js` | 4975 | All config builder UI rendering. Upscaling section ~line 4437 |
| `resources/logic_utils.js` | 599 | Dashboard helpers: `exportFavorites()`, `deleteNonFavorites()`, `loadSession()`, `scanDirectory()` |
| `resources/logic_ui.js` | 1780 | Dashboard DOM: cards, modals, `buildComfyNodesWorkflow()`, analytics |
| `resources/logic_virtual.js` | 925 | Virtual scroller — renders only visible cards from thousands |

## The Two Codepaths That Must Stay In Sync

When adding ANY new config field, you MUST update BOTH:

1. **JS:** `convertStateToConfigs()` in `conf-builder-utilities.js` (line 497)
2. **Python:** `generate_config()` in `config_builder_node.py` (line 465)

Also add default values to:
- `conf-builder-main.js` default state (line 80)
- Migration check in `onConfigure` handler (~line 363) for existing saved workflows

## Config Data Flow

```
JS node.state
  → JSON.stringify() → lora_config widget value
  → Python json.loads(lora_config) in generate_config()
  → Output: {"configs": [...], "_distribution": {...}, "_session_settings": {...}}
  → sampler_node.py unwraps configs, extracts _distribution + _session_settings
  → generation_orchestrator.run_generation_loop() receives all as params
  → config_utils.expand_configs() creates Cartesian product job list
  → Loop: load model → encode prompts → generate → save
```

## Session Settings (Not Per-Config)

`_session_settings` is session-level, embedded alongside configs:
```json
{
  "upscaling": {
    "enabled": true,
    "save_pre_upscale": false,
    "run_upscales_at_end": false,
    "hires_prompt_adjust": false,
    "hires_prompt_behavior": "append_end",
    "hires_prompt_text": "",
    "pipelines": [{ "active": true, "name": "Pipeline 1", "steps": [{ "active": true, "mode": "hires_only", "repeat": 1, "upscale_models": [], "upscale_ratios": "1.5", "hires_denoise": "0.3", "hires_steps": 0, ... }] }]
  },
  "cooldown": { "enabled": true, "seconds": 5, "every_n": 1, "clear_vram": false },
  "start_at_job": 0
}
```
Extracted by `sampler_node.py` line 277, passed to orchestrator as `session_settings` param.

## Image/Manifest Format

Images saved as WebP at `output/benchmarks/{session}/images/img_{id}.webp`

**File URL format** (MUST match exactly for ComfyUI `/view` endpoint):
```
/view?filename={name}&type=output&subfolder=benchmarks/{session}/images
```

**Manifest entry required fields:**
```json
{
  "id": 170941234567890,        // int(time.time() * 100000) + random.randint(0, 1000)
  "file": "/view?filename=...", // Full URL as above
  "rejected": false,            // Required for dashboard display
  "favorited": false,           // User annotation
  "seed": 12345, "cfg": 7.0, "steps": 20,
  "sampler": "euler", "scheduler": "normal",
  "model": "model.safetensors", "lora": "lora:1.0:1.0",
  "positive": "prompt", "negative": "neg prompt",
  "width": 1024, "height": 1024, "duration": 45.2, "denoise": 1.0
}
```

## Key Patterns

- **Model discovery:** `folder_paths.get_filename_list("key")` → API at `/configbuilder/model_lists` → JS `getModelLists()`
- **Path security:** All endpoints use `_is_path_within()` + `re.sub(r'[^\w\-]', '', name)` sanitization
- **Dashboard updates:** `PromptServer.send_sync("ultimate_grid.update", {...})` → `dashboard.js` → `postMessage()` → iframe
- **All outbound network requests go through `network_utils.py`** — no other file imports `urllib.request`. CivitAI, HuggingFace VAE, and Distribution calls are all centralized there.
- **No `subprocess`, `os.system`, `eval()`, `exec()`** — blocked by security scanner
- **LoRA string format:** `"name:model_str:clip_str"`, stacked with `" + "` separator
- **Prompt nesting:** Flat list = OR, nested lists = AND (Cartesian product). Recursive in `parse_prompt_input_nested()`

## Field Name Warning

`manifest_utils.py` uses key `"favorite"`. `__init__.py` routes use `"favorited"`. Always check which key the specific code path expects.

## Testing Changes

- **Python files:** Restart ComfyUI
- **`web/` JS files:** Refresh browser (Ctrl+F5)
- **`resources/` files:** Must regenerate dashboard HTML — re-run sampler or call `/config_tester/get_session_html`
- **New state fields:** Add migration in `conf-builder-main.js` `onConfigure`

## Common Tasks

**Add a new config field:**
1. Add to default state in `conf-builder-main.js` (line 80)
2. Add migration in `onConfigure` (~line 363)
3. Add UI rendering in `conf-builder-config-management.js`
4. Add to `convertStateToConfigs()` in `conf-builder-utilities.js`
5. Add to `generate_config()` in `config_builder_node.py`
6. Consume in `generation_orchestrator.py` or relevant backend file

**Add a new API endpoint:**
1. Add route in `__init__.py` with `@server.PromptServer.instance.routes`
2. Add path security: sanitize session name, use `_is_path_within()`
3. Call from dashboard JS (`resources/logic_utils.js`) or config builder JS (`web/conf_builder/`)

**Add a new session setting:**
1. Add to default state in `conf-builder-main.js` under appropriate key
2. Add UI in `conf-builder-config-management.js`
3. Add to `convertStateToConfigs()` session settings block (line 689)
4. Add to `generate_config()` session settings embedding (line 706)
5. Consume in `generation_orchestrator.py` after the `session_settings` param check

**Modify dashboard UI:**
1. Edit files in `resources/` (HTML in `template.html`, JS in `logic_*.js`, CSS in `report.css`)
2. Remember: changes require HTML regeneration to take effect
3. JS load order: state → utils → ui → virtual → pipeline → events → init
