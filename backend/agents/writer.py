"""Writers' room — turns a channel + cast into episode ideas, then a scene-by-scene script.

Provider-agnostic via OpenRouter: one OpenAI-compatible endpoint + one key (OPENROUTER_API_KEY)
gives every model (Claude, Gemini, GPT). The channel picks the model as a plain OpenRouter id
(e.g. "anthropic/claude-sonnet-4"); default via VF_WRITER_MODEL.

Each character's Personality DNA (personality_prompt()) is assembled into the system prompt so the
actor writes/speaks consistently, and in a multi-hander both bibles are present so the relationship
dynamic stays true.

Graceful: with no key it returns a deterministic STUB so the whole gated flow + UI are testable with
zero spend. Text-only stage — cheap.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY")


def default_model() -> str:
    return os.environ.get("VF_WRITER_MODEL", "anthropic/claude-sonnet-4")


@dataclass
class WriterResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    stubbed: bool = False
    error: str | None = None


# --------------------------------------------------------------------------- OpenRouter call

def _chat(system: str, user: str, model: str, *, temperature: float = 0.85,
          max_tokens: int = 3000, reasoning_effort: str | None = None) -> tuple[str, dict[str, Any]]:
    """One OpenRouter chat completion. Returns (text, usage). Raises on transport/API failure."""
    headers = {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gauravrai79/video-factory",
        "X-Title": "AI Influencer Factory",
    }
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "usage": {"include": True},
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}   # OpenRouter reasoning control
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    text = (data["choices"][0]["message"]["content"] or "").strip()
    usage = data.get("usage", {}) or {}
    return text, usage


def _parse_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction: strip reasoning-model <think> blocks + code fences, then take the
    outermost JSON object."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"```(?:json)?|```", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


# --------------------------------------------------------------------------- prompt assembly

def _cast_block(cast_chars: list) -> str:
    lines = []
    for c in cast_chars:
        bible = c.personality_prompt() or f"Character: {c.name}."
        lines.append(bible)
    return "\n\n".join(lines)


def _channel_system(channel, cast_chars: list) -> str:
    fmt = "long-form narrative" if not channel.is_short() else "short-form"
    lang = (getattr(channel, "language", "") or "English").strip()
    world = (getattr(channel, "world", "") or "").strip()
    parts = [
        f"You are the writers' room for a {channel.platform} {fmt} series titled \"{channel.name}\".",
        f"Premise: {channel.premise}" if channel.premise else "",
        f"Setting / world: {world}" if world else "",
        f"Visual/tone style: {channel.art_style}." if channel.art_style else "",
        (f"LANGUAGE: write ALL spoken content — every dialogue line AND every narration/VO line — "
         f"in {lang}. Keep the whole episode in {lang}; never narrate in English over {lang} dialogue."
         if lang and lang.lower() != "english" else ""),
        "",
        "CAST (keep each character's voice, traits, and relationships perfectly consistent):",
        _cast_block(cast_chars),
    ]
    return "\n".join(p for p in parts if p != "")


# --------------------------------------------------------------------------- ideate

# The default multi-model ideation panel: each model proposes ideas concurrently so you can pick the
# best across models. (label, OpenRouter model id, reasoning effort). Override via VF_IDEA_PANEL
# (comma-separated model ids) if you want a different lineup.
DEFAULT_IDEA_PANEL = [
    ("Opus 4.8", "anthropic/claude-opus-4.8", None),
    ("GPT-5.5 high", "openai/gpt-5.5", "high"),
    ("DeepSeek V4 Pro", "deepseek/deepseek-v4-pro", None),
    ("GLM 5.2", "z-ai/glm-5.2", None),
]


def idea_panel() -> list[tuple[str, str, str | None]]:
    override = os.environ.get("VF_IDEA_PANEL", "").strip()
    if override:
        return [(mid.split("/")[-1], mid.strip(), None) for mid in override.split(",") if mid.strip()]
    return DEFAULT_IDEA_PANEL


def ideate_panel(channel, cast_chars: list, *, brief: str | None = None,
                 recent_titles: list[str] | None = None, panel: list | None = None,
                 n_per_model: int = 1) -> WriterResult:
    """Run every model in the panel concurrently; return all their ideas, each tagged with its
    source model. Failures are skipped so a flaky model doesn't block the others."""
    panel = panel or idea_panel()
    if not _key():
        ideas = []
        for label, mid, _ in panel:
            for it in _stub_ideate(channel, n_per_model, brief).data["ideas"][:n_per_model]:
                ideas.append({**it, "model": mid, "model_label": label})
        return WriterResult(ok=True, data={"ideas": ideas}, model="panel", stubbed=True)

    import concurrent.futures as cf

    def _one(item):
        label, mid, eff = item
        r = ideate(channel, cast_chars, brief=brief, recent_titles=recent_titles,
                   n=n_per_model, model=mid, reasoning_effort=eff)
        return label, mid, r

    ideas, cost, failed = [], 0.0, []
    with cf.ThreadPoolExecutor(max_workers=max(1, len(panel))) as ex:
        for label, mid, r in ex.map(_one, panel):
            if r.ok and r.data.get("ideas"):
                cost += float(r.cost_usd or 0.0)
                for it in r.data["ideas"][:n_per_model]:
                    ideas.append({**it, "model": mid, "model_label": label})
            else:
                failed.append(label)
    if not ideas:
        return WriterResult(ok=False, model="panel", error=f"all models failed: {', '.join(failed)}")
    return WriterResult(ok=True, data={"ideas": ideas, "failed": failed}, model="panel", cost_usd=round(cost, 4))


def ideate(channel, cast_chars: list, *, recent_titles: list[str] | None = None,
           brief: str | None = None, n: int = 4, model: str | None = None,
           reasoning_effort: str | None = None) -> WriterResult:
    """Propose n distinct episode concepts from the channel bible, optionally steered by `brief`."""
    model = model or channel.writer_model or default_model()
    recent = recent_titles or []
    if not _key():
        return _stub_ideate(channel, n, brief)

    system = _channel_system(channel, cast_chars)
    avoid = f" Avoid repeating these existing episodes: {', '.join(recent)}." if recent else ""
    steer = f"\nThe creator's steer for these ideas (build the concepts around this): {brief}\n" if brief else ""
    user = (
        f"Propose {n} distinct, bingeable episode concepts for this series.{avoid}{steer}\n"
        "Each concept: a punchy title, a one-sentence logline, a hook (the opening beat that grabs "
        "attention), and 3-5 story beats.\n"
        "Respond with ONLY JSON, no prose:\n"
        '{"ideas": [{"title": "...", "logline": "...", "hook": "...", "beats": ["...", "..."]}]}'
    )
    try:
        text, usage = _chat(system, user, model, max_tokens=1800, reasoning_effort=reasoning_effort)
        data = _parse_json(text)
        ideas = data.get("ideas") or []
        if not isinstance(ideas, list) or not ideas:
            raise ValueError("no ideas returned")
        return WriterResult(ok=True, data={"ideas": ideas}, model=model, usage=usage,
                            cost_usd=float(usage.get("cost", 0.0) or 0.0))
    except Exception as e:  # noqa: BLE001 — degrade to stub so the gate flow never hard-blocks
        return WriterResult(ok=False, model=model, error=f"{type(e).__name__}: {str(e)[:200]}")


# --------------------------------------------------------------------------- script

_SHOT_RULES = (
    "Assign every scene a shot_type — pick the CHEAPEST that sells the beat (this controls cost):\n"
    "  - \"broll\": atmosphere / establishing / insert with NO main character on screen (cheapest).\n"
    "  - \"still_kenburns\": narration-over or a held reaction; a still with slow pan/zoom (cheap).\n"
    "  - \"lipsync_still\": a character TALKING on camera (a still animated to the voice) — use for "
    "most dialogue (cheap).\n"
    "  - \"hero_video\": a character physically ACTING/MOVING; reserve these — at most {budget} per "
    "episode (expensive).\n"
    "At most ONE speaking character per scene (cut between characters across scenes) — never two "
    "people talking in the same shot.\n"
)


def script(channel, cast_chars: list, idea: dict[str, Any], *, model: str | None = None) -> WriterResult:
    """Expand an approved idea into a structured scene-by-scene script."""
    model = model or channel.writer_model or default_model()
    n = int(channel.target_scene_count or (3 if channel.is_short() else 16))
    if not _key():
        return _stub_script(channel, cast_chars, idea, n)

    system = _channel_system(channel, cast_chars)
    cast_names = ", ".join(f"{c.name} ({c.character_id})" for c in cast_chars)
    user = (
        f"Write the full script for this episode:\n"
        f"Title: {idea.get('title','')}\nLogline: {idea.get('logline','')}\n"
        f"Hook: {idea.get('hook','')}\n\n"
        f"Produce EXACTLY {n} scenes totalling ~{channel.target_duration_s}s. Cast character_ids: {cast_names}.\n"
        + _SHOT_RULES.format(budget=channel.video_budget) +
        "Write each scene like a film SHOT, not a summary. The `action` field MUST be a vivid, "
        "self-contained cinematic description a video model can render directly — for THIS beat: the "
        "environment detail, where each character is and what they are physically doing (blocking), "
        "their expression and body language, key props, and the lighting/mood. Do NOT re-describe a "
        "character's fixed appearance (it is locked separately) — describe what they DO, where they "
        "are, and how they feel. Make `camera` specific: shot size + angle + movement "
        "(e.g. 'low-angle medium two-shot, slow push-in').\n"
        "Density target for `action` (adapt per beat): 'At a neon-lit chai stall in light rain, Zruv "
        "crouches low with a worried frown while Jango sits alert at ground level beside him, both "
        "washed in warm neon; steam curls from a kettle; wet reflections shimmer on the wet pavement.'\n"
        "For each scene give: heading (location - time of day), action (the rich shot above), camera, "
        "cast_present (character_ids on screen), dialogue (list of {speaker, line, delivery}), narration "
        "(VO text, may be empty), shot_type, duration_s.\n"
        f"Every `line` and `narration` value MUST be written in {getattr(channel, 'language', 'English')}.\n"
        "Respond with ONLY JSON, no prose:\n"
        '{"scenes": [{"heading": "...", "action": "...", "camera": "...", "cast_present": ["id"], '
        '"dialogue": [{"speaker": "id", "line": "...", "delivery": "..."}], "narration": "...", '
        '"shot_type": "lipsync_still", "duration_s": 6}]}'
    )
    try:
        text, usage = _chat(system, user, model, temperature=0.8, max_tokens=10000)
        data = _parse_json(text)
        scenes = data.get("scenes") or []
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("no scenes returned")
        scenes = _normalize_scenes(scenes, channel)
        return WriterResult(ok=True, data={"scenes": scenes}, model=model, usage=usage,
                            cost_usd=float(usage.get("cost", 0.0) or 0.0))
    except Exception as e:  # noqa: BLE001
        return WriterResult(ok=False, model=model, error=f"{type(e).__name__}: {str(e)[:200]}")


def _single_speaker(dialogue: list) -> list:
    """Keep only the first speaker's lines in a scene. Multi-speaker lip-sync in one shot is
    unreliable, so each shot features at most one talking character (cut between characters
    across shots), which keeps every talking-still/hero clip clean to sync."""
    if not isinstance(dialogue, list) or not dialogue:
        return dialogue or []
    first, kept = None, []
    for d in dialogue:
        if not isinstance(d, dict):
            continue
        if first is None:
            first = d.get("speaker")
        if d.get("speaker") == first:
            kept.append(d)
    return kept


def _normalize_scenes(scenes: list[dict], channel) -> list[dict]:
    """Clamp shot types + enforce the video budget (excess hero_video -> lipsync_still) and one
    speaker per shot."""
    valid = {"broll", "still_kenburns", "lipsync_still", "hero_video"}
    videos = 0
    out = []
    for i, s in enumerate(scenes):
        st = s.get("shot_type") if s.get("shot_type") in valid else "still_kenburns"
        if st == "hero_video":
            if videos >= channel.video_budget:
                st = "lipsync_still"
            else:
                videos += 1
        out.append({
            "seq": i,
            "heading": s.get("heading", ""),
            "action": s.get("action", ""),
            "camera": s.get("camera", ""),
            "cast_present": s.get("cast_present") or [],
            "dialogue": _single_speaker(s.get("dialogue") or []),
            "narration": s.get("narration", ""),
            "shot_type": st,
            "duration_s": float(s.get("duration_s", 5) or 5),
            "reference_image": {}, "clip": {}, "voice_clips": [], "status": "pending",
        })
    return out


# --------------------------------------------------------------------------- deterministic stubs

def _stub_ideate(channel, n: int, brief: str | None = None) -> WriterResult:
    base = brief or channel.premise or channel.name
    ideas = [{
        "title": f"{channel.name}: Case #{i + 1}" if not channel.is_short() else f"{channel.name} — Ep {i + 1}",
        "logline": f"A fresh take on: {base}",
        "hook": "Open on a striking, in-world moment that raises a question.",
        "beats": ["Setup / status quo", "Inciting incident", "Investigation / build", "Twist", "Resolution"],
    } for i in range(n)]
    return WriterResult(ok=True, data={"ideas": ideas}, model="stub", stubbed=True)


def _stub_script(channel, cast_chars: list, idea: dict[str, Any], n: int) -> WriterResult:
    ids = [c.character_id for c in cast_chars]
    lead = ids[0] if ids else None
    cycle = ["still_kenburns", "lipsync_still", "broll", "hero_video"]
    raw = []
    for i in range(n):
        st = cycle[i % len(cycle)]
        raw.append({
            "heading": f"SCENE {i + 1}",
            "action": f"Beat {i + 1} of \"{idea.get('title','the episode')}\".",
            "camera": "slow push-in" if st != "broll" else "static establishing",
            "cast_present": [] if st == "broll" else ([lead] if lead else []),
            "dialogue": ([] if st in ("broll", "still_kenburns") or not lead
                         else [{"speaker": lead, "line": f"Line for beat {i + 1}.", "delivery": "in-character"}]),
            "narration": "Narration bridges the beat." if st in ("broll", "still_kenburns") else "",
            "shot_type": st,
            "duration_s": round((channel.target_duration_s or 60) / n, 1),
        })
    return WriterResult(ok=True, data={"scenes": _normalize_scenes(raw, channel)},
                        model="stub", stubbed=True)
