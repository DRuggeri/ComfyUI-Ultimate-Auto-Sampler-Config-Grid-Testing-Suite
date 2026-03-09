# Favorites Workflow Packing & Cleanup Design

## Overview

Extend the Dashboard's "Export Favorites" section with workflow embedding, manifest export, and non-favorite cleanup.

## Features

### 1. New Checkboxes (3 new, after existing 4)

**Copy cleaned favorites-only manifest** (`copy-manifest-checkbox`, default checked)
- Copies `manifest.json` filtered to only favorited items into `favorites/manifest.json`

**Pack full ComfyUI workflow into image metadata** (`pack-workflow-checkbox`, default unchecked)
- Captures current ComfyUI graph via `app.graph.serialize()` from the parent window
- Embeds as `"workflow"` PNG text chunk so dragging into ComfyUI loads the full node graph

**Pack config data as pure nodes workflow** (`pack-nodes-workflow-checkbox`, default unchecked)
- Per-image: generates a standalone workflow (Checkpoint → LoRAs → CLIP → KSampler → VAEDecode → Preview) from that image's config data
- Reuses logic from `copyConfigsAsComfyNodes()` in the REVISE modal
- Embeds as `"workflow"` PNG text chunk
- If both workflow checkboxes are checked, this one takes priority (more specific per-image)

### 2. Workflow Capture & Data Flow

**Current workflow capture (JS side):**
- In `exportFavorites()`, when pack-workflow is checked: `app.graph.serialize() || window.parent?.app?.graph?.serialize()`
- Serialized workflow JSON sent as `workflow_data` in POST body

**Per-image nodes workflow (JS side):**
- Extract workflow-building logic from `copyConfigsAsComfyNodes()` into reusable `buildComfyNodesWorkflow(itemData)` returning JSON object
- Generate per-image, send as array alongside favorited items

**Backend (`__init__.py`):**
- `export_favorites` receives new params: `pack_workflow`, `pack_nodes_workflow`, `copy_manifest`, `workflow_data`, `nodes_workflows`
- Pass workflow data through to `pack_metadata_into_image()`

**`metadata_packer.py` fix:**
- Line 429: Change `if True:` to `if not workflow_data_full:` — fixes bug where `workflowExample` always overrides actual workflow

**Cleaned manifest:**
- Filter `manifest["items"]` to favorited-only, write to `favorites/manifest.json`

### 3. DELETE ALL NON FAVORITED ITEMS

**UI:** Big red button below all checkboxes in Export Favorites section.

**Flow:**
1. `window.confirm("Are you sure you want to delete all non-favorited items? This cannot be undone.")`
2. POST `/config_tester/delete_non_favorites` with `session_name`
3. Backend: load manifest, delete non-favorited image files, update manifest, save
4. Frontend: show status, refresh dashboard

## Files Affected

### Python:
- `__init__.py` — export_favorites endpoint (new params), new delete_non_favorites endpoint
- `metadata_packer.py` — fix line 429 `if True:` bug

### JavaScript:
- `resources/template.html` — 3 new checkboxes + delete button in Export Favorites section
- `resources/logic_utils.js` — exportFavorites() new params, workflow capture, deleteNonFavorites() function
- `resources/logic_ui.js` — extract `buildComfyNodesWorkflow()` from `copyConfigsAsComfyNodes()`
