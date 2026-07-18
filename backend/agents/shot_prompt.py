"""Per-scene prompts for the visual stages.

Builds the reference-still prompt (the frame handed to the image model) and the motion prompt (for
hero-video animation), injecting the present cast's Visual DNA + the channel art style so identity and
look stay locked across every scene and episode.
"""

from __future__ import annotations

from ..channels import Channel
from ..characters import Character

# Style-neutral guard (no "photorealistic" — that would override the channel's chosen art style).
_GUARD = ("High detail, consistent character identity and wardrobe across scenes. "
          "No on-screen text, captions, logos, or watermarks.")


def scene_cast(scene: dict, cast_map: dict[str, Character]) -> list[Character]:
    return [cast_map[cid] for cid in (scene.get("cast_present") or []) if cid in cast_map]


_FOOTER_STILL = ("Sharp focus, crisp linework, no motion blur. Consistent character identity and "
                 "wardrobe. No on-screen text, captions, logos, or watermarks.")


def reference_still_prompt(scene: dict, present: list[Character], channel: Channel,
                           *, framing: str = "") -> tuple[str, list[str]]:
    """KEYFRAME prompt — a STILL, STABLE instant (all motion belongs to the video prompt). Style
    anchor -> setting + single light source (anti-compositing) -> subjects (canonical looks, restyled
    from reference images) -> frozen beat -> composition/ground plane -> still footer. `framing` is the
    per-episode aspect composition hint (portrait vs landscape)."""
    from .writer import lint_keyframe
    style = channel.art_style or "cinematic, photorealistic"
    setting = (getattr(channel, "world", "") or "").strip()
    heading = scene.get("heading", "")
    frozen = (scene.get("frozen_beat") or "").strip() or scene.get("action", "")
    # Camera MOVEMENT belongs to the video stage — a keyframe only keeps a motion-free framing
    # ("low-angle medium two-shot" yes; "slow motion tracking the flying food" no).
    camera = scene.get("camera", "")
    if lint_keyframe(camera):
        camera = ""
    if present:
        who = "; ".join(c.look_descriptor() for c in present)
        # NO repeat of the art-style string here (it already leads the prompt) — repetition bloats it.
        subject = (f"Render {who}, keeping each character's identity from the reference images but "
                   f"restyled to fully match this art style. Natural proportions")
    else:
        subject = "Atmospheric establishing shot, no characters"
    world_line = (f"Setting — {setting}. Single consistent light source — every element shares the "
                  f"same lighting so nothing looks composited"
                  if setting else "Single consistent light source so nothing looks composited")
    frozen_line = f"Frozen beat (one stable instant, at rest): {frozen}" if frozen else ""
    # NOTE: intent.must_show is the scene/MOTION contract (it contains action verbs) — injecting it
    # into a STILL made the model draw one character several times (once per action). It belongs in
    # the video prompt + QC only, never in the keyframe. A short mood word is fine.
    mood_line = f"Mood: {(scene.get('intent') or {}).get('mood')}" if (scene.get("intent") or {}).get("mood") else ""
    compo = f"Composition: {camera}. One continuous ground plane — all characters share the same floor" \
        if camera else "One continuous ground plane — all characters share the same floor"
    prompt = ". ".join(p for p in [f"Art style: {style}", world_line, heading, subject,
                                   frozen_line, mood_line, framing, compo, _FOOTER_STILL] if p)
    refs = [p for c in present for p in c.reference_images]
    return prompt, refs


def motion_prompt(scene: dict, present: list[Character], channel: Channel | None = None) -> str:
    """Prompt for image-to-video on a hero scene — keep the subject, add the scene's action + camera."""
    who = ", ".join(c.name for c in present) or "the subject"
    setting = (getattr(channel, "world", "") or "").strip() if channel else ""
    world_line = f" Setting: {setting}." if setting else ""
    return (f"{who}. {scene.get('action', '')}. Camera: {scene.get('camera', '')}.{world_line} "
            f"Natural, subtle motion; keep identity, face, and wardrobe consistent; "
            f"smooth realistic movement, no morphing or warping.")


def veo_prompt(scene: dict, present: list[Character], channel: Channel) -> str:
    """VIDEO prompt for Veo native-audio image-to-video. The keyframe (image_url) already carries the
    characters, style, and setting — so this prompt does NOT re-describe them (shorter prompt = less
    identity drift). It carries ALL the motion, the camera move, and the spoken line: the speaker is
    referenced by a VISUAL tag (the model doesn't know names), and lip-sync is requested ONLY when
    there is dialogue (otherwise a silent character gets a talking mouth)."""
    lang = (getattr(channel, "language", "") or "English").strip()
    id2char = {c.character_id: c for c in present}
    motion = (scene.get("motion") or "").strip() or scene.get("action", "")
    parts = ["Animate from this exact frame. Keep every character's exact look, wardrobe, and the "
             "scene's art style locked"]
    if motion:
        parts.append(f"Action: {motion}")
    # NOTE: intent.must_show (a prop/element checklist) used to be injected here, but the model
    # over-fixated on the listed objects (e.g. it turned a protest into a 'samosa' scene). The motion
    # already describes the shot; must_show stays in QC only, not in the generation prompt.
    if scene.get("camera"):
        parts.append(f"Camera: {scene['camera']}")
    dlg = next((d for d in (scene.get("dialogue") or [])
                if isinstance(d, dict) and (d.get("line") or "").strip()), None)
    narr = (scene.get("narration") or "").strip()
    if dlg:
        spk = id2char.get(dlg.get("speaker"))
        tag = spk.speaker_tag() if spk else "the character"
        delivery = (dlg.get("delivery") or "").strip()
        dtag = f", {delivery}" if delivery else ""
        parts.append(f'One short spoken line — {tag} says out loud in {lang}{dtag}, with accurate '
                     f'lip-sync: "{dlg["line"].strip()}"')
    elif narr:
        parts.append(f'No character speaks on screen. A warm narrator voiceover says in {lang}: "{narr}"')
    else:
        parts.append("No spoken dialogue in this shot")
    parts.append("Natural physics, weight and expression; ambient scene motion. "
                 "No on-screen text, captions, subtitles, logos or watermarks")
    return ". ".join(p for p in parts if p)
