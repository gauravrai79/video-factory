"""Channel-concept assistant — turns a one-line idea into a full show concept.

Used by the New-channel wizard so the creator doesn't face a blank 'premise' box: from a rough
brief ("a detective dog in Mumbai who busts scams") it drafts a channel name, a tagline, a rich
premise (the engine of each episode), a suggested tone, and a couple of art-style suggestions from
the library. Stub mode (no key) returns a usable scaffold so the wizard works at $0.
"""
from __future__ import annotations

from typing import Any

from .writer import WriterResult, _chat, _key, _parse_json, default_model
from ..styles import ART_STYLES

TONES = ["comedy", "action-comedy", "thriller", "wholesome", "educational", "satire", "drama"]


def draft_concept(brief: str, *, platform: str = "youtube", model: str | None = None) -> WriterResult:
    """Return {name, tagline, premise, tone, style_ids:[..]} from a rough one-line brief."""
    brief = (brief or "").strip()
    style_ids = [s["id"] for s in ART_STYLES]
    if not _key():
        return WriterResult(ok=True, stubbed=True, model="stub", data={
            "name": (brief[:40] or "New Channel").title(),
            "tagline": "A brand-new series.",
            "premise": (brief or "A fun recurring series.") + " Each episode follows the cast through "
                       "a self-contained story with a satisfying payoff.",
            "tone": "comedy", "style_ids": ["comic_cinematic", "pixar_3d"]})
    model = model or default_model()
    style_menu = ", ".join(f"{s['id']} ({s['label']})" for s in ART_STYLES)
    system = ("You are a sharp creative director who develops bingeable short-video series concepts. "
              "Given a rough idea you return a tight, production-ready concept. Respond ONLY with JSON.")
    user = (
        f"Platform: {platform}. Rough idea: \"{brief}\".\n\n"
        "Develop it into a series concept:\n"
        "- name: a punchy, memorable channel/series name (<= 5 words)\n"
        "- tagline: one catchy line (<= 12 words)\n"
        "- premise: 3-5 sentences — the world, the recurring cast dynamic, and the ENGINE of each "
        "episode (what repeatable thing happens every time). Make it specific and funny/dramatic per "
        "the idea, not generic.\n"
        f"- tone: one of {TONES}\n"
        f"- style_ids: pick the 2-3 art styles that fit best, by id, from: {style_menu}\n"
        'Respond ONLY: {"name": "...", "tagline": "...", "premise": "...", "tone": "...", '
        '"style_ids": ["...", "..."]}')
    try:
        text, usage = _chat(system, user, model, temperature=0.9, max_tokens=1200)
        data = _parse_json(text)
        data["style_ids"] = [s for s in (data.get("style_ids") or []) if s in style_ids][:3] or ["comic_cinematic"]
        if data.get("tone") not in TONES:
            data["tone"] = "comedy"
        return WriterResult(ok=True, model=model, usage=usage,
                            cost_usd=float(usage.get("cost", 0.0) or 0.0), data=data)
    except Exception as e:  # noqa: BLE001
        return WriterResult(ok=False, model=model, error=f"{type(e).__name__}: {str(e)[:200]}")
