"""Storyboard planner — turns a character + a content brief into a shot-by-shot reel plan.

This is the new intelligence layer (replacing CSV ingest). Given a Character and a brief
("3 reels, travel theme") it sequences scene templates into an ordered storyboard, decides per shot
whether to render a cheap still+Ken Burns or spend on a paid video clip, and builds the generation
prompts. The `render_mode` field is the cost lever: most shots stay on stills, and a small video
budget is spent only on motion-defining beats.

Deterministic by default (predictable cost, no key needed); optional LLM refinement of prompts.

Cost model per shot:
  - every shot = one generated still (image_cost)
  - "kenburns" shots add free FFmpeg motion (no extra spend)
  - "video" shots add a paid image-to-video pass (video_cost over the shot duration)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..capabilities import pricing
from ..characters import Character
from ..scene_library import SCENE_TEMPLATES, SceneTemplate, templates_for_tags
from .prompt_builder import motion_prompt, refine_still_prompt, still_prompt


@dataclass
class Shot:
    seq: int
    template_key: str
    description: str
    render_mode: str                 # "kenburns" (still+free motion) | "video" (paid i2v)
    duration_s: float
    camera: str
    mood: str
    clothing: str
    still_prompt: str = ""
    motion_prompt: str = ""
    image_model: str = pricing.DEFAULT_IMAGE_MODEL
    video_model: str = pricing.DEFAULT_VIDEO_MODEL
    est_cost_usd: float = 0.0
    llm_refined: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Storyboard:
    storyboard_id: str
    character_id: str
    slug: str                        # post slug
    brief: str
    format: str                      # reel | short | square | longform ...
    shots: list[Shot] = field(default_factory=list)
    caption_hook: str = ""           # optional opening hook super
    est_cost_usd: float = 0.0
    created_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["shots"] = [s.as_dict() for s in self.shots]
        return d

    @property
    def total_duration_s(self) -> float:
        return round(sum(s.duration_s for s in self.shots), 2)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "post"


def _select_templates(tags: list[str], n: int) -> list[SceneTemplate]:
    """Pick n templates matching the tags, varied (cycle through candidates without immediate repeats)."""
    pool = templates_for_tags(tags) or list(SCENE_TEMPLATES.values())
    out: list[SceneTemplate] = []
    i = 0
    while len(out) < n:
        out.append(pool[i % len(pool)])
        i += 1
    return out[:n]


def plan_storyboard(
    char: Character,
    *,
    brief: str = "",
    fmt: str = "reel",
    tags: list[str] | None = None,
    n_shots: int = 6,
    video_budget: int = 2,
    storyboard_id: str = "",
    created_at: float = 0.0,
    refine: bool = True,
) -> Storyboard:
    """Plan one post. `video_budget` caps how many shots get a paid video pass (the rest are
    still+Ken Burns), which bounds the post's cost. Returns a fully-priced storyboard with prompts."""
    tags = tags or []
    n_shots = max(1, min(n_shots, 12))
    templates = _select_templates(tags, n_shots)

    shots: list[Shot] = []
    videos_used = 0
    for i, tmpl in enumerate(templates):
        wants_video = tmpl.render_bias == "video"
        if wants_video and videos_used < video_budget:
            render_mode = "video"
            videos_used += 1
        else:
            render_mode = "kenburns"

        sp = still_prompt(char, tmpl)
        refined = False
        if refine:
            sp, refined = refine_still_prompt(sp)
        mp = motion_prompt(char, tmpl) if render_mode == "video" else ""

        cost = pricing.image_cost(pricing.DEFAULT_IMAGE_MODEL)
        if render_mode == "video":
            cost += pricing.video_cost(pricing.DEFAULT_VIDEO_MODEL, tmpl.duration_s)

        shots.append(Shot(
            seq=i,
            template_key=tmpl.key,
            description=tmpl.label,
            render_mode=render_mode,
            duration_s=tmpl.duration_s,
            camera=tmpl.camera,
            mood=tmpl.mood,
            clothing=tmpl.clothing_hint,
            still_prompt=sp,
            motion_prompt=mp,
            est_cost_usd=round(cost, 4),
            llm_refined=refined,
        ))

    slug = f"{char.slug}-{_slugify(brief or fmt)}"
    sb = Storyboard(
        storyboard_id=storyboard_id,
        character_id=char.character_id,
        slug=slug,
        brief=brief,
        format=fmt,
        shots=shots,
        est_cost_usd=round(sum(s.est_cost_usd for s in shots), 4),
        created_at=created_at,
    )
    return sb
