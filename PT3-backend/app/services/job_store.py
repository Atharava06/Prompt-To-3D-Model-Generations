from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core import database
from app.core.job_registry import JobStatus
from app.core.quality import QualityPreset
from app.services import object_storage


@dataclass(frozen=True)
class StoredJob:
    job_id: str
    user_id: str
    prompt: str
    status: JobStatus
    created_at: str
    updated_at: str
    image_path: str
    glb_path: str
    quality_preset: QualityPreset = QualityPreset.BALANCED
    image_object_key: str | None = None
    glb_object_key: str | None = None
    error: str | None = None

    @property
    def has_image(self) -> bool:
        return os.path.exists(self.image_path) or object_storage.exists(self.image_object_key)

    @property
    def has_glb(self) -> bool:
        return os.path.exists(self.glb_path) or object_storage.exists(self.glb_object_key)


def _optional(row, column: str, default=None):
    if hasattr(row, "get"):
        return row.get(column, default)
    try:
        return row[column]
    except (IndexError, KeyError):
        return default


def _job_from_row(row) -> StoredJob:
    return StoredJob(
        job_id=row["job_id"],
        user_id=row["user_id"],
        prompt=row["prompt"],
        status=JobStatus(row["status"]),
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        image_path=row["image_path"],
        glb_path=row["glb_path"],
        quality_preset=QualityPreset(_optional(row, "quality_preset", QualityPreset.BALANCED.value)),
        image_object_key=_optional(row, "image_object_key"),
        glb_object_key=_optional(row, "glb_object_key"),
    )


def create_job(
    job_id: str,
    user_id: str,
    prompt: str,
    image_path: Path,
    glb_path: Path,
    quality_preset: QualityPreset = QualityPreset.BALANCED,
) -> StoredJob:
    now = database.utc_now_iso()
    database.execute(
        """
        INSERT INTO jobs (
            job_id, user_id, prompt, status, error, created_at, updated_at,
            image_path, glb_path, quality_preset
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            user_id,
            prompt,
            JobStatus.QUEUED.value,
            now,
            now,
            str(image_path),
            str(glb_path),
            quality_preset.value,
        ),
    )
    job = get_job(job_id)
    if job is None:
        raise RuntimeError(f"Job {job_id} was not persisted.")
    return job


def update_status(job_id: str, status: JobStatus) -> None:
    database.execute(
        "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
        (status.value, database.utc_now_iso(), job_id),
    )


def set_error(job_id: str, error: str) -> None:
    database.execute(
        "UPDATE jobs SET error = ?, updated_at = ? WHERE job_id = ?",
        (error, database.utc_now_iso(), job_id),
    )


def set_object_keys(job_id: str, image_object_key: str | None, glb_object_key: str | None) -> None:
    database.execute(
        """
        UPDATE jobs
        SET image_object_key = ?, glb_object_key = ?, updated_at = ?
        WHERE job_id = ?
        """,
        (image_object_key, glb_object_key, database.utc_now_iso(), job_id),
    )


def get_job(job_id: str) -> StoredJob | None:
    row = database.fetch_one("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    return _job_from_row(row) if row else None


def get_user_job(job_id: str, user_id: str) -> StoredJob | None:
    row = database.fetch_one(
        "SELECT * FROM jobs WHERE job_id = ? AND user_id = ?",
        (job_id, user_id),
    )
    return _job_from_row(row) if row else None


def list_user_jobs(user_id: str) -> list[StoredJob]:
    rows = database.fetch_all(
        "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    return [_job_from_row(row) for row in rows]


def latest_user_job_with_glb(user_id: str) -> StoredJob | None:
    rows = database.fetch_all(
        """
        SELECT * FROM jobs
        WHERE user_id = ? AND status = ?
        ORDER BY updated_at DESC
        """,
        (user_id, JobStatus.DONE.value),
    )
    for row in rows:
        job = _job_from_row(row)
        if job.has_glb:
            return job
    return None


def latest_user_job_with_image(user_id: str) -> StoredJob | None:
    rows = database.fetch_all(
        """
        SELECT * FROM jobs
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    for row in rows:
        job = _job_from_row(row)
        if job.has_image:
            return job
    return None


def list_queued_jobs() -> list[StoredJob]:
    rows = database.fetch_all(
        "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC",
        (JobStatus.QUEUED.value,),
    )
    return [_job_from_row(row) for row in rows]


def reset_interrupted_jobs() -> int:
    interrupted = (JobStatus.SDXL_RUNNING.value, JobStatus.CONVERTING.value, JobStatus.MULTIVIEW.value)
    return database.execute(
        f"""
        UPDATE jobs
        SET status = ?, updated_at = ?
        WHERE status IN ({','.join('?' for _ in interrupted)})
        """,
        (JobStatus.QUEUED.value, database.utc_now_iso(), *interrupted),
    )