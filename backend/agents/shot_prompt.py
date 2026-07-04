"""Per-scene prompts for the visual stages.

Builds the reference-still prompt (the frame handed to the image model) and the motion prompt (for
hero-video animation), injecting the present cast's Visual DNA + the channel art style so identity and
look stay locked across every scene and episode.
"""

from __future__ import annotations

from ..channels import Channel
from ..characters import Character

_GUARD = ("Photorealistic, cinematic lighting, high detail, consistent character identity and "
          "wardrobe. No on-screen text, captions, logos, or watermarks.")


def scene_cast(scene: dict, cast_map: dict[str, Character]) -> list[Character]:
    return [cast_map[cid] for cid in (scene.get("cast_present") or []) if cid in cast_map]


def reference_still_prompt(scene: dict, present: list[Character], channel: Channel) -> tuple[str, list[str]]:
    """Return (prompt, reference_image_paths). For a b-roll/no-cast scene it's an establishing shot."""
    style = channel.art_style or "cinematic, photorealistic"
    heading = scene.get("heading", "")
    action = scene.get("action", "")
    camera = scene.get("camera", "")
    if present:
        who = "; ".join(c.look_descriptor() for c in present)
        subject = who
    else:
        subject = "atmospheric establishing shot, no people"
    prompt = ". ".join(p for p in [
        style, heading, subject, action, camera, _GUARD] if p)
    refs = [p for c in present for p in c.reference_images]
    return prompt, refs


def motion_prompt(scene: dict, present: list[Character]) -> str:
    """Prompt for image-to-video on a hero scene — keep the subject, add the scene's action + camera."""
    who = ", ".join(c.name for c in present) or "the subject"
    return (f"{who}. {scene.get('action', '')}. Camera: {scene.get('camera', '')}. "
            f"Natural, subtle motion; keep identity, face, and wardrobe consistent; "
            f"smooth realistic movement, no morphing or warping.")
