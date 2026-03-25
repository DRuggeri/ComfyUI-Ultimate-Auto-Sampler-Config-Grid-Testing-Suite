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
let availableVAEs = null;
let vaeFolders = null;
let availableUpscaleModels = [];
let upscaleModelFolders = ["/"];
let clipTypes = [];
let dualClipTypes = [];
let availableSamplers = [];
let availableSchedulers = [];
let availableSessions = ["None"];
let availableConfigs = ["None"];

// Cache-loaded flags for fetchers that can't use null-check
// (their initial values are already non-null arrays)
let _modelListsLoaded = false;
let _sessionsLoaded = false;
let _configsLoaded = false;

// Track all active ConfigBuilder nodes for refresh
let activeConfigBuilderNodes = new Set();

// --- localStorage PERSISTENT CACHE ---
const LS_CACHE_KEY = "uscg_model_cache";
const LS_COUNTS_KEY = "uscg_model_counts";

function _saveToLocalStorage() {
    try {
        const data = {
            ts: Date.now(),
            availableLoras, loraFolders, availableModels, modelFolders,
            availableDiffusionModels, diffusionModelFolders,
            availableGGUFModels, ggufModelFolders,
            availableTextEncoders, textEncoderFolders,
            availableVAEs, vaeFolders, availableUpscaleModels, upscaleModelFolders,
            clipTypes, dualClipTypes, availableSamplers, availableSchedulers
        };
        localStorage.setItem(LS_CACHE_KEY, JSON.stringify(data));
    } catch (e) { /* localStorage may be full or unavailable */ }
}

function _loadFromLocalStorage() {
    try {
        const raw = localStorage.getItem(LS_CACHE_KEY);
        if (!raw) return false;
        const data = JSON.parse(raw);
        // Only use cache from last 24 hours
        if (Date.now() - data.ts > 86400000) return false;
        availableLoras = data.availableLoras;
        loraFolders = data.loraFolders;
        availableModels = data.availableModels;
        modelFolders = data.modelFolders;
        availableDiffusionModels = data.availableDiffusionModels || [];
        diffusionModelFolders = data.diffusionModelFolders || ["/"];
        availableGGUFModels = data.availableGGUFModels || [];
        ggufModelFolders = data.ggufModelFolders || ["/"];
        availableTextEncoders = data.availableTextEncoders || [];
        textEncoderFolders = data.textEncoderFolders || ["/"];
        availableVAEs = data.availableVAEs || [];
        vaeFolders = data.vaeFolders || ["/"];
        availableUpscaleModels = data.availableUpscaleModels || [];
        upscaleModelFolders = data.upscaleModelFolders || ["/"];
        clipTypes = data.clipTypes || [];
        dualClipTypes = data.dualClipTypes || [];
        availableSamplers = data.availableSamplers || [];
        availableSchedulers = data.availableSchedulers || [];
        _modelListsLoaded = true;
        console.log("[ConfigBuilder] ⚡ Loaded model cache from localStorage");
        return true;
    } catch (e) { return false; }
}

// --- BACKGROUND COUNT POLLING ---
let _countPollInterval = null;
let _lastKnownCounts = null;

export function startModelCountPolling(onChangedCallback) {
    if (_countPollInterval) return; // Already polling
    _countPollInterval = setInterval(async () => {
        try {
            const resp = await fetch("/configbuilder/model_counts");
            const counts = await resp.json();
            if (_lastKnownCounts) {
                let changed = false;
                for (const key of Object.keys(counts)) {
                    if (counts[key] !== _lastKnownCounts[key]) {
                        console.log(`[ConfigBuilder] 🔍 ${key} changed: ${_lastKnownCounts[key]} → ${counts[key]}`);
                        changed = true;
                    }
                }
                if (changed && onChangedCallback) {
                    onChangedCallback(counts);
                }
            }
            _lastKnownCounts = counts;
        } catch (e) { /* ignore poll errors */ }
    }, 30000); // Check every 30 seconds
}

export function stopModelCountPolling() {
    if (_countPollInterval) { clearInterval(_countPollInterval); _countPollInterval = null; }
}

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
    availableVAEs = null;
    vaeFolders = null;
    clipTypes = [];
    dualClipTypes = [];
    availableSamplers = [];
    availableSchedulers = [];
    _modelListsLoaded = false;
    _sessionsLoaded = false;
    _configsLoaded = false;
    _objectInfoCache = null;
    _objectInfoPromise = null;
    try { localStorage.removeItem(LS_CACHE_KEY); } catch (e) {}
}

// Try to restore from localStorage immediately (before any fetches)
_loadFromLocalStorage();

// Targeted cache invalidation for when specific data changes
export function clearConfigsCache() { _configsLoaded = false; }
export function clearSessionsCache() { _sessionsLoaded = false; }

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

// Shared /object_info cache to avoid redundant fetches
let _objectInfoCache = null;
let _objectInfoPromise = null;

async function _getObjectInfo() {
    if (_objectInfoCache) return _objectInfoCache;
    if (_objectInfoPromise) return _objectInfoPromise;
    _objectInfoPromise = fetch("/object_info", { headers: { "X-Config-Builder-Internal": "true" } })
        .then(r => r.json())
        .then(data => { _objectInfoCache = data; _objectInfoPromise = null; return data; })
        .catch(e => { _objectInfoPromise = null; throw e; });
    return _objectInfoPromise;
}

export async function getAvailableLoras() {
    if (availableLoras) return availableLoras;
    try {
        const objectInfo = await _getObjectInfo();
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
        const objectInfo = await _getObjectInfo();
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
    // Return cached data if already loaded (cleared by clearAllCaches on explicit refresh)
    if (_modelListsLoaded) return;
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

        // Sampler and scheduler lists
        availableSamplers = data.samplers || [];
        availableSchedulers = data.schedulers || [];

        // VAE list
        availableVAEs = (data.vae || []).map(normalizePath);
        vaeFolders = extractFolders(availableVAEs);

        // Upscale model list
        availableUpscaleModels = (data.upscale_models || []).map(normalizePath);
        upscaleModelFolders = extractFolders(availableUpscaleModels);

        console.log(`[ConfigBuilder] Model lists loaded: ${availableModels?.length || 0} checkpoints, ` +
            `${availableDiffusionModels.length} diffusion models, ${availableGGUFModels.length} GGUFs, ` +
            `${availableTextEncoders.length} text encoders, ${availableVAEs.length} VAEs, ` +
            `${availableSamplers.length} samplers, ${availableSchedulers.length} schedulers, ` +
            `${availableUpscaleModels.length} upscale models`);
        if (availableDiffusionModels.length === 0) {
            console.log(`[ConfigBuilder] ℹ️ No diffusion models found. Place .safetensors files in ComfyUI/models/unet/ or ComfyUI/models/diffusion_models/`);
        }
        if (availableGGUFModels.length === 0) {
            console.log(`[ConfigBuilder] ℹ️ No GGUF models found. Install ComfyUI-GGUF and place .gguf files in the unet_gguf folder.`);
        }
        _modelListsLoaded = true;
        // Persist to localStorage for instant startup next time
        _saveToLocalStorage();
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
export function getAvailableVAEs() { return availableVAEs || []; }
export function getVAEFolders() { return vaeFolders || ["/"]; }
export function getClipTypes() { return clipTypes; }
export function getDualClipTypes() { return dualClipTypes; }
export function getAvailableSamplers() { return availableSamplers || []; }
export function getAvailableSchedulers() { return availableSchedulers || []; }
export function getAvailableUpscaleModels() { return availableUpscaleModels || []; }
export function getUpscaleModelFolders() { return upscaleModelFolders || ["/"]; }

export async function getAvailableSessions() {
    // Return cached sessions if already loaded (cleared by clearAllCaches on explicit refresh)
    if (_sessionsLoaded) return availableSessions;
    try {
        const resp = await fetch("/object_info", { headers: { "X-Config-Builder-Internal": "true" } });
        const objectInfo = await resp.json();
        for (const nodeType in objectInfo) {
            const nodeDef = objectInfo[nodeType];
            if (nodeType === "UltimateConfigBuilder" && nodeDef.input?.required?.load_session) {
                availableSessions = nodeDef.input.required.load_session[0];
                _sessionsLoaded = true;
                return availableSessions;
            }
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching sessions:", e); }
    _sessionsLoaded = true;
    return availableSessions;
}

export async function getAvailableConfigs() {
    // Return cached configs if already loaded (use clearConfigsCache() to force refresh)
    if (_configsLoaded) return availableConfigs;
    try {
        const resp = await fetch("/configbuilder/list_configs");
        if (resp.ok) {
            const files = await resp.json();
            availableConfigs = files.length > 0 ? files : ["None"];
        }
    } catch (e) { console.error("[ConfigBuilder] Error fetching configs:", e); }
    _configsLoaded = true;
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
/**
 * Recursively resolve a nested prompt structure into flat string options.
 * Rules:
 *   - String/primitive → single option ["text"]
 *   - Flat list of strings ["a", "b"] → OPTIONS (OR logic)
 *   - List containing sub-lists → SEQUENCE (AND logic, Cartesian product)
 *   - Nesting can be arbitrarily deep
 *
 * Example: ["Photo of", ["a cat", "a dog"], ["in space", ["eating", "sleeping"]]]
 *   → ["Photo of, a cat, in space, eating", "Photo of, a cat, in space, sleeping",
 *      "Photo of, a dog, in space, eating", "Photo of, a dog, in space, sleeping"]
 */
function recursiveCartesian(item) {
    if (!Array.isArray(item)) return [String(item)];

    const hasNested = item.some(sub => Array.isArray(sub));

    // Flat list of strings → OPTIONS (OR)
    if (!hasNested) return item.map(String);

    // List with sub-lists → SEQUENCE (AND, Cartesian product)
    const resolvedGroups = item.map(sub => recursiveCartesian(sub));

    // Cartesian product across resolved groups
    let combos = [[]];
    for (const group of resolvedGroups) {
        const newCombos = [];
        for (const existing of combos) {
            for (const opt of group) {
                newCombos.push([...existing, opt]);
            }
        }
        combos = newCombos;
    }
    return combos.map(c => c.join(", "));
}

/**
 * Efficiently count total prompt combinations from a (possibly recursive) nested structure
 * without generating all combinations. O(n) where n is structure size.
 */
function recursiveCount(item) {
    if (!Array.isArray(item)) return 1;

    const hasNested = item.some(sub => Array.isArray(sub));

    // Flat list of strings → OPTIONS count
    if (!hasNested) return item.length || 1;

    // List with sub-lists → product of each sub-item's count
    return item.reduce((total, sub) => total * recursiveCount(sub), 1);
}

/**
 * Count total prompt combinations from a (possibly recursive) nested structure.
 * Handles both old format [["a","b"], ["c","d"]] and new recursive format.
 */
export function countPromptCombinations(groups) {
    if (!groups || !Array.isArray(groups) || groups.length === 0) return 1;
    return recursiveCount(groups) || 1;
}

/**
 * Generate preview of expanded prompt combinations from nested groups.
 * Returns array of strings, capped at `limit` entries.
 * Supports arbitrarily deep recursive nesting.
 */
export function expandPromptPreview(groups, limit = 20) {
    if (!groups || !Array.isArray(groups) || groups.length === 0) return [];
    const all = recursiveCartesian(groups);
    return all.slice(0, limit);
}

// --- ITERATION COUNT CALCULATION ---

export function getIterationCount(configArray) {
    // 1. Params
    const countSplit = (val) => {
        if (Array.isArray(val)) return val.length || 1;
        return String(val).split(",").map(s => s.trim()).filter(s => s).length || 1;
    };
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
            if (configArray.model_bypass_states?.[modelPath]) return; // Skip bypassed
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
            if (configArray.lora_bypass_states?.[name]) return; // Skip bypassed
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

    // 4. VAEs
    let v_count = 0;
    if (!configArray.vaes || configArray.vaes.length === 0) {
        v_count = 1; // Default VAE
    } else {
        configArray.vaes.forEach(v => {
            if (configArray.vae_bypass_states?.[v]) return; // Skip bypassed
            if (!v || v === "None") {
                v_count += 1; // "None" = use Default
            } else {
                v_count += 1;
            }
        });
    }
    if (v_count === 0) v_count = 1;

    // 5. Prompts (per-config custom prompts multiply the iteration count)
    let p_count = 1;
    if (configArray.use_custom_prompts && configArray.positive_prompt_groups && configArray.positive_prompt_groups.length > 0) {
        p_count = countPromptCombinations(configArray.positive_prompt_groups);
    }

    // 6. Attention modes
    const a_count = (configArray.attention_modes && configArray.attention_modes.length > 0) ? configArray.attention_modes.length : 1;

    // 7. Resolutions (per-config overrides)
    const r_count = (configArray.resolutions && configArray.resolutions.length > 0) ? configArray.resolutions.length : 1;

    return m_count * l_count * v_count * s_count * sch_count * st_count * c_count * p_count * a_count * r_count;
}

// --- CONFIG CONVERSION ---
// ============================================================================
// SYNC WARNING: This function MUST stay in sync with the Python-side
// generate_config() in config_builder_node.py.
// That function produces the actual configs_json consumed by the sampler node.
// If you add a new config field here, add it there too (and vice versa).
// Fields consumed by config_utils.expand_configs() must be output by BOTH.
// ============================================================================

export function convertStateToConfigs(state) {
    const configs = [];
    const split = (val) => {
        if (Array.isArray(val)) return val.filter(s => s);
        return String(val).split(",").map(s => s.trim()).filter(s => s);
    };

    // Global prompts from state (used when per-config prompts not set)
    const globalPositiveGroups = state.global_positive_groups || [];
    const globalNegative = state.global_negative || "";

    state.config_arrays.forEach(configArray => {
        // Process LoRAs - filter out bypassed entries
        let loras = configArray.loras.filter(l => {
            if (!l || l === "None") return false;
            const parsed = parseLoraString(l);
            return !configArray.lora_bypass_states?.[parsed.name];
        });

        // Apply weight arrays (bracket notation) for LoRAs with multiple strengths
        const wa = configArray.lora_weight_arrays || {};
        loras = loras.map(l => {
            const parsed = parseLoraString(l);
            const modelArr = wa[parsed.name + "_model"];
            const clipArr = wa[parsed.name + "_clip"];
            if (modelArr && modelArr.length > 1) {
                const modelPart = "[" + modelArr.join(", ") + "]";
                const clipPart = (clipArr && clipArr.length > 1) ? "[" + clipArr.join(", ") + "]" : parsed.clip_str.toFixed(2);
                return parsed.name + ":" + modelPart + ":" + clipPart;
            }
            if (clipArr && clipArr.length > 1) {
                return parsed.name + ":" + parsed.model_str.toFixed(2) + ":[" + clipArr.join(", ") + "]";
            }
            return l;
        });

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
                if (m.path && m.path !== "None" && !configArray.model_bypass_states?.[m.path]) {
                    finalModels.push(m.path);
                    modelType = m.type || "checkpoint";
                }
            } else if (typeof m === 'string' && m && m !== "None" && !configArray.model_bypass_states?.[m]) {
                finalModels.push(m);
            }
        });

        // Process VAEs - filter out bypassed entries
        const vaes = (configArray.vaes || []).filter(v => v && v !== "None" && !configArray.vae_bypass_states?.[v]);

        const config = {
            sampler: split(configArray.samplers),
            scheduler: split(configArray.schedulers),
            steps: configArray.steps.split(",").map(s => parseInt(s)),
            cfg: configArray.cfg.split(",").map(s => parseFloat(s)),
            lora: loraValue,
            model: finalModels.length > 1 ? finalModels : finalModels[0] || "None"
        };

        // Add attention_mode if not just "default"
        const attentionModes = (configArray.attention_modes || ["default"]).filter(a => a);
        if (attentionModes.length > 0 && !(attentionModes.length === 1 && attentionModes[0] === "default")) {
            config.attention_mode = attentionModes.length > 1 ? attentionModes : attentionModes[0];
        }

        // Per-config resolutions (override sampler's resolutions_json)
        if (configArray.resolutions && configArray.resolutions.length > 0) {
            config.resolutions = configArray.resolutions.map(r => {
                const parts = r.split("x").map(Number);
                return [parts[0], parts[1]];
            });
        }

        // Add extra model & sampling options if enabled
        if (configArray.model_sampling_override && configArray.model_sampling_override !== "none") {
            config.model_sampling_override = configArray.model_sampling_override;
            if (configArray.model_sampling_override === "flux") {
                config.model_sampling_flux_max_shift = configArray.model_sampling_flux_max_shift || "1.15";
                config.model_sampling_flux_base_shift = configArray.model_sampling_flux_base_shift || "0.5";
            } else {
                config.model_sampling_shift = configArray.model_sampling_shift || "1.73";
            }
        }
        if (configArray.use_advanced_sampling) {
            config.use_advanced_sampling = true;
            config.advanced_guider = configArray.advanced_guider || "cfg_guider";
            config.advanced_scheduler = configArray.advanced_scheduler || "basic";
        }
        if (configArray.use_flux_guidance) {
            config.use_flux_guidance = true;
            config.flux_guidance_value = configArray.flux_guidance_value || "3.5";
        }

        // Add VAE if any are selected (not "None")
        if (vaes.length > 0) {
            config.vae = vaes.length > 1 ? vaes : vaes[0];
        }

        // Add model_type and related fields for non-checkpoint models
        if (modelType !== "checkpoint") {
            config.model_type = modelType;
            const textEncoders = (configArray.text_encoders || []).filter(te => te && te !== "None" && !configArray.te_bypass_states?.[te]);
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

        // Add model_bypass_states if any are set
        if (configArray.model_bypass_states && Object.keys(configArray.model_bypass_states).length > 0) {
            config.model_bypass_states = configArray.model_bypass_states;
        }

        // Add lora_strength_lock if any are set
        if (configArray.lora_strength_lock && Object.keys(configArray.lora_strength_lock).length > 0) {
            config.lora_strength_lock = configArray.lora_strength_lock;
        }

        // vae_bypass_states and te_bypass_states are internal UI state only.
        // They control filtering (lines 500, 545) but should NOT be in config output.
        // Bypass state persistence is handled by node.saveState() separately.
        // if (configArray.vae_bypass_states && Object.keys(configArray.vae_bypass_states).length > 0) {
        //     config.vae_bypass_states = configArray.vae_bypass_states;
        // }
        // if (configArray.te_bypass_states && Object.keys(configArray.te_bypass_states).length > 0) {
        //     config.te_bypass_states = configArray.te_bypass_states;
        // }

        // Add seed_behavior if set to randomize
        if (configArray.seed_behavior === "randomize") {
            config.seed_behavior = "randomize";
        }

        // Add full_run_seed_behavior if not fixed
        if (configArray.full_run_seed_behavior && configArray.full_run_seed_behavior !== "fixed") {
            config.full_run_seed_behavior = configArray.full_run_seed_behavior;
        }

        // Add full_run_seed if set (overrides node seed)
        if (configArray.full_run_seed && configArray.full_run_seed > 0) {
            config.full_run_seed = configArray.full_run_seed;
        }

        // ==== PROMPT HANDLING ====
        // Priority: per-config > global > omit (node inputs used as fallback)
        if (configArray.use_custom_prompts && configArray.positive_prompt_groups && configArray.positive_prompt_groups.length > 0) {
            config.positive = configArray.positive_prompt_groups;
            if (configArray.negative_prompt) {
                config.negative = configArray.negative_prompt;
            }
            config._prompt_source = "custom";
        } else if (globalPositiveGroups.length > 0) {
            config.positive = globalPositiveGroups;
            if (globalNegative) {
                config.negative = globalNegative;
            }
            config._prompt_source = "global";
        }

        // ==== MODEL PROMPT PREFIX/SUFFIX ====
        // Quality tags prepended/appended to ALL prompts for this config
        if (configArray.model_prompt_prefix && configArray.model_prompt_prefix.trim()) {
            config.model_prompt_prefix = configArray.model_prompt_prefix.trim();
        }
        if (configArray.model_prompt_suffix && configArray.model_prompt_suffix.trim()) {
            config.model_prompt_suffix = configArray.model_prompt_suffix.trim();
        }

        configs.push(config);
    });

    // Session-level settings (not per-config, applied globally)
    // These are attached as a special _session_settings key alongside the configs array
    const sessionSettings = {};

    // Upscaling settings (pipeline-based, filter out inactive pipelines and steps)
    if (state.upscaling && state.upscaling.enabled && state.upscaling.pipelines) {
        const activePipelines = state.upscaling.pipelines
            .filter(p => p.active !== false)
            .map(p => ({
                ...p,
                steps: (p.steps || []).filter(s => s.active !== false).map(s => ({ ...s }))
            }))
            .filter(p => p.steps.length > 0);
        if (activePipelines.length > 0) {
            sessionSettings.upscaling = {
                enabled: true,
                save_pre_upscale: state.upscaling.save_pre_upscale || false,
                run_upscales_at_end: state.upscaling.run_upscales_at_end || false,
                hires_prompt_adjust: state.upscaling.hires_prompt_adjust || false,
                hires_prompt_behavior: state.upscaling.hires_prompt_behavior || "append_end",
                hires_prompt_text: state.upscaling.hires_prompt_text || "",
                pipelines: activePipelines
            };
        }
    }

    // Cooldown settings
    if (state.cooldown && state.cooldown.enabled) {
        sessionSettings.cooldown = { ...state.cooldown };
    }

    // Start At Job # (skip to a specific job number)
    if (state.start_at_job && parseInt(state.start_at_job) > 0) {
        sessionSettings.start_at_job = parseInt(state.start_at_job);
    }

    // Attach session settings to the configs output if any are enabled
    if (Object.keys(sessionSettings).length > 0) {
        configs._session_settings = sessionSettings;
    }

    return configs;
}

export function convertConfigsToConfigArrays(configs) {
    if (!configs || !Array.isArray(configs)) {
        return [{
            name: "Config 1",
            samplers: ["euler"],
            schedulers: ["normal"],
            steps: "20",
            cfg: "7.0",
            seed_behavior: "fixed",
            full_run_seed_behavior: "fixed",
            full_run_seed: 0,
            models: ["None"],
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
            attention_modes: ["default"]
        }];
    }

    // Preserve session-level settings if present in imported config
    if (configs._session_settings) {
        // These will be applied to node.state directly, not to config arrays
        // The caller should handle extracting these
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

        // Load model_bypass_states
        let modelBypassStates = {};
        if (config.model_bypass_states && typeof config.model_bypass_states === 'object') {
            modelBypassStates = { ...config.model_bypass_states };
        }

        // Load vae_bypass_states
        let vaeBypassStates = {};
        if (config.vae_bypass_states && typeof config.vae_bypass_states === 'object') {
            vaeBypassStates = { ...config.vae_bypass_states };
        }

        // Load te_bypass_states
        let teBypassStates = {};
        if (config.te_bypass_states && typeof config.te_bypass_states === 'object') {
            teBypassStates = { ...config.te_bypass_states };
        }

        // Parse VAE
        let vaes = ["None"];
        if (config.vae) {
            if (Array.isArray(config.vae)) {
                vaes = config.vae.map(v => normalizePath(String(v)));
            } else {
                vaes = [normalizePath(String(config.vae))];
            }
        }

        // Parse prompt fields from loaded config
        let positivePromptGroups = [];
        let negativePrompt = "";
        let useCustomPrompts = false;

        // _prompt_source distinguishes global vs per-config prompts on round-trip.
        // "global" = prompts came from the Global Prompts section (should NOT populate custom prompts)
        // "custom" or missing = prompts are per-config custom prompts
        const promptSource = config._prompt_source || "custom";

        if (config.positive && promptSource !== "global") {
            // Config has per-config custom prompts
            useCustomPrompts = true;
            if (Array.isArray(config.positive)) {
                // Check if this is a recursive/nested structure (any element is a sub-array)
                const hasAnyNesting = config.positive.some(item => Array.isArray(item));
                if (hasAnyNesting) {
                    // Recursive or nested array format - preserve structure as-is
                    // This handles both classic [["a","b"],["c"]] and recursive ["text",["a","b"],["x",["y","z"]]]
                    positivePromptGroups = config.positive;
                } else {
                    // Simple flat array of strings - wrap as single group
                    positivePromptGroups = [config.positive];
                }
            } else if (typeof config.positive === 'string' && config.positive.trim()) {
                // Plain string - wrap as single variation in single group
                positivePromptGroups = [[config.positive]];
            }
        }

        if (config.negative && promptSource !== "global") {
            if (typeof config.negative === 'string') {
                negativePrompt = config.negative;
            } else if (Array.isArray(config.negative)) {
                negativePrompt = JSON.stringify(config.negative);
            }
        }

        configArrays.push({
            name: `Loaded Config ${idx + 1}`,
            samplers: Array.isArray(config.sampler) ? config.sampler : [config.sampler || "euler"],
            schedulers: Array.isArray(config.scheduler) ? config.scheduler : [config.scheduler || "normal"],
            steps: toString(config.steps || "20"),
            cfg: toString(config.cfg || "7.0"),
            seed_behavior: config.seed_behavior || "fixed",
            full_run_seed_behavior: config.full_run_seed_behavior || "fixed",
            full_run_seed: config.full_run_seed || 0,
            models: models,
            vaes: vaes,
            text_encoders: config.text_encoders || [],
            clip_type: config.clip_type || "stable_diffusion",
            gguf_options: config.gguf_options || {},
            loras: loras,
            lora_omit_triggers: omitTriggers,
            lora_triggerwords_append_settings: triggerPlacements,
            lora_bypass_states: bypassStates,
            lora_strength_lock: strengthLock,
            model_bypass_states: modelBypassStates,
            vae_bypass_states: vaeBypassStates,
            te_bypass_states: teBypassStates,
            combine: hasCombined,
            positive_prompt_groups: positivePromptGroups,
            negative_prompt: negativePrompt,
            use_custom_prompts: useCustomPrompts,
            model_prompt_prefix: config.model_prompt_prefix || "",
            model_prompt_suffix: config.model_prompt_suffix || "",
            attention_modes: config.attention_mode
                ? (Array.isArray(config.attention_mode) ? config.attention_mode : [config.attention_mode])
                : ["default"],
            // Extra model & sampling options
            model_sampling_override: config.model_sampling_override || "none",
            model_sampling_shift: config.model_sampling_shift || "1.73",
            model_sampling_flux_max_shift: config.model_sampling_flux_max_shift || "1.15",
            model_sampling_flux_base_shift: config.model_sampling_flux_base_shift || "0.5",
            use_advanced_sampling: config.use_advanced_sampling || false,
            advanced_guider: config.advanced_guider || "cfg_guider",
            advanced_scheduler: config.advanced_scheduler || "basic",
            use_flux_guidance: config.use_flux_guidance || false,
            flux_guidance_value: config.flux_guidance_value || "3.5"
        });
    });

    return configArrays.length > 0 ? configArrays : [{
        name: "Config 1",
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
        attention_modes: ["default"]
    }];
}