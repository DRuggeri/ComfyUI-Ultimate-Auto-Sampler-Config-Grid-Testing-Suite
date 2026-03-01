# Per-Config Resolutions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-config resolution support to the Builder UI with a categorized preset dropdown, flowing through configs_json to override the sampler's resolutions_json on a per-config basis.

**Architecture:** Each config array gains a `resolutions` array (e.g., `["1024x1024", "832x1216"]`). The UI uses an `<optgroup>`-based dropdown categorized by model type and orientation plus a custom W×H input. Resolutions flow through `configs_json` as `[[w,h],...]`, get expanded into the Cartesian product in `expand_configs()`, and override the sampler's global `resolutions_json` in the generation loop.

**Tech Stack:** Vanilla JS (ComfyUI widget), Python (config expansion + generation loop)

**Critical constraint:** DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

### Task 1: State Migration — Add `resolutions` to Config Arrays

**Files:**
- Modify: `web/conf_builder/conf-builder-main.js:392-397` (migration block)

**Step 1: Add migration for resolutions field**

In the per-config-array migration block (around line 397, after the `attention_modes` migration), add:

```javascript
if (!arr.resolutions) arr.resolutions = [];
```

This follows the exact pattern of `if (!arr.attention_modes) arr.attention_modes = ["default"];` at line 397.

**Step 2: Verify by checking the file**

Confirm the new line sits inside the `this.state.config_arrays.forEach(arr => { ... })` block, after the existing migrations.

**Step 3: Commit**

```
feat: add resolutions field migration for config arrays
```

---

### Task 2: Resolution Chip Builder UI

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js`
  - New function `createResolutionBuilder()` (after `createChipListBuilder` ~line 270)
  - Render call after Attention builder (~line 362)

**Step 1: Define the preset resolution data**

Add this constant near the top of the file (after imports, ~line 20):

```javascript
const RESOLUTION_PRESETS = [
    { group: "SD 1.5 — Square",    items: ["512x512"] },
    { group: "SD 1.5 — Portrait",  items: ["512x896", "512x768"] },
    { group: "SD 1.5 — Landscape", items: ["896x512", "768x512"] },
    { group: "SDXL — Square",      items: ["1024x1024"] },
    { group: "SDXL — Portrait",    items: ["768x1344", "832x1216", "896x1152"] },
    { group: "SDXL — Landscape",   items: ["1344x768", "1216x832", "1152x896"] },
    { group: "Flux — Square",      items: ["1024x1024"] },
    { group: "Flux — Portrait",    items: ["768x1344", "832x1216"] },
    { group: "Flux — Landscape",   items: ["1344x768", "1216x832"] },
];
```

**Step 2: Create the `createResolutionBuilder()` function**

Add after `createChipListBuilder` (~line 270). This function creates:
- Chip display area (same pattern as `createChipListBuilder`)
- `<select>` with `<optgroup>` categories populated from `RESOLUTION_PRESETS`
- Custom W × H number inputs with Add button
- Clear button

```javascript
function createResolutionBuilder({ node, arrayIdx, configArray }) {
    const container = document.createElement("div");
    container.style.cssText = "width: 100%; margin-bottom: 2px;";

    // Ensure array exists
    if (!Array.isArray(configArray.resolutions)) {
        configArray.resolutions = [];
        node.state.config_arrays[arrayIdx].resolutions = [];
    }

    // ===== CHIPS DISPLAY =====
    const chipsContainer = document.createElement("div");
    chipsContainer.style.cssText = "display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; min-height: 24px;";

    const renderChips = () => {
        chipsContainer.innerHTML = "";
        const items = configArray.resolutions;

        if (!items || items.length === 0) {
            const ph = document.createElement("div");
            ph.textContent = "Using sampler node resolutions";
            ph.style.cssText = "color: #666; font-style: italic; padding: 2px 4px; font-size: 11px;";
            chipsContainer.appendChild(ph);
            return;
        }

        items.forEach((item, idx) => {
            const chip = document.createElement("div");
            chip.style.cssText = "display: flex; align-items: center; background: #554400; color: #ffcc44; border-radius: 12px; padding: 2px 8px; font-size: 11px; border: 1px solid #886600;";

            const text = document.createElement("span");
            text.textContent = item;
            chip.appendChild(text);

            const closeBtn = document.createElement("span");
            closeBtn.textContent = "×";
            closeBtn.style.cssText = "margin-left: 6px; cursor: pointer; color: #ff8888; font-weight: bold;";
            closeBtn.onclick = () => {
                node.state.config_arrays[arrayIdx].resolutions.splice(idx, 1);
                node.saveState();
                renderChips();
                populateSelect();
            };
            chip.appendChild(closeBtn);
            chipsContainer.appendChild(chip);
        });
    };
    renderChips();
    container.appendChild(chipsContainer);

    // ===== PRESET DROPDOWN =====
    const inputRow = document.createElement("div");
    inputRow.style.cssText = "display: flex; gap: 4px; align-items: center;";

    const select = document.createElement("select");
    select.className = "cb-select";
    select.style.cssText = "flex: 1; font-size: 11px; padding: 3px 4px;";

    const populateSelect = () => {
        select.innerHTML = "";
        const currentItems = configArray.resolutions || [];

        // Placeholder option
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Add resolution...";
        placeholder.disabled = true;
        placeholder.selected = true;
        select.appendChild(placeholder);

        // Optgroups from presets
        for (const preset of RESOLUTION_PRESETS) {
            const available = preset.items.filter(r => !currentItems.includes(r));
            if (available.length === 0) continue;

            const optgroup = document.createElement("optgroup");
            optgroup.label = preset.group;
            for (const res of available) {
                const opt = document.createElement("option");
                opt.value = res;
                opt.textContent = res.replace("x", " × ");
                optgroup.appendChild(opt);
            }
            select.appendChild(optgroup);
        }
    };
    populateSelect();

    // Add on selection change (instant add)
    select.onchange = () => {
        const val = select.value;
        if (val && !configArray.resolutions.includes(val)) {
            node.state.config_arrays[arrayIdx].resolutions.push(val);
            node.saveState();
            renderChips();
            populateSelect();
        }
    };

    inputRow.appendChild(select);

    // ===== CUSTOM W x H INPUT =====
    const customW = document.createElement("input");
    customW.type = "number";
    customW.className = "cb-input";
    customW.placeholder = "W";
    customW.style.cssText = "width: 55px; font-size: 11px; padding: 3px 4px;";
    customW.min = 64;
    customW.max = 8192;
    customW.step = 8;

    const xLabel = document.createElement("span");
    xLabel.textContent = "×";
    xLabel.style.cssText = "color: #888; font-size: 11px;";

    const customH = document.createElement("input");
    customH.type = "number";
    customH.className = "cb-input";
    customH.placeholder = "H";
    customH.style.cssText = "width: 55px; font-size: 11px; padding: 3px 4px;";
    customH.min = 64;
    customH.max = 8192;
    customH.step = 8;

    const addCustomBtn = document.createElement("button");
    addCustomBtn.className = "cb-button primary";
    addCustomBtn.textContent = "+";
    addCustomBtn.title = "Add custom resolution";
    addCustomBtn.style.cssText = "padding: 3px 8px; font-size: 11px; min-width: 28px;";
    addCustomBtn.onclick = () => {
        const w = parseInt(customW.value);
        const h = parseInt(customH.value);
        if (w > 0 && h > 0) {
            const res = `${w}x${h}`;
            if (!configArray.resolutions.includes(res)) {
                node.state.config_arrays[arrayIdx].resolutions.push(res);
                node.saveState();
                renderChips();
                populateSelect();
            }
            customW.value = "";
            customH.value = "";
        }
    };

    // Clear all button
    const clearBtn = document.createElement("button");
    clearBtn.className = "cb-button";
    clearBtn.textContent = "Clear";
    clearBtn.title = "Remove all resolutions";
    clearBtn.style.cssText = "padding: 3px 8px; font-size: 11px; min-width: 40px; color: #ff8888;";
    clearBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].resolutions = [];
        configArray.resolutions = [];
        node.saveState();
        renderChips();
        populateSelect();
    };

    inputRow.appendChild(customW);
    inputRow.appendChild(xLabel);
    inputRow.appendChild(customH);
    inputRow.appendChild(addCustomBtn);
    inputRow.appendChild(clearBtn);
    container.appendChild(inputRow);

    return container;
}
```

**Step 3: Add the resolution builder to the render flow**

After the Attention builder block (line 362, after `settingsGrid.appendChild(createInputGroup("Attention", attentionBuilder));`), add:

```javascript
    // Resolutions - categorized preset dropdown + custom input + chips
    const resolutionBuilder = createResolutionBuilder({ node, arrayIdx, configArray });
    settingsGrid.appendChild(createInputGroup("Resolutions", resolutionBuilder));
```

**Step 4: Update iteration count**

In `conf-builder-utilities.js`, in `getIterationCount()` (~line 470-473), add resolution count and include it in the product:

After line 471 (`const a_count = ...`), add:
```javascript
    // 7. Resolutions (per-config overrides)
    const r_count = (configArray.resolutions && configArray.resolutions.length > 0) ? configArray.resolutions.length : 1;
```

Update the return (line 473) to include `* r_count`:
```javascript
    return m_count * l_count * v_count * s_count * sch_count * st_count * c_count * p_count * a_count * r_count;
```

**Step 5: Commit**

```
feat: add resolution chip builder UI with categorized presets
```

---

### Task 3: Config JSON Output — Add Resolutions to `convertStateToConfigs()`

**Files:**
- Modify: `web/conf_builder/conf-builder-utilities.js:478-596` (`convertStateToConfigs`)

**Step 1: Add resolutions to config output**

In `convertStateToConfigs()`, after the attention_mode block (~line 514), add:

```javascript
        // Per-config resolutions (override sampler's resolutions_json)
        if (configArray.resolutions && configArray.resolutions.length > 0) {
            config.resolutions = configArray.resolutions.map(r => {
                const parts = r.split("x").map(Number);
                return [parts[0], parts[1]];
            });
        }
```

This outputs `"resolutions": [[1024, 1024], [832, 1216]]` — same format as `resolutions_json`.

**Step 2: Commit**

```
feat: output per-config resolutions in configs_json
```

---

### Task 4: Config Expansion — Add Resolutions to Cartesian Product

**Files:**
- Modify: `config_utils.py:364-615` (`expand_configs`)

**Step 1: Extract resolutions from config entry**

After line 496 (attention_modes extraction), add:

```python
        # Per-config resolutions (override sampler's resolutions_json when present)
        raw_resolutions = entry.get("resolutions", None)
        if raw_resolutions and isinstance(raw_resolutions, list) and len(raw_resolutions) > 0:
            config_resolutions = [tuple(r) for r in raw_resolutions]  # [(w, h), ...]
        else:
            config_resolutions = [None]  # Single None = no override, use global resolutions
```

**Step 2: Add resolutions to the itertools.product call**

Modify the `itertools.product` call (line 548-553) to include `config_resolutions`:

Add `config_resolutions` to the end of the product arguments:
```python
        for combo in itertools.product(samplers, schedulers, steps_l, cfgs, clip_skips, expanded_loras,
                                      denoise_values, entry_prompt_pairs, expanded_models, raw_vaes,
                                      attention_modes, model_sampling_overrides, model_sampling_shifts,
                                      flux_max_shifts, flux_base_shifts,
                                      advanced_sampling_values, advanced_guiders, advanced_schedulers,
                                      flux_guidance_values, config_resolutions):
```

**Step 3: Add resolution to the combo dict**

After line 594 (`"flux_guidance_value": combo[18],`), add:

```python
                "resolution": combo[19],  # (w, h) tuple or None
```

**Step 4: Commit**

```
feat: expand per-config resolutions in Cartesian product
```

---

### Task 5: Generation Loop — Per-Config Resolution Override

**Files:**
- Modify: `generation_orchestrator.py` (main generation loop, ~lines 376-382 and 617-621)

**Step 1: Fix total job count calculation**

Replace lines 376-382 with resolution-aware counting:

```python
    input_jobs = prepare_input_jobs(optional_latent, resolutions)

    # Count total jobs: configs with per-config resolutions provide their own
    # width/height and don't multiply with the global input_jobs.
    configs_with_res = sum(1 for c in expanded if c.get("resolution") is not None)
    configs_without_res = len(expanded) - configs_with_res
    total_jobs = configs_with_res + (configs_without_res * len(input_jobs))

    print(f"{'='*80}")
    print(f"[GridTester] 🚀 GENERATION START")
    if configs_with_res > 0:
        print(f"[GridTester] 📋 {configs_with_res} configs with per-config resolutions + "
              f"{configs_without_res} configs × {len(input_jobs)} resolutions = {total_jobs} total jobs")
    else:
        print(f"[GridTester] 📋 {len(expanded)} configs × {len(input_jobs)} resolutions = {total_jobs} total jobs")
    print(f"{'='*80}")
```

**Step 2: Add per-config resolution override in the generation loop**

At the start of the inner loop body (~line 621, after `for conf_idx, conf in enumerate(expanded):`), add:

```python
            # Per-config resolution override: if this config has its own resolution,
            # use it instead of the global input_job's resolution. Only process once
            # (at job_idx == 0) to avoid duplicating work across input_jobs.
            if conf.get("resolution") is not None:
                if job_idx > 0:
                    continue  # Already processed at job_idx=0
                w, h = conf["resolution"]
                batch_idx = 0
```

This keeps `w, h` from the outer loop for configs without per-config resolutions, and overrides them for configs that have their own.

**Step 3: Commit**

```
feat: per-config resolution override in generation loop
```

---

### Task 6: Distribution Manager — Same Per-Config Resolution Override

**Files:**
- Modify: `distribution_manager.py:97-102` (job population loop)

**Step 1: Add per-config resolution override**

In `populate_jobs()`, after line 102 (`for conf_idx, conf in enumerate(expanded_configs):`), add the same skip/override logic:

```python
                    # Per-config resolution override
                    if conf.get("resolution") is not None:
                        if job_idx > 0:
                            continue
                        w = conf["resolution"][0]
                        h = conf["resolution"][1]
                        batch_idx = 0
```

**Step 2: Commit**

```
feat: per-config resolution override in distribution manager
```

---

### Task 7: Verify & Sync

**Step 1: Python syntax check**

Run:
```bash
python -c "import py_compile; py_compile.compile('config_utils.py', doraise=True); py_compile.compile('generation_orchestrator.py', doraise=True); py_compile.compile('distribution_manager.py', doraise=True); print('OK')"
```

**Step 2: JS brace balance check**

Verify all JS files have balanced braces/parens.

**Step 3: Sync worktree to main if using worktree**

**Step 4: Final commit**

```
feat: per-config resolutions — builder UI, config expansion, generation override
```
