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

        # Register with master
        self._register()

        last_heartbeat = time.time()

        while not self._stop_event.is_set():
            # Periodic heartbeat
            if time.time() - last_heartbeat > self.heartbeat_interval:
                self._send_heartbeat()
                last_heartbeat = time.time()

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

            # Process the job
            try:
                image_bytes, meta = self._process_job(job)

                # Submit result
                self._submit_result(job["job_id"], image_bytes, meta)
                self.jobs_processed += 1

                print(f"[Worker {self.worker_id}] ✅ Job {job['job_id']} complete "
                      f"(total: {self.jobs_processed})")

            except Exception as e:
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
        # Build prompt with trigger words
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
            attention_mode=attention_mode
        )

        # --- VAE Decode ---
        image = decode_latent_with_vae(vae, result_latent["samples"])

        # --- Convert to bytes ---
        buf = io.BytesIO()
        image.save(buf, format="WEBP", quality=80)
        image_bytes = buf.getvalue()

        # --- Create metadata ---
        ts = int(time.time() * 100000) + random.randint(0, 1000)
        meta = create_image_metadata(
            config, w, h, duration, config["seed"],
            batch_idx, actual_positive, actual_negative,
            gen_index=job.get("gen_index")
        )
        meta["id"] = ts

        # Free latent tensors
        del result_latent, latent_in, pos_cond, neg_cond

        return image_bytes, meta

    def _submit_result(self, job_id, image_bytes, meta):
        """
        Upload image + metadata to master via multipart POST.
        Uses urllib (no 'requests' library for ComfyUI Registry compliance).
        """
        boundary = f"----DistWorker{uuid.uuid4().hex[:16]}"

        # Build multipart body manually
        body = b""

        # Metadata part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="metadata"\r\n'
        body += b'Content-Type: application/json\r\n\r\n'
        body += json.dumps({
            "job_id": job_id,
            "meta": meta,
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
