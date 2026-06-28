"""Output specification — the delivery contract for a finished post.

A post is rendered to a platform format (vertical reel, square feed, landscape long-form). Unlike a
single product clip, a post is a multi-shot reel whose length is the sum of its shots, so we target a
video bitrate (quality) rather than a fixed file-size band — the file size follows the duration.

Select the active default with VF_SPEC_PRESET; a storyboard can also carry its own format which maps
to one of these presets. Default is the vertical reel (Instagram Reels / TikTok / YouTube Shorts).
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
    video_mbps: float = 8.0           # target video bitrate; size follows duration
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate_kbps: int = 128
    # Watermark is OFF by default — a burned-in caption breaks the influencer persona. Set a value
    # (e.g. an @handle) only if a character wants a signature super.
    watermark_text: str = ""

    @property
    def target_duration_s(self) -> float:
        return (self.min_duration_s + self.max_duration_s) / 2

    @property
    def video_bitrate_kbps(self) -> int:
        return int(self.video_mbps * 1000)

    @property
    def aspect_ratio(self) -> str:
        # Reduced W:H for the generator's aspect_ratio hint.
        from math import gcd
        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"


PRESETS: dict[str, OutputSpec] = {
    # Vertical reel — Instagram Reels / TikTok / YouTube Shorts. The default.
    "reel": OutputSpec(
        name="reel",
        width=1080,
        height=1920,
        min_duration_s=8.0,
        max_duration_s=90.0,
        video_mbps=8.0,
    ),
    # Square feed post (Instagram / Facebook).
    "square": OutputSpec(
        name="square",
        width=1080,
        height=1080,
        min_duration_s=5.0,
        max_duration_s=60.0,
        video_mbps=8.0,
    ),
    # Landscape long-form — YouTube / horizontal players.
    "landscape": OutputSpec(
        name="landscape",
        width=1920,
        height=1080,
        min_duration_s=15.0,
        max_duration_s=600.0,
        video_mbps=10.0,
    ),
}

# Map a storyboard `format` to a spec preset (a story can target "short" which is a vertical reel).
FORMAT_TO_PRESET = {
    "reel": "reel",
    "short": "reel",
    "story": "reel",
    "tiktok": "reel",
    "square": "square",
    "feed": "square",
    "longform": "landscape",
    "youtube": "landscape",
    "landscape": "landscape",
}


def get_spec(preset: str | None = None) -> OutputSpec:
    preset = preset or os.environ.get("VF_SPEC_PRESET", "reel")
    # Allow a storyboard format name to resolve to its spec.
    preset = FORMAT_TO_PRESET.get(preset, preset)
    if preset not in PRESETS:
        raise ValueError(
            f"Unknown spec/format {preset!r}. Choose one of: {', '.join(PRESETS)} "
            f"(or a format: {', '.join(FORMAT_TO_PRESET)})"
        )
    return PRESETS[preset]
