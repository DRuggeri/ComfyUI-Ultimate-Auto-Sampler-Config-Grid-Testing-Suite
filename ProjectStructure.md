### **ComfyUI Registry Security Requirements**

This node is published to the ComfyUI Registry. Every version is scanned by an automated
security scanner. Versions that fail the scan receive `NodeVersionStatusFlagged` status and
are hidden from ComfyUI Manager. **All contributors must follow these rules:**

1. **No `import requests`** — Use `urllib.request` (stdlib) instead. The scanner flags
   outbound HTTP libraries as potential data exfiltration vectors.
2. **No `subprocess`, `os.system`, `eval()`, `exec()`** — These are blocked as arbitrary
   code execution risks.
3. **No runtime `pip install`** — Package installation must go through `requirements.txt`
   only, never called at runtime.
4. **No code obfuscation** — No encoded strings, multi-statement tricks, or undefined
   variable patterns.
5. **No custom file-serving endpoints** — Use ComfyUI's built-in `WEB_DIRECTORY` for JS and
   the built-in `/view` endpoint for images. Never use `web.FileResponse` or create custom
   routes that serve files from disk. For external images, create symlinks into the output
   directory and use `/view?filename=X&type=output&subfolder=Y`.
6. **Path containment on all filesystem operations** — Every endpoint that touches the
   filesystem must validate that resolved paths stay within the expected base directory
   (e.g., `output/benchmarks/`). Use `os.path.realpath()` + `startswith()` checks.
7. **Sanitize all user-supplied path components** — Session names, filenames, etc. must be
   sanitized with `re.sub(r'[^\w\-]', '', name)` or `os.path.basename()` before use.

Reference: https://blog.comfy.org/p/comfyui-2025-jan-security-update

---

### **Updated Project File Structure**

```text
ComfyUI-Ultimate-Sampler-Grid/
├── __init__.py                  # Server Routes & Node Mappings
├── sampler_node.py              # Main "Sampler Grid" Node
├── dashboard_node.py            # "Dashboard Viewer" Node
├── config_builder_node.py       # "Config Builder" Node
├── json_text_node.py            # "Smart JSON" Node
│
├── generation_orchestrator.py   # The "Conductor" (Loop Logic)
├── image_generation.py          # KSampler & VAE Wrappers
├── model_loader.py              # Checkpoint/LoRA Loading Logic
├── model_cache.py               # 3-Tier Model Caching System
├── remote_vae.py                # Remote VAE Offloading
│
├── batch_encoding.py            # Batch CLIP Encoding with Combinator Support
├── conditioning_cache.py        # Disk-based Conditioning Cache
├── lora_utils.py                # LoRA Searching & Validation
├── trigger_words.py             # CivitAI Trigger Word Fetching & Prompt Assembly
├── config_utils.py              # Config Parsing, Expansion & Cartesian Products
├── directory_scanner.py         # External Directory Session Scanner
├── metadata_packer.py           # PNG/WebP Metadata Embedding for Exports
├── manifest_utils.py            # Manifest Read/Write/Merge Helpers
├── html_generator.py            # Reads /resources/ to build the Dashboard HTML
│
├── web/                         # [ComfyUI Integration Layer]
│   ├── dashboard.js             # Registers Dashboard Node & Message Handling
│   ├── config_builder.js        # Registers Builder Node & Custom UI Widget
│   ├── smart_json_text.js       # Registers JSON Node & Syntax Highlighting
│   └── conf_builder/            # [Config Builder UI Modules]
│       ├── conf-builder-main.js           # Main entry, widget registration
│       ├── conf-builder-ui-components.js  # UI rendering (dropdowns, sliders, cards)
│       ├── conf-builder-config-management.js # Save/Load/Duplicate config logic
│       └── conf-builder-utilities.js      # State-to-JSON conversion, iteration counting
│
└── resources/                   # [The Dashboard SPA Core]
    ├── template.html            # HTML Skeleton for the generated report
    ├── report.css               # Styling (Infinite Canvas, Cards, Modals)
    ├── logic_init.js            # Bootstrapper (Load JSON, Init State)
    ├── logic_state.js           # State Store (Redux-style: filters, favorites)
    ├── logic_pipeline.js        # Data Processing (Filter -> Sort -> Layout)
    ├── logic_virtual.js         # Virtual DOM / Infinite Scroller Engine
    ├── logic_ui.js              # UI Renderer (DOM creation, Modal handling)
    ├── logic_events.js          # Interaction Handler (Hotkeys, API calls)
    └── logic_utils.js           # Helpers (Debounce, Formatters)

```

**Output Directory Structure (Generated at Runtime):**
```text
ComfyUI/output/
├── ultimate-configs/                  # Saved config presets (NOT under benchmarks/)
│   └── {name}.json
└── benchmarks/
    ├── loras_tags.json                # LoRA trigger word cache (shared)
    ├── model_hashes.json              # SHA256 hash cache for CivitAI lookups
    ├── model-data/                    # CivitAI metadata cache per model
    │   └── {model_name}/metadata.json
    └── {session_name}/
        ├── manifest.json              # Generation metadata + user annotations
        ├── images/
        │   └── img_{n}.webp
        └── favorites/                 # Created by export_favorites endpoint
```

---

### **Project Architecture Overview**

**ComfyUI-Ultimate-Sampler-Grid** is a hybrid application.

1. **The Backend (Python):** Runs inside ComfyUI. It orchestrates the grid generation, manages resources (caching/loading), and serves the API.
2. **The Frontend Bridge (JS):** Runs in the ComfyUI browser tab. It registers the custom nodes and widgets.
3. **The Dashboard SPA (HTML/JS/CSS):** A standalone, virtualized "IDE" for viewing results. It is generated by the backend but runs entirely in the client's browser, communicating back to the server only when saving changes.

---

### **Node Class Mappings**

| Internal Name | Python Class | Purpose |
|---|---|---|
| `UltimateSamplerGrid` | `SamplerGridTester` | Main generation node — receives configs, runs Cartesian grid |
| `UltimateGridDashboard` | `SamplerConfigDashboardViewer` | Dashboard viewer — renders iframe with results |
| `UltimateConfigBuilder` | `UltimateConfigBuilder` | Visual config builder — outputs `configs_json` string |
| `SmartJSONText` | `SmartJSONTextNode` | JSON text widget with syntax highlighting |

---

### **API Routes Reference**

All routes registered in `__init__.py` via `PromptServer.instance.routes`.

**Config Builder APIs** (`/configbuilder/`):

| Method | Route | Purpose |
|---|---|---|
| GET | `/configbuilder/list_configs` | List saved config preset filenames |
| POST | `/configbuilder/save_config` | Save config preset `{name, data}` |
| POST | `/configbuilder/load_config` | Load config preset `{name}` |
| POST | `/configbuilder/lookup_triggers` | Bulk LoRA trigger word lookup `{loras: [...]}` |
| POST | `/configbuilder/lookup_lora_metadata` | Full CivitAI metadata for LoRA `{lora_name}` |
| POST | `/configbuilder/lookup_model_metadata` | Full CivitAI metadata for model `{model_name, model_type}` |
| GET | `/configbuilder/model_lists` | All model/sampler/scheduler/VAE lists |
| POST | `/configbuilder/refresh_models` | Signal frontend cache clear |

**Dashboard/Tester APIs** (`/config_tester/`):

| Method | Route | Purpose |
|---|---|---|
| POST | `/config_tester/delete_session` | Delete session folder `{session_name}` |
| POST | `/config_tester/save_changes` | Delta save — only changed items `{session_name, changed_items}` |
| POST | `/config_tester/save_manifest` | Full merge save `{session_name, manifest}` |
| POST | `/config_tester/get_session_html` | Generate dashboard HTML on-demand `{session_name, node_id}` |
| POST | `/config_tester/export_favorites` | Export favorited images `{session_name, pack_metadata, organize_by_prompt, organize_by_lora}` |
| POST | `/config_tester/scan_directory` | Scan external dir, create symlinks, use built-in `/view` `{directory_path, session_name}` |

---

### **1. The Backend: Core Logic & Orchestration**

*Located in the root directory.*

* **`sampler_node.py`** (The Interface)
* **Role:** The primary ComfyUI node (`SamplerGridTester`). Validates inputs and passes control to the orchestrator.
* **Key Functions:** `run_tests()` (entry point → delegates to `generation_orchestrator.run_generation_loop()`), `find_existing_match()`, `get_latent_channels()`
* **Key Logic:** Disables caching features if "Optional" inputs are connected (since external changes can't be tracked). `IS_CHANGED()` returns `NaN` when optionals connected (forces re-execution), deterministic hash otherwise.
* **Required Inputs:** `ckpt_name`, `positive_text`, `negative_text`, `seed`, `denoise`, `configs_json`, `resolutions_json`, `session_name`, `overwrite_existing`, `flush_batch_every`, `add_random_seeds_to_gens`, `lora_triggerwords_mode`, `remote_vae_endpoint`, `save_conditioning_cache_to_file`, `enable_model_cache`
* **Optional Inputs:** `optional_model` (MODEL), `optional_clip` (CLIP), `optional_vae` (VAE), `optional_positive` (CONDITIONING), `optional_negative` (CONDITIONING), `optional_latent` (LATENT)


* **`generation_orchestrator.py`** (The Conductor — largest file, ~987 lines)
* **Role:** Manages the generation loop.
* **Key Functions:** `run_generation_loop()`, `check_if_job_completed()`, `setup_session_directories()`, `load_model_by_type()`, `get_model_cache_key()`, `calculate_clip_hash()`
* **Key Logic:**
* **Smart Skip:** `check_if_job_completed()` matches against manifest items by seed/resolution/sampler/scheduler/steps/cfg/denoise. Skips model/lora/prompt matching when optional inputs connected.
* **Lookahead:** Triggers `model_cache.preload_lora_model()` / `preload_base_model()` for the *next* job while the current one runs.
* **Interrupts:** Catches `InterruptProcessingException` during text encoding AND image generation. Flushes pending VAE batch and saves manifest before stopping.
* **ETA Tracking:** Sends `ultimate_grid.progress` events to dashboard via `PromptServer.instance.send_sync()`.
* **Node Change Detection:** Detects when connected upstream nodes have changed for smarter job resuming.
* **Pre-encoding:** Single model → batch-encode all unique prompts upfront. Multi-model → re-encode per model switch.
* **VAE Switching:** Flushes pending batch before switching VAE. Tracks `default_model_vae` for reverting to "Default".




* **`image_generation.py`** (The Worker)
* **Role:** Wraps KSampler and VAE Decode.
* **Key Logic:** Implements `flush_batch_with_vae` to save images and update the manifest in chunks (preventing VRAM overflow).


* **`config_builder_node.py`** (The Builder UI Backend)
* **Role:** `UltimateConfigBuilder` node. All state stored in single `lora_config` widget as JSON string.
* **Key Functions:** `generate_config()`, `process_lora_array()`, `get_available_sessions()`, `expand_lora_folders()`, `lookup_lora_triggers()`
* **Key Logic:** Python reads ONLY `lora_config` widget — all other INPUT_TYPES widgets (samplers, schedulers, steps, cfg) are vestigial and ignored. Also defines API routes for trigger/metadata lookup and model lists.


* **`html_generator.py`** (The Builder)
* **Role:** Compiles the SPA into a single inlined HTML string.
* **Key Functions:** `get_html_template(title, manifest_data, node_id)`
* **Key Logic:** Reads all files from `/resources/` in dependency order, injects them into `template.html`, embeds `manifest.json` as `fullManifest` JS variable. Replaces placeholders: `__CSS_CONTENT__`, `__JS_CONTENT__`, `__TITLE__`, `__NODE_ID__`. No separate HTTP requests — everything inlined.
* **JS Load Order:** `logic_state.js` → `logic_utils.js` → `logic_ui.js` → `logic_virtual.js` → `logic_pipeline.js` → `logic_events.js` → `logic_init.js`



---

### **2. The Backend: Resource Management**

*Located in the root directory.*

* **`model_cache.py`** (The 3-Tier Cache)
* **Role:** Thread-safe resource manager. Single `ModelCache` class.
* **Tiers:** 1. LoRA File Cache (raw state_dicts in RAM), 2. Incremental States (partial LoRA stacks via `check_incremental_cache()`), 3. Final Patched Models (`get_lora_model()` / `put_lora_model()`).
* **Key Methods:** `get_base_model()`, `put_base_model()`, `preload_lora_model()`, `preload_base_model()`, `register_schedule()`, `set_current_step()`, `clear()`, `print_stats()`
* **Async Preloading:** `preload_*` methods run loaders in background threads via `concurrent.futures`, results retrieved later.


* **`conditioning_cache.py`** (The Prompt Cache)
* **Role:** Caches CLIP text encodings to disk.
* **Key Logic:** Hashes `(Prompt + CLIP State + LoRA Config)` to ensure validity. Auto-disabled when optional inputs connected.


* **`batch_encoding.py`** (The Accelerator)
* **Role:** Bulk prompt encoder with combinator support.
* **Key Functions:** `encode_prompt_with_combinators(clip, text, clip_skip)`, `batch_encode_prompts(clip, positives, negatives, cond_cache, clip_skip)`
* **Combinators:** `AND` (multi-cond with optional weights like `:1.5`), `CAT` (tensor concatenation), `AVG(weight)` (weighted average, default 0.5), `BREAK` (native tokenizer segment break at 77-token chunks).


* **`model_loader.py`** (The Loader)
* **Role:** Checkpoint, LoRA, VAE, GGUF, and diffusion model loading.
* **Key Functions:** `load_checkpoint()`, `load_loras()`, `load_vae_by_name()`, `load_diffusion_model_and_clip()`, `load_loras_for_preencoding()`, `cleanup_model_references()`, `print_incompatible_loras_summary()`


* **`trigger_words.py`** (Trigger Word Engine)
* **Role:** CivitAI trigger word fetching and prompt assembly.
* **Key Functions:** `collect_unique_prompts_with_triggers(expanded_configs, mode)`, `build_prompt_with_triggers(config, mode)`, `get_filtered_lora_triggers(lora_string, omit_list)`
* **Modes:** `"None"`, `"Append To End"`, `"Append To Start"`, `"Read From Config"`. Per-LoRA placement via `lora_triggerwords_append_settings`. Also applies `model_prompt_prefix` / `model_prompt_suffix`.


* **`config_utils.py`** (Expansion Engine)
* **Role:** Config parsing, Cartesian product expansion, folder expansion.
* **Key Functions:** `expand_configs()`, `parse_prompt_input_nested()`, `prepare_input_jobs()`, `parse_lora_definition()`, `get_files_from_folder()`, `sanitize_session_name()`
* **Key Logic:** `parse_prompt_input_nested()` supports arbitrarily deep nested arrays for Cartesian prompting. `"folder/"` = expand individually, `"folder/*"` = stack all together.


* **`manifest_utils.py`** (Manifest Persistence)
* **Key Functions:** `load_existing_manifest()`, `save_manifest()`, `merge_manifest_user_changes()`
* **Key Logic:** `save_manifest()` calls `merge_manifest_user_changes()` first — reloads from disk to preserve user favorites/rejected/notes that may have changed concurrently.


* **`directory_scanner.py`** (External Image Scanner)
* **Key Functions:** `scan_directory_for_images()`, `parse_a1111_parameters()`
* **Key Logic:** Parses A1111-style PNG metadata into dashboard-compatible manifest items. Preserves user tags on re-scan by merging with existing manifest.


* **`metadata_packer.py`** (Export Metadata)
* **Key Functions:** `pack_metadata_into_image()`, `extract_metadata_from_image()`, `calculate_file_hash()`
* **Key Logic:** Packs ComfyUI-compatible metadata into PNG for CivitAI uploads. Maintains SHA256 hash cache at `benchmarks/model_hashes.json`.


---

### **Key Data Shapes**

**Config Array State** (`node.state.config_arrays[n]` in JS, parsed from `lora_config` widget in Python):
```json
{
  "name": "Config 1",
  "samplers": ["euler", "dpmpp_2m"],
  "schedulers": ["normal", "karras"],
  "steps": "20, 30",
  "cfg": "7.0",
  "models": [{"path": "model.safetensors", "type": "checkpoint"}],
  "vaes": ["None"],
  "loras": ["lora.safetensors:1.00:1.00"],
  "lora_bypass_states": {"lora_name": true},
  "model_bypass_states": {"model_path": true},
  "lora_omit_triggers": [],
  "lora_triggerwords_append_settings": {},
  "lora_strength_lock": {},
  "combine": false,
  "positive_prompt_groups": [],
  "negative_prompt": "",
  "use_custom_prompts": false,
  "model_prompt_prefix": "",
  "model_prompt_suffix": "",
  "attention_modes": ["default"],
  "seed_behavior": "fixed",
  "text_encoders": [],
  "clip_type": "stable_diffusion",
  "gguf_options": {}
}
```

**Manifest Item** (`manifest.json` `items[n]`):
```json
{
  "id": "uuid-string",
  "seed": 12345, "cfg": 7.0, "steps": 20,
  "sampler": "euler", "scheduler": "normal",
  "model": "model.safetensors", "lora": "lora:1.0:1.0",
  "vae": "vae.safetensors", "attention_mode": "default",
  "positive": "prompt text", "negative": "negative text",
  "denoise": 1.0, "width": 1024, "height": 1024,
  "batch_idx": 0, "generation_time": 45.2,
  "file": "/view?filename=img_0.webp&type=output&subfolder=benchmarks/session/images",
  "favorite": false, "rejected": false, "notes": ""
}
```

---

### **Communication Patterns**

**Widget Bridge (Config Builder → Python):**
```
JS node.state → JSON.stringify() → lora_config widget.value → Python json.loads(lora_config)
```
All other widget params in INPUT_TYPES (samplers, schedulers, steps, cfg) are ignored by Python.

**Live Dashboard Updates (Server → Dashboard iframe):**
```
generation_orchestrator → PromptServer.send_sync("ultimate_grid.update")
  → dashboard.js api.addEventListener → postMessage({type: 'update_data'})
  → iframe logic_events.js message handler
```

**Progress Updates (Server → Dashboard iframe):**
```
generation_orchestrator → PromptServer.send_sync("ultimate_grid.progress")
  → dashboard.js → postMessage({type: 'progress_update'})
  → iframe #eta-bar update
```

**Dashboard → Parent Frame:**
```
iframe postMessage({type: 'toggle_fullscreen', node_id})
  → dashboard.js listener → toggle .dashboard-fullscreen class
```

---

### **3. The Frontend: ComfyUI Integration**

*Located in `/web/`.*

* **`dashboard.js`**
* **Role:** Registers the Dashboard node (`UltimateGridDashboard`). Listens for `ultimate_grid.update` and `ultimate_grid.progress` server events.
* **Key Logic:** Forwards events to matching iframe via `postMessage()`. Auto-loads session when update received for unloaded session. Handles fullscreen toggle via `.dashboard-fullscreen` CSS class.
* **Widgets:** "RELOAD / SHOW SESSION" button → `forceLoadSession()`, "DELETE SESSION" button → POST `/config_tester/delete_session`


* **`config_builder.js`** (entry point, loads `conf_builder/` modules)
* **Role:** Registers the Builder node (`UltimateConfigBuilder`). Entry point for the modular Config Builder UI.
* **Key Logic:** `onNodeCreated` **MUST be synchronous** (async init runs in fire-and-forget IIFE). Uses `Date.now()` cache-busting on module `import()` calls. Hooks `app.refreshComboInNodes()` to detect model/LoRA changes.
* **Node Methods:** `node.saveState()`, `node.renderUI()`, `node.loadSession(sessionName)`, `node.saveConfigToBackend()`, `node.loadConfigFromBackend(filename)`, `node.triggerAutoSave()` (2s debounce)


* **`smart_json_text.js`**
* **Role:** Registers the JSON node (`SmartJSONText`). Adds syntax highlighting and validation.


* **`conf_builder/conf-builder-utilities.js`** (The Data Layer)
* **Key Exports:** `convertStateToConfigs()`, `getIterationCount()`, `parseLoraString()`, `buildLoraString()`, `refreshAllConfigBuilders()`, `clearAllCaches()`, `normalizePath()`, `getAvailableLoras()`, `getModelLists()`
* **Global Caches:** `availableLoras`, `availableModels`, `availableVAEs`, `availableSamplers`, `availableSchedulers`, `availableSessions`, `availableConfigs`


* **`conf_builder/conf-builder-config-management.js`** (The UI Builder)
* **Key Exports:** `renderUI()`, `updatePreview()`, `renderConfigSection()`, `renderSessionSection()`, `createConfigArrayElement()`, `createModelElement()`


* **`conf_builder/conf-builder-ui-components.js`** (The Widget Library)
* **Key Exports:** `createSearchableSelect()`, `createSlider()`, `createInputGroup()`, `getStyles()`



---

### **4. The Frontend: The Dashboard SPA**

*Located in `/resources/`. This is the "App" users interact with.*

* **`logic_init.js`** (The Bootstrapper)
* **Role:** Main Entry Point.
* **Key Logic:**
* **`initDashboard()`:** The first function called.
* **Data Injection:** detects if `fullManifest` exists (injected by Python). If not, it attempts to fetch it (View Mode).
* **Lifecycle:** Calls `initLogicState()` -> `applyPipeline()` -> `initVirtualScroller()` -> `initGlobalEvents()`.




* **`logic_state.js`** (The Brain)
* **Role:** Central State Store (Redux-style).
* **Key Logic:**
* **`State` Object:** Holds `items` (all images), `filteredItems` (visible), `selection` (active card), and `favorites`.
* **Triple JSON Lists:** Manages the logic for the "Accepted", "Favorites", and "Rejected" JSON bars at the bottom of the UI.
* **Persistence:** Saves user preferences (Sort Order, Column Count) to `localStorage` so they persist across reloads.




* **`logic_events.js`** (The Handler)
* **Role:** Interaction & API Bridge.
* **Key Logic:**
* **Keyboard Shortcuts:** Maps `Arrow Keys` (Pan), `Space` (Scroll), `+/-` (Zoom), `F` (Fit), `Escape` (close modals with priority chain).
* **API Calls:** Uses `fetch` to hit endpoints like `/config_tester/save_manifest` (when you star/reject an image) and `/config_tester/delete_session`.
* **Live Updates:** Listens for the `executed` event from ComfyUI to trigger a soft-refresh of the image list.




* **`logic_virtual.js`** (The Engine)
* **Role:** Virtual Scroller.
* **Key Logic:** Calculates viewport geometry to render only the ~20 visible cards out of thousands, enabling high performance.


* **`logic_pipeline.js`** (The Processor)
* **Role:** Filtering & Sorting.
* **Key Logic:** Transforms the raw item list based on active filters (Model, Sampler, etc.) before passing it to the virtual scroller.


* **`logic_ui.js`** (The Renderer)
* **Role:** DOM Manipulation.
* **Key Logic:** Generates the HTML for individual cards, the "Revise" modal, and the unified Settings panel (gear icon). Manages modal open/close with overlay and body overflow lock.


* **`logic_utils.js`** (The Helpers)
* **Role:** Utilities and server communication.
* **Key Functions:** `loadSession()`, `saveState()`, `exportFavorites()`, `scanDirectory()`, `triggerGen()`, `toggleFullscreen()`, `rejectItem()`



---

### **Key Functions Quick Reference**

**Python (by file):**

| File | Key Functions |
|---|---|
| `sampler_node.py` | `run_tests()`, `find_existing_match()`, `get_latent_channels()`, `IS_CHANGED()` |
| `config_builder_node.py` | `generate_config()`, `process_lora_array()`, `get_available_sessions()`, `expand_lora_folders()` |
| `generation_orchestrator.py` | `run_generation_loop()`, `check_if_job_completed()`, `setup_session_directories()`, `load_model_by_type()` |
| `batch_encoding.py` | `encode_prompt_with_combinators()`, `batch_encode_prompts()` |
| `config_utils.py` | `expand_configs()`, `parse_prompt_input_nested()`, `prepare_input_jobs()`, `parse_lora_definition()` |
| `model_loader.py` | `load_checkpoint()`, `load_loras()`, `load_vae_by_name()`, `load_diffusion_model_and_clip()` |
| `model_cache.py` | `ModelCache.get_base_model()`, `.put_base_model()`, `.preload_lora_model()`, `.register_schedule()` |
| `trigger_words.py` | `collect_unique_prompts_with_triggers()`, `build_prompt_with_triggers()`, `get_filtered_lora_triggers()` |
| `manifest_utils.py` | `load_existing_manifest()`, `save_manifest()`, `merge_manifest_user_changes()` |
| `directory_scanner.py` | `scan_directory_for_images()`, `parse_a1111_parameters()` |
| `metadata_packer.py` | `pack_metadata_into_image()`, `extract_metadata_from_image()`, `calculate_file_hash()` |

**JavaScript (by file):**

| File | Key Functions |
|---|---|
| `conf-builder-utilities.js` | `convertStateToConfigs()`, `getIterationCount()`, `parseLoraString()`, `buildLoraString()`, `refreshAllConfigBuilders()` |
| `conf-builder-config-management.js` | `renderUI()`, `updatePreview()`, `createConfigArrayElement()`, `createModelElement()` |
| `conf-builder-ui-components.js` | `createSearchableSelect()`, `createSlider()`, `getStyles()` |
| `conf-builder-main.js` | `ensureModulesLoaded()`, `node.saveState()`, `node.renderUI()`, `node.loadSession()` |
| `logic_ui.js` | `toggleCogMenu()`, `toggleFiltersPopup()`, `initFilters()` |
| `logic_utils.js` | `loadSession()`, `exportFavorites()`, `scanDirectory()`, `triggerGen()`, `toggleFullscreen()` |
| `logic_virtual.js` | `renderDOM()`, `updateVisibleItems()`, `calculateVisibleRange()`, `autoFitZoom()`, `goToImage()` |
| `logic_pipeline.js` | `updateDataPipeline()`, `executePipeline()`, `processNewData()`, `incrementalFilter()` |
| `logic_events.js` | Message handler for `progress_update` and `update_data` types |

---

### **Summary of Data Flow**

1. **User Config:** You set parameters in the **Sampler Node** (Python).
2. **Expansion:** `generation_orchestrator.py` expands this into a list of jobs.
3. **Generation:** The backend loops through jobs, using **ModelCache** and **ConditioningCache** for speed.
4. **Storage:** Images are saved to disk; metadata is appended to `manifest.json`.
5. **Compilation:** `html_generator.py` reads the `manifest.json` and all `.js` files in `/resources/`, baking them into a single `dashboard_html` string.
6. **Display:** The **Dashboard Node** (JS) renders this HTML in an iframe.
7. **Boot:** `logic_init.js` wakes up, loads the data into `logic_state.js`, and `logic_virtual.js` starts rendering cards.
8. **Interaction:** You click "Favorite" in the UI -> `logic_events.js` sends an API request to `__init__.py` -> Python updates `manifest.json` on disk.

---

### **Critical Development Gotchas**

1. **Dual Data Path** — Frontend `convertStateToConfigs()` (in `conf-builder-utilities.js`) and Python `generate_config()` (in `config_builder_node.py`) are **independent implementations** that both transform `node.state` into config JSON. Both must stay in sync when adding new config fields or the UI preview will mismatch the actual output.

2. **Widget Bridge** — The `lora_config` widget (STRING type) holds the **entire** node state as serialized JSON. Python `generate_config()` ignores all other widget params and reads only `lora_config`. The `samplers`, `schedulers`, `steps`, `cfg` widgets in `INPUT_TYPES` are vestigial (kept for ComfyUI schema compliance only).

3. **onNodeCreated Must Be Synchronous** — In `conf-builder-main.js`, `onNodeCreated` MUST remain synchronous. Async initialization runs inside a fire-and-forget `(async () => { ... })()` IIFE. Making `onNodeCreated` itself async breaks widget registration.

4. **Resources Are Inlined** — `html_generator.py` reads all `/resources/` files and bakes them into one HTML string. Zero external HTTP requests. Changes to dashboard JS/CSS require re-generating the HTML (re-run the sampler node or call `/config_tester/get_session_html`).

5. **Manifest Merge on Save** — `manifest_utils.py` `save_manifest()` calls `merge_manifest_user_changes()` which reloads from disk before saving. This preserves user favorites/rejected/notes that may have been changed concurrently while generation was running.

6. **Optional Inputs Disable Caches** — `sampler_node.py` disables conditioning cache when `optional_model`/`optional_clip`/`optional_positive`/`optional_negative` are connected. `IS_CHANGED()` returns `NaN` (forces re-execution). `check_if_job_completed()` skips model/lora/prompt matching.

7. **Folder Expansion Syntax** — `"folder/"` = expand to individual entries (one combination each). `"folder/*"` = stack ALL files in folder together as a single combined entry. Weight array syntax `"lora:[0.5, 0.8]:1.0"` creates grid search over strengths. No trailing slash = single file match.

8. **LoRA String Format** — `"name:model_str:clip_str"`, stacked with `" + "` separator. `parseLoraString()` in JS, `parse_lora_definition()` in Python. Default strengths: 1.0 for both if colon-separated parts are missing.

9. **Cache Busting** — `conf-builder-main.js` uses `Date.now()` timestamp on `import()` calls for module loading. Also intercepts `window.fetch` to detect `/object_info` calls and trigger cache refresh. Static JS served via ComfyUI's `/extensions/` path.

10. **Config Presets Path** — Saved to `output/ultimate-configs/` (defined in `__init__.py`), NOT `output/benchmarks/configs/`. Session data goes under `output/benchmarks/{session_name}/`.

11. **Field Name Inconsistency: `favorite` vs `favorited`** — `manifest_utils.py` `merge_manifest_user_changes()` uses the key `"favorite"`. But `__init__.py` routes like `save_manifest` and `export_favorites` check `"favorited"`. When touching favorite/unfavorite logic, check which key name the specific code path uses.

12. **Prompt Expansion is Recursive** — `parse_prompt_input_nested()` in `config_utils.py` supports arbitrarily deep nested arrays. Flat list = OR (options). List containing sub-lists = AND (Cartesian product). This is used by both the node text inputs and per-config prompt groups from the builder UI.