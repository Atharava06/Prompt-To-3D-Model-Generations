from __future__ import annotations

from enum import Enum


class QualityPreset(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    QUALITY = "quality"

