#!/bin/bash
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Prompt-to-3D  â€”  One-shot cloud pod setup
#
# Usage (run once on a fresh pod):
#   bash cloud_setup.sh
#
# Then configure .env:
#   cp PT3-backend/.env.example PT3-backend/.env
#   nano PT3-backend/.env          # set HOST, PORT, ALLOWED_ORIGINS
#
# Then start:
#   bash deploy.sh
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
set -e

REPO="https://github.com/nikkvijay/Prompt-to-3d.git"
WORKSPACE="/workspace/Prompt-to-3d"

echo ""
echo "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—"
echo "â•‘   Prompt-to-3D  Cloud Setup          â•‘"
echo "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"
echo ""

# â”€â”€ 1. System packages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[1/7] Installing system packages â€¦"
apt-get update -q
apt-get install -y -q git python3-pip python3-venv \
    libgl1 libglib2.0-0 libgomp1 \
    curl wget build-essential

# â”€â”€ 2. Clone / update repo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[2/7] Setting up project repo â€¦"
if [ -d "$WORKSPACE/.git" ]; then
    echo "  repo exists â€” pulling latest â€¦"
    cd "$WORKSPACE" && git pull origin main
else
    echo "  cloning from GitHub â€¦"
    git clone "$REPO" "$WORKSPACE"
    cd "$WORKSPACE"
fi

cd "$WORKSPACE/PT3-backend"

# â”€â”€ 3. Python venv â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[3/7] Creating Python venv â€¦"
python3 -m venv venv
source venv/bin/activate

# â”€â”€ 4. PyTorch with CUDA â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[4/7] Installing PyTorch (CUDA 12.1) â€¦"
# Use cu121 for RTX 3090 / A100 / H100 compatibility
pip install --quiet torch==2.5.1 torchvision \
    --index-url https://download.pytorch.org/whl/cu121

# â”€â”€ 5. Backend + pipeline dependencies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[5/7] Installing backend dependencies â€¦"
pip install --quiet -r requirements.txt
pip install --quiet -r pipeline/requirements.txt
pip install --quiet pymeshlab rembg[gpu] xformers

# â”€â”€ 6. Hunyuan3D-2 (hy3dgen) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[6/7] Installing Hunyuan3D-2 (hy3dgen) â€¦"
if [ ! -d "/tmp/Hunyuan3D-2" ]; then
    git clone --depth 1 https://github.com/Tencent/Hunyuan3D-2.git /tmp/Hunyuan3D-2
fi
cd /tmp/Hunyuan3D-2
pip install --quiet -e .
# Build custom CUDA rasterizer
if [ -d "hy3dgen/texgen/custom_rasterizer" ]; then
    cd hy3dgen/texgen/custom_rasterizer
    python setup.py build_ext --inplace 2>&1 | tail -5 || echo "  rasterizer build failed â€” texture may fall back to CPU"
    cd /tmp/Hunyuan3D-2
fi
cd "$WORKSPACE/PT3-backend"

# â”€â”€ 7. Environment config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "[7/7] Setting up .env â€¦"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "  âš   Created .env from template."
    echo "     Edit it now to set your pod IP and ports:"
    echo "       nano $WORKSPACE/PT3-backend/.env"
    echo ""
fi

source venv/bin/activate

echo ""
echo "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—"
echo "â•‘   Setup complete!                    â•‘"
echo "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"
echo ""
echo "Next steps:"
echo "  1. Edit .env:  nano PT3-backend/.env"
echo "  2. Start:      bash deploy.sh"
echo ""
