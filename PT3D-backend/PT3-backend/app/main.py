from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.config import settings
from app.routes import admin, auth, generate, images, jobs, models, status
from app.services.pipeline import pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    # Create output directories so generation never fails on a fresh clone
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    # NOTE: Model pipelines are established lazily on first use.
    # Loading at startup makes local boot slow and can fail on machines without GPU access.

    yield
    # Shutdown


app = FastAPI(
    title="Prompt-to-3D API",
    description="Generate 3D GLB models from text prompts via SDXL → Hunyuan3D pipeline.",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "PATCH", "HEAD"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request, call_next) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(generate.router)
app.include_router(jobs.router)
app.include_router(status.router)
app.include_router(models.router)
app.include_router(images.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "busy": pipeline.is_busy}
