"""Script QC gate — a judge model scores the script before any money is spent on visuals.

Rubric (0-10 each, weighted to a 0-100 composite): hook (25), narrative drive incl. a VISIBLE
resolution mechanism (30), ending payoff (20), character comedy (10), virality (15). Below the
channel threshold -> the judge's actionable notes go back to the writer for a targeted revision
(max iterations), then the best version parks at the human gate regardless — the gate informs the
human, it never replaces them.

The judge also distills a per-scene INTENT contract ({purpose, must_show, mood}) that downstream
stages inject into prompts and (later) verify with vision QC — this is how a QC-passed script's
intent survives into refs and clips.

Cross-model judging: the judge defaults to a DIFFERENT model than the writer (self-grading is
inflated). Stub mode (no key) returns a passing scorecard so the pipeline stays testable at $0.
"""
from __future__ import annotations

import os
from typing import Any

from .writer import WriterResult, _chat, _key, _parse_json

WEIGHTS = {"hook": 25, "narrative": 30, "ending": 20, "comedy": 10, "virality": 15}
DEFAULT_JUDGE_MODEL = "openai/gpt-5.5"
DEFAULT_THRESHOLD = 75.0
MAX_ITERATIONS = 3          # total writer passes (1 original + up to 2 revisions)


def threshold(channel) -> float:
    t = getattr(channel, "script_qc_threshold", None) or os.environ.get("VF_SCRIPT_QC_THRESHOLD")
    try:
        return float(t)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def judge_model(channel) -> str:
    m = os.environ.get("VF_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    # never self-grade: if the judge equals the writer's model, flip to the default alternative
    writer_m = getattr(channel, "writer_model", "") or ""
    if m and writer_m and m == writer_m:
        m = "anthropic/claude-opus-4.8" if "anthropic" not in writer_m else DEFAULT_JUDGE_MODEL
    return m


def composite(breakdown: dict[str, Any]) -> float:
    """Weighted 0-100 composite from 0-10 dimension scores (missing dimensions score 0)."""
    total = 0.0
    for dim, w in WEIGHTS.items():
        try:
            v = max(0.0, min(10.0, float(breakdown.get(dim, 0) or 0)))
        except (TypeError, ValueError):
            v = 0.0
        total += v * w
    return round(total / 10.0, 1)


def _scene_digest(scenes: list[dict], cast_names: dict[str, str]) -> str:
    rows = []
    for s in scenes:
        d = next((x for x in (s.get("dialogue") or []) if isinstance(x, dict) and x.get("line")), None)
        line = f' {cast_names.get(d.get("speaker"), "?")}: "{d.get("line")}"' if d else ""
        narr = f' VO: "{s.get("narration")}"' if (s.get("narration") or "").strip() else ""
        rows.append(f'#{s.get("seq", 0) + 1} [{s.get("heading", "")}] ({s.get("beat_type", "")}) '
                    f'{s.get("motion") or s.get("action", "")}{line}{narr}')
    return "\n".join(rows)


def judge(channel, cast_chars: list, idea: dict[str, Any], scenes: list[dict]) -> WriterResult:
    """Score the script + distill per-scene intents. data = {score, breakdown, notes, intents}."""
    if not _key():
        return WriterResult(ok=True, stubbed=True, model="stub", data={
            "score": 80.0, "breakdown": {k: 8 for k in WEIGHTS}, "notes": ["stub judge"],
            "intents": [{"seq": s.get("seq", i), "purpose": "stub", "must_show": [], "mood": ""}
                        for i, s in enumerate(scenes)]})
    model = judge_model(channel)
    names = {c.character_id: c.name for c in cast_chars}
    system = (
        "You are a ruthless story editor and YouTube growth expert for an animated Hindi comedy "
        "series. You judge scripts scene-by-scene and score them honestly — a mediocre script must "
        "NOT pass. Respond with ONLY JSON.")
    user = (
        f"Series premise: {channel.premise[:600]}\n"
        f"Episode idea: {idea.get('title','')} — {idea.get('logline','')}\n\n"
        f"SCRIPT ({len(scenes)} scenes):\n{_scene_digest(scenes, names)}\n\n"
        "Score 0-10 each (be harsh; 8+ means genuinely excellent):\n"
        "- hook: do scenes 1-2 grab within the first ~5 seconds (visual + line)?\n"
        "- narrative: causality (each scene forced by the previous), rising stakes, and a VISIBLE "
        "resolution mechanism — can you point to the exact scene where the hero's plan works ON "
        "SCREEN (not narrated)?\n"
        "- ending: does the finale land a payoff + a sharp deadpan closing line?\n"
        "- comedy: is the character dynamic actually used for laughs?\n"
        "- virality: meme-able moments, shareability, thumbnail/title potential.\n"
        "Then give `notes`: the 3-6 most impactful, SPECIFIC fixes (name scene numbers; say exactly "
        "what to change). Then give `intents`: for EVERY scene, {seq, purpose (the beat's dramatic "
        "job), must_show (1-3 concrete visual elements that MUST be in frame), mood}.\n"
        'Respond ONLY: {"breakdown": {"hook": 0, "narrative": 0, "ending": 0, "comedy": 0, '
        '"virality": 0}, "notes": ["..."], "intents": [{"seq": 0, "purpose": "...", '
        '"must_show": ["..."], "mood": "..."}]}')
    try:
        text, usage = _chat(system, user, model, temperature=0.2, max_tokens=6000)
        data = _parse_json(text)
        breakdown = data.get("breakdown") or {}
        return WriterResult(ok=True, model=model, usage=usage,
                            cost_usd=float(usage.get("cost", 0.0) or 0.0),
                            data={"score": composite(breakdown), "breakdown": breakdown,
                                  "notes": data.get("notes") or [],
                                  "intents": data.get("intents") or []})
    except Exception as e:  # noqa: BLE001 — a judge outage must not block the human gate
        return WriterResult(ok=False, model=model, error=f"{type(e).__name__}: {str(e)[:200]}")


def attach_intents(scenes: list[dict], intents: list[dict]) -> None:
    """Map the judge's per-scene intents onto scenes. The judge returns them in scene order (and
    tends to 1-index its `seq` to match the '#N' digest), so when the counts match we pair BY ORDER —
    this fixes the off-by-one that attached scene N's must_show to scene N+1."""
    intents = [i for i in (intents or []) if isinstance(i, dict)]
    if intents and len(intents) == len(scenes):
        pairs = list(zip(scenes, intents))          # full coverage -> pair by order (fixes off-by-one)
    else:
        by_seq = {i.get("seq"): i for i in intents}  # partial -> exact seq match only
        pairs = [(s, by_seq.get(s.get("seq"))) for s in scenes]
    for s, i in pairs:
        if i:
            s["intent"] = {"purpose": (i.get("purpose") or "")[:200],
                           "must_show": [str(x)[:120] for x in (i.get("must_show") or [])][:3],
                           "mood": (i.get("mood") or "")[:100]}
