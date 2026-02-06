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


let pendingSaveItems = new Map();  // CHANGED: Set -> Map
let saveTimer = null;
const SAVE_BATCH_DELAY = 2000;

/**
 * OPTIMIZED: Schedule a save that only sends changed items
 */
function scheduleBatchedSave() {
    if (saveTimer) {
        clearTimeout(saveTimer);
    }

    saveTimer = setTimeout(async () => {
        if (pendingSaveItems.size === 0) return;

        console.log(`[Save] 💾 Sending ${pendingSaveItems.size} changed items to server`);

        try {
            const sessionName = document.getElementById('session-input')?.value || "default";

            // Convert Map to array of items
            const changedItems = Array.from(pendingSaveItems.values());

            // CHANGED: Use new endpoint that only accepts changed items
            const response = await fetch('/config_tester/save_changes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_name: sessionName,
                    changed_items: changedItems  // Only changed items!
                })
            });

            if (!response.ok) {
                throw new Error(`Save failed: ${response.status}`);
            }

            console.log(`[Save] ✅ Successfully saved ${pendingSaveItems.size} changes`);
            pendingSaveItems.clear();

        } catch (error) {
            console.error('[Save] ❌ Batch save failed:', error);
            // Don't clear pendingSaveItems - will retry on next change
        }
    }, SAVE_BATCH_DELAY);
}
function markItemChanged(item) {
    if (!item || !item.id) return;

    // Store the full item object, not just the ID
    pendingSaveItems.set(item.id, item);
    scheduleBatchedSave();
}
// Lightweight JSON update (separate debounce from save)
let jsonUpdateTimer = null;
const JSON_UPDATE_DELAY = 500; // 500ms debounce

function scheduleJSONUpdate() {
    if (jsonUpdateTimer) {
        clearTimeout(jsonUpdateTimer);
    }

    jsonUpdateTimer = setTimeout(() => {
        updateJSONs(processedData);
    }, JSON_UPDATE_DELAY);
}

// Toggle Favorite

async function toggleFavorite(element) {
    // [OPTIMIZATION] Find parent card and grab data directly (O(1) access)
    // No getElementById, no array.find, no iteration.
    const card = element.closest('.card');
    if (!card || !card._dataItem) return;

    const item = card._dataItem;

    // Update Data
    item.favorited = !item.favorited;
 
    // Update UI - Scope querySelector to just this card for extra speed
    const favBtn = card.querySelector('.favorite-btn');

    if (favBtn) {
        favBtn.classList.toggle('favorited', item.favorited);
        favBtn.innerText = item.favorited ? '★' : '☆';

        // Simple animation
        favBtn.style.transform = 'scale(1.2)';
        setTimeout(() => favBtn.style.transform = 'scale(1)', 120);
    }

    markItemChanged(item);
    scheduleJSONUpdate();
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
    card._dataItem = d;
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
        loraLine = `<div class="stat" title="${d.lora.replace(/ \+ /g, '\n')}"><b>LoRA:</b><br /> <span style="color:var(--accent-lora)">(${d.lora.replace(/ \+ /g, '\n')})</span></div>`;
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
            <img ondblclick="toggleFavorite(this)" data-src="${d.file}" alt="Image ${d.id}" draggable="false">
            <button class="reject-btn" onclick="rejectItem(this)">✕</button>
            <button class="favorite-btn ${favClass}" onclick="toggleFavorite(this)">${favIcon}</button>
            <button class="revise-btn" onclick="openM(${d.id})">REVISE</button>
            <div class="time-tag">${d.duration}s</div>
            <div class="index-tag">#${totalIndex}</div>
        </div>
        <div class="info">
            <div class="stat" title="${modelName}"><b>Model:</b> <span>${finalModel}</span></div>

            ${loraLine}
            <div class="stat"><b>Smp:</b> <span>${d.sampler} / ${d.scheduler}</span></div>
            <div class="stat">
                <b>Cfg:</b> ${d.cfg} &nbsp; <b>Stp:</b> ${d.steps} &nbsp; <b>Dn:</b> <span style="color:var(--accent-denoise)">${d.denoise}</span>
            </div>
            
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
        // 🚀 OPTIMIZED: Single pass through data instead of 3 separate filters
        const good = [];
        const favorited = [];
        const rejected = [];

        for (const item of activeData) {
            if (item.rejected) {
                rejected.push(item);
            } else {
                good.push(item);
                if (item.favorited) {
                    favorited.push(item);
                }
            }
        }

        // Disabled automatic JSON generation - now on-demand via buttons
        // Store the datasets for on-demand generation
        window.cachedJSONData = { good, favorited, rejected };
        
        // Update button labels with counts
        updateJSONButtonLabels(good.length, favorited.length, rejected.length);
    }, 100); // Reduced from 300ms since we have separate debounce above
}

// OPTIMIZED JSON generation
const jsonElCache = new Map();

// Fallback for browsers that don't support requestIdleCallback
const runIdle = window.requestIdleCallback || (cb => setTimeout(cb, 1));
const cancelIdle = window.cancelIdleCallback || clearTimeout;

function generateSmartJSON(dataset, targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;

    if (dataset.length === 0) {
        el.innerText = "[]";
        return;
    }

    // Processing Logic
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

// Add button label update function
function updateJSONButtonLabels(goodCount, favCount, rejCount) {
    const goodBtn = document.getElementById('json-btn-good');
    const favBtn = document.getElementById('json-btn-favorite');
    const rejBtn = document.getElementById('json-btn-bad');
    
    if (goodBtn) goodBtn.innerText = `View Configs (${goodCount})`;
    if (favBtn) favBtn.innerText = `View Favorited (${favCount})`;
    if (rejBtn) rejBtn.innerText = `View Rejected (${rejCount})`;
}

// On-demand JSON generation functions
function viewGoodJSON() {
    if (!window.cachedJSONData) return;
    const bar = document.getElementById('json-bar-good');
    if (!bar) return;
    
    // Toggle visibility
    if (bar.style.display === 'block') {
        bar.style.display = 'none';
        return;
    }
    
    const { good } = window.cachedJSONData;
    generateSmartJSON(good, 'json-bar-good');
    
    bar.style.display = 'block';
    bar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function viewFavoritedJSON() {
    if (!window.cachedJSONData) return;
    const bar = document.getElementById('json-bar-favorite');
    if (!bar) return;
    
    // Toggle visibility
    if (bar.style.display === 'block') {
        bar.style.display = 'none';
        return;
    }
    
    const { favorited } = window.cachedJSONData;
    generateSmartJSON(favorited, 'json-bar-favorite');
    
    bar.style.display = 'block';
    bar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function viewRejectedJSON() {
    if (!window.cachedJSONData) return;
    const bar = document.getElementById('json-bar-bad');
    if (!bar) return;
    
    // Toggle visibility
    if (bar.style.display === 'block') {
        bar.style.display = 'none';
        return;
    }
    
    const { rejected } = window.cachedJSONData;
    generateSmartJSON(rejected, 'json-bar-bad');
    
    bar.style.display = 'block';
    bar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
/**
 * SEARCH FILTER FUNCTIONS
 */

// Add a search filter
function addSearchFilter() {
    const typeSelect = document.getElementById('search-filter-type');
    const inputField = document.getElementById('search-filter-input');

    if (!typeSelect || !inputField) return;

    const filterType = typeSelect.value;
    const searchTerm = inputField.value.trim();

    // Validation
    if (!filterType) {
        alert('Please select a filter type');
        return;
    }

    if (!searchTerm) {
        alert('Please enter a search term');
        return;
    }

    // Check if this exact filter already exists
    const exists = searchFilters.some(f => f.type === filterType && f.term === searchTerm);
    if (exists) {
        alert('This search filter already exists');
        return;
    }

    // Add to search filters array
    searchFilters.push({
        type: filterType,
        term: searchTerm
    });

    // Clear inputs
    typeSelect.value = '';
    inputField.value = '';

    // Update UI
    renderSearchFilters();

    // Trigger data pipeline update
    updateDataPipeline();

    console.log(`[Search Filter] Added: ${filterType} contains "${searchTerm}"`);
}

// Remove a search filter
function removeSearchFilter(index) {
    if (index >= 0 && index < searchFilters.length) {
        const removed = searchFilters.splice(index, 1)[0];
        console.log(`[Search Filter] Removed: ${removed.type} contains "${removed.term}"`);

        // Update UI
        renderSearchFilters();

        // Trigger data pipeline update
        updateDataPipeline();
    }
}

// Clear all search filters
function clearAllSearchFilters() {
    if (searchFilters.length === 0) return;

    searchFilters = [];
    renderSearchFilters();
    updateDataPipeline();

    console.log('[Search Filter] All search filters cleared');
}

// Render search filter tags
function renderSearchFilters() {
    const container = document.getElementById('active-search-filters');
    if (!container) return;

    container.innerHTML = '';

    if (searchFilters.length === 0) {
        container.innerHTML = '<div style="color: #555; font-size: 10px; padding: 4px 0;">No active search filters</div>';
        return;
    }

    searchFilters.forEach((filter, index) => {
        const tag = document.createElement('div');
        tag.className = 'search-filter-tag';

        // Format display name for filter type
        const typeNames = {
            'model': 'Model',
            'positive': 'Positive',
            'negative': 'Negative',
            'sampler': 'Sampler',
            'scheduler': 'Scheduler',
            'lora': 'LoRA'
        };

        tag.innerHTML = `
            <span class="filter-type ${filter.type}">${typeNames[filter.type] || filter.type}</span>
            <span class="filter-term" title="${filter.term}">${filter.term}</span>
            <button class="remove-btn" onclick="removeSearchFilter(${index})" title="Remove filter">✕</button>
        `;

        container.appendChild(tag);
    });

    // Add clear all button if there are multiple filters
    if (searchFilters.length > 1) {
        const clearBtn = document.createElement('button');
        clearBtn.className = 'search-filter-add-btn';
        clearBtn.style.background = '#ff3860';
        clearBtn.style.padding = '4px 10px';
        clearBtn.innerText = 'CLEAR ALL';
        clearBtn.onclick = clearAllSearchFilters;
        container.appendChild(clearBtn);
    }
}

// Check if an item matches search filters
function matchesSearchFilters(item) {
    if (searchFilters.length === 0) return true;

    // Item must match ALL search filters (AND logic)
    return searchFilters.every(filter => {
        let value = '';

        switch (filter.type) {
            case 'model':
                value = item.model || meta.model || "Default";
                break;
            case 'positive':
                value = item.positive || meta.positive || "";
                break;
            case 'negative':
                value = item.negative || meta.negative || "";
                break;
            case 'sampler':
                value = item.sampler || "";
                break;
            case 'scheduler':
                value = item.scheduler || "";
                break;
            case 'lora':
                value = item.lora || "";
                break;
            default:
                return false;
        }

        // Case-insensitive search
        return value.toLowerCase().includes(filter.term.toLowerCase());
    });
}