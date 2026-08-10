import os

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.auth import current_user
from app.services import job_store, object_storage
from app.services.auth_service import SessionUser

router = APIRouter(tags=["images"])

_PNG_MEDIA_TYPE = "image/png"


@router.get("/image/{job_id}", response_class=FileResponse)
def get_image(
    job_id: str = Path(..., pattern=r"^[a-f0-9]{10}$"),
    user: SessionUser = Depends(current_user),
) -> Response:
    job = job_store.get_user_job(job_id, user.user_id)
    if job is None or not job.has_image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not ready yet. The job may still be running.",
        )
    return _image_response(job, f"{job_id}.png")


@router.get("/latest-image", response_class=FileResponse)
def latest_image(user: SessionUser = Depends(current_user)) -> Response:
    job = job_store.latest_user_job_with_image(user.user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No images generated yet.",
        )
    return _image_response(job, f"{job.job_id}.png")


def _image_response(job, filename: str) -> Response:
    if object_storage.enabled() and job.image_object_key:
        try:
            stream, content_length, content_type = object_storage.open_stream(job.image_object_key)
        except object_storage.ObjectStorageError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        headers = {"Content-Disposition": f'inline; filename="{filename}"'}
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        return StreamingResponse(
            stream,
            media_type=content_type or _PNG_MEDIA_TYPE,
            headers=headers,
        )

    if os.path.exists(job.image_path):
        return FileResponse(job.image_path, media_type=_PNG_MEDIA_TYPE, filename=filename)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Image not ready yet. The job may still be running.",
    )
