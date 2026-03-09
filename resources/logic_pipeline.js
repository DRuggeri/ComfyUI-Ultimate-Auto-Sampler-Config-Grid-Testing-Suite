/**
 * OPTIMIZED DATA PIPELINE & SORT LOGIC
 * Fixes: Clean code (no window. prefixes), restores refreshIndices, enables Dual Sort
 */

// Threshold for switching to async pipeline processing (used by multiple functions)
const ASYNC_PIPELINE_THRESHOLD = 500;

// RESTORED: Helper to update index map
// Maps each item's ID to its sequential position (1-based) when sorted by ID.
// This provides a stable "original order" number for each card regardless of
// current sort/filter, used for "Go To Card #" and the #N tag on cards.
function refreshIndices() {
    if (!activeData) return;
    const sorted = activeData.slice().sort((a, b) => (a.gen_index ?? a.id) - (b.gen_index ?? b.id));
    idToIndexMap = new Map(sorted.map((item, index) => [item.id, index + 1]));
}

// Generate cache key from current filters
function getFilterKey() {
    const parts = [
        currentSort,
        currentSecondarySort,
        topFilters.showFavorites ? '1' : '0',
        topFilters.showNonFavorited ? '1' : '0',
        topFilters.showRejected ? '1' : '0',
        [...filters.sampler].sort().join(','),
        [...filters.scheduler].sort().join(','),
        [...filters.denoise].sort().join(','),
        [...filters.lora].sort().join(','),
        [...filters.model].sort().join(','),
        [...filters.positive].sort().join(','),
        [...filters.negative].sort().join(','),
        [...filters.size].sort().join(','),
        [...filters.seed].sort().join(','),
        searchFilters.map(f => `${f.type}:${f.term}`).join('|')
    ];
    return parts.join('|');
}

// --- 3. SORT UI LOGIC ---

function initSortUI() {
    console.log('[initSortUI] Called');
    
    const pList = document.getElementById('sort-list-primary');
    const sList = document.getElementById('sort-list-secondary');
    
    console.log('[initSortUI] Elements found:', {
        pList: !!pList,
        sList: !!sList,
        currentSort,
        currentSecondarySort
    });
    
    // Safety check: if HTML elements are missing, stop
    if(!pList || !sList) {
        console.error('[initSortUI] Missing elements! Cannot initialize sort UI');
        return;
    }

    // Helper to create options
    const renderOptions = (container, isSecondary) => {
        console.log(`[initSortUI] Rendering ${isSecondary ? 'secondary' : 'primary'} options`);
        container.innerHTML = ''; // Clear existing
        
        // Add "None" option for secondary only
        if (isSecondary) {
            const div = document.createElement('div');
            div.className = `sort-option ${currentSecondarySort === 'none' ? 'secondary-selected' : ''}`;
            div.textContent = 'None';
            div.onclick = () => setSecondarySort('none');
            container.appendChild(div);
        }

        sortOptionsList.forEach(opt => {
            const div = document.createElement('div');
            div.className = 'sort-option';
            div.textContent = opt.label;
            
            // Interaction Logic
            if (!isSecondary) {
                // Primary Column
                if (currentSort === opt.id) div.classList.add('selected');
                div.onclick = () => setPrimarySort(opt.id);
            } else {
                // Secondary Column
                if (currentSecondarySort === opt.id) div.classList.add('secondary-selected');
                
                // Disable if same as primary
                if (currentSort === opt.id) {
                    div.style.opacity = '0.3';
                    div.style.pointerEvents = 'none';
                }
                div.onclick = () => setSecondarySort(opt.id);
            }
            container.appendChild(div);
        });
        
        console.log(`[initSortUI] Rendered ${container.children.length} options for ${isSecondary ? 'secondary' : 'primary'}`);
    };

    renderOptions(pList, false);
    renderOptions(sList, true);
    
    // Update the main button label
    const primLabel = sortOptionsList.find(x => x.id === currentSort)?.label || 'Oldest';
    const secLabel = sortOptionsList.find(x => x.id === currentSecondarySort)?.label;
    
    const btnLbl = document.getElementById('sort-primary-label');
    if(btnLbl) {
        const secHtml = (secLabel && currentSecondarySort !== 'none') ? '+ ' + secLabel : '';
        btnLbl.innerHTML = `${primLabel} <span style="color:#666; font-weight:400; font-size:9px;">${secHtml}</span>`;
        console.log('[initSortUI] Updated button label:', btnLbl.innerHTML);
    }
}

function toggleSortPopup() {
    console.log('[toggleSortPopup] Called');
    
    const popup = document.getElementById('sort-popup');
    const btn = document.getElementById('sort-main-btn');
    
    if (!popup) {
        console.error('[toggleSortPopup] Popup element not found!');
        return;
    }
    
    const isHidden = popup.style.display === 'none' || !popup.style.display;
    console.log('[toggleSortPopup] Current state:', isHidden ? 'hidden' : 'visible');
    
    if (isHidden) {
        console.log('[toggleSortPopup] Opening popup');
        initSortUI(); 
        popup.style.display = 'flex';
        if(btn) btn.classList.add('active');
    } else {
        console.log('[toggleSortPopup] Closing popup');
        closeSortPopup();
    }
}

function closeSortPopup() {
    const popup = document.getElementById('sort-popup');
    const btn = document.getElementById('sort-main-btn');
    if (popup) popup.style.display = 'none';
    if (btn) btn.classList.remove('active');
}

function setPrimarySort(id) {
    console.log('[setPrimarySort]', id);
    currentSort = id;
    localStorage.setItem('ultimate_grid_sort', currentSort);
    initSortUI(); 
    updateDataPipeline();
}

function setSecondarySort(id) {
    console.log('[setSecondarySort]', id);
    currentSecondarySort = id;
    localStorage.setItem('ultimate_grid_sort_sec', currentSecondarySort);
    closeSortPopup(); 
    initSortUI();
    updateDataPipeline();
}

// Unified Comparison Helper
function compareItems(a, b, sortKey) {
    switch (sortKey) {
        case 'newest': return (b.gen_index ?? b.id) - (a.gen_index ?? a.id);
        case 'oldest': return (a.gen_index ?? a.id) - (b.gen_index ?? b.id);
        case 'fastest': return a.duration - b.duration;
        case 'favorited': return (b.favorited ? 1 : 0) - (a.favorited ? 1 : 0);
        case 'cfg': return a.cfg - b.cfg;
        case 'denoise': return a.denoise - b.denoise;
        case 'seed': return a.seed - b.seed;
        case 'model': 
            return (a.model || meta.model || "Default").toLowerCase().localeCompare((b.model || meta.model || "Default").toLowerCase());
        case 'prompt': 
            return (a.positive || meta.positive || "").toLowerCase().localeCompare((b.positive || meta.positive || "").toLowerCase());
        case 'lora': 
            return (a.lora || "None").toLowerCase().localeCompare((b.lora || "None").toLowerCase());
        case 'sampler': 
            return (a.sampler || "").toLowerCase().localeCompare((b.sampler || "").toLowerCase());
        case 'size':
            return (a.width * a.height) - (b.width * b.height);
        default: return 0;
    }
}

// Master Sort Function
function runMultiSort(list) {
    list.sort((a, b) => {
        // 1. Primary Sort
        let res = compareItems(a, b, currentSort);
        
        // 2. Secondary Sort (if Primary is tied and Secondary is active)
        if (res === 0 && currentSecondarySort !== 'none' && currentSecondarySort !== currentSort) {
            res = compareItems(a, b, currentSecondarySort);
        }
        
        // 3. Fallback to gen_index/ID (Stable sort, backwards-compatible)
        if (res === 0) {
            return (a.gen_index ?? a.id) - (b.gen_index ?? b.id);
        }
        return res;
    });
}

// --- 4. PIPELINE & FILTER LOGIC ---

function incrementalFilter(newItems) {
    const hasButtonFilters = filters.sampler.size > 0 ||
        filters.scheduler.size > 0 ||
        filters.denoise.size > 0 ||
        filters.lora.size > 0 ||
        filters.model.size > 0 ||
        filters.positive.size > 0 ||
        filters.negative.size > 0 ||
        filters.size.size > 0 ||
        filters.seed.size > 0;

    return newItems.filter(d => {
        // Apply top-level filters (Favorites/Non-Favorited/Rejected visibility)
        if (d.favorited && !topFilters.showFavorites) return false;
        if (!d.favorited && !d.rejected && !topFilters.showNonFavorited) return false;
        if (d.rejected && !topFilters.showRejected) return false;

        // Apply button filters
        if (hasButtonFilters) {
            if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
            if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
            if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
            if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
            if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
            if (filters.positive.size > 0) {
                const st = document.getElementById('toggle-triggers')?.checked !== false;
                const posValue = st ? (d.positive || meta.positive || "") : (d.config_positive || d.positive || meta.positive || "");
                if (!filters.positive.has(posValue)) return false;
            }
            if (filters.negative.size > 0) {
                const st = document.getElementById('toggle-triggers')?.checked !== false;
                const negValue = st ? (d.negative || meta.negative || "") : (d.config_negative || d.negative || meta.negative || "");
                if (!filters.negative.has(negValue)) return false;
            }
            if (filters.size.size > 0) {
                const sizeStr = `${d.width}x${d.height}`;
                if (!filters.size.has(sizeStr)) return false;
            }
            if (filters.seed.size > 0 && !filters.seed.has(d.seed)) return false;
        }

        // Apply search filters
        if (typeof matchesSearchFilters === 'function') {
            if (!matchesSearchFilters(d)) return false;
        }

        return true;
    });
}

function updateDataPipeline() {
    if (isPipelinePending) return;
    isPipelinePending = true;

    requestAnimationFrame(() => {
        executePipeline();
        isPipelinePending = false;
    });
}

// Abort controller for canceling in-progress async pipelines
let pipelineAbortId = 0;

function executePipeline() {
    const startTime = performance.now();
    const currentFilterKey = getFilterKey();
    const filtersChanged = currentFilterKey !== lastFilterKey;

    // Always filter from activeData to prevent data loss from self-filtering
    console.log(`[Pipeline] ${filtersChanged ? 'Filters changed, full reprocess' : 'Re-applying filters'}`);
    if (filtersChanged) {
        lastFilterKey = currentFilterKey;
    }

    // Check for button filters once to avoid repeated Set.size lookups
    const hasButtonFilters = filters.sampler.size > 0 ||
        filters.scheduler.size > 0 ||
        filters.denoise.size > 0 ||
        filters.lora.size > 0 ||
        filters.model.size > 0 ||
        filters.positive.size > 0 ||
        filters.negative.size > 0 ||
        filters.size.size > 0 ||
        filters.seed.size > 0;

    const hasSearchFilters = typeof matchesSearchFilters === 'function' && searchFilters.length > 0;

    processedData = activeData.filter(d => {
        // Apply top-level filters (Favorites/Non-Favorited/Rejected visibility)
        if (d.favorited && !topFilters.showFavorites) return false;
        if (!d.favorited && !d.rejected && !topFilters.showNonFavorited) return false;
        if (d.rejected && !topFilters.showRejected) return false;

        // Apply button filters (skip entirely if none are active)
        if (hasButtonFilters) {
            if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
            if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
            if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
            if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
            if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
            if (filters.positive.size > 0) {
                const st = document.getElementById('toggle-triggers')?.checked !== false;
                const posValue = st ? (d.positive || meta.positive || "") : (d.config_positive || d.positive || meta.positive || "");
                if (!filters.positive.has(posValue)) return false;
            }
            if (filters.negative.size > 0) {
                const st = document.getElementById('toggle-triggers')?.checked !== false;
                const negValue = st ? (d.negative || meta.negative || "") : (d.config_negative || d.negative || meta.negative || "");
                if (!filters.negative.has(negValue)) return false;
            }
            if (filters.size.size > 0 && !filters.size.has(`${d.width}x${d.height}`)) return false;
            if (filters.seed.size > 0 && !filters.seed.has(d.seed)) return false;
        }

        if (hasSearchFilters && !matchesSearchFilters(d)) return false;

        return true;
    });

    // Apply sorting
    // Fast path: for oldest/newest with no secondary sort, activeData is stored newest-first
    // (items are inserted/unshifted at position 0), so processedData after filter() is also newest-first.
    // For 'oldest' we reverse; for 'newest' it's already correct.
    if ((currentSort === 'oldest' || currentSort === 'newest') && currentSecondarySort === 'none') {
        if (currentSort === 'oldest') {
            processedData.reverse();
        }
    } else {
        runMultiSort(processedData);
    }

    const elapsed = (performance.now() - startTime).toFixed(1);
    console.log(`[Pipeline] Processed ${processedData.length} items in ${elapsed}ms`);
    updateJSONs(processedData);

    if (filtersChanged) {
        if(typeof renderDOM === 'function') renderDOM();
    } else {
        if (typeof updateVisibleItems === 'function') updateVisibleItems();
    }
}

// OPTIMIZED: Process new data incrementally
// NOTE: Caller (logic_events.js) already adds newItems to fullManifest.items
// which IS activeData (same array reference from init). So we must NOT push
// to activeData again here to avoid duplicate entries.
function processNewData(newItems) {
    if (!newItems || newItems.length === 0) return;

    // IMPORTANT: Update indices when new data arrives
    // (activeData already contains the new items via fullManifest.items reference)
    refreshIndices();

    // Recompute label global values when data changes (new items may change what's unique)
    // Then refresh ALL existing card labels since what's "unique" may have changed
    if (typeof computeLabelGlobalValues === 'function' && labelMode && labelMode.enabled) {
        computeLabelGlobalValues();
        if (typeof refreshLabelOverlays === 'function') {
            refreshLabelOverlays();
        }
    }

    // Update filter options
    updateFiltersForNewData(newItems);

    // Process pipeline
    const filtered = incrementalFilter(newItems);
    if (filtered.length === 0) {
        // All new items were filtered out, just update JSONs
        updateJSONs(processedData);
        return;
    }

    let prependedToTop = false;

    // Logic for Prepend/Append based on Sort Mode
    if (currentSort === 'newest') {
        // Prepend to beginning
        processedData.unshift(...filtered);
        // Only consider it "prepended" (stable scroll) if we aren't sub-sorting
        if(currentSecondarySort === 'none') prependedToTop = true;
    } else if (currentSort === 'oldest') {
        // Append to end
        processedData.push(...filtered);
    } else {
        // For other sort modes with large datasets, use binary insertion instead of full re-sort
        if (processedData.length > ASYNC_PIPELINE_THRESHOLD && filtered.length < 50) {
            // Binary insert each new item into already-sorted array (much faster than re-sorting all)
            for (const item of filtered) {
                binaryInsert(processedData, item);
            }
        } else {
            // Small dataset or large batch of new items: just append and re-sort
            processedData.push(...filtered);
            runMultiSort(processedData);
        }
    }

    updateJSONs(processedData);

    if (prependedToTop && typeof forceVisibleRangeUpdate === 'function') {
        forceVisibleRangeUpdate(filtered.length);
    } else if (typeof updateVisibleItems === 'function') {
        updateVisibleItems();
    }
}

// Binary insert a single item into an already-sorted array
function binaryInsert(arr, item) {
    let low = 0;
    let high = arr.length;

    while (low < high) {
        const mid = (low + high) >>> 1;
        let cmp = compareItems(arr[mid], item, currentSort);
        if (cmp === 0 && currentSecondarySort !== 'none' && currentSecondarySort !== currentSort) {
            cmp = compareItems(arr[mid], item, currentSecondarySort);
        }
        if (cmp === 0) {
            cmp = (arr[mid].gen_index ?? arr[mid].id) - (item.gen_index ?? item.id); // Stable sort fallback
        }
        if (cmp <= 0) {
            low = mid + 1;
        } else {
            high = mid;
        }
    }

    arr.splice(low, 0, item);
}

// Load sort order from localStorage
function loadSortPreference() {
    const savedSort = localStorage.getItem('ultimate_grid_sort');
    const savedSec = localStorage.getItem('ultimate_grid_sort_sec');
    
    const validSortOptions = sortOptionsList.map(o => o.id);

    if (savedSort && validSortOptions.includes(savedSort)) {
        currentSort = savedSort;
    }
    
    if (savedSec) {
        currentSecondarySort = savedSec;
    }

    console.log(`[loadSortPreference] Loaded sort: ${currentSort}, Secondary: ${currentSecondarySort}`);
    
    // Initialize the UI after a brief delay to ensure DOM is ready
    setTimeout(() => {
        console.log('[loadSortPreference] Initializing Sort UI after delay');
        initSortUI();
    }, 100);
}

function updateFiltersForNewData(newItems) {
    // Track which filter categories actually got new unique values
    let changed = false;
    const filterKeys = ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'];

    // Build a set of new values for each key in a single pass over newItems
    for (let i = 0; i < newItems.length; i++) {
        const d = newItems[i];
        for (let k = 0; k < filterKeys.length; k++) {
            const key = filterKeys[k];
            let val;
            if (key === 'model') val = d.model || meta.model || "Default";
            else if (key === 'positive') val = d.positive || meta.positive || "";
            else if (key === 'negative') val = d.negative || meta.negative || "";
            else if (key === 'size') val = `${d.width}x${d.height}`;
            else val = d[key];

            if (val !== undefined && val !== null && !filters[key].has(val)) {
                changed = true;
                // Don't break - we need to continue checking all items/keys
                // so that initFilters gets a complete picture
            }
        }
        if (changed) break; // Once we know we need to rebuild, no need to check more items
    }

    if (changed && typeof initFilters === 'function') {
        initFilters(); // Re-render filter buttons
    }
}

// --- 5. INITIALIZATION ---
// Ensure init fires after DOM is ready
// Note: init() in logic_init.js handles the full initialization including
// showSessionLandingIfEmpty() for sessions with no data. Only call loadSession()
// here when we have embedded data to reload from disk.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (fullManifest && fullManifest.items && fullManifest.items.length > 0) {
            console.log('[Init] DOMContentLoaded - calling loadSession');
            loadSession();
        }
    });
} else {
    if (fullManifest && fullManifest.items && fullManifest.items.length > 0) {
        console.log('[Init] DOM already loaded - calling loadSession');
        loadSession();
    }
}