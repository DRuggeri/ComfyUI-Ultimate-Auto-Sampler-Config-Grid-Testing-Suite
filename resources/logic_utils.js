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
        const r = await fetch(`/view?filename=manifest.json&type=output&subfolder=benchmarks/${sess}&t=${Date.now()}`);
        if (!r.ok) throw new Error("Session not found");
        const data = await r.json();

        console.log(`[Load] 📊 Loaded ${data.items?.length || 0} items`);

        // 1. CRITICAL FIX: Reset viewport position
        const viewport = document.getElementById('viewport');
        const canvas = document.getElementById('canvas');

        // Reset pan/zoom to defaults
        if (typeof resetZoom === 'function') {
            // This resets currentScale, panOffsetX, panOffsetY
            // currentScale = 1;
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

        // 4b. Recompute label global values with new data so unique-only works on first load
        if (typeof computeLabelGlobalValues === 'function' && labelMode && labelMode.enabled) {
            computeLabelGlobalValues();
        }

        // 5. Reset indices
        refreshIndices();

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
        await new Promise(resolve => setTimeout(resolve, 100));

        console.log(`[Load] 🎨 Rendering ${processedData?.length || 0} processed items...`);

        // Force a full render
        if (typeof renderDOM === 'function') {
            renderDOM();
        }


        // 11. Restore UI
        if (grid) grid.style.opacity = '1';

        // Close Settings Panel
        const cogPanel = document.getElementById('cog-menu-dropdown');
        const cogOverlay = document.getElementById('cog-menu-overlay');
        if (cogPanel) cogPanel.style.display = 'none';
        if (cogOverlay) cogOverlay.style.display = 'none';
        document.body.style.overflow = '';
        // Hide landing page, show viewport
        const landing = document.getElementById('session-landing');
        if (landing) landing.style.display = 'none';
        if (viewport) viewport.style.display = 'block';

        console.log('[Load] ✅ Session loaded successfully');


    } catch (e) {
        console.error('[Load] ❌ Load failed:', e);
        if (grid) grid.style.opacity = '1';
        alert("Load Error: " + e.message);
    }
}

// Load session from picker dropdown or session card
function loadSessionFromPicker(sessionName) {
    if (!sessionName) return;
    const sessInput = document.getElementById('session-input');
    if (sessInput) sessInput.value = sessionName;
    loadSession();
}

// Fetch available sessions and populate picker dropdown + landing page
async function fetchAndShowSessions() {
    try {
        const resp = await fetch('/config_tester/list_sessions');
        if (!resp.ok) return;
        const sessions = await resp.json();
        if (!sessions || sessions.length === 0) return;

        // Populate the session picker dropdown in cog menu
        const picker = document.getElementById('session-picker');
        if (picker) {
            // Keep the default option
            picker.innerHTML = '<option value="">-- Select a session --</option>';
            sessions.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.name;
                const date = new Date(s.mtime * 1000);
                const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
                opt.textContent = `${s.name} (${s.item_count} images, ${dateStr})`;
                picker.appendChild(opt);
            });
        }

        // Render session cards on the landing page
        const cardsContainer = document.getElementById('session-cards');
        const landingEl = document.getElementById('session-landing');
        if (cardsContainer && landingEl) {
            cardsContainer.innerHTML = '';
            sessions.forEach(s => {
                const card = document.createElement('div');
                card.style.cssText = 'width: 180px; background: #2a2a2a; border: 1px solid #444; border-radius: 8px; overflow: hidden; cursor: pointer; transition: border-color 0.2s, transform 0.15s;';
                card.onmouseenter = () => { card.style.borderColor = '#0af'; card.style.transform = 'translateY(-2px)'; };
                card.onmouseleave = () => { card.style.borderColor = '#444'; card.style.transform = 'none'; };
                card.onclick = () => loadSessionFromPicker(s.name);

                // Thumbnail
                const thumbDiv = document.createElement('div');
                thumbDiv.style.cssText = 'width: 100%; height: 120px; background: #1a1a1a; display: flex; align-items: center; justify-content: center; overflow: hidden;';
                if (s.first_image) {
                    const img = document.createElement('img');
                    img.src = `/view?filename=${encodeURIComponent(s.first_image.split('/').pop())}&type=output&subfolder=${encodeURIComponent(s.first_image.substring(0, s.first_image.lastIndexOf('/')))}&t=${Date.now()}`;
                    img.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
                    img.onerror = () => { img.style.display = 'none'; thumbDiv.textContent = '📷'; thumbDiv.style.fontSize = '24px'; thumbDiv.style.color = '#555'; };
                    thumbDiv.appendChild(img);
                } else {
                    thumbDiv.textContent = '📷';
                    thumbDiv.style.fontSize = '24px';
                    thumbDiv.style.color = '#555';
                }
                card.appendChild(thumbDiv);

                // Info
                const info = document.createElement('div');
                info.style.cssText = 'padding: 8px; font-size: 11px;';
                const nameEl = document.createElement('div');
                nameEl.style.cssText = 'font-weight: bold; color: #ddd; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;';
                nameEl.textContent = s.name;
                nameEl.title = s.name;
                info.appendChild(nameEl);

                const metaEl = document.createElement('div');
                metaEl.style.cssText = 'color: #888; font-size: 10px;';
                const date = new Date(s.mtime * 1000);
                metaEl.textContent = `${s.item_count} images · ${date.toLocaleDateString()}`;
                info.appendChild(metaEl);

                card.appendChild(info);
                cardsContainer.appendChild(card);
            });
        }
    } catch (e) {
        console.error('[Sessions] Failed to fetch sessions:', e);
    }
}

// Show session landing page if no data is loaded
function showSessionLandingIfEmpty() {
    const hasData = fullManifest && fullManifest.items && fullManifest.items.length > 0;
    const landing = document.getElementById('session-landing');
    const viewport = document.getElementById('viewport');

    // Always populate session picker dropdown and landing cards
    fetchAndShowSessions();

    if (!hasData && landing && viewport) {
        landing.style.display = 'block';
        viewport.style.display = 'none';
    } else if (landing && viewport) {
        landing.style.display = 'none';
        viewport.style.display = 'block';
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

    // Get organize by lora checkbox state
    const organizeLoraCheckbox = document.getElementById('organize-by-lora-checkbox');
    const organizeByLora = organizeLoraCheckbox ? organizeLoraCheckbox.checked : false;

    // Get export prompt txt checkbox state
    const promptTxtCheckbox = document.getElementById('export-prompt-txt-checkbox');
    const exportPromptTxt = promptTxtCheckbox ? promptTxtCheckbox.checked : false;

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
                organize_by_prompt: organizeByPrompt,
                organize_by_lora: organizeByLora,
                export_prompt_txt: exportPromptTxt,
                copy_manifest: copyManifest,
                pack_workflow: packWorkflow,
                pack_nodes_workflow: packNodesWorkflow,
                workflow_data: workflowData,
                nodes_workflows: nodesWorkflows
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

// Scan an external directory and load it as a session
async function scanDirectory() {
    const pathInput = document.getElementById('scan-directory-input');
    const statusEl = document.getElementById('scan-status');
    const btn = document.getElementById('scan-directory-btn');

    if (!pathInput || !pathInput.value.trim()) {
        if (statusEl) {
            statusEl.innerText = 'Please enter a directory path';
            statusEl.style.color = '#ff3860';
        }
        return;
    }

    const directoryPath = pathInput.value.trim();

    // Use session input value if set, otherwise auto-generate from dir name
    const sessInput = document.getElementById('session-input');
    let sessionName = '';
    // Auto-generate from directory name
    const dirParts = directoryPath.replace(/\\/g, '/').split('/').filter(Boolean);
    sessionName = 'scan-' + (dirParts[dirParts.length - 1] || 'unnamed').replace(/[^\w-]/g, '');

    // UI feedback - scanning
    if (statusEl) {
        statusEl.innerText = 'Scanning directory...';
        statusEl.style.color = '#ffaa00';
    }
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.textContent = 'SCANNING...';
    }

    try {
        const response = await fetch('/config_tester/scan_directory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                directory_path: directoryPath,
                session_name: sessionName
            })
        });

        const result = await response.json();

        if (response.ok) {
            const fromManifest = result.from_manifest || 0;
            let metaInfo;
            if (fromManifest > 0) {
                metaInfo = `${fromManifest} from manifest`;
                if (result.with_metadata > fromManifest) {
                    metaInfo += `, ${result.with_metadata - fromManifest} with embedded metadata`;
                }
            } else {
                metaInfo = result.with_metadata > 0
                    ? `${result.with_metadata} with metadata`
                    : 'no metadata found';
            }

            if (statusEl) {
                statusEl.innerText = `Found ${result.item_count} images (${metaInfo}). Loading...`;
                statusEl.style.color = '#4caf50';
            }

            // Update session input with the scan session name
            if (sessInput) sessInput.value = result.session_name;

            // Load the session into the dashboard using existing infrastructure
            await loadSession();

            if (statusEl) {
                statusEl.innerText = `Loaded ${result.item_count} images (${metaInfo})`;
                statusEl.style.color = '#4caf50';
            }
        } else {
            if (statusEl) {
                statusEl.innerText = 'Error: ' + (result.error || response.statusText);
                statusEl.style.color = '#ff3860';
            }
        }
    } catch (error) {
        console.error('[Scan] Error:', error);
        if (statusEl) {
            statusEl.innerText = 'Network error: ' + error.message;
            statusEl.style.color = '#ff3860';
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.textContent = 'SCAN';
        }
    }
}

setupKeyReloadFullscreen()