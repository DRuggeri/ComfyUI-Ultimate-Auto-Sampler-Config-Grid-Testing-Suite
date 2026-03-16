// ============================================================================
// UPSCALE MODAL — Dashboard image upscaling with preset management
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
};

/**
 * Open the upscale modal for a specific image
 */
function openUpscaleModal(imageId) {
    const item = activeData ? activeData.find(d => d.id === imageId) : null;
    if (!item) return;

    upscaleModalState.open = true;
    upscaleModalState.imageId = imageId;
    upscaleModalState.imageData = item;
    upscaleModalState.jobId = null;

    // Fetch presets then render
    fetchUpscalePresets().then(() => renderUpscaleModal());
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
    const modal = document.getElementById('upscale-modal-overlay');
    if (modal) modal.style.display = 'none';
}

/**
 * Fetch upscale presets from server
 */
async function fetchUpscalePresets() {
    try {
        const resp = await fetch('/configbuilder/upscale_presets');
        if (resp.ok) {
            const data = await resp.json();
            upscaleModalState.presets = data.presets || [];
        }
    } catch (e) { console.error('Failed to fetch upscale presets:', e); }
}

/**
 * Save current config as a new preset
 */
async function saveUpscalePreset(name) {
    if (!name || !upscaleModalState.currentConfig) return;
    const preset = {
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
    upscaleModalState.currentConfig = null;
    renderUpscaleModal();
}

/**
 * Load a preset into the current config
 */
function loadUpscalePreset(index) {
    const preset = upscaleModalState.presets[index];
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
 * Build a readable summary of the current upscale config
 */
function buildUpscaleConfigSummary(config) {
    if (!config || !config.pipelines) return 'No configuration loaded. Select and load a preset above.';
    const lines = [];
    config.pipelines.forEach((p, pi) => {
        if (p.active === false) return;
        const steps = (p.steps || []).filter(s => s.active !== false);
        lines.push((p.name || ('Pipeline ' + (pi + 1))) + ': ' + steps.length + ' step(s)');
        steps.forEach((s, si) => {
            const mode = (s.mode || 'hires_only').replace(/_/g, ' ');
            const modelList = (s.upscale_models || []).map(m => m.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, ''));
            const ratio = s.upscale_ratios || '1.5';
            const denoise = s.hires_denoise || '0.3';
            let desc = '  Step ' + (si + 1) + ': ' + mode;
            if (modelList.length > 0 && modelList[0]) desc += ' \u2014 ' + modelList.join(', ');
            desc += ' \u2014 ratio ' + ratio + 'x, denoise ' + denoise;
            if (s.repeat && s.repeat > 1) desc += ' (repeat x' + s.repeat + ')';
            lines.push(desc);
        });
    });
    if (config.hires_prompt_adjust && config.hires_prompt_text) {
        lines.push('');
        lines.push('HiRes Prompt: ' + config.hires_prompt_behavior + ' \u2014 "' + config.hires_prompt_text + '"');
    }
    return lines.join('\n');
}

/**
 * Render the upscale modal
 */
function renderUpscaleModal() {
    var overlay = document.getElementById('upscale-modal-overlay');
    if (!overlay) return;
    overlay.style.display = 'flex';

    var item = upscaleModalState.imageData;
    var favCount = activeData ? activeData.filter(d => d.favorited).length : 0;

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
    scopeDiv.style.cssText = 'margin-bottom: 12px; padding: 8px; background: #252525; border-radius: 4px;';
    var scopeLabel = document.createElement('div');
    scopeLabel.style.cssText = 'font-size: 11px; color: #999; margin-bottom: 6px;';
    scopeLabel.textContent = 'Scope:';
    scopeDiv.appendChild(scopeLabel);

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

    // Preset selector
    var presetDiv = document.createElement('div');
    presetDiv.style.cssText = 'margin-bottom: 12px; padding: 8px; background: #252525; border-radius: 4px;';
    var presetLabel = document.createElement('div');
    presetLabel.style.cssText = 'font-size: 11px; color: #999; margin-bottom: 6px;';
    presetLabel.textContent = 'Upscale Preset:';
    presetDiv.appendChild(presetLabel);

    var presetRow = document.createElement('div');
    presetRow.style.cssText = 'display: flex; gap: 4px; align-items: center;';
    var presetSelect = document.createElement('select');
    presetSelect.id = 'upscale-preset-select';
    presetSelect.style.cssText = 'flex: 1; background: #1a1a1a; color: #ccc; border: 1px solid #444; border-radius: 4px; padding: 4px 6px; font-size: 11px;';
    var defaultOpt = document.createElement('option');
    defaultOpt.value = ''; defaultOpt.textContent = '-- Select a preset --';
    presetSelect.appendChild(defaultOpt);
    upscaleModalState.presets.forEach(function(p, i) {
        var opt = document.createElement('option');
        opt.value = i; opt.textContent = p.name;
        presetSelect.appendChild(opt);
    });

    var loadBtn = document.createElement('button');
    loadBtn.textContent = 'Load';
    loadBtn.style.cssText = 'background: var(--accent); color: #000; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer; font-weight: bold;';
    loadBtn.onclick = function() {
        var idx = parseInt(presetSelect.value);
        if (!isNaN(idx)) loadUpscalePreset(idx);
    };

    var saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'background: #555; color: #fff; border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer;';
    saveBtn.onclick = function() {
        if (!upscaleModalState.currentConfig) { alert('Load or configure a preset first'); return; }
        var name = prompt('Preset name:');
        if (name) saveUpscalePreset(name);
    };

    var delBtn = document.createElement('button');
    delBtn.textContent = '\uD83D\uDDD1'; // 🗑
    delBtn.style.cssText = 'background: var(--danger); color: #fff; border: none; border-radius: 4px; padding: 4px 6px; font-size: 11px; cursor: pointer;';
    delBtn.onclick = function() {
        var idx = parseInt(presetSelect.value);
        if (!isNaN(idx) && idx >= 0 && idx < upscaleModalState.presets.length) {
            if (confirm('Delete preset "' + upscaleModalState.presets[idx].name + '"?')) {
                deleteUpscalePreset(idx);
            }
        }
    };

    presetRow.appendChild(presetSelect);
    presetRow.appendChild(loadBtn);
    presetRow.appendChild(saveBtn);
    presetRow.appendChild(delBtn);
    presetDiv.appendChild(presetRow);
    modal.appendChild(presetDiv);

    // Config summary
    var summaryDiv = document.createElement('div');
    summaryDiv.style.cssText = 'margin-bottom: 12px; padding: 8px; background: #1a1a1a; border-radius: 4px; border: 1px solid #333;';
    var summaryPre = document.createElement('pre');
    summaryPre.style.cssText = 'font-size: 10px; color: #aaa; margin: 0; white-space: pre-wrap; font-family: monospace;';
    summaryPre.textContent = buildUpscaleConfigSummary(upscaleModalState.currentConfig);
    summaryDiv.appendChild(summaryPre);
    modal.appendChild(summaryDiv);

    // Progress area (hidden until upscale starts)
    var progressDiv = document.createElement('div');
    progressDiv.id = 'upscale-modal-progress';
    progressDiv.style.cssText = 'margin-bottom: 12px; display: none;';
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
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: upscaleModalState.jobId })
            });
        }
        closeUpscaleModal();
    };

    var startBtn = document.createElement('button');
    startBtn.textContent = 'Start Upscale';
    startBtn.id = 'upscale-start-btn';
    startBtn.style.cssText = 'background: var(--accent); color: #000; border: none; border-radius: 4px; padding: 6px 16px; font-size: 12px; cursor: pointer; font-weight: bold;';
    startBtn.disabled = !upscaleModalState.currentConfig;
    if (!upscaleModalState.currentConfig) startBtn.style.opacity = '0.5';
    startBtn.onclick = startUpscaleFromModal;

    actionsDiv.appendChild(cancelBtn);
    actionsDiv.appendChild(startBtn);
    modal.appendChild(actionsDiv);
}

/**
 * Start the upscale job from the modal
 */
async function startUpscaleFromModal() {
    if (!upscaleModalState.currentConfig) return;

    var scopeEl = document.querySelector('input[name="upscale-scope"]:checked');
    var scope = scopeEl ? scopeEl.value : 'single';
    var allFavorited = scope === 'favorites';
    var imageIds = allFavorited ? [] : [upscaleModalState.imageId];

    // Disable start button, show progress
    var startBtn = document.getElementById('upscale-start-btn');
    if (startBtn) { startBtn.disabled = true; startBtn.style.opacity = '0.5'; startBtn.textContent = 'Starting...'; }
    var progressDiv = document.getElementById('upscale-modal-progress');
    if (progressDiv) progressDiv.style.display = 'block';

    try {
        var resp = await fetch('/config_tester/upscale_images', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_name: sessionName,
                image_ids: imageIds,
                upscale_config: upscaleModalState.currentConfig,
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
