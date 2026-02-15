/**
 * Config Builder Utilities Module
 * Handles data fetching, caching, path normalization, and parsing
 */

// Cache for available resources
let availableLoras = null;
let loraFolders = null;
let availableModels = null;
let modelFolders = null;
let availableDiffusionModels = null;
let diffusionModelFolders = null;
let availableGGUFModels = null;
let ggufModelFolders = null;
let availableTextEncoders = null;
let textEncoderFolders = null;
let clipTypes = [];
let dualClipTypes = [];
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
    availableDiffusionModels = null;
    diffusionModelFolders = null;
    availableGGUFModels = null;
    ggufModelFolders = null;
    availableTextEncoders = null;
    textEncoderFolders = null;
    clipTypes = [];
    dualClipTypes = [];
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

// --- UNIFIED MODEL LISTS (for GGUF, Diffusion Models, Text Encoders) ---

export async function getModelLists() {
    // Fetch all model lists from the unified endpoint
    try {
        const resp = await fetch("/configbuilder/model_lists", {
            headers: { "X-Config-Builder-Internal": "true" }
        });
        const data = await resp.json();

        if (data.checkpoints) {
            availableModels = data.checkpoints.map(normalizePath);
            modelFolders = extractFolders(availableModels);
        }
        availableDiffusionModels = (data.diffusion_models || []).map(normalizePath);
        diffusionModelFolders = extractFolders(availableDiffusionModels);
        availableGGUFModels = (data.unet_gguf || []).map(normalizePath);
        ggufModelFolders = extractFolders(availableGGUFModels);

        // Combine text_encoders and clip_gguf, deduplicate
        const teSet = new Set([
            ...(data.text_encoders || []).map(normalizePath),
            ...(data.clip_gguf || []).map(normalizePath)
        ]);
        availableTextEncoders = Array.from(teSet).sort();
        textEncoderFolders = extractFolders(availableTextEncoders);

        clipTypes = data.clip_types || [];
        dualClipTypes = data.dual_clip_types || [];

        console.log(`[ConfigBuilder] Model lists: ${availableModels?.length || 0} checkpoints, ` +
            `${availableDiffusionModels.length} diffusion, ${availableGGUFModels.length} GGUF, ` +
            `${availableTextEncoders.length} text encoders`);
        return data;
    } catch (e) {
        console.error("[ConfigBuilder] Error fetching model lists:", e);
        return {};
    }
}

export function getAvailableDiffusionModels() { return availableDiffusionModels || []; }
export function getDiffusionModelFolders() { return diffusionModelFolders || ["/"]; }
export function getAvailableGGUFModels() { return availableGGUFModels || []; }
export function getGGUFModelFolders() { return ggufModelFolders || ["/"]; }
export function getAvailableTextEncoders() { return availableTextEncoders || []; }
export function getTextEncoderFolders() { return textEncoderFolders || ["/"]; }
export function getClipTypes() { return clipTypes; }
export function getDualClipTypes() { return dualClipTypes; }

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

// --- PROMPT HELPER FUNCTIONS ---

/**
 * Count the number of Cartesian product combinations from nested prompt groups.
 * Each group is an array of variations. The total is the product of all group sizes.
 * Example: [["a", "b"], ["c"]] = 2 * 1 = 2 combinations
 */
export function countPromptCombinations(groups) {
    if (!groups || !Array.isArray(groups) || groups.length === 0) return 1;
    // Filter out empty groups
    const validGroups = groups.filter(g => Array.isArray(g) && g.length > 0);
    if (validGroups.length === 0) return 1;
    return validGroups.reduce((total, group) => total * group.length, 1);
}

/**
 * Generate preview of expanded prompt combinations from nested groups.
 * Returns array of strings, capped at `limit` entries.
 * Example: [["a", "b"], ["1", "2"]] -> ["a, 1", "a, 2", "b, 1", "b, 2"]
 */
export function expandPromptPreview(groups, limit = 20) {
    if (!groups || !Array.isArray(groups) || groups.length === 0) return [];
    const validGroups = groups.filter(g => Array.isArray(g) && g.length > 0);
    if (validGroups.length === 0) return [];

    // Iterative Cartesian product with early cutoff
    let combinations = [[]];
    for (const group of validGroups) {
        const newCombinations = [];
        for (const existing of combinations) {
            for (const item of group) {
                newCombinations.push([...existing, item]);
                if (newCombinations.length > limit) {
                    return newCombinations.slice(0, limit).map(combo => combo.join(", "));
                }
            }
        }
        combinations = newCombinations;
    }
    return combinations.map(combo => combo.join(", "));
}

// --- ITERATION COUNT CALCULATION ---

export function getIterationCount(configArray) {
    // 1. Params
    const countSplit = (str) => str.split(",").map(s => s.trim()).filter(s => s).length || 1;
    const s_count = countSplit(configArray.samplers);
    const sch_count = countSplit(configArray.schedulers);
    const st_count = countSplit(configArray.steps);
    const c_count = countSplit(configArray.cfg);

    // 2. Models (handles both string format and object format {path, type})
    let m_count = 0;
    if (!configArray.models || configArray.models.length === 0) {
        m_count = 1; // Defaults to None
    } else {
        configArray.models.forEach(m => {
            const modelPath = typeof m === 'string' ? m : (m?.path || "None");
            const modelType = typeof m === 'string' ? 'checkpoint' : (m?.type || 'checkpoint');

            // Pick the correct file list for folder expansion
            let modelList;
            if (modelType === 'gguf') modelList = availableGGUFModels;
            else if (modelType === 'diffusion_model') modelList = availableDiffusionModels;
            else modelList = availableModels;

            if (modelPath === "None") {
                m_count += 1;
            } else if (modelPath.endsWith("/")) {
                const norm = normalizePath(modelPath);
                if (norm === "/" || norm === "") {
                    m_count += modelList ? modelList.length : 1;
                } else {
                    m_count += modelList ? modelList.filter(am => normalizePath(am).startsWith(norm)).length : 1;
                }
            } else {
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

    // 4. Prompts (per-config custom prompts multiply the iteration count)
    let p_count = 1;
    if (configArray.use_custom_prompts && configArray.positive_prompt_groups && configArray.positive_prompt_groups.length > 0) {
        p_count = countPromptCombinations(configArray.positive_prompt_groups);
    }

    return m_count * l_count * s_count * sch_count * st_count * c_count * p_count;
}

// --- CONFIG CONVERSION ---

export function convertStateToConfigs(state) {
    const configs = [];
    const split = (str) => str.split(",").map(s => s.trim()).filter(s => s);

    // Global prompts from state (used when per-config prompts not set)
    const globalPositiveGroups = state.global_positive_groups || [];
    const globalNegative = state.global_negative || "";

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

        // Process Models - handle object format {path, type} and string format
        let modelType = "checkpoint";
        let finalModels = [];
        (configArray.models || []).forEach(m => {
            if (typeof m === 'object' && m !== null) {
                if (m.path && m.path !== "None") {
                    finalModels.push(m.path);
                    modelType = m.type || "checkpoint";
                }
            } else if (typeof m === 'string' && m && m !== "None") {
                finalModels.push(m);
            }
        });

        const config = {
            sampler: split(configArray.samplers),
            scheduler: split(configArray.schedulers),
            steps: configArray.steps.split(",").map(s => parseInt(s)),
            cfg: configArray.cfg.split(",").map(s => parseFloat(s)),
            lora: loraValue,
            model: finalModels.length > 1 ? finalModels : finalModels[0] || "None"
        };

        // Add model_type and related fields for non-checkpoint models
        if (modelType !== "checkpoint") {
            config.model_type = modelType;
            const textEncoders = (configArray.text_encoders || []).filter(te => te && te !== "None");
            if (textEncoders.length > 0) config.text_encoders = textEncoders;
            if (configArray.clip_type) config.clip_type = configArray.clip_type;
            if (modelType === "gguf" && configArray.gguf_options) {
                config.gguf_options = configArray.gguf_options;
            }
        }

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

        // Add seed_behavior if set to randomize
        if (configArray.seed_behavior === "randomize") {
            config.seed_behavior = "randomize";
        }

        // ==== PROMPT HANDLING ====
        // Priority: per-config > global > omit (node inputs used as fallback)
        if (configArray.use_custom_prompts && configArray.positive_prompt_groups && configArray.positive_prompt_groups.length > 0) {
            config.positive = configArray.positive_prompt_groups;
            if (configArray.negative_prompt) {
                config.negative = configArray.negative_prompt;
            }
        } else if (globalPositiveGroups.length > 0) {
            config.positive = globalPositiveGroups;
            if (globalNegative) {
                config.negative = globalNegative;
            }
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
            seed_behavior: "fixed",
            models: ["None"],
            text_encoders: [],
            clip_type: "stable_diffusion",
            gguf_options: {},
            loras: ["None"],
            lora_omit_triggers: [],
            lora_triggerwords_append_settings: {},
            lora_bypass_states: {},
            lora_strength_lock: {},
            combine: false,
            positive_prompt_groups: [],
            negative_prompt: "",
            use_custom_prompts: false
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

        // Determine model type from config
        const loadedModelType = config.model_type || "checkpoint";

        // Convert models to object format if non-checkpoint, keep string for checkpoint
        if (loadedModelType !== "checkpoint") {
            models = models.map(m => ({ path: normalizePath(m), type: loadedModelType }));
        } else {
            models = models.map(normalizePath);
        }

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

        // Parse prompt fields from loaded config
        let positivePromptGroups = [];
        let negativePrompt = "";
        let useCustomPrompts = false;

        if (config.positive) {
            // Config has per-config prompts
            useCustomPrompts = true;
            if (Array.isArray(config.positive)) {
                // Could be nested array [["a", "b"], ["c"]] or simple array ["a", "b"]
                if (config.positive.length > 0 && Array.isArray(config.positive[0])) {
                    // Nested array format - use as-is
                    positivePromptGroups = config.positive;
                } else {
                    // Simple array - wrap as single group
                    positivePromptGroups = [config.positive];
                }
            } else if (typeof config.positive === 'string' && config.positive.trim()) {
                // Plain string - wrap as single variation in single group
                positivePromptGroups = [[config.positive]];
            }
        }

        if (config.negative) {
            if (typeof config.negative === 'string') {
                negativePrompt = config.negative;
            } else if (Array.isArray(config.negative)) {
                negativePrompt = JSON.stringify(config.negative);
            }
        }

        configArrays.push({
            name: `Loaded Config ${idx + 1}`,
            samplers: toString(config.sampler || "euler"),
            schedulers: toString(config.scheduler || "normal"),
            steps: toString(config.steps || "20"),
            cfg: toString(config.cfg || "7.0"),
            seed_behavior: config.seed_behavior || "fixed",
            models: models,
            text_encoders: config.text_encoders || [],
            clip_type: config.clip_type || "stable_diffusion",
            gguf_options: config.gguf_options || {},
            loras: loras,
            lora_omit_triggers: omitTriggers,
            lora_triggerwords_append_settings: triggerPlacements,
            lora_bypass_states: bypassStates,
            lora_strength_lock: strengthLock,
            combine: hasCombined,
            positive_prompt_groups: positivePromptGroups,
            negative_prompt: negativePrompt,
            use_custom_prompts: useCustomPrompts
        });
    });

    return configArrays.length > 0 ? configArrays : [{
        name: "Config 1",
        samplers: "euler",
        schedulers: "normal",
        steps: "20",
        cfg: "7.0",
        seed_behavior: "fixed",
        models: ["None"],
        text_encoders: [],
        clip_type: "stable_diffusion",
        gguf_options: {},
        loras: ["None"],
        lora_omit_triggers: [],
        lora_triggerwords_append_settings: {},
        lora_bypass_states: {},
        lora_strength_lock: {},
        combine: false,
        positive_prompt_groups: [],
        negative_prompt: "",
        use_custom_prompts: false
    }];
}