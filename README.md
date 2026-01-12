# ComfyUI Ultimate Auto Sampler Config Grid Testing Suite


<img width="1856" height="1030" alt="image" src="https://github.com/user-attachments/assets/e1d57553-80a8-4058-aea5-455e6bfbdf8a" />


**ComfyUI Sampler testing & benchmarking tool for testing Stable Diffusion samplers, schedulers, CFG scales, prompts, img2img denoise values, and LoRA combinations. Features infinite-canvas dashboard image grids with virtual scrolling that can handle thousands of images, multi-model comparison, automatic resume on interrupt, and real-time visualization. Test entire checkpoint folders, stack multiple LoRAs, generate random seed variations, and export optimized configs. Includes fullscreen mode, keyboard navigation, smart filtering by parameters, and one-click regeneration workflow. Perfect for sampler output optimization and hyperparameter tuning.**

Stop guessing which Sampler, Scheduler, or CFG value works best. This custom node suite allows you to generate massive Cartesian product grids, view them in an interactive infinite-canvas dashboard, and refine your settings with a "Revise & Generate" workflow without ever leaving the interface.

---

## 🌟 Key Features

### 🚀 Powerful Grid Generation
* **Cartesian Product Engine:** Automatically generates every permutation of your input settings. Test unlimited Samplers, Schedulers, CFG scales, Sizes, Prompts, LoRA combinations all in one go.
* **Multi-Model Support:** Test multiple checkpoints in a single run by passing an array of model names or folder paths.
* **Multi-LoRA Stacking:** Layer multiple LoRAs with custom strengths using the `+` separator. Supports folder expansion for testing entire LoRA directories.
* **Multi-Seed Generation:** Add extra random variations per config with the `add_random_seeds_to_gens` parameter - perfect for evaluating consistency.
* **Smart Caching:** Intelligently skips model and LoRA reloading when consecutive runs share the same resources, making generation instant for parameter tweaks.
* **Stop & Resume:** Intelligent skip detection - if you stop a generation mid-run, resuming will skip already-generated images and continue where you left off.
* **VAE Batching:** Includes a `vae_batch_size` input to batch decode images, significantly speeding up large grid runs.
* **Live Dashboard Updates:** Configure `flush_batch_every` to update the dashboard incrementally (e.g., every 4 images) instead of waiting for the entire batch to complete.

### 🎨 Interactive Dashboard (The "IDE")
* **Infinite Canvas with Pan/Zoom:** Google Maps-style navigation with mouse drag, mousewheel zoom, and keyboard shortcuts.
* **Virtual Scrolling:** Ultra-optimized rendering handles thousands of images smoothly by only loading visible items - scroll through 5000+ images without lag.
* **Fullscreen Mode:** Click the fullscreen button (⛶) to expand the dashboard to fill your entire screen.
* **Smart Filtering:** Toggle visibility by Model, Sampler, Scheduler, Denoise, or LoRA type.
* **Intelligent Sorting:** Instantly sort your grid by **Oldest**, **Newest**, or **Fastest** (generation time). Your preference is saved to localStorage.
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
* **Instant Tweak:** Adjust CFG, Steps, or Sampler for *just that specific image*.
* **Generate New:** A "GENERATE NEW" button queues the new variation immediately without needing to disconnect wires or change the main batch.
* **Similarity Reel:** The revision modal shows a side-scrolling reel of all other images that share the same seed, allowing for perfect A/B comparison.
* **Multiple Prompts:** Use an array to run multiple prompts in one run without re-running your entire workflow: `["picture of a forest", "mountains at night", "masterpiece, painting of dog"]`

### 🧹 Curation & JSON Export
* **Rejection System:** Click the red **"✕"** on bad generations to hide them.
* **Dual JSON Bars:**
    * **Green Bar:** Automatically groups all *accepted* configs into a clean, optimized JSON array ready for copy-pasting.
    * **Red Bar:** Collects all *rejected* configs so you know exactly what settings to avoid.

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
* **Latent Input:** Connect a `LATENT` to use img2img or upscaling workflows.

---

## 🖥️ Dashboard Interface

### Header Bar
* **Model/Prompt Info:** Shows current model and prompt metadata
* **Column Count:** Set fixed grid columns or leave at 0 for auto-sizing
* **Zoom Controls:** `⊙` (reset), `−` (zoom out), `+` (zoom in)

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

### Dashboard Issues
* **Cards not appearing:** Click inside the viewport area first to give it focus, then use keyboard navigation.
* **Can't scroll/pan:** Right-click on the canvas area to focus it, or click and drag with left mouse button.
* **Slow performance with many images:** The virtual scrolling should handle 5000+ images smoothly. If it's slow, try:
  - Closing other browser tabs
  - Reducing browser zoom to 100%
  - Clearing localStorage (`F12` → Console → `localStorage.clear()`)
* **Images not loading:** Scroll slower to give the lazy loader time to fetch images.
* **Hover z-index issues:** Ensure you're using the latest CSS file with `z-index: 999999 !important` on card hover.

### Browser Compatibility
* **Chrome/Edge:** Full support ✅
* **Firefox:** Full support ✅  
* **Safari:** Mostly works, some keyboard shortcuts may conflict
* **Mobile:** Touch gestures work but not optimized for small screens

---

## 📝 Changelog

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