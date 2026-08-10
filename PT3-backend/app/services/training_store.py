from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from app.core import database
from app.core.quality import QualityPreset
from app.schemas.training import TrainingFailureLabel, TrainingExampleCreate, TrainingExampleUpdate
from app.services import job_store, object_storage


@dataclass(frozen=True)
class TrainingExample:
    example_id: str
    job_id: str
    user_id: str
    prompt: str
    quality_preset: QualityPreset
    failure_label: TrainingFailureLabel
    admin_notes: str | None
    image_path: str
    glb_path: str
    image_object_key: str | None
    glb_object_key: str | None
    include_in_sdxl_lora: bool
    include_in_hunyuan: bool
    review_status: str
    created_by: str
    created_at: str
    updated_at: str

    @property
    def has_image(self) -> bool:
        return os.path.exists(self.image_path) or object_storage.exists(self.image_object_key)

    @property
    def has_glb(self) -> bool:
        return os.path.exists(self.glb_path) or object_storage.exists(self.glb_object_key)


def _bool(value) -> bool:
    return bool(int(value or 0))


def _from_row(row) -> TrainingExample:
    return TrainingExample(
        example_id=row["example_id"],
        job_id=row["job_id"],
        user_id=row["user_id"],
        prompt=row["prompt"],
        quality_preset=QualityPreset(row["quality_preset"]),
        failure_label=TrainingFailureLabel(row["failure_label"]),
        admin_notes=row["admin_notes"],
        image_path=row["image_path"],
        glb_path=row["glb_path"],
        image_object_key=row["image_object_key"],
        glb_object_key=row["glb_object_key"],
        include_in_sdxl_lora=_bool(row["include_in_sdxl_lora"]),
        include_in_hunyuan=_bool(row["include_in_hunyuan"]),
        review_status=row["review_status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_from_job(body: TrainingExampleCreate, created_by: str) -> TrainingExample:
    job = job_store.get_job(body.job_id)
    if job is None:
        raise ValueError("Job not found.")

    now = database.utc_now_iso()
    example_id = uuid.uuid4().hex[:12]
    database.execute(
        """
        INSERT INTO training_examples (
            example_id, job_id, user_id, prompt, quality_preset, failure_label,
            admin_notes, image_path, glb_path, image_object_key, glb_object_key,
            include_in_sdxl_lora, include_in_hunyuan, review_status,
            created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            example_id,
            job.job_id,
            job.user_id,
            job.prompt,
            job.quality_preset.value,
            body.failure_label.value,
            body.admin_notes,
            job.image_path,
            job.glb_path,
            job.image_object_key,
            job.glb_object_key,
            int(body.include_in_sdxl_lora),
            int(body.include_in_hunyuan),
            body.review_status,
            created_by,
            now,
            now,
        ),
    )
    example = get_example(example_id)
    if example is None:
        raise RuntimeError("Training example was not persisted.")
    return example


def update_example(example_id: str, body: TrainingExampleUpdate) -> TrainingExample | None:
    current = get_example(example_id)
    if current is None:
        return None

    failure_label = body.failure_label.value if body.failure_label else current.failure_label.value
    admin_notes = body.admin_notes if body.admin_notes is not None else current.admin_notes
    include_in_sdxl_lora = current.include_in_sdxl_lora if body.include_in_sdxl_lora is None else body.include_in_sdxl_lora
    include_in_hunyuan = current.include_in_hunyuan if body.include_in_hunyuan is None else body.include_in_hunyuan
    review_status = body.review_status or current.review_status

    database.execute(
        """
        UPDATE training_examples
        SET failure_label = ?, admin_notes = ?, include_in_sdxl_lora = ?,
            include_in_hunyuan = ?, review_status = ?, updated_at = ?
        WHERE example_id = ?
        """,
        (
            failure_label,
            admin_notes,
            int(include_in_sdxl_lora),
            int(include_in_hunyuan),
            review_status,
            database.utc_now_iso(),
            example_id,
        ),
    )
    return get_example(example_id)


def get_example(example_id: str) -> TrainingExample | None:
    row = database.fetch_one("SELECT * FROM training_examples WHERE example_id = ?", (example_id,))
    return _from_row(row) if row else None


def list_examples() -> list[TrainingExample]:
    rows = database.fetch_all("SELECT * FROM training_examples ORDER BY created_at DESC")
    return [_from_row(row) for row in rows]