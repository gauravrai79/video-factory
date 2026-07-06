"""fal.ai image-to-video client — animates a generated still into a moving shot.

Only the cheap, high-value models: Wan 2.5 ($0.05/s @480p, the default) and Kling 2.5 Turbo Pro
($0.07/s). Seedance was dropped as too expensive. A shot's base still (from fal_image) is animated
here only when the storyboard marks the shot `render_mode=video`; still+Ken Burns shots never reach
this module.

Generation runs **audio off** — music is added deterministically in finishing.

This module also hosts the shared fal queue infra (_poll_fal/_download/_fal_key/GenResult) that
fal_image reuses, so there is a single fal integration.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from . import pricing


class GenerationError(RuntimeError):
    """Raised when a generation call fails after the API path was reachable."""


@dataclass
class GenResult:
    success: bool
    provider: str
    model: str
    output_path: str | None = None
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    seed: int | None = None
    request_id: str | None = None     # fal request id — traceable against the fal usage dashboard
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _fal_key() -> str | None:
    return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")


def _simulated_failure(model: str) -> str | None:
    """Test hook: VF_SIMULATE_GEN_FAILURE=wan-2.5[,...] forces the named model(s) to fail, so the
    retry/fallback path is exercisable in a dry run with no paid call. Empty in prod."""
    names = {n.strip().lower() for n in os.environ.get("VF_SIMULATE_GEN_FAILURE", "").split(",") if n.strip()}
    if model.lower() in names:
        return f"simulated failure for {model} (VF_SIMULATE_GEN_FAILURE)"
    return None


def _poll_fal(model_path: str, payload: dict[str, Any], *, base: str, poll_s: int = 5,
              timeout_s: int = 600) -> tuple[dict[str, Any], str | None]:
    """Submit to the fal queue API and poll to completion. Returns (result JSON, request_id)."""
    key = _fal_key()
    if not key:
        raise GenerationError("FAL_KEY not set. Get one at https://fal.ai/dashboard/keys")
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}

    submit = requests.post(f"{base}/{model_path}", headers=headers, json=payload, timeout=30)
    submit.raise_for_status()
    q = submit.json()
    status_url, response_url = q["status_url"], q["response_url"]
    request_id = q.get("request_id")

    deadline = time.time() + timeout_s
    while True:
        if time.time() > deadline:
            raise GenerationError(f"fal generation timed out after {timeout_s}s")
        time.sleep(poll_s)
        st = requests.get(status_url, headers=headers, timeout=15)
        st.raise_for_status()
        status = st.json().get("status", "UNKNOWN")
        if status == "COMPLETED":
            break
        if status in ("FAILED", "CANCELLED"):
            raise GenerationError(f"fal generation {status.lower()}")

    res = requests.get(response_url, headers=headers, timeout=30)
    res.raise_for_status()
    return res.json(), request_id


def _download(url: str, output_path: Path) -> None:
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(r.content)


def image_ref(path_or_url: str) -> str:
    """Resolve an image input fal can consume. http(s) URLs pass through; a local file (our v1
    storage) is inlined as a base64 data URI (fal accepts data URIs for image inputs)."""
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    import base64
    import mimetypes
    p = Path(path_or_url)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# --------------------------------------------------------------------------- image-to-video

# model key -> (endpoint under the fal base, fal base url)
_VIDEO_ENDPOINTS = {
    "wan-2.5": ("fal-ai/wan-25-preview/image-to-video", "https://queue.fal.run"),
    "kling-2.5-turbo": ("fal-ai/kling-video/v2.5-turbo/pro/image-to-video", "https://queue.fal.run"),
}

# These models accept discrete durations; snap to the nearest allowed value (finishing trims).
_ALLOWED_DURATIONS = ("5", "10")


def _snap_duration(duration_s: float) -> str:
    return "10" if float(duration_s) >= 8 else "5"


def default_resolution() -> str:
    """480p is cheapest; override with VF_VIDEO_RESOLUTION=720p|1080p for crisper (pricier) motion."""
    return os.environ.get("VF_VIDEO_RESOLUTION", "480p")


def video_billed_cost(model: str, duration_s: float) -> float:
    """Real cost on the BILLED (snapped) duration, so the estimate matches what fal charges."""
    return pricing.video_cost(model, int(_snap_duration(duration_s)))


# --------------------------------------------------------------------------- Veo 3.1 Lite (native audio)
VEO_LITE_ENDPOINT = "fal-ai/veo3.1/lite/image-to-video"
VEO_BASE = "https://queue.fal.run"
# ($/sec) keyed by (resolution, audio_on). 720p+audio is the default; audio is included in-clip.
_VEO_LITE_RATE = {("720p", True): 0.05, ("720p", False): 0.03,
                  ("1080p", True): 0.08, ("1080p", False): 0.05}


def _veo_duration(duration_s: float) -> str:
    """Veo accepts only 4s/6s/8s clips — snap to the nearest."""
    return min(("4s", "6s", "8s"), key=lambda d: abs(int(d[:-1]) - float(duration_s)))


def veo_lite_billed_cost(duration_s: float, resolution: str = "720p", audio: bool = True) -> float:
    """Real Veo 3.1 Lite cost on the snapped (4/6/8s) duration, so estimates match fal billing."""
    secs = int(_veo_duration(duration_s)[:-1])
    return round(secs * _VEO_LITE_RATE.get((resolution, audio), 0.05), 4)


def generate_native_video(
    *,
    prompt: str,
    image_url: str,
    output_path: str,
    duration_s: float = 6.0,
    resolution: str = "720p",
    generate_audio: bool = True,
    aspect_ratio: str = "16:9",
    execute: bool = True,
) -> GenResult:
    """Veo 3.1 Lite image-to-video WITH native audio (dialogue + lip-sync + SFX generated in one pass).
    image_url is the shot's reference still (locks the character); the spoken line goes IN the prompt.
    Returns a clip that already contains its audio — no separate TTS/lip-sync needed."""
    dur = _veo_duration(duration_s)
    est = veo_lite_billed_cost(duration_s, resolution, generate_audio)
    if _simulated_failure("veo3.1-lite"):
        return GenResult(success=False, provider="fal-veo", model=VEO_LITE_ENDPOINT,
                         error=_simulated_failure("veo3.1-lite"))
    if not execute or not _fal_key():
        from ..finishing import stub_video
        stub_video(output_path, duration_s=int(dur[:-1]))     # placeholder clip (+silent audio) for $0 tests
        return GenResult(success=True, provider="fal-veo", model=VEO_LITE_ENDPOINT,
                         output_path=output_path, cost_usd=est, raw={"dry_run": True})
    payload: dict[str, Any] = {
        "prompt": prompt, "image_url": image_url, "duration": dur,
        "resolution": resolution, "generate_audio": generate_audio, "aspect_ratio": aspect_ratio,
    }
    start = time.time()
    try:
        data, request_id = _poll_fal(VEO_LITE_ENDPOINT, payload, base=VEO_BASE)
        _download(data["video"]["url"], Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return GenResult(success=False, provider="fal-veo", model=VEO_LITE_ENDPOINT,
                         error=f"veo generation failed: {e}")
    return GenResult(success=True, provider="fal-veo", model=VEO_LITE_ENDPOINT, output_path=output_path,
                     cost_usd=est, request_id=request_id,
                     duration_seconds=round(time.time() - start, 2), raw=data)


def generate_video(
    *,
    prompt: str,
    image_url: str,
    output_path: str,
    model: str = pricing.DEFAULT_VIDEO_MODEL,
    duration_s: float = 5.0,
    aspect_ratio: str = "9:16",
    resolution: str | None = None,
    execute: bool = False,
) -> GenResult:
    """Image-to-video on fal. execute=False returns a priced dry-run. The image_url is the shot's
    generated still (the character is already locked in it)."""
    endpoint, base = _VIDEO_ENDPOINTS.get(model, _VIDEO_ENDPOINTS[pricing.DEFAULT_VIDEO_MODEL])
    billed = _snap_duration(duration_s)
    est = video_billed_cost(model, duration_s)

    sim = _simulated_failure(model)
    if sim:
        return GenResult(success=False, provider="fal-video", model=endpoint, error=sim)
    if not execute:
        return GenResult(success=True, provider="fal-video", model=endpoint, cost_usd=est,
                         raw={"dry_run": True, "image_url": image_url, "billed_s": billed})

    start = time.time()
    payload: dict[str, Any] = {
        "prompt": prompt, "image_url": image_url, "duration": billed,
        "resolution": resolution or default_resolution(), "enable_prompt_expansion": False,
    }
    # model_path passed to _poll_fal is the endpoint after the base host.
    model_path = endpoint
    try:
        data, request_id = _poll_fal(model_path, payload, base=base)
        _download(data["video"]["url"], Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return GenResult(success=False, provider="fal-video", model=endpoint,
                         error=f"video generation failed: {e}")
    return GenResult(success=True, provider="fal-video", model=endpoint, output_path=output_path,
                     cost_usd=est, request_id=request_id,
                     duration_seconds=round(time.time() - start, 2), raw=data)
