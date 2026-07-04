"""fal.ai lip-sync — animate a character's reference still to a voice line (talking head).

Default VEED Fabric 1.0 (cheapest still-image talking head, image+audio@480p); OmniHuman v1.5 is the
premium option. Output is a video clip that already contains the audio, used directly as a "talking"
shot in the scored assembly.

STUB (no key): builds a static talking clip (still held for the audio length + the audio muxed) so the
pipeline behaves identically at $0.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

from . import pricing
from .fal_video import GenerationError, _download, _fal_key, _poll_fal, image_ref
from ..finishing import FFMPEG, media_duration

FAL_BASE = "https://queue.fal.run"

LIPSYNC_ENDPOINTS = {
    "veed-fabric": "veed/fabric-1.0",
    "omnihuman": "fal-ai/bytedance/omnihuman/v1.5",
    "kling-avatar": "fal-ai/kling-video/ai-avatar/v2/standard",
}


@dataclass
class LipsyncResult:
    ok: bool
    path: str | None = None
    duration_s: float = 0.0
    cost_usd: float = 0.0
    model: str = ""
    stubbed: bool = False
    error: str | None = None


def _stub(image_path: str, audio_path: str, output_path: str, model: str) -> LipsyncResult:
    dur = media_duration(audio_path) or 3.0
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-loop", "1", "-i", str(image_path), "-i", str(audio_path),
                    "-t", f"{dur}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", output_path], capture_output=True)
    return LipsyncResult(ok=True, path=output_path, duration_s=dur, cost_usd=0.0, model=model, stubbed=True)


def lipsync(*, image_path: str, audio_path: str, output_path: str,
            model: str = pricing.DEFAULT_LIPSYNC_MODEL, resolution: str = "480p",
            execute: bool = True) -> LipsyncResult:
    """Animate a still to a voice line. Returns a talking clip (video with embedded audio)."""
    dur = media_duration(audio_path)
    est = pricing.lipsync_cost(model, dur)
    if not execute or not _fal_key():
        return _stub(image_path, audio_path, output_path, model)

    endpoint = LIPSYNC_ENDPOINTS.get(model, LIPSYNC_ENDPOINTS[pricing.DEFAULT_LIPSYNC_MODEL])
    payload: dict = {"image_url": image_ref(image_path), "audio_url": image_ref(audio_path)}
    if model == "veed-fabric":
        payload["resolution"] = resolution
    elif model == "omnihuman":
        payload["resolution"] = "720p" if resolution != "480p" else "720p"   # omnihuman: 720p|1080p
    try:
        data, _ = _poll_fal(endpoint, payload, base=FAL_BASE, timeout_s=600)
        url = (data.get("video") or {}).get("url")
        if not url:
            return LipsyncResult(ok=False, model=model, error="no video url")
        _download(url, Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return LipsyncResult(ok=False, model=model, error=f"lipsync failed: {e}")
    return LipsyncResult(ok=True, path=output_path, duration_s=media_duration(output_path) or dur,
                         cost_usd=est, model=model)
