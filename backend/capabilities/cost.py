"""Cost model — per-post and portfolio (content-calendar) projections.

A post's cost is the sum of its shots: every shot is one generated still; video shots add a paid
image-to-video pass. Still+Ken Burns shots add no generation spend (FFmpeg motion is free). The cost
lever is therefore the still/video mix the planner chooses — see agents/storyboard.

infra is a rounding error; there is no QC labor line in v1 (auto VLM QC). Plug the numbers from a
planned storyboard straight in.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import pricing


@dataclass
class CostLine:
    label: str
    per_post_usd: float
    monthly_usd: float


def estimate_post(*, n_stills: int, n_videos: int, video_seconds_each: float = 5.0,
                  image_model: str | None = None, video_model: str | None = None) -> float:
    """Estimate one post: stills + video passes. (The planner already sums this per storyboard; this
    is for projections and what-ifs.)"""
    stills = n_stills * pricing.image_cost(image_model)
    videos = n_videos * pricing.video_cost(video_model, video_seconds_each)
    return round(stills + videos, 4)


def monthly_projection(
    *,
    reels_per_day: int = 3,
    shots_per_reel: int = 6,
    videos_per_reel: int = 2,
    video_seconds_each: float = 5.0,
    infra_per_post_usd: float = 0.03,
    days: int = 30,
    image_model: str | None = None,
    video_model: str | None = None,
) -> dict:
    """Project monthly spend for one character's posting cadence."""
    gen = estimate_post(n_stills=shots_per_reel, n_videos=videos_per_reel,
                        video_seconds_each=video_seconds_each,
                        image_model=image_model, video_model=video_model)
    posts = reels_per_day * days
    lines = [
        CostLine("Generation (stills + video)", gen, round(gen * posts, 2)),
        CostLine("Infra (orchestration+FFmpeg+storage)", infra_per_post_usd,
                 round(infra_per_post_usd * posts, 2)),
    ]
    total_per_post = round(sum(l.per_post_usd for l in lines), 4)
    return {
        "reels_per_day": reels_per_day,
        "posts_per_month": posts,
        "image_model": image_model or pricing.DEFAULT_IMAGE_MODEL,
        "video_model": video_model or pricing.DEFAULT_VIDEO_MODEL,
        "lines": [l.__dict__ for l in lines],
        "total_per_post_usd": total_per_post,
        "total_monthly_usd": round(total_per_post * posts, 2),
        "note": "Lower the video-per-reel budget (more still+Ken Burns) to cut spend.",
    }
