import base64
import binascii
from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, HTTPException, status
from PIL import Image, UnidentifiedImageError

from app.core.auth import current_user
from app.schemas.generate import GenerateImageRequest, GenerateRequest, GenerateResponse
from app.services.auth_service import SessionUser
from app.services.pipeline import pipeline

router = APIRouter(tags=["generate"])

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate(
    body: GenerateRequest,
    user: SessionUser = Depends(current_user),
) -> GenerateResponse:
    """
    Start a 3D generation job.

    - **202 Accepted** - job queued, returns `job_id`
    - **409 Conflict** - pipeline is already running
    """
    job_id = pipeline.start_job(user.user_id, body.prompt, body.quality_preset)

    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline is busy. Wait for the current job to finish.",
        )

    return GenerateResponse(status="started", job_id=job_id, quality_preset=body.quality_preset)


@router.post(
    "/generate/image",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_from_image(
    body: GenerateImageRequest,
    user: SessionUser = Depends(current_user),
) -> GenerateResponse:
    """
    Start a 3D generation job from an uploaded image.

    This skips SDXL image generation and runs only image -> Hunyuan3D -> GLB.
    """
    if body.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a PNG, JPEG, or WebP image.",
        )

    try:
        data = base64.b64decode(body.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image data.") from exc

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must be 12 MB or smaller.",
        )

    temp_path: Path | None = None
    try:
        from io import BytesIO

        with Image.open(BytesIO(data)) as uploaded:
            uploaded.verify()
        with Image.open(BytesIO(data)) as uploaded:
            normalized = uploaded.convert("RGBA")
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            temp_path = Path(handle.name)
            handle.close()
            normalized.save(temp_path, format="PNG")
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image file.") from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image could not be processed.") from exc

    job_id = pipeline.start_image_job(user.user_id, body.prompt, temp_path, body.quality_preset)
    if job_id is None:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline is busy. Wait for the current job to finish.",
        )

    return GenerateResponse(status="started", job_id=job_id, quality_preset=body.quality_preset)
