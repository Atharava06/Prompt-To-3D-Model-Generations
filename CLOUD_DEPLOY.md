# Prompt-to-3D â€” Cloud GPU Deployment Guide

---

## Code Readiness Status

| Component | Status | Notes |
|---|---|---|
| SDXL image generation | Ready | Loads from local path or HF repo ID via `SDXL_MODEL_PATH` |
| Hunyuan3D conversion | Ready | Defaults to Hunyuan3D-2.1; old 2.0 works by changing `HUNYUAN_MODEL_PATH` and `HUNYUAN_SUBFOLDER` |
| FastAPI server | Ready | Host/port/reload all configurable via `.env` |
| Docker | Ready | Single-command build and run |
| Job state | SQLite or Supabase | Use `DATABASE_URL` for Supabase Postgres; fallback is `DATABASE_PATH` SQLite |
| Generated files | Local disk or Cloudflare R2 | Set `R2_*` variables to persist PNG/GLB files outside the GPU |
| Concurrency | 1 job at a time | Thread lock enforces this â€” matches single GPU |

---

## What Model Files You Have Locally

### SDXL â€” Complete, usable right now

Full diffusers model cached at:
```
C:\Users\project\.cache\huggingface\hub\models--stabilityai--stable-diffusion-xl-base-1.0\
  snapshots\462165984030d82259a11f4367a4eed129e94a7b\
```
Contains: UNet, VAE, text encoders, tokenizers, scheduler â€” everything needed.
Set `SDXL_MODEL_PATH` to this path to skip any download.

### Hunyuan3D-2 â€” Incomplete, needs one more step

What you have in ComfyUI:
```
C:\Users\athar\Documents\ComfyUI\models\hy3dgen\
  hunyuan3d-dit-v2-0-fp16.safetensors        â† DiT shape model weights only
```

What `from_pretrained()` also needs (not present locally):
```
tencent/Hunyuan3D-2/
  model_index.json                            â† pipeline config
  hunyuan3d-dit-v2-0/config.json             â† architecture config
  hunyuan3d-sdf-v2-0/                        â† SDF mesh decoder (separate model)
```

The single `.safetensors` file is just the DiT transformer weights.
The SDF decoder (which converts latents â†’ 3D mesh) is a different model entirely and is missing.
**You need to download the remaining parts once** â€” see Part 1 below.

---

## Part 1 â€” Complete the Hunyuan3D-2 Model Download

Run this once on your local machine (or on the cloud GPU):

```python
# Run this in a Python terminal with huggingface_hub installed:
# pip install huggingface_hub
from huggingface_hub import snapshot_download

snapshot_download(
    "tencent/Hunyuan3D-2",
    local_dir="C:/models/Hunyuan3D-2",  # choose any folder you want
    ignore_patterns=["*.md", "*.txt"],   # skip docs, only weights + configs
)
```

This downloads the config files + SDF decoder (~3â€“4 GB) into `C:/models/Hunyuan3D-2`.

Then set `HUNYUAN_MODEL_PATH=C:/models/Hunyuan3D-2` in your `.env`.

If you want to use your existing fp16 weights instead of the downloaded ones:
```bash
# Replace the downloaded DiT weights with your existing fp16 file:
copy "C:\Users\athar\Documents\ComfyUI\models\hy3dgen\hunyuan3d-dit-v2-0-fp16.safetensors" ^
     "C:\models\Hunyuan3D-2\hunyuan3d-dit-v2-0\"
```

---

## Part 2 â€” Local `.env` (Run on Your PC)

Create `PT3-backend/.env`:

```ini
# SDXL: use the local HF cache â€” no download needed
SDXL_MODEL_PATH=C:/Users/project/.cache/huggingface/hub/models--stabilityai--stable-diffusion-xl-base-1.0/snapshots/462165984030d82259a11f4367a4eed129e94a7b

# Hunyuan3D-2: full model directory (after completing Part 1)
HUNYUAN_MODEL_PATH=C:/models/Hunyuan3D-2

# Keep localhost binding for local dev
HOST=127.0.0.1
PORT=8000
RELOAD=true

ALLOWED_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

---

## Part 3 â€” How the Pipeline Works

```
User prompt
    â”‚
    â–¼
POST /generate  â†’  background worker thread
                      â”‚
                      â”œâ”€ Step 1: sdxl_generate.py (subprocess)
                      â”‚    Loads SDXL from SDXL_MODEL_PATH
                      â”‚    text â†’ 768Ã—768 PNG  (~20â€“40s on cloud GPU)
                      â”‚    Process exits â†’ VRAM fully freed
                      â”‚
                      â””â”€ Step 2: hy3dgen in-process
                             Loads Hunyuan3D-2 from HUNYUAN_MODEL_PATH
                             PNG â†’ GLB  (~30â€“90s)
                             Unloads from VRAM after the job
```

**Why SDXL is a subprocess:** Its process exit frees VRAM completely before Hunyuan3D-2 loads. Running both at the same time would exceed 24 GB.

**Why Hunyuan3D-2 unloads after conversion:** SDXL and Hunyuan are large enough that keeping both around can cause the next job to OOM on modest GPUs. Reloading Hunyuan each job is slower, but it keeps peak VRAM predictable.

---

## Part 4 â€” GPU Requirements

| VRAM | Verdict |
|---|---|
| 8 GB | Too small â€” SDXL alone needs ~7 GB |
| 16 GB (T4, RTX 3080 Ti) | Works â€” comfortable margin |
| 24 GB (A10G, RTX 3090/4090) | Ideal |
| 40â€“80 GB (A100) | Overkill but fast |

Peak VRAM is `max(SDXL, Hunyuan)` not their sum, because they run sequentially.

---

## Part 5 â€” Cloud Provider

### Recommended: RunPod

- Persistent pods â€” files survive between sessions
- Pre-built PyTorch images â€” CUDA already set up
- Port forwarding â€” your frontend can reach the backend
- ~$0.39â€“0.76/hr for 24 GB GPU

| Provider | $/hr | Notes |
|---|---|---|
| RunPod | $0.39â€“0.76 | Best balance of ease + cost |
| Vast.ai | $0.20â€“0.40 | Cheapest, less reliable |
| Lambda Labs | $0.50â€“1.10 | Clean UI, reserved options |
| Modal | pay/sec | Avoid â€” cold start per request kills UX |

---

## Part 6 â€” RunPod Setup

1. Go to **runpod.io â†’ Deploy â†’ GPU Cloud â†’ + Deploy**
2. GPU: **RTX A5000 (24 GB)** or **A10G**
3. Template: **RunPod PyTorch 2.2** (has Python + CUDA already)
4. Container disk: **50 GB** (models + OS)
5. Volume disk: **30 GB** at `/workspace` (survives restarts, store models here)
6. Expose TCP port: **8000**
7. Click Deploy â†’ wait â†’ connect via SSH

---

## Part 7 â€” Cloud Server Setup (SSH Commands)

### 7.1 Install hy3dgen

```bash
git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 /workspace/Hunyuan3D-2.1
pip install -r /workspace/Hunyuan3D-2.1/requirements.txt
```

### 7.2 Install Python dependencies

```bash
pip install -r /workspace/Prompt-to-3d/PT3-backend/requirements.txt
pip install diffusers>=0.27.0 transformers>=4.40.0 accelerate>=0.30.0 safetensors>=0.4.0
```

### 7.3 Get the models onto the cloud server

**Option A â€” Download from HF directly on the server (simplest):**
```bash
python - <<'EOF'
from huggingface_hub import snapshot_download
# SDXL
snapshot_download("stabilityai/stable-diffusion-xl-base-1.0",
                  local_dir="/workspace/models/sdxl")
# Hunyuan3D-2.1
snapshot_download("tencent/Hunyuan3D-2.1",
                  local_dir="/workspace/models/hunyuan3d-2.1")
EOF
```

**Option B â€” Upload your local models via SCP (faster, uses files you already have):**
```bash
# Run on your LOCAL Windows machine in PowerShell:
# Upload SDXL (the full HF cache snapshot folder):
scp -r -P <port> \
  "C:\Users\project\.cache\huggingface\hub\models--stabilityai--stable-diffusion-xl-base-1.0\snapshots\462165984030d82259a11f4367a4eed129e94a7b" \
  root@<pod-ip>:/workspace/models/sdxl

# Upload Hunyuan3D-2 (after you complete Part 1 locally):
scp -r -P <port> "C:\models\Hunyuan3D-2" root@<pod-ip>:/workspace/models/hunyuan3d-2
```

### 7.4 Clone your project

```bash
git clone <your-repo-url> /workspace/Prompt-to-3d
# or upload via SCP if you don't have a remote yet
```

### 7.5 Configure `.env`

```bash
cat > /workspace/Prompt-to-3d/PT3-backend/.env <<'EOF'
SDXL_MODEL_PATH=/workspace/models/sdxl
HUNYUAN_MODEL_PATH=/workspace/models/hunyuan3d-2.1
HUNYUAN_SUBFOLDER=hunyuan3d-dit-v2-1
HUNYUAN_REPO_PATH=/workspace/Hunyuan3D-2.1
HOST=0.0.0.0
PORT=8000
RELOAD=false
# DATABASE_URL=postgresql://postgres.xxxxx:password@aws-0-region.pooler.supabase.com:6543/postgres
# R2_ACCOUNT_ID=your-cloudflare-account-id
# R2_ACCESS_KEY_ID=your-r2-access-key-id
# R2_SECRET_ACCESS_KEY=your-r2-secret-access-key
# R2_BUCKET_NAME=prompt-to-3d
ALLOWED_ORIGINS=["https://your-frontend.example.com","http://localhost:5173"]
EOF
```

### 7.6 Start the server

```bash
tmux new -s server
cd /workspace/Prompt-to-3d/PT3-backend
python run.py
# Ctrl+B then D  to detach (server keeps running)
```

### 7.7 Verify

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", "busy": false}
```

---

## Part 8 - Deploy And Connect The Frontend On Vercel

1. On RunPod pod page â†’ **Connect** â†’ copy HTTP URL for port 8000
   Looks like: `https://abc123-8000.proxy.runpod.net`

2. In Vercel, import this repository and use these project settings:
   - Root Directory: `PT3-frontend`
   - Framework Preset: `Vite`
   - Install Command: `npm ci`
   - Build Command: `npm run build`
   - Output Directory: `dist`

3. Add this Vercel environment variable:
   ```ini
   VITE_API_URL=https://abc123-8000.proxy.runpod.net
   ```

4. Update backend `.env` ALLOWED_ORIGINS:
   ```ini
   ALLOWED_ORIGINS=["https://your-frontend.vercel.app","http://localhost:5173"]
   ```

5. Restart the server: `Ctrl+C` -> `python run.py`

---

## Part 9 â€” Docker (Alternative)

```bash
docker build -t prompt-to-3d .

docker run --gpus all -p 8000:8000 \
  --env-file PT3-backend/.env \
  -v /workspace/models:/workspace/models \
  prompt-to-3d
```

Mount the models volume so container restarts don't re-download weights.

---

## Part 10 â€” Common Issues

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: hy3dshape` | Hunyuan3D-2.1 package path not installed | Install Hunyuan3D-2.1 requirements and run backend from a shell with `/workspace/Hunyuan3D-2.1/hy3dshape` importable |
| `CUDA out of memory` | Both models in VRAM simultaneously | Verify SDXL subprocess exits before Hunyuan loads â€” check logs |
| `Connection refused` | Server bound to 127.0.0.1 | Set `HOST=0.0.0.0` in `.env` |
| CORS error in browser | Frontend URL not in allowed origins | Add frontend URL to `ALLOWED_ORIGINS` in `.env` |
| First request very slow | Model loading or HF download | Wait 2â€“5 min on first request; mount a persistent volume to cache |
| `No such file or directory` (model path) | Path typo in `.env` | Use forward slashes even on Windows: `C:/models/...` |
| Generated files disappear after GPU deletion | Outputs stayed only on GPU disk | Configure Cloudflare R2 and run `python scripts/backfill_r2_objects.py` |

---

## Part 11 â€” Production Checklist

- [ ] Part 1 complete â€” Hunyuan3D-2 full model directory downloaded
- [ ] `SDXL_MODEL_PATH` points to a real directory (run `ls` to confirm)
- [ ] `HUNYUAN_MODEL_PATH` points to a real directory (run `ls` to confirm)
- [ ] `HOST=0.0.0.0` in cloud `.env`
- [ ] `RELOAD=false` in cloud `.env`
- [ ] `ALLOWED_ORIGINS` locked to specific URLs (not `["*"]`)
- [ ] `R2_*` variables set if the GPU may be deleted or replaced
- [ ] Models on a persistent volume (survive pod restart)
- [ ] Server running in `tmux` (survives SSH disconnect)
- [ ] `curl /health` returns 200

---

## Quick Reference â€” Everything in One Block

```bash
# â”€â”€ On the cloud server â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# 1. hy3dgen
git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1 /workspace/Hunyuan3D-2.1
pip install -r /workspace/Hunyuan3D-2.1/requirements.txt

# 2. Python deps
pip install -r /workspace/Prompt-to-3d/PT3-backend/requirements.txt
pip install diffusers transformers accelerate safetensors

# 3. Download models (or upload via SCP â€” see Part 7.3)
python -c "
from huggingface_hub import snapshot_download
snapshot_download('stabilityai/stable-diffusion-xl-base-1.0', local_dir='/workspace/models/sdxl')
snapshot_download('tencent/Hunyuan3D-2.1', local_dir='/workspace/models/hunyuan3d-2.1')
"

# 4. Configure
cat > /workspace/Prompt-to-3d/PT3-backend/.env <<'EOF'
SDXL_MODEL_PATH=/workspace/models/sdxl
HUNYUAN_MODEL_PATH=/workspace/models/hunyuan3d-2.1
HUNYUAN_SUBFOLDER=hunyuan3d-dit-v2-1
HUNYUAN_REPO_PATH=/workspace/Hunyuan3D-2.1
HOST=0.0.0.0
PORT=8000
RELOAD=false
# DATABASE_URL=postgresql://postgres.xxxxx:password@aws-0-region.pooler.supabase.com:6543/postgres
# R2_ACCOUNT_ID=your-cloudflare-account-id
# R2_ACCESS_KEY_ID=your-r2-access-key-id
# R2_SECRET_ACCESS_KEY=your-r2-secret-access-key
# R2_BUCKET_NAME=prompt-to-3d
ALLOWED_ORIGINS=["https://your-frontend.example.com","http://localhost:5173"]
EOF

# 5. Run
tmux new -s server
cd /workspace/Prompt-to-3d/PT3-backend && python run.py

# 6. Test
curl http://localhost:8000/health
```
