"""
Model Cache System with THREE-TIER LORA CACHING

Tier 1: LoRA File Cache - Raw LoRA files (A, B, C)
Tier 2: Incremental Patched Model Cache - Partial application states (A+B+C, A+B+C+D)
Tier 3: Final Patched Model Cache - Complete results

This enables INCREMENTAL LoRA APPLICATION:
- If you have A+B+C+D cached and need A+B+C+D+E
- Just apply E on top of the cached A+B+C+D state
- Massive speedup when testing variations of large LoRA stacks
"""

import gc
import time
import torch
import hashlib
import threading
from typing import Dict, Tuple, Optional, Any, List
from collections import OrderedDict


class ModelCache:
    """
    Three-tier LoRA caching system with incremental patching.
    Thread-safe for async background patching.
    """
    
    def __init__(self, max_models=2, max_clips=3, max_lora_sets=3, max_lora_files=20,
                 enable_incremental=True, enable_preload=True, async_preload=True, 
                 cache_device='cuda', verbose=True):
        """
        Initialize the model cache.
        """
        self.max_models = max_models
        self.max_clips = max_clips
        self.max_lora_sets = max_lora_sets
        self.max_lora_files = max_lora_files
        self.enable_incremental = enable_incremental
        self.enable_preload = enable_preload
        self.async_preload = async_preload
        self.cache_device = cache_device
        self.verbose = verbose
        
        if cache_device not in ['cuda', 'cpu']:
            raise ValueError(f"cache_device must be 'cuda' or 'cpu', got '{cache_device}'")
        
        # Caches
        self.base_models = OrderedDict()
        self.clip_models = OrderedDict()
        self.lora_models = OrderedDict()  # Complete results
        self.lora_files = OrderedDict()   # Raw files
        
        # Locks for thread safety
        self.cache_lock = threading.RLock()
        self.preload_lock = threading.Lock()
        self.preload_thread = None
        
        # Track WHAT is currently being loaded in background
        self.preloading_key = None 
        
        # Track last patched state for incremental application
        self.last_patched_state = None  # (base_model_name, lora_list, patched_model, patched_clip)
        
        # Pre-load storage
        self.preloaded_base = None
        self.preloaded_clip = None
        self.preloaded_lora = None
        
        # Statistics
        self.stats = {
            "base_hits": 0, "base_misses": 0, "base_disk_loads": 0,
            "clip_hits": 0, "clip_misses": 0, "clip_disk_loads": 0,
            "lora_hits": 0, "lora_misses": 0, "lora_disk_loads": 0,
            "lora_file_hits": 0, "lora_file_misses": 0, "lora_file_disk_loads": 0,
            "incremental_hits": 0,        
            "incremental_loras_skipped": 0,  
            "preload_successes": 0, "preload_failures": 0, "async_preloads": 0,
            "thread_joins": 0,
            "evictions": 0,
            "total_load_time": 0.0, "cache_load_time": 0.0, "disk_load_time": 0.0,
            "vram_to_ram_moves": 0, "ram_to_vram_moves": 0
        }
        
        # NEW: Lookahead scheduling
        self.key_last_usage = {}  # Map of {cache_key: last_job_index}
        self.current_job_index = -1
        self.smart_cache_enabled = False

        self._log("🚀 Model Cache initialized (Async GPU Preload + Thread-Safe + Normalization)", force=True)
   
    def register_schedule(self, expanded_configs: List[Dict]):
        """
        Analyze the generation schedule to determine when each config is last needed.
        """
        self.key_last_usage.clear()
        self.smart_cache_enabled = True
        
        print(f"[ModelCache] 🔮 Analyzing {len(expanded_configs)} jobs for Smart Caching...")
        
        for idx, conf in enumerate(expanded_configs):
            model = conf.get("model")
            lora = conf.get("lora_expanded", "None")
            
            # Generate the key exactly how the cache expects it
            # Note: We use the internal helper to ensure matching hashes
            key = self._get_lora_cache_key(model, lora)
            
            # Store the LATEST index this key is seen
            self.key_last_usage[key] = idx
            
        print(f"[ModelCache] 🔮 Smart Cache Strategy: Identified {len(self.key_last_usage)} unique LoRA combinations.")

    def set_current_step(self, index: int):
        """Update the current progress through the generation list."""
        self.current_job_index = index
    def set_current_step(self, index: int):
        """Update the current progress through the generation list."""
        self.current_job_index = index

    def _log(self, message: str, force: bool = False):
        if self.verbose or force:
            print(f"[ModelCache] {message}")

    # =========================================================================
    #  Helper: Strict Key Normalization
    # =========================================================================
    def _normalize_key(self, key: str) -> str:
        """Normalize file paths to ensure consistent cache keys (fix Windows backslashes)."""
        if not key: return "None"
        return key.replace("\\", "/").strip()
    
    # =========================================================================
    #  Incremental LoRA Patching Logic
    # =========================================================================
    
    def _parse_lora_list(self, lora_string: str) -> List[Tuple[str, float, float]]:
        """Parse LoRA string into list of (path, model_strength, clip_strength)."""
        if not lora_string or lora_string == "None":
            return []
        
        result = []
        parts = [p.strip() for p in lora_string.split('+')]
        
        for part in parts:
            if not part:
                continue
            
            components = part.split(':')
            path = components[0].strip().replace('\\', '/')
            
            model_str = 1.0
            clip_str = 1.0
            
            if len(components) >= 2:
                try:
                    model_str = float(components[1])
                    clip_str = model_str
                except ValueError:
                    pass
            
            if len(components) >= 3:
                try:
                    clip_str = float(components[2])
                except ValueError:
                    pass
            
            result.append((path, model_str, clip_str))
        
        return result
    
    def _lora_lists_match_prefix(self, list1: List, list2: List) -> int:
        """Check how many LoRAs match from the start of both lists."""
        match_count = 0
        for i in range(min(len(list1), len(list2))):
            if list1[i] == list2[i]:
                match_count += 1
            else:
                break
        return match_count
    
    def check_incremental_cache(self, base_model_name: str, lora_string: str) -> Optional[Tuple[Any, Any, int]]:
        """
        Check if we can use incremental patching.
        """
        if not self.enable_incremental:
            return None
            
        norm_model = self._normalize_key(base_model_name)
        
        with self.cache_lock:
            if self.last_patched_state is None:
                return None
            
            cached_base, cached_loras, cached_model, cached_clip = self.last_patched_state
        
        # Must be same base model
        if cached_base != norm_model:
            return None
        
        # Parse requested LoRAs
        requested_loras = self._parse_lora_list(lora_string)
        
        # Check how many match from the start
        match_count = self._lora_lists_match_prefix(cached_loras, requested_loras)
        
        # Need at least some overlap to be useful
        if match_count == 0:
            return None
        
        # If exact match, this should be caught by full result cache
        if match_count == len(cached_loras) and match_count == len(requested_loras):
            return None
        
        # If requested is a PREFIX of cached (e.g., need A+B+C but have A+B+C+D+E)
        if match_count == len(requested_loras) and len(requested_loras) < len(cached_loras):
            return None
        
        # If cached is a PREFIX of requested (e.g., have A+B+C, need A+B+C+D+E)
        if match_count == len(cached_loras) and len(requested_loras) > len(cached_loras):
            self.stats["incremental_hits"] += 1
            self.stats["incremental_loras_skipped"] += match_count
            
            lora_names = " + ".join([path.split('/')[-1] for path, _, _ in cached_loras])
            self._log(f"⚡ INCREMENTAL HIT: Reusing {match_count} cached LoRAs ({lora_names[:50]}...)")
            
            return (cached_model, cached_clip, match_count)
        
        return None
    
    def update_incremental_cache(self, base_model_name: str, lora_string: str, model, clip):
        """Update the incremental cache with the latest patched state."""
        if not self.enable_incremental:
            return
        
        norm_model = self._normalize_key(base_model_name)
        lora_list = self._parse_lora_list(lora_string)
        
        with self.cache_lock:
            self.last_patched_state = (norm_model, lora_list, model, clip)
    
    # =========================================================================
    #  LoRA File Cache (Raw Files)
    # =========================================================================
    
    def _clean_lora_path(self, lora_part: str) -> str:
        """Extract clean path from LoRA string."""
        clean_part = lora_part.split(':')[0]
        clean_part = clean_part.replace('\\', '/').strip()
        return clean_part
    
    def get_lora_file(self, lora_part_string: str) -> Optional[Dict]:
        """Get raw LoRA file from cache."""
        with self.cache_lock:
            start_time = time.time()
            clean_path = self._clean_lora_path(lora_part_string)
            
            if clean_path in self.lora_files:
                self.lora_files.move_to_end(clean_path)
                self.stats["lora_file_hits"] += 1
                elapsed = time.time() - start_time
                self.stats["cache_load_time"] += elapsed
                
                filename = clean_path.split('/')[-1]
                self._log(f"✅ LoRA FILE HIT: {filename} ({elapsed*1000:.1f}ms)")
                
                return self.lora_files[clean_path]
            
            self.stats["lora_file_misses"] += 1
            return None
    
    def put_lora_file(self, lora_part_string: str, state_dict: Dict):
        """Store raw LoRA file in cache."""
        clean_path = self._clean_lora_path(lora_part_string)
        
        try:
            if isinstance(state_dict, dict):
                cpu_dict = {k: v.to('cpu') if hasattr(v, 'to') else v 
                           for k, v in state_dict.items()}
            else:
                cpu_dict = state_dict
            
            with self.cache_lock:
                self.lora_files[clean_path] = cpu_dict
                self.lora_files.move_to_end(clean_path)
                
                filename = clean_path.split('/')[-1]
                self._log(f"💾 Stored LoRA file: {filename} (cache: {len(self.lora_files)}/{self.max_lora_files})")
                
                while len(self.lora_files) > self.max_lora_files:
                    evicted_path, evicted_data = self.lora_files.popitem(last=False)
                    self._evict_lora_file(evicted_path, evicted_data)
                
        except Exception as e:
            self._log(f"⚠️ Failed to cache LoRA file: {e}")
    
    def _evict_lora_file(self, path: str, data):
        """Evict LoRA file from cache."""
        self.stats["evictions"] += 1
        filename = path.split('/')[-1]
        self._log(f"🗑️  EVICTING LoRA file: {filename}")
        if data is not None:
            del data
        gc.collect()
    
    def record_lora_file_disk_load(self, load_time: float):
        """Record LoRA file disk load."""
        self.stats["lora_file_disk_loads"] += 1
        self.stats["disk_load_time"] += load_time
        self.stats["total_load_time"] += load_time
    
    # =========================================================================
    #  LoRA Patched Model Cache (Complete Results)
    # =========================================================================
    
    def _get_lora_cache_key(self, model_name: str, lora_string: str) -> str:
        """Generate cache key for complete LoRA result."""
        # Normalize inputs immediately
        norm_model = self._normalize_key(model_name)
        
        if not lora_string or lora_string == "None":
            return hashlib.md5(f"{norm_model}:None".encode()).hexdigest()[:16]
        
        try:
            parts = [p.strip() for p in lora_string.split('+')]
            normalized_parts = []
            
            for part in parts:
                if not part:
                    continue
                    
                components = part.split(':')
                # Normalize file path inside LoRA string
                name = self._normalize_key(components[0])
                
                model_str = 1.0
                clip_str = 1.0
                
                if len(components) >= 2:
                    try:
                        val = float(components[1])
                        model_str = val
                        clip_str = val
                    except ValueError:
                        pass
                
                if len(components) >= 3:
                    try:
                        clip_str = float(components[2])
                    except ValueError:
                        pass
                
                normalized_parts.append(f"{name}:{model_str:.2f}:{clip_str:.2f}")
            
            normalized_lora_string = " + ".join(normalized_parts)
            
        except Exception as e:
            normalized_lora_string = self._normalize_key(lora_string)
        
        return hashlib.md5(f"{norm_model}:{normalized_lora_string}".encode()).hexdigest()[:16]
    
    def get_lora_model(self, model_name: str, lora_string: str) -> Optional[Tuple[Any, Any]]:
        """Get complete LoRA result from cache."""
        
        cache_key = self._get_lora_cache_key(model_name, lora_string)
        thread_to_join = None
        
        # STEP 1: Check if we need to wait
        with self.cache_lock:
             if self.preloading_key == cache_key and self.preload_thread and self.preload_thread.is_alive():
                 thread_to_join = self.preload_thread
                 
        if thread_to_join:
             lora_short = lora_string[:30] + "..." if len(lora_string) > 30 else lora_string
             self._log(f"⏳ Waiting for background preload to finish: {lora_short}")
             thread_to_join.join()
             with self.cache_lock:
                 self.stats["thread_joins"] += 1

        # STEP 2: Acquire lock and check cache
        with self.cache_lock:
            start_time = time.time()
            
            lora_display = (lora_string[:50] + "...") if len(lora_string) > 50 else lora_string
            
            # Check pre-loaded bucket
            if self.preloaded_lora and self.preloaded_lora[0] == cache_key:
                model, clip = self.preloaded_lora[1:]
                self.stats["lora_hits"] += 1
                elapsed = time.time() - start_time
                self.stats["cache_load_time"] += elapsed
                self._log(f"⚡ LORA RESULT HIT (PRE-LOADED): {lora_display} ({elapsed*1000:.1f}ms)")
                
                # NOTE: Already moved to compute device in worker!
                # model = self._move_to_compute_device(model) # Causes GPU thread conflict crashes 
                # clip = self._move_to_compute_device(clip)  # Causes GPU thread conflict crashes
                
                self.lora_models[cache_key] = (model, clip)
                self.lora_models.move_to_end(cache_key)
                self.preloaded_lora = None
                self.preloading_key = None # Clear key
                self.stats["preload_successes"] += 1
                
                return (model, clip)
            
            # Check main cache
            if cache_key in self.lora_models:
                model, clip = self.lora_models[cache_key]
                self.lora_models.move_to_end(cache_key)
                self.stats["lora_hits"] += 1
                elapsed = time.time() - start_time
                self.stats["cache_load_time"] += elapsed
                self._log(f"✅ LORA RESULT HIT: {lora_display} ({elapsed*1000:.1f}ms)")
                
                    # model = self._move_to_compute_device(model)  # Causes GPU thread conflict crashes 
                    # clip = self._move_to_compute_device(clip)  # Causes GPU thread conflict crashes 
                   
                
                return (model, clip)
            
            # Cache miss
            self.stats["lora_misses"] += 1
            return None
    
    def put_lora_model(self, model_name: str, lora_string: str, model, clip):
        """Store complete LoRA result in cache."""

        # ==== NEW: Smart Lookahead Check ====
        cache_key = self._get_lora_cache_key(model_name, lora_string)
        
        if self.smart_cache_enabled:
            last_needed_at = self.key_last_usage.get(cache_key, -1)
            
            # If the last time we need this is NOW (or in the past), 
            # there is ZERO point in caching it.
            if last_needed_at <= self.current_job_index:
                if self.verbose:
                    lora_short = lora_string[:30] + "..." if len(lora_string) > 30 else lora_string
                    print(f"[ModelCache] 🚫 Smart Skip: Not caching {lora_short} (Last use: Step {last_needed_at})")
                return
        # ====================================
        
        with self.cache_lock:
            cache_key = self._get_lora_cache_key(model_name, lora_string)
            
            model = self._move_to_cache_device(model)
            clip = self._move_to_cache_device(clip)
            
            if cache_key in self.lora_models:
                self.lora_models[cache_key] = (model, clip)
                self.lora_models.move_to_end(cache_key)
                return
            
            self.lora_models[cache_key] = (model, clip)
            lora_display = (lora_string[:50] + "...") if len(lora_string) > 50 else lora_string
            self._log(f"💾 Stored LoRA result: {lora_display} (cache: {len(self.lora_models)}/{self.max_lora_sets})")
            
            while len(self.lora_models) > self.max_lora_sets:
                evicted_key, evicted_data = self.lora_models.popitem(last=False)
                self._evict_lora_model(evicted_key, evicted_data)
    
    def _evict_lora_model(self, cache_key: str, model_data):
        """Evict LoRA result from cache."""
        self.stats["evictions"] += 1
        self._log(f"🗑️  EVICTING LoRA result (key: {cache_key[:8]}...)")
        if model_data is not None:
            del model_data
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    # =========================================================================
    #  Pre-loading Methods (Async)
    # =========================================================================

    def preload_lora_model(self, model_name: str, lora_string: str, loader_func, *args, **kwargs):
        """
        Asynchronously pre-patch a model with LoRAs.
        """
        if not self.enable_preload: return
        
        with self.cache_lock:
            cache_key = self._get_lora_cache_key(model_name, lora_string)
            if cache_key in self.lora_models: return
            if self.preloaded_lora and self.preloaded_lora[0] == cache_key: return
            
            # If we are already loading this specific key, don't restart
            if self.preloading_key == cache_key and self.preload_thread and self.preload_thread.is_alive():
                return

        # If loading something ELSE, wait for it to finish first
        if self.preload_thread and self.preload_thread.is_alive():
            self.preload_thread.join()

        if self.async_preload:
            # Set the key BEFORE starting thread
            self.preloading_key = cache_key
            
            def _async_load():
                try:
                    with self.preload_lock:
                        # Double check if still needed
                        with self.cache_lock:
                            if self.preloaded_lora and self.preloaded_lora[0] == cache_key: return

                        self._log(f"⏳ PRE-PATCHING LORA (Async): {lora_string[:30]}...")
                        # Run the patching
                        result = loader_func(*args, **kwargs)
                        
                        # load_loras returns (model, clip, should_skip)
                        if result and len(result) >= 2:
                            model, clip = result[0], result[1]
                            
                            # CRITICAL CHANGE: Move to COMPUTE device (GPU) immediately
                            # This pays the VRAM transfer cost in the background thread
                    # model = self._move_to_compute_device(model)  # Causes GPU thread conflict crashes 
                    # clip = self._move_to_compute_device(clip)  # Causes GPU thread conflict crashes 
                   
                            
                            with self.cache_lock:
                                self.preloaded_lora = (cache_key, model, clip)
                            
                            self._log(f"✅ ASYNC PRE-PATCH COMPLETE (ON GPU)")
                except Exception as e:
                    self._log(f"❌ ASYNC PRE-PATCH FAILED: {e}")
                # Note: We do NOT clear self.preloading_key here to avoid race conditions.
                # get_lora_model cleans it up.

            self.preload_thread = threading.Thread(target=_async_load, daemon=True)
            self.preload_thread.start()
        else:
            # Sync fallback
            try:
                result = loader_func(*args, **kwargs)
                if result and len(result) >= 2:
                     with self.cache_lock:
                        self.preloaded_lora = (cache_key, result[0], result[1])
            except Exception as e:
                pass
    
    def preload_base_model(self, model_name: str, loader_func, *args, **kwargs):
        """Pre-load base model (sync or async)."""
        if not self.enable_preload:
            return
        
        norm_name = self._normalize_key(model_name)
        
        with self.cache_lock:
            if norm_name in self.base_models: return
            if self.preloaded_base and self.preloaded_base[0] == norm_name: return
            # Check if currently loading
            if self.preloading_key == norm_name and self.preload_thread and self.preload_thread.is_alive(): return
        
        if self.preload_thread and self.preload_thread.is_alive():
            self.preload_thread.join()
        
        def _async_load(): 
            try:
                with self.preload_lock:
                    start_time = time.time()
                    self._log(f"⏳ PRE-LOADING (async): {norm_name}")
                    
                    model, clip, vae = loader_func(*args, **kwargs)
                    
                    # CRITICAL CHANGE: Move to COMPUTE device (GPU) immediately
                    # model = self._move_to_compute_device(model)  # Causes GPU thread conflict crashes 
                    # clip = self._move_to_compute_device(clip)  # Causes GPU thread conflict crashes 
                    # vae = self._move_to_compute_device(vae)  # Causes GPU thread conflict crashes 
                    
                    elapsed = time.time() - start_time
                    self.stats["disk_load_time"] += elapsed
                    self.stats["base_disk_loads"] += 1
                    
                    with self.cache_lock:
                        self.preloaded_base = (norm_name, model, clip, vae)
                    
                    self._log(f"✅ ASYNC PRELOAD COMPLETE (ON GPU): {norm_name} ({elapsed:.2f}s)")
                    
            except Exception as e:
                self.stats["preload_failures"] += 1
                self._log(f"❌ ASYNC PRELOAD FAILED: {norm_name} - {e}")
        
        if self.async_preload:
            self.preloading_key = norm_name
            self.stats["async_preloads"] += 1
            self.preload_thread = threading.Thread(target=_async_load, daemon=True)
            self.preload_thread.start()
        else:
            _async_load()
    
    def record_disk_load(self, is_base_model: bool, load_time: float):
        """Record disk load operation."""
        if is_base_model:
            self.stats["base_disk_loads"] += 1
        else:
            self.stats["lora_disk_loads"] += 1
        self.stats["disk_load_time"] += load_time
        self.stats["total_load_time"] += load_time
    
    def clear(self):
        """Clear all caches."""
        self._log("🧹 Clearing all caches...", force=True)
        
        if self.preload_thread and self.preload_thread.is_alive():
            self.preload_thread.join(timeout=30)
        
        with self.cache_lock:
            for name, data in list(self.base_models.items()):
                self._evict_base_model(name, data)
            self.base_models.clear()
            
            for key, data in list(self.clip_models.items()):
                self._evict_clip_model(key, data)
            self.clip_models.clear()
            
            for key, data in list(self.lora_models.items()):
                self._evict_lora_model(key, data)
            self.lora_models.clear()
            
            for path, data in list(self.lora_files.items()):
                self._evict_lora_file(path, data)
            self.lora_files.clear()
            
            self.preloaded_base = None
            self.preloaded_clip = None
            self.preloaded_lora = None
            self.last_patched_state = None
            self.preloading_key = None
        
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        self._log("✅ Cache cleared", force=True)
    
    # =========================================================================
    #  Base Model Methods
    # =========================================================================
    
    def get_base_model(self, model_name: str) -> Optional[Tuple[Any, Any, Any]]:
        """Get base model from cache."""
        norm_name = self._normalize_key(model_name)
        
        thread_to_join = None
        
        # STEP 1: Check if we need to wait
        with self.cache_lock:
            if self.preloading_key == norm_name and self.preload_thread and self.preload_thread.is_alive():
                 thread_to_join = self.preload_thread

        if thread_to_join:
             self._log(f"⏳ Waiting for background preload to finish: {norm_name}...")
             thread_to_join.join()
             with self.cache_lock:
                 self.stats["thread_joins"] += 1

        # STEP 2: Proceed with cache retrieval
        with self.cache_lock:
            start_time = time.time()
            
            if self.preloaded_base and self.preloaded_base[0] == norm_name:
                model, clip, vae = self.preloaded_base[1:]
                self.stats["base_hits"] += 1
                elapsed = time.time() - start_time
                self.stats["cache_load_time"] += elapsed
                self._log(f"⚡ BASE MODEL HIT (PRE-LOADED): {norm_name} ({elapsed*1000:.1f}ms)")
                
                # Already on GPU from worker
                    # model = self._move_to_compute_device(model)  # Causes GPU thread conflict crashes 
                    # clip = self._move_to_compute_device(clip)  # Causes GPU thread conflict crashes 
                    # vae = self._move_to_compute_device(vae)  # Causes GPU thread conflict crashes 
                    
                
                self.base_models[norm_name] = (model, clip, vae)
                self.base_models.move_to_end(norm_name)
                self.preloaded_base = None
                self.preloading_key = None
                self.stats["preload_successes"] += 1
                
                return (model, clip, vae)
            
            if norm_name in self.base_models:
                model, clip, vae = self.base_models[norm_name]
                self.base_models.move_to_end(norm_name)
                self.stats["base_hits"] += 1
                elapsed = time.time() - start_time 
                self.stats["cache_load_time"] += elapsed
                self._log(f"✅ BASE MODEL HIT: {norm_name} ({elapsed*1000:.1f}ms)")
                
                    # model = self._move_to_compute_device(model)  # Causes GPU thread conflict crashes 
                    # clip = self._move_to_compute_device(clip)  # Causes GPU thread conflict crashes 
                    # vae = self._move_to_compute_device(vae)  # Causes GPU thread conflict crashes 
                    
                
                return (model, clip, vae)
            
            self.stats["base_misses"] += 1
            return None
    
    def put_base_model(self, model_name: str, model, clip, vae):
        """Store base model in cache."""
        norm_name = self._normalize_key(model_name)
        with self.cache_lock:
            model = self._move_to_cache_device(model)
            clip = self._move_to_cache_device(clip)
            vae = self._move_to_cache_device(vae)
            
            if norm_name in self.base_models:
                self.base_models[norm_name] = (model, clip, vae)
                self.base_models.move_to_end(norm_name)
                return
            
            self.base_models[norm_name] = (model, clip, vae)
            self._log(f"💾 Stored base model: {norm_name} (cache: {len(self.base_models)}/{self.max_models})")
            
            while len(self.base_models) > self.max_models:
                evicted_name, evicted_data = self.base_models.popitem(last=False)
                self._evict_base_model(evicted_name, evicted_data)
    
    def _evict_base_model(self, name: str, model_data):
        """Evict base model from cache."""
        self.stats["evictions"] += 1
        self._log(f"🗑️  EVICTING base model: {name}")
        if model_data is not None:
            del model_data
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    # =========================================================================
    #  CLIP Model Methods
    # =========================================================================
    
    def _get_clip_cache_key(self, model_name: str, clip_skip: int = 0) -> str:
        """Generate cache key for CLIP model."""
        norm_model = self._normalize_key(model_name)
        combined = f"{norm_model}:clip_skip_{clip_skip}"
        return hashlib.md5(combined.encode()).hexdigest()[:16]
    
    def get_clip_model(self, model_name: str, clip_skip: int = 0) -> Optional[Any]:
        """Get CLIP model from cache."""
        with self.cache_lock:
            start_time = time.time()
            cache_key = self._get_clip_cache_key(model_name, clip_skip)
            
            if self.preloaded_clip and self.preloaded_clip[0] == cache_key:
                clip = self.preloaded_clip[1]
                self.stats["clip_hits"] += 1
                elapsed = time.time() - start_time
                self.stats["cache_load_time"] += elapsed
                self._log(f"⚡ CLIP HIT (PRE-LOADED): {model_name} ({elapsed*1000:.1f}ms)")
                
                clip = self._move_to_compute_device(clip)
                
                self.clip_models[cache_key] = clip
                self.clip_models.move_to_end(cache_key)
                self.preloaded_clip = None
                self.stats["preload_successes"] += 1
                
                return clip
            
            if cache_key in self.clip_models:
                clip = self.clip_models[cache_key]
                self.clip_models.move_to_end(cache_key)
                self.stats["clip_hits"] += 1
                clip = self._move_to_compute_device(clip)
                return clip
            
            self.stats["clip_misses"] += 1
            return None
    
    def put_clip_model(self, model_name: str, clip, clip_skip: int = 0):
        """Store CLIP model in cache."""
        with self.cache_lock:
            cache_key = self._get_clip_cache_key(model_name, clip_skip)
            
            clip = self._move_to_cache_device(clip)
            
            if cache_key in self.clip_models:
                self.clip_models[cache_key] = clip
                self.clip_models.move_to_end(cache_key)
                return
            
            self.clip_models[cache_key] = clip
            
            while len(self.clip_models) > self.max_clips:
                evicted_key, evicted_data = self.clip_models.popitem(last=False)
                self._evict_clip_model(evicted_key, evicted_data)
    
    def _evict_clip_model(self, cache_key: str, clip_data):
        """Evict CLIP model from cache."""
        self.stats["evictions"] += 1
        self._log(f"🗑️  EVICTING CLIP (key: {cache_key[:8]}...)")
        if clip_data is not None:
            del clip_data
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    # =========================================================================
    #  Device Management
    # =========================================================================
    
    def _move_to_cache_device(self, model):
        """Move model to cache device."""
        if model is None:
            return None
        try:
            if self.cache_device == 'cpu':
                if hasattr(model, 'model') and hasattr(model.model, 'to'):
                    model.model.to('cpu')
                    self.stats["vram_to_ram_moves"] += 1
                elif hasattr(model, 'to'):
                    model.to('cpu')
                    self.stats["vram_to_ram_moves"] += 1
            return model
        except Exception as e:
            self._log(f"⚠️ Move to {self.cache_device} failed: {e}")
            return model
    
    def _move_to_compute_device(self, model):
        """Move model to compute device (CUDA)."""
        if model is None:
            return None
        try:
            if self.cache_device == 'cpu':
                import comfy.model_management
                device = comfy.model_management.get_torch_device()
                if hasattr(model, 'model') and hasattr(model.model, 'to'):
                    model.model.to(device)
                    self.stats["ram_to_vram_moves"] += 1
                elif hasattr(model, 'to'):
                    model.to(device)
                    self.stats["ram_to_vram_moves"] += 1
            return model
        except Exception as e:
            self._log(f"⚠️ Move to CUDA failed: {e}")
            return model
    
    # =========================================================================
    #  Statistics
    # =========================================================================
    
    def print_stats(self):
        """Print detailed cache statistics."""
        stats = self.get_stats()
        
        print(f"\n{'='*80}")
        print(f"[ModelCache] 📊 THREE-TIER CACHE STATISTICS")
        print(f"{'='*80}")
        print(f"  LORA COMPLETE RESULTS:")
        print(f"    Cache Hits: {stats['lora_hits']} ({stats['lora_hit_rate']}%)")
        print(f"    Cache Misses: {stats['lora_misses']}")
        print(f"    Currently Cached: {stats['current_lora_cached']}/{self.max_lora_sets}")
        print(f"")
        print(f"  LORA RAW FILES:")
        print(f"    Cache Hits: {stats['lora_file_hits']} ({stats['lora_file_hit_rate']}%)")
        print(f"    Cache Misses: {stats['lora_file_misses']}")
        print(f"    Disk Loads: {stats['lora_file_disk_loads']}")
        print(f"    Currently Cached: {stats['current_lora_files_cached']}/{self.max_lora_files}")
        print(f"")
        print(f"  INCREMENTAL PATCHING:")
        print(f"    Incremental Hits: {stats['incremental_hits']}")
        print(f"    LoRAs Skipped (reused): {stats['incremental_loras_skipped']}")
        print(f"")
        print(f"  ASYNC PRELOADS:")
        print(f"    Preload Successes: {stats['preload_successes']}")
        print(f"    Main Thread Waits: {stats['thread_joins']} (Saved potential cache misses)")
        print(f"")
        print(f"  PERFORMANCE:")
        print(f"    Disk Load Time: {stats['disk_load_time']:.2f}s")
        print(f"    Cache Load Time: {stats['cache_load_time']:.2f}s")
        if stats['total_load_time'] > 0:
            time_saved = stats['disk_load_time'] - stats['cache_load_time']
            print(f"    Time Saved: {time_saved:.2f}s")
        print(f"{'='*80}\n")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.cache_lock:
            total_lora = self.stats["lora_hits"] + self.stats["lora_misses"]
            total_lora_files = self.stats["lora_file_hits"] + self.stats["lora_file_misses"]
            
            lora_hit_rate = 0
            if total_lora > 0:
                lora_hit_rate = (self.stats["lora_hits"] / total_lora) * 100
            
            lora_file_hit_rate = 0
            if total_lora_files > 0:
                lora_file_hit_rate = (self.stats["lora_file_hits"] / total_lora_files) * 100
            
            return {
                **self.stats,
                "lora_hit_rate": round(lora_hit_rate, 1),
                "lora_file_hit_rate": round(lora_file_hit_rate, 1),
                "total_lora_requests": total_lora,
                "total_lora_file_requests": total_lora_files,
                "current_lora_cached": len(self.lora_models),
                "current_lora_files_cached": len(self.lora_files),
                "has_incremental_state": self.last_patched_state is not None
            }