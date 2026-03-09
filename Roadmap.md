

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


# Run this after lots of updates & before starting a new convo

## Please update ProjectStructure.md to be better structured and fixed up for having all relevant AI Notes in it that will help and assist AI to develop this project further. Add your findings, file system notes, important considerations and more to it and make sure its up to date and full of helpful info.


#  **ComfyUI Ultimate Sampler Grid – Development Roadmap** 


## Bug: If we omit entries from the Builder UI's config_json output the manifest.json files lose that data and entries that are toggled off will be lost when loading the session from the manifest file. We should

## Feature idea, Config Section Presets, Saveable, Nameable & Loadable or Importable/Mergeable presets for each section, Prompts, Models, Text Encoders, Vaes, Loras, Trigger Omit, Upscalers. Would make mixing and matching and setting up new configs easier & more customizable.


## The Dashboard Session Load Option in the cog settings topbar modal needs sort by most recent and session search feature like how the Builder UI Session Load has.

## Feature: Add builder UI option to pack pure nodes like REVISE copy as comfy nodes into every image always.

## Issue: Distributed Worker bug with save models to worker, not working

## Small bug, centering zoom doesn't perfectly fit the images into the canvas, I think it doesnt account for the topbar and bottom smartjson bar sizes.

## Vae settings in the Builder UI passed to sampler gen orchestrator through the config_json need to override the hf_remote setting in the sampler node input selection. All settings should be override from the Builder UI config_json, it should take first priority over any setting in the sampler node as we are phasing out the sampler node settings completely eventually. (Fix needs testing)

## Issue: If running a job in one tab and reviewing images from a past session with the Dashboard in another tab, the Dashboard receives updates across all tabs and force-loads the Dashboard to the currently running session. (Fix needs testing)

## The batch encoding step lost its ability to stop everything during its run loop. If the user clicks cancel job in ComfyUI it needs to stop the entire loop, not just one encoding, like how the generation loop works. Its incredibly inconventient to have to wait for it to finish on large runs if you need to cancel early. (Fix needs testing)

## Feature: Drag and drop re-organzie loras, models, text encoders, vaes. This would make changing their run order and lora_tag append order much easier to control. (needs more testing/fixing)

## Jobs don't generate prompts in the order they're written in the array, it's mildly inconvenient. Lets fix that and make it run in order from top to bottom of the array.

## Custom Job Resume / Skipping - Start At Job # Option

## Batch Encoding could use with implementing the smart, look ahead, caching system we built for lora swapping. 

## bug fix, the Builder UI is very slow to update when first starting, adding models, adding loras, a few other things, we need to check it and optimize it to load and respond faster. (Needs more improvement)




#### **12. Arrays in LoRA Weights** Integrated but needs adding to the Builder UI

Builder UI could have a + button right next to model strength text input (on its right side) to make it easy to add a compare different lora strengths. If activated it should add an additonal slider, or two sliders if 🔒 Lock Model & CLIP Strength Together is deactivated, for each time they click +. If a lora has a multiple strength array, the preview json and py node json_output should duplicate the full config for that run for each entry with the only difference being each lora strength. If multiple loras have multiple arrays it needs to output a cartesian of an each for each of all lora strenth combos. 



## Bug Fix: Batch Encoding Runs Before Job Skip/Continue/Resume check and will encode everything again even if it's already been completed. Also Continue/Resume needs optional inputs to be tracked. We need to track connected node changes from each of the optional inputs, we could also use this step to save the workflow to the benchmark/session folder and compare the last run workflow to the current to track node changes and determine changes and also integrate currenly missing from optional inputs such as model, loras, prompts, etc. (Needs testing)


#### **7. CivitAI Download Integration** (low priority)
A button in the builder UI to pack short sha256 into config with an explanation that it can be used to share or move an Ultimate Sampler Config Tester workflow and allow for downloading all models and loras in the workflow from civitAI with a few simple easy clicks. lora_utils has calculate civit model has function in it. dropdown configurable options for where to store each file type.

#### **9. Tag/Token-Based Omit Logic** (Needs testing)

#### **10. Validation Warning (Omit vs Lookup) - Warn user if omits are added but lookup is off** (low priority) (Needs testing)


#### **11. Model-Specific Prompts** (Needs improvement)

#### **13. Real-Time ETA** (Needs improvement, doesnt consider distribtion times, and upscale jobs kind of throw off ETA, seconds/job counter and dashboard image/manifest saved "duration" metric )

#### **14. Cache Trigger Word Placement** (low priority)
* **Problem:** `trigger_words.py` logic runs every loop iteration.
* **Target Files:** `trigger_words.py`


#### **20. Hotkeys Reference List** (Needs updating)


#### **22. Import Configs (Merge)** (low priority)

* **Problem:** Can only load full sessions, not merge snippets.


#### **23. Pseudo-JSON Nodes (Recursion)** (low priority)
* **Problem:** Advanced. Running a raw JSON workflow as a sub-node. Inserting any node into any part of the genereation would make this tool have an immense customizability increase.
More info needed on how this could work, would like to see a visual interface for it in the builder UI eventaully. (big job, very low priority)


#### **24. Combinatorial Randomization** - More Randomization tools - generate x configs from y possibilities and z prompts - (very low priority)

* **Problem:**  Feature. Combinatorial generation logic. Combine random prompts with random loras, fun!
