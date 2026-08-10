"""
Entry point. Run with:

    python run.py
    # or directly:
    uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import os
import sys

# Make PyTorch shared libraries visible to CUDA extensions (e.g. custom_rasterizer).
# Required on Linux when extensions are built against PyTorch's bundled libs.
try:
    import torch
    torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
    ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    if torch_lib not in ld_path:
        os.environ["LD_LIBRARY_PATH"] = f"{torch_lib}:{ld_path}"
        # Re-exec so the dynamic linker picks up the updated path
        os.execv(sys.executable, [sys.executable] + sys.argv)
except ImportError:
    pass

import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
