from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.sdxl_generate import load_pipeline


DEFAULT_PROMPTS = [
    "ceramic coffee mug with C shaped handle",
    "matte black water bottle with screw cap",
    "small wireless computer mouse",
    "rounded bluetooth speaker with fabric texture",
    "desk lamp with circular shade",
    "leather backpack with front pocket",
    "running shoe with thick white sole",
    "rectangular cardboard shipping box",
    "toy sports car with smooth body",
    "handheld game controller",
    "metal wristwatch with round face",
    "tabletop camera lens",
    "folding pocket knife shaped utility tool",
    "plastic spray bottle with trigger",
    "minimal table chair with wooden legs",
    "modern office chair with armrests",
    "small potted plant in ceramic pot",
    "round analog alarm clock",
    "sleek desk microphone on small stand",
    "simple headphones with padded ear cups",
    "compact electric drill tool",
    "silver flashlight cylinder",
    "toy robot figure with simple limbs",
    "rectangular smartphone with blank screen",
    "open laptop computer at slight angle",
    "glass perfume bottle with square cap",
    "lipstick tube with cap removed",
    "small handbag with curved handle",
    "simple table fan with circular guard",
    "pair of sunglasses as one object",
    "metal key with round head",
    "kitchen toaster with two slots",
    "standing desk clock with brass frame",
    "small toy airplane with rounded wings",
    "wooden toy train engine",
    "compact toolbox with handle",
    "single tennis racket",
    "small electric kettle with handle",
    "modern pendant lamp shade",
    "decorative vase with narrow neck",
    "simple ring box opened slightly",
    "single leather wallet",
    "studio headphone amplifier box",
    "small drone with four propellers",
    "toy dinosaur figure",
    "soft plush teddy bear toy",
    "ceramic bowl with smooth rim",
    "single candle jar with lid",
    "rectangular smart speaker",
    "small table radio with knobs",
]


def slugify(text: str, limit: int = 54) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].strip("-") or "object"


def lora_caption(object_text: str, view: str, no_shadows: bool) -> str:
    view_text = "straight front view" if view == "front" else "front three-quarter view"
    shadow_text = "no shadows, no ground plane, no reflection, " if no_shadows else ""
    return (
        "A clean studio product photo of a single "
        f"{object_text}, centered, isolated on a white or light neutral background, "
        f"soft diffused lighting, highly detailed, {view_text}, "
        f"{shadow_text}clear silhouette, no extra objects, no text, no clutter."
    )


def generation_prompts(object_text: str, view: str, no_shadows: bool) -> tuple[str, str]:
    view_text = "straight front view, symmetrical front angle" if view == "front" else "front three-quarter view"
    shadow_text = "no shadows, no cast shadow, no contact shadow, no ground plane, no floor reflection, " if no_shadows else ""
    prompt = (
        "A clean studio product photo of a single "
        f"{object_text}, centered, isolated on a white or light neutral background, "
        "soft diffused lighting, highly detailed material texture, "
        f"{view_text}, {shadow_text}clear silhouette, no extra objects, no text, no clutter."
    )
    negative_prompt = (
        "multiple objects, duplicate, pair, group, cropped, cut off, partial object, "
        "busy background, props, scene, hands, person, text, watermark, logo, "
        "cartoon, illustration, sketch, blurry, low quality, harsh shadows, "
        "shadow, cast shadow, contact shadow, ground plane, floor, floor reflection, pedestal, stand"
    )
    return prompt, negative_prompt


def read_prompts(path: Path | None) -> list[str]:
    if path is None:
        return DEFAULT_PROMPTS
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SDXL product/prop images for LoRA dataset review.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prompts-file", type=Path)
    parser.add_argument("--max-images", type=int, default=50)
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--guidance", type=float, default=9.0)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=240624)
    parser.add_argument("--view", choices=["front", "three-quarter"], default="three-quarter")
    parser.add_argument("--no-shadows", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "metadata.jsonl"
    error_path = output_dir / "errors.jsonl"

    prompts = read_prompts(args.prompts_file)[: args.max_images]
    print(f"[dataset] output={output_dir}")
    print(
        f"[dataset] prompts={len(prompts)} steps={args.steps} guidance={args.guidance} "
        f"view={args.view} no_shadows={args.no_shadows}"
    )

    pipe, _ = load_pipeline()

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    for index, object_text in enumerate(prompts, start=1):
        file_name = f"{index:03d}-{slugify(object_text)}.png"
        output_path = output_dir / file_name
        if args.resume and output_path.exists() and output_path.stat().st_size > 0:
            print(f"[dataset] skip existing {file_name}")
            continue

        prompt, negative_prompt = generation_prompts(object_text, args.view, args.no_shadows)
        generator = torch.Generator(device=device).manual_seed(args.seed + index) if args.seed else None
        started = time.time()
        print(f"[dataset] {index}/{len(prompts)} {object_text!r}")
        try:
            image = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=args.steps,
                guidance_scale=args.guidance,
                height=args.height,
                width=args.width,
                generator=generator,
            ).images[0]
            image.save(output_path, format="PNG", optimize=False)
            append_jsonl(
                metadata_path,
                {
                    "file_name": file_name,
                    "text": lora_caption(object_text, args.view, args.no_shadows),
                    "object_prompt": object_text,
                    "view": args.view,
                    "no_shadows": args.no_shadows,
                    "steps": args.steps,
                    "guidance": args.guidance,
                    "seed": args.seed + index if args.seed else None,
                },
            )
            print(f"[dataset] saved {output_path} ({time.time() - started:.1f}s)")
        except Exception as exc:
            append_jsonl(
                error_path,
                {
                    "file_name": file_name,
                    "object_prompt": object_text,
                    "error": str(exc),
                },
            )
            print(f"[dataset] failed {file_name}: {exc}", file=sys.stderr)
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
