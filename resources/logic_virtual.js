/**
 * TRUE VIRTUAL SCROLL - ZERO FLICKER
 * With full keyboard navigation support
 */

// --- VIRTUAL WINDOW STATE ---
let visibleRange = { start: 0, end: 50 };
const MAX_VISIBLE_ITEMS = 50;
let updateTimeout = null;

// --- PAN/ZOOM STATE ---
let currentScale = 1;
const MIN_SCALE = 0.1;
const MAX_SCALE = 10;
let isPanning = false;
let isMiddleMousePanning = false;
let panStartX = 0;
let panStartY = 0;
let panOffsetX = 0;
let panOffsetY = 0;

// --- GRID METRICS ---
let itemHeight = 400;
let itemWidth = 260;
let columnsCount = 4;
let rowHeight = 410;

// --- LAZY LOADING ---
const imageObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src && !img.src) {
                img.src = img.dataset.src;
                img.onload = () => img.style.opacity = '1';
                imageObserver.unobserve(img);
            }
        }
    });
}, { rootMargin: '400px' });

// --- CALCULATE VISIBLE RANGE ---
function calculateVisibleRange() {
    const viewport = document.getElementById('viewport');
    if (!viewport) return visibleRange;

    const effectiveScrollTop = (-panOffsetY / currentScale);
    const viewportHeight = viewport.clientHeight / currentScale;

    const firstVisibleRow = Math.floor(effectiveScrollTop / rowHeight);
    const lastVisibleRow = Math.ceil((effectiveScrollTop + viewportHeight) / rowHeight);

    const bufferRows = 3;
    const startRow = Math.max(0, firstVisibleRow - bufferRows);
    const endRow = lastVisibleRow + bufferRows;

    const start = startRow * columnsCount;
    const end = Math.min(processedData.length, endRow * columnsCount);

    return { start, end };
}

// --- FORCE VISIBLE RANGE UPDATE (for prepended items) ---
function forceVisibleRangeUpdate(prependedCount) {
    console.log(`[Grid] 🔝 ${prependedCount} items prepended - recalculating ALL positions`);

    const effectiveScrollTop = (-panOffsetY / currentScale);

    if (effectiveScrollTop < rowHeight * 5) {
        const newItemRows = Math.ceil(prependedCount / columnsCount);
        const additionalItems = newItemRows * columnsCount;

        visibleRange.start = 0;
        visibleRange.end = Math.min(
            processedData.length,
            visibleRange.end + additionalItems
        );

        console.log(`[Grid] Expanded visible range: ${visibleRange.start}-${visibleRange.end}`);
    }

    renderVisibleItems(true);
}

// --- UPDATE VISIBLE ITEMS ---
function updateVisibleItems() {
    const newRange = calculateVisibleRange();

    if (newRange.start === visibleRange.start && newRange.end === visibleRange.end) {
        const grid = document.getElementById('grid');
        if (grid && processedData.length > 0) {
            const totalRows = Math.ceil(processedData.length / columnsCount);
            const totalHeight = totalRows * rowHeight;
            if (grid.style.height !== `${totalHeight}px`) {
                grid.style.height = `${totalHeight}px`;
            }
        }
        return;
    }

    visibleRange = newRange;
    renderVisibleItems();
}

function scheduleVisibleUpdate() {
    if (updateTimeout) {
        clearTimeout(updateTimeout);
    }

    updateTimeout = setTimeout(() => {
        updateVisibleItems();
    }, 100);
}

// --- RENDER VISIBLE ITEMS ---
function renderVisibleItems(forcePositionUpdate = false) {
    const grid = document.getElementById('grid');
    if (!grid || !processedData || processedData.length === 0) return;

    const totalRows = Math.ceil(processedData.length / columnsCount);
    const totalHeight = totalRows * rowHeight;
    grid.style.height = `${totalHeight}px`;

    const itemsToShow = processedData.slice(visibleRange.start, visibleRange.end);
    const visibleIds = new Set(itemsToShow.map(item => item.id));

    const toRemove = [];
    for (const [id, node] of nodeMap) {
        if (!visibleIds.has(id)) {
            toRemove.push(id);
        }
    }

    toRemove.forEach(id => {
        const node = nodeMap.get(id);
        if (node && node.parentNode) {
            node.remove();
        }
        nodeMap.delete(id);
    });

    const fragment = document.createDocumentFragment();
    let newCardsAdded = 0;
    let positionsUpdated = 0;

    itemsToShow.forEach((data, offsetIndex) => {
        const globalIndex = visibleRange.start + offsetIndex;

        const row = Math.floor(globalIndex / columnsCount);
        const col = globalIndex % columnsCount;
        const x = col * itemWidth;
        const y = row * rowHeight;

        let card = nodeMap.get(data.id);

        if (!card) {
            card = createCard(data);
            card.style.position = 'absolute';
            card.style.left = `${x}px`;
            card.style.top = `${y}px`;
            card.style.width = `${itemWidth - 10}px`;
            card.style.zIndex = globalIndex;

            nodeMap.set(data.id, card);
            fragment.appendChild(card);
            newCardsAdded++;

            const img = card.querySelector('img[data-src]');
            if (img) imageObserver.observe(img);
        } else {
            const currentLeft = parseInt(card.style.left) || 0;
            const currentTop = parseInt(card.style.top) || 0;
            const currentZIndex = parseInt(card.style.zIndex) || 0;

            if (forcePositionUpdate || currentLeft !== x || currentTop !== y || currentZIndex !== globalIndex) {
                card.style.left = `${x}px`;
                card.style.top = `${y}px`;
                card.style.zIndex = globalIndex;
                positionsUpdated++;
            }
        }
    });

    if (fragment.childNodes.length > 0) {
        grid.appendChild(fragment);
    }

    if (forcePositionUpdate) {
        console.log(`[Grid] Added ${newCardsAdded} new, repositioned ${positionsUpdated} existing cards`);
    } else if (newCardsAdded > 0) {
        console.log(`[Grid] Added ${newCardsAdded} new cards, kept ${nodeMap.size - newCardsAdded} existing`);
    }

    viewport.focus();
    viewport.setAttribute('tabindex', '0');
}

// --- RECALCULATE LAYOUT ---
function recalculateLayout() {
    const viewport = document.getElementById('viewport');
    if (!viewport) return;

    const colInput = document.getElementById('col-count');
    const manualCols = colInput ? parseInt(colInput.value) : 0;

    const oldColCount = columnsCount;

    if (manualCols > 0) {
        columnsCount = manualCols;
    } else {
        const viewportWidth = viewport.clientWidth;
        columnsCount = Math.max(1, Math.floor(viewportWidth / itemWidth));
    }

    if (oldColCount !== columnsCount) {
        console.log(`[Grid] Column count changed: ${oldColCount} → ${columnsCount}, triggering re-render`);
        renderDOM();
    }
}

// --- MAIN RENDER ---
function renderDOM() {
    const grid = document.getElementById('grid');
    if (!grid) return;

    console.log('[Grid] 🔄 Full re-render');

    grid.innerHTML = '';
    nodeMap.clear();

    recalculateLayout();

    visibleRange = { start: 0, end: Math.min(MAX_VISIBLE_ITEMS, processedData.length) };
    renderVisibleItems();

    viewport.focus();
    viewport.setAttribute('tabindex', '0');
}

// --- PAN/ZOOM CONTROLS ---
const canvas = document.getElementById('canvas');
const viewport = document.getElementById('viewport');

function updateTransform() {
    if (!canvas) return;
    canvas.style.transform = `translate(${panOffsetX}px, ${panOffsetY}px) scale(${currentScale})`;
    scheduleVisibleUpdate();
}

function getZoomDelta() {
    if (currentScale < 0.5) return 0.05;
    else if (currentScale < 1) return 0.15;
    else if (currentScale < 3) return 0.3;
    else if (currentScale < 6) return 0.5;
    else return 0.8;
}

function updateZoom(delta, mouseX, mouseY) {
    if (!canvas || !viewport) return;

    const oldScale = currentScale;
    const adaptiveDelta = delta > 0 ? getZoomDelta() : -getZoomDelta();
    currentScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, currentScale + adaptiveDelta));

    if (oldScale === currentScale) return;

    const rect = viewport.getBoundingClientRect();
    const offsetX = mouseX - rect.left;
    const offsetY = mouseY - rect.top;

    const scaleFactor = currentScale / oldScale;
    panOffsetX = offsetX - (offsetX - panOffsetX) * scaleFactor;
    panOffsetY = offsetY - (offsetY - panOffsetY) * scaleFactor;

    updateTransform();
}

function zoomIn() {
    if (!viewport) return;
    updateZoom(1, viewport.clientWidth / 2, viewport.clientHeight / 2);
}

function zoomOut() {
    if (!viewport) return;
    updateZoom(-1, viewport.clientWidth / 2, viewport.clientHeight / 2);
}

function resetZoom() {
    if (!canvas || !viewport) return;
    currentScale = 1;
    panOffsetX = 0;
    panOffsetY = 0;
    updateTransform();
}

// --- AUTO-FIT ZOOM: Fit first row perfectly in viewport ---
function autoFitZoom() {
    if (!canvas || !viewport || !processedData || processedData.length === 0) {
        console.log('[Grid] Cannot auto-fit: missing data or viewport');
        return;
    }

    // Only fit the first row horizontally
    const totalWidth = columnsCount * itemWidth;
    const viewportWidth = viewport.clientWidth;

    // Calculate scale to fit width
    const targetScale = (viewportWidth / totalWidth) * 0.98; // 95% to add small padding

    // Clamp to min/max
    currentScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, targetScale));

    // Center horizontally, position at top
    const scaledWidth = totalWidth * currentScale;

    panOffsetX = (viewportWidth - scaledWidth) / 2;
    panOffsetY = 20; // Small top margin

    updateTransform();
    
    console.log(`[Grid] 🎯 Auto-fit first row: ${columnsCount} columns, scale: ${currentScale.toFixed(2)}`);
}

// --- MOUSE CONTROLS ---
if (viewport) {
    viewport.addEventListener('mousedown', (e) => {
        viewport.focus();
        viewport.setAttribute('tabindex', '0');
        if (e.button === 0) {
            isPanning = true;
            panStartX = e.clientX - panOffsetX;
            panStartY = e.clientY - panOffsetY;
            viewport.style.cursor = 'grabbing';
            e.preventDefault();
        } else if (e.button === 1) {
            isMiddleMousePanning = true;
            panStartX = e.clientX - panOffsetX;
            panStartY = e.clientY - panOffsetY;
            viewport.style.cursor = 'grabbing';
            e.preventDefault();
        }
    });

    window.addEventListener('mouseup', (e) => {
        if (e.button === 0 && isPanning) {
            isPanning = false;
            if (viewport) viewport.style.cursor = 'grab';
        } else if (e.button === 1 && isMiddleMousePanning) {
            isMiddleMousePanning = false;
            if (viewport) viewport.style.cursor = 'grab';
        }
    });

    window.addEventListener('mousemove', (e) => {
        if (!isPanning && !isMiddleMousePanning) return;
        e.preventDefault();

        panOffsetX = e.clientX - panStartX;
        panOffsetY = e.clientY - panStartY;
        updateTransform();
    });

    viewport.addEventListener('wheel', (e) => {
        e.preventDefault();
        updateZoom(e.deltaY > 0 ? -1 : 1, e.clientX, e.clientY);
    }, { passive: false });

    viewport.addEventListener('contextmenu', (e) => {
        if (e.button === 1) e.preventDefault();
    });
}

// --- RESIZE OBSERVER ---
const resizeObserver = new ResizeObserver(() => {
    recalculateLayout();
    autoFitZoom();
});

if (viewport) {
    resizeObserver.observe(viewport);
}

// --- KEYBOARD SHORTCUTS ---
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        switch(e.key) {
            case '+':
            case '=':
                e.preventDefault();
                zoomIn();
                break;
            case '-':
            case '_':
                e.preventDefault();
                zoomOut();
                break;
            case '0':
                e.preventDefault();
                resetZoom();
                autoFitZoom();
                break;
            case 'f':
            case 'F':
                e.preventDefault();
                autoFitZoom();
                break;
            case ' ': // Spacebar - scroll by one row
                e.preventDefault();
                const rowScroll = rowHeight * currentScale;
                if (e.shiftKey) {
                    // Shift+Space = scroll up
                    panOffsetY += rowScroll;
                } else {
                    // Space = scroll down
                    panOffsetY -= rowScroll;
                }
                updateTransform();
                updateVisibleItems(); // IMMEDIATE update instead of scheduled
                break;
            case 'ArrowUp':
                e.preventDefault();
                panOffsetY += 100;
                updateTransform();
                updateVisibleItems(); // IMMEDIATE update instead of scheduled
                break;
            case 'ArrowDown':
                e.preventDefault();
                panOffsetY -= 100;
                updateTransform();
                updateVisibleItems(); // IMMEDIATE update instead of scheduled
                break;
            case 'ArrowLeft':
                e.preventDefault();
                panOffsetX += 100;
                updateTransform();
                updateVisibleItems(); // IMMEDIATE update instead of scheduled
                break;
            case 'ArrowRight':
                e.preventDefault();
                panOffsetX -= 100;
                updateTransform();
                updateVisibleItems(); // IMMEDIATE update instead of scheduled
                break;
        }
    });
};

// --- LEGACY COMPATIBILITY ---
function measureGridItem() {
    metrics.ready = true;
    renderDOM();
}

function recalcColumns() {
    recalculateLayout();
    autoFitZoom();
}

function updateVirtualWindow(force = false) {
    if (force) renderDOM();
}

function scheduleRender() {
    renderDOM();
}

function onDataAdded() {
    renderDOM();
}

// Expose functions
window.zoomIn = zoomIn;
window.zoomOut = zoomOut;
window.resetZoom = resetZoom;
window.autoFitZoom = autoFitZoom;
window.updateVisibleItems = updateVisibleItems;
window.forceVisibleRangeUpdate = forceVisibleRangeUpdate;
setupKeyboardShortcuts();