"""
Distributed Task Manager
Thread-safe job queue for distributing generation work across multiple ComfyUI instances.
Uses a pull-based model: workers claim jobs from the master via API.
"""

import threading
import time
import json
import os
import uuid


class JobState:
    """Job lifecycle states."""
    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"


class DistributedJob:
    """Represents a single job in the distributed queue."""
    __slots__ = [
        'job_id', 'config', 'input_job', 'state', 'worker_id',
        'claimed_at', 'completed_at', 'error', 'gen_index', 'fail_count'
    ]

    def __init__(self, job_id, config, input_job, gen_index):
        self.job_id = job_id
        self.config = config          # Expanded config dict (sampler, model, lora, etc.)
        self.input_job = input_job    # {label, width, height, batch_idx}
        self.state = JobState.PENDING
        self.worker_id = None
        self.claimed_at = None
        self.completed_at = None
        self.error = None
        self.gen_index = gen_index    # Sequential index for deterministic sort ordering
        self.fail_count = 0


class DistributionManager:
    """
    Thread-safe job distribution coordinator.

    Manages an in-memory job list with atomic claim/complete/fail operations.
    The master populates jobs at startup, then workers claim them one at a time.
    Jobs that time out (worker crash) are automatically re-queued.
    """

    # Max times a job can fail before being permanently abandoned
    MAX_FAIL_COUNT = 3

    def __init__(self, session_name, paths, unique_id, existing_data,
                 claim_timeout_seconds=600):
        self._lock = threading.Lock()
        self._jobs = {}               # job_id -> DistributedJob
        self._pending_queue = []      # List of job_ids in FIFO order
        self._workers = {}            # worker_id -> {url, last_heartbeat, jobs_completed, ...}
        self.session_name = session_name
        self.paths = paths
        self.unique_id = unique_id
        self.existing_data = existing_data  # Shared manifest reference
        self.claim_timeout = claim_timeout_seconds
        self._persistence_path = os.path.join(paths["base"], "distribution_state.json")
        self._active = True
        self._total_completed = 0
        # Pre-encoded conditionings from master, keyed by "(model_key|lora_key)"
        # Structure: {"model|lora": {"positive": {prompt: serialized}, "negative": {...}}}
        # Populated by master pre-encoding phase; attached to job claim responses
        self._encoded_conditionings = {}
        # Model sync: when enabled, job claim responses include upcoming_models for pre-fetching
        self.sync_models_to_workers = False
        # Session-level settings (upscaling, cooldown) passed through to workers
        self._session_settings = None

    def populate_jobs(self, expanded_configs, input_jobs, existing_data,
                      overwrite_existing, has_optional_inputs, lora_triggerwords_mode):
        """
        Build the full job list from expanded configs × input jobs.
        Filters out already-completed jobs using check_if_job_completed().

        Args:
            expanded_configs: List of expanded config dicts (from expand_configs())
            input_jobs: List of input job dicts (from prepare_input_jobs())
            existing_data: Loaded manifest data for skip detection
            overwrite_existing: If True, don't skip completed jobs
            has_optional_inputs: If True, relaxed skip matching
            lora_triggerwords_mode: Trigger word mode string
        """
        from .generation_orchestrator import check_if_job_completed
        from .trigger_words import build_prompt_with_triggers

        existing_items = existing_data.get("items", [])
        gen_index_offset = len(existing_items)
        skipped = 0
        total = 0

        with self._lock:
            job_index = 0
            for job_idx, job in enumerate(input_jobs):
                w = job["width"]
                h = job["height"]
                batch_idx = job.get("batch_idx", 0)

                for conf_idx, conf in enumerate(expanded_configs):
                    total += 1

                    # Per-config resolution override
                    if conf.get("resolution") is not None:
                        if job_idx > 0:
                            continue
                        w = conf["resolution"][0]
                        h = conf["resolution"][1]
                        batch_idx = 0

                    # Compute actual prompts (with trigger words applied)
                    # build_prompt_with_triggers returns (final_positive, trigger_string)
                    try:
                        actual_positive, _ = build_prompt_with_triggers(
                            conf, lora_triggerwords_mode
                        )
                    except Exception:
                        actual_positive = conf.get("positive", "")
                    actual_negative = conf.get("negative", "")

                    # Skip detection (same logic as main generation loop)
                    if not overwrite_existing:
                        match_index = check_if_job_completed(
                            existing_items, conf,
                            conf.get("seed", 0), w, h, batch_idx,
                            actual_positive, actual_negative,
                            has_optional_inputs=has_optional_inputs
                        )
                        if match_index != -1:
                            skipped += 1
                            continue

                    # Create job with serializable input_job (no latent tensors)
                    serializable_input_job = {
                        "label": job.get("label", f"{w}x{h}"),
                        "width": w,
                        "height": h,
                        "batch_idx": batch_idx
                    }

                    job_id = str(uuid.uuid4())[:12]
                    gen_index = gen_index_offset + job_index

                    distributed_job = DistributedJob(
                        job_id=job_id,
                        config=conf,
                        input_job=serializable_input_job,
                        gen_index=gen_index
                    )

                    self._jobs[job_id] = distributed_job
                    self._pending_queue.append(job_id)
                    job_index += 1

            self._persist_state()

        print(f"[Distribution] 📋 Populated {len(self._jobs)} jobs "
              f"({skipped} skipped, {total} total before filtering)")

    def claim_job(self, worker_id):
        """
        Atomically claim the next pending job for a worker.

        Returns:
            dict with job details, or None if no pending jobs.
        """
        with self._lock:
            # Release timed-out claimed jobs first
            self._release_timed_out_jobs()

            if not self._pending_queue:
                return None

            job_id = self._pending_queue.pop(0)
            job = self._jobs[job_id]
            job.state = JobState.CLAIMED
            job.worker_id = worker_id
            job.claimed_at = time.time()

            self._persist_state()

            return self._job_to_dict(job)

    def complete_job(self, job_id, metadata=None):
        """
        Mark a job as completed.

        Guards against double-completion (can happen if a job times out and is
        reclaimed by another worker, then the original worker finishes late).

        Args:
            job_id: The job ID string
            metadata: Optional metadata dict (not stored in job, just for logging)

        Returns:
            True if job was found and completed, False otherwise.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                print(f"[Distribution] ⚠️ complete_job: unknown job_id {job_id}")
                return False

            # Prevent double-completion (job may have been reclaimed after timeout)
            if job.state == JobState.COMPLETED:
                print(f"[Distribution] ⚠️ complete_job: job {job_id} already completed, ignoring duplicate")
                return False

            job.state = JobState.COMPLETED
            job.completed_at = time.time()
            self._total_completed += 1

            # Update worker stats
            if job.worker_id and job.worker_id in self._workers:
                self._workers[job.worker_id]["jobs_completed"] += 1

            self._persist_state()
            return True

    def fail_job(self, job_id, error_msg=""):
        """
        Mark a job as failed and re-queue to pending (up to MAX_FAIL_COUNT times).

        Args:
            job_id: The job ID string
            error_msg: Error description

        Returns:
            True if job was found and re-queued, False otherwise.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                print(f"[Distribution] ⚠️ fail_job: unknown job_id {job_id}")
                return False

            job.fail_count += 1

            # Update worker stats
            if job.worker_id and job.worker_id in self._workers:
                self._workers[job.worker_id]["jobs_failed"] += 1

            if job.fail_count >= self.MAX_FAIL_COUNT:
                job.state = JobState.FAILED
                job.error = error_msg
                print(f"[Distribution] ❌ Job {job_id} permanently failed after "
                      f"{job.fail_count} attempts: {error_msg}")
            else:
                job.state = JobState.PENDING
                job.worker_id = None
                job.claimed_at = None
                job.error = error_msg
                self._pending_queue.append(job_id)
                print(f"[Distribution] 🔄 Job {job_id} re-queued "
                      f"(attempt {job.fail_count}/{self.MAX_FAIL_COUNT}): {error_msg}")

            self._persist_state()
            return True

    def claim_batch_for_local(self, count):
        """
        Claim a batch of jobs for the master's local processing.
        Uses worker_id "master" to distinguish from remote workers.

        Args:
            count: Maximum number of jobs to claim

        Returns:
            List of job dicts (may be empty).
        """
        with self._lock:
            self._release_timed_out_jobs()

            batch = []
            for _ in range(min(count, len(self._pending_queue))):
                job_id = self._pending_queue.pop(0)
                job = self._jobs[job_id]
                job.state = JobState.CLAIMED
                job.worker_id = "master"
                job.claimed_at = time.time()
                batch.append(self._job_to_dict(job))

            if batch:
                self._persist_state()

            return batch

    def heartbeat(self, worker_id):
        """Update worker heartbeat timestamp."""
        with self._lock:
            if worker_id in self._workers:
                self._workers[worker_id]["last_heartbeat"] = time.time()

    def register_worker(self, worker_id, worker_url=""):
        """
        Register a new worker.

        Args:
            worker_id: Unique worker identifier
            worker_url: Worker's base URL (for display/monitoring only)
        """
        with self._lock:
            self._workers[worker_id] = {
                "url": worker_url,
                "last_heartbeat": time.time(),
                "jobs_completed": 0,
                "jobs_failed": 0,
                "jobs_duplicated": 0,
                "status": "idle"
            }
            print(f"[Distribution] 🤝 Worker registered: {worker_id} ({worker_url})")

    def record_late_submission(self, worker_id):
        """
        Record a duplicate/late submission from a worker.

        Called when a worker submits a result for a job that was already completed
        (e.g. because the job timed out, was reclaimed by master, and completed
        before the worker finished). The worker did real work — this tracks it.

        Args:
            worker_id: The worker that submitted late
        """
        with self._lock:
            if worker_id in self._workers:
                self._workers[worker_id]["jobs_duplicated"] += 1

    def get_status(self):
        """Return overall progress status."""
        with self._lock:
            total = len(self._jobs)
            pending = len(self._pending_queue)
            claimed = sum(1 for j in self._jobs.values()
                         if j.state == JobState.CLAIMED)
            completed = sum(1 for j in self._jobs.values()
                           if j.state == JobState.COMPLETED)
            failed = sum(1 for j in self._jobs.values()
                        if j.state == JobState.FAILED)

            return {
                "total": total,
                "pending": pending,
                "claimed": claimed,
                "completed": completed,
                "failed": failed,
                "workers": {
                    wid: info.copy()
                    for wid, info in self._workers.items()
                }
            }

    def deactivate(self):
        """Mark the distribution manager as inactive (generation complete)."""
        with self._lock:
            self._active = False

    @property
    def is_active(self):
        """Check if distribution is still active."""
        with self._lock:
            return self._active

    @property
    def has_pending_or_claimed(self):
        """True if any jobs are still pending or claimed (excluding failed)."""
        with self._lock:
            return any(
                j.state in (JobState.PENDING, JobState.CLAIMED)
                for j in self._jobs.values()
            )

    @property
    def total_completed(self):
        """Number of completed jobs."""
        with self._lock:
            return self._total_completed

    def set_encoded_conditionings(self, encoded_dict):
        """
        Store pre-encoded conditionings from the master's pre-encoding phase.

        Args:
            encoded_dict: Dict keyed by "(model_cache_key|lora_key)" with structure:
                {"positive": {prompt_text: serialized_list}, "negative": {prompt_text: serialized_list}}
        """
        with self._lock:
            self._encoded_conditionings = encoded_dict
            total_groups = len(encoded_dict)
            total_prompts = sum(
                len(v.get("positive", {})) + len(v.get("negative", {}))
                for v in encoded_dict.values()
            )
            print(f"[Distribution] 🧠 Stored pre-encoded conditionings: "
                  f"{total_groups} model/LoRA groups, {total_prompts} total prompt encodings")

    def get_encoded_conditionings_for_job(self, job):
        """
        Look up pre-encoded conditionings for a specific job.

        Uses the job's config to compute the group key and prompt text,
        then returns the matching serialized positive/negative conditionings.

        Args:
            job: DistributedJob instance

        Returns:
            dict with "encoded_positive" and "encoded_negative" keys, or None if not available.
        """
        if not self._encoded_conditionings:
            return None

        try:
            from .generation_orchestrator import get_model_cache_key
            from .trigger_words import build_prompt_with_triggers

            config = job.config

            # Build the group key: "model_cache_key|lora_key"
            model_key = get_model_cache_key(config)
            lora_key = config.get("lora_expanded", config.get("lora", "None"))
            group_key = f"{model_key}|{lora_key}"

            group = self._encoded_conditionings.get(group_key)
            if not group:
                return None

            # Build the actual prompt text (with trigger words applied)
            lora_triggerwords_mode = config.get("_lora_triggerwords_mode", "None")
            try:
                actual_positive, _ = build_prompt_with_triggers(config, lora_triggerwords_mode)
            except Exception:
                actual_positive = config.get("positive", "")
            actual_negative = config.get("negative", "")

            encoded_positive = group.get("positive", {}).get(actual_positive)
            encoded_negative = group.get("negative", {}).get(actual_negative)

            if encoded_positive is not None and encoded_negative is not None:
                return {
                    "encoded_positive": encoded_positive,
                    "encoded_negative": encoded_negative,
                    # Include final prompt text so workers can use it for metadata
                    # without needing to re-run trigger word lookups
                    "actual_positive_text": actual_positive,
                    "actual_negative_text": actual_negative,
                }

            return None

        except Exception as e:
            print(f"[Distribution] ⚠️ Error looking up conditionings for job {job.job_id}: {e}")
            return None

    def _release_timed_out_jobs(self):
        """
        Release jobs that have been claimed but not completed within timeout.
        Must be called with lock held.

        Uses the worker's last heartbeat timestamp (not just job claimed_at) to
        determine if the worker is still alive. A slow-but-alive worker that
        sends heartbeats will NOT have its jobs reclaimed. Only workers that
        have stopped heartbeating (crash/disconnect) will have jobs reclaimed.
        """
        now = time.time()
        released = 0
        for job in self._jobs.values():
            if (job.state == JobState.CLAIMED
                    and job.worker_id != "master"
                    and job.claimed_at
                    and now - job.claimed_at > self.claim_timeout):

                # Check if the worker is still heartbeating — if so, it's alive
                # and just slow (e.g. slow GPU, first-time model loading).
                # Only reclaim if the worker has gone silent.
                worker = self._workers.get(job.worker_id)
                if worker:
                    last_hb = worker.get("last_heartbeat", 0)
                    if now - last_hb < self.claim_timeout:
                        # Worker is still alive — don't reclaim
                        continue

                print(f"[Distribution] ⏰ Job {job.job_id} timed out "
                      f"from worker {job.worker_id} (no heartbeat), re-queuing")
                job.state = JobState.PENDING
                job.worker_id = None
                job.claimed_at = None
                self._pending_queue.append(job.job_id)
                released += 1

        if released > 0:
            print(f"[Distribution] Released {released} timed-out jobs")

    def release_timed_out_jobs(self):
        """Public wrapper — call from the wait loop to reclaim dead worker jobs."""
        with self._lock:
            self._release_timed_out_jobs()

    def _persist_state(self):
        """
        Persist job states to disk for crash recovery.
        Must be called with lock held.
        """
        state = {
            "session_name": self.session_name,
            "timestamp": time.time(),
            "jobs": {
                jid: {
                    "state": j.state,
                    "worker_id": j.worker_id,
                    "fail_count": j.fail_count
                }
                for jid, j in self._jobs.items()
            }
        }
        try:
            with open(self._persistence_path, "w") as f:
                json.dump(state, f)
        except Exception as e:
            print(f"[Distribution] ⚠️ Persist error: {e}")

    def _get_upcoming_models(self, exclude_job_id=None, limit=10):
        """
        Scan pending jobs and collect unique model references for pre-fetching.
        Must be called with lock held.

        Args:
            exclude_job_id: Job to skip (the current job being claimed)
            limit: Maximum number of unique model references to return

        Returns:
            List of {category, filename} dicts
        """
        seen = set()
        upcoming = []

        for job_id in self._pending_queue:
            if job_id == exclude_job_id:
                continue
            job = self._jobs.get(job_id)
            if not job:
                continue

            config = job.config

            # Main model/checkpoint
            model_name = config.get("model", "None")
            if model_name and model_name != "None":
                model_type = config.get("model_type", "checkpoint")
                if model_type == "checkpoint":
                    cat = "checkpoints"
                elif model_type == "gguf":
                    cat = "unet_gguf"
                elif model_type == "diffusion_model":
                    cat = "diffusion_models"
                else:
                    cat = "checkpoints"
                key = f"{cat}:{model_name}"
                if key not in seen:
                    seen.add(key)
                    upcoming.append({"category": cat, "filename": model_name})

            # LoRA — combo string: "name:str:str + name2:str:str", may include folders
            lora = config.get("lora_expanded", config.get("lora", "None"))
            if lora and lora != "None":
                for lora_part in lora.split(" + "):
                    lora_filename = lora_part.strip().split(":")[0].strip()
                    if not lora_filename or lora_filename == "None":
                        continue
                    # Skip folder references — workers expand those locally
                    if lora_filename.endswith("/") or lora_filename.endswith("/*") or ("[" in lora_filename and "]" in lora_filename):
                        continue
                    key = f"loras:{lora_filename}"
                    if key not in seen:
                        seen.add(key)
                        upcoming.append({"category": "loras", "filename": lora_filename})

            # VAE (skip remote URLs and "Default")
            vae = config.get("vae", "Default")
            if vae and vae != "Default" and not vae.startswith("remote:"):
                key = f"vae:{vae}"
                if key not in seen:
                    seen.add(key)
                    upcoming.append({"category": "vae", "filename": vae})

            # Text encoders
            text_encoders = config.get("text_encoders", [])
            for te in text_encoders:
                if te and te != "None":
                    key = f"text_encoders:{te}"
                    if key not in seen:
                        seen.add(key)
                        upcoming.append({"category": "text_encoders", "filename": te})

            if len(upcoming) >= limit:
                break

        return upcoming

    def _job_to_dict(self, job):
        """
        Convert a DistributedJob to a serializable dict for API responses.
        Note: input_job latent tensors are NOT included (workers create their own).
        Config is round-tripped through JSON to ensure all values are serializable
        (e.g. numpy int64 → Python int, sets → lists, etc.).
        If pre-encoded conditionings are available, they are attached to the response
        so workers can skip CLIP encoding entirely.
        """
        try:
            safe_config = json.loads(json.dumps(job.config, default=str))
        except Exception:
            safe_config = job.config

        result = {
            "job_id": job.job_id,
            "config": safe_config,
            "input_job": job.input_job,
            "gen_index": job.gen_index
        }

        # Attach session-level cooldown settings to worker config
        if hasattr(self, '_session_settings') and self._session_settings and 'cooldown' in self._session_settings:
            safe_config["_session_cooldown"] = self._session_settings["cooldown"]

        # Attach pre-encoded conditionings if available (master encoding feature)
        encoded = self.get_encoded_conditionings_for_job(job)
        if encoded:
            result["encoded_positive"] = encoded["encoded_positive"]
            result["encoded_negative"] = encoded["encoded_negative"]
            # Include final prompt text (with triggers applied) so workers can
            # use it for metadata without re-running CivitAI trigger lookups
            result["actual_positive_text"] = encoded.get("actual_positive_text")
            result["actual_negative_text"] = encoded.get("actual_negative_text")

        # Attach upcoming models list if sync is enabled (for pre-fetching)
        if self.sync_models_to_workers:
            result["upcoming_models"] = self._get_upcoming_models(
                exclude_job_id=job.job_id, limit=10
            )

        return result
