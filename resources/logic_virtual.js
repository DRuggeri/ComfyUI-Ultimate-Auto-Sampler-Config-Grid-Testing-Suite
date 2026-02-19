/**
 * TRUE VIRTUAL SCROLL - ZERO FLICKER
 * With full keyboard navigation support and AUTO-CALCULATED DIMENSIONS
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

// --- GRID METRICS (Auto-calculated from image data) ---
let itemHeight = 420;  // Will be auto-calculated
let itemWidth = 260;   // Will be auto-calculated
let columnsCount = 4;
let rowHeight = 370;   // Will be auto-calculated

// --- DIMENSION CALCULATION CONSTANTS ---
const CARD_PADDING = 10;           // Space between cards
const CARD_METADATA_HEIGHT = 50;   // Height of the metadata/button area below image
const ASPECT_RATIO_FALLBACK = 2/3; // Default aspect ratio if no images loaded (portrait)
const MIN_CARD_WIDTH = 150;        // Minimum card width
const MAX_CARD_WIDTH = 500;        // Maximum card width

/**
 * Calculate optimal grid dimensions based on image aspect ratios
 * This runs once when data is loaded or when images change
 */
function calculateGridDimensions() {
    // Use activeData (all items) for dimension sampling, not processedData (filtered/sorted)
    // This prevents dimension changes when filters/sorts change
    const sourceData = (activeData && activeData.length > 0) ? activeData : processedData;
    if (!sourceData || sourceData.length === 0) {
        console.log('[Grid Dimensions] No data available, using defaults');
        return;
    }

    // Sample up to 50 images evenly distributed across the dataset for a representative average
    const totalItems = sourceData.length;
    const sampleSize = Math.min(50, totalItems);
    const step = Math.max(1, Math.floor(totalItems / sampleSize));
    let totalAspectRatio = 0;
    let validSamples = 0;

    for (let i = 0; i < totalItems && validSamples < sampleSize; i += step) {
        const item = sourceData[i];
        if (item.width && item.height && item.width > 0 && item.height > 0) {
            totalAspectRatio += item.width / item.height;
            validSamples++;
        }
    }

    // Calculate average aspect ratio
    const avgAspectRatio = validSamples > 0 
        ? totalAspectRatio / validSamples 
        : ASPECT_RATIO_FALLBACK;

    // Get viewport width to determine optimal card width
    const viewport = document.getElementById('viewport');
    const viewportWidth = viewport ? viewport.clientWidth : 1200;

    // Calculate column count based on viewport and desired card size
    const colInput = document.getElementById('col-count');
    const manualCols = colInput ? parseInt(colInput.value) : 0;
    
    if (manualCols > 0) {
        columnsCount = manualCols;
        // Calculate card width to fit columns
        itemWidth = Math.max(MIN_CARD_WIDTH, 
            Math.min(MAX_CARD_WIDTH, 
                Math.floor((viewportWidth - (columnsCount * CARD_PADDING)) / columnsCount)
            )
        );
    } else {
        // Auto-calculate optimal card width (aim for ~250px base width)
        const targetCardWidth = 250;
        columnsCount = Math.max(1, Math.floor(viewportWidth / (targetCardWidth + CARD_PADDING)));
        itemWidth = Math.floor((viewportWidth - (columnsCount * CARD_PADDING)) / columnsCount);
        itemWidth = Math.max(MIN_CARD_WIDTH, Math.min(MAX_CARD_WIDTH, itemWidth));
    }

    // Calculate item height based on aspect ratio and card width
    const imageWidth = itemWidth - CARD_PADDING;
    const imageHeight = Math.floor(imageWidth / avgAspectRatio);
    itemHeight = imageHeight + CARD_METADATA_HEIGHT + CARD_PADDING;

    // Row height is slightly less than item height for tighter packing
    rowHeight = itemHeight - 50;

    console.log(`[Grid Dimensions] Auto-calculated:`);
    console.log(`  - Avg Aspect Ratio: ${avgAspectRatio.toFixed(3)} (from ${validSamples} samples)`);
    console.log(`  - Columns: ${columnsCount}`);
    console.log(`  - Item Width: ${itemWidth}px`);
    console.log(`  - Item Height: ${itemHeight}px`);
    console.log(`  - Row Height: ${rowHeight}px`);
    console.log(`  - Image dimensions: ${imageWidth}x${imageHeight}px`);
}

/**
 * Recalculate dimensions when data changes
 * Call this after processedData is updated
 */
function updateGridDimensions() {
    calculateGridDimensions();
    
    // Force a full re-render with new dimensions
    if (processedData && processedData.length > 0) {
        renderDOM();
    }
}

// Expose for external use
window.updateGridDimensions = updateGridDimensions;

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
        const genOrderNumber = idToIndexMap.get(data.id) || (globalIndex + 1); // Generation order number (backwards-compatible)

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

            // Update card number to reflect generation order
            const indexTag = card.querySelector('.index-tag');
            if (indexTag) indexTag.textContent = `#${genOrderNumber}`;

            nodeMap.set(data.id, card);
            fragment.appendChild(card);
            newCardsAdded++;

            const img = card.querySelector('img[data-src]');
            if (img && !img.src) {
                img.src = img.dataset.src;
                img.onload = () => img.style.opacity = '1';
            }

        } else {
            const currentLeft = parseInt(card.style.left) || 0;
            const currentTop = parseInt(card.style.top) || 0;
            const currentZIndex = parseInt(card.style.zIndex) || 0;

            if (forcePositionUpdate || currentLeft !== x || currentTop !== y || currentZIndex !== globalIndex) {
                card.style.left = `${x}px`;
                card.style.top = `${y}px`;
                card.style.zIndex = globalIndex;
                positionsUpdated++;

                // Update card number when position changes (sort/filter changed)
                const indexTag = card.querySelector('.index-tag');
                if (indexTag) indexTag.textContent = `#${genOrderNumber}`;
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

    const oldColCount = columnsCount;
    const oldItemWidth = itemWidth;
    const oldItemHeight = itemHeight;

    // Recalculate dimensions based on current viewport and data
    calculateGridDimensions();

    if (oldColCount !== columnsCount || oldItemWidth !== itemWidth || oldItemHeight !== itemHeight) {
        console.log(`[Grid] Layout changed: cols ${oldColCount}→${columnsCount}, w ${oldItemWidth}→${itemWidth}, h ${oldItemHeight}→${itemHeight}`);
        renderDOM();
    }
}

// --- MAIN RENDER ---
let isRendering = false; // Guard against recursive renderDOM calls
function renderDOM() {
    if (isRendering) return; // Prevent recursive calls from recalculateLayout
    isRendering = true;

    const grid = document.getElementById('grid');
    if (!grid) { isRendering = false; return; }

    console.log('[Grid] 🔄 Full re-render');

    grid.innerHTML = '';
    nodeMap.clear();

    // Recalculate dimensions (may change columnsCount)
    calculateGridDimensions();

    // Calculate visible range from current viewport position instead of resetting to 0
    visibleRange = calculateVisibleRange();
    // Ensure we have a reasonable range even if viewport position is at origin
    if (visibleRange.end <= visibleRange.start) {
        visibleRange = { start: 0, end: Math.min(MAX_VISIBLE_ITEMS, processedData.length) };
    }
    renderVisibleItems();

    viewport.focus();
    viewport.setAttribute('tabindex', '0');

    isRendering = false;
}

// --- PAN/ZOOM CONTROLS ---
const canvas = document.getElementById('canvas');
const viewport = document.getElementById('viewport');

function updateTransform() {
    if (!canvas) return;
    canvas.style.transform = `translate(${panOffsetX}px, ${panOffsetY}px) scale(${currentScale})`;
    scheduleVisibleUpdate();
    // Auto-save viewport position on any pan/zoom change
    if (typeof scheduleViewportSave === 'function') scheduleViewportSave();
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
    autoFitZoom();
}

function autoFitZoom() {
    if (!canvas || !viewport || !processedData || processedData.length === 0) {
        console.log('[Grid] Cannot auto-fit: missing data or viewport');
        return;
    }

    const totalWidth = columnsCount * itemWidth;
    const viewportWidth = viewport.clientWidth;

    const targetScale = (viewportWidth / totalWidth) * 0.95;
    currentScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, targetScale));

    const scaledWidth = totalWidth * currentScale;
    panOffsetX = (viewportWidth - scaledWidth) / 2;
    panOffsetY = 20;

    updateTransform();

    console.log(`[Grid] 🎯 Auto-fit first row: ${columnsCount} columns, scale: ${currentScale.toFixed(2)}`);
}

function goToImage(imageNumber) {
    if (!processedData || processedData.length === 0) {
        console.log('[Grid] No data to navigate');
        return;
    }

    let targetItem = null;
    let targetIndex = -1;

    // Card numbers reflect sorted position (1-based), so #N = processedData[N-1]
    if (imageNumber >= 1 && imageNumber <= processedData.length) {
        targetIndex = imageNumber - 1;
        targetItem = processedData[targetIndex];
    }

    if (!targetItem || targetIndex === -1) {
        console.log(`[Grid] Image #${imageNumber} not found`);
        alert(`Image #${imageNumber} not found in current view (${processedData.length} items visible)`);
        return;
    }

    const row = Math.floor(targetIndex / columnsCount);
    const col = targetIndex % columnsCount;
    const x = col * itemWidth;
    const y = row * rowHeight;

    const viewportWidth = viewport.clientWidth;
    const viewportHeight = viewport.clientHeight;

    panOffsetY = (viewportHeight / 2) - (y * currentScale) - ((rowHeight * currentScale) / 2);

    updateTransform();
    updateVisibleItems();

    setTimeout(() => {
        const card = document.getElementById(`card-${targetItem.id}`);
        if (card) {
            card.style.transition = 'box-shadow 0.3s, border-color 0.3s';
            card.style.boxShadow = '0 0 30px rgba(0, 209, 178, 0.8)';
            card.style.borderColor = 'var(--accent)';

            setTimeout(() => {
                card.style.boxShadow = '';
                card.style.borderColor = '';
            }, 2000);
        }
    }, 200);

    console.log(`[Grid] 📍 Navigated to image #${imageNumber} at position (${row}, ${col})`);
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

    // --- TOUCH CONTROLS FOR MOBILE ---
    let touchStartDistance = 0;
    let touchStartScale = 1;
    let isTouching = false;
    let touchStartX = 0;
    let touchStartY = 0;
    let wasZooming = false;

    viewport.addEventListener('touchstart', (e) => {
        viewport.focus();
        viewport.setAttribute('tabindex', '0');

        if (e.touches.length === 1) {
            isTouching = true;
            const touch = e.touches[0];
            touchStartX = touch.clientX - panOffsetX;
            touchStartY = touch.clientY - panOffsetY;
        } else if (e.touches.length === 2) {
            e.preventDefault();
            wasZooming = true;
            const touch1 = e.touches[0];
            const touch2 = e.touches[1];
            touchStartDistance = Math.hypot(
                touch2.clientX - touch1.clientX,
                touch2.clientY - touch1.clientY
            );
            touchStartScale = currentScale;
        }
    }, { passive: false });

    viewport.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1 && isTouching) {
            if (wasZooming) {
                const touch = e.touches[0];
                touchStartX = touch.clientX - panOffsetX;
                touchStartY = touch.clientY - panOffsetY;
                wasZooming = false;
                return;
            }

            e.preventDefault();
            const touch = e.touches[0];
            panOffsetX = touch.clientX - touchStartX;
            panOffsetY = touch.clientY - touchStartY;
            updateTransform();
        } else if (e.touches.length === 2) {
            e.preventDefault();
            const touch1 = e.touches[0];
            const touch2 = e.touches[1];

            const currentDistance = Math.hypot(
                touch2.clientX - touch1.clientX,
                touch2.clientY - touch1.clientY
            );

            const centerX = (touch1.clientX + touch2.clientX) / 2;
            const centerY = (touch1.clientY + touch2.clientY) / 2;

            const scaleChange = currentDistance / touchStartDistance;
            const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, touchStartScale * scaleChange));

            if (newScale !== currentScale) {
                const rect = viewport.getBoundingClientRect();
                const offsetX = centerX - rect.left;
                const offsetY = centerY - rect.top;

                const scaleFactor = newScale / currentScale;
                panOffsetX = offsetX - (offsetX - panOffsetX) * scaleFactor;
                panOffsetY = offsetY - (offsetY - panOffsetY) * scaleFactor;
                currentScale = newScale;

                updateTransform();
            }
        }
    }, { passive: false });

    viewport.addEventListener('touchend', (e) => {
        if (e.touches.length === 0) {
            isTouching = false;
            wasZooming = false;
        }
        if (e.touches.length < 2) {
            touchStartDistance = 0;
        }
    });
}

// --- RESIZE OBSERVER ---
const resizeObserver = new ResizeObserver(() => {
    recalculateLayout();
});

if (viewport) {
    resizeObserver.observe(viewport);
}

// --- KEYBOARD SHORTCUTS ---
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        switch (e.key) {
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
                autoFitZoom();
                break;
            case ' ':
                e.preventDefault();
                const rowScroll = rowHeight * currentScale;
                if (e.shiftKey) {
                    panOffsetY += rowScroll;
                } else {
                    panOffsetY -= rowScroll;
                }
                updateTransform();
                updateVisibleItems();
                break;
            case 'ArrowUp':
                e.preventDefault();
                panOffsetY += 100;
                updateTransform();
                updateVisibleItems();
                break;
            case 'ArrowDown':
                e.preventDefault();
                panOffsetY -= 100;
                updateTransform();
                updateVisibleItems();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                panOffsetX += 100;
                updateTransform();
                updateVisibleItems();
                break;
            case 'ArrowRight':
                e.preventDefault();
                panOffsetX -= 100;
                updateTransform();
                updateVisibleItems();
                break;
        }
    });
}

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

// --- VIEWPORT POSITION PERSISTENCE ---
// Save viewport position to localStorage for persistence across fullscreen toggles and reloads
function saveViewportPosition() {
    try {
        const sessInput = document.getElementById('session-input');
        const sessionKey = sessInput ? sessInput.value : 'default';
        const state = {
            panOffsetX: panOffsetX,
            panOffsetY: panOffsetY,
            currentScale: currentScale,
            timestamp: Date.now()
        };
        localStorage.setItem(`ultimate_grid_viewport_${sessionKey}`, JSON.stringify(state));
    } catch (e) {
        console.warn('[Viewport] Failed to save position:', e);
    }
}

// Restore viewport position from localStorage
// Returns true if position was restored, false otherwise
function restoreViewportPosition() {
    try {
        const sessInput = document.getElementById('session-input');
        const sessionKey = sessInput ? sessInput.value : 'default';
        const saved = localStorage.getItem(`ultimate_grid_viewport_${sessionKey}`);
        if (!saved) return false;

        const state = JSON.parse(saved);

        // Only restore if saved within the last 24 hours
        if (Date.now() - state.timestamp > 24 * 60 * 60 * 1000) {
            localStorage.removeItem(`ultimate_grid_viewport_${sessionKey}`);
            return false;
        }

        panOffsetX = state.panOffsetX;
        panOffsetY = state.panOffsetY;
        currentScale = state.currentScale;

        updateTransform();
        updateVisibleItems();

        console.log(`[Viewport] Restored position: panX=${panOffsetX.toFixed(0)}, panY=${panOffsetY.toFixed(0)}, scale=${currentScale.toFixed(2)}`);
        return true;
    } catch (e) {
        console.warn('[Viewport] Failed to restore position:', e);
        return false;
    }
}

// Auto-save viewport position periodically during interaction
let viewportSaveTimer = null;
function scheduleViewportSave() {
    if (viewportSaveTimer) clearTimeout(viewportSaveTimer);
    viewportSaveTimer = setTimeout(saveViewportPosition, 500);
}

// Hook into updateTransform to auto-save position on pan/zoom changes
const _originalUpdateTransform = updateTransform;
// We can't reassign updateTransform since it's used by reference, so we hook via the scheduleVisibleUpdate path
// Instead, add save scheduling to mouse/touch/keyboard interactions

// Expose functions
window.zoomIn = zoomIn;
window.zoomOut = zoomOut;
window.resetZoom = resetZoom;
window.autoFitZoom = autoFitZoom;
window.goToImage = goToImage;
window.updateVisibleItems = updateVisibleItems;
window.forceVisibleRangeUpdate = forceVisibleRangeUpdate;
window.saveViewportPosition = saveViewportPosition;
window.restoreViewportPosition = restoreViewportPosition;

// --- MOBILE NAVIGATION FUNCTIONS ---
function scrollDownOneRow() {
    const rowScroll = rowHeight * currentScale;
    panOffsetY -= rowScroll;
    updateTransform();
    updateVisibleItems();
}

function scrollUpOneRow() {
    const rowScroll = rowHeight * currentScale;
    panOffsetY += rowScroll;
    updateTransform();
    updateVisibleItems();
}

// Expose mobile navigation functions
window.scrollDownOneRow = scrollDownOneRow;
window.scrollUpOneRow = scrollUpOneRow;

// Initialize keyboard shortcuts immediately
setupKeyboardShortcuts();

// Set up Go To Image input handler
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupGoToInput);
} else {
    setupGoToInput();
}

function setupGoToInput() {
    const gotoInput = document.getElementById('goto-input');
    if (gotoInput) {
        gotoInput.addEventListener('blur', () => {
            const imageNum = parseInt(gotoInput.value);
            if (imageNum && imageNum > 0) {
                goToImage(imageNum);
                gotoInput.value = '';
            }
        });

        gotoInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                gotoInput.blur();
            }
        });
    }
}