#!/bin/bash
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Prompt-to-3D  â€”  Deploy / update on running pod
#
# Run this every time you push new code from local machine:
#   bash deploy.sh
#
# What it does:
#   1. git pull latest code from GitHub
#   2. Kill existing backend
#   3. Restart with updated code
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
set -e

WORKSPACE="/workspace/Prompt-to-3d"

echo "[deploy] Pulling latest code from GitHub â€¦"
cd "$WORKSPACE"
git pull origin main

echo "[deploy] Stopping existing backend â€¦"
pkill -f uvicorn 2>/dev/null && echo "[deploy] Stopped." || echo "[deploy] Nothing running."
sleep 1

echo "[deploy] Starting backend â€¦"
cd "$WORKSPACE/PT3-backend"
source venv/bin/activate
python run.py
