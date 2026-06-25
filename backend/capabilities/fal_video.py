"""fal.ai image-to-video clients — Kling (default) and Seedance (hero-SKU fallback).

Harvested from OpenMontage tools/video/kling_video.py and seedance_video.py: the queue-submit +
poll + download logic, lifted out of the BaseTool framework into plain clients. Aggregator-routed so
the model is a config string, never a hard-coded vendor dependency.

Generation runs **audio off** by design — music is added deterministically in finishing (cheaper and
more controllable, per the SOW finishing strategy).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests


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
    """Test hook: VF_SIMULATE_GEN_FAILURE=kling[,seedance] forces the named model(s) to fail,
    so the retry/fallback path is exercisable in a dry run with no paid call. Empty in prod."""
    names = {n.strip().lower() for n in os.environ.get("VF_SIMULATE_GEN_FAILURE", "").split(",") if n.strip()}
    if model in names:
        return f"simulated failure for {model} (VF_SIMULATE_GEN_FAILURE)"
    return None


def _poll_fal(model_path: str, payload: dict[str, Any], *, base: str, poll_s: int = 5,
              timeout_s: int = 600) -> tuple[dict[str, Any], str | None]:
    """Submit to the fal queue API and poll to completion. Returns (result JSON, request_id).
    The request_id is what reconciles a job against a line in the fal usage dashboard."""
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


# --------------------------------------------------------------------------- Kling (default)

# fal Kling 2.1 image-to-video pricing = base price for the first 5s + a per-additional-second rate.
# Verified from fal.ai/models/fal-ai/kling-video/v2.1/<tier>/image-to-video (2026-06):
#   standard: $0.28 / 5s + $0.056/s   |   pro: $0.49 / 5s + $0.098/s
# Master is unverified (not used by routing); update before enabling it.
KLING_PRICING = {            # tier -> (base_first_5s_usd, per_additional_second_usd)
    "standard": (0.28, 0.056),
    "pro": (0.49, 0.098),
    "master": (0.98, 0.196),  # ESTIMATE — verify against fal before routing to master
}

# fal's Kling image-to-video accepts only these discrete values; anything else -> 422.
_KLING_DURATIONS = ("5", "10")
_KLING_ASPECTS = {"16:9": 16 / 9, "1:1": 1.0, "9:16": 9 / 16}


def _kling_duration(duration: str | int) -> str:
    """Snap the requested duration to Kling's allowed set (5 or 10s). Finishing clamps into the
    spec band afterward; 10s covers the 10-12s SOW window."""
    return "10" if int(duration) >= 8 else "5"


def _kling_aspect(aspect_ratio: str) -> str:
    """Map an arbitrary W:H (e.g. the spec's 4:3) to the nearest aspect Kling supports. Finishing
    scales + pads to the exact spec dimensions, so the generator only needs a valid frame."""
    try:
        w, h = (float(x) for x in aspect_ratio.split(":"))
        target = w / h
    except (ValueError, ZeroDivisionError):
        return "1:1"
    return min(_KLING_ASPECTS, key=lambda k: abs(_KLING_ASPECTS[k] - target))


def _kling_tier(model_variant: str) -> str:
    v = (model_variant or "").lower()
    if "master" in v:
        return "master"
    if "standard" in v:
        return "standard"
    return "pro"


def kling_cost(model_variant: str, duration_s: int) -> float:
    """Real fal cost = base (first 5s) + per-second after, priced on the BILLED duration (we clamp
    every call to 5 or 10s), so the estimate matches what fal actually charges."""
    base, per_sec = KLING_PRICING[_kling_tier(model_variant)]
    billed_s = int(_kling_duration(duration_s))   # 5 or 10 — matches the clamp applied to the call
    return round(base + per_sec * (billed_s - 5), 4)


def generate_kling(
    *,
    prompt: str,
    image_url: str,
    output_path: str,
    model_variant: str = "v2.1/standard",   # volume default tier; pin the SKU default here
    duration: str = "10",
    aspect_ratio: str = "4:3",
    execute: bool = False,
) -> GenResult:
    """Image-to-video via Kling on fal.ai. With execute=False returns a priced dry-run."""
    model_path = f"kling-video/{model_variant}/image-to-video"
    est = kling_cost(model_variant, int(duration))
    sim = _simulated_failure("kling")
    if sim:
        return GenResult(success=False, provider="kling", model=f"fal-ai/{model_path}", error=sim)
    if not execute:
        return GenResult(success=True, provider="kling", model=f"fal-ai/{model_path}",
                         cost_usd=est, raw={"dry_run": True, "image_url": image_url})

    start = time.time()
    payload = {"prompt": prompt, "duration": _kling_duration(duration),
               "aspect_ratio": _kling_aspect(aspect_ratio), "image_url": image_url}
    try:
        data, request_id = _poll_fal(model_path, payload, base="https://queue.fal.run/fal-ai")
        _download(data["video"]["url"], Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return GenResult(success=False, provider="kling", model=f"fal-ai/{model_path}",
                         error=f"Kling generation failed: {e}")
    return GenResult(success=True, provider="kling", model=f"fal-ai/{model_path}",
                     output_path=output_path, cost_usd=est, request_id=request_id,
                     duration_seconds=round(time.time() - start, 2), raw=data)


# --------------------------------------------------------------------------- Seedance (hero fallback)

SEEDANCE_RATE_USD_PER_S = {"standard": 0.3034, "fast": 0.2419}


def seedance_cost(model_variant: str, duration_s: int) -> float:
    rate = SEEDANCE_RATE_USD_PER_S.get(model_variant, SEEDANCE_RATE_USD_PER_S["standard"])
    return round(rate * duration_s, 4)


def generate_seedance(
    *,
    prompt: str,
    output_path: str,
    image_url: str | None = None,
    reference_image_urls: list[str] | None = None,   # up to 9 — garment fidelity from seller angles
    model_variant: str = "standard",
    duration: str = "10",
    aspect_ratio: str = "4:3",
    resolution: str = "720p",
    seed: int | None = None,
    execute: bool = False,
) -> GenResult:
    """Seedance 2.0 image/reference-to-video on fal.ai. Reserve for hero SKUs / difficult prints."""
    refs = list(reference_image_urls or [])
    if len(refs) > 9:
        return GenResult(success=False, provider="seedance", model="seedance-2.0",
                         error=f"Seedance accepts at most 9 reference images; got {len(refs)}")
    operation = "reference-to-video" if refs else "image-to-video"
    model_path = (f"bytedance/seedance-2.0/fast/{operation}" if model_variant == "fast"
                  else f"bytedance/seedance-2.0/{operation}")
    est = seedance_cost(model_variant, int(duration))
    sim = _simulated_failure("seedance")
    if sim:
        return GenResult(success=False, provider="seedance", model=model_path, error=sim)
    if not execute:
        return GenResult(success=True, provider="seedance", model=model_path, cost_usd=est,
                         raw={"dry_run": True, "operation": operation, "refs": len(refs)})

    start = time.time()
    payload: dict[str, Any] = {"prompt": prompt, "duration": duration,
                               "aspect_ratio": aspect_ratio, "resolution": resolution,
                               "generate_audio": False}
    if seed is not None:
        payload["seed"] = seed
    if refs:
        payload["reference_image_urls"] = refs
    elif image_url:
        payload["image_url"] = image_url
    try:
        data, request_id = _poll_fal(model_path, payload, base="https://queue.fal.run")
        _download(data["video"]["url"], Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return GenResult(success=False, provider="seedance", model=model_path,
                         error=f"Seedance generation failed: {e}")
    return GenResult(success=True, provider="seedance", model=model_path, output_path=output_path,
                     cost_usd=est, request_id=request_id,
                     duration_seconds=round(time.time() - start, 2),
                     seed=data.get("seed"), raw=data)
