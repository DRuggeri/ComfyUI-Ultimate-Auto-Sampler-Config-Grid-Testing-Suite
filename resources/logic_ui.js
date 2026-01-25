/**
 * UI COMPONENTS - COMPACT LAYOUT WITH FILTERS POPUP
 * Fixed: Index tag z-index, time tag position
 * Added: Favorites feature, Filters popup, Prompt/Size/Seed filters
 */

// Cache for filter buttons
let filterButtonCache = {};

// Toggle Filters Popup
function toggleFiltersPopup() {
    const popup = document.getElementById('filters-popup');
    const overlay = document.getElementById('filters-overlay');
    
    if (popup.style.display === 'none' || !popup.style.display) {
        popup.style.display = 'block';
        overlay.style.display = 'block';
        document.body.style.overflow = 'hidden'; // Prevent background scroll
    } else {
        popup.style.display = 'none';
        overlay.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Toggle Session Popup
function toggleSessionPopup() {
    const popup = document.getElementById('session-popup');
    const overlay = document.getElementById('session-overlay');
    
    if (popup.style.display === 'none' || !popup.style.display) {
        popup.style.display = 'block';
        overlay.style.display = 'block';
        document.body.style.overflow = 'hidden';
    } else {
        popup.style.display = 'none';
        overlay.style.display = 'none';
        document.body.style.overflow = '';
    }
}

// Close popup on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const filtersPopup = document.getElementById('filters-popup');
        const sessionPopup = document.getElementById('session-popup');
        
        if (filtersPopup && filtersPopup.style.display !== 'none') {
            toggleFiltersPopup();
        } else if (sessionPopup && sessionPopup.style.display !== 'none') {
            toggleSessionPopup();
        }
    }
});

// Truncate long text with tooltip
function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Initialize Filter Buttons (with caching)
function initFilters() {
    if (!activeData || activeData.length === 0) return;

    // Ensure all filter Sets exist (add new ones if missing)
    const filterKeys = ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'];
    filterKeys.forEach(key => {
        if (!filters.hasOwnProperty(key) || !(filters[key] instanceof Set)) {
            filters[key] = new Set();
        }
    });

    ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'].forEach(key => {
        const unique = [...new Set(activeData.map(d => {
            if (key === 'model') return d.model || meta.model || "Default";
            if (key === 'positive') return d.positive || meta.positive || "";
            if (key === 'negative') return d.negative || meta.negative || "";
            if (key === 'size') return `${d.width}x${d.height}`;
            return d[key];
        }))].sort();

        const container = document.getElementById('filter-' + key);
        if (!container) return;
        
        const cacheKey = unique.join(',');
        if (filterButtonCache[key] === cacheKey) {
            return;
        }
        
        filterButtonCache[key] = cacheKey;
        container.innerHTML = '';

        unique.forEach(val => {
            const safeVal = String(val).replace(/[^a-zA-Z0-9]/g, '');
            const btnId = `btn-${key}-${safeVal}`;
            
            let b = document.createElement('button');
            b.id = btnId;
            b.className = `filter-btn active ${key}`;

            let label = val;
            let fullText = val;
            
            // Handle special formatting for different filter types
            if (key === 'lora') {
                if (val === "None") {
                    label = "None";
                } else if (val.includes(" + ")) {
                    label = "Stack";
                    fullText = val.replace(/ \+ /g, '\n');
                } else {
                    let clean = val.replace(/\\/g, '/').split('/').pop().split(':')[0];
                    label = truncateText(clean, 12);
                    fullText = val;
                }
            } else if (key === 'model') {
                let clean = val.replace(/\\/g, '/').split('/').pop();
                label = truncateText(clean, 12);
                fullText = val;
            } else if (key === 'positive' || key === 'negative') {
                // Truncate prompts to 30 characters for button display
                label = truncateText(val, 30);
                fullText = val;
            } else if (key === 'seed') {
                // Display seeds in a more readable format
                label = String(val);
                fullText = val;
            }

            b.innerText = label;
            b.title = fullText;

            b.onclick = (e) => {
                // Shift-click: Isolate this filter (deselect all others of this type)
                if (e.shiftKey) {
                    e.preventDefault();
                    
                    // Check if this is the only active filter
                    const isOnlyActive = filters[key].size === 1 && filters[key].has(val);
                    
                    if (isOnlyActive) {
                        // If it's the only one active, select all instead
                        unique.forEach(v => filters[key].add(v));
                        // Update all buttons
                        const allButtons = container.querySelectorAll('.filter-btn');
                        allButtons.forEach(btn => btn.classList.add('active'));
                    } else {
                        // Clear all filters of this type
                        filters[key].clear();
                        // Add only this one
                        filters[key].add(val);
                        
                        // Update all buttons visually
                        const allButtons = container.querySelectorAll('.filter-btn');
                        allButtons.forEach(btn => btn.classList.remove('active'));
                        b.classList.add('active');
                    }
                } else {
                    // Normal click: Toggle this filter
                    if (filters[key].has(val)) {
                        filters[key].delete(val);
                        b.classList.remove('active');
                    } else {
                        filters[key].add(val);
                        b.classList.add('active');
                    }
                }
                
                updateDataPipeline();
            };

            filters[key].add(val);
            container.appendChild(b);
        });
    });
}

// Toggle Favorite

async function toggleFavorite(id) {
    const item = activeData.find(d => d.id === id);
    if (!item) {
        console.warn(`toggleFavorite: Item with id ${id} not found`);
        return;
    }
    
    // Store previous state for rollback
    const previousState = item.favorited;
    
    // Optimistically update the data
    item.favorited = !item.favorited;
    
    // Get UI elements
    const card = document.getElementById(`card-${id}`);
    const favBtn = card ? card.querySelector('.favorite-btn') : null;
    
    // Show loading state
    if (favBtn) {
        favBtn.disabled = true;
        favBtn.style.opacity = '0.6';
        favBtn.style.cursor = 'wait';
        
        if (item.favorited) {
            favBtn.classList.add('favorited');
            favBtn.innerText = '★';
        } else {
            favBtn.classList.remove('favorited');
            favBtn.innerText = '☆';
        }
    }
    
    try {
        // Call the existing saveState function
        const response = await fetch('/config_tester/save_manifest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_name: document.getElementById('session-input')?.value || "default", 
                manifest: fullManifest 
            })
        });
        
        // Check if the request was successful
        if (!response.ok) {
            const errorText = await response.text().catch(() => 'Unknown error');
            throw new Error(`Server error (${response.status}): ${errorText}`);
        }
        
        // Try to parse response to check for any error messages
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const data = await response.json();
            if (data.error || data.success === false) {
                throw new Error(data.message || data.error || 'Save failed');
            }
        }
        
        // Success! Update JSON bars
        updateJSONs(processedData);
        
        // Show success feedback animation
        if (favBtn) {
            favBtn.style.transition = 'transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1)';
            favBtn.style.transform = 'scale(1.25)';
            
            setTimeout(() => {
                favBtn.style.transform = 'scale(1)';
                setTimeout(() => {
                    favBtn.style.transition = '';
                }, 150);
            }, 150);
        }
        
    } catch (error) {
        // Save failed - rollback the change
        console.error('Failed to save favorite state:', error);
        
        item.favorited = previousState;
        
        // Restore UI to previous state
        if (favBtn) {
            if (previousState) {
                favBtn.classList.add('favorited');
                favBtn.innerText = '★';
            } else {
                favBtn.classList.remove('favorited');
                favBtn.innerText = '☆';
            }
        }
        
        // Determine error type for better user message
        let errorTitle = 'Failed to Save Favorite';
        let errorMessage = 'Unable to save changes to the server. Your favorite status has not been saved.';
        
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
            errorTitle = 'Network Error';
            errorMessage = 'Could not connect to the server. Please check your connection and try again.';
        } else if (error.message.includes('500')) {
            errorTitle = 'Server Error';
            errorMessage = 'The server encountered an error. Please try again or contact support.';
        } else if (error.message.includes('404')) {
            errorTitle = 'Endpoint Not Found';
            errorMessage = 'The save endpoint could not be found. Please contact support.';
        }
        
        // Show error alert to user
        showSaveErrorAlert(errorTitle, errorMessage, error.message);
        
    } finally {
        // Always re-enable the button
        if (favBtn) {
            favBtn.disabled = false;
            favBtn.style.opacity = '1';
            favBtn.style.cursor = 'pointer';
        }
    }
}

/**
 * Show error alert popup with details
 */
function showSaveErrorAlert(title, message, technicalDetails = '') {
    // Remove any existing error alert
    const existingAlert = document.getElementById('save-error-alert');
    if (existingAlert) {
        existingAlert.remove();
    }
    
    // Create overlay
    const overlay = document.createElement('div');
    overlay.id = 'save-error-alert';
    overlay.className = 'error-alert-overlay';
    
    // Create popup
    const popup = document.createElement('div');
    popup.className = 'error-alert-popup';
    
    // Build details section if we have technical info
    const detailsHtml = technicalDetails ? `
        <details class="error-alert-details">
            <summary>Technical Details</summary>
            <pre>${technicalDetails}</pre>
        </details>
    ` : '';
    
    popup.innerHTML = `
        <div class="error-alert-header">
            <span class="error-alert-icon">⚠️</span>
            <h3>${title}</h3>
        </div>
        <p class="error-alert-message">${message}</p>
        ${detailsHtml}
        <div class="error-alert-actions">
            <button class="error-alert-button error-alert-button-primary" onclick="this.closest('.error-alert-overlay').remove()">
                OK
            </button>
        </div>
    `;
    
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
    
    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.remove();
        }
    });
    
    // Close on Escape key
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            overlay.remove();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
    
    // Auto-close after 12 seconds
    setTimeout(() => {
        if (overlay.parentNode) {
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 200);
        }
    }, 12000);
}



// Create card - FIXED UI LAYOUT WITH FAVORITE BUTTON
function createCard(d) {
    const totalIndex = idToIndexMap.get(d.id) || 0;
    const card = document.createElement('div');
    card.className = 'card';
    card.id = `card-${d.id}`;
    card.dataset.id = d.id;

    // Check if favorited
    const isFavorited = d.favorited || false;
    const favClass = isFavorited ? 'favorited' : '';
    const favIcon = isFavorited ? '★' : '☆';

    // Calculate LoRA display
    let loraLine = "";
    if (d.lora === "None") {
        loraLine = `<div class="stat"><b>LoRA:</b> <span style="opacity:0.3">-</span></div>`;
    } else if (d.lora.includes(" + ")) {
        const count = d.lora.split(" + ").length;
        loraLine = `<div class="stat" title="${d.lora.replace(/ \+ /g, '\n')}"><b>LoRA:</b> <span style="color:var(--accent-lora)">Stack (${count})</span></div>`;
    } else {
        const rawName = String(d.lora);
        let fileName = rawName.replace(/\\/g, '/').split('/').pop().split(':')[0];
        if (fileName.length > 20) fileName = fileName.substring(0, 18) + '...';
        loraLine = `<div class="stat" title="${d.lora}"><b>LoRA:</b> <span>${fileName}</span></div>`;
    }

    let promptInfo = "";
    // Always show prompt info if available
    if (d.positive || meta.positive) {
        const promptText = d.positive || meta.positive || "";
        const shortPrompt = truncateText(promptText, 30);
        promptInfo = `<div class="stat" title="${promptText}"><b>Pos:</b> ${shortPrompt}</div>`;
    }

    const modelName = d.model || meta.model || "Default";
    const shortModel = modelName.replace(/\\/g, '/').split('/').pop();
    const finalModel = shortModel.length > 25 ? shortModel.substring(0, 22) + "..." : shortModel;

    // Calculate aspect ratio
    const aspectRatio = (d.width && d.height) ? (d.height / d.width) : 1;
    const paddingBottom = (aspectRatio * 100).toFixed(2);

    // FIXED LAYOUT: Star top-right, Revise below it, time bottom-right, index bottom-left
    card.innerHTML = `
        <div class="img-wrapper" style="padding-bottom: ${paddingBottom}%;">
            <img ondblclick="toggleFavorite(${d.id})" data-src="${d.file}" alt="Image ${d.id}" draggable="false">
            <button class="reject-btn" onclick="rejectItem(${d.id})">✕</button>
            <button class="favorite-btn ${favClass}" onclick="toggleFavorite(${d.id})">${favIcon}</button>
            <button class="revise-btn" onclick="openM(${d.id})">REVISE</button>
            <div class="time-tag">${d.duration}s</div>
            <div class="index-tag">#${totalIndex}</div>
        </div>
        <div class="info">
            <div class="stat"><b>Smp:</b> <span>${d.sampler} / ${d.scheduler}</span></div>
            <div class="stat">
                <b>Cfg:</b> ${d.cfg} &nbsp; <b>Stp:</b> ${d.steps} &nbsp; <b>Dn:</b> <span style="color:var(--accent-denoise)">${d.denoise}</span>
            </div>
            <div class="stat" title="${modelName}"><b>Model:</b> <span>${finalModel}</span></div>
            ${loraLine}
            ${promptInfo}
            <div class="stat"><b>Size:</b> ${d.width}x${d.height} &nbsp; <b>Seed:</b> ${d.seed}</div>
        </div>`;

    return card;
}

// Open Revision Modal
function openM(id) {
    const d = activeData.find(x => x.id === id);
    if (!d) return;
    document.getElementById('m-img').src = d.file;

    // Populate read-only info fields
    const modelEl = document.getElementById('f-model');
    const seedEl = document.getElementById('f-seed');
    const posEl = document.getElementById('f-pos');
    const negEl = document.getElementById('f-neg');
    
    if (modelEl) modelEl.value = d.model || meta.model || "Default";
    if (seedEl) seedEl.value = d.seed || 0;
    if (posEl) posEl.value = d.positive || meta.positive || "";
    if (negEl) negEl.value = d.negative || meta.negative || "";

    // Populate editable parameter fields
    const map = { 
        'smp': d.sampler, 
        'sch': d.scheduler, 
        'stp': d.steps, 
        'cfg': d.cfg, 
        'den': d.denoise, 
        'lor': d.lora 
    };
    
    for (let k in map) {
        const el = document.getElementById('f-' + k);
        if (el) el.value = map[k];
    }

    // Populate related variants reel
    const r = document.getElementById('reel'); 
    r.innerHTML = '';
    
    activeData.forEach(x => {
        if (x.rejected) return;
        if (x.seed === d.seed) {
            const i = document.createElement('img'); 
            i.src = x.file; 
            i.onclick = () => openM(x.id);
            if (x.id === id) i.style.borderColor = "var(--accent)";
            r.appendChild(i);
        }
    });
    
    document.getElementById('modal').style.display = 'flex';
}

function closeM() { 
    document.getElementById('modal').style.display = 'none'; 
}

// THROTTLED JSON Updates
let jsonUpdateTimeout = null;

function updateJSONs(visible) {
    if (jsonUpdateTimeout) {
        clearTimeout(jsonUpdateTimeout);
    }
    
    jsonUpdateTimeout = setTimeout(() => {
        generateSmartJSON(visible, 'json-bar-good');
        const favorited = activeData.filter(d => d.favorited && !d.rejected);
        generateSmartJSON(favorited, 'json-bar-favorite');
        const rejected = activeData.filter(d => d.rejected);
        generateSmartJSON(rejected, 'json-bar-bad');
    }, 300);
}

// OPTIMIZED JSON generation
function generateSmartJSON(dataset, targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;
    
    if (dataset.length === 0) { 
        el.innerText = "[]"; 
        return; 
    }

    const limit = Math.min(dataset.length, 100);
    const limited = dataset.slice(0, limit);
    
    const finalOutput = limited.map(d => ({
        sampler: d.sampler,
        scheduler: d.scheduler,
        steps: d.steps,
        cfg: d.cfg,
        denoise: d.denoise,
        lora: d.lora,
        model: d.model || "Default"
    }));

    let jsonText = JSON.stringify(finalOutput, null, 2);
    
    if (dataset.length > 100) {
        jsonText += `\n\n// ... and ${dataset.length - 100} more items`;
    }

    el.innerText = jsonText;
}