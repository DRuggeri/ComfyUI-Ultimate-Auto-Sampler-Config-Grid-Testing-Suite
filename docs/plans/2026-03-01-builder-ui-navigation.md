# Builder UI Navigation, Layout & Styles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Overhaul the Builder UI with sticky top bar, left sidebar navigation, uniform section headers, and improved dark mode colors.

**Architecture:** Replace the 3-section top row with a compact top bar (session name + settings dropdown). Add a left sidebar with navigation icons and quick actions. Restructure the main container as a flex layout: top bar + (sidebar | scrollable content). All section headers get uniform styling with accent color stripes.

**Tech Stack:** Vanilla JS (ComfyUI widget), embedded CSS via getStyles()

**Critical constraint:** DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

### Task 1: Add New CSS Classes to getStyles()

**Files:**
- Modify: `web/conf_builder/conf-builder-ui-components.js:184-394` (getStyles function)

**Step 1: Add top bar CSS**

After the `.cb-container` rule (line 187), add:

```css
.cb-top-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 12px;
    background: #1a1a1a;
    border-bottom: 1px solid #3a3a3a;
    position: sticky;
    top: 0;
    z-index: 100;
    min-height: 36px;
    flex-shrink: 0;
}
.cb-top-bar-input {
    flex: 1;
    background: transparent;
    border: 1px solid transparent;
    color: #e0e0e0;
    font-size: 14px;
    font-weight: bold;
    padding: 6px 10px;
    border-radius: 4px;
    font-family: monospace;
    min-width: 100px;
}
.cb-top-bar-input:hover { border-color: #444; }
.cb-top-bar-input:focus { outline: none; border-color: #0077dd; background: #1a1a1a; }
.cb-settings-btn {
    background: #333;
    border: 1px solid #555;
    color: #ccc;
    padding: 6px 14px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 6px;
}
.cb-settings-btn:hover { background: #444; color: #fff; }
```

**Step 2: Add settings dropdown CSS**

```css
.cb-settings-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    min-width: 280px;
    background: #1e1e1e;
    border: 1px solid #444;
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    z-index: 200;
    overflow: hidden;
    display: none;
}
.cb-settings-dropdown.open { display: block; }
.cb-settings-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    cursor: pointer;
    color: #ccc;
    font-size: 12px;
    border: none;
    background: none;
    width: 100%;
    text-align: left;
}
.cb-settings-item:hover { background: #2a2a2a; color: #fff; }
.cb-settings-divider {
    height: 1px;
    background: #333;
    margin: 4px 0;
}
.cb-settings-expand {
    padding: 8px 14px;
    background: #252525;
    border-top: 1px solid #333;
    display: none;
}
.cb-settings-expand.open { display: block; }
```

**Step 3: Add sidebar CSS**

```css
.cb-layout-wrapper {
    display: flex;
    flex: 1;
    overflow: hidden;
}
.cb-sidebar {
    width: 42px;
    min-width: 42px;
    background: #1e1e1e;
    border-right: 1px solid #333;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 8px;
    gap: 2px;
    flex-shrink: 0;
    overflow-y: auto;
}
.cb-sidebar-icon {
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
    background: transparent;
    border: none;
    color: #888;
    position: relative;
    transition: background 0.15s, color 0.15s;
}
.cb-sidebar-icon:hover { background: #333; color: #fff; }
.cb-sidebar-icon.active { background: #0077dd33; color: #4aa8ff; }
.cb-sidebar-icon[title]:hover::after {
    content: attr(title);
    position: absolute;
    left: 42px;
    top: 50%;
    transform: translateY(-50%);
    background: #222;
    color: #eee;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    white-space: nowrap;
    z-index: 300;
    border: 1px solid #444;
    pointer-events: none;
}
.cb-sidebar-divider {
    width: 24px;
    height: 1px;
    background: #444;
    margin: 6px 0;
}
.cb-main-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
}
```

**Step 4: Add uniform section header CSS**

```css
.cb-section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    margin: -12px -12px 12px -12px;
    border-radius: 4px 4px 0 0;
    font-size: 16px;
    font-weight: bold;
    color: #e0e0e0;
    user-select: none;
}
```

**Step 5: Update existing colors for better contrast**

Update these existing rules:
- `.cb-label`: change `color: #aaa` to `color: #ccc`
- `.cb-button`: ensure text is `color: #e0e0e0`
- `.cb-button.primary`: change `background: #0066cc` to `background: #0077dd`
- `.cb-button.primary:hover`: change `background: #0077ee` to `background: #0088ee`
- `.cb-input, .cb-select`: change `border: 1px solid #4a4a4a` to `border: 1px solid #555`
- `.cb-controls-bar`: change `background: #252525` to `background: #2a2a2a`

**Step 6: Update `.cb-container` for new layout**

Change `.cb-container` from:
```css
.cb-container { padding: 12px; height: 100%; overflow-y: auto; box-sizing: border-box; }
```
to:
```css
.cb-container { display: flex; flex-direction: column; height: 100%; overflow: hidden; box-sizing: border-box; }
```

The scrolling now happens in `.cb-main-content` instead.

**Step 7: Commit**
```
feat: add CSS classes for top bar, sidebar, settings dropdown, section headers
```

---

### Task 2: Create Top Bar and Settings Dropdown Components

**Files:**
- Modify: `web/conf_builder/conf-builder-ui-components.js` (add new exports after getStyles)

**Step 1: Add `createTopBar()` function**

Add after `getStyles()` function (after line ~395):

```javascript
// --- TOP BAR COMPONENT ---

export function createTopBar(node, {
    availableSessions, availableConfigs,
    refreshAllConfigBuilders,
    onLoadSession, onLoadConfig, onSaveConfig
}) {
    const bar = document.createElement("div");
    bar.className = "cb-top-bar";

    // Session name input
    const sessionInput = document.createElement("input");
    sessionInput.className = "cb-top-bar-input";
    sessionInput.type = "text";
    sessionInput.value = node.state.session_name || "my_test_session";
    sessionInput.placeholder = "Session name...";
    sessionInput.title = "Session Name";
    sessionInput.onchange = () => {
        node.state.session_name = sessionInput.value;
        node.saveState();
    };
    bar.appendChild(sessionInput);

    // Settings button + dropdown container
    const settingsWrapper = document.createElement("div");
    settingsWrapper.style.position = "relative";

    const settingsBtn = document.createElement("button");
    settingsBtn.className = "cb-settings-btn";
    settingsBtn.innerHTML = "⚙ Settings ▾";

    const dropdown = createSettingsDropdown(node, {
        availableSessions, availableConfigs,
        refreshAllConfigBuilders,
        onLoadSession, onLoadConfig, onSaveConfig
    });

    settingsBtn.onclick = (e) => {
        e.stopPropagation();
        dropdown.classList.toggle("open");
    };

    // Close on click outside
    document.addEventListener("click", (e) => {
        if (!settingsWrapper.contains(e.target)) {
            dropdown.classList.remove("open");
        }
    });

    settingsWrapper.appendChild(settingsBtn);
    settingsWrapper.appendChild(dropdown);
    bar.appendChild(settingsWrapper);

    return bar;
}
```

**Step 2: Add `createSettingsDropdown()` function**

Add after `createTopBar()`:

```javascript
function createSettingsDropdown(node, {
    availableSessions, availableConfigs,
    refreshAllConfigBuilders,
    onLoadSession, onLoadConfig, onSaveConfig
}) {
    const dropdown = document.createElement("div");
    dropdown.className = "cb-settings-dropdown";

    // Helper: create expandable item
    function addExpandableItem(emoji, label, expandContent) {
        const item = document.createElement("div");
        item.className = "cb-settings-item";
        item.innerHTML = `<span>${emoji}</span><span>${label}</span><span style="margin-left:auto;font-size:10px;color:#666">▶</span>`;

        const expand = document.createElement("div");
        expand.className = "cb-settings-expand";
        expand.appendChild(expandContent);

        item.onclick = (e) => {
            e.stopPropagation();
            // Close other expands
            dropdown.querySelectorAll(".cb-settings-expand.open").forEach(el => {
                if (el !== expand) el.classList.remove("open");
            });
            expand.classList.toggle("open");
            const arrow = item.querySelector("span:last-child");
            arrow.textContent = expand.classList.contains("open") ? "▼" : "▶";
        };

        dropdown.appendChild(item);
        dropdown.appendChild(expand);
    }

    // Helper: create toggle item
    function addToggleItem(emoji, label, checked, onChange) {
        const item = document.createElement("label");
        item.className = "cb-settings-item";
        item.style.cursor = "pointer";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = checked;
        cb.onchange = () => onChange(cb.checked);
        item.innerHTML = `<span>${emoji}</span>`;
        item.appendChild(cb);
        const lbl = document.createElement("span");
        lbl.textContent = label;
        item.appendChild(lbl);
        dropdown.appendChild(item);
    }

    // Helper: divider
    function addDivider() {
        const d = document.createElement("div");
        d.className = "cb-settings-divider";
        dropdown.appendChild(d);
    }

    // === Load Session (expandable) ===
    const sessionSelectContainer = document.createElement("div");
    const sessionSelect = createSearchableSelect(
        availableSessions || [],
        "",
        (value) => {
            if (value && value !== "None") {
                onLoadSession(value);
                dropdown.classList.remove("open");
            }
        },
        "Search sessions..."
    );
    sessionSelectContainer.appendChild(sessionSelect);
    addExpandableItem("📂", "Load Session", sessionSelectContainer);

    // === Load Config (expandable) ===
    const configSelectContainer = document.createElement("div");
    const configSelect = createSearchableSelect(
        availableConfigs || [],
        "",
        (value) => {
            if (value && value !== "None") {
                onLoadConfig(value);
                dropdown.classList.remove("open");
            }
        },
        "Search configs..."
    );
    configSelectContainer.appendChild(configSelect);
    addExpandableItem("📂", "Load Config", configSelectContainer);

    // === Save Config (expandable) ===
    const saveContainer = document.createElement("div");
    saveContainer.style.cssText = "display: flex; gap: 6px; align-items: center;";
    const saveNameInput = document.createElement("input");
    saveNameInput.className = "cb-input";
    saveNameInput.style.cssText = "flex: 1; font-size: 12px; padding: 6px 8px;";
    saveNameInput.value = node.state.config_name || "";
    saveNameInput.placeholder = "config_name";
    saveNameInput.onchange = () => {
        node.state.config_name = saveNameInput.value;
        node.saveState();
    };
    const saveBtn = document.createElement("button");
    saveBtn.className = "cb-button primary";
    saveBtn.textContent = "💾 Save";
    saveBtn.style.cssText = "font-size: 12px; padding: 6px 12px;";
    saveBtn.onclick = async (e) => {
        e.stopPropagation();
        node.state.config_name = saveNameInput.value;
        await onSaveConfig();
        saveBtn.textContent = "✅ Saved!";
        setTimeout(() => { saveBtn.textContent = "💾 Save"; }, 2000);
    };
    saveContainer.appendChild(saveNameInput);
    saveContainer.appendChild(saveBtn);
    addExpandableItem("💾", "Save Config", saveContainer);

    addDivider();

    // === Auto-Save toggle ===
    addToggleItem("💾", "Auto-Save (2s)", node.state.auto_save || false, (val) => {
        node.state.auto_save = val;
        node.saveState();
    });

    addDivider();

    // === Enable Distribution toggle ===
    addToggleItem("🌐", "Enable Distribution", node.state.distribution_enabled || false, (val) => {
        node.state.distribution_enabled = val;
        node.saveState();
        node.renderUI();
    });

    addDivider();

    // === Refresh Models action ===
    const refreshItem = document.createElement("div");
    refreshItem.className = "cb-settings-item";
    refreshItem.innerHTML = "<span>🔄</span><span>Refresh Models & LoRAs</span>";
    refreshItem.onclick = async () => {
        refreshItem.querySelector("span:last-child").textContent = "Refreshing...";
        await refreshAllConfigBuilders();
        refreshItem.querySelector("span:last-child").textContent = "✅ Refreshed!";
        setTimeout(() => {
            refreshItem.querySelector("span:last-child").textContent = "Refresh Models & LoRAs";
        }, 2000);
    };
    dropdown.appendChild(refreshItem);

    // === Label Mode toggle ===
    addToggleItem("🏷️", "Label Mode", node.state.label_mode || false, (val) => {
        node.state.label_mode = val;
        node.saveState();
        node.renderUI();
    });

    // === Include None toggle ===
    addToggleItem("⬜", "Include None", node.state.include_none || false, (val) => {
        node.state.include_none = val;
        node.saveState();
    });

    // === Include Default toggle ===
    addToggleItem("⬜", "Include Default", node.state.include_default || false, (val) => {
        node.state.include_default = val;
        node.saveState();
    });

    return dropdown;
}
```

**Step 3: Commit**
```
feat: add top bar and settings dropdown components
```

---

### Task 3: Create Sidebar Component

**Files:**
- Modify: `web/conf_builder/conf-builder-ui-components.js` (add after settings dropdown)

**Step 1: Add `createSidebar()` function**

```javascript
// --- SIDEBAR COMPONENT ---

export function createSidebar(node, mainContent) {
    const sidebar = document.createElement("div");
    sidebar.className = "cb-sidebar";

    const icons = [];

    // Navigation icons
    function addNavIcon(emoji, title, targetId) {
        const btn = document.createElement("button");
        btn.className = "cb-sidebar-icon";
        btn.textContent = emoji;
        btn.title = title;
        btn.dataset.targetId = targetId;
        btn.onclick = () => {
            const target = mainContent.querySelector(`#${targetId}`);
            if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        };
        sidebar.appendChild(btn);
        icons.push(btn);
        return btn;
    }

    addNavIcon("📝", "Global Prompts", "cb-sec-prompts");
    addNavIcon("⚙️", "Config Arrays", "cb-sec-configs");

    // Distribution icon (only when enabled)
    if (node.state.distribution_enabled) {
        addNavIcon("🌐", "Distribution", "cb-sec-distribution");
    }

    addNavIcon("📄", "JSON Preview", "cb-sec-preview");

    // Divider
    const divider = document.createElement("div");
    divider.className = "cb-sidebar-divider";
    sidebar.appendChild(divider);

    // Quick action: Add Config
    const addBtn = document.createElement("button");
    addBtn.className = "cb-sidebar-icon";
    addBtn.textContent = "+";
    addBtn.title = "Add Config";
    addBtn.style.cssText = "font-size: 20px; font-weight: bold;";
    addBtn.onclick = () => {
        // Dispatch to same handler as the Add Config button
        node.state.config_arrays.push({
            name: `Config ${node.state.config_arrays.length + 1}`,
            samplers: ["euler"],
            schedulers: ["normal"],
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
            attention_modes: ["default"],
            resolutions: [],
            model_sampling_override: "none",
            model_sampling_shift: "1.73",
            model_sampling_flux_max_shift: "1.15",
            model_sampling_flux_base_shift: "0.5",
            use_advanced_sampling: false,
            advanced_guider: "cfg_guider",
            advanced_scheduler: "basic",
            use_flux_guidance: false,
            flux_guidance_value: "3.5"
        });
        node.saveState();
        node.renderUI();
    };
    sidebar.appendChild(addBtn);

    // Quick action: Refresh Models
    const refreshBtn = document.createElement("button");
    refreshBtn.className = "cb-sidebar-icon";
    refreshBtn.textContent = "🔄";
    refreshBtn.title = "Refresh Models & LoRAs";
    sidebar.appendChild(refreshBtn);

    // Scroll spy: highlight active section
    const sectionIds = ["cb-sec-prompts", "cb-sec-configs", "cb-sec-distribution", "cb-sec-preview"];
    const updateActiveIcon = () => {
        const scrollTop = mainContent.scrollTop;
        let activeId = sectionIds[0];
        for (const id of sectionIds) {
            const el = mainContent.querySelector(`#${id}`);
            if (el && el.offsetTop - 20 <= scrollTop) {
                activeId = id;
            }
        }
        icons.forEach(btn => {
            btn.classList.toggle("active", btn.dataset.targetId === activeId);
        });
    };
    mainContent.addEventListener("scroll", updateActiveIcon);
    // Initial highlight
    setTimeout(updateActiveIcon, 50);

    return { sidebar, refreshBtn };
}
```

**Step 2: Commit**
```
feat: add sidebar navigation component with scroll spy
```

---

### Task 4: Create Uniform Section Header Helper

**Files:**
- Modify: `web/conf_builder/conf-builder-ui-components.js` (add after sidebar)

**Step 1: Add `createSectionHeader()` function**

```javascript
// --- UNIFORM SECTION HEADER ---

const SECTION_ACCENTS = {
    prompts: "#00cc55",
    configs: "#0088ff",
    distribution: "#ff8800",
    preview: "#00cccc"
};

export function createSectionHeader(emoji, title, accentKey, { collapsible = false, collapsed = false, onToggle = null } = {}) {
    const header = document.createElement("div");
    header.className = "cb-section-header";
    header.style.cssText = `
        background: linear-gradient(90deg, ${SECTION_ACCENTS[accentKey] || "#0088ff"}22, transparent);
        border-left: 3px solid ${SECTION_ACCENTS[accentKey] || "#0088ff"};
    `;

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `${emoji} ${title}`;
    header.appendChild(titleSpan);

    if (collapsible) {
        header.style.cursor = "pointer";
        const arrow = document.createElement("span");
        arrow.textContent = collapsed ? "▶" : "▼";
        arrow.style.cssText = "margin-left: auto; font-size: 12px; color: #888;";
        header.appendChild(arrow);

        header.onclick = () => {
            if (onToggle) onToggle();
        };
    }

    return header;
}
```

**Step 2: Commit**
```
feat: add uniform section header component with accent colors
```

---

### Task 5: Restructure renderUI() — New Layout with Top Bar + Sidebar

**Files:**
- Modify: `web/conf_builder/conf-builder-config-management.js:3837-3963` (renderUI function)

This is the main layout restructure. The renderUI function changes from:
1. `cb-container` > topRow (3 sections) > globalPrompts > configArrays > preview

To:
1. `cb-container` > topBar (sticky) > layoutWrapper (sidebar | mainContent)
2. In mainContent: globalPrompts > configArrays > distributionSettings > preview

**Step 1: Update imports**

At the top of the file (line ~19-24), update the import from `conf-builder-ui-components.js` to include new exports:

```javascript
import {
    createSearchableSelect,
    createSlider,
    createInputGroup,
    getStyles,
    createTopBar,
    createSidebar,
    createSectionHeader
} from './conf-builder-ui-components.js';
```

**Step 2: Replace the renderUI function body**

The new renderUI function should:

1. Save scroll from `.cb-main-content` (not `.cb-container`)
2. Inject styles + `cb-container` root
3. Create top bar with `createTopBar()`
4. Create layout wrapper (flex row)
5. Create main content area
6. Create sidebar with `createSidebar()` — pass mainContent for scroll spy
7. In main content: render sections with IDs and uniform headers
8. Wire up the sidebar refresh button
9. Restore scroll on `.cb-main-content`

Replace lines 3837-3963 with the new version. Key changes:

- Remove the `topRow` creation and the 3 `render*Section` calls
- Replace `root.appendChild(topRow)` with top bar
- Add sidebar + layout wrapper
- Add `id="cb-sec-prompts"` to Global Prompts section
- Add `id="cb-sec-configs"` to Config Arrays section
- Add `id="cb-sec-distribution"` to Distribution section (conditionally)
- Add `id="cb-sec-preview"` to Preview section
- Use `createSectionHeader()` for each section title instead of inline `.cb-section-title`
- Remove the old sticky nav bar (replaced by sidebar)
- Keep config nav bar inside config section (it supplements the sidebar for config-specific navigation)

**Step 3: Update renderGlobalPromptsSection**

Change the section header from inline-styled `.cb-section-title` to use `createSectionHeader()`:

Replace the header creation in `renderGlobalPromptsSection` (~line 3571-3593) to:
- Add `id="cb-sec-prompts"` to the section element
- Use `createSectionHeader("📝", "Global Prompts", "prompts", { collapsible: true, ... })` instead of the manual header

**Step 4: Update renderPreviewSection**

Change the section header (~line 3819-3828):
- Add `id="cb-sec-preview"` to the section element
- Use `createSectionHeader("📄", "JSON Preview", "preview")` instead of inline title

**Step 5: Commit**
```
feat: restructure renderUI with top bar, sidebar, and uniform section headers
```

---

### Task 6: Refactor Distribution Section as Standalone Full-Width Section

**Files:**
- Modify: `web/conf_builder/conf-builder-distribution.js`

**Step 1: Add new export for standalone distribution section**

Add a new function `renderDistributionSettingsSection()` that renders the distribution controls as a full-width section (not inside the top row). This function:

- Creates a `cb-section full-width` div with `id="cb-sec-distribution"`
- Uses `createSectionHeader("🌐", "Distribution Settings", "distribution")`
- Contains all the existing distribution details (worker URLs, claim timeout, master encoding) but NOT the enable/disable toggle (that's now in Settings dropdown)
- Only rendered when `node.state.distribution_enabled === true`

Keep the original `renderDistributionSection()` function intact (DO NOT REMOVE) but it will no longer be called from renderUI.

**Step 2: Import `createSectionHeader` in distribution module**

```javascript
import { createInputGroup, createSlider, createSectionHeader } from './conf-builder-ui-components.js';
```

**Step 3: Commit**
```
feat: add standalone distribution settings section for new layout
```

---

### Task 7: Verify & Commit

**Step 1: JS brace balance check**

Verify all modified JS files have balanced braces/parens.

**Step 2: Visual review**

Check that all section IDs are consistent between sidebar nav targets and section elements.

**Step 3: Final commit**

```
feat: builder UI overhaul — top bar, sidebar nav, uniform headers, dark mode contrast
```
