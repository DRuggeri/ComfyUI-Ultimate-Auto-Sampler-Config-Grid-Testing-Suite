# Builder UI & Dashboard Improvements Implementation Plan

**Critical Constraint:** DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

---

## Task 1: Double Prompt JSON Editor Size (Easy)
**File:** `web/conf_builder/conf-builder-ui-components.js`
- Change `.cb-prompt-raw-editor` `min-height: 80px` → `min-height: 160px`

## Task 2: Sidebar Always-Open + Icon Changes
**File:** `web/conf_builder/conf-builder-ui-components.js`
- CSS: Change `.cb-sidebar-sub-icons` `display: none` → `display: flex`
- CSS: Remove `.cb-sidebar-config-group:hover .cb-sidebar-sub-icons` rule
- CSS: Add `overflow-y: auto` to sidebar container
- JS: Change config icon content from `idx+1` to `⚙️${idx+1}`
- JS: Change TE icon from "📎" to "🔣"
- JS: Change LoRA icon from "🔗" to "🔮"

## Task 3: Dashboard Shift+N Column Hotkeys
**File:** `resources/logic_virtual.js`
- Add cases in `setupKeyboardShortcuts()` for digits 0-9 with shiftKey

## Task 4: Dashboard Session Landing & Reload
**Files:** `resources/template.html`, `resources/logic_utils.js`, `resources/logic_init.js`, `resources/report.css`, `__init__.py`
- Rename topbar load button
- Add list_sessions endpoint
- Add landing page rendering
- Add session dropdown in cog menu

## Task 5: Distribution Settings Refactor
**Files:** `web/conf_builder/conf-builder-distribution.js`, `web/conf_builder/conf-builder-config-management.js`, `config_builder_node.py`, `sampler_node.py`, `generation_orchestrator.py`
- Always show distribution toggle
- Embed distribution_config in configs_json
- Remove separate output/input
