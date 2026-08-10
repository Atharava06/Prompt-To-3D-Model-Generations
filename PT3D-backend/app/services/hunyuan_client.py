"""
Hunyuan3D local client.

Runs shape generation in-process via the official hy3dgen package. The model
path, subfolder, and quality preset are configurable so the app can use
Hunyuan3D-2.1 while keeping Hunyuan3D-2.0 as a fallback.
"""

from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

from app.config import settings
from app.core.quality import QualityPreset


class HunyuanConversionError(Exception):
    """Raised when the local Hunyuan3D pipeline fails."""


class HunyuanClient:
    def __init__(self) -> None:
        self._pipeline = None
        self._rembg = None
        self._vram_gb: float = 0.0
        self._loaded_model_key: tuple[str, str] | None = None

    def unload(self) -> None:
        """Release loaded Hunyuan objects so SDXL and Hunyuan VRAM do not overlap."""
        if self._pipeline is None and self._rembg is None:
            return

        print("[hunyuan] unloading before SDXL run ...")
        self._pipeline = None
        self._rembg = None
        self._vram_gb = 0.0
        self._loaded_model_key = None
        gc.collect()

        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception as exc:
            print(f"[hunyuan] warning: CUDA cache cleanup failed: {exc}")

    def connect(self) -> None:
        """Load the configured model pipeline and background remover lazily."""
        import torch

        self._add_repo_paths()

        package_family = "hy3dshape"
        try:
            from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
            from hy3dshape.rembg import BackgroundRemover
        except ImportError:
            package_family = "hy3dgen"
            from hy3dgen.rembg import BackgroundRemover
            from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

        model_path = settings.hunyuan_finetuned_model_path or settings.hunyuan_model_path
        model_key = (model_path, settings.hunyuan_subfolder)
        if self._pipeline is not None and self._loaded_model_key == model_key:
            return

        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            self._vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"[hunyuan] {torch.cuda.get_device_name(0)} - {self._vram_gb:.1f} GB VRAM")

        print(
            f"[hunyuan] loading from '{model_path}' "
            f"subfolder='{settings.hunyuan_subfolder}' ..."
        )
        t0 = time.time()

        load_kwargs = {
            "subfolder": settings.hunyuan_subfolder,
            "variant": "fp16",
            "use_safetensors": package_family == "hy3dgen",
        }
        if package_family == "hy3dshape":
            load_kwargs["device"] = device

        try:
            self._pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
                model_path,
                **load_kwargs,
            )
        except TypeError:
            load_kwargs.pop("variant", None)
            self._pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
                model_path,
                **load_kwargs,
            )
        self._rembg = BackgroundRemover()
        self._loaded_model_key = model_key

        print(f"[hunyuan] ready ({time.time() - t0:.1f}s)")

    def _add_repo_paths(self) -> None:
        if not settings.hunyuan_repo_path:
            return

        repo_path = Path(settings.hunyuan_repo_path)
        candidates = [repo_path / "hy3dshape", repo_path / "hy3dpaint", repo_path]
        for candidate in candidates:
            value = str(candidate)
            if candidate.exists() and value not in sys.path:
                sys.path.insert(0, value)

    def _preset_settings(self, quality_preset: QualityPreset) -> dict[str, float | int]:
        """Quality presets sized for single-GPU hosted inference."""
        if quality_preset == QualityPreset.FAST:
            return {
                "num_inference_steps": 24,
                "guidance_scale": 4.5,
                "octree_resolution": 256,
                "num_chunks": 6000,
            }
        if quality_preset == QualityPreset.QUALITY:
            return {
                "num_inference_steps": 56,
                "guidance_scale": 6.0,
                "octree_resolution": 512 if self._vram_gb >= 22 else 384,
                "num_chunks": 14000 if self._vram_gb >= 22 else 10000,
            }
        return {
            "num_inference_steps": 40,
            "guidance_scale": 5.5,
            "octree_resolution": 384 if self._vram_gb >= 20 else 256,
            "num_chunks": 10000 if self._vram_gb >= 20 else 8000,
        }

    def _prepare_image_for_shape(self, image):
        """
        Give Hunyuan a clean single-object input.

        SDXL images can contain too much empty border or a faint white background.
        Cropping to the alpha mask, adding controlled padding, and resizing back to
        a square canvas helps the shape model focus on object silhouette and depth.
        """
        from PIL import Image

        image = image.convert("RGBA")
        image = self._rembg(image).convert("RGBA")

        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        if bbox is None:
            return image

        cropped = image.crop(bbox)
        max_side = max(cropped.size)
        padding = max(32, int(max_side * 0.18))
        canvas_size = max_side + padding * 2
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
        canvas.alpha_composite(
            cropped,
            ((canvas_size - cropped.width) // 2, (canvas_size - cropped.height) // 2),
        )

        resampling = getattr(Image, "Resampling", Image).LANCZOS
        return canvas.resize((1024, 1024), resampling)

    def convert(
        self,
        image_path: Path,
        out_glb_path: Path,
        quality_preset: QualityPreset = QualityPreset.BALANCED,
    ) -> None:
        """
        Convert a PNG image to a GLB 3D model.

        Steps:
            1. Remove background with BackgroundRemover.
            2. Run the configured Hunyuan3D shape-generation pipeline.
            3. Export the trimesh as GLB.
        """
        from PIL import Image

        if self._pipeline is None:
            self.connect()

        preset_settings = self._preset_settings(quality_preset)
        print(
            f"[hunyuan] converting {image_path.name} "
            f"preset={quality_preset.value} settings={preset_settings}"
        )

        try:
            image = Image.open(str(image_path)).convert("RGBA")
            image = self._prepare_image_for_shape(image)

            t0 = time.time()
            meshes = self._pipeline(image=image, **preset_settings)
            mesh = meshes[0]

            out_glb_path.parent.mkdir(parents=True, exist_ok=True)
            mesh.export(str(out_glb_path))
            print(f"[hunyuan] saved -> {out_glb_path} ({time.time() - t0:.1f}s)")

        except Exception as exc:
            raise HunyuanConversionError(f"Hunyuan3D conversion failed: {exc}") from exc


hunyuan_client = HunyuanClient()
