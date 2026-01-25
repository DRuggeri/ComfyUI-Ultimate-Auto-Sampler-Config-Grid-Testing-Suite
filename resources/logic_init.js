/**
 * INITIALIZATION
 * Runs on startup to bind inputs and start the pipeline.
 */

function init() {

    try {


        // Bind Column Input
        const colInput = document.getElementById('col-count');
        if (colInput) {
            // Load saved column preference
            const savedCols = localStorage.getItem('ultimate_grid_cols');
            if (savedCols) {
                const val = parseInt(savedCols);
                if (val > 0) colInput.value = val;
            }

            let colInputTimeout = null;

            colInput.addEventListener('input', (e) => {
                // Clear previous timeout
                if (colInputTimeout) clearTimeout(colInputTimeout);

                // Debounce the recalculation
                colInputTimeout = setTimeout(() => {
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
                }, 600);
            });
        }

        // Load sort preference from localStorage
        if (typeof loadSortPreference === 'function') {
            loadSortPreference();
        }

        // Start
        refreshIndices();

        if (typeof initFilters === 'function') initFilters();

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