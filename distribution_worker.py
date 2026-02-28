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
import urllib.request
import urllib.error
import urllib.parse

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
        """Register with master."""
        data = json.dumps({
            "worker_id": self.worker_id,
            "worker_url": ""
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.master_url}/distribution/register_worker",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                print(f"[Worker {self.worker_id}] 🤝 Registered with master "
                      f"(session: {result.get('session_name', 'unknown')})")
        except Exception as e:
            print(f"[Worker {self.worker_id}] ⚠️ Registration failed: {e}")

    def _claim_job(self):
        """Claim next job from master. Returns job dict or None."""
        url = (f"{self.master_url}/distribution/claim_job"
               f"?worker_id={urllib.parse.quote(self.worker_id)}")

        if self.consecutive_empty == 0 and self.jobs_processed == 0:
            print(f"[Worker {self.worker_id}] 🔍 Claiming from: {url}")

        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 204:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return None
            if e.code == 503:
                # Distribution not active, stop polling
                print(f"[Worker {self.worker_id}] ℹ️ Distribution not active on master")
                self.consecutive_empty = self.max_empty_polls
                return None
            print(f"[Worker {self.worker_id}] ⚠️ Claim failed: HTTP {e.code}")
            return None
        except Exception as e:
            print(f"[Worker {self.worker_id}] ⚠️ Claim failed: {e}")
            return None

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
        config_vae = config.get("vae", "Default")
        if config_vae != "Default":
            vae = load_vae_by_name(config_vae)
        else:
            vae = self._loaded_vae

        # Validate VAE is available (non-checkpoint models like GGUF may not bundle a VAE)
        if vae is None:
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
        # Build prompt with trigger words (always needed for metadata even if using master encoding)
        lora_triggerwords_mode = config.get("_lora_triggerwords_mode", "None")
        try:
            actual_positive, _ = build_prompt_with_triggers(config, lora_triggerwords_mode)
        except Exception:
            actual_positive = config.get("positive", "")
        actual_negative = config.get("negative", "")

        # Check for master pre-encoded conditionings (skip CLIP encoding if available)
        encoded_pos = job.get("encoded_positive")
        encoded_neg = job.get("encoded_negative")

        if encoded_pos is not None and encoded_neg is not None:
            # Master already encoded these prompts — deserialize and use directly
            from .generation_orchestrator import _serializable_to_conditioning
            pos_cond = _serializable_to_conditioning(encoded_pos)
            neg_cond = _serializable_to_conditioning(encoded_neg)
            print(f"[Worker {self.worker_id}] 🧠 Using master pre-encoded conditionings")
        else:
            # Fallback: encode locally with CLIP
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
            attention_mode=attention_mode
        )

        # --- VAE Decode ---
        image = decode_latent_with_vae(vae, result_latent["samples"])

        # Free latent tensors ASAP (before image conversion, which is CPU-only)
        del result_latent, latent_in, pos_cond, neg_cond

        # --- Convert to bytes ---
        buf = io.BytesIO()
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

        return image_bytes, meta

    def _submit_result(self, job_id, image_bytes, meta, max_retries=3):
        """
        Upload image + metadata to master via multipart POST.
        Uses urllib (no 'requests' library for ComfyUI Registry compliance).
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
                req = urllib.request.Request(
                    f"{self.master_url}/distribution/submit_result",
                    data=body,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                    },
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=60) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"Submit failed: HTTP {resp.status}")
                return  # Success

            except urllib.error.HTTPError as e:
                # 503 = master deactivated (all jobs done). Don't retry — it won't help.
                # Raise a special exception so the main loop can stop gracefully.
                if e.code == 503:
                    raise _MasterFinishedError(
                        f"Master distribution is no longer active (HTTP 503)"
                    )
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"[Worker {self.worker_id}] ⚠️ Submit retry {attempt + 1}/{max_retries} "
                          f"for job {job_id}: {e} (waiting {wait}s)")
                    time.sleep(wait)

            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"[Worker {self.worker_id}] ⚠️ Submit retry {attempt + 1}/{max_retries} "
                          f"for job {job_id}: {e} (waiting {wait}s)")
                    time.sleep(wait)

        raise RuntimeError(f"Submit failed after {max_retries} attempts: {last_error}")

    def _send_heartbeat(self):
        """Send heartbeat to master."""
        data = json.dumps({"worker_id": self.worker_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.master_url}/distribution/heartbeat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=5)
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
        data = json.dumps({
            "job_id": job_id,
            "error": error,
            "worker_id": self.worker_id
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.master_url}/distribution/fail_job",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=10)
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
