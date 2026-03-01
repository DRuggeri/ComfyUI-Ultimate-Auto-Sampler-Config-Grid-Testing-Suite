# Builder UI Improvements — Design Document

**Date:** 2026-02-28
**Scope:** 9 items — performance, bug fixes, and feature enhancements

## Critical Constraint

DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

## 1. Performance Optimization (Builder UI Slow Everywhere)

### Problem
`renderUI()` does a full DOM rebuild on every state change. There are 30+ call sites across `conf-builder-config-management.js` that trigger complete re-renders after single-item interactions (toggle, add, remove, dropdown change). This makes the UI sluggish on initial load AND on every interaction.

### Solution: Eliminate unnecessary full re-renders
- **On/off toggles**: Already update DOM inline (opacity/filter). Remove any `node.renderUI()` calls following toggle actions — the visual update is already done.
- **Add model/lora/VAE**: After creating the new item in state, create its DOM element directly and `appendChild()` it to the container. Skip `renderUI()`.
- **Remove model/lora/VAE**: Remove the specific DOM element from the parent container. Skip `renderUI()`.
- **Dropdown changes** (model type, model selection, LoRA selection): Update only the affected card's content. Skip `renderUI()`.
- **Collapse/expand**: Already handled inline — verify no re-render follows.
- **Chip list builders** (samplers, schedulers): Already DON'T call `renderUI()` — no change needed.
- **Bulk operations** (load session, add config, delete config, duplicate config): Keep `renderUI()` — these legitimately change entire UI structure.

### Approach for add/remove operations
Each `renderUI()` call after an add operation follows this pattern:
```javascript
// Current: add to state then rebuild everything
node.state.config_arrays[arrayIdx].models.push(newModel);
node.saveState();
node.renderUI();

// New: add to state then append just the new element
node.state.config_arrays[arrayIdx].models.push(newModel);
node.saveState();
const newElement = createModelElement(node, newModel, arrayIdx, newIdx, modelLists);
modelsContainer.appendChild(newElement);
```

For remove operations:
```javascript
// Current: remove from state then rebuild everything
node.state.config_arrays[arrayIdx].models.splice(idx, 1);
node.saveState();
node.renderUI();

// New: remove from state then remove DOM element
node.state.config_arrays[arrayIdx].models.splice(idx, 1);
node.saveState();
element.parentNode.removeChild(element);
```

### Key files
- `web/conf_builder/conf-builder-config-management.js` — all 30+ `renderUI()` call sites

---

## 2. VAE & Text Encoder On/Off Switches (Bug Fix + Cleanup)

### Problem
VAE on/off switches exist in the UI but user reports they "don't work." Additionally, `vae_bypass_states` and `te_bypass_states` are being output as separate fields in the `config_json` output (lines 586-594 in `conf-builder-utilities.js`), which is unnecessary — they should only control filtering.

### Root Cause
The bypass states are internal UI state that controls which items are included. The filtering in `convertStateToConfigs()` at line 500 already works:
```javascript
const vaes = (configArray.vaes || []).filter(v => v && v !== "None" && !configArray.vae_bypass_states?.[v]);
```
But the bypass state dicts are ALSO being added to the output config (lines 586-594), polluting the JSON output. Additionally, the bypass states may not be persisted properly across sessions.

### Fix
1. **Remove** lines 586-594 in `conf-builder-utilities.js` that output `vae_bypass_states` and `te_bypass_states` to config JSON — these are UI-internal, not config parameters
2. **Verify** the bypass toggle onclick handler properly persists via `node.saveState()`
3. **Verify** bypass states survive load/save session cycles (check migration in `loadSession`)
4. Ensure `convertConfigsToConfigArrays()` preserves bypass states when loading

### Key files
- `web/conf_builder/conf-builder-utilities.js` lines 586-594 (remove output), line 500 (VAE filter), line 545 (TE filter)
- `web/conf_builder/conf-builder-config-management.js` — VAE element (line 2277+), TE section (line 1664+)

---

## 3. Model Hashing Bug Fix

### Problem
Console shows `"Using fallback hash for model: 559ad07aae"` — models from the builder UI aren't getting proper SHA256 hashes.

### Root Cause
In `metadata_packer.py` line 145-175, `find_model_file()` only searches `checkpoints` and `loras` folder paths. It **never checks `diffusion_models` or `unet` folders**. When a diffusion model is used, the file isn't found, and a filename-based hash is generated instead (line 268-272).

### Fix
Add `diffusion_models` and `unet` to the search paths in `find_model_file()`:
```python
search_paths = [
    folder_paths.get_folder_paths("checkpoints")[0] if folder_paths.get_folder_paths("checkpoints") else None,
    folder_paths.get_folder_paths("loras")[0] if folder_paths.get_folder_paths("loras") else None,
    folder_paths.get_folder_paths("diffusion_models")[0] if folder_paths.get_folder_paths("diffusion_models") else None,
    folder_paths.get_folder_paths("unet")[0] if folder_paths.get_folder_paths("unet") else None,
]
```

Also consider using `folder_paths.get_full_path()` which handles all model types, as a secondary fallback before the filename hash.

### Key files
- `metadata_packer.py` lines 145-175 (`find_model_file()`), lines 260-272 (fallback hash)

---

## 4. Dashboard Prompt Toggle (Hide Trigger Words)

### Problem
Dashboard always shows prompts WITH lora trigger words appended. When comparing prompts across different loras, the trigger words create visual noise and apparent duplicates.

### Solution
Store the raw config prompt (without triggers) alongside the final prompt in the manifest. Add a toggle in the dashboard to switch between views.

### Implementation
1. **In `image_generation.py` `create_image_metadata()`**: Before overwriting `positive` with `actual_positive_prompt`, preserve the raw config prompt:
   ```python
   meta["config_positive"] = config.get("positive", "")
   meta["config_negative"] = config.get("negative", "")
   meta.update(update_dict)  # This overwrites "positive" with actual_positive_prompt
   ```

2. **In `resources/template.html`**: Add a toggle checkbox near the prompt filter area:
   ```html
   <label><input type="checkbox" id="toggle-triggers" checked> Show Trigger Words</label>
   ```

3. **In `resources/logic_ui.js`** line 836-837: Check toggle state when displaying prompts:
   ```javascript
   const showTriggers = document.getElementById('toggle-triggers')?.checked !== false;
   if (posEl) posEl.value = showTriggers ? (d.positive || meta.positive || "") : (d.config_positive || d.positive || meta.positive || "");
   ```

4. **In filter buttons**: When toggle is off, filter by `config_positive` instead of `positive`

### Key files
- `image_generation.py` line 356-367 (`create_image_metadata`)
- `resources/template.html` line 287-294 (filter area)
- `resources/logic_ui.js` line 831-837 (prompt display)

---

## 5. CivitAI Lookup Enhancements

### Current State
- Cache warning banner exists (lines 1186-1195) with orange styling
- Full JSON toggle exists (lines 1287-1300) for models and (lines 1517-1529) for loras
- Cache date shown from `data.cache_date`

### Enhancements Needed
1. **Bigger cache warning**: Move to very top of modal, increase font size, add a red/orange gradient border
2. **Re-check button**: Add "Re-fetch from CivitAI" button inside the cache banner. Calls the same endpoint with `force_refresh=true` parameter
3. **Save JSON button**: Add "Save JSON Response" button next to the JSON toggle. Downloads the JSON as a `.json` file using `Blob` + `URL.createObjectURL()`
4. **Backend `force_refresh` support**: In the CivitAI lookup endpoint in `config_builder_node.py`, accept `force_refresh` parameter that skips disk cache and re-fetches from API

### Key files
- `web/conf_builder/conf-builder-config-management.js` — model modal (line 1112+), lora modal (line 1375+)
- `config_builder_node.py` — CivitAI lookup endpoints

---

## 6. Sampler/Scheduler Instant Add (Verification)

### Current State
The `onchange` handler in `createChipListBuilder()` (line 239) already adds items immediately when a dropdown option is selected. The Add button is redundant.

### Action Needed
Verify that no `renderUI()` call follows the chip addition that would cause perceived lag. The `createChipListBuilder` function correctly uses local `renderChips()` + `populateSelect()` without triggering a full re-render. If there's still lag, it's from the performance issue (Item 1) affecting other interactions.

### Key files
- `web/conf_builder/conf-builder-config-management.js` lines 159-283

---

## 7. Custom Lora Trigger Word Editor

### Design
A dedicated modal accessible from each lora card via an "Edit Triggers" button.

### UI
- Button: "✏️ Edit Triggers" on each lora card, next to the existing "🔍 Lookup LoRA Metadata from CivitAI" button
- Modal contains:
  - Header: "Edit Trigger Words — {lora_name}"
  - Current triggers displayed as editable chips (each with × remove button)
  - Text input field + Enter/Add button to add new trigger words
  - "Save" button (saves to `loras_tags.json`) and "Cancel" button
  - "Reset to CivitAI" button that re-fetches from API and replaces custom edits

### Backend
- New endpoint: `POST /configbuilder/save_lora_triggers`
  - Request body: `{ "lora_name": "...", "triggers": ["word1", "word2"] }`
  - Reads `loras_tags.json`, updates the entry, writes back
  - Clears the trigger word LRU cache after save
- New endpoint: `GET /configbuilder/get_lora_triggers?lora_name=...`
  - Returns current triggers from `loras_tags.json`

### Data flow
- `loras_tags.json` format: `{ "lora_name.safetensors": ["trigger1", "trigger2"] }`
- Editor reads from and writes to this file
- Trigger word cache (`@lru_cache`) cleared after save so changes take effect immediately

### Key files
- `web/conf_builder/conf-builder-config-management.js` — new modal + button on lora card
- `config_builder_node.py` — new endpoints
- `lora_utils.py` — `loras_tags.json` read/write
- `trigger_words.py` — cache clearing

---

## Implementation Order

Recommended order (dependencies + quick wins first):

1. **Model hashing bug** — smallest change, standalone fix
2. **VAE & TE on/off switches** — small fix, verifiable immediately
3. **Performance optimization** — foundational, makes everything else feel better
4. **Sampler/scheduler instant add** — verification only after perf fix
5. **CivitAI lookup enhancements** — moderate scope, self-contained
6. **Dashboard prompt toggle** — touches backend + frontend, needs manifest change
7. **Custom lora trigger word editor** — largest new feature, self-contained

Total estimated scope: ~15-20 implementation tasks across 8-10 files.
