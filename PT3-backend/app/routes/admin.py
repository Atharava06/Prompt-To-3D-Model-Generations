from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import settings
from app.core import database
from app.core.auth import current_user
from app.schemas.job import JobSummaryResponse
from app.schemas.training import (
    TrainingExampleCreate,
    TrainingExampleResponse,
    TrainingExampleUpdate,
)
from app.services import job_store, object_storage, training_store
from app.services.auth_service import SessionUser

router = APIRouter(prefix="/admin", tags=["admin"])


class TrainingConfigResponse(BaseModel):
    sdxl_lora_enabled: bool
    sdxl_lora_path: str | None
    sdxl_lora_scale: float
    hunyuan_finetuned_enabled: bool
    hunyuan_finetuned_model_path: str | None
    hunyuan_model_path: str
    hunyuan_subfolder: str


def require_admin(user: SessionUser = Depends(current_user)) -> SessionUser:
    if user.user_id not in settings.admin_user_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user


def _job_summary(job: job_store.StoredJob) -> JobSummaryResponse:
    return JobSummaryResponse(
        job_id=job.job_id,
        prompt=job.prompt,
        quality_preset=job.quality_preset,
        status=job.status,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        has_image=job.has_image,
        has_glb=job.has_glb,
    )


def _training_response(example: training_store.TrainingExample) -> TrainingExampleResponse:
    return TrainingExampleResponse(
        example_id=example.example_id,
        job_id=example.job_id,
        user_id=example.user_id,
        prompt=example.prompt,
        quality_preset=example.quality_preset,
        failure_label=example.failure_label,
        admin_notes=example.admin_notes,
        include_in_sdxl_lora=example.include_in_sdxl_lora,
        include_in_hunyuan=example.include_in_hunyuan,
        review_status=example.review_status,
        has_image=example.has_image,
        has_glb=example.has_glb,
        created_by=example.created_by,
        created_at=example.created_at,
        updated_at=example.updated_at,
    )


@router.get("/export.csv")
def export_csv(_: SessionUser = Depends(require_admin)) -> Response:
    users = database.fetch_all(
        """
        SELECT user_id, display_name, created_at
        FROM users
        ORDER BY created_at DESC
        """
    )
    jobs = database.fetch_all(
        """
        SELECT
            job_id, user_id, prompt, status, error, created_at, updated_at,
            image_path, glb_path, quality_preset, image_object_key, glb_object_key
        FROM jobs
        ORDER BY created_at DESC
        """
    )

    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "row_type",
            "user_id",
            "display_name",
            "user_created_at",
            "job_id",
            "prompt",
            "status",
            "quality_preset",
            "error",
            "job_created_at",
            "job_updated_at",
            "has_image",
            "has_glb",
        ],
    )
    writer.writeheader()

    for user in users:
        writer.writerow(
            {
                "row_type": "user",
                "user_id": user["user_id"],
                "display_name": user["display_name"],
                "user_created_at": user["created_at"],
            }
        )

    for job in jobs:
        writer.writerow(
            {
                "row_type": "job",
                "user_id": job["user_id"],
                "job_id": job["job_id"],
                "prompt": job["prompt"],
                "status": job["status"],
                "quality_preset": job["quality_preset"],
                "error": job["error"] or "",
                "job_created_at": job["created_at"],
                "job_updated_at": job["updated_at"],
                "has_image": Path(job["image_path"]).is_file()
                or object_storage.exists(job["image_object_key"]),
                "has_glb": Path(job["glb_path"]).is_file()
                or object_storage.exists(job["glb_object_key"]),
            }
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="prompt-to-3d-export.csv"'},
    )


@router.get("/jobs", response_model=list[JobSummaryResponse])
def admin_jobs(_: SessionUser = Depends(require_admin)) -> list[JobSummaryResponse]:
    rows = database.fetch_all("SELECT * FROM jobs ORDER BY created_at DESC")
    return [_job_summary(job_store._job_from_row(row)) for row in rows]


@router.get("/training/config", response_model=TrainingConfigResponse)
def training_config(_: SessionUser = Depends(require_admin)) -> TrainingConfigResponse:
    return TrainingConfigResponse(
        sdxl_lora_enabled=bool(settings.sdxl_lora_path),
        sdxl_lora_path=settings.sdxl_lora_path,
        sdxl_lora_scale=settings.sdxl_lora_scale,
        hunyuan_finetuned_enabled=bool(settings.hunyuan_finetuned_model_path),
        hunyuan_finetuned_model_path=settings.hunyuan_finetuned_model_path,
        hunyuan_model_path=settings.hunyuan_model_path,
        hunyuan_subfolder=settings.hunyuan_subfolder,
    )


@router.get("/training/examples", response_model=list[TrainingExampleResponse])
def list_training_examples(_: SessionUser = Depends(require_admin)) -> list[TrainingExampleResponse]:
    return [_training_response(example) for example in training_store.list_examples()]


@router.post(
    "/training/examples",
    response_model=TrainingExampleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_training_example(
    body: TrainingExampleCreate,
    user: SessionUser = Depends(require_admin),
) -> TrainingExampleResponse:
    try:
        example = training_store.create_from_job(body, user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _training_response(example)


@router.patch("/training/examples/{example_id}", response_model=TrainingExampleResponse)
def update_training_example(
    example_id: str,
    body: TrainingExampleUpdate,
    _: SessionUser = Depends(require_admin),
) -> TrainingExampleResponse:
    example = training_store.update_example(example_id, body)
    if example is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training example not found.")
    return _training_response(example)


@router.get("/training/examples.csv")
def training_examples_csv(_: SessionUser = Depends(require_admin)) -> Response:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "example_id",
            "job_id",
            "user_id",
            "prompt",
            "quality_preset",
            "failure_label",
            "review_status",
            "include_in_sdxl_lora",
            "include_in_hunyuan",
            "has_image",
            "has_glb",
            "admin_notes",
            "created_by",
            "created_at",
            "updated_at",
        ],
    )
    writer.writeheader()
    for example in training_store.list_examples():
        writer.writerow(
            {
                "example_id": example.example_id,
                "job_id": example.job_id,
                "user_id": example.user_id,
                "prompt": example.prompt,
                "quality_preset": example.quality_preset.value,
                "failure_label": example.failure_label.value,
                "review_status": example.review_status,
                "include_in_sdxl_lora": example.include_in_sdxl_lora,
                "include_in_hunyuan": example.include_in_hunyuan,
                "has_image": example.has_image,
                "has_glb": example.has_glb,
                "admin_notes": example.admin_notes or "",
                "created_by": example.created_by,
                "created_at": example.created_at,
                "updated_at": example.updated_at,
            }
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="training-examples.csv"'},
    )
