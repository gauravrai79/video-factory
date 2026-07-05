"""fal.ai image client — character-consistent stills.

Generates the base still for a shot with the character's reference images injected so the same
face/body carries through (Nano Banana holds up to 5 people consistent with no fine-tuning). Also
mints a reference sheet for a brand-new, text-described character (e.g. a glamour persona) by
generating one base look and then editing variations from it to stay consistent.

`safety_tolerance` (1=strict .. 6=permissive) is forwarded so glamour/suggestive personas aren't
false-flagged. Synthetic personas only — never a real person's likeness (see project constraints).

Reuses the queue-poll + download infra and GenResult from fal_video (one fal integration).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from . import pricing
from .fal_video import (GenerationError, GenResult, _download, _fal_key, _poll_fal,
                        _simulated_failure, image_ref)

FAL_BASE = "https://queue.fal.run/fal-ai"

# model key -> (base_endpoint, edit_endpoint, supports_safety_tolerance)
_IMAGE_ENDPOINTS = {
    "nano-banana-2": ("nano-banana-2", "nano-banana-2/edit", False),
    "nano-banana-pro": ("nano-banana-pro", "nano-banana-pro/edit", False),
    "flux-kontext": ("flux-pro/kontext", "flux-pro/kontext", True),
    "flux-dev": ("flux/dev", "flux/dev", False),          # text-to-image, good cheap default
    "flux-schnell": ("flux/schnell", "flux/schnell", False),
}


def _endpoint(model: str, has_refs: bool) -> tuple[str, bool]:
    base, edit, safety = _IMAGE_ENDPOINTS.get(model, _IMAGE_ENDPOINTS[pricing.DEFAULT_IMAGE_MODEL])
    return (edit if has_refs else base), safety


def generate_still(
    *,
    prompt: str,
    output_path: str,
    reference_image_urls: list[str] | None = None,   # character "DNA" — kept consistent
    model: str = pricing.DEFAULT_IMAGE_MODEL,
    safety_tolerance: int = 5,
    execute: bool = False,
) -> GenResult:
    """Generate one character-consistent still. execute=False returns a priced dry-run."""
    refs = list(reference_image_urls or [])
    model_path, supports_safety = _endpoint(model, bool(refs))
    est = pricing.image_cost(model)

    sim = _simulated_failure(model)
    if sim:
        return GenResult(success=False, provider="fal-image", model=f"fal-ai/{model_path}", error=sim)
    if not execute or not _fal_key():
        from ..finishing import stub_image
        stub_image(output_path)                      # placeholder so the pipeline is testable at $0
        return GenResult(success=True, provider="fal-image", model=f"fal-ai/{model_path}",
                         cost_usd=est, raw={"dry_run": True, "refs": len(refs)})

    payload: dict[str, Any] = {"prompt": prompt, "num_images": 1}
    if refs:
        payload["image_urls"] = [image_ref(r) for r in refs]   # reference/edit conditioning
    if supports_safety:
        payload["safety_tolerance"] = str(max(1, min(safety_tolerance, 6)))

    start = time.time()
    try:
        data, request_id = _poll_fal(model_path, payload, base=FAL_BASE, timeout_s=180)
        url = (data.get("images") or [{}])[0].get("url")
        if not url:
            return GenResult(success=False, provider="fal-image", model=f"fal-ai/{model_path}",
                             error="no image url in response", raw=data)
        _download(url, Path(output_path))
    except (requests.RequestException, GenerationError, KeyError) as e:
        return GenResult(success=False, provider="fal-image", model=f"fal-ai/{model_path}",
                         error=f"image generation failed: {e}")
    return GenResult(success=True, provider="fal-image", model=f"fal-ai/{model_path}",
                     output_path=output_path, cost_usd=est, request_id=request_id,
                     duration_seconds=round(time.time() - start, 2), raw=data)


def mint_reference_sheet(
    *,
    dna_prompt: str,
    out_dir: str,
    slug: str,
    n: int = 4,
    model: str = pricing.DEFAULT_IMAGE_MODEL,
    safety_tolerance: int = 5,
    execute: bool = False,
) -> tuple[list[str], float, list[str]]:
    """Mint a character reference sheet from a text description. Generates one base look, then edits
    consistent variations (different angle/expression) from it. Returns (image_paths, total_cost,
    errors). With execute=False, returns the would-be paths/cost without spending."""
    angles = ["front portrait, neutral expression",
              "three-quarter view, soft smile",
              "full body, standing",
              "side profile",
              "candid, looking away",
              "close-up face detail"]
    dest = Path(out_dir) / "characters" / slug / "reference"
    paths: list[str] = []
    errors: list[str] = []
    total = 0.0

    base_path = str(dest / "ref_00.png")
    base_prompt = f"{dna_prompt}. {angles[0]}. Photorealistic, editorial quality, plain background."
    base = generate_still(prompt=base_prompt, output_path=base_path, model=model,
                          safety_tolerance=safety_tolerance, execute=execute)
    total += base.cost_usd
    if base.success and (not execute or base.output_path):
        paths.append(base_path)
    elif base.error:
        errors.append(base.error)

    # Variations conditioned on the base for identity consistency.
    refs = [base_path] if (execute and base.success) else []
    for i in range(1, min(n, len(angles))):
        p = str(dest / f"ref_{i:02d}.png")
        prompt = f"{dna_prompt}. {angles[i]}. Same person, identical face. Plain background."
        r = generate_still(prompt=prompt, output_path=p, reference_image_urls=refs,
                           model=model, safety_tolerance=safety_tolerance, execute=execute)
        total += r.cost_usd
        if r.success and (not execute or r.output_path):
            paths.append(p)
        elif r.error:
            errors.append(r.error)
    return paths, round(total, 4), errors
