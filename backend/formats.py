"""Per-episode format config — the Setup stage's contract.

A Channel carries brand defaults; an Episode's `config` overrides them for THIS video, so the same
channel can ship a 2-min landscape YouTube episode AND a 30s portrait Reel. `episode_config()` merges
channel defaults under the episode's config (with back-compat defaults so pre-config episodes still
work), and `episode_spec()` turns that into the concrete render OutputSpec (canvas w/h, duration band,
bitrate). Platform presets one-click stamp a sensible config; the creative pipeline reads pacing /
hook_seconds / transitions / qc_threshold from the same config.
"""
from __future__ import annotations

import os
from typing import Any

from .spec import OutputSpec

LAYOUTS = ("landscape", "portrait")
RESOLUTIONS = ("720p", "1080p")
PACINGS = ("dialogue", "balanced", "action")

# One-click platform presets. `custom` leaves the current config untouched.
PLATFORM_PRESETS: dict[str, dict[str, Any]] = {
    "youtube_long": {"label": "YouTube — long-form", "layout": "landscape", "duration_s": 120,
                     "resolution": "720p", "music": True, "transitions": "auto",
                     "qc_threshold": 75, "pacing": "balanced"},
    "youtube_short": {"label": "YouTube Shorts", "layout": "portrait", "duration_s": 45,
                      "resolution": "720p", "music": True, "transitions": "auto",
                      "qc_threshold": 75, "pacing": "action"},
    "instagram_reel": {"label": "Instagram Reel", "layout": "portrait", "duration_s": 30,
                       "resolution": "1080p", "music": True, "transitions": "auto",
                       "qc_threshold": 78, "pacing": "action"},
    "tiktok": {"label": "TikTok", "layout": "portrait", "duration_s": 30, "resolution": "1080p",
               "music": True, "transitions": "auto", "qc_threshold": 78, "pacing": "action"},
    "custom": {"label": "Custom"},
}


def default_scene_count(duration_s: float) -> int:
    """~one beat per ~7.5s, clamped to 3-30. Veo caps a clip at 8s, so aiming near that gives the
    FEWEST cuts for a given length — every extra cut is another independently-generated shot and
    another chance for the world to look different, so fewer/longer beats read as more coherent."""
    return max(3, min(30, round(float(duration_s or 60) / 7.5)))


def episode_config(ep, ch) -> dict[str, Any]:
    """Effective config for an episode: episode.config over channel defaults, with back-compat
    fallbacks so episodes created before the Setup stage still resolve to a valid config."""
    cfg = dict(getattr(ep, "config", None) or {})
    is_short = ch.is_short() if ch else False
    cfg.setdefault("platform", "youtube_short" if is_short else "youtube_long")
    cfg.setdefault("layout", "portrait" if is_short else "landscape")
    if cfg["layout"] not in LAYOUTS:
        cfg["layout"] = "landscape"
    cfg.setdefault("duration_s", int((ch.target_duration_s if ch else 0) or 120))
    res = cfg.get("resolution") or os.environ.get("VF_VIDEO_RESOLUTION", "720p")
    cfg["resolution"] = res if res in RESOLUTIONS else "720p"
    cfg.setdefault("scene_count", int((ch.target_scene_count if ch else 0)
                                      or default_scene_count(cfg["duration_s"])))
    cfg.setdefault("language", (ch.language if ch else "") or "English")
    cfg.setdefault("music", True)
    cfg.setdefault("transitions", "auto")         # auto | off
    cfg.setdefault("qc_threshold", 75)
    cfg["pacing"] = cfg.get("pacing") if cfg.get("pacing") in PACINGS else "balanced"
    cfg.setdefault("cost_ceiling_usd", 0)         # 0 = channel/global default
    cfg.setdefault("configured", bool(getattr(ep, "config", None)))
    return cfg


def veo_aspect(layout: str) -> str:
    return "9:16" if layout == "portrait" else "16:9"


def hook_seconds(cfg: dict[str, Any]) -> int:
    """Shorts/Reels must hook in ~2s; long-form has ~5s."""
    return 2 if cfg.get("layout") == "portrait" else 5


def framing_hint(cfg: dict[str, Any]) -> str:
    """Composition instruction injected into keyframe prompts so portrait frames are shot vertical
    (subject centered) rather than a cropped landscape."""
    if cfg.get("layout") == "portrait":
        return ("Vertical 9:16 portrait composition — frame the subject centered and full-height "
                "for a tall phone screen, important action in the central vertical band")
    return "Horizontal 16:9 widescreen composition"


def _dims(layout: str, resolution: str) -> tuple[int, int]:
    hi = resolution == "1080p"
    if layout == "portrait":
        return (1080, 1920) if hi else (720, 1280)
    return (1920, 1080) if hi else (1280, 720)


def episode_spec(ep, ch) -> OutputSpec:
    """Concrete render spec (final canvas + duration band + bitrate) from the episode config."""
    cfg = episode_config(ep, ch)
    w, h = _dims(cfg["layout"], cfg["resolution"])
    dur = float(cfg["duration_s"] or 120)
    return OutputSpec(name=f"{cfg['layout']}_{cfg['resolution']}", width=w, height=h,
                      min_duration_s=max(3.0, dur * 0.3), max_duration_s=max(dur * 3.0, 600.0),
                      video_mbps=10.0 if cfg["resolution"] == "1080p" else 8.0)
