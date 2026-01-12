/**
 * INITIALIZATION
 * Runs on startup to bind inputs and start the pipeline.
 */

function init() {
    try {
        // Bind Meta Info
        if (meta.model) document.getElementById('meta-model').innerText = meta.model;
        if (meta.positive) {
            const el = document.getElementById('meta-pos');
            if(el) { el.innerText = meta.positive; el.title = meta.positive; }
        }
        if (meta.negative) {
            const el = document.getElementById('meta-neg');
            if(el) { el.innerText = meta.negative; el.title = meta.negative; }
        }

        // Bind Column Input
        const colInput = document.getElementById('col-count');
        if (colInput) {
            // Load saved column preference
            const savedCols = localStorage.getItem('ultimate_grid_cols');
            if (savedCols) {
                const val = parseInt(savedCols);
                if (val > 0) colInput.value = val;
            }

            // Handle column changes
            colInput.addEventListener('input', (e) => {
                const val = parseInt(e.target.value);
                if (val > 0) {
                    localStorage.setItem('ultimate_grid_cols', val);
                } else {
                    localStorage.removeItem('ultimate_grid_cols');
                }
                
                // Recalculate layout and re-render
                if (typeof recalcColumns === 'function') {
                    recalcColumns();
                }
            });

            colInput.addEventListener('change', (e) => {
                // Trigger full re-render on blur/enter
                const val = parseInt(e.target.value);
                if (val > 0) {
                    localStorage.setItem('ultimate_grid_cols', val);
                } else {
                    localStorage.removeItem('ultimate_grid_cols');
                }
                
                if (typeof recalcColumns === 'function') {
                    recalcColumns();
                }
            });
        }

        // Load sort preference from localStorage
        if (typeof loadSortPreference === 'function') {
            loadSortPreference();
        }

        // Start
        refreshIndices(); 
        
        if(typeof initFilters === 'function') initFilters();
        
        updateDataPipeline();
        
        // Auto-fit zoom after initial render
        setTimeout(() => {
            if (typeof autoFitZoom === 'function') {
                autoFitZoom();
            }
        }, 100);
        
    } catch (e) { 
        console.error("Init Error", e); 
    }
}

// Ensure init fires after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}