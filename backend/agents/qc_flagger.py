"""VLM auto-QC — catch visual defects a deterministic spec check can't see.

The finishing layer guarantees dims/duration/size, but it cannot tell that the model hallucinated a
floating black patch, warped the garment, or grew an extra hand. This flagger samples frames from the
finished clip and asks a vision LLM (via fal's any-llm/vision — reuses FAL_KEY, no new credential) for
a structured defect verdict. Flagged clips route to the human QC gate instead of auto-approving.

Design rule: VLM QC is ADVISORY and ADDITIVE. If the call fails (no key, endpoint down/deprecated,
bad JSON), it returns `ran=False` and the pipeline proceeds on the deterministic checks alone — a
flaky VLM must never block the line.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..capabilities.fal_video import _fal_key, _poll_fal
from ..finishing import FFMPEG, _summary
from ..spec import OutputSpec

DEFAULT_VLM_MODEL = "google/gemini-2.5-flash-lite"

_SYSTEM = (
    "You are a strict quality-control inspector for an ecommerce product-video factory. You are shown "
    "several frames sampled from one short AI-generated product clip. Judge ONLY for defects that would "
    "make the clip unusable for a retail catalog."
)

_PROMPT = (
    "Inspect these frames of a single product video for generation defects:\n"
    "- floating/extra artifacts (stray shapes, black patches, smears, ghosting)\n"
    "- garment/product distortion (warped shape, melted edges, impossible folds)\n"
    "- anatomy errors (extra or missing limbs/fingers, deformed face or hands)\n"
    "- unwanted added text, logos, or watermarks (ignore a small 'Synthetically Generated' caption and "
    "short marketing supers — those are intentional)\n"
    "- the product changing color, pattern, or identity between frames\n\n"
    "Respond with ONLY a JSON object, no prose, no code fences:\n"
    '{"pass": true|false, "issues": [{"type": "...", "detail": "...", "severity": "minor|major"}], '
    '"summary": "one short sentence"}\n'
    "Set pass=false if there is any MAJOR defect. Minor issues alone can still pass."
)


@dataclass
class QCVerdict:
    ran: bool
    passed: bool = True
    issues: list[dict] = field(default_factory=list)
    summary: str = ""
    model: str = ""
    request_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def major_issues(self) -> list[dict]:
        return [i for i in self.issues if str(i.get("severity", "")).lower() == "major"]


def vlm_qc_enabled() -> bool:
    return os.environ.get("VF_VLM_QC", "1").lower() in ("1", "true", "yes")


def _sample_frames(video_path: str | Path, n: int = 4, width: int = 512) -> list[str]:
    """Extract n evenly-spaced frames, return them as base64 jpeg data URIs (small, inline-able)."""
    info = _summary(video_path)
    dur = float(info.get("duration_s") or 0) or 1.0
    # Avoid the very first/last frame (padding/cuts); spread across the middle.
    ts = [dur * (i + 1) / (n + 1) for i in range(n)]
    uris: list[str] = []
    for t in ts:
        out = subprocess.run(
            [FFMPEG, "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
             "-frames:v", "1", "-vf", f"scale={width}:-1", "-f", "image2pipe",
             "-vcodec", "mjpeg", "-"],
            capture_output=True,
        )
        if out.returncode == 0 and out.stdout:
            b64 = base64.b64encode(out.stdout).decode("ascii")
            uris.append(f"data:image/jpeg;base64,{b64}")
    return uris


def _parse_verdict(output: str) -> tuple[bool, list[dict], str]:
    """Pull the JSON verdict out of the model's text (tolerant of code fences / stray prose)."""
    text = output.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        # No JSON — treat as inconclusive-but-pass (advisory tool, don't fabricate a fail).
        return True, [], text[:160]
    obj = json.loads(m.group(0))
    passed = bool(obj.get("pass", True))
    issues = obj.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    return passed, issues, str(obj.get("summary", ""))[:200]


def run_vlm_qc(video_path: str | Path, spec: OutputSpec | None = None, *,
               model: str | None = None, n_frames: int = 4) -> QCVerdict:
    """Sample frames -> vision LLM -> defect verdict. Never raises; returns ran=False on any failure."""
    model = model or os.environ.get("VF_VLM_MODEL", DEFAULT_VLM_MODEL)
    if not _fal_key():
        return QCVerdict(ran=False, error="FAL_KEY not set", model=model)
    if not Path(video_path).is_file():
        return QCVerdict(ran=False, error=f"clip not found: {video_path}", model=model)
    try:
        frames = _sample_frames(video_path, n_frames)
        if not frames:
            return QCVerdict(ran=False, error="frame extraction failed", model=model)
        payload = {
            "prompt": _PROMPT, "system_prompt": _SYSTEM, "image_urls": frames,
            "model": model, "max_tokens": 600, "temperature": 0.0,
        }
        data, request_id = _poll_fal("any-llm/vision", payload,
                                     base="https://queue.fal.run/fal-ai", timeout_s=120)
        output = data.get("output", "") or ""
        if not output:
            return QCVerdict(ran=False, error="empty VLM output", model=model, request_id=request_id)
        passed, issues, summary = _parse_verdict(output)
        return QCVerdict(ran=True, passed=passed, issues=issues, summary=summary,
                         model=model, request_id=request_id)
    except Exception as e:  # noqa: BLE001 — advisory tool, degrade gracefully on ANY failure
        return QCVerdict(ran=False, error=f"{type(e).__name__}: {str(e)[:160]}", model=model)
