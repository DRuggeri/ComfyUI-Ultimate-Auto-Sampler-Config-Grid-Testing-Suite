/**
 * OPTIMIZED DATA PIPELINE
 * Fixed: New items appear immediately when prepended to top
 */

let isPipelinePending = false;
let filterCache = new Map();
let lastFilterKey = null;

// Helper to update index map
function refreshIndices() {
    if (!activeData) return;
    const sorted = activeData.slice().sort((a, b) => a.id - b.id);
    idToIndexMap = new Map(sorted.map((item, index) => [item.id, index + 1]));
}

// Generate cache key from current filters
function getFilterKey() {
    const parts = [
        currentSort,
        [...filters.sampler].sort().join(','),
        [...filters.scheduler].sort().join(','),
        [...filters.denoise].sort().join(','),
        [...filters.lora].sort().join(','),
        [...filters.model].sort().join(',')
    ];
    return parts.join('|');
}

// INCREMENTAL FILTERING: Only filter new items
function incrementalFilter(newItems) {
    const hasFilters = filters.sampler.size > 0 || 
                       filters.scheduler.size > 0 || 
                       filters.denoise.size > 0 ||
                       filters.lora.size > 0 ||
                       filters.model.size > 0;
    
    if (!hasFilters) {
        return newItems.filter(d => !d.rejected);
    }

    return newItems.filter(d => {
        if (d.rejected) return false;
        
        if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
        if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
        if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
        if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
        if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
        
        return true;
    });
}

// MAIN TRIGGER: Debounced and cached
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
            if (d.rejected) return false;
            
            if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
            if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
            if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
            if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
            if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
            
            return true;
        });
    } else {
        processedData = processedData.filter(d => !d.rejected);
    }

    // Sort
    if (currentSort === 'newest') {
        processedData.sort((a, b) => b.id - a.id);
    } else if (currentSort === 'fastest') {
        processedData.sort((a, b) => a.duration - b.duration);
    } else {
        processedData.sort((a, b) => a.id - b.id);
    }

    const elapsed = performance.now() - startTime;
    console.log(`[Pipeline] ✅ Processed ${processedData.length} items in ${elapsed.toFixed(1)}ms`);

    updateJSONs(processedData);
    
    // Only full re-render if filters changed
    if (filtersChanged) {
        renderDOM();
    } else {
        if (typeof updateVisibleItems === 'function') {
            updateVisibleItems();
        }
    }
}

// OPTIMIZED: Process new data incrementally
function processNewData(newItems) {
    if (!newItems || newItems.length === 0) return;
    
    console.log(`[Pipeline] ⚡ Processing ${newItems.length} new items incrementally`);
    
    const filtered = incrementalFilter(newItems);
    
    // Track if we're prepending (affects visible range)
    let prependedToTop = false;
    
    // Add to correct position based on sort mode
    if (currentSort === 'newest') {
        // Prepend to beginning
        processedData.unshift(...filtered);
        prependedToTop = true;
    } else if (currentSort === 'oldest') {
        // Append to end
        processedData.push(...filtered);
    } else {
        // Fastest: need to re-sort
        processedData.push(...filtered);
        processedData.sort((a, b) => a.duration - b.duration);
    }
    
    console.log(`[Pipeline] Now have ${processedData.length} items`);
    
    updateJSONs(processedData);
    
    // CRITICAL FIX: If prepended to top, force visible range recalc
    if (prependedToTop && typeof forceVisibleRangeUpdate === 'function') {
        forceVisibleRangeUpdate(filtered.length);
    } else if (typeof updateVisibleItems === 'function') {
        updateVisibleItems();
    }
}

// Toggle Sort Order with localStorage
function toggleSort() {
    const b = document.getElementById('sort-btn');
    if (currentSort === 'oldest') { 
        currentSort = 'newest'; 
        b.innerText = "Sort: Newest"; 
    } else if (currentSort === 'newest') { 
        currentSort = 'fastest'; 
        b.innerText = "Sort: Fastest"; 
    } else { 
        currentSort = 'oldest'; 
        b.innerText = "Sort: Oldest"; 
    }
    
    // Save to localStorage
    localStorage.setItem('ultimate_grid_sort', currentSort);
    
    updateDataPipeline();
}

// Load sort order from localStorage
function loadSortPreference() {
    const savedSort = localStorage.getItem('ultimate_grid_sort');
    if (savedSort && ['oldest', 'newest', 'fastest'].includes(savedSort)) {
        currentSort = savedSort;
        const b = document.getElementById('sort-btn');
        if (b) {
            if (currentSort === 'newest') {
                b.innerText = "Sort: Newest";
            } else if (currentSort === 'fastest') {
                b.innerText = "Sort: Fastest";
            } else {
                b.innerText = "Sort: Oldest";
            }
        }
        console.log(`[Pipeline] Loaded sort preference: ${currentSort}`);
    }
}

// Update Filters when new data arrives
function updateFiltersForNewData(newItems) {
    let changed = false;
    
    ['model', 'sampler', 'scheduler', 'denoise', 'lora'].forEach(key => {
        newItems.forEach(d => {
            const val = (key === 'model') ? (d.model || meta.model || "Default") : d[key];
            
            if (!filters[key].has(val)) {
                changed = true;
                filters[key].add(val); 
            }
        });
    });
    
    if (changed && typeof initFilters === 'function') {
        console.log('[Pipeline] New filter options detected, rebuilding filter UI');
        initFilters();
    }
}