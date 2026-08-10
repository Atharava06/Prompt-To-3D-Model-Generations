#!/usr/bin/env bash
set -euo pipefail

# CheapCUDA fresh-GPU bootstrap for Prompt-to-3D.
# This prepares the FastAPI backend, Supabase/R2-backed auth/history/files,
# and a supervisor service. It intentionally does not download model weights.

REPO_URL="${REPO_URL:-https://github.com/nikkvijay/Prompt-to-3d.git}"
APP_DIR="${APP_DIR:-/root/Prompt-to-3d}"
APP_ARCHIVE="${APP_ARCHIVE:-/tmp/prompt-to-3d-backend-upload.tar.gz}"
BACKEND_DIR="$APP_DIR/PT3-backend"
PORT="${PORT:-50200}"
HOST="${HOST:-0.0.0.0}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-https://prompt-to-3d-frontend.vercel.app}"
SERVICE_NAME="${SERVICE_NAME:-prompt-to-3d-backend}"

echo "[1/6] Installing system packages"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git python3 python3-venv python3-pip supervisor curl \
  libgl1 libglib2.0-0 libgomp1

echo "[2/6] Installing app code"
if [ -f "$APP_ARCHIVE" ]; then
  echo "  using uploaded archive: $APP_ARCHIVE"
  rm -rf "$APP_DIR"
  mkdir -p "$APP_DIR"
  tar -xzf "$APP_ARCHIVE" -C "$APP_DIR"
elif [ -d "$APP_DIR/.git" ]; then
  echo "  updating existing git checkout"
  git -C "$APP_DIR" fetch origin main
  git -C "$APP_DIR" reset --hard origin/main
else
  echo "  cloning from GitHub"
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$BACKEND_DIR"

echo "[3/6] Creating Python virtualenv"
python3 -m venv venv
venv/bin/python -m pip install --upgrade pip wheel setuptools

echo "[4/6] Installing backend API dependencies only"
venv/bin/pip install -r requirements.txt

echo "[5/6] Writing environment file"
if [ -f .env ] && grep -Eq 'C:\\|HOST=127\.0\.0\.1|PORT=8000' .env; then
  mv .env ".env.local-backup.$(date +%s)"
fi

if [ ! -f .env ]; then
  cat > .env <<EOF
HOST=$HOST
PORT=$PORT
RELOAD=false
ALLOWED_ORIGINS='["$FRONTEND_ORIGIN","http://localhost:5173","http://127.0.0.1:5173"]'

# Fill these once, then rerun: supervisorctl restart $SERVICE_NAME
DATABASE_URL=
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=

# Models are intentionally not downloaded by this bootstrap.
# Generation will require these later:
SDXL_MODEL_PATH=/root/models/sdxl
# Optional products/props LoRA; leave empty to use base SDXL.
SDXL_LORA_PATH=
SDXL_LORA_SCALE=1.0
HUNYUAN_MODEL_PATH=/root/models/hunyuan3d-2.1
# Optional fine-tuned checkpoint; leave empty to use base Hunyuan.
HUNYUAN_FINETUNED_MODEL_PATH=
HUNYUAN_SUBFOLDER=hunyuan3d-dit-v2-1
HUNYUAN_REPO_PATH=/root/Hunyuan3D-2.1
ADMIN_USER_IDS='["admin"]'
EOF
  chmod 600 .env
else
  echo "  Keeping existing $BACKEND_DIR/.env"
fi

echo "[6/6] Installing supervisor service"
cat > "/etc/supervisor/conf.d/$SERVICE_NAME.conf" <<EOF
[program:$SERVICE_NAME]
directory=$BACKEND_DIR
command=$BACKEND_DIR/venv/bin/python run.py
autostart=true
autorestart=true
startsecs=5
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/$SERVICE_NAME.out.log
stderr_logfile=/var/log/$SERVICE_NAME.err.log
environment=PYTHONUNBUFFERED="1"
EOF

supervisorctl reread
supervisorctl update
supervisorctl restart "$SERVICE_NAME" || supervisorctl start "$SERVICE_NAME"

echo ""
echo "Backend service status:"
supervisorctl status "$SERVICE_NAME" || true
echo ""
echo "Health check:"
curl -fsS "http://127.0.0.1:$PORT/health" || true
echo ""
echo "Done. If .env was empty, fill DATABASE_URL and R2_* before real use."
