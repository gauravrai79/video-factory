"""AI Influencer Factory — ops + QC console (FastAPI app).

Endpoints:
  - characters: create personas, list, mint a reference sheet
  - storyboards: plan a post (character + brief -> priced shot list); optionally commit + run it
  - jobs: list/inspect posts moving through the machine, human QC decisions
  - media: stream finished/delivered reels
  - scenes: the curated scene-template catalog the planner draws from

Run it:  python scripts/serve.py        (or: uvicorn backend.api:app --reload --port 8310)

The sync backend drains in a background thread so the UI stays responsive while posts are generated
(real fal calls take minutes). Each request opens its own JobStore (its own sqlite connection).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import episode_jobs, episode_pipeline, runner, sla as sla_mod
from .agents.storyboard import plan_storyboard
from .capabilities import fal_image, pricing
from .channels import CAST_ROLES, FORMATS, ChannelStore
from .characters import CharacterStore
from .episode_pipeline import StageError
from .episodes import STAGE_ORDER, EpisodeStore, Stage
from .jobstore import JobStore, State
from .pipeline import cost_ceiling_usd, create_job, qc_decision
from .scene_library import catalog as scene_catalog
from .spec import PRESETS, get_spec

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OUT_DIR = ROOT / "out"
MEDIA_KINDS = {"finished", "delivered"}

app = FastAPI(title="AI Influencer Factory", version="1.0.0")


def _tenant() -> str:
    return os.environ.get("VF_TENANT_ID", "factory")


def _project() -> str:
    return os.environ.get("VF_PROJECT", "influencer-factory")


def _has_media(slug: str, kind: str) -> bool:
    return (OUT_DIR / kind / f"{slug}.mp4").is_file()


def _job_view(store: JobStore, job, *, full: bool = False) -> dict[str, Any]:
    p = job.payload or {}
    char = p.get("character", {}) or {}
    sb = p.get("storyboard", {}) or {}
    gen = job.result.get("generation") or {}
    s = sla_mod.status_for(store, job)
    view: dict[str, Any] = {
        "job_id": job.job_id,
        "slug": job.slug,
        "character": char.get("name", ""),
        "character_id": char.get("character_id", ""),
        "format": sb.get("format", ""),
        "brief": sb.get("brief", ""),
        "shots": len(sb.get("shots", [])),
        "state": job.state.value,
        "tier": p.get("tier", "basic"),
        "execute": bool(p.get("execute", True)),
        "human_qc": bool(p.get("human_qc")),
        "priority": p.get("priority"),
        "est_cost_usd": p.get("est_cost_usd"),
        "cost_usd": gen.get("cost_usd"),
        "finished": job.result.get("finished"),
        "violations": job.result.get("violations"),
        "vlm_qc": job.result.get("vlm_qc"),
        "held": job.result.get("held"),
        "error": job.result.get("error"),
        "failed_stage": job.result.get("failed_stage"),
        "sla": {"elapsed_s": s.elapsed_s, "budget_s": s.budget_s,
                "breached": s.breached, "remaining_s": s.remaining_s},
        "media": {k: _has_media(job.slug, k) for k in MEDIA_KINDS},
        "updated_at": job.updated_at,
        "created_at": job.created_at,
    }
    if full:
        view["payload"] = p
        view["result"] = job.result
        view["audit"] = store.audit_trail(job.job_id)
        view["audit_chain_valid"] = store.verify_chain(job.job_id)
    return view


# --------------------------------------------------------------------------- summary / config

@app.get("/api/summary")
def summary() -> dict[str, Any]:
    store = JobStore()
    jobs = store.list(tenant_id=_tenant())
    by_state: dict[str, int] = {}
    spent = 0.0
    for j in jobs:
        by_state[j.state.value] = by_state.get(j.state.value, 0) + 1
        spent += float((j.result.get("generation") or {}).get("cost_usd") or 0)
    breaches = [s for s in sla_mod.evaluate(store, tenant_id=_tenant()) if s.breached]
    cs = CharacterStore(store)
    ch_store, ep_store = ChannelStore(store), EpisodeStore(store)
    return {
        "tenant": _tenant(),
        "project": _project(),
        "queue_backend": os.environ.get("VF_QUEUE_BACKEND", "sync"),
        "spec": get_spec().name,
        "specs": [{"name": pp.name, "label": f"{pp.name} · {pp.width}×{pp.height}"} for pp in PRESETS.values()],
        "fal_key_present": bool(os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")),
        "cost_ceiling_usd": cost_ceiling_usd(),
        "image_model": pricing.default_image_model(),
        "video_model": pricing.DEFAULT_VIDEO_MODEL,
        "channels": len(ch_store.list(_tenant())),
        "episodes": len(ep_store.list(_tenant())),
        "characters": len(cs.list(_tenant())),
        "total_jobs": len(jobs),
        "by_state": by_state,
        "spent_usd": round(spent, 4),
        "sla_breaches": len(breaches),
        "drain": runner.progress(),
    }


@app.get("/api/scenes")
def scenes() -> list[dict[str, Any]]:
    return scene_catalog()


# --------------------------------------------------------------------------- characters (actors)

_CHAR_FIELDS = ("species", "age", "persona", "reference_images", "dna_prompt",
                "safety_tolerance", "voice", "personality", "social_accounts", "posting_schedule")


def _char_view(char) -> dict[str, Any]:
    """Character as a digital actor: includes reference-image URLs so the UI can SHOW the actor."""
    d = char.as_dict()
    d["reference_image_urls"] = [f"/api/characters/{char.character_id}/reference/{i}"
                                 for i in range(len(char.reference_images))]
    d["has_reference"] = char.has_reference()
    d["has_voice"] = char.has_voice()
    d["voice_preview_url"] = (f"/api/characters/{char.character_id}/voice-preview"
                              if (char.voice or {}).get("preview_path") else None)
    return d


@app.get("/api/characters")
def list_characters() -> list[dict[str, Any]]:
    cs = CharacterStore()
    return [_char_view(c) for c in cs.list(_tenant())]


@app.post("/api/characters")
def create_character(body: dict[str, Any]) -> dict[str, Any]:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    slug = (body.get("slug") or name).strip().lower().replace(" ", "-")
    cs = CharacterStore()
    if cs.get_by_slug(_tenant(), slug):
        raise HTTPException(409, f"character slug '{slug}' already exists")
    fields = {k: v for k, v in body.items() if k in _CHAR_FIELDS}
    char = cs.create(tenant_id=_tenant(), name=name, slug=slug, **fields)
    return _char_view(char)


@app.get("/api/characters/{character_id}")
def get_character(character_id: str) -> dict[str, Any]:
    cs = CharacterStore()
    char = cs.get(character_id)
    if not char:
        raise HTTPException(404, "character not found")
    return _char_view(char)


@app.patch("/api/characters/{character_id}")
def update_character(character_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Edit the actor — voice DNA, personality bible, dna_prompt, persona, name/slug."""
    cs = CharacterStore()
    fields = {k: v for k, v in body.items() if k in (*_CHAR_FIELDS, "name", "slug")}
    char = cs.patch(character_id, **fields)
    if not char:
        raise HTTPException(404, "character not found")
    return _char_view(char)


@app.post("/api/characters/{character_id}/reference")
def upload_reference(character_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Upload a reference image (real photo) as base64 — no generation spend. Body: {filename,
    data_base64}. Makes the actor's Visual DNA visible immediately."""
    import base64
    cs = CharacterStore()
    char = cs.get(character_id)
    if not char:
        raise HTTPException(404, "character not found")
    raw = body.get("data_base64") or ""
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(400, "data_base64 is not valid base64")
    if not blob:
        raise HTTPException(400, "empty image")
    ext = Path(body.get("filename") or "ref.png").suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "unsupported image type")
    dest_dir = OUT_DIR / "characters" / char.slug / "reference"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"upload_{len(char.reference_images):02d}{ext}"
    dest.write_bytes(blob)
    cs.add_reference_images(character_id, [str(dest)])
    return _char_view(cs.get(character_id))


@app.get("/api/characters/{character_id}/reference/{idx}")
def get_reference(character_id: str, idx: int):
    cs = CharacterStore()
    char = cs.get(character_id)
    if not char or idx < 0 or idx >= len(char.reference_images):
        raise HTTPException(404, "reference image not found")
    path = Path(char.reference_images[idx])
    if not path.is_file():
        raise HTTPException(404, "reference file missing on disk")
    return FileResponse(str(path))


@app.delete("/api/characters/{character_id}/reference/{idx}")
def delete_reference(character_id: str, idx: int) -> dict[str, Any]:
    """Remove one reference image from a character's Visual DNA."""
    cs = CharacterStore()
    char = cs.remove_reference_image(character_id, idx)
    if not char:
        raise HTTPException(404, "reference image not found")
    return _char_view(char)


@app.post("/api/characters/{character_id}/mint")
def mint_reference(character_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mint a reference sheet for a text-described character (e.g. a synthetic glamour persona).
    execute=false (default) returns the priced plan without spending."""
    body = body or {}
    cs = CharacterStore()
    char = cs.get(character_id)
    if not char:
        raise HTTPException(404, "character not found")
    if not char.dna_prompt:
        raise HTTPException(400, "character has no dna_prompt to mint from")
    n = int(body.get("n", 4))
    execute = bool(body.get("execute", False))
    paths, cost, errors = fal_image.mint_reference_sheet(
        dna_prompt=char.dna_prompt, out_dir=str(OUT_DIR), slug=char.slug, n=n,
        safety_tolerance=char.safety_tolerance, execute=execute)
    if execute and paths:
        cs.add_reference_images(character_id, paths)
    return {"character_id": character_id, "minted": paths, "cost_usd": cost,
            "errors": errors, "executed": execute}


# --------------------------------------------------------------------------- channels (series)

def _channel_view(ch, cs: CharacterStore) -> dict[str, Any]:
    d = ch.as_dict()
    # resolve cast to names so the UI can show the roster
    roster = []
    for member in ch.cast:
        c = cs.get(member.get("character_id", ""))
        roster.append({"character_id": member.get("character_id"), "role": member.get("role"),
                       "name": c.name if c else "(missing)", "slug": c.slug if c else None,
                       "has_reference": c.has_reference() if c else False,
                       "has_voice": c.has_voice() if c else False})
    d["roster"] = roster
    d["transitions"] = [{**t, "video_url": f"/api/channels/{ch.channel_id}/transitions/{t.get('id')}/media"}
                        for t in (ch.transitions or [])]
    from .transitions import TEMPLATES
    d["transition_templates"] = [{"kind": k, "label": v["label"], "tags": v["tags"]}
                                 for k, v in TEMPLATES.items()]
    return d


@app.get("/api/styles")
def list_styles() -> dict[str, Any]:
    """The art-style library for the channel-wizard visual picker (id, label, sample image, tags)."""
    from .styles import ART_STYLES
    return {"styles": [{"id": s["id"], "label": s["label"], "tags": s.get("tags", []),
                        "prompt": s["prompt"], "sample_url": f"/assets/styles/{s['id']}.jpg"}
                       for s in ART_STYLES]}


@app.post("/api/assist/premise")
def assist_premise(body: dict[str, Any]) -> dict[str, Any]:
    """Draft a channel concept (name, tagline, premise, tone, suggested style ids) from a one-liner."""
    from .agents import concept
    res = concept.draft_concept((body or {}).get("brief", ""),
                                platform=(body or {}).get("platform", "youtube"))
    if not res.ok:
        raise HTTPException(502, res.error or "concept drafting failed")
    return {**res.data, "stubbed": res.stubbed}


@app.get("/api/channels")
def list_channels() -> list[dict[str, Any]]:
    store = JobStore()
    ch_store, cs = ChannelStore(store), CharacterStore(store)
    return [_channel_view(ch, cs) for ch in ch_store.list(_tenant())]


@app.post("/api/channels")
def create_channel(body: dict[str, Any]) -> dict[str, Any]:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    slug = (body.get("slug") or name).strip().lower().replace(" ", "-")
    fmt = body.get("format", "long_form")
    if fmt not in FORMATS:
        raise HTTPException(400, f"format must be one of {FORMATS}")
    store = JobStore()
    ch_store, cs = ChannelStore(store), CharacterStore(store)
    if ch_store.get_by_slug(_tenant(), slug):
        raise HTTPException(409, f"channel slug '{slug}' already exists")
    fields = {k: v for k, v in body.items()
              if k in ("platform", "format", "premise", "cast", "narrator_voice_id", "art_style",
                       "art_style_id", "tone", "tagline", "world", "language", "style_reference_images",
                       "target_scene_count", "target_duration_s", "video_budget", "writer_provider",
                       "writer_model", "posting_cadence")}
    if fields.get("art_style_id") and not fields.get("art_style"):
        from .styles import prompt_for
        fields["art_style"] = prompt_for(fields["art_style_id"])
    ch = ch_store.create(tenant_id=_tenant(), name=name, slug=slug, **fields)
    return _channel_view(ch, cs)


@app.get("/api/channels/{channel_id}")
def get_channel(channel_id: str) -> dict[str, Any]:
    store = JobStore()
    ch_store, cs = ChannelStore(store), CharacterStore(store)
    ch = ch_store.get(channel_id)
    if not ch:
        raise HTTPException(404, "channel not found")
    return _channel_view(ch, cs)


@app.patch("/api/channels/{channel_id}")
def update_channel(channel_id: str, body: dict[str, Any]) -> dict[str, Any]:
    store = JobStore()
    ch_store, cs = ChannelStore(store), CharacterStore(store)
    fields = {k: v for k, v in body.items()
              if k in ("name", "slug", "platform", "premise", "cast", "narrator_voice_id",
                       "art_style", "art_style_id", "tone", "tagline", "world", "language",
                       "style_reference_images", "target_scene_count", "target_duration_s",
                       "video_budget", "writer_provider", "writer_model", "series_memory",
                       "posting_cadence", "active")}
    if fields.get("art_style_id"):
        from .styles import prompt_for
        fields["art_style"] = prompt_for(fields["art_style_id"])
    ch = ch_store.patch(channel_id, **fields)
    if not ch:
        raise HTTPException(404, "channel not found")
    return _channel_view(ch, cs)


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: str) -> dict[str, Any]:
    """Delete a channel and everything under it: its episodes (+ their media) and channel-level media
    (transitions). Characters are shared across channels, so they are NOT deleted."""
    import shutil
    store = JobStore()
    ch_store, ep_store = ChannelStore(store), EpisodeStore(store)
    ch = ch_store.get(channel_id)
    if not ch:
        raise HTTPException(404, "channel not found")
    out = Path(os.environ.get("VF_OUT_DIR", "out"))
    eps = ep_store.list(_tenant(), channel_id=channel_id)
    for ep in eps:
        ep_store.delete(ep.episode_id)
        shutil.rmtree(out / "episodes" / ep.episode_id, ignore_errors=True)
    shutil.rmtree(out / "channels" / channel_id, ignore_errors=True)
    store.conn.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))
    store.conn.commit()
    return {"deleted": channel_id, "episodes_deleted": len(eps)}


# --------------------------------------------------------------------------- transition library

@app.post("/api/channels/{channel_id}/transitions")
def add_transition(channel_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Generate one reusable transition clip for a channel from a template {kind}."""
    from . import transitions
    store = JobStore()
    ch_store, cs = ChannelStore(store), CharacterStore(store)
    ch = ch_store.get(channel_id)
    if not ch:
        raise HTTPException(404, "channel not found")
    try:
        info, _cost = transitions.generate_transition(store, ch, str((body or {}).get("kind", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if info.get("status") != "ok":
        raise HTTPException(502, f"transition generation failed: {info.get('error')}")
    return _channel_view(ch_store.get(channel_id), cs)


@app.delete("/api/channels/{channel_id}/transitions/{tid}")
def remove_transition(channel_id: str, tid: str) -> dict[str, Any]:
    from . import transitions
    store = JobStore()
    ch_store, cs = ChannelStore(store), CharacterStore(store)
    ch = ch_store.get(channel_id)
    if not ch:
        raise HTTPException(404, "channel not found")
    if not transitions.delete_transition(store, ch, tid):
        raise HTTPException(404, "transition not found")
    return _channel_view(ch_store.get(channel_id), cs)


@app.get("/api/channels/{channel_id}/transitions/{tid}/media")
def transition_media(channel_id: str, tid: str):
    ch = ChannelStore().get(channel_id)
    t = next((x for x in (ch.transitions if ch else []) if x.get("id") == tid), None)
    if not t or not Path(t.get("path", "")).is_file():
        raise HTTPException(404, "transition media not found")
    return FileResponse(t["path"], media_type="video/mp4")


# --------------------------------------------------------------------------- episodes

def _episode_view(ep, channel_name: str = "", ch=None) -> dict[str, Any]:
    from . import formats
    d = ep.as_dict()
    d["channel_name"] = channel_name
    d["stage_index"] = [s.value for s in STAGE_ORDER].index(ep.stage) if ep.stage in [s.value for s in STAGE_ORDER] else 0
    d["stages"] = [s.value for s in STAGE_ORDER]
    # Effective format config + Setup-stage options (presets, suggested scene count).
    d["config"] = formats.episode_config(ep, ch)
    d["config_saved"] = bool((ep.config or {}).get("configured"))
    d["platform_presets"] = [{"id": k, **v} for k, v in formats.PLATFORM_PRESETS.items()]
    d["scene_count_suggested"] = formats.default_scene_count(d["config"]["duration_s"])
    d["scene_count"] = len(ep.scenes)
    d["stage_estimate_usd"] = episode_pipeline.stage_estimate(ep)
    d["image_unit_cost"] = round(pricing.image_cost(), 4)
    d["image_models"] = [{"id": m, "label": l, "cost": round(pricing.image_cost(m), 4)} for m, l in (
        ("gemini-flash", "Gemini Flash (cheap, consistent)"),
        ("nano-banana-pro", "Nano Banana Pro (best identity)"),
        ("nano-banana-2", "Nano Banana 2"),
        ("gemini-3-flash", "Gemini 3 Flash"),
        ("flux-kontext", "Flux Kontext (edit)"),
    )]
    d["refs_done_count"] = sum(1 for s in ep.scenes if (s.get("reference_image") or {}).get("status") == "ok")
    d["scenes_done_count"] = sum(1 for s in ep.scenes if (s.get("clip") or {}).get("status") in ("ok", "kenburns"))
    d["audio_done_count"] = sum(1 for s in ep.scenes if (s.get("audio") or {}).get("status") == "ok")
    d["generating"] = (ep.stage_status == "generating") or episode_jobs.is_running(ep.episode_id)
    # per-scene media URLs (only when the asset exists)
    for sc in d["scenes"]:
        seq = sc.get("seq")
        if (sc.get("reference_image") or {}).get("status") == "ok":
            sc["still_url"] = f"/api/episodes/{ep.episode_id}/still/{seq}"
        if (sc.get("clip") or {}).get("status") == "ok":
            sc["clip_url"] = f"/api/episodes/{ep.episode_id}/clip/{seq}"
        sc["asset"] = bool(sc.get("asset_path"))
        sc["asset_kind"] = sc.get("asset_kind", "")
    tl = ep.timeline or {}
    d["rough_cut_url"] = f"/api/episodes/{ep.episode_id}/rough-cut" if tl.get("rough_cut") else None
    d["audio_cut_url"] = f"/api/episodes/{ep.episode_id}/audio-cut" if tl.get("audio_cut") else None
    d["final_url"] = f"/api/episodes/{ep.episode_id}/final" if tl.get("final_video") else None
    prev = ep.script_prev or {}   # slim (don't ship the whole prior script to the client)
    d["script_prev"] = {"scenes": len(prev.get("scenes") or []), "score": (prev.get("script_qc") or {}).get("score")}
    d["oneoff"] = bool((ep.config or {}).get("oneoff"))
    d["has_voiceover"] = bool((ep.config or {}).get("voiceover_text"))
    d["titles_url"] = f"/api/episodes/{ep.episode_id}/titles.srt" if tl.get("titles_srt") else None
    return d


def _episode_action(episode_id: str, fn) -> dict[str, Any]:
    """Shared plumbing for stage actions: load episode, run fn(store, ep), return the view."""
    store = JobStore()
    ep_store, ch_store = EpisodeStore(store), ChannelStore(store)
    ep = ep_store.get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    try:
        ep = fn(store, ep)
    except StageError as e:
        raise HTTPException(409, str(e))
    ch = ch_store.get(ep.channel_id)
    return _episode_view(ep, ch.name if ch else "", ch)


@app.get("/api/episodes")
def list_episodes(channel_id: str | None = None) -> list[dict[str, Any]]:
    store = JobStore()
    ep_store, ch_store = EpisodeStore(store), ChannelStore(store)
    names = {c.channel_id: c.name for c in ch_store.list(_tenant())}
    eps = ep_store.list(_tenant(), channel_id=channel_id)
    chmap = {c.channel_id: c for c in ch_store.list(_tenant())}
    return [_episode_view(e, names.get(e.channel_id, ""), chmap.get(e.channel_id)) for e in eps]


@app.get("/api/oneoff")
def list_oneoff() -> list[dict[str, Any]]:
    """List one-off 'Quick Video' projects (episodes under the hidden system channel)."""
    from . import oneoff
    store = JobStore()
    ep_store = EpisodeStore(store)
    ch = ChannelStore(store).get_by_slug(_tenant(), oneoff.ONEOFF_SLUG)
    if not ch:
        return []
    eps = ep_store.list(_tenant(), channel_id=ch.channel_id)
    return [_episode_view(e, "Quick Video", ch) for e in eps]


@app.post("/api/oneoff")
def create_oneoff(body: dict[str, Any]) -> dict[str, Any]:
    """Compile a Markdown prompt-pack into a ready-to-run one-off video. Body {md, aspect?, music?,
    resolution?, voice?}."""
    from . import oneoff
    md = (body or {}).get("md", "")
    if not (md or "").strip():
        raise HTTPException(400, "paste a script (markdown) first")
    store = JobStore()
    try:
        ep = oneoff.create_from_md(store, _tenant(), md, aspect=(body or {}).get("aspect"),
                                   music=bool((body or {}).get("music", True)),
                                   resolution=(body or {}).get("resolution", "720p"),
                                   voice_id=(body or {}).get("voice") or "Rachel",
                                   assets=(body or {}).get("assets") or {})
    except ValueError as e:
        raise HTTPException(422, str(e))
    ch = ChannelStore(store).get(ep.channel_id)
    return _episode_view(ep, "Quick Video", ch)


@app.post("/api/episodes")
def create_episode(body: dict[str, Any]) -> dict[str, Any]:
    """Create an episode shell for a channel (stage=idea/pending). Generation runs in later stages."""
    channel_id = body.get("channel_id", "")
    store = JobStore()
    ep_store, ch_store = EpisodeStore(store), ChannelStore(store)
    ch = ch_store.get(channel_id)
    if not ch:
        raise HTTPException(404, "channel not found (pass channel_id)")
    ep = ep_store.create(tenant_id=_tenant(), channel_id=channel_id,
                         title=(body.get("title") or "").strip(), cast=ch.cast_ids())
    return _episode_view(ep, ch.name, ch)


@app.get("/api/episodes/{episode_id}")
def get_episode(episode_id: str) -> dict[str, Any]:
    store = JobStore()
    ep_store, ch_store = EpisodeStore(store), ChannelStore(store)
    ep = ep_store.get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    ch = ch_store.get(ep.channel_id)
    return _episode_view(ep, ch.name if ch else "", ch)


@app.post("/api/episodes/{episode_id}/config")
def configure_episode(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Save the Setup-stage format config (layout/length/resolution/language/music/QC/…) and, on
    first save, advance from Setup to Idea."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.configure(s, e, body or {}))


@app.delete("/api/episodes/{episode_id}")
def delete_episode(episode_id: str) -> dict[str, Any]:
    """Delete an episode and its generated media (stills/clips/audio/cuts)."""
    import shutil
    store = JobStore()
    ep_store = EpisodeStore(store)
    if not ep_store.get(episode_id):
        raise HTTPException(404, "episode not found")
    ep_store.delete(episode_id)
    media = Path(os.environ.get("VF_OUT_DIR", "out")) / "episodes" / episode_id
    if media.exists():
        shutil.rmtree(media, ignore_errors=True)
    return {"deleted": episode_id}


def _ep_view(episode_id: str) -> dict[str, Any]:
    store = JobStore()
    ep = EpisodeStore(store).get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    ch = ChannelStore(store).get(ep.channel_id)
    return _episode_view(ep, ch.name if ch else "")


@app.post("/api/episodes/{episode_id}/run")
def run_stage(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate the current stage's artifact. Quick stages (idea/script/refs-preview/assembly) run
    inline; the heavy multi-asset stages (scenes/audio) run in the background so the UI can watch the
    grid fill in. Optional {brief} steers ideation; {style_note} steers the refs preview look."""
    body = body or {}
    store = JobStore()
    ep = EpisodeStore(store).get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    if ep.stage in ("scenes", "audio"):
        episode_jobs.start(episode_id, "generate_scenes" if ep.stage == "scenes" else "generate_audio")
        return _ep_view(episode_id)
    return _episode_action(episode_id, lambda s, e: episode_pipeline.run_stage(
        s, e, brief=body.get("brief"), style_note=body.get("style_note")))


@app.post("/api/episodes/{episode_id}/refs/batch")
def refs_batch(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """After the preview is approved, generate reference images for all remaining scenes — in the
    background, so the grid fills in one image at a time."""
    body = body or {}
    episode_jobs.start(episode_id, "generate_refs_batch", style_note=(body or {}).get("style_note"))
    return _ep_view(episode_id)


@app.post("/api/episodes/{episode_id}/approve")
def approve_stage(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Approve the current stage's artifact and advance. Body: {choice|idea} for idea, {scenes?} for script."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.approve_stage(s, e, payload=body or {}))


@app.post("/api/episodes/{episode_id}/reject")
def reject_stage(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return _episode_action(episode_id, lambda s, e: episode_pipeline.reject_stage(s, e, reason=str((body or {}).get("reason", ""))))


@app.patch("/api/episodes/{episode_id}/artifact")
def edit_artifact(episode_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Hand-edit the current artifact (idea or scenes) in place."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.edit_artifact(
        s, e, idea=body.get("idea"), scenes=body.get("scenes")))


@app.post("/api/episodes/{episode_id}/script/revise")
def revise_script(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply the QC feedback (plus optional human direction) to the CURRENT script and re-judge —
    a targeted revision, not a from-scratch rewrite. Body {notes: [str]}."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.revise_script_stage(
        s, e, notes=(body or {}).get("notes")))


@app.post("/api/episodes/{episode_id}/script/revert")
def revert_script(episode_id: str) -> dict[str, Any]:
    """Undo the last rewrite/revise — restore the stashed previous script (itself undoable)."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.revert_script(s, e))


@app.post("/api/episodes/{episode_id}/reopen")
def reopen_stage(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-open a previously-approved stage (e.g. script) to edit or re-run it."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.reopen_stage(
        s, e, stage=str((body or {}).get("stage", "script"))))


@app.post("/api/episodes/{episode_id}/scene/{seq}/reroll")
def reroll_scene(episode_id: str, seq: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-generate one scene's asset for the current stage (still at refs, Veo clip at scenes).
    Optional {prompt, model} override the wording / image model when re-rolling a reference."""
    return _episode_action(episode_id, lambda s, e: episode_pipeline.reroll_scene(
        s, e, seq=seq, prompt_override=(body or {}).get("prompt"), model=(body or {}).get("model")))


@app.post("/api/episodes/{episode_id}/seams")
def set_seams(episode_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Save the human seam overrides for assembly: {seams: {"<incoming shot idx>": "auto"|"none"|kind}}."""
    store = JobStore()
    ep_store = EpisodeStore(store)
    ep = ep_store.get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    seams = body.get("seams") or {}
    ep.timeline = {**(ep.timeline or {}), "seams": {str(k): str(v) for k, v in seams.items()}}
    ep.log("seams_edited", {"overrides": len(seams)})
    ep_store.update(ep)
    return _ep_view(episode_id)


@app.get("/api/episodes/{episode_id}/scene/{seq}/veo-prompt")
def scene_veo_prompt(episode_id: str, seq: int) -> dict[str, Any]:
    """The editable Veo prompt for a scene: a saved override / the prompt last used, else the default
    computed from the scene (action, dialogue, style, world)."""
    store = JobStore()
    ep = EpisodeStore(store).get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    scene = next((s for s in ep.scenes if s.get("seq") == seq), None)
    if not scene:
        raise HTTPException(404, "scene not found")
    prompt = (scene.get("veo_prompt_override") or (scene.get("clip") or {}).get("prompt") or "").strip()
    if not prompt:
        from .agents import shot_prompt
        ch = ChannelStore(store).get(ep.channel_id)
        cast_map = episode_pipeline._cast_map(CharacterStore(store), ep.cast or ch.cast_ids())
        prompt = shot_prompt.veo_prompt(scene, shot_prompt.scene_cast(scene, cast_map), ch)
    return {"seq": seq, "prompt": prompt}


@app.post("/api/episodes/{episode_id}/scenes/generate")
def generate_scenes_selected(episode_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate scenes with per-scene control. Body {seqs?: [int], prompts?: {seq: text}}. seqs omitted
    -> generate every scene still missing a clip; seqs=[...] -> (re)generate exactly those. Any prompts
    are saved as per-scene Veo overrides first. Runs in the background so the grid fills in live."""
    body = body or {}
    store = JobStore()
    ep_store = EpisodeStore(store)
    ep = ep_store.get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    if ep.stage != "scenes":
        raise HTTPException(409, "not at the scenes stage")
    prompts = body.get("prompts") or {}
    if prompts:
        for s in ep.scenes:
            val = (prompts.get(str(s.get("seq"))) or "").strip()
            if val:
                s["veo_prompt_override"] = val
        ep_store.update(ep)
    seqs = body.get("seqs")
    kwargs = {"seqs": [int(x) for x in seqs]} if seqs else {}
    episode_jobs.start(episode_id, "generate_scenes", **kwargs)
    return _ep_view(episode_id)


def _episode_media(episode_id: str, kind: str, seq: int | None = None):
    store = JobStore()
    ep = EpisodeStore(store).get(episode_id)
    if not ep:
        raise HTTPException(404, "episode not found")
    if kind in ("rough-cut", "audio-cut", "final", "music"):
        key = {"rough-cut": "rough_cut", "audio-cut": "audio_cut", "final": "final_video",
               "music": "music"}[kind]
        path = (ep.timeline or {}).get(key)
        media = "audio/mpeg" if kind == "music" else "video/mp4"
    else:
        sc = next((s for s in ep.scenes if s.get("seq") == seq), None)
        if not sc:
            raise HTTPException(404, "scene not found")
        node = sc.get("reference_image" if kind == "still" else "clip") or {}
        path = node.get("path")
        media = "image/png" if kind == "still" else "video/mp4"
    if not path or not Path(path).is_file():
        raise HTTPException(404, "media not found")
    return FileResponse(str(path), media_type=media)


@app.get("/api/episodes/{episode_id}/still/{seq}")
def episode_still(episode_id: str, seq: int):
    return _episode_media(episode_id, "still", seq)


@app.get("/api/episodes/{episode_id}/clip/{seq}")
def episode_clip(episode_id: str, seq: int):
    return _episode_media(episode_id, "clip", seq)


@app.get("/api/episodes/{episode_id}/rough-cut")
def episode_rough_cut(episode_id: str):
    return _episode_media(episode_id, "rough-cut")


@app.get("/api/episodes/{episode_id}/audio-cut")
def episode_audio_cut(episode_id: str):
    return _episode_media(episode_id, "audio-cut")


@app.get("/api/episodes/{episode_id}/final")
def episode_final(episode_id: str):
    return _episode_media(episode_id, "final")


@app.get("/api/episodes/{episode_id}/music")
def episode_music(episode_id: str):
    return _episode_media(episode_id, "music")


@app.get("/api/episodes/{episode_id}/titles.srt")
def episode_titles(episode_id: str):
    store = JobStore()
    ep = EpisodeStore(store).get(episode_id)
    path = (ep.timeline or {}).get("titles_srt") if ep else None
    if not path or not Path(path).is_file():
        raise HTTPException(404, "no titles file")
    return FileResponse(path, media_type="text/plain",
                        filename=f"{(ep.title or 'titles')[:40]}.srt")


# --------------------------------------------------------------------------- storyboards / posts

@app.post("/api/storyboards")
def storyboard(body: dict[str, Any]) -> dict[str, Any]:
    """Plan a post for a character. By default also commits it as a job and starts generating.
    Set create=false to only preview the priced storyboard; execute=false for a dry (priced) run."""
    cs = CharacterStore()
    char = cs.get(body.get("character_id", ""))
    if not char:
        raise HTTPException(404, "character not found (pass character_id)")

    fmt = body.get("format", "reel")
    try:
        out_spec = get_spec(fmt)
    except ValueError as e:
        raise HTTPException(400, str(e))

    sb = plan_storyboard(
        char,
        brief=body.get("brief", ""),
        fmt=fmt,
        tags=body.get("tags") or [],
        n_shots=int(body.get("n_shots", 6)),
        video_budget=int(body.get("video_budget", 2)),
        refine=bool(body.get("refine", True)),
    )

    create = bool(body.get("create", True))
    if not create:
        return {"storyboard": sb.as_dict(), "committed": False}

    execute = bool(body.get("execute", True))
    store = JobStore()
    job, is_new = create_job(
        store, char, sb, tenant_id=_tenant(), project=_project(), spec=out_spec,
        execute=execute, human_qc=bool(body.get("human_qc", False)),
        tier=body.get("tier", "basic"), dedupe=True)

    no_ref_warning = None
    if not char.reference_images and not char.dna_prompt:
        no_ref_warning = ("character has no reference images or dna_prompt — identity will be "
                          "bootstrapped from the first generated still (less controllable).")

    block_run = execute and not (os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY"))
    run = bool(body.get("run", True)) and not block_run
    started = runner.start_background_drain() if run else False
    return {"storyboard": sb.as_dict(), "committed": True, "created": is_new,
            "job_id": job.job_id, "slug": job.slug, "est_cost_usd": sb.est_cost_usd,
            "warnings": [w for w in [no_ref_warning] if w],
            "blocked_run": block_run, "drain_started": started, "drain": runner.progress()}


@app.post("/api/run")
def run() -> dict[str, Any]:
    """Drain PENDING posts in the background (generate -> assemble -> qc -> deliver)."""
    started = runner.start_background_drain()
    return {"drain_started": started, "drain": runner.progress()}


# --------------------------------------------------------------------------- jobs / qc

@app.get("/api/jobs")
def list_jobs(state: str | None = None) -> list[dict[str, Any]]:
    store = JobStore()
    st = State(state) if state else None
    jobs = store.list(tenant_id=_tenant(), state=st)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [_job_view(store, j) for j in jobs]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    store = JobStore()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return _job_view(store, job, full=True)


@app.post("/api/jobs/{job_id}/qc")
def qc(job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Human QC decision: {"approve": true} clears -> delivered; {"approve": false, "reason": ...} -> rework."""
    store = JobStore()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        job = qc_decision(store, job, approve=bool(body.get("approve")),
                          reason=str(body.get("reason", "")))
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _job_view(store, job, full=True)


@app.get("/api/media/{kind}/{slug}")
def media(kind: str, slug: str):
    if kind not in MEDIA_KINDS:
        raise HTTPException(404, "unknown media kind")
    path = OUT_DIR / kind / f"{slug}.mp4"
    if not path.is_file():
        raise HTTPException(404, "media not found")
    return FileResponse(str(path), media_type="video/mp4")  # Starlette handles Range -> seekable


@app.get("/api/sla")
def sla() -> list[dict[str, Any]]:
    store = JobStore()
    return [{"slug": s.slug, "tier": s.tier, "state": s.state, "elapsed_s": s.elapsed_s,
             "budget_s": s.budget_s, "remaining_s": s.remaining_s, "breached": s.breached}
            for s in sla_mod.evaluate(store, tenant_id=_tenant())]


# --------------------------------------------------------------------------- frontend (served last)

if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
else:  # pragma: no cover
    @app.get("/")
    def _no_frontend() -> JSONResponse:
        return JSONResponse({"error": "frontend/ not found"}, status_code=500)
