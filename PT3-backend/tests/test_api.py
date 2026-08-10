import base64
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.core import database
from app.core.quality import QualityPreset
from app.main import app
from app.services import job_store
from app.services.pipeline import pipeline


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        settings.database_path = self.root / "data" / "app.db"
        settings.images_dir = self.root / "output" / "images"
        settings.models_dir = self.root / "output" / "models"
        settings.admin_user_ids = ["admin"]
        settings.min_password_chars = 12
        settings.auth_rate_limit_attempts = 8
        settings.auth_rate_limit_window_seconds = 900
        settings.hunyuan_model_path = "tencent/Hunyuan3D-2.1"
        settings.hunyuan_subfolder = "hunyuan3d-dit-v2-1"
        settings.images_dir.mkdir(parents=True, exist_ok=True)
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        with pipeline._lock:
            pipeline._busy = False

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(app)

    def _register(self, client: TestClient, user_id: str = "athar") -> str:
        response = client.post(
            "/auth/register",
            json={
                "user_id": user_id,
                "password": "Strongpass123!",
                "display_name": f"{user_id} profile",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["access_token"]

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_health_reports_pipeline_busy_state(self) -> None:
        with self._client() as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "busy": False})

    def test_register_login_me_and_logout(self) -> None:
        with self._client() as client:
            token = self._register(client)
            duplicate = client.post(
                "/auth/register",
                json={"user_id": "athar", "password": "Strongpass123!"},
            )
            login = client.post(
                "/auth/login",
                json={"user_id": "athar", "password": "Strongpass123!"},
            )
            me = client.get("/auth/me", headers=self._auth(login.json()["access_token"]))
            logout = client.post("/auth/logout", headers=self._auth(login.json()["access_token"]))
            revoked = client.get("/auth/me", headers=self._auth(login.json()["access_token"]))

        self.assertTrue(token)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user_id"], "athar")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(revoked.status_code, 401)


    def test_change_password_rotates_credentials_and_revokes_other_sessions(self) -> None:
        with self._client() as client:
            token = self._register(client, "secureuser")
            second_login = client.post(
                "/auth/login",
                json={"user_id": "secureuser", "password": "Strongpass123!"},
            )
            self.assertEqual(second_login.status_code, 200)
            second_token = second_login.json()["access_token"]

            weak = client.post(
                "/auth/change-password",
                json={"current_password": "Strongpass123!", "new_password": "password123"},
                headers=self._auth(token),
            )
            changed = client.post(
                "/auth/change-password",
                json={"current_password": "Strongpass123!", "new_password": "BetterPass123!"},
                headers=self._auth(token),
            )
            old_login = client.post(
                "/auth/login",
                json={"user_id": "secureuser", "password": "Strongpass123!"},
            )
            new_login = client.post(
                "/auth/login",
                json={"user_id": "secureuser", "password": "BetterPass123!"},
            )
            revoked = client.get("/auth/me", headers=self._auth(second_token))

        self.assertEqual(weak.status_code, 422)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)
        self.assertEqual(revoked.status_code, 401)
    def test_auth_rejects_weak_or_invalid_credentials(self) -> None:
        with self._client() as client:
            weak = client.post(
                "/auth/register",
                json={"user_id": "ab", "password": "short"},
            )
            bad_login = client.post(
                "/auth/login",
                json={"user_id": "missing", "password": "Strongpass123!"},
            )

        self.assertEqual(weak.status_code, 422)
        self.assertEqual(bad_login.status_code, 401)

    def test_protected_routes_reject_missing_or_invalid_tokens(self) -> None:
        with self._client() as client:
            no_token = client.get("/jobs")
            bad_token = client.get("/jobs", headers=self._auth("not-real"))

        self.assertEqual(no_token.status_code, 401)
        self.assertEqual(bad_token.status_code, 401)

    def test_generate_requires_auth_and_creates_owned_job(self) -> None:
        with self._client() as client:
            token = self._register(client)
            missing = client.post("/generate", json={"prompt": "low poly car"})
            with (
                patch("app.services.pipeline.sdxl_runner.run", return_value=None),
                patch("app.services.pipeline.hunyuan_client.convert", return_value=None),
            ):
                response = client.post(
                    "/generate",
                    json={"prompt": "  low poly car  ", "quality_preset": "quality"},
                    headers=self._auth(token),
                )

            self.assertEqual(missing.status_code, 401)
            self.assertEqual(response.status_code, 202, response.text)
            job_id = response.json()["job_id"]
            self.assertEqual(response.json()["quality_preset"], "quality")
            job = job_store.get_user_job(job_id, "athar")
            self.assertIsNotNone(job)
            self.assertEqual(job.prompt, "low poly car")
            self.assertEqual(job.quality_preset, QualityPreset.QUALITY)

            # Let the patched background thread release the busy lock.
            for _ in range(20):
                if client.get("/health").json()["busy"] is False:
                    break
                time.sleep(0.05)

    def test_generate_from_image_requires_auth_and_skips_sdxl(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(image_buffer, format="PNG")
        tiny_png = image_buffer.getvalue()
        with self._client() as client:
            token = self._register(client)
            missing = client.post(
                "/generate/image",
                json={
                    "prompt": "uploaded chair",
                    "quality_preset": "balanced",
                    "content_type": "image/png",
                    "image_base64": base64.b64encode(tiny_png).decode("ascii"),
                },
            )
            with (
                patch("app.services.pipeline.sdxl_runner.run", return_value=None) as sdxl_run,
                patch("app.services.pipeline.hunyuan_client.convert", return_value=None),
            ):
                response = client.post(
                    "/generate/image",
                    json={
                        "prompt": "uploaded chair",
                        "quality_preset": "balanced",
                        "content_type": "image/png",
                        "image_base64": base64.b64encode(tiny_png).decode("ascii"),
                    },
                    headers=self._auth(token),
                )

            self.assertEqual(missing.status_code, 401)
            self.assertEqual(response.status_code, 202, response.text)
            sdxl_run.assert_not_called()
            job_id = response.json()["job_id"]
            job = job_store.get_user_job(job_id, "athar")
            self.assertIsNotNone(job)
            self.assertEqual(job.prompt, "uploaded chair")
            self.assertTrue(Path(job.image_path).exists())

            for _ in range(20):
                if client.get("/health").json()["busy"] is False:
                    break
                time.sleep(0.05)


    def test_generate_rejects_empty_and_long_prompt(self) -> None:
        with self._client() as client:
            token = self._register(client)
            empty = client.post("/generate", json={"prompt": "   "}, headers=self._auth(token))
            long = client.post("/generate", json={"prompt": "x" * 501}, headers=self._auth(token))

        self.assertEqual(empty.status_code, 422)
        self.assertEqual(long.status_code, 422)

    def test_jobs_and_assets_are_owned_by_user(self) -> None:
        with self._client() as client:
            token_a = self._register(client, "owner")
            token_b = self._register(client, "viewer")

            image_path = settings.images_dir / "1111111111.png"
            glb_path = settings.models_dir / "1111111111.glb"
            image_path.write_bytes(b"fake-png")
            glb_path.write_bytes(b"fake-glb")
            job_store.create_job(
                "1111111111",
                "owner",
                "owner prompt",
                image_path,
                glb_path,
            )
            job_store.update_status("1111111111", job_store.JobStatus.DONE)

            own_jobs = client.get("/jobs", headers=self._auth(token_a))
            other_jobs = client.get("/jobs", headers=self._auth(token_b))
            own_status = client.get("/status/1111111111", headers=self._auth(token_a))
            other_status = client.get("/status/1111111111", headers=self._auth(token_b))
            own_image = client.get("/image/1111111111", headers=self._auth(token_a))
            other_image = client.get("/image/1111111111", headers=self._auth(token_b))
            own_glb = client.get("/glb/1111111111.glb", headers=self._auth(token_a))
            other_glb = client.get("/glb/1111111111.glb", headers=self._auth(token_b))

        self.assertEqual(own_jobs.status_code, 200)
        self.assertEqual(len(own_jobs.json()), 1)
        self.assertEqual(other_jobs.status_code, 200)
        self.assertEqual(other_jobs.json(), [])
        self.assertEqual(own_status.status_code, 200)
        self.assertEqual(own_status.json()["quality_preset"], "balanced")
        self.assertEqual(other_status.status_code, 404)
        self.assertEqual(own_image.status_code, 200)
        self.assertEqual(other_image.status_code, 404)
        self.assertEqual(own_glb.status_code, 200)
        self.assertEqual(other_glb.status_code, 404)

    def test_admin_export_csv_is_admin_only_and_omits_secrets(self) -> None:
        settings.admin_user_ids = ["admin"]
        with self._client() as client:
            admin_token = self._register(client, "admin")
            user_token = self._register(client, "regular")
            job_store.create_job(
                "2222222222",
                "regular",
                "regular prompt",
                settings.images_dir / "2222222222.png",
                settings.models_dir / "2222222222.glb",
            )

            denied = client.get("/admin/export.csv", headers=self._auth(user_token))
            exported = client.get("/admin/export.csv", headers=self._auth(admin_token))

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("regular prompt", exported.text)
        self.assertNotIn("password_hash", exported.text)
        self.assertNotIn("password_salt", exported.text)



    def test_admin_training_examples_workflow(self) -> None:
        settings.admin_user_ids = ["admin"]
        with self._client() as client:
            admin_token = self._register(client, "admin")
            user_token = self._register(client, "regular")
            job_store.create_job(
                "3333333333",
                "regular",
                "ceramic mug product prop",
                settings.images_dir / "3333333333.png",
                settings.models_dir / "3333333333.glb",
                QualityPreset.QUALITY,
            )

            denied = client.post(
                "/admin/training/examples",
                json={"job_id": "3333333333", "failure_label": "bad_shape"},
                headers=self._auth(user_token),
            )
            created = client.post(
                "/admin/training/examples",
                json={
                    "job_id": "3333333333",
                    "failure_label": "bad_shape",
                    "admin_notes": "Handle collapsed.",
                    "include_in_hunyuan": True,
                },
                headers=self._auth(admin_token),
            )
            examples = client.get("/admin/training/examples", headers=self._auth(admin_token))
            exported = client.get("/admin/training/examples.csv", headers=self._auth(admin_token))
            config = client.get("/admin/training/config", headers=self._auth(admin_token))

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["prompt"], "ceramic mug product prop")
        self.assertEqual(created.json()["failure_label"], "bad_shape")
        self.assertTrue(created.json()["include_in_hunyuan"])
        self.assertEqual(examples.status_code, 200)
        self.assertEqual(len(examples.json()), 1)
        self.assertEqual(exported.status_code, 200)
        self.assertIn("ceramic mug product prop", exported.text)
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json()["hunyuan_model_path"], "tencent/Hunyuan3D-2.1")

if __name__ == "__main__":
    unittest.main()
