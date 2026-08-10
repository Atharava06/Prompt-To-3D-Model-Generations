# Cloud GPU image — PyTorch + CUDA included.
# Build: docker build -t prompt-to-3d .
# Run:   docker run --gpus all -p 8000:8000 \
#          -v /your/volume:/workspace \
#          --env-file PT3-backend/.env.cloud.example \
#          prompt-to-3d
FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install git so we can clone Hunyuan3D-2 for the hy3dgen package
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Install Hunyuan3D-2 source (provides the hy3dgen Python package — no API key needed)
RUN git clone --depth=1 https://github.com/Tencent/Hunyuan3D-2 /opt/hy3dgen-src && \
    pip install --no-cache-dir -e /opt/hy3dgen-src

# Install server + pipeline dependencies
COPY PT3-backend/requirements.txt /tmp/server_req.txt
COPY PT3-backend/pipeline/requirements.txt /tmp/pipeline_req.txt
RUN pip install --no-cache-dir -r /tmp/server_req.txt && \
    grep -v '^#' /tmp/pipeline_req.txt | grep -v '^$' | grep -v 'hy3dgen' | grep -v 'torch' | \
    xargs pip install --no-cache-dir

# Copy backend code
COPY PT3-backend/ /app/

EXPOSE 8000

# ── Runtime defaults (override via --env-file or -e flags) ────────────────────
ENV HOST=0.0.0.0
ENV PORT=8000

# HF Hub cache — point at a mounted volume so models persist across restarts.
# If unset, defaults to ~/.cache/huggingface inside the container (ephemeral).
ENV HF_HOME=/workspace/hf_cache

# hy3dgen model cache — where Hunyuan3D-2 weights are stored/looked up.
# smart_load_model checks here before downloading from HF Hub.
ENV HY3DGEN_MODELS=/workspace/models

CMD ["python", "run.py"]
