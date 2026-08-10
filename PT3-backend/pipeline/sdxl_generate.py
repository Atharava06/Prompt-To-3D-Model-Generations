"""
SDXL image generation script — single high-quality front view.

Generates one 1024×1024 front-facing product image. Zero123++ (the next
pipeline stage) handles multi-view synthesis from this single image, which
produces geometrically consistent views far better than SDXL-generated angles.

Called by the backend as a subprocess:
    python sdxl_generate.py <job_id> <output_dir> <prompt words...>

Outputs:
    <output_dir>/<job_id>.png
"""

import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")


def parse_args() -> tuple[str, str, str]:
    if len(sys.argv) < 4:
        print("Usage: sdxl_generate.py <job_id> <output_dir> <prompt...>")
        sys.exit(1)
    job_id = sys.argv[1]
    output_dir = sys.argv[2]
    prompt_text = " ".join(sys.argv[3:]).strip() or "object"
    return job_id, output_dir, prompt_text


def build_prompts(user_text: str) -> tuple[str, str]:
    prompt = (
        f"studio product photograph of a single {user_text}, "
        "front three-quarter view, camera slightly above object height, "
        "floating isolated in air, no base, no stand, no pedestal, no surface, "
        "centered in frame, pure white background, "
        "professional studio lighting, even diffuse illumination, "
        "no shadows below object, no ground plane, no floor reflection, "
        "all surface materials clearly visible, visible texture and surface detail, "
        "every material layer distinct, sharp material edges, "
        "photorealistic, hyper detailed, sharp focus, "
        "physically based rendering quality, 8k uhd"
    )
    negative_prompt = (
        "multiple objects, duplicate, pair, group, collection, "
        "stand, pedestal, base, platform, display stand, mount, holder, "
        "surface, table, floor, ground, shelf, "
        "shadow underneath, ground shadow, floor reflection, cast shadow, "
        "perfect side view, rear view, back view, extreme angle, "
        "cropped, cut off, partial, out of frame, "
        "harsh shadows, dramatic shadows, specular glare, overexposed, "
        "background clutter, props, scene, environment, "
        "blurry, out of focus, motion blur, depth of field, "
        "fisheye, wide angle distortion, "
        "text, watermark, logo, signature, "
        "painting, illustration, cartoon, anime, sketch, "
        "low quality, worst quality, jpeg artifacts, noise, grain"
    )
    return prompt, negative_prompt


def get_vram_gb() -> float:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / 1e9
    except Exception:
        pass
    return 0.0


def load_pipeline():
    import torch
    from diffusers import AutoencoderKL, DPMSolverMultistepScheduler, StableDiffusionXLPipeline

    model_source = os.environ.get("SDXL_MODEL_PATH", "stabilityai/stable-diffusion-xl-base-1.0")
    vram_gb = get_vram_gb()
    device = "cuda" if vram_gb > 0 else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    if device == "cuda":
        print(f"[sdxl] GPU: {torch.cuda.get_device_name(0)} ({vram_gb:.1f} GB VRAM)")

    vae = None
    vae_kwargs = {"torch_dtype": dtype}
    if device == "cuda":
        vae_kwargs["variant"] = "fp16"
    for vae_subfolder in ("vae_1_0", "vae"):
        try:
            vae = AutoencoderKL.from_pretrained(
                model_source,
                subfolder=vae_subfolder,
                **vae_kwargs,
            )
            print(f"[sdxl] using {vae_subfolder}")
            break
        except Exception:
            if "variant" in vae_kwargs:
                try:
                    fallback_kwargs = dict(vae_kwargs)
                    fallback_kwargs.pop("variant", None)
                    vae = AutoencoderKL.from_pretrained(
                        model_source,
                        subfolder=vae_subfolder,
                        **fallback_kwargs,
                    )
                    print(f"[sdxl] using {vae_subfolder} without fp16 variant")
                    break
                except Exception:
                    vae = None

    pipeline_kwargs = {"vae": vae, "torch_dtype": dtype, "use_safetensors": True}
    if device == "cuda":
        pipeline_kwargs["variant"] = "fp16"
    try:
        pipe = StableDiffusionXLPipeline.from_pretrained(model_source, **pipeline_kwargs)
    except Exception:
        pipeline_kwargs.pop("variant", None)
        pipe = StableDiffusionXLPipeline.from_pretrained(model_source, **pipeline_kwargs)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config, use_karras_sigmas=True, algorithm_type="dpmsolver++",
    )
    lora_path = os.environ.get("SDXL_LORA_PATH", "").strip()
    if lora_path:
        lora_scale = float(os.environ.get("SDXL_LORA_SCALE", "1.0"))
        print(f"[sdxl] loading LoRA from '{lora_path}' scale={lora_scale}")
        pipe.load_lora_weights(lora_path)
        pipe.fuse_lora(lora_scale=lora_scale)

    if device == "cuda":
        if vram_gb < 12:
            pipe.enable_attention_slicing()
            pipe.enable_vae_slicing()
            pipe.enable_model_cpu_offload()
            print("[sdxl] low-VRAM mode: CPU offload enabled")
        else:
            pipe = pipe.to(device)
            try:
                pipe.enable_xformers_memory_efficient_attention()
                print("[sdxl] xformers enabled")
            except Exception:
                pass
    else:
        print("[sdxl] no CUDA — running on CPU (slow)")
        pipe = pipe.to(device)

    return pipe, vram_gb


def load_refiner(vram_gb: float):
    refiner_source = os.environ.get("SDXL_REFINER_PATH", "")
    if not refiner_source:
        return None
    if vram_gb < 16:
        print(f"[sdxl] refiner skipped — need 16+ GB VRAM, have {vram_gb:.1f} GB")
        return None

    import torch
    from diffusers import DPMSolverMultistepScheduler, StableDiffusionXLImg2ImgPipeline

    print(f"[sdxl] loading refiner from '{refiner_source}' …")
    refiner = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        refiner_source, torch_dtype=torch.float16, use_safetensors=True,
    )
    refiner.scheduler = DPMSolverMultistepScheduler.from_config(
        refiner.scheduler.config, use_karras_sigmas=True, algorithm_type="dpmsolver++",
    )
    refiner = refiner.to("cuda")
    print("[sdxl] refiner ready")
    return refiner


def main() -> None:
    job_id, output_dir, user_text = parse_args()
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{job_id}.png")
    print(f"[sdxl] job={job_id}  prompt={user_text!r}")

    pipe, vram_gb = load_pipeline()
    refiner = load_refiner(vram_gb)
    prompt, negative_prompt = build_prompts(user_text)

    t0 = time.time()

    if refiner is not None:
        print("[sdxl] running base (80% denoising) …")
        latents = pipe(
            prompt=prompt, negative_prompt=negative_prompt,
            num_inference_steps=60, guidance_scale=9.0,
            height=1024, width=1024,
            denoising_end=0.8, output_type="latent",
        ).images
        print("[sdxl] running refiner (20% polish) …")
        image = refiner(
            prompt=prompt, negative_prompt=negative_prompt,
            num_inference_steps=60, guidance_scale=9.0,
            denoising_start=0.8, image=latents,
        ).images[0]
    else:
        print("[sdxl] running single-stage (60 steps, 1024×1024) …")
        image = pipe(
            prompt=prompt, negative_prompt=negative_prompt,
            num_inference_steps=60, guidance_scale=9.0,
            height=1024, width=1024,
        ).images[0]

    image.save(output_path, format="PNG", optimize=False)
    print(f"[sdxl] saved → {output_path}  ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
