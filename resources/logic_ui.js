/**
 * UI COMPONENTS - FIXED LAYOUT
 * Fixed: Index tag z-index, time tag position
 * Added: Favorites feature
 */

// Cache for filter buttons
let filterButtonCache = {};

// Initialize Filter Buttons (with caching)
function initFilters() {
    if (!activeData || activeData.length === 0) return;

    ['model', 'sampler', 'scheduler', 'denoise', 'lora'].forEach(key => {
        const unique = [...new Set(activeData.map(d => {
            if (key === 'model') return d.model || meta.model || "Default";
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
            if (key === 'lora') {
                if (val === "None") label = "None";
                else if (val.includes(" + ")) label = "Stack";
                else {
                    let clean = val.replace(/\\/g, '/').split('/').pop().split(':')[0];
                    label = (clean.length > 12) ? clean.substring(0, 10) + '...' : clean;
                }
            } else if (key === 'model') {
                let clean = val.replace(/\\/g, '/').split('/').pop();
                label = (clean.length > 12) ? clean.substring(0, 10) + '...' : clean;
            }

            b.innerText = label;
            b.title = val;

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

// Toggle Favorite
function toggleFavorite(id) {
    const item = activeData.find(d => d.id === id);
    if (!item) return;
    
    item.favorited = !item.favorited;
    
    // Update the button in DOM
    const card = document.getElementById(`card-${id}`);
    if (card) {
        const favBtn = card.querySelector('.favorite-btn');
        if (favBtn) {
            if (item.favorited) {
                favBtn.classList.add('favorited');
                favBtn.innerText = '★';
            } else {
                favBtn.classList.remove('favorited');
                favBtn.innerText = '☆';
            }
        }
    }
    
    // Update JSON bars
    updateJSONs(processedData);
    
    // Save state
    if (typeof saveState === 'function') {
        saveState();
    }
}

// Create card - FIXED UI LAYOUT WITH FAVORITE BUTTON
function createCard(d) {
    const totalIndex = idToIndexMap.get(d.id) || 0;
    const card = document.createElement('div');
    card.className = 'card';
    card.id = `card-${d.id}`;
    card.dataset.id = d.id;

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
        loraLine = `<div class="stat" title="${d.lora.replace(/ \+ /g, '\n')}"><b>LoRA:</b> <span style="color:var(--accent-lora)">Stack (${count})</span></div>`;
    } else {
        const rawName = String(d.lora);
        let fileName = rawName.replace(/\\/g, '/').split('/').pop().split(':')[0];
        if (fileName.length > 20) fileName = fileName.substring(0, 18) + '...';
        loraLine = `<div class="stat" title="${d.lora}"><b>LoRA:</b> <span>${fileName}</span></div>`;
    }

    let promptInfo = "";
    if (meta.positive === "Multiple") {
        const shortPrompt = d.positive ? d.positive.substring(0, 20) : "";
        promptInfo = `<div class="stat" title="${d.positive || ''}"><b>Pos:</b> ${shortPrompt}...</div>`;
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
            <img data-src="${d.file}" alt="Image ${d.id}" draggable="false">
            <button class="reject-btn" onclick="rejectItem(${d.id})">✕</button>
            <button class="favorite-btn ${favClass}" onclick="toggleFavorite(${d.id})">${favIcon}</button>
            <button class="revise-btn" onclick="openM(${d.id})">REVISE</button>
            <div class="time-tag">${d.duration}s</div>
            <div class="index-tag">#${totalIndex}</div>
        </div>
        <div class="info">
            <div class="stat"><b>Smp:</b> <span>${d.sampler} / ${d.scheduler}</span></div>
            <div class="stat">
                <b>Cfg:</b> ${d.cfg} &nbsp; <b>Stp:</b> ${d.steps} &nbsp; <b>Dn:</b> <span style="color:var(--accent-denoise)">${d.denoise}</span>
            </div>
            <div class="stat" title="${modelName}"><b>Model:</b> <span>${finalModel}</span></div>
            ${loraLine}
            ${promptInfo}
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
        generateSmartJSON(visible, 'json-bar-good');
        const favorited = activeData.filter(d => d.favorited && !d.rejected);
        generateSmartJSON(favorited, 'json-bar-favorite');
        const rejected = activeData.filter(d => d.rejected);
        generateSmartJSON(rejected, 'json-bar-bad');
    }, 300);
}

// OPTIMIZED JSON generation
function generateSmartJSON(dataset, targetId) {
    const el = document.getElementById(targetId);
    if (!el) return;
    
    if (dataset.length === 0) { 
        el.innerText = "[]"; 
        return; 
    }

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