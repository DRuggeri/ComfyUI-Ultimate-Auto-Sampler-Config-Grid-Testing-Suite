# Builder UI Fixes & Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bypass toggle JSON output, add force_refresh tag diff prompts, add Remote VAE presets dropdown, add per-config sidebar navigation, and reorganize sections with improved headers.

**Architecture:** Five independent UI/backend improvements to the Config Builder node. Items 1, 3, and 5 are frontend-only. Item 2 spans backend (Python) and frontend (JS). Item 4 modifies sidebar and section rendering. All changes are additive — existing code must not be removed.

**Tech Stack:** Vanilla JS (ComfyUI widget), Python (aiohttp server routes), JSON file I/O

**Critical Constraint:** DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

## Task 1: Fix Bypass Toggle JSON Preview Update

All four bypass toggles (model, TE, VAE, LoRA) update visual state and call `node.saveState()` but never call `updatePreview(node)`, so the JSON Preview shows stale data when items are toggled off.

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js:696-704` (model bypass)
- Modify: `web/conf_builder/conf-builder-config-management.js:975-982` (LoRA bypass)
- Modify: `web/conf_builder/conf-builder-config-management.js:2131-2139` (TE bypass)
- Modify: `web/conf_builder/conf-builder-config-management.js:2713-2721` (VAE bypass)

**Step 1: Add `updatePreview(node)` to model bypass toggle**

In `conf-builder-config-management.js`, find the model bypass onclick handler at line ~696:

```javascript
bypassCheck.onclick = (e) => {
    e.stopPropagation(); // Prevent header collapse
    const newBypassState = !bypassCheck.checked;
    node.state.config_arrays[arrayIdx].model_bypass_states[modelPath] = newBypassState;
    node.saveState();
    // Visual feedback
    div.style.opacity = newBypassState ? "0.5" : "1.0";
    div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

Add `updatePreview(node);` after `node.saveState();`:

```javascript
bypassCheck.onclick = (e) => {
    e.stopPropagation(); // Prevent header collapse
    const newBypassState = !bypassCheck.checked;
    node.state.config_arrays[arrayIdx].model_bypass_states[modelPath] = newBypassState;
    node.saveState();
    updatePreview(node);
    // Visual feedback
    div.style.opacity = newBypassState ? "0.5" : "1.0";
    div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

**Step 2: Add `updatePreview(node)` to LoRA bypass toggle**

Find the LoRA bypass onclick at line ~975:

```javascript
bypassCheck.onclick = (e) => {
    e.stopPropagation(); // Prevent header collapse
    const newBypassState = !bypassCheck.checked;
    node.state.config_arrays[arrayIdx].lora_bypass_states[parsed.name] = newBypassState;
    node.saveState();
    // Visual feedback
    div.style.opacity = newBypassState ? "0.5" : "1.0";
    div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

Add `updatePreview(node);` after `node.saveState();`:

```javascript
bypassCheck.onclick = (e) => {
    e.stopPropagation(); // Prevent header collapse
    const newBypassState = !bypassCheck.checked;
    node.state.config_arrays[arrayIdx].lora_bypass_states[parsed.name] = newBypassState;
    node.saveState();
    updatePreview(node);
    // Visual feedback
    div.style.opacity = newBypassState ? "0.5" : "1.0";
    div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

**Step 3: Add `updatePreview(node)` to TE bypass toggle**

Find the TE bypass onclick at line ~2131:

```javascript
teBypassCheck.onclick = (e) => {
    e.stopPropagation();
    const newBypassState = !teBypassCheck.checked;
    node.state.config_arrays[arrayIdx].te_bypass_states[tePath] = newBypassState;
    node.saveState();
    // Visual feedback
    teRow.style.opacity = newBypassState ? "0.5" : "1.0";
    teRow.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

Add `updatePreview(node);` after `node.saveState();`:

```javascript
teBypassCheck.onclick = (e) => {
    e.stopPropagation();
    const newBypassState = !teBypassCheck.checked;
    node.state.config_arrays[arrayIdx].te_bypass_states[tePath] = newBypassState;
    node.saveState();
    updatePreview(node);
    // Visual feedback
    teRow.style.opacity = newBypassState ? "0.5" : "1.0";
    teRow.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

**Step 4: Add `updatePreview(node)` to VAE bypass toggle**

Find the VAE bypass onclick at line ~2713:

```javascript
bypassCheck.onclick = (e) => {
    e.stopPropagation(); // Prevent header collapse
    const newBypassState = !bypassCheck.checked;
    node.state.config_arrays[arrayIdx].vae_bypass_states[vaeName] = newBypassState;
    node.saveState();
    // Visual feedback
    div.style.opacity = newBypassState ? "0.5" : "1.0";
    div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

Add `updatePreview(node);` after `node.saveState();`:

```javascript
bypassCheck.onclick = (e) => {
    e.stopPropagation(); // Prevent header collapse
    const newBypassState = !bypassCheck.checked;
    node.state.config_arrays[arrayIdx].vae_bypass_states[vaeName] = newBypassState;
    node.saveState();
    updatePreview(node);
    // Visual feedback
    div.style.opacity = newBypassState ? "0.5" : "1.0";
    div.style.filter = newBypassState ? "grayscale(0.7)" : "none";
};
```

**Step 5: Verify and commit**

Verify: Open the Builder UI, add a VAE, toggle it off via the "On" checkbox, and check the JSON Preview — the bypassed VAE should NOT appear. Repeat for models, TEs, and LoRAs.

```bash
git add web/conf_builder/conf-builder-config-management.js
git commit -m "Fix bypass toggles not updating JSON Preview

Add updatePreview(node) call after node.saveState() in all four
bypass toggle handlers (model, LoRA, TE, VAE) so the JSON Preview
immediately reflects bypass state changes."
```

---

## Task 2: force_refresh Tag Comparison & Update Prompt

When force_refresh re-fetches CivitAI metadata, compare fresh `trainedWords` with stored tags and prompt the user if they differ.

**Files:**
- Modify: `config_builder_node.py:764-805` (metadata endpoint response)
- Modify: `web/conf_builder/conf-builder-config-management.js:1384-1413` (metadata modal response handler)

**Step 1: Add tag comparison to backend metadata endpoint**

In `config_builder_node.py`, inside `lookup_lora_metadata_endpoint`, after the metadata dict is built (line ~779) and before saving (line ~798), add tag comparison logic. Find this code block:

```python
        # Save metadata to file
        output_dir = folder_paths.get_output_directory()
        model_data_dir = os.path.join(output_dir, "benchmarks", "model-data", lora_name.replace("/", "_").replace("\\", "_").replace(".safetensors", ""))
        os.makedirs(model_data_dir, exist_ok=True)

        metadata_file = os.path.join(model_data_dir, "metadata.json")
        save_dict_to_json(metadata, metadata_file)

        print(f"[ConfigBuilder] ✅ Metadata saved to: {metadata_file}")

        return web.json_response({
            "metadata": metadata,
            "saved_to": metadata_file
        })
```

Replace the return statement only (keep everything above intact):

```python
        # Save metadata to file
        output_dir = folder_paths.get_output_directory()
        model_data_dir = os.path.join(output_dir, "benchmarks", "model-data", lora_name.replace("/", "_").replace("\\", "_").replace(".safetensors", ""))
        os.makedirs(model_data_dir, exist_ok=True)

        metadata_file = os.path.join(model_data_dir, "metadata.json")
        save_dict_to_json(metadata, metadata_file)

        print(f"[ConfigBuilder] ✅ Metadata saved to: {metadata_file}")

        # Compare fresh tags with stored loras_tags.json (only on force_refresh)
        tags_changed = False
        old_tags = []
        new_tags = metadata.get("trained_words", [])
        if force_refresh and new_tags:
            json_tags_path = os.path.join(output_dir, "benchmarks/loras_tags.json")
            if os.path.exists(json_tags_path):
                lora_tags = load_json_from_file(json_tags_path) or {}
                normalized = lora_name.replace("\\", "/")
                backslash = lora_name.replace("/", "\\")
                old_tags = lora_tags.get(lora_name, lora_tags.get(normalized, lora_tags.get(backslash, [])))
                if old_tags is None:
                    old_tags = []
                # Compare sorted lists to detect any difference
                if sorted(old_tags) != sorted(new_tags):
                    tags_changed = True
                    print(f"[ConfigBuilder] ⚠️ Tags changed for {lora_name}: {old_tags} -> {new_tags}")

        return web.json_response({
            "metadata": metadata,
            "saved_to": metadata_file,
            "tags_changed": tags_changed,
            "old_tags": old_tags,
            "new_tags": new_tags
        })
```

**Step 2: Add tag diff banner to frontend metadata modal**

In `conf-builder-config-management.js`, find the metadata modal response handling at line ~1384:

```javascript
        const data = await resp.json();
        const metadata = data.metadata;

        status.textContent = "✅ Metadata loaded successfully!";
        status.style.color = "#66ff66";

        // Display metadata
        content.innerHTML = "";
```

Add a tag diff banner right after `content.innerHTML = "";` and before the cache warning banner block (line ~1393). Insert this code at line ~1392 (after `content.innerHTML = "";`):

```javascript
        // Tag diff banner (shown when force_refresh detects different tags)
        if (data.tags_changed) {
            const tagDiffBanner = document.createElement("div");
            tagDiffBanner.style.cssText = "background: #1a3300; border: 2px solid #44cc00; border-radius: 6px; padding: 10px 14px; margin-bottom: 15px;";

            const tagDiffTitle = document.createElement("div");
            tagDiffTitle.style.cssText = "font-size: 14px; font-weight: bold; color: #44cc00; margin-bottom: 8px;";
            tagDiffTitle.textContent = "🔄 Trigger Words Changed";
            tagDiffBanner.appendChild(tagDiffTitle);

            const oldTagsDiv = document.createElement("div");
            oldTagsDiv.style.cssText = "font-size: 11px; color: #cc6666; margin-bottom: 4px;";
            oldTagsDiv.textContent = "Old: " + (data.old_tags.length > 0 ? data.old_tags.join(", ") : "(none)");
            tagDiffBanner.appendChild(oldTagsDiv);

            const newTagsDiv = document.createElement("div");
            newTagsDiv.style.cssText = "font-size: 11px; color: #66cc66; margin-bottom: 8px;";
            newTagsDiv.textContent = "New: " + data.new_tags.join(", ");
            tagDiffBanner.appendChild(newTagsDiv);

            const tagBtnRow = document.createElement("div");
            tagBtnRow.style.cssText = "display: flex; gap: 8px;";

            const updateTagsBtn = document.createElement("button");
            updateTagsBtn.className = "cb-button primary";
            updateTagsBtn.style.cssText = "flex: 1; background: #336600; border: 1px solid #44cc00; color: #88ff44;";
            updateTagsBtn.textContent = "✅ Update Tags";
            updateTagsBtn.onclick = async () => {
                try {
                    const saveResp = await fetch("/configbuilder/save_lora_triggers", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ lora_name: loraName, triggers: data.new_tags })
                    });
                    if (saveResp.ok) {
                        updateTagsBtn.textContent = "✅ Updated!";
                        updateTagsBtn.disabled = true;
                        keepTagsBtn.disabled = true;
                    }
                } catch (e) {
                    updateTagsBtn.textContent = "❌ Error";
                }
            };

            const keepTagsBtn = document.createElement("button");
            keepTagsBtn.className = "cb-button";
            keepTagsBtn.style.cssText = "flex: 1;";
            keepTagsBtn.textContent = "Keep Current";
            keepTagsBtn.onclick = () => {
                tagDiffBanner.style.display = "none";
            };

            tagBtnRow.appendChild(updateTagsBtn);
            tagBtnRow.appendChild(keepTagsBtn);
            tagDiffBanner.appendChild(tagBtnRow);
            content.appendChild(tagDiffBanner);
        }
```

**Step 3: Commit**

```bash
git add config_builder_node.py web/conf_builder/conf-builder-config-management.js
git commit -m "Add tag diff prompt on force_refresh metadata re-fetch

Backend compares fresh CivitAI trainedWords with stored loras_tags.json
and returns tags_changed/old_tags/new_tags. Frontend shows diff banner
with Update/Keep buttons in the metadata modal."
```

---

## Task 3: HF Remote VAE Presets Dropdown

When "Remote URL" is selected as VAE type, show a presets dropdown for known HuggingFace endpoints.

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js:2820-2841` (remote VAE URL section in `createVAEElement()`)

**Step 1: Add REMOTE_VAE_PRESETS constant**

At the top of `conf-builder-config-management.js`, near the other constants (e.g., `CONFIG_COLORS`), add:

```javascript
// HF Remote VAE endpoint presets (mirrors remote_vae.py HF_ENDPOINTS)
const REMOTE_VAE_PRESETS = {
    "Custom": "",
    "HF-SD": "https://q1bj3bpq6kzilnsu.us-east-1.aws.endpoints.huggingface.cloud/",
    "HF-SDXL": "https://x2dmsqunjd6k9prw.us-east-1.aws.endpoints.huggingface.cloud/",
    "HF-Flux": "https://whhx50ex1aryqvw6.us-east-1.aws.endpoints.huggingface.cloud/",
    "HF-HunyuanVideo": "https://o7ywnmrahorts457.us-east-1.aws.endpoints.huggingface.cloud/"
};
```

Find the exact location: search for `const CONFIG_COLORS` and add the `REMOTE_VAE_PRESETS` constant right after the CONFIG_COLORS array declaration.

**Step 2: Add presets dropdown in the Remote URL branch**

In `createVAEElement()`, find the `if (isRemote)` block at line ~2820:

```javascript
    if (isRemote) {
        // Text input for remote VAE endpoint URL
        const urlInput = document.createElement("input");
```

Replace the entire `if (isRemote) { ... }` block (lines 2820-2841, up to but NOT including the `} else {`) with:

```javascript
    if (isRemote) {
        // Presets dropdown for known HF Remote VAE endpoints
        const presetSelect = document.createElement("select");
        presetSelect.className = "cb-select";
        presetSelect.style.marginBottom = "4px";
        const currentUrl = vaeName.replace(/^remote:/, "");
        Object.entries(REMOTE_VAE_PRESETS).forEach(([label, url]) => {
            const opt = document.createElement("option");
            opt.value = url;
            opt.textContent = label;
            // Select matching preset, or "Custom" if URL doesn't match any preset
            if (url && currentUrl === url) opt.selected = true;
            else if (!url && !Object.values(REMOTE_VAE_PRESETS).includes(currentUrl)) opt.selected = true;
            presetSelect.appendChild(opt);
        });

        // Text input for remote VAE endpoint URL
        const urlInput = document.createElement("input");
        urlInput.className = "cb-input";
        urlInput.type = "text";
        urlInput.placeholder = "http://192.168.1.100:8080/decode";
        urlInput.value = currentUrl;
        urlInput.style.fontFamily = "monospace";
        urlInput.style.fontSize = "12px";
        urlInput.onchange = () => {
            const url = urlInput.value.trim();
            node.state.config_arrays[arrayIdx].vaes[vaeIdx] = url ? `remote:${url}` : "remote:";
            node.saveState();
            // Update preset dropdown to match
            const matchingPreset = Object.entries(REMOTE_VAE_PRESETS).find(([, u]) => u && u === url);
            presetSelect.value = matchingPreset ? matchingPreset[1] : "";
        };
        urlInput.onblur = urlInput.onchange;

        presetSelect.onchange = () => {
            const selectedUrl = presetSelect.value;
            if (selectedUrl) {
                urlInput.value = selectedUrl;
                node.state.config_arrays[arrayIdx].vaes[vaeIdx] = `remote:${selectedUrl}`;
                node.saveState();
            } else {
                // "Custom" selected - clear URL for manual entry
                urlInput.value = "";
                urlInput.focus();
            }
        };

        contentDiv.appendChild(presetSelect);
        contentDiv.appendChild(urlInput);

        // Helper text
        const helperText = document.createElement("div");
        helperText.style.cssText = "font-size: 9px; color: #666; padding: 2px 4px;";
        helperText.textContent = "Select a preset or enter a custom endpoint URL for your remote VAE decode server";
        contentDiv.appendChild(helperText);
    } else {
```

Note: The `} else {` line that follows must remain unchanged — only the content inside `if (isRemote) { ... }` is replaced.

**Step 3: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js
git commit -m "Add Remote VAE presets dropdown for HF endpoints

When Remote URL type is selected in VAE element, show a presets
dropdown with known HuggingFace VAE endpoints (SD, SDXL, Flux,
HunyuanVideo). Selecting a preset auto-fills the URL input."
```

---

## Task 4: Per-Config Sidebar Navigation

Add per-config-array cog icons in the sidebar that expand on hover to show sub-section navigation (Models, TE, VAE, LoRAs).

**Files:**
- Modify: `web/conf_builder/conf-builder-ui-components.js:723-731` (sidebar nav icons section)
- Modify: `web/conf_builder/conf-builder-ui-components.js:801` (scroll spy section IDs)
- Modify: `web/conf_builder/conf-builder-config-management.js:1964` (models section — add ID)
- Modify: `web/conf_builder/conf-builder-config-management.js:2064-2066` (TE section — add ID)
- Modify: `web/conf_builder/conf-builder-config-management.js:2263-2272` (VAE section — add ID)
- Modify: `web/conf_builder/conf-builder-config-management.js:2888-2896` (LoRAs section — add ID)
- Modify: `web/conf_builder/conf-builder-ui-components.js:184-424` (getStyles — add sidebar expansion CSS)

**Step 1: Add sub-section IDs to config sections**

Each sub-section renderer needs a unique ID for sidebar scroll-to targeting.

In `renderModelsSection()` at line ~1969, after `const modelGrid = document.createElement("div");` (line ~1969-1970), add:

```javascript
    modelGrid.id = `cb-config-${arrayIdx}-models`;
```

In `renderTextEncodersSection()` at line ~2065, after `const section = document.createElement("div");`, add:

```javascript
    section.id = `cb-config-${arrayIdx}-te`;
```

In `renderVAEsSection()` at line ~2271, after `const vaeGrid = document.createElement("div");` (line ~2271-2272), add:

```javascript
    vaeGrid.id = `cb-config-${arrayIdx}-vae`;
```

In `renderLorasSection()` at line ~2893, after `const loraGrid = document.createElement("div");` (line ~2893-2894), add:

```javascript
    loraGrid.id = `cb-config-${arrayIdx}-loras`;
```

**Step 2: Add CSS for sidebar config expansion**

In `getStyles()` in `conf-builder-ui-components.js`, find the closing `</style>` tag at line ~423. Just BEFORE the closing `</style>`, add:

```css
            /* Per-config sidebar navigation */
            .cb-sidebar-config-group {
                position: relative;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .cb-sidebar-config-icon {
                width: 28px;
                height: 28px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 11px;
                font-weight: bold;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                color: #999;
                transition: background 0.15s;
            }
            .cb-sidebar-config-icon:hover {
                background: #333;
            }
            .cb-sidebar-config-icon.active {
                background: #333;
                color: #fff;
            }
            .cb-sidebar-sub-icons {
                display: none;
                flex-direction: column;
                align-items: center;
                gap: 2px;
                padding: 2px 0;
            }
            .cb-sidebar-config-group:hover .cb-sidebar-sub-icons {
                display: flex;
            }
            .cb-sidebar-sub-icon {
                width: 28px;
                height: 22px;
                border: none;
                border-radius: 3px;
                cursor: pointer;
                font-size: 9px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                color: #888;
                transition: background 0.15s;
            }
            .cb-sidebar-sub-icon:hover {
                background: #444;
                color: #fff;
            }
```

**Step 3: Add per-config icons to sidebar**

In `createSidebar()` in `conf-builder-ui-components.js`, find the line that adds the ⚙️ Config Arrays nav icon at line ~724:

```javascript
    addNavIcon("⚙️", "Config Arrays", "cb-sec-configs");
```

After this line, add the per-config cog icons. Import `CONFIG_COLORS` at the top of the file if needed (check if it's already imported — it is defined in `conf-builder-config-management.js`). Since `CONFIG_COLORS` is in a different module, we'll define a local copy or pass it via the node state. The simplest approach: read from `node.state.config_arrays` directly since the sidebar already receives `node`.

Add after `addNavIcon("⚙️", "Config Arrays", "cb-sec-configs");`:

```javascript
    // Per-config array navigation icons
    const configColors = ["#0088ff", "#ff6600", "#00cc66", "#cc44cc", "#ffaa00", "#44cccc", "#ff4466", "#88aa00"];
    if (node.state.config_arrays && node.state.config_arrays.length > 0) {
        node.state.config_arrays.forEach((ca, idx) => {
            const color = configColors[idx % configColors.length];
            const group = document.createElement("div");
            group.className = "cb-sidebar-config-group";

            const cogBtn = document.createElement("button");
            cogBtn.className = "cb-sidebar-config-icon";
            cogBtn.style.color = color;
            cogBtn.style.borderLeft = `2px solid ${color}`;
            cogBtn.textContent = `${idx + 1}`;
            cogBtn.title = ca.name || `Config ${idx + 1}`;
            cogBtn.dataset.targetId = `cb-config-${idx}`;
            cogBtn.onclick = () => {
                const target = mainContent.querySelector(`#cb-config-${idx}`);
                if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
            };
            icons.push(cogBtn);
            group.appendChild(cogBtn);

            // Sub-icons container (shown on hover)
            const subIcons = document.createElement("div");
            subIcons.className = "cb-sidebar-sub-icons";

            const subSections = [
                { emoji: "🧊", label: "Models", id: `cb-config-${idx}-models` },
                { emoji: "📎", label: "Text Enc", id: `cb-config-${idx}-te` },
                { emoji: "🎨", label: "VAE", id: `cb-config-${idx}-vae` },
                { emoji: "🔗", label: "LoRAs", id: `cb-config-${idx}-loras` }
            ];

            subSections.forEach(sub => {
                const subBtn = document.createElement("button");
                subBtn.className = "cb-sidebar-sub-icon";
                subBtn.textContent = sub.emoji;
                subBtn.title = sub.label;
                subBtn.onclick = () => {
                    const target = mainContent.querySelector(`#${sub.id}`);
                    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
                };
                subIcons.appendChild(subBtn);
            });

            group.appendChild(subIcons);
            sidebar.appendChild(group);
        });
    }
```

**Step 4: Update scroll spy to include config IDs**

In `createSidebar()`, find the scroll spy `sectionIds` array at line ~801:

```javascript
    const sectionIds = ["cb-sec-prompts", "cb-sec-configs", "cb-sec-distribution", "cb-sec-preview"];
```

Add per-config IDs dynamically. Replace this line with:

```javascript
    const sectionIds = ["cb-sec-prompts", "cb-sec-configs"];
    // Add per-config section IDs for scroll spy
    if (node.state.config_arrays) {
        node.state.config_arrays.forEach((_, idx) => {
            sectionIds.push(`cb-config-${idx}`);
        });
    }
    sectionIds.push("cb-sec-distribution", "cb-sec-preview");
```

**Step 5: Commit**

```bash
git add web/conf_builder/conf-builder-ui-components.js web/conf_builder/conf-builder-config-management.js
git commit -m "Add per-config sidebar navigation with hover sub-sections

Each config array gets a numbered cog icon in the sidebar, color-coded
with CONFIG_COLORS. Hovering expands sub-icons for Models, TE, VAE,
and LoRAs sub-section navigation. Adds section IDs for scroll targets."
```

---

## Task 5: Section Organization & Header Fixes

Reorder sections, move Extra Model Sampling inside Models, and improve header contrast.

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js:3885-3991` (renderUI section order)
- Modify: `web/conf_builder/conf-builder-config-management.js:3977-3981` (per-config sub-section order)
- Modify: `web/conf_builder/conf-builder-config-management.js:2064-2070` (TE header style)
- Modify: `web/conf_builder/conf-builder-config-management.js:2274-2276` (VAE header style)
- Modify: `web/conf_builder/conf-builder-config-management.js:2898-2900` (LoRAs header style)
- Modify: `web/conf_builder/conf-builder-ui-components.js:723-731` (sidebar icon order)

**Step 1: Reorder main content sections in renderUI()**

In `renderUI()`, find the section rendering order at lines ~3884-3991. Change the order to: Distribution → Global Prompts → Config Arrays → Preview.

Find this block:

```javascript
    // === MAIN CONTENT SECTIONS ===

    // Global Prompts Section
    renderGlobalPromptsSection(node, mainContent);

    // Config Arrays Section
    const configSection = document.createElement("div");
```

Change it to:

```javascript
    // === MAIN CONTENT SECTIONS ===

    // Distribution Settings Section (when enabled, appears first)
    if (node.state.distribution_enabled) {
        renderDistributionSettingsSection(node, mainContent);
    }

    // Global Prompts Section
    renderGlobalPromptsSection(node, mainContent);

    // Config Arrays Section
    const configSection = document.createElement("div");
```

And REMOVE the old distribution block at lines ~3988-3991 (after `mainContent.appendChild(configSection);`):

```javascript
    // Distribution Settings Section (only when enabled)
    if (node.state.distribution_enabled) {
        renderDistributionSettingsSection(node, mainContent);
    }
```

Delete those 4 lines (the comment and the if block). The distribution section is now rendered at the top instead.

**Step 2: Move Extra Model Sampling inside Models section**

In `renderUI()`, find the per-config sub-section rendering at lines ~3977-3981:

```javascript
        renderConfigPromptsSection(node, arrayElement, configArray, arrayIdx);
        renderModelsSection(node, arrayElement, configArray, arrayIdx, modelLists);
        renderExtraModelSamplingSection(node, arrayElement, configArray, arrayIdx);
        renderVAEsSection(node, arrayElement, configArray, arrayIdx, modelLists);
        renderLorasSection(node, arrayElement, configArray, arrayIdx, availableLoras, loraFolders);
```

The `renderExtraModelSamplingSection` call needs to move inside `renderModelsSection()` instead. Remove line 3979:

```javascript
        renderExtraModelSamplingSection(node, arrayElement, configArray, arrayIdx);
```

So it becomes:

```javascript
        renderConfigPromptsSection(node, arrayElement, configArray, arrayIdx);
        renderModelsSection(node, arrayElement, configArray, arrayIdx, modelLists);
        renderVAEsSection(node, arrayElement, configArray, arrayIdx, modelLists);
        renderLorasSection(node, arrayElement, configArray, arrayIdx, availableLoras, loraFolders);
```

Now add the call inside `renderModelsSection()`. Find the end of `renderModelsSection()` — look for where the function appends its final elements and returns. Find the line that appends `modelGrid` to `div` (around line ~2060):

```javascript
    div.appendChild(modelGrid);
}
```

Just before the closing `}` of `renderModelsSection`, add:

```javascript
    // Extra Model & Sampling Options (sub-section of Models)
    renderExtraModelSamplingSection(node, div, configArray, arrayIdx);
```

So it becomes:

```javascript
    div.appendChild(modelGrid);

    // Extra Model & Sampling Options (sub-section of Models)
    renderExtraModelSamplingSection(node, div, configArray, arrayIdx);
}
```

**Step 3: Fix Text Encoders header to be bigger and match other sections**

In `renderTextEncodersSection()` at line ~2068-2070, find:

```javascript
    const header = document.createElement("div");
    header.style.cssText = "font-size: 11px; font-weight: bold; color: #44aaff; margin-bottom: 6px;";
    header.textContent = "TEXT ENCODERS (CLIP)";
```

Change the style to match the other section toggle headers (bigger font, same background pattern):

```javascript
    const header = document.createElement("div");
    header.className = "cb-section-toggle";
    header.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #66bbff;";
    header.textContent = "Text Encoders (CLIP)";
```

**Step 4: Fix VAE header — lighter background, brighter text**

In `renderVAEsSection()` at line ~2274-2276, find:

```javascript
    const vaeHeader = document.createElement("div");
    vaeHeader.className = "cb-section-toggle";
    vaeHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #9900cc;";
```

Change to lighter background and brighter text:

```javascript
    const vaeHeader = document.createElement("div");
    vaeHeader.className = "cb-section-toggle";
    vaeHeader.style.cssText = "padding: 8px; background: #444; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #cc66ff;";
```

**Step 5: Fix LoRAs header — brighter text**

In `renderLorasSection()` at line ~2898-2900, find:

```javascript
    const loraHeader = document.createElement("div");
    loraHeader.className = "cb-section-toggle";
    loraHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #0066cc;";
```

Change to brighter text:

```javascript
    const loraHeader = document.createElement("div");
    loraHeader.className = "cb-section-toggle";
    loraHeader.style.cssText = "padding: 8px; background: #3a3a3a; border-radius: 4px; margin-bottom: 8px; font-weight: bold; color: #4499ff;";
```

**Step 6: Update sidebar icon order**

In `createSidebar()` in `conf-builder-ui-components.js`, find the nav icon order at lines ~723-731:

```javascript
    addNavIcon("📝", "Global Prompts", "cb-sec-prompts");
    addNavIcon("⚙️", "Config Arrays", "cb-sec-configs");

    // Distribution icon (only when enabled)
    if (node.state.distribution_enabled) {
        addNavIcon("🌐", "Distribution", "cb-sec-distribution");
    }

    addNavIcon("📄", "JSON Preview", "cb-sec-preview");
```

Change to put Distribution first:

```javascript
    // Distribution icon (only when enabled, appears first)
    if (node.state.distribution_enabled) {
        addNavIcon("🌐", "Distribution", "cb-sec-distribution");
    }

    addNavIcon("📝", "Global Prompts", "cb-sec-prompts");
    addNavIcon("⚙️", "Config Arrays", "cb-sec-configs");

    addNavIcon("📄", "JSON Preview", "cb-sec-preview");
```

**Step 7: Commit**

```bash
git add web/conf_builder/conf-builder-config-management.js web/conf_builder/conf-builder-ui-components.js
git commit -m "Reorganize sections and improve header contrast

Move Distribution Settings to top of layout. Move Extra Model &
Sampling Options inside Models section as sub-section. Make TE header
bigger with matching toggle style. Lighten VAE header background and
brighten text. Brighten LoRAs header text color."
```

---

## Verification Checklist

After all tasks are complete, verify each item:

1. **Bypass toggles:** Toggle off a VAE/TE/model/LoRA and confirm it vanishes from JSON Preview immediately (no page reload needed)
2. **Tag diff:** Open a LoRA metadata modal, click re-fetch, verify the diff banner appears if tags changed, and the Update button writes to `loras_tags.json`
3. **Remote VAE presets:** Set a VAE to Remote URL type, verify the presets dropdown appears with HF-SD/SDXL/Flux/HunyuanVideo options, selecting one fills the URL input
4. **Sidebar nav:** With 2+ config arrays, verify numbered cog icons appear in sidebar, hovering shows sub-icons, clicking scrolls to the right section
5. **Section order:** Distribution is at top, Extra Model Sampling is inside Models, headers have improved contrast
