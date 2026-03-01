# Builder UI Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bugs (model hashing, VAE on/off switches), optimize builder UI performance, enhance CivitAI lookup modals, add dashboard prompt toggle, and build a lora trigger word editor.

**Architecture:** Incremental changes across the existing JS/Python codebase. Performance fix eliminates unnecessary full DOM rebuilds. Bug fixes are targeted. New features follow existing modal/endpoint patterns.

**Tech Stack:** Vanilla JavaScript (ComfyUI widget), Python aiohttp routes, JSON file storage.

**Critical Constraint:** DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

### Task 1: Fix Model Hashing Bug (metadata_packer.py)

**Files:**
- Modify: `metadata_packer.py:145-175` (find_model_file function)

**Step 1: Add diffusion_models and unet to search paths**

In `find_model_file()` (line 156-163), the `search_paths` default only includes `checkpoints` and `loras`. Add `diffusion_models` and `unet`:

```python
# Current (lines 156-163):
if search_paths is None:
    import folder_paths
    search_paths = [
        folder_paths.get_folder_paths("checkpoints")[0] if folder_paths.get_folder_paths("checkpoints") else None,
        folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else None,
    ]
    search_paths = [p for p in search_paths if p]

# New:
if search_paths is None:
    import folder_paths
    search_paths = []
    for folder_type in ["checkpoints", "loras", "diffusion_models", "unet"]:
        try:
            paths = folder_paths.get_folder_paths(folder_type)
            if paths:
                search_paths.extend(paths)
        except Exception:
            pass
```

Note: Use `extend(paths)` not just `[0]` — some folder types have multiple search directories.

**Step 2: Add folder_paths.get_full_path fallback before filename hash**

In lines 262-272, before the filename-based fallback hash, try `folder_paths.get_full_path()` for multiple model types:

```python
# After line 263 (model_file = find_model_file(model, checkpoint_paths)):
# Add this BEFORE the existing fallback block (lines 268-272):
if not model_file:
    # Try folder_paths.get_full_path for various model types
    import folder_paths as fp
    for model_type in ["checkpoints", "diffusion_models", "unet"]:
        try:
            resolved = fp.get_full_path(model_type, model)
            if resolved and os.path.isfile(resolved):
                model_file = resolved
                break
        except Exception:
            pass
```

**Step 3: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('metadata_packer.py', doraise=True)"`
Expected: No errors

**Step 4: Commit**

```bash
git add metadata_packer.py
git commit -m "Fix model hashing: search diffusion_models and unet folders"
```

---

### Task 2: Fix VAE & Text Encoder On/Off Switches

**Files:**
- Modify: `web/conf_builder/conf-builder-utilities.js:586-594`

**Step 1: Remove bypass state fields from config JSON output**

The VAE/TE bypass states are internal UI state — they should filter the arrays (which they already do at lines 500 and 545) but NOT appear in the output config JSON. Remove lines 586-594:

```javascript
// DELETE these lines (586-594) — bypass states are internal, not config output:
        // Add vae_bypass_states if any are set
        if (configArray.vae_bypass_states && Object.keys(configArray.vae_bypass_states).length > 0) {
            config.vae_bypass_states = configArray.vae_bypass_states;
        }

        // Add te_bypass_states if any are set
        if (configArray.te_bypass_states && Object.keys(configArray.te_bypass_states).length > 0) {
            config.te_bypass_states = configArray.te_bypass_states;
        }
```

Wait — the constraint says DO NOT REMOVE ANY CODE. So instead, comment them out and add an explanation:

```javascript
        // vae_bypass_states and te_bypass_states are internal UI state only.
        // They control filtering (lines 500, 545) but should NOT be in config output.
        // Bypass state persistence is handled by node.saveState() separately.
        // if (configArray.vae_bypass_states && Object.keys(configArray.vae_bypass_states).length > 0) {
        //     config.vae_bypass_states = configArray.vae_bypass_states;
        // }
        // if (configArray.te_bypass_states && Object.keys(configArray.te_bypass_states).length > 0) {
        //     config.te_bypass_states = configArray.te_bypass_states;
        // }
```

**Step 2: Verify bypass states persist across sessions**

Check that `conf-builder-main.js` migration block includes `vae_bypass_states` and `te_bypass_states` in the default state. They should already be there (line ~3486 in config-management.js sets defaults). Also verify `loadSession` and `loadConfigFromBackend` preserve them.

**Step 3: Commit**

```bash
git add web/conf_builder/conf-builder-utilities.js
git commit -m "Fix VAE/TE on/off switches: remove bypass states from config output"
```

---

### Task 3: Performance — Eliminate Unnecessary renderUI() Calls

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js` (many locations)

This is the largest task. There are 30+ `node.renderUI()` calls after single-item interactions. Most can be replaced with targeted DOM updates.

**Category A: Toggle/checkbox changes that DON'T need re-render**

These already update DOM inline. Remove the `node.renderUI()` call:

- Line 975: Strength lock toggle — BUT this one actually needs re-render to show/hide the CLIP slider. **KEEP this one.**
- Line 3307: Custom prompts toggle — needs re-render to show/hide prompt editors. **KEEP this one.**
- Line 3510: Label mode toggle — needs re-render to change display. **KEEP this one.**

**Category B: Model type / selection changes that trigger re-render**

These change the element structure (different dropdowns, different options). These are harder to optimize without a significant refactor. **KEEP these for now** but they're candidates for future optimization:

- Line 591: Model type changed (checkpoint/diffusion/gguf) — changes available options
- Line 611: Model selection via searchable select
- Line 861: LoRA type changed
- Line 880: LoRA selection via searchable select

**Category C: Add/Delete operations that CAN be optimized**

Replace `renderUI()` with targeted DOM manipulation:

**Step 1: Add Model button (line 384-389)**

Replace the onclick handler. Instead of rebuilding everything, create and append the new model element:

```javascript
// Line 384-389 — replace the onclick handler:
addModelBtn.onclick = () => {
    if (!node.state.config_arrays[arrayIdx].models) node.state.config_arrays[arrayIdx].models = [];
    node.state.config_arrays[arrayIdx].models.push("None");
    node.saveState();
    // Instead of node.renderUI(), append new element directly
    const newIdx = node.state.config_arrays[arrayIdx].models.length - 1;
    const modelsContainer = document.querySelector(`#config-array-${arrayIdx} .cb-models-container`);
    if (modelsContainer) {
        const newElement = createModelElement(node, "None", arrayIdx, newIdx, modelLists);
        modelsContainer.appendChild(newElement);
    } else {
        node.renderUI(); // Fallback if container not found
    }
};
```

**IMPORTANT:** For this to work, we need to add an id or class to the models container in `renderModelsSection()`. Find where models are rendered and add `modelsContainer.className = "cb-models-container";` or similar. We also need `modelLists` to be accessible.

**Given the complexity of making all add/delete operations work without renderUI, and the constraint "ONLY CHANGE WHAT IS NECESSARY", a better approach is debouncing:**

**Step 2: Add debounced renderUI wrapper**

At the top of conf-builder-config-management.js, add a debounced version:

```javascript
// Debounced renderUI to batch rapid state changes
let _renderUITimer = null;
function debouncedRenderUI(node) {
    if (_renderUITimer) clearTimeout(_renderUITimer);
    _renderUITimer = setTimeout(() => {
        _renderUITimer = null;
        node.renderUI();
    }, 150);
}
```

Then replace `node.renderUI()` with `debouncedRenderUI(node)` at all 30+ call sites EXCEPT:
- Initial load / loadSession / loadConfig (these should render immediately)
- Add config / delete config / duplicate config (structural changes, render immediately)

This batches rapid changes (e.g., strength slider dragging) without the risk of breaking targeted DOM updates.

**Step 3: Optimize the main renderUI function for speed**

In the `renderUI` function (conf-builder-config-management.js line ~3440), the scroll position save/restore is already there. Add one optimization: skip re-fetching model lists if they haven't changed.

In `conf-builder-main.js` line 213, the `renderUI` function does `await utilities.getModelLists()` every time. This fetches from the backend. Cache it:

```javascript
// In conf-builder-main.js, add caching for model lists:
let _cachedModelLists = null;
let _modelListsCacheTime = 0;

this.renderUI = async function () {
    if (!utilities || !configManagement) return;

    // Cache model lists for 5 seconds to avoid redundant fetches during rapid re-renders
    const now = Date.now();
    if (!_cachedModelLists || (now - _modelListsCacheTime) > 5000) {
        const availableLoras = await utilities.getAvailableLoras();
        const loraFolders = await utilities.getLoraFolders();
        await utilities.getModelLists();
        _cachedModelLists = {
            // ... build modelLists object ...
        };
        _modelListsCacheTime = now;
    }
    // ... rest of renderUI using _cachedModelLists ...
};
```

Actually, the simplest high-impact change: the `renderUI` function in `conf-builder-main.js` makes multiple `await` calls to get model lists. These can be parallelized:

```javascript
// Current: sequential awaits (slow)
const availableLoras = await utilities.getAvailableLoras();
const loraFolders = await utilities.getLoraFolders();
const availableSessions = await utilities.getAvailableSessions();
const availableConfigs = await utilities.getAvailableConfigs();
await utilities.getModelLists();

// New: parallel fetches (fast)
const [availableLoras, loraFolders, availableSessions, availableConfigs] = await Promise.all([
    utilities.getAvailableLoras(),
    utilities.getLoraFolders(),
    utilities.getAvailableSessions(),
    utilities.getAvailableConfigs(),
    utilities.getModelLists()
]);
```

**Step 4: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js web/conf_builder/conf-builder-main.js
git commit -m "Optimize builder UI: debounce renderUI, parallelize model list fetches"
```

---

### Task 4: CivitAI Lookup Enhancements

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js` (both modals)
- Modify: `config_builder_node.py` (lookup endpoints)

**Step 1: Add force_refresh support to backend endpoints**

In `config_builder_node.py`, modify both lookup endpoints to accept `force_refresh`:

For the model endpoint (line 816+), after line 820 (`data = await request.json()`):
```python
        force_refresh = data.get("force_refresh", False)
```

Then wrap the cache check (lines 836-851) with:
```python
        if os.path.exists(metadata_file) and not force_refresh:
```

Same pattern for the LoRA endpoint (line 703+).

**Step 2: Add Re-fetch button to cache banner (both modals)**

In the LoRA modal (line 1186-1195), enhance the cache banner:

```javascript
        if (data.cached) {
            const cacheBanner = document.createElement("div");
            cacheBanner.style.cssText = "background: #553300; border: 2px solid #ffaa00; border-radius: 6px; padding: 10px 14px; margin-bottom: 15px; text-align: center;";
            cacheBanner.innerHTML = `
                <div style="font-size: 16px; font-weight: bold; color: #ffaa00;">⚠️ READ FROM DISK CACHE</div>
                <div style="font-size: 12px; color: #ccaa66; margin-top: 4px;">Last looked up on: <strong>${data.cache_date || 'Unknown'}</strong></div>
            `;
            // Re-fetch button
            const refetchBtn = document.createElement("button");
            refetchBtn.className = "cb-button";
            refetchBtn.style.cssText = "margin-top: 8px; background: #664400; border: 1px solid #ffaa00; color: #ffcc44; font-size: 12px; padding: 6px 16px;";
            refetchBtn.textContent = "🔄 Re-fetch from CivitAI Now";
            refetchBtn.onclick = async () => {
                refetchBtn.disabled = true;
                refetchBtn.textContent = "🔄 Fetching...";
                closeModal();
                await showLoraMetadataModal(node, arrayIdx, loraName, true); // pass force_refresh
            };
            cacheBanner.appendChild(refetchBtn);
            content.appendChild(cacheBanner);
        }
```

Update `showLoraMetadataModal` signature to accept `forceRefresh` parameter:
```javascript
async function showLoraMetadataModal(node, arrayIdx, loraName, forceRefresh = false) {
```

And update the fetch call (line 1163-1166) to include it:
```javascript
        body: JSON.stringify({ lora_name: loraName, force_refresh: forceRefresh })
```

Apply the SAME pattern to `showModelMetadataModal` (lines 1340+, 1416-1425).

**Step 3: Add Save JSON button**

Near the existing JSON toggle (line 1287-1300 for models, 1517-1529 for loras), add a save button:

```javascript
        // Save JSON button
        const saveJsonBtn = document.createElement("button");
        saveJsonBtn.className = "cb-button";
        saveJsonBtn.style.cssText = "margin-bottom: 8px; margin-left: 8px; background: #333; border-left: 3px solid #44aa44;";
        saveJsonBtn.textContent = "💾 Save JSON Response";
        saveJsonBtn.onclick = () => {
            const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${loraName.replace(/[/\\]/g, "_")}_civitai_metadata.json`;
            a.click();
            URL.revokeObjectURL(url);
        };
        jsonSection.appendChild(saveJsonBtn);
```

**Step 4: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js config_builder_node.py
git commit -m "Enhance CivitAI modals: re-fetch button, save JSON, force_refresh"
```

---

### Task 5: Dashboard Prompt Toggle

**Files:**
- Modify: `image_generation.py:356-367` (create_image_metadata)
- Modify: `resources/template.html:286-294` (add toggle)
- Modify: `resources/logic_ui.js:831-837` (prompt display)
- Modify: `resources/logic_pipeline.js:291-307` (filter logic)

**Step 1: Store raw config prompt in metadata**

In `image_generation.py` `create_image_metadata()`, preserve the raw config prompts before they get overwritten. Add before line 356 (the `update_dict`):

```python
    # Preserve raw config prompts (without trigger words) for dashboard toggle
    meta["config_positive"] = config.get("positive", "")
    meta["config_negative"] = config.get("negative", "")
```

These get added to the meta dict BEFORE `meta.update(update_dict)` overwrites `positive` and `negative` with the trigger-appended versions.

**Step 2: Add toggle to dashboard template**

In `resources/template.html`, after line 279 (the FILTERS section title), add a toggle:

```html
                <div style="margin-bottom: 8px; padding: 4px 0;">
                    <label style="display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 11px; color: #aaa;">
                        <input type="checkbox" id="toggle-triggers" checked
                            style="cursor: pointer;"
                            onchange="if(typeof toggleTriggerWords==='function') toggleTriggerWords(this.checked)">
                        Show Lora Trigger Words in Prompts
                    </label>
                </div>
```

**Step 3: Update prompt display in logic_ui.js**

In `resources/logic_ui.js`, modify lines 836-837:

```javascript
    // Check trigger word toggle
    const showTriggers = document.getElementById('toggle-triggers')?.checked !== false;
    if (posEl) posEl.value = showTriggers
        ? (d.positive || meta.positive || "")
        : (d.config_positive || d.positive || meta.positive || "");
    if (negEl) negEl.value = showTriggers
        ? (d.negative || meta.negative || "")
        : (d.config_negative || d.negative || meta.negative || "");
```

**Step 4: Update filter logic in logic_pipeline.js**

In `resources/logic_pipeline.js`, modify lines 304-305 to respect the toggle:

```javascript
            const showTriggers = document.getElementById('toggle-triggers')?.checked !== false;
            if (filters.positive.size > 0) {
                const posValue = showTriggers
                    ? (d.positive || meta.positive || "")
                    : (d.config_positive || d.positive || meta.positive || "");
                if (!filters.positive.has(posValue)) return false;
            }
            if (filters.negative.size > 0) {
                const negValue = showTriggers
                    ? (d.negative || meta.negative || "")
                    : (d.config_negative || d.negative || meta.negative || "");
                if (!filters.negative.has(negValue)) return false;
            }
```

**Step 5: Update filter button generation in logic_ui.js**

In `resources/logic_ui.js` `initFilters()` (lines 145-152), update the positive/negative value extraction:

```javascript
    const showTriggers = document.getElementById('toggle-triggers')?.checked !== false;
    // ... inside the forEach ...
    if (key === 'positive') return showTriggers
        ? (d.positive || meta.positive || "")
        : (d.config_positive || d.positive || meta.positive || "");
    if (key === 'negative') return showTriggers
        ? (d.negative || meta.negative || "")
        : (d.config_negative || d.negative || meta.negative || "");
```

**Step 6: Add toggleTriggerWords function in logic_ui.js**

```javascript
function toggleTriggerWords(showTriggers) {
    // Rebuild filters with new prompt mode
    initFilters();
    updateDataPipeline();
    // If modal is open, refresh prompt display
    if (window.currentModalId) {
        openM(window.currentModalId);
    }
}
```

**Step 7: Commit**

```bash
git add image_generation.py resources/template.html resources/logic_ui.js resources/logic_pipeline.js
git commit -m "Add dashboard toggle to show/hide trigger words in prompts"
```

---

### Task 6: Custom Lora Trigger Word Editor

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js` (add button + modal)
- Modify: `config_builder_node.py` (new endpoints)

**Step 1: Add backend endpoints**

In `config_builder_node.py`, after the existing route handlers (after line ~940), add:

```python
@server.PromptServer.instance.routes.get("/configbuilder/get_lora_triggers")
async def get_lora_triggers_endpoint(request):
    """Get trigger words for a specific LoRA from loras_tags.json"""
    try:
        lora_name = request.query.get("lora_name", "")
        if not lora_name:
            return web.json_response({"error": "Missing lora_name"}, status=400)

        json_tags_path = os.path.join(folder_paths.get_output_directory(), "benchmarks/loras_tags.json")
        triggers = []
        if os.path.exists(json_tags_path):
            from .lora_utils import load_json_from_file
            lora_tags = load_json_from_file(json_tags_path) or {}
            # Try exact match, normalized, and backslash variants
            normalized = lora_name.replace("\\", "/")
            backslash = lora_name.replace("/", "\\")
            triggers = lora_tags.get(lora_name, lora_tags.get(normalized, lora_tags.get(backslash, [])))

        return web.json_response({"lora_name": lora_name, "triggers": triggers})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@server.PromptServer.instance.routes.post("/configbuilder/save_lora_triggers")
async def save_lora_triggers_endpoint(request):
    """Save edited trigger words for a LoRA to loras_tags.json"""
    try:
        data = await request.json()
        lora_name = data.get("lora_name", "")
        triggers = data.get("triggers", [])

        if not lora_name:
            return web.json_response({"error": "Missing lora_name"}, status=400)

        json_tags_path = os.path.join(folder_paths.get_output_directory(), "benchmarks/loras_tags.json")
        from .lora_utils import load_json_from_file, save_dict_to_json
        lora_tags = {}
        if os.path.exists(json_tags_path):
            lora_tags = load_json_from_file(json_tags_path) or {}

        # Normalize the name for consistent storage
        normalized = lora_name.replace("\\", "/")
        lora_tags[normalized] = triggers

        save_dict_to_json(lora_tags, json_tags_path)

        # Clear the trigger word LRU cache so changes take effect immediately
        from .trigger_words import clear_trigger_caches
        clear_trigger_caches()

        print(f"[ConfigBuilder] ✏️ Saved {len(triggers)} trigger words for: {normalized}")
        return web.json_response({"status": "saved", "lora_name": normalized, "triggers": triggers})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
```

**Step 2: Add "Edit Triggers" button to lora card**

In `conf-builder-config-management.js`, after line 1056 (the existing LoRA metadata button), add:

```javascript
        // 4. Edit Trigger Words Button
        const editTriggersBtn = document.createElement("button");
        editTriggersBtn.className = "cb-button";
        editTriggersBtn.style.cssText = `width: 100%; background: linear-gradient(135deg, #336633, #446644); border-left: 4px solid #66cc66; margin-top: 4px;`;
        editTriggersBtn.textContent = "✏️ Edit Trigger Words";
        editTriggersBtn.onclick = async () => await showEditTriggersModal(node, arrayIdx, parsed.name);
        moreOptionsContent.appendChild(editTriggersBtn);
```

**Step 3: Create the trigger word editor modal**

Add this function near the other modal functions (after `showLoraMetadataModal` or `showModelMetadataModal`):

```javascript
async function showEditTriggersModal(node, arrayIdx, loraName) {
    // Build modal overlay (same pattern as metadata modals)
    const overlay = document.createElement("div");
    overlay.style.cssText = "position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); z-index: 10000; display: flex; align-items: center; justify-content: center;";

    const modal = document.createElement("div");
    modal.style.cssText = "background: #1a1a1a; border: 2px solid #66cc66; border-radius: 12px; padding: 25px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; position: relative;";

    const closeModal = () => { document.body.removeChild(overlay); };
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
    document.addEventListener("keydown", function escHandler(e) {
        if (e.key === "Escape") { closeModal(); document.removeEventListener("keydown", escHandler); }
    });

    // Close X button
    const closeX = document.createElement("button");
    closeX.textContent = "✕";
    closeX.style.cssText = "position: absolute; top: 10px; right: 15px; background: none; border: none; color: #ff4444; font-size: 20px; cursor: pointer;";
    closeX.onclick = closeModal;
    modal.appendChild(closeX);

    // Title
    const title = document.createElement("h3");
    title.textContent = "✏️ Edit Trigger Words";
    title.style.cssText = "margin: 0 0 5px 0; color: #66cc66;";
    modal.appendChild(title);

    const subtitle = document.createElement("div");
    subtitle.style.cssText = "font-size: 12px; color: #888; margin-bottom: 15px;";
    subtitle.textContent = loraName.split('/').pop();
    modal.appendChild(subtitle);

    const status = document.createElement("div");
    status.textContent = "🔄 Loading trigger words...";
    status.style.cssText = "margin-bottom: 15px; color: #aaa; font-size: 12px;";
    modal.appendChild(status);

    const chipsContainer = document.createElement("div");
    chipsContainer.style.cssText = "display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 15px; min-height: 30px; padding: 8px; background: #111; border: 1px solid #333; border-radius: 6px;";
    modal.appendChild(chipsContainer);

    // Input row
    const inputRow = document.createElement("div");
    inputRow.style.cssText = "display: flex; gap: 6px; margin-bottom: 15px;";
    const input = document.createElement("input");
    input.className = "cb-input";
    input.type = "text";
    input.placeholder = "Add new trigger word...";
    input.style.cssText = "flex: 1; padding: 6px 10px; font-size: 12px;";
    const addWordBtn = document.createElement("button");
    addWordBtn.className = "cb-button primary";
    addWordBtn.textContent = "+ Add";
    addWordBtn.style.cssText = "padding: 6px 12px; font-size: 12px;";
    inputRow.appendChild(input);
    inputRow.appendChild(addWordBtn);
    modal.appendChild(inputRow);

    // Button row
    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px;";

    const saveBtn = document.createElement("button");
    saveBtn.className = "cb-button";
    saveBtn.style.cssText = "background: #336633; border: 1px solid #66cc66; color: #88ff88; padding: 8px 20px;";
    saveBtn.textContent = "💾 Save";

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "cb-button";
    cancelBtn.style.cssText = "background: #333; color: #aaa; padding: 8px 20px;";
    cancelBtn.textContent = "Cancel";
    cancelBtn.onclick = closeModal;

    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    modal.appendChild(btnRow);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // State
    let currentTriggers = [];

    function renderTriggerChips() {
        chipsContainer.innerHTML = "";
        if (currentTriggers.length === 0) {
            const empty = document.createElement("span");
            empty.style.cssText = "color: #666; font-size: 11px; font-style: italic;";
            empty.textContent = "No trigger words";
            chipsContainer.appendChild(empty);
            return;
        }
        currentTriggers.forEach((trigger, idx) => {
            const chip = document.createElement("span");
            chip.style.cssText = "background: #224422; border: 1px solid #448844; color: #aaffaa; padding: 3px 8px; border-radius: 12px; font-size: 11px; display: flex; align-items: center; gap: 4px;";
            chip.textContent = trigger;
            const removeBtn = document.createElement("span");
            removeBtn.textContent = "×";
            removeBtn.style.cssText = "cursor: pointer; color: #ff6666; font-weight: bold; margin-left: 2px;";
            removeBtn.onclick = () => {
                currentTriggers.splice(idx, 1);
                renderTriggerChips();
            };
            chip.appendChild(removeBtn);
            chipsContainer.appendChild(chip);
        });
    }

    function addTriggerWord() {
        const word = input.value.trim();
        if (word && !currentTriggers.includes(word)) {
            currentTriggers.push(word);
            renderTriggerChips();
            input.value = "";
        }
        input.focus();
    }

    addWordBtn.onclick = addTriggerWord;
    input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); addTriggerWord(); } };

    saveBtn.onclick = async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = "💾 Saving...";
        try {
            const resp = await fetch("/configbuilder/save_lora_triggers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lora_name: loraName, triggers: currentTriggers })
            });
            if (resp.ok) {
                status.textContent = "✅ Trigger words saved!";
                status.style.color = "#66ff66";
                setTimeout(closeModal, 800);
            } else {
                const err = await resp.json();
                status.textContent = "❌ Error: " + (err.error || "Save failed");
                status.style.color = "#ff6666";
                saveBtn.disabled = false;
                saveBtn.textContent = "💾 Save";
            }
        } catch (e) {
            status.textContent = "❌ Error: " + e.message;
            status.style.color = "#ff6666";
            saveBtn.disabled = false;
            saveBtn.textContent = "💾 Save";
        }
    };

    // Fetch current triggers
    try {
        const resp = await fetch(`/configbuilder/get_lora_triggers?lora_name=${encodeURIComponent(loraName)}`);
        if (resp.ok) {
            const data = await resp.json();
            currentTriggers = data.triggers || [];
            status.textContent = `Loaded ${currentTriggers.length} trigger word(s)`;
            status.style.color = "#88ff88";
        } else {
            status.textContent = "⚠️ No triggers found (you can add new ones)";
            status.style.color = "#ffaa00";
        }
    } catch (e) {
        status.textContent = "⚠️ Could not load triggers: " + e.message;
        status.style.color = "#ffaa00";
    }
    renderTriggerChips();
    input.focus();
}
```

**Step 4: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('config_builder_node.py', doraise=True)"`

**Step 5: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js config_builder_node.py
git commit -m "Add custom lora trigger word editor with modal UI and backend endpoints"
```

---

### Task 7: Sampler/Scheduler Instant Add (Verification)

**Files:**
- Verify: `web/conf_builder/conf-builder-config-management.js:239-246`

**Step 1: Verify behavior**

The `createChipListBuilder` function already adds items on dropdown `onchange` (line 239). It does NOT call `renderUI()`. Verify this still works after the debouncing changes from Task 3. No code changes expected — this is a verification task.

**Step 2: Commit (only if changes needed)**

No commit expected unless issues found.

---

### Task 8: Sync to Main Working Directory

**Step 1: Verify all changes compile**

```bash
python -c "import py_compile; py_compile.compile('metadata_packer.py', doraise=True)"
python -c "import py_compile; py_compile.compile('config_builder_node.py', doraise=True)"
python -c "import py_compile; py_compile.compile('image_generation.py', doraise=True)"
```

**Step 2: Fast-forward merge to main**

```bash
cd Z:\comfy_v0.12.3\ComfyUI\custom_nodes\ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite
git merge claude/upbeat-jackson --ff-only
```

---

## Summary

| Task | Scope | Files | Estimated Steps |
|------|-------|-------|----------------|
| 1. Model hashing bug | Small | metadata_packer.py | 4 |
| 2. VAE/TE on/off fix | Small | conf-builder-utilities.js | 3 |
| 3. Performance | Medium | conf-builder-config-management.js, conf-builder-main.js | 4 |
| 4. CivitAI enhancements | Medium | conf-builder-config-management.js, config_builder_node.py | 4 |
| 5. Dashboard prompt toggle | Medium | image_generation.py, template.html, logic_ui.js, logic_pipeline.js | 7 |
| 6. Trigger word editor | Large | conf-builder-config-management.js, config_builder_node.py | 5 |
| 7. Sampler/scheduler verify | Tiny | (verification only) | 1 |
| 8. Sync to main | Tiny | git operations | 2 |
