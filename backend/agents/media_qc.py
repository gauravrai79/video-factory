"""Vision QC — checks generated media against the scene's INTENT contract.

Gate 2 (stills): after a keyframe generates, a cheap vision model verifies the frame actually
serves the scene — must_show elements present, the right characters on-model, no compositing
artifacts, mood roughly right. Gate 3 (clips): 3 sampled frames of the Veo clip, same contract
plus "did the action happen". A failing verdict drives ONE corrective retry (reasons appended to
the prompt) and is stored on the asset for a UI badge — never a money-burning loop; after the
retry the human decides.

Stub mode (no OPENROUTER_API_KEY): passes everything at $0 so the pipeline stays testable.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from ..capabilities.fal_video import image_ref
from ..capabilities.or_image import OR_URL, _key
from ..finishing import FFMPEG, media_duration
from .writer import _parse_json

QC_MODEL = os.environ.get("VF_QC_MODEL", "google/gemini-2.5-flash-lite")
_COST_PER_CHECK = 0.002        # rough OpenRouter flash-lite vision call


@dataclass
class Verdict:
    ok: bool                   # the CHECK ran (not the content verdict)
    passed: bool = True
    score: float = 10.0        # 0-10
    reasons: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    stubbed: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "score": self.score, "reasons": self.reasons,
                "stubbed": self.stubbed, "error": self.error}


def _contract(scene: dict, present_names: list[str], *, is_clip: bool) -> str:
    intent = scene.get("intent") or {}
    must = "; ".join(intent.get("must_show") or [])
    beat = scene.get("frozen_beat") if not is_clip else (scene.get("motion") or scene.get("action"))
    lines = [
        f"Scene beat: {beat}",
        f"Characters that must be on screen: {', '.join(present_names) or 'none'}",
    ]
    if must:
        lines.append(f"MUST clearly show: {must}")
    if intent.get("mood"):
        lines.append(f"Mood: {intent['mood']}")
    checks = ("the required elements/characters are present; characters match their established "
              "look; everything shares one ground plane and consistent lighting (nothing looks "
              "pasted in); the composition serves the beat")
    if is_clip:
        checks += "; the described ACTION visibly happens across the frames"
    return "\n".join(lines) + (
        f"\n\nJudge STRICTLY whether the image(s) satisfy this: {checks}. "
        'Respond ONLY JSON: {"score": 0-10, "pass": true/false (pass = score >= 6), '
        '"reasons": ["short, specific defects — empty if clean"]}')


def _vision_check(image_paths: list[str], prompt: str) -> Verdict:
    if not _key():
        return Verdict(ok=True, stubbed=True)
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for p in image_paths[:3]:
        content.append({"type": "image_url", "image_url": {"url": image_ref(p)}})
    try:
        r = requests.post(OR_URL, json={"model": QC_MODEL,
                                        "messages": [{"role": "user", "content": content}],
                                        "max_tokens": 400},
                          headers={"Authorization": f"Bearer {_key()}",
                                   "Content-Type": "application/json"}, timeout=90)
        r.raise_for_status()
        data = _parse_json(r.json()["choices"][0]["message"]["content"] or "")
        score = max(0.0, min(10.0, float(data.get("score", 0) or 0)))
        return Verdict(ok=True, passed=bool(data.get("pass", score >= 6)), score=score,
                       reasons=[str(x)[:160] for x in (data.get("reasons") or [])][:4],
                       cost_usd=_COST_PER_CHECK)
    except Exception as e:  # noqa: BLE001 — QC outage must never block generation
        return Verdict(ok=False, error=f"{type(e).__name__}: {str(e)[:160]}")


def qc_still(image_path: str, scene: dict, present_names: list[str]) -> Verdict:
    """Gate 2 — does the keyframe serve the scene's intent?"""
    return _vision_check([image_path], _contract(scene, present_names, is_clip=False))


def qc_clip(video_path: str, scene: dict, present_names: list[str]) -> Verdict:
    """Gate 3 — sample 3 frames of the clip and check the intent + that the action happened."""
    dur = media_duration(video_path) or 4.0
    frames: list[str] = []
    td = tempfile.mkdtemp(prefix="vf_qc_")
    for i, t in enumerate((dur * 0.15, dur * 0.5, dur * 0.85)):
        fp = str(Path(td) / f"f{i}.jpg")
        p = subprocess.run([FFMPEG, "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
                            "-frames:v", "1", "-q:v", "4", fp], capture_output=True, text=True)
        if p.returncode == 0 and Path(fp).is_file():
            frames.append(fp)
    if not frames:
        return Verdict(ok=False, error="could not sample frames")
    v = _vision_check(frames, _contract(scene, present_names, is_clip=True))
    for f in frames:
        Path(f).unlink(missing_ok=True)
    return v


def corrective_suffix(reasons: list[str]) -> str:
    """Appended to the generation prompt on the single corrective retry."""
    fixes = "; ".join(reasons[:3]) if reasons else "match the scene description exactly"
    return f" IMPORTANT — the previous attempt failed review, fix these issues: {fixes}."
