"""One-off "Quick Video" — render a self-contained video from a Markdown prompt-pack, outside the
channel/episode show structure.

It reuses the whole Episode engine (refs → Veo scenes → assembly + loudnorm, with the per-scene
grid and vision-QC) by compiling the MD into an Episode under a hidden system channel. The author's
image/motion prompts are preserved verbatim (still_prompt_override / veo_prompt_override); a global
voiceover track and the on-screen-title sidecar live on the episode config.
"""
from __future__ import annotations

import time
from typing import Any

from .agents import ad_compiler
from .channels import ChannelStore
from .episodes import EpisodeStore, Stage, StageStatus

ONEOFF_SLUG = "__oneoff__"


def system_channel(store, tenant_id: str):
    """Get-or-create the hidden channel that all one-off videos hang under."""
    chs = ChannelStore(store)
    ch = chs.get_by_slug(tenant_id, ONEOFF_SLUG)
    if ch:
        return ch
    return chs.create(tenant_id=tenant_id, name="Quick Video", slug=ONEOFF_SLUG,
                      platform="one-off", format="long_form",
                      premise="Standalone one-off videos compiled from a script.", active=False)


def is_oneoff(ep) -> bool:
    return bool((ep.config or {}).get("oneoff"))


def _titles(compiled: dict) -> list[dict]:
    out = []
    for s in compiled["scenes"]:
        if (s.get("title") or "").strip():
            out.append({"seq": s["seq"], "start_s": s.get("start_s"), "end_s": s.get("end_s"),
                        "text": s["title"].strip()})
    return out


def create_from_md(store, tenant_id: str, md: str, *, aspect: str | None = None,
                   music: bool = True, resolution: str = "720p", voice_id: str = "Rachel") -> Any:
    """Compile the MD and create a ready-to-run one-off Episode. Lands at the REFS stage with every
    scene pre-populated (verbatim keyframe + motion prompts); Setup/Idea/Script are skipped."""
    compiled = ad_compiler.compile_md(md or "")
    if not compiled.get("scenes"):
        raise ValueError("could not find any scenes in that script")
    ch = system_channel(store, tenant_id)
    layout = "portrait" if (aspect or compiled.get("aspect")) == "9:16" else "landscape"
    scenes = []
    for s in compiled["scenes"]:
        dur = float(s.get("duration_s") or 6)
        scenes.append({
            "seq": s["seq"], "heading": s.get("label", ""),
            "action": s.get("motion_prompt", ""), "motion": s.get("motion_prompt", ""),
            "frozen_beat": s.get("still_prompt", ""),
            "still_prompt_override": s.get("still_prompt", ""),   # verbatim keyframe
            "veo_prompt_override": s.get("motion_prompt", ""),    # verbatim video prompt
            "camera": "", "cast_present": [], "dialogue": [], "narration": "",
            "shot_type": "broll", "duration_s": dur, "scripted_duration_s": dur,
            "on_screen_text": s.get("title", ""), "beat_type": "neutral", "time_jump": False,
            "location_id": f"scene_{s['seq']}",
            "reference_image": {}, "clip": {}, "voice_clips": [], "status": "pending",
            "intent": {"purpose": s.get("label", ""), "must_show": [], "mood": ""},
        })
    config = {
        "oneoff": True, "configured": True, "layout": layout, "resolution": resolution,
        "aspect": aspect or compiled.get("aspect", "16:9"),
        "duration_s": int(sum(x["duration_s"] for x in scenes)),
        "scene_count": len(scenes), "language": "English", "pacing": "balanced",
        "music": bool(music), "transitions": "off",       # ads = clean hard cuts, no library wipes
        "qc_threshold": 75,
        "style_base": compiled.get("style_base", ""),
        "voiceover": compiled.get("voiceover", []),
        "voiceover_text": compiled.get("voiceover_text", ""),
        "voice_id": voice_id,
        "music_brief": compiled.get("music", ""),
        "titles": _titles(compiled),
    }
    eps = EpisodeStore(store)
    ep = eps.create(tenant_id=tenant_id, channel_id=ch.channel_id,
                    title=compiled.get("title", "Quick Video")[:120], cast=[],
                    scenes=scenes, config=config,
                    stage=Stage.REFS.value, stage_status=StageStatus.PENDING.value,
                    refs_batch_done=False)
    ep.log("oneoff_compiled", {"scenes": len(scenes), "vo_lines": len(config["voiceover"]),
                               "aspect": config["aspect"]})
    return eps.update(ep)
