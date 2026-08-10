"""
SDXL subprocess runner.

Encapsulates launching the SDXL generation script as a blocking subprocess.
Raises SDXLFailedError on non-zero exit so the pipeline orchestrator can
update job state cleanly.
"""

import os
import subprocess
from pathlib import Path

from app.config import settings


class SDXLFailedError(Exception):
    """Raised when the SDXL subprocess exits with a non-zero return code."""


class SDXLRunner:
    @staticmethod
    def _stringify_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def _tail(text: str, limit: int = 2400) -> str:
        text = text.strip()
        if len(text) <= limit:
            return text
        return "..." + text[-limit:]

    def run(self, job_id: str, prompt: str, output_dir: Path) -> None:
        """
        Synchronously run the SDXL generation script.

        Blocks until the subprocess exits. Raises SDXLFailedError if it
        exits with a non-zero return code.

        Args:
            job_id:     10-char hex job identifier.
            prompt:     Raw user prompt string.
            output_dir: Directory where the script will write {job_id}.png.
        """
        cmd = [
            settings.sdxl_python,
            str(settings.sdxl_script),
            job_id,
            str(output_dir),
            prompt,
        ]

        env = {
            **os.environ,
            "SDXL_MODEL_PATH": settings.sdxl_model_path,
            "SDXL_LORA_SCALE": str(settings.sdxl_lora_scale),
        }
        if settings.sdxl_lora_path:
            env["SDXL_LORA_PATH"] = settings.sdxl_lora_path
        try:
            result = subprocess.run(
                cmd,
                shell=False,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.sdxl_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(
                part
                for part in [
                    self._stringify_output(exc.stdout),
                    self._stringify_output(exc.stderr),
                ]
                if part
            )
            raise SDXLFailedError(
                f"SDXL timed out after {settings.sdxl_timeout_seconds}s "
                f"(job_id={job_id}). {self._tail(output)}"
            ) from exc

        if result.returncode != 0:
            output = "\n".join(part for part in [result.stdout, result.stderr] if part)
            raise SDXLFailedError(
                f"SDXL subprocess exited with code {result.returncode} "
                f"(job_id={job_id}). {self._tail(output)}"
            )

        expected_output = output_dir / f"{job_id}.png"
        if not expected_output.exists() or expected_output.stat().st_size == 0:
            output = "\n".join(part for part in [result.stdout, result.stderr] if part)
            raise SDXLFailedError(
                f"SDXL completed but did not create a valid PNG "
                f"(job_id={job_id}, expected={expected_output}). {self._tail(output)}"
            )


# Module-level singleton
sdxl_runner = SDXLRunner()
