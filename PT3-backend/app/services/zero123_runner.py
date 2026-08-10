"""
Zero123++ multi-view synthesis service.

Sits between SDXL and Hunyuan3D in the pipeline. Takes one high-quality
front-view image from SDXL and generates 6 geometrically consistent orbital
views. These are passed to Hunyuan3D for vastly better shape reconstruction
and texture painting — solving the single-view ambiguity problem.

Why this matters:
  - SDXL can't generate consistent multi-angle images of the same object.
    Each angle hallucinate a different model/colour/shape.
  - Zero123++ is trained specifically to orbit a single image in 3D space,
    producing views that are mathematically consistent with one 3D shape.
  - Hunyuan3D shape gen with 6 consistent views >> single front view.
  - Hunyuan3D texture with 6 real views >> texture guessing from 1 image.

GPU layout:
  4x RTX 3090  →  GPU 1 (was idle, ~8GB needed)
  H100 80GB    →  GPU 0 (alongside everything else)

Model: sudo-ai/zero123plus-v1.2
Output: 6 views at 320×320, orbital azimuths 30°/90°/150°/210°/270°/330°
"""

import time
from pathlib import Path

from app.config import settings


class Zero123Runner:
    def __init__(self) -> None:
        self._pipeline = None
        self._device: str = "cpu"

    def connect(self) -> None:
        import torch
        from diffusers import DiffusionPipeline

        gpu_idx = int(settings.zero123_gpu)
        self._device = f"cuda:{gpu_idx}" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if "cuda" in self._device else torch.float32

        print(f"[zero123] loading Zero123++ on {self._device} …")
        t0 = time.time()

        self._pipeline = DiffusionPipeline.from_pretrained(
            "sudo-ai/zero123plus-v1.2",
            custom_pipeline="sudo-ai/zero123plus-pipeline",
            torch_dtype=dtype,
            trust_remote_code=True,
        )
        self._pipeline.to(self._device)

        try:
            self._pipeline.enable_xformers_memory_efficient_attention()
            print("[zero123] xformers enabled")
        except Exception:
            pass

        print(f"[zero123] ready in {time.time() - t0:.1f}s")

    def generate_views(self, image_path: Path) -> list[Path]:
        """
        Generate 6 consistent orbital views from a single front-facing image.

        Args:
            image_path: Path to the front-view PNG (rembg already applied).

        Returns:
            List of 6 Paths to 320×320 view PNGs saved alongside the source.
            Returns [] if Zero123++ is unavailable (graceful degradation).
        """
        import torch
        from PIL import Image

        if self._pipeline is None:
            try:
                self.connect()
            except Exception as e:
                print(f"[zero123] load failed ({e}) — skipping multi-view")
                return []

        try:
            img = Image.open(str(image_path)).convert("RGBA")

            # Composite onto white — Zero123++ expects RGB
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                bg.paste(img)

            # Zero123++ requires 512×512 input
            bg = bg.resize((512, 512), Image.LANCZOS)

            t0 = time.time()
            print("[zero123] synthesising 6 orbital views …")
            with torch.no_grad():
                result = self._pipeline(bg, num_inference_steps=75).images[0]

            # Split the 3×2 output grid into 6 individual view images
            # Grid layout (azimuths, elevations):
            #   row 0: (30°, +20°)  (90°, +20°)  (150°, +20°)
            #   row 1: (210°, -10°) (270°, -10°) (330°, -10°)
            cols, rows = 3, 2
            w, h = result.size
            tw, th = w // cols, h // rows

            view_paths: list[Path] = []
            stem = image_path.stem
            out_dir = image_path.parent

            for row in range(rows):
                for col in range(cols):
                    idx = row * cols + col
                    view = result.crop((col * tw, row * th, (col + 1) * tw, (row + 1) * th))
                    p = out_dir / f"{stem}_z{idx}.png"
                    view.save(str(p))
                    view_paths.append(p)

            print(f"[zero123] 6 views saved in {time.time() - t0:.1f}s")
            return view_paths

        except Exception as e:
            print(f"[zero123] view generation failed ({e}) — skipping multi-view")
            return []


zero123_runner = Zero123Runner()
