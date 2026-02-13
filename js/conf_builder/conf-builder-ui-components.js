/**
 * Config Builder UI Components Module
 * Reusable UI elements and component builders
 */

import { normalizePath } from '/ultimate_config_sampler/js/conf_builder/conf-builder-utilities.js';

// --- SEARCHABLE SELECT COMPONENT ---

export function createSearchableSelect(options, currentValue, onChange, placeholder = "Search...") {
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
        dropdown.innerHTML = "";
        filteredOptions.forEach(opt => {
            const optDiv = document.createElement("div");
            optDiv.textContent = opt;
            optDiv.style.cssText = `
                padding: 8px 10px;
                cursor: pointer;
                color: white;
                font-size: 13px;
                font-family: monospace;
            `;
            optDiv.onmouseover = () => optDiv.style.background = "#2a2a2a";
            optDiv.onmouseout = () => optDiv.style.background = "transparent";
            optDiv.onclick = () => {
                input.value = opt;
                dropdown.style.display = "none";
                onChange(opt);
            };
            dropdown.appendChild(optDiv);
        });

        if (filteredOptions.length === 0) {
            const noResults = document.createElement("div");
            noResults.textContent = "No matches found";
            noResults.style.cssText = "padding: 8px 10px; color: #666; font-style: italic;";
            dropdown.appendChild(noResults);
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

    // Close dropdown when clicking outside
    document.addEventListener("click", (e) => {
        if (!container.contains(e.target)) {
            dropdown.style.display = "none";
        }
    });

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
            .cb-container { padding: 12px; height: 100%; overflow-y: auto; box-sizing: border-box; }
            .cb-sections-row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
            .cb-section { background: #2a2a2a; border-radius: 4px; padding: 12px; border: 1px solid #3a3a3a; box-sizing: border-box; flex: 1 1 300px; }
            .cb-section.full-width { flex: 1 1 100%; width: 100%; }
            .cb-section-title { color: #0066cc; font-size: 14px; font-weight: bold; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #3a3a3a; }
            .cb-flex-grid { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
            .cb-input-group { flex: 1 1 180px; min-width: 140px; display: flex; flex-direction: column; }
            .cb-input, .cb-select { background: #1a1a1a; border: 1px solid #4a4a4a; color: white; padding: 8px 10px; border-radius: 4px; width: 100%; box-sizing: border-box; font-size: 13px; font-family: monospace; }
            .cb-input:focus, .cb-select:focus { outline: none; border-color: #0066cc; }
            .cb-label { color: #aaa; font-size: 12px; margin-bottom: 4px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .cb-button { background: #4a4a4a; border: none; color: white; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; margin: 4px 2px; white-space: nowrap; }
            .cb-button:hover { background: #5a5a5a; }
            .cb-button.primary { background: #0066cc; }
            .cb-button.primary:hover { background: #0077ee; }
            .cb-button.danger { background: #cc3333; }
            .cb-button.danger:hover { background: #dd4444; }
            .cb-array { background: #333; border-radius: 4px; padding: 12px; margin: 8px 0; border: 1px solid #3a3a3a; width: 100%; }
            .cb-arrays-container { display: flex; flex-direction: column; gap: 12px; }
            .cb-list-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #444; }
            .cb-item-card { background: #2a2a2a; border-radius: 4px; padding: 10px; border-left: 3px solid #0066cc; flex: 1 1 300px; min-width: 250px; display: flex; flex-direction: column; gap: 6px; }
            .cb-item-card.model-card { border-left-color: #cc6600; }
            .cb-slider-container { display: flex; align-items: center; gap: 10px; }
            .cb-slider { flex: 1; height: 6px; background: #1a1a1a; border-radius: 3px; outline: none; }
            
            /* Numerical Input Styles */
            .cb-number-input { width: 60px; background: #1a1a1a; color: #0066cc; border: 1px solid #3a3a3a; border-radius: 4px; padding: 2px 4px; font-size: 12px; font-family: monospace; text-align: right; margin-left: 8px; }
            .cb-number-input:focus { outline: none; border-color: #0066cc; }

            .cb-toggle { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; padding: 6px 0; }
            .cb-preview { background: #0a0a0a; border: 1px solid #3a3a3a; border-radius: 4px; padding: 10px; margin: 10px 0; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 11px; color: #0cc; }
            .cb-controls-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 10px; padding: 8px; background: #252525; border-radius: 4px; }
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
                
            </style>
    `;
}