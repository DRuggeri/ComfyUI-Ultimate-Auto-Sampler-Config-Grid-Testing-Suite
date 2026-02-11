/**
 * Config Builder Main Registration Module
 * Handles ComfyUI node registration and lifecycle
 */

import { app } from "../../../scripts/app.js";

import {
    clearAllCaches,
    refreshAllConfigBuilders,
    getActiveConfigBuilderNodes,
    normalizePath,
    parseLoraString,
    buildLoraString,
    getAvailableLoras,
    getAvailableModels,
    getLoraFolders,
    getModelFolders,
    getAvailableSessions,
    getAvailableConfigs,
    convertConfigsToConfigArrays
} from '/extensions/ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite/conf_builder/conf-builder-utilities.mjs';

import {
    renderUI,
    updatePreview
} from '/extensions/ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite/conf_builder/conf-builder-config-management.mjs';

// --- NODE REGISTRATION ---

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
                await getAvailableConfigs();

                this.configWidget = configWidget;

                // Register this node for refresh tracking
                getActiveConfigBuilderNodes().add(this);

                // UI State to track collapsed items between renders
                this.uiState = {
                    modelsSectionCollapsed: {},
                    lorasSectionCollapsed: {},
                    modelsCollapsed: {},
                    lorasCollapsed: {}
                };

                this.state = {
                    session_name: "my_test_session",
                    config_name: "default_config",
                    auto_save: false,
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
                        lora_triggerwords_append_settings: {},
                        combine: false
                    }]
                };

                // Load state
                try {
                    const existing = JSON.parse(configWidget.value);
                    if (existing.config_arrays) {
                        this.state = existing;
                        if (!this.state.config_name) this.state.config_name = "default_config";
                        if (this.state.auto_save === undefined) this.state.auto_save = false;

                        // Migration: ensure models is an array and normalize
                        this.state.config_arrays.forEach(arr => {
                            if (arr.model && !arr.models) {
                                arr.models = [arr.model];
                                delete arr.model;
                            }
                            if (!arr.models) arr.models = ["None"];
                            arr.models = arr.models.map(normalizePath);
                            arr.loras = arr.loras ? arr.loras.map(l => {
                                const p = parseLoraString(l);
                                return buildLoraString(p.name, p.model_str, p.clip_str);
                            }) : ["None"];

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
                        config_name: "default_config",
                        auto_save: false,
                        include_none: oldState.include_none !== undefined ? oldState.include_none : false,
                        config_arrays: arrays.map(arr => ({
                            name: arr.name,
                            samplers: oldState.samplers || "euler",
                            schedulers: oldState.schedulers || "normal",
                            steps: oldState.steps || "20",
                            cfg: oldState.cfg || "7.0",
                            models: oldState.model ? [normalizePath(oldState.model)] : ["None"],
                            loras: arr.loras ? arr.loras.map(l => normalizePath(l)) : ["None"],
                            lora_omit_triggers: [],
                            lora_triggerwords_append_settings: {},
                            combine: arr.combine || false
                        }))
                    };
                };

                this.autoSaveTimer = null;

                this.triggerAutoSave = function () {
                    if (this.state.auto_save && this.state.config_name) {
                        if (this.autoSaveTimer) clearTimeout(this.autoSaveTimer);
                        this.autoSaveTimer = setTimeout(() => {
                            this.saveConfigToBackend();
                        }, 2000);
                    }
                };

                this.saveState = function () {
                    configWidget.value = JSON.stringify(this.state, null, 2);
                    this.updatePreview();
                    this.triggerAutoSave();
                };

                this.saveConfigToBackend = async function () {
                    const name = this.state.config_name;
                    if (!name) return;

                    try {
                        await fetch("/configbuilder/save_config", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                name: name,
                                data: this.state
                            })
                        });
                        await getAvailableConfigs();
                    } catch (e) {
                        console.error("Save Failed", e);
                    }
                };

                this.loadConfigFromBackend = async function (filename) {
                    try {
                        const resp = await fetch("/configbuilder/load_config", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ name: filename })
                        });
                        if (resp.ok) {
                            const data = await resp.json();
                            this.state = data;
                            if (!this.state.config_name) this.state.config_name = filename.replace(".json", "");
                            if (this.state.auto_save === undefined) this.state.auto_save = false;

                            this.saveState();
                            this.renderUI();
                        }
                    } catch (e) {
                        console.error("Load failed", e);
                    }
                };

                this.htmlContainer = document.createElement("div");
                this.htmlContainer.style.cssText = `width: 100%; height: 100%; background: #1a1a1a; display: flex; flex-direction: column;`;
                this.addDOMWidget("config_ui", "div", this.htmlContainer, { serialize: false, hideOnZoom: false });

                this.updatePreview = function () {
                    updatePreview(this);
                };

                this.renderUI = async function () {
                    const availableLoras = await getAvailableLoras();
                    const availableModels = await getAvailableModels();
                    const loraFolders = await getLoraFolders();
                    const modelFolders = await getModelFolders();
                    const availableSessions = await getAvailableSessions();
                    const availableConfigs = await getAvailableConfigs();

                    await renderUI(
                        this,
                        availableLoras,
                        availableModels,
                        loraFolders,
                        modelFolders,
                        availableSessions,
                        availableConfigs,
                        refreshAllConfigBuilders
                    );
                };

                this.loadSession = async function (sessionName) {
                    console.log(`[ConfigBuilder] Loading session: ${sessionName}`);

                    const availableLoras = await getAvailableLoras();
                    const loraFolders = await getLoraFolders();
                    const availableModels = await getAvailableModels();
                    const modelFolders = await getModelFolders();

                    try {
                        const manifestUrl = `/view?filename=manifest.json&type=output&subfolder=benchmarks/${sessionName}&t=${Date.now()}`;
                        const resp = await fetch(manifestUrl);
                        if (!resp.ok) return;
                        const manifest = await resp.json();
                        const meta = manifest.meta || {};

                        if (meta.configs_json) {
                            try {
                                const configs = JSON.parse(meta.configs_json);
                                let loadedArrays = convertConfigsToConfigArrays(configs);

                                const normalize = (str) => str.replace(/\\/g, "/");

                                loadedArrays.forEach(arr => {
                                    arr.loras = arr.loras.map(loraStr => {
                                        const parsed = parseLoraString(loraStr);
                                        const normName = normalize(parsed.name);

                                        if (normName.endsWith("/") || normName.endsWith("/*")) {
                                            return buildLoraString(normName, parsed.model_str, parsed.clip_str);
                                        }

                                        const potentialFolder = normName + "/";

                                        if (loraFolders && loraFolders.includes(potentialFolder)) {
                                            return buildLoraString(potentialFolder, parsed.model_str, parsed.clip_str);
                                        }
                                        if (loraFolders && loraFolders.includes(normName)) {
                                            return buildLoraString(normName, parsed.model_str, parsed.clip_str);
                                        }

                                        return loraStr;
                                    });

                                    arr.models = arr.models.map(modelStr => {
                                        const normModel = normalize(modelStr);
                                        if (normModel.endsWith("/")) return normModel;
                                        if (modelFolders && modelFolders.includes(normModel + "/")) return normModel + "/";
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

            // Add cleanup when node is removed
            const onRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function () {
                getActiveConfigBuilderNodes().delete(this);
                if (onRemoved) {
                    onRemoved.apply(this, arguments);
                }
            };
        }
    },

    // Listen for API calls that indicate node definitions were updated
    async setup() {
        console.log("[ConfigBuilder] Setting up auto-refresh listener");

        let isRefreshing = false;

        // Hook into the app's refreshComboInNodes function if it exists
        if (app.refreshComboInNodes) {
            const originalRefresh = app.refreshComboInNodes;
            app.refreshComboInNodes = async function () {
                console.log("[ConfigBuilder] 🔄 Detected refreshComboInNodes call");

                const result = await originalRefresh.apply(this, arguments);

                if (!isRefreshing) {
                    isRefreshing = true;
                    setTimeout(async () => {
                        console.log("[ConfigBuilder] Clearing caches and refreshing nodes");
                        await refreshAllConfigBuilders();
                        isRefreshing = false;
                    }, 1000);
                }

                return result;
            };
        }

        // Also monitor fetch calls to /object_info as a backup
        const originalFetch = window.fetch;
        let lastObjectInfoTime = 0;
        window.fetch = async function (...args) {
            // 1. Check if this is an internal fetch from our own extension
            const options = args[1];
            if (options && options.headers && options.headers["X-Config-Builder-Internal"]) {
                // This is US fetching data. Pass it through without triggering the listener.
                return originalFetch.apply(this, args);
            }

            // 2. Perform the fetch
            const result = await originalFetch.apply(this, args);

            // 3. Check if it was an external /object_info call (e.g. ComfyUI Refresh button)
            if (args[0] && typeof args[0] === 'string' && args[0].includes('/object_info')) {
                const now = Date.now();
                if (now - lastObjectInfoTime > 2000 && !isRefreshing) {
                    lastObjectInfoTime = now;
                    console.log("[ConfigBuilder] 🔄 Detected EXTERNAL /object_info fetch");

                    isRefreshing = true;
                    setTimeout(async () => {
                        console.log("[ConfigBuilder] Clearing caches and refreshing nodes");
                        await refreshAllConfigBuilders();
                        isRefreshing = false;
                    }, 1000);
                }
            }

            return result;
        };

        console.log("[ConfigBuilder] Auto-refresh listener installed");
    }
});
