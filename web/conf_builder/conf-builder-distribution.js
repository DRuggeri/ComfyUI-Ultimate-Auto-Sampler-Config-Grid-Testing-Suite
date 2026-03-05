/**
 * Config Builder Distribution Module
 * Handles the UI for distributed task processing configuration.
 * Workers are other ComfyUI instances that pull jobs from this master.
 */

import { createInputGroup, createSlider, createSectionHeader } from './conf-builder-ui-components.js';

// --- DISTRIBUTION SECTION RENDERER ---

export function renderDistributionSection(node, container) {
    const section = document.createElement("div");
    section.className = "cb-section";
    section.innerHTML = '<div class="cb-section-title">🌐 Distribution</div>';
    const content = document.createElement("div");

    // Ensure distribution state defaults exist
    if (node.state.distribution_enabled === undefined) node.state.distribution_enabled = false;
    if (!node.state.worker_urls) node.state.worker_urls = [];
    if (node.state.claim_timeout === undefined) node.state.claim_timeout = 600;
    if (node.state.use_master_encoding === undefined) node.state.use_master_encoding = false;

    // Enable/Disable toggle
    const toggleRow = document.createElement("div");
    toggleRow.style.cssText = "display: flex; align-items: center; gap: 10px; margin-bottom: 10px;";

    const toggleLabel = document.createElement("label");
    toggleLabel.className = "cb-toggle";
    toggleLabel.style.fontSize = "12px";
    const toggleCheckbox = document.createElement("input");
    toggleCheckbox.type = "checkbox";
    toggleCheckbox.checked = node.state.distribution_enabled;
    toggleCheckbox.onchange = () => {
        node.state.distribution_enabled = toggleCheckbox.checked;
        node.saveState();
        node.renderUI();
    };
    toggleLabel.appendChild(toggleCheckbox);
    toggleLabel.appendChild(document.createTextNode(" Enable Distributed Processing"));
    toggleRow.appendChild(toggleLabel);
    content.appendChild(toggleRow);

    // Only show details when enabled
    if (node.state.distribution_enabled) {
        const detailsContainer = document.createElement("div");
        detailsContainer.style.cssText = "border: 1px solid #333; border-radius: 4px; padding: 10px; background: #1e1e1e;";

        // Info text
        const info = document.createElement("div");
        info.style.cssText = "font-size: 11px; color: #888; margin-bottom: 10px; line-height: 1.4;";
        info.textContent = "Add ComfyUI worker URLs below. Workers must have this node installed. "
            + "Jobs are pulled by workers (fast workers get more jobs).";
        detailsContainer.appendChild(info);

        // Worker URL list
        const workerList = document.createElement("div");
        workerList.style.cssText = "display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px;";

        const renderWorkerEntries = () => {
            workerList.innerHTML = "";

            node.state.worker_urls.forEach((url, idx) => {
                const row = document.createElement("div");
                row.style.cssText = "display: flex; gap: 6px; align-items: center;";

                const input = document.createElement("input");
                input.className = "cb-input";
                input.style.flex = "1";
                input.value = url;
                input.placeholder = "http://192.168.1.10:8188";
                input.onchange = () => {
                    node.state.worker_urls[idx] = input.value.trim();
                    node.saveState();
                };

                const statusDot = document.createElement("span");
                statusDot.style.cssText = "width: 10px; height: 10px; border-radius: 50%; background: #555; flex-shrink: 0;";
                statusDot.title = "Not tested";
                statusDot.dataset.workerIdx = idx;

                const removeBtn = document.createElement("button");
                removeBtn.className = "cb-button";
                removeBtn.textContent = "✕";
                removeBtn.style.cssText = "padding: 4px 8px; min-width: unset;";
                removeBtn.onclick = () => {
                    node.state.worker_urls.splice(idx, 1);
                    node.saveState();
                    renderWorkerEntries();
                };

                row.appendChild(statusDot);
                row.appendChild(input);
                row.appendChild(removeBtn);
                workerList.appendChild(row);
            });

            // Add empty entry if list is empty
            if (node.state.worker_urls.length === 0) {
                const emptyMsg = document.createElement("div");
                emptyMsg.style.cssText = "font-size: 11px; color: #666; text-align: center; padding: 8px;";
                emptyMsg.textContent = "No workers added. Click '+ Add Worker' below.";
                workerList.appendChild(emptyMsg);
            }
        };

        renderWorkerEntries();
        detailsContainer.appendChild(workerList);

        // Button row: Add Worker + Test Connections
        const buttonRow = document.createElement("div");
        buttonRow.style.cssText = "display: flex; gap: 8px; margin-bottom: 10px;";

        const addBtn = document.createElement("button");
        addBtn.className = "cb-button primary";
        addBtn.textContent = "+ Add Worker";
        addBtn.style.flex = "1";
        addBtn.onclick = () => {
            node.state.worker_urls.push("");
            node.saveState();
            renderWorkerEntries();
        };

        const testBtn = document.createElement("button");
        testBtn.className = "cb-button";
        testBtn.textContent = "🔍 Test Connections";
        testBtn.style.flex = "1";
        testBtn.onclick = async () => {
            testBtn.disabled = true;
            testBtn.textContent = "Testing...";

            const dots = workerList.querySelectorAll("[data-worker-idx]");

            for (let i = 0; i < node.state.worker_urls.length; i++) {
                const url = node.state.worker_urls[i].trim();
                if (!url) continue;

                const dot = dots[i];
                if (dot) dot.style.background = "#cc0"; // yellow = testing

                try {
                    // Proxy through master backend to avoid CORS issues
                    // (browser can't fetch cross-origin worker URLs directly)
                    const resp = await fetch("/distribution/test_worker", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ worker_url: url })
                    });
                    if (resp.ok) {
                        const data = await resp.json();
                        if (dot) {
                            if (data.reachable) {
                                dot.style.background = "#0c0"; // green = reachable
                                dot.title = data.status === "busy"
                                    ? `Busy (${data.jobs_processed} jobs done)`
                                    : "Idle - Ready";
                            } else {
                                dot.style.background = "#c00"; // red = error
                                dot.title = `Unreachable: ${data.error}`;
                            }
                        }
                    } else {
                        if (dot) {
                            dot.style.background = "#c00"; // red = error
                            dot.title = `Proxy error: HTTP ${resp.status}`;
                        }
                    }
                } catch (e) {
                    if (dot) {
                        dot.style.background = "#c00";
                        dot.title = `Error: ${e.message}`;
                    }
                }
            }

            testBtn.disabled = false;
            testBtn.textContent = "🔍 Test Connections";
        };

        buttonRow.appendChild(addBtn);
        buttonRow.appendChild(testBtn);
        detailsContainer.appendChild(buttonRow);

        // Claim timeout slider
        const timeoutSlider = createSlider(
            "Claim Timeout (seconds)",
            node.state.claim_timeout,
            30, 900, 30,
            (val) => {
                node.state.claim_timeout = val;
                node.saveState();
            }
        );
        detailsContainer.appendChild(timeoutSlider);

        // Use Master Text Encoding toggle
        const encodingRow = document.createElement("div");
        encodingRow.style.cssText = "display: flex; align-items: flex-start; gap: 10px; margin-top: 10px;";

        const encodingLabel = document.createElement("label");
        encodingLabel.className = "cb-toggle";
        encodingLabel.style.fontSize = "12px";
        const encodingCheckbox = document.createElement("input");
        encodingCheckbox.type = "checkbox";
        encodingCheckbox.checked = node.state.use_master_encoding;
        encodingCheckbox.onchange = () => {
            node.state.use_master_encoding = encodingCheckbox.checked;
            node.saveState();
        };
        encodingLabel.appendChild(encodingCheckbox);
        encodingLabel.appendChild(document.createTextNode(" Use Master Text Encoding"));
        encodingRow.appendChild(encodingLabel);
        detailsContainer.appendChild(encodingRow);

        const encodingInfo = document.createElement("div");
        encodingInfo.style.cssText = "font-size: 10px; color: #666; margin-top: 4px; line-height: 1.3; padding-left: 2px;";
        encodingInfo.textContent = "Master pre-encodes all prompts and sends them to workers. "
            + "Workers skip CLIP loading and text encoding, saving significant time. "
            + "Disabled when optional conditioning inputs are connected.";
        detailsContainer.appendChild(encodingInfo);

        content.appendChild(detailsContainer);
    }

    section.appendChild(content);
    container.appendChild(section);
}

// --- STANDALONE DISTRIBUTION SETTINGS SECTION ---
// Used by the new top-bar layout (distribution toggle is in Settings dropdown)

export function renderDistributionSettingsSection(node, container) {
    // Ensure distribution state defaults exist
    if (!node.state.worker_urls) node.state.worker_urls = [];
    if (node.state.claim_timeout === undefined) node.state.claim_timeout = 600;
    if (node.state.use_master_encoding === undefined) node.state.use_master_encoding = false;

    const section = document.createElement("div");
    section.className = "cb-section full-width";
    section.id = "cb-sec-distribution";

    // Uniform section header
    const header = createSectionHeader("🌐", "Distribution Settings", "distribution");
    section.appendChild(header);

    // On/Off toggle row (always visible)
    const toggleRow = document.createElement("div");
    toggleRow.style.cssText = "display: flex; align-items: center; gap: 10px; margin-bottom: 8px;";
    const toggleLabel = document.createElement("label");
    toggleLabel.className = "cb-toggle";
    toggleLabel.style.fontSize = "13px";
    toggleLabel.style.fontWeight = "bold";
    const toggleCheckbox = document.createElement("input");
    toggleCheckbox.type = "checkbox";
    toggleCheckbox.checked = node.state.distribution_enabled || false;
    const toggleText = document.createTextNode(node.state.distribution_enabled ? " Distributed Processing: ON" : " Distributed Processing: OFF");
    toggleLabel.appendChild(toggleCheckbox);
    toggleLabel.appendChild(toggleText);
    toggleRow.appendChild(toggleLabel);
    section.appendChild(toggleRow);

    // Collapsible details container (hidden when distribution is off)
    const detailsContainer = document.createElement("div");
    detailsContainer.id = "cb-distribution-details";
    detailsContainer.style.display = node.state.distribution_enabled ? "block" : "none";

    toggleCheckbox.onchange = () => {
        node.state.distribution_enabled = toggleCheckbox.checked;
        detailsContainer.style.display = toggleCheckbox.checked ? "block" : "none";
        toggleText.textContent = toggleCheckbox.checked ? " Distributed Processing: ON" : " Distributed Processing: OFF";
        node.saveState();
    };

    // Info text
    const info = document.createElement("div");
    info.style.cssText = "font-size: 11px; color: #999; margin-bottom: 10px; line-height: 1.4;";
    info.textContent = "Add ComfyUI worker URLs below. Workers must have this node installed. "
        + "Jobs are pulled by workers (fast workers get more jobs).";
    detailsContainer.appendChild(info);

    // Worker URL list
    const workerList = document.createElement("div");
    workerList.style.cssText = "display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px;";

    const renderWorkerEntries = () => {
        workerList.innerHTML = "";

        node.state.worker_urls.forEach((url, idx) => {
            const row = document.createElement("div");
            row.style.cssText = "display: flex; gap: 6px; align-items: center;";

            const input = document.createElement("input");
            input.className = "cb-input";
            input.style.flex = "1";
            input.value = url;
            input.placeholder = "http://192.168.1.10:8188";
            input.onchange = () => {
                node.state.worker_urls[idx] = input.value.trim();
                node.saveState();
            };

            const statusDot = document.createElement("span");
            statusDot.style.cssText = "width: 10px; height: 10px; border-radius: 50%; background: #555; flex-shrink: 0;";
            statusDot.title = "Not tested";
            statusDot.dataset.workerIdx = idx;

            const removeBtn = document.createElement("button");
            removeBtn.className = "cb-button";
            removeBtn.textContent = "✕";
            removeBtn.style.cssText = "padding: 4px 8px; min-width: unset;";
            removeBtn.onclick = () => {
                node.state.worker_urls.splice(idx, 1);
                node.saveState();
                renderWorkerEntries();
            };

            row.appendChild(statusDot);
            row.appendChild(input);
            row.appendChild(removeBtn);
            workerList.appendChild(row);
        });

        // Add empty entry if list is empty
        if (node.state.worker_urls.length === 0) {
            const emptyMsg = document.createElement("div");
            emptyMsg.style.cssText = "font-size: 11px; color: #777; text-align: center; padding: 8px;";
            emptyMsg.textContent = "No workers added. Click '+ Add Worker' below.";
            workerList.appendChild(emptyMsg);
        }
    };

    renderWorkerEntries();
    detailsContainer.appendChild(workerList);

    // Button row: Add Worker + Test Connections
    const buttonRow = document.createElement("div");
    buttonRow.style.cssText = "display: flex; gap: 8px; margin-bottom: 10px;";

    const addBtn = document.createElement("button");
    addBtn.className = "cb-button primary";
    addBtn.textContent = "+ Add Worker";
    addBtn.style.flex = "1";
    addBtn.onclick = () => {
        node.state.worker_urls.push("");
        node.saveState();
        renderWorkerEntries();
    };

    const testBtn = document.createElement("button");
    testBtn.className = "cb-button";
    testBtn.textContent = "🔍 Test Connections";
    testBtn.style.flex = "1";
    testBtn.onclick = async () => {
        testBtn.disabled = true;
        testBtn.textContent = "Testing...";

        const dots = workerList.querySelectorAll("[data-worker-idx]");

        for (let i = 0; i < node.state.worker_urls.length; i++) {
            const url = node.state.worker_urls[i].trim();
            if (!url) continue;

            const dot = dots[i];
            if (dot) dot.style.background = "#cc0"; // yellow = testing

            try {
                // Proxy through master backend to avoid CORS issues
                // (browser can't fetch cross-origin worker URLs directly)
                const resp = await fetch("/distribution/test_worker", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ worker_url: url })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    if (dot) {
                        if (data.reachable) {
                            dot.style.background = "#0c0"; // green = reachable
                            dot.title = data.status === "busy"
                                ? `Busy (${data.jobs_processed} jobs done)`
                                : "Idle - Ready";
                        } else {
                            dot.style.background = "#c00"; // red = error
                            dot.title = `Unreachable: ${data.error}`;
                        }
                    }
                } else {
                    if (dot) {
                        dot.style.background = "#c00"; // red = error
                        dot.title = `Proxy error: HTTP ${resp.status}`;
                    }
                }
            } catch (e) {
                if (dot) {
                    dot.style.background = "#c00";
                    dot.title = `Error: ${e.message}`;
                }
            }
        }

        testBtn.disabled = false;
        testBtn.textContent = "🔍 Test Connections";
    };

    buttonRow.appendChild(addBtn);
    buttonRow.appendChild(testBtn);
    detailsContainer.appendChild(buttonRow);

    // Claim timeout slider
    const timeoutSlider = createSlider(
        "Claim Timeout (seconds)",
        node.state.claim_timeout,
        30, 900, 30,
        (val) => {
            node.state.claim_timeout = val;
            node.saveState();
        }
    );
    detailsContainer.appendChild(timeoutSlider);

    // Use Master Text Encoding toggle
    const encodingRow = document.createElement("div");
    encodingRow.style.cssText = "display: flex; align-items: flex-start; gap: 10px; margin-top: 10px;";

    const encodingLabel = document.createElement("label");
    encodingLabel.className = "cb-toggle";
    encodingLabel.style.fontSize = "12px";
    const encodingCheckbox = document.createElement("input");
    encodingCheckbox.type = "checkbox";
    encodingCheckbox.checked = node.state.use_master_encoding;
    encodingCheckbox.onchange = () => {
        node.state.use_master_encoding = encodingCheckbox.checked;
        node.saveState();
    };
    encodingLabel.appendChild(encodingCheckbox);
    encodingLabel.appendChild(document.createTextNode(" Use Master Text Encoding"));
    encodingRow.appendChild(encodingLabel);
    detailsContainer.appendChild(encodingRow);

    const encodingInfo = document.createElement("div");
    encodingInfo.style.cssText = "font-size: 10px; color: #777; margin-top: 4px; line-height: 1.3; padding-left: 2px;";
    encodingInfo.textContent = "Master pre-encodes all prompts and sends them to workers. "
        + "Workers skip CLIP loading and text encoding, saving significant time. "
        + "Disabled when optional conditioning inputs are connected.";
    detailsContainer.appendChild(encodingInfo);

    // Sync Models to Workers toggle
    const syncRow = document.createElement("div");
    syncRow.style.cssText = "display: flex; align-items: flex-start; gap: 10px; margin-top: 10px;";

    const syncLabel = document.createElement("label");
    syncLabel.className = "cb-toggle";
    syncLabel.style.fontSize = "12px";
    const syncCheckbox = document.createElement("input");
    syncCheckbox.type = "checkbox";
    syncCheckbox.checked = node.state.sync_models_to_workers || false;
    syncCheckbox.onchange = () => {
        node.state.sync_models_to_workers = syncCheckbox.checked;
        node.saveState();
    };
    syncLabel.appendChild(syncCheckbox);
    syncLabel.appendChild(document.createTextNode(" ☁️ Sync Models to Workers"));
    syncRow.appendChild(syncLabel);
    detailsContainer.appendChild(syncRow);

    const syncInfo = document.createElement("div");
    syncInfo.style.cssText = "font-size: 10px; color: #777; margin-top: 4px; line-height: 1.3; padding-left: 2px;";
    syncInfo.textContent = "Automatically transfer required models, LoRAs, text encoders, "
        + "and VAEs to workers via HTTP. Files are saved permanently to each worker's "
        + "ComfyUI models folder, matching the master's directory structure.";
    detailsContainer.appendChild(syncInfo);

    section.appendChild(detailsContainer);
    container.appendChild(section);
}
