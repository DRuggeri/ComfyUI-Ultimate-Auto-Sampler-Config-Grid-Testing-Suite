

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


Check Roadmap.md for some tasks and do them. don't do any marked as (low priority). If you think you can do the ones marked as New to-do items, needs more info/explaining/numbering those are good. There is some info on the project in README.md and info on the file structure and notes on each files functions in the ProjectStructure.md 


### **ComfyUI Ultimate Sampler Grid – Development Roadmap**



## When you click a sampler or scheduler in the dropdown it should add it to the list right away.







## Save/Load/Import (Merge) Prompts. (With settable unique naming option) Load should offer a searchable dropdown menu for all past saved prompts. Let's store this data in a outputs/benchmarks/PromptsData folder. Each prompt/save should be its own file.


## Easy Feature: Add Esc key close to Revise modal and add X to close in top right of modal in Dashboard and the Lookup LoRA Metadata from CivitAI, and omit lora triggerwords modals in the Builder UI.  Also
Replace revise button in dashboard with edit emoji 



## Bug Fix: Batch Encoding Runs Before Job Skip/Continue/Resume check and will encode everything again even if it's already been completed. Also Continue/Resume needs optional inputs to be tracked. We need to track connected node changes from each of the optional inputs, we could also use this step to save the workflow to the benchmark/session folder and compare the last run workflow to the current to track node changes and determine changes and also integrate currenly missing from optional inputs such as model, loras, prompts, etc.


# Needs Testing: Batch encoding doesnt seem to be working for optional inputs possibly, or maybe its very large models, I get loading messages after every single encoding instead of once per batch and it takes a long time (low priority)
Symptom: each encoding fills the GPU more and more and eventually it becomes 0 usable, 0 loaded all offloaded.
loaded partially; 5585.34 MB usable, 5543.55 MB loaded, 628.32 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
loaded partially; 5569.51 MB usable, 5527.72 MB loaded, 644.90 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
loaded partially; 5553.58 MB usable, 5511.79 MB loaded, 660.34 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
loaded partially; 5537.65 MB usable, 5495.86 MB loaded, 676.40 MB offloaded, 41.79 MB buffer reserved, lowvram patches: 0
maybe we need to force encodings to offload to ram?

## Add attention options, xformers, sdpa, sage, flash, etc, option for test all, test all should clear ram & vram between each test.

# Deeper explained items to-do list

#### **1. Skip Logic for Optional Inputs**

* **Problem:** The `SamplerGridTester` node cannot reliably detect changes in optional inputs (`optional_model`, `optional_vae`, etc.) because standard `IS_CHANGED` logic relies on input hash comparisons, which don't update for passed objects in optional slots.

 * Job continuation/skipping/resuming




#### **7. CivitAI Download Integration** (low priority)
A button in the builder UI to pack short sha256 into config with an explanation that it can be used to share or move an Ultimate Sampler Config Tester workflow and allow for downloading all models and loras in the workflow from civitAI with a few simple easy clicks. lora_utils has calculate civit model has function in it. dropdown configurable options for where to store each file type.


* **Target Files:** `__init__.py`, `lora_utils.py`, `web/config_builder.js`


#### **9. Tag/Token-Based Omit Logic** DONE


#### **10. Validation Warning (Omit vs Lookup) - Warn user if omits are added but lookup is off** (low priority) DONE


#### **11. Model-Specific Prompts**

* **Problem:** Different models need different trigger words (e.g., "score_9, score_8" for Pony vs "masterpiece" for SD1.5).
* **Instruction:**
1. **Backend:** Add `model_specific_prompts` input to `SamplerGridTester` (dict or JSON).
2. **Orchestrator:** In `generation_orchestrator.py`, inside the loop, check the current `conf["model"]`.
3. **Injection:** Look up the model name in the map. If found, prepend/append the specific tags to `actual_positive_prompt` before encoding.

add options for append to start or end of prompt.

* **Target Files:** `sampler_node.py`, `generation_orchestrator.py`, `trigger_words.py` `batch_encoder.py`

#### **12. Arrays in LoRA Weights**

* **Problem:** Cannot grid search LoRA weights like `lora.safetensors:[0.5, 0.8]:1.0`.
* **Instruction:**
1. **Modify `config_utils.py`:** Update `expand_configs`.
2. **Logic:** Detect brackets `[]` inside the LoRA string part. If found, treat it as a list.
3. **Expansion:** Use `itertools.product` to generate separate config entries for each weight in the array (e.g., one config with 0.5, one with 0.8).


* **Target Files:** `config_utils.py`

#### **13. Real-Time ETA**

* **Problem:** ETA only prints to server console.
* **Instruction:**
1. **Backend (`generation_orchestrator.py`):** In `print_generation_progress`, calculate ETA. Use `PromptServer.instance.send_sync("ultimate_grid.progress", { eta: "..." })` to send it to the frontend.
2. **Frontend (`resources/logic_events.js`):** Add a listener for `ultimate_grid.progress`.
3. **UI:** Update a DOM element (e.g., `#header-eta`) in `template.html`.


* **Target Files:** `generation_orchestrator.py`, `resources/logic_events.js`, `resources/template.html`




#### **17. Menu Refactor (Cog Wheel)**

* **Problem:** Header is cluttered.
* **Instruction:**
1. **Modify `resources/template.html`:** Replace the "Session" button with a `div` class "menu-container" containing an SVG gear icon.
2. **Dropdown:** Create a hidden `div` "menu-dropdown". Move "Cols", "Go To", and "Save/Load" inputs inside it.
3. **Modify `resources/logic_ui.js`:** Add logic to toggle visibility of "menu-dropdown" when the gear is clicked.

Move COLS input into session popup modal, change session to cogwheel, change filters to filter icon,

* **Target Files:** `resources/template.html`, `resources/logic_ui.js`

#### **18. Optionally Pack workflow into images ** (low priority)

* **Problem:** Pack workflow into images optionally 
* **Instruction:**
1. **Modify `image_generation.py`:** In `save_image_to_disk`.
2. **Implementation:** Use `PIL.PngImagePlugin.PngInfo`. Create a `PngInfo` object. Add `info.add_text("prompt", json.dumps(prompt))`. Pass this `pnginfo` to `image.save()`.
3. **Data Source:** Ensure the raw prompt/workflow is passed down from `sampler_node.py`.


* **Target Files:** `image_generation.py`, `generation_orchestrator.py`


#### **20. Hotkeys Reference List**

* **Problem:** Users don't know shortcuts.
* **Instruction:**
1. **Modify `resources/logic_ui.js`:** In the function that renders the settings menu, append a table.
2. **Content:** `F: Fullscreen`, `Arrows: Pan`, `+/-: Zoom`, `Space: Scroll`. `0 Key Resets Zoom & Pan` Etc

* **Target Files:** `resources/logic_ui.js`

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
