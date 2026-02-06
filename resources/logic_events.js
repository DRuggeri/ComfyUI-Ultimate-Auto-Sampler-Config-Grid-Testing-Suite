/**
 * EVENT LISTENERS - INCREMENTAL UPDATES
 * Only processes NEW data, doesn't refilter everything
 */

// Track last update to prevent duplicates
let lastUpdateId = 0;

// WebSocket Listener - OPTIMIZED
window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'update_data') {
        const payload = event.data.data;
        if (!payload) return;

        // 1. Handle NEW ITEMS (incremental)
        if (payload.new_items && payload.new_items.length > 0) {
            console.log(`[Events] 📥 Received ${payload.new_items.length} new items`);
            
            if (!fullManifest.items) fullManifest.items = [];
            
            // Add to data source
            fullManifest.items.unshift(...payload.new_items);
            activeData = fullManifest.items;
            

            
            // CRITICAL: Process only new items, don't refilter everything
            refreshIndices();
            
            // Update filter options (but don't rebuild unnecessarily)
            updateFiltersForNewData(payload.new_items);
            
            // INCREMENTAL PROCESSING (much faster!)
            if (typeof processNewData === 'function') {
                processNewData(payload.new_items);
            } else {
                // Fallback to full reprocess if function not available
                updateDataPipeline();
            }
            
            lastUpdateId++;
            return;
        } 
        
        // 2. Handle FULL MANIFEST reload (rare)
        if (payload.manifest) {
            console.log('[Events] 📚 Full manifest reload');
            fullManifest = payload.manifest;
            activeData = fullManifest.items || [];
            meta = payload.meta || {};
            

            
            refreshIndices();
            
            // Full reprocess needed
            updateDataPipeline();
        }
    }
});