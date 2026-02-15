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
    convertStateToConfigs,
    countPromptCombinations,
    expandPromptPreview,
    getAvailableVAEs,
    getVAEFolders
} from './conf-builder-utilities.js';

import {
    createSearchableSelect,
    createSlider,
    createInputGroup,
    getStyles
} from './conf-builder-ui-components.js';

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
        const { getAvailableConfigs } = await import('./conf-builder-utilities.js');
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

    // Seed Behavior Select
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
    settingsGrid.appendChild(createInputGroup("Seed Behavior", seedSelect));

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

    const addVaeBtn = document.createElement("button");
    addVaeBtn.className = "cb-button";
    addVaeBtn.style.borderLeft = "4px solid #9900cc";
    addVaeBtn.textContent = `➕ Add VAE`;
    addVaeBtn.onclick = () => {
        if (!node.state.config_arrays[arrayIdx].vaes) node.state.config_arrays[arrayIdx].vaes = [];
        node.state.config_arrays[arrayIdx].vaes.push("None");
        node.saveState();
        node.renderUI();
    };
    controlsBar.appendChild(addVaeBtn);

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

    // Label Mode overlay — shows config name at bottom center of card
    if (node.state.label_mode && configArray.name) {
        const labelOverlay = document.createElement("div");
        labelOverlay.className = "cb-config-label-overlay";
        labelOverlay.textContent = configArray.name;
        div.appendChild(labelOverlay);
    }

    return div;
}

// --- MODEL ELEMENT CREATOR ---

export function createModelElement(node, modelEntry, arrayIdx, modelIdx, modelLists) {
    // Handle both string format (legacy) and object format {path, type}
    const modelPath = typeof modelEntry === 'string' ? modelEntry : (modelEntry?.path || "None");
    const modelType = typeof modelEntry === 'string' ? 'checkpoint' : (modelEntry?.type || 'checkpoint');
    const isFolder = modelPath.endsWith("/");

    const div = document.createElement("div");
    div.className = "cb-item-card model-card";
    const uid = `${arrayIdx}_${modelIdx}`;

    // Initial State
    const isCollapsed = node.uiState.modelsCollapsed[uid] || false;

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
    label.textContent = `Model #${modelIdx + 1}`;
    label.style.color = "#aaa";
    label.style.whiteSpace = "nowrap";
    leftGroup.appendChild(label);

    // Show model type badge
    if (modelType !== "checkpoint") {
        const typeBadge = document.createElement("span");
        typeBadge.textContent = modelType === "gguf" ? "GGUF" : "DM";
        typeBadge.style.cssText = "background: #553300; color: #ffaa44; padding: 1px 5px; border-radius: 3px; font-size: 9px; font-weight: bold;";
        leftGroup.appendChild(typeBadge);
    }

    const nameSpan = document.createElement("span");
    nameSpan.className = "cb-header-name";
    nameSpan.textContent = getShortName(modelPath);
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

    // Content Container
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "flex";
    contentDiv.style.flexDirection = "column";
    contentDiv.style.gap = "6px";
    contentDiv.style.width = "100%";

    header.onclick = (e) => {
        if (e.target.tagName === 'BUTTON') return;
        const isNowCollapsed = contentDiv.style.display !== "none";
        contentDiv.style.display = isNowCollapsed ? "none" : "flex";
        toggleArrow.textContent = isNowCollapsed ? "▶" : "▼";
        node.uiState.modelsCollapsed[uid] = isNowCollapsed;
    };

    // Model Type Select (Checkpoint / Diffusion Model / GGUF)
    const modelTypeSelect = document.createElement("select");
    modelTypeSelect.className = "cb-select";
    modelTypeSelect.innerHTML = `
        <option value="checkpoint" ${modelType === 'checkpoint' ? 'selected' : ''}>Checkpoint</option>
        <option value="diffusion_model" ${modelType === 'diffusion_model' ? 'selected' : ''}>Diffusion Model</option>
        <option value="gguf" ${modelType === 'gguf' ? 'selected' : ''}>GGUF</option>
    `;
    modelTypeSelect.onchange = () => {
        const newType = modelTypeSelect.value;
        node.state.config_arrays[arrayIdx].models[modelIdx] = newType === "checkpoint"
            ? "None"
            : { path: "None", type: newType };
        node.saveState();
        node.renderUI();
    };
    contentDiv.appendChild(modelTypeSelect);

    // File/Folder Type Select
    const typeSelect = document.createElement("select");
    typeSelect.className = "cb-select";
    const fileLabel = modelType === "gguf" ? "GGUF File" : modelType === "diffusion_model" ? "Diffusion File" : "Checkpoint File";
    typeSelect.innerHTML = `
        <option value="file" ${!isFolder ? 'selected' : ''}>${fileLabel}</option>
        <option value="folder" ${isFolder ? 'selected' : ''}>Folder</option>
    `;
    typeSelect.onchange = () => {
        const newVal = typeSelect.value === "folder" ? "/" : "None";
        if (modelType === "checkpoint") {
            node.state.config_arrays[arrayIdx].models[modelIdx] = newVal;
        } else {
            node.state.config_arrays[arrayIdx].models[modelIdx] = { path: newVal, type: modelType };
        }
        node.saveState();
        node.renderUI();
    };
    contentDiv.appendChild(typeSelect);

    // Pick the correct file list and folder list based on model type
    let fileOptions, folderOptions;
    if (modelType === 'gguf') {
        fileOptions = modelLists.ggufModels || [];
        folderOptions = modelLists.ggufFolders || ["/"];
    } else if (modelType === 'diffusion_model') {
        fileOptions = modelLists.diffusionModels || [];
        folderOptions = modelLists.diffusionFolders || ["/"];
    } else {
        fileOptions = modelLists.checkpoints || [];
        folderOptions = modelLists.checkpointFolders || ["/"];
    }

    // Searchable Select
    const options = isFolder ? folderOptions : fileOptions;
    const currentVal = modelPath;
    const optionsList = (options && options.includes(currentVal)) || currentVal === "None" || currentVal === "/"
        ? options || ["None"]
        : [currentVal, ...(options || ["None"])];

    const nameSearchable = createSearchableSelect(
        optionsList,
        currentVal,
        (value) => {
            const normalized = normalizePath(value);
            if (modelType === "checkpoint") {
                node.state.config_arrays[arrayIdx].models[modelIdx] = normalized;
            } else {
                node.state.config_arrays[arrayIdx].models[modelIdx] = { path: normalized, type: modelType };
            }
            node.saveState();
            node.renderUI();
        },
        isFolder ? "Search folders..." : "Search models..."
    );
    contentDiv.appendChild(nameSearchable);

    // Folder expand button
    if (isFolder && modelPath !== "None" && modelPath !== "/") {
        const expandBtn = document.createElement("button");
        expandBtn.className = "cb-button";
        expandBtn.style.borderLeft = "3px solid #cc6600";
        expandBtn.style.width = "100%";
        expandBtn.style.fontSize = "11px";
        expandBtn.style.marginTop = "4px";
        expandBtn.textContent = "📂 Add all individually";
        expandBtn.onclick = () => {
            const normalize = (str) => str.replace(/\\/g, "/");
            const folderPrefix = normalize(modelPath);
            const matchingModels = fileOptions ? fileOptions.filter(m => normalize(m).startsWith(folderPrefix)) : [];
            if (matchingModels.length > 0) {
                const expanded = matchingModels.map(m => modelType === "checkpoint" ? m : { path: m, type: modelType });
                node.state.config_arrays[arrayIdx].models.splice(modelIdx, 1, ...expanded);
                node.saveState();
                node.renderUI();
            } else {
                alert(`No models found in folder: ${folderPrefix}`);
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

    // Initialize state objects if they don't exist
    if (!node.state.config_arrays[arrayIdx].lora_bypass_states) {
        node.state.config_arrays[arrayIdx].lora_bypass_states = {};
    }
    if (!node.state.config_arrays[arrayIdx].lora_strength_lock) {
        node.state.config_arrays[arrayIdx].lora_strength_lock = {};
    }

    // Get bypass state
    const isBypassed = node.state.config_arrays[arrayIdx].lora_bypass_states[parsed.name] || false;

    // Get strength lock state (default to true - locked by default)
    const isStrengthLocked = node.state.config_arrays[arrayIdx].lora_strength_lock[parsed.name] !== false;

    // Header with bypass toggle
    const header = document.createElement("div");
    header.className = "cb-header-bar";

    const leftGroup = document.createElement("div");
    leftGroup.className = "cb-header-left";

    // Bypass Checkbox (in header, before toggle arrow)
    const bypassLabel = document.createElement("label");
    bypassLabel.style.cssText = "display: flex; align-items: center; gap: 4px; cursor: pointer; margin-right: 8px;";
    bypassLabel.title = "Bypass (disable) this LoRA";

    const bypassCheck = document.createElement("input");
    bypassCheck.type = "checkbox";
    bypassCheck.checked = !isBypassed; // Inverted: checked = enabled
    bypassCheck.style.cssText = "cursor: pointer;";
    bypassCheck.onclick = (e) => {
        e.stopPropagation(); // Prevent header collapse
        const newBypassState = !bypassCheck.checked;
        node.state.config_arrays[arrayIdx].lora_bypass_states[parsed.name] = newBypassState;
        node.saveState();
        // Visual feedback
        div.style.opacity = newBypassState ? "0.5" : "1.0";
        div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
    };

    bypassLabel.appendChild(bypassCheck);
    const bypassText = document.createElement("span");
    bypassText.textContent = "On";
    bypassText.style.cssText = "font-size: 11px; color: #0cc;";
    bypassLabel.appendChild(bypassText);
    leftGroup.appendChild(bypassLabel);

    const toggleArrow = document.createElement("span");
    toggleArrow.textContent = isCollapsed ? "▶" : "▼";
    toggleArrow.style.cssText = "margin-right: 6px;";
    leftGroup.appendChild(toggleArrow);

    const label = document.createElement("span");
    label.style.color = "#0066cc";
    label.style.fontSize = "10px";
    label.style.marginRight = "6px";
    label.textContent = "LoRA:";
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

    // Apply bypass visual state
    if (isBypassed) {
        div.style.opacity = "0.5";
        div.style.filter = "grayscale(0.7)";
    }

    // Content
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "flex";
    contentDiv.style.flexDirection = "column";
    contentDiv.style.gap = "6px";
    contentDiv.style.width = "100%";

    // --- TOGGLE LOGIC (INSTANT) ---
    header.onclick = (e) => {
        if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;

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

        // If strength is locked, update both sliders
        if (isStrengthLocked) {
            currentClipStr = val;
        }

        node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, currentModelStr, currentClipStr);
        node.saveState();

        // Update CLIP slider if locked
        if (isStrengthLocked && clipSliderContainer) {
            const clipSliderInput = clipSliderContainer.querySelector('input[type="range"]');
            const clipNumberInput = clipSliderContainer.querySelector('input[type="number"]');
            if (clipSliderInput) clipSliderInput.value = val;
            if (clipNumberInput) clipNumberInput.value = val;
        }
    });
    contentDiv.appendChild(modelSlider);

    // CLIP Slider - conditionally visible based on lock state
    let clipSliderContainer = null;
    if (!isStrengthLocked) {
        clipSliderContainer = createSlider("CLIP Strength", currentClipStr, 0, 2, 0.05, (val) => {
            currentClipStr = val;
            const currentName = isCombined ? cleanName + "*" : parsed.name;
            node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, currentModelStr, currentClipStr);
            node.saveState();
        });
        contentDiv.appendChild(clipSliderContainer);
    }

    // --- COLLAPSIBLE "MORE LORA OPTIONS" SECTION ---
    if (parsed.name !== "None") {
        const moreOptionsUid = `${uid}-moreoptions`;
        const isMoreOptionsCollapsed = node.uiState.lorasCollapsed[moreOptionsUid] !== false; // Default collapsed

        const moreOptionsSection = document.createElement("div");
        moreOptionsSection.style.cssText = `background: #252525; border-radius: 4px; padding: 8px; margin-top: 6px; border-left: 3px solid #9966cc;`;

        const moreOptionsHeader = document.createElement("div");
        moreOptionsHeader.style.cssText = "display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none;";

        const moreOptionsTitle = document.createElement("div");
        moreOptionsTitle.textContent = "⚙️ More LoRA Options";
        moreOptionsTitle.style.cssText = "font-size: 11px; font-weight: bold; color: #9966cc;";

        const moreOptionsArrow = document.createElement("span");
        moreOptionsArrow.textContent = isMoreOptionsCollapsed ? "▶" : "▼";
        moreOptionsArrow.style.cssText = "font-size: 10px; color: #9966cc;";

        moreOptionsHeader.appendChild(moreOptionsTitle);
        moreOptionsHeader.appendChild(moreOptionsArrow);
        moreOptionsSection.appendChild(moreOptionsHeader);

        const moreOptionsContent = document.createElement("div");
        moreOptionsContent.style.display = isMoreOptionsCollapsed ? "none" : "flex";
        moreOptionsContent.style.flexDirection = "column";
        moreOptionsContent.style.gap = "8px";
        moreOptionsContent.style.marginTop = "8px";

        // Toggle handler
        moreOptionsHeader.onclick = () => {
            const isNowCollapsed = moreOptionsContent.style.display !== "none";
            moreOptionsContent.style.display = isNowCollapsed ? "none" : "flex";
            moreOptionsArrow.textContent = isNowCollapsed ? "▶" : "▼";
            node.uiState.lorasCollapsed[moreOptionsUid] = isNowCollapsed;
        };

        // 1. Strength Lock Checkbox
        const strengthLockLabel = document.createElement("label");
        strengthLockLabel.style.cssText = "display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer;";

        const strengthLockCheck = document.createElement("input");
        strengthLockCheck.type = "checkbox";
        strengthLockCheck.checked = isStrengthLocked;
        strengthLockCheck.onchange = () => {
            node.state.config_arrays[arrayIdx].lora_strength_lock[parsed.name] = strengthLockCheck.checked;

            // If locking, sync CLIP to Model strength
            if (strengthLockCheck.checked) {
                currentClipStr = currentModelStr;
                const currentName = isCombined ? cleanName + "*" : parsed.name;
                node.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, currentModelStr, currentClipStr);
            }

            node.saveState();
            node.renderUI(); // Re-render to show/hide CLIP slider
        };

        strengthLockLabel.appendChild(strengthLockCheck);
        strengthLockLabel.appendChild(document.createTextNode("🔒 Lock Model & CLIP Strength Together"));
        moreOptionsContent.appendChild(strengthLockLabel);

        // 2. Auto Append Trigger Words Section
        const triggerSubSection = document.createElement("div");
        triggerSubSection.style.cssText = `background: #2a2a2a; border-radius: 4px; padding: 8px; border-left: 3px solid #00aa88;`;

        const triggerTitle = document.createElement("div");
        triggerTitle.textContent = "🏷️ Auto Append LoRA Trigger Words To:";
        triggerTitle.style.cssText = "font-size: 11px; font-weight: bold; color: #00aa88; margin-bottom: 6px;";
        triggerSubSection.appendChild(triggerTitle);

        if (!node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings) {
            node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings = {};
        }
        const currentPlacement = node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings[parsed.name] || "none";

        const checkboxContainer = document.createElement("div");
        checkboxContainer.style.cssText = "display: flex; gap: 12px; align-items: center; flex-wrap: wrap;";

        const createCheck = (lbl, val) => {
            const label = document.createElement("label");
            label.style.cssText = "display: flex; align-items: center; gap: 4px; font-size: 12px; cursor: pointer;";
            const check = document.createElement("input");
            check.type = "checkbox";
            check.checked = currentPlacement === val;
            check.onchange = async () => {
                // Special handling for "dont_append"
                if (val === "dont_append" && check.checked) {
                    // Fetch triggers and add them to omit list
                    const triggers = await fetchLoraTriggersForOmit(node, arrayIdx, parsed.name);
                    if (triggers && triggers.length > 0) {
                        if (!node.state.config_arrays[arrayIdx].lora_omit_triggers) {
                            node.state.config_arrays[arrayIdx].lora_omit_triggers = [];
                        }
                        triggers.forEach(trigger => {
                            if (!node.state.config_arrays[arrayIdx].lora_omit_triggers.includes(trigger)) {
                                node.state.config_arrays[arrayIdx].lora_omit_triggers.push(trigger);
                            }
                        });
                    }
                }

                node.state.config_arrays[arrayIdx].lora_triggerwords_append_settings[parsed.name] = check.checked ? val : "none";
                node.saveState();

                // Manually uncheck the others
                if (check.checked) {
                    const other = checkboxContainer.querySelectorAll('input');
                    other.forEach(i => { if (i !== check) i.checked = false; });
                }
            };
            label.appendChild(check);
            label.appendChild(document.createTextNode(lbl));
            return label;
        };

        checkboxContainer.appendChild(createCheck("Start", "start"));
        checkboxContainer.appendChild(createCheck("End", "end"));
        checkboxContainer.appendChild(createCheck("Don't Append", "dont_append"));

        triggerSubSection.appendChild(checkboxContainer);

        // Info text for Don't Append
        const dontAppendInfo = document.createElement("div");
        dontAppendInfo.style.cssText = "font-size: 10px; color: #888; font-style: italic; margin-top: 4px;";
        dontAppendInfo.textContent = "ℹ️ 'Don't Append' adds all trigger words to the omit list";
        triggerSubSection.appendChild(dontAppendInfo);

        moreOptionsContent.appendChild(triggerSubSection);

        // 3. LoRA Metadata Lookup Button
        const metadataBtn = document.createElement("button");
        metadataBtn.className = "cb-button";
        metadataBtn.style.cssText = `width: 100%; background: linear-gradient(135deg, #cc6699, #9966cc); border-left: 4px solid #ff66cc; margin-top: 4px;`;
        metadataBtn.textContent = "🔍 Lookup LoRA Metadata from CivitAI";
        metadataBtn.onclick = async () => await showLoraMetadataModal(node, arrayIdx, parsed.name);
        moreOptionsContent.appendChild(metadataBtn);

        moreOptionsSection.appendChild(moreOptionsContent);
        contentDiv.appendChild(moreOptionsSection);
    }

    // Folder expand button (outside More Options)
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

// Helper function to fetch triggers for "Don't Append" option
async function fetchLoraTriggersForOmit(node, arrayIdx, loraName) {
    try {
        const resp = await fetch("/configbuilder/lookup_triggers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ loras: [loraName] })
        });

        if (resp.ok) {
            const data = await resp.json();
            return data.triggers[loraName] || [];
        }
    } catch (e) {
        console.error("[ConfigBuilder] Error fetching triggers for omit:", e);
    }
    return [];
}

// New modal for LoRA metadata lookup
async function showLoraMetadataModal(node, arrayIdx, loraName) {
    const overlay = document.createElement("div");
    overlay.style.cssText = `position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.85); display: flex; align-items: center; justify-content: center; z-index: 10000;`;

    const modal = document.createElement("div");
    // Red X close button in top right
    modal.classList.add("cb-modal-popup");
    const closeX = document.createElement("button");
    closeX.textContent = "✖";
    closeX.style.cssText = "position: absolute; top: 10px; right: 10px; background: #cc3333; color: white; border: none; border-radius: 4px; width: 28px; height: 28px; font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center; z-index: 1;";
    closeX.onmouseover = () => closeX.style.background = "#dd4444";
    closeX.onmouseout = () => closeX.style.background = "#cc3333";
    closeX.onclick = () => document.body.removeChild(overlay);
    modal.appendChild(closeX);

    const title = document.createElement("h3");
    title.textContent = "🔍 LoRA Metadata Lookup";
    title.style.cssText = "margin: 0 0 15px 0; color: #9966cc;";
    modal.appendChild(title);

    const status = document.createElement("div");
    status.textContent = `🔄 Fetching metadata for: ${loraName.split('/').pop()}`;
    status.style.cssText = "margin-bottom: 15px; color: #aaa;";
    modal.appendChild(status);

    const content = document.createElement("div");
    modal.appendChild(content);

    const closeBtn = document.createElement("button");
    closeBtn.className = "cb-button";
    closeBtn.textContent = "Close";
    closeBtn.style.marginTop = "15px";
    closeBtn.onclick = () => document.body.removeChild(overlay);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Fetch metadata
    try {
        const resp = await fetch("/configbuilder/lookup_lora_metadata", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lora_name: loraName })
        });

        if (!resp.ok) {
            const errorData = await resp.json();
            status.textContent = "❌ Error: " + (errorData.error || "Failed to fetch metadata");
            status.style.color = "#ff6666";
            modal.appendChild(closeBtn);
            return;
        }

        const data = await resp.json();
        const metadata = data.metadata;

        status.textContent = "✅ Metadata loaded successfully!";
        status.style.color = "#66ff66";

        // Display metadata
        content.innerHTML = "";

        // Model name and creator
        const headerSection = document.createElement("div");
        headerSection.style.cssText = "margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #444;";
        headerSection.innerHTML = `
            <div style="font-size: 18px; font-weight: bold; color: #ff66cc; margin-bottom: 5px;">${metadata.model_name}</div>
            <div style="font-size: 14px; color: #aaa;">Version: ${metadata.name}</div>
            <div style="font-size: 12px; color: #888;">Creator: ${metadata.creator}</div>
            <div style="font-size: 11px; color: #666; margin-top: 5px;">
                Hash: <code style="background: #1a1a1a; padding: 2px 6px; border-radius: 3px;">${metadata.short_hash}</code>
            </div>
        `;
        content.appendChild(headerSection);

        // Base Model and Tags
        const infoSection = document.createElement("div");
        infoSection.style.cssText = "margin-bottom: 15px;";
        infoSection.innerHTML = `
            <div style="margin-bottom: 8px;"><strong style="color: #9966cc;">Base Model:</strong> ${metadata.base_model}</div>
            <div style="margin-bottom: 8px;">
                <strong style="color: #9966cc;">Tags:</strong> 
                <div style="margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px;">
                    ${metadata.tags.slice(0, 10).map(tag => `<span style="background: #444; padding: 2px 8px; border-radius: 10px; font-size: 11px;">${tag}</span>`).join('')}
                </div>
            </div>
        `;
        content.appendChild(infoSection);

        // Trigger Words
        if (metadata.trained_words && metadata.trained_words.length > 0) {
            const triggerSection = document.createElement("div");
            triggerSection.style.cssText = "margin-bottom: 15px; background: #252525; padding: 10px; border-radius: 4px; border-left: 3px solid #00aa88;";
            triggerSection.innerHTML = `
                <div style="font-weight: bold; color: #00aa88; margin-bottom: 6px;">🏷️ Trigger Words:</div>
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                    ${metadata.trained_words.map(word => `<span style="background: #333; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-family: monospace;">${word}</span>`).join('')}
                </div>
            `;
            content.appendChild(triggerSection);
        }

        // Images
        if (metadata.images && metadata.images.length > 0) {
            const imagesSection = document.createElement("div");
            imagesSection.style.cssText = "margin-bottom: 15px;";
            imagesSection.innerHTML = `<div style="font-weight: bold; color: #9966cc; margin-bottom: 8px;">📸 Example Images:</div>`;

            const imageGrid = document.createElement("div");
            imageGrid.style.cssText = "display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px;";

            metadata.images.forEach(img => {
                const imgContainer = document.createElement("div");
                imgContainer.style.cssText = "position: relative; aspect-ratio: 1; overflow: hidden; border-radius: 4px; border: 1px solid #444; cursor: pointer;";
                imgContainer.title = "Click to open full size";

                const imgElem = document.createElement("img");
                imgElem.src = img.url;
                imgElem.style.cssText = "width: 100%; height: 100%; object-fit: cover;";
                imgElem.onclick = () => window.open(img.url, '_blank');

                imgContainer.appendChild(imgElem);
                imageGrid.appendChild(imgContainer);
            });

            imagesSection.appendChild(imageGrid);
            content.appendChild(imagesSection);
        }

        // Links
        const linksSection = document.createElement("div");
        linksSection.style.cssText = "margin-top: 15px; padding-top: 10px; border-top: 2px solid #444;";

        const civitaiLink = document.createElement("a");
        civitaiLink.href = metadata.url;
        civitaiLink.target = "_blank";
        civitaiLink.textContent = "🌐 View on CivitAI";
        civitaiLink.style.cssText = "display: inline-block; background: #0066cc; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; margin-right: 10px;";

        const savedPath = document.createElement("div");
        savedPath.style.cssText = "margin-top: 8px; font-size: 11px; color: #666;";
        savedPath.textContent = `💾 Metadata saved to: ${data.saved_to}`;

        linksSection.appendChild(civitaiLink);
        linksSection.appendChild(savedPath);
        content.appendChild(linksSection);

    } catch (e) {
        status.textContent = "❌ Error: " + e.message;
        status.style.color = "#ff6666";
        console.error("[ConfigBuilder] Metadata lookup error:", e);
    }

    modal.appendChild(closeBtn);
}



// --- RENDER MODELS AND LORAS SECTIONS ---

export function renderModelsSection(node, div, configArray, arrayIdx, modelLists) {
    if (!configArray.models || configArray.models.length === 0) configArray.models = ["None"];

    const isSectionCollapsed = node.uiState.modelsSectionCollapsed[arrayIdx] || false;

    const modelGrid = document.createElement("div");
    modelGrid.className = "cb-list-grid";

    const modelHeader = document.createElement("div");
    modelHeader.className = "cb-section-toggle";
    modelHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #cc6600;";

    // Count total models (handle both string and object format)
    let totalModels = 0;
    configArray.models.forEach(m => {
        const mPath = typeof m === 'string' ? m : (m?.path || "None");
        const mType = typeof m === 'string' ? 'checkpoint' : (m?.type || 'checkpoint');
        let list;
        if (mType === 'gguf') list = modelLists.ggufModels;
        else if (mType === 'diffusion_model') list = modelLists.diffusionModels;
        else list = modelLists.checkpoints;

        if (mPath === "None") totalModels++;
        else if (mPath.endsWith("/")) {
            const norm = normalizePath(mPath);
            if (norm === "/") totalModels += list ? list.length : 1;
            else totalModels += list ? list.filter(am => normalizePath(am).startsWith(norm)).length : 1;
        } else totalModels++;
    });

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `Models (${configArray.models.length} Entries, Totaling ${totalModels} Models)`;
    modelHeader.appendChild(titleSpan);

    const arrowSpan = document.createElement("span");
    arrowSpan.textContent = isSectionCollapsed ? "▶" : "▼";
    modelHeader.appendChild(arrowSpan);

    modelGrid.appendChild(modelHeader);

    const contentContainer = document.createElement("div");
    contentContainer.style.display = isSectionCollapsed ? "none" : "contents";

    modelHeader.onclick = () => {
        const isNowCollapsed = contentContainer.style.display === "none";
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

    configArray.models.forEach((model, modelIdx) => {
        contentContainer.appendChild(createModelElement(node, model, arrayIdx, modelIdx, modelLists));
    });

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

    // --- TEXT ENCODERS SECTION (shown when any model is non-checkpoint) ---
    const hasNonCheckpoint = configArray.models.some(m =>
        typeof m === 'object' && m !== null && m.type && m.type !== 'checkpoint'
    );

    if (hasNonCheckpoint) {
        renderTextEncodersSection(node, contentContainer, configArray, arrayIdx, modelLists);
    }

    // --- GGUF OPTIONS SECTION (shown when any model is GGUF) ---
    const hasGGUF = configArray.models.some(m =>
        typeof m === 'object' && m !== null && m.type === 'gguf'
    );

    if (hasGGUF) {
        renderGGUFOptionsSection(node, contentContainer, configArray, arrayIdx);
    }

    modelGrid.appendChild(contentContainer);
    div.appendChild(modelGrid);
}

// --- TEXT ENCODERS SECTION ---
function renderTextEncodersSection(node, container, configArray, arrayIdx, modelLists) {
    const section = document.createElement("div");
    section.style.cssText = "width: 100%; border-top: 1px solid #444; margin-top: 8px; padding-top: 8px;";

    const header = document.createElement("div");
    header.style.cssText = "font-size: 11px; font-weight: bold; color: #44aaff; margin-bottom: 6px;";
    header.textContent = "TEXT ENCODERS (CLIP)";
    section.appendChild(header);

    // Clip Type selector
    const clipRow = document.createElement("div");
    clipRow.style.cssText = "display: flex; gap: 6px; align-items: center; margin-bottom: 6px;";
    const clipLabel = document.createElement("label");
    clipLabel.textContent = "CLIP Type:";
    clipLabel.style.cssText = "color: #aaa; font-size: 11px; white-space: nowrap;";
    clipRow.appendChild(clipLabel);

    const clipSelect = document.createElement("select");
    clipSelect.className = "cb-select";
    // Combine single and dual clip types
    const allClipTypes = [...new Set([...(modelLists.clipTypes || []), ...(modelLists.dualClipTypes || [])])];
    allClipTypes.forEach(ct => {
        const opt = document.createElement("option");
        opt.value = ct;
        opt.textContent = ct;
        if (ct === (configArray.clip_type || "stable_diffusion")) opt.selected = true;
        clipSelect.appendChild(opt);
    });
    clipSelect.onchange = () => {
        node.state.config_arrays[arrayIdx].clip_type = clipSelect.value;
        node.saveState();
    };
    clipRow.appendChild(clipSelect);
    section.appendChild(clipRow);

    // Text encoder entries
    const teList = configArray.text_encoders || [];
    teList.forEach((te, teIdx) => {
        const teRow = document.createElement("div");
        teRow.style.cssText = "display: flex; gap: 4px; align-items: center; margin-bottom: 4px;";

        const teSearchable = createSearchableSelect(
            modelLists.textEncoders || ["None"],
            te || "None",
            (value) => {
                node.state.config_arrays[arrayIdx].text_encoders[teIdx] = normalizePath(value);
                node.saveState();
            },
            "Search text encoders..."
        );
        teSearchable.style.flex = "1";
        teRow.appendChild(teSearchable);

        const delBtn = document.createElement("button");
        delBtn.className = "cb-button danger";
        delBtn.style.cssText = "padding: 2px 6px; font-size: 10px;";
        delBtn.textContent = "✖";
        delBtn.onclick = () => {
            node.state.config_arrays[arrayIdx].text_encoders.splice(teIdx, 1);
            node.saveState();
            node.renderUI();
        };
        teRow.appendChild(delBtn);
        section.appendChild(teRow);
    });

    // Add text encoder button
    const addTeBtn = document.createElement("button");
    addTeBtn.className = "cb-button";
    addTeBtn.style.cssText = "width: 100%; border: 1px dashed #446; background: rgba(0,50,100,0.2); color: #88bbff; font-size: 11px;";
    addTeBtn.textContent = "+ Add Text Encoder";
    addTeBtn.onclick = () => {
        if (!node.state.config_arrays[arrayIdx].text_encoders) {
            node.state.config_arrays[arrayIdx].text_encoders = [];
        }
        node.state.config_arrays[arrayIdx].text_encoders.push("None");
        node.saveState();
        node.renderUI();
    };
    section.appendChild(addTeBtn);

    container.appendChild(section);
}

// --- GGUF OPTIONS SECTION ---
function renderGGUFOptionsSection(node, container, configArray, arrayIdx) {
    const section = document.createElement("details");
    section.style.cssText = "width: 100%; border-top: 1px solid #444; margin-top: 8px; padding-top: 8px;";

    const summary = document.createElement("summary");
    summary.textContent = "GGUF Options";
    summary.style.cssText = "cursor: pointer; color: #aaa; font-size: 11px; font-weight: bold;";
    section.appendChild(summary);

    const opts = configArray.gguf_options || {};
    const grid = document.createElement("div");
    grid.style.cssText = "display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 6px;";

    // Helper for select rows
    const addSelectRow = (label, options, currentVal, onChange) => {
        const lbl = document.createElement("label");
        lbl.textContent = label;
        lbl.style.cssText = "color: #aaa; font-size: 11px; display: flex; align-items: center;";
        grid.appendChild(lbl);

        const sel = document.createElement("select");
        sel.className = "cb-select";
        options.forEach(o => {
            const opt = document.createElement("option");
            opt.value = o;
            opt.textContent = o;
            if (o === currentVal) opt.selected = true;
            sel.appendChild(opt);
        });
        sel.onchange = () => onChange(sel.value);
        grid.appendChild(sel);
    };

    const dtypeOptions = ["default", "target", "float32", "float16", "bfloat16"];

    addSelectRow("Dequant dtype:", dtypeOptions, opts.dequant_dtype || "default", (val) => {
        if (!node.state.config_arrays[arrayIdx].gguf_options) node.state.config_arrays[arrayIdx].gguf_options = {};
        node.state.config_arrays[arrayIdx].gguf_options.dequant_dtype = val;
        node.saveState();
    });

    addSelectRow("Patch dtype:", dtypeOptions, opts.patch_dtype || "default", (val) => {
        if (!node.state.config_arrays[arrayIdx].gguf_options) node.state.config_arrays[arrayIdx].gguf_options = {};
        node.state.config_arrays[arrayIdx].gguf_options.patch_dtype = val;
        node.saveState();
    });

    // Patch on device checkbox
    const podLabel = document.createElement("label");
    podLabel.textContent = "Patch on device:";
    podLabel.style.cssText = "color: #aaa; font-size: 11px; display: flex; align-items: center;";
    grid.appendChild(podLabel);

    const podCheck = document.createElement("input");
    podCheck.type = "checkbox";
    podCheck.checked = opts.patch_on_device || false;
    podCheck.onchange = () => {
        if (!node.state.config_arrays[arrayIdx].gguf_options) node.state.config_arrays[arrayIdx].gguf_options = {};
        node.state.config_arrays[arrayIdx].gguf_options.patch_on_device = podCheck.checked;
        node.saveState();
    };
    grid.appendChild(podCheck);

    section.appendChild(grid);
    container.appendChild(section);
}

// --- VAE SECTION RENDERER ---

export function renderVAEsSection(node, div, configArray, arrayIdx) {
    if (!configArray.vaes || configArray.vaes.length === 0) return; // Don't show section if no VAEs added

    // Filter out "only None" case — if vaes is ["None"], don't show section unless explicitly added
    const hasRealVAEs = configArray.vaes.some(v => v && v !== "None");
    if (!hasRealVAEs && configArray.vaes.length <= 1) return;

    const vaeList = getAvailableVAEs();
    const vFolders = getVAEFolders();

    const isSectionCollapsed = node.uiState.vaesSectionCollapsed?.[arrayIdx] || false;

    const vaeGrid = document.createElement("div");
    vaeGrid.className = "cb-list-grid";

    const vaeHeader = document.createElement("div");
    vaeHeader.className = "cb-section-toggle";
    vaeHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #9900cc;";

    const activeVaes = configArray.vaes.filter(v => v && v !== "None").length;
    const titleSpan = document.createElement("span");
    titleSpan.textContent = `VAEs (${configArray.vaes.length} Entries, ${activeVaes} Active)`;
    vaeHeader.appendChild(titleSpan);

    const arrowSpan = document.createElement("span");
    arrowSpan.textContent = isSectionCollapsed ? "▶" : "▼";
    vaeHeader.appendChild(arrowSpan);

    vaeGrid.appendChild(vaeHeader);

    const contentContainer = document.createElement("div");
    contentContainer.style.display = isSectionCollapsed ? "none" : "contents";

    vaeHeader.onclick = () => {
        const isNowCollapsed = contentContainer.style.display === "none";
        if (isNowCollapsed) {
            contentContainer.style.display = "contents";
            arrowSpan.textContent = "▼";
            if (!node.uiState.vaesSectionCollapsed) node.uiState.vaesSectionCollapsed = {};
            node.uiState.vaesSectionCollapsed[arrayIdx] = false;
        } else {
            contentContainer.style.display = "none";
            arrowSpan.textContent = "▶";
            if (!node.uiState.vaesSectionCollapsed) node.uiState.vaesSectionCollapsed = {};
            node.uiState.vaesSectionCollapsed[arrayIdx] = true;
        }
    };

    configArray.vaes.forEach((vae, vaeIdx) => {
        contentContainer.appendChild(createVAEElement(node, vae, arrayIdx, vaeIdx, vaeList, vFolders));
    });

    const addRow = document.createElement("div");
    addRow.style.width = "100%";
    addRow.style.padding = "4px 0";
    const addBtn = document.createElement("button");
    addBtn.className = "cb-button";
    addBtn.style.cssText = "width: 100%; border: 1px dashed #555; background: rgba(0,0,0,0.2); color: #aaa;";
    addBtn.textContent = "➕ Add New VAE";
    addBtn.onmouseover = () => addBtn.style.background = "rgba(255,255,255,0.1)";
    addBtn.onmouseout = () => addBtn.style.background = "rgba(0,0,0,0.2)";
    addBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].vaes.push("None");
        node.saveState();
        node.renderUI();
    };
    addRow.appendChild(addBtn);
    contentContainer.appendChild(addRow);

    vaeGrid.appendChild(contentContainer);
    div.appendChild(vaeGrid);
}

// --- VAE ELEMENT CREATOR ---

function createVAEElement(node, vaeName, arrayIdx, vaeIdx, vaeList, vFolders) {
    const isFolder = vaeName && vaeName.endsWith("/");

    const div = document.createElement("div");
    div.className = "cb-item-card";
    div.style.borderLeft = "3px solid #9900cc";
    const uid = `vae_${arrayIdx}_${vaeIdx}`;

    const isCollapsed = node.uiState.vaesCollapsed?.[uid] || false;

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
    label.textContent = `VAE #${vaeIdx + 1}`;
    label.style.color = "#9900cc";
    label.style.fontSize = "10px";
    label.style.marginRight = "6px";
    leftGroup.appendChild(label);

    const nameSpan = document.createElement("span");
    nameSpan.className = "cb-header-name";
    nameSpan.textContent = getShortName(vaeName || "None");
    leftGroup.appendChild(nameSpan);

    header.appendChild(leftGroup);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "cb-button danger";
    deleteBtn.style.padding = "2px 6px";
    deleteBtn.style.fontSize = "10px";
    deleteBtn.textContent = "✖";
    deleteBtn.onclick = () => {
        node.state.config_arrays[arrayIdx].vaes.splice(vaeIdx, 1);
        if (node.state.config_arrays[arrayIdx].vaes.length === 0) {
            node.state.config_arrays[arrayIdx].vaes = ["None"];
        }
        node.saveState();
        node.renderUI();
    };
    header.appendChild(deleteBtn);
    div.appendChild(header);

    // Content container
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "flex";
    contentDiv.style.flexDirection = "column";
    contentDiv.style.gap = "6px";
    contentDiv.style.width = "100%";

    header.onclick = (e) => {
        if (e.target.tagName === 'BUTTON') return;
        const isNowCollapsed = contentDiv.style.display !== "none";
        contentDiv.style.display = isNowCollapsed ? "none" : "flex";
        toggleArrow.textContent = isNowCollapsed ? "▶" : "▼";
        if (!node.uiState.vaesCollapsed) node.uiState.vaesCollapsed = {};
        node.uiState.vaesCollapsed[uid] = isNowCollapsed;
    };

    // File/Folder Type Select
    const typeSelect = document.createElement("select");
    typeSelect.className = "cb-select";
    typeSelect.innerHTML = `
        <option value="file" ${!isFolder ? 'selected' : ''}>VAE File</option>
        <option value="folder" ${isFolder ? 'selected' : ''}>Folder</option>
    `;
    typeSelect.onchange = () => {
        const newVal = typeSelect.value === "folder" ? "/" : "None";
        node.state.config_arrays[arrayIdx].vaes[vaeIdx] = newVal;
        node.saveState();
        node.renderUI();
    };
    contentDiv.appendChild(typeSelect);

    // Searchable Select for VAE
    const options = isFolder ? vFolders : vaeList;
    const currentVal = vaeName || "None";
    const optionsList = (options && options.includes(currentVal)) || currentVal === "None" || currentVal === "/"
        ? options || ["None"]
        : [currentVal, ...(options || ["None"])];

    const nameSearchable = createSearchableSelect(
        optionsList,
        currentVal,
        (value) => {
            node.state.config_arrays[arrayIdx].vaes[vaeIdx] = normalizePath(value);
            node.saveState();
            node.renderUI();
        },
        isFolder ? "Search folders..." : "Search VAEs..."
    );
    contentDiv.appendChild(nameSearchable);

    // Folder expand button
    if (isFolder && vaeName !== "None" && vaeName !== "/") {
        const expandBtn = document.createElement("button");
        expandBtn.className = "cb-button";
        expandBtn.style.cssText = "width: 100%; border-left: 3px solid #9900cc; font-size: 11px; margin-top: 4px;";
        expandBtn.textContent = "📂 Add all individually";
        expandBtn.onclick = () => {
            const normalize = (str) => str.replace(/\\/g, "/");
            const folderPrefix = normalize(vaeName);
            const matchingVAEs = vaeList ? vaeList.filter(v => normalize(v).startsWith(folderPrefix)) : [];
            if (matchingVAEs.length > 0) {
                node.state.config_arrays[arrayIdx].vaes.splice(vaeIdx, 1, ...matchingVAEs);
                node.saveState();
                node.renderUI();
            } else {
                alert(`No VAEs found in folder: ${folderPrefix}`);
            }
        };
        contentDiv.appendChild(expandBtn);
    }

    div.appendChild(contentDiv);
    return div;
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

    // Warning element for when omits are set but no trigger append settings exist
    const warningEl = document.createElement("div");
    warningEl.style.cssText = "display: none; background: #3d2e00; border: 1px solid #cc6600; border-radius: 4px; padding: 6px 10px; margin-bottom: 8px; font-size: 11px; color: #ffaa00;";
    warningEl.textContent = "⚠️ Omit list is active, but no LoRAs have trigger word append settings configured. Make sure the Sampler node's \"lora_triggerwords_mode\" is not set to \"None\", or omits will have no effect.";
    omitSection.appendChild(warningEl);

    const updateOmitWarning = () => {
        const hasOmits = configArray.lora_omit_triggers && configArray.lora_omit_triggers.length > 0;
        const appendSettings = configArray.lora_triggerwords_append_settings || {};
        const hasAppendSettings = Object.values(appendSettings).some(v => v === "start" || v === "end");
        // Show warning if omits exist but no per-lora append settings are configured
        warningEl.style.display = (hasOmits && !hasAppendSettings) ? "block" : "none";
    };

    const renderChips = () => {
        chipsContainer.innerHTML = "";
        updateOmitWarning();
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
        // Build a normalized set of omitted triggers for visual comparison
        const omitSet = new Set((configArray.lora_omit_triggers || []).map(t => t.toLowerCase().trim()));

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
                    const isOmitted = omitSet.has(trigger.toLowerCase().trim());
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
                    if (isOmitted) {
                        triggerText.style.cssText = "color: #888; text-decoration: line-through; opacity: 0.5;";
                        // Add omitted label
                        const omitLabel = document.createElement("span");
                        omitLabel.textContent = "(omitted)";
                        omitLabel.style.cssText = "color: #cc6600; font-size: 10px; margin-left: 4px;";
                        triggerRow.appendChild(checkbox);
                        triggerRow.appendChild(triggerText);
                        triggerRow.appendChild(omitLabel);
                    } else {
                        triggerText.style.cssText = "color: #ddd;";
                        triggerRow.appendChild(checkbox);
                        triggerRow.appendChild(triggerText);
                    }
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

// =============================================================================
// --- PROMPT BUILDER COMPONENTS ---
// =============================================================================

/**
 * Creates a reusable prompt group editor.
 * Supports visual chip/tag mode and raw JSON mode.
 * Shows live preview of Cartesian product combinations.
 *
 * @param {Array} groups - Nested array of prompt groups: [["a", "b"], ["c", "d"]]
 * @param {Function} onChange - Callback when groups change: (newGroups) => void
 * @param {string} label - Label for this editor (e.g. "Positive Prompt" or "Negative Prompt")
 * @param {string} borderColor - CSS color for left border accent
 * @returns {HTMLElement}
 */
function createPromptGroupEditor(groups, onChange, label, borderColor = "#0066cc") {
    const container = document.createElement("div");
    container.style.cssText = `display: flex; flex-direction: column; gap: 8px; width: 100%;`;

    // Track mode state locally (visual vs raw)
    let isRawMode = false;

    // --- HEADER ---
    const header = document.createElement("div");
    header.style.cssText = "display: flex; justify-content: space-between; align-items: center;";

    const titleEl = document.createElement("div");
    titleEl.style.cssText = `font-size: 12px; font-weight: bold; color: ${borderColor};`;
    titleEl.textContent = label;
    header.appendChild(titleEl);

    const modeToggleContainer = document.createElement("div");
    modeToggleContainer.style.cssText = "display: flex; gap: 4px;";

    const visualBtn = document.createElement("button");
    visualBtn.className = "cb-prompt-mode-toggle active";
    visualBtn.textContent = "Visual";

    const rawBtn = document.createElement("button");
    rawBtn.className = "cb-prompt-mode-toggle";
    rawBtn.textContent = "JSON";

    modeToggleContainer.appendChild(visualBtn);
    modeToggleContainer.appendChild(rawBtn);
    header.appendChild(modeToggleContainer);
    container.appendChild(header);

    // --- VISUAL MODE CONTAINER ---
    const visualContainer = document.createElement("div");
    visualContainer.style.cssText = "display: flex; flex-direction: column; gap: 6px;";

    // --- RAW MODE CONTAINER ---
    const rawContainer = document.createElement("div");
    rawContainer.style.display = "none";

    const rawTextarea = document.createElement("textarea");
    rawTextarea.className = "cb-prompt-raw-editor";
    rawTextarea.placeholder = '[["variation1", "variation2"], ["subject1", "subject2"]]';
    rawTextarea.value = groups.length > 0 ? JSON.stringify(groups, null, 2) : "";

    rawTextarea.onchange = () => {
        try {
            const parsed = JSON.parse(rawTextarea.value);
            if (Array.isArray(parsed)) {
                // Normalize: ensure each item is an array
                const normalized = parsed.map(item =>
                    Array.isArray(item) ? item.map(String) : [String(item)]
                );
                onChange(normalized);
                rawTextarea.style.borderColor = "#00aa44";
                setTimeout(() => { rawTextarea.style.borderColor = "#3a3a3a"; }, 1000);
                renderVisualGroups(normalized);
                renderPreview(normalized);
            }
        } catch (e) {
            rawTextarea.style.borderColor = "#cc3333";
        }
    };
    rawContainer.appendChild(rawTextarea);

    // --- MODE TOGGLE LOGIC ---
    visualBtn.onclick = () => {
        isRawMode = false;
        visualContainer.style.display = "flex";
        rawContainer.style.display = "none";
        visualBtn.classList.add("active");
        rawBtn.classList.remove("active");
    };
    rawBtn.onclick = () => {
        isRawMode = true;
        visualContainer.style.display = "none";
        rawContainer.style.display = "block";
        rawBtn.classList.add("active");
        visualBtn.classList.remove("active");
        // Sync raw editor with current groups
        rawTextarea.value = groups.length > 0 ? JSON.stringify(groups, null, 2) : "";
    };

    container.appendChild(visualContainer);
    container.appendChild(rawContainer);

    // --- PREVIEW SECTION ---
    const previewContainer = document.createElement("div");
    container.appendChild(previewContainer);

    function renderPreview(currentGroups) {
        previewContainer.innerHTML = "";
        const validGroups = (currentGroups || []).filter(g => Array.isArray(g) && g.length > 0);
        if (validGroups.length === 0) return;

        const count = countPromptCombinations(validGroups);
        const previews = expandPromptPreview(validGroups, 20);

        const previewDiv = document.createElement("div");
        previewDiv.className = "cb-prompt-preview";

        const countLabel = document.createElement("div");
        countLabel.style.cssText = "font-weight: bold; margin-bottom: 4px; color: #00cc88;";
        countLabel.textContent = `${count} combination${count !== 1 ? 's' : ''}${count > 20 ? ' (showing first 20)' : ''}:`;
        previewDiv.appendChild(countLabel);

        previews.forEach(preview => {
            const item = document.createElement("div");
            item.className = "cb-prompt-preview-item";
            item.textContent = preview;
            previewDiv.appendChild(item);
        });

        previewContainer.appendChild(previewDiv);
    }

    // --- VISUAL GROUP RENDERING ---
    function renderVisualGroups(currentGroups) {
        visualContainer.innerHTML = "";

        (currentGroups || []).forEach((group, groupIdx) => {
            const groupDiv = document.createElement("div");
            groupDiv.className = "cb-prompt-group";

            // Group header
            const groupHeader = document.createElement("div");
            groupHeader.className = "cb-prompt-group-header";

            const groupLabel = document.createElement("span");
            groupLabel.textContent = `Group ${groupIdx + 1} (${group.length} variation${group.length !== 1 ? 's' : ''})`;
            groupHeader.appendChild(groupLabel);

            const groupDeleteBtn = document.createElement("button");
            groupDeleteBtn.className = "cb-button danger";
            groupDeleteBtn.style.cssText = "padding: 1px 6px; font-size: 10px;";
            groupDeleteBtn.textContent = "✖";
            groupDeleteBtn.title = "Remove this group";
            groupDeleteBtn.onclick = () => {
                const newGroups = [...currentGroups];
                newGroups.splice(groupIdx, 1);
                onChange(newGroups);
                renderVisualGroups(newGroups);
                renderPreview(newGroups);
                rawTextarea.value = newGroups.length > 0 ? JSON.stringify(newGroups, null, 2) : "";
            };
            groupHeader.appendChild(groupDeleteBtn);
            groupDiv.appendChild(groupHeader);

            // Chips container
            const chipsDiv = document.createElement("div");
            chipsDiv.className = "cb-prompt-chips";

            group.forEach((variation, varIdx) => {
                const chip = document.createElement("span");
                chip.className = "cb-prompt-chip";

                const chipText = document.createElement("span");
                chipText.textContent = variation;
                chipText.title = variation;
                chip.appendChild(chipText);

                const chipClose = document.createElement("span");
                chipClose.className = "chip-close";
                chipClose.textContent = "×";
                chipClose.onclick = () => {
                    const newGroups = currentGroups.map(g => [...g]);
                    newGroups[groupIdx].splice(varIdx, 1);
                    // Remove group if empty
                    if (newGroups[groupIdx].length === 0) {
                        newGroups.splice(groupIdx, 1);
                    }
                    onChange(newGroups);
                    renderVisualGroups(newGroups);
                    renderPreview(newGroups);
                    rawTextarea.value = newGroups.length > 0 ? JSON.stringify(newGroups, null, 2) : "";
                };
                chip.appendChild(chipClose);
                chipsDiv.appendChild(chip);
            });

            // Add variation input
            const addVarBtn = document.createElement("button");
            addVarBtn.className = "cb-prompt-add-variation";
            addVarBtn.textContent = "+ variation";
            addVarBtn.onclick = () => {
                // Replace button with inline input
                const inputContainer = document.createElement("div");
                inputContainer.style.cssText = "display: inline-flex; gap: 2px;";

                const input = document.createElement("input");
                input.className = "cb-input";
                input.style.cssText = "width: 180px; padding: 3px 6px; font-size: 12px;";
                input.placeholder = "Enter prompt text...";

                const confirmBtn = document.createElement("button");
                confirmBtn.className = "cb-button primary";
                confirmBtn.style.cssText = "padding: 2px 8px; font-size: 11px;";
                confirmBtn.textContent = "Add";

                const addVariation = () => {
                    const val = input.value.trim();
                    if (val) {
                        const newGroups = currentGroups.map(g => [...g]);
                        newGroups[groupIdx].push(val);
                        onChange(newGroups);
                        renderVisualGroups(newGroups);
                        renderPreview(newGroups);
                        rawTextarea.value = newGroups.length > 0 ? JSON.stringify(newGroups, null, 2) : "";
                    }
                };

                input.onkeydown = (e) => {
                    if (e.key === "Enter") addVariation();
                    if (e.key === "Escape") {
                        inputContainer.replaceWith(addVarBtn);
                    }
                };
                confirmBtn.onclick = addVariation;

                inputContainer.appendChild(input);
                inputContainer.appendChild(confirmBtn);
                addVarBtn.replaceWith(inputContainer);
                input.focus();
            };
            chipsDiv.appendChild(addVarBtn);

            groupDiv.appendChild(chipsDiv);
            visualContainer.appendChild(groupDiv);
        });

        // Add Group button
        const addGroupBtn = document.createElement("button");
        addGroupBtn.className = "cb-prompt-add-group-btn";
        addGroupBtn.textContent = "➕ Add Prompt Group";
        addGroupBtn.onclick = () => {
            // Create input for the first variation of the new group
            const inputContainer = document.createElement("div");
            inputContainer.style.cssText = "display: flex; gap: 4px; margin-top: 4px;";

            const input = document.createElement("input");
            input.className = "cb-input";
            input.style.cssText = "flex: 1; padding: 6px 8px; font-size: 12px;";
            input.placeholder = "Enter first variation for new group...";

            const confirmBtn = document.createElement("button");
            confirmBtn.className = "cb-button primary";
            confirmBtn.style.padding = "4px 12px";
            confirmBtn.textContent = "Add Group";

            const addGroup = () => {
                const val = input.value.trim();
                if (val) {
                    const newGroups = [...(currentGroups || []), [val]];
                    onChange(newGroups);
                    renderVisualGroups(newGroups);
                    renderPreview(newGroups);
                    rawTextarea.value = newGroups.length > 0 ? JSON.stringify(newGroups, null, 2) : "";
                }
            };

            input.onkeydown = (e) => {
                if (e.key === "Enter") addGroup();
                if (e.key === "Escape") {
                    inputContainer.replaceWith(addGroupBtn);
                }
            };
            confirmBtn.onclick = addGroup;

            inputContainer.appendChild(input);
            inputContainer.appendChild(confirmBtn);
            addGroupBtn.replaceWith(inputContainer);
            input.focus();
        };
        visualContainer.appendChild(addGroupBtn);
    }

    // Initial render
    renderVisualGroups(groups);
    renderPreview(groups);

    return container;
}

// --- GLOBAL PROMPTS SECTION ---

export function renderGlobalPromptsSection(node, container) {
    const isCollapsed = node.uiState.globalPromptsSectionCollapsed || false;

    const section = document.createElement("div");
    section.className = "cb-section full-width";

    // Header (collapsible)
    const header = document.createElement("div");
    header.className = "cb-section-toggle";
    header.style.cssText = "display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; margin-bottom: 10px;";

    const titleSpan = document.createElement("div");
    titleSpan.className = "cb-section-title";
    titleSpan.style.cssText = "margin-bottom: 0; border-bottom: none; padding-bottom: 0; color: #00aa44;";
    titleSpan.textContent = "📝 Global Prompts (Override Node Inputs)";
    header.appendChild(titleSpan);

    const arrowSpan = document.createElement("span");
    arrowSpan.textContent = isCollapsed ? "▶" : "▼";
    arrowSpan.style.cssText = "color: #00aa44; font-size: 12px;";
    header.appendChild(arrowSpan);

    section.appendChild(header);

    // Content container
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "flex";
    contentDiv.style.flexDirection = "column";
    contentDiv.style.gap = "12px";

    header.onclick = () => {
        const isNowCollapsed = contentDiv.style.display !== "none";
        contentDiv.style.display = isNowCollapsed ? "none" : "flex";
        arrowSpan.textContent = isNowCollapsed ? "▶" : "▼";
        node.uiState.globalPromptsSectionCollapsed = isNowCollapsed;
    };

    // Info text
    const info = document.createElement("div");
    info.style.cssText = "font-size: 11px; color: #888; font-style: italic;";
    info.textContent = "These prompts override the sampler node's positive/negative text inputs for ALL config arrays. Per-config prompts (below) can further override these.";
    contentDiv.appendChild(info);

    // Positive Prompt Editor
    const positiveSection = document.createElement("div");
    positiveSection.className = "cb-prompt-section global";

    const positiveEditor = createPromptGroupEditor(
        node.state.global_positive_groups || [],
        (newGroups) => {
            node.state.global_positive_groups = newGroups;
            node.saveState();
        },
        "✅ Positive Prompt Groups",
        "#00aa44"
    );
    positiveSection.appendChild(positiveEditor);
    contentDiv.appendChild(positiveSection);

    // Negative Prompt (simple text area, not nested groups)
    const negativeSection = document.createElement("div");
    negativeSection.className = "cb-prompt-section global";

    const negLabel = document.createElement("div");
    negLabel.style.cssText = "font-size: 12px; font-weight: bold; color: #cc4444; margin-bottom: 6px;";
    negLabel.textContent = "❌ Negative Prompt";
    negativeSection.appendChild(negLabel);

    const negInput = document.createElement("textarea");
    negInput.className = "cb-prompt-raw-editor";
    negInput.style.minHeight = "50px";
    negInput.placeholder = "bad quality, worst quality, lowres";
    negInput.value = node.state.global_negative || "";
    negInput.onchange = () => {
        node.state.global_negative = negInput.value;
        node.saveState();
    };
    negativeSection.appendChild(negInput);
    contentDiv.appendChild(negativeSection);

    section.appendChild(contentDiv);
    container.appendChild(section);
}

// --- PER-CONFIG PROMPTS SECTION ---

export function renderConfigPromptsSection(node, div, configArray, arrayIdx) {
    const uid = `prompts_${arrayIdx}`;
    const isCollapsed = node.uiState.promptsSectionCollapsed[uid] !== false; // Default collapsed

    const section = document.createElement("div");
    section.style.cssText = "width: 100%; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #444;";

    // Header
    const header = document.createElement("div");
    header.className = "cb-section-toggle";
    header.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #9966cc;";

    const promptCount = configArray.use_custom_prompts && configArray.positive_prompt_groups
        ? countPromptCombinations(configArray.positive_prompt_groups)
        : 0;

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `Prompts${promptCount > 0 ? ` (${promptCount} combinations)` : ''}`;
    header.appendChild(titleSpan);

    const arrowSpan = document.createElement("span");
    arrowSpan.textContent = isCollapsed ? "▶" : "▼";
    header.appendChild(arrowSpan);

    section.appendChild(header);

    // Content
    const contentDiv = document.createElement("div");
    contentDiv.style.display = isCollapsed ? "none" : "block";

    header.onclick = () => {
        const isNowCollapsed = contentDiv.style.display !== "none";
        contentDiv.style.display = isNowCollapsed ? "none" : "block";
        arrowSpan.textContent = isNowCollapsed ? "▶" : "▼";
        node.uiState.promptsSectionCollapsed[uid] = isNowCollapsed;
    };

    // Toggle: Use Custom Prompts
    const toggleLabel = document.createElement("label");
    toggleLabel.style.cssText = "display: flex; align-items: center; gap: 8px; cursor: pointer; margin-bottom: 10px; font-size: 13px;";

    const toggleCheck = document.createElement("input");
    toggleCheck.type = "checkbox";
    toggleCheck.checked = configArray.use_custom_prompts || false;
    toggleCheck.onchange = () => {
        node.state.config_arrays[arrayIdx].use_custom_prompts = toggleCheck.checked;
        node.saveState();
        node.renderUI();
    };
    toggleLabel.appendChild(toggleCheck);
    toggleLabel.appendChild(document.createTextNode("Use Custom Prompts (Override Global/Node)"));
    contentDiv.appendChild(toggleLabel);

    if (configArray.use_custom_prompts) {
        // Positive Prompt Editor
        const positiveSection = document.createElement("div");
        positiveSection.className = "cb-prompt-section per-config";

        const positiveEditor = createPromptGroupEditor(
            configArray.positive_prompt_groups || [],
            (newGroups) => {
                node.state.config_arrays[arrayIdx].positive_prompt_groups = newGroups;
                node.saveState();
            },
            "✅ Positive Prompt Groups",
            "#9966cc"
        );
        positiveSection.appendChild(positiveEditor);
        contentDiv.appendChild(positiveSection);

        // Negative Prompt (simple text)
        const negativeSection = document.createElement("div");
        negativeSection.className = "cb-prompt-section per-config";
        negativeSection.style.marginTop = "8px";

        const negLabel = document.createElement("div");
        negLabel.style.cssText = "font-size: 12px; font-weight: bold; color: #cc4444; margin-bottom: 6px;";
        negLabel.textContent = "❌ Negative Prompt";
        negativeSection.appendChild(negLabel);

        const negInput = document.createElement("textarea");
        negInput.className = "cb-prompt-raw-editor";
        negInput.style.minHeight = "50px";
        negInput.placeholder = "bad quality, worst quality, lowres";
        negInput.value = configArray.negative_prompt || "";
        negInput.onchange = () => {
            node.state.config_arrays[arrayIdx].negative_prompt = negInput.value;
            node.saveState();
        };
        negativeSection.appendChild(negInput);
        contentDiv.appendChild(negativeSection);
    } else {
        const infoText = document.createElement("div");
        infoText.style.cssText = "font-size: 11px; color: #666; font-style: italic; padding: 4px;";
        infoText.textContent = "Using global prompts (or node inputs if no global prompts defined).";
        contentDiv.appendChild(infoText);
    }

    section.appendChild(contentDiv);
    div.appendChild(section);
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

export async function renderUI(node, availableLoras, modelLists, loraFolders, availableSessions, availableConfigs, refreshAllConfigBuilders) {
    const scrollContainer = node.htmlContainer.querySelector(".cb-container");
    const savedScrollTop = scrollContainer ? scrollContainer.scrollTop : 0;

    node.htmlContainer.innerHTML = getStyles() + '<div class="cb-container" id="cb-root"></div>';

    const root = node.htmlContainer.querySelector("#cb-root");

    const topRow = document.createElement("div");
    topRow.className = "cb-sections-row";
    renderSessionSection(node, topRow, availableSessions, refreshAllConfigBuilders);
    renderConfigSection(node, topRow, availableConfigs);
    root.appendChild(topRow);

    // Global Prompts Section (between session/config management and config arrays)
    renderGlobalPromptsSection(node, root);

    const configSection = document.createElement("div");
    configSection.className = "cb-section full-width";
    configSection.innerHTML = '<div class="cb-section-title">⚙️ Config Arrays</div>';

    const headerBar = document.createElement("div");
    headerBar.style.cssText = "margin-bottom: 10px; display: flex; align-items: center; gap: 12px;";
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
            seed_behavior: "fixed",
            models: ["None"],
            vaes: ["None"],
            text_encoders: [],
            clip_type: "stable_diffusion",
            gguf_options: {},
            loras: ["None"],
            lora_omit_triggers: [],
            lora_triggerwords_append_settings: {},
            combine: false,
            positive_prompt_groups: [],
            negative_prompt: "",
            use_custom_prompts: false
        });
        node.saveState();
        node.renderUI();
    };
    headerBar.appendChild(addConfigBtn);

    const labelModeLabel = document.createElement("label");
    labelModeLabel.className = "cb-toggle";
    labelModeLabel.style.fontSize = "12px";
    const labelModeCheckbox = document.createElement("input");
    labelModeCheckbox.type = "checkbox";
    labelModeCheckbox.checked = node.state.label_mode || false;
    labelModeCheckbox.onchange = () => {
        node.state.label_mode = labelModeCheckbox.checked;
        node.saveState();
        node.renderUI();
    };
    labelModeLabel.appendChild(labelModeCheckbox);
    labelModeLabel.appendChild(document.createTextNode(" \u{1F3F7}\uFE0F Label Mode"));
    headerBar.appendChild(labelModeLabel);

    configSection.appendChild(headerBar);

    const arraysContainer = document.createElement("div");
    arraysContainer.className = "cb-arrays-container";

    node.state.config_arrays.forEach((configArray, arrayIdx) => {
        const arrayElement = createConfigArrayElement(node, configArray, arrayIdx);
        renderConfigPromptsSection(node, arrayElement, configArray, arrayIdx);
        renderModelsSection(node, arrayElement, configArray, arrayIdx, modelLists);
        renderVAEsSection(node, arrayElement, configArray, arrayIdx);
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