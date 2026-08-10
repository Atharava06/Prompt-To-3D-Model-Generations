from fastapi import APIRouter, Depends

from app.core.auth import current_user
from app.schemas.job import JobSummaryResponse
from app.services import job_store
from app.services.auth_service import SessionUser

router = APIRouter(tags=["jobs"])


def _summary(job) -> JobSummaryResponse:
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


@router.get("/jobs", response_model=list[JobSummaryResponse])
def list_jobs(user: SessionUser = Depends(current_user)) -> list[JobSummaryResponse]:
    return [_summary(job) for job in job_store.list_user_jobs(user.user_id)]
