/**
 * UTILITIES & API
 * Handles server communication and generic helpers.
 * FIXED: Session reload now properly re-renders grid
 */

function toggleFullscreen() {
    window.parent.postMessage({ type: 'toggle_fullscreen', node_id: TARGET_NODE_ID }, '*');
}


function setupKeyReloadFullscreen() {
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        switch (e.key) {
            case 'f':
                toggleFullscreen()
                break;
            case 'r':
                loadSession()
        }
    })
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
    if (!sessInput) return;
    const sess = sessInput.value;
    
    console.log(`[Load] 🔄 Loading session: ${sess}`);
    
    // UI Feedback
    const grid = document.getElementById('grid');
    if (grid) grid.style.opacity = '0.5';

    try {
        const r = await fetch(`/view?filename=manifest.json&type=output&subfolder=benchmarks/${sess}`);
        if (!r.ok) throw new Error("Session not found");
        const data = await r.json();

        console.log(`[Load] 📊 Loaded ${data.items?.length || 0} items`);

        // 1. CRITICAL FIX: Reset viewport position
        const viewport = document.getElementById('viewport');
        const canvas = document.getElementById('canvas');
        
        // Reset pan/zoom to defaults
        if (typeof resetZoom === 'function') {
            // This resets currentScale, panOffsetX, panOffsetY
            currentScale = 1;
            // panOffsetX = 0;
            // panOffsetY = 0;
            // if (canvas) {
            //     canvas.style.transform = 'translate(0px, 0px) scale(1)';
            // }
        }

        // 2. Clear grid completely
        if (grid) {
            grid.innerHTML = '';
            grid.style.paddingTop = '0px';
            grid.style.height = '0px';
        }

        // 3. Clear all caches
        nodeMap.clear();
        
        // Clear filter sets
        ['sampler', 'scheduler', 'lora', 'denoise', 'model', 'positive', 'negative', 'size', 'seed'].forEach(k => {
            if (filters[k]) filters[k].clear();
        });

        // 4. Swap data (CRITICAL: Do this before pipeline)
        fullManifest = data;
        activeData = fullManifest.items || [];
        meta = fullManifest.meta || {};

        console.log(`[Load] 📦 activeData now has ${activeData.length} items`);

        // 5. Reset indices
        refreshIndices();
        
        // 6. CRITICAL FIX: Reset visible range
        // if (typeof visibleRange !== 'undefined') {
        //     visibleRange = { start: 0, end: 0 };
        // }

        // 7. Re-initialize filters (don't skip this!)
        if (typeof initFilters === 'function') {
            initFilters();
        }
        
        // Initialize search filter UI
        if (typeof renderSearchFilters === 'function') {
            renderSearchFilters();
        }

        // 8. CRITICAL FIX: Force pipeline and render
        // Wait a tick for the DOM to update, then process
        await new Promise(resolve => setTimeout(resolve, 10));
        
        console.log(`[Load] 🔧 Running pipeline...`);
        updateDataPipeline();
        
        // 9. Wait for pipeline to complete, then render
        await new Promise(resolve => setTimeout(resolve, 50));
        
        console.log(`[Load] 🎨 Rendering ${processedData?.length || 0} processed items...`);
        
        // Force a full render
        if (typeof renderDOM === 'function') {
            renderDOM();
        }
        
        // 10. Auto-fit after render completes
        // setTimeout(() => {
        //     if (typeof autoFitZoom === 'function') {
        //         autoFitZoom();
        //     }
        // }, 100);

        // 11. Restore UI
        if (grid) grid.style.opacity = '1';

        // Close Popups
        const popup = document.getElementById('session-popup');
        const overlay = document.getElementById('session-overlay');
        if (popup) popup.style.display = 'none';
        if (overlay) overlay.style.display = 'none';
        document.body.style.overflow = '';
        
        console.log('[Load] ✅ Session loaded successfully');

    } catch (e) { 
        console.error('[Load] ❌ Load failed:', e); 
        if (grid) grid.style.opacity = '1';
        alert("Load Error: " + e.message);
    }
}

// Export favorited images to benchmark_favorites folder
async function exportFavorites() {
    const statusEl = document.getElementById('export-status');
    const btn = event.target;

    // Get session name
    const sessInput = document.getElementById('session-input');
    if (!sessInput) {
        if (statusEl) statusEl.innerText = '❌ Error: Session input not found';
        return;
    }
    const sessionName = sessInput.value;

    // Get pack metadata checkbox state
    const packCheckbox = document.getElementById('pack-metadata-checkbox');
    const packMetadata = packCheckbox ? packCheckbox.checked : false;

    // Get organize by prompt checkbox state
    const organizeCheckbox = document.getElementById('organize-by-prompt-checkbox');
    const organizeByPrompt = organizeCheckbox ? organizeCheckbox.checked : false;

    // Show loading state
    if (statusEl) {
        statusEl.innerText = '⏳ Exporting favorites...';
        statusEl.style.color = '#ffaa00';
    }
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.cursor = 'wait';
    }

    try {
        const response = await fetch('/config_tester/export_favorites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_name: sessionName,
                pack_metadata: packMetadata,
                organize_by_prompt: organizeByPrompt
            })
        });

        const resultText = await response.text();

        if (response.ok) {
            if (statusEl) {
                statusEl.innerText = '✅ ' + resultText;
                statusEl.style.color = '#4caf50';
            }

            // Reset status after 5 seconds
            setTimeout(() => {
                if (statusEl) {
                    statusEl.innerText = '';
                }
            }, 5000);
        } else {
            if (statusEl) {
                statusEl.innerText = '❌ Error: ' + resultText;
                statusEl.style.color = '#ff3860';
            }
        }

    } catch (error) {
        console.error('[Export] Error:', error);
        if (statusEl) {
            statusEl.innerText = '❌ Network error: ' + error.message;
            statusEl.style.color = '#ff3860';
        }
    } finally {
        // Re-enable button
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        }
    }
}

// Reject a specific image (X button)
function rejectItem(element) {
    const card = element.closest('.card');
    if (!card || !card._dataItem) return;

    const item = card._dataItem;

    item.rejected = true;

    if (typeof markItemChanged === "function") {
        markItemChanged(item);
    } else {
        pendingSaveItems.set(item.id, item);
        scheduleBatchedSave();
    }

    card.style.opacity = '0';
    card.style.transform = 'scale(0.9)'; 
    card.style.pointerEvents = 'none';   

    setTimeout(() => {
        updateDataPipeline(); 
        scheduleJSONUpdate();
    }, 100); 
}

// Helper to select text in JSON bars
function selectJSON(id) {
    const r = document.createRange();
    r.selectNode(document.getElementById(id));
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(r);
}

// Trigger generation from Modal
async function triggerGen(btn) {
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
        node = graph._nodes.find(n => n.type === "UltimateSamplerGrid");
        if (node) {
            const widget = node.widgets.find(w => w.name === "configs_json");
            if (widget) {
                widget.value = jsonStr;
                window.parent.app.queuePrompt(0);
                const b = btn; b.innerText = "QUEUED!";
                setTimeout(() => { closeM(); b.innerText = "GENERATE NEW"; }, 1000);
            }
        }
    } catch (e) { alert("Error: " + e); }
}
setupKeyReloadFullscreen()