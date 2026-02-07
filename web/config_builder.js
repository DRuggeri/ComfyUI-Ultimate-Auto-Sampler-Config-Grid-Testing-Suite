/**
 * Ultimate Config Builder - COMPLETE HTML UI
 * - ALL inputs in HTML/JS
 * - Session loading updates everything
 * - Live JSON preview
 * - FLEX WRAP LAYOUT
 * - DYNAMIC MODEL SELECTION (Multiple Models & Folders)
 */

import { app } from "../../scripts/app.js";

// Cache for available resources
let availableLoras = null;
let loraFolders = null;
let availableModels = null;
let modelFolders = null;
let availableSessions = ["None"];

// Fetch available LoRAs
async function getAvailableLoras() {
    if (availableLoras) return availableLoras;
    try {
        const resp = await fetch("/object_info");
        const objectInfo = await resp.json();
        for (const nodeType in objectInfo) {
            const nodeDef = objectInfo[nodeType];
            if (nodeDef.input?.required?.lora_name) {
                const loraInput = nodeDef.input.required.lora_name;
                if (Array.isArray(loraInput) && Array.isArray(loraInput[0])) {
                    availableLoras = loraInput[0];
                    return availableLoras;
                }
            }
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching LoRAs:", e); }
    availableLoras = ["None"];
    return availableLoras;
}

// Fetch available Models (Checkpoints)
async function getAvailableModels() {
    if (availableModels) return availableModels;
    try {
        const resp = await fetch("/object_info");
        const objectInfo = await resp.json();
        // Look for standard CheckpointLoaderSimple or similar
        const loaderNode = objectInfo["CheckpointLoaderSimple"] || objectInfo["CheckpointLoader"];
        if (loaderNode?.input?.required?.ckpt_name) {
             const modelInput = loaderNode.input.required.ckpt_name;
             if (Array.isArray(modelInput) && Array.isArray(modelInput[0])) {
                 availableModels = modelInput[0];
                 console.log(`[ConfigBuilder] Found ${availableModels.length} Models`);
                 return availableModels;
             }
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching Models:", e); }
    availableModels = ["None"];
    return availableModels;
}

// Extract folders from paths (Generic)
function extractFolders(itemList) {
    const folders = new Set(["/"]);
    itemList.forEach(item => {
        const parts = item.split(/[\/\\]/);
        if (parts.length > 1) {
            let currentPath = "";
            for (let i = 0; i < parts.length - 1; i++) {
                currentPath += parts[i] + "/";
                folders.add(currentPath);
            }
        }
    });
    return Array.from(folders).sort();
}

async function getLoraFolders() {
    if (loraFolders) return loraFolders;
    const loras = await getAvailableLoras();
    loraFolders = extractFolders(loras);
    return loraFolders;
}

async function getModelFolders() {
    if (modelFolders) return modelFolders;
    const models = await getAvailableModels();
    modelFolders = extractFolders(models);
    return modelFolders;
}

// Fetch available sessions
async function getAvailableSessions() {
    try {
        const resp = await fetch("/object_info");
        const objectInfo = await resp.json();
        for (const nodeType in objectInfo) {
            const nodeDef = objectInfo[nodeType];
            if (nodeType === "UltimateConfigBuilder" && nodeDef.input?.required?.load_session) {
                availableSessions = nodeDef.input.required.load_session[0];
                return availableSessions;
            }
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching sessions:", e); }
    return availableSessions;
}

// Parse LoRA string
function parseLoraString(loraStr) {
    if (!loraStr || loraStr === "None") return { name: "None", model_str: 1.0, clip_str: 1.0 };
    if (loraStr.endsWith("/")) return { name: loraStr, model_str: 1.0, clip_str: 1.0 };
    const parts = loraStr.split(":");
    return {
        name: parts[0] || "None",
        model_str: parts.length > 1 ? parseFloat(parts[1]) : 1.0,
        clip_str: parts.length > 2 ? parseFloat(parts[2]) : 1.0
    };
}

function buildLoraString(name, modelStr, clipStr) {
    if (!name || name === "None") return "None";
    if (name.endsWith("/")) return name;
    if (modelStr === 1.0 && clipStr === 1.0) return name;
    return `${name}:${modelStr.toFixed(2)}:${clipStr.toFixed(2)}`;
}

app.registerExtension({
    name: "UltimateConfigBuilder.CompleteHTML",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UltimateConfigBuilder") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = async function () {
                const result = onNodeCreated?.apply(this, arguments);

                const configWidget = this.widgets?.find(w => w.name === "lora_config");
                if (!configWidget) return result;

                this.widgets.forEach(w => {
                    w.type = "converted-widget";
                    w.computeSize = () => [0, -4];
                });

                // Pre-fetch everything
                await getAvailableLoras();
                await getLoraFolders();
                await getAvailableModels();
                await getModelFolders();
                await getAvailableSessions();

                this.configWidget = configWidget;
                this.state = {
                    session_name: "my_test_session",
                    include_none: true,
                    config_arrays: [{
                        name: "Config 1",
                        samplers: "euler, dpmpp_2m",
                        schedulers: "normal, karras",
                        steps: "20, 30",
                        cfg: "7.0",
                        models: ["None"], // Changed to array
                        loras: ["None"],
                        combine: false
                    }]
                };

                // Load state
                try {
                    const existing = JSON.parse(configWidget.value);
                    if (existing.config_arrays) {
                        this.state = existing;
                        // Migration check: ensure models is an array
                        this.state.config_arrays.forEach(arr => {
                            if (arr.model && !arr.models) {
                                arr.models = [arr.model];
                                delete arr.model;
                            }
                            if (!arr.models) arr.models = ["None"];
                        });
                    } else if (existing.lora_config) {
                        this.state = this.migrateOldFormat(existing);
                    }
                } catch (e) {}

                this.migrateOldFormat = function(oldState) {
                    const arrays = oldState.lora_config?.arrays || [];
                    return {
                        session_name: oldState.session_name || "my_test_session",
                        include_none: oldState.include_none !== undefined ? oldState.include_none : true,
                        config_arrays: arrays.map(arr => ({
                            name: arr.name,
                            samplers: oldState.samplers || "euler",
                            schedulers: oldState.schedulers || "normal",
                            steps: oldState.steps || "20",
                            cfg: oldState.cfg || "7.0",
                            models: oldState.model ? [oldState.model] : ["None"], // Handle legacy model string
                            loras: arr.loras || ["None"],
                            combine: arr.combine || false
                        }))
                    };
                };

                this.saveState = function() {
                    configWidget.value = JSON.stringify(this.state, null, 2);
                    this.updatePreview();
                };

                this.htmlContainer = document.createElement("div");
                this.htmlContainer.style.cssText = `width: 100%; height: 100%; background: #1a1a1a; display: flex; flex-direction: column;`;
                this.addDOMWidget("config_ui", "div", this.htmlContainer, { serialize: false, hideOnZoom: false });

                // --- UI RENDER ---
                this.renderUI = function() {
                    this.htmlContainer.innerHTML = `
                        <style>
                            .cb-container { padding: 12px; height: 100%; overflow-y: auto; box-sizing: border-box; }
                            .cb-sections-row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
                            .cb-section { background: #2a2a2a; border-radius: 4px; padding: 12px; border: 1px solid #3a3a3a; box-sizing: border-box; flex: 1 1 300px; }
                            .cb-section.full-width { flex: 1 1 100%; width: 100%; }
                            .cb-section-title { color: #0066cc; font-size: 14px; font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid #3a3a3a; padding-bottom: 6px; }
                            .cb-flex-grid { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
                            .cb-input-group { flex: 1 1 180px; min-width: 140px; display: flex; flex-direction: column; }
                            .cb-input, .cb-select { background: #1a1a1a; border: 1px solid #4a4a4a; color: white; padding: 8px 10px; border-radius: 4px; width: 100%; font-family: monospace; }
                            .cb-input:focus, .cb-select:focus { outline: none; border-color: #0066cc; }
                            .cb-label { color: #aaa; font-size: 12px; margin-bottom: 4px; display: block; }
                            .cb-button { background: #4a4a4a; border: none; color: white; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; margin: 4px 2px; }
                            .cb-button:hover { background: #5a5a5a; }
                            .cb-button.primary { background: #0066cc; }
                            .cb-button.primary:hover { background: #0077ee; }
                            .cb-button.danger { background: #cc3333; }
                            .cb-button.danger:hover { background: #dd4444; }
                            .cb-array { background: #333; border-radius: 4px; padding: 12px; margin: 8px 0; border: 1px solid #3a3a3a; width: 100%; }
                            .cb-arrays-container { display: flex; flex-direction: column; gap: 12px; }
                            
                            /* Shared Grid for Models & Loras */
                            .cb-list-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #444; }
                            .cb-item-card { background: #2a2a2a; border-radius: 4px; padding: 10px; border-left: 3px solid #0066cc; flex: 1 1 300px; min-width: 250px; display: flex; flex-direction: column; gap: 6px; }
                            .cb-item-card.model-card { border-left-color: #cc6600; } /* Orange for models */
                            
                            .cb-controls-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 10px; padding: 8px; background: #252525; border-radius: 4px; }
                            .cb-header-bar { display: flex; justify-content: space-between; margin-bottom: 4px; }
                            .cb-slider-container { display: flex; align-items: center; gap: 10px; }
                            .cb-slider { flex: 1; height: 6px; background: #1a1a1a; border-radius: 3px; outline: none; }
                            .cb-slider-value { color: #0066cc; font-weight: bold; min-width: 45px; text-align: right; font-size: 12px; }
                            .cb-preview { background: #0a0a0a; border: 1px solid #3a3a3a; border-radius: 4px; padding: 10px; margin: 10px 0; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 11px; color: #0cc; }
                            .cb-toggle { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; color: #ccc; }
                        </style>
                        <div class="cb-container" id="cb-root"></div>
                    `;

                    const root = this.htmlContainer.querySelector("#cb-root");
                    
                    // Top Section
                    const topRow = document.createElement("div");
                    topRow.className = "cb-sections-row";
                    this.renderSessionSection(topRow);
                    // this.renderOptionsSection(topRow);
                    root.appendChild(topRow);

                    // Config Arrays
                    const configSection = document.createElement("div");
                    configSection.className = "cb-section full-width";
                    configSection.innerHTML = '<div class="cb-section-title">⚙️ Config Arrays</div>';
                    
                    const headerBar = document.createElement("div");
                    headerBar.style.marginBottom = "10px";
                    const addConfigBtn = document.createElement("button");
                    addConfigBtn.className = "cb-button primary";
                    addConfigBtn.textContent = "➕ Add Config Array";
                    addConfigBtn.onclick = () => {
                        this.state.config_arrays.push({
                            name: `Config ${this.state.config_arrays.length + 1}`,
                            samplers: "euler",
                            schedulers: "normal",
                            steps: "20",
                            cfg: "7.0",
                            models: ["None"],
                            loras: ["None"],
                            combine: false
                        });
                        this.saveState();
                        this.renderUI();
                    };
                    headerBar.appendChild(addConfigBtn);
                    configSection.appendChild(headerBar);
                    
                    const arraysContainer = document.createElement("div");
                    arraysContainer.className = "cb-arrays-container";
                    this.state.config_arrays.forEach((configArray, arrayIdx) => {
                        arraysContainer.appendChild(this.createConfigArrayElement(configArray, arrayIdx));
                    });
                    configSection.appendChild(arraysContainer);
                    root.appendChild(configSection);

                    this.renderPreviewSection(root);
                    this.updatePreview();
                };

                this.createInputGroup = function(labelText, inputElement) {
                    const group = document.createElement("div");
                    group.className = "cb-input-group";
                    const label = document.createElement("label");
                    label.className = "cb-label";
                    label.textContent = labelText;
                    group.appendChild(label);
                    group.appendChild(inputElement);
                    return group;
                };

                this.renderSessionSection = function(container) {
                    const section = document.createElement("div");
                    section.className = "cb-section";
                    section.innerHTML = '<div class="cb-section-title">📁 Session Management</div>';
                    const grid = document.createElement("div");
                    grid.className = "cb-flex-grid";

                    const nameInput = document.createElement("input");
                    nameInput.className = "cb-input";
                    nameInput.value = this.state.session_name;
                    nameInput.onchange = () => { this.state.session_name = nameInput.value; this.saveState(); };
                    grid.appendChild(this.createInputGroup("Session Name", nameInput));

                    const loadSelect = document.createElement("select");
                    loadSelect.className = "cb-select";
                    loadSelect.innerHTML = availableSessions.map(s => `<option value="${s}">${s}</option>`).join('');
                    loadSelect.onchange = async () => { if (loadSelect.value && loadSelect.value !== "None") await this.loadSession(loadSelect.value); };
                    grid.appendChild(this.createInputGroup("Load Session", loadSelect));

                    section.appendChild(grid);
                    container.appendChild(section);
                };

                this.renderOptionsSection = function(container) {
                    const section = document.createElement("div");
                    section.className = "cb-section";
                    section.innerHTML = '<div class="cb-section-title">🎯 Options</div>';
                    const grid = document.createElement("div");
                    grid.className = "cb-flex-grid";

                    const toggleLabel = document.createElement("label");
                    toggleLabel.className = "cb-toggle";
                    const toggleInput = document.createElement("input");
                    toggleInput.type = "checkbox";
                    toggleInput.checked = this.state.include_none;
                    toggleInput.onchange = () => { this.state.include_none = toggleInput.checked; this.saveState(); };
                    toggleLabel.appendChild(toggleInput);
                    toggleLabel.appendChild(document.createTextNode(" Include 'None' in Lists"));
                    
                    grid.appendChild(toggleLabel);
                    section.appendChild(grid);
                    container.appendChild(section);
                };

                this.createConfigArrayElement = function(configArray, arrayIdx) {
                    const div = document.createElement("div");
                    div.className = "cb-array";

                    // Settings Grid
                    const settingsGrid = document.createElement("div");
                    settingsGrid.className = "cb-flex-grid";

                    const nameInput = document.createElement("input");
                    nameInput.className = "cb-input";
                    nameInput.value = configArray.name;
                    nameInput.onchange = () => { this.state.config_arrays[arrayIdx].name = nameInput.value; this.saveState(); };
                    settingsGrid.appendChild(this.createInputGroup("Config Name", nameInput));

                    const samplersInput = document.createElement("input");
                    samplersInput.className = "cb-input";
                    samplersInput.value = configArray.samplers;
                    samplersInput.onchange = () => { this.state.config_arrays[arrayIdx].samplers = samplersInput.value; this.saveState(); };
                    settingsGrid.appendChild(this.createInputGroup("Samplers", samplersInput));

                    const schedulersInput = document.createElement("input");
                    schedulersInput.className = "cb-input";
                    schedulersInput.value = configArray.schedulers;
                    schedulersInput.onchange = () => { this.state.config_arrays[arrayIdx].schedulers = schedulersInput.value; this.saveState(); };
                    settingsGrid.appendChild(this.createInputGroup("Schedulers", schedulersInput));

                    const stepsInput = document.createElement("input");
                    stepsInput.className = "cb-input";
                    stepsInput.value = configArray.steps;
                    stepsInput.onchange = () => { this.state.config_arrays[arrayIdx].steps = stepsInput.value; this.saveState(); };
                    settingsGrid.appendChild(this.createInputGroup("Steps", stepsInput));

                    const cfgInput = document.createElement("input");
                    cfgInput.className = "cb-input";
                    cfgInput.value = configArray.cfg;
                    cfgInput.onchange = () => { this.state.config_arrays[arrayIdx].cfg = cfgInput.value; this.saveState(); };
                    settingsGrid.appendChild(this.createInputGroup("CFG", cfgInput));

                    div.appendChild(settingsGrid);

                    // --- CONTROLS BAR (Buttons) ---
                    const controlsBar = document.createElement("div");
                    controlsBar.className = "cb-controls-bar";

                    const toggleLabel = document.createElement("label");
                    toggleLabel.className = "cb-toggle";
                    const toggleInput = document.createElement("input");
                    toggleInput.type = "checkbox";
                    toggleInput.checked = configArray.combine;
                    toggleInput.onchange = () => { this.state.config_arrays[arrayIdx].combine = toggleInput.checked; this.saveState(); };
                    toggleLabel.appendChild(toggleInput);
                    toggleLabel.appendChild(document.createTextNode(" Stack All LoRAs"));
                    controlsBar.appendChild(toggleLabel);

                    const spacer = document.createElement("div");
                    spacer.style.flex = "1";
                    controlsBar.appendChild(spacer);

                    const addModelBtn = document.createElement("button");
                    addModelBtn.className = "cb-button";
                    addModelBtn.style.borderLeft = "4px solid #cc6600"; // Orange accent
                    addModelBtn.textContent = `➕ Add Model`;
                    addModelBtn.onclick = () => {
                        if(!this.state.config_arrays[arrayIdx].models) this.state.config_arrays[arrayIdx].models = [];
                        this.state.config_arrays[arrayIdx].models.push("None");
                        this.saveState();
                        this.renderUI();
                    };
                    controlsBar.appendChild(addModelBtn);

                    const addLoraBtn = document.createElement("button");
                    addLoraBtn.className = "cb-button";
                    addLoraBtn.style.borderLeft = "4px solid #0066cc"; // Blue accent
                    addLoraBtn.textContent = `➕ Add LoRA`;
                    addLoraBtn.onclick = () => {
                        this.state.config_arrays[arrayIdx].loras.push("None");
                        this.saveState();
                        this.renderUI();
                    };
                    controlsBar.appendChild(addLoraBtn);

                    const deleteBtn = document.createElement("button");
                    deleteBtn.className = "cb-button danger";
                    deleteBtn.textContent = `🗑️ Delete Config`;
                    deleteBtn.onclick = () => {
                        this.state.config_arrays.splice(arrayIdx, 1);
                        this.saveState();
                        this.renderUI();
                    };
                    controlsBar.appendChild(deleteBtn);

                    div.appendChild(controlsBar);

                    // --- MODELS GRID ---
                    if (configArray.models && configArray.models.length > 0) {
                        const modelGrid = document.createElement("div");
                        modelGrid.className = "cb-list-grid";
                        const modelTitle = document.createElement("div");
                        modelTitle.style.width = "100%";
                        modelTitle.style.color = "#cc6600";
                        modelTitle.style.fontWeight = "bold";
                        modelTitle.style.fontSize = "12px";
                        modelTitle.textContent = "Models / Checkpoints";
                        modelGrid.appendChild(modelTitle);

                        configArray.models.forEach((model, modelIdx) => {
                            modelGrid.appendChild(this.createModelElement(model, arrayIdx, modelIdx));
                        });
                        div.appendChild(modelGrid);
                    }

                    // --- LORAS GRID ---
                    if (configArray.loras && configArray.loras.length > 0) {
                        const loraGrid = document.createElement("div");
                        loraGrid.className = "cb-list-grid";
                        const loraTitle = document.createElement("div");
                        loraTitle.style.width = "100%";
                        loraTitle.style.color = "#0066cc";
                        loraTitle.style.fontWeight = "bold";
                        loraTitle.style.fontSize = "12px";
                        loraTitle.textContent = "LoRAs";
                        loraGrid.appendChild(loraTitle);

                        configArray.loras.forEach((lora, loraIdx) => {
                            loraGrid.appendChild(this.createLoraElement(lora, arrayIdx, loraIdx));
                        });
                        div.appendChild(loraGrid);
                    }

                    return div;
                };

                // Create Model Element
                this.createModelElement = function(modelStr, arrayIdx, modelIdx) {
                    const div = document.createElement("div");
                    div.className = "cb-item-card model-card";
                    const isFolder = modelStr.endsWith("/");

                    // Header
                    const header = document.createElement("div");
                    header.className = "cb-header-bar";
                    const label = document.createElement("span");
                    label.textContent = `Model #${modelIdx + 1}`;
                    label.style.color = "#aaa";
                    header.appendChild(label);

                    const deleteBtn = document.createElement("button");
                    deleteBtn.className = "cb-button danger";
                    deleteBtn.style.padding = "2px 6px";
                    deleteBtn.style.fontSize = "10px";
                    deleteBtn.textContent = "✖";
                    deleteBtn.onclick = () => {
                        this.state.config_arrays[arrayIdx].models.splice(modelIdx, 1);
                        this.saveState();
                        this.renderUI();
                    };
                    header.appendChild(deleteBtn);
                    div.appendChild(header);

                    // Type Select
                    const typeSelect = document.createElement("select");
                    typeSelect.className = "cb-select";
                    typeSelect.innerHTML = `
                        <option value="file" ${!isFolder ? 'selected' : ''}>Checkpoint File</option>
                        <option value="folder" ${isFolder ? 'selected' : ''}>Folder</option>
                    `;
                    typeSelect.onchange = () => {
                        this.state.config_arrays[arrayIdx].models[modelIdx] = typeSelect.value === "folder" ? "/" : "None";
                        this.saveState();
                        this.renderUI();
                    };
                    div.appendChild(typeSelect);

                    // Name Select
                    const nameSelect = document.createElement("select");
                    nameSelect.className = "cb-select";
                    const options = isFolder ? modelFolders : availableModels;
                    // Ensure current value is in list
                    const currentVal = modelStr;
                    const optionsList = (options.includes(currentVal) || currentVal === "None" || currentVal === "/") ? options : [currentVal, ...options];

                    nameSelect.innerHTML = optionsList.map(opt => `<option value="${opt}" ${opt === currentVal ? 'selected' : ''}>${opt}</option>`).join('');
                    nameSelect.onchange = () => {
                        this.state.config_arrays[arrayIdx].models[modelIdx] = nameSelect.value;
                        this.saveState();
                    };
                    div.appendChild(nameSelect);

                    return div;
                };

                // Create LoRA Element
                this.createLoraElement = function(loraStr, arrayIdx, loraIdx) {
                    const div = document.createElement("div");
                    div.className = "cb-item-card";
                    const parsed = parseLoraString(loraStr);
                    const isFolder = parsed.name.endsWith("/");

                    const header = document.createElement("div");
                    header.className = "cb-header-bar";
                    const label = document.createElement("span");
                    label.textContent = `LoRA #${loraIdx + 1}`;
                    label.style.color = "#aaa";
                    header.appendChild(label);

                    const deleteBtn = document.createElement("button");
                    deleteBtn.className = "cb-button danger";
                    deleteBtn.style.padding = "2px 6px";
                    deleteBtn.style.fontSize = "10px";
                    deleteBtn.textContent = "✖";
                    deleteBtn.onclick = () => {
                        this.state.config_arrays[arrayIdx].loras.splice(loraIdx, 1);
                        this.saveState();
                        this.renderUI();
                    };
                    header.appendChild(deleteBtn);
                    div.appendChild(header);

                    const typeSelect = document.createElement("select");
                    typeSelect.className = "cb-select";
                    typeSelect.innerHTML = `
                        <option value="lora" ${!isFolder ? 'selected' : ''}>LoRA File</option>
                        <option value="folder" ${isFolder ? 'selected' : ''}>Folder</option>
                    `;
                    typeSelect.onchange = () => {
                        this.state.config_arrays[arrayIdx].loras[loraIdx] = typeSelect.value === "folder" ? "/" : "None";
                        this.saveState();
                        this.renderUI();
                    };
                    div.appendChild(typeSelect);

                    const nameSelect = document.createElement("select");
                    nameSelect.className = "cb-select";
                    const options = isFolder ? loraFolders : availableLoras;
                    const optionsList = (options.includes(parsed.name) || parsed.name === "None") ? options : [parsed.name, ...options];
                    
                    nameSelect.innerHTML = optionsList.map(opt => `<option value="${opt}" ${opt === parsed.name ? 'selected' : ''}>${opt}</option>`).join('');
                    nameSelect.onchange = () => {
                        if (isFolder) this.state.config_arrays[arrayIdx].loras[loraIdx] = nameSelect.value;
                        else this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(nameSelect.value, parsed.model_str, parsed.clip_str);
                        this.saveState();
                    };
                    div.appendChild(nameSelect);

                    if (!isFolder && parsed.name !== "None") {
                        // Sliders logic...
                        const makeSlider = (label, val, onChange) => {
                            const c = document.createElement("div");
                            c.className = "cb-slider-container";
                            const l = document.createElement("span");
                            l.style.fontSize = "10px"; l.style.color = "#aaa"; l.textContent = label;
                            c.appendChild(l);
                            const s = document.createElement("input");
                            s.type = "range"; s.className = "cb-slider"; s.min = "-10"; s.max = "10"; s.step = "0.01"; s.value = val;
                            const v = document.createElement("span");
                            v.className = "cb-slider-value"; v.textContent = val.toFixed(2);
                            s.oninput = () => v.textContent = parseFloat(s.value).toFixed(2);
                            s.onchange = () => onChange(parseFloat(s.value));
                            c.appendChild(s); c.appendChild(v);
                            return c;
                        };

                        div.appendChild(makeSlider("M", parsed.model_str, (v) => {
                             this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(parsed.name, v, parsed.clip_str);
                             this.saveState();
                        }));
                        div.appendChild(makeSlider("C", parsed.clip_str, (v) => {
                             this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(parsed.name, parsed.model_str, v);
                             this.saveState();
                        }));
                    }
                    return div;
                };

                this.renderPreviewSection = function(root) {
                    const section = document.createElement("div");
                    section.className = "cb-section full-width";
                    section.innerHTML = '<div class="cb-section-title">👁️ Config Preview (Final Output)</div>';
                    const preview = document.createElement("pre");
                    preview.className = "cb-preview";
                    preview.id = "cb-preview";
                    section.appendChild(preview);
                    root.appendChild(section);
                };

                this.updatePreview = function() {
                    const preview = this.htmlContainer.querySelector("#cb-preview");
                    if (!preview) return;
                    try { preview.textContent = JSON.stringify(this.generateOutput(), null, 2); } 
                    catch (e) { preview.textContent = `Error: ${e.message}`; }
                };

                this.generateOutput = function() {
                    const configs = [];
                    this.state.config_arrays.forEach(configArray => {
                        const split = (str) => str.split(",").map(s => s.trim()).filter(s => s);
                        
                        // Process LoRAs
                        let loras = [...configArray.loras];
                        const nonNoneLoras = loras.filter(l => l !== "None");
                        if (configArray.combine && nonNoneLoras.length > 1) {
                            const stackable = nonNoneLoras.filter(l => !l.endsWith("/"));
                            loras = stackable.length > 1 ? [stackable.join(" + ")] : nonNoneLoras;
                        } else {
                            loras = nonNoneLoras;
                        }
                        if (this.state.include_none) loras.unshift("None");

                        // Process Models
                        let models = configArray.models || ["None"];
                        let finalModels = models.filter(m => m !== "None");
                        if (this.state.include_none) finalModels.unshift("None");
                        // If no models selected/valid, ensure at least one entry if desired, or let it be empty?
                        // Usually "None" implies pass-through.
                        if (finalModels.length === 0 && this.state.include_none) finalModels = ["None"];

                        const config = {
                            sampler: split(configArray.samplers),
                            scheduler: split(configArray.schedulers),
                            steps: configArray.steps.split(",").map(s => parseFloat(s)),
                            cfg: configArray.cfg.split(",").map(s => parseFloat(s)),
                            lora: loras.length > 1 ? loras : loras[0] || "None",
                            model: finalModels.length > 1 ? finalModels : finalModels[0] || "None"
                        };
                        configs.push(config);
                    });
                    return configs;
                };

                this.loadSession = async function(sessionName) {
                    // (Session loading logic mostly same, just updating models parsing)
                    // Simplified for brevity - assumes previous robust logic handles this
                    // just ensure we map meta.model to array if single string
                    try {
                        const manifestUrl = `/view?filename=manifest.json&type=output&subfolder=benchmarks/${sessionName}&t=${Date.now()}`;
                        const resp = await fetch(manifestUrl);
                        if(!resp.ok) return;
                        const manifest = await resp.json();
                        const meta = manifest.meta || {};
                        
                        if(meta.configs_json) {
                            const configs = JSON.parse(meta.configs_json);
                            // Simple conversion
                             this.state.config_arrays = configs.map((c, i) => {
                                 // Handle Model Array conversion
                                 let m = c.model;
                                 if(!Array.isArray(m)) m = m ? [m] : ["None"];
                                 
                                 // Handle Lora logic (same as before)
                                 let l = Array.isArray(c.lora) ? c.lora : [c.lora || "None"];
                                 
                                 return {
                                    name: `Loaded Config ${i+1}`,
                                    samplers: Array.isArray(c.sampler) ? c.sampler.join(", ") : c.sampler,
                                    schedulers: Array.isArray(c.scheduler) ? c.scheduler.join(", ") : c.scheduler,
                                    steps: Array.isArray(c.steps) ? c.steps.join(", ") : c.steps,
                                    cfg: Array.isArray(c.cfg) ? c.cfg.join(", ") : c.cfg,
                                    models: m,
                                    loras: l,
                                    combine: false 
                                 };
                             });
                        }
                        this.state.session_name = sessionName;
                        this.saveState();
                        this.renderUI();
                    } catch(e) { console.error(e); }
                };

                this.renderUI();
                return result;
            };
        }
    }
});