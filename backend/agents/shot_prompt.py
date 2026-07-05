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


def reference_still_prompt(scene: dict, present: list[Character], channel: Channel) -> tuple[str, list[str]]:
    """Return (prompt, reference_image_paths). The channel art style leads the prompt and, when a
    stylised style is set, the referenced characters are explicitly re-rendered in that style (so
    photoreal reference photos still become e.g. 3D-comic characters)."""
    style = channel.art_style or "cinematic, photorealistic"
    setting = (getattr(channel, "world", "") or "").strip()
    heading = scene.get("heading", "")
    action = scene.get("action", "")
    camera = scene.get("camera", "")
    if present:
        who = "; ".join(c.look_descriptor() for c in present)
        subject = (f"Render {who} in a {style} art style — keep each character's identity from the "
                   f"reference images but restyle them to fully match this art style")
    else:
        subject = f"Atmospheric establishing shot, no characters, in a {style} art style"
    # Setting leads the scene description so the world (e.g. contemporary India) anchors every frame.
    world_line = f"Setting — {setting}" if setting else ""
    prompt = ". ".join(p for p in [f"Art style: {style}", world_line, heading, subject, action, camera, _GUARD] if p)
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
