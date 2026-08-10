from pydantic import BaseModel, field_validator

from app.core.quality import QualityPreset


MAX_PROMPT_CHARS = 500


class GenerateRequest(BaseModel):
    prompt: str
    quality_preset: QualityPreset = QualityPreset.BALANCED

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Prompt must not be empty")
        if len(v) > MAX_PROMPT_CHARS:
            raise ValueError(f"Prompt must be {MAX_PROMPT_CHARS} characters or fewer")
        return v


class GenerateImageRequest(BaseModel):
    prompt: str = "Uploaded reference image"
    quality_preset: QualityPreset = QualityPreset.BALANCED
    image_base64: str
    content_type: str = "image/png"

    @field_validator("prompt")
    @classmethod
    def prompt_valid(cls, v: str) -> str:
        v = v.strip() or "Uploaded reference image"
        if len(v) > MAX_PROMPT_CHARS:
            raise ValueError(f"Prompt must be {MAX_PROMPT_CHARS} characters or fewer")
        return v

    @field_validator("image_base64")
    @classmethod
    def image_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Image data must not be empty")
        return v


class GenerateResponse(BaseModel):
    status: str
    job_id: str
    quality_preset: QualityPreset
