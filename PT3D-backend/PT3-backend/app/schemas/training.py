from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.core.quality import QualityPreset


class TrainingFailureLabel(str, Enum):
    BAD_IMAGE = "bad_image"
    BAD_SHAPE = "bad_shape"
    BAD_TEXTURE = "bad_texture"
    MISSING_PARTS = "missing_parts"
    WRONG_CATEGORY = "wrong_category"
    PREVIEW_FAILED = "preview_failed"
    GOOD_REFERENCE = "good_reference"


class TrainingExampleCreate(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    failure_label: TrainingFailureLabel
    admin_notes: str | None = Field(default=None, max_length=1000)
    include_in_sdxl_lora: bool = False
    include_in_hunyuan: bool = False
    review_status: str = Field(default="candidate", min_length=1, max_length=32)


class TrainingExampleUpdate(BaseModel):
    failure_label: TrainingFailureLabel | None = None
    admin_notes: str | None = Field(default=None, max_length=1000)
    include_in_sdxl_lora: bool | None = None
    include_in_hunyuan: bool | None = None
    review_status: str | None = Field(default=None, min_length=1, max_length=32)


class TrainingExampleResponse(BaseModel):
    example_id: str
    job_id: str
    user_id: str
    prompt: str
    quality_preset: QualityPreset
    failure_label: TrainingFailureLabel
    admin_notes: str | None
    include_in_sdxl_lora: bool
    include_in_hunyuan: bool
    review_status: str
    has_image: bool
    has_glb: bool
    created_by: str
    created_at: str
    updated_at: str