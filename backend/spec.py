"""Output specification — the locked SOW contract for finished videos.

Phase 0 of the build plan is to resolve the spec contradiction the feasibility doc flagged:

    SOW (written):   960x720 / 720p, <= 10 MB, 10-12 s
    Sample asset:    1080x1920,       17 MB, 13 s

The finishing layer cannot be built until this is settled with the client. We encode BOTH as
presets and select via VF_SPEC_PRESET, so flipping the decision is one env var, not a code change.
Default is the written SOW.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputSpec:
    name: str
    width: int
    height: int
    min_duration_s: float
    max_duration_s: float
    min_size_mb: float            # two-pass encode targets the middle of the band
    max_size_mb: float
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate_kbps: int = 96
    watermark_text: str = "Synthetically Generated"
    # End-frame rule: final frame loops back to the opening shot, no logos.
    enforce_end_frame_loop: bool = True

    @property
    def target_duration_s(self) -> float:
        return (self.min_duration_s + self.max_duration_s) / 2

    @property
    def target_size_mb(self) -> float:
        return (self.min_size_mb + self.max_size_mb) / 2

    @property
    def aspect_ratio(self) -> str:
        # Reduced W:H for the generator's aspect_ratio hint.
        from math import gcd
        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"


PRESETS: dict[str, OutputSpec] = {
    # Written SOW — the default until the client confirms.
    "sow_written": OutputSpec(
        name="sow_written",
        width=960,
        height=720,
        min_duration_s=10.0,
        max_duration_s=12.0,
        min_size_mb=6.0,
        max_size_mb=10.0,
    ),
    # The delivered sample asset (vertical, larger). Selectable if the client governs by the sample.
    "sample": OutputSpec(
        name="sample",
        width=1080,
        height=1920,
        min_duration_s=12.0,
        max_duration_s=13.0,
        min_size_mb=12.0,
        max_size_mb=17.0,
    ),
}


def get_spec(preset: str | None = None) -> OutputSpec:
    preset = preset or os.environ.get("VF_SPEC_PRESET", "sow_written")
    if preset not in PRESETS:
        raise ValueError(
            f"Unknown VF_SPEC_PRESET={preset!r}. Choose one of: {', '.join(PRESETS)}"
        )
    return PRESETS[preset]
