"""Cost model — per-video and monthly projections.

Mirrors the feasibility doc's headline insight: at 20K/month with offshore QC labor, **generation
cost dominates**; infra is a rounding error and QC labor is under 10%. So the optimization levers are
the regeneration (reshoot) rate and the per-second model cost — not shaving QC.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fal_video import kling_cost, seedance_cost


@dataclass
class CostLine:
    label: str
    per_video_usd: float
    monthly_usd: float


def estimate_generation(model: str, model_variant: str, duration_s: int) -> float:
    """Single-attempt generation estimate (no reshoot multiplier) — used to price a job at enqueue
    and to enforce the per-job cost ceiling before any paid call."""
    base = kling_cost(model_variant, duration_s) if model == "kling" else seedance_cost(model_variant, duration_s)
    return round(base, 4)


def per_video_generation(model: str, model_variant: str, duration_s: int,
                         regen_factor: float = 1.35) -> float:
    """Generation cost including the reshoot multiplier (~35% need one retry to pass QC)."""
    base = kling_cost(model_variant, duration_s) if model == "kling" else seedance_cost(model_variant, duration_s)
    return round(base * regen_factor, 4)


def monthly_projection(
    *,
    volume: int = 20_000,
    model: str = "kling",
    model_variant: str = "v2.1/standard",
    duration_s: int = 12,
    regen_factor: float = 1.35,
    infra_per_video_usd: float = 0.12,
    qc_per_video_usd: float = 0.20,    # Posture A (100% human) ballpark; see feasibility §5
) -> dict:
    gen = per_video_generation(model, model_variant, duration_s, regen_factor)
    lines = [
        CostLine("Generation (incl. reshoot)", gen, round(gen * volume, 2)),
        CostLine("Infra (orchestration+FFmpeg+storage)", infra_per_video_usd, round(infra_per_video_usd * volume, 2)),
        CostLine("QC labor", qc_per_video_usd, round(qc_per_video_usd * volume, 2)),
    ]
    total_per_video = round(sum(l.per_video_usd for l in lines), 4)
    return {
        "volume": volume,
        "model": model,
        "model_variant": model_variant,
        "duration_s": duration_s,
        "regen_factor": regen_factor,
        "lines": [l.__dict__ for l in lines],
        "total_per_video_usd": total_per_video,
        "total_monthly_usd": round(total_per_video * volume, 2),
        "note": "Generation dominates; cut the reshoot rate (better prompts/reference conditioning) to move the needle.",
    }
