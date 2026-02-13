/**
 * Config Builder Utilities Module
 * Handles data fetching, caching, path normalization, and parsing
 */

// Cache for available resources
let availableLoras = null;
let loraFolders = null;
let availableModels = null;
let modelFolders = null;
let availableSessions = ["None"];
let availableConfigs = ["None"];

// Track all active ConfigBuilder nodes for refresh
let activeConfigBuilderNodes = new Set();

// --- CACHE MANAGEMENT ---

export function clearAllCaches() {
    console.log("[ConfigBuilder] 🔄 Clearing all caches...");
    availableLoras = null;
    loraFolders = null;
    availableModels = null;
    modelFolders = null;
}

export async function refreshAllConfigBuilders() {
    console.log("[ConfigBuilder] 🔄 Refreshing all Config Builder nodes...");
    clearAllCaches();
    
    // Refresh each active node
    for (const node of activeConfigBuilderNodes) {
        if (node && node.renderUI) {
            console.log("[ConfigBuilder] Refreshing node:", node.id);
            await node.renderUI();
        }
    }
}

export function getActiveConfigBuilderNodes() {
    return activeConfigBuilderNodes;
}

// --- PATH NORMALIZATION ---

export function normalizePath(path) {
    if (!path) return "";
    return path.replace(/\\/g, "/");
}

export function getShortName(path) {
    if (!path || path === "None") return "None";
    const normalized = normalizePath(path);
    const parts = normalized.split("/");
    return parts[parts.length - 1] || parts[parts.length - 2] || path;
}

// --- DATA FETCHING ---

export async function getAvailableLoras() {
    if (availableLoras) return availableLoras;
    try {
        const resp = await fetch("/object_info", { headers: { "X-Config-Builder-Internal": "true" } });
        const objectInfo = await resp.json();
        for (const nodeType in objectInfo) {
            const nodeDef = objectInfo[nodeType];
            if (nodeDef.input?.required?.lora_name) {
                const loraInput = nodeDef.input.required.lora_name;
                if (Array.isArray(loraInput) && Array.isArray(loraInput[0])) {
                    // Normalize immediately upon fetch
                    availableLoras = loraInput[0].map(normalizePath);
                    return availableLoras;
                }
            }
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching LoRAs:", e); }
    availableLoras = ["None"];
    return availableLoras;
}

export async function getAvailableModels() {
    if (availableModels) return availableModels;
    try {
        const resp = await fetch("/object_info", { headers: { "X-Config-Builder-Internal": "true" } });
        const objectInfo = await resp.json();
        // Look for standard CheckpointLoaderSimple or similar
        const loaderNode = objectInfo["CheckpointLoaderSimple"] || objectInfo["CheckpointLoader"];
        if (loaderNode?.input?.required?.ckpt_name) {
            const modelInput = loaderNode.input.required.ckpt_name;
            if (Array.isArray(modelInput) && Array.isArray(modelInput[0])) {
                // Normalize immediately upon fetch
                availableModels = modelInput[0].map(normalizePath);
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

export async function getLoraFolders() {
    if (loraFolders) return loraFolders;
    const loras = await getAvailableLoras();
    loraFolders = extractFolders(loras);
    return loraFolders;
}

export async function getModelFolders() {
    if (modelFolders) return modelFolders;
    const models = await getAvailableModels();
    modelFolders = extractFolders(models);
    return modelFolders;
}

export async function getAvailableSessions() {
    try {
        const resp = await fetch("/object_info", { headers: { "X-Config-Builder-Internal": "true" } });
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

export async function getAvailableConfigs() {
    try {
        const resp = await fetch("/configbuilder/list_configs");
        if (resp.ok) {
            const files = await resp.json();
            availableConfigs = files.length > 0 ? files : ["None"];
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching configs:", e); }
    return availableConfigs;
}

// --- LORA PARSING ---

export function parseLoraString(loraStr) {
    const norm = normalizePath(loraStr);
    if (!norm || norm === "None") return { name: "None", model_str: 1.0, clip_str: 1.0 };
    if (norm.endsWith("/")) return { name: norm, model_str: 1.0, clip_str: 1.0 };
    const parts = norm.split(":");
    return {
        name: parts[0] || "None",
        model_str: parts.length > 1 ? parseFloat(parts[1]) : 1.0,
        clip_str: parts.length > 2 ? parseFloat(parts[2]) : 1.0
    };
}

export function buildLoraString(name, modelStr, clipStr) {
    if (!name || name === "None") return "None";
    const norm = normalizePath(name);
    return `${norm}:${modelStr.toFixed(2)}:${clipStr.toFixed(2)}`;
}

// --- ITERATION COUNT CALCULATION ---

export function getIterationCount(configArray) {
    // 1. Params
    const countSplit = (str) => str.split(",").map(s => s.trim()).filter(s => s).length || 1;
    const s_count = countSplit(configArray.samplers);
    const sch_count = countSplit(configArray.schedulers);
    const st_count = countSplit(configArray.steps);
    const c_count = countSplit(configArray.cfg);

    // 2. Models
    let m_count = 0;
    if (!configArray.models || configArray.models.length === 0) {
        m_count = 1; // Defaults to None
    } else {
        configArray.models.forEach(m => {
            if (m === "None") {
                m_count += 1;
            } else if (m.endsWith("/")) {
                // Folder
                const norm = normalizePath(m);
                if (norm === "/" || norm === "") {
                    m_count += availableModels ? availableModels.length : 1;
                } else {
                    m_count += availableModels ? availableModels.filter(am => normalizePath(am).startsWith(norm)).length : 1;
                }
            } else {
                // Single
                m_count += 1;
            }
        });
    }
    if (m_count === 0) m_count = 1;

    // 3. LoRAs
    let l_count = 0;
    if (!configArray.loras || configArray.loras.length === 0) {
        l_count = 1;
    } else {
        configArray.loras.forEach(l => {
            const parsed = parseLoraString(l);
            const name = parsed.name;
            if (name === "None") {
                l_count += 1;
            } else if (name.endsWith("/*")) {
                // Combined Folder -> 1 iteration (Single Stack)
                l_count += 1;
            } else if (name.endsWith("/")) {
                // Separate Folder -> N iterations
                const norm = normalizePath(name);
                if (norm === "/" || norm === "") {
                    l_count += availableLoras ? availableLoras.length : 1;
                } else {
                    l_count += availableLoras ? availableLoras.filter(al => normalizePath(al).startsWith(norm)).length : 1;
                }
            } else {
                // Single File -> 1 iteration
                l_count += 1;
            }
        });
    }
    if (l_count === 0) l_count = 1;

    return m_count * l_count * s_count * sch_count * st_count * c_count;
}

// --- CONFIG CONVERSION ---

export function convertStateToConfigs(state) {
    const configs = [];
    const split = (str) => str.split(",").map(s => s.trim()).filter(s => s);

    state.config_arrays.forEach(configArray => {
        // Process LoRAs - FIXED VERSION
        let loras = configArray.loras.filter(l => l && l !== "None");
        
        // Convert loras array to proper format
        let loraValue;
        if (loras.length === 0) {
            loraValue = "None";
        } else if (loras.length === 1) {
            loraValue = loras[0];
        } else {
            // Multiple loras: combine with " + " separator
            loraValue = loras.join(" + ");
        }

        // Process Models
        let finalModels = configArray.models?.filter(m => m && m !== "None") || [];

        const config = {
            sampler: split(configArray.samplers),
            scheduler: split(configArray.schedulers),
            steps: configArray.steps.split(",").map(s => parseInt(s)),
            cfg: configArray.cfg.split(",").map(s => parseFloat(s)),
            lora: loraValue,
            model: finalModels.length > 1 ? finalModels : finalModels[0] || "None"
        };

        // Add lora_omit_triggers if present
        if (configArray.lora_omit_triggers && configArray.lora_omit_triggers.length > 0) {
            config.lora_omit_triggers = configArray.lora_omit_triggers;
        }

        // Add lora_triggerwords_append_settings if any placements are configured
        if (configArray.lora_triggerwords_append_settings && Object.keys(configArray.lora_triggerwords_append_settings).length > 0) {
            const settings = {};
            for (const [loraName, placement] of Object.entries(configArray.lora_triggerwords_append_settings)) {
                if (placement !== "none") {
                    settings[loraName] = placement;
                }
            }
            if (Object.keys(settings).length > 0) {
                config.lora_triggerwords_append_settings = settings;
            }
        }

        // Add lora_bypass_states if any are set
        if (configArray.lora_bypass_states && Object.keys(configArray.lora_bypass_states).length > 0) {
            config.lora_bypass_states = configArray.lora_bypass_states;
        }

        // Add lora_strength_lock if any are set
        if (configArray.lora_strength_lock && Object.keys(configArray.lora_strength_lock).length > 0) {
            config.lora_strength_lock = configArray.lora_strength_lock;
        }

        configs.push(config);
    });
    return configs;
}

export function convertConfigsToConfigArrays(configs) {
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
            lora_triggerwords_append_settings: {},
            lora_bypass_states: {},
            lora_strength_lock: {},
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
        let loras = [];
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

        // Normalize loaded models
        models = models.map(normalizePath);
        // Normalize loaded loras
        loras = loras.map(normalizePath);

        let omitTriggers = config.lora_omit_triggers;
        if (!Array.isArray(omitTriggers)) omitTriggers = [];

        // Load lora_triggerwords_append_settings
        let triggerPlacements = {};
        if (config.lora_triggerwords_append_settings && typeof config.lora_triggerwords_append_settings === 'object') {
            triggerPlacements = { ...config.lora_triggerwords_append_settings };
        }

        // Load lora_bypass_states
        let bypassStates = {};
        if (config.lora_bypass_states && typeof config.lora_bypass_states === 'object') {
            bypassStates = { ...config.lora_bypass_states };
        }

        // Load lora_strength_lock
        let strengthLock = {};
        if (config.lora_strength_lock && typeof config.lora_strength_lock === 'object') {
            strengthLock = { ...config.lora_strength_lock };
        }

        configArrays.push({
            name: `Loaded Config ${idx + 1}`,
            samplers: toString(config.sampler || "euler"),
            schedulers: toString(config.scheduler || "normal"),
            steps: toString(config.steps || "20"),
            cfg: toString(config.cfg || "7.0"),
            models: models,
            loras: loras,
            lora_omit_triggers: omitTriggers,
            lora_triggerwords_append_settings: triggerPlacements,
            lora_bypass_states: bypassStates,
            lora_strength_lock: strengthLock,
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
        lora_triggerwords_append_settings: {},
        lora_bypass_states: {},
        lora_strength_lock: {},
        combine: false
    }];
}