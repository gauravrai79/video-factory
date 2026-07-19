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
from .finishing import (FFMPEG, ScoredShot, ShotMedia, assemble, assemble_scored, media_duration,
                        speech_end)
from .spec import OutputSpec, get_spec


class StageError(RuntimeError):
    pass


def episode_ceiling_usd() -> float:
    """Per-episode per-stage spend ceiling (safety net over the human commit-spend gate)."""
    return float(os.environ.get("VF_EPISODE_CEILING_USD", "25"))


def channel_spec(ch: Channel) -> OutputSpec:
    """Map the channel format to an output spec: long-form -> landscape, short-form -> vertical reel."""
    return get_spec("reel" if ch.is_short() else "landscape")


def episode_spec(ep: Episode, ch: Channel) -> OutputSpec:
    """The per-episode render spec from its Setup config (layout/resolution/length)."""
    from . import formats
    return formats.episode_spec(ep, ch)


def _out_dir(ep: Episode) -> Path:
    return Path(os.environ.get("VF_OUT_DIR", "out")) / "episodes" / ep.episode_id


def _episode_resolution(ep: Episode) -> str:
    from . import formats
    ch = ChannelStore(EpisodeStore().store).get(ep.channel_id) if ep.channel_id else None
    return formats.episode_config(ep, ch)["resolution"]


def stage_estimate(ep: Episode) -> float:
    """Estimated USD to run the current stage (shown before the paid gate)."""
    if ep.stage == Stage.REFS.value:
        return round(len(ep.scenes) * pricing.image_cost(None), 4)
    if ep.stage == Stage.SCENES.value:
        res = _episode_resolution(ep)
        return round(sum(fal_video.veo_lite_billed_cost(s.get("duration_s", 6), res, audio=True)
                         for s in ep.scenes if not s.get("asset_path")), 4)   # asset scenes are $0
    if ep.stage == Stage.AUDIO.value:                 # native audio is already in the clips; only music
        return round(pricing.music_cost(None, sum(s.get("duration_s", 6) for s in ep.scenes)), 4)
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


def _image_gen(*, prompt: str, output_path: str, reference_image_urls, model: str, safety: int,
               aspect_ratio: str = "16:9"):
    """Route to OpenRouter (Gemini) or fal based on the model. Same GenResult either way."""
    if model in pricing.OPENROUTER_IMAGE_MODELS:
        return or_image_cap.generate_still(prompt=prompt, output_path=output_path,
                                           reference_image_urls=reference_image_urls, model=model,
                                           aspect_ratio=aspect_ratio, execute=True)
    return fal_image.generate_still(prompt=prompt, output_path=output_path,
                                    reference_image_urls=reference_image_urls, model=model,
                                    safety_tolerance=safety, aspect_ratio=aspect_ratio, execute=True)


def _gen_scene_still(scene: dict, cast_map: dict[str, Character], ch: Channel,
                     out_dir: Path, *, prompt_override: str | None = None, style_note: str = "",
                     model: str | None = None, framing: str = "", aspect_ratio: str = "16:9",
                     location_ref: str | None = None) -> tuple[dict, float]:
    """`location_ref` is an earlier still of the SAME location — passed as an extra reference so a
    recurring place stays the same place across independently-generated scenes (the #1 cause of an
    incoherent cut: every scene inventing its own version of the same street)."""
    present = shot_prompt.scene_cast(scene, cast_map)
    prompt, refs = shot_prompt.reference_still_prompt(scene, present, ch, framing=framing)
    # A one-off/ad scene carries the author's exact keyframe prompt — honor it verbatim.
    stored_override = (scene.get("still_prompt_override") or "").strip()
    if prompt_override:
        prompt = prompt_override
    elif stored_override:
        prompt = stored_override
    if style_note:
        prompt = f"{prompt} {style_note}"
    if location_ref and Path(location_ref).is_file():
        refs = list(refs) + [location_ref]
        prompt = (prompt + " CONTINUITY — one of the reference images is an earlier shot of THIS "
                  "EXACT SAME location: reproduce the same place, architecture, background, signage, "
                  "props and time of day; only the camera angle and the characters' action change.")
    safety = max([c.safety_tolerance for c in present], default=5)
    path = str(out_dir / "stills" / f"{scene['seq']:03d}.png")
    model = model or pricing.default_image_model()
    res = _image_gen(prompt=prompt, output_path=path, reference_image_urls=refs or None,
                     model=model, safety=safety, aspect_ratio=aspect_ratio)
    cost = res.cost_usd
    # Self-heal a content-filter refusal: retry ONCE with safety-softened wording so one graphic
    # beat doesn't block the whole batch (this was a real failure mode — a violent crash shot).
    if not res.success and "refus" in (res.error or "").lower():
        soft = (prompt + " Keep it non-graphic, comedic and cartoon-safe: no injury, blood, gore, "
                "or realistic harm; stylised slapstick only.")
        res = _image_gen(prompt=soft, output_path=path, reference_image_urls=refs or None,
                         model=model, safety=safety, aspect_ratio=aspect_ratio)
        cost += res.cost_usd
        if res.success:
            prompt = soft
    qc = None
    if res.success and not prompt_override:
        # Gate 2 (vision QC): does the keyframe serve the scene's intent? One corrective retry.
        from .agents import media_qc
        names = [c.name for c in present]
        v = media_qc.qc_still(path, scene, names)
        cost += v.cost_usd
        if v.ok and not v.passed:
            fixed = prompt + media_qc.corrective_suffix(v.reasons)
            res2 = _image_gen(prompt=fixed, output_path=path, reference_image_urls=refs or None,
                              model=model, safety=safety, aspect_ratio=aspect_ratio)
            cost += res2.cost_usd
            if res2.success:
                prompt = fixed
                v2 = media_qc.qc_still(path, scene, names)
                cost += v2.cost_usd
                v = v2 if v2.ok else v
        qc = v.as_dict() if v.ok else None
    info = {"path": path if res.success else "", "status": "ok" if res.success else "failed",
            "prompt": prompt, "model": model, "error": res.error, "qc": qc}
    return info, cost


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


def _asset_clip(scene: dict, spec: OutputSpec, out_dir: Path) -> tuple[dict, float]:
    """Build a scene clip from a REAL uploaded asset (no generation, $0): an image is animated with a
    subtle Ken-Burns move (direction from the scene's asset_motion), a video is trimmed + conformed to
    spec. Silent — the global voiceover/music carries the audio."""
    from .finishing import asset_image_clip, normalize_video_shot
    ap = scene.get("asset_path")
    if not ap or not Path(ap).is_file():
        return {"status": "failed", "error": "asset file missing", "asset": True}, 0.0
    out = str(out_dir / "clips" / f"{scene['seq']:03d}.mp4")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    dur = float(scene.get("duration_s", 6) or 6)
    if scene.get("asset_kind") == "video":
        ok = normalize_video_shot(ap, out, duration_s=dur, spec=spec, keep_audio=False)
    else:
        direction = "out" if "out" in (scene.get("asset_motion") or "").lower() else "in"
        ok = asset_image_clip(ap, out, duration_s=dur, spec=spec, direction=direction)
    if not ok:
        return {"status": "failed", "error": "asset clip render failed", "asset": True}, 0.0
    return {"path": out, "status": "ok", "has_audio": False, "has_speech": False, "asset": True,
            "prompt": f"[asset: {Path(ap).name}]", "cost": 0.0}, 0.0


def _scene_has_speech(scene: dict) -> bool:
    dlg = next((d for d in (scene.get("dialogue") or [])
                if isinstance(d, dict) and (d.get("line") or "").strip()), None)
    return bool(dlg) or bool((scene.get("narration") or "").strip())


def _speech_seconds(scene: dict) -> float:
    """Seconds the scene's spoken line needs (Hindi/Devanagari ~12 chars/s + a breath). 0 = silent."""
    dlg = next((d for d in (scene.get("dialogue") or [])
                if isinstance(d, dict) and (d.get("line") or "").strip()), None)
    text = (dlg.get("line", "") if dlg else "") or (scene.get("narration") or "")
    text = text.strip()
    return round(len(text) / 12.0 + 1.2, 1) if text else 0.0


def _gen_scene_veo(scene: dict, cast_map: dict[str, Character], ch: Channel,
                   out_dir: Path, *, aspect: str = "16:9", resolution: str = "720p") -> tuple[dict, float]:
    """Render ONE scene as a Veo 3.1 Lite clip: motion + native audio generated in a single pass from
    the scene's reference still. EVERY clip gets audio (dialogue+lip-sync when there's a line, ambient
    sound/SFX otherwise — dead-silent clips read as broken), and the clip duration is stretched to
    FIT the spoken line so lip-sync isn't rushed. Aspect + resolution come from the episode config."""
    present = shot_prompt.scene_cast(scene, cast_map)
    still = (scene.get("reference_image") or {}).get("path")
    if not still:
        return {"status": "failed", "error": "no reference image"}, 0.0
    speech = _scene_has_speech(scene)
    res_ = resolution if resolution in ("720p", "1080p") else "720p"
    path = str(out_dir / "clips" / f"{scene['seq']:03d}.mp4")
    prompt = (scene.get("veo_prompt_override") or "").strip() or shot_prompt.veo_prompt(scene, present, ch)
    # duration must FIT the line (rushed lip-sync looks broken); writer caps lines at ~80 chars
    dur = max(float(scene.get("duration_s", 6) or 6), _speech_seconds(scene))
    res = fal_video.generate_native_video(
        prompt=prompt, image_url=image_ref(still),
        output_path=path, duration_s=dur, resolution=res_,
        generate_audio=True, aspect_ratio=aspect, execute=True)
    cost = res.cost_usd
    qc = None
    if res.success and not (scene.get("veo_prompt_override") or "").strip():
        # Gate 3 (vision QC): sampled frames vs the scene's intent. One corrective retry.
        from .agents import media_qc
        names = [c.name for c in present]
        v = media_qc.qc_clip(path, scene, names)
        cost += v.cost_usd
        if v.ok and not v.passed:
            fixed = prompt + media_qc.corrective_suffix(v.reasons)
            res2 = fal_video.generate_native_video(
                prompt=fixed, image_url=image_ref(still), output_path=path, duration_s=dur,
                resolution=res_, generate_audio=True, aspect_ratio=aspect, execute=True)
            cost += res2.cost_usd
            if res2.success:
                res, prompt = res2, fixed
                v2 = media_qc.qc_clip(path, scene, names)
                cost += v2.cost_usd
                v = v2 if v2.ok else v
        qc = v.as_dict() if v.ok else None
    info = {"path": path if res.success else "", "status": "ok" if res.success else "failed",
            "prompt": prompt, "error": res.error, "has_audio": res.success,
            "has_speech": bool(speech), "cost": round(cost, 4), "qc": qc}
    if res.success:
        # Preserve the WRITER's duration (cut rhythm) before snapping to the actual clip length —
        # Veo rounds to 4/6/8s and assembly trims silent clips back to the scripted beat.
        if not scene.get("scripted_duration_s"):
            scene["scripted_duration_s"] = scene.get("duration_s", 6)
        scene["duration_s"] = round(media_duration(path) or scene.get("duration_s", 6), 2)
    return info, cost


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
    """Build the scored shot from a scene's Veo clip, applying CUT-RHYTHM trims (uniform 6-8s clips
    laid end-to-end read as amateur):
      - dialogue clips ('talking'): NEVER cut into speech — only trim trailing dead air after the
        line ends (silence-detected), keeping a small breath.
      - silent clips ('video'): trim back to the writer's scripted beat length (Veo rounds up to
        4/6/8s), so shot lengths vary with the script's rhythm again.
    A missing clip falls back to a Ken-Burns pan so assembly never hard-fails."""
    clip = scene.get("clip") or {}
    actual = scene.get("duration_s", 6)
    scripted = scene.get("scripted_duration_s") or actual
    if clip.get("status") == "ok" and clip.get("path"):
        # Every Veo clip carries its own audio (speech or ambient) -> 'talking' keeps it through
        # assembly. Speech clips only trim trailing dead air (never into the line); ambient clips
        # trim back to the scripted beat length for cut rhythm.
        if clip.get("has_speech"):
            dur = actual
            end = speech_end(clip["path"])
            if end:                                       # trailing dead air -> trim to line + breath
                dur = round(min(actual, end + 0.35), 2)
            return ScoredShot("talking", clip["path"], dur)
        dur = round(min(actual, max(scripted, 1.5)), 2)
        mode = "talking" if clip.get("has_audio") else "video"
        return ScoredShot(mode, clip["path"], dur)
    still = (scene.get("reference_image") or {}).get("path")
    zoom = "in" if scene["seq"] % 2 == 0 else "out"
    return ScoredShot("kenburns", still, min(actual, max(scripted, 1.5)), zoom=zoom)


def _assemble_scenes_cut(ep: Episode, ch: Channel, *, music_path: str | None = None,
                         out_name: str = "final.mp4", out_key: str = "final_video") -> tuple[bool, str]:
    """Concatenate the Veo clips (each keeping its native audio) with transitions spliced per the
    cut-rhythm rules and any human seam overrides, an optional music bed, and loudnorm. This is THE
    stitch — it happens at ASSEMBLY, not at the scenes stage (scenes stay individual clips)."""
    from . import formats, transitions
    kept = [s for s in ep.scenes if (s.get("clip") or {}).get("status") == "ok"]
    shots = [_shot_for_scene(s) for s in kept]
    if not shots:
        return False, "no scene clips to assemble"
    if formats.episode_config(ep, ch).get("transitions") != "off":   # config can disable all transitions
        overrides = (ep.timeline or {}).get("seams") or {}
        shots = transitions.interleave(shots, kept, ch, overrides=overrides)
    out = str(_out_dir(ep) / out_name)
    vo = (ep.timeline or {}).get("voiceover")
    if vo and not Path(vo).is_file():
        vo = None
    fr = assemble_scored(shots, out, spec=episode_spec(ep, ch), music_path=music_path, vo_path=vo)
    if fr.success:
        ep.timeline = {**(ep.timeline or {}), out_key: out, "silent": False, "probe": fr.probe}
    return fr.success, fr.error or ""


def _write_titles(ep: Episode) -> str | None:
    """Write the on-screen-title sidecar (SRT) for a one-off/ad — text-free master + timed titles the
    creator composites externally. Uses authored MD timings when present, else clip durations."""
    titles = (ep.config or {}).get("titles") or []
    if not titles:
        return None

    def ts(sec: float) -> str:
        sec = max(0.0, float(sec)); h = int(sec // 3600); m = int(sec % 3600 // 60)
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
    # fall back to running clip durations when the MD gave no absolute timings
    durs = {s["seq"]: s.get("duration_s", 6) for s in ep.scenes}
    running, srt = 0.0, []
    for i, t in enumerate(titles, 1):
        start = t.get("start_s"); end = t.get("end_s")
        if start is None or end is None:
            start = running; end = running + durs.get(t.get("seq"), 6)
        running = end
        srt.append(f"{i}\n{ts(start)} --> {ts(end)}\n{t['text']}\n")
    path = str(_out_dir(ep) / "titles.srt")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(srt), encoding="utf-8")
    return path


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
    fr = assemble_scored(shots, audio_cut, spec=episode_spec(ep, ch), music_path=music_path)
    if not fr.success:
        return False, fr.error or "assembly failed", cost
    ep.timeline = {**(ep.timeline or {}), "audio_cut": audio_cut, "music": music_path,
                   "probe": fr.probe, "silent": False}
    return True, "", cost


def _assemble_rough(ep: Episode, ch: Channel) -> tuple[bool, str]:
    """Assemble the silent rough cut: Ken Burns on stills, hero clips inline, crossfade transitions."""
    spec = episode_spec(ep, ch)
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

def configure(store, ep: Episode, config: dict[str, Any]) -> Episode:
    """Save the Setup-stage format config and advance to Idea. Validates + normalizes via
    formats.episode_config so downstream stages always read a complete, valid config."""
    from . import formats
    eps, chs, cs, ch, cast = _ctx(store, ep)
    incoming = dict(ep.config or {})
    for k in ("platform", "layout", "duration_s", "scene_count", "resolution", "language",
              "music", "music_hint", "transitions", "qc_threshold", "pacing", "cost_ceiling_usd"):
        if k in (config or {}):
            incoming[k] = config[k]
    incoming["configured"] = True
    ep.config = incoming
    resolved = formats.episode_config(ep, ch)                 # normalize + fill defaults
    ep.config = {**resolved, **{k: v for k, v in incoming.items() if v is not None}}
    if ep.stage == Stage.SETUP.value:                         # first time -> open the pipeline
        ep.stage = Stage.IDEA.value
        ep.stage_status = StageStatus.PENDING.value
    ep.log("configured", {"config": ep.config})
    return eps.update(ep)


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
        from . import formats
        from .agents import script_qc
        cfg = formats.episode_config(ep, ch)
        prior_scenes, prior_qc = list(ep.scenes or []), dict(ep.script_qc or {})   # for revert
        res = writer.script(ch, cast, ep.idea, model=ep.writer_model, cfg=cfg)
        if not res.ok:
            # a REWRITE that fails (e.g. out of credits) must not discard the script you already have
            return _fail_keep_review(eps, ep, res.error or "scripting failed") if ep.scenes \
                else _fail(eps, ep, res.error or "scripting failed")
        _bill(ep, res)
        # QC gate: judge -> (below threshold) targeted revision with the judge's notes -> re-judge,
        # up to MAX_ITERATIONS writer passes. The best-scoring version parks at the human gate with
        # its scorecard either way — the gate informs the human, it never blocks them.
        thr = float(cfg.get("qc_threshold") or script_qc.threshold(ch))
        best_scenes, best_qc = res.data["scenes"], None
        scenes = res.data["scenes"]
        for it in range(1, script_qc.MAX_ITERATIONS + 1):
            q = script_qc.judge(ch, cast, ep.idea, scenes)
            if not q.ok:                        # judge outage -> park what we have, unscored
                best_scenes, best_qc = scenes, {"score": None, "error": q.error}
                break
            _bill(ep, q)
            qc = {**q.data, "iterations": it, "threshold": thr, "judge_model": q.model}
            if best_qc is None or (qc.get("score") or 0) > (best_qc.get("score") or 0):
                best_scenes, best_qc = scenes, qc
            if (qc.get("score") or 0) >= thr or it == script_qc.MAX_ITERATIONS:
                break
            rev = writer.revise_script(ch, cast, ep.idea, scenes, qc.get("notes") or [],
                                       model=ep.writer_model)
            if not rev.ok:
                break
            _bill(ep, rev)
            scenes = rev.data["scenes"]
        ep.scenes = best_scenes
        if best_qc is not None:
            best_qc["passed"] = bool((best_qc.get("score") or 0) >= thr)
            script_qc.attach_intents(ep.scenes, best_qc.pop("intents", []))
            ep.script_qc = best_qc
        if prior_scenes:                    # a rewrite -> stash the prior script so it can be reverted
            ep.script_prev = {"scenes": prior_scenes, "script_qc": prior_qc}
        ep.refs_batch_done = False          # fresh script -> old reference batch is invalid
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("script", {"scenes": len(ep.scenes), "model": res.model, "stub": res.stubbed,
                          "qc_score": (ep.script_qc or {}).get("score"),
                          "qc_iterations": (ep.script_qc or {}).get("iterations")})

    elif stage == Stage.REFS:
        if not ep.scenes:
            return _fail(eps, ep, "approve a script before generating reference images")
        if style_note is not None:
            ep.style_note = style_note.strip()
        # PREVIEW-FIRST: generate one representative still so you can approve the LOOK (style +
        # character identity) before spending on the whole batch. Prefer the first scene that
        # actually features the cast (so you see the character, not an empty establishing shot).
        from . import formats
        cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
        out_dir = _out_dir(ep)
        framing = formats.framing_hint(formats.episode_config(ep, ch))
        # prefer a cast scene; else the first GENERATED (non-asset) scene — never preview an asset
        # scene (its still is the real uploaded file, nothing to generate).
        pidx = next((i for i, s in enumerate(ep.scenes) if s.get("cast_present")), None)
        if pidx is None:
            pidx = next((i for i, s in enumerate(ep.scenes) if not s.get("asset_path")), 0)
        preview = ep.scenes[pidx]
        info, cost = _gen_scene_still(preview, cast_map, ch, out_dir, style_note=ep.style_note,
                                      framing=framing, aspect_ratio=formats.veo_aspect(formats.episode_config(ep, ch)["layout"]))
        preview["reference_image"] = info
        for i, scene in enumerate(ep.scenes):     # a fresh preview invalidates any prior batch
            if i != pidx and not scene.get("asset_path"):   # keep asset scenes' real files intact
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
        # THE stitch: clips (native audio) + transitions (auto rules + human seam overrides) +
        # optional music bed + loudnorm -> final.mp4.
        music = (ep.timeline or {}).get("music")
        if music and not Path(music).is_file():
            music = None
        ok, err = _assemble_scenes_cut(ep, ch, music_path=music)
        if not ok:
            return _fail(eps, ep, f"final assembly failed: {err}")
        edl = [{"seq": s["seq"], "shot_type": s.get("shot_type"), "duration_s": s.get("duration_s"),
                "heading": s.get("heading")} for s in ep.scenes]
        titles_path = _write_titles(ep)          # one-off/ad: timed on-screen-title sidecar (SRT)
        ep.timeline = {**(ep.timeline or {}), "edl": edl, **({"titles_srt": titles_path} if titles_path else {})}
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("assembly", {"scenes": len(ep.scenes), "music": bool(music),
                            "voiceover": bool((ep.timeline or {}).get("voiceover")),
                            "titles": bool(titles_path)})

    else:
        return _fail(eps, ep, f"stage '{stage.value}' runs in a later milestone")

    return eps.update(ep)


def reroll_scene(store, ep: Episode, *, seq: int, prompt_override: str | None = None,
                 model: str | None = None) -> Episode:
    """Regenerate one scene's asset for the current stage (per-asset re-roll at the gate). At the
    refs stage an optional prompt/model override lets you tweak the wording or try a different image
    model for a shot you don't like."""
    from . import formats
    eps, chs, cs, ch, cast = _ctx(store, ep)
    scene = next((s for s in ep.scenes if s.get("seq") == seq), None)
    if not scene:
        raise StageError(f"scene {seq} not found")
    cfg = formats.episode_config(ep, ch)
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    out_dir = _out_dir(ep)
    if ep.stage == Stage.REFS.value:
        info, cost = _gen_scene_still(scene, cast_map, ch, out_dir, prompt_override=prompt_override,
                                      style_note=ep.style_note, model=model,
                                      framing=formats.framing_hint(cfg), aspect_ratio=formats.veo_aspect(cfg["layout"]))
        scene["reference_image"] = info
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        ep.log("ref_reroll", {"seq": seq, "status": info["status"], "cost_usd": cost})
    elif ep.stage in (Stage.SCENES.value, Stage.AUDIO.value, Stage.ASSEMBLY.value):
        info, cost = _gen_scene_veo(scene, cast_map, ch, out_dir,
                                    aspect=formats.veo_aspect(cfg["layout"]), resolution=cfg["resolution"])
        scene["clip"] = info
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        ep.log("scene_reroll", {"seq": seq, "status": info["status"], "cost_usd": cost})
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
    from . import formats
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    out_dir = _out_dir(ep)
    framing = formats.framing_hint(formats.episode_config(ep, ch))
    pending = [s for s in ep.scenes if (s.get("reference_image") or {}).get("status") != "ok"]
    est = round(len(pending) * pricing.image_cost(pricing.default_image_model()), 4)
    if est > episode_ceiling_usd():
        raise StageError(f"batch est ${est} over episode ceiling ${episode_ceiling_usd()}")
    # LOCATION CONTINUITY: the first good still for a location becomes that place's master, and every
    # later scene in the same location gets it as an extra reference — otherwise each scene invents
    # its own version of the "same" street and the cut falls apart.
    aspect = formats.veo_aspect(formats.episode_config(ep, ch)["layout"])
    masters: dict[str, str] = {}
    for s in ep.scenes:
        loc, ri = s.get("location_id"), (s.get("reference_image") or {})
        if loc and ri.get("status") == "ok" and ri.get("path") and loc not in masters:
            masters[loc] = ri["path"]          # seed from the approved preview / already-done stills
    spent, failed = 0.0, 0
    for scene in pending:
        loc = scene.get("location_id")
        info, cost = _gen_scene_still(scene, cast_map, ch, out_dir, style_note=ep.style_note,
                                      framing=framing, aspect_ratio=aspect,
                                      location_ref=masters.get(loc))
        scene["reference_image"] = info
        if loc and info.get("status") == "ok" and loc not in masters:
            masters[loc] = info["path"]        # this scene establishes the place for the rest
        spent += cost
        failed += (info["status"] != "ok")
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        eps.update(ep)                       # persist per-image so a live poll sees the grid fill
    ep.refs_batch_done = True
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("refs_batch", {"generated": len(pending), "failed": failed, "cost_usd": round(spent, 4)})
    return eps.update(ep)


def generate_scenes(store, ep: Episode, *, seqs: list[int] | None = None) -> Episode:
    """Render scenes as Veo 3.1 Lite clips (motion + native audio) and stitch the voiced rough cut.
    seqs=None -> generate every scene still missing a clip (idempotent, no re-charge). seqs=[...] ->
    (re)generate exactly those scenes (the per-scene / selected-batch path, forced even if a clip
    already exists, since the user picked them). Persists per clip for the live grid."""
    from . import formats
    eps, chs, cs, ch, cast = _ctx(store, ep)
    if not ep.scenes or not all((s.get("reference_image") or {}).get("status") == "ok" for s in ep.scenes):
        return _fail(eps, ep, "generate + approve reference images first")
    cfg = formats.episode_config(ep, ch)
    aspect, resolution = formats.veo_aspect(cfg["layout"]), cfg["resolution"]
    want = set(seqs) if seqs is not None else None
    est = stage_estimate(ep) if want is None else round(sum(
        fal_video.veo_lite_billed_cost(s.get("duration_s", 6), resolution, audio=True)
        for s in ep.scenes if s.get("seq") in want), 4)
    if est > episode_ceiling_usd():
        return _fail(eps, ep, f"est ${est} over episode ceiling ${episode_ceiling_usd()}")
    cast_map = _cast_map(cs, ep.cast or ch.cast_ids())
    out_dir = _out_dir(ep)
    spent, failed = 0.0, 0
    for scene in ep.scenes:
        if want is not None and scene.get("seq") not in want:
            continue                               # selected-only run: leave other scenes untouched
        cl = scene.get("clip") or {}
        if want is None and cl.get("status") == "ok" and Path(cl.get("path", "")).is_file():
            continue                               # bulk run: skip already-done (idempotent, no re-charge)
        if scene.get("asset_path"):                # real uploaded asset -> Ken-Burns/conform, no Veo, $0
            info, cost = _asset_clip(scene, episode_spec(ep, ch), out_dir)
        else:
            info, cost = _gen_scene_veo(scene, cast_map, ch, out_dir, aspect=aspect, resolution=resolution)
        scene["clip"] = info
        spent += cost
        failed += (info["status"] != "ok")
        ep.spent_usd = round(ep.spent_usd + cost, 4)
        eps.update(ep)
    # NO stitching here — scenes stay individual clips you review/re-roll one by one; the stitch
    # (transitions + music + loudnorm) happens once, at ASSEMBLY.
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("scenes", {"veo_clips": sum(1 for s in ep.scenes if (s.get("clip") or {}).get("status") == "ok"),
                      "failed": failed, "cost_usd": round(spent, 4)})
    return eps.update(ep)


def generate_audio(store, ep: Episode) -> Episode:
    """The Veo clips already carry native audio — this stage generates an OPTIONAL music bed and, for
    a one-off/ad, the GLOBAL VOICEOVER track (one clean narration file laid over the whole cut and
    ducking the music at assembly). Skippable at the approve gate."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    if not all((s.get("clip") or {}).get("status") == "ok" for s in ep.scenes):
        return _fail(eps, ep, "generate + approve the scenes first")
    out_dir = _out_dir(ep)
    total_dur = round(sum(s.get("duration_s", 6) for s in ep.scenes), 2)
    cfg = ep.config or {}
    tl = dict(ep.timeline or {})
    cost = 0.0
    # Music: use the ad's music brief when present, else the channel score.
    music_path = str(out_dir / "music.mp3")
    mprompt = (cfg.get("music_brief") or "").strip() or _music_prompt(ch)
    mr = music_cap.generate(prompt=mprompt, output_path=music_path, duration_s=total_dur, execute=True)
    cost += mr.cost_usd
    if not mr.ok:
        return _fail(eps, ep, f"music generation failed: {mr.error}")
    tl["music"] = music_path
    # Global voiceover (one-off): TTS the whole narration script into one file.
    vo_text = (cfg.get("voiceover_text") or "").strip()
    if vo_text:
        vo_path = str(out_dir / "voiceover.mp3")
        vr = voice_cap.speak(text=vo_text, output_path=vo_path,
                             voice_id=cfg.get("voice_id") or "Rachel", execute=True)
        cost += vr.cost_usd
        if vr.ok:
            tl["voiceover"] = vo_path
    ep.spent_usd = round(ep.spent_usd + cost, 4)
    ep.timeline = tl
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("audio", {"cost_usd": round(cost, 4), "duration_s": total_dur, "voiceover": bool(vo_text)})
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
        bad = [s["seq"] + 1 for s in ep.scenes if (s.get("clip") or {}).get("status") != "ok"]
        if bad:
            raise StageError(f"scenes {bad} have no clip yet — generate or re-roll them first")
        ep.log("scenes_approved", {"clips": len(ep.scenes)})
    elif stage == Stage.AUDIO:
        if payload.get("skip_music"):
            ep.timeline = {**(ep.timeline or {}), "music": None}
            ep.log("audio_skipped", {"reason": "native clip audio only"})
        elif not (ep.timeline or {}).get("music"):
            raise StageError("generate a music bed first, or skip (the clips already carry audio)")
        else:
            ep.log("audio_approved", {"music": True})
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


def revise_script_stage(store, ep: Episode, *, notes: list[str] | None = None) -> Episode:
    """Targeted revision of the CURRENT script (not a fresh rewrite): apply the QC judge's notes —
    plus any extra direction the human adds — to the parked script, then re-judge. Replaces the script
    with the revision and updates the scorecard, staying at the script gate."""
    from . import formats
    from .agents import script_qc
    eps, chs, cs, ch, cast = _ctx(store, ep)
    if ep.stage != Stage.SCRIPT.value or not ep.scenes:
        raise StageError("no script to revise")
    cfg = formats.episode_config(ep, ch)
    thr = float(cfg.get("qc_threshold") or script_qc.threshold(ch))
    prior_scenes, prior_qc = list(ep.scenes or []), dict(ep.script_qc or {})   # for revert
    use_notes = [n for n in (notes or []) if str(n).strip()] or (ep.script_qc or {}).get("notes") or []
    rev = writer.revise_script(ch, cast, ep.idea, ep.scenes, use_notes, model=ep.writer_model)
    if not rev.ok:
        return _fail_keep_review(eps, ep, rev.error or "revision failed")   # keep the current script
    _bill(ep, rev)
    scenes = rev.data["scenes"]
    prev_iters = (ep.script_qc or {}).get("iterations", 1)
    q = script_qc.judge(ch, cast, ep.idea, scenes)
    if q.ok:
        _bill(ep, q)
        qc = {**q.data, "iterations": prev_iters + 1, "threshold": thr, "judge_model": q.model}
        qc["passed"] = bool((qc.get("score") or 0) >= thr)
        ep.scenes = scenes
        script_qc.attach_intents(ep.scenes, qc.pop("intents", []))
        ep.script_qc = qc
    else:                                    # judge outage: keep the revision, unscored
        ep.scenes = scenes
        ep.script_qc = {**(ep.script_qc or {}), "iterations": prev_iters + 1, "error": q.error}
    ep.script_prev = {"scenes": prior_scenes, "script_qc": prior_qc}   # stash so a worse revise is undoable
    ep.refs_batch_done = False
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.log("script_revised", {"score": (ep.script_qc or {}).get("score"), "note_count": len(use_notes),
                              "prev_score": prior_qc.get("score")})
    return eps.update(ep)


def revert_script(store, ep: Episode) -> Episode:
    """One-click undo: swap the current script with the stashed previous one (so revert is itself
    undoable). Used when a rewrite/revise scored worse and you want the earlier version back."""
    eps = EpisodeStore(store)
    prev = ep.script_prev or {}
    if not prev.get("scenes"):
        raise StageError("no previous script to revert to")
    current = {"scenes": list(ep.scenes or []), "script_qc": dict(ep.script_qc or {})}
    ep.scenes = prev["scenes"]
    ep.script_qc = prev.get("script_qc") or {}
    ep.script_prev = current               # swap -> the revert can be undone again
    ep.refs_batch_done = False
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.stage_error = ""
    ep.log("script_reverted", {"score": (ep.script_qc or {}).get("score")})
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
        from .agents.writer import freeze_beat, lint_keyframe, _location_id
        for s in scenes:                    # keep the keyframe/video split coherent after hand-edits
            if not isinstance(s, dict):
                continue
            s["motion"] = (s.get("motion") or s.get("action") or "").strip()
            fb = (s.get("frozen_beat") or "").strip()
            if not fb or lint_keyframe(fb):
                s["frozen_beat"] = freeze_beat(s["motion"])
            s.setdefault("location_id", _location_id(s.get("heading", "")))
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


def _fail_keep_review(eps: EpisodeStore, ep: Episode, msg: str) -> Episode:
    """Surface an error but KEEP the existing approved-pending artifact visible (awaiting_review) —
    used when a re-generation/revision fails so it never hides the artifact you already had."""
    ep.stage_status = StageStatus.AWAITING_REVIEW.value
    ep.stage_error = msg
    ep.log("stage_error", {"error": msg, "kept_prior_artifact": True})
    return eps.update(ep)


def _bill(ep: Episode, res) -> None:
    ep.spent_usd = round(ep.spent_usd + float(res.cost_usd or 0.0), 4)


def _tenant_of(ep: Episode, eps: EpisodeStore) -> str:
    row = eps.conn.execute("SELECT tenant_id FROM episodes WHERE episode_id=?",
                           (ep.episode_id,)).fetchone()
    return row["tenant_id"] if row else "factory"
