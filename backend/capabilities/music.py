"""fal.ai music generation — the background bed (ducked under voices in assembly).

Default CassetteAI ($0.02/min, exact-second duration) since the bed is background and ducked; the
premium option is ElevenLabs Music ($0.80/min). STUB (no key) writes silence of the target length.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

from . import pricing
from .fal_video import GenerationError, _download, _fal_key, _poll_fal
from ..finishing import FFMPEG

FAL_BASE = "https://queue.fal.run"

MUSIC_ENDPOINTS = {
    "cassetteai": ("CassetteAI/music-generator", "audio_file"),   # (endpoint, response key)
    "elevenlabs-music": ("fal-ai/elevenlabs/music", "audio"),
}


@dataclass
class MusicResult:
    ok: bool
    path: str | None = None
    cost_usd: float = 0.0
    model: str = ""
    stubbed: bool = False
    error: str | None = None


def _stub(output_path: str, duration_s: float, model: str) -> MusicResult:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{max(1.0, duration_s)}", "-c:a", "libmp3lame", "-b:a", "128k", output_path],
                   capture_output=True)
    return MusicResult(ok=Path(output_path).is_file(), path=output_path, cost_usd=0.0, model=model, stubbed=True)


def generate(*, prompt: str, output_path: str, duration_s: float,
             model: str = pricing.DEFAULT_MUSIC_MODEL, execute: bool = True) -> MusicResult:
    """Generate an instrumental bed of ~duration_s. output_path should end in .mp3/.wav."""
    est = pricing.music_cost(model, duration_s)
    if not execute or not _fal_key():
        return _stub(output_path, duration_s, model)

    endpoint, key = MUSIC_ENDPOINTS.get(model, MUSIC_ENDPOINTS[pricing.DEFAULT_MUSIC_MODEL])
    if model == "cassetteai":
        payload: dict = {"prompt": prompt, "duration": max(1, int(round(duration_s)))}
    else:
        payload = {"prompt": prompt, "music_length_ms": max(3000, int(duration_s * 1000)),
                   "force_instrumental": True}
    try:
        data, _ = _poll_fal(endpoint, payload, base=FAL_BASE, timeout_s=240)
        url = (data.get(key) or {}).get("url")
        if not url:
            return MusicResult(ok=False, model=model, error="no audio url")
        _download(url, Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return MusicResult(ok=False, model=model, error=f"music gen failed: {e}")
    return MusicResult(ok=True, path=output_path, cost_usd=est, model=model)
