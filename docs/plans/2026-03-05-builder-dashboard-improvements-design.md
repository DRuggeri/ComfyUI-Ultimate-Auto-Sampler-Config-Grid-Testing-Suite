# Builder UI & Dashboard Improvements Design

## Item 1: Double Prompt JSON Editor Size

**Change:** In `conf-builder-ui-components.js`, update `.cb-prompt-raw-editor` CSS class from `min-height: 80px` to `min-height: 160px`. The `resize: vertical` property is already set so users can still manually adjust.

## Item 2: Sidebar Always-Open Config Sub-Icons + Icon Changes

**Current:** Per-config sidebar groups show sub-icons (Models, TE, VAE, LoRAs) only on hover via CSS `.cb-sidebar-config-group:hover .cb-sidebar-sub-icons { display: flex; }`.

**Changes:**
1. Change `.cb-sidebar-sub-icons` from `display: none` to `display: flex` (always visible)
2. Remove the `:hover` rule (no longer needed)
3. Change config icon labels from numbered circles ("1", "2") to "⚙️1", "⚙️2" etc.
4. Change Text Encoders icon from "📎" to "🔣"
5. Change LoRAs icon from "🔗" to "🔮"
6. If sidebar overflows vertically, make it scrollable with `overflow-y: auto`

## Item 3: Dashboard Shift+N Column Hotkeys

**Change:** Add keyboard listener in `resources/logic_virtual.js` `setupKeyboardShortcuts()` for `Shift+1` through `Shift+9` to set column count. Update the `#col-count` input value, save to localStorage, and call `recalcColumns()`. Skip if focus is in an input/textarea. Shift+0 resets to auto mode.

## Item 4: Dashboard Session Landing & Reload

### 4a: Rename Load Session Button
Change topbar button from folder icon + "Load Session" title to a refresh/reload icon + "Reload Session" title. The button calls the existing `loadSession()` function.

### 4b: Session Landing Page
On page load with no session data (empty manifest), show a landing page with session cards instead of an empty grid. Each card shows:
- Session name
- First image as thumbnail (loaded from `/view?filename=...&type=output&subfolder=benchmarks/{name}/`)
- Modification date
- Item count from manifest

**Implementation:**
- Add a new backend endpoint `GET /config_tester/list_sessions` that returns `[{name, item_count, first_image, mtime}]` sorted by most recent
- In `logic_init.js`, after init(), check if `fullManifest.items` is empty. If so, call the list endpoint and render session cards
- Clicking a card calls `loadSession()` with that session name
- Add the same dropdown to the Settings cog panel SESSION section

### 4c: Settings Cog Session Dropdown
Add a `<select>` dropdown in the SESSION section of the cog menu populated from the list_sessions endpoint. Selecting a session loads it.

## Item 5: Distribution Settings Refactor

### 5a: Always-Visible Toggle
Distribution Settings section currently only renders when `node.state.distribution_enabled` is true. Change to:
1. Always render the section at the top
2. Show a simple On/Off toggle at the top
3. When Off, collapse/hide all settings below the toggle
4. When On, show full settings as before

### 5b: Remove Separate distribution_config Output/Input (Clean Break)
**Config Builder (`config_builder_node.py`):**
- Change `RETURN_TYPES` from `("STRING", "STRING", "STRING")` to `("STRING", "STRING")`
- Change `RETURN_NAMES` from `("configs_json", "session_name", "distribution_config")` to `("configs_json", "session_name")`
- Embed distribution_config data inside the configs_json output as a top-level `_distribution` key
- Return format: `{"configs": [...], "_distribution": {...}}` instead of just `[...]`

**Sampler Node (`sampler_node.py`):**
- Remove `distribution_config` from optional INPUT_TYPES
- Remove `distribution_config` parameter from `run_tests()`
- Parse distribution config from within `configs_json` (look for `_distribution` key)

**Generation Orchestrator (`generation_orchestrator.py`):**
- Update `run_generation_loop()` signature to remove `distribution_config` parameter
- Extract `_distribution` from the parsed configs_json data instead
