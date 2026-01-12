/**
 * UTILITIES & API
 * Handles server communication and generic helpers.
 */

function toggleFullscreen() {
    window.parent.postMessage({ type: 'toggle_fullscreen', node_id: TARGET_NODE_ID }, '*');
}

// Persist session to disk
async function saveState() {
    try {
        await fetch('/config_tester/save_manifest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_name: document.getElementById('session-input')?.value || "default", 
                manifest: fullManifest 
            })
        });
    } catch (e) { console.error("Save failed", e); }
}

// Load session from disk
async function loadSession() {
    const sessInput = document.getElementById('session-input');
    if(!sessInput) return;
    const sess = sessInput.value;
    try {
        const r = await fetch(`/view?filename=manifest.json&type=output&subfolder=benchmarks/${sess}`);
        if (!r.ok) throw new Error("Session not found");
        const data = await r.json();

        // Update Globals
        fullManifest = data;
        activeData = fullManifest.items || [];
        meta = fullManifest.meta || {};

        // Reset UI State
        refreshIndices();
        filters.sampler.clear();
        filters.scheduler.clear();
        filters.lora.clear();
        filters.denoise.clear();
        nodeMap.clear();

        // Clear Grid
        const grid = document.getElementById('grid');
        if (grid) {
            grid.innerHTML = '';
            grid.style.paddingTop = '0px'; 
        }
        
        // Reset Metrics & Pipeline
        metrics.ready = false; 
        init();
        updateDataPipeline();
    } catch (e) { console.error(e); }
}

// Reject a specific image (X button)
function rejectItem(id) {
    const item = activeData.find(d => d.id === id);
    if (item) {
        item.rejected = true;
        saveState();
        updateDataPipeline();
    }
}

// Helper to select text in JSON bars
function selectJSON(id) {
    const r = document.createRange(); 
    r.selectNode(document.getElementById(id));
    window.getSelection().removeAllRanges(); 
    window.getSelection().addRange(r);
}

// Trigger generation from Modal
async function triggerGen() {
    const newCfg = [{
        sampler: document.getElementById('f-smp').value,
        scheduler: document.getElementById('f-sch').value,
        steps: parseInt(document.getElementById('f-stp').value),
        cfg: parseFloat(document.getElementById('f-cfg').value),
        denoise: parseFloat(document.getElementById('f-den').value),
        lora: document.getElementById('f-lor').value
    }];
    const jsonStr = JSON.stringify(newCfg, null, 2);
    try {
        // Communicate with ComfyUI Graph
        const graph = window.parent.app.graph;
        let node = graph.getNodeById(parseInt(TARGET_NODE_ID));
        if (!node) node = graph._nodes.find(n => n.type === "UltimateSamplerGrid");
        if (node) {
            const widget = node.widgets.find(w => w.name === "configs_json");
            if (widget) {
                widget.value = jsonStr;
                window.parent.app.queuePrompt(0);
                const b = event.target; b.innerText = "QUEUED!";
                setTimeout(() => { closeM(); b.innerText = "GENERATE NEW"; }, 1000);
            }
        }
    } catch (e) { alert("Error: " + e); }
}