from datetime import datetime

from pydantic import BaseModel

from app.core.job_registry import JobStatus
from app.core.quality import QualityPreset


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    prompt: str
    quality_preset: QualityPreset
    created_at: datetime
    error: str | None = None


class JobSummaryResponse(BaseModel):
    job_id: str
    prompt: str
    quality_preset: QualityPreset
    status: JobStatus
    created_at: str
    updated_at: str
    error: str | None = None
    has_image: bool
    has_glb: bool
