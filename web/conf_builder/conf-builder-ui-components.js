/**
 * Config Builder UI Components Module
 * Reusable UI elements and component builders
 */

import { normalizePath } from './conf-builder-utilities.js';

// --- SEARCHABLE SELECT COMPONENT ---

export function createSearchableSelect(options, currentValue, onChange, placeholder = "Search...") {
    const MAX_VISIBLE = 50; // Only render first N items for performance
    const container = document.createElement("div");
    container.style.position = "relative";
    container.style.width = "100%";

    const input = document.createElement("input");
    input.className = "cb-input";
    input.type = "text";
    input.placeholder = placeholder;
    input.value = normalizePath(currentValue) || "";
    input.autocomplete = "off";

    const dropdown = document.createElement("div");
    dropdown.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        max-height: 300px;
        overflow-y: auto;
        background: #1a1a1a;
        border: 1px solid #0066cc;
        border-top: none;
        border-radius: 0 0 4px 4px;
        z-index: 1000;
        display: none;
    `;

    let filteredOptions = options;

    const renderOptions = () => {
        dropdown.textContent = "";
        const showCount = Math.min(filteredOptions.length, MAX_VISIBLE);
        for (let i = 0; i < showCount; i++) {
            const optDiv = document.createElement("div");
            optDiv.textContent = filteredOptions[i];
            optDiv.dataset.idx = i;
            optDiv.style.cssText = "padding: 8px 10px; cursor: pointer; color: white; font-size: 13px; font-family: monospace;";
            dropdown.appendChild(optDiv);
        }

        if (filteredOptions.length > MAX_VISIBLE) {
            const more = document.createElement("div");
            more.textContent = `... ${filteredOptions.length - MAX_VISIBLE} more \u2014 type to filter`;
            more.style.cssText = "padding: 6px 10px; color: #666; font-size: 11px; font-style: italic;";
            dropdown.appendChild(more);
        }

        if (filteredOptions.length === 0) {
            const noResults = document.createElement("div");
            noResults.textContent = "No matches found";
            noResults.style.cssText = "padding: 8px 10px; color: #666; font-style: italic;";
            dropdown.appendChild(noResults);
        }
    };

    // Event delegation for dropdown clicks and hover (instead of per-option handlers)
    dropdown.onmouseover = (e) => {
        const t = e.target;
        if (t.dataset && t.dataset.idx !== undefined) t.style.background = "#2a2a2a";
    };
    dropdown.onmouseout = (e) => {
        const t = e.target;
        if (t.dataset && t.dataset.idx !== undefined) t.style.background = "transparent";
    };
    dropdown.onclick = (e) => {
        const t = e.target;
        if (t.dataset && t.dataset.idx !== undefined) {
            const opt = filteredOptions[parseInt(t.dataset.idx)];
            if (opt !== undefined) {
                input.value = opt;
                dropdown.style.display = "none";
                onChange(opt);
            }
        }
    };

    input.onfocus = () => {
        filteredOptions = options;
        renderOptions();
        dropdown.style.display = "block";
    };

    input.oninput = () => {
        const searchTerm = input.value.toLowerCase();
        filteredOptions = options.filter(opt =>
            opt.toLowerCase().includes(searchTerm)
        );
        renderOptions();
        dropdown.style.display = "block";
    };

    input.onkeydown = (e) => {
        if (e.key === "Enter" && filteredOptions.length > 0) {
            input.value = filteredOptions[0];
            dropdown.style.display = "none";
            onChange(filteredOptions[0]);
        } else if (e.key === "Escape") {
            dropdown.style.display = "none";
        }
    };

    // Close dropdown when clicking outside — use onblur instead of global listener
    input.onblur = () => {
        // Delay to allow dropdown click to register before hiding
        setTimeout(() => { dropdown.style.display = "none"; }, 200);
    };

    container.appendChild(input);
    container.appendChild(dropdown);

    return container;
}

// --- SLIDER COMPONENT ---
export function createSlider(label, value, min, max, step, onChange) {
    const container = document.createElement("div");
    container.className = "cb-slider-container";

    const labelElem = document.createElement("span");
    labelElem.className = "cb-label";
    labelElem.textContent = label;
    labelElem.style.flex = "1";
    container.appendChild(labelElem);

    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "cb-slider";
    slider.min = min;
    slider.max = max;
    slider.step = step;
    slider.value = value;
    container.appendChild(slider);

    // Number Input for better control
    const numberInput = document.createElement("input");
    numberInput.type = "number";
    numberInput.className = "cb-number-input";

    // FIX 1: Set step to "any" to allow any decimal precision without browser validation errors
    numberInput.step = "any";
    // FIX 2: Do NOT set min/max here, so the browser allows typing outside the range
    numberInput.value = value.toFixed(2);

    container.appendChild(numberInput);

    // Sync Logic: Slider -> Number Input
    slider.oninput = () => {
        const val = parseFloat(slider.value);
        numberInput.value = val.toFixed(2);
        onChange(val);
    };

    // Sync Logic: Number Input -> Slider
    numberInput.onchange = () => {
        let val = parseFloat(numberInput.value);

        // Safety check for empty or invalid input
        if (isNaN(val)) {
            val = parseFloat(slider.value);
        }

        slider.value = val;

        // Optional: formatting to 2 decimals, or remove to keep exact typed value
        numberInput.value = val;

        onChange(val);
    };

    return container;
}

// --- INPUT GROUP COMPONENT ---

export function createInputGroup(label, element) {
    const group = document.createElement("div");
    group.className = "cb-input-group";

    const labelElem = document.createElement("label");
    labelElem.className = "cb-label";
    labelElem.textContent = label;
    group.appendChild(labelElem);

    group.appendChild(element);
    return group;
}

// --- STYLES ---

export function getStyles() {
    return `
        <style>
            .cb-container { display: flex; flex-direction: column; height: 100%; overflow: hidden; box-sizing: border-box; }

            /* Top Bar */
            .cb-top-bar { display: flex; align-items: center; gap: 12px; padding: 6px 12px; background: #1a1a1a; border-bottom: 1px solid #3a3a3a; position: sticky; top: 0; z-index: 100; min-height: 36px; flex-shrink: 0; }
            .cb-top-bar-input { flex: 1; background: transparent; border: 1px solid transparent; color: #e0e0e0; font-size: 14px; font-weight: bold; padding: 6px 10px; border-radius: 4px; font-family: monospace; min-width: 100px; }
            .cb-top-bar-input:hover { border-color: #444; }
            .cb-top-bar-input:focus { outline: none; border-color: #0077dd; background: #1a1a1a; }
            .cb-settings-btn { background: #333; border: 1px solid #555; color: #ccc; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 13px; white-space: nowrap; display: flex; align-items: center; gap: 6px; }
            .cb-settings-btn:hover { background: #444; color: #fff; }

            /* Settings Dropdown */
            .cb-settings-dropdown { position: absolute; top: 100%; right: 0; min-width: 280px; background: #1e1e1e; border: 1px solid #444; border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); z-index: 200; overflow: hidden; display: none; max-height: 80vh; overflow-y: auto; }
            .cb-settings-dropdown.open { display: block; }
            .cb-settings-item { display: flex; align-items: center; gap: 8px; padding: 8px 14px; cursor: pointer; color: #ccc; font-size: 12px; border: none; background: none; width: 100%; text-align: left; box-sizing: border-box; }
            .cb-settings-item:hover { background: #2a2a2a; color: #fff; }
            .cb-settings-divider { height: 1px; background: #333; margin: 4px 0; }
            .cb-settings-expand { padding: 8px 14px; background: #252525; border-top: 1px solid #333; display: none; }
            .cb-settings-expand.open { display: block; }

            /* Sidebar */
            .cb-layout-wrapper { display: flex; flex: 1; overflow: hidden; }
            .cb-sidebar { width: 42px; min-width: 42px; background: #1e1e1e; border-right: 1px solid #333; display: flex; flex-direction: column; align-items: center; padding-top: 8px; gap: 2px; flex-shrink: 0; overflow-y: auto; }
            .cb-sidebar-icon { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border-radius: 6px; cursor: pointer; font-size: 16px; background: transparent; border: none; color: #888; position: relative; }
            .cb-sidebar-icon:hover { background: #333; color: #fff; }
            .cb-sidebar-icon.active { background: #0077dd33; color: #4aa8ff; }
            .cb-sidebar-divider { width: 24px; height: 1px; background: #444; margin: 6px 0; }
            .cb-main-content { flex: 1; overflow-y: auto; padding: 12px; }

            /* Uniform Section Header */
            .cb-section-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px; margin: -12px -12px 12px -12px; border-radius: 4px 4px 0 0; font-size: 16px; font-weight: bold; color: #e0e0e0; user-select: none; }
            .cb-sections-row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
            .cb-section { background: #2a2a2a; border-radius: 4px; padding: 12px; border: 1px solid #3a3a3a; box-sizing: border-box; flex: 1 1 300px; }
            .cb-section.full-width { flex: 1 1 100%; width: 100%; }
            .cb-section-title { color: #0066cc; font-size: 14px; font-weight: bold; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #3a3a3a; }
            .cb-flex-grid { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
            .cb-input-group { flex: 1 1 180px; min-width: 140px; display: flex; flex-direction: column; }
            .cb-input, .cb-select { background: #1a1a1a; border: 1px solid #555; color: white; padding: 8px 10px; border-radius: 4px; width: 100%; box-sizing: border-box; font-size: 13px; font-family: monospace; }
            .cb-input:focus, .cb-select:focus { outline: none; border-color: #0066cc; }
            .cb-label { color: #ccc; font-size: 12px; margin-bottom: 4px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .cb-button { background: #4a4a4a; border: none; color: #e0e0e0; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; margin: 4px 2px; white-space: nowrap; }
            .cb-button:hover { background: #5a5a5a; }
            .cb-button.primary { background: #0077dd; }
            .cb-button.primary:hover { background: #0088ee; }
            .cb-button.danger { background: #cc3333; }
            .cb-button.danger:hover { background: #dd4444; }
            .cb-array { background: #333; border-radius: 4px; padding: 12px; margin: 8px 0; border: 1px solid #3a3a3a; width: 100%; position: relative; }
            .cb-config-label-overlay { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); background: rgba(0, 102, 204, 0.85); color: #fff; padding: 4px 16px; border-radius: 12px; font-size: 13px; font-weight: bold; font-family: monospace; pointer-events: none; z-index: 10; white-space: nowrap; max-width: 80%; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
            .cb-arrays-container { display: flex; flex-direction: column; gap: 12px; }
            .cb-list-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #444; }
            .cb-item-card { background: #2a2a2a; border-radius: 4px; padding: 10px; border-left: 3px solid #0066cc; flex: 1 1 300px; min-width: 250px; display: flex; flex-direction: column; gap: 6px; }
            .cb-item-card.model-card { border-left-color: #cc6600; }

            /* Drag-and-drop reorder styles */
            .cb-item-card.cb-dragging { opacity: 0.4; }
            .cb-item-card.cb-drop-above { border-top: 2px solid #0088ff; }
            .cb-item-card.cb-drop-below { border-bottom: 2px solid #0088ff; }
            .cb-drag-handle { opacity: 0.4; transition: opacity 0.15s; }
            .cb-header-bar:hover .cb-drag-handle { opacity: 1; }
            .cb-te-row.cb-dragging { opacity: 0.4; }
            .cb-te-row.cb-drop-above { border-top: 2px solid #0088ff; }
            .cb-te-row.cb-drop-below { border-bottom: 2px solid #0088ff; }

            .cb-slider-container { display: flex; align-items: center; gap: 10px; }
            .cb-slider { flex: 1; height: 6px; background: #1a1a1a; border-radius: 3px; outline: none; }
            
            /* Numerical Input Styles */
            .cb-number-input { width: 60px; background: #1a1a1a; color: #0066cc; border: 1px solid #3a3a3a; border-radius: 4px; padding: 2px 4px; font-size: 12px; font-family: monospace; text-align: right; margin-left: 8px; }
            .cb-number-input:focus { outline: none; border-color: #0066cc; }

            .cb-toggle { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; padding: 6px 0; }
            .cb-preview { background: #0a0a0a; border: 1px solid #3a3a3a; border-radius: 4px; padding: 10px; margin: 10px 0; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 11px; color: #0cc; }

            /* Output Preview Panel — fixed at bottom of cb-container, resizable */
            /* Default ~8 lines of 11px/1.4-leading JSON visible: header 28px +
               handle 6px + padding 20px + 8 lines × ~15px ≈ 175px. Users can
               drag the handle to grow it. */
            .cb-preview-panel { display: flex; flex-direction: column; flex: 0 1 175px; min-height: 100px; max-height: 80%; background: #0a0a0a; border-top: 2px solid #3a3a3a; overflow: hidden; }
            .cb-preview-resize-handle { height: 6px; flex: 0 0 6px; background: #2a2a2a; cursor: row-resize; user-select: none; transition: background 0.15s; }
            .cb-preview-resize-handle:hover { background: #4aa8ff; }
            .cb-preview-resize-handle.dragging { background: #4aa8ff; }
            .cb-preview-panel-header { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: #1e1e1e; border-bottom: 1px solid #3a3a3a; color: #e0e0e0; font-size: 12px; font-weight: bold; flex: 0 0 auto; }
            .cb-preview-panel-header .cb-preview-panel-title { display: flex; align-items: center; gap: 8px; }
            .cb-preview-panel-header .cb-preview-panel-meta { color: #888; font-weight: normal; font-size: 11px; }
            .cb-preview-panel-content { flex: 1; overflow: auto; padding: 10px 12px; margin: 0; font-family: monospace; font-size: 11px; line-height: 1.4; color: #0cc; background: #0a0a0a; white-space: pre; }
            .cb-controls-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 10px; padding: 8px; background: #2a2a2a; border-radius: 4px; }
            .cb-header-bar { display: flex; justify-content: space-between; align-items: center; cursor: pointer; padding: 2px 0; }
            .cb-header-bar:hover { background: rgba(255,255,255,0.05); border-radius: 4px; }
            .cb-header-left { display: flex; align-items: center; gap: 8px; overflow: hidden; flex: 1; }
            .cb-header-name { color: #fff; font-weight: bold; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 10px; }
            .cb-section-toggle { cursor: pointer; display: flex; justify-content: space-between; align-items: center; width: 100%; user-select: none; }
                    
            .cb-modal-popup {
                background: #2a2a2a;
                border: 2px solid #9966cc;
                border-radius: 8px;
                padding: 20px;
                max-width: 800px;
                max-height: 85vh;
                overflow-y: auto;
                color: white;
                position: relative;
                width: 95%; /* Responsive width */
                box-sizing: border-box;
            }

            @media (max-width: 600px) {
                .cb-modal-popup {
                    padding: 10px; /* Smaller padding on mobile */
                    width: 98%;    /* Use more screen space on mobile */
                }
            }

            /* --- Prompt Builder Styles --- */
            .cb-prompt-section {
                background: #252525;
                border-radius: 4px;
                padding: 10px;
                margin-top: 8px;
                width: 100%;
                box-sizing: border-box;
            }
            .cb-prompt-section.global {
                border-left: 3px solid #00aa44;
            }
            .cb-prompt-section.per-config {
                border-left: 3px solid #9966cc;
            }
            .cb-prompt-group {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
                margin-bottom: 6px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .cb-prompt-group-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 11px;
                color: #888;
            }
            .cb-prompt-chips {
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                min-height: 28px;
                align-items: center;
            }
            .cb-prompt-chip {
                display: inline-flex;
                align-items: center;
                background: #0066cc33;
                border: 1px solid #0066cc66;
                color: #88ccff;
                border-radius: 12px;
                padding: 3px 8px;
                font-size: 12px;
                font-family: monospace;
                gap: 4px;
                max-width: 300px;
                word-break: break-all;
            }
            .cb-prompt-chip .chip-close {
                cursor: pointer;
                color: #ff8888;
                font-weight: bold;
                font-size: 14px;
                line-height: 1;
                margin-left: 2px;
            }
            .cb-prompt-chip .chip-close:hover {
                color: #ff4444;
            }
            .cb-prompt-preview {
                background: #0a0a0a;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 8px;
                margin-top: 8px;
                max-height: 200px;
                overflow-y: auto;
                font-family: monospace;
                font-size: 11px;
                color: #00cc88;
            }
            .cb-prompt-preview-item {
                padding: 2px 0;
                border-bottom: 1px solid #1a1a1a;
            }
            .cb-prompt-preview-item:last-child {
                border-bottom: none;
            }
            .cb-prompt-raw-editor {
                width: 100%;
                min-height: 160px;
                background: #0a0a0a;
                border: 1px solid #3a3a3a;
                color: #0cc;
                padding: 8px;
                border-radius: 4px;
                font-family: monospace;
                font-size: 12px;
                resize: vertical;
                box-sizing: border-box;
            }
            .cb-prompt-raw-editor:focus {
                outline: none;
                border-color: #0066cc;
            }
            .cb-prompt-mode-toggle {
                background: transparent;
                border: 1px solid #555;
                color: #aaa;
                padding: 3px 8px;
                border-radius: 3px;
                cursor: pointer;
                font-size: 10px;
            }
            .cb-prompt-mode-toggle:hover {
                background: #333;
                color: #fff;
            }
            .cb-prompt-mode-toggle.active {
                background: #0066cc33;
                border-color: #0066cc;
                color: #88ccff;
            }
            .cb-prompt-add-group-btn {
                width: 100%;
                border: 1px dashed #555;
                background: rgba(0,102,204,0.1);
                color: #88ccff;
                padding: 6px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                margin-top: 4px;
            }
            .cb-prompt-add-group-btn:hover {
                background: rgba(0,102,204,0.2);
                border-color: #0066cc;
            }
            .cb-prompt-add-variation {
                background: transparent;
                border: 1px dashed #444;
                color: #888;
                padding: 3px 8px;
                border-radius: 12px;
                cursor: pointer;
                font-size: 11px;
            }
            .cb-prompt-add-variation:hover {
                background: #333;
                color: #ccc;
                border-color: #666;
            }

            /* Per-config sidebar navigation */
            .cb-sidebar-config-group {
                position: relative;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .cb-sidebar-config-icon {
                width: 28px;
                height: 28px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 11px;
                font-weight: bold;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                color: #999;
                transition: background 0.15s;
            }
            .cb-sidebar-config-icon:hover {
                background: #333;
            }
            .cb-sidebar-config-icon.active {
                background: #333;
                color: #fff;
            }
            .cb-sidebar-sub-icons {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 2px;
                padding: 2px 0;
            }
            .cb-sidebar-sub-icon {
                width: 28px;
                height: 22px;
                border: none;
                border-radius: 3px;
                cursor: pointer;
                font-size: 9px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                color: #888;
                transition: background 0.15s;
            }
            .cb-sidebar-sub-icon:hover {
                background: #444;
                color: #fff;
            }

            </style>
    `;
}

// --- SECTION HEADER ACCENTS ---

const SECTION_ACCENTS = {
    prompts: "#00cc55",
    configs: "#0088ff",
    distribution: "#ff8800",
    preview: "#00cccc"
};

// --- UNIFORM SECTION HEADER ---

export function createSectionHeader(emoji, title, accentKey, { collapsible = false, collapsed = false, onToggle = null } = {}) {
    const accent = SECTION_ACCENTS[accentKey] || "#0088ff";
    const header = document.createElement("div");
    header.className = "cb-section-header";
    header.style.cssText = `background: linear-gradient(90deg, ${accent}22, transparent); border-left: 3px solid ${accent};`;

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `${emoji} ${title}`;
    header.appendChild(titleSpan);

    if (collapsible) {
        header.style.cursor = "pointer";
        const arrow = document.createElement("span");
        arrow.textContent = collapsed ? "▶" : "▼";
        arrow.style.cssText = "margin-left: auto; font-size: 12px; color: #888;";
        header.appendChild(arrow);

        header.onclick = () => {
            if (onToggle) onToggle();
        };
    }

    return header;
}

// --- TOP BAR COMPONENT ---

export function createTopBar(node, {
    availableSessions, availableConfigs,
    refreshAllConfigBuilders,
    onLoadSession, onLoadConfig, onSaveConfig
}) {
    const bar = document.createElement("div");
    bar.className = "cb-top-bar";

    // Session name input
    const sessionInput = document.createElement("input");
    sessionInput.className = "cb-top-bar-input";
    sessionInput.type = "text";
    sessionInput.value = node.state.session_name || "my_test_session";
    sessionInput.placeholder = "Session name...";
    sessionInput.title = "Session Name";
    sessionInput.onchange = () => {
        node.state.session_name = sessionInput.value;
        node.saveState();
    };
    bar.appendChild(sessionInput);

    // Settings button + dropdown container
    const settingsWrapper = document.createElement("div");
    settingsWrapper.style.position = "relative";

    const settingsBtn = document.createElement("button");
    settingsBtn.className = "cb-settings-btn";
    settingsBtn.innerHTML = "⚙ Settings ▾";

    const dropdown = _createSettingsDropdown(node, {
        availableSessions, availableConfigs,
        refreshAllConfigBuilders,
        onLoadSession, onLoadConfig, onSaveConfig
    });

    settingsBtn.onclick = (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("open");
    };

    // Close on click outside
    document.addEventListener("click", (e) => {
        if (!settingsWrapper.contains(e.target)) {
            dropdown.classList.remove("open");
        }
    });

    settingsWrapper.appendChild(settingsBtn);
    settingsWrapper.appendChild(dropdown);
    bar.appendChild(settingsWrapper);

    return bar;
}

// --- SETTINGS DROPDOWN (internal) ---

function _createSettingsDropdown(node, {
    availableSessions, availableConfigs,
    refreshAllConfigBuilders,
    onLoadSession, onLoadConfig, onSaveConfig
}) {
    const dropdown = document.createElement("div");
    dropdown.className = "cb-settings-dropdown";

    // Helper: create expandable item
    function addExpandableItem(emoji, label, expandContent) {
        const item = document.createElement("div");
        item.className = "cb-settings-item";
        item.innerHTML = `<span>${emoji}</span><span>${label}</span><span style="margin-left:auto;font-size:10px;color:#666">▶</span>`;

        const expand = document.createElement("div");
        expand.className = "cb-settings-expand";
        expand.appendChild(expandContent);

        item.onclick = (e) => {
            e.stopPropagation();
            // Close other expands
            dropdown.querySelectorAll(".cb-settings-expand.open").forEach(el => {
                if (el !== expand) el.classList.remove("open");
            });
            expand.classList.toggle("open");
            const arrow = item.querySelector("span:last-child");
            arrow.textContent = expand.classList.contains("open") ? "▼" : "▶";
        };

        dropdown.appendChild(item);
        dropdown.appendChild(expand);
    }

    // Helper: create toggle item
    function addToggleItem(emoji, label, checked, onChange) {
        const item = document.createElement("label");
        item.className = "cb-settings-item";
        item.style.cursor = "pointer";
        const iconSpan = document.createElement("span");
        iconSpan.textContent = emoji;
        item.appendChild(iconSpan);
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = checked;
        cb.onchange = () => onChange(cb.checked);
        item.appendChild(cb);
        const lbl = document.createElement("span");
        lbl.textContent = label;
        item.appendChild(lbl);
        dropdown.appendChild(item);
    }

    // Helper: divider
    function addDivider() {
        const d = document.createElement("div");
        d.className = "cb-settings-divider";
        dropdown.appendChild(d);
    }

    // === Load Session (expandable) ===
    const sessionSelectContainer = document.createElement("div");
    const sessionSelect = createSearchableSelect(
        availableSessions || [],
        "",
        (value) => {
            if (value && value !== "None") {
                onLoadSession(value);
                dropdown.classList.remove("open");
            }
        },
        "Search sessions..."
    );
    sessionSelectContainer.appendChild(sessionSelect);
    addExpandableItem("📂", "Load Session", sessionSelectContainer);

    // === Load Config (expandable) ===
    const configSelectContainer = document.createElement("div");
    const configSelect = createSearchableSelect(
        availableConfigs || [],
        "",
        (value) => {
            if (value && value !== "None") {
                onLoadConfig(value);
                dropdown.classList.remove("open");
            }
        },
        "Search configs..."
    );
    configSelectContainer.appendChild(configSelect);
    addExpandableItem("📂", "Load Config", configSelectContainer);

    // === Save Config (expandable) ===
    const saveContainer = document.createElement("div");
    saveContainer.style.cssText = "display: flex; gap: 6px; align-items: center;";
    const saveNameInput = document.createElement("input");
    saveNameInput.className = "cb-input";
    saveNameInput.style.cssText = "flex: 1; font-size: 12px; padding: 6px 8px;";
    saveNameInput.value = node.state.config_name || "";
    saveNameInput.placeholder = "config_name";
    saveNameInput.onchange = () => {
        node.state.config_name = saveNameInput.value;
        node.saveState();
    };
    const saveBtn = document.createElement("button");
    saveBtn.className = "cb-button primary";
    saveBtn.textContent = "💾 Save";
    saveBtn.style.cssText = "font-size: 12px; padding: 6px 12px;";
    saveBtn.onclick = async (e) => {
        e.stopPropagation();
        node.state.config_name = saveNameInput.value;
        await onSaveConfig();
        saveBtn.textContent = "✅ Saved!";
        setTimeout(() => { saveBtn.textContent = "💾 Save"; }, 2000);
    };
    saveContainer.appendChild(saveNameInput);
    saveContainer.appendChild(saveBtn);
    addExpandableItem("💾", "Save Config", saveContainer);

    addDivider();

    // === Auto-Save toggle ===
    addToggleItem("💾", "Auto-Save (2s)", node.state.auto_save || false, (val) => {
        node.state.auto_save = val;
        node.saveState();
    });

    addDivider();

    // === Enable Distribution toggle ===
    addToggleItem("🌐", "Enable Distribution", node.state.distribution_enabled || false, (val) => {
        node.state.distribution_enabled = val;
        node.saveState();
        node.renderUI();
    });

    addDivider();

    // === Refresh Models action ===
    const refreshItem = document.createElement("div");
    refreshItem.className = "cb-settings-item";
    const refreshIcon = document.createElement("span");
    refreshIcon.textContent = "🔄";
    refreshItem.appendChild(refreshIcon);
    const refreshLabel = document.createElement("span");
    refreshLabel.textContent = "Refresh Models & LoRAs";
    refreshItem.appendChild(refreshLabel);
    refreshItem.onclick = async () => {
        refreshLabel.textContent = "Refreshing...";
        await refreshAllConfigBuilders();
        refreshLabel.textContent = "✅ Refreshed!";
        setTimeout(() => {
            refreshLabel.textContent = "Refresh Models & LoRAs";
        }, 2000);
    };
    dropdown.appendChild(refreshItem);

    // === Label Mode toggle ===
    addToggleItem("🏷️", "Label Mode", node.state.label_mode || false, (val) => {
        node.state.label_mode = val;
        node.saveState();
        node.renderUI();
    });

    // === Include None toggle ===
    addToggleItem("⬜", "Include None", node.state.include_none || false, (val) => {
        node.state.include_none = val;
        node.saveState();
    });

    // === Include Default toggle ===
    addToggleItem("⬜", "Include Default", node.state.include_default || false, (val) => {
        node.state.include_default = val;
        node.saveState();
    });

    return dropdown;
}

// --- SIDEBAR COMPONENT ---

export function createSidebar(node, mainContent, refreshAllConfigBuilders) {
    const sidebar = document.createElement("div");
    sidebar.className = "cb-sidebar";

    const icons = [];

    // Navigation icons
    function addNavIcon(emoji, title, targetId) {
        const btn = document.createElement("button");
        btn.className = "cb-sidebar-icon";
        btn.textContent = emoji;
        btn.title = title;
        btn.dataset.targetId = targetId;
        btn.onclick = () => {
            const target = mainContent.querySelector(`#${targetId}`);
            if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        };
        sidebar.appendChild(btn);
        icons.push(btn);
        return btn;
    }

    // Distribution icon (only when enabled, appears first)
    if (node.state.distribution_enabled) {
        addNavIcon("🌐", "Distribution", "cb-sec-distribution");
    }

    addNavIcon("📝", "Global Prompts", "cb-sec-prompts");
    addNavIcon("⚙️", "Config Arrays", "cb-sec-configs");

    // Per-config array navigation icons
    const configColors = ["#0088ff", "#ff6600", "#00cc66", "#cc44cc", "#ffaa00", "#44cccc", "#ff4466", "#88aa00"];
    if (node.state.config_arrays && node.state.config_arrays.length > 0) {
        node.state.config_arrays.forEach((ca, idx) => {
            const color = configColors[idx % configColors.length];
            const group = document.createElement("div");
            group.className = "cb-sidebar-config-group";

            const cogBtn = document.createElement("button");
            cogBtn.className = "cb-sidebar-config-icon";
            cogBtn.style.color = color;
            cogBtn.style.borderLeft = `2px solid ${color}`;
            cogBtn.textContent = `⚙️${idx + 1}`;
            cogBtn.title = ca.name || `Config ${idx + 1}`;
            cogBtn.dataset.targetId = `cb-config-${idx}`;
            cogBtn.onclick = () => {
                const target = mainContent.querySelector(`#cb-config-${idx}`);
                if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
            };
            icons.push(cogBtn);
            group.appendChild(cogBtn);

            // Sub-icons container (always visible)
            const subIcons = document.createElement("div");
            subIcons.className = "cb-sidebar-sub-icons";

            const subSections = [
                { emoji: "🧊", label: "Models", id: `cb-config-${idx}-models` },
                { emoji: "🔣", label: "Text Enc", id: `cb-config-${idx}-te` },
                { emoji: "🎨", label: "VAE", id: `cb-config-${idx}-vae` },
                { emoji: "🔮", label: "LoRAs", id: `cb-config-${idx}-loras` }
            ];

            subSections.forEach(sub => {
                const subBtn = document.createElement("button");
                subBtn.className = "cb-sidebar-sub-icon";
                subBtn.textContent = sub.emoji;
                subBtn.title = sub.label;
                subBtn.onclick = () => {
                    const target = mainContent.querySelector(`#${sub.id}`);
                    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
                };
                subIcons.appendChild(subBtn);
            });

            group.appendChild(subIcons);
            sidebar.appendChild(group);
        });
    }

    // Divider
    const divider = document.createElement("div");
    divider.className = "cb-sidebar-divider";
    sidebar.appendChild(divider);

    // Quick action: Add Config
    const addBtn = document.createElement("button");
    addBtn.className = "cb-sidebar-icon";
    addBtn.textContent = "+";
    addBtn.title = "Add Config";
    addBtn.style.cssText = "font-size: 20px; font-weight: bold;";
    addBtn.onclick = () => {
        node.state.config_arrays.push({
            name: `Config ${node.state.config_arrays.length + 1}`,
            samplers: ["euler"],
            schedulers: ["normal"],
            steps: "20",
            cfg: "7.0",
            seed_behavior: "fixed",
            full_run_seed_behavior: "fixed",
            full_run_seed: 0,
            models: ["None"],
            vaes: ["None"],
            text_encoders: [],
            clip_type: "stable_diffusion",
            gguf_options: {},
            loras: ["None"],
            lora_omit_triggers: [],
            lora_triggerwords_append_settings: {},
            lora_bypass_states: {},
            lora_strength_lock: {},
            model_bypass_states: {},
            vae_bypass_states: {},
            te_bypass_states: {},
            combine: false,
            positive_prompt_groups: [],
            negative_prompt: "",
            use_custom_prompts: false,
            model_prompt_prefix: "",
            model_prompt_suffix: "",
            attention_modes: ["default"],
            resolutions: [],
            model_sampling_override: "none",
            model_sampling_shift: "1.73",
            model_sampling_flux_max_shift: "1.15",
            model_sampling_flux_base_shift: "0.5",
            use_advanced_sampling: false,
            advanced_guider: "cfg_guider",
            advanced_scheduler: "basic",
            use_flux_guidance: false,
            flux_guidance_value: "3.5"
        });
        node.saveState();
        node.renderUI();
    };
    sidebar.appendChild(addBtn);

    // Quick action: Refresh Models
    const refreshBtn = document.createElement("button");
    refreshBtn.className = "cb-sidebar-icon";
    refreshBtn.textContent = "🔄";
    refreshBtn.title = "Refresh Models & LoRAs";
    refreshBtn.onclick = async () => {
        refreshBtn.style.opacity = "0.5";
        await refreshAllConfigBuilders();
        refreshBtn.style.opacity = "1";
    };
    sidebar.appendChild(refreshBtn);

    // Scroll spy: highlight active section
    const sectionIds = ["cb-sec-prompts", "cb-sec-configs"];
    // Add per-config section IDs for scroll spy
    if (node.state.config_arrays) {
        node.state.config_arrays.forEach((_, idx) => {
            sectionIds.push(`cb-config-${idx}`);
        });
    }
    sectionIds.push("cb-sec-distribution");
    const updateActiveIcon = () => {
        const scrollTop = mainContent.scrollTop;
        let activeId = sectionIds[0];
        for (const id of sectionIds) {
            const el = mainContent.querySelector(`#${id}`);
            if (el && el.offsetTop - 20 <= scrollTop) {
                activeId = id;
            }
        }
        icons.forEach(btn => {
            btn.classList.toggle("active", btn.dataset.targetId === activeId);
        });
    };
    mainContent.addEventListener("scroll", updateActiveIcon);
    // Initial highlight
    setTimeout(updateActiveIcon, 50);

    return sidebar;
}