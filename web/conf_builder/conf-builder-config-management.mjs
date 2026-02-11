/**
 * Config Builder Configuration Management Module
 * Handles state management, UI rendering, and config operations
 */

import {
    normalizePath,
    getShortName,
    parseLoraString,
    buildLoraString,
    getIterationCount,
    convertStateToConfigs
} from './conf-builder-utilities.mjs?v=2'; // RELATIVE IMPORT

import {
    createSearchableSelect,
    createSlider,
    createInputGroup,
    getStyles
} from './conf-builder-ui-components.mjs?v=2'; // RELATIVE IMPORT

// --- SESSION SECTION RENDERER ---

export function renderSessionSection(node, container, availableSessions, refreshAllConfigBuilders) {
    const section = document.createElement("div");
    section.className = "cb-section";
    section.innerHTML = '<div class="cb-section-title">📁 Session Management</div>';
    const grid = document.createElement("div");
    grid.className = "cb-flex-grid";

    const nameInput = document.createElement("input");
    nameInput.className = "cb-input";
    nameInput.value = node.state.session_name;
    nameInput.onchange = () => { node.state.session_name = nameInput.value; node.saveState(); };
    grid.appendChild(createInputGroup("Session Name", nameInput));

    const loadSearchable = createSearchableSelect(
        availableSessions,
        "",
        async (value) => {
            if (value && value !== "None") {
                node.state.auto_save = false;
                await node.loadSession(value);
            }
        },
        "Search sessions..."
    );
    grid.appendChild(createInputGroup("Load Session", loadSearchable));

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "cb-button primary";
    refreshBtn.textContent = "🔄 Refresh Models/LoRAs";
    refreshBtn.style.width = "100%";
    refreshBtn.title = "Clear cache and reload model/LoRA lists from disk";
    refreshBtn.onclick = async () => {
        refreshBtn.disabled = true;
        refreshBtn.textContent = "🔄 Refreshing...";
        await refreshAllConfigBuilders();
        refreshBtn.disabled = false;
        refreshBtn.textContent = "✅ Refreshed!";
        setTimeout(() => { refreshBtn.textContent = "🔄 Refresh Models/LoRAs"; }, 2000);
    };
    grid.appendChild(createInputGroup("Reload Lists", refreshBtn));

    section.appendChild(grid);
    container.appendChild(section);
}

// --- CONFIG SECTION RENDERER ---

export function renderConfigSection(node, container, availableConfigs) {
    const section = document.createElement("div");
    section.className = "cb-section";
    section.innerHTML = '<div class="cb-section-title">💾 Config Management</div>';
    const grid = document.createElement("div");
    grid.className = "cb-flex-grid";

    const nameInput = document.createElement("input");
    nameInput.className = "cb-input";
    nameInput.value = node.state.config_name;
    nameInput.placeholder = "my_config";
    nameInput.onchange = () => {
        node.state.config_name = nameInput.value;
        node.saveState();
    };
    grid.appendChild(createInputGroup("Config Name (Filename)", nameInput));

    const loadSearchable = createSearchableSelect(
        availableConfigs,
        "",
        async (value) => {
            if (value && value !== "None") {
                await node.loadConfigFromBackend(value);
            }
        },
        "Load Config..."
    );
    grid.appendChild(createInputGroup("Load Saved Config", loadSearchable));

    const buttonsDiv = document.createElement("div");
    buttonsDiv.style.cssText = "display: flex; flex-direction: column; gap: 5px; height: 100%; justify-content: flex-end;";

    const saveBtn = document.createElement("button");
    saveBtn.className = "cb-button primary";
    saveBtn.textContent = "💾 Save Config Now";
    saveBtn.style.width = "100%";
    saveBtn.onclick = async () => {
        await node.saveConfigToBackend();
        const { getAvailableConfigs } = await import('./conf-builder-utilities.mjs');
        await getAvailableConfigs();
        node.renderUI();
    };
    buttonsDiv.appendChild(saveBtn);

    const autoSaveLabel = document.createElement("label");
    autoSaveLabel.className = "cb-toggle";
    autoSaveLabel.style.fontSize = "12px";

    const autoSaveCheckbox = document.createElement("input");
    autoSaveCheckbox.type = "checkbox";
    autoSaveCheckbox.checked = node.state.auto_save;
    autoSaveCheckbox.onchange = () => {
        node.state.auto_save = autoSaveCheckbox.checked;
        node.saveState();
    };

    autoSaveLabel.appendChild(autoSaveCheckbox);
    autoSaveLabel.appendChild(document.createTextNode(" Auto-Save (2s)"));
    buttonsDiv.appendChild(autoSaveLabel);

    grid.appendChild(createInputGroup("Actions", buttonsDiv));
    section.appendChild(grid);
    container.appendChild(section);
}

// --- CONFIG ARRAY ELEMENT CREATOR ---

export function createConfigArrayElement(node, configArray, arrayIdx) {
    const div = document.createElement("div");
    div.className = "cb-array";

    const settingsGrid = document.createElement("div");
    settingsGrid.className = "cb-flex-grid";

    // Helper for inputs to reduce code duplication
    const addInput = (label, key) => {
        const input = document.createElement("input");
        input.className = "cb-input";
        input.value = configArray[key];
        input.onchange = () => { node.state.config_arrays[arrayIdx][key] = input.value; node.saveState(); };
        settingsGrid.appendChild(createInputGroup(label, input));
    };

    addInput("Config Name", "name");
    addInput("Samplers", "samplers");
    addInput("Schedulers", "schedulers");
    addInput("Steps", "steps");
    addInput("CFG", "cfg");

    div.appendChild(settingsGrid);

    const controlsBar = document.createElement("div");
    controlsBar.className = "cb-controls-bar";

    const iterationCount = getIterationCount(configArray);
    const countDisplay = document.createElement("div");
    countDisplay.style.cssText = "color: #00cc00; font-family: monospace; font-size: 13px; font-weight: bold; display: flex; align-items: center;";
    countDisplay.innerHTML = `⏱️ Iterations: ${iterationCount}`;
    controlsBar.appendChild(countDisplay);

    const spacer = document.createElement("div");
    spacer.style.flex = "1";
    controlsBar.appendChild(spacer);

    const addModelBtn = document.createElement("button");
    addModelBtn.className = "cb-button";
    addModelBtn.style.borderLeft = "4px solid #cc6600";
    addModelBtn.textContent = `➕ Add Model`;
    addModelBtn.onclick = () => {
        if (!node.state.config_arrays[arrayIdx].models) node.state.config_arrays[arrayIdx].models = [];
        node.state.config_arrays[arrayIdx].models.push("None");
        node.saveState();
        node.renderUI();
    };
    controlsBar.appendChild(addModelBtn);

    const addLoraBtn = document.createElement("button");
    addLoraBtn.className = "cb-button";
    addLoraBtn.style.borderLeft = "4px solid #0066cc";
    addLoraBtn.textContent = `➕ Add LoRA`;
    addLoraBtn.onclick = () => {
        if (!node.state.config_arrays[arrayIdx].loras) node.state.config_arrays[arrayIdx].loras = [];
        node.state.config_arrays[arrayIdx].loras.push("None");
        node.saveState();
        node.renderUI();
    };
    controlsBar.appendChild(addLoraBtn);

    const duplicateBtn = document.createElement("button");
    duplicateBtn.className = "cb-button primary";
    duplicateBtn.textContent = "📋 Duplicate";
    duplicateBtn.onclick = () => {
        const clone = JSON.parse(JSON.stringify(configArray));
        clone.name = `${clone.name} (Copy)`;
        node.state.config_arrays.splice(arrayIdx + 1, 0, clone);
        node.saveState();
        node.renderUI();
    };
    controlsBar.appendChild(duplicateBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "cb-button danger";
    deleteBtn.textContent = "🗑️ Delete";
    deleteBtn.onclick = () => {
        if (node.state.config_arrays.length > 1) {
            node.state.config_arrays.splice(arrayIdx, 1);
            node.saveState();
            node.renderUI();
        }
    };
    controlsBar.appendChild(deleteBtn);

    div.appendChild(controlsBar);
    return div;
}

// --- MODEL ELEMENT CREATOR ---

export function createModelElement(node, modelStr, arrayIdx, modelIdx, availableModels, modelFolders) {
    const div = document.createElement("div");
    div.className = "cb-item-card model-card";
    const isFolder = modelStr.endsWith("/");
    const uid = `${arrayIdx}_${modelIdx}`;
    
    // Initial State
    const isCollapsed = node.uiState.modelsCollapsed[uid] || false;

    // Header
    const header = document.createElement("div");
    header.className = "cb-header-bar";
    
    const leftGroup = document.createElement("div");
    leftGroup.className = "cb-header-left";

    const toggleArrow = document.createElement("span");
    toggleArrow.textContent = isCollapsed ? "▶" : "▼"; // Right arrow if collapsed, Down if open
    toggleArrow.style.color = "#aaa";
    toggleArrow.style.fontSize = "10px";
    toggleArrow.style.width = "12px";
    leftGroup.appendChild(toggleArrow);

    const label = document.createElement("span");
    label.textContent = `Model #${modelIdx + 1}`;
    label.style.color = "#aaa";
    label.style.whiteSpace = "nowrap";
    leftGroup.appendChild(label);

    const nameSpan = document.createElement("span");
    nameSpan.className = "cb-header-name";
    nameSpan.textContent = getShortName(modelStr);
    leftGroup.appendChild(nameSpan);

    header.appendChild(leftGroup);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "cb-button danger";
    deleteBtn.style.padding = "2px 6px";
    deleteBtn.style.fontSize = "10px";
    deleteBtn.textContent = "✖";
    deleteBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].models.splice(modelIdx, 1);
        node.saveState();
        node.renderUI();
    };
    header.appendChild(deleteBtn);
    div.appendChild(header);

    // Content Container (Rendered but hidden if collapsed)
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "flex";
    contentDiv.style.flexDirection = "column";
    contentDiv.style.gap = "6px";
    contentDiv.style.width = "100%";

    // --- TOGGLE LOGIC (INSTANT) ---
    header.onclick = (e) => {
        if (e.target.tagName === 'BUTTON') return; // Ignore delete button
        
        const isNowCollapsed = contentDiv.style.display !== "none";
        contentDiv.style.display = isNowCollapsed ? "none" : "flex";
        toggleArrow.textContent = isNowCollapsed ? "▶" : "▼";
        
        // Save state silently
        node.uiState.modelsCollapsed[uid] = isNowCollapsed;
    };

    // Type Select
    const typeSelect = document.createElement("select");
    typeSelect.className = "cb-select";
    typeSelect.innerHTML = `
        <option value="file" ${!isFolder ? 'selected' : ''}>Checkpoint File</option>
        <option value="folder" ${isFolder ? 'selected' : ''}>Folder</option>
    `;
    typeSelect.onchange = () => {
        node.state.config_arrays[arrayIdx].models[modelIdx] = typeSelect.value === "folder" ? "/" : "None";
        node.saveState();
        node.renderUI();
    };
    contentDiv.appendChild(typeSelect);

    // Searchable Select
    const options = isFolder ? modelFolders : availableModels;
    const currentVal = modelStr;
    const optionsList = (options && options.includes(currentVal)) || currentVal === "None" || currentVal === "/" 
        ? options || ["None"]
        : [currentVal, ...(options || ["None"])];

    const nameSearchable = createSearchableSelect(
        optionsList,
        currentVal,
        (value) => {
            node.state.config_arrays[arrayIdx].models[modelIdx] = normalizePath(value);
            node.saveState();
            node.renderUI();
        },
        isFolder ? "Search folders..." : "Search models..."
    );
    contentDiv.appendChild(nameSearchable);

    if (isFolder && modelStr !== "None" && modelStr !== "/") {
        const expandBtn = document.createElement("button");
        expandBtn.className = "cb-button";
        expandBtn.style.borderLeft = "3px solid #cc6600";
        expandBtn.style.width = "100%";
        expandBtn.style.fontSize = "11px";
        expandBtn.style.marginTop = "4px";
        expandBtn.textContent = "📂 Add all individually";
        expandBtn.onclick = () => {
            const normalize = (str) => str.replace(/\\/g, "/");
            const folderPrefix = normalize(modelStr);
            const matchingModels = availableModels ? availableModels.filter(m => normalize(m).startsWith(folderPrefix)) : [];
            if (matchingModels.length > 0) {
                node.state.config_arrays[arrayIdx].models.splice(modelIdx, 1, ...matchingModels);
                node.saveState();
                node.renderUI();
            } else {
                alert(`No Checkpoints found in folder: ${folderPrefix}`);
            }
        };
        contentDiv.appendChild(expandBtn);
    }

    div.appendChild(contentDiv);
    return div;
}

// --- LORA ELEMENT CREATOR ---

export function createLoraElement(node, loraStr, arrayIdx, loraIdx, availableLoras, loraFolders) {
    const div = document.createElement("div");
    div.className = "cb-item-card";
    const parsed = parseLoraString(loraStr);
    const isCombined = parsed.name.endsWith("/*");
    const cleanName = parsed.name.replace(/\*$/, "");
    const isFolder = parsed.name.endsWith("/") || isCombined;
    const uid = `${arrayIdx}_${loraIdx}`;
    
    const isCollapsed = node.uiState.lorasCollapsed[uid] || false;
    let currentModelStr = parsed.model_str;
    let currentClipStr = parsed.clip_str;

    // Header
    const header = document.createElement("div");
    header.className = "cb-header-bar";

    const leftGroup = document.createElement("div");
    leftGroup.className = "cb-header-left";

    const toggleArrow = document.createElement("span");
    toggleArrow.textContent = isCollapsed ? "▶" : "▼";
    toggleArrow.style.color = "#aaa";
    toggleArrow.style.fontSize = "10px";
    toggleArrow.style.width = "12px";
    leftGroup.appendChild(toggleArrow);

    const label = document.createElement("span");
    label.textContent = `LoRA #${loraIdx + 1}`;
    label.style.color = "#aaa";
    label.style.whiteSpace = "nowrap";
    leftGroup.appendChild(label);

    const nameSpan = document.createElement("span");
    nameSpan.className = "cb-header-name";
    nameSpan.textContent = getShortName(parsed.name);
    leftGroup.appendChild(nameSpan);

    header.appendChild(leftGroup);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "cb-button danger";
    deleteBtn.style.padding = "2px 6px";
    deleteBtn.style.fontSize = "10px";
    deleteBtn.textContent = "✖";
    deleteBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].loras.splice(loraIdx, 1);
        node.saveState();
        node.renderUI();
    };
    header.appendChild(deleteBtn);
    div.appendChild(header);

    // Content
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "flex";
    contentDiv.style.flexDirection = "column";
    contentDiv.style.gap = "6px";
    contentDiv.style.width = "100%";

    // --- TOGGLE LOGIC (INSTANT) ---
    header.onclick = (e) => {
        if (e.target.tagName === 'BUTTON') return;
        
        const isNowCollapsed = contentDiv.style.display !== "none";
        contentDiv.style.display = isNowCollapsed ? "none" : "flex";
        toggleArrow.textContent = isNowCollapsed ? "▶" : "▼";
        
        node.uiState.lorasCollapsed[uid] = isNowCollapsed;
    };

    const typeSelect = document.createElement("select");
    typeSelect.className = "cb-select";
    typeSelect.innerHTML = `
        <option value="file" ${!isFolder ? 'selected' : ''}>LoRA File</option>
        <option value="folder" ${isFolder && !isCombined ? 'selected' : ''}>Folder (Individual)</option>
        <option value="combined" ${isCombined ? 'selected' : ''}>Folder (Combined Stack)</option>
    `;
    typeSelect.onchange = () => {
        if (typeSelect.value === "folder") node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString("/", currentModelStr, currentClipStr);
        else if (typeSelect.value === "combined") node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString("/*", currentModelStr, currentClipStr);
        else node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString("None", currentModelStr, currentClipStr);
        node.saveState();
        node.renderUI();
    };
    contentDiv.appendChild(typeSelect);

    const options = isFolder ? loraFolders : availableLoras;
    const currentVal = isCombined ? cleanName : parsed.name;
    const optionsList = (options && options.includes(currentVal)) || currentVal === "None" || currentVal === "/" || currentVal === ""
        ? options || ["None"]
        : [currentVal, ...(options || ["None"])];

    const nameSearchable = createSearchableSelect(
        optionsList,
        currentVal,
        (selectedName) => {
            const finalName = isCombined && !selectedName.endsWith("*") && selectedName !== "None"
                ? normalizePath(selectedName) + "*"
                : normalizePath(selectedName);
            node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(finalName, currentModelStr, currentClipStr);
            node.saveState();
            node.renderUI();
        },
        isFolder ? "Search folders..." : "Search LoRAs..."
    );
    contentDiv.appendChild(nameSearchable);

    const modelSlider = createSlider("Model Strength", currentModelStr, 0, 2, 0.05, (val) => {
        currentModelStr = val;
        const currentName = isCombined ? cleanName + "*" : parsed.name;
        node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, currentModelStr, currentClipStr);
        node.saveState();
    });
    contentDiv.appendChild(modelSlider);

    const clipSlider = createSlider("CLIP Strength", currentClipStr, 0, 2, 0.05, (val) => {
        currentClipStr = val;
        const currentName = isCombined ? cleanName + "*" : parsed.name;
        node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, currentModelStr, currentClipStr);
        node.saveState();
    });
    contentDiv.appendChild(clipSlider);

    if (parsed.name !== "None") {
        const triggerSection = document.createElement("div");
        triggerSection.style.cssText = `background: #2a2a2a; border-radius: 4px; padding: 8px; margin-top: 6px; border-left: 3px solid #00aa88;`;
        
        const triggerTitle = document.createElement("div");
        triggerTitle.textContent = "🏷️ Auto Append LoRA Trigger Words To:";
        triggerTitle.style.cssText = "font-size: 11px; font-weight: bold; color: #00aa88; margin-bottom: 6px;";
        triggerSection.appendChild(triggerTitle);

        if (!node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings) {
            node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings = {};
        }
        const currentPlacement = node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings[parsed.name] || "none";

        const checkboxContainer = document.createElement("div");
        checkboxContainer.style.cssText = "display: flex; gap: 12px; align-items: center;";

        const createCheck = (lbl, val) => {
            const label = document.createElement("label");
            label.style.cssText = "display: flex; align-items: center; gap: 4px; font-size: 12px; cursor: pointer;";
            const check = document.createElement("input");
            check.type = "checkbox";
            check.checked = currentPlacement === val;
            check.onchange = () => {
                 node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings[parsed.name] = check.checked ? val : "none";
                 node.saveState();
                 // This one technically could just re-render or not, 
                 // but since it affects checkbox state of "the other" box, we might want to re-render OR manual toggle.
                 // For now, saveState is enough, UI will update next time or you can manipulate DOM.
                 // To avoid lag, we manually uncheck the other one:
                 if(check.checked) {
                     const other = checkboxContainer.querySelectorAll('input');
                     other.forEach(i => { if(i !== check) i.checked = false; });
                 }
            };
            label.appendChild(check);
            label.appendChild(document.createTextNode(lbl));
            return label;
        };

        checkboxContainer.appendChild(createCheck("Start", "start"));
        checkboxContainer.appendChild(createCheck("End", "end"));
        triggerSection.appendChild(checkboxContainer);
        contentDiv.appendChild(triggerSection);
    }

    if (isFolder && parsed.name !== "None") {
        const expandBtn = document.createElement("button");
        expandBtn.className = "cb-button";
        expandBtn.style.cssText = "width: 100%; border-left: 3px solid #0066cc; font-size: 11px; margin-top: 4px;";
        expandBtn.textContent = "📂 Add all individually";
        expandBtn.onclick = () => {
            const normalize = (str) => str.replace(/\\/g, "/");
            let matchingLoras;
            if (cleanName === "/" || cleanName === "") matchingLoras = availableLoras || [];
            else {
                const folderPrefix = normalize(cleanName);
                matchingLoras = availableLoras ? availableLoras.filter(l => normalize(l).startsWith(folderPrefix)) : [];
            }
            if (matchingLoras.length > 0) {
                const withStrengths = matchingLoras.map(l => buildLoraString(l, parsed.model_str, parsed.clip_str));
                node.state.config_arrays[arrayIdx].loras.splice(loraIdx, 1, ...withStrengths);
                node.saveState();
                node.renderUI();
            } else {
                alert(`No LoRAs found in folder: ${cleanName}`);
            }
        };
        contentDiv.appendChild(expandBtn);
    }

    div.appendChild(contentDiv);
    return div;
}

// --- RENDER MODELS AND LORAS SECTIONS ---

export function renderModelsSection(node, div, configArray, arrayIdx, availableModels, modelFolders) {
    if (!configArray.models || configArray.models.length === 0) configArray.models = ["None"];

    const isSectionCollapsed = node.uiState.modelsSectionCollapsed[arrayIdx] || false;

    // FIX: Restore class for Grid Layout
    const modelGrid = document.createElement("div");
    modelGrid.className = "cb-list-grid";

    const modelHeader = document.createElement("div");
    modelHeader.className = "cb-section-toggle";
    modelHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #cc6600;";

    let totalModels = 0;
    configArray.models.forEach(m => {
        if (m === "None") totalModels++;
        else if (m.endsWith("/")) {
            const norm = normalizePath(m);
            if (norm === "/") totalModels += availableModels ? availableModels.length : 1;
            else totalModels += availableModels ? availableModels.filter(am => normalizePath(am).startsWith(norm)).length : 1;
        } else totalModels++;
    });

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `Models (${configArray.models.length} Entries, Totaling ${totalModels} Models)`;
    modelHeader.appendChild(titleSpan);

    const arrowSpan = document.createElement("span");
    arrowSpan.textContent = isSectionCollapsed ? "▶" : "▼"; // Initial icon
    modelHeader.appendChild(arrowSpan);

    modelGrid.appendChild(modelHeader);

    // CONTENT CONTAINER (Always render, just toggle display)
    const contentContainer = document.createElement("div");
    contentContainer.style.display = isSectionCollapsed ? "none" : "contents"; // 'contents' keeps the grid layout working!
    // Note: 'contents' acts as if the container isn't there, so children become grid items.
    
    // --- HEADER CLICK (INSTANT) ---
    modelHeader.onclick = () => {
        const isNowCollapsed = contentContainer.style.display === "none";
        // Toggle
        if (isNowCollapsed) {
             contentContainer.style.display = "contents";
             arrowSpan.textContent = "▼";
             node.uiState.modelsSectionCollapsed[arrayIdx] = false;
        } else {
             contentContainer.style.display = "none";
             arrowSpan.textContent = "▶";
             node.uiState.modelsSectionCollapsed[arrayIdx] = true;
        }
    };

    // Always render items
    configArray.models.forEach((model, modelIdx) => {
        contentContainer.appendChild(createModelElement(node, model, arrayIdx, modelIdx, availableModels, modelFolders));
    });

    // FIX: Add Model Button (Bottom)
    const addRow = document.createElement("div");
    addRow.style.width = "100%";
    addRow.style.padding = "4px 0";
    const addBtn = document.createElement("button");
    addBtn.className = "cb-button";
    addBtn.style.cssText = "width: 100%; border: 1px dashed #555; background: rgba(0,0,0,0.2); color: #aaa;";
    addBtn.textContent = "➕ Add New Model";
    addBtn.onmouseover = () => addBtn.style.background = "rgba(255,255,255,0.1)";
    addBtn.onmouseout = () => addBtn.style.background = "rgba(0,0,0,0.2)";
    addBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].models.push("None");
        node.saveState();
        node.renderUI();
    };
    addRow.appendChild(addBtn);
    contentContainer.appendChild(addRow);

    modelGrid.appendChild(contentContainer);
    div.appendChild(modelGrid);
}

export function renderLorasSection(node, div, configArray, arrayIdx, availableLoras, loraFolders) {
    if (!configArray.loras || configArray.loras.length === 0) configArray.loras = ["None"];

    const isSectionCollapsed = node.uiState.lorasSectionCollapsed[arrayIdx] || false;

    const loraGrid = document.createElement("div");
    loraGrid.className = "cb-list-grid";
    // FIX: Removed flexDirection column. Let Grid/Flex handle it.
    loraGrid.style.width = "100%";

    const loraHeader = document.createElement("div");
    loraHeader.className = "cb-section-toggle";
    loraHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #0066cc;";

    const totalEntries = configArray.loras.length;
    let totalLoras = 0;
    configArray.loras.forEach(l => {
        const parsed = parseLoraString(l);
        if (parsed.name.endsWith("/*") || parsed.name.endsWith("/")) {
            const folderName = parsed.name.replace(/\*$/, "");
            if (folderName === "/") totalLoras += availableLoras ? availableLoras.length : 0;
            else {
                const prefix = normalizePath(folderName);
                totalLoras += availableLoras ? availableLoras.filter(al => normalizePath(al).startsWith(prefix)).length : 0;
            }
        } else if (parsed.name !== "None") totalLoras++;
    });

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `LoRAs (${totalEntries} Entries, Totaling ${totalLoras} LoRAs)`;
    loraHeader.appendChild(titleSpan);

    const arrowSpan = document.createElement("span");
    arrowSpan.textContent = isSectionCollapsed ? "▶" : "▼";
    loraHeader.appendChild(arrowSpan);

    loraGrid.appendChild(loraHeader);

    // CONTENT CONTAINER
    const contentContainer = document.createElement("div");
    // Use 'contents' to allow grid/flex wrapping of children to work properly with parent
    contentContainer.style.display = isSectionCollapsed ? "none" : "contents";
    
    // --- HEADER CLICK (INSTANT) ---
    loraHeader.onclick = () => {
        const isNowCollapsed = contentContainer.style.display === "none";
        if (isNowCollapsed) {
             contentContainer.style.display = "contents";
             arrowSpan.textContent = "▼";
             node.uiState.lorasSectionCollapsed[arrayIdx] = false;
        } else {
             contentContainer.style.display = "none";
             arrowSpan.textContent = "▶";
             node.uiState.lorasSectionCollapsed[arrayIdx] = true;
        }
    };

    configArray.loras.forEach((lora, loraIdx) => {
        contentContainer.appendChild(createLoraElement(node, lora, arrayIdx, loraIdx, availableLoras, loraFolders));
    });

    const addRow = document.createElement("div");
    addRow.style.width = "100%";
    addRow.style.padding = "4px 0";
    const addBtn = document.createElement("button");
    addBtn.className = "cb-button";
    addBtn.style.cssText = "width: 100%; border: 1px dashed #555; background: rgba(0,0,0,0.2); color: #aaa;";
    addBtn.textContent = "➕ Add New LoRA";
    addBtn.onmouseover = () => addBtn.style.background = "rgba(255,255,255,0.1)";
    addBtn.onmouseout = () => addBtn.style.background = "rgba(0,0,0,0.2)";
    addBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].loras.push("None");
        node.saveState();
        node.renderUI();
    };
    addRow.appendChild(addBtn);
    contentContainer.appendChild(addRow);
    
    loraGrid.appendChild(contentContainer);
    div.appendChild(loraGrid);

    // OMIT TRIGGERS (Outside the flex grid loop to stay at bottom)
    const omitContainer = document.createElement("div");
    omitContainer.style.display = isSectionCollapsed ? "none" : "block"; // Separate container for omit, basic block
    
    // Hack: Attach header click listener to this too? 
    // Easier way: The header click updates TWO containers?
    // Or simpler: put omitContainer inside contentContainer? 
    // contentContainer is display: contents, so omitContainer becomes a flex item. 
    // It should be full width.
    omitContainer.style.width = "100%";
    omitContainer.style.flexBasis = "100%"; // Force new line in flex wrap
    
    renderOmitTriggersSection(node, omitContainer, configArray, arrayIdx);
    contentContainer.appendChild(omitContainer);
}

function renderOmitTriggersSection(node, div, configArray, arrayIdx) {
    const omitSection = document.createElement("div");
    omitSection.style.cssText = `
        width: 100%; background: #252525; border-radius: 4px; padding: 10px; margin-top: 10px; border-left: 3px solid #cc6600;
    `;

    const omitTitle = document.createElement("div");
    omitTitle.textContent = "🚫 Omit Trigger Words";
    omitTitle.style.cssText = "font-weight: bold; margin-bottom: 8px; color: #cc6600; font-size: 12px;";
    omitSection.appendChild(omitTitle);

    if (!configArray.lora_omit_triggers) configArray.lora_omit_triggers = [];

    const chipsContainer = document.createElement("div");
    chipsContainer.style.cssText = `display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; min-height: 30px;`;

    const renderChips = () => {
        chipsContainer.innerHTML = "";
        if (configArray.lora_omit_triggers.length === 0) {
            const placeholder = document.createElement("div");
            placeholder.textContent = "No triggers omitted";
            placeholder.style.cssText = "color: #666; font-style: italic; padding: 4px;";
            chipsContainer.appendChild(placeholder);
            return;
        }
        configArray.lora_omit_triggers.forEach((trigger, tIdx) => {
            const chip = document.createElement("div");
            chip.style.cssText = `display: flex; align-items: center; background: #444; color: #fff; border-radius: 12px; padding: 2px 8px; font-size: 11px;`;
            const text = document.createElement("span");
            text.textContent = trigger;
            chip.appendChild(text);
            const closeBtn = document.createElement("span");
            closeBtn.textContent = "×";
            closeBtn.style.cssText = "margin-left: 6px; cursor: pointer; color: #ff8888; font-weight: bold;";
            closeBtn.onclick = () => {
                node.state.config_arrays[arrayIdx].lora_omit_triggers.splice(tIdx, 1);
                node.saveState();
                renderChips();
            };
            chip.appendChild(closeBtn);
            chipsContainer.appendChild(chip);
        });
    };
    renderChips();
    omitSection.appendChild(chipsContainer);

    const inputRow = document.createElement("div");
    inputRow.style.cssText = "display: flex; gap: 8px; margin-bottom: 8px;";
    const triggerInput = document.createElement("input");
    triggerInput.className = "cb-input";
    triggerInput.placeholder = "Enter trigger to omit...";
    triggerInput.style.flex = "1";
    triggerInput.onkeydown = (e) => { if (e.key === "Enter" && triggerInput.value.trim()) addTrigger(); };
    
    const addTriggerBtn = document.createElement("button");
    addTriggerBtn.className = "cb-button primary";
    addTriggerBtn.textContent = "Add";
    addTriggerBtn.style.padding = "4px 12px";
    
    const addTrigger = () => {
        const val = triggerInput.value.trim();
        if (val && !configArray.lora_omit_triggers.includes(val)) {
            node.state.config_arrays[arrayIdx].lora_omit_triggers.push(val);
            node.saveState();
            renderChips();
            triggerInput.value = "";
        }
    };
    addTriggerBtn.onclick = addTrigger;
    inputRow.appendChild(triggerInput);
    inputRow.appendChild(addTriggerBtn);
    omitSection.appendChild(inputRow);

    const lookupBtn = document.createElement("button");
    lookupBtn.className = "cb-button";
    lookupBtn.style.cssText = `width: 100%; background: linear-gradient(135deg, #0066cc, #0088ff); border-left: 4px solid #00aaff; margin-top: 4px;`;
    lookupBtn.textContent = "🔎 Lookup Current LoRA Triggerwords For Review";
    // NOTE: This assumes showTriggerLookupModal is exported/available. 
    // It is defined in this same file below (or above if moved). 
    // Ensure showTriggerLookupModal is imported or defined in scope.
    // In this module it is defined in the same file.
    lookupBtn.onclick = async () => await showTriggerLookupModal(node, arrayIdx);
    omitSection.appendChild(lookupBtn);

    div.appendChild(omitSection);
}

// --- TRIGGER LOOKUP MODAL (Kept same as before) ---
export async function showTriggerLookupModal(node, arrayIdx) {
    // ... (This function remains unchanged from previous versions, 
    //      just ensure it's present in the file)
    const configArray = node.state.config_arrays[arrayIdx];
    const overlay = document.createElement("div");
    overlay.style.cssText = `position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); display: flex; align-items: center; justify-content: center; z-index: 10000;`;
    const modal = document.createElement("div");
    modal.style.cssText = `background: #2a2a2a; border: 2px solid #0066cc; border-radius: 8px; padding: 20px; max-width: 600px; max-height: 80vh; overflow-y: auto; color: white;`;
    const title = document.createElement("h3");
    title.textContent = "🔎 LoRA Trigger Words Lookup";
    title.style.cssText = "margin: 0 0 15px 0; color: #0066cc;";
    modal.appendChild(title);
    const status = document.createElement("div");
    status.textContent = "🔄 Fetching trigger words from CivitAI...";
    status.style.cssText = "margin-bottom: 15px; color: #aaa;";
    modal.appendChild(status);
    const content = document.createElement("div");
    modal.appendChild(content);
    const buttonBar = document.createElement("div");
    buttonBar.style.cssText = "display: flex; gap: 10px; margin-top: 15px; justify-content: flex-end;";
    const addAllBtn = document.createElement("button");
    addAllBtn.className = "cb-button primary";
    addAllBtn.textContent = "➕ Add All Selected to Omit List";
    addAllBtn.disabled = true;
    const closeBtn = document.createElement("button");
    closeBtn.className = "cb-button";
    closeBtn.textContent = "Close";
    closeBtn.onclick = () => document.body.removeChild(overlay);
    buttonBar.appendChild(addAllBtn);
    buttonBar.appendChild(closeBtn);
    modal.appendChild(buttonBar);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    try {
        const loras = configArray.loras.filter(l => l && l !== "None");
        const response = await fetch("/configbuilder/lookup_triggers", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ loras })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const triggers = data.triggers || {};
        status.textContent = `✅ Found triggers for ${Object.keys(triggers).length} LoRAs`;
        const selectedTriggers = new Set();
        Object.entries(triggers).forEach(([loraName, triggerList]) => {
            const loraSection = document.createElement("div");
            loraSection.style.cssText = `background: #333; border-left: 3px solid #0066cc; padding: 10px; margin-bottom: 10px; border-radius: 4px;`;
            const loraTitle = document.createElement("div");
            loraTitle.textContent = getShortName(loraName.replace('.safetensors', ''));
            loraTitle.style.cssText = "font-weight: bold; margin-bottom: 8px; color: #0066cc;";
            loraSection.appendChild(loraTitle);
            if (!triggerList || triggerList.length === 0) {
                const noTriggers = document.createElement("div");
                noTriggers.textContent = "No triggers found";
                noTriggers.style.cssText = "color: #888; font-style: italic;";
                loraSection.appendChild(noTriggers);
            } else {
                triggerList.forEach(trigger => {
                    const triggerRow = document.createElement("label");
                    triggerRow.style.cssText = `display: flex; align-items: center; gap: 8px; padding: 4px; cursor: pointer; border-radius: 3px;`;
                    triggerRow.onmouseover = () => triggerRow.style.background = "#444";
                    triggerRow.onmouseout = () => triggerRow.style.background = "transparent";
                    const checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.checked = false;
                    checkbox.onchange = () => {
                        if (checkbox.checked) selectedTriggers.add(trigger); else selectedTriggers.delete(trigger);
                        addAllBtn.disabled = selectedTriggers.size === 0;
                    };
                    const triggerText = document.createElement("span");
                    triggerText.textContent = trigger;
                    triggerText.style.cssText = "color: #ddd;";
                    triggerRow.appendChild(checkbox);
                    triggerRow.appendChild(triggerText);
                    loraSection.appendChild(triggerRow);
                });
            }
            content.appendChild(loraSection);
        });
        addAllBtn.onclick = () => {
            const existing = new Set(configArray.lora_omit_triggers);
            selectedTriggers.forEach(t => existing.add(t));
            node.state.config_arrays[arrayIdx].lora_omit_triggers = Array.from(existing);
            node.saveState();
            node.renderUI();
            document.body.removeChild(overlay);
        };
    } catch (error) {
        status.textContent = `❌ Error: ${error.message}`;
        console.error("[ConfigBuilder] Trigger lookup error:", error);
    }
}

// --- MAIN RENDER UI FUNCTION ---

export function renderPreviewSection(container) {
    const section = document.createElement("div");
    section.className = "cb-section full-width";
    section.innerHTML = '<div class="cb-section-title">📄 JSON Preview</div>';
    const preview = document.createElement("pre");
    preview.className = "cb-preview";
    preview.id = "json-preview";
    section.appendChild(preview);
    container.appendChild(section);
}

export function updatePreview(node) {
    const preview = node.htmlContainer.querySelector("#json-preview");
    if (!preview) return;
    const configs = convertStateToConfigs(node.state);
    preview.textContent = JSON.stringify(configs, null, 2);
}

export async function renderUI(node, availableLoras, availableModels, loraFolders, modelFolders, availableSessions, availableConfigs, refreshAllConfigBuilders) {
    const scrollContainer = node.htmlContainer.querySelector(".cb-container");
    const savedScrollTop = scrollContainer ? scrollContainer.scrollTop : 0;

    node.htmlContainer.innerHTML = getStyles() + '<div class="cb-container" id="cb-root"></div>';

    const root = node.htmlContainer.querySelector("#cb-root");

    const topRow = document.createElement("div");
    topRow.className = "cb-sections-row";
    renderSessionSection(node, topRow, availableSessions, refreshAllConfigBuilders);
    renderConfigSection(node, topRow, availableConfigs);
    root.appendChild(topRow);

    const configSection = document.createElement("div");
    configSection.className = "cb-section full-width";
    configSection.innerHTML = '<div class="cb-section-title">⚙️ Config Arrays</div>';

    const headerBar = document.createElement("div");
    headerBar.style.marginBottom = "10px";
    const addConfigBtn = document.createElement("button");
    addConfigBtn.className = "cb-button primary";
    addConfigBtn.textContent = "➕ Add Config Array";
    addConfigBtn.onclick = () => {
        node.state.config_arrays.push({
            name: `Config ${node.state.config_arrays.length + 1}`,
            samplers: "euler",
            schedulers: "normal",
            steps: "20",
            cfg: "7.0",
            models: ["None"],
            loras: ["None"],
            lora_omit_triggers: [],
            lora_triggerwords_append_settings: {},
            combine: false
        });
        node.saveState();
        node.renderUI();
    };
    headerBar.appendChild(addConfigBtn);
    configSection.appendChild(headerBar);

    const arraysContainer = document.createElement("div");
    arraysContainer.className = "cb-arrays-container";
    
    node.state.config_arrays.forEach((configArray, arrayIdx) => {
        const arrayElement = createConfigArrayElement(node, configArray, arrayIdx);
        renderModelsSection(node, arrayElement, configArray, arrayIdx, availableModels, modelFolders);
        renderLorasSection(node, arrayElement, configArray, arrayIdx, availableLoras, loraFolders);
        arraysContainer.appendChild(arrayElement);
    });
    
    configSection.appendChild(arraysContainer);
    root.appendChild(configSection);

    renderPreviewSection(root);
    updatePreview(node);

    const newScrollContainer = node.htmlContainer.querySelector(".cb-container");
    if (newScrollContainer) {
        newScrollContainer.scrollTop = savedScrollTop;
    }
}