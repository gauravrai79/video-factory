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
        f"Tone: {channel.tone} — keep every episode in this register." if getattr(channel, "tone", "") else "",
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
    "Assign every scene a shot_type. If a CHARACTER is on screen the shot MUST have real motion — "
    "never a static still. Give the episode a healthy MIX of dynamic action and talking:\n"
    "  - \"hero_video\": a character in DYNAMIC ACTION or physical movement — running, chasing, "
    "fighting, a big physical gag, a dramatic reveal or camera move. Full generative motion. USE THIS "
    "for the episode's action/spectacle beats EVEN IF the character also shouts a short line. Aim to "
    "use it {budget} times per episode — don't make the whole episode talking heads.\n"
    "  - \"lipsync_still\": a character mainly TALKING (a conversation, reaction, or exposition line) "
    "— animated into a moving, lip-synced talking performance. Use when DIALOGUE carries the beat.\n"
    "  - \"broll\": establishing / atmosphere / insert with NO character on screen — a cheap still "
    "pan. Use ONLY when no character is present.\n"
    "  - \"still_kenburns\": a held object/detail insert with NO character — cheap still pan.\n"
    "For a character scene: choose hero_video when MOTION/action carries it, lipsync_still when "
    "DIALOGUE carries it. HARD RULE: cast_present non-empty -> hero_video or lipsync_still, never a "
    "still. Stills are for character-free shots only.\n"
    "At most ONE speaking character per scene (cut between characters across scenes) — never two "
    "people talking in the same shot.\n"
)


def _story_rules(n: int, *, hook_s: int = 5, pacing: str = "balanced", duration_s: int = 120) -> str:
    a1 = max(2, round(n * 0.2)); a2 = max(3, round(n * 0.4)); a3 = max(2, round(n * 0.25))
    pace = {"dialogue": "Lean on character dialogue and reactions; fewer big action set-pieces.",
            "action": "Lean on visual gags, motion and physical comedy; keep talking terse.",
            "balanced": "Balance dialogue beats with visual action."}.get(pacing, "")
    hookline = (f"- HOOK (scene 1): grab within the FIRST {hook_s} SECONDS — open ON the gag/problem, "
                f"no establishing ramp. " + ("For a short vertical video the very first frame must be "
                "arresting and the payoff must land fast.\n" if hook_s <= 2 else "\n"))
    return (
        f"STORY STRUCTURE (mandatory — a weak plot gets rejected by QC). Total ~{duration_s}s across "
        f"{n} scenes. {pace}\n"
        + hookline +
        f"- ACT 1 (~{a1} scenes): setup + inciting incident — the scam/injustice hurts a real person "
        f"we care about.\n"
        f"- ACT 2 (~{a2} scenes): investigation + escalation — Jango works the case (observation, "
        f"R.A.W. dogs, Champa's cats), Zruv makes it comically worse; stakes RISE every scene.\n"
        f"- ACT 3 (~{a3} scenes): the jugaad plan + the TRAP — the resolution MECHANISM must be "
        f"VISIBLE ON SCREEN: the audience must SEE exactly how the trick catches the villain (a "
        f"specific scene where the plan clicks), never resolved by narration or off-screen.\n"
        f"- PAYOFF (final scenes): public comeuppance, Zruv obliviously takes the credit, and the "
        f"episode ENDS on Jango's sharp deadpan seekh — a quotable button, not an explanation.\n"
        f"Every scene must ADVANCE the plot (cut anything that only decorates). Callbacks and "
        f"running gags encouraged.\n"
        f"DIALOGUE: every line MUST be under 80 characters (speakable in ~6s) — split longer "
        f"thoughts across scenes.\n")


def script(channel, cast_chars: list, idea: dict[str, Any], *, model: str | None = None,
           cfg: dict[str, Any] | None = None) -> WriterResult:
    """Expand an approved idea into a structured scene-by-scene script. `cfg` (the episode Setup
    config) overrides channel defaults for THIS video: scene_count, duration, language, pacing,
    hook timing (portrait shorts hook faster)."""
    cfg = cfg or {}
    model = model or channel.writer_model or default_model()
    n = int(cfg.get("scene_count") or channel.target_scene_count or (3 if channel.is_short() else 16))
    duration = int(cfg.get("duration_s") or channel.target_duration_s or 120)
    language = cfg.get("language") or getattr(channel, "language", "English")
    hook_s = 2 if cfg.get("layout") == "portrait" else 5
    pacing = cfg.get("pacing") or "balanced"
    if not _key():
        return _stub_script(channel, cast_chars, idea, n)

    system = _channel_system(channel, cast_chars)
    cast_names = ", ".join(f"{c.name} ({c.character_id})" for c in cast_chars)
    user = (
        f"Write the full script for this episode:\n"
        f"Title: {idea.get('title','')}\nLogline: {idea.get('logline','')}\n"
        f"Hook: {idea.get('hook','')}\n\n"
        f"Produce EXACTLY {n} scenes totalling ~{duration}s. Cast character_ids: {cast_names}.\n"
        + _story_rules(n, hook_s=hook_s, pacing=pacing, duration_s=duration)
        + _SHOT_RULES.format(budget=channel.video_budget) +
        "Write each scene like a film SHOT, not a summary, split into TWO fields. Both must be RICH "
        "and SPECIFIC — 2-3 full sentences EACH, naming the exact props, signboards, expressions, "
        "background detail and the comic beat a reader could vividly picture. A single terse clause "
        "is a REJECT (thin scenes score low and generate generic visuals):\n"
        "  - `frozen_beat`: the KEYFRAME — one STILL, STABLE instant, everything at rest or in a "
        "held pose. Blocking (where each character is, ~scale in frame), expression, eyelines "
        "(who looks at what), key props ON THE GROUND or held, one continuous ground plane, a scale "
        "anchor for any hole/large object (e.g. 'pothole roughly the width of a scooter wheel'), and "
        "an agent for any vehicle (a rider on the scooter, never an empty moving vehicle). "
        "STRICTLY NO motion words (no mid-air, flying, spilling, tumbling, launching, 'about to').\n"
        "  - `motion`: ALL the movement for the video model — what moves, how, in what order, plus "
        "physics and comic timing. Every motion word lives HERE.\n"
        "DENSITY EXAMPLE (write at THIS level of detail, in the episode's language):\n"
        "  frozen_beat: 'Two rival hunger-strike tents under a faded blue tarp: on the left a real, "
        "gaunt student sits cross-legged with cracked lips and a hand-painted placard; on the right a "
        "well-fed hired actor lounges on a cushion, a half-eaten samosa hidden behind a water bottle, "
        "an oily orange stain on his crisp white kurta. Jango sits low in the foreground, ears up.'\n"
        "  motion: 'Jango's head swivels slowly from the real student to the actor and locks onto the "
        "samosa stain; his nose twitches twice, one ear flicks, and his eyes narrow into a deadpan "
        "squint as a tiny knowing glint crosses his face.'\n"
        "Do NOT re-describe a character's fixed appearance (it is locked separately) — describe what "
        "they DO, where they are, and how they feel. Make `camera` specific: shot size + angle + "
        "movement (movement belongs to the video stage).\n"
        "Keep the main characters ON SCREEN and acting in MOST scenes — use character-free b-roll "
        "sparingly (at most ~3-4 establishing/insert shots in the whole episode).\n"
        "Also give per scene: `location_id` (stable slug per location, e.g. 'market_street_A' — same "
        "value whenever the story returns to that place), `time_jump` (true only if time skips since "
        "the previous scene), `beat_type` (one of: establishing, dialogue, reveal, punchline, chase, "
        "impact_gag, zruv_entrance, neutral).\n"
        "For each scene give: heading (location - time of day), frozen_beat, motion, camera, "
        "cast_present (character_ids on screen — EVERY character visible in the shot), dialogue "
        "(list of {speaker, line, delivery}), narration (VO text, may be empty), shot_type, "
        "duration_s, location_id, time_jump, beat_type.\n"
        f"Every `line` and `narration` value MUST be written in {language}.\n"
        "Respond with ONLY JSON, no prose:\n"
        '{"scenes": [{"heading": "...", "frozen_beat": "...", "motion": "...", "camera": "...", '
        '"cast_present": ["id"], "dialogue": [{"speaker": "id", "line": "...", "delivery": "..."}], '
        '"narration": "...", "shot_type": "lipsync_still", "duration_s": 6, '
        '"location_id": "market_street_A", "time_jump": false, "beat_type": "dialogue"}]}'
    )
    try:
        text, usage = _chat(system, user, model, temperature=0.8, max_tokens=10000)
        data = _parse_json(text)
        scenes = data.get("scenes") or []
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("no scenes returned")
        scenes = _normalize_scenes(scenes, channel, cast_chars)
        return WriterResult(ok=True, data={"scenes": scenes}, model=model, usage=usage,
                            cost_usd=float(usage.get("cost", 0.0) or 0.0))
    except Exception as e:  # noqa: BLE001
        return WriterResult(ok=False, model=model, error=f"{type(e).__name__}: {str(e)[:200]}")


def revise_script(channel, cast_chars: list, idea: dict[str, Any], scenes: list[dict],
                  notes: list[str], *, model: str | None = None) -> WriterResult:
    """Targeted revision: rewrite the script applying the QC judge's notes (keep what works)."""
    model = model or channel.writer_model or default_model()
    if not _key():
        return WriterResult(ok=True, data={"scenes": scenes}, model="stub", stubbed=True)
    import json as _json
    n = len(scenes)
    system = _channel_system(channel, cast_chars)
    slim = [{k: s.get(k) for k in ("seq", "heading", "frozen_beat", "motion", "camera",
                                   "cast_present", "dialogue", "narration", "shot_type",
                                   "duration_s", "location_id", "time_jump", "beat_type")}
            for s in scenes]
    user = (
        f"Here is the current draft script ({n} scenes) as JSON:\n{_json.dumps(slim, ensure_ascii=False)}\n\n"
        "A story editor rejected it with these notes — fix ALL of them while keeping what already "
        "works (do not rewrite scenes the notes don't touch unless required for causality):\n- "
        + "\n- ".join(str(x) for x in notes[:8]) + "\n\n"
        + _story_rules(n) + _SHOT_RULES.format(budget=channel.video_budget) +
        f"Keep EXACTLY {n} scenes and the same JSON schema as the draft. Every `line` and "
        f"`narration` in {getattr(channel, 'language', 'English')}.\n"
        "Respond with ONLY JSON: {\"scenes\": [...]}")
    try:
        text, usage = _chat(system, user, model, temperature=0.6, max_tokens=10000)
        data = _parse_json(text)
        out = data.get("scenes") or []
        if not isinstance(out, list) or not out:
            raise ValueError("no scenes returned")
        return WriterResult(ok=True, data={"scenes": _normalize_scenes(out, channel, cast_chars)},
                            model=model, usage=usage, cost_usd=float(usage.get("cost", 0.0) or 0.0))
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


# Motion language that must NEVER reach a KEYFRAME (still-image) prompt — a still model can't hold
# a mid-air instant and collapses it (empty scooter, grounded tiffin, pasted-in characters). These
# words belong only in the video/motion prompt.
LINT_BANNED_IN_KEYFRAME = (
    "mid-air", "in the air", "hangs", "hanging", "airborne", "flying", "tumbling", "tumbles",
    "spilling", "spills", "launches", "launching", "popping", "pops loose", "springing",
    "slow-motion", "slow motion", "just as", "in the act of", "about to", "mid-", "tracking shot",
    "camera pans", "camera tracks", "motion blur", "streaking", "bursting", "leaps", "leaping",
    "jumps", "jumping", "flies", "swinging", "swings",
)


def lint_keyframe(text: str) -> list[str]:
    """Banned motion tokens found in a keyframe prompt (empty list = clean)."""
    low = (text or "").lower()
    return [t for t in LINT_BANNED_IN_KEYFRAME if t in low]


def freeze_beat(text: str) -> str:
    """Deterministic fallback: drop the clauses that carry motion language so the remainder reads as
    a stable, at-rest instant. Used when the writer didn't supply a clean `frozen_beat`. Splits on
    clause boundaries; if everything is motion, returns the first clause as-is (lint then just logs)."""
    import re
    clauses = re.split(r"(?<=[;.])\s+|,\s+(?=\w)", (text or "").strip())
    kept = [c for c in clauses if not lint_keyframe(c)]
    return (", ".join(kept) if kept else (clauses[0] if clauses else "")).strip(" ,;.")


def _location_id(heading: str) -> str:
    """Stable location key derived from a heading like 'Roadside - Continuous' -> 'roadside'."""
    loc = (heading or "").split(" - ")[0].split("-")[0]
    return "".join(ch if ch.isalnum() else "_" for ch in loc.strip().lower()).strip("_") or "unknown"


BEAT_TYPES = ("establishing", "dialogue", "reveal", "punchline", "chase", "impact_gag",
              "zruv_entrance", "neutral")


def _normalize_scenes(scenes: list[dict], channel, cast_chars: list | None = None) -> list[dict]:
    """Clamp shot types + video budget, one speaker per shot, cast auto-fix (anyone named in the
    action MUST be in cast_present or their reference photos never reach the model — the identity-
    drift bug), max 3 characters per shot, and the keyframe/video split fields with lint-safe
    fallbacks."""
    valid = {"broll", "still_kenburns", "lipsync_still", "hero_video"}
    name_to_id = {c.name.strip().lower(): c.character_id for c in (cast_chars or [])}
    videos = 0
    out = []
    for i, s in enumerate(scenes):
        st = s.get("shot_type") if s.get("shot_type") in valid else "still_kenburns"
        action = (s.get("action") or "").strip()
        motion = (s.get("motion") or "").strip() or action
        action = action or motion                # UI + legacy paths read `action`
        frozen = (s.get("frozen_beat") or "").strip()
        if not frozen or lint_keyframe(frozen):
            frozen = freeze_beat(frozen or action)
        cast = list(s.get("cast_present") or [])
        # Cast auto-fix: a character described in the shot text but absent from cast_present would
        # render from TEXT ONLY (no reference photos) and drift. Add them.
        blob = f"{action} {motion} {frozen}".lower()
        for nm, cid in name_to_id.items():
            if nm in blob and cid not in cast:
                cast.append(cid)
        cast = cast[:3]                          # per-shot cap: max 3 named characters
        has_dialogue = bool(_single_speaker(s.get("dialogue") or []))
        # Character on screen -> MUST move (never a still). Keep the writer's choice between
        # hero_video (full dynamic action motion) and lipsync_still (lip-synced talking); only
        # coerce a bad still up to one of them. No character -> cheap still (never pay for video).
        if cast:
            if st not in ("hero_video", "lipsync_still"):
                st = "hero_video" if not has_dialogue else "lipsync_still"
        elif st in ("hero_video", "lipsync_still"):
            st = "broll"
        if st == "hero_video":
            if videos >= channel.video_budget:
                # over the hero-video budget: a CHARACTER-free scene can drop to a cheap still pan,
                # but a scene WITH cast must stay in motion (still_kenburns is for char-free shots
                # only) — so bump it to lipsync_still, never a cast still.
                st = "lipsync_still" if cast else "still_kenburns"
            else:
                videos += 1
        beat = s.get("beat_type") if s.get("beat_type") in BEAT_TYPES else (
            "dialogue" if has_dialogue else "neutral")
        out.append({
            "seq": i,
            "heading": s.get("heading", ""),
            "action": action,
            "frozen_beat": frozen,               # still-safe instant (keyframe stage)
            "motion": motion,                    # ALL movement (video stage)
            "location_id": s.get("location_id") or _location_id(s.get("heading", "")),
            "time_jump": bool(s.get("time_jump", False)),
            "beat_type": beat,
            "camera": s.get("camera", ""),
            "cast_present": cast,
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
    return WriterResult(ok=True, data={"scenes": _normalize_scenes(raw, channel, cast_chars)},
                        model="stub", stubbed=True)
