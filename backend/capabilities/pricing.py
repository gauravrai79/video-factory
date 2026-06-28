"""Central price table for fal models (verified mid-2026; update before relying on exact figures).

Single source of truth so the planner, the cost model, and the capability clients all price the same
way. Prices are USD. Image models bill per image; video models bill per second of output.

Seedance is intentionally absent — dropped as too expensive (see project decisions).
"""

from __future__ import annotations

# --- image generation / editing (USD per image) ---
IMAGE_PRICING_USD = {
    "nano-banana-2": 0.10,        # Gemini 3 image — up to 5 people consistent, no fine-tune
    "nano-banana-pro": 0.15,      # top character consistency + text rendering
    "flux-kontext": 0.04,         # strong identity across iterative edits, cheap
    "flux-schnell": 0.003,        # cheapest draft (no built-in consistency)
}
DEFAULT_IMAGE_MODEL = "nano-banana-2"

# --- image-to-video (USD per second of output) ---
VIDEO_PRICING_USD_PER_S = {
    "wan-2.5": 0.05,              # 480p — cheapest practical HD workhorse
    "kling-2.5-turbo": 0.07,     # best price/quality flagship tier
}
DEFAULT_VIDEO_MODEL = "wan-2.5"


def image_cost(model: str | None = None) -> float:
    return IMAGE_PRICING_USD.get(model or DEFAULT_IMAGE_MODEL, IMAGE_PRICING_USD[DEFAULT_IMAGE_MODEL])


def video_cost(model: str | None, duration_s: float) -> float:
    rate = VIDEO_PRICING_USD_PER_S.get(model or DEFAULT_VIDEO_MODEL,
                                       VIDEO_PRICING_USD_PER_S[DEFAULT_VIDEO_MODEL])
    return round(rate * max(duration_s, 0.0), 4)
