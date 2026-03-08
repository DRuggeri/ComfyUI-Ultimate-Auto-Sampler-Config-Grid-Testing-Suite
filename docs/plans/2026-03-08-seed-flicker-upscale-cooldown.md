# Seed Settings, Canvas Flicker Fix, Upscaling & GPU Cooldown Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 4 features: expanded seed behavior options per-config, fix canvas flicker during simultaneous pan+zoom, add 3 upscaling modes as session-level settings, and add GPU cooldown breaks between generations.

**Architecture:** Seed settings extend existing per-config `seed_behavior` dropdown with new options (random/increment/decrement before/after full run). Canvas flicker fix batches pan+zoom transforms via requestAnimationFrame. Upscaling and cooldown are session-level settings stored in `node.state` and output alongside `configs_json`, consumed by `generation_orchestrator.py` and `distribution_worker.py`.

**Tech Stack:** Python (ComfyUI custom nodes), JavaScript (Builder UI widgets), ComfyUI model management APIs, requestAnimationFrame

---

## CRITICAL RULE

**DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.**

---

## Task 1: Expand Seed Behavior Options (Builder UI)

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js:1018-1029` (seed select dropdown)
- Modify: `web/conf_builder/conf-builder-utilities.js:637-639` (convertStateToConfigs seed output)
- Modify: `web/conf_builder/conf-builder-ui-components.js:867` (default state)

**Step 1: Update the seed behavior dropdown**

In `web/conf_builder/conf-builder-config-management.js`, find the seed select at line 1018-1029. Replace the `<select>` innerHTML with expanded options. Change the label from "Seed Behavior" to "Seed Behavior (Per Gen)":

```javascript
    // Seed Behavior Select — Per-Generation seed behavior
    const seedSelect = document.createElement("select");
    seedSelect.className = "cb-select";
    seedSelect.innerHTML = `
        <option value="fixed" ${(configArray.seed_behavior || "fixed") === "fixed" ? 'selected' : ''}>Fixed (use node seed)</option>
        <option value="randomize" ${configArray.seed_behavior === "randomize" ? 'selected' : ''}>Randomize every gen</option>
    `;
    seedSelect.onchange = () => {
        node.state.config_arrays[arrayIdx].seed_behavior = seedSelect.value;
        node.saveState();
    };
    settingsGrid.appendChild(createInputGroup("Seed Behavior (Per Gen)", seedSelect));
```

**Step 2: Add Full Run Seed Behavior dropdown**

Immediately after the per-gen seed select block (after the `settingsGrid.appendChild` for "Seed Behavior (Per Gen)"), add:

```javascript
    // Full Run Seed Behavior — applied before/after the entire grid test session
    const fullRunSeedSelect = document.createElement("select");
    fullRunSeedSelect.className = "cb-select";
    fullRunSeedSelect.innerHTML = `
        <option value="fixed" ${(configArray.full_run_seed_behavior || "fixed") === "fixed" ? 'selected' : ''}>Fixed</option>
        <option value="random_before" ${configArray.full_run_seed_behavior === "random_before" ? 'selected' : ''}>Random Before Entire Run</option>
        <option value="random_after" ${configArray.full_run_seed_behavior === "random_after" ? 'selected' : ''}>Random After Entire Run</option>
        <option value="increment_after" ${configArray.full_run_seed_behavior === "increment_after" ? 'selected' : ''}>Increment After Entire Run</option>
        <option value="decrement_after" ${configArray.full_run_seed_behavior === "decrement_after" ? 'selected' : ''}>Decrement After Entire Run</option>
    `;
    fullRunSeedSelect.onchange = () => {
        node.state.config_arrays[arrayIdx].full_run_seed_behavior = fullRunSeedSelect.value;
        node.saveState();
    };
    settingsGrid.appendChild(createInputGroup("Full Run Seed Behavior", fullRunSeedSelect));
```

**Step 3: Update convertStateToConfigs to output full_run_seed_behavior**

In `web/conf_builder/conf-builder-utilities.js`, find the seed_behavior output block at line 637-639. After it, add:

```javascript
        // Add full_run_seed_behavior if not fixed
        if (configArray.full_run_seed_behavior && configArray.full_run_seed_behavior !== "fixed") {
            config.full_run_seed_behavior = configArray.full_run_seed_behavior;
        }
```

**Step 4: Update default state objects**

In `conf-builder-utilities.js`, find the default config objects (around lines 680 and 883) that have `seed_behavior: "fixed"`. After each `seed_behavior: "fixed"` line, add:

```javascript
            full_run_seed_behavior: "fixed",
```

Do the same in `conf-builder-ui-components.js` at line 867.

**Step 5: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js web/conf_builder/conf-builder-utilities.js web/conf_builder/conf-builder-ui-components.js
git commit -m "feat: add full run seed behavior options to Builder UI"
```

---

## Task 2: Seed Behavior Python Backend

**Files:**
- Modify: `config_builder_node.py:465-524` (generate_config — add full_run_seed_behavior output)
- Modify: `config_utils.py:603-604` (expand_configs — pass through full_run_seed_behavior)
- Modify: `generation_orchestrator.py:627-695` (main loop — apply full run seed logic)
- Modify: `distribution_worker.py:478-480` (worker seed handling)

**Step 1: Add full_run_seed_behavior to Python config output**

In `config_builder_node.py`, inside `generate_config()`, find where `seed_behavior` is output (search for "seed_behavior" in the config-building loop). After that line, add:

```python
                # Full run seed behavior (applied before/after entire grid test session)
                full_run_seed_behavior = config_array.get("full_run_seed_behavior", "fixed")
                if full_run_seed_behavior and full_run_seed_behavior != "fixed":
                    config["full_run_seed_behavior"] = full_run_seed_behavior
```

**Step 2: Pass through in expand_configs**

In `config_utils.py`, find line 604 where `seed_behavior` is set in the expanded config dict. After it, add:

```python
                "full_run_seed_behavior": entry.get("full_run_seed_behavior", "fixed"),
```

**Step 3: Apply full run seed behavior in generation_orchestrator.py**

In `generation_orchestrator.py`, find the `# ==== MAIN GENERATION LOOP ====` section at line 627. **Before** the `for job_idx, job in enumerate(input_jobs):` loop (line 630), add:

```python
    # ==== FULL RUN SEED BEHAVIOR (PRE-RUN) ====
    # Apply "random_before" full run seed behavior: randomize seed before the entire session
    for conf_idx, conf in enumerate(expanded):
        if conf.get("full_run_seed_behavior") == "random_before":
            import random
            conf["seed"] = random.randint(0, 2**63 - 1)
            print(f"[GridTester] 🎲 Full run random_before: config {conf_idx} seed → {conf['seed']}")
```

Then, **after** the main generation loop ends (after all jobs complete, before the final manifest save), add:

```python
    # ==== FULL RUN SEED BEHAVIOR (POST-RUN) ====
    # These modify the seed for the NEXT queue/run, not the current one.
    # We update the node's seed widget value so the next execution uses the new seed.
    for conf_idx, conf in enumerate(expanded):
        frb = conf.get("full_run_seed_behavior", "fixed")
        if frb == "random_after":
            import random
            new_seed = random.randint(0, 2**63 - 1)
            print(f"[GridTester] 🎲 Full run random_after: config {conf_idx} next seed → {new_seed}")
            conf["seed"] = new_seed
        elif frb == "increment_after":
            conf["seed"] = conf["seed"] + 1
            print(f"[GridTester] ➕ Full run increment_after: config {conf_idx} next seed → {conf['seed']}")
        elif frb == "decrement_after":
            conf["seed"] = conf["seed"] - 1
            print(f"[GridTester] ➖ Full run decrement_after: config {conf_idx} next seed → {conf['seed']}")
```

**Step 4: Update distribution_worker.py**

In `distribution_worker.py`, find the seed handling at line 478-480. After it, add:

```python
        # Full run seed behavior is handled by the orchestrator/master before dispatching jobs.
        # Workers just use whatever seed is in the config they receive.
```

**Step 5: Commit**

```bash
git add config_builder_node.py config_utils.py generation_orchestrator.py distribution_worker.py
git commit -m "feat: implement full run seed behavior in backend"
```

---

## Task 3: Fix Canvas Flicker Bug (requestAnimationFrame Batching)

**Files:**
- Modify: `resources/logic_virtual.js:11-20` (pan/zoom state vars)
- Modify: `resources/logic_virtual.js:363-369` (updateTransform)
- Modify: `resources/logic_virtual.js:379-404` (updateZoom)
- Modify: `resources/logic_virtual.js:530-544` (mousemove + wheel handlers)

**Step 1: Add rAF batching state variables**

In `resources/logic_virtual.js`, after the pan/zoom state variables (after line 20 `let panOffsetY = 0;`), add:

```javascript
// --- RAF BATCHING STATE (prevents flicker from simultaneous pan+zoom) ---
let rafPending = false;
let pendingPanDeltaX = 0;
let pendingPanDeltaY = 0;
let pendingZoomDelta = 0;
let pendingZoomMouseX = 0;
let pendingZoomMouseY = 0;
let hasPendingZoom = false;
```

**Step 2: Add the batched transform apply function**

After the `updateTransform()` function (after line 369), add:

```javascript
/**
 * Apply all pending pan+zoom transforms in a single animation frame.
 * This prevents flicker when zooming and panning simultaneously,
 * because both transforms are applied atomically before the next paint.
 */
function applyPendingTransforms() {
    rafPending = false;

    // Apply zoom first (adjusts panOffset to keep cursor stable)
    if (hasPendingZoom) {
        updateZoom(pendingZoomDelta, pendingZoomMouseX, pendingZoomMouseY);
        hasPendingZoom = false;
        pendingZoomDelta = 0;
    }

    // Apply pan delta
    if (pendingPanDeltaX !== 0 || pendingPanDeltaY !== 0) {
        panOffsetX += pendingPanDeltaX;
        panOffsetY += pendingPanDeltaY;
        pendingPanDeltaX = 0;
        pendingPanDeltaY = 0;
        updateTransform();
    }
}

function scheduleRAF() {
    if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(applyPendingTransforms);
    }
}
```

**Step 3: Update mousemove handler to batch when zooming simultaneously**

Replace the mousemove handler at lines 530-539 with:

```javascript
    window.addEventListener('mousemove', (e) => {
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
        if (!isPanning && !isMiddleMousePanning) return;
        e.preventDefault();

        // If a zoom is also pending, batch the pan via rAF to prevent flicker
        if (hasPendingZoom) {
            pendingPanDeltaX = e.clientX - panStartX - panOffsetX;
            pendingPanDeltaY = e.clientY - panStartY - panOffsetY;
            scheduleRAF();
        } else {
            // No pending zoom — apply pan immediately for responsiveness
            panOffsetX = e.clientX - panStartX;
            panOffsetY = e.clientY - panStartY;
            updateTransform();
        }
    });
```

**Step 4: Update wheel handler to batch via rAF**

Replace the wheel handler at lines 541-544 with:

```javascript
    viewport.addEventListener('wheel', (e) => {
        e.preventDefault();
        // Batch zoom via rAF to prevent flicker with simultaneous pan
        if (isPanning || isMiddleMousePanning) {
            pendingZoomDelta += (e.deltaY > 0 ? -1 : 1);
            pendingZoomMouseX = e.clientX;
            pendingZoomMouseY = e.clientY;
            hasPendingZoom = true;
            scheduleRAF();
        } else {
            // Not panning — apply zoom immediately for responsiveness
            updateZoom(e.deltaY > 0 ? -1 : 1, e.clientX, e.clientY);
        }
    }, { passive: false });
```

**Step 5: Commit**

```bash
git add resources/logic_virtual.js
git commit -m "fix: prevent canvas flicker during simultaneous pan+zoom via rAF batching"
```

---

## Task 4: Upscaling Settings (Builder UI)

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js` (add upscaling UI section)
- Modify: `web/conf_builder/conf-builder-utilities.js` (output upscaling in convertStateToConfigs)
- Modify: `web/conf_builder/conf-builder-ui-components.js` (default state)

**Step 1: Add upscaling UI section**

In `web/conf_builder/conf-builder-config-management.js`, find the main Builder UI panel rendering. Look for where session-level settings are rendered (near the top of the config panel, before individual config arrays). Add a new "Upscaling" collapsible section:

```javascript
// ============================================================================
// UPSCALING SETTINGS (Session-level, applies to all configs)
// ============================================================================
function createUpscalingSection(node) {
    const state = node.state;
    if (!state.upscaling) {
        state.upscaling = {
            enabled: false,
            mode: "hires_only",
            upscale_ratio: 1.5,
            hires_denoise: 0.5,
            hires_steps: 0,
            tiled_vae: false,
            tile_size: 512,
            upscale_model: "",
            upscale_size: 2.0
        };
    }
    const ups = state.upscaling;

    const container = document.createElement("div");
    container.className = "cb-section";

    // Header with enable toggle
    const header = document.createElement("div");
    header.className = "cb-section-header";
    header.style.cssText = "display: flex; align-items: center; gap: 8px; cursor: pointer;";

    const enableCb = document.createElement("input");
    enableCb.type = "checkbox";
    enableCb.checked = ups.enabled;
    enableCb.onclick = (e) => e.stopPropagation();
    enableCb.onchange = () => {
        ups.enabled = enableCb.checked;
        body.style.display = enableCb.checked ? "block" : "none";
        node.saveState();
    };

    const title = document.createElement("span");
    title.textContent = "🔍 Upscaling Settings";
    title.style.cssText = "font-weight: bold; color: #cc99ff;";

    header.appendChild(enableCb);
    header.appendChild(title);
    container.appendChild(header);

    // Body (hidden when disabled)
    const body = document.createElement("div");
    body.style.display = ups.enabled ? "block" : "none";
    body.style.cssText += " padding: 8px; display: " + (ups.enabled ? "block" : "none") + ";";

    // Mode select
    const modeSelect = document.createElement("select");
    modeSelect.className = "cb-select";
    modeSelect.innerHTML = `
        <option value="hires_only" ${ups.mode === "hires_only" ? 'selected' : ''}>HiRes Fix Only</option>
        <option value="model_only" ${ups.mode === "model_only" ? 'selected' : ''}>Model Upscale Only</option>
        <option value="model_then_hires" ${ups.mode === "model_then_hires" ? 'selected' : ''}>Model Upscale → HiRes Fix</option>
    `;
    modeSelect.onchange = () => {
        ups.mode = modeSelect.value;
        updateVisibility();
        node.saveState();
    };
    body.appendChild(createInputGroup("Upscale Mode", modeSelect));

    // HiRes Fix settings
    const hiresGroup = document.createElement("div");
    hiresGroup.id = "upscale-hires-group";

    const ratioInput = createNumberInput(ups.upscale_ratio, 1.1, 4.0, 0.1, (v) => { ups.upscale_ratio = v; node.saveState(); });
    hiresGroup.appendChild(createInputGroup("Upscale Ratio", ratioInput));

    const denoiseInput = createNumberInput(ups.hires_denoise, 0.0, 1.0, 0.05, (v) => { ups.hires_denoise = v; node.saveState(); });
    hiresGroup.appendChild(createInputGroup("HiRes Denoise", denoiseInput));

    const stepsInput = createNumberInput(ups.hires_steps, 0, 150, 1, (v) => { ups.hires_steps = v; node.saveState(); });
    hiresGroup.appendChild(createInputGroup("HiRes Steps (0=same)", stepsInput));

    const tiledCb = document.createElement("input");
    tiledCb.type = "checkbox";
    tiledCb.checked = ups.tiled_vae;
    tiledCb.onchange = () => {
        ups.tiled_vae = tiledCb.checked;
        tileSizeGroup.style.display = tiledCb.checked ? "block" : "none";
        node.saveState();
    };
    hiresGroup.appendChild(createInputGroup("Tiled VAE", tiledCb));

    const tileSizeInput = createNumberInput(ups.tile_size, 128, 1024, 64, (v) => { ups.tile_size = v; node.saveState(); });
    const tileSizeGroup = createInputGroup("Tile Size", tileSizeInput);
    tileSizeGroup.style.display = ups.tiled_vae ? "block" : "none";
    hiresGroup.appendChild(tileSizeGroup);

    body.appendChild(hiresGroup);

    // Model Upscale settings
    const modelGroup = document.createElement("div");
    modelGroup.id = "upscale-model-group";

    const modelInput = document.createElement("input");
    modelInput.type = "text";
    modelInput.className = "cb-input";
    modelInput.value = ups.upscale_model || "";
    modelInput.placeholder = "e.g. 4x-UltraSharp";
    modelInput.onchange = () => { ups.upscale_model = modelInput.value; node.saveState(); };
    modelGroup.appendChild(createInputGroup("Upscale Model", modelInput));

    const sizeInput = createNumberInput(ups.upscale_size, 1.0, 4.0, 0.5, (v) => { ups.upscale_size = v; node.saveState(); });
    modelGroup.appendChild(createInputGroup("Upscale Size (multiplier)", sizeInput));

    body.appendChild(modelGroup);

    function updateVisibility() {
        const showHires = ups.mode === "hires_only" || ups.mode === "model_then_hires";
        const showModel = ups.mode === "model_only" || ups.mode === "model_then_hires";
        hiresGroup.style.display = showHires ? "block" : "none";
        modelGroup.style.display = showModel ? "block" : "none";
    }
    updateVisibility();

    container.appendChild(body);
    return container;
}

// Helper: create a number input with min/max/step and onchange callback
function createNumberInput(value, min, max, step, onChange) {
    const input = document.createElement("input");
    input.type = "number";
    input.className = "cb-input";
    input.value = value;
    input.min = min;
    input.max = max;
    input.step = step;
    input.onchange = () => onChange(parseFloat(input.value));
    return input;
}
```

NOTE: Find the appropriate place to insert `createUpscalingSection(node)` call — look for where the main panel is built and add it after the config arrays section but before the preview. Also check if `createInputGroup` already exists — it's likely already defined in the codebase. If `createNumberInput` already exists, don't duplicate it.

**Step 2: Output upscaling in convertStateToConfigs**

In `web/conf_builder/conf-builder-utilities.js`, in `convertStateToConfigs()`, at the end of the function (before `return configs;`), add session-level settings output:

```javascript
    // Session-level settings (not per-config, applied globally)
    const sessionSettings = {};

    // Upscaling settings
    if (state.upscaling && state.upscaling.enabled) {
        sessionSettings.upscaling = { ...state.upscaling };
    }

    // Attach session settings if any exist
    if (Object.keys(sessionSettings).length > 0) {
        configs._session_settings = sessionSettings;
    }
```

**Step 3: Update default state**

In `conf-builder-ui-components.js`, find where default state is initialized and add:

```javascript
            upscaling: {
                enabled: false,
                mode: "hires_only",
                upscale_ratio: 1.5,
                hires_denoise: 0.5,
                hires_steps: 0,
                tiled_vae: false,
                tile_size: 512,
                upscale_model: "",
                upscale_size: 2.0
            },
```

**Step 4: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js web/conf_builder/conf-builder-utilities.js web/conf_builder/conf-builder-ui-components.js
git commit -m "feat: add upscaling settings UI to Builder"
```

---

## Task 5: GPU Cooldown Settings (Builder UI)

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js` (add cooldown UI section)
- Modify: `web/conf_builder/conf-builder-utilities.js` (output cooldown settings)
- Modify: `web/conf_builder/conf-builder-ui-components.js` (default state)

**Step 1: Add cooldown UI section**

In `web/conf_builder/conf-builder-config-management.js`, add a cooldown section function (right after the upscaling section from Task 4):

```javascript
// ============================================================================
// GPU COOLDOWN SETTINGS (Session-level, applies to all configs)
// ============================================================================
function createCooldownSection(node) {
    const state = node.state;
    if (!state.cooldown) {
        state.cooldown = {
            enabled: false,
            seconds: 5,
            every_n: 1,
            clear_vram: false
        };
    }
    const cd = state.cooldown;

    const container = document.createElement("div");
    container.className = "cb-section";

    // Header with enable toggle
    const header = document.createElement("div");
    header.className = "cb-section-header";
    header.style.cssText = "display: flex; align-items: center; gap: 8px; cursor: pointer;";

    const enableCb = document.createElement("input");
    enableCb.type = "checkbox";
    enableCb.checked = cd.enabled;
    enableCb.onclick = (e) => e.stopPropagation();
    enableCb.onchange = () => {
        cd.enabled = enableCb.checked;
        body.style.display = enableCb.checked ? "block" : "none";
        node.saveState();
    };

    const title = document.createElement("span");
    title.textContent = "❄️ GPU Cooldown Breaks";
    title.style.cssText = "font-weight: bold; color: #66ccff;";

    header.appendChild(enableCb);
    header.appendChild(title);
    container.appendChild(header);

    // Body
    const body = document.createElement("div");
    body.style.display = cd.enabled ? "block" : "none";
    body.style.cssText += " padding: 8px; display: " + (cd.enabled ? "block" : "none") + ";";

    const secondsInput = createNumberInput(cd.seconds, 1, 300, 1, (v) => { cd.seconds = v; node.saveState(); });
    body.appendChild(createInputGroup("Cooldown Seconds", secondsInput));

    const everyNInput = createNumberInput(cd.every_n, 1, 100, 1, (v) => { cd.every_n = v; node.saveState(); });
    body.appendChild(createInputGroup("Every N Generations", everyNInput));

    const vramCb = document.createElement("input");
    vramCb.type = "checkbox";
    vramCb.checked = cd.clear_vram;
    vramCb.onchange = () => {
        cd.clear_vram = vramCb.checked;
        node.saveState();
    };
    body.appendChild(createInputGroup("Clear VRAM During Cooldown", vramCb));

    container.appendChild(body);
    return container;
}
```

Add the `createCooldownSection(node)` call right after the upscaling section in the panel builder.

**Step 2: Output cooldown settings in convertStateToConfigs**

In `web/conf_builder/conf-builder-utilities.js`, in the session settings block added in Task 4 Step 2, add:

```javascript
    // Cooldown settings
    if (state.cooldown && state.cooldown.enabled) {
        sessionSettings.cooldown = { ...state.cooldown };
    }
```

**Step 3: Update default state**

In `conf-builder-ui-components.js`, add to default state:

```javascript
            cooldown: {
                enabled: false,
                seconds: 5,
                every_n: 1,
                clear_vram: false
            },
```

**Step 4: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js web/conf_builder/conf-builder-utilities.js web/conf_builder/conf-builder-ui-components.js
git commit -m "feat: add GPU cooldown settings UI to Builder"
```

---

## Task 6: Upscaling Python Backend

**Files:**
- Modify: `image_generation.py:262-314` (add upscale_image function after generate_image, before decode_latent_with_vae)
- Modify: `model_loader.py` (add load_upscale_model function)
- Modify: `config_builder_node.py` (output session settings in generate_config)
- Modify: `generation_orchestrator.py:1081-1121` (apply upscaling after generate_image)
- Modify: `distribution_worker.py:592-595` (apply upscaling after generate_image in worker)

**Step 1: Add load_upscale_model to model_loader.py**

At the end of `model_loader.py`, add:

```python
def load_upscale_model(model_name):
    """
    Load an upscale model (ESRGAN, RealESRGAN, etc.) by name.

    Args:
        model_name: Name of the upscale model file (e.g. "4x-UltraSharp.pth")

    Returns:
        Loaded upscale model ready for use
    """
    from comfy_extras.nodes_upscale_model import UpscaleModelLoader
    loader = UpscaleModelLoader()
    (upscale_model,) = loader.load_model(model_name)
    return upscale_model
```

**Step 2: Add upscale_image to image_generation.py**

After the `generate_image()` function (after line 262 `return result[0], duration`) and before `decode_latent_with_vae()` (line 265), add:

```python
def upscale_image(result_latent, vae, patched_model, upscaling_config, config, positive_conditioning, negative_conditioning, width, height):
    """
    Apply upscaling to a generated latent based on upscaling settings.

    Args:
        result_latent: Generated latent dict with "samples" key
        vae: VAE model for encode/decode
        patched_model: Patched model for re-sampling (HiRes fix)
        upscaling_config: Dict with mode, upscale_ratio, hires_denoise, etc.
        config: Current generation config (steps, sampler, scheduler, etc.)
        positive_conditioning: Positive conditioning
        negative_conditioning: Negative conditioning
        width: Original image width
        height: Original image height

    Returns:
        Upscaled latent dict or PIL Image depending on mode
    """
    import torch
    import time
    import comfy.utils

    mode = upscaling_config.get("mode", "hires_only")
    upscale_ratio = float(upscaling_config.get("upscale_ratio", 1.5))
    hires_denoise = float(upscaling_config.get("hires_denoise", 0.5))
    hires_steps = int(upscaling_config.get("hires_steps", 0)) or config.get("steps", 20)
    tiled_vae = upscaling_config.get("tiled_vae", False)
    tile_size = int(upscaling_config.get("tile_size", 512))
    upscale_model_name = upscaling_config.get("upscale_model", "")

    new_w = int(width * upscale_ratio)
    new_h = int(height * upscale_ratio)

    t0 = time.time()
    print(f"[GridTester] 🔍 Upscaling: mode={mode}, ratio={upscale_ratio}, target={new_w}x{new_h}")

    if mode == "model_only":
        # Decode → model upscale → return as PIL image
        from model_loader import load_upscale_model
        from comfy_extras.nodes_upscale_model import ImageUpscaleWithModel

        pil_image = decode_latent_with_vae(vae, result_latent["samples"])

        # Convert PIL to tensor for model upscale
        import numpy as np
        img_np = np.array(pil_image).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)  # (1, H, W, C)

        upscaler = ImageUpscaleWithModel()
        up_model = load_upscale_model(upscale_model_name)
        (upscaled_tensor,) = upscaler.upscale(up_model, img_tensor)

        # Convert back to PIL
        up_np = upscaled_tensor[0].cpu().float().numpy()
        up_np = np.clip(up_np * 255, 0, 255).astype(np.uint8)
        upscaled_image = Image.fromarray(up_np)

        duration = round(time.time() - t0, 3)
        print(f"[GridTester] 🔍 Model upscale complete in {duration}s → {upscaled_image.size[0]}x{upscaled_image.size[1]}")
        return upscaled_image, duration

    elif mode == "hires_only":
        # Upscale latent → re-sample with denoise
        latent_samples = result_latent["samples"]
        upscaled_latent = comfy.utils.common_upscale(
            latent_samples, new_w // 8, new_h // 8, "bilinear", "disabled"
        )

        # Re-sample with denoise
        from comfy.sample import prepare_noise
        import comfy.samplers

        hires_latent, hires_duration = generate_image(
            patched_model, config.get("seed", 0), hires_steps, config.get("cfg", 7),
            config.get("sampler", "euler"), config.get("scheduler", "normal"),
            positive_conditioning, negative_conditioning,
            {"samples": upscaled_latent}, hires_denoise,
            width=new_w, height=new_h
        )

        duration = round(time.time() - t0, 3)
        print(f"[GridTester] 🔍 HiRes fix complete in {duration}s → {new_w}x{new_h}")
        return hires_latent, duration

    elif mode == "model_then_hires":
        # Model upscale first, then encode to latent, then HiRes fix
        from model_loader import load_upscale_model
        from comfy_extras.nodes_upscale_model import ImageUpscaleWithModel

        pil_image = decode_latent_with_vae(vae, result_latent["samples"])

        import numpy as np
        img_np = np.array(pil_image).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(img_np).unsqueeze(0)

        upscaler = ImageUpscaleWithModel()
        up_model = load_upscale_model(upscale_model_name)
        (upscaled_tensor,) = upscaler.upscale(up_model, img_tensor)

        # Encode back to latent
        upscaled_tensor_permuted = upscaled_tensor.permute(0, 3, 1, 2)  # NHWC → NCHW for VAE
        encoded_latent = vae.encode(upscaled_tensor[:, :, :, :3])  # VAE expects NHWC

        up_h, up_w = upscaled_tensor.shape[1], upscaled_tensor.shape[2]

        # HiRes fix on the model-upscaled latent
        hires_latent, hires_duration = generate_image(
            patched_model, config.get("seed", 0), hires_steps, config.get("cfg", 7),
            config.get("sampler", "euler"), config.get("scheduler", "normal"),
            positive_conditioning, negative_conditioning,
            {"samples": encoded_latent}, hires_denoise,
            width=up_w, height=up_h
        )

        duration = round(time.time() - t0, 3)
        print(f"[GridTester] 🔍 Model+HiRes upscale complete in {duration}s → {up_w}x{up_h}")
        return hires_latent, duration

    else:
        print(f"[GridTester] ⚠️ Unknown upscale mode: {mode}")
        return result_latent, 0
```

**Step 3: Output session settings in generate_config**

In `config_builder_node.py`, in `generate_config()`, find where `configs_json` is built. The session settings (upscaling, cooldown) need to be output as a separate key. Find where the final configs list is serialized to JSON, and add:

```python
            # Session-level settings (upscaling, cooldown) — not per-config
            session_settings = {}

            # Upscaling settings from Builder UI state
            upscaling_data = lora_config_data.get("upscaling", {})
            if upscaling_data and upscaling_data.get("enabled", False):
                session_settings["upscaling"] = upscaling_data

            # Cooldown settings from Builder UI state
            cooldown_data = lora_config_data.get("cooldown", {})
            if cooldown_data and cooldown_data.get("enabled", False):
                session_settings["cooldown"] = cooldown_data

            if session_settings:
                result["_session_settings"] = session_settings
```

**Step 4: Apply upscaling in generation_orchestrator.py**

In `generation_orchestrator.py`, after the `generate_image()` call at line 1081, before the metadata creation at line 1111, add:

```python
                # ==== UPSCALING (if enabled) ====
                upscaling_config = session_settings.get("upscaling", {}) if session_settings else {}
                if upscaling_config.get("enabled", False) and result_latent is not None:
                    from image_generation import upscale_image
                    upscale_result, upscale_duration = upscale_image(
                        result_latent, loaded_vae, patched_model, upscaling_config,
                        conf, final_positive, final_negative, w, h
                    )
                    if isinstance(upscale_result, Image.Image):
                        # Model-only mode returns PIL directly — save it
                        upscaled_meta = create_image_metadata(
                            conf, upscale_result.size[0], upscale_result.size[1],
                            duration + upscale_duration, current_seed, batch_idx,
                            actual_positive_prompt, actual_negative_prompt,
                            gen_index=gen_index_offset + total_generated
                        )
                        upscaled_meta["upscaled"] = True
                        upscaled_meta["upscale_mode"] = upscaling_config["mode"]
                        # Save upscaled image directly (no VAE decode needed)
                        upscaled_filename = f"upscaled_{total_generated:04d}.webp"
                        upscale_result.save(
                            os.path.join(paths["images"], upscaled_filename),
                            "WEBP", quality=80
                        )
                        upscaled_meta["file"] = f"filename={upscaled_filename}"
                        existing_data["items"].append(upscaled_meta)
                    else:
                        # HiRes modes return latent — replace result_latent
                        result_latent = upscale_result
                        duration += upscale_duration
```

Also, at the top of the main generation function, extract session settings from configs:

```python
    # Extract session-level settings (upscaling, cooldown)
    session_settings = None
    if isinstance(configs_json, str):
        import json
        try:
            parsed = json.loads(configs_json)
            if isinstance(parsed, dict) and "_session_settings" in parsed:
                session_settings = parsed["_session_settings"]
        except:
            pass
```

**Step 5: Commit**

```bash
git add image_generation.py model_loader.py config_builder_node.py generation_orchestrator.py
git commit -m "feat: implement upscaling pipeline (HiRes fix, model upscale, combined)"
```

---

## Task 7: GPU Cooldown Python Backend

**Files:**
- Modify: `generation_orchestrator.py` (main generation loop — add cooldown logic)
- Modify: `distribution_worker.py` (worker loop — add cooldown logic)

**Step 1: Add cooldown logic to generation_orchestrator.py**

In `generation_orchestrator.py`, after the pending_batch append at line 1120-1121, add:

```python
                # ==== GPU COOLDOWN (if enabled) ====
                cooldown_config = session_settings.get("cooldown", {}) if session_settings else {}
                if cooldown_config.get("enabled", False):
                    cooldown_every_n = int(cooldown_config.get("every_n", 1))
                    if total_generated > 0 and total_generated % cooldown_every_n == 0:
                        cooldown_seconds = int(cooldown_config.get("seconds", 5))
                        clear_vram = cooldown_config.get("clear_vram", False)

                        print(f"[GridTester] ❄️ GPU Cooldown: pausing {cooldown_seconds}s after {total_generated} generations")

                        if clear_vram:
                            import comfy.model_management as mm_cooldown
                            mm_cooldown.soft_empty_cache()
                            mm_cooldown.unload_all_models()
                            print(f"[GridTester] ❄️ VRAM cleared")
                            # Force model reload flag so next iteration reloads
                            cached_model_key = None

                        import time as time_module
                        time_module.sleep(cooldown_seconds)
                        print(f"[GridTester] ❄️ Cooldown complete, resuming generation")
```

**Step 2: Add cooldown logic to distribution_worker.py**

In `distribution_worker.py`, in `_process_job()`, after the image is generated and returned, add similar cooldown logic. Find the end of `_process_job` where it returns results, and before the return, add:

```python
        # ==== GPU COOLDOWN (if enabled in session settings) ====
        cooldown_config = config.get("_session_cooldown", {})
        if cooldown_config.get("enabled", False):
            cooldown_every_n = int(cooldown_config.get("every_n", 1))
            # Workers track generation count internally
            if not hasattr(self, '_gen_count'):
                self._gen_count = 0
            self._gen_count += 1
            if self._gen_count % cooldown_every_n == 0:
                cooldown_seconds = int(cooldown_config.get("seconds", 5))
                clear_vram = cooldown_config.get("clear_vram", False)

                print(f"[Worker] ❄️ GPU Cooldown: pausing {cooldown_seconds}s after {self._gen_count} generations")

                if clear_vram:
                    import comfy.model_management as mm_cooldown
                    mm_cooldown.soft_empty_cache()
                    mm_cooldown.unload_all_models()
                    print(f"[Worker] ❄️ VRAM cleared")

                import time as time_module
                time_module.sleep(cooldown_seconds)
                print(f"[Worker] ❄️ Cooldown complete, resuming")
```

**Step 3: Pass cooldown settings to workers**

In `distribution_manager.py`, in `_job_to_dict()` at line 591, after building the result dict, add cooldown settings to the config:

```python
        # Attach session-level cooldown settings to worker config
        if hasattr(self, '_session_settings') and 'cooldown' in self._session_settings:
            safe_config["_session_cooldown"] = self._session_settings["cooldown"]
```

**Step 4: Commit**

```bash
git add generation_orchestrator.py distribution_worker.py distribution_manager.py
git commit -m "feat: implement GPU cooldown breaks with optional VRAM clearing"
```

---

## Task 8: Integration Testing

**Step 1: Test seed behavior**

Create a small grid test in ComfyUI with:
- 2 configs, one with `full_run_seed_behavior: "random_before"`, one with `"increment_after"`
- Queue the workflow twice
- Verify: first config gets a random seed each run, second config's seed increments by 1 between runs

**Step 2: Test canvas flicker**

Open the dashboard with images loaded. Hold left-click drag while simultaneously scrolling the mouse wheel. Verify no flicker or position jumps.

**Step 3: Test upscaling**

Enable upscaling in Builder UI, set to HiRes Fix mode with ratio 1.5 and denoise 0.5. Run a small grid test. Verify upscaled images appear alongside originals in the output folder.

**Step 4: Test cooldown**

Enable cooldown with 3 seconds every 2 generations. Run a grid test with 6+ jobs. Verify console shows cooldown messages every 2 generations.

**Step 5: Commit any test fixes**

```bash
git add -A
git commit -m "fix: integration test adjustments"
```
