/**
 * GLOBAL STATE MANAGEMENT
 * Holds the raw data, layout metrics, and viewport coordinates.
 */

// --- DATA CONTAINERS ---
let activeData = fullManifest.items || [];
let meta = fullManifest.meta || {};

// --- FILTER STATE ---
const filters = { 
    sampler: new Set(), 
    scheduler: new Set(), 
    lora: new Set(), 
    denoise: new Set(), 
    model: new Set() 
};

let currentSort = 'oldest';

// --- VIRTUALIZATION & PIPELINE ---
let processedData = [];
let visibleSlice = { start: -1, end: -1 };
const nodeMap = new Map();
let idToIndexMap = new Map();

// --- LAYOUT METRICS ---
let metrics = { 
    cardWidth: 240,
    cardHeight: 350,
    colCount: 4,
    totalHeight: 0,
    ready: false 
};

// --- VIEWPORT COORDINATES (Legacy - kept for compatibility) ---
let px = 0;
let py = 0;
let s = 1;

// --- RENDER THROTTLING ---
let isRenderPending = false; 
let lastRenderTime = 0;
const RENDER_THROTTLE_MS = 16;

// --- DEBOUNCE TIMER (Prevents rapid re-renders) ---
let updateDebounceTimer = null;