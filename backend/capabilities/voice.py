"""fal.ai TTS — character voices + narration (the Voice DNA renderer).

Quality-first default: ElevenLabs multilingual-v2 (stable, expressive, speed control). A character's
`voice.voice_id` is an ElevenLabs voice NAME (Rachel, Aria, ...) reused for every line so the voice is
consistent by construction. Chatterbox is the alternative when you need zero-shot cloning from a
reference sample (`clone_audio`) or the ~4x lower cost.

Graceful STUB (no key): writes a silence clip sized to the text so durations flow through assembly at
$0 — the pipeline + UI are fully testable without a key.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from . import pricing
from .fal_video import GenerationError, _download, _fal_key, _poll_fal, _simulated_failure, image_ref
from ..finishing import FFMPEG, media_duration

FAL_BASE = "https://queue.fal.run"

VOICE_ENDPOINTS = {
    "elevenlabs-multilingual-v2": "fal-ai/elevenlabs/tts/multilingual-v2",
    "elevenlabs-v3": "fal-ai/elevenlabs/tts/eleven-v3",
    "elevenlabs-turbo": "fal-ai/elevenlabs/tts/turbo-v2.5",
    "chatterbox": "fal-ai/chatterbox/text-to-speech",
}


@dataclass
class VoiceResult:
    ok: bool
    path: str | None = None
    duration_s: float = 0.0
    cost_usd: float = 0.0
    model: str = ""
    stubbed: bool = False
    error: str | None = None


def _snap_stability(v: float) -> float:
    return min((0.0, 0.5, 1.0), key=lambda x: abs(x - v))


def _stub(text: str, output_path: str, est: float, model: str) -> VoiceResult:
    dur = round(max(1.0, len(text) / 14.0), 1)          # ~14 chars/sec speaking rate
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{dur}", "-c:a", "libmp3lame", "-b:a", "128k", output_path], capture_output=True)
    return VoiceResult(ok=Path(output_path).is_file(), path=output_path, duration_s=dur,
                       cost_usd=0.0, model=model, stubbed=True)


def speak(*, text: str, output_path: str, voice_id: str = "Rachel",
          model: str = pricing.DEFAULT_TTS_MODEL, stability: float = 0.5, speed: float = 1.0,
          clone_audio: str | None = None, execute: bool = True) -> VoiceResult:
    """Render one line/narration to speech. output_path should end in .mp3."""
    text = (text or "").strip()
    if not text:
        return VoiceResult(ok=False, model=model, error="empty text")
    est = pricing.tts_cost(model, len(text))
    if _simulated_failure(model):
        return VoiceResult(ok=False, model=model, error="simulated failure")
    if not execute or not _fal_key():
        return _stub(text, output_path, est, model)

    endpoint = VOICE_ENDPOINTS.get(model, VOICE_ENDPOINTS[pricing.DEFAULT_TTS_MODEL])
    if model == "chatterbox":
        payload: dict = {"text": text}
        if clone_audio:
            payload["audio_url"] = image_ref(clone_audio)
    else:
        payload = {"text": text, "voice": voice_id or "Rachel", "stability": _snap_stability(stability)}
        if model != "elevenlabs-v3":
            payload["speed"] = max(0.7, min(speed, 1.2))
    try:
        data, _ = _poll_fal(endpoint, payload, base=FAL_BASE, timeout_s=180)
        url = (data.get("audio") or {}).get("url")
        if not url:
            return VoiceResult(ok=False, model=model, error="no audio url", )
        _download(url, Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return VoiceResult(ok=False, model=model, error=f"tts failed: {e}")
    return VoiceResult(ok=True, path=output_path, duration_s=media_duration(output_path),
                       cost_usd=est, model=model)
