from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import database
from app.services import job_store, object_storage


def _upload_if_present(path_value: str, key: str, content_type: str, dry_run: bool) -> bool:
    path = Path(path_value)
    if not path.is_file():
        print(f"missing local file: {path}")
        return False
    if dry_run:
        print(f"would upload {path} -> {key}")
        return True
    object_storage.upload_file(path, key, content_type)
    print(f"uploaded {path} -> {key}")
    return True


def backfill(dry_run: bool) -> None:
    if not object_storage.enabled():
        raise SystemExit(
            "R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME."
        )

    database.init_db()
    jobs = database.fetch_all("SELECT * FROM jobs ORDER BY created_at ASC")
    for job in jobs:
        image_key = job["image_object_key"] or object_storage.object_key(
            job["user_id"], job["job_id"], "png"
        )
        glb_key = job["glb_object_key"] or object_storage.object_key(
            job["user_id"], job["job_id"], "glb"
        )

        image_uploaded = _upload_if_present(job["image_path"], image_key, "image/png", dry_run)
        glb_uploaded = _upload_if_present(
            job["glb_path"], glb_key, "model/gltf-binary", dry_run
        )

        if not dry_run and (image_uploaded or glb_uploaded):
            job_store.set_object_keys(
                job["job_id"],
                image_key if image_uploaded else job["image_object_key"],
                glb_key if glb_uploaded else job["glb_object_key"],
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload existing generated assets to Cloudflare R2.")
    parser.add_argument("--dry-run", action="store_true", help="Print uploads without changing R2 or DB.")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
