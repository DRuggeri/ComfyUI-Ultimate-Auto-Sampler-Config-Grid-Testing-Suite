# ComfyUI Ultimate Auto Sampler Config Grid Testing Suite

<br>
Want to support development of this project? Buy me a coffee on Ko-fi:
<br><br>
<a href="https://ko-fi.com/jasonhoku" target="_blank">
  <img src="https://storage.ko-fi.com/cdn/brandasset/kofi_button_blue.png" alt="Support Me on Ko-fi" height="41">
</a>
<br><br>


**A professional-grade benchmarking and "IDE-like" testing suite for ComfyUI.**

Stop guessing which Sampler, Scheduler, Prompt, Denoise, Model, Lora or CFG value works best. This custom node suite allows you to generate massive Cartesian product grids, view them in an interactive infinite-canvas dashboard, and refine your settings with a "Revise & Generate" workflow without ever leaving the interface.


<img width="1856" height="1030" alt="image" src="https://github.com/user-attachments/assets/e1d57553-80a8-4058-aea5-455e6bfbdf8a" />

---

## 🌟 Key Features

### 🚀 Powerful Grid Generation
* **Cartesian Product Engine:** Automatically generates every permutation of your input settings. Test unlimited Samplers, Schedulers, CFG scales, Sizes, Prompts, LoRA combinations all in one go.
* **Non-Standard Model Support:** Full support for SD3, Flux, Z-Image, and other non-standard architectures with automatic latent channel detection.
* **Multi-Model Support:** Test multiple checkpoints in a single run by passing an array of model names or folder paths.
* **Model Folder Expansion:** Use `"model": "FolderName/"` to test all checkpoints in a folder automatically - perfect for comparing different versions or architectures.
* **CLIP Skip Support:** Control which CLIP layer to use for text encoding with the `clip_skip` parameter - essential for anime models (typically -2) vs realistic models (typically 0).
* **Intelligent CLIP Encoding:** Automatically detects when multiple models are used and handles CLIP encoding correctly per-model to ensure accurate results.
* **Batch Encoding on Model Switch:** When switching between models, all prompts are batch-encoded at once rather than per-generation, resulting in 3-6x faster encoding for multi-model workflows.
* **Multi-LoRA Stacking:** Layer multiple LoRAs with custom strengths using the `+` separator. Supports folder expansion for testing entire LoRA directories.
* **LoRA Trigger Word Filtering:** Use `lora_omit_triggers` to exclude specific trigger words from auto-appended LoRA triggers, giving you fine control over prompts.
* **Random LoRA Selection:** Randomly select LoRAs from folders with `[count,strength]` or `[count,strength,random]` syntax. Supports both reproducible (seed-based) and truly random selection modes.
* **Auto LoRA Trigger Words:** Automatically fetches and appends LoRA trigger words from CivitAI API using SHA256 hash lookup. Results are cached locally for offline use.
* **Multi-Seed Generation:** Add extra random variations per config with the `add_random_seeds_to_gens` parameter - perfect for evaluating consistency.
* **Smart Caching:** Intelligently skips model and LoRA reloading when consecutive runs share the same resources, making generation instant for parameter tweaks.
* **Stop & Resume:** Intelligent skip detection - if you stop a generation mid-run, resuming will skip already-generated images and continue where you left off.
* **Advanced Skip Logic:** Uses conditioning tensor hashing to detect prompt changes even when using pre-encoded conditioning from CLIP nodes.
* **LoRA Compatibility Detection:** Automatically detects and skips incompatible LoRAs with detailed error reporting, preventing log spam.
* **Graceful Interruption:** Cancel button now stops ALL remaining jobs (not just current generation) and saves all completed work including pending remote VAE decodes.
* **VAE Batching:** Includes a `vae_batch_size` input to batch decode images, significantly speeding up large grid runs.
* **Live Dashboard Updates:** Configure `flush_batch_every` to update the dashboard incrementally (e.g., every 4 images) instead of waiting for the entire batch to complete.
* **Remote VAE Support:** Offload VAE decoding to remote servers (HuggingFace endpoints or local) for 20-30% faster generation and lower VRAM usage.

### 🎨 Interactive Dashboard (The "IDE")
* **Infinite Canvas with Pan/Zoom:** Google Maps-style navigation with mouse drag, mousewheel zoom, and keyboard shortcuts.
* **Virtual Scrolling:** Ultra-optimized rendering handles thousands of images smoothly by only loading visible items - scroll through 5000+ images without lag.
* **Mobile Touch Support:** Full pinch-to-zoom and pan gestures on mobile devices with optimized touch controls.
* **Fullscreen Mode:** Click the fullscreen button (⛶) to expand the dashboard to fill your entire screen.
* **Favorites System:** Star your best images with a ⭐ button - favorites are collected in a separate gold JSON bar for easy export.
* **Smart Filtering:** Toggle visibility by Model, Sampler, Scheduler, Denoise, or LoRA type.
  - **Shift+Click:** Isolate a single filter (deselect all others) for quick A/B testing
* **Intelligent Sorting:** Instantly sort your grid by **Oldest**, **Newest**, or **Fastest** (generation time). Your preference is saved to localStorage.
* **Go to Image #:** Jump directly to any image number with the "Go to #" input field in the header.
* **Auto-Load Sessions:** Dashboard automatically loads when generation starts - no manual session name entry needed.
* **Session Management:** Save and Load previous testing sessions directly from the UI.
* **Keyboard Navigation:**
  - `Space` - Pan down one row
  - `Shift+Space` - Pan up one row  
  - `Arrow Keys` - Pan in any direction
  - `+/-` - Zoom in/out
  - `0` - Reset zoom to 1:1
  - `F` - Auto-fit first row to viewport width

### ⚡ The "Revise & Generate" Workflow
* **One-Click Revision:** Click "REVISE" on any image to open a detail view.
* **Complete Metadata View:** Shows model, seed, prompts (with trigger words), and all generation parameters.
* **Instant Tweak:** Adjust CFG, Steps, or Sampler for *just that specific image*.
* **Generate New:** A "GENERATE NEW" button queues the new variation immediately without needing to disconnect wires or change the main batch.
* **Similarity Reel:** The revision modal shows a side-scrolling reel of all other images that share the same seed, allowing for perfect A/B comparison.
* **Multiple Prompts:** Use an array to run multiple prompts in one run without re-running your entire workflow: `["picture of a forest", "mountains at night", "masterpiece, painting of dog"]`

### 🧹 Curation & JSON Export
* **Rejection System:** Click the red **"✕"** on bad generations to hide them.
* **Triple JSON Bars (Horizontal Layout):**
    * **Green Bar (Left):** Automatically groups all *accepted* configs into a clean, optimized JSON array ready for copy-pasting.
    * **Gold Bar (Center):** Contains all *favorited* configs - your best-performing settings.
    * **Red Bar (Right):** Collects all *rejected* configs so you know exactly what settings to avoid.

---

## 📦 Installation

1. Navigate to your ComfyUI `custom_nodes` directory:
    ```bash
    cd ComfyUI/custom_nodes/
    ```

2. Clone this repository:
    ```bash
    git clone https://github.com/YOUR_USERNAME/ComfyUI-Ultimate-Auto-Sampler-Config-Grid-Testing-Suite.git
    ```

3. Restart ComfyUI.

---

## 🛠️ Usage Guide

### 1. The Nodes
This suite consists of two main nodes found under the `sampling/testing` category:

1. **Ultimate Sampler Grid (Generator):** The engine. It handles model loading, grid generation, and saving.
2. **Ultimate Grid Dashboard (Viewer):** The display. It renders the HTML output.

**Basic Setup:**
* Add the **Generator** node.
* Connect your Checkpoint, CLIP, and VAE (optional, see "Hybrid Inputs" below).
* Add the **Viewer** node.
* Connect the `dashboard_html` output from the Generator to the input of the Viewer.

### 2. Generator Node Parameters

#### Core Settings
* **`ckpt_name`**: Default checkpoint to use (can be overridden by `model` in JSON or optional input).
* **`positive_text`** / **`negative_text`**: Prompts. Supports arrays: `["prompt 1", "prompt 2"]` or JSON arrays.
* **`seed`**: Base seed. Each config uses this seed unless overridden.
* **`denoise`**: Denoise strength(s). Supports single value, array, or comma-separated: `"1.0"` or `"0.8, 0.9, 1.0"`.

#### Performance Settings
* **`vae_batch_size`**: How many images to decode at once.
  - `4` (default): Good for 8-12GB VRAM
  - `12-24`: For 24GB+ VRAM  
  - `-1`: Decode all images at once (fastest, but risky)
  
* **`flush_batch_every`**: Update dashboard every X images (0 = use VAE batch size).
  - `0`: Wait until VAE batch is full
  - `4`: Update dashboard every 4 images (recommended for live monitoring)

#### Advanced Settings
* **`overwrite_existing`**: 
  - `False` (default): Skip already-generated images (resume mode)
  - `True`: Re-generate everything
  
* **`add_random_seeds_to_gens`**: Generate X extra random variations per config.
  - `0` (default): Only use base seed
  - `3`: Generate 3 additional random seed variations per config
  - Random seeds are deterministic per base seed - changing base seed generates new random variations

* **`lookup_and_append_lora_triggerwords`**: Automatically fetch and append LoRA trigger words.
  - `False` (default): Use prompts as-is
  - `True`: Calculate SHA256 hash of each LoRA, query CivitAI API for trigger words, cache results locally, and prepend to prompts
  - Example: LoRA has trigger word "character_name" → Prompt becomes "character_name, your original prompt"
  - Cache stored in `loras_tags.json` for offline use

* **`session_name`**: Folder name where results are saved (`ComfyUI/output/benchmarks/{session_name}/`).

### 3. The JSON Configuration
The `configs_json` widget determines your grid. It accepts an array of objects. All fields support single values or arrays.

**Basic Example:**
```json
[
  {
    "sampler": ["euler", "dpmpp_2m"],
    "scheduler": ["normal", "karras"],
    "steps": [20, 30],
    "cfg": [7.0, 8.0]
  }
]
```
*Generates 16 images (2 samplers × 2 schedulers × 2 steps × 2 cfg)*

**Advanced Features:**

#### Multi-Model Testing
```json
[
  {
    "sampler": "euler",
    "scheduler": "normal", 
    "steps": 20,
    "cfg": 7.0,
    "model": [
      "sd_xl_base_1.0.safetensors",
      "juggernautXL_v9.safetensors",
      "ponyDiffusionV6XL_v6.safetensors"
    ]
  }
]
```
*Tests 3 different models with the same settings*

#### Folder Expansion
```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 20, 
    "cfg": 7.0,
    "model": "sdxl_models/"  // Tests ALL models in this folder
  }
]
```

#### Multi-LoRA with Stacking
```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 20,
    "cfg": 7.0,
    "lora": [
      "None",
      "style_lora.safetensors:0.8:1.0",
      "style_lora.safetensors:0.5:1.0 + detail_lora.safetensors:1.0:1.0",
      "loras_folder/"  // Tests ALL loras in folder
    ]
  }
]
```
*LoRA format: `filename:strength_model:strength_clip`*  
*Stack with `+` separator: `lora1:0.8:1.0 + lora2:1.0:1.0`*

#### Resolution Grid
```json
// In resolutions_json input:
[
  [1024, 1024],
  [1024, 1536], 
  [1536, 1024]
]
```

#### Multiple Prompts
```json
// In positive_text input (as JSON array):
[
  "a beautiful landscape, mountains, sunset",
  "cyberpunk city at night, neon lights",
  "portrait of a warrior, detailed armor"
]
```

### 4. Hybrid Inputs (Optional)
The Generator node features built-in widgets for Model Selection and Prompts, but also has **Optional Inputs** for flexibility:
* **Standalone Mode:** Use the dropdown menu to select a checkpoint and type prompts into the text boxes.
* **Hybrid Mode:** Connect a `MODEL`, `CLIP`, `VAE`, or `CONDITIONING` wire. The node will automatically ignore the internal widget and use the connected input instead.
* **Non-Standard Models:** For SD3, Flux, Z-Image, and other architectures:
  - Connect `optional_model`, `optional_clip`, and `optional_vae` from your model loader
  - Connect `optional_positive` and `optional_negative` for pre-encoded conditioning
  - The node automatically detects latent channel count (4 for SD1.5/SDXL, 16 for SD3/Flux/Z-Image)
  - Skip detection uses conditioning tensor hashing to properly detect prompt changes
* **Latent Input:** Connect a `LATENT` to use img2img or upscaling workflows.
  - For SD3/Flux: Use `EmptySD3LatentImage` instead of `EmptyLatentImage`
  - Latent dimensions are automatically preserved

---

## 🖥️ Dashboard Interface

### Header Bar
* **Model/Prompt Info:** Shows current model and prompt metadata
* **Go to Image #:** Jump directly to any image by entering its number (shown in bottom-left of cards)
* **Column Count:** Set fixed grid columns or leave at 0 for auto-sizing
* **Zoom Controls:** `⊙` (reset), `−` (zoom out), `+` (zoom in)

### Toolbar
* **Session Controls:** 
  - Dashboard auto-loads when connected to sampler and generation starts
  - **SAVE** to persist current state to disk
  - **DELETE** to remove session and all images
  
* **Filter Groups:** Click colored buttons to toggle visibility:
  - **Model** (Purple): Filter by checkpoint
  - **Sampler** (Cyan): Filter by sampler type
  - **Scheduler** (Blue): Filter by scheduler
  - **Denoise** (Red): Filter by denoise value
  - **LoRA** (Orange): Filter by LoRA configs
  - **Shift+Click:** Isolate single filter (deselect all others)
  
* **Sort Button:** Cycles between:
  - **Sort: Oldest** - Original generation order (default)
  - **Sort: Newest** - Most recent first
  - **Sort: Fastest** - By generation time
  - *Sort preference is saved to localStorage*
  
* **Fullscreen Button (⛶):** Expand dashboard to fill entire screen

### Navigation & Controls
* **Mouse:**
  - Left-click drag to pan
  - Middle-click drag to pan  
  - Scroll wheel to zoom in/out
  - Right-click on canvas to focus for keyboard controls
  
* **Touch (Mobile/Tablet):**
  - Single finger drag to pan
  - Two finger pinch/spread to zoom
  - Tap card to reveal buttons
  
* **Keyboard:**
  - `Space` - Scroll down one row
  - `Shift+Space` - Scroll up one row
  - `↑↓←→` - Pan in any direction
  - `+/-` - Zoom in/out
  - `0` - Reset zoom to 1:1
  - `F` - Auto-fit first row to viewport width

### Card Overlays
* **Bottom Left:** Index number (#1, #2, etc.) - used for "Go to #" feature
* **Bottom Right:** Generation time in seconds
* **Top Left (on hover):** Red ✕ button to reject/hide image
* **Top Right (on hover):** 
  - Gold ⭐ button to favorite image
  - Green "REVISE" button (below star) to open studio view

### JSON Bars (Bottom - Horizontal Layout)
* **Green Bar (Left - Accepted):** Contains optimized JSON of all currently visible images. Click to select all, then copy-paste back into the `configs_json` widget to refine your batch.
* **Gold Bar (Center - Favorites):** Contains configs of all images you starred with ⭐. Your best-performing settings in one place.
* **Red Bar (Right - Rejected):** Contains the configs of images you deleted with the **"✕"** button. Know what to avoid.

### Revision Modal
Clicking **REVISE** on a card opens the studio view:
1. **Left:** Full-resolution preview.
2. **Top Right - Read-Only Info:**
   - Model used
   - Seed number
   - Positive prompt (with trigger words if applicable)
   - Negative prompt
3. **Bottom Right - Adjustable Parameters:**
   - Sampler, Scheduler, Steps, CFG, Denoise, LoRA
4. **Bottom:** "Related Variants" reel showing other images with the same seed.
5. **GENERATE NEW:** Queues the specific config you just edited.

### Toolbar
* **Session Controls:** 
  - Type session name and click **LOAD** to view previous results
  - **SAVE** to persist current state to disk
  - **DELETE** to remove session and all images
  
* **Filter Groups:** Click colored buttons to toggle visibility:
  - **Model** (Purple): Filter by checkpoint
  - **Sampler** (Cyan): Filter by sampler type
  - **Scheduler** (Blue): Filter by scheduler
  - **Denoise** (Red): Filter by denoise value
  - **LoRA** (Orange): Filter by LoRA configs
  
* **Sort Button:** Cycles between:
  - **Sort: Oldest** - Original generation order (default)
  - **Sort: Newest** - Most recent first
  - **Sort: Fastest** - By generation time
  - *Sort preference is saved to localStorage*
  
* **Fullscreen Button (⛶):** Expand dashboard to fill entire screen

### Navigation & Controls
* **Mouse:**
  - Left-click drag to pan
  - Middle-click drag to pan  
  - Scroll wheel to zoom in/out
  - Right-click on canvas to focus for keyboard controls
  
* **Keyboard:**
  - `Space` - Scroll down one row
  - `Shift+Space` - Scroll up one row
  - `↑↓←→` - Pan in any direction
  - `+/-` - Zoom in/out
  - `0` - Reset zoom to 1:1
  - `F` - Auto-fit first row to viewport width

### Card Overlays
* **Bottom Left:** Index number (#1, #2, etc.)
* **Bottom Right:** Generation time in seconds
* **Top Left (on hover):** Red ✕ button to reject/hide image
* **Top Right (on hover):** Green "REVISE" button to open studio view

### JSON Bars (Bottom)
* **Green Bar (Accepted):** Contains a "Smart Grouped" JSON of all currently visible images. Click to select all, then copy-paste back into the `configs_json` widget to refine your batch.
* **Red Bar (Rejected):** Contains the configs of images you deleted with the **"✕"** button.

### Revision Modal
Clicking **REVISE** on a card opens the studio view:
1. **Left:** Full-resolution preview.
2. **Right:** Input fields to tweak settings for *this specific image*.
3. **Bottom:** "Related Variants" reel showing other images with the same seed.
4. **GENERATE NEW:** Queues the specific config you just edited.

---

## 🎯 Example Workflows

### Quick Quality Test (40 images)
```json
[
  {
    "sampler": ["dpmpp_2m", "euler"],
    "scheduler": ["karras", "normal"],
    "steps": [20, 30],
    "cfg": [6.0, 7.0, 8.0],
    "denoise": "1.0"
  }
]
```

### Multi-Model Comparison (9 images)
```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 25,
    "cfg": 7.0,
    "model": [
      "model_v1.safetensors",
      "model_v2.safetensors", 
      "model_v3.safetensors"
    ]
  }
]
```
Set `add_random_seeds_to_gens: 2` to get 3 variations per model (27 total images).

### LoRA Stack Testing (24 images)
```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 25,
    "cfg": 7.0,
    "lora": [
      "None",
      "style.safetensors:0.6:1.0",
      "style.safetensors:0.8:1.0",
      "style.safetensors:1.0:1.0",
      "style.safetensors:0.8:1.0 + detail.safetensors:0.5:1.0",
      "style.safetensors:1.0:1.0 + detail.safetensors:1.0:1.0"
    ]
  }
]
```
Test multiple LoRA strengths and combinations in one run.

### Random LoRA Selection
Randomly select LoRAs from a folder for variety and experimentation:

**Basic Syntax:**
```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 25,
    "cfg": 7.0,
    "lora": "XL/Styles/[3,0.85]"
  }
]
```
- Randomly selects **3 LoRAs** from `XL/Styles/` folder at strength **0.85**
- Selection is **reproducible** (uses the config's seed) - same seed = same LoRAs

**Truly Random (Non-Reproducible):**
```json
"lora": "XL/Styles/[3,0.85,random]"
```
- Add `random` keyword to disable seed-based selection
- Different LoRAs selected on each run for maximum variety

**Dual Strength (Model + CLIP):**
```json
"lora": "XL/Characters/[2,0.8,0.6]"
```
- Model strength: **0.8**
- CLIP strength: **0.6**
- Still seed-based (reproducible)

**Combining with Regular LoRAs:**
```json
"lora": "XL/base.safetensors:1.0 + XL/Styles/[2,0.7] + XL/Details/[1,0.5,random]"
```
- Loads `base.safetensors` at strength 1.0 (always)
- Picks 2 random style LoRAs at 0.7 (same ones with same seed)
- Picks 1 truly random detail LoRA at 0.5 (different each run)

**Notes:**
- Random selection works with all subfolders
- Trigger words are automatically fetched for all selected LoRAs
- Path separators work on both Windows (`\`) and Linux (`/`)

### Full Model Folder Test
```json
[
  {
    "sampler": "dpmpp_2m",
    "scheduler": "karras",
    "steps": 25,
    "cfg": 7.0,
    "model": "realistic_models/"
  }
]
```
Tests ALL checkpoints in the `realistic_models` folder.

### CLIP Skip for Anime Models
Control which CLIP layer to use for text encoding - crucial for anime models:

```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 28,
    "cfg": 7.0,
    "model": "anime_model.safetensors",
    "clip_skip": -2
  }
]
```
- `clip_skip: 0` (default) - Use last layer (best for realistic models)
- `clip_skip: -1` - Skip 1 layer (transition)
- `clip_skip: -2` - Skip 2 layers (best for anime/illustration models)
- `clip_skip: -3` - Skip 3 layers (experimental)

**Testing Multiple CLIP Skip Values:**
```json
[
  {
    "sampler": "euler",
    "steps": 28,
    "cfg": 7.0,
    "model": "anime_model.safetensors",
    "clip_skip": [0, -1, -2, -3]
  }
]
```
Generates 4 images testing different CLIP skip values with the same seed.

### LoRA Trigger Word Filtering
Exclude specific trigger words from auto-appended LoRA triggers:

```json
[
  {
    "sampler": "euler",
    "steps": 28,
    "cfg": 7.0,
    "lora": "bimbo_style.safetensors:0.8:0.6",
    "lora_omit_triggers": ["bimbo", "makeup", "jewelry"]
  }
]
```
- Automatically fetches trigger words from CivitAI
- Filters out unwanted triggers (e.g., "bimbo, makeup, jewelry")
- Only keeps relevant triggers
- Handles comma normalization (CivitAI stores triggers with trailing commas)

**Multiple LoRAs with Filtering:**
```json
[
  {
    "lora": "XL/Quality/*:0.6:0.6 + XL/Style/anime.safetensors:1.0:0.8",
    "lora_omit_triggers": ["masterpiece", "best quality", "highres"]
  }
]
```
Filters apply to ALL LoRAs in the stack.

### Model Folder Expansion
Test all models in a folder automatically:

```json
[
  {
    "sampler": "euler",
    "scheduler": "normal",
    "steps": 28,
    "cfg": 7.0,
    "model": "SDXL/"
  }
]
```
- Trailing `/` triggers folder expansion
- Tests every `.safetensors` file in the folder
- Can combine with other parameters for comprehensive testing

**Multi-Architecture Comparison:**
```json
[
  {
    "model": ["SD1.5/", "SDXL/", "Flux/"],
    "sampler": "euler",
    "steps": 28
  }
]
```
Tests all models from all three folders with the same settings.

**Note:** When using model folder expansion with multiple models, the system automatically disables pre-encoding and batch-encodes prompts per-model for correct CLIP handling. You'll see:
```
[GridTester] ⚠️ Multiple models detected (3 different models) - pre-encoding DISABLED
[GridTester] ℹ️  Each model has a different CLIP - encoding will happen per-generation
```

---

## 📋 Preset Configs

## 🏆 Group 1: The "Gold Standards" (Reliable Realism)

*Tests the 5 most reliable industry-standard combinations.*  
5 samplers × 2 schedulers × 2 step settings × 2 cfgs = **40 images**

```json
[
  {
    "sampler": ["dpmpp_2m", "dpmpp_2m_sde", "euler", "uni_pc", "heun"],
    "scheduler": ["karras", "normal"],
    "steps": [25, 30],
    "cfg": [6.0, 7.0],
    "lora": "None"
  }
]
```

## 🎨 Group 2: Artistic & Painterly

*Tests 5 creative/soft combinations best for illustration and anime.*  
2 samplers × 3 schedulers × 3 step settings × 2 cfgs = **36 images**

```json
[
  {
    "sampler": ["euler", "dpmpp_2m"],
    "scheduler": ["simple", "beta", "normal"],
    "steps": [20, 25, 30],
    "cfg": [1.0, 4.5],
    "lora": "None"
  }
]
```

## ⚡ Group 3: Speed / Turbo / LCM

*Tests 4 ultra-fast configs. (Note: Ensure you are using a Turbo/LCM capable model or LoRA).*  
4 samplers × 3 schedulers × 4 step settings × 2 cfgs = **96 images**

```json
[
  {
    "sampler": ["lcm", "euler", "dpmpp_sde", "euler_ancestral"],
    "scheduler": ["simple", "sgm_uniform", "karras"],
    "steps": [4, 5, 6, 8],
    "cfg": [1.0, 1.5],
    "lora": "None"
  }
]
```

## 🦾 Group 4: Flux & SD3 Specials

*Tests 4 configs specifically tuned for newer Rectified Flow models like Flux and SD3.*  
2 samplers × 3 schedulers × 3 step settings × 2 cfgs = **36 images**

```json
[
  {
    "sampler": ["euler", "dpmpp_2m"],
    "scheduler": ["simple", "beta", "normal"],
    "steps": [20, 25, 30],
    "cfg": [1.0, 4.5],
    "lora": "None"
  }
]
```

## 🧪 Group 5: Experimental & Unique

*Tests 6 weird/niche combinations for discovering unique textures.*  
6 samplers × 4 schedulers × 5 step settings × 4 cfgs = **480 images**

```json
[
  {
    "sampler": ["dpmpp_3m_sde", "ddim", "ipndm", "heunpp2", "dpm_2_ancestral", "euler"],
    "scheduler": ["exponential", "normal", "karras", "beta"],
    "steps": [25, 30, 35, 40, 50],
    "cfg": [4.5, 6.0, 7.0, 8.0],
    "lora": "None"
  }
]
```

---

## 🔧 Performance Tips

### For Large Batches (1000+ images)
1. Set `flush_batch_every: 10-20` to see progress updates without overwhelming the browser
2. Use `vae_batch_size: 8-12` (balance between speed and VRAM)
3. Enable `overwrite_existing: False` so you can stop/resume safely
4. Close other browser tabs to free up memory for virtual scrolling

### For Multi-Model Testing
1. Sort models by similarity in the JSON (reduces cache invalidation)
2. Use identical LoRA/prompt settings across models for fair comparison
3. Use `add_random_seeds_to_gens: 2-3` to evaluate model consistency

### For Memory-Constrained Systems
1. Lower `vae_batch_size` to 1-2
2. Test one model at a time instead of multi-model arrays
3. Use smaller resolution grids
4. Filter the dashboard to reduce visible cards

---

## ⚠️ Troubleshooting

### Generation Issues
* **"Session not found":** Ensure the `session_name` matches a folder inside `ComfyUI/output/benchmarks/`.
* **OOM Errors:** If you crash during decoding, lower the `vae_batch_size` to 1 or 2.
* **Images not resuming:** Make sure `overwrite_existing: False`. Check console for skip messages.
* **Random seeds different each run:** This is intentional - random seeds are tied to the base seed. Change the base `seed` parameter to generate new random variations.
* **"mat1 and mat2 shapes cannot be multiplied" error:**
  - This indicates a model architecture mismatch
  - For SD3/Flux/Z-Image models, ensure you connect ALL optional inputs (model, clip, vae, positive, negative)
  - Check that your LoRAs are compatible with your model architecture
  - Incompatible LoRAs are automatically detected and skipped with detailed error messages
* **Dashboard not auto-loading:**
  - Ensure the dashboard node is connected to the sampler's `dashboard_html` output
  - Check browser console for connection errors
  - Try manually clicking "RELOAD / SHOW SESSION" button

### Dashboard Issues
* **Cards not appearing:** Click inside the viewport area first to give it focus, then use keyboard navigation.
* **Can't scroll/pan:** Right-click on the canvas area to focus it, or click and drag with left mouse button.
* **Slow performance with many images:** The virtual scrolling should handle 5000+ images smoothly. If it's slow, try:
  - Closing other browser tabs
  - Reducing browser zoom to 100%
  - Clearing localStorage (`F12` → Console → `localStorage.clear()`)
* **Images not loading:** Scroll slower to give the lazy loader time to fetch images.
* **Hover z-index issues:** Ensure you're using the latest CSS file with `z-index: 999999 !important` on card hover.
* **Mobile touch not working:** 
  - Ensure you're using the latest version with touch support
  - Try tapping and holding to reveal card buttons
  - Use two fingers for pinch-to-zoom

### LoRA & Trigger Word Issues
* **Trigger words not appearing:** 
  - Enable `lookup_and_append_lora_triggerwords` in the sampler node
  - Ensure internet connection for first-time LoRA lookup
  - Check `loras_tags.json` in ComfyUI root for cached results
* **"INCOMPATIBLE LORA DETECTED" messages:**
  - This is normal - the node automatically skips incompatible LoRAs
  - Check the summary at the end of generation for list of incompatible LoRAs
  - Ensure your LoRAs match your model architecture (SD1.5 LoRAs won't work on SDXL, etc.)
* **Random LoRA selection not working:**
  - Ensure folder path is correct (e.g., `"XL/Styles/[3,0.85]"` not `"XL/Styles[3,0.85]"`)
  - Check console for debug messages showing available LoRAs
  - Verify LoRAs exist in the specified folder and subfolders
  - Path separators: Use forward slashes `/` in the syntax (auto-converts backslashes internally)
* **Random LoRAs different from expected:**
  - Seed-based selection is intentional - change base seed for different selection
  - Use `[count,strength,random]` for truly random (non-reproducible) selection
  - Random selection happens once at start - all generations in batch use same selected LoRAs
* **Trigger words not being filtered with `lora_omit_triggers`:**
  - Ensure `lookup_and_append_lora_triggerwords` is enabled
  - Check that trigger words are actually being fetched (see console output)
  - Trigger filtering is case-insensitive and handles trailing commas automatically
  - Filters apply to all LoRAs in the stack

### Model & CLIP Issues
* **Images look wrong with multiple models:**
  - System automatically handles multi-model CLIP encoding
  - You should see: `[GridTester] ⚠️ Multiple models detected - pre-encoding DISABLED`
  - Each model uses its own CLIP - this is correct behavior
  - If you don't see this message with multiple models, check configs are properly formatted
* **CLIP skip not affecting results:**
  - Verify the model supports CLIP skip (anime models typically do)
  - Use appropriate values: 0 for realistic, -2 for anime
  - Test with same seed and only change clip_skip to see differences
  - SDXL models may not be as sensitive to CLIP skip as SD1.5
* **"No files found in folder" for model expansion:**
  - Ensure trailing `/` in path: `"SDXL/"` not `"SDXL"`
  - Check folder exists in `ComfyUI/models/checkpoints/`
  - Folder names are case-sensitive on Linux/Mac
  - Verify there are actually `.safetensors` files in the folder

### Remote VAE Issues
* **Remote VAE not working:**
  - Check endpoint is set correctly in node parameters
  - Verify server is running and accessible
  - Look for `[GridTester] 🌐 Remote VAE worker started` in console
  - Should see `[GridTester] 🌐 Queued X images for remote VAE decoding`
  - If no queue messages appear, remote VAE isn't being used
* **Remote VAE hangs on "Waiting for remote VAE":**
  - Server may have crashed - check server logs
  - Network connectivity issues - try local endpoint first
  - Restart remote VAE server and try again

### Interrupt/Cancel Issues
* **Cancel doesn't stop generation:**
  - Ensure you're using the latest version with interrupt handling
  - Cancel now stops ALL remaining jobs (not just current image)
  - Should see `🛑 INTERRUPTED - Stopping all jobs` in console
  - Completed work is automatically saved
* **Work lost after canceling:**
  - This shouldn't happen - manifest is saved on interrupt
  - Check `ComfyUI/output/benchmarks/{session_name}/manifest.json`
  - Dashboard should show all completed images
  - If manifest is empty, check console for save errors

### Browser Compatibility
* **Chrome/Edge:** Full support ✅
* **Firefox:** Full support ✅  
* **Safari:** Mostly works, some keyboard shortcuts may conflict
* **Mobile:** Full touch support ✅ (iOS Safari, Android Chrome tested)

---

## 📝 Changelog

### Update 2/5/26 - Code Refactoring & Performance Improvements
* 🏗️ **Major Code Refactoring:** Reorganized codebase into 6 modular files for better maintainability
  - `trigger_words.py` - LoRA trigger word handling
  - `batch_encoding.py` - CLIP batch encoding with caching
  - `manifest_utils.py` - Manifest file management
  - `model_loader.py` - Model/LoRA loading and patching
  - `image_generation.py` - Image generation and sampling
  - `generation_orchestrator.py` - Main orchestration layer
* 🎯 **CLIP Skip Support:** Control CLIP layer usage with `clip_skip` parameter
  - Essential for anime models (typically -2) vs realistic models (0)
  - Supports arrays for testing multiple values
  - Integrated with batch encoding system
* 🧠 **Intelligent CLIP Encoding:** Multi-model workflows now handle CLIP correctly
  - Automatically detects when multiple models are used
  - Disables pre-encoding when needed to prevent CLIP mismatches
  - Each model uses its own CLIP for accurate results
* ⚡ **Batch Encoding on Model Switch:** 3-6x faster encoding for multi-model workflows
  - When switching models, all prompts are batch-encoded at once
  - Reduces CLIP load/unload cycles dramatically
  - Intelligent look-ahead collects all prompts for each model
* 🗑️ **LoRA Trigger Word Filtering:** New `lora_omit_triggers` parameter
  - Exclude specific trigger words from auto-appended LoRA triggers
  - Supports arrays: `["trigger1", "trigger2"]`
  - Handles comma normalization from CivitAI API
* 📁 **Model Folder Expansion:** Use `"model": "FolderName/"` to test all checkpoints in a folder
  - Works just like LoRA folder expansion
  - Perfect for comparing model versions or architectures
  - Automatically detects and tests all `.safetensors` files
* 🛑 **Graceful Interruption:** Cancel now stops ALL jobs, not just current generation
  - Flushes pending batches before stopping
  - Waits for remote VAE to complete current jobs
  - Saves manifest with all completed work
  - Generates HTML dashboard with progress so far
* 🌐 **Remote VAE Fixes:** Remote VAE decoding now works correctly
  - Fixed initialization to work with all configurations
  - Fixed job queuing with correct method signature
  - Works with single or multiple models
  - Properly integrated with interrupt handling
* 🔧 **str_model/str_clip Removal:** Deprecated config fields removed
  - Strengths now properly specified in LoRA string: `"lora.safetensors:0.8:0.6"`
  - Each LoRA in stack can have different strengths
  - Cleaner, more intuitive syntax
* 📚 **Comprehensive Documentation:** Added detailed guides for all new features
  - CLIP skip usage and best practices
  - Model folder expansion examples
  - Batch encoding optimization explanation
  - LoRA trigger filtering guide
  - Remote VAE configuration

### Update 2/5/26 - Random LoRA Selection
* 🎲 **Random LoRA Selection:** Randomly select LoRAs from folders with powerful new syntax
  - `[count,strength]` - Select N random LoRAs at specified strength (seed-based, reproducible)
  - `[count,strength,random]` - Truly random selection that changes each run
  - `[count,model_str,clip_str]` - Support for dual strength (model and CLIP)
  - Combine with regular LoRAs: `"base.safetensors:1.0 + XL/Folder/[3,0.8]"`
  - Cross-platform path handling (Windows `\` and Linux `/` both work)
  - Full integration with trigger word lookup system
  - Automatic expansion before generation for consistent results


### Update 1/14/26 - Major Feature Update
* 🎯 **Non-Standard Model Support:** Full compatibility with SD3, Flux, Z-Image, and other architectures
  - Automatic latent channel detection (4 for SD1.5/SDXL, 16 for SD3/Flux/Z-Image)
  - Smart model/clip/vae override handling
  - Proper dimension handling for non-standard architectures
* ⭐ **Favorites System:** Star your best images with dedicated gold JSON bar for favorited configs
* 🎨 **Horizontal JSON Bars:** Redesigned layout with three side-by-side bars (Accepted/Favorites/Rejected)
* 🔍 **LoRA Auto Trigger Words:** Automatic CivitAI API integration
  - SHA256 hash-based LoRA lookup
  - Automatic trigger word prepending to prompts
  - Local caching in `loras_tags.json`
* 🚫 **LoRA Compatibility Detection:** Automatically detects and skips incompatible LoRAs
  - Clear error messages once per LoRA+Model combination
  - End-of-run summary of incompatible LoRAs
  - No more log spam from dimension mismatches
* ⌨️ **Shift+Click Filter Isolation:** Shift+click any filter to isolate it (deselect all others)
* 🎯 **Go to Image #:** Jump directly to any image number from header input field
* 🚀 **Dashboard Auto-Load:** Automatically loads session when generation starts (no manual entry needed)
* 📱 **Mobile Touch Support:** Full pinch-to-zoom and pan gestures on mobile devices
* 🔐 **Conditioning Change Detection:** Uses tensor hashing to detect prompt changes in pre-encoded conditioning
* 📋 **Enhanced Revise Modal:** Now shows model, seed, and complete prompts (with trigger words)
* 💾 **Prompt Persistence:** Saves actual prompts (with trigger words) to manifest.json
* ⚡ **Performance Improvements:** Optimized skip logic, better cache invalidation, reduced redundant operations

### Update 1/11/26 - Major Overhaul
* ✨ **Virtual Scrolling:** Handles 5000+ images smoothly with automatic load/unload
* 🖼️ **Fullscreen Mode:** Expand dashboard to fill entire screen
* 🔄 **Multi-Model Support:** Test multiple checkpoints in single run with folder expansion
* 🎨 **Multi-LoRA Stacking:** Layer multiple LoRAs with `+` separator, supports folder expansion
* 🎲 **Multi-Seed Generation:** Add random variations per config with deterministic seeds
* ⏸️ **Stop & Resume:** Intelligent skip detection - resume where you left off
* ⌨️ **Keyboard Navigation:** Spacebar to scroll rows, arrow keys, F for auto-fit
* 📊 **Live Updates:** `flush_batch_every` parameter for incremental dashboard updates
* 💾 **Persistent Settings:** Sort order and column count saved to localStorage
* 🎯 **Auto-Fit Zoom:** Automatically centers and fits first row on load
* ⚡ **Performance:** Massive refactoring and optimization throughout codebase

---

## 📜 License

MIT License. Feel free to use, modify, and distribute.

---

## 🙏 Credits

Created for the ComfyUI community. Special thanks to all contributors and testers who helped refine this tool.

**Star this repo if you find it useful!** ⭐