

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

### **ComfyUI Ultimate Sampler Grid – Development Roadmap**


## Calculate diff - pack into manifest, read in card view at top of card stats, add to sort favorites by lora with lora diff name

## Implement Settings For Lookahead Async Model Cacher

## Feature: LoRA Lookup From Builder UI. Get metadata, images, url, tags, & more to view quickly from builder in comfyui

## ~~Fix: Manifest doesn't need lora omit triggers list in every item~~ (DONE - already stripped in create_image_metadata via .pop())

## Add attention options, xformers, sdpa, sage, flash, etc, option for test all, test all should clear ram & vram between each test.


#### **1. Skip Logic for Optional Inputs**

* **Problem:** The `SamplerGridTester` node cannot reliably detect changes in optional inputs (`optional_model`, `optional_vae`, etc.) because standard `IS_CHANGED` logic relies on input hash comparisons, which don't update for passed objects in optional slots.

 Causes problems with:

 * Grid view using wrong model names
 * Job continuation/skipping/resuming


 * **Instruction:**
1. **Modify `sampler_node.py`:** Implement the `IS_CHANGED` class method. Check if any optional input keys are present in the `kwargs`. If yes, return `float("NaN")` (standard ComfyUI trick to force execution) or a `uuid.uuid4().hex`.
2. **Modify `generation_orchestrator.py`:** Update `check_if_job_completed`. If optional inputs were used, you cannot trust the `manifest.json` history for that specific job. Force a re-run or calculate a hash of the optional input's internal state (e.g., `model.model.diffusion_model`) if possible, otherwise force execution.


* **Target Files:** `sampler_node.py`, `generation_orchestrator.py`

#### **3. Lora/Model Quick Toggle (Bypass)**

* **Problem:** Users delete LoRAs to test without them, losing the config.
* **Instruction:**
1. **Frontend (`web/config_builder.js`):** In the LoRA list UI, add a small checkbox or "eye" icon next to each entry.
2. **Data Handling:** When generating the JSON for `lora_config`, do **not** remove the entry if unchecked. Instead, prepend a specific marker (e.g., `#` or `OFF::`) to the string.
3. **Backend (`config_utils.py`):** In `parse_lora_definition`, add a check: `if part.startswith("#") or part.startswith("OFF::"): continue`. This filters it out at expansion time while keeping it in the UI text.


* **Target Files:** `web/config_builder.js`, `config_utils.py`


#### **7. CivitAI Download Integration**

* **Problem:** Can fetch info but not download files.
* **Instruction:**
1. **Backend:** In `__init__.py`, add route `@routes.post("/configbuilder/download_lora")`.
2. **Logic:** In `lora_utils.py`, write a `download_file(url, filename)` function using `requests`. Ensure it saves to `folder_paths.get_full_path("loras")`.
3. **Frontend:** In `web/config_builder.js`, add a "Download" button next to the CivitAI info result. Call the new API endpoint.


* **Target Files:** `__init__.py`, `lora_utils.py`, `web/config_builder.js`

#### **8. Visualize Omitted Triggers**

* **Problem:** Users don't know which triggers are being removed.
* **Instruction:**
1. **Modify `web/config_builder.js`:** In the function that renders the trigger tags list (e.g., `renderOmitTags` or similar), iterate through the current `omit_list`.
2. **Style:** If a tag in the cloud matches an entry in `omit_list`, apply a specific CSS class (e.g., `style="text-decoration: line-through; opacity: 0.5;"`).


* **Target Files:** `web/config_builder.js`

#### **9. Token-Based Omit Logic**

* **Problem:** Current logic (`if word in tag`) is too broad or too strict.
* **Instruction:**
1. **Modify `trigger_words.py`:** Update `get_filtered_lora_triggers`.
2. **Regex:** Instead of `if omit in tag`, use `re.search(r'\b' + re.escape(omit) + r'\b', tag, re.IGNORECASE)`. This ensures "blue" removes "blue" but not "blueberry".
3. **Tokenization:** Split the tag into words, filter against the omit set, and rejoin.


* **Target Files:** `trigger_words.py`

#### **10. Validation Warning (Omit vs Lookup) - Warn user if omits are added but lookup is off**

* **Problem:** User adds omit words but forgets to enable "Lookup & Append".
* **Instruction:**
1. **Modify `web/config_builder.js`:** inside the `render()` loop.
2. **Logic:** `if (this.state.lora_omit_triggers.length > 0 && !this.state.lookup_triggers)`.
3. **UI:** Render a warning alert div: "⚠️ Omit list is active, but Trigger Lookup is disabled. Omits will have no effect."


* **Target Files:** `web/config_builder.js`

#### **11. Model-Specific Prompts**

* **Problem:** Different models need different trigger words (e.g., "score_9, score_8" for Pony vs "masterpiece" for SD1.5).
* **Instruction:**
1. **Backend:** Add `model_specific_prompts` input to `SamplerGridTester` (dict or JSON).
2. **Orchestrator:** In `generation_orchestrator.py`, inside the loop, check the current `conf["model"]`.
3. **Injection:** Look up the model name in the map. If found, prepend/append the specific tags to `actual_positive_prompt` before encoding.


* **Target Files:** `sampler_node.py`, `generation_orchestrator.py`, `trigger_words.py`

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

#### **14. Cache Trigger Word Placement**

* **Problem:** `trigger_words.py` logic runs every loop iteration.
* **Instruction:**
1. **Modify `trigger_words.py`:** Import `functools.lru_cache`.
2. **Apply:** Decorate `get_filtered_lora_triggers` and `build_prompt_with_triggers` with `@lru_cache(maxsize=128)`. Note: You must ensure arguments are hashable (convert lists to tuples before passing).


* **Target Files:** `trigger_words.py`




#### **17. Menu Refactor (Cog Wheel)**

* **Problem:** Header is cluttered.
* **Instruction:**
1. **Modify `resources/template.html`:** Replace the "Session" button with a `div` class "menu-container" containing an SVG gear icon.
2. **Dropdown:** Create a hidden `div` "menu-dropdown". Move "Cols", "Go To", and "Save/Load" inputs inside it.
3. **Modify `resources/logic_ui.js`:** Add logic to toggle visibility of "menu-dropdown" when the gear is clicked.


* **Target Files:** `resources/template.html`, `resources/logic_ui.js`

#### **18. Optionally Pack workflow into images **

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
2. **Content:** `F: Fullscreen`, `Arrows: Pan`, `+/-: Zoom`, `Space: Scroll`.


* **Target Files:** `resources/logic_ui.js`

#### **21. Virtual DOM Pan/Zoom (Canvas Builder)**

* **Problem:** The Config Builder UI (graph node) needs infinite canvas capabilities for large node graphs.
* **Instruction:**
1. **Scope Check:** If this refers to the *Dashboard*, it's done (`logic_virtual.js`). If this refers to the *Config Builder Node UI* (`web/config_builder.js`), it needs HTML5 Canvas implementation.
2. **Implementation:** In `web/config_builder.js`, wrap the main container in a parent `div` with `overflow: hidden`. Implement `mousedown` (start pan), `mousemove` (update transform translate), `wheel` (update transform scale) event listeners on the container.


* **Target Files:** `web/config_builder.js`

#### **22. Import Configs (Merge)**

* **Problem:** Can only load full sessions, not merge snippets.
* **Instruction:**
1. **Backend:** `config_utils.py` handles parsing.
2. **Frontend (`web/config_builder.js`):** Add "Import JSON" button.
3. **Logic:** On click, open file picker. Read JSON. Iterate through arrays in JSON. Push them into `this.state.config_arrays`. Call `this.renderUI()`.


* **Target Files:** `web/config_builder.js`

#### **23. Pseudo-JSON Nodes (Recursion)**

* **Problem:** Advanced. Running a raw JSON workflow as a sub-node.
* **Instruction:**
1. **Modify `json_text_node.py`:** This needs to interface with `comfy.nodes.GraphExecutor`.
2. **Logic:** Treat the input JSON as a "Group Node". Map the inputs of the `SamplerGridTester` to the inputs defined in the JSON. Execute the subgraph. Return the latent.


* **Target Files:** `json_text_node.py`, `sampler_node.py`

#### **24. Combinatorial Randomization** - More Randomization tools - generate x configs from y possibilities and z prompts

* **Problem:**  Feature. Combinatorial generation logic. Combine random prompts with random loras, fun!
* **Instruction:**
1. **Modify `config_builder_node.py`:** In `generate_config`.
2. **Logic:** Add a "Random Sample" mode. Instead of `itertools.product` (all combos), use `random.sample(all_combos, k=N)`.


* **Target Files:** `config_builder_node.py`

#### **25. Double Click Filter (Isolate)**

* **Problem:** Tedious to uncheck all other filters.
* **Instruction:**
1. **Modify `resources/logic_ui.js`:** When generating filter tag buttons.
2. **Event:** Add `ondblclick`.
3. **Logic:** On double click, clear all other filters in that category and select only the clicked one. Call `logic_pipeline.update()`.


* **Target Files:** `resources/logic_ui.js`

#### **26. Path Validation in Builder**

* **Problem:** Add validation check to builder for lora and model paths
* **Instruction:**
1. **Modify `web/config_builder.js`:** In the rendering loop for models/LoRAs.
2. **Check:** Compare input value against `availableModels` / `availableLoras` arrays.
3. **UI:** If not found, add `border: 1px solid red` and a tooltip "File not found".


* **Target Files:** `web/config_builder.js`



#### COMPLETED

#### **27. Refresh Model List**  COMPLETED

#### **Show Rejected ASDFeature**  COMPLETED
* **Problem:** Rejected images disappear; hard to undo.
3. **UI:** Added a toggle button for rejected in the Filters menu.

#### **2. Session Load: Disable Auto-Save & Safe Filename**  COMPLETED

#### **6. Copy Favorites To Favorites Subfolders Based On LoRA Sets **  COMPLETED

#### **4. Fix Lora Trigger Append Position** COMPLETED

#### **15/16. Lookahead Caching Switch & Debug** COMPLETED