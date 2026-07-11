"""Transition library — reusable ~2s Veo clips spliced between scenes at assembly.

A channel owns a small library of branded transition clips (Jango/Zruv rushing the camera,
blaze wipes, comic slams, …). Each is generated ONCE via Veo 3.1 Lite (min 4s, trimmed to a
punchy 2s), stored on disk + recorded on the channel, and reused across every episode. At
assembly, a random transition (tagged by use-case) is dropped in at each location/time change.
"""
from __future__ import annotations

import os
import random
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .channels import Channel, ChannelStore
from .characters import CharacterStore
from .capabilities import fal_video
from .capabilities.fal_video import image_ref
from .finishing import FFMPEG, ScoredShot, media_duration

# kind -> template. needs_char=True animates the lead's reference still (image-to-video); else
# it's an abstract text-to-video effect. `tags` classify where the transition fits.
TEMPLATES: dict[str, dict[str, Any]] = {
    "hero_rush": {"label": "Hero rush", "tags": ["act_break", "reveal"], "needs_char": True,
        "prompt": "The character sprints straight toward the camera and fills the frame with a "
                  "heroic pose, dynamic speed lines and motion blur, then a bright flash. Energetic "
                  "whoosh and impact sound."},
    "blaze": {"label": "Blaze whoosh", "tags": ["cut", "action"], "needs_char": False,
        "prompt": "A streak of blazing orange fire and sparks sweeps rapidly across the screen from "
                  "left to right as a wipe, dark background, cinematic. A fiery whoosh sound."},
    "comic_slam": {"label": "Comic panel slam", "tags": ["cut", "comedic"], "needs_char": False,
        "prompt": "Bold inked comic-book panels slam and snap into place across the screen with "
                  "halftone dots and a POW burst, graphic-novel style. A snappy slam sound."},
    "whip_pan": {"label": "Whip pan", "tags": ["cut"], "needs_char": False,
        "prompt": "A fast horizontal whip-pan blur in warm neon colours sweeps across the frame with "
                  "heavy motion blur. A quick swish sound."},
    "dust_puff": {"label": "Dust puff", "tags": ["comedic", "cut"], "needs_char": False,
        "prompt": "A big cartoon dust cloud puffs up and fills the screen on a dusty Indian street, "
                  "then clears. A comedic poof sound."},
    "dhoom": {"label": "DHOOM burst", "tags": ["punchline", "reveal"], "needs_char": False,
        "prompt": "A vibrant comic-book explosion bursts and fills the screen with a big stylised "
                  "'DHOOM' energy blast in bright colours. A big boom sound."},
}


def _dir(channel: Channel) -> Path:
    d = Path(os.environ.get("VF_OUT_DIR", "out")) / "channels" / channel.channel_id / "transitions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lead_still(store, channel: Channel) -> str | None:
    cs = CharacterStore(store)
    lead = cs.get(channel.lead_id()) if channel.lead_id() else None
    if lead and lead.reference_images:
        return lead.reference_images[0]
    return None


def generate_transition(store, channel: Channel, kind: str) -> tuple[dict, float]:
    """Generate one 2s transition clip for a channel and record it in the library."""
    tpl = TEMPLATES.get(kind)
    if not tpl:
        raise ValueError(f"unknown transition kind '{kind}'")
    style = channel.art_style or "comic-book cinematic style"
    prompt = f"{style}. {tpl['prompt']} A short 2-second screen transition. No spoken dialogue."
    tid = str(uuid.uuid4())[:8]
    # Character transitions animate the lead's reference still; abstract effects animate over a neutral
    # black frame — both use the reliable image-to-video path (Veo's text-to-video route is flaky).
    base_png = None
    image = _lead_still(store, channel) if tpl["needs_char"] else None
    if not image:
        from .finishing import stub_image
        base_png = str(_dir(channel) / f"{tid}_base.png")
        stub_image(base_png, color="black")
        image = base_png
    full = str(_dir(channel) / f"{tid}_full.mp4")
    res = fal_video.generate_native_video(
        prompt=prompt, image_url=image_ref(image), output_path=full,
        duration_s=4, resolution="720p", generate_audio=True, aspect_ratio="16:9", execute=True)
    if base_png:
        Path(base_png).unlink(missing_ok=True)
    if not res.success:
        return {"status": "failed", "error": res.error, "kind": kind}, res.cost_usd
    # Veo's minimum clip is 4s — trim to a punchy 2s for a transition.
    out = str(_dir(channel) / f"{tid}.mp4")
    subprocess.run([FFMPEG, "-y", "-i", full, "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", out], capture_output=True)
    Path(full).unlink(missing_ok=True)
    t = {"id": tid, "kind": kind, "label": tpl["label"], "tags": tpl["tags"], "path": out,
         "prompt": prompt, "created_at": None}
    channel.transitions = [*(channel.transitions or []), t]
    ChannelStore(store).update(channel)
    return {**t, "status": "ok"}, res.cost_usd


def delete_transition(store, channel: Channel, tid: str) -> bool:
    lib = channel.transitions or []
    removed = next((t for t in lib if t.get("id") == tid), None)
    if not removed:
        return False
    channel.transitions = [t for t in lib if t.get("id") != tid]
    ChannelStore(store).update(channel)
    try:
        Path(removed.get("path", "")).unlink(missing_ok=True)
    except OSError:
        pass
    return True


# beat_type of the INCOMING scene -> transition kind (None = always hard cut into that beat).
BEAT_TO_TRANSITION: dict[str, str | None] = {
    "reveal": "comic_slam",
    "punchline": "comic_slam",
    "chase": "whip_pan",
    "impact_gag": "dust_puff",
    "zruv_entrance": "hero_rush",
    "establishing": "blaze",
    "dialogue": None,
    "neutral": None,
}
ENERGY_ALTERNATES = {"chase": ["whip_pan", "blaze"], "impact_gag": ["dust_puff", "dhoom"],
                     "punchline": ["comic_slam", "dhoom"]}
MIN_CUTS_BETWEEN = 3


def _loc(scene: dict) -> str:
    if scene.get("location_id"):
        return str(scene["location_id"]).lower()
    return (scene.get("heading") or "").split(" - ")[0].strip().lower() or "unknown"


def interleave(scene_shots: list[ScoredShot], scenes: list[dict], channel: Channel) -> list[ScoredShot]:
    """Splice transitions per the cut-rhythm rules: the DEFAULT seam is a hard cut. A transition is
    inserted only when the location changes (or time jumps) INTO a beat whose type maps to a clip
    that exists in the channel library — never back-to-back, at least MIN_CUTS_BETWEEN hard cuts
    apart, and at most ceil(scenes/3) per episode. Breaks the every-seam metronome."""
    import math
    lib_by_kind: dict[str, list[dict]] = {}
    for t in (channel.transitions or []):
        if Path(t.get("path", "")).is_file():
            lib_by_kind.setdefault(t.get("kind", ""), []).append(t)
    if not lib_by_kind or len(scene_shots) < 2:
        return scene_shots
    rng = random.Random(len(scene_shots))          # deterministic per episode length (repeatable cuts)
    max_transitions = math.ceil(len(scene_shots) / 3)
    used, cuts_since_last = 0, MIN_CUTS_BETWEEN    # allow one early if warranted
    out = [scene_shots[0]]
    for i in range(1, len(scene_shots)):
        prev_sc, cur_sc = scenes[i - 1], scenes[i]
        eligible = (_loc(prev_sc) != _loc(cur_sc)) or bool(cur_sc.get("time_jump"))
        kind = BEAT_TO_TRANSITION.get(cur_sc.get("beat_type") or "neutral")
        candidates = [k for k in ([kind] + ENERGY_ALTERNATES.get(cur_sc.get("beat_type") or "", []))
                      if k and k in lib_by_kind] if kind else []
        if eligible and candidates and used < max_transitions and cuts_since_last >= MIN_CUTS_BETWEEN:
            t = rng.choice(lib_by_kind[rng.choice(candidates)])
            out.append(ScoredShot("talking", t["path"], media_duration(t["path"]) or 2.0))
            used += 1
            cuts_since_last = 0
        else:
            cuts_since_last += 1                   # hard cut (the default)
        out.append(scene_shots[i])
    return out
