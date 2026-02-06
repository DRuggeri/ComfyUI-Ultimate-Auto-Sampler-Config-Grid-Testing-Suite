/**
 * Web extension for Ultimate Config Builder - OPTIMIZED
 * Proper widget management and LoRA selection
 */

import { app } from "../../scripts/app.js";

// Cache for available LoRAs
let availableLoras = null;
let loraFolders = null;

// Fetch available LoRAs from ComfyUI
async function getAvailableLoras() {
    if (availableLoras) return availableLoras;
    
    try {
        const resp = await fetch("/object_info");
        const objectInfo = await resp.json();
        
        // Find LoRA selector from LoraLoader or similar nodes
        for (const nodeType in objectInfo) {
            const nodeDef = objectInfo[nodeType];
            if (nodeDef.input?.required?.lora_name) {
                const loraInput = nodeDef.input.required.lora_name;
                if (Array.isArray(loraInput) && Array.isArray(loraInput[0])) {
                    availableLoras = loraInput[0];
                    console.log(`[ConfigBuilder] Found ${availableLoras.length} LoRAs`);
                    return availableLoras;
                }
            }
        }
    } catch (e) {
        console.error("[ConfigBuilder] Error fetching LoRAs:", e);
    }
    
    availableLoras = ["None"];
    return availableLoras;
}

// Extract unique folders from LoRA paths
async function getLoraFolders() {
    if (loraFolders) return loraFolders;
    
    const loras = await getAvailableLoras();
    const folders = new Set(["/"]); // Root folder
    
    loras.forEach(lora => {
        const parts = lora.split(/[\/\\]/);
        if (parts.length > 1) {
            // Build folder path progressively
            let currentPath = "";
            for (let i = 0; i < parts.length - 1; i++) {
                currentPath += parts[i] + "/";
                folders.add(currentPath);
            }
        }
    });
    
    loraFolders = Array.from(folders).sort();
    console.log(`[ConfigBuilder] Found ${loraFolders.length} folders`);
    return loraFolders;
}

app.registerExtension({
    name: "UltimateConfigBuilder.Dynamic",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UltimateConfigBuilder") {
            console.log("[ConfigBuilder] Setting up optimized dynamic UI");

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = async function () {
                const result = onNodeCreated?.apply(this, arguments);

                // Get the lora_config widget
                const configWidget = this.widgets?.find(w => w.name === "lora_config");
                if (!configWidget) {
                    console.error("[ConfigBuilder] lora_config widget not found!");
                    return result;
                }

                // Pre-fetch LoRAs and folders
                await getAvailableLoras();
                await getLoraFolders();

                console.log("[ConfigBuilder] Found lora_config widget, setting up UI");

                // Store references
                this.configWidget = configWidget;
                this.dynamicWidgets = []; // Track all dynamic widgets for cleanup

                // Helper to get config
                this.getConfig = function () {
                    try {
                        return JSON.parse(configWidget.value);
                    } catch (e) {
                        console.error("[ConfigBuilder] Invalid JSON:", e);
                        return { arrays: [] };
                    }
                };

                // Helper to save config
                this.saveConfig = function (config) {
                    configWidget.value = JSON.stringify(config, null, 2);
                };

                // CRITICAL: Proper cleanup function
                this.cleanupDynamicWidgets = function () {
                    // Remove all dynamic widgets
                    this.dynamicWidgets.forEach(widget => {
                        const idx = this.widgets.indexOf(widget);
                        if (idx > -1) {
                            this.widgets.splice(idx, 1);
                        }
                    });
                    this.dynamicWidgets = [];
                };

                // Add a dynamic widget and track it
                this.addDynamicWidget = function (type, name, value, callback, options) {
                    const widget = this.addWidget(type, name, value, callback, options);
                    this.dynamicWidgets.push(widget);
                    return widget;
                };

                // Main refresh function
                this.refreshUI = function () {
                    console.log("[ConfigBuilder] Refreshing UI...");
                    
                    // Clean up ALL dynamic widgets first
                    this.cleanupDynamicWidgets();

                    const config = this.getConfig();

                    // Add "Add Array" button at the top
                    this.addDynamicWidget("button", "➕ Add LoRA Array", "add_array", () => {
                        const config = this.getConfig();
                        config.arrays.push({
                            name: `Array ${config.arrays.length + 1}`,
                            combine: false,
                            loras: []
                        });
                        this.saveConfig(config);
                        this.refreshUI();
                    });

                    // Render each array
                    config.arrays.forEach((array, arrayIdx) => {
                        this.renderArray(array, arrayIdx);
                    });

                    // Force node to recalculate size
                    this.setSize(this.computeSize());
                    
                    console.log("[ConfigBuilder] UI refresh complete");
                };

                // Render a single array
                this.renderArray = function (array, arrayIdx) {
                    const config = this.getConfig();

                    // Separator
                    const sep = this.addDynamicWidget("button", "═══════════════════", `sep_top_${arrayIdx}`, () => {});
                    sep.disabled = true;

                    // Array name
                    const nameWidget = this.addDynamicWidget(
                        "text",
                        `📁 Array Name`,
                        array.name,
                        (value) => {
                            const config = this.getConfig();
                            config.arrays[arrayIdx].name = value;
                            this.saveConfig(config);
                        },
                        { multiline: false }
                    );

                    // Stack toggle
                    const stackWidget = this.addDynamicWidget(
                        "toggle",
                        `Stack All (Combine)`,
                        array.combine,
                        (value) => {
                            const config = this.getConfig();
                            config.arrays[arrayIdx].combine = value;
                            this.saveConfig(config);
                        }
                    );

                    // Add LoRA button
                    this.addDynamicWidget("button", `➕ Add LoRA`, `add_lora_${arrayIdx}`, () => {
                        const config = this.getConfig();
                        config.arrays[arrayIdx].loras.push({
                            type: "lora",
                            name: "None",
                            str_model: 1.0,
                            str_clip: 1.0
                        });
                        this.saveConfig(config);
                        this.refreshUI();
                    });

                    // Render each LoRA in this array
                    array.loras.forEach((lora, loraIdx) => {
                        this.renderLora(arrayIdx, loraIdx, lora);
                    });

                    // Delete array button
                    this.addDynamicWidget("button", `🗑️ Delete Array "${array.name}"`, `delete_array_${arrayIdx}`, () => {
                        const config = this.getConfig();
                        config.arrays.splice(arrayIdx, 1);
                        this.saveConfig(config);
                        this.refreshUI();
                    });
                };

                // Render a single LoRA
                this.renderLora = function (arrayIdx, loraIdx, lora) {
                    const config = this.getConfig();
                    const loraLabel = `  LoRA ${loraIdx + 1}`;

                    // Type selector
                    this.addDynamicWidget(
                        "combo",
                        `${loraLabel} Type`,
                        lora.type,
                        (value) => {
                            const config = this.getConfig();
                            config.arrays[arrayIdx].loras[loraIdx].type = value;
                            // Update name to appropriate default
                            if (value === "folder") {
                                config.arrays[arrayIdx].loras[loraIdx].name = "/";
                            } else {
                                config.arrays[arrayIdx].loras[loraIdx].name = "None";
                            }
                            this.saveConfig(config);
                            this.refreshUI(); // Refresh to update name dropdown
                        },
                        { values: ["lora", "folder"] }
                    );

                    // Name selector (dropdown with appropriate options)
                    if (lora.type === "folder") {
                        // Folder selector
                        this.addDynamicWidget(
                            "combo",
                            `${loraLabel} Folder`,
                            lora.name,
                            (value) => {
                                const config = this.getConfig();
                                config.arrays[arrayIdx].loras[loraIdx].name = value;
                                this.saveConfig(config);
                            },
                            { values: loraFolders }
                        );
                    } else {
                        // LoRA file selector
                        this.addDynamicWidget(
                            "combo",
                            `${loraLabel} File`,
                            lora.name,
                            (value) => {
                                const config = this.getConfig();
                                config.arrays[arrayIdx].loras[loraIdx].name = value;
                                this.saveConfig(config);
                            },
                            { values: availableLoras }
                        );
                    }

                    // Model strength slider
                    this.addDynamicWidget(
                        "number",
                        `${loraLabel} Model Strength`,
                        lora.str_model,
                        (value) => {
                            const config = this.getConfig();
                            config.arrays[arrayIdx].loras[loraIdx].str_model = value;
                            this.saveConfig(config);
                        },
                        { min: -10, max: 10, step: 0.01, precision: 2 }
                    );

                    // CLIP strength slider
                    this.addDynamicWidget(
                        "number",
                        `${loraLabel} CLIP Strength`,
                        lora.str_clip,
                        (value) => {
                            const config = this.getConfig();
                            config.arrays[arrayIdx].loras[loraIdx].str_clip = value;
                            this.saveConfig(config);
                        },
                        { min: -10, max: 10, step: 0.01, precision: 2 }
                    );

                    // Delete LoRA button
                    this.addDynamicWidget("button", `${loraLabel} 🗑️ Delete`, `delete_lora_${arrayIdx}_${loraIdx}`, () => {
                        const config = this.getConfig();
                        config.arrays[arrayIdx].loras.splice(loraIdx, 1);
                        this.saveConfig(config);
                        this.refreshUI();
                    });

                    // Mini separator
                    const miniSep = this.addDynamicWidget("button", "  ─────", `sep_lora_${arrayIdx}_${loraIdx}`, () => {});
                    miniSep.disabled = true;
                };

                // Initial render
                this.refreshUI();

                // Watch for load_session changes
                const loadSessionWidget = this.widgets?.find(w => w.name === "load_session");
                if (loadSessionWidget) {
                    const originalCallback = loadSessionWidget.callback;
                    loadSessionWidget.callback = function(value) {
                        if (originalCallback) {
                            originalCallback.call(this, value);
                        }
                        
                        // If a session is selected (not "None"), trigger node execution
                        if (value && value !== "None") {
                            console.log(`[ConfigBuilder] Load session changed to: ${value}`);
                            console.log("[ConfigBuilder] Triggering execution to load session data...");
                            
                            // Queue the node for execution
                            app.queuePrompt(0, 1);
                        }
                    }.bind(loadSessionWidget);
                }

                // Handle execution results to update widgets with loaded data
                const onExecuted = this.onExecuted;
                this.onExecuted = function(message) {
                    if (onExecuted) {
                        onExecuted.apply(this, arguments);
                    }
                    
                    // Check if we have loaded values in the output
                    if (message && message.length >= 7) {
                        const [configs_json, session_name, loaded_samplers, loaded_schedulers, loaded_steps, loaded_cfg, loaded_lora_config] = message;
                        
                        console.log("[ConfigBuilder] Received loaded session data, updating widgets...");
                        
                        // Update widget values with loaded data
                        const samplersWidget = this.widgets?.find(w => w.name === "samplers");
                        const schedulersWidget = this.widgets?.find(w => w.name === "schedulers");
                        const stepsWidget = this.widgets?.find(w => w.name === "steps");
                        const cfgWidget = this.widgets?.find(w => w.name === "cfg");
                        const sessionNameWidget = this.widgets?.find(w => w.name === "session_name");
                        
                        if (samplersWidget && loaded_samplers) {
                            samplersWidget.value = loaded_samplers;
                            console.log(`[ConfigBuilder] Updated samplers: ${loaded_samplers}`);
                        }
                        if (schedulersWidget && loaded_schedulers) {
                            schedulersWidget.value = loaded_schedulers;
                            console.log(`[ConfigBuilder] Updated schedulers: ${loaded_schedulers}`);
                        }
                        if (stepsWidget && loaded_steps) {
                            stepsWidget.value = loaded_steps;
                            console.log(`[ConfigBuilder] Updated steps: ${loaded_steps}`);
                        }
                        if (cfgWidget && loaded_cfg) {
                            cfgWidget.value = loaded_cfg;
                            console.log(`[ConfigBuilder] Updated cfg: ${loaded_cfg}`);
                        }
                        if (sessionNameWidget && session_name) {
                            sessionNameWidget.value = session_name;
                            console.log(`[ConfigBuilder] Updated session_name: ${session_name}`);
                        }
                        if (this.configWidget && loaded_lora_config) {
                            this.configWidget.value = loaded_lora_config;
                            console.log(`[ConfigBuilder] Updated lora_config`);
                            
                            // Refresh UI to show loaded LoRAs
                            this.refreshUI();
                        }
                    }
                };

                console.log("[ConfigBuilder] Setup complete!");

                return result;
            };
        }
    }
});