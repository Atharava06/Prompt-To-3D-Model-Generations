import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# PT3-backend/
BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # ── Optional overrides ─────────────────────────────────────────────────────
    # On cloud: leave unset — defaults to the current Python (sys.executable).
    # On local: set to the conda env python that has torch/diffusers installed.
    sdxl_python: str = sys.executable

    # SDXL model — HF repo ID (default, downloads on first use) or absolute
    # path to a local diffusers directory (set via SDXL_MODEL_PATH in .env).
    sdxl_model_path: str = "stabilityai/stable-diffusion-xl-base-1.0"
    sdxl_lora_path: str | None = None
    sdxl_lora_scale: float = 1.0

    # Hunyuan3D shape model. Set HUNYUAN_MODEL_PATH and HUNYUAN_SUBFOLDER
    # together to switch between 2.1 and the old 2.0 fallback.
    hunyuan_model_path: str = "tencent/Hunyuan3D-2.1"
    hunyuan_finetuned_model_path: str | None = None
    hunyuan_subfolder: str = "hunyuan3d-dit-v2-1"
    hunyuan_repo_path: str | None = None

    host: str = "127.0.0.1"  # Set to 0.0.0.0 on cloud to accept external traffic
    port: int = 8000
    reload: bool = False  # Enable only for local development
    sdxl_timeout_seconds: int = 900
    session_ttl_hours: int = 72
    min_password_chars: int = 12
    auth_rate_limit_attempts: int = 5
    auth_rate_limit_window_seconds: int = 900
    admin_user_ids: list[str] = ["admin"]
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: str | None = None
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None

    # ── Structural constants — derived from BASE_DIR, not configurable ─────────
    database_path: Path = BASE_DIR / "data" / "app.db"
    images_dir: Path = BASE_DIR / "output" / "images"
    models_dir: Path = BASE_DIR / "output" / "models"
    sdxl_script: Path = BASE_DIR / "pipeline" / "sdxl_generate.py"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
