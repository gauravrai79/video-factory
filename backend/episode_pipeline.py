"""Episode stage orchestrator — runs a stage's generator, then holds at its human gate.

The token-safety model: `run_stage` generates the CURRENT stage's artifact and parks the episode at
`awaiting_review`; nothing advances until a human calls `approve` (which promotes the artifact and
moves to the next stage) or `reject` (back up) or edits the artifact in place. Every action is logged
to the episode history.

M2 implements the IDEA and SCRIPT stages (writers' room, text-only, cheap). REFS/SCENES/AUDIO/ASSEMBLY
are wired in later milestones and return a "not available yet" result.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .agents import shot_prompt, writer
from .capabilities import (fal_image, fal_video, lipsync as lipsync_cap, music as music_cap,
                           or_image as or_image_cap, pricing, voice as voice_cap)
from .capabilities.fal_video import image_ref
from .channels import Channel, ChannelStore
from .characters import Character, CharacterStore
from .episodes import Episode, EpisodeStore, Stage, StageStatus, next_stage
from .finishing import FFMPEG, ScoredShot, ShotMedia, assemble, assemble_scored, media_duration
from .spec import OutputSpec, get_spec


class StageError(RuntimeError):
    pass


def episode_ceiling_usd() -> float:
    """Per-episode per-stage spend ceiling (safety net over the human commit-spend gate)."""
    return float(os.environ.get("VF_EPISODE_CEILING_USD", "25"))


def channel_spec(ch: Channel) -> OutputSpec:
    """Map the channel format to an output spec: long-form -> landscape, short-form -> vertical reel."""
    return get_spec("reel" if ch.is_short() else "landscape")


def _out_dir(ep: Episode) -> Path:
    return Path(os.environ.get("VF_OUT_DIR", "out")) / "episodes" / ep.episode_id


def stage_estimate(ep: Episode) -> float:
    """Estimated USD to run the current stage (shown before the paid gate)."""
    if ep.stage == Stage.REFS.value:
        return round(len(ep.scenes) * pricing.image_cost(None), 4)
    if ep.stage == Stage.SCENES.value:
        return round(sum(fal_video.video_billed_cost(pricing.DEFAULT_VIDEO_MODEL, s.get("duration_s", 5))
                         for s in ep.scenes if s.get("shot_type") == "hero_video"), 4)
    if ep.stage == Stage.AUDIO.value:
        chars = sum(len(s.get("narration", "")) + sum(len(d.get("line", "")) for d in (s.get("dialogue") or []))
                    for s in ep.scenes)
        lip = sum(pricing.lipsync_cost(None, s.get("duration_s", 5))
                  for s in ep.scenes if s.get("shot_type") == "lipsync_still")
        music = pricing.music_cost(None, sum(s.get("duration_s", 5) for s in ep.scenes))
        return round(pricing.tts_cost(None, chars) + lip + music, 4)
    return 0.0


def _cast_chars(cs: CharacterStore, ep: Episode, ch: Channel) -> list[Character]:
    ids = ep.cast or ch.cast_ids()
    out = [cs.get(cid) for cid in ids]
    return [c for c in out if c]


def _ctx(store, ep: Episode) -> tuple[EpisodeStore, ChannelStore, CharacterStore, Channel, list[Character]]:
    eps, chs, cs = EpisodeStore(store), ChannelStore(store), CharacterStore(store)
    ch = chs.get(ep.channel_id)
    if not ch:
        raise StageError("channel not found for episode")
    return eps, chs, cs, ch, _cast_chars(cs, ep, ch)


def _cast_map(cs: CharacterStore, ids: list[str]) -> dict[str, Character]:
    out = {}
    for cid in ids:
        c = cs.get(cid)
        if c:
            out[cid] = c
    return out


def _image_gen(*, prompt: str, output_path: str, reference_image_urls, model: str, safety: int):
    """Route to OpenRouter (Gemini) or fal based on the model. Same GenResult either way."""
    if model in pricing.OPENROUTER_IMAGE_MODELS:
        return or_image_cap.generate_still(prompt=prompt, output_path=output_path,
                                           reference_image_urls=reference_image_urls, model=model,
                                           execute=True)
    return fal_image.generate_still(prompt=prompt, output_path=output_path,
                                    reference_image_urls=reference_image_urls, model=model,
                                    safety_tolerance=safety, execute=True)


def _gen_scene_still(scene: dict, cast_map: dict[str, Character], ch: Channel,
                     out_dir: Path, *, prompt_override: str | None = None,
                     style_note: str = "") -> tuple[dict, float]:
    present = shot_prompt.scene_cast(scene, cast_map)
    prompt, refs = shot_prompt.reference_still_prompt(scene, present, ch)
    if prompt_override:
        prompt = prompt_override
    if style_note:
        prompt = f"{prompt} {style_note}"
    safety = max([c.safety_tolerance for c in present], default=5)
    path = str(out_dir / "stills" / f"{scene['seq']:03d}.png")
    res = _image_gen(prompt=prompt, output_path=path, reference_image_urls=refs or None,
                     model=pricing.default_image_model(), safety=safety)
    info = {"path": path if res.success else "", "status": "ok" if res.success else "failed",
            "prompt": prompt, "error": res.error}
    return info, res.cost_usd


def _gen_scene_clip(scene: dict, cast_map: dict[str, Character], ch: Channel, spec: OutputSpec,
                    out_dir: Path) -> tuple[dict, float]:
    present = shot_prompt.scene_cast(scene, cast_map)
    still = (scene.get("reference_image") or {}).get("path")
    if not still:
        return {"status": "failed", "error": "no reference image"}, 0.0
    path = str(out_dir / "clips" / f"{scene['seq']:03d}.mp4")
    res = fal_video.generate_video(prompt=shot_prompt.motion_prompt(scene, present, ch),
                                   image_url=image_ref(still), output_path=path,
                                   model=pricing.DEFAULT_VIDEO_MODEL,
                                   duration_s=scene.get("duration_s", 5),
                                   aspect_ratio=spec.aspect_ratio, execute=True)
    info = {"path": path if res.success else "", "status": "ok" if res.success else "failed",
            "error": res.error}
    return info, res.cost_usd


def _sarvam_on() -> bool:
    """True only when a real (non-comment, non-blank) SARVAM_API_KEY is present."""
    from .capabilities import sarvam_voice
    return sarvam_voice._key() is not None


def _voice_opts(char: Character | None) -> tuple[str, str, str | None]:
    """(model, voice_id, clone_audio) for a character's Voice DNA. Prefers Sarvam (authentic
    Indian voices) when the character opts in AND SARVAM_API_KEY is set; else ElevenLabs."""
    v = (char.voice if char else {}) or {}
    provider = v.get("provider", "elevenlabs")
    if provider == "sarvam" and _sarvam_on():
        return "sarvam-bulbul", (v.get("sarvam_speaker") or "abhilash"), None
    model = v.get("model") or ("chatterbox" if provider == "chatterbox" else pricing.DEFAULT_TTS_MODEL)
    return model, (v.get("voice_id") or "Rachel"), v.get("clone_audio")


def _narrator_opts(ch: Channel) -> tuple[str, str]:
    """(model, voice) for channel narration — Sarvam for a Hindi channel when the key is set."""
    if (getattr(ch, "language", "") or "").lower() == "hindi" and _sarvam_on():
        return "sarvam-bulbul", "hitesh"
    return pricing.DEFAULT_TTS_MODEL, (ch.narrator_voice_id or "Rachel")


def _concat_audio(paths: list[str], out_path: str) -> bool:
    if len(paths) == 1:
        shutil.copy(paths[0], out_path)
        return True
    cmd = [FFMPEG, "-y"]
    for p in paths:
        cmd += ["-i", p]
    inp = "".join(f"[{i}:a]" for i in range(len(paths)))
    cmd += ["-filter_complex", f"{inp}concat=n={len(paths)}:v=0:a=1[a]", "-map", "[a]",
            "-c:a", "libmp3lame", "-b:a", "128k", out_path]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def _scene_voice(scene: dict, cast_map: dict[str, Character], ch: Channel, out_dir: Path,
                 *, execute: bool = True) -> tuple[str | None, float]:
    """Render a scene's voice track: narrator VO + each dialogue line in its speaker's voice. Returns
    (audio_path|None, cost)."""
    seq = scene["seq"]
    adir = out_dir / "audio"
    parts, cost = [], 0.0
    narr = (scene.get("narration") or "").strip()
    if narr:
        p = str(adir / f"{seq:03d}_narr.mp3")
        n_model, n_voice = _narrator_opts(ch)
        r = voice_cap.speak(text=narr, output_path=p, voice_id=n_voice, model=n_model,
                            execute=execute)
        if r.ok:
            parts.append(p); cost += r.cost_usd
    for k, line in enumerate(scene.get("dialogue") or []):
        txt = (line.get("line") or "").strip()
        if not txt:
            continue
        spk = cast_map.get(line.get("speaker"))
        model, vid, clone = _voice_opts(spk)
        p = str(adir / f"{seq:03d}_d{k}.mp3")
        r = voice_cap.speak(text=txt, output_path=p, voice_id=vid, model=model, clone_audio=clone,
                            execute=execute)
        if r.ok:
            parts.append(p); cost += r.cost_usd
    if not parts:
        return None, cost
    if len(parts) == 1:
        return parts[0], cost
    out = str(adir / f"{seq:03d}_voice.mp3")
    _concat_audio(parts, out)
    return out, cost


def _music_prompt(ch: Channel) -> str:
    style = ch.art_style or "cinematic"
    return (f"{style} instrumental background score for a {ch.format.replace('_', ' ')} titled "
            f"'{ch.name}'. {ch.premise[:160]}. Subtle, non-distracting, loopable.")


def _shot_for_scene(scene: dict) -> ScoredShot:
    """Build the scored shot from a scene's already-generated media/audio."""
    audio = scene.get("audio") or {}
    dur = scene.get("duration_s", 5)
    if scene.get("shot_type") == "lipsync_still" and audio.get("talk"):
        return ScoredShot("talking", audio["talk"], dur)
    voice = audio.get("voice")
    if scene.get("shot_type") == "hero_video" and (scene.get("clip") or {}).get("status") == "ok":
        return ScoredShot("video", scene["clip"]["path"], dur, audio_path=voice)
    still = (scene.get("reference_image") or {}).get("path")
    zoom = "in" if scene["seq"] % 2 == 0 else "out"
    return ScoredShot("kenburns", still, dur, audio_path=voice, zoom=zoom)


def _assemble_audio_cut(ep: Episode, ch: Channel, *, regen_music: bool = False,
                        execute: bool = True) -> tuple[bool, str, float]:
    """Assemble the voiced+scored cut from each scene's stored audio; (re)generate the music bed."""
    out_dir = _out_dir(ep)
    total_dur = round(sum(s.get("duration_s", 5) for s in ep.scenes), 2)
    music_path = (ep.timeline or {}).get("music")
    cost = 0.0
    if regen_music or not music_path or not Path(music_path or "").is_file():
        music_path = str(out_dir / "music.mp3")
        mr = music_cap.generate(prompt=_music_prompt(ch), output_path=music_path,
                                duration_s=total_dur, execute=execute)
        cost += mr.cost_usd
        if not mr.ok:
            music_path = None
    shots = [_shot_for_scene(s) for s in ep.scenes]
    audio_cut = str(out_dir / "audio_cut.mp4")
    fr = assemble_scored(shots, audio_cut, spec=channel_spec(ch), music_path=music_path)
    if not fr.success:
        return False, fr.error or "assembly failed", cost
    ep.timeline = {**(ep.timeline or {}), "audio_cut": audio_cut, "music": music_path,
                   "probe": fr.probe, "silent": False}
    return True, "", cost


def _assemble_rough(ep: Episode, ch: Channel) -> tuple[bool, str]:
    """Assemble the silent rough cut: Ken Burns on stills, hero clips inline, crossfade transitions."""
    spec = channel_spec(ch)
    medias: list[ShotMedia] = []
    for scene in ep.scenes:
        if scene.get("shot_type") == "hero_video" and (scene.get("clip") or {}).get("status") == "ok":
            medias.append(ShotMedia("video", scene["clip"]["path"], scene.get("duration_s", 5)))
        else:
            still = (scene.get("reference_image") or {}).get("path")
            if not still:
                return False, f"scene {scene['seq']} has no reference image"
            zoom = "in" if scene["seq"] % 2 == 0 else "out"
            medias.append(ShotMedia("kenburns", still, scene.get("duration_s", 5), zoom=zoom))
    rough = str(_out_dir(ep) / "rough_cut.mp4")
    fr = assemble(medias, rough, spec=spec, transition_s=0.4)
    if fr.success:
        ep.timeline = {"rough_cut": rough, "probe": fr.probe, "silent": True}
    return fr.success, fr.error or ""


# --------------------------------------------------------------------------- run (generate stage)

def run_stage(store, ep: Episode, *, brief: str | None = None, style_note: str | None = None) -> Episode:
    """Generate the current stage's artifact and park at awaiting_review. `brief` steers ideation;
    `style_note` steers reference-image look (applied to the preview + batch)."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    ep.writer_model = ch.writer_model or writer.default_model()
    ep.stage_status = StageStatus.GENERATING.value
    ep.stage_error = ""
    eps.update(ep)

    stage = Stage(ep.stage)
    if stage == Stage.IDEA:
        if brief is not None:
            ep.idea_brief = brief.strip()
        recent = [e.title for e in eps.list(_tenant_of(ep, eps), ch.channel_id) if e.episode_id != ep.episode_id]
        # Multi-model panel: every model proposes ideas concurrently so you pick the best across them.
        res = writer.ideate_panel(ch, cast, recent_titles=recent, brief=(ep.idea_brief or None))
        if not res.ok:
            return _fail(eps, ep, res.error or "ideation failed")
        ep.idea_candidates = res.data["ideas"]
        _bill(ep, res)
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("ideate", {"n": len(ep.idea_candidates),
                          "models": [c.get("model_label") for c in ep.idea_candidates],
                          "cost_usd": res.cost_usd})

    elif stage == Stage.SCRIPT:
        if not ep.idea:
            return _fail(eps, ep, "approve an idea before scripting")
        res = writer.script(ch, cast, ep.idea, model=ep.writer_model)
        if not res.ok:
            return _fail(eps, ep, res.error or "scripting failed")
        ep.scenes = res.data["scenes"]
        ep.refs_batch_done = False          # fresh script -> old reference batch is invalid
        _bill(ep, res)
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("script", {"scenes": len(ep.scenes), "model": res.model, "stub": res.stubbed})

    elif stage == Stage.REFS:
        if not ep.scenes:
            return _fail(eps, ep, "approve a script before generating reference images")
        if style_note is not None:
            ep.style_note = style_note.strip()
        # PREVIEW-FIRST: generate one representative still so you can approve the LOOK (style +
        # character identity) before spending on the whole batch. Prefer the first scene that
        # actually features the cast (so you see the character, not an empty establishing shot).
        cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
        out_dir = _out_dir(ep)
        pidx = next((i for i, s in enumerate(ep.scenes) if s.get("cast_present")), 0)
        preview = ep.scenes[pidx]
        info, cost = _gen_scene_still(preview, cast_map, ch, out_dir, style_note=ep.style_note)
        preview["reference_image"] = info
        for i, scene in enumerate(ep.scenes):     # a fresh preview invalidates any prior batch
            if i != pidx:
                scene["reference_image"] = {}
        ep.refs_batch_done = False
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("refs_preview", {"status": info["status"], "cost_usd": round(cost, 4)})

    elif stage == Stage.SCENES:
        return generate_scenes(store, ep)

    elif stage == Stage.AUDIO:
        return generate_audio(store, ep)

    elif stage == Stage.ASSEMBLY:
        audio_cut = (ep.timeline or {}).get("audio_cut")
        if not audio_cut or not Path(audio_cut).is_file():
            return _fail(eps, ep, "run the audio stage first")
        final = str(_out_dir(ep) / "final.mp4")
        shutil.copy(audio_cut, final)
        edl = [{"seq": s["seq"], "shot_type": s.get("shot_type"), "duration_s": s.get("duration_s"),
                "heading": s.get("heading")} for s in ep.scenes]
        ep.timeline = {**(ep.timeline or {}), "final_video": final, "edl": edl}
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("assembly", {"scenes": len(ep.scenes)})

    else:
        return _fail(eps, ep, f"stage '{stage.value}' runs in a later milestone")

    return eps.update(ep)


def reroll_scene(store, ep: Episode, *, seq: int, prompt_override: str | None = None) -> Episode:
    """Regenerate one scene's asset for the current stage (per-asset re-roll at the gate)."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    scene = next((s for s in ep.scenes if s.get("seq") == seq), None)
    if not scene:
        raise StageError(f"scene {seq} not found")
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    out_dir = _out_dir(ep)
    if ep.stage == Stage.REFS.value:
        info, cost = _gen_scene_still(scene, cast_map, ch, out_dir, prompt_override=prompt_override,
                                      style_note=ep.style_note)
        scene["reference_image"] = info
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        ep.log("ref_reroll", {"seq": seq, "status": info["status"], "cost_usd": cost})
    elif ep.stage == Stage.SCENES.value:
        if scene.get("shot_type") == "hero_video":
            info, cost = _gen_scene_clip(scene, cast_map, ch, channel_spec(ch), out_dir)
            scene["clip"] = info
            ep.spent_usd = round(ep.spent_usd + cost, 4)
        _assemble_rough(ep, ch)             # rebuild the rough cut with the new asset
        ep.log("scene_reroll", {"seq": seq})
    elif ep.stage == Stage.AUDIO.value:
        vpath, vcost = _scene_voice(scene, cast_map, ch, out_dir)
        ep.spent_usd = round(ep.spent_usd + vcost, 4)
        if scene.get("shot_type") == "lipsync_still" and vpath:
            still = (scene.get("reference_image") or {}).get("path")
            talk = str(out_dir / "talk" / f"{scene['seq']:03d}.mp4")
            lr = lipsync_cap.lipsync(image_path=still, audio_path=vpath, output_path=talk, resolution="720p")
            ep.spent_usd = round(ep.spent_usd + lr.cost_usd, 4)
            scene["duration_s"] = round(lr.duration_s or scene.get("duration_s", 5), 2)
            scene["audio"] = {"voice": vpath, "talk": (talk if lr.ok else None)}
        else:
            if vpath:
                scene["duration_s"] = round(max(scene.get("duration_s", 5), media_duration(vpath) + 0.4), 2)
            scene["audio"] = {"voice": vpath}
        _assemble_audio_cut(ep, ch, regen_music=False)   # reuse existing music bed
        ep.log("audio_reroll", {"seq": seq})
    else:
        raise StageError(f"nothing to re-roll at stage '{ep.stage}'")
    return eps.update(ep)


def generate_refs_batch(store, ep: Episode, *, style_note: str | None = None) -> Episode:
    """After the preview is approved, generate reference images for all remaining scenes."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    if ep.stage != Stage.REFS.value:
        raise StageError("not at the reference-image stage")
    if not any((s.get("reference_image") or {}).get("status") == "ok" for s in ep.scenes):
        raise StageError("generate a preview first")
    if style_note is not None:
        ep.style_note = style_note.strip()
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    out_dir = _out_dir(ep)
    pending = [s for s in ep.scenes if (s.get("reference_image") or {}).get("status") != "ok"]
    est = round(len(pending) * pricing.image_cost(pricing.default_image_model()), 4)
    if est > episode_ceiling_usd():
        raise StageError(f"batch est ${est} over episode ceiling ${episode_ceiling_usd()}")
    spent, failed = 0.0, 0
    for scene in pending:
        info, cost = _gen_scene_still(scene, cast_map, ch, out_dir, style_note=ep.style_note)
        scene["reference_image"] = info
        spent += cost
        failed += (info["status"] != "ok")
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        eps.update(ep)                       # persist per-image so a live poll sees the grid fill
    ep.refs_batch_done = True
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("refs_batch", {"generated": len(pending), "failed": failed, "cost_usd": round(spent, 4)})
    return eps.update(ep)


def generate_scenes(store, ep: Episode) -> Episode:
    """Render the shot-type mix (hero videos + Ken Burns) into a silent rough cut. Persists per shot
    so a live poll sees clips appear one by one."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    if not ep.scenes or not all((s.get("reference_image") or {}).get("status") == "ok" for s in ep.scenes):
        return _fail(eps, ep, "generate + approve reference images first")
    est = stage_estimate(ep)
    if est > episode_ceiling_usd():
        return _fail(eps, ep, f"est ${est} over episode ceiling ${episode_ceiling_usd()}")
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    spec = channel_spec(ch)
    out_dir = _out_dir(ep)
    spent, failed = 0.0, 0
    for scene in ep.scenes:
        if scene.get("shot_type") == "hero_video":
            cl = scene.get("clip") or {}
            if cl.get("status") == "ok" and Path(cl.get("path", "")).is_file():
                pass                               # already generated — never re-charge on retry
            else:
                info, cost = _gen_scene_clip(scene, cast_map, ch, spec, out_dir)
                scene["clip"] = info
                spent += cost
                failed += (info["status"] != "ok")
                ep.spent_usd = round(ep.spent_usd + cost, 4)
        else:
            scene["clip"] = {"status": "kenburns"}   # marks it "done" (free) for the live grid
        eps.update(ep)
    ok, err = _assemble_rough(ep, ch)
    if not ok:
        return _fail(eps, ep, f"rough-cut assembly failed: {err}")
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("scenes", {"hero_videos": sum(1 for s in ep.scenes if s.get("shot_type") == "hero_video"),
                      "failed": failed, "cost_usd": round(spent, 4)})
    return eps.update(ep)


def generate_audio(store, ep: Episode) -> Episode:
    """Voices + lip-sync + music into a scored cut. Persists per scene for the live grid."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    if not ep.scenes or not all((s.get("reference_image") or {}).get("status") == "ok" for s in ep.scenes):
        return _fail(eps, ep, "generate + approve reference images and scenes first")
    est = stage_estimate(ep)
    if est > episode_ceiling_usd():
        return _fail(eps, ep, f"est ${est} over episode ceiling ${episode_ceiling_usd()}")
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    out_dir = _out_dir(ep)
    spent = 0.0
    for scene in ep.scenes:
        au = scene.get("audio") or {}
        if au.get("status") == "ok" and (not au.get("voice") or Path(au.get("voice", "")).is_file()):
            continue                               # already voiced — don't re-charge on retry
        vpath, vcost = _scene_voice(scene, cast_map, ch, out_dir)
        spent += vcost
        if scene.get("shot_type") == "lipsync_still" and vpath:
            still = (scene.get("reference_image") or {}).get("path")
            talk = str(out_dir / "talk" / f"{scene['seq']:03d}.mp4")
            lr = lipsync_cap.lipsync(image_path=still, audio_path=vpath, output_path=talk, resolution="720p")
            spent += lr.cost_usd
            scene["duration_s"] = round(lr.duration_s or scene.get("duration_s", 5), 2)
            scene["audio"] = {"voice": vpath, "talk": (talk if lr.ok else None), "status": "ok"}
        else:
            if vpath:
                scene["duration_s"] = round(max(scene.get("duration_s", 5), media_duration(vpath) + 0.4), 2)
            scene["audio"] = {"voice": vpath, "status": "ok"}
        ep.spent_usd = round(ep.spent_usd + vcost, 4)
        eps.update(ep)
    ok, err, mcost = _assemble_audio_cut(ep, ch, regen_music=False)   # reuse music on retry
    ep.spent_usd = round(ep.spent_usd + mcost, 4)
    if not ok:
        return _fail(eps, ep, f"audio assembly failed: {err}")
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("audio", {"cost_usd": round(spent + mcost, 4),
                     "duration_s": (ep.timeline.get("probe") or {}).get("duration_s")})
    return eps.update(ep)


# --------------------------------------------------------------------------- gate actions

def approve_stage(store, ep: Episode, *, payload: dict[str, Any] | None = None) -> Episode:
    """Approve the current stage's artifact and advance to the next stage (pending)."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    payload = payload or {}
    stage = Stage(ep.stage)

    if stage == Stage.IDEA:
        chosen = payload.get("idea")
        if chosen is None:
            idx = int(payload.get("choice", 0))
            if idx < 0 or idx >= len(ep.idea_candidates):
                raise StageError("choice out of range")
            chosen = ep.idea_candidates[idx]
        ep.idea = chosen
        ep.title = (chosen.get("title") or ep.title)
        ep.logline = chosen.get("logline", "")
        # Script with the SAME model that authored the chosen idea (falls back to channel default).
        if chosen.get("model"):
            ep.writer_model = chosen["model"]
        ep.log("idea_approved", {"title": ep.title, "model": chosen.get("model_label")})
    elif stage == Stage.SCRIPT:
        if payload.get("scenes"):                 # accept human-edited scenes
            ep.scenes = payload["scenes"]
        if not ep.scenes:
            raise StageError("no script to approve")
        ep.log("script_approved", {"scenes": len(ep.scenes)})
    elif stage == Stage.REFS:
        if not ep.refs_batch_done:
            raise StageError("approve the preview and generate the full batch first")
        if not all((s.get("reference_image") or {}).get("status") == "ok" for s in ep.scenes):
            raise StageError("some reference images failed — re-roll them before approving")
        ep.log("refs_approved", {"scenes": len(ep.scenes)})
    elif stage == Stage.SCENES:
        if not (ep.timeline or {}).get("rough_cut"):
            raise StageError("no rough cut to approve")
        ep.log("scenes_approved", {})
    elif stage == Stage.AUDIO:
        if not (ep.timeline or {}).get("audio_cut"):
            raise StageError("no audio cut to approve")
        ep.log("audio_approved", {})
    elif stage == Stage.ASSEMBLY:
        if not (ep.timeline or {}).get("final_video"):
            raise StageError("no final video to approve")
        ep.log("assembly_approved", {})
    else:
        raise StageError(f"stage '{stage.value}' cannot be approved yet")

    ep.stage = next_stage(stage).value
    ep.stage_status = (StageStatus.APPROVED.value if ep.stage == Stage.DONE.value
                       else StageStatus.PENDING.value)
    ep.stage_error = ""
    return eps.update(ep)


def reject_stage(store, ep: Episode, *, reason: str = "") -> Episode:
    """Reject the current artifact — reset it to pending so it can be re-run."""
    eps = EpisodeStore(store)
    stage = Stage(ep.stage)
    if stage == Stage.IDEA:
        ep.idea_candidates = []
    elif stage == Stage.SCRIPT:
        ep.scenes = []
    ep.stage_status = StageStatus.PENDING.value
    ep.log("rejected", {"reason": reason or "rejected"})
    return eps.update(ep)


def edit_artifact(store, ep: Episode, *, idea: dict[str, Any] | None = None,
                  scenes: list[dict[str, Any]] | None = None) -> Episode:
    """Hand-edit the current artifact in place (the Edit gate action)."""
    eps = EpisodeStore(store)
    if idea is not None:
        ep.idea = idea
        ep.title = idea.get("title", ep.title)
        ep.log("idea_edited", {})
    if scenes is not None:
        ep.scenes = scenes
        ep.log("script_edited", {"scenes": len(scenes)})
    return eps.update(ep)


def reopen_stage(store, ep: Episode, *, stage: str) -> Episode:
    """Re-open a previously-approved stage so it can be edited or re-run. Sets it as the current
    stage, awaiting review, so run_stage / edit_artifact apply to it again. Downstream stages are
    left as-is on disk but fall 'behind' the pointer, so the stepper shows they need re-running."""
    eps = EpisodeStore(store)
    valid = {s.value for s in Stage}
    if stage not in valid:
        return _fail(eps, ep, f"unknown stage '{stage}'")
    ep.stage = stage
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.stage_error = ""
    ep.log("reopen", {"stage": stage})
    return eps.update(ep)


# --------------------------------------------------------------------------- helpers

def _fail(eps: EpisodeStore, ep: Episode, msg: str) -> Episode:
    ep.stage_status = StageStatus.PENDING.value
    ep.stage_error = msg
    ep.log("stage_error", {"error": msg})
    return eps.update(ep)


def _bill(ep: Episode, res) -> None:
    ep.spent_usd = round(ep.spent_usd + float(res.cost_usd or 0.0), 4)


def _tenant_of(ep: Episode, eps: EpisodeStore) -> str:
    row = eps.conn.execute("SELECT tenant_id FROM episodes WHERE episode_id=?",
                           (ep.episode_id,)).fetchone()
    return row["tenant_id"] if row else "factory"
