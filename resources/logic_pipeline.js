/**
 * OPTIMIZED DATA PIPELINE & SORT LOGIC
 * Fixes: Clean code (no window. prefixes), restores refreshIndices, enables Dual Sort
 */

// RESTORED: Helper to update index map
function refreshIndices() {
    if (!activeData) return;
    const sorted = activeData.slice().sort((a, b) => a.id - b.id);
    idToIndexMap = new Map(sorted.map((item, index) => [item.id, index + 1]));
}

// Generate cache key from current filters
function getFilterKey() {
    const parts = [
        currentSort,
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
        case 'newest': return b.id - a.id;
        case 'oldest': return a.id - b.id;
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
        
        // 3. Fallback to ID (Stable sort)
        if (res === 0) {
            return a.id - b.id;
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
            if (filters.positive.size > 0 && !filters.positive.has(d.positive || meta.positive || "")) return false;
            if (filters.negative.size > 0 && !filters.negative.has(d.negative || meta.negative || "")) return false;
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

function executePipeline() {
    const startTime = performance.now();
    const currentFilterKey = getFilterKey();
    const filtersChanged = currentFilterKey !== lastFilterKey;

    if (filtersChanged) {
        console.log('[Pipeline] Filters changed, full reprocess');
        lastFilterKey = currentFilterKey;

        processedData = activeData.filter(d => {
            // Apply top-level filters (Favorites/Non-Favorited/Rejected visibility)
            if (d.favorited && !topFilters.showFavorites) return false;
            if (!d.favorited && !d.rejected && !topFilters.showNonFavorited) return false;
            if (d.rejected && !topFilters.showRejected) return false;

            // Re-apply all filters
            if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
            if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
            if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
            if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
            if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
            if (filters.positive.size > 0 && !filters.positive.has(d.positive || meta.positive || "")) return false;
            if (filters.negative.size > 0 && !filters.negative.has(d.negative || meta.negative || "")) return false;
            if (filters.size.size > 0 && !filters.size.has(`${d.width}x${d.height}`)) return false;
            if (filters.seed.size > 0 && !filters.seed.has(d.seed)) return false;
            
            if (typeof matchesSearchFilters === 'function' && !matchesSearchFilters(d)) return false;

            return true;
        });
    } else {
        // When filters haven't changed, just filter by top-level visibility
        processedData = processedData.filter(d => {
            if (d.favorited && !topFilters.showFavorites) return false;
            if (!d.favorited && !d.rejected && !topFilters.showNonFavorited) return false;
            if (d.rejected && !topFilters.showRejected) return false;
            return true;
        });
    }

    // Apply Sorting (Multi Sort)
    runMultiSort(processedData);

    console.log(`[Pipeline] Processed ${processedData.length} items`);
    updateJSONs(processedData);

    if (filtersChanged) {
        if(typeof renderDOM === 'function') renderDOM();
    } else {
        if (typeof updateVisibleItems === 'function') updateVisibleItems();
    }
}

// OPTIMIZED: Process new data incrementally
function processNewData(newItems) {
    if (!newItems || newItems.length === 0) return;
    
    // Update global active data
    activeData.push(...newItems);
    
    // IMPORTANT: Update indices when new data arrives
    refreshIndices(); 

    // Update filter options
    updateFiltersForNewData(newItems);
    
    // Process pipeline
    const filtered = incrementalFilter(newItems);
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
        // All other sort modes: add items and re-sort entire array
        processedData.push(...filtered);
        runMultiSort(processedData);
    }
    
    updateJSONs(processedData);
    
    if (prependedToTop && typeof forceVisibleRangeUpdate === 'function') {
        forceVisibleRangeUpdate(filtered.length);
    } else if (typeof updateVisibleItems === 'function') {
        updateVisibleItems();
    }
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
    let changed = false;
    ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'].forEach(key => {
        newItems.forEach(d => {
            let val;
            if (key === 'model') val = d.model || meta.model || "Default";
            else if (key === 'positive') val = d.positive || meta.positive || "";
            else if (key === 'negative') val = d.negative || meta.negative || "";
            else if (key === 'size') val = `${d.width}x${d.height}`;
            else val = d[key];

            if (val && !filters[key].has(val)) {
                changed = true;
            }
        });
    });
    
    if (changed && typeof initFilters === 'function') {
        initFilters(); // Re-render filter buttons
    }
}

// --- 5. INITIALIZATION ---
// Ensure init fires after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[Init] DOMContentLoaded - calling loadSession');
        loadSession();
    });
} else {
    console.log('[Init] DOM already loaded - calling loadSession');
    loadSession();
}