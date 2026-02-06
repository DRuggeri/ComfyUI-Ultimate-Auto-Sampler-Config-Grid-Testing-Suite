/**
 * OPTIMIZED DATA PIPELINE
 * Fixed: New items appear immediately when prepended to top
 * Added: Prompt, Size, Seed filters, and Search Filters
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
 
// Generate cache key from current filters (including search filters)
function getFilterKey() { 
    const parts = [
        currentSort,
        [...filters.sampler].sort().join(','),
        [...filters.scheduler].sort().join(','),
        [...filters.denoise].sort().join(','),
        [...filters.lora].sort().join(','),
        [...filters.model].sort().join(','),
        [...filters.positive].sort().join(','),
        [...filters.negative].sort().join(','),
        [...filters.size].sort().join(','),
        [...filters.seed].sort().join(','),
        // Include search filters in cache key
        searchFilters.map(f => `${f.type}:${f.term}`).join('|')
    ];
    return parts.join('|');
}

// INCREMENTAL FILTERING: Only filter new items
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
        if (d.rejected) return false;
        
        // Apply button filters
        if (hasButtonFilters) {
            if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
            if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
            if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
            if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
            if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
            
            // Prompt filters
            if (filters.positive.size > 0 && !filters.positive.has(d.positive || meta.positive || "")) return false;
            if (filters.negative.size > 0 && !filters.negative.has(d.negative || meta.negative || "")) return false;
            
            // Size filter
            if (filters.size.size > 0) {
                const sizeStr = `${d.width}x${d.height}`;
                if (!filters.size.has(sizeStr)) return false;
            }
            
            // Seed filter
            if (filters.seed.size > 0 && !filters.seed.has(d.seed)) return false;
        }
        
        // Apply search filters (if function is available)
        if (typeof matchesSearchFilters === 'function') {
            if (!matchesSearchFilters(d)) return false;
        }
        
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
            
            // Button filters
            if (filters.sampler.size > 0 && !filters.sampler.has(d.sampler)) return false;
            if (filters.scheduler.size > 0 && !filters.scheduler.has(d.scheduler)) return false;
            if (filters.denoise.size > 0 && !filters.denoise.has(d.denoise)) return false;
            if (filters.lora.size > 0 && !filters.lora.has(d.lora)) return false;
            if (filters.model.size > 0 && !filters.model.has(d.model || meta.model || "Default")) return false;
            
            // Prompt filters
            if (filters.positive.size > 0 && !filters.positive.has(d.positive || meta.positive || "")) return false;
            if (filters.negative.size > 0 && !filters.negative.has(d.negative || meta.negative || "")) return false;
            
            // Size filter
            if (filters.size.size > 0) {
                const sizeStr = `${d.width}x${d.height}`;
                if (!filters.size.has(sizeStr)) return false;
            }
            
            // Seed filter
            if (filters.seed.size > 0 && !filters.seed.has(d.seed)) return false;
            
            // Search filters
            if (typeof matchesSearchFilters === 'function') {
                if (!matchesSearchFilters(d)) return false;
            }
            
            return true;
        });
    } else {
        processedData = processedData.filter(d => !d.rejected);
    }

    // Sort
    switch (currentSort) {
        case 'newest':
            processedData.sort((a, b) => b.id - a.id);
            break;
        case 'fastest':
            processedData.sort((a, b) => a.duration - b.duration);
            break;
        case 'favorited':
            // Favorited first, then by ID
            processedData.sort((a, b) => {
                const aFav = a.favorited ? 1 : 0;
                const bFav = b.favorited ? 1 : 0;
                if (bFav !== aFav) return bFav - aFav;
                return a.id - b.id;
            });
            break;
        case 'model':
            processedData.sort((a, b) => {
                const aModel = (a.model || meta.model || "Default").toLowerCase();
                const bModel = (b.model || meta.model || "Default").toLowerCase();
                return aModel.localeCompare(bModel);
            });
            break;
        case 'prompt':
            processedData.sort((a, b) => {
                const aPrompt = (a.positive || meta.positive || "").toLowerCase();
                const bPrompt = (b.positive || meta.positive || "").toLowerCase();
                return aPrompt.localeCompare(bPrompt);
            });
            break;
        case 'cfg':
            processedData.sort((a, b) => a.cfg - b.cfg);
            break;
        case 'denoise':
            processedData.sort((a, b) => a.denoise - b.denoise);
            break;
        case 'lora':
            processedData.sort((a, b) => {
                const aLora = (a.lora || "None").toLowerCase();
                const bLora = (b.lora || "None").toLowerCase();
                return aLora.localeCompare(bLora);
            });
            break;
        case 'sampler':
            processedData.sort((a, b) => {
                const aSampler = (a.sampler || "").toLowerCase();
                const bSampler = (b.sampler || "").toLowerCase();
                return aSampler.localeCompare(bSampler);
            });
            break;
        default: // oldest
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
        // All other sort modes: add items and re-sort entire array
        processedData.push(...filtered);
        
        switch (currentSort) {
            case 'fastest':
                processedData.sort((a, b) => a.duration - b.duration);
                break;
            case 'favorited':
                processedData.sort((a, b) => {
                    const aFav = a.favorited ? 1 : 0;
                    const bFav = b.favorited ? 1 : 0;
                    if (bFav !== aFav) return bFav - aFav;
                    return a.id - b.id;
                });
                break;
            case 'model':
                processedData.sort((a, b) => {
                    const aModel = (a.model || meta.model || "Default").toLowerCase();
                    const bModel = (b.model || meta.model || "Default").toLowerCase();
                    return aModel.localeCompare(bModel);
                });
                break;
            case 'prompt':
                processedData.sort((a, b) => {
                    const aPrompt = (a.positive || meta.positive || "").toLowerCase();
                    const bPrompt = (b.positive || meta.positive || "").toLowerCase();
                    return aPrompt.localeCompare(bPrompt);
                });
                break;
            case 'cfg':
                processedData.sort((a, b) => a.cfg - b.cfg);
                break;
            case 'denoise':
                processedData.sort((a, b) => a.denoise - b.denoise);
                break;
            case 'lora':
                processedData.sort((a, b) => {
                    const aLora = (a.lora || "None").toLowerCase();
                    const bLora = (b.lora || "None").toLowerCase();
                    return aLora.localeCompare(bLora);
                });
                break;
            case 'sampler':
                processedData.sort((a, b) => {
                    const aSampler = (a.sampler || "").toLowerCase();
                    const bSampler = (b.sampler || "").toLowerCase();
                    return aSampler.localeCompare(bSampler);
                });
                break;
        }
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

// Change Sort Order with dropdown
function changeSort() {
    const select = document.getElementById('sort-select');
    if (!select) return;
    
    currentSort = select.value;
    
    // Save to localStorage
    localStorage.setItem('ultimate_grid_sort', currentSort);
    
    console.log(`[Pipeline] Sort changed to: ${currentSort}`);
    updateDataPipeline();
}

// Load sort order from localStorage
function loadSortPreference() {
    const savedSort = localStorage.getItem('ultimate_grid_sort');
    const select = document.getElementById('sort-select');
    
    const validSortOptions = ['oldest', 'newest', 'fastest', 'favorited', 'model', 'prompt', 'cfg', 'denoise', 'lora', 'sampler'];
    
    if (savedSort && validSortOptions.includes(savedSort)) {
        currentSort = savedSort;
        if (select) {
            select.value = currentSort;
        }
        console.log(`[Pipeline] Loaded sort preference: ${currentSort}`);
    }
}

// Update Filters when new data arrives
function updateFiltersForNewData(newItems) {
    let changed = false;
    
    ['model', 'sampler', 'scheduler', 'denoise', 'lora', 'positive', 'negative', 'size', 'seed'].forEach(key => {
        newItems.forEach(d => {
            let val;
            
            if (key === 'model') {
                val = d.model || meta.model || "Default";
            } else if (key === 'positive') {
                val = d.positive || meta.positive || "";
            } else if (key === 'negative') {
                val = d.negative || meta.negative || "";
            } else if (key === 'size') {
                val = `${d.width}x${d.height}`;
            } else {
                val = d[key];
            }
            
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