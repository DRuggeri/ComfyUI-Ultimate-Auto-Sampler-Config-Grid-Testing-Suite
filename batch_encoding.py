"""
Batch CLIP Encoding Module
Handles efficient batch encoding of prompts with caching
"""

import torch
import gc
import comfy.model_management


def batch_encode_with_cache(clip_model, prompts, cond_cache, prompt_type="positive", batch_size=16, clip_skip=0):
    """
    Batch encode prompts while checking persistent cache first.
    Only encodes prompts that aren't already cached.
    
    Args:
        clip_model: CLIP model to use for encoding
        prompts: Set or list of prompt strings to encode
        cond_cache: ConditioningCache instance
        prompt_type: "positive" or "negative"
        batch_size: Number of prompts to encode at once
        clip_skip: Number of CLIP layers to skip from the end (0 = use last layer, -1 = skip 1 layer, -2 = skip 2 layers)
        
    Returns:
        dict: Mapping of prompt text to conditioning tensors
    """
    results = {}
    prompts_to_encode = []
    
    # Check cache first
    print(f"[GridTester] 🔍 Checking cache for {len(prompts)} {prompt_type} prompts...")
    for prompt in prompts:
        cached = cond_cache.get(prompt, prompt_type)
        if cached is not None:
            results[prompt] = cached
        else:
            prompts_to_encode.append(prompt)
    
    cache_hits = len(results)
    cache_misses = len(prompts_to_encode)
    
    print(f"[GridTester] 📊 Cache: {cache_hits} hits, {cache_misses} misses")
    
    # Batch encode uncached prompts
    if prompts_to_encode:
        clip_skip_msg = f" (clip_skip={clip_skip})" if clip_skip != 0 else ""
        print(f"[GridTester] 🚀 Batch encoding {len(prompts_to_encode)} {prompt_type} prompts{clip_skip_msg} (batch_size={batch_size})")
        
        # Force model to stay in VRAM
        comfy.model_management.load_models_gpu([clip_model.patcher])
        
        prompts_list = list(prompts_to_encode)
        total_batches = (len(prompts_list) + batch_size - 1) // batch_size
        
        with torch.no_grad():
            for batch_idx in range(0, len(prompts_list), batch_size):
                batch_prompts = prompts_list[batch_idx:batch_idx + batch_size]
                current_batch = (batch_idx // batch_size) + 1
                
                # Encode batch
                for prompt in batch_prompts:
                    try:
                        tokens = clip_model.tokenize(prompt)
                        
                        # ComfyUI's CLIP encode_from_tokens doesn't have a layer parameter
                        # We need to use the CLIP model's layer setter before encoding
                        # Store original layer setting
                        original_layer = None
                        if clip_skip != 0 and hasattr(clip_model.cond_stage_model, 'clip_layer'):
                            original_layer = clip_model.cond_stage_model.clip_layer
                            clip_model.cond_stage_model.set_clip_options({"layer": clip_skip})
                        
                        cond, pooled = clip_model.encode_from_tokens(tokens, return_pooled=True)
                        conditioning = [[cond, {"pooled_output": pooled}]]
                        results[prompt] = conditioning
                        cond_cache.set(prompt, conditioning, prompt_type)
                        
                        # Restore original layer
                        if original_layer is not None:
                            clip_model.cond_stage_model.set_clip_options({"layer": original_layer})
                            
                    except Exception as e:
                        print(f"[GridTester] ⚠️ Failed to encode: {e}")
                        results[prompt] = None
                
                # Progress
                encoded_count = min(batch_idx + batch_size, len(prompts_list))
                if current_batch % 5 == 0 or current_batch == total_batches:
                    print(f"[GridTester]   Batch {current_batch}/{total_batches} | Encoded {encoded_count}/{len(prompts_list)}")
        
        print(f"[GridTester] ✅ Batch encoding complete!")
    
    return results


def batch_encode_prompts(patched_clip, unique_positives, unique_negatives, cond_cache, clip_skip=0):
    """
    Batch encode both positive and negative prompts.
    
    Args:
        patched_clip: Patched CLIP model
        unique_positives: Set of unique positive prompts
        unique_negatives: Set of unique negative prompts
        cond_cache: ConditioningCache instance
        clip_skip: Number of CLIP layers to skip from the end
        
    Returns:
        dict: conditioning_cache with "positive" and "negative" keys
    """
    conditioning_cache = {"positive": {}, "negative": {}}
    
    print(f"[GridTester] 🧠 Found {len(unique_positives)} unique positive prompts")
    print(f"[GridTester] 🧠 Found {len(unique_negatives)} unique negative prompts")
    
    # Use ComfyUI's model management to prevent memory leak warnings during batch encoding
    # The model needs to stay loaded for the entire encoding loop
    with torch.no_grad():
        # Encode all positive prompts
        print(f"[GridTester] 🧠 Encoding {len(unique_positives)} unique positive prompts...")
        conditioning_cache["positive"] = batch_encode_with_cache(
            patched_clip, 
            unique_positives, 
            cond_cache, 
            prompt_type="positive",
            batch_size=16,
            clip_skip=clip_skip
        )

        conditioning_cache["negative"] = batch_encode_with_cache(
            patched_clip, 
            unique_negatives, 
            cond_cache, 
            prompt_type="negative",
            batch_size=16,
            clip_skip=clip_skip
        )
    
    # Save and print cache stats
    if cond_cache is not None:
        cond_cache.save()
        cond_cache.print_stats()
    
    # Final cleanup after all encoding is complete
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    print(f"[GridTester] ✅ All prompts pre-encoded!")
    print(f"[GridTester] 💾 Cache size: {len(conditioning_cache['positive'])} positive, {len(conditioning_cache['negative'])} negative")
    
    return conditioning_cache