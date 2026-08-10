from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.core.auth import current_user
from app.schemas.job import JobStatusResponse
from app.services import job_store
from app.services.auth_service import SessionUser

router = APIRouter(tags=["status"])


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str = Path(..., pattern=r"^[a-f0-9]{10}$"),
    user: SessionUser = Depends(current_user),
) -> JobStatusResponse:
    """
    Poll the status of a generation job.

    Status progression:
        queued → sdxl_running → converting → done | failed

    - **200 OK** – returns current job state
    - **404 Not Found** – unknown job_id
    """
    job = job_store.get_user_job(job_id, user.user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        prompt=job.prompt,
        quality_preset=job.quality_preset,
        created_at=datetime.fromisoformat(job.created_at),
        error=job.error,
    )
