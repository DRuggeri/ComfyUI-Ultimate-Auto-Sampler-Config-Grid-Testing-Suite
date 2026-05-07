"""
Distributed Worker Thread
Runs on remote ComfyUI instances. Polls the master for jobs,
processes them using the local GPU, and uploads results back.
"""

import threading
import time
import uuid
import json
import io
import os
import random
from urllib.parse import quote as url_quote
from .network_utils import (
    distribution_get,
    distribution_post_json,
    distribution_post_multipart,
    distribution_stream_download,
)

import torch


class _MasterFinishedError(Exception):
    """Raised when the master has deactivated (503 on submit).
    Not a real error — means master already completed all jobs."""
    pass


class WorkerThread(threading.Thread):
    """
    Background thread that polls master for jobs and processes them.

    Lifecycle:
        1. Register with master
        2. Claim job (GET /distribution/claim_job)
        3. Process job locally (model load → encode → sample → VAE decode)
        4. Submit result (POST /distribution/submit_result)
        5. Repeat from 2 until no more jobs
        6. Exit
    """

    def __init__(self, master_url):
        super().__init__(daemon=True)
        self.master_url = master_url.rstrip("/")
        self.worker_id = f"w_{uuid.uuid4().hex[:8]}"
        self.jobs_processed = 0
        self.current_model = None
        self._stop_event = threading.Event()
        self.poll_interval = 2      # seconds between polls when idle
        self.heartbeat_interval = 30  # seconds between heartbeats
        self.consecutive_empty = 0   # Track consecutive empty poll responses
        self.max_empty_polls = 30    # Stop after this many consecutive empty polls

        # Cached state for model reuse between jobs
        self._loaded_model = None
        self._loaded_clip = None
        self._loaded_vae = None
        self._patched_model = None
        self._patched_clip = None
        self._cached_model_key = None
        self._cached_lora_key = None
        self._incompatible_loras = {}

        # Model sync: download missing models from master before processing
        self._sync_models = False  # Set by master when sync_models_to_workers enabled
        self._prefetch_thread = None
        self._prefetch_queue = []  # List of {category, filename} to pre-fetch
        self._prefetch_lock = threading.Lock()

    # =========================================================================
    # MODEL SYNC HELPERS
    # =========================================================================

    def _download_model_from_master(self, category, filename):
        """
        Download a single model file from the master instance.
        Preserves full subdirectory structure.

        Args:
            category: Model category (checkpoints, loras, vae, etc.)
            filename: Relative path including subdirs (e.g. SDXL/Illustrious/model.safetensors)

        Returns:
            str: Local path where file was saved, or None on failure
        """
        import folder_paths

        # Determine target directory
        # folder_paths stores base directories per category
        base_dirs = folder_paths.get_folder_paths(category)
        if not base_dirs:
            print(f"[Worker {self.worker_id}] ❌ Unknown model category: {category}")
            return None
        target_dir = base_dirs[0]  # Use first (primary) directory
        target_path = os.path.join(target_dir, filename.replace("/", os.sep))

        # Skip if already exists
        if os.path.exists(target_path):
            return target_path

        # Create subdirectories
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # Download from master via network gateway
        try:
            print(f"[Worker {self.worker_id}] ⬇️ Downloading {category}/{filename}...")
            last_progress = 0

            def on_progress(downloaded, total_size):
                nonlocal last_progress
                if total_size > 0:
                    pct = int(downloaded * 100 / total_size)
                    if pct >= last_progress + 10:
                        last_progress = pct
                        size_str = f"{total_size / (1024**3):.2f} GB" if total_size > 1024**3 else f"{total_size / (1024**2):.0f} MB"
                        print(f"[Worker {self.worker_id}] ⬇️ {category}/{filename}: {pct}% of {size_str}")

            distribution_stream_download(
                url=f"{self.master_url}/distribution/download_model",
                data_dict={
                    "worker_id": self.worker_id,
                    "category": category,
                    "filename": filename
                },
                target_path=target_path,
                timeout=3600,
                progress_callback=on_progress
            )
            print(f"[Worker {self.worker_id}] ✅ Downloaded {category}/{filename}")
            return target_path

        except Exception as e:
            print(f"[Worker {self.worker_id}] ❌ Failed to download {category}/{filename}: {e}")
            # Clean up partial download
            temp_path = target_path + ".downloading"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None

    def _extract_required_models(self, config):
        """
        Extract all model file references from a job config.

        Returns:
            List of {category, filename} dicts
        """
        import folder_paths
        models = []

        # Main model/checkpoint
        model_name = config.get("model", "None")
        if model_name and model_name != "None":
            model_type = config.get("model_type", "checkpoint")
            if model_type == "checkpoint":
                category = "checkpoints"
            elif model_type == "gguf":
                category = "unet_gguf"
            elif model_type == "diffusion_model":
                category = "diffusion_models"
            else:
                category = "checkpoints"
            models.append({"category": category, "filename": model_name})

        # LoRA — combo string format: "name:model_str:clip_str + name2:model_str:clip_str"
        # Parts can also be folder references like "FolderName/:0.90:0.90" which expand
        # to all LoRA files in that folder, or random syntax "Folder/[3,0.5]"
        lora = config.get("lora_expanded", config.get("lora", "None"))
        if lora and lora != "None":
            for lora_part in lora.split(" + "):
                lora_part = lora_part.strip()
                if not lora_part:
                    continue
                # Extract just the filename (before first ":")
                lora_filename = lora_part.split(":")[0].strip()
                if not lora_filename or lora_filename == "None":
                    continue

                # Check if it's a folder reference (ends with / or /*)
                clean_name = lora_filename.rstrip("/*").rstrip("/")
                is_folder = lora_filename.endswith("/") or lora_filename.endswith("/*")
                # Also check for random selection syntax: folder/[count,strength]
                has_bracket = "[" in lora_filename and "]" in lora_filename
                if has_bracket:
                    clean_name = lora_filename.split("[")[0].rstrip("/")
                    is_folder = True

                if is_folder:
                    # Expand folder to individual LoRA files
                    folder_prefix = clean_name.replace("\\", "/") + "/"
                    all_loras = folder_paths.get_filename_list("loras")
                    for lora_file in all_loras:
                        if lora_file.replace("\\", "/").startswith(folder_prefix):
                            models.append({"category": "loras", "filename": lora_file})
                else:
                    models.append({"category": "loras", "filename": lora_filename})

        # VAE (skip remote URLs and "Default")
        vae = config.get("vae", "Default")
        if vae and vae != "Default" and not vae.startswith("remote:"):
            models.append({"category": "vae", "filename": vae})

        # Text encoders
        text_encoders = config.get("text_encoders", [])
        for te in text_encoders:
            if te and te != "None":
                models.append({"category": "text_encoders", "filename": te})

        return models

    def _ensure_models_available(self, config):
        """
        Check all required models exist locally, download missing ones from master.
        Blocks until all models are available.
        """
        import folder_paths

        required = self._extract_required_models(config)
        if not required:
            return

        missing = []
        for m in required:
            path = folder_paths.get_full_path(m["category"], m["filename"])
            if path is None:
                missing.append(m)

        if not missing:
            return

        print(f"[Worker {self.worker_id}] 📦 Missing {len(missing)} model(s), downloading from master...")
        for m in missing:
            result = self._download_model_from_master(m["category"], m["filename"])
            if result is None:
                raise RuntimeError(
                    f"Failed to download required model: {m['category']}/{m['filename']}. "
                    f"Check that the file exists on the master instance."
                )

    def _start_prefetch(self, upcoming_models):
        """Start background thread to pre-fetch upcoming models."""
        if not upcoming_models:
            return

        with self._prefetch_lock:
            self._prefetch_queue = list(upcoming_models)

        if self._prefetch_thread and self._prefetch_thread.is_alive():
            return  # Already running

        def _prefetch_worker():
            while True:
                with self._prefetch_lock:
                    if not self._prefetch_queue:
                        break
                    model = self._prefetch_queue.pop(0)
                try:
                    self._download_model_from_master(model["category"], model["filename"])
                except Exception as e:
                    print(f"[Worker {self.worker_id}] ⚠️ Pre-fetch failed: {e}")

        self._prefetch_thread = threading.Thread(target=_prefetch_worker, daemon=True)
        self._prefetch_thread.start()

    def run(self):
        """Main worker loop."""
        print(f"[Worker {self.worker_id}] 🚀 Starting worker thread, master: {self.master_url}")

        # Worker threads run outside ComfyUI's normal prompt execution context.
        # The sampling callback (latent_preview.py → comfy/utils.py → main.py hook)
        # expects PromptServer.instance.last_prompt_id to exist. Set a dummy value
        # so the progress bar callback doesn't crash with AttributeError.
        try:
            from server import PromptServer
            if PromptServer and hasattr(PromptServer, 'instance') and PromptServer.instance is not None:
                if not hasattr(PromptServer.instance, 'last_prompt_id'):
                    PromptServer.instance.last_prompt_id = f"dist_worker_{self.worker_id}"
                    print(f"[Worker {self.worker_id}] 🔧 Set last_prompt_id for sampling callbacks")
        except Exception:
            pass

        # Register with master
        self._register()

        # Start background heartbeat thread so heartbeats flow even during
        # long-running job processing (model loading, generation, etc.).
        # Without this, the main loop blocks on _process_job() and no heartbeats
        # are sent, causing the master to wrongly reclaim jobs from slow workers.
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

        while not self._stop_event.is_set():
            # Claim a job
            job = self._claim_job()

            if job is None:
                self.consecutive_empty += 1
                if self.consecutive_empty >= self.max_empty_polls:
                    print(f"[Worker {self.worker_id}] 🏁 No more jobs after "
                          f"{self.max_empty_polls} polls, stopping")
                    break
                self._stop_event.wait(self.poll_interval)
                continue

            self.consecutive_empty = 0

            # Validate job has required fields
            if not all(k in job for k in ("job_id", "config", "input_job")):
                print(f"[Worker {self.worker_id}] ⚠️ Malformed job, skipping: {list(job.keys())}")
                continue

            # Sync missing models from master if enabled
            try:
                if self._sync_models:
                    self._ensure_models_available(job["config"])

                    # Start background pre-fetch for upcoming models
                    if job.get("upcoming_models"):
                        self._start_prefetch(job["upcoming_models"])
            except Exception as e:
                print(f"[Worker {self.worker_id}] ❌ Model sync failed for job {job['job_id']}: {e}")
                self._report_failure(job["job_id"], f"Model sync failed: {e}")
                continue

            # Process the job
            try:
                image_bytes, meta = self._process_job(job)

                # Submit result (with retry on network error)
                self._submit_result(job["job_id"], image_bytes, meta)
                self.jobs_processed += 1

                print(f"[Worker {self.worker_id}] ✅ Job {job['job_id']} complete "
                      f"(total: {self.jobs_processed})")

                # Periodic VRAM cleanup
                if self.jobs_processed % 5 == 0:
                    import gc
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

            except _MasterFinishedError:
                # Master has shut down (503 on submit). This is NOT a failure —
                # the master already finished all jobs (possibly reclaimed ours).
                # Stop gracefully instead of reporting failure.
                print(f"[Worker {self.worker_id}] 🏁 Master finished before we could submit "
                      f"job {job['job_id']} — stopping gracefully")
                break

            except Exception as e:
                # Check if ComfyUI interrupted processing on this worker
                try:
                    from comfy.model_management import InterruptProcessingException
                    if isinstance(e, InterruptProcessingException):
                        print(f"[Worker {self.worker_id}] 🛑 Processing interrupted, stopping worker")
                        self._report_failure(job["job_id"], "Worker interrupted")
                        break
                except ImportError:
                    pass

                print(f"[Worker {self.worker_id}] ❌ Job {job['job_id']} failed: {e}")
                import traceback
                traceback.print_exc()
                self._report_failure(job["job_id"], str(e))

        # Cleanup
        self._cleanup_models()
        print(f"[Worker {self.worker_id}] 🛑 Worker stopped. "
              f"Processed {self.jobs_processed} jobs.")

    def stop(self):
        """Signal the worker to stop after its current job."""
        self._stop_event.set()

    def _register(self):
        """Register with master. Retries on 503 (master still starting up)."""
        max_retries = 5
        retry_delay = 3  # seconds between retries

        for attempt in range(1, max_retries + 1):
            try:
                status, resp_data = distribution_post_json(
                    f"{self.master_url}/distribution/register_worker",
                    {"worker_id": self.worker_id, "worker_url": ""},
                    timeout=10
                )
                result = json.loads(resp_data.decode("utf-8"))
                print(f"[Worker {self.worker_id}] 🤝 Registered with master "
                      f"(session: {result.get('session_name', 'unknown')})")
                return  # Success
            except Exception as e:
                if hasattr(e, 'code') and e.code == 503 and attempt < max_retries:
                    print(f"[Worker {self.worker_id}] ⏳ Master not ready yet "
                          f"(attempt {attempt}/{max_retries}), retrying in {retry_delay}s...")
                    self._stop_event.wait(retry_delay)
                    if self._stop_event.is_set():
                        return
                    continue
                print(f"[Worker {self.worker_id}] ⚠️ Registration failed: {e}")
                return

    def _claim_job(self):
        """Claim next job from master. Returns job dict or None."""
        url = (f"{self.master_url}/distribution/claim_job"
               f"?worker_id={url_quote(self.worker_id)}")

        if self.consecutive_empty == 0 and self.jobs_processed == 0:
            print(f"[Worker {self.worker_id}] 🔍 Claiming from: {url}")

        try:
            status, resp_data = distribution_get(url, timeout=10)
            if status == 204:
                return None
            return json.loads(resp_data.decode("utf-8"))
        except Exception as e:
            if hasattr(e, 'code'):
                if e.code == 204:
                    return None
                if e.code == 503:
                    # Distribution not active yet — master may still be starting up
                    # (e.g. pre-encoding prompts). Don't immediately stop; let the
                    # normal empty-poll counter handle eventual timeout.
                    if self.jobs_processed == 0 and self.consecutive_empty < 5:
                        print(f"[Worker {self.worker_id}] ⏳ Master not active yet, "
                              f"waiting... ({self.consecutive_empty + 1}/5)")
                    elif self.jobs_processed > 0:
                        # Already processed jobs — master has finished and deactivated.
                        # Stop immediately to avoid wasting time.
                        print(f"[Worker {self.worker_id}] ℹ️ Distribution ended on master")
                        self.consecutive_empty = self.max_empty_polls
                    else:
                        print(f"[Worker {self.worker_id}] ℹ️ Distribution not active on master")
                        self.consecutive_empty = self.max_empty_polls
                    return None
                print(f"[Worker {self.worker_id}] ⚠️ Claim failed: HTTP {e.code}")
                return None
            print(f"[Worker {self.worker_id}] ⚠️ Claim failed: {e}")
            return None

    @torch.inference_mode()
    def _process_job(self, job):
        """
        Process a single job using local ComfyUI infrastructure.

        Steps:
            1. Load model/LoRA (reuse if same as previous job)
            2. Encode prompts with CLIP
            3. Create latent noise tensor
            4. Generate image (KSampler)
            5. Decode with local VAE
            6. Return image bytes + metadata

        Args:
            job: Job dict from master with config, input_job, gen_index

        Returns:
            tuple: (image_bytes, metadata_dict)

        Note: @torch.inference_mode() is required because worker threads run
        outside ComfyUI's execution engine which wraps everything in
        inference_mode. Without it, Dynamic VRAM's lazy weight loading can
        produce NaN values during VAE decode.
        """
        from .model_loader import (
            load_checkpoint, load_loras, load_vae_by_name,
            load_diffusion_model_and_clip, get_latent_channels
        )
        from .image_generation import (
            generate_image, decode_latent_with_vae, create_image_metadata
        )
        from .batch_encoding import encode_prompt_with_combinators
        from .trigger_words import build_prompt_with_triggers
        from .generation_orchestrator import get_model_cache_key

        config = job["config"]
        input_job = job["input_job"]
        w = input_job["width"]
        h = input_job["height"]
        batch_idx = input_job.get("batch_idx", 0)

        # Handle seed_behavior: "randomize" (same as main generation loop)
        if config.get("seed_behavior") == "randomize":
            config["seed"] = random.randint(0, 2**63 - 1)

        # Full run seed behavior is handled by the orchestrator/master before dispatching jobs.
        # Workers just use whatever seed is in the config they receive.

        # ==== GPU COOLDOWN (if enabled in session settings) ====
        cooldown_config = config.get("_session_cooldown", {})
        if cooldown_config.get("enabled", False):
            if not hasattr(self, '_gen_count'):
                self._gen_count = 0
            self._gen_count += 1
            cooldown_every_n = int(cooldown_config.get("every_n", 1))
            if self._gen_count % cooldown_every_n == 0:
                cooldown_seconds = int(cooldown_config.get("seconds", 5))
                clear_vram = cooldown_config.get("clear_vram", False)
                print(f"[Worker {self.worker_id}] ❄️ GPU Cooldown: pausing {cooldown_seconds}s after {self._gen_count} generations")
                if clear_vram:
                    import comfy.model_management as mm_cooldown
                    mm_cooldown.soft_empty_cache()
                    mm_cooldown.unload_all_models()
                    print(f"[Worker {self.worker_id}] ❄️ VRAM cleared")
                    self._cached_model_key = None  # Force model reload on next iteration
                import time as time_cooldown
                time_cooldown.sleep(cooldown_seconds)
                print(f"[Worker {self.worker_id}] ❄️ Cooldown complete, resuming")

        # --- Model Loading (with caching between jobs) ---
        target_model_key = get_model_cache_key(config)
        self.current_model = config.get("model", "unknown")

        if target_model_key != self._cached_model_key:
            # Need to load a different model
            self._cleanup_models()

            model_type = config.get("model_type", "checkpoint")
            if model_type == "checkpoint":
                self._loaded_model, self._loaded_clip, self._loaded_vae = load_checkpoint(
                    config["model"], config["model"], False,
                    None, None, None, None, None, None, None,
                    model_cache=None
                )
            else:
                self._loaded_model, self._loaded_clip, self._loaded_vae = load_diffusion_model_and_clip(
                    model_name=config["model"],
                    model_type=model_type,
                    text_encoder_paths=config.get("text_encoders", []),
                    clip_type_str=config.get("clip_type", "stable_diffusion"),
                    gguf_options=config.get("gguf_options"),
                    use_remote_vae=False,
                    optional_model=None,
                    optional_clip=None,
                    optional_vae=None,
                    model_cache=None
                )

            self._cached_model_key = target_model_key
            self._cached_lora_key = None  # Force LoRA reload on model switch
            print(f"[Worker {self.worker_id}] 📦 Loaded model: {config['model']}")

        # --- Per-config VAE loading ---
        # Supports three modes:
        #   1. "Default" → use model's bundled VAE
        #   2. "remote:https://..." → remote HuggingFace VAE endpoint (decoded at decode step)
        #   3. "ae.safetensors" → load local VAE file
        config_vae = config.get("vae", "Default")
        _remote_vae_url = None
        if config_vae != "Default":
            if config_vae.startswith("remote:"):
                _remote_vae_url = config_vae[len("remote:"):]
                vae = None  # No local VAE needed — will use remote endpoint
                print(f"[Worker {self.worker_id}] 🌐 Using remote VAE: {_remote_vae_url}")
            else:
                vae = load_vae_by_name(config_vae)
        else:
            vae = self._loaded_vae

        # Validate VAE is available (non-checkpoint models like GGUF may not bundle a VAE)
        # Skip this check when using remote VAE — no local VAE object needed.
        if vae is None and _remote_vae_url is None:
            raise RuntimeError(
                f"No VAE available for model '{config.get('model', 'unknown')}'. "
                f"Non-checkpoint models (GGUF/diffusion) require a VAE to be specified "
                f"in the config builder, or connect one via optional_vae on the master."
            )

        # --- LoRA Loading (with caching) ---
        lora_key = config.get("lora_expanded", config.get("lora", "None"))
        if lora_key != self._cached_lora_key:
            if lora_key != "None":
                self._patched_model, self._patched_clip, should_skip = load_loras(
                    self._loaded_model, self._loaded_clip, lora_key,
                    config["model"], self._incompatible_loras,
                    model_cache=None
                )
                if should_skip:
                    raise RuntimeError(f"LoRA incompatible: {lora_key}")
            else:
                self._patched_model = self._loaded_model
                self._patched_clip = self._loaded_clip

            self._cached_lora_key = lora_key
            print(f"[Worker {self.worker_id}] 🔗 Applied LoRA: {lora_key}")

        # --- Prompt Encoding ---
        # Check for master pre-encoded conditionings (skip CLIP encoding if available)
        encoded_pos = job.get("encoded_positive")
        encoded_neg = job.get("encoded_negative")

        if encoded_pos is not None and encoded_neg is not None:
            # Master already encoded these prompts — deserialize and use directly.
            # Use the master's prompt text for metadata (avoids CivitAI trigger lookups
            # on the worker since the master already applied trigger words during encoding).
            from .generation_orchestrator import _serializable_to_conditioning
            pos_cond = _serializable_to_conditioning(encoded_pos)
            neg_cond = _serializable_to_conditioning(encoded_neg)
            actual_positive = job.get("actual_positive_text", config.get("positive", ""))
            actual_negative = job.get("actual_negative_text", config.get("negative", ""))
            print(f"[Worker {self.worker_id}] 🧠 Using master pre-encoded conditionings")
        else:
            # Fallback: encode locally with CLIP (need to build prompt with trigger words)
            lora_triggerwords_mode = config.get("_lora_triggerwords_mode", "None")
            try:
                actual_positive, _ = build_prompt_with_triggers(config, lora_triggerwords_mode)
            except Exception:
                actual_positive = config.get("positive", "")
            actual_negative = config.get("negative", "")
            clip_skip = config.get("clip_skip", 0)
            pos_cond = encode_prompt_with_combinators(self._patched_clip, actual_positive, clip_skip)
            neg_cond = encode_prompt_with_combinators(self._patched_clip, actual_negative, clip_skip)

        # --- Create Latent ---
        latent_channels = get_latent_channels(self._loaded_model, None)
        latent_in = {"samples": torch.zeros([1, latent_channels, h // 8, w // 8])}

        # --- Generate Image ---
        attention_mode = config.get("attention_mode", "default")
        result_latent, duration = generate_image(
            self._patched_model, config["seed"], config["steps"], config["cfg"],
            config["sampler"], config["scheduler"], pos_cond, neg_cond,
            latent_in, config["denoise"],
            attention_mode=attention_mode,
            model_sampling_override=config.get("model_sampling_override", "none"),
            model_sampling_shift=config.get("model_sampling_shift", 1.73),
            model_sampling_flux_max_shift=config.get("model_sampling_flux_max_shift", 1.15),
            model_sampling_flux_base_shift=config.get("model_sampling_flux_base_shift", 0.5),
            use_advanced_sampling=config.get("use_advanced_sampling", False),
            advanced_guider=config.get("advanced_guider", "cfg_guider"),
            advanced_scheduler=config.get("advanced_scheduler", "basic"),
            flux_guidance_value=config.get("flux_guidance_value", 0.0),
            width=w,
            height=h
        )

        # --- VAE Decode ---
        # Clone latent samples and free UNet-related tensors BEFORE VAE decode.
        # With Dynamic VRAM, the model manager needs to evict the UNet to load
        # the VAE. Holding references to UNet output tensors on GPU can interfere
        # with memory eviction, causing the VAE to run in a degraded state that
        # produces NaN values.
        latent_for_decode = result_latent["samples"].clone()
        del result_latent, latent_in, pos_cond, neg_cond
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if _remote_vae_url:
            # Remote VAE: send latents to HuggingFace endpoint for decoding
            from .remote_vae import remote_decode_hf
            from PIL import Image as PILImage
            import numpy as np
            if latent_for_decode.ndim == 3:
                latent_for_decode = latent_for_decode.unsqueeze(0)
            decoded = remote_decode_hf(_remote_vae_url, latent_for_decode, h, w)
            del latent_for_decode
            # Denormalize from [-1, 1] → [0, 1] (same as VaeImageProcessor.postprocess)
            decoded = (decoded / 2 + 0.5).clamp(0, 1)
            img_data = decoded[0].permute(1, 2, 0).cpu().numpy()
            image = PILImage.fromarray((img_data * 255).round().astype(np.uint8))
        else:
            image = decode_latent_with_vae(vae, latent_for_decode)
            del latent_for_decode

        # --- Convert to bytes ---
        # Honour image_format from session settings (injected by master into config)
        _raw_fmt = config.get("_session_image_format", "webp")
        _fmt = (_raw_fmt or "webp").lower().strip()
        if _fmt not in ("webp", "png", "jpg", "jpeg"):
            _fmt = "webp"
        buf = io.BytesIO()
        if _fmt == "png":
            image.save(buf, format="PNG")
        elif _fmt in ("jpg", "jpeg"):
            image.save(buf, format="JPEG", quality=95)
        else:
            image.save(buf, format="WEBP", quality=80)
        image_bytes = buf.getvalue()
        del image, buf  # Free PIL image and buffer

        # --- Create metadata ---
        ts = int(time.time() * 100000) + random.randint(0, 1000)
        meta = create_image_metadata(
            config, w, h, duration, config["seed"],
            batch_idx, actual_positive, actual_negative,
            gen_index=job.get("gen_index")
        )
        meta["id"] = ts
        # Pass the chosen extension to the master so it can save with the right filename
        _ext = "jpg" if _fmt in ("jpg", "jpeg") else _fmt
        meta["_image_ext"] = _ext

        return image_bytes, meta

    def _submit_result(self, job_id, image_bytes, meta, max_retries=3):
        """
        Upload image + metadata to master via multipart POST.
        Uses network_utils.py gateway for all outbound requests.
        Retries on transient network errors (connection reset, timeout).
        """
        # JSON-safe meta (ensure no non-serializable types from config round-trip)
        try:
            safe_meta = json.loads(json.dumps(meta, default=str))
        except Exception:
            safe_meta = meta

        boundary = f"----DistWorker{uuid.uuid4().hex[:16]}"

        # Build multipart body manually
        body = b""

        # Metadata part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="metadata"\r\n'
        body += b'Content-Type: application/json\r\n\r\n'
        body += json.dumps({
            "job_id": job_id,
            "meta": safe_meta,
            "worker_id": self.worker_id
        }).encode("utf-8")
        body += b"\r\n"

        # Image part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="image"; filename="image.webp"\r\n'
        body += b'Content-Type: image/webp\r\n\r\n'
        body += image_bytes
        body += b"\r\n"

        body += f"--{boundary}--\r\n".encode()

        last_error = None
        for attempt in range(max_retries):
            try:
                status, _ = distribution_post_multipart(
                    f"{self.master_url}/distribution/submit_result",
                    f"multipart/form-data; boundary={boundary}",
                    body,
                    timeout=60
                )
                if status != 200:
                    raise RuntimeError(f"Submit failed: HTTP {status}")
                return  # Success

            except Exception as e:
                # 503 = master deactivated (all jobs done). Don't retry — it won't help.
                # Raise a special exception so the main loop can stop gracefully.
                if hasattr(e, 'code') and e.code == 503:
                    raise _MasterFinishedError(
                        f"Master distribution is no longer active (HTTP 503)"
                    )
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"[Worker {self.worker_id}] ⚠️ Submit retry {attempt + 1}/{max_retries} "
                          f"for job {job_id}: {e} (waiting {wait}s)")
                    time.sleep(wait)

        raise RuntimeError(f"Submit failed after {max_retries} attempts: {last_error}")

    def _send_heartbeat(self):
        """Send heartbeat to master."""
        try:
            distribution_post_json(
                f"{self.master_url}/distribution/heartbeat",
                {"worker_id": self.worker_id},
                timeout=5
            )
        except Exception:
            pass

    def _heartbeat_loop(self):
        """
        Background heartbeat loop. Runs in a separate daemon thread so that
        heartbeats are sent continuously even while _process_job() blocks the
        main worker loop. This prevents the master from incorrectly reclaiming
        jobs from slow-but-alive workers.
        """
        while not self._stop_event.is_set():
            self._send_heartbeat()
            self._stop_event.wait(self.heartbeat_interval)

    def _report_failure(self, job_id, error):
        """Report job failure to master."""
        try:
            distribution_post_json(
                f"{self.master_url}/distribution/fail_job",
                {
                    "job_id": job_id,
                    "error": error,
                    "worker_id": self.worker_id
                },
                timeout=10
            )
        except Exception:
            pass

    def _cleanup_models(self):
        """Release cached model references."""
        self._loaded_model = None
        self._loaded_clip = None
        self._loaded_vae = None
        self._patched_model = None
        self._patched_clip = None
        self._cached_model_key = None
        self._cached_lora_key = None
        self.current_model = None

        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
