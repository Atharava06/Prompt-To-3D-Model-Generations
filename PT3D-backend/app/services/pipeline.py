"""
Pipeline orchestrator.

Owns the full job lifecycle: SDXL image generation -> Hunyuan3D conversion.
Only one job can run at a time (single GPU constraint).

This module contains no generation logic -- it delegates entirely to
sdxl_runner and hunyuan_client, and updates the job registry at each stage.
"""

import glob
import threading
import uuid
from pathlib import Path

from app.config import settings
from app.core.job_registry import JobStatus, registry
from app.core.quality import QualityPreset
from app.services import job_store, object_storage
from app.services.hunyuan_client import HunyuanConversionError, hunyuan_client
from app.services.sdxl_runner import SDXLFailedError, sdxl_runner


class PipelineService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._busy = False

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._busy

    def start_job(
        self,
        user_id: str,
        prompt: str,
        quality_preset: QualityPreset = QualityPreset.BALANCED,
    ) -> str | None:
        """
        Attempt to start a generation job.

        Returns:
            job_id (str) if the job was queued successfully.
            None if the pipeline is already busy.
        """
        with self._lock:
            if self._busy:
                return None
            self._busy = True

        job_id = uuid.uuid4().hex[:10]
        image_path = settings.images_dir / f"{job_id}.png"
        glb_path = settings.models_dir / f"{job_id}.glb"
        try:
            job_store.create_job(job_id, user_id, prompt, image_path, glb_path, quality_preset)
            registry.create(job_id, user_id, prompt)
        except Exception:
            with self._lock:
                self._busy = False
            raise

        threading.Thread(
            target=self._run_pipeline,
            args=(job_id, user_id, prompt, quality_preset),
            name=f"pt3-job-{job_id}",
        ).start()

        return job_id

    def start_image_job(
        self,
        user_id: str,
        prompt: str,
        uploaded_image_path: Path,
        quality_preset: QualityPreset = QualityPreset.BALANCED,
    ) -> str | None:
        """
        Start image-to-3D generation from an uploaded PNG.

        This skips the SDXL text-to-image stage and runs only Hunyuan3D.
        """
        with self._lock:
            if self._busy:
                return None
            self._busy = True

        job_id = uuid.uuid4().hex[:10]
        image_path = settings.images_dir / f"{job_id}.png"
        glb_path = settings.models_dir / f"{job_id}.glb"
        try:
            settings.images_dir.mkdir(parents=True, exist_ok=True)
            uploaded_image_path.replace(image_path)
            job_store.create_job(job_id, user_id, prompt, image_path, glb_path, quality_preset)
            registry.create(job_id, user_id, prompt)
        except Exception:
            with self._lock:
                self._busy = False
            raise

        threading.Thread(
            target=self._run_image_pipeline,
            args=(job_id, user_id, image_path, quality_preset),
            name=f"pt3-image-job-{job_id}",
        ).start()

        return job_id

    def glb_path(self, filename: str) -> str:
        """Return the full path for a GLB filename inside models_dir."""
        return str(settings.models_dir / filename)

    def latest_glb(self) -> str | None:
        """Return path of the most-recently modified .glb, or None."""
        files = glob.glob(str(settings.models_dir / "*.glb"))
        return max(files, key=lambda f: __import__("os").path.getmtime(f)) if files else None

    def image_path(self, job_id: str) -> str:
        """Return the full path for a PNG file given a job_id."""
        return str(settings.images_dir / f"{job_id}.png")

    def latest_image(self) -> str | None:
        """Return path of the most-recently modified .png, or None."""
        files = glob.glob(str(settings.images_dir / "*.png"))
        return max(files, key=lambda f: __import__("os").path.getmtime(f)) if files else None

    def _run_pipeline(
        self,
        job_id: str,
        user_id: str,
        prompt: str,
        quality_preset: QualityPreset,
    ) -> None:
        """
        Full two-step pipeline running in a background worker thread.

        Steps:
            1. SDXL: text -> PNG  (~60-120s on a 6GB GPU)
            2. Hunyuan3D: PNG -> GLB  (~30-90s via local hy3dgen)

        The `finally` block guarantees _busy is always released, even on
        unexpected exceptions, so the pipeline never gets permanently locked.
        """
        try:
            hunyuan_client.unload()

            registry.update_status(job_id, JobStatus.SDXL_RUNNING)
            job_store.update_status(job_id, JobStatus.SDXL_RUNNING)
            sdxl_runner.run(job_id, prompt, settings.images_dir)
            image_path = settings.images_dir / f"{job_id}.png"
            image_object_key = object_storage.object_key(user_id, job_id, "png")
            object_storage.upload_file(image_path, image_object_key, "image/png")
            job_store.set_object_keys(
                job_id,
                image_object_key if object_storage.enabled() else None,
                None,
            )

            registry.update_status(job_id, JobStatus.CONVERTING)
            job_store.update_status(job_id, JobStatus.CONVERTING)
            glb_path = settings.models_dir / f"{job_id}.glb"
            hunyuan_client.convert(image_path, glb_path, quality_preset)
            glb_object_key = object_storage.object_key(user_id, job_id, "glb")
            object_storage.upload_file(glb_path, glb_object_key, "model/gltf-binary")
            job_store.set_object_keys(
                job_id,
                image_object_key if object_storage.enabled() else None,
                glb_object_key if object_storage.enabled() else None,
            )

            registry.update_status(job_id, JobStatus.DONE)
            job_store.update_status(job_id, JobStatus.DONE)

        except (SDXLFailedError, HunyuanConversionError) as exc:
            registry.set_error(job_id, str(exc))
            job_store.set_error(job_id, str(exc))
            registry.update_status(job_id, JobStatus.FAILED)
            job_store.update_status(job_id, JobStatus.FAILED)

        except Exception as exc:
            registry.set_error(job_id, f"Unexpected error: {exc}")
            job_store.set_error(job_id, f"Unexpected error: {exc}")
            registry.update_status(job_id, JobStatus.FAILED)
            job_store.update_status(job_id, JobStatus.FAILED)

        finally:
            hunyuan_client.unload()
            with self._lock:
                self._busy = False

    def _run_image_pipeline(
        self,
        job_id: str,
        user_id: str,
        image_path,
        quality_preset: QualityPreset,
    ) -> None:
        """Run uploaded image -> Hunyuan3D -> GLB."""
        try:
            image_object_key = object_storage.object_key(user_id, job_id, "png")
            object_storage.upload_file(image_path, image_object_key, "image/png")
            job_store.set_object_keys(
                job_id,
                image_object_key if object_storage.enabled() else None,
                None,
            )

            registry.update_status(job_id, JobStatus.CONVERTING)
            job_store.update_status(job_id, JobStatus.CONVERTING)
            glb_path = settings.models_dir / f"{job_id}.glb"
            hunyuan_client.convert(image_path, glb_path, quality_preset)
            glb_object_key = object_storage.object_key(user_id, job_id, "glb")
            object_storage.upload_file(glb_path, glb_object_key, "model/gltf-binary")
            job_store.set_object_keys(
                job_id,
                image_object_key if object_storage.enabled() else None,
                glb_object_key if object_storage.enabled() else None,
            )

            registry.update_status(job_id, JobStatus.DONE)
            job_store.update_status(job_id, JobStatus.DONE)

        except HunyuanConversionError as exc:
            registry.set_error(job_id, str(exc))
            job_store.set_error(job_id, str(exc))
            registry.update_status(job_id, JobStatus.FAILED)
            job_store.update_status(job_id, JobStatus.FAILED)

        except Exception as exc:
            registry.set_error(job_id, f"Unexpected error: {exc}")
            job_store.set_error(job_id, f"Unexpected error: {exc}")
            registry.update_status(job_id, JobStatus.FAILED)
            job_store.update_status(job_id, JobStatus.FAILED)

        finally:
            hunyuan_client.unload()
            with self._lock:
                self._busy = False


pipeline = PipelineService()
