// ============================================================================
// UPSCALE MODAL — Dashboard image upscaling with inline config + presets
// ============================================================================

// State for the upscale modal
var upscaleModalState = {
    open: false,
    imageId: null,
    imageData: null,
    presets: [],
    currentConfig: null,
    jobId: null,
    pollInterval: null,
    availableModels: [],  // Upscale model list from server
};

// Default Florence2 Hi-Res Fix options — mirrors createDefaultFlorence2Options()
// in conf-builder-config-management.js. Keep these two in sync if you change either.
function _defaultFlorence2Options() {
    return {
        model: "microsoft/Florence-2-base",
        text_input: "face",
        output_mask_select: "",
        max_new_tokens: 1024,
        florence2_input_mp: 0.5,
        target_megapixels: 1.0,
        crop_padding: 64,
        min_crop_resolution: 0,       // No floor — Florence2's polygon decides
        max_crop_resolution: 99999,   // No ceiling — paste-back natural cap is the image itself
        grow_expand: 32,
        feather_left: 128,
        feather_top: 128,
        feather_right: 128,
        feather_bottom: 128,
        model_source: "from_manifest",
        on_no_detection: "skip"
    };
}

// Default SeedVR2 options — matches SeedVR2 node defaults
function _defaultSeedVR2Options() {
    return {
        dit_model: "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
        resolution: 1080,
        max_resolution: 0,
        seed: 42,
        color_correction: "lab",
        batch_size: 1,
        input_noise_scale: 0.0,
        latent_noise_scale: 0.0,
        blocks_to_swap: 0,
        attention_mode: "sdpa",
        offload_device: "cpu",
        cache_model: false,
        encode_tiled: false,
        encode_tile_size: 1024,
        encode_tile_overlap: 128,
        decode_tiled: false,
        decode_tile_size: 1024,
        decode_tile_overlap: 128,
        vae_offload_device: "none",
        vae_cache_model: false
    };
}

// Default upscale step config — ALL fields matching the Builder UI's createDefaultStep()
function _defaultUpscaleStep() {
    return {
        active: true,
        mode: "hires_only",
        repeat: 1,
        upscale_models: [],
        upscale_ratios: "1.5",
        upscale_size: "2.0",
        hires_denoise: "0.3",
        hires_steps: 0,
        tiled_vae: false,
        tile_size: 512,
        tile_overlap: 64,
        temporal_size: 512,
        temporal_overlap: 64,
        resize_method: "bilinear",
        hires_tiled_sampling: false,
        hires_tile_width: 512,
        hires_tile_height: 512,
        hires_mask_blur: 8,
        hires_tile_padding: 32,
        hires_force_uniform_tiles: false,
        seedvr2: _defaultSeedVR2Options(),
        florence2: _defaultFlorence2Options()
    };
}

// Ensure a step has all required fields (migration/defaults) — mirrors Builder's ensureStepFields()
function _ensureUpscaleStepFields(step) {
    if (step.active === undefined) step.active = true;
    if (!step.repeat || step.repeat < 1) step.repeat = 1;
    if (!step.upscale_models) step.upscale_models = [];
    if (!step.upscale_ratios) step.upscale_ratios = "1.5";
    if (!step.upscale_size) step.upscale_size = "2.0";
    if (!step.hires_denoise) step.hires_denoise = "0.3";
    if (step.hires_steps === undefined) step.hires_steps = 0;
    if (step.tiled_vae === undefined) step.tiled_vae = false;
    if (!step.tile_size) step.tile_size = 512;
    if (!step.tile_overlap) step.tile_overlap = 64;
    if (!step.temporal_size) step.temporal_size = 512;
    if (!step.temporal_overlap) step.temporal_overlap = 64;
    if (!step.resize_method) step.resize_method = "bilinear";
    if (step.hires_tiled_sampling === undefined) step.hires_tiled_sampling = false;
    if (!step.hires_tile_width) step.hires_tile_width = 512;
    if (!step.hires_tile_height) step.hires_tile_height = 512;
    if (step.hires_mask_blur === undefined) step.hires_mask_blur = 8;
    if (!step.hires_tile_padding) step.hires_tile_padding = 32;
    if (step.hires_force_uniform_tiles === undefined) step.hires_force_uniform_tiles = false;
    if (!step.seedvr2) step.seedvr2 = _defaultSeedVR2Options();
    if (!step.florence2) step.florence2 = _defaultFlorence2Options();
}

// Default config
function _defaultUpscaleConfig() {
    return {
        pipelines: [{ active: true, name: "Pipeline 1", steps: [_defaultUpscaleStep()] }],
        hires_prompt_adjust: false, hires_prompt_behavior: "append_end", hires_prompt_text: "",
    };
}

/**
 * Open the upscale modal for a specific image
 */
function openUpscaleModal(imageId) {
    var item = activeData ? activeData.find(function(d) { return d.id === imageId; }) : null;
    if (!item) return;

    upscaleModalState.open = true;
    upscaleModalState.imageId = imageId;
    upscaleModalState.imageData = item;
    upscaleModalState.jobId = null;

    // Initialize with default config if none set
    if (!upscaleModalState.currentConfig) {
        upscaleModalState.currentConfig = _defaultUpscaleConfig();
    }

    // Fetch presets and model list in parallel, then render
    Promise.all([
        fetchUpscalePresets(),
        fetchUpscaleModels()
    ]).then(function() { renderUpscaleModal(); });
}

/**
 * Close the upscale modal
 */
function closeUpscaleModal() {
    upscaleModalState.open = false;
    if (upscaleModalState.pollInterval) {
        clearInterval(upscaleModalState.pollInterval);
        upscaleModalState.pollInterval = null;
    }
    var modal = document.getElementById('upscale-modal-overlay');
    if (modal) modal.style.display = 'none';
}

/**
 * Fetch upscale presets from server
 */
async function fetchUpscalePresets() {
    try {
        var resp = await fetch('/configbuilder/upscale_presets');
        if (resp.ok) {
            var data = await resp.json();
            upscaleModalState.presets = data.presets || [];
        }
    } catch (e) { console.error('Failed to fetch upscale presets:', e); }
}

/**
 * Fetch available upscale models from server
 */
async function fetchUpscaleModels() {
    try {
        var resp = await fetch('/configbuilder/model_lists');
        if (resp.ok) {
            var data = await resp.json();
            upscaleModalState.availableModels = data.upscale_models || [];
        }
    } catch (e) { console.error('Failed to fetch upscale models:', e); }
}

/**
 * Save current config as a new preset
 */
async function saveUpscalePreset(name) {
    if (!name || !upscaleModalState.currentConfig) return;
    // Check for duplicate name and replace if exists
    var existingIdx = -1;
    for (var i = 0; i < upscaleModalState.presets.length; i++) {
        if (upscaleModalState.presets[i].name === name) { existingIdx = i; break; }
    }
    var preset = {
        name: name,
        pipelines: JSON.parse(JSON.stringify(upscaleModalState.currentConfig.pipelines)),
        hires_prompt_adjust: upscaleModalState.currentConfig.hires_prompt_adjust || false,
        hires_prompt_behavior: upscaleModalState.currentConfig.hires_prompt_behavior || "append_end",
        hires_prompt_text: upscaleModalState.currentConfig.hires_prompt_text || "",
    };
    if (existingIdx >= 0) {
        upscaleModalState.presets[existingIdx] = preset;
    } else {
        upscaleModalState.presets.push(preset);
    }
    try {
        await fetch('/configbuilder/upscale_presets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ presets: upscaleModalState.presets })
        });
    } catch (e) { console.error('Failed to save preset:', e); }
    renderUpscaleModal();
}

/**
 * Delete a preset by index
 */
async function deleteUpscalePreset(index) {
    upscaleModalState.presets.splice(index, 1);
    try {
        await fetch('/configbuilder/upscale_presets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ presets: upscaleModalState.presets })
        });
    } catch (e) { console.error('Failed to delete preset:', e); }
    renderUpscaleModal();
}

/**
 * Load a preset into the current config
 */
function loadUpscalePreset(index) {
    var preset = upscaleModalState.presets[index];
    if (!preset) return;
    upscaleModalState.currentConfig = {
        pipelines: JSON.parse(JSON.stringify(preset.pipelines)),
        hires_prompt_adjust: preset.hires_prompt_adjust || false,
        hires_prompt_behavior: preset.hires_prompt_behavior || "append_end",
        hires_prompt_text: preset.hires_prompt_text || "",
    };
    // Ensure all loaded steps have required fields
    upscaleModalState.currentConfig.pipelines.forEach(function(p) {
        if (p.active === undefined) p.active = true;
        if (!p.name) p.name = "Pipeline";
        if (!p.steps || p.steps.length === 0) p.steps = [_defaultUpscaleStep()];
        p.steps.forEach(_ensureUpscaleStepFields);
    });
    renderUpscaleModal();
}

/**
 * Helper: create a labeled select
 */
function _makeSelect(label, options, currentVal, onChange) {
    var row = document.createElement('div');
    row.style.cssText = 'display: flex; align-items: center; gap: 6px; margin-bottom: 6px;';
    var lbl = document.createElement('span');
    lbl.textContent = label;
    lbl.style.cssText = 'font-size: 11px; color: #999; min-width: 70px;';
    var sel = document.createElement('select');
    sel.style.cssText = 'flex: 1; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 3px 6px; font-size: 11px;';
    options.forEach(function(o) {
        var opt = document.createElement('option');
        opt.value = typeof o === 'object' ? o.value : o;
        opt.textContent = typeof o === 'object' ? o.label : o;
        if (opt.value === String(currentVal)) opt.selected = true;
        sel.appendChild(opt);
    });
    sel.onchange = function() { onChange(sel.value); };
    row.appendChild(lbl);
    row.appendChild(sel);
    return row;
}

/**
 * Helper: create a labeled text input
 */
function _makeInput(label, currentVal, placeholder, onChange) {
    var row = document.createElement('div');
    row.style.cssText = 'display: flex; align-items: center; gap: 6px; margin-bottom: 6px;';
    var lbl = document.createElement('span');
    lbl.textContent = label;
    lbl.style.cssText = 'font-size: 11px; color: #999; min-width: 70px;';
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.value = currentVal || '';
    inp.placeholder = placeholder || '';
    inp.style.cssText = 'flex: 1; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 3px 6px; font-size: 11px;';
    inp.onchange = function() { onChange(inp.value); };
    row.appendChild(lbl);
    row.appendChild(inp);
    return row;
}

/**
 * Helper: create a labeled number input
 */
function _makeNumber(label, currentVal, min, max, step, onChange) {
    var row = document.createElement('div');
    row.style.cssText = 'display: flex; align-items: center; gap: 6px; margin-bottom: 6px;';
    var lbl = document.createElement('span');
    lbl.textContent = label;
    lbl.style.cssText = 'font-size: 11px; color: #999; min-width: 70px;';
    var inp = document.createElement('input');
    inp.type = 'number';
    inp.value = currentVal;
    inp.min = min;
    inp.max = max;
    inp.step = step;
    inp.style.cssText = 'flex: 1; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 3px 6px; font-size: 11px; max-width: 80px;';
    inp.onchange = function() { var v = parseFloat(inp.value); onChange(isNaN(v) ? min : Math.max(min, Math.min(max, v))); };
    row.appendChild(lbl);
    row.appendChild(inp);
    return row;
}

/**
 * Helper: create a labeled checkbox
 */
function _makeCheckbox(label, checked, onChange) {
    var row = document.createElement('div');
    row.style.cssText = 'display: flex; align-items: center; gap: 6px; margin-bottom: 6px;';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = checked;
    cb.onchange = function() { onChange(cb.checked); };
    var lbl = document.createElement('span');
    lbl.textContent = label;
    lbl.style.cssText = 'font-size: 11px; color: #ccc; cursor: pointer;';
    lbl.onclick = function() { cb.checked = !cb.checked; onChange(cb.checked); };
    row.appendChild(cb);
    row.appendChild(lbl);
    return row;
}

// ============================================================================
// PIPELINE EDITOR — Full pipeline/step UI, reusable component
// Mirrors the Builder UI's renderPipelines() in conf-builder-config-management.js
// ============================================================================

/**
 * Render the full pipeline editor into a container.
 * @param {HTMLElement} container — DOM element to render into (will be cleared)
 * @param {Object} config — { pipelines: [...], hires_prompt_adjust, hires_prompt_behavior, hires_prompt_text }
 * @param {Array} modelList — array of upscale model filenames
 * @param {Object} callbacks — { onUpdate(), onRender() }
 *   onUpdate — called when any config value changes (caller can persist)
 *   onRender — called when DOM needs full re-render (add/remove pipeline/step, mode change)
 */
function renderPipelineEditor(container, config, modelList, callbacks) {
    container.textContent = '';

    // Ensure all pipelines/steps have required fields
    if (!config.pipelines || config.pipelines.length === 0) {
        config.pipelines = [{ active: true, name: "Pipeline 1", steps: [_defaultUpscaleStep()] }];
    }
    config.pipelines.forEach(function(p) {
        if (p.active === undefined) p.active = true;
        if (!p.name) p.name = "Pipeline";
        if (!p.steps || p.steps.length === 0) p.steps = [_defaultUpscaleStep()];
        p.steps.forEach(_ensureUpscaleStepFields);
    });

    // --- HiRes Prompt Adjustment Section ---
    var hiresDiv = document.createElement('div');
    hiresDiv.style.cssText = 'margin-bottom: 8px; padding: 6px 8px; background: #1e1e1e; border-radius: 4px;';
    var hiresPromptRow = _makeCheckbox('Adjust Prompt During HiRes Fix', config.hires_prompt_adjust || false, function(v) {
        config.hires_prompt_adjust = v;
        hiresOpts.style.display = v ? 'block' : 'none';
        callbacks.onUpdate();
    });
    hiresDiv.appendChild(hiresPromptRow);

    var hiresOpts = document.createElement('div');
    hiresOpts.style.cssText = 'margin-top: 4px; display: ' + (config.hires_prompt_adjust ? 'block' : 'none') + ';';
    hiresOpts.appendChild(_makeSelect('Behavior:', [
        { value: 'prepend', label: 'Append To Front' },
        { value: 'append_end', label: 'Append To End' },
        { value: 'replace', label: 'Replace Prompt' },
    ], config.hires_prompt_behavior || 'append_end', function(v) {
        config.hires_prompt_behavior = v;
        callbacks.onUpdate();
    }));
    // Prompt text textarea
    var promptRow = document.createElement('div');
    promptRow.style.cssText = 'margin-bottom: 6px;';
    var promptLbl = document.createElement('span');
    promptLbl.textContent = 'HiRes Prompt:';
    promptLbl.style.cssText = 'font-size: 11px; color: #999; display: block; margin-bottom: 2px;';
    var promptTa = document.createElement('textarea');
    promptTa.value = config.hires_prompt_text || '';
    promptTa.placeholder = 'Enter prompt adjustment text...';
    promptTa.style.cssText = 'width: 100%; min-height: 40px; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 4px 6px; font-size: 11px; resize: vertical; box-sizing: border-box;';
    promptTa.onchange = function() { config.hires_prompt_text = promptTa.value; callbacks.onUpdate(); };
    promptRow.appendChild(promptLbl);
    promptRow.appendChild(promptTa);
    hiresOpts.appendChild(promptRow);
    hiresDiv.appendChild(hiresOpts);
    container.appendChild(hiresDiv);

    // --- Pipelines ---
    var pipelinesContainer = document.createElement('div');

    function reRender() {
        renderPipelineEditor(container, config, modelList, callbacks);
    }

    config.pipelines.forEach(function(pipeline, pipeIdx) {
        var pipeCard = document.createElement('div');
        pipeCard.style.cssText = 'border: 2px solid #665599; border-radius: 8px; margin-bottom: 8px; background: #1a1a2e;' + (pipeline.active === false ? ' opacity: 0.5;' : '');

        // Pipeline header (collapsible)
        var pipeHeader = document.createElement('div');
        pipeHeader.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; cursor: pointer; background: #252540; border-radius: 6px 6px 0 0;';

        var pipeLeft = document.createElement('div');
        pipeLeft.style.cssText = 'display: flex; align-items: center; gap: 6px;';

        var pipeActiveCb = document.createElement('input');
        pipeActiveCb.type = 'checkbox';
        pipeActiveCb.checked = pipeline.active !== false;
        pipeActiveCb.title = pipeline.active !== false ? 'Pipeline is ON' : 'Pipeline is OFF';
        pipeActiveCb.onclick = function(e) { e.stopPropagation(); };
        pipeActiveCb.onchange = function() {
            pipeline.active = pipeActiveCb.checked;
            pipeCard.style.opacity = pipeline.active !== false ? '1' : '0.5';
            callbacks.onUpdate();
        };
        pipeLeft.appendChild(pipeActiveCb);

        var pipeNameInput = document.createElement('input');
        pipeNameInput.type = 'text';
        pipeNameInput.value = pipeline.name || ('Pipeline ' + (pipeIdx + 1));
        pipeNameInput.style.cssText = 'font-weight: bold; color: #cc99ff; font-size: 12px; background: transparent; border: 1px solid transparent; padding: 2px 4px; width: 130px;';
        pipeNameInput.onclick = function(e) { e.stopPropagation(); };
        pipeNameInput.onfocus = function() { pipeNameInput.style.borderColor = '#665599'; };
        pipeNameInput.onblur = function() { pipeNameInput.style.borderColor = 'transparent'; };
        pipeNameInput.onchange = function() { pipeline.name = pipeNameInput.value; callbacks.onUpdate(); };
        pipeLeft.appendChild(pipeNameInput);

        var pipeStepCount = document.createElement('span');
        pipeStepCount.style.cssText = 'font-size: 10px; color: #888;';
        pipeStepCount.textContent = '(' + pipeline.steps.length + ' step' + (pipeline.steps.length !== 1 ? 's' : '') + ')';
        pipeLeft.appendChild(pipeStepCount);

        pipeHeader.appendChild(pipeLeft);

        var pipeRight = document.createElement('div');
        pipeRight.style.cssText = 'display: flex; align-items: center; gap: 6px;';

        if (config.pipelines.length > 1) {
            var pipeDelBtn = document.createElement('button');
            pipeDelBtn.textContent = '\u2715';
            pipeDelBtn.style.cssText = 'background: #cc3333; color: #fff; border: none; border-radius: 3px; padding: 2px 8px; font-size: 12px; cursor: pointer;';
            pipeDelBtn.onclick = function(e) {
                e.stopPropagation();
                config.pipelines.splice(pipeIdx, 1);
                callbacks.onUpdate();
                reRender();
            };
            pipeRight.appendChild(pipeDelBtn);
        }

        var collapseIcon = document.createElement('span');
        collapseIcon.style.cssText = 'color: #888; font-size: 12px; user-select: none;';
        collapseIcon.textContent = '\u25BC';
        pipeRight.appendChild(collapseIcon);

        pipeHeader.appendChild(pipeRight);
        pipeCard.appendChild(pipeHeader);

        // Pipeline body (collapsible)
        var pipeBody = document.createElement('div');
        pipeBody.style.cssText = 'padding: 6px 10px;';

        pipeHeader.onclick = function() {
            var isCollapsed = pipeBody.style.display === 'none';
            pipeBody.style.display = isCollapsed ? 'block' : 'none';
            collapseIcon.textContent = isCollapsed ? '\u25BC' : '\u25B6';
        };

        // Render steps
        pipeline.steps.forEach(function(ucfg, stepIdx) {
            _renderStep(pipeBody, config, pipeline, ucfg, stepIdx, modelList, callbacks, reRender);
        });

        // Add Step button
        var addStepBtn = document.createElement('button');
        addStepBtn.textContent = '+ Add Step';
        addStepBtn.style.cssText = 'background: #333; color: #cc99ff; border: 1px solid #665599; border-radius: 4px; padding: 3px 10px; font-size: 11px; cursor: pointer; margin-top: 4px;';
        addStepBtn.onclick = function() {
            pipeline.steps.push(_defaultUpscaleStep());
            callbacks.onUpdate();
            reRender();
        };
        pipeBody.appendChild(addStepBtn);

        pipeCard.appendChild(pipeBody);
        pipelinesContainer.appendChild(pipeCard);
    });

    // Add Pipeline button
    var addPipeBtn = document.createElement('button');
    addPipeBtn.textContent = '+ Add Pipeline';
    addPipeBtn.style.cssText = 'background: #333; color: #cc99ff; border: 1px solid #cc99ff; border-radius: 4px; padding: 4px 12px; font-size: 11px; cursor: pointer; margin-top: 4px;';
    addPipeBtn.onclick = function() {
        config.pipelines.push({
            active: true,
            name: 'Pipeline ' + (config.pipelines.length + 1),
            steps: [_defaultUpscaleStep()]
        });
        callbacks.onUpdate();
        reRender();
    };
    pipelinesContainer.appendChild(addPipeBtn);

    container.appendChild(pipelinesContainer);
}

/**
 * Render a single step card inside a pipeline body.
 * Internal helper for renderPipelineEditor.
 */
function _renderStep(pipeBody, config, pipeline, ucfg, stepIdx, modelList, callbacks, reRender) {
    var card = document.createElement('div');
    card.style.cssText = 'border: 1px solid #444; border-radius: 6px; margin-bottom: 6px; padding: 8px;' + (ucfg.active === false ? ' opacity: 0.5;' : '');

    // Card header
    var cardHeader = document.createElement('div');
    cardHeader.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;';

    var cardLeft = document.createElement('div');
    cardLeft.style.cssText = 'display: flex; align-items: center; gap: 6px;';

    var activeCb = document.createElement('input');
    activeCb.type = 'checkbox';
    activeCb.checked = ucfg.active !== false;
    activeCb.onchange = function() {
        ucfg.active = activeCb.checked;
        card.style.opacity = ucfg.active !== false ? '1' : '0.5';
        callbacks.onUpdate();
    };
    cardLeft.appendChild(activeCb);

    var cardTitle = document.createElement('span');
    cardTitle.style.cssText = 'font-weight: bold; color: #cc99ff; font-size: 12px;';
    cardTitle.textContent = 'Step ' + (stepIdx + 1);
    cardLeft.appendChild(cardTitle);

    // Repeat field inline
    var repeatLbl = document.createElement('span');
    repeatLbl.style.cssText = 'font-size: 10px; color: #888; margin-left: 6px;';
    repeatLbl.textContent = 'Repeat:';
    cardLeft.appendChild(repeatLbl);

    var repeatInput = document.createElement('input');
    repeatInput.type = 'number';
    repeatInput.value = ucfg.repeat || 1;
    repeatInput.min = 0; repeatInput.max = 20; repeatInput.step = "any";
    repeatInput.style.cssText = 'width: 44px; padding: 1px 3px; font-size: 10px; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 3px;';
    repeatInput.onchange = function() { ucfg.repeat = Math.max(1, parseFloat(repeatInput.value) || 1); callbacks.onUpdate(); reRender(); };
    cardLeft.appendChild(repeatInput);

    if (ucfg.repeat > 1) {
        var repeatNote = document.createElement('span');
        repeatNote.style.cssText = 'font-size: 9px; color: #cc99ff;';
        repeatNote.textContent = '(\u00D7' + ucfg.repeat + ' feedback loop)';
        cardLeft.appendChild(repeatNote);
    }

    cardHeader.appendChild(cardLeft);

    if (pipeline.steps.length > 1) {
        var delBtn = document.createElement('button');
        delBtn.textContent = '\u2715';
        delBtn.style.cssText = 'background: #cc3333; color: #fff; border: none; border-radius: 3px; padding: 2px 8px; font-size: 11px; cursor: pointer;';
        delBtn.onclick = function() {
            pipeline.steps.splice(stepIdx, 1);
            callbacks.onUpdate();
            reRender();
        };
        cardHeader.appendChild(delBtn);
    }
    card.appendChild(cardHeader);

    // Grid of settings
    var grid = document.createElement('div');
    grid.style.cssText = 'display: flex; flex-wrap: wrap; gap: 4px;';

    // Mode select
    grid.appendChild(_makeSelect('Mode:', [
        { value: 'hires_only', label: 'HiRes Fix Only' },
        { value: 'model_only', label: 'Model Upscale Only' },
        { value: 'model_then_hires', label: 'Model + HiRes Fix' },
        { value: 'seedvr2', label: 'SeedVR2 Upscale' },
        { value: 'florence2_hires', label: 'Florence2 Hi-Res Fix' },
    ], ucfg.mode, function(v) {
        ucfg.mode = v;
        callbacks.onUpdate();
        reRender();
    }));

    // Resize method
    grid.appendChild(_makeSelect('Resize:', [
        'nearest-exact', 'bilinear', 'area', 'bicubic', 'lanczos'
    ], ucfg.resize_method || 'bilinear', function(v) {
        ucfg.resize_method = v;
        callbacks.onUpdate();
    }));

    var showHires = ucfg.mode === 'hires_only' || ucfg.mode === 'model_then_hires' || ucfg.mode === 'florence2_hires';
    var showModel = ucfg.mode === 'model_only' || ucfg.mode === 'model_then_hires';
    var showSeedVR2 = ucfg.mode === 'seedvr2';
    var showFlorence2 = ucfg.mode === 'florence2_hires';

    // --- HiRes fields ---
    if (showHires) {
        // Upscale Ratios is irrelevant for florence2_hires (it inpaints a region, not
        // the whole image; target_megapixels controls the internal pass size instead).
        if (!showFlorence2) {
            grid.appendChild(_makeInput('Ratios:', ucfg.upscale_ratios || '1.5', '1.2, 1.5, 2.0', function(v) {
                ucfg.upscale_ratios = v; callbacks.onUpdate();
            }));
        }
        grid.appendChild(_makeInput('Denoise:', ucfg.hires_denoise || '0.3', '0.2, 0.3, 0.5', function(v) {
            ucfg.hires_denoise = v; callbacks.onUpdate();
        }));
        grid.appendChild(_makeNumber('HiRes Steps:', ucfg.hires_steps || 0, 0, 150, 1, function(v) {
            ucfg.hires_steps = v; callbacks.onUpdate();
        }));

        // Tiled sampling — hidden for florence2_hires (crops are too small to need tiling).
        if (!showFlorence2) {
            grid.appendChild(_makeCheckbox('HiRes Tiled Sampling', ucfg.hires_tiled_sampling || false, function(v) {
                ucfg.hires_tiled_sampling = v; callbacks.onUpdate(); reRender();
            }));
        }

        if (ucfg.hires_tiled_sampling && !showFlorence2) {
            grid.appendChild(_makeNumber('Tile Width:', ucfg.hires_tile_width || 512, 128, 2048, 64, function(v) {
                ucfg.hires_tile_width = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeNumber('Tile Height:', ucfg.hires_tile_height || 512, 128, 2048, 64, function(v) {
                ucfg.hires_tile_height = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeNumber('Mask Blur:', ucfg.hires_mask_blur || 8, 0, 64, 1, function(v) {
                ucfg.hires_mask_blur = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeNumber('Tile Padding:', ucfg.hires_tile_padding || 32, 0, 256, 8, function(v) {
                ucfg.hires_tile_padding = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeCheckbox('Force Uniform Tiles', ucfg.hires_force_uniform_tiles !== false, function(v) {
                ucfg.hires_force_uniform_tiles = v; callbacks.onUpdate();
            }));
        }

        // Tiled VAE — hidden for florence2_hires (crops decode quickly without tiling).
        if (!showFlorence2) {
            grid.appendChild(_makeCheckbox('Tiled VAE Decode', ucfg.tiled_vae || false, function(v) {
                ucfg.tiled_vae = v; callbacks.onUpdate(); reRender();
            }));
        }

        if (ucfg.tiled_vae && !showFlorence2) {
            grid.appendChild(_makeNumber('Tile Size:', ucfg.tile_size || 512, 128, 1024, 64, function(v) {
                ucfg.tile_size = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeNumber('Tile Overlap:', ucfg.tile_overlap || 64, 0, 512, 8, function(v) {
                ucfg.tile_overlap = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeNumber('Temporal Size:', ucfg.temporal_size || 512, 128, 1024, 64, function(v) {
                ucfg.temporal_size = v; callbacks.onUpdate();
            }));
            grid.appendChild(_makeNumber('Temporal Overlap:', ucfg.temporal_overlap || 64, 0, 512, 8, function(v) {
                ucfg.temporal_overlap = v; callbacks.onUpdate();
            }));
        }
    }

    // --- Model fields ---
    if (showModel) {
        // Output size multiplier — only for model_only mode
        if (ucfg.mode === 'model_only') {
            grid.appendChild(_makeInput('Size Mult:', ucfg.upscale_size || '2.0', '2.0', function(v) {
                ucfg.upscale_size = v; callbacks.onUpdate();
            }));
        }

        // Model multi-select: chips + searchable dropdown
        var modelsWrap = document.createElement('div');
        modelsWrap.style.cssText = 'width: 100%; margin-bottom: 6px;';

        var noModels = !ucfg.upscale_models || ucfg.upscale_models.length === 0;
        if (noModels) {
            modelsWrap.style.border = '2px solid #ff3333';
            modelsWrap.style.borderRadius = '4px';
            modelsWrap.style.padding = '4px';
        }

        var modelsLbl = document.createElement('div');
        modelsLbl.style.cssText = 'font-size: 11px; color: ' + (noModels ? '#ff3333' : '#999') + '; margin-bottom: 3px;';
        modelsLbl.textContent = 'Upscale Models (' + (ucfg.upscale_models || []).length + ')' + (noModels ? ' \u2014 Select a model!' : '');
        modelsWrap.appendChild(modelsLbl);

        // Model chips
        (ucfg.upscale_models || []).forEach(function(modelName, mIdx) {
            var chip = document.createElement('div');
            chip.style.cssText = 'display: inline-flex; align-items: center; gap: 3px; background: #333; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 10px; color: #ccc;';
            chip.textContent = modelName.replace(/\\/g, '/').split('/').pop();
            var removeBtn = document.createElement('span');
            removeBtn.textContent = '\u2715';
            removeBtn.style.cssText = 'cursor: pointer; color: #cc3333; margin-left: 3px; font-size: 11px;';
            removeBtn.onclick = function() {
                ucfg.upscale_models.splice(mIdx, 1);
                callbacks.onUpdate();
                reRender();
            };
            chip.appendChild(removeBtn);
            modelsWrap.appendChild(chip);
        });

        // Searchable model dropdown
        var modelSearchWrap = document.createElement('div');
        modelSearchWrap.style.cssText = 'position: relative; margin-top: 3px;';

        var modelSearchInput = document.createElement('input');
        modelSearchInput.type = 'text';
        modelSearchInput.placeholder = 'Search upscale models...';
        modelSearchInput.style.cssText = 'width: 100%; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 3px 6px; font-size: 10px; box-sizing: border-box;';

        var modelDropdown = document.createElement('div');
        modelDropdown.style.cssText = 'display: none; position: absolute; top: 100%; left: 0; right: 0; max-height: 150px; overflow-y: auto; background: #222; border: 1px solid #555; border-radius: 4px; z-index: 100;';

        function populateModelDropdown(query) {
            modelDropdown.textContent = '';
            var q = (query || '').toLowerCase();
            var existing = ucfg.upscale_models || [];
            var filtered = (modelList || []).filter(function(m) {
                if (existing.indexOf(m) >= 0) return false;
                return !q || m.toLowerCase().indexOf(q) >= 0;
            });
            if (filtered.length === 0) {
                modelDropdown.style.display = 'none';
                return;
            }
            modelDropdown.style.display = 'block';
            filtered.forEach(function(m) {
                var opt = document.createElement('div');
                opt.style.cssText = 'padding: 3px 8px; font-size: 10px; color: #ccc; cursor: pointer;';
                opt.textContent = m.replace(/\\/g, '/').split('/').pop();
                opt.title = m;
                opt.onmouseenter = function() { opt.style.background = '#444'; };
                opt.onmouseleave = function() { opt.style.background = 'transparent'; };
                opt.onclick = function() {
                    if (!ucfg.upscale_models) ucfg.upscale_models = [];
                    if (ucfg.upscale_models.indexOf(m) < 0) {
                        ucfg.upscale_models.push(m);
                        callbacks.onUpdate();
                        reRender();
                    }
                };
                modelDropdown.appendChild(opt);
            });
        }

        modelSearchInput.onfocus = function() { populateModelDropdown(modelSearchInput.value); };
        modelSearchInput.oninput = function() { populateModelDropdown(modelSearchInput.value); };
        modelSearchInput.onblur = function() {
            // Delay hide so click on dropdown item registers
            setTimeout(function() { modelDropdown.style.display = 'none'; }, 200);
        };

        modelSearchWrap.appendChild(modelSearchInput);
        modelSearchWrap.appendChild(modelDropdown);
        modelsWrap.appendChild(modelSearchWrap);
        grid.appendChild(modelsWrap);
    }

    // --- SeedVR2 fields ---
    if (showSeedVR2) {
        if (!ucfg.seedvr2) ucfg.seedvr2 = _defaultSeedVR2Options();
        var sv = ucfg.seedvr2;

        var ditModels = [
            'seedvr2_ema_3b_fp8_e4m3fn.safetensors', 'seedvr2_ema_3b_fp16.safetensors',
            'seedvr2_ema_3b-Q4_K_M.gguf', 'seedvr2_ema_3b-Q8_0.gguf',
            'seedvr2_ema_7b_fp8_e4m3fn_mixed_block35_fp16.safetensors', 'seedvr2_ema_7b_fp16.safetensors',
            'seedvr2_ema_7b-Q4_K_M.gguf', 'seedvr2_ema_7b_sharp_fp8_e4m3fn_mixed_block35_fp16.safetensors',
            'seedvr2_ema_7b_sharp_fp16.safetensors', 'seedvr2_ema_7b_sharp-Q4_K_M.gguf'
        ];
        grid.appendChild(_makeSelect('DiT Model:', ditModels.map(function(m) {
            return { value: m, label: m.replace('.safetensors', '').replace('.gguf', ' (GGUF)') };
        }), sv.dit_model, function(v) { sv.dit_model = v; callbacks.onUpdate(); }));

        grid.appendChild(_makeNumber('Resolution:', sv.resolution || 1080, 16, 16384, 2, function(v) { sv.resolution = v; callbacks.onUpdate(); }));
        grid.appendChild(_makeNumber('Max Res (0=none):', sv.max_resolution || 0, 0, 16384, 2, function(v) { sv.max_resolution = v; callbacks.onUpdate(); }));
        grid.appendChild(_makeNumber('Seed:', sv.seed || 42, 0, 4294967295, 1, function(v) { sv.seed = v; callbacks.onUpdate(); }));

        grid.appendChild(_makeSelect('Color Correct:', ['lab', 'wavelet', 'wavelet_adaptive', 'hsv', 'adain', 'none'],
            sv.color_correction || 'lab', function(v) { sv.color_correction = v; callbacks.onUpdate(); }));

        grid.appendChild(_makeNumber('Input Noise:', sv.input_noise_scale || 0, 0, 1, 0.001, function(v) { sv.input_noise_scale = v; callbacks.onUpdate(); }));
        grid.appendChild(_makeNumber('Latent Noise:', sv.latent_noise_scale || 0, 0, 1, 0.001, function(v) { sv.latent_noise_scale = v; callbacks.onUpdate(); }));
        grid.appendChild(_makeNumber('Blocks to Swap:', sv.blocks_to_swap || 0, 0, 36, 1, function(v) { sv.blocks_to_swap = v; callbacks.onUpdate(); }));

        grid.appendChild(_makeSelect('Attention:', ['sdpa', 'flash_attn_2', 'flash_attn_3', 'sageattn_2', 'sageattn_3'],
            sv.attention_mode || 'sdpa', function(v) { sv.attention_mode = v; callbacks.onUpdate(); }));

        grid.appendChild(_makeSelect('DiT Offload:', ['none', 'cpu'], sv.offload_device || 'cpu', function(v) { sv.offload_device = v; callbacks.onUpdate(); }));
        grid.appendChild(_makeCheckbox('Encode Tiled', sv.encode_tiled || false, function(v) { sv.encode_tiled = v; callbacks.onUpdate(); reRender(); }));
        if (sv.encode_tiled) {
            grid.appendChild(_makeNumber('Enc Tile Size:', sv.encode_tile_size || 1024, 64, 4096, 32, function(v) { sv.encode_tile_size = v; callbacks.onUpdate(); }));
            grid.appendChild(_makeNumber('Enc Overlap:', sv.encode_tile_overlap || 128, 0, 1024, 32, function(v) { sv.encode_tile_overlap = v; callbacks.onUpdate(); }));
        }
        grid.appendChild(_makeCheckbox('Decode Tiled', sv.decode_tiled || false, function(v) { sv.decode_tiled = v; callbacks.onUpdate(); reRender(); }));
        if (sv.decode_tiled) {
            grid.appendChild(_makeNumber('Dec Tile Size:', sv.decode_tile_size || 1024, 64, 4096, 32, function(v) { sv.decode_tile_size = v; callbacks.onUpdate(); }));
            grid.appendChild(_makeNumber('Dec Overlap:', sv.decode_tile_overlap || 128, 0, 1024, 32, function(v) { sv.decode_tile_overlap = v; callbacks.onUpdate(); }));
        }
    }

    // --- Florence2 Hi-Res Fix fields ---
    if (showFlorence2) {
        if (!ucfg.florence2) ucfg.florence2 = _defaultFlorence2Options();
        var f2 = ucfg.florence2;

        // Group A: Florence2 detection
        var f2Models = [
            'microsoft/Florence-2-base',
            'microsoft/Florence-2-base-ft',
            'microsoft/Florence-2-large',
            'microsoft/Florence-2-large-ft'
        ];
        grid.appendChild(_makeSelect('Florence2 Model:', f2Models, f2.model || 'microsoft/Florence-2-base', function(v) {
            f2.model = v; callbacks.onUpdate();
        }));

        grid.appendChild(_makeInput('Detect What?', f2.text_input || 'face', 'face, head, hands, eyes...', function(v) {
            f2.text_input = v; callbacks.onUpdate();
        }));

        grid.appendChild(_makeInput('Mask Select:', f2.output_mask_select || '', '(empty = all)', function(v) {
            f2.output_mask_select = v; callbacks.onUpdate();
        }));

        grid.appendChild(_makeNumber('Max New Tokens:', f2.max_new_tokens != null ? f2.max_new_tokens : 1024, 64, 2048, 32, function(v) {
            f2.max_new_tokens = v; callbacks.onUpdate();
        }));

        grid.appendChild(_makeNumber('Florence2 Input MP:', f2.florence2_input_mp != null ? f2.florence2_input_mp : 0.5, 0, 4.0, 0.01, function(v) {
            f2.florence2_input_mp = v; callbacks.onUpdate();
        }));

        // Group B: Crop & resize
        grid.appendChild(_makeNumber('Hi-Res Target MP:', f2.target_megapixels != null ? f2.target_megapixels : 1.0, 0.25, 4.0, 0.25, function(v) {
            f2.target_megapixels = v; callbacks.onUpdate();
        }));

        grid.appendChild(_makeNumber('Crop Padding (px):', f2.crop_padding != null ? f2.crop_padding : 64, 0, 256, 8, function(v) {
            f2.crop_padding = v; callbacks.onUpdate();
        }));

        // Group C: Mask shaping
        grid.appendChild(_makeNumber('Grow Mask (px):', f2.grow_expand != null ? f2.grow_expand : 32, -64, 256, 1, function(v) {
            f2.grow_expand = v; callbacks.onUpdate();
        }));

        ['left', 'top', 'right', 'bottom'].forEach(function(side) {
            var key = 'feather_' + side;
            var label = 'Feather ' + side.charAt(0).toUpperCase() + side.slice(1) + ' (px):';
            grid.appendChild(_makeNumber(label, f2[key] != null ? f2[key] : 128, 0, 256, 1, function(v) {
                f2[key] = v; callbacks.onUpdate();
            }));
        });

        // Group E: Model/LoRA source
        grid.appendChild(_makeSelect('Model/LoRA Source:', [
            { value: 'from_manifest', label: 'From manifest (per-image)' },
            { value: 'from_builder', label: 'From this Builder config' }
        ], f2.model_source || 'from_manifest', function(v) {
            f2.model_source = v; callbacks.onUpdate();
        }));

        // Group F: No-detection (single-option for forward-compat)
        grid.appendChild(_makeSelect('If No Detection:', [
            { value: 'skip', label: 'Skip + log' }
        ], f2.on_no_detection || 'skip', function(v) {
            f2.on_no_detection = v; callbacks.onUpdate();
        }));
    }

    card.appendChild(grid);

    // Iteration count display
    var countDisplay = document.createElement('div');
    countDisplay.style.cssText = 'color: #00cc00; font-family: monospace; font-size: 10px; margin-top: 4px;';
    var ratios = (ucfg.upscale_ratios || '1.5').split(',').map(function(s) { return s.trim(); }).filter(function(s) { return s; }).length;
    var denoises = (ucfg.hires_denoise || '0.3').split(',').map(function(s) { return s.trim(); }).filter(function(s) { return s; }).length;
    var models = Math.max(1, (ucfg.upscale_models || []).length);
    var combos = 1;
    if (showSeedVR2) combos = 1;
    else if (showFlorence2) combos = 1; // 1 output per input (uses single hires_denoise + target_megapixels)
    else if (showHires) combos *= ratios * denoises;
    if (showModel) combos *= models;
    var repeatCount = ucfg.repeat || 1;
    countDisplay.textContent = combos + ' upscale combo(s) per image' + (repeatCount > 1 ? ' \u00D7 ' + repeatCount + ' repeats' : '');
    card.appendChild(countDisplay);

    pipeBody.appendChild(card);
}


// ============================================================================
// MODAL RENDERING — Uses renderPipelineEditor for full pipeline UI
// ============================================================================

/**
 * Render the upscale modal
 */
function renderUpscaleModal() {
    var overlay = document.getElementById('upscale-modal-overlay');
    if (!overlay) return;
    overlay.style.display = 'flex';

    var item = upscaleModalState.imageData;
    var favCount = activeData ? activeData.filter(function(d) { return d.favorited; }).length : 0;
    var cfg = upscaleModalState.currentConfig;

    var modal = document.getElementById('upscale-modal-content');
    if (!modal) return;
    modal.textContent = '';

    // Header
    var header = document.createElement('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;';
    var title = document.createElement('h3');
    title.style.cssText = 'margin: 0; color: #fff; font-size: 16px;';
    title.textContent = 'Upscale Image';
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '\u2715';
    closeBtn.style.cssText = 'background: none; border: none; color: #999; font-size: 18px; cursor: pointer;';
    closeBtn.onclick = closeUpscaleModal;
    header.appendChild(title);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // Scope toggle
    var scopeDiv = document.createElement('div');
    scopeDiv.style.cssText = 'margin-bottom: 10px; padding: 8px; background: #252525; border-radius: 4px;';
    var radioThis = document.createElement('input');
    radioThis.type = 'radio'; radioThis.name = 'upscale-scope'; radioThis.value = 'single';
    radioThis.checked = true; radioThis.id = 'upscale-scope-single';
    var labelThis = document.createElement('label');
    labelThis.htmlFor = 'upscale-scope-single';
    labelThis.style.cssText = 'color: #ccc; font-size: 12px; cursor: pointer; margin-right: 16px;';
    labelThis.textContent = ' Upscale This Image';
    var radioAll = document.createElement('input');
    radioAll.type = 'radio'; radioAll.name = 'upscale-scope'; radioAll.value = 'favorites';
    radioAll.id = 'upscale-scope-favorites';
    var labelAll = document.createElement('label');
    labelAll.htmlFor = 'upscale-scope-favorites';
    labelAll.style.cssText = 'color: #ccc; font-size: 12px; cursor: pointer;';
    labelAll.textContent = ' Upscale All Favorited (' + favCount + ' images)';
    scopeDiv.appendChild(radioThis); scopeDiv.appendChild(labelThis);
    scopeDiv.appendChild(radioAll); scopeDiv.appendChild(labelAll);
    modal.appendChild(scopeDiv);

    // === FULL PIPELINE EDITOR ===
    var configDiv = document.createElement('div');
    configDiv.style.cssText = 'margin-bottom: 10px; padding: 8px; background: #252525; border-radius: 4px; max-height: 55vh; overflow-y: auto;';

    var configTitle = document.createElement('div');
    configTitle.style.cssText = 'font-size: 12px; color: #fff; font-weight: bold; margin-bottom: 8px;';
    configTitle.textContent = 'Upscale Pipeline Configuration';
    configDiv.appendChild(configTitle);

    // Ensure config exists
    if (!cfg) { cfg = _defaultUpscaleConfig(); upscaleModalState.currentConfig = cfg; }

    // Pipeline editor container (separate from configDiv title so reRender only clears this)
    var editorContainer = document.createElement('div');
    configDiv.appendChild(editorContainer);

    renderPipelineEditor(editorContainer, cfg, upscaleModalState.availableModels, {
        onUpdate: function() { /* config is mutated in-place, nothing to persist */ },
        onRender: function() { /* no-op — renderPipelineEditor self-re-renders via reRender() */ }
    });

    modal.appendChild(configDiv);

    // === PRESET SELECTOR ===
    var presetDiv = document.createElement('div');
    presetDiv.style.cssText = 'margin-bottom: 10px; padding: 8px; background: #1e1e1e; border-radius: 4px; border: 1px solid #333;';
    var presetRow = document.createElement('div');
    presetRow.style.cssText = 'display: flex; gap: 4px; align-items: center;';
    var presetLbl = document.createElement('span');
    presetLbl.textContent = 'Presets:';
    presetLbl.style.cssText = 'font-size: 10px; color: #666; white-space: nowrap;';
    var presetSelect = document.createElement('select');
    presetSelect.style.cssText = 'flex: 1; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 3px 6px; font-size: 10px;';
    var defaultOpt = document.createElement('option');
    defaultOpt.value = ''; defaultOpt.textContent = '-- Presets --';
    presetSelect.appendChild(defaultOpt);
    upscaleModalState.presets.forEach(function(p, i) {
        var opt = document.createElement('option');
        opt.value = i; opt.textContent = p.name;
        presetSelect.appendChild(opt);
    });

    var pLoadBtn = document.createElement('button');
    pLoadBtn.textContent = 'Load';
    pLoadBtn.style.cssText = 'background: var(--accent); color: #000; border: none; border-radius: 3px; padding: 2px 6px; font-size: 10px; cursor: pointer; font-weight: bold;';
    pLoadBtn.onclick = function() { var idx = parseInt(presetSelect.value); if (!isNaN(idx)) loadUpscalePreset(idx); };

    var pSaveBtn = document.createElement('button');
    pSaveBtn.textContent = 'Save';
    pSaveBtn.style.cssText = 'background: #555; color: #fff; border: none; border-radius: 3px; padding: 2px 6px; font-size: 10px; cursor: pointer;';
    pSaveBtn.onclick = function() { var n = prompt('Preset name:'); if (n) saveUpscalePreset(n); };

    var pDelBtn = document.createElement('button');
    pDelBtn.textContent = 'Del';
    pDelBtn.style.cssText = 'background: var(--danger); color: #fff; border: none; border-radius: 3px; padding: 2px 6px; font-size: 10px; cursor: pointer;';
    pDelBtn.onclick = function() {
        var idx = parseInt(presetSelect.value);
        if (!isNaN(idx) && idx >= 0 && idx < upscaleModalState.presets.length) {
            if (confirm('Delete "' + upscaleModalState.presets[idx].name + '"?')) deleteUpscalePreset(idx);
        }
    };

    presetRow.appendChild(presetLbl);
    presetRow.appendChild(presetSelect);
    presetRow.appendChild(pLoadBtn);
    presetRow.appendChild(pSaveBtn);
    presetRow.appendChild(pDelBtn);
    presetDiv.appendChild(presetRow);
    modal.appendChild(presetDiv);

    // Progress area (hidden until upscale starts)
    var progressDiv = document.createElement('div');
    progressDiv.id = 'upscale-modal-progress';
    progressDiv.style.cssText = 'margin-bottom: 10px; display: none;';
    var progressBar = document.createElement('div');
    progressBar.style.cssText = 'height: 6px; background: #333; border-radius: 3px; overflow: hidden;';
    var progressFill = document.createElement('div');
    progressFill.id = 'upscale-modal-progress-fill';
    progressFill.style.cssText = 'height: 100%; background: var(--accent); width: 0%; transition: width 0.3s;';
    progressBar.appendChild(progressFill);
    progressDiv.appendChild(progressBar);
    var progressText = document.createElement('div');
    progressText.id = 'upscale-modal-progress-text';
    progressText.style.cssText = 'font-size: 11px; color: #999; margin-top: 4px;';
    progressDiv.appendChild(progressText);
    modal.appendChild(progressDiv);

    // Action buttons
    var actionsDiv = document.createElement('div');
    actionsDiv.style.cssText = 'display: flex; gap: 8px; justify-content: flex-end;';
    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'background: #444; color: #fff; border: none; border-radius: 4px; padding: 6px 16px; font-size: 12px; cursor: pointer;';
    cancelBtn.onclick = function() {
        if (upscaleModalState.jobId && upscaleModalState.pollInterval) {
            // Active upscale — send cancel and let the poll detect "cancelled" status
            fetch('/config_tester/cancel_upscale', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: upscaleModalState.jobId })
            });
            cancelBtn.disabled = true;
            cancelBtn.textContent = 'Cancelling...';
            cancelBtn.style.opacity = '0.5';
        } else {
            // No active upscale — just close
            closeUpscaleModal();
        }
    };
    var startBtn = document.createElement('button');
    startBtn.textContent = 'Start Upscale';
    startBtn.id = 'upscale-start-btn';
    startBtn.style.cssText = 'background: var(--accent); color: #000; border: none; border-radius: 4px; padding: 6px 16px; font-size: 12px; cursor: pointer; font-weight: bold;';
    startBtn.onclick = startUpscaleFromModal;
    actionsDiv.appendChild(cancelBtn);
    actionsDiv.appendChild(startBtn);
    modal.appendChild(actionsDiv);
}

/**
 * Start the upscale job from the modal
 */
async function startUpscaleFromModal() {
    var cfg = upscaleModalState.currentConfig;
    if (!cfg) return;

    var scopeEl = document.querySelector('input[name="upscale-scope"]:checked');
    var scope = scopeEl ? scopeEl.value : 'single';
    var allFavorited = scope === 'favorites';
    var imageIds = allFavorited ? [] : [upscaleModalState.imageId];

    var startBtn = document.getElementById('upscale-start-btn');
    if (startBtn) { startBtn.disabled = true; startBtn.style.opacity = '0.5'; startBtn.textContent = 'Starting...'; }
    var progressDiv = document.getElementById('upscale-modal-progress');
    if (progressDiv) progressDiv.style.display = 'block';

    try {
        var resp = await fetch('/config_tester/upscale_images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_name: document.getElementById('session-input')?.value || "default",
                image_ids: imageIds,
                upscale_config: cfg,
                all_favorited: allFavorited,
            })
        });
        var result = await resp.json();
        if (result.error) {
            alert('Upscale failed: ' + result.error);
            if (startBtn) { startBtn.disabled = false; startBtn.style.opacity = '1'; startBtn.textContent = 'Start Upscale'; }
            return;
        }
        upscaleModalState.jobId = result.job_id;
        if (startBtn) startBtn.textContent = 'Upscaling...';

        // Poll for progress
        upscaleModalState.pollInterval = setInterval(async function() {
            try {
                var statusResp = await fetch('/config_tester/upscale_status?job_id=' + upscaleModalState.jobId);
                var status = await statusResp.json();
                var fill = document.getElementById('upscale-modal-progress-fill');
                var text = document.getElementById('upscale-modal-progress-text');
                if (fill && status.total > 0) fill.style.width = Math.round((status.completed / status.total) * 100) + '%';
                if (text) text.textContent = 'Upscaling ' + status.completed + '/' + status.total + '...';
                if (status.status === 'complete' || status.status === 'error' || status.status === 'cancelled') {
                    clearInterval(upscaleModalState.pollInterval);
                    upscaleModalState.pollInterval = null;
                    upscaleModalState.jobId = null;
                    if (text) {
                        if (status.status === 'complete') text.textContent = 'Complete! ' + status.completed + ' images upscaled.';
                        else if (status.status === 'cancelled') text.textContent = 'Cancelled. ' + status.completed + '/' + status.total + ' completed.';
                        else text.textContent = 'Error: ' + (status.error || 'Unknown error');
                    }
                    if (startBtn) { startBtn.disabled = false; startBtn.style.opacity = '1'; startBtn.textContent = 'Start Upscale'; }
                    // Reset cancel button to Close
                    var cBtn = document.querySelector('#upscale-modal-content button');
                    if (cBtn && (cBtn.textContent === 'Cancelling...' || cBtn.textContent === 'Cancel')) {
                        cBtn.disabled = false; cBtn.style.opacity = '1'; cBtn.textContent = 'Close';
                    }
                }
            } catch (e) { /* ignore poll errors */ }
        }, 2000);

    } catch (e) {
        alert('Failed to start upscale: ' + e);
        if (startBtn) { startBtn.disabled = false; startBtn.style.opacity = '1'; startBtn.textContent = 'Start Upscale'; }
    }
}
