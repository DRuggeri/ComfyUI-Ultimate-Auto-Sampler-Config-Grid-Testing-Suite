

99% of this project's near 10k lines of code was written by either Gemini or Claude. Sorry if that upsets you, I've been a programmer for 15 years and it's simply a much faster means of developing.

With that said, here is a guide on:

Easyily Get AI To Add Features To This Project:

Gemini Pro & Claude Sonnet 4.5 both work great but they sometimes make mistakes. The key is to really get a very clear prompt built out.

Step 1.
Send the AI the ProjectStructure.md and README.md files and your task and ask it to tell you which files need to be edited to get your task completed.

Step 2. 
Start a new chat and attach the files it mentioned, along with the following prompt or something similar with your task request prompt in the middle:

Prompt Fill-in:

Help me update my ComfyUI Custom Node. When updating files, DO NOT REMOVE ANY CODE. DO NOT REMOVE ANY COMMENTS. ONLY CHANGE WHAT IS NECESSARY.

PUT YOUR TASK HERE

Check ProjectStructure.md to get an idea of file structure and contents, check README.md  to get an idea of the project as a whole.

step 3
?????

step 4
Profit!!!

But seriously, after updating your code see if it works. If it didn't send the error message if there isnt one or your symptoms. If its still not working try a different AI or try breaking down your task in smaller pieces.


---

!!!!
Check Roadmap.md for some tasks and do them. If you think you can do the ones marked as New to-do items, needs more info/explaining/numbering those are good.

There is info on the project in README.md and info on the file structure and notes on each files functions in the ProjectStructure.md 
!!!!
ProjectStructure.md has notes to assist AI in developing this project
!!!!

### **ComfyUI Ultimate Sampler Grid – Development Roadmap**


## Add on off switches in builder ui to text encoder selection and vae selection


## Add more info to the lora and model civitai lookups in the builderUI, option to show full API response, show full JSON response, save full JSON resposne, if lookup data is cached, show a big warning on the very top that says READ FROM DISK CACHE, LAST LOOKED UP ON {lookup date}


## When you click a sampler or scheduler in the dropdown it should add it to the list right away.



## Save/Load/Import (Merge) Prompts. (With settable unique naming option) Load should offer a searchable dropdown menu for all past saved prompts. Let's store this data in a outputs/benchmarks/PromptsData folder. Each prompt/save should be its own file.


## ~~Easy Feature: Add Esc key close to Revise modal and add X to close in top right of modal in Dashboard and the Lookup LoRA Metadata from CivitAI, and omit lora triggerwords modals in the Builder UI.~~ COMPLETED Also
Replace revise button in dashboard with edit emoji 



## Bug Fix: Batch Encoding Runs Before Job Skip/Continue/Resume check and will encode everything again even if it's already been completed. Also Continue/Resume needs optional inputs to be tracked. We need to track connected node changes from each of the optional inputs, we could also use this step to save the workflow to the benchmark/session folder and compare the last run workflow to the current to track node changes and determine changes and also integrate currenly missing from optional inputs such as model, loras, prompts, etc.

## ~~Fix: Manifest doesn't need lora omit triggers list in every item~~ (DONE - already stripped in create_image_metadata via .pop())

# Needs Testing: Batch encoding doesnt seem to be working for optional inputs possibly, or maybe its very large models, maybe ggufs, I get loading messages after every single encoding instead of once per batch and it takes a long time (low priority)
Symptom: each encoding fills the GPU more and more and eventually it becomes 0 usable, 0 loaded all offloaded.
loaded partially; 5585.34 MB usable, 5543.55 MB loaded, 628.32 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
loaded partially; 5569.51 MB usable, 5527.72 MB loaded, 644.90 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
loaded partially; 5553.58 MB usable, 5511.79 MB loaded, 660.34 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
loaded partially; 5537.65 MB usable, 5495.86 MB loaded, 676.40 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
maybe we need to force encodings to offload to ram?

## ~~Add attention options, xformers, sdpa, sage, flash, etc, option for test all, test all should clear ram & vram between each test.~~ COMPLETED
* **Status:** Added `attention_mode` config field supporting: default, xformers, pytorch, flash, sage, sage3, sub_quad, split. Use `"*"` to test all modes. Runtime switching via `transformer_options["optimized_attention_override"]` in ComfyUI's attention registry. Config Builder UI has dropdown+chips selector. Per-image metadata tracks which attention mode was used for dashboard filtering. Integrated into config expansion (Cartesian product with other params), skip/resume matching, and generation pipeline.

# Deeper explained items to-do list

#### **1. Skip Logic for Optional Inputs** COMPLETED

* **Problem:** The `SamplerGridTester` node cannot reliably detect changes in optional inputs (`optional_model`, `optional_vae`, etc.) because standard `IS_CHANGED` logic relies on input hash comparisons, which don't update for passed objects in optional slots.
* **Status:** Implemented `IS_CHANGED` classmethod in `sampler_node.py` that returns `float("NaN")` when any optional input is connected (forces re-execution), or a deterministic hash when no optional inputs are used (allows caching). Updated `check_if_job_completed` in `generation_orchestrator.py` to skip model/lora/prompt matching when optional inputs are connected, since those values come from upstream nodes whose changes can't be tracked. Added warning when resume mode is used with optional inputs.
* **Target Files:** `sampler_node.py`, `generation_orchestrator.py`


#### **7. CivitAI Download Integration** (low priority)
A button in the builder UI to pack short sha256 into config with an explanation that it can be used to share or move an Ultimate Sampler Config Tester workflow and allow for downloading all models and loras in the workflow from civitAI with a few simple easy clicks. lora_utils has calculate civit model has function in it. dropdown configurable options for where to store each file type.


* **Target Files:** `__init__.py`, `lora_utils.py`, `web/config_builder.js`


#### **9. Tag/Token-Based Omit Logic** DONE


#### **10. Validation Warning (Omit vs Lookup) - Warn user if omits are added but lookup is off** (low priority) DONE


#### **11. Model-Specific Prompts** COMPLETED

* **Problem:** Different models need different trigger words (e.g., "score_9, score_8" for Pony vs "masterpiece" for SD1.5).
* **Status:** Implemented as per-config `model_prompt_prefix` and `model_prompt_suffix` fields. These quality tags are prepended/appended to ALL prompts for a given config, wrapping around the entire prompt+triggers assembly. Added `_apply_model_prompt_affixes()` helper in `trigger_words.py`, integrated into both `build_prompt_with_triggers()` and `collect_unique_prompts_with_triggers()` for correct pre-encoding. Config Builder UI shows prefix/suffix text inputs in the Prompts section of each config. Fields persist through save/load and are passed through `expand_configs()` in `config_utils.py`.
* **Target Files:** `trigger_words.py`, `config_utils.py`, `conf-builder-config-management.js`, `conf-builder-utilities.js`, `conf-builder-main.js`

#### **12. Arrays in LoRA Weights** COMPLETED

* **Problem:** Cannot grid search LoRA weights like `lora.safetensors:[0.5, 0.8]:1.0`.
* **Status:** Implemented `_expand_lora_weight_arrays()` in `config_utils.py`. Supports `[0.5, 0.8]` syntax in both model_strength and clip_strength positions, with Cartesian product for multiple arrays.
* **Target Files:** `config_utils.py`

#### **13. Real-Time ETA** COMPLETED

* **Problem:** ETA only prints to server console.
* **Status:** Implemented real-time progress bar in Dashboard. Backend sends `ultimate_grid.progress` events via WebSocket after each job. Frontend displays an ETA bar below the header with job count, percentage, ETA, finish time, and avg duration. Shows completion summary and auto-hides after 30s.
* **Target Files:** `generation_orchestrator.py`, `web/dashboard.js`, `resources/logic_events.js`, `resources/template.html`

#### **14. Cache Trigger Word Placement** (low priority)

* **Problem:** `trigger_words.py` logic runs every loop iteration.
* **Instruction:**
1. **Modify `trigger_words.py`:**  
2. **Apply:** Decorate `get_filtered_lora_triggers`

* **Target Files:** `trigger_words.py`




#### **17. Menu Refactor (Cog Wheel)** COMPLETED

* **Problem:** Header is cluttered.
* **Instruction:**
1. **Modify `resources/template.html`:** Replace the "Session" button with a `div` class "menu-container" containing an SVG gear icon.
2. **Dropdown:** Create a hidden `div` "menu-dropdown". Move "Cols", "Go To", and "Save/Load" inputs inside it.
3. **Modify `resources/logic_ui.js`:** Add logic to toggle visibility of "menu-dropdown" when the gear is clicked.

Move COLS input into session popup modal, change session to cogwheel, change filters to filter icon,

* **Target Files:** `resources/template.html`, `resources/logic_ui.js`
* **Status:** Moved Go To #, Cols, and Reset Zoom into a cog wheel (gear icon) dropdown menu. Added SVG gear icon button, CSS for dropdown menu with items, click-outside-to-close, and Esc key handling.
* **Target Files:** `resources/template.html`, `resources/logic_ui.js`, `resources/report.css`

#### **18. Optionally Pack workflow into images ** (low priority)

* **Problem:** Pack workflow into images optionally 
* **Instruction:**
1. **Modify `image_generation.py`:** In `save_image_to_disk`.
2. **Implementation:** Use `PIL.PngImagePlugin.PngInfo`. Create a `PngInfo` object. Add `info.add_text("prompt", json.dumps(prompt))`. Pass this `pnginfo` to `image.save()`.
3. **Data Source:** Ensure the raw prompt/workflow is passed down from `sampler_node.py`.


* **Target Files:** `image_generation.py`, `generation_orchestrator.py`


#### **20. Hotkeys Reference List** COMPLETED

* **Problem:** Users don't know shortcuts.
* **Status:** Already implemented in `resources/template.html` as a KEYBOARD SHORTCUTS section in the Filters & Info popup, with a table showing Space, Shift+Space, Arrow Keys, +/-, 0, F, and Shift+Click shortcuts. `0 Key Resets Zoom & Pan` Etc
* **Target Files:** `resources/template.html`

Put the reference list at the bottom of the session popup modal

#### **21. Virtual DOM Pan/Zoom (Canvas Builder)** (low priority)

* **Problem:** The Config Builder UI (graph node) needs infinite canvas capabilities for large node graphs.
* **Instruction:**
1. **Scope Check:** If this refers to the *Dashboard*, it's done (`logic_virtual.js`). If this refers to the *Config Builder Node UI* (`web/config_builder.js`), it needs HTML5 Canvas implementation.
2. **Implementation:** In `web/config_builder.js`, wrap the main container in a parent `div` with `overflow: hidden`. Implement `mousedown` (start pan), `mousemove` (update transform translate), `wheel` (update transform scale) event listeners on the container.


* **Target Files:** `web/config_builder.js`

#### **22. Import Configs (Merge)** (low priority)

* **Problem:** Can only load full sessions, not merge snippets.
* **Instruction:**
1. **Backend:** `config_utils.py` handles parsing.
2. **Frontend (`web/config_builder.js`):** Add "Import JSON" button.
3. **Logic:** On click, open file picker. Read JSON. Iterate through arrays in JSON. Push them into `this.state.config_arrays`. Call `this.renderUI()`.


* **Target Files:** `web/config_builder.js`

#### **23. Pseudo-JSON Nodes (Recursion)** (low priority)

* **Problem:** Advanced. Running a raw JSON workflow as a sub-node.
* **Instruction:**
1. **Modify `json_text_node.py`:** This needs to interface with `comfy.nodes.GraphExecutor`.
2. **Logic:** Treat the input JSON as a "Group Node". Map the inputs of the `SamplerGridTester` to the inputs defined in the JSON. Execute the subgraph. Return the latent.

More info needed on how this could work, would like to see a visual interface for it in the builder UI eventaully. (big job, very low priority)

* **Target Files:** `json_text_node.py`, `sampler_node.py`

#### **24. Combinatorial Randomization** - More Randomization tools - generate x configs from y possibilities and z prompts - (very low priority)

* **Problem:**  Feature. Combinatorial generation logic. Combine random prompts with random loras, fun!
* **Instruction:**
1. **Modify `config_builder_node.py`:** In `generate_config`.
2. **Logic:** Add a "Random Sample" mode. Instead of `itertools.product` (all combos), use `random.sample(all_combos, k=N)`.


* **Target Files:** `config_builder_node.py`

#### **25. Double Click Filter (Isolate)** - (very low priority)

* **Problem:** Tedious to uncheck all other filters.
* **Instruction:**
1. **Modify `resources/logic_ui.js`:** When generating filter tag buttons.
2. **Event:** Add `ondblclick`.
3. **Logic:** On double click, clear all other filters in that category and select only the clicked one. Call `logic_pipeline.update()`.


* **Target Files:** `resources/logic_ui.js`

#### **26. Path Validation in Builder** (DONE)





#### COMPLETED

#### **27. Refresh Model List**  COMPLETED

#### **Show Rejected ASDFeature**  COMPLETED
* **Problem:** Rejected images disappear; hard to undo.
3. **UI:** Added a toggle button for rejected in the Filters menu.

#### **2. Session Load: Disable Auto-Save & Safe Filename**  COMPLETED

#### **6. Copy Favorites To Favorites Subfolders Based On LoRA Sets **  COMPLETED

#### **4. Fix Lora Trigger Append Position** COMPLETED

#### **15/16. Lookahead Caching Switch & Debug** COMPLETED


Add "Don't Append" option to Append Lora Triggerwords To: section. Adds all triggerwords to omit lora triggerwords list. COMPLETED


## Feature: LoRA Lookup From Builder UI. Get metadata, images, url, tags, & more to view quickly from builder in comfyui

## Fix: Manifest doesn't need lora omit triggers list in every item. Save civitai lookup hashes when calculating lora short 256 and looking up lora trigger words. For use later with civit lookup lora / model info. Save all meta-data from lookup in a folder in output/benchmarks/model-data/{modelName} COMPLETED


Prompts manager section in config builder, browse & combine past prompts, analyze favorited tags, auto generate tag tests, COMPLETED


#### **3. Lora/Model Quick Toggle (Bypass)** COMPLETED


#### **8. Visualize Omitted Triggers** COMPLETED


## ~~Fix: Manifest doesn't need lora omit triggers list in every item~~ (DONE - already stripped in create_image_metadata via .pop())
