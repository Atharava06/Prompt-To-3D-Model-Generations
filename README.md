# Prompt → 3D

Generate interactive 3D models from a text prompt. Type a description, hit **Generate**, and inspect the result in a real-time Three.js viewer.

---

## Overview

| Layer | Stack |
|---|---|
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS · Three.js |
| Backend | FastAPI · Pydantic v2 · Uvicorn |
| Pipeline | SDXL (text -> PNG) -> Hunyuan3D-2.1 shape generation (PNG -> GLB) |
| Output | GLB (binary glTF) served over HTTP; optional Cloudflare R2 object storage |

---

## Project Structure

```
prompt-to-3d/
├── PT3-frontend/
│   ├── src/
│   │   ├── components/Viewer/ThreeViewer.tsx   # Three.js canvas
│   │   ├── constant/index.ts                   # API URL constants
│   │   ├── types/index.ts                      # Shared TypeScript types
│   │   └── App.tsx                             # Main UI + polling logic
│   └── .env.example
│
└── PT3-backend/
    ├── app/
    │   ├── config.py                   # Settings — all paths auto-derived from project root
    │   ├── main.py                     # App factory, CORS, startup hooks
    │   ├── core/job_registry.py        # Thread-safe in-memory job state
    │   ├── routes/
    │   │   ├── generate.py             # POST /generate
    │   │   ├── status.py               # GET /status/{job_id}
    │   │   ├── models.py               # GET /glb/{id}.glb, HEAD+GET /latest.glb
    │   │   └── images.py               # GET /image/{job_id}
    │   ├── schemas/
    │   │   ├── generate.py             # GenerateRequest / GenerateResponse
    │   │   └── job.py                  # JobStatusResponse
    │   └── services/
    │       ├── pipeline.py             # Orchestrator — runs both steps in background thread
    │       ├── sdxl_runner.py          # Blocking SDXL subprocess wrapper
    │       └── hunyuan_client.py       # Local Hunyuan3D-2 hy3dgen client
    ├── pipeline/
    │   ├── sdxl_generate.py            # SDXL script (runs inside prompto3d conda env)
    │   └── requirements.txt            # Deps for the SDXL conda env
    ├── output/                         # Auto-created at startup — never commit this
    │   ├── images/                     # SDXL PNG outputs
    │   └── models/                     # Hunyuan GLB outputs
    ├── run.py
    ├── requirements.txt                # FastAPI server deps only
    ├── .env                            # Your local config (gitignored)
    └── .env.example
```

---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+ (for the FastAPI server)
- Anaconda / Miniconda with a `prompto3d` env that has `torch` + `diffusers`
- Network access for first-time model downloads, or local model directories

---

### 1 — SDXL conda environment

```bash
conda activate prompto3d

# PyTorch — match your CUDA version (check with: nvidia-smi)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130

# SDXL deps
pip install -r PT3-backend/pipeline/requirements.txt
```

---

### 2 — Backend

```bash
cd PT3-backend

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Install FastAPI server deps
pip install -r requirements.txt

# Configure — only one value needs to change
cp .env.example .env
```

Open `.env` and set `SDXL_PYTHON` to the `python.exe` inside your conda env if
your FastAPI virtualenv does not have torch/diffusers installed:

```ini
SDXL_PYTHON=C:\Users\YourName\anaconda3\envs\prompto3d\python.exe
```

Everything else (output directories, script path) is **automatically derived from the project folder** — no other paths to configure.

```bash
# Start the server
python run.py
# → http://127.0.0.1:8000
```

---

### 3 — Frontend

```bash
cd PT3-frontend
npm install
npm run dev
# -> http://localhost:5173
```

---

## Deploy Frontend To Vercel

The GPU backend should stay on a GPU host such as RunPod, Vast.ai, Lambda Labs,
or your own GPU server. Vercel should host the Vite frontend only.

In Vercel:

1. Import the Git repository.
2. Set **Root Directory** to `PT3-frontend`.
3. Use the detected **Vite** framework settings.
4. Add environment variable:
   ```ini
   VITE_API_URL=https://your-public-backend-url
   ```
5. Deploy.

Then update `PT3-backend/.env` on the backend host:

```ini
ALLOWED_ORIGINS=["https://your-project.vercel.app","http://localhost:5173","http://127.0.0.1:5173"]
```

Restart the backend after changing CORS settings.

---

## Environment Variables

### `PT3-backend/.env`

| Variable | Required | Description | Default |
|---|---|---|---|
| `SDXL_MODEL_PATH` | No | HF repo ID or local diffusers SDXL directory | `stabilityai/stable-diffusion-xl-base-1.0` |
| `SDXL_LORA_PATH` | No | Optional products/props LoRA directory or weights path | unset |
| `SDXL_LORA_SCALE` | No | Optional LoRA strength for SDXL inference | `1.0` |
| `HUNYUAN_MODEL_PATH` | No | HF repo ID or local Hunyuan3D directory | `tencent/Hunyuan3D-2.1` |
| `HUNYUAN_FINETUNED_MODEL_PATH` | No | Optional fine-tuned Hunyuan checkpoint path; base model remains fallback | unset |
| `HUNYUAN_SUBFOLDER` | No | Hunyuan shape-model subfolder. Use `hunyuan3d-dit-v2-0` for old 2.0 fallback. | `hunyuan3d-dit-v2-1` |
| `HUNYUAN_REPO_PATH` | No | Local Hunyuan3D-2.1 repo path; adds `hy3dshape` to Python imports. | unset |
| `SDXL_PYTHON` | No | Python executable used for the SDXL subprocess | current Python |
| `SDXL_TIMEOUT_SECONDS` | No | Max seconds allowed for SDXL image generation | `900` |
| `DATABASE_URL` | No | Supabase/Postgres URL for users, sessions, and job history. Overrides SQLite when set. | unset |
| `DATABASE_PATH` | No | SQLite DB for users, sessions, and jobs | `PT3-backend/data/app.db` |
| `SESSION_TTL_HOURS` | No | Login session lifetime | `72` |
| `MIN_PASSWORD_CHARS` | No | Minimum password length | `12` |
| `AUTH_RATE_LIMIT_ATTEMPTS` | No | Auth attempts per window before 429 | `5` |
| `R2_ACCOUNT_ID` | No | Cloudflare account ID for R2 object storage | unset |
| `R2_ACCESS_KEY_ID` | No | Cloudflare R2 access key ID | unset |
| `R2_SECRET_ACCESS_KEY` | No | Cloudflare R2 secret access key | unset |
| `R2_BUCKET_NAME` | No | Private R2 bucket for generated PNG and GLB files | unset |
| `HOST` | No | Bind address | `127.0.0.1` |
| `PORT` | No | Bind port | `8000` |
| `ALLOWED_ORIGINS` | No | CORS origins (JSON array) | `["http://localhost:5173","http://127.0.0.1:5173"]` |

> **All output paths are relative to the project.**
> `output/images/` and `output/models/` are created automatically on startup.
> `GLB_DIR` and `SDXL_SCRIPT` are no longer configurable — they point to
> `PT3-backend/output/models/` and `PT3-backend/pipeline/sdxl_generate.py` automatically.

### `PT3-frontend/.env`

| Variable | Required | Description | Default |
|---|---|---|---|
| `VITE_API_URL` | No | Backend base URL | `http://127.0.0.1:8000` |

### Supabase Data Storage

Use Supabase Postgres when the GPU host should not be the source of truth for
profiles and job history.

1. Create a Supabase project.
2. Copy the Postgres connection string from Project Settings -> Database.
   The transaction pooler URL is usually best for hosted app backends.
3. Set it on the backend host:
   ```ini
   DATABASE_URL=postgresql://postgres.xxxxx:password@aws-0-region.pooler.supabase.com:6543/postgres
   ```
4. Restart the backend.

To migrate existing CheapCUDA SQLite data into Supabase:

### Background SDXL LoRA Training

The current app already supports loading a trained SDXL LoRA for inference via
`SDXL_LORA_PATH`, but LoRA training itself runs outside the FastAPI server.

On a Linux GPU host, the helper scripts in `PT3-backend/scripts/` can manage a
background SDXL LoRA run using Hugging Face Diffusers' official
`train_text_to_image_lora_sdxl.py` script:

```bash
export DIFFUSERS_DIR=/root/diffusers
export TRAIN_DATA_DIR=/root/datasets/products-props
export OUTPUT_ROOT=/root/training/sdxl-lora
bash PT3-backend/scripts/start_sdxl_lora_bg.sh
```

Check status and logs:

```bash
bash PT3-backend/scripts/lora_bg_status.sh
```

Stop the latest run:

```bash
bash PT3-backend/scripts/stop_sdxl_lora_bg.sh
```

Notes:
- You must clone `diffusers` and install its example dependencies on the GPU host first.
- You must provide either `DATASET_NAME` or `TRAIN_DATA_DIR`.
- The app currently stores training-review metadata, but it does not auto-build a LoRA dataset yet.

```bash
cd PT3-backend
DATABASE_URL='postgresql://...' ./venv/bin/python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path /root/Prompt-to-3d/data/app.db
```

Supabase stores users, sessions, and job rows. Use Cloudflare R2 for the bulky
generated image/GLB files so they survive GPU deletion and do not fill the GPU disk.

### Cloudflare R2 File Storage

Create a private R2 bucket, then create an R2 API token with object read/write
access for that bucket. Set these on the backend host:

```ini
R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ACCESS_KEY_ID=your-r2-access-key-id
R2_SECRET_ACCESS_KEY=your-r2-secret-access-key
R2_BUCKET_NAME=prompt-to-3d
```

Restart the backend after changing `.env`. New generations will upload their PNG
and GLB files to R2, while `/image/{job_id}` and `/glb/{job_id}.glb` still enforce
login and job ownership before streaming files back to the browser.

To upload older GPU files into R2 after setting the variables:

```bash
cd PT3-backend
python scripts/backfill_r2_objects.py --dry-run
python scripts/backfill_r2_objects.py
```

---

## How It Works

```
User types prompt
      │
      ▼
POST /generate  →  202 Accepted + job_id
      │
      ▼  [background worker thread]
      │
      ├─ SDXL runs locally on GPU  (~2-3 min)
      │  → output/images/{job_id}.png
      │
      ├─ Hunyuan3D-2 runs locally, then unloads from VRAM  (~1-2 min)
      │  → output/models/{job_id}.glb
      │
      └─ status → DONE

Frontend polls GET /status/{job_id} every 3s:
  queued → sdxl_running → converting → done
      │
      ▼  (done)
GET /glb/{job_id}.glb  →  Three.js renders the model
```

Only one job runs at a time (single GPU). Concurrent requests receive `409 Conflict`.

---

## API Reference

### `POST /generate`
```json
// Request
{
  "prompt": "low poly dinosaur, gray matte surface, game asset",
  "quality_preset": "balanced"
}

// 202 Accepted
{ "status": "started", "job_id": "a1b2c3d4e5", "quality_preset": "balanced" }

// 409 Conflict — pipeline busy
{ "detail": "Pipeline is busy. Wait for the current job to finish." }
```

Requires `Authorization: Bearer <token>`.

`quality_preset` is optional and defaults to `balanced`:
- `fast`: lower Hunyuan steps/resolution for quicker previews
- `balanced`: default production setting
- `quality`: higher Hunyuan steps/chunks where VRAM allows

### `POST /auth/register`
```json
{ "user_id": "athar", "password": "password123", "display_name": "Athar" }
```

### `POST /auth/login`
```json
{ "user_id": "athar", "password": "password123" }
```

Both auth endpoints return:
```json
{
  "access_token": "session-token",
  "token_type": "bearer",
  "user": { "user_id": "athar", "display_name": "Athar", "created_at": "..." }
}
```

### `GET /jobs`
Returns only the authenticated user's generation history.

### `GET /status/{job_id}`
```json
{
  "job_id": "a1b2c3d4e5",
  "status": "converting",       // queued | sdxl_running | converting | done | failed
  "prompt": "low poly dinosaur",
  "created_at": "2025-01-15T10:30:00Z",
  "error": null
}
```

### Quality Benchmark

Run the 30-prompt general-object benchmark through the live authenticated API:

```bash
cd PT3-backend
PT3_BENCHMARK_PASSWORD='admin-password' python scripts/run_quality_benchmark.py \
  --api-base http://127.0.0.1:8000 \
  --user-id admin \
  --quality-preset balanced
```

The script creates normal generation jobs, so Supabase history and Cloudflare R2
storage are exercised when configured. It writes a review JSON file under
`PT3-backend/benchmark_runs/`.

### `GET /glb/{job_id}.glb`
Returns the `.glb` file (`model/gltf-binary`) when ready, `404` while still running.

### `HEAD /latest.glb` / `GET /latest.glb`
HEAD returns `200`/`404` for pre-check. GET streams the most recent GLB.

### `GET /health`
```json
{ "status": "ok", "busy": false }
```

---

## Development

```bash
# Backend — auto-reload
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend — HMR via Vite
npm run dev

# Frontend — production build
npm run build
```

---

## Notes

- `.env` and `output/` are gitignored. Never commit them.
- The viewer normalises all GLB materials to a flat gray `MeshStandardMaterial` for a consistent look.
- Hunyuan3D-2 runs locally through `hy3dgen`. It is unloaded after each job so the next SDXL subprocess has clean VRAM.
