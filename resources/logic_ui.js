/**
 * UI COMPONENTS - COMPACT LAYOUT WITH FILTERS POPUP
 * Fixed: Index tag z-index, time tag position
 * Added: Favorites feature, Filters popup, Prompt/Size/Seed filters
 */

// --- LABEL MODE FUNCTIONS ---

/**
 * Compute which values are global (same on every card) across activeData.
 * Called once when label mode is toggled on or when data changes while labels are active.
 */
function computeLabelGlobalValues() {
    if (!activeData || activeData.length === 0) {
        labelGlobalValues = null;
        return;
    }

    const fields = ['model', 'lora', 'sampler', 'scheduler', 'cfg', 'steps', 'seed', 'denoise', 'positive',
                     'upscale', 'upscaleMode', 'upscaleModel', 'upscaleRatio', 'upscaleDenoise',
                     'upscaleResizeMethod', 'upscaleHiresSteps', 'upscaleTiling',
                     'hiresPromptBehavior', 'hiresPromptText'];
    const valueSets = {};
    fields.forEach(f => valueSets[f] = new Set());

    for (const item of activeData) {
        valueSets.model.add(item.model || meta.model || "Default");
        valueSets.lora.add(item.lora || "None");
        valueSets.sampler.add(item.sampler || "");
        valueSets.scheduler.add(item.scheduler || "");
        valueSets.cfg.add(String(item.cfg));
        valueSets.steps.add(String(item.steps));
        valueSets.seed.add(String(item.seed));
        valueSets.denoise.add(String(item.denoise));
        valueSets.positive.add(item.positive || meta.positive || "");
        // Upscale composite (for the "all" toggle)
        const upParts = [];
        if (item.upscale_mode) upParts.push(item.upscale_mode);
        if (item.upscale_model) upParts.push(item.upscale_model);
        if (item.upscale_ratio) upParts.push('x' + item.upscale_ratio);
        if (item.upscale_denoise !== undefined && item.upscale_denoise !== null) upParts.push('dn:' + item.upscale_denoise);
        valueSets.upscale.add(upParts.length > 0 ? upParts.join(' ') : '');
        // Individual upscale fields (stringify arrays for set comparison)
        const toStr = (v) => v === undefined || v === null ? '' : (Array.isArray(v) ? JSON.stringify(v) : String(v));
        valueSets.upscaleMode.add(toStr(item.upscale_mode));
        valueSets.upscaleModel.add(toStr(item.upscale_model));
        valueSets.upscaleRatio.add(toStr(item.upscale_ratio));
        valueSets.upscaleDenoise.add(toStr(item.upscale_denoise));
        valueSets.upscaleResizeMethod.add(toStr(item.upscale_resize_method));
        valueSets.upscaleHiresSteps.add(toStr(item.upscale_hires_steps));
        // Tiling composite: combine tiled_vae + tiled_sampling info
        const tileParts = [];
        if (item.upscale_tiled_vae) tileParts.push('VAE:' + toStr(item.upscale_tile_size));
        if (item.upscale_tiled_sampling) tileParts.push('Sample:' + toStr(item.upscale_tile_w) + 'x' + toStr(item.upscale_tile_h));
        valueSets.upscaleTiling.add(tileParts.length > 0 ? tileParts.join(' ') : '');
        valueSets.hiresPromptBehavior.add(toStr(item.hires_prompt_behavior));
        valueSets.hiresPromptText.add(toStr(item.hires_prompt_text));
    }

    // A value is "global" if only 1 unique value exists for that field
    labelGlobalValues = {};
    fields.forEach(f => {
        labelGlobalValues[f] = valueSets[f].size === 1;
    });

    // For lora unique-only: also track which individual loras appear on every card
    if (labelMode.fields.loraUniqueOnly) {
        const loraCountMap = {};
        let totalCards = activeData.length;
        for (const item of activeData) {
            const loraStr = item.lora || "None";
            if (loraStr === "None") continue;
            const parts = loraStr.split(" + ");
            const seen = new Set();
            for (const part of parts) {
                const name = part.split(":")[0];
                if (!seen.has(name)) {
                    seen.add(name);
                    loraCountMap[name] = (loraCountMap[name] || 0) + 1;
                }
            }
        }
        labelGlobalValues._loraGlobalNames = new Set();
        for (const [name, count] of Object.entries(loraCountMap)) {
            if (count === totalCards) {
                labelGlobalValues._loraGlobalNames.add(name);
            }
        }
    }
}

/**
 * Build label overlay HTML for a single card data item.
 */
function buildLabelOverlay(d) {
    if (!labelMode.enabled) return '';

    const uniqueOnly = labelMode.fields.loraUniqueOnly;
    const tags = [];

    if (labelMode.fields.model) {
        const val = d.model || meta.model || "Default";
        if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.model) {
            const short = val.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '');
            tags.push(`<span class="label-tag label-model" title="${val}">${short}</span>`);
        }
    }

    if (labelMode.fields.lora) {
        const loraStr = d.lora || "None";
        if (loraStr !== "None") {
            const parts = loraStr.split(" + ");
            for (const part of parts) {
                const name = part.split(":")[0];
                const shortName = name.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '');
                // Skip loras that are on every card when unique-only is on
                if (uniqueOnly && labelGlobalValues && labelGlobalValues._loraGlobalNames && labelGlobalValues._loraGlobalNames.has(name)) continue;
                tags.push(`<span class="label-tag label-lora" title="${part}">${shortName}</span>`);
            }
        }
    }

    if (labelMode.fields.prompt) {
        const val = d.positive || meta.positive || "";
        if (val && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.positive)) {
            const short = val.length > 40 ? val.substring(0, 38) + '...' : val;
            tags.push(`<span class="label-tag label-prompt" title="${val}">${short}</span>`);
        }
    }

    if (labelMode.fields.sampler) {
        const val = d.sampler || "";
        if (val && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.sampler)) {
            tags.push(`<span class="label-tag label-sampler">${val}</span>`);
        }
    }

    if (labelMode.fields.scheduler) {
        const val = d.scheduler || "";
        if (val && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.scheduler)) {
            tags.push(`<span class="label-tag label-scheduler">${val}</span>`);
        }
    }

    if (labelMode.fields.cfg) {
        const val = d.cfg;
        if (val !== undefined && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.cfg)) {
            tags.push(`<span class="label-tag label-cfg">CFG:${val}</span>`);
        }
    }

    if (labelMode.fields.steps) {
        const val = d.steps;
        if (val !== undefined && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.steps)) {
            tags.push(`<span class="label-tag label-steps">Steps:${val}</span>`);
        }
    }

    if (labelMode.fields.seed) {
        const val = d.seed;
        if (val !== undefined && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.seed)) {
            tags.push(`<span class="label-tag label-seed">Seed:${val}</span>`);
        }
    }

    if (labelMode.fields.denoise) {
        const val = d.denoise;
        if (val !== undefined && (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.denoise)) {
            tags.push(`<span class="label-tag label-denoise">Dn:${val}</span>`);
        }
    }

    // --- Upscale labels (each on its own line via class) ---
    const anyUpscaleField = labelMode.fields.upscale || labelMode.fields.upscaleMode || labelMode.fields.upscaleModel ||
        labelMode.fields.upscaleRatio || labelMode.fields.upscaleDenoise || labelMode.fields.upscaleResizeMethod ||
        labelMode.fields.upscaleHiresSteps || labelMode.fields.upscaleTiling;

    if (anyUpscaleField && d.upscaled) {
        // Helper: format a value that may be scalar or array (stacking mode) into a display string
        const fmtVal = (v, prefix, transform) => {
            if (v === undefined || v === null) return null;
            const fn = transform || (x => String(x));
            if (Array.isArray(v)) return prefix + v.map(fn).join(', ');
            return prefix + fn(v);
        };
        const shortModelName = (m) => m ? m.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '') : '';
        const isStacked = d.upscale_stacked;

        // "Upscale (all)" — combined summary tag
        if (labelMode.fields.upscale) {
            const parts = [];
            if (d.upscale_mode) {
                const modes = Array.isArray(d.upscale_mode) ? d.upscale_mode.map(m => m.replace(/_/g, ' ')).join(', ') : d.upscale_mode.replace(/_/g, ' ');
                parts.push(modes);
            }
            if (d.upscale_model) {
                const models = Array.isArray(d.upscale_model) ? d.upscale_model.map(shortModelName).join(', ') : shortModelName(d.upscale_model);
                parts.push(models);
            }
            if (d.upscale_ratio) {
                const ratios = Array.isArray(d.upscale_ratio) ? d.upscale_ratio.map(r => 'x' + r).join(', ') : 'x' + d.upscale_ratio;
                parts.push(ratios);
            }
            const label = parts.length > 0 ? (isStacked ? '⛓ ' : '') + parts.join(' | ') : 'Upscaled';
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscale) {
                tags.push(`<span class="label-tag label-upscale" title="${label}">${label}</span>`);
            }
        }
        // Individual upscale fields — each on its own line
        if (labelMode.fields.upscaleMode && d.upscale_mode) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleMode) {
                const val = fmtVal(d.upscale_mode, 'Mode: ', m => m.replace(/_/g, ' '));
                tags.push(`<span class="label-tag label-upscale">${val}</span>`);
            }
        }
        if (labelMode.fields.upscaleModel && d.upscale_model) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleModel) {
                const raw = d.upscale_model;
                const val = fmtVal(raw, 'Model: ', shortModelName);
                const full = Array.isArray(raw) ? raw.join(', ') : raw;
                tags.push(`<span class="label-tag label-upscale" title="${full}">${val}</span>`);
            }
        }
        if (labelMode.fields.upscaleRatio && d.upscale_ratio !== undefined) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleRatio) {
                const val = fmtVal(d.upscale_ratio, 'Ratio: ', r => 'x' + r);
                tags.push(`<span class="label-tag label-upscale">${val}</span>`);
            }
        }
        if (labelMode.fields.upscaleDenoise && d.upscale_denoise !== undefined) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleDenoise) {
                const val = fmtVal(d.upscale_denoise, 'Denoise: ');
                tags.push(`<span class="label-tag label-upscale">${val}</span>`);
            }
        }
        if (labelMode.fields.upscaleResizeMethod && d.upscale_resize_method) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleResizeMethod) {
                const val = fmtVal(d.upscale_resize_method, 'Resize: ');
                tags.push(`<span class="label-tag label-upscale">${val}</span>`);
            }
        }
        if (labelMode.fields.upscaleHiresSteps && d.upscale_hires_steps) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleHiresSteps) {
                const val = fmtVal(d.upscale_hires_steps, 'HiRes Steps: ');
                tags.push(`<span class="label-tag label-upscale">${val}</span>`);
            }
        }
        if (labelMode.fields.upscaleTiling) {
            const tileParts = [];
            if (d.upscale_tiled_vae) {
                const ts = d.upscale_tile_size;
                tileParts.push('VAE Tile: ' + (Array.isArray(ts) ? ts.join(', ') : (ts || 512)));
            }
            if (d.upscale_tiled_sampling) {
                const tw = d.upscale_tile_w;
                const th = d.upscale_tile_h;
                if (Array.isArray(tw)) {
                    tileParts.push('Sample Tile: ' + tw.map((w, i) => w + 'x' + (th[i] || w)).join(', '));
                } else {
                    tileParts.push('Sample Tile: ' + (tw || 512) + 'x' + (th || 512));
                }
            }
            if (tileParts.length > 0) {
                if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscaleTiling) {
                    for (const tp of tileParts) {
                        tags.push(`<span class="label-tag label-upscale">${tp}</span>`);
                    }
                }
            }
        }
        if (labelMode.fields.hiresPromptBehavior && d.hires_prompt_behavior) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.hiresPromptBehavior) {
                const val = fmtVal(d.hires_prompt_behavior, 'HiRes Prompt: ', b => b.replace(/_/g, ' '));
                tags.push(`<span class="label-tag label-hiresPrompt">${val}</span>`);
            }
        }
        if (labelMode.fields.hiresPromptText && d.hires_prompt_text) {
            if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.hiresPromptText) {
                const text = d.hires_prompt_text;
                const short = text.length > 30 ? text.substring(0, 28) + '...' : text;
                tags.push(`<span class="label-tag label-hiresPrompt" title="${text}">${short}</span>`);
            }
        }
    } else if (anyUpscaleField && !d.upscaled) {
        // Show "No Upscale" only when there's a mix of upscaled and non-upscaled images
        if (!uniqueOnly || !labelGlobalValues || !labelGlobalValues.upscale) {
            const hasAnyUpscaled = activeData && activeData.some(i => i.upscaled);
            if (hasAnyUpscaled) {
                tags.push(`<span class="label-tag label-upscale" style="opacity:0.5;">No Upscale</span>`);
            }
        }
    }

    if (tags.length === 0) return '';
    return `<div class="label-overlay">${tags.join('')}</div>`;
}

/**
 * Toggle label mode on/off
 */
function toggleLabelMode(enabled) {
    labelMode.enabled = enabled;
    const fieldsContainer = document.getElementById('label-fields-container');
    if (fieldsContainer) fieldsContainer.style.display = enabled ? 'block' : 'none';

    if (enabled) {
        computeLabelGlobalValues();
    }
    saveLabelPreferences();
    refreshLabelOverlays();
}

/**
 * Update label field selections from checkboxes
 */
function updateLabelFields() {
    const fields = ['model', 'lora', 'prompt', 'sampler', 'scheduler', 'cfg', 'steps', 'seed', 'denoise', 'upscale',
                     'upscaleMode', 'upscaleModel', 'upscaleRatio', 'upscaleDenoise', 'upscaleResizeMethod', 'upscaleHiresSteps', 'upscaleTiling',
                     'hiresPromptBehavior', 'hiresPromptText'];
    fields.forEach(f => {
        const cb = document.getElementById(`label-field-${f}`);
        if (cb) labelMode.fields[f] = cb.checked;
    });
    const uniqueCb = document.getElementById('label-unique-only');
    if (uniqueCb) labelMode.fields.loraUniqueOnly = uniqueCb.checked;

    if (labelMode.enabled) {
        computeLabelGlobalValues();
    }
    saveLabelPreferences();
    refreshLabelOverlays();
}

/**
 * Save label preferences to localStorage
 */
function saveLabelPreferences() {
    try {
        localStorage.setItem('ultimate_grid_labels', JSON.stringify(labelMode));
    } catch (e) { /* ignore */ }
}

/**
 * Load label preferences from localStorage and sync UI checkboxes
 */
function loadLabelPreferences() {
    try {
        const saved = localStorage.getItem('ultimate_grid_labels');
        if (saved) {
            const parsed = JSON.parse(saved);
            labelMode.enabled = parsed.enabled || false;
            if (parsed.fields) {
                Object.assign(labelMode.fields, parsed.fields);
            }
        }
    } catch (e) { /* ignore */ }

    // Sync UI checkboxes
    const toggle = document.getElementById('label-mode-toggle');
    if (toggle) toggle.checked = labelMode.enabled;

    const fieldsContainer = document.getElementById('label-fields-container');
    if (fieldsContainer) fieldsContainer.style.display = labelMode.enabled ? 'block' : 'none';

    const fields = ['model', 'lora', 'prompt', 'sampler', 'scheduler', 'cfg', 'steps', 'seed', 'denoise', 'upscale',
                     'upscaleMode', 'upscaleModel', 'upscaleRatio', 'upscaleDenoise', 'upscaleResizeMethod', 'upscaleHiresSteps', 'upscaleTiling',
                     'hiresPromptBehavior', 'hiresPromptText'];
    fields.forEach(f => {
        const cb = document.getElementById(`label-field-${f}`);
        if (cb) cb.checked = labelMode.fields[f] || false;
    });

    const uniqueCb = document.getElementById('label-unique-only');
    if (uniqueCb) uniqueCb.checked = labelMode.fields.loraUniqueOnly !== false;

    if (labelMode.enabled) {
        computeLabelGlobalValues();
    }
}

/**
 * Refresh label overlays on all visible cards (add/remove/update)
 */
function refreshLabelOverlays() {
    for (const [id, card] of nodeMap) {
        const d = card._dataItem;
        if (!d) continue;

        // Remove existing label overlay
        const existing = card.querySelector('.label-overlay');
        if (existing) existing.remove();

        // Add new one if enabled
        if (labelMode.enabled) {
            const html = buildLabelOverlay(d);
            if (html) {
                const wrapper = card.querySelector('.img-wrapper');
                if (wrapper) {
                    wrapper.insertAdjacentHTML('beforeend', html);
                }
            }
        }
    }
}

// Cache for filter buttons
let filterButtonCache = {};

// Toggle Filters Popup
function toggleFiltersPopup() {
    const popup = document.getElementById('filters-popup');
    const overlay = document.getElementById('filters-overlay');

    if (popup.style.display === 'none' || !popup.style.display) {
        popup.style.display = 'block';
        overlay.style.display = 'block';
        document.body.style.overflow = 'hidden'; // Prevent background scroll
    } else {
        popup.style.display = 'none';
        overlay.style.display = 'none';
        document.body.style.overflow = '';
    }
}


// Toggle Favorites Filter
function toggleFavoritesFilter() {
    topFilters.showFavorites = !topFilters.showFavorites;
    
    const btn = document.getElementById('top-filter-favorites');
    if (btn) {
        if (topFilters.showFavorites) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
    
    updateDataPipeline();
    console.log('[Top Filter] Favorites:', topFilters.showFavorites ? 'ON' : 'OFF');
}

// Toggle Non-Favorited Filter
function toggleNonFavoritedFilter() {
    topFilters.showNonFavorited = !topFilters.showNonFavorited;
    
    const btn = document.getElementById('top-filter-nonfavorited');
    if (btn) {
        if (topFilters.showNonFavorited) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
    
    updateDataPipeline();
    console.log('[Top Filter] Non-Favorited:', topFilters.showNonFavorited ? 'ON' : 'OFF');
}

// Toggle Rejected Filter
function toggleRejectedFilter() {
    topFilters.showRejected = !topFilters.showRejected;
    
    const btn = document.getElementById('top-filter-rejected');
    if (btn) {
        if (topFilters.showRejected) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    }
    
    updateDataPipeline();
    console.log('[Top Filter] Rejected:', topFilters.showRejected ? 'ON' : 'OFF');
}
// Settings Panel Toggle (unified cog + session)
function toggleCogMenu() {
    const panel = document.getElementById('cog-menu-dropdown');
    const overlay = document.getElementById('cog-menu-overlay');
    if (!panel) return;

    if (panel.style.display === 'none' || !panel.style.display) {
        panel.style.display = 'block';
        if (overlay) overlay.style.display = 'block';
        document.body.style.overflow = 'hidden';
    } else {
        panel.style.display = 'none';
        if (overlay) overlay.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Close popup on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        // Close Revise modal first (highest priority)
        const reviseModal = document.getElementById('modal');
        if (reviseModal && reviseModal.style.display !== 'none' && reviseModal.style.display !== '') {
            closeM();
            return;
        }

        // Close analytics results modal
        const analyticsModal = document.getElementById('analytics-results-modal');
        if (analyticsModal) {
            analyticsModal.remove();
            return;
        }

        // Close settings panel
        const cogPanel = document.getElementById('cog-menu-dropdown');
        if (cogPanel && cogPanel.style.display !== 'none') {
            toggleCogMenu();
            return;
        }

        // Close filters popup
        const filtersPopup = document.getElementById('filters-popup');
        if (filtersPopup && filtersPopup.style.display !== 'none') {
            toggleFiltersPopup();
        }
    }
});

// Truncate long text with tooltip
function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Initialize Filter Buttons (with caching)
function initFilters() {
    if (!activeData || activeData.length === 0) return;

    // Ensure all filter Sets exist (add new ones if missing)
    const filterKeys = ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'];
    filterKeys.forEach(key => {
        if (!filters.hasOwnProperty(key) || !(filters[key] instanceof Set)) {
            filters[key] = new Set();
        }
    });

    ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'].forEach(key => {
        const unique = [...new Set(activeData.map(d => {
            if (key === 'model') return d.model || meta.model || "Default";
            if (key === 'positive') {
                const st = document.getElementById('toggle-triggers')?.checked !== false;
                return st ? (d.positive || meta.positive || "") : (d.config_positive || d.positive || meta.positive || "");
            }
            if (key === 'negative') {
                const st = document.getElementById('toggle-triggers')?.checked !== false;
                return st ? (d.negative || meta.negative || "") : (d.config_negative || d.negative || meta.negative || "");
            }
            if (key === 'size') return `${d.width}x${d.height}`;
            return d[key];
        }))].sort();

        const container = document.getElementById('filter-' + key);
        if (!container) return;

        const cacheKey = unique.join(',');
        if (filterButtonCache[key] === cacheKey) {
            return;
        }

        filterButtonCache[key] = cacheKey;
        container.innerHTML = '';

        unique.forEach(val => {
            const safeVal = String(val).replace(/[^a-zA-Z0-9]/g, '');
            const btnId = `btn-${key}-${safeVal}`;

            let b = document.createElement('button');
            b.id = btnId;
            b.className = `filter-btn active ${key}`;

            let label = val;
            let fullText = val;

            // Handle special formatting for different filter types
            if (key === 'lora') {
                if (val === "None") {
                    label = "None";
                } else if (val.includes(" + ")) {
                    label = "Stack";
                    fullText = val.replace(/ \+ /g, '\n');
                } else {
                    let clean = val.replace(/\\/g, '/').split('/').pop().split(':')[0];
                    label = truncateText(clean, 12);
                    fullText = val;
                }
            } else if (key === 'model') {
                let clean = val.replace(/\\/g, '/').split('/').pop();
                label = truncateText(clean, 12);
                fullText = val;
            } else if (key === 'positive' || key === 'negative') {
                // Truncate prompts to 30 characters for button display
                label = truncateText(val, 30);
                fullText = val;
            } else if (key === 'seed') {
                // Display seeds in a more readable format
                label = String(val);
                fullText = val;
            }

            b.innerText = label;
            b.title = fullText;

            // Isolate filter: deselect all others, or re-select all if already isolated
            const isolateFilter = () => {
                // Check if this is the only active filter
                const isOnlyActive = filters[key].size === 1 && filters[key].has(val);

                if (isOnlyActive) {
                    // If it's the only one active, select all instead
                    unique.forEach(v => filters[key].add(v));
                    const allButtons = container.querySelectorAll('.filter-btn');
                    allButtons.forEach(btn => btn.classList.add('active'));
                } else {
                    // Clear all filters of this type, add only this one
                    filters[key].clear();
                    filters[key].add(val);
                    const allButtons = container.querySelectorAll('.filter-btn');
                    allButtons.forEach(btn => btn.classList.remove('active'));
                    b.classList.add('active');
                }

                updateDataPipeline();
            };

            b.onclick = (e) => {
                // Shift-click: Isolate this filter (deselect all others of this type)
                if (e.shiftKey) {
                    e.preventDefault();
                    isolateFilter();
                } else {
                    // Normal click: Toggle this filter
                    if (filters[key].has(val)) {
                        filters[key].delete(val);
                        b.classList.remove('active');
                    } else {
                        filters[key].add(val);
                        b.classList.add('active');
                    }

                    updateDataPipeline();
                }
            };

            // Double-click: Isolate this filter (same as shift-click)
            b.ondblclick = (e) => {
                e.preventDefault();
                isolateFilter();
            };

            filters[key].add(val);
            container.appendChild(b);
        });
    });
}

// Toggle trigger word visibility in prompts
function toggleTriggerWords(showTriggers) {
    // Rebuild filters with new prompt mode
    initFilters();
    updateDataPipeline();
    // If modal is open, refresh prompt display
    if (window.currentModalId) {
        openM(window.currentModalId);
    }
}


let pendingSaveItems = new Map();  // CHANGED: Set -> Map
let saveTimer = null;
const SAVE_BATCH_DELAY = 100;

/**
 * OPTIMIZED: Schedule a save that only sends changed items
 */
function scheduleBatchedSave() {
    if (saveTimer) {
        clearTimeout(saveTimer);
    }

    saveTimer = setTimeout(async () => {
        if (pendingSaveItems.size === 0) return;

        console.log(`[Save] 💾 Sending ${pendingSaveItems.size} changed items to server`);

        try {
            const sessionName = document.getElementById('session-input')?.value || "default";

            // Convert Map to array of items
            const changedItems = Array.from(pendingSaveItems.values());

            // CHANGED: Use new endpoint that only accepts changed items
            const response = await fetch('/config_tester/save_changes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_name: sessionName,
                    changed_items: changedItems  // Only changed items!
                })
            });

            if (!response.ok) {
                throw new Error(`Save failed: ${response.status}`);
            }

            console.log(`[Save] ✅ Successfully saved ${pendingSaveItems.size} changes`);
            pendingSaveItems.clear();

        } catch (error) {
            console.error('[Save] ❌ Batch save failed:', error);
            // Don't clear pendingSaveItems - will retry on next change
        }
    }, SAVE_BATCH_DELAY);
}
function markItemChanged(item) {
    if (!item || !item.id) return;

    // Store the full item object, not just the ID
    pendingSaveItems.set(item.id, item);
    scheduleBatchedSave();
}
// Lightweight JSON update (separate debounce from save)
let jsonUpdateTimer = null;
const JSON_UPDATE_DELAY = 500; // 500ms debounce

function scheduleJSONUpdate() {
    if (jsonUpdateTimer) {
        clearTimeout(jsonUpdateTimer);
    }

    jsonUpdateTimer = setTimeout(() => {
        updateJSONs(processedData);
    }, JSON_UPDATE_DELAY);
}

// Toggle Favorite

async function toggleFavorite(element) {
    // [OPTIMIZATION] Find parent card and grab data directly (O(1) access)
    // No getElementById, no array.find, no iteration.
    const card = element.closest('.card');
    if (!card || !card._dataItem) return;

    const item = card._dataItem;

    // Update Data
    item.favorited = !item.favorited;

    // Update UI - Scope querySelector to just this card for extra speed
    const favBtn = card.querySelector('.favorite-btn');

    if (favBtn) {
        favBtn.classList.toggle('favorited', item.favorited);
        favBtn.innerText = item.favorited ? '★' : '☆';

        // Simple animation
        favBtn.style.transform = 'scale(1.2)';
        setTimeout(() => favBtn.style.transform = 'scale(1)', 120);
    }

    markItemChanged(item);
    scheduleJSONUpdate();
}


/**
 * Show error alert popup with details
 */
function showSaveErrorAlert(title, message, technicalDetails = '') {
    // Remove any existing error alert
    const existingAlert = document.getElementById('save-error-alert');
    if (existingAlert) {
        existingAlert.remove();
    }

    // Create overlay
    const overlay = document.createElement('div');
    overlay.id = 'save-error-alert';
    overlay.className = 'error-alert-overlay';

    // Create popup
    const popup = document.createElement('div');
    popup.className = 'error-alert-popup';

    // Build details section if we have technical info
    const detailsHtml = technicalDetails ? `
        <details class="error-alert-details">
            <summary>Technical Details</summary>
            <pre>${technicalDetails}</pre>
        </details>
    ` : '';

    popup.innerHTML = `
        <div class="error-alert-header">
            <span class="error-alert-icon">⚠️</span>
            <h3>${title}</h3>
        </div>
        <p class="error-alert-message">${message}</p>
        ${detailsHtml}
        <div class="error-alert-actions">
            <button class="error-alert-button error-alert-button-primary" onclick="this.closest('.error-alert-overlay').remove()">
                OK
            </button>
        </div>
    `;

    overlay.appendChild(popup);
    document.body.appendChild(overlay);

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.remove();
        }
    });

    // Close on Escape key
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            overlay.remove();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);

    // Auto-close after 12 seconds
    setTimeout(() => {
        if (overlay.parentNode) {
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 200);
        }
    }, 12000);
}


// Build a pure ComfyUI nodes workflow JSON from image config data
// Reusable version of the clipboard copy logic — returns the workflow object
function buildComfyNodesWorkflow(d) {
    // Parse LoRA string into array
    const loras = [];
    if (d.lora && d.lora !== "None") {
        // Fix: Filter empty entries to prevent 'ghost' nodes from trailing " + "
        const loraEntries = d.lora.split(' + ').filter(e => e.trim().length > 0);
        loraEntries.forEach(entry => {
            const parts = entry.split(':');
            const name = parts[0];
            const strength_model = parseFloat(parts[1] || 1.0);
            const strength_clip = parseFloat(parts[2] || strength_model);
            loras.push({ name, strength_model, strength_clip });
        });
    }

    // Generate node IDs
    let nodeId = 1;
    const checkpointNode = nodeId++;
    const loraNodes = loras.map(() => nodeId++);
    const positiveClipNode = nodeId++;
    const negativeClipNode = nodeId++;
    const emptyLatentNode = nodeId++;
    const ksamplerNode = nodeId++;
    const vaeDecodeNode = nodeId++;
    const previewNode = nodeId++;

    if (!crypto.randomUUID) {
        crypto.randomUUID = function () {
            return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, c =>
                (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
            );
        };
    }

    // Build the workflow JSON
    const workflow = {
        id: crypto.randomUUID(),
        revision: 0,
        last_node_id: nodeId - 1,
        last_link_id: 100, // We will update this at the end
        nodes: [],
        links: [],
        groups: [],
        config: {},
        extra: {
            workflowRendererVersion: "LG",
            ds: { scale: 0.573, offset: [488, 377] }
        },
        version: 0.4
    };

    // --- 1. CREATE NODES ---
    // (This section remains mostly the same, just ensured clean initialization)

    // Checkpoint
    workflow.nodes.push({
        id: checkpointNode,
        type: "CheckpointLoaderSimple",
        pos: [-200, 60],
        size: [315, 98],
        flags: {}, order: 0, mode: 0,
        inputs: [],
        outputs: [
            { name: "MODEL", type: "MODEL", links: [] },
            { name: "CLIP", type: "CLIP", links: [] },
            { name: "VAE", type: "VAE", links: [] }
        ],
        properties: { "Node name for S&R": "CheckpointLoaderSimple" },
        widgets_values: [d.model || "XL\\waiANIPONYXL_v140_fp8_e4m3fn_full.safetensors"]
    });

    // LoRAs
    loras.forEach((lora, index) => {
        workflow.nodes.push({
            id: loraNodes[index],
            type: "LoraLoader",
            pos: [170 + (index * 312), 60],
            size: [270, 126],
            flags: {}, order: index + 1, mode: 0,
            inputs: [
                { name: "model", type: "MODEL", link: null },
                { name: "clip", type: "CLIP", link: null }
            ],
            outputs: [
                { name: "MODEL", type: "MODEL", links: [] },
                { name: "CLIP", type: "CLIP", links: [] }
            ],
            properties: { "Node name for S&R": "LoraLoader" },
            widgets_values: [String(lora.name).replace(/\//g, "\\"), lora.strength_model, lora.strength_clip]
        });
    });

    const posX = 910 + (loras.length * 312);

    // Positive Clip
    workflow.nodes.push({
        id: positiveClipNode,
        type: "CLIPTextEncode",
        pos: [posX, 3.52],
        size: [460, 190],
        flags: {}, order: loras.length + 1, mode: 0,
        inputs: [{ name: "clip", type: "CLIP", link: null }],
        outputs: [{ name: "CONDITIONING", type: "CONDITIONING", links: [] }],
        properties: { "Node name for S&R": "CLIPTextEncode" },
        widgets_values: [d.positive || ""]
    });

    // Negative Clip
    workflow.nodes.push({
        id: negativeClipNode,
        type: "CLIPTextEncode",
        pos: [posX, 240],
        size: [470, 200],
        flags: {}, order: loras.length + 2, mode: 0,
        inputs: [{ name: "clip", type: "CLIP", link: null }],
        outputs: [{ name: "CONDITIONING", type: "CONDITIONING", links: [] }],
        properties: { "Node name for S&R": "CLIPTextEncode" },
        widgets_values: [d.negative || ""]
    });

    // Empty Latent
    workflow.nodes.push({
        id: emptyLatentNode,
        type: "EmptyLatentImage",
        pos: [posX + 130, 510],
        size: [270, 106],
        flags: {}, order: 1, mode: 0,
        inputs: [],
        outputs: [{ name: "LATENT", type: "LATENT", links: [] }],
        properties: { "Node name for S&R": "EmptyLatentImage" },
        widgets_values: [d.width || 1080, d.height || 1584, 1]
    });

    // KSampler
    const sampX = posX + 510;
    workflow.nodes.push({
        id: ksamplerNode,
        type: "KSampler",
        pos: [sampX, 23.52],
        size: [315, 708],
        flags: {}, order: loras.length + 3, mode: 0,
        inputs: [
            { name: "model", type: "MODEL", link: null },
            { name: "positive", type: "CONDITIONING", link: null },
            { name: "negative", type: "CONDITIONING", link: null },
            { name: "latent_image", type: "LATENT", link: null }
        ],
        outputs: [{ name: "LATENT", type: "LATENT", links: [] }],
        properties: { "Node name for S&R": "KSampler" },
        widgets_values: [
            d.seed || 0, "fixed", d.steps || 25, d.cfg || 7,
            d.sampler || "dpmpp_2m", d.scheduler || "karras", d.denoise || 1
        ]
    });

    // VAE Decode
    workflow.nodes.push({
        id: vaeDecodeNode,
        type: "VAEDecode",
        pos: [sampX + 390, 33],
        size: [210, 46],
        flags: {}, order: loras.length + 4, mode: 0,
        inputs: [
            { name: "samples", type: "LATENT", link: null },
            { name: "vae", type: "VAE", link: null }
        ],
        outputs: [{ name: "IMAGE", type: "IMAGE", links: [] }],
        properties: { "Node name for S&R": "VAEDecode" },
        widgets_values: []
    });

    // Preview
    workflow.nodes.push({
        id: previewNode,
        type: "PreviewImage",
        pos: [sampX + 370, 173],
        size: [418, 556],
        flags: {}, order: loras.length + 5, mode: 0,
        inputs: [{ name: "images", type: "IMAGE", link: null }],
        outputs: [],
        properties: { "Node name for S&R": "PreviewImage" },
        widgets_values: []
    });


    // --- 2. WIRE NODES (THE FIX) ---

    const getNode = (id) => workflow.nodes.find(n => n.id === id);
    let linkId = 1;

    // TRACKERS: These hold the ID of the node currently supplying the signal
    // We start with the Checkpoint
    let currentModelSource = { id: checkpointNode, slot: 0 };
    let currentClipSource = { id: checkpointNode, slot: 1 };

    // 1. Loop through LoRAs and Daisy Chain them
    // Checkpoint -> Lora1 -> Lora2 -> ...
    for (let i = 0; i < loras.length; i++) {
        const thisLoraId = loraNodes[i];

        // Wire MODEL: Previous Output -> This Lora Input
        workflow.links.push([linkId, currentModelSource.id, currentModelSource.slot, thisLoraId, 0, "MODEL"]);
        getNode(currentModelSource.id).outputs[currentModelSource.slot].links.push(linkId);
        getNode(thisLoraId).inputs[0].link = linkId;
        linkId++;

        // Wire CLIP: Previous Output -> This Lora Input
        workflow.links.push([linkId, currentClipSource.id, currentClipSource.slot, thisLoraId, 1, "CLIP"]);
        getNode(currentClipSource.id).outputs[currentClipSource.slot].links.push(linkId);
        getNode(thisLoraId).inputs[1].link = linkId;
        linkId++;

        // Update Trackers: The output of THIS Lora is now the source for the next step
        currentModelSource = { id: thisLoraId, slot: 0 };
        currentClipSource = { id: thisLoraId, slot: 1 };
    }

    // 2. Connect Final Signal (from last LoRA or Checkpoint) to Engines

    // Final Model -> KSampler
    workflow.links.push([linkId, currentModelSource.id, currentModelSource.slot, ksamplerNode, 0, "MODEL"]);
    getNode(currentModelSource.id).outputs[currentModelSource.slot].links.push(linkId);
    getNode(ksamplerNode).inputs[0].link = linkId;
    linkId++;

    // Final CLIP -> Positive Prompt
    workflow.links.push([linkId, currentClipSource.id, currentClipSource.slot, positiveClipNode, 0, "CLIP"]);
    getNode(currentClipSource.id).outputs[currentClipSource.slot].links.push(linkId);
    getNode(positiveClipNode).inputs[0].link = linkId;
    linkId++;

    // Final CLIP -> Negative Prompt (Shared link logic, but new link ID for Comfy)
    workflow.links.push([linkId, currentClipSource.id, currentClipSource.slot, negativeClipNode, 0, "CLIP"]);
    getNode(currentClipSource.id).outputs[currentClipSource.slot].links.push(linkId);
    getNode(negativeClipNode).inputs[0].link = linkId;
    linkId++;

    // 3. Connect the rest of the standard components

    // VAE: Checkpoint -> VAE Decode
    workflow.links.push([linkId, checkpointNode, 2, vaeDecodeNode, 1, "VAE"]);
    getNode(checkpointNode).outputs[2].links.push(linkId);
    getNode(vaeDecodeNode).inputs[1].link = linkId;
    linkId++;

    // Conditioning: Positive -> KSampler
    workflow.links.push([linkId, positiveClipNode, 0, ksamplerNode, 1, "CONDITIONING"]);
    getNode(positiveClipNode).outputs[0].links.push(linkId);
    getNode(ksamplerNode).inputs[1].link = linkId;
    linkId++;

    // Conditioning: Negative -> KSampler
    workflow.links.push([linkId, negativeClipNode, 0, ksamplerNode, 2, "CONDITIONING"]);
    getNode(negativeClipNode).outputs[0].links.push(linkId);
    getNode(ksamplerNode).inputs[2].link = linkId;
    linkId++;

    // Latent: Empty Latent -> KSampler
    workflow.links.push([linkId, emptyLatentNode, 0, ksamplerNode, 3, "LATENT"]);
    getNode(emptyLatentNode).outputs[0].links.push(linkId);
    getNode(ksamplerNode).inputs[3].link = linkId;
    linkId++;

    // Latent: KSampler -> VAE Decode
    workflow.links.push([linkId, ksamplerNode, 0, vaeDecodeNode, 0, "LATENT"]);
    getNode(ksamplerNode).outputs[0].links.push(linkId);
    getNode(vaeDecodeNode).inputs[0].link = linkId;
    linkId++;

    // Image: VAE Decode -> Preview
    workflow.links.push([linkId, vaeDecodeNode, 0, previewNode, 0, "IMAGE"]);
    getNode(vaeDecodeNode).outputs[0].links.push(linkId);
    getNode(previewNode).inputs[0].link = linkId;
    linkId++;

    // Update workflow config
    workflow.last_link_id = linkId;
    return workflow;
}


function copyConfigsAsComfyNodes(id) {
    // console.log(param)


    const d = activeData.find(x => x.id === id);
    if (!d) {
        alert('Configuration data not found!');
        return;
    }

    try {
        const workflow = buildComfyNodesWorkflow(d);

        // Copy to clipboard logic (Standard)
        const jsonString = JSON.stringify(workflow, null, 2);

        const copyToClipboard = async (text) => {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                const success = document.execCommand('copy');
                document.body.removeChild(textarea);
                return success;
            }
        };

        copyToClipboard(jsonString).then((success) => {
            if (success) {
                alert('✅ ComfyUI workflow copied to clipboard!\n\nYou can now paste this into ComfyUI.');
                console.log('[ComfyUI] Workflow copied:', workflow);
            }
        }).catch(err => {
            console.error('[ComfyUI] Failed to copy:', err);
            alert('❌ Failed to copy to clipboard. JSON logged to console.');
            console.log('ComfyUI Workflow JSON:', jsonString);
        });

    } catch (error) {
        console.error('[ComfyUI] Error generating workflow:', error);
        alert('❌ Error generating workflow: ' + error.message);
    }
}


// Create card - FIXED UI LAYOUT WITH FAVORITE BUTTON
function createCard(d) {
    const totalIndex = idToIndexMap.get(d.id) || 0;
    const card = document.createElement('div');
    card.className = 'card';
    card.id = `card-${d.id}`;
    card.dataset.id = d.id;
    card._dataItem = d;
    // Check if favorited
    const isFavorited = d.favorited || false;
    const favClass = isFavorited ? 'favorited' : '';
    const favIcon = isFavorited ? '★' : '☆';

    // Calculate LoRA display
    let loraLine = "";
    if (d.lora === "None") {
        loraLine = `<div class="stat"><b>LoRA:</b> <span style="opacity:0.3">-</span></div>`;
    } else if (d.lora.includes(" + ")) {
        const count = d.lora.split(" + ").length;
        loraLine = `<div class="stat" title="${d.lora.replace(/ \+ /g, '\n')}"><b>LoRA:</b><br /> <span style="color:var(--accent-lora)">(${d.lora.replace(/ \+ /g, '\n')})</span></div>`;
    } else {
        const rawName = String(d.lora);
        let fileName = rawName.replace(/\\/g, '/').split('/').pop().split(':')[0];
        if (fileName.length > 20) fileName = fileName.substring(0, 18) + '...';
        loraLine = `<div class="stat" title="${d.lora}"><b>LoRA:</b> <span>${fileName}</span></div>`;
    }

    let promptInfo = "";
    // Always show prompt info if available
    if (d.positive || meta.positive) {
        const promptText = d.positive || meta.positive || "";
        const shortPrompt = truncateText(promptText, 30);
        promptInfo = `<div class="stat" title="${promptText}"><b>Pos:</b> ${shortPrompt}</div>`;
    }

    const modelName = d.model || meta.model || "Default";
    const shortModel = modelName.replace(/\\/g, '/').split('/').pop();
    const finalModel = shortModel.length > 25 ? shortModel.substring(0, 22) + "..." : shortModel;

    // Calculate aspect ratio
    const aspectRatio = (d.width && d.height) ? (d.height / d.width) : 1;
    const paddingBottom = (aspectRatio * 100).toFixed(2);

    // FIXED LAYOUT: Star top-right, Revise below it, time bottom-right, index bottom-left
    card.innerHTML = `
        <div class="img-wrapper" style="padding-bottom: ${paddingBottom}%;">
            <img ondblclick="toggleFavorite(this)" data-src="${d.file}" alt="Image ${d.id}" draggable="false">
            <button class="reject-btn" onclick="rejectItem(this)">✕</button>
            <button class="favorite-btn ${favClass}" onclick="toggleFavorite(this)">${favIcon}</button>
            <button class="revise-btn" onclick="openM(${d.id})">REVISE</button>
            <div class="time-tag">${d.duration}s</div>
            <div class="index-tag">#${totalIndex}</div>
            ${buildLabelOverlay(d)}
        </div>
        <div class="info">
            <div class="stat" title="${modelName}"><b>Model:</b> <span>${finalModel}</span></div>

            ${loraLine}
            <div class="stat"><b>Smp:</b> <span>${d.sampler} / ${d.scheduler}</span></div>
            <div class="stat">
                <b>Cfg:</b> ${d.cfg} &nbsp; <b>Stp:</b> ${d.steps} &nbsp; <b>Dn:</b> <span style="color:var(--accent-denoise)">${d.denoise}</span>
            </div>
            
            ${promptInfo}
            <div class="stat"><b>Size:</b> ${d.width}x${d.height} &nbsp; <b>Seed:</b> ${d.seed}</div>
        </div>`;

    return card;
}

// Open Revision Modal
function openM(id) {
    window.currentModalId = id;
    const d = activeData.find(x => x.id === id);
    if (!d) return;
    document.getElementById('m-img').src = d.file;
    console.log(d)
    // Populate read-only info fields
    const modelEl = document.getElementById('f-model');
    const seedEl = document.getElementById('f-seed');
    const posEl = document.getElementById('f-pos');
    const negEl = document.getElementById('f-neg');

    if (modelEl) modelEl.value = d.model || meta.model || "Default";
    if (seedEl) seedEl.value = d.seed || 0;
    // Check trigger word toggle
    const showTriggers = document.getElementById('toggle-triggers')?.checked !== false;
    if (posEl) posEl.value = showTriggers
        ? (d.positive || meta.positive || "")
        : (d.config_positive || d.positive || meta.positive || "");
    if (negEl) negEl.value = showTriggers
        ? (d.negative || meta.negative || "")
        : (d.config_negative || d.negative || meta.negative || "");

    // Populate editable parameter fields
    const map = {
        'smp': d.sampler,
        'sch': d.scheduler,
        'stp': d.steps,
        'cfg': d.cfg,
        'den': d.denoise,
        'lor': d.lora
    };

    for (let k in map) {
        const el = document.getElementById('f-' + k);
        if (el) el.value = map[k];
    }

    // Populate related variants reel
    const r = document.getElementById('reel');
    r.innerHTML = '';

    activeData.forEach(x => {
        if (x.rejected) return;
        if (x.seed === d.seed) {
            const i = document.createElement('img');
            i.src = x.file;
            i.onclick = () => openM(x.id);
            if (x.id === id) i.style.borderColor = "var(--accent)";
            r.appendChild(i);
        }
    });

    document.getElementById('modal').style.display = 'flex';
}

function closeM() {
    document.getElementById('modal').style.display = 'none';
}

// THROTTLED JSON Updates
let jsonUpdateTimeout = null;

function updateJSONs(visible) {
    if (jsonUpdateTimeout) {
        clearTimeout(jsonUpdateTimeout);
    }

    jsonUpdateTimeout = setTimeout(() => {
        // 🚀 OPTIMIZED: Single pass through data instead of 3 separate filters
        const good = [];
        const favorited = [];
        const rejected = [];

        for (const item of activeData) {
            if (item.rejected) {
                rejected.push(item);
            } else {
                good.push(item);
                if (item.favorited) {
                    favorited.push(item);
                }
            }
        }

        // Disabled automatic JSON generation - now on-demand via buttons
        // Store the datasets for on-demand generation
        window.cachedJSONData = { good, favorited, rejected };

        // Calculate unique config counts for button labels
        const goodUniqueCount = countUniqueConfigs(good);
        const favUniqueCount = countUniqueConfigs(favorited);
        const rejUniqueCount = countUniqueConfigs(rejected);

        // Update button labels with unique counts
        updateJSONButtonLabels(goodUniqueCount, favUniqueCount, rejUniqueCount);
    }, 100); // Reduced from 300ms since we have separate debounce above
}

// OPTIMIZED JSON generation
const jsonElCache = new Map();

// Fallback for browsers that don't support requestIdleCallback
const runIdle = window.requestIdleCallback || (cb => setTimeout(cb, 1));
const cancelIdle = window.cancelIdleCallback || clearTimeout;

function generateSmartJSON(dataset, targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;

    if (dataset.length === 0) {
        el.innerText = "[]";
        return;
    }

    // Extract unique configurations
    const configMap = new Map();

    for (const d of dataset) {
        const config = {
            sampler: d.sampler,
            scheduler: d.scheduler,
            steps: d.steps,
            cfg: d.cfg,
            denoise: d.denoise,
            lora: d.lora,
            model: d.model || "Default"
        };

        // Create a unique key for this configuration
        const key = JSON.stringify(config);

        // Only add if we haven't seen this exact config before
        if (!configMap.has(key)) {
            configMap.set(key, config);
        }
    }

    // Convert map to array
    const uniqueConfigs = Array.from(configMap.values());

    // Limit output
    const limit = Math.min(uniqueConfigs.length, 100);
    const limited = uniqueConfigs.slice(0, limit);

    let jsonText = JSON.stringify(limited, null, 2);

    if (uniqueConfigs.length > 100) {
        jsonText += `\n\n// ... and ${uniqueConfigs.length - 100} more unique configs`;
    }

    el.innerText = jsonText;
}

// Helper function to count unique configs in a dataset
function countUniqueConfigs(dataset) {
    const configSet = new Set();

    for (const d of dataset) {
        const key = JSON.stringify({
            sampler: d.sampler,
            scheduler: d.scheduler,
            steps: d.steps,
            cfg: d.cfg,
            denoise: d.denoise,
            lora: d.lora,
            model: d.model || "Default"
        });
        configSet.add(key);
    }

    return configSet.size;
}

// Add button label update function
function updateJSONButtonLabels(goodCount, favCount, rejCount) {
    const goodBtn = document.getElementById('json-btn-good');
    const favBtn = document.getElementById('json-btn-favorite');
    const rejBtn = document.getElementById('json-btn-bad');

    if (goodBtn) goodBtn.innerText = `View Configs (${goodCount})`;
    if (favBtn) favBtn.innerText = `View Favorited (${favCount})`;
    if (rejBtn) rejBtn.innerText = `View Rejected (${rejCount})`;
}

// On-demand JSON generation functions
function viewGoodJSON() {
    if (!window.cachedJSONData) return;
    const bar = document.getElementById('json-bar-good');
    if (!bar) return;

    // Toggle visibility
    if (bar.style.display === 'block') {
        bar.style.display = 'none';
        return;
    }

    const { good } = window.cachedJSONData;
    generateSmartJSON(good, 'json-bar-good');

    bar.style.display = 'block';
    bar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function viewFavoritedJSON() {
    if (!window.cachedJSONData) return;
    const bar = document.getElementById('json-bar-favorite');
    if (!bar) return;

    // Toggle visibility
    if (bar.style.display === 'block') {
        bar.style.display = 'none';
        return;
    }

    const { favorited } = window.cachedJSONData;
    generateSmartJSON(favorited, 'json-bar-favorite');

    bar.style.display = 'block';
    bar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function viewRejectedJSON() {
    if (!window.cachedJSONData) return;
    const bar = document.getElementById('json-bar-bad');
    if (!bar) return;

    // Toggle visibility
    if (bar.style.display === 'block') {
        bar.style.display = 'none';
        return;
    }

    const { rejected } = window.cachedJSONData;
    generateSmartJSON(rejected, 'json-bar-bad');

    bar.style.display = 'block';
    bar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
/**
 * SEARCH FILTER FUNCTIONS
 */

// Add a search filter
function addSearchFilter() {
    const typeSelect = document.getElementById('search-filter-type');
    const inputField = document.getElementById('search-filter-input');

    if (!typeSelect || !inputField) return;

    const filterType = typeSelect.value;
    const searchTerm = inputField.value.trim();

    // Validation
    if (!filterType) {
        alert('Please select a filter type');
        return;
    }

    if (!searchTerm) {
        alert('Please enter a search term');
        return;
    }

    // Check if this exact filter already exists
    const exists = searchFilters.some(f => f.type === filterType && f.term === searchTerm);
    if (exists) {
        alert('This search filter already exists');
        return;
    }

    // Add to search filters array
    searchFilters.push({
        type: filterType,
        term: searchTerm
    });

    // Clear inputs
    typeSelect.value = '';
    inputField.value = '';

    // Update UI
    renderSearchFilters();

    // Trigger data pipeline update
    updateDataPipeline();

    console.log(`[Search Filter] Added: ${filterType} contains "${searchTerm}"`);
}

// Remove a search filter
function removeSearchFilter(index) {
    if (index >= 0 && index < searchFilters.length) {
        const removed = searchFilters.splice(index, 1)[0];
        console.log(`[Search Filter] Removed: ${removed.type} contains "${removed.term}"`);

        // Update UI
        renderSearchFilters();

        // Trigger data pipeline update
        updateDataPipeline();
    }
}

// Clear all search filters
function clearAllSearchFilters() {
    if (searchFilters.length === 0) return;

    searchFilters = [];
    renderSearchFilters();
    updateDataPipeline();

    console.log('[Search Filter] All search filters cleared');
}

// Render search filter tags
function renderSearchFilters() {
    const container = document.getElementById('active-search-filters');
    if (!container) return;

    container.innerHTML = '';

    if (searchFilters.length === 0) {
        container.innerHTML = '<div style="color: #555; font-size: 10px; padding: 4px 0;">No active search filters</div>';
        return;
    }

    searchFilters.forEach((filter, index) => {
        const tag = document.createElement('div');
        tag.className = 'search-filter-tag';

        // Format display name for filter type
        const typeNames = {
            'model': 'Model',
            'positive': 'Positive',
            'negative': 'Negative',
            'sampler': 'Sampler',
            'scheduler': 'Scheduler',
            'lora': 'LoRA'
        };

        tag.innerHTML = `
            <span class="filter-type ${filter.type}">${typeNames[filter.type] || filter.type}</span>
            <span class="filter-term" title="${filter.term}">${filter.term}</span>
            <button class="remove-btn" onclick="removeSearchFilter(${index})" title="Remove filter">✕</button>
        `;

        container.appendChild(tag);
    });

    // Add clear all button if there are multiple filters
    if (searchFilters.length > 1) {
        const clearBtn = document.createElement('button');
        clearBtn.className = 'search-filter-add-btn';
        clearBtn.style.background = '#ff3860';
        clearBtn.style.padding = '4px 10px';
        clearBtn.innerText = 'CLEAR ALL';
        clearBtn.onclick = clearAllSearchFilters;
        container.appendChild(clearBtn);
    }
}

// Check if an item matches search filters
function matchesSearchFilters(item) {
    if (searchFilters.length === 0) return true;

    // Item must match ALL search filters (AND logic)
    return searchFilters.every(filter => {
        let value = '';

        switch (filter.type) {
            case 'model':
                value = item.model || meta.model || "Default";
                break;
            case 'positive':
                value = item.positive || meta.positive || "";
                break;
            case 'negative':
                value = item.negative || meta.negative || "";
                break;
            case 'sampler':
                value = item.sampler || "";
                break;
            case 'scheduler':
                value = item.scheduler || "";
                break;
            case 'lora':
                value = item.lora || "";
                break;
            default:
                return false;
        }

        // Case-insensitive search
        return value.toLowerCase().includes(filter.term.toLowerCase());
    });
}


// ============================================================
// MANIFEST ANALYTICS
// ============================================================

/**
 * Dispatch to the correct analysis function based on type.
 * type: 'lora' | 'model' | 'prompt' | 'tags'
 */
function runManifestAnalysis(type) {
    const statusEl = document.getElementById('analytics-status');

    // Guard: fullManifest must exist
    if (!fullManifest || !Array.isArray(fullManifest.items) || fullManifest.items.length === 0) {
        if (statusEl) {
            statusEl.innerText = 'No manifest data available.';
            statusEl.style.color = '#ff3860';
        }
        return;
    }

    const items = fullManifest.items;
    let results = [];
    let title = '';

    if (type === 'lora') {
        title = 'LoRA Usage Stats (Favorited)';
        results = analyzeFieldStats(items, 'lora', true);
    } else if (type === 'model') {
        title = 'Model Usage Stats (Favorited)';
        results = analyzeFieldStats(items, 'model', true);
    } else if (type === 'prompt') {
        title = 'Full Prompt Stats (All Items)';
        results = analyzePromptStats(items);
    } else if (type === 'tags') {
        title = 'Prompt Tag Stats (Favorited)';
        results = analyzeTagStats(items);
    }

    if (results.length === 0) {
        if (statusEl) {
            statusEl.innerText = 'No data found (check favorited items).';
            statusEl.style.color = '#ffaa00';
        }
        return;
    }

    if (statusEl) {
        statusEl.innerText = results.length + ' unique entries found.';
        statusEl.style.color = '#4caf50';
        setTimeout(() => { if (statusEl) statusEl.innerText = ''; }, 4000);
    }

    showAnalyticsModal(title, results, type);
}

/**
 * Generic counter for lora and model fields.
 * Splits field value by " + " to handle combined entries.
 * @param {Array} items - all manifest items
 * @param {string} field - 'lora' or 'model'
 * @param {boolean} favoritedOnly - true to count only favorited items
 * @returns {Array} sorted [{count, name}] descending
 */
function analyzeFieldStats(items, field, favoritedOnly) {
    const counter = new Map();

    for (const item of items) {
        if (favoritedOnly && !item.favorited) continue;

        const raw = item[field];
        if (!raw || raw === 'None') continue;

        // Split by " + " to handle combined loras/models
        const entries = String(raw).split(' + ').map(s => s.trim()).filter(Boolean);
        for (const entry of entries) {
            counter.set(entry, (counter.get(entry) || 0) + 1);
        }
    }

    return Array.from(counter.entries())
        .map(([name, count]) => ({ count, name }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/**
 * Full Prompt Stats (unique behavior):
 * - ALL items register their prompt with count 0
 * - Only favorited items increment the count
 * @param {Array} items - all manifest items
 * @returns {Array} sorted [{count, name}] descending by count
 */
function analyzePromptStats(items) {
    const counter = new Map();

    // Pass 1: register ALL prompts with count 0
    for (const item of items) {
        const prompt = item.positive;
        if (prompt && !counter.has(prompt)) {
            counter.set(prompt, 0);
        }
    }

    // Pass 2: increment for favorited items
    for (const item of items) {
        if (!item.favorited) continue;
        const prompt = item.positive;
        if (prompt && counter.has(prompt)) {
            counter.set(prompt, counter.get(prompt) + 1);
        }
    }

    return Array.from(counter.entries())
        .map(([name, count]) => ({ count, name }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/**
 * Tag Stats: splits item.positive by comma, trims, counts occurrences.
 * Only favorited items.
 * @param {Array} items - all manifest items
 * @returns {Array} sorted [{count, name}] descending
 */
function analyzeTagStats(items) {
    const counter = new Map();

    for (const item of items) {
        if (!item.favorited) continue;
        const prompt = item.positive;
        if (!prompt) continue;

        const tags = prompt.split(',').map(t => t.trim()).filter(Boolean);
        for (const tag of tags) {
            counter.set(tag, (counter.get(tag) || 0) + 1);
        }
    }

    return Array.from(counter.entries())
        .map(([name, count]) => ({ count, name }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/**
 * Escape HTML entities for safe innerHTML insertion.
 */
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/**
 * Show the analytics results modal.
 * Follows the same dynamic overlay pattern as showSaveErrorAlert.
 * @param {string} title - modal title
 * @param {Array} results - [{count, name}]
 * @param {string} type - 'lora'|'model'|'prompt'|'tags' (for accent color)
 */
function showAnalyticsModal(title, results, type) {
    // Deduplication: remove existing analytics modal
    const existing = document.getElementById('analytics-results-modal');
    if (existing) existing.remove();

    // Accent color per type
    const accentMap = {
        lora:   '#8b5cf6',
        model:  '#6366f1',
        prompt: '#00d1b2',
        tags:   '#d0873e'
    };
    const accent = accentMap[type] || '#00d1b2';

    // Build table rows HTML (limit to 500 rows max for performance)
    const displayResults = results.slice(0, 500);
    const totalItems = results.length;
    const truncated = results.length > 500;

    const rowsHtml = displayResults.map((r, i) => {
        // Show full prompt text - no truncation
        const rank = i + 1;
        return '<tr class="analytics-row">' +
            '<td class="analytics-rank">' + rank + '</td>' +
            '<td class="analytics-count" style="color:' + accent + ';">' + r.count + '</td>' +
            '<td class="analytics-name">' + escapeHtml(r.name) + '</td>' +
        '</tr>';
    }).join('');

    const truncatedNote = truncated
        ? '<div style="text-align:center; font-size:10px; color:#666; padding:8px 0;">' +
              'Showing top 500 of ' + totalItems + ' entries.' +
          '</div>'
        : '';

    // Count summary
    const favCount = results.filter(r => r.count > 0).length;
    const totalCount = results.reduce((s, r) => s + r.count, 0);
    const summaryHtml =
        '<div class="analytics-summary">' +
            '<span>' + totalItems + ' unique entries</span>' +
            '<span style="color:#666;">|</span>' +
            '<span>' + totalCount + ' total occurrences</span>' +
            (type === 'prompt' ? '<span style="color:#666;">|</span><span>' + favCount + ' with favorites</span>' : '') +
        '</div>';

    // For prompt type: build "Copy Favorited Prompts as JSON" button
    const copyFavBtnHtml = (type === 'prompt')
        ? '<button id="analytics-copy-fav-btn" style="' +
              'background:#00d1b2; color:#000; border:none; border-radius:5px;' +
              'padding:6px 12px; font-size:11px; font-weight:bold; cursor:pointer;' +
              'margin-right:8px; white-space:nowrap;' +
          '" title="Copy all favorited prompts as a JSON array">📋 Copy Favorited Prompts as JSON</button>'
        : '';

    // Create overlay
    const overlay = document.createElement('div');
    overlay.id = 'analytics-results-modal';
    overlay.className = 'analytics-modal-overlay';

    overlay.innerHTML =
        '<div class="analytics-modal-popup">' +
            '<div class="analytics-modal-header" style="border-bottom-color:' + accent + ';">' +
                '<span class="analytics-modal-title" style="color:' + accent + ';">' + escapeHtml(title) + '</span>' +
                '<div style="display:flex; align-items:center; gap:4px;">' +
                    copyFavBtnHtml +
                    '<button class="close-popup-btn" onclick="document.getElementById(\'analytics-results-modal\').remove()">&#10005;</button>' +
                '</div>' +
            '</div>' +
            summaryHtml +
            '<div class="analytics-modal-body">' +
                '<table class="analytics-table">' +
                    '<thead>' +
                        '<tr>' +
                            '<th class="analytics-th">#</th>' +
                            '<th class="analytics-th" style="color:' + accent + ';">Count</th>' +
                            '<th class="analytics-th">Name</th>' +
                        '</tr>' +
                    '</thead>' +
                    '<tbody>' +
                        rowsHtml +
                    '</tbody>' +
                '</table>' +
                truncatedNote +
            '</div>' +
        '</div>';

    document.body.appendChild(overlay);

    // Wire up "Copy Favorited Prompts as JSON" button (prompt type only)
    if (type === 'prompt') {
        const copyFavBtn = document.getElementById('analytics-copy-fav-btn');
        if (copyFavBtn) {
            copyFavBtn.addEventListener('click', async () => {
                // All results with count > 0 are favorited prompts; include all (not just displayResults slice)
                const favoritedPrompts = results.filter(r => r.count > 0).map(r => r.name);
                const jsonStr = JSON.stringify(favoritedPrompts, null, 2);
                try {
                    await navigator.clipboard.writeText(jsonStr);
                } catch {
                    // Fallback for browsers that block async clipboard
                    const ta = document.createElement('textarea');
                    ta.value = jsonStr;
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }
                const orig = copyFavBtn.textContent;
                copyFavBtn.textContent = '✅ Copied ' + favoritedPrompts.length + ' prompts!';
                copyFavBtn.style.background = '#00aa88';
                setTimeout(() => {
                    copyFavBtn.textContent = orig;
                    copyFavBtn.style.background = '#00d1b2';
                }, 2000);
            });
        }
    }

    // Click-outside-to-close
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });
}