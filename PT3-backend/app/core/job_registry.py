"""
Thread-safe in-memory store for all job state.

Both HTTP route handlers and background pipeline threads read/write here.
The registry has no dependencies on other app modules — it is a pure data store.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    SDXL_RUNNING = "sdxl_running"
    MULTIVIEW = "multiview"      # Zero123++ generating consistent orbital views
    CONVERTING = "converting"
    DONE = "done"
    FAILED = "failed"


@dataclass
class JobRecord:
    job_id: str
    user_id: str
    prompt: str
    status: JobStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


class JobRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, JobRecord] = {}

    def create(self, job_id: str, user_id: str, prompt: str) -> JobRecord:
        record = JobRecord(
            job_id=job_id,
            user_id=user_id,
            prompt=prompt,
            status=JobStatus.QUEUED,
        )
        with self._lock:
            self._store[job_id] = record
        return record

    def update_status(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            if job_id in self._store:
                self._store[job_id].status = status

    def set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            if job_id in self._store:
                self._store[job_id].error = error

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._store.get(job_id)


# Module-level singleton — imported by both routes and services
registry = JobRegistry()
