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

// Default upscale step config
function _defaultUpscaleStep() {
    return {
        active: true, mode: "hires_only", repeat: 1,
        upscale_models: [], upscale_ratios: "1.5", upscale_size: "2.0",
        hires_denoise: "0.3", hires_steps: 0, tiled_vae: false, tile_size: 512,
        resize_method: "bilinear",
    };
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
        var resp = await fetch('/configbuilder/model_lists', { method: 'POST' });
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
    var preset = {
        name: name,
        pipelines: JSON.parse(JSON.stringify(upscaleModalState.currentConfig.pipelines)),
        hires_prompt_adjust: upscaleModalState.currentConfig.hires_prompt_adjust || false,
        hires_prompt_behavior: upscaleModalState.currentConfig.hires_prompt_behavior || "append_end",
        hires_prompt_text: upscaleModalState.currentConfig.hires_prompt_text || "",
    };
    upscaleModalState.presets.push(preset);
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

    // === INLINE UPSCALE CONFIGURATION ===
    var configDiv = document.createElement('div');
    configDiv.style.cssText = 'margin-bottom: 10px; padding: 8px; background: #252525; border-radius: 4px;';

    var configTitle = document.createElement('div');
    configTitle.style.cssText = 'font-size: 12px; color: #fff; font-weight: bold; margin-bottom: 8px;';
    configTitle.textContent = 'Upscale Settings';
    configDiv.appendChild(configTitle);

    // Ensure config exists
    if (!cfg) { cfg = _defaultUpscaleConfig(); upscaleModalState.currentConfig = cfg; }
    var step = cfg.pipelines[0] && cfg.pipelines[0].steps[0] ? cfg.pipelines[0].steps[0] : _defaultUpscaleStep();

    // Mode selector
    configDiv.appendChild(_makeSelect('Mode:', [
        { value: 'hires_only', label: 'HiRes Fix Only' },
        { value: 'model_only', label: 'Model Upscale Only' },
        { value: 'model_then_hires', label: 'Model + HiRes Fix' },
    ], step.mode, function(v) {
        step.mode = v;
        // Show/hide model selector based on mode
        if (modelRow) modelRow.style.display = (v === 'hires_only') ? 'none' : 'flex';
        if (denoiseRow) denoiseRow.style.display = (v === 'model_only') ? 'none' : 'flex';
    }));

    // Upscale model selector
    var showModel = step.mode !== 'hires_only';
    var modelOptions = [{ value: '', label: '-- Select Model --' }];
    upscaleModalState.availableModels.forEach(function(m) {
        var short = m.replace(/\\/g, '/').split('/').pop();
        modelOptions.push({ value: m, label: short });
    });
    var modelRow = _makeSelect('Model:', modelOptions, step.upscale_models[0] || '', function(v) {
        step.upscale_models = v ? [v] : [];
    });
    modelRow.style.display = showModel ? 'flex' : 'none';
    configDiv.appendChild(modelRow);

    // Ratio
    configDiv.appendChild(_makeInput('Ratio:', step.upscale_ratios, '1.5', function(v) {
        step.upscale_ratios = v;
    }));

    // Denoise
    var showDenoise = step.mode !== 'model_only';
    var denoiseRow = _makeInput('Denoise:', step.hires_denoise, '0.3', function(v) {
        step.hires_denoise = v;
    });
    denoiseRow.style.display = showDenoise ? 'flex' : 'none';
    configDiv.appendChild(denoiseRow);

    // HiRes Steps (0 = use original steps)
    configDiv.appendChild(_makeInput('HiRes Steps:', step.hires_steps || '0', '0 = use original', function(v) {
        step.hires_steps = parseInt(v) || 0;
    }));

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
        if (upscaleModalState.jobId) {
            fetch('/config_tester/cancel_upscale', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: upscaleModalState.jobId })
            });
        }
        closeUpscaleModal();
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
                    if (text) {
                        if (status.status === 'complete') text.textContent = 'Complete! ' + status.completed + ' images upscaled.';
                        else if (status.status === 'cancelled') text.textContent = 'Cancelled. ' + status.completed + '/' + status.total + ' completed.';
                        else text.textContent = 'Error: ' + (status.error || 'Unknown error');
                    }
                    if (startBtn) { startBtn.disabled = false; startBtn.style.opacity = '1'; startBtn.textContent = 'Start Upscale'; }
                }
            } catch (e) { /* ignore poll errors */ }
        }, 2000);

    } catch (e) {
        alert('Failed to start upscale: ' + e);
        if (startBtn) { startBtn.disabled = false; startBtn.style.opacity = '1'; startBtn.textContent = 'Start Upscale'; }
    }
}
