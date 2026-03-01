# Builder UI Fixes & Enhancements Design

**Date:** 2026-03-01
**Status:** Approved

## Summary

Five targeted improvements to the Builder UI: fix VAE/TE bypass toggle JSON
output, add force_refresh tag comparison prompts, add Remote VAE presets
dropdown, add per-config sidebar navigation, and reorganize sections with
improved header contrast.

## Item 1: VAE/TE On/Off Switch Fix

**Problem:** Bypassed VAEs and TEs still appear in JSON Preview despite being
toggled off. The bypass toggle onclick handler updates visual state and calls
`node.saveState()` but does NOT call `updatePreview(node)`, so the JSON preview
shows stale data.

**Root cause:** In `conf-builder-config-management.js`, the bypass toggle in
`createVAEElement()` (line ~2713-2721) and similar handlers for TE and model
bypass toggles do not trigger `updatePreview(node)`.

**Fix:**
- Add `updatePreview(node)` call after `node.saveState()` in every bypass
  toggle onclick handler (VAE, TE, model)
- Add `normalizePath()` safety to bypass state filter key lookups in
  `convertStateToConfigs()` to guard against path separator mismatches

**Files:** `conf-builder-config-management.js`, `conf-builder-utilities.js`

## Item 2: force_refresh Lora Tags Update Prompt

**Problem:** When force_refresh re-fetches CivitAI metadata, the system
overwrites without checking if tags changed. User wants to see what changed
and choose whether to update.

**Backend changes:**
- In `config_builder_node.py` `lookup_lora_metadata_endpoint`: when
  `force_refresh=True`, compare fresh `trainedWords` with stored tags from
  `loras_tags.json`
- Return additional fields: `tags_changed: bool`, `old_tags: list`,
  `new_tags: list`

**Frontend changes:**
- In the CivitAI metadata modal re-fetch handler: check response for
  `tags_changed`
- Show inline diff banner with old/new tags and Update/Keep buttons
- Update button writes new tags to `loras_tags.json` via existing save endpoint

**Files:** `config_builder_node.py`, `lora_utils.py`,
`conf-builder-config-management.js`

## Item 3: HF Remote VAE Presets Dropdown

**Problem:** When "Remote URL" VAE type is selected, user must manually paste
HuggingFace URLs. The URLs are already defined in Python (`remote_vae.py`
`HF_ENDPOINTS`) but not exposed to the frontend.

**Fix:**
- Define `REMOTE_VAE_PRESETS` constant in JS matching Python's `HF_ENDPOINTS`:
  `{ "HF-SD": "url", "HF-SDXL": "url", "HF-Flux": "url", "HF-HunyuanVideo": "url" }`
- In `createVAEElement()`, when type selector changes to "Remote URL", show a
  presets dropdown below the type selector
- Selecting a preset auto-fills the URL input
- "Custom" option leaves URL input empty for manual entry

**Files:** `conf-builder-config-management.js`

## Item 4: Per-Config Sidebar Navigation

**Problem:** Sidebar only has one "Config Arrays" icon. With multiple config
arrays, there's no way to quickly jump to a specific config's sub-section.

**Fix:**
- Below the main ⚙️ Config Arrays icon, show numbered cog icons (one per
  config array), color-coded using `CONFIG_COLORS`
- Hovering a config cog icon expands the sidebar vertically to show sub-section
  icons: Models, Text Encoders, VAE, LoRAs
- Clicking a sub-icon scrolls to that specific sub-section
- Add `id` attributes to sub-section containers:
  `cb-config-{idx}-models`, `cb-config-{idx}-te`, `cb-config-{idx}-vae`,
  `cb-config-{idx}-loras`
- Scroll spy highlights the active config cog

**Files:** `conf-builder-ui-components.js`, `conf-builder-config-management.js`

## Item 5: Section Organization & Header Fixes

**Problem:** Section order and header contrast need improvement for dark mode.

**Changes:**
- **Section order:** Distribution Settings (top) → Global Prompts → Config
  Arrays → JSON Preview
- **Extra Model & Sampling Options:** Move inside Models section as a
  sub-section, rendered just below the models list
- **Text Encoders header:** Brighter to match Models section header style
- **VAE header:** Lighter background (`#444` instead of `#3a3a3a`), brighter
  text color (`#cc66ff`)
- **LoRAs header:** Brighter text (`#4499ff`)

**Files:** `conf-builder-config-management.js`, `conf-builder-ui-components.js`

## Files Changed Summary

| File | Changes |
|------|---------|
| `conf-builder-config-management.js` | Bypass toggle fix (Item 1), tag diff UI (Item 2), Remote VAE presets (Item 3), sub-section IDs (Item 4), section reorder + header colors (Item 5) |
| `conf-builder-utilities.js` | Path normalization in bypass filter (Item 1) |
| `conf-builder-ui-components.js` | Per-config sidebar nav (Item 4), header style updates (Item 5) |
| `config_builder_node.py` | Tag comparison in force_refresh (Item 2) |
| `lora_utils.py` | Tag comparison helper (Item 2) |
| `conf-builder-distribution.js` | No changes (section already has standalone renderer) |
