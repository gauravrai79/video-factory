"""OpenRouter image generation — Gemini (Nano Banana) at ~60% of fal's price, one key.

google/gemini-2.5-flash-image is the SAME model as fal's nano-banana-2, but ~$0.039/image vs $0.10.
Character consistency works the same way: the cast's reference photos are passed as input images in
the message, and Gemini locks the generated scene to those faces.

Returns the shared GenResult so it's a drop-in alongside fal_image.generate_still.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

import requests

from . import pricing
from .fal_video import GenResult, image_ref

OR_URL = "https://openrouter.ai/api/v1/chat/completions"

# our model key -> OpenRouter model id
OR_IMAGE_MODELS = {
    "gemini-flash": "google/gemini-2.5-flash-image",
    "gemini-3-flash": "google/gemini-3.1-flash-image",
}


def _key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY")


def _save_image(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("data:"):
        b64 = url.split(",", 1)[1]
        output_path.write_bytes(base64.b64decode(b64))
    else:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        output_path.write_bytes(r.content)


def generate_still(*, prompt: str, output_path: str, reference_image_urls: list[str] | None = None,
                   model: str = "gemini-flash", safety_tolerance: int = 5,
                   aspect_ratio: str = "16:9", execute: bool = True) -> GenResult:
    """Generate a character-consistent still via OpenRouter Gemini. Reference photos are passed as
    input images so the same faces carry through. `aspect_ratio` (e.g. "9:16") is honored via Gemini's
    image_config so portrait episodes render natively vertical. safety_tolerance is accepted for
    signature parity (Gemini has its own safety; not a tunable param here)."""
    or_model = OR_IMAGE_MODELS.get(model, model)
    est = pricing.image_cost(model)
    if not execute or not _key():
        from ..finishing import stub_image
        stub_image(output_path)                      # placeholder so the pipeline is testable at $0
        return GenResult(success=True, provider="openrouter", model=or_model, cost_usd=est,
                         raw={"dry_run": True})

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for ref in (reference_image_urls or []):
        content.append({"type": "image_url", "image_url": {"url": image_ref(ref)}})
    payload = {
        "model": or_model,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect_ratio},   # native portrait/landscape (verified: honored)
        "usage": {"include": True},
    }
    headers = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
               "HTTP-Referer": "https://github.com/gauravrai79/video-factory",
               "X-Title": "AI Influencer Factory"}
    start = time.time()
    try:
        r = requests.post(OR_URL, headers=headers, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        imgs = msg.get("images") or []
        if not imgs:
            return GenResult(success=False, provider="openrouter", model=or_model,
                             error="no image returned (model may have refused)")
        url = imgs[0].get("image_url", {}).get("url") or imgs[0].get("url")
        _save_image(url, Path(output_path))
        cost = float((data.get("usage") or {}).get("cost") or est)
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        return GenResult(success=False, provider="openrouter", model=or_model,
                         error=f"openrouter image failed: {e}")
    return GenResult(success=True, provider="openrouter", model=or_model, output_path=output_path,
                     cost_usd=round(cost, 4), duration_seconds=round(time.time() - start, 2))
