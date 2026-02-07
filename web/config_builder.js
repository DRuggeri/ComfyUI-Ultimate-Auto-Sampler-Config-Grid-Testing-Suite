/**
 * Ultimate Config Builder - COMPLETE HTML UI
 * - ALL inputs in HTML/JS
 * - Session loading updates everything
 * - Live JSON preview
 * - FLEX WRAP LAYOUT
 * - DYNAMIC MODEL SELECTION (Multiple Models & Folders)
 * - TRIGGER WORD LOOKUP FEATURE
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
    return `${name}:${modelStr.toFixed(2)}:${clipStr.toFixed(2)}`;
}

// Create a searchable/filterable select element
function createSearchableSelect(options, currentValue, onChange, placeholder = "Search...") {
    const container = document.createElement("div");
    container.style.position = "relative";
    container.style.width = "100%";

    const input = document.createElement("input");
    input.className = "cb-input";
    input.type = "text";
    input.placeholder = placeholder;
    input.value = currentValue || "";
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
                    include_none: false,
                    config_arrays: [{
                        name: "Config 1",
                        samplers: "euler, dpmpp_2m",
                        schedulers: "normal, karras",
                        steps: "20, 30",
                        cfg: "7.0",
                        models: ["None"],
                        loras: ["None"],
                        lora_omit_triggers: [],
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
                            if (!arr.lora_omit_triggers) arr.lora_omit_triggers = [];
                        });
                    } else if (existing.lora_config) {
                        this.state = this.migrateOldFormat(existing);
                    }
                } catch (e) { }

                this.migrateOldFormat = function (oldState) {
                    const arrays = oldState.lora_config?.arrays || [];
                    return {
                        session_name: oldState.session_name || "my_test_session",
                        include_none: oldState.include_none !== undefined ? oldState.include_none : false,
                        config_arrays: arrays.map(arr => ({
                            name: arr.name,
                            samplers: oldState.samplers || "euler",
                            schedulers: oldState.schedulers || "normal",
                            steps: oldState.steps || "20",
                            cfg: oldState.cfg || "7.0",
                            models: oldState.model ? [oldState.model] : ["None"],
                            loras: arr.loras || ["None"],
                            lora_omit_triggers: [],
                            combine: arr.combine || false
                        }))
                    };
                };

                this.saveState = function () {
                    configWidget.value = JSON.stringify(this.state, null, 2);
                    this.updatePreview();
                };

                this.htmlContainer = document.createElement("div");
                this.htmlContainer.style.cssText = `width: 100%; height: 100%; background: #1a1a1a; display: flex; flex-direction: column;`;
                this.addDOMWidget("config_ui", "div", this.htmlContainer, { serialize: false, hideOnZoom: false });

                // --- TRIGGER LOOKUP MODAL ---
                this.showTriggerLookupModal = async function(arrayIdx) {
                    const configArray = this.state.config_arrays[arrayIdx];
                    
                    // Create modal overlay
                    const overlay = document.createElement("div");
                    overlay.style.cssText = `
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0, 0, 0, 0.8);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        z-index: 10000;
                    `;

                    const modal = document.createElement("div");
                    modal.style.cssText = `
                        background: #2a2a2a;
                        border: 2px solid #0066cc;
                        border-radius: 8px;
                        padding: 20px;
                        max-width: 600px;
                        max-height: 80vh;
                        overflow-y: auto;
                        color: white;
                    `;

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

                    // Fetch triggers
                    try {
                        const loras = configArray.loras.filter(l => l && l !== "None");
                        const response = await fetch("/configbuilder/lookup_triggers", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ loras })
                        });

                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }

                        const data = await response.json();
                        const triggers = data.triggers || {};

                        status.textContent = `✅ Found triggers for ${Object.keys(triggers).length} LoRAs`;

                        // Display results
                        const selectedTriggers = new Set();

                        Object.entries(triggers).forEach(([loraName, triggerList]) => {
                            const loraSection = document.createElement("div");
                            loraSection.style.cssText = `
                                background: #333;
                                border-left: 3px solid #0066cc;
                                padding: 10px;
                                margin-bottom: 10px;
                                border-radius: 4px;
                            `;

                            const loraTitle = document.createElement("div");
                            loraTitle.textContent = loraName.split('/').pop().replace('.safetensors', '');
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
                                    triggerRow.style.cssText = `
                                        display: flex;
                                        align-items: center;
                                        gap: 8px;
                                        padding: 4px;
                                        cursor: pointer;
                                        border-radius: 3px;
                                    `;
                                    triggerRow.onmouseover = () => triggerRow.style.background = "#444";
                                    triggerRow.onmouseout = () => triggerRow.style.background = "transparent";

                                    const checkbox = document.createElement("input");
                                    checkbox.type = "checkbox";
                                    checkbox.checked = false;
                                    checkbox.onchange = () => {
                                        if (checkbox.checked) {
                                            selectedTriggers.add(trigger);
                                        } else {
                                            selectedTriggers.delete(trigger);
                                        }
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

                        // Add All button handler
                        addAllBtn.onclick = () => {
                            const existing = new Set(configArray.lora_omit_triggers);
                            selectedTriggers.forEach(t => existing.add(t));
                            this.state.config_arrays[arrayIdx].lora_omit_triggers = Array.from(existing);
                            this.saveState();
                            this.renderUI();
                            document.body.removeChild(overlay);
                        };

                    } catch (error) {
                        status.textContent = `❌ Error: ${error.message}`;
                        console.error("[ConfigBuilder] Trigger lookup error:", error);
                    }
                };

                // --- UI RENDERING ---
                this.renderUI = function () {
                    // 1. SAVE SCROLL POSITION
                    const scrollContainer = this.htmlContainer.querySelector(".cb-container");
                    const savedScrollTop = scrollContainer ? scrollContainer.scrollTop : 0;

                    this.htmlContainer.innerHTML = `
                        <style>
                            .cb-container {
                                padding: 12px;
                                height: 100%;
                                overflow-y: auto;
                                box-sizing: border-box;
                            }
                            .cb-sections-row { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
                            .cb-section { background: #2a2a2a; border-radius: 4px; padding: 12px; border: 1px solid #3a3a3a; box-sizing: border-box; flex: 1 1 300px; }
                            .cb-section.full-width { flex: 1 1 100%; width: 100%; }
                            .cb-section-title { color: #0066cc; font-size: 14px; font-weight: bold; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid #3a3a3a; }
                            .cb-flex-grid { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
                            .cb-input-group { flex: 1 1 180px; min-width: 140px; display: flex; flex-direction: column; }
                            .cb-input-group.wide { flex: 2 1 300px; }
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
                            .cb-slider-value { color: #0066cc; font-weight: bold; min-width: 45px; text-align: right; font-size: 12px; }
                            .cb-toggle { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; padding: 6px 0; }
                            .cb-preview { background: #0a0a0a; border: 1px solid #3a3a3a; border-radius: 4px; padding: 10px; margin: 10px 0; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 11px; color: #0cc; }
                            .cb-controls-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 10px; padding: 8px; background: #252525; border-radius: 4px; }
                            .cb-header-bar { display: flex; justify-content: space-between; margin-bottom: 4px; }
                        </style>
                        <div class="cb-container" id="cb-root"></div>
                    `;

                    const root = this.htmlContainer.querySelector("#cb-root");

                    const topRow = document.createElement("div");
                    topRow.className = "cb-sections-row";
                    this.renderSessionSection(topRow);
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
                        this.state.config_arrays.push({
                            name: `Config ${this.state.config_arrays.length + 1}`,
                            samplers: "euler",
                            schedulers: "normal",
                            steps: "20",
                            cfg: "7.0",
                            models: ["None"],
                            loras: ["None"],
                            lora_omit_triggers: [],
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

                    // 2. RESTORE SCROLL POSITION
                    const newScrollContainer = this.htmlContainer.querySelector(".cb-container");
                    if (newScrollContainer) {
                        newScrollContainer.scrollTop = savedScrollTop;
                    }
                };

                this.renderSessionSection = function (container) {
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

                    const loadSearchable = createSearchableSelect(
                        availableSessions,
                        "",
                        async (value) => {
                            if (value && value !== "None") {
                                await this.loadSession(value);
                            }
                        },
                        "Search sessions..."
                    );
                    grid.appendChild(this.createInputGroup("Load Session", loadSearchable));

                    section.appendChild(grid);
                    container.appendChild(section);
                };

                this.createConfigArrayElement = function (configArray, arrayIdx) {
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
                    addModelBtn.style.borderLeft = "4px solid #cc6600";
                    addModelBtn.textContent = `➕ Add Model`;
                    addModelBtn.onclick = () => {
                        if (!this.state.config_arrays[arrayIdx].models) this.state.config_arrays[arrayIdx].models = [];
                        this.state.config_arrays[arrayIdx].models.push("None");
                        this.saveState();
                        this.renderUI();
                    };
                    controlsBar.appendChild(addModelBtn);

                    const addLoraBtn = document.createElement("button");
                    addLoraBtn.className = "cb-button";
                    addLoraBtn.style.borderLeft = "4px solid #0066cc";
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

                        // --- OMIT TRIGGERS SECTION (NEW) ---
                        const omitSection = document.createElement("div");
                        omitSection.style.cssText = `
                            width: 100%;
                            background: #252525;
                            border-radius: 4px;
                            padding: 10px;
                            margin-top: 10px;
                            border-left: 3px solid #cc6600;
                        `;

                        const omitTitle = document.createElement("div");
                        omitTitle.textContent = "🚫 Omit Trigger Words";
                        omitTitle.style.cssText = "font-weight: bold; margin-bottom: 8px; color: #cc6600; font-size: 12px;";
                        omitSection.appendChild(omitTitle);

                        // Ensure lora_omit_triggers exists
                        if (!configArray.lora_omit_triggers) {
                            configArray.lora_omit_triggers = [];
                        }

                        // Chips display
                        const chipsContainer = document.createElement("div");
                        chipsContainer.style.cssText = `
                            display: flex;
                            flex-wrap: wrap;
                            gap: 6px;
                            margin-bottom: 8px;
                            min-height: 30px;
                        `;

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
                                chip.style.cssText = `
                                    display: flex;
                                    align-items: center;
                                    background: #444;
                                    color: #fff;
                                    border-radius: 12px;
                                    padding: 2px 8px;
                                    font-size: 11px;
                                `;

                                const text = document.createElement("span");
                                text.textContent = trigger;
                                chip.appendChild(text);

                                const closeBtn = document.createElement("span");
                                closeBtn.textContent = "×";
                                closeBtn.style.cssText = "margin-left: 6px; cursor: pointer; color: #ff8888; font-weight: bold;";
                                closeBtn.onclick = () => {
                                    this.state.config_arrays[arrayIdx].lora_omit_triggers.splice(tIdx, 1);
                                    this.saveState();
                                    renderChips();
                                };
                                chip.appendChild(closeBtn);
                                chipsContainer.appendChild(chip);
                            });
                        };
                        renderChips();
                        omitSection.appendChild(chipsContainer);

                        // Input & Buttons Row
                        const inputRow = document.createElement("div");
                        inputRow.style.cssText = "display: flex; gap: 8px; margin-bottom: 8px;";

                        const triggerInput = document.createElement("input");
                        triggerInput.className = "cb-input";
                        triggerInput.placeholder = "Enter trigger to omit...";
                        triggerInput.style.flex = "1";

                        // Add on Enter key
                        triggerInput.onkeydown = (e) => {
                            if (e.key === "Enter" && triggerInput.value.trim()) {
                                addTrigger();
                            }
                        };

                        const addTriggerBtn = document.createElement("button");
                        addTriggerBtn.className = "cb-button primary";
                        addTriggerBtn.textContent = "Add";
                        addTriggerBtn.style.padding = "4px 12px";

                        const addTrigger = () => {
                            const val = triggerInput.value.trim();
                            if (val && !configArray.lora_omit_triggers.includes(val)) {
                                this.state.config_arrays[arrayIdx].lora_omit_triggers.push(val);
                                this.saveState();
                                renderChips();
                                triggerInput.value = "";
                            }
                        };
                        addTriggerBtn.onclick = addTrigger;

                        inputRow.appendChild(triggerInput);
                        inputRow.appendChild(addTriggerBtn);
                        omitSection.appendChild(inputRow);

                        // --- NEW: LOOKUP BUTTON ---
                        const lookupBtn = document.createElement("button");
                        lookupBtn.className = "cb-button";
                        lookupBtn.style.cssText = `
                            width: 100%;
                            background: linear-gradient(135deg, #0066cc, #0088ff);
                            border-left: 4px solid #00aaff;
                            margin-top: 4px;
                        `;
                        lookupBtn.textContent = "🔎 Lookup Current LoRA Triggerwords For Review";
                        lookupBtn.onclick = async () => {
                            await this.showTriggerLookupModal(arrayIdx);
                        };
                        omitSection.appendChild(lookupBtn);

                        configArray.loras.forEach((lora, loraIdx) => {
                            loraGrid.appendChild(this.createLoraElement(lora, arrayIdx, loraIdx));
                        });
                        div.appendChild(loraGrid);
                        div.appendChild(omitSection);
                    }

                    return div;
                };

                // Create Model Element
                this.createModelElement = function (modelStr, arrayIdx, modelIdx) {
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

                    // Name Select (Searchable)
                    const options = isFolder ? modelFolders : availableModels;
                    const currentVal = modelStr;
                    const optionsList = (options.includes(currentVal) || currentVal === "None" || currentVal === "/") ? options : [currentVal, ...options];

                    const nameSearchable = createSearchableSelect(
                        optionsList,
                        currentVal,
                        (value) => {
                            this.state.config_arrays[arrayIdx].models[modelIdx] = value;
                            this.saveState();
                            this.renderUI();
                        },
                        isFolder ? "Search folders..." : "Search models..."
                    );
                    div.appendChild(nameSearchable);

                    // --- EXPAND BUTTON (Fixed for Windows Slashes) ---
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
                            const matchingModels = availableModels.filter(m => normalize(m).startsWith(folderPrefix));

                            if (matchingModels.length > 0) {
                                this.state.config_arrays[arrayIdx].models.splice(modelIdx, 1, ...matchingModels);
                                this.saveState();
                                this.renderUI();
                            } else {
                                alert(`No Checkpoints found in folder: ${folderPrefix}\n(Checked against ${availableModels.length} available models)`);
                            }
                        };
                        div.appendChild(expandBtn);
                    }

                    return div;
                };

                // Create LoRA Element
                this.createLoraElement = function (loraStr, arrayIdx, loraIdx) {
                    const div = document.createElement("div");
                    div.className = "cb-item-card";
                    const parsed = parseLoraString(loraStr);

                    const isFolder = parsed.name.endsWith("/") || parsed.name.endsWith("/*");
                    const isCombined = parsed.name.endsWith("/*");
                    const cleanName = isCombined ? parsed.name.slice(0, -1) : parsed.name;

                    // --- Header ---
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

                    // --- Type Selector ---
                    const typeSelect = document.createElement("select");
                    typeSelect.className = "cb-select";
                    typeSelect.innerHTML = `
                        <option value="file" ${!isFolder ? 'selected' : ''}>LoRA File</option>
                        <option value="folder" ${isFolder && !isCombined ? 'selected' : ''}>Folder (Separate)</option>
                        <option value="combined" ${isCombined ? 'selected' : ''}>Folder (Combined /*)</option>
                    `;
                    typeSelect.onchange = () => {
                        let newName = "None";
                        if (typeSelect.value === "file") newName = "None";
                        else if (typeSelect.value === "folder") newName = "/";
                        else if (typeSelect.value === "combined") newName = "/*";

                        this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(newName, 1.0, 1.0);
                        this.saveState();
                        this.renderUI();
                    };
                    div.appendChild(typeSelect);

                    // --- Name Selector (Searchable) ---
                    const options = isFolder ? loraFolders : availableLoras;
                    const currentVal = cleanName;
                    const optionsList = (options.includes(currentVal) || currentVal === "None" || currentVal === "/" || currentVal === "/*")
                        ? options
                        : [currentVal, ...options];

                    const nameSearchable = createSearchableSelect(
                        optionsList,
                        currentVal,
                        (selectedName) => {
                            const finalName = isCombined && !selectedName.endsWith("*") && selectedName !== "None"
                                ? selectedName + "*"
                                : selectedName;

                            this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(finalName, parsed.model_str, parsed.clip_str);
                            this.saveState();
                            this.renderUI();
                        },
                        isFolder ? "Search folders..." : "Search LoRAs..."
                    );
                    div.appendChild(nameSearchable);

                    // --- Sliders (Show for all types including folders) ---
                    const modelSlider = this.createSlider("Model Strength", parsed.model_str, 0, 2, 0.05, (val) => {
                        const currentName = isCombined ? cleanName + "*" : parsed.name;
                        this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, val, parsed.clip_str);
                        this.saveState();
                    });
                    div.appendChild(modelSlider);

                    const clipSlider = this.createSlider("CLIP Strength", parsed.clip_str, 0, 2, 0.05, (val) => {
                        const currentName = isCombined ? cleanName + "*" : parsed.name;
                        this.state.config_arrays[arrayIdx].loras[loraIdx] = buildLoraString(currentName, parsed.model_str, val);
                        this.saveState();
                    });
                    div.appendChild(clipSlider);

                    // --- Expand Button (Show for all folders including combined and root /) ---
                    if (isFolder && parsed.name !== "None") {
                        const expandBtn = document.createElement("button");
                        expandBtn.className = "cb-button";
                        expandBtn.style.borderLeft = "3px solid #0066cc";
                        expandBtn.style.width = "100%";
                        expandBtn.style.fontSize = "11px";
                        expandBtn.style.marginTop = "4px";
                        expandBtn.textContent = "📂 Add all individually";

                        expandBtn.onclick = () => {
                            const normalize = (str) => str.replace(/\\/g, "/");
                            
                            let matchingLoras;
                            if (cleanName === "/" || cleanName === "") {
                                // Root folder - get all LoRAs
                                matchingLoras = availableLoras;
                            } else {
                                // Specific folder
                                const folderPrefix = normalize(cleanName);
                                matchingLoras = availableLoras.filter(l => normalize(l).startsWith(folderPrefix));
                            }

                            if (matchingLoras.length > 0) {
                                const withStrengths = matchingLoras.map(l => buildLoraString(l, parsed.model_str, parsed.clip_str));
                                this.state.config_arrays[arrayIdx].loras.splice(loraIdx, 1, ...withStrengths);
                                this.saveState();
                                this.renderUI();
                            } else {
                                alert(`No LoRAs found in folder: ${cleanName || "root"}\n(Checked against ${availableLoras.length} available LoRAs)`);
                            }
                        };
                        div.appendChild(expandBtn);
                    }

                    return div;
                };

                this.createSlider = function (label, value, min, max, step, onChange) {
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

                    const valueDisplay = document.createElement("span");
                    valueDisplay.className = "cb-slider-value";
                    valueDisplay.textContent = value.toFixed(2);
                    container.appendChild(valueDisplay);

                    slider.oninput = () => {
                        const val = parseFloat(slider.value);
                        valueDisplay.textContent = val.toFixed(2);
                        onChange(val);
                    };

                    return container;
                };

                this.createInputGroup = function (label, element) {
                    const group = document.createElement("div");
                    group.className = "cb-input-group";

                    const labelElem = document.createElement("label");
                    labelElem.className = "cb-label";
                    labelElem.textContent = label;
                    group.appendChild(labelElem);

                    group.appendChild(element);
                    return group;
                };

                this.renderPreviewSection = function (container) {
                    const section = document.createElement("div");
                    section.className = "cb-section full-width";
                    section.innerHTML = '<div class="cb-section-title">📄 JSON Preview</div>';

                    const preview = document.createElement("pre");
                    preview.className = "cb-preview";
                    preview.id = "json-preview";
                    section.appendChild(preview);

                    container.appendChild(section);
                };

                this.updatePreview = function () {
                    const preview = this.htmlContainer.querySelector("#json-preview");
                    if (!preview) return;

                    const configs = this.convertStateToConfigs();
                    preview.textContent = JSON.stringify(configs, null, 2);
                };

                this.convertStateToConfigs = function () {
                    const configs = [];
                    const split = (str) => str.split(",").map(s => s.trim()).filter(s => s);

                    this.state.config_arrays.forEach(configArray => {
                        // Process LoRAs
                        let loras = configArray.loras.filter(l => l && l !== "None");
                        if (this.state.include_none || loras.length === 0) {
                            loras = ["None", ...loras];
                        }

                        // Process Models
                        let finalModels = configArray.models?.filter(m => m && m !== "None") || [];
                        if (this.state.include_none || finalModels.length === 0) {
                            finalModels = ["None", ...finalModels];
                        }

                        const config = {
                            sampler: split(configArray.samplers),
                            scheduler: split(configArray.schedulers),
                            steps: configArray.steps.split(",").map(s => parseFloat(s)),
                            cfg: configArray.cfg.split(",").map(s => parseFloat(s)),
                            lora: loras.length > 1 ? loras : loras[0] || "None",
                            model: finalModels.length > 1 ? finalModels : finalModels[0] || "None",
                            lora_omit_triggers: configArray.lora_omit_triggers || []
                        };
                        configs.push(config);
                    });
                    return configs;
                };

                this.convertConfigsToConfigArrays = function (configs) {
                    if (!configs || !Array.isArray(configs)) {
                        return [{
                            name: "Config 1",
                            samplers: "euler",
                            schedulers: "normal",
                            steps: "20",
                            cfg: "7.0",
                            models: ["None"],
                            loras: ["None"],
                            lora_omit_triggers: [],
                            combine: false
                        }];
                    }

                    const configArrays = [];

                    const toString = (val) => {
                        if (Array.isArray(val)) return val.join(", ");
                        return String(val !== undefined && val !== null ? val : "");
                    };

                    configs.forEach((config, idx) => {
                        const loraValue = config.lora;
                        const loras = [];
                        let hasCombined = false;
                        let loraList = [];

                        if (typeof loraValue === 'string') loraList = [loraValue];
                        else if (Array.isArray(loraValue)) loraList = loraValue;
                        else loraList = ["None"];

                        loraList.forEach(loraStr => {
                            if (!loraStr || loraStr === "None") {
                                loras.push("None");
                            } else if (loraStr.includes(" + ")) {
                                hasCombined = true;
                                const parts = loraStr.split(" + ");
                                parts.forEach(part => loras.push(part.trim()));
                            } else {
                                loras.push(loraStr);
                            }
                        });

                        let models = config.model;
                        if (!Array.isArray(models)) models = models ? [models] : ["None"];

                        let omitTriggers = config.lora_omit_triggers;
                        if (!Array.isArray(omitTriggers)) omitTriggers = [];

                        configArrays.push({
                            name: `Loaded Config ${idx + 1}`,
                            samplers: toString(config.sampler || "euler"),
                            schedulers: toString(config.scheduler || "normal"),
                            steps: toString(config.steps || "20"),
                            cfg: toString(config.cfg || "7.0"),
                            models: models,
                            loras: loras,
                            lora_omit_triggers: omitTriggers,
                            combine: hasCombined
                        });
                    });

                    return configArrays.length > 0 ? configArrays : [{
                        name: "Config 1",
                        samplers: "euler",
                        schedulers: "normal",
                        steps: "20",
                        cfg: "7.0",
                        models: ["None"],
                        loras: ["None"],
                        lora_omit_triggers: [],
                        combine: false
                    }];
                };

                this.loadSession = async function (sessionName) {
                    console.log(`[ConfigBuilder] Loading session: ${sessionName}`);

                    if (!availableLoras) await getAvailableLoras();
                    if (!loraFolders) await getLoraFolders();
                    if (!availableModels) await getAvailableModels();
                    if (!modelFolders) await getModelFolders();

                    try {
                        const manifestUrl = `/view?filename=manifest.json&type=output&subfolder=benchmarks/${sessionName}&t=${Date.now()}`;
                        const resp = await fetch(manifestUrl);
                        if (!resp.ok) return;
                        const manifest = await resp.json();
                        const meta = manifest.meta || {};

                        if (meta.configs_json) {
                            try {
                                const configs = JSON.parse(meta.configs_json);
                                let loadedArrays = this.convertConfigsToConfigArrays(configs);

                                const normalize = (str) => str.replace(/\\/g, "/");

                                loadedArrays.forEach(arr => {
                                    arr.loras = arr.loras.map(loraStr => {
                                        const parsed = parseLoraString(loraStr);
                                        const normName = normalize(parsed.name);

                                        if (normName.endsWith("/") || normName.endsWith("/*")) {
                                            return buildLoraString(normName, parsed.model_str, parsed.clip_str);
                                        }

                                        const potentialFolder = normName + "/";

                                        if (loraFolders.includes(potentialFolder)) {
                                            return buildLoraString(potentialFolder, parsed.model_str, parsed.clip_str);
                                        }
                                        if (loraFolders.includes(normName)) {
                                            return buildLoraString(normName, parsed.model_str, parsed.clip_str);
                                        }

                                        return loraStr;
                                    });

                                    arr.models = arr.models.map(modelStr => {
                                        const normModel = normalize(modelStr);

                                        if (normModel.endsWith("/")) return normModel;

                                        if (modelFolders.includes(normModel + "/")) {
                                            return normModel + "/";
                                        }

                                        return normModel;
                                    });
                                });

                                this.state.config_arrays = loadedArrays;

                            } catch (e) {
                                console.error("[ConfigBuilder] Error parsing configs_json:", e);
                            }
                        }

                        this.state.session_name = sessionName;
                        this.saveState();
                        this.renderUI();
                    } catch (e) {
                        console.error("[ConfigBuilder] Error loading session:", e);
                    }
                };

                this.renderUI();
                return result;
            };
        }
    }
});