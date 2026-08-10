import os

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.auth import current_user
from app.services import job_store, object_storage
from app.services.auth_service import SessionUser

router = APIRouter(tags=["models"])

_GLB_MEDIA_TYPE = "model/gltf-binary"


@router.head("/latest.glb")
def head_latest_glb(user: SessionUser = Depends(current_user)) -> Response:
    job = job_store.latest_user_job_with_glb(user.user_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(headers={"content-type": _GLB_MEDIA_TYPE})


@router.get("/latest.glb", response_class=FileResponse)
def latest_glb(user: SessionUser = Depends(current_user)):
    job = job_store.latest_user_job_with_glb(user.user_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GLB files found yet.",
        )
    return _glb_response(job, f"{job.job_id}.glb")


@router.get("/glb/{filename}", response_class=FileResponse)
def get_glb_by_id(
    filename: str = Path(..., pattern=r"^[a-f0-9]{10}\.glb$"),
    user: SessionUser = Depends(current_user),
) -> Response:
    job_id = filename.removesuffix(".glb")
    job = job_store.get_user_job(job_id, user.user_id)
    if job is None or not job.has_glb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GLB not ready yet. Poll /status/{job_id} for progress.",
        )
    return _glb_response(job, filename)


def _glb_response(job, filename: str) -> Response:
    if object_storage.enabled() and job.glb_object_key:
        try:
            stream, content_length, content_type = object_storage.open_stream(job.glb_object_key)
        except object_storage.ObjectStorageError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        return StreamingResponse(
            stream,
            media_type=content_type or _GLB_MEDIA_TYPE,
            headers=headers,
        )

    if os.path.exists(job.glb_path):
        return FileResponse(job.glb_path, media_type=_GLB_MEDIA_TYPE, filename=filename)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="GLB not ready yet. Poll /status/{job_id} for progress.",
    )
