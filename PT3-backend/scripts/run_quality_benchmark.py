from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BENCHMARK_PROMPTS = [
    "white ceramic coffee mug with one handle, centered product render",
    "transparent reusable water bottle with screw cap",
    "matte black wireless computer mouse, ergonomic shape",
    "compact bluetooth speaker with rounded corners and fabric grille",
    "small desk lamp with conical shade and thin stem",
    "modern wristwatch with round face and leather strap",
    "leather boot, single shoe, side view product photo",
    "canvas backpack with front pocket and shoulder straps",
    "rectangular cardboard shipping box, closed top flaps",
    "toy robot figure with blocky limbs, standing upright",
    "plastic toy airplane with wings and tail fins",
    "toy sports car with smooth body and four visible wheels",
    "handheld game controller with buttons and analog sticks",
    "kitchen toaster with two slots and side lever",
    "stainless steel cooking pot with two handles and lid",
    "chef knife with black handle and shiny blade",
    "red fire extinguisher with hose and pressure gauge",
    "yellow power drill with handle and drill bit",
    "metal hammer with rubber grip",
    "adjustable wrench with open jaw, centered object",
    "green watering can with handle and long spout",
    "small cactus in a clay pot",
    "round wall clock with simple black hands",
    "tabletop picture frame with thick white border",
    "pair of over-ear headphones, front product render",
    "folded sunglasses with dark lenses",
    "lipstick tube with cap removed, product render",
    "perfume bottle with square glass body and cap",
    "sports trophy cup with handles and base",
    "gold wedding ring, smooth circular band",
    "classic chess knight piece, single object",
    "treasure chest with metal bands and latch",
    "wooden toy train engine, simple wheels",
    "rubber duck bath toy, yellow material",
    "soccer ball, white and black panels",
    "basketball with visible seams, isolated object",
    "baseball cap with curved brim",
    "travel suitcase with handle and wheels",
    "office stapler, black plastic and metal",
    "calculator with number buttons and display",
    "notebook with spiral binding and closed cover",
    "fountain pen with metallic nib",
    "flashlight with textured handle",
    "padlock with U-shaped shackle",
    "door key with round head and teeth",
    "USB flash drive with cap removed",
    "small first aid kit box with cross symbol",
    "spray bottle with trigger nozzle",
    "rolled yoga mat with carrying strap",
    "ceramic teapot with handle, spout, and lid",
]


def request_json(
    method: str,
    url: str,
    payload: dict | None = None,
    token: str | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: {exc.code} {body}") from exc


def login(api_base: str, user_id: str, password: str) -> str:
    response = request_json(
        "POST",
        f"{api_base}/auth/login",
        {"user_id": user_id, "password": password},
    )
    return response["access_token"]


def wait_for_job(api_base: str, token: str, job_id: str, poll_seconds: int) -> dict:
    while True:
        status = request_json("GET", f"{api_base}/status/{job_id}", token=token)
        if status["status"] in {"done", "failed"}:
            return status
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the 30-prompt Hunyuan quality benchmark through the live API."
    )
    parser.add_argument("--api-base", default=os.environ.get("PT3_API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--user-id", default=os.environ.get("PT3_BENCHMARK_USER", "admin"))
    parser.add_argument("--password", default=os.environ.get("PT3_BENCHMARK_PASSWORD"))
    parser.add_argument("--quality-preset", choices=["fast", "balanced", "quality"], default="balanced")
    parser.add_argument("--limit", type=int, default=len(BENCHMARK_PROMPTS))
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "benchmark_runs"),
    )
    args = parser.parse_args()

    if not args.password:
        raise SystemExit("Provide --password or PT3_BENCHMARK_PASSWORD.")

    api_base = args.api_base.rstrip("/")
    token = login(api_base, args.user_id, args.password)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    prompts = BENCHMARK_PROMPTS[: max(0, min(args.limit, len(BENCHMARK_PROMPTS)))]

    results = []
    for index, prompt in enumerate(prompts, start=1):
        print(f"[{index}/{len(prompts)}] {prompt}")
        started = request_json(
            "POST",
            f"{api_base}/generate",
            {"prompt": prompt, "quality_preset": args.quality_preset},
            token=token,
        )
        final_status = wait_for_job(api_base, token, started["job_id"], args.poll_seconds)
        results.append(
            {
                "run_id": run_id,
                "job_id": started["job_id"],
                "prompt": prompt,
                "quality_preset": args.quality_preset,
                "status": final_status["status"],
                "error": final_status.get("error"),
                "review_notes": "",
                "silhouette_pass": None,
                "missing_parts_pass": None,
                "mesh_integrity_pass": None,
                "object_completeness_pass": None,
                "frontend_preview_pass": None,
            }
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"quality-benchmark-{run_id}.json"
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
