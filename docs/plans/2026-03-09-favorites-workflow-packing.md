# Favorites Workflow Packing & Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add workflow embedding, manifest export, and non-favorite deletion to the Dashboard's Export Favorites section.

**Architecture:** Three new checkboxes + one delete button in `template.html`. JS captures workflow data and sends to backend. Backend embeds workflow into PNG metadata via existing `pack_metadata_into_image()`. Separate endpoint for deleting non-favorites. Node workflow generation extracted from existing `copyConfigsAsComfyNodes()` into reusable function.

**Tech Stack:** Python (PIL, PngInfo, shutil, json), JavaScript (DOM, fetch, ComfyUI app API)

---

## CRITICAL RULE

**DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.**

---

## Task 1: Add New Checkboxes + Delete Button to Template

**Files:**
- Modify: `resources/template.html:219-228`

**Step 1: Add three new checkboxes and delete button**

In `resources/template.html`, find line 226 (the closing `</div>` of the export-prompt-txt checkbox). After line 226, and before line 228 (`<div id="export-status"`), add:

```html
                <div style="margin-top: 8px; display: flex; align-items: center; gap: 6px;">
                    <input type="checkbox" checked id="copy-manifest-checkbox"
                        style="width: 14px; height: 14px; cursor: pointer;">
                    <label for="copy-manifest-checkbox"
                        style="font-size: 10px; color: #999; cursor: pointer; user-select: none;">
                        Copy cleaned favorites-only manifest into favorites folder
                    </label>
                </div>

                <div style="margin-top: 8px; display: flex; align-items: center; gap: 6px;">
                    <input type="checkbox" id="pack-workflow-checkbox"
                        style="width: 14px; height: 14px; cursor: pointer;">
                    <label for="pack-workflow-checkbox"
                        style="font-size: 10px; color: #999; cursor: pointer; user-select: none;">
                        Pack full ComfyUI workflow into image metadata (drag into ComfyUI to load)
                    </label>
                </div>

                <div style="margin-top: 8px; display: flex; align-items: center; gap: 6px;">
                    <input type="checkbox" id="pack-nodes-workflow-checkbox"
                        style="width: 14px; height: 14px; cursor: pointer;">
                    <label for="pack-nodes-workflow-checkbox"
                        style="font-size: 10px; color: #999; cursor: pointer; user-select: none;">
                        Pack config data as pure nodes workflow into image metadata
                    </label>
                </div>
```

Then after the `<div id="export-status"...></div>` line (line 228), add the delete button:

```html
                <button class="session-action-btn"
                    style="background: #cc2222; width: 100%; font-size: 11px; padding: 10px; margin-top: 12px; border: 2px solid #ff4444;"
                    onclick="deleteNonFavorites()" title="Permanently delete all non-favorited images and update manifest">
                    🗑️ DELETE ALL NON FAVORITED ITEMS
                </button>
                <div id="delete-status" style="margin-top: 4px; font-size: 10px; color: #666; min-height: 16px;"></div>
```

**Step 2: Commit**

```bash
git add resources/template.html
git commit -m "feat: add workflow packing checkboxes and delete non-favorites button to template"
```

---

## Task 2: Extract buildComfyNodesWorkflow from copyConfigsAsComfyNodes

**Files:**
- Modify: `resources/logic_ui.js:692-1001`

**Step 1: Create reusable buildComfyNodesWorkflow function**

In `resources/logic_ui.js`, add a new function BEFORE `copyConfigsAsComfyNodes` (before line 692). This function takes an item data object and returns a workflow JSON object. It contains the workflow-building logic extracted from `copyConfigsAsComfyNodes`:

```javascript
// Build a pure ComfyUI nodes workflow JSON from image config data
// Reusable version of the clipboard copy logic — returns the workflow object
function buildComfyNodesWorkflow(d) {
    // Parse LoRA string into array
    const loras = [];
    if (d.lora && d.lora !== "None") {
        const loraEntries = d.lora.split(' + ').filter(e => e.trim().length > 0);
        loraEntries.forEach(entry => {
            const parts = entry.split(':');
            const name = parts[0];
            const strength_model = parseFloat(parts[1] || 1.0);
            const strength_clip = parseFloat(parts[2] || strength_model);
            loras.push({ name, strength_model, strength_clip });
        });
    }

    // Generate node IDs
    let nodeId = 1;
    const checkpointNode = nodeId++;
    const loraNodes = loras.map(() => nodeId++);
    const positiveClipNode = nodeId++;
    const negativeClipNode = nodeId++;
    const emptyLatentNode = nodeId++;
    const ksamplerNode = nodeId++;
    const vaeDecodeNode = nodeId++;
    const previewNode = nodeId++;

    if (!crypto.randomUUID) {
        crypto.randomUUID = function () {
            return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, c =>
                (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
            );
        };
    }

    const workflow = {
        id: crypto.randomUUID(),
        revision: 0,
        last_node_id: nodeId - 1,
        last_link_id: 100,
        nodes: [],
        links: [],
        groups: [],
        config: {},
        extra: {
            workflowRendererVersion: "LG",
            ds: { scale: 0.573, offset: [488, 377] }
        },
        version: 0.4
    };

    // Checkpoint
    workflow.nodes.push({
        id: checkpointNode,
        type: "CheckpointLoaderSimple",
        pos: [-200, 60],
        size: [315, 98],
        flags: {}, order: 0, mode: 0,
        inputs: [],
        outputs: [
            { name: "MODEL", type: "MODEL", links: [] },
            { name: "CLIP", type: "CLIP", links: [] },
            { name: "VAE", type: "VAE", links: [] }
        ],
        properties: { "Node name for S&R": "CheckpointLoaderSimple" },
        widgets_values: [d.model || ""]
    });

    // LoRAs
    loras.forEach((lora, index) => {
        workflow.nodes.push({
            id: loraNodes[index],
            type: "LoraLoader",
            pos: [170 + (index * 312), 60],
            size: [270, 126],
            flags: {}, order: index + 1, mode: 0,
            inputs: [
                { name: "model", type: "MODEL", link: null },
                { name: "clip", type: "CLIP", link: null }
            ],
            outputs: [
                { name: "MODEL", type: "MODEL", links: [] },
                { name: "CLIP", type: "CLIP", links: [] }
            ],
            properties: { "Node name for S&R": "LoraLoader" },
            widgets_values: [String(lora.name).replace(/\//g, "\\"), lora.strength_model, lora.strength_clip]
        });
    });

    const posX = 910 + (loras.length * 312);

    // Positive Clip
    workflow.nodes.push({
        id: positiveClipNode,
        type: "CLIPTextEncode",
        pos: [posX, 3.52],
        size: [460, 190],
        flags: {}, order: loras.length + 1, mode: 0,
        inputs: [{ name: "clip", type: "CLIP", link: null }],
        outputs: [{ name: "CONDITIONING", type: "CONDITIONING", links: [] }],
        properties: { "Node name for S&R": "CLIPTextEncode" },
        widgets_values: [d.positive || ""]
    });

    // Negative Clip
    workflow.nodes.push({
        id: negativeClipNode,
        type: "CLIPTextEncode",
        pos: [posX, 240],
        size: [470, 200],
        flags: {}, order: loras.length + 2, mode: 0,
        inputs: [{ name: "clip", type: "CLIP", link: null }],
        outputs: [{ name: "CONDITIONING", type: "CONDITIONING", links: [] }],
        properties: { "Node name for S&R": "CLIPTextEncode" },
        widgets_values: [d.negative || ""]
    });

    // Empty Latent
    workflow.nodes.push({
        id: emptyLatentNode,
        type: "EmptyLatentImage",
        pos: [posX + 130, 510],
        size: [270, 106],
        flags: {}, order: 1, mode: 0,
        inputs: [],
        outputs: [{ name: "LATENT", type: "LATENT", links: [] }],
        properties: { "Node name for S&R": "EmptyLatentImage" },
        widgets_values: [d.width || 1080, d.height || 1584, 1]
    });

    // KSampler
    const sampX = posX + 510;
    workflow.nodes.push({
        id: ksamplerNode,
        type: "KSampler",
        pos: [sampX, 23.52],
        size: [315, 708],
        flags: {}, order: loras.length + 3, mode: 0,
        inputs: [
            { name: "model", type: "MODEL", link: null },
            { name: "positive", type: "CONDITIONING", link: null },
            { name: "negative", type: "CONDITIONING", link: null },
            { name: "latent_image", type: "LATENT", link: null }
        ],
        outputs: [{ name: "LATENT", type: "LATENT", links: [] }],
        properties: { "Node name for S&R": "KSampler" },
        widgets_values: [
            d.seed || 0, "fixed", d.steps || 25, d.cfg || 7,
            d.sampler || "dpmpp_2m", d.scheduler || "karras", d.denoise || 1
        ]
    });

    // VAE Decode
    workflow.nodes.push({
        id: vaeDecodeNode,
        type: "VAEDecode",
        pos: [sampX + 390, 33],
        size: [210, 46],
        flags: {}, order: loras.length + 4, mode: 0,
        inputs: [
            { name: "samples", type: "LATENT", link: null },
            { name: "vae", type: "VAE", link: null }
        ],
        outputs: [{ name: "IMAGE", type: "IMAGE", links: [] }],
        properties: { "Node name for S&R": "VAEDecode" },
        widgets_values: []
    });

    // Preview
    workflow.nodes.push({
        id: previewNode,
        type: "PreviewImage",
        pos: [sampX + 370, 173],
        size: [418, 556],
        flags: {}, order: loras.length + 5, mode: 0,
        inputs: [{ name: "images", type: "IMAGE", link: null }],
        outputs: [],
        properties: { "Node name for S&R": "PreviewImage" },
        widgets_values: []
    });

    // Wire nodes
    const getNode = (id) => workflow.nodes.find(n => n.id === id);
    let linkId = 1;

    let currentModelSource = { id: checkpointNode, slot: 0 };
    let currentClipSource = { id: checkpointNode, slot: 1 };

    // Daisy chain LoRAs
    for (let i = 0; i < loras.length; i++) {
        const thisLoraId = loraNodes[i];
        workflow.links.push([linkId, currentModelSource.id, currentModelSource.slot, thisLoraId, 0, "MODEL"]);
        getNode(currentModelSource.id).outputs[currentModelSource.slot].links.push(linkId);
        getNode(thisLoraId).inputs[0].link = linkId;
        linkId++;
        workflow.links.push([linkId, currentClipSource.id, currentClipSource.slot, thisLoraId, 1, "CLIP"]);
        getNode(currentClipSource.id).outputs[currentClipSource.slot].links.push(linkId);
        getNode(thisLoraId).inputs[1].link = linkId;
        linkId++;
        currentModelSource = { id: thisLoraId, slot: 0 };
        currentClipSource = { id: thisLoraId, slot: 1 };
    }

    // Final Model -> KSampler
    workflow.links.push([linkId, currentModelSource.id, currentModelSource.slot, ksamplerNode, 0, "MODEL"]);
    getNode(currentModelSource.id).outputs[currentModelSource.slot].links.push(linkId);
    getNode(ksamplerNode).inputs[0].link = linkId;
    linkId++;

    // Final CLIP -> Positive Prompt
    workflow.links.push([linkId, currentClipSource.id, currentClipSource.slot, positiveClipNode, 0, "CLIP"]);
    getNode(currentClipSource.id).outputs[currentClipSource.slot].links.push(linkId);
    getNode(positiveClipNode).inputs[0].link = linkId;
    linkId++;

    // Final CLIP -> Negative Prompt
    workflow.links.push([linkId, currentClipSource.id, currentClipSource.slot, negativeClipNode, 0, "CLIP"]);
    getNode(currentClipSource.id).outputs[currentClipSource.slot].links.push(linkId);
    getNode(negativeClipNode).inputs[0].link = linkId;
    linkId++;

    // VAE: Checkpoint -> VAE Decode
    workflow.links.push([linkId, checkpointNode, 2, vaeDecodeNode, 1, "VAE"]);
    getNode(checkpointNode).outputs[2].links.push(linkId);
    getNode(vaeDecodeNode).inputs[1].link = linkId;
    linkId++;

    // Conditioning: Positive -> KSampler
    workflow.links.push([linkId, positiveClipNode, 0, ksamplerNode, 1, "CONDITIONING"]);
    getNode(positiveClipNode).outputs[0].links.push(linkId);
    getNode(ksamplerNode).inputs[1].link = linkId;
    linkId++;

    // Conditioning: Negative -> KSampler
    workflow.links.push([linkId, negativeClipNode, 0, ksamplerNode, 2, "CONDITIONING"]);
    getNode(negativeClipNode).outputs[0].links.push(linkId);
    getNode(ksamplerNode).inputs[2].link = linkId;
    linkId++;

    // Latent: Empty Latent -> KSampler
    workflow.links.push([linkId, emptyLatentNode, 0, ksamplerNode, 3, "LATENT"]);
    getNode(emptyLatentNode).outputs[0].links.push(linkId);
    getNode(ksamplerNode).inputs[3].link = linkId;
    linkId++;

    // Latent: KSampler -> VAE Decode
    workflow.links.push([linkId, ksamplerNode, 0, vaeDecodeNode, 0, "LATENT"]);
    getNode(ksamplerNode).outputs[0].links.push(linkId);
    getNode(vaeDecodeNode).inputs[0].link = linkId;
    linkId++;

    // Image: VAE Decode -> Preview
    workflow.links.push([linkId, vaeDecodeNode, 0, previewNode, 0, "IMAGE"]);
    getNode(vaeDecodeNode).outputs[0].links.push(linkId);
    getNode(previewNode).inputs[0].link = linkId;
    linkId++;

    workflow.last_link_id = linkId;
    return workflow;
}
```

**Step 2: Refactor copyConfigsAsComfyNodes to use the new function**

In `copyConfigsAsComfyNodes` (line 692), replace lines 702-979 (everything inside the `try` block before the clipboard copy logic at line 980) with a call to the new function:

Replace from `// Parse LoRA string into array` through `workflow.last_link_id = linkId;` (lines 703-978) with:

```javascript
        const workflow = buildComfyNodesWorkflow(d);
```

Keep the existing clipboard copy logic (lines 980-1001+) unchanged.

**Step 3: Commit**

```bash
git add resources/logic_ui.js
git commit -m "refactor: extract buildComfyNodesWorkflow from copyConfigsAsComfyNodes"
```

---

## Task 3: Update exportFavorites JS to Send New Parameters

**Files:**
- Modify: `resources/logic_utils.js:252-340`

**Step 1: Add checkbox reads and workflow capture**

In `resources/logic_utils.js`, in the `exportFavorites()` function, after line 279 (the `exportPromptTxt` variable), add:

```javascript
    // Get copy manifest checkbox state
    const copyManifestCheckbox = document.getElementById('copy-manifest-checkbox');
    const copyManifest = copyManifestCheckbox ? copyManifestCheckbox.checked : true;

    // Get pack workflow checkbox state
    const packWorkflowCheckbox = document.getElementById('pack-workflow-checkbox');
    const packWorkflow = packWorkflowCheckbox ? packWorkflowCheckbox.checked : false;

    // Get pack nodes workflow checkbox state
    const packNodesWorkflowCheckbox = document.getElementById('pack-nodes-workflow-checkbox');
    const packNodesWorkflow = packNodesWorkflowCheckbox ? packNodesWorkflowCheckbox.checked : false;

    // Capture current ComfyUI workflow if pack_workflow is checked
    let workflowData = null;
    if (packWorkflow) {
        try {
            const app = window.app || window.parent?.app;
            if (app && app.graph) {
                workflowData = app.graph.serialize();
                console.log('[Export] Captured current ComfyUI workflow');
            } else {
                console.warn('[Export] Could not access ComfyUI app.graph — workflow will not be packed');
            }
        } catch (e) {
            console.warn('[Export] Error capturing workflow:', e);
        }
    }

    // Generate per-image nodes workflows if pack_nodes_workflow is checked
    let nodesWorkflows = null;
    if (packNodesWorkflow && typeof buildComfyNodesWorkflow === 'function') {
        try {
            nodesWorkflows = {};
            // activeData is the global array of all manifest items in the dashboard
            const favoritedItems = activeData.filter(item => item.favorited);
            for (const item of favoritedItems) {
                const wf = buildComfyNodesWorkflow(item);
                // Key by the item's file path so backend can match
                nodesWorkflows[item.file || item.id] = wf;
            }
            console.log(`[Export] Generated ${Object.keys(nodesWorkflows).length} per-image node workflows`);
        } catch (e) {
            console.warn('[Export] Error generating node workflows:', e);
        }
    }
```

**Step 2: Add new parameters to fetch body**

In the same function, update the `JSON.stringify` body (around line 296-302) to include the new parameters. Replace:

```javascript
            body: JSON.stringify({
                session_name: sessionName,
                pack_metadata: packMetadata,
                organize_by_prompt: organizeByPrompt,
                organize_by_lora: organizeByLora,
                export_prompt_txt: exportPromptTxt
            })
```

With:

```javascript
            body: JSON.stringify({
                session_name: sessionName,
                pack_metadata: packMetadata,
                organize_by_prompt: organizeByPrompt,
                organize_by_lora: organizeByLora,
                export_prompt_txt: exportPromptTxt,
                copy_manifest: copyManifest,
                pack_workflow: packWorkflow,
                pack_nodes_workflow: packNodesWorkflow,
                workflow_data: workflowData,
                nodes_workflows: nodesWorkflows
            })
```

**Step 3: Add deleteNonFavorites function**

After the `exportFavorites()` function (after line 340), add:

```javascript
// Delete all non-favorited items from the session
async function deleteNonFavorites() {
    if (!window.confirm("Are you sure you want to delete all non-favorited items? This cannot be undone.")) {
        return;
    }

    const statusEl = document.getElementById('delete-status');
    const sessInput = document.getElementById('session-input');
    if (!sessInput) {
        if (statusEl) statusEl.innerText = '❌ Error: Session input not found';
        return;
    }
    const sessionName = sessInput.value;

    if (statusEl) {
        statusEl.innerText = '⏳ Deleting non-favorited items...';
        statusEl.style.color = '#ffaa00';
    }

    try {
        const response = await fetch('/config_tester/delete_non_favorites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_name: sessionName })
        });

        const resultText = await response.text();

        if (response.ok) {
            if (statusEl) {
                statusEl.innerText = '✅ ' + resultText;
                statusEl.style.color = '#4caf50';
            }
            // Reload the page to refresh the dashboard with updated manifest
            setTimeout(() => { location.reload(); }, 2000);
        } else {
            if (statusEl) {
                statusEl.innerText = '❌ Error: ' + resultText;
                statusEl.style.color = '#ff3860';
            }
        }
    } catch (error) {
        console.error('[Delete] Error:', error);
        if (statusEl) {
            statusEl.innerText = '❌ Network error: ' + error.message;
            statusEl.style.color = '#ff3860';
        }
    }
}
```

**Step 4: Commit**

```bash
git add resources/logic_utils.js
git commit -m "feat: add workflow capture, nodes workflow generation, and delete non-favorites to export"
```

---

## Task 4: Fix metadata_packer.py Bug + Accept Workflow Data

**Files:**
- Modify: `metadata_packer.py:429-430`

**Step 1: Fix the hardcoded workflowExample bug**

In `metadata_packer.py`, find line 429-430:

```python
    if True:
        workflow_data_full = workflowExample
```

Replace with:

```python
    if not workflow_data_full:
        workflow_data_full = workflowExample
```

This ensures the `workflowExample` is only used as a fallback when no actual workflow data was provided, which was the original intent.

**Step 2: Commit**

```bash
git add metadata_packer.py
git commit -m "fix: use workflowExample as fallback only when no workflow data provided"
```

---

## Task 5: Backend — Handle New Export Parameters + Delete Endpoint

**Files:**
- Modify: `__init__.py:434-621`

**Step 1: Add new parameters to export_favorites endpoint**

In `__init__.py`, in the `export_favorites` function (line 434), after line 447 (`export_prompt_txt = data.get(...)`), add:

```python
        copy_manifest = data.get("copy_manifest", True)
        pack_workflow = data.get("pack_workflow", False)
        pack_nodes_workflow = data.get("pack_nodes_workflow", False)
        workflow_data = data.get("workflow_data", None)
        nodes_workflows = data.get("nodes_workflows", None)
```

**Step 2: Pass workflow data to pack_metadata_into_image**

In the same function, find line 579 where `pack_metadata_into_image` is called:

```python
                    pack_metadata_into_image(source_path, dest_path, item, manifest.get("meta", {}))
```

Replace with:

```python
                    # Determine which workflow to embed
                    item_workflow = None
                    if pack_nodes_workflow and nodes_workflows:
                        # Per-image nodes workflow takes priority
                        item_workflow = nodes_workflows.get(item.get("file", ""))
                    elif pack_workflow and workflow_data:
                        # Full ComfyUI graph workflow
                        item_workflow = workflow_data
                    pack_metadata_into_image(source_path, dest_path, item, manifest.get("meta", {}), workflow_data=item_workflow)
```

**Step 3: Add cleaned manifest copy**

After the `for item in favorited:` loop (after line 612, before the `result_msg` line), add:

```python
        # Copy cleaned favorites-only manifest if requested
        if copy_manifest:
            try:
                cleaned_manifest = {
                    "items": favorited,
                    "meta": manifest.get("meta", {}),
                    "session_name": session_name
                }
                manifest_dest = os.path.join(export_base, "manifest.json")
                with open(manifest_dest, "w", encoding="utf-8") as f:
                    json.dump(cleaned_manifest, f, indent=2, ensure_ascii=False)
                print(f"[Export] Saved cleaned favorites manifest to {manifest_dest}")
            except Exception as e:
                print(f"[Export] Error saving cleaned manifest: {e}")
```

**Step 4: Update result message**

After the existing result message conditionals (after line 612 `if export_prompt_txt:`), add:

```python
        if copy_manifest:
            result_msg += " (with favorites manifest)"
        if pack_workflow:
            result_msg += " (with full workflow)"
        if pack_nodes_workflow:
            result_msg += " (with nodes workflows)"
```

**Step 5: Add delete_non_favorites endpoint**

After the `export_favorites` function's closing `except` block (after line 621), add:

```python
# =============================================================================
# API: DELETE NON-FAVORITED ITEMS
# =============================================================================

@server.PromptServer.instance.routes.post("/config_tester/delete_non_favorites")
async def delete_non_favorites(request):
    """
    Delete all non-favorited images from a session and update the manifest.
    """
    try:
        data = await request.json()
        session_name = data.get("session_name")

        # Sanitize
        if session_name:
            session_name = re.sub(r'[^\w\-]', '', session_name)

        if not session_name:
            return web.Response(status=400, text="Missing session_name")

        # Paths
        base_dir = os.path.join(folder_paths.get_output_directory(), "benchmarks", session_name)

        if not _is_path_within(base_dir, _get_benchmarks_base()):
            return web.Response(status=403, text="Forbidden: path outside benchmarks directory")

        manifest_path = os.path.join(base_dir, "manifest.json")
        images_dir = os.path.join(base_dir, "images")

        # Load manifest
        if not os.path.exists(manifest_path):
            return web.Response(status=404, text=f"Session '{session_name}' not found")

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        items = manifest.get("items", [])
        favorited = [item for item in items if item.get("favorited", False)]
        non_favorited = [item for item in items if not item.get("favorited", False)]

        if not non_favorited:
            return web.Response(status=200, text="No non-favorited items to delete")

        # Delete non-favorited image files
        deleted_count = 0
        for item in non_favorited:
            file_path = item.get("file", "")

            # Parse filename from various formats
            if file_path.startswith("/view?"):
                parsed_url = urllib.parse.urlparse(file_path)
                url_params = urllib.parse.parse_qs(parsed_url.query)
                filename = url_params.get("filename", [""])[0]
            elif file_path.startswith("./images/"):
                filename = file_path[9:]
            elif "filename=" in file_path:
                filename = file_path.split("filename=")[-1].split("&")[0]
            else:
                filename = os.path.basename(file_path)

            if filename:
                image_path = os.path.join(images_dir, filename)
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                        deleted_count += 1
                    except Exception as e:
                        print(f"[Delete] Error deleting {filename}: {e}")

        # Update manifest to only contain favorited items
        manifest["items"] = favorited
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        result_msg = f"Deleted {deleted_count} non-favorited images. {len(favorited)} favorited items remain."
        print(f"[ConfigTester] 🗑️ {result_msg}")
        return web.Response(status=200, text=result_msg)

    except Exception as e:
        print(f"[ConfigTester] Error deleting non-favorites: {e}")
        import traceback
        traceback.print_exc()
        return web.Response(status=500, text=str(e))
```

**Step 6: Commit**

```bash
git add __init__.py
git commit -m "feat: add workflow packing to export, cleaned manifest copy, and delete non-favorites endpoint"
```

---

## Task 6: Integration Verification

**Step 1: Verify template renders correctly**

Open ComfyUI, load a session in the Dashboard. Verify:
- 3 new checkboxes appear below the existing 4
- "Copy cleaned favorites-only manifest" is checked by default
- The other two are unchecked by default
- Red "DELETE ALL NON FAVORITED ITEMS" button appears below the status line

**Step 2: Verify export favorites with new options**

1. Favorite a few images in the dashboard
2. Check "Pack full ComfyUI workflow" checkbox
3. Click "COPY FAVORITES TO BENCHMARK FAVORITES FOLDER"
4. Verify favorites folder contains images + `manifest.json`
5. Drag a PNG from favorites into ComfyUI — should load the full workflow

**Step 3: Verify pack nodes workflow**

1. Uncheck "Pack full ComfyUI workflow"
2. Check "Pack config data as pure nodes workflow"
3. Export favorites again
4. Drag a PNG into ComfyUI — should load a clean Checkpoint→LoRA→CLIP→KSampler workflow with that image's specific settings

**Step 4: Verify delete non-favorites**

1. Click "DELETE ALL NON FAVORITED ITEMS"
2. Confirm the dialog appears
3. Click Cancel — verify nothing happens
4. Click the button again, confirm Yes
5. Verify non-favorited images are deleted, manifest is updated, dashboard refreshes

**Step 5: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: integration fixes for favorites workflow packing"
```
