from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.config import settings


class ObjectStorageError(Exception):
    """Raised when object storage cannot read or write an asset."""


def enabled() -> bool:
    return all(
        [
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
            settings.r2_bucket_name,
        ]
    )


def _client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise ObjectStorageError("R2 is configured, but boto3 is not installed.") from exc

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def object_key(user_id: str, job_id: str, extension: str) -> str:
    clean_extension = extension.lstrip(".")
    folder = "models" if clean_extension == "glb" else "images"
    return f"{folder}/{user_id}/{job_id}.{clean_extension}"


def upload_file(path: Path, key: str, content_type: str) -> None:
    if not enabled():
        return
    try:
        _client().upload_file(
            str(path),
            settings.r2_bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception as exc:
        raise ObjectStorageError(f"Could not upload {key} to R2: {exc}") from exc


def exists(key: str | None) -> bool:
    if not enabled() or not key:
        return False
    try:
        _client().head_object(Bucket=settings.r2_bucket_name, Key=key)
        return True
    except Exception:
        return False


def open_stream(key: str) -> tuple[BinaryIO, int | None, str | None]:
    if not enabled():
        raise ObjectStorageError("R2 is not configured.")
    try:
        response = _client().get_object(Bucket=settings.r2_bucket_name, Key=key)
    except Exception as exc:
        raise ObjectStorageError(f"Could not read {key} from R2: {exc}") from exc

    return (
        response["Body"],
        response.get("ContentLength"),
        response.get("ContentType"),
    )
