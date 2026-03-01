# Per-Config Resolutions in Builder UI

**Date:** 2026-03-01
**Status:** Approved

## Summary

Add per-config resolution support to the Builder UI. Each config array gets its own
resolution list displayed as chips (same pattern as samplers/schedulers). Resolutions
flow through `configs_json` and override the sampler node's `resolutions_json` input
on a per-config basis.

## Requirements

1. **Per-config scope:** Each config array has its own resolution list, independent of
   other config arrays.
2. **Override behavior:** If a config includes resolutions, they replace the sampler
   node's `resolutions_json` for that config. If a config has NO resolutions, the
   sampler's `resolutions_json` is used as fallback.
3. **Categorized preset dropdown:** Quick-add dropdown organized by model type
   (SD 1.5, SDXL, Flux) with sub-categories for orientation (Square, Portrait,
   Landscape), sizes listed largest to smallest within each sub-category.
4. **Custom resolution input:** W x H number inputs for arbitrary resolutions.
5. **Chip display:** Selected resolutions shown as removable chips with x button,
   matching the visual pattern of samplers/schedulers.

## UI Design

### Preset Dropdown Structure (using native `<optgroup>`)

```
── SD 1.5 — Square ──
  512 x 512
── SD 1.5 — Portrait ──
  512 x 896
  512 x 768
── SD 1.5 — Landscape ──
  896 x 512
  768 x 512
── SDXL — Square ──
  1024 x 1024
── SDXL — Portrait ──
  768 x 1344
  832 x 1216
  896 x 1152
── SDXL — Landscape ──
  1344 x 768
  1216 x 832
  1152 x 896
── Flux — Square ──
  1024 x 1024
── Flux — Portrait ──
  768 x 1344
  832 x 1216
── Flux — Landscape ──
  1344 x 768
  1216 x 832
```

### Custom Input

Small inline W x H number inputs with an Add button for arbitrary resolutions.

### Chip Display

Amber-accented (#cc8800) rounded chips showing "WxH" with x remove button.
Clear button to remove all. Same visual pattern as samplers/schedulers.

## Data Flow

### State Storage

```javascript
configArray.resolutions = ["1024x1024", "832x1216", "1344x768"]
```

Array of "WxH" strings, same pattern as `configArray.samplers`.

### Config JSON Output

In `convertStateToConfigs()`, resolutions are converted to nested arrays:

```json
{
    "sampler": ["euler"],
    "scheduler": ["normal"],
    "resolutions": [[1024, 1024], [832, 1216], [1344, 768]]
}
```

Only included when the config has resolutions specified (omitted = use sampler fallback).

### Config Expansion

In `expand_configs()`, resolutions become another axis of the Cartesian product.
Each expanded config gets a single `"resolution": [w, h]` field.

### Generation Loop Override

In the orchestrator, if an expanded config has a `resolution` field, it provides
its own width/height instead of using the global `input_jobs` from `resolutions_json`.

Configs WITHOUT resolutions continue to iterate over the sampler's `input_jobs`
as before.

## Files Changed

| File | Change |
|------|--------|
| `conf-builder-config-management.js` | New resolution chip builder with categorized optgroup dropdown + custom input |
| `conf-builder-utilities.js` | Add `resolutions` to `convertStateToConfigs()` output |
| `config_utils.py` | Expand `resolutions` array in `expand_configs()` Cartesian product |
| `generation_orchestrator.py` | Per-config resolution override in generation loop |
| `conf-builder-main.js` | State migration: add empty `resolutions: []` to existing config arrays |
