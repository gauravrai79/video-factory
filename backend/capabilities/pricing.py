"""Central price table for fal models (verified mid-2026; update before relying on exact figures).

Single source of truth so the planner, the cost model, and the capability clients all price the same
way. Prices are USD. Image models bill per image; video models bill per second of output.

Seedance is intentionally absent — dropped as too expensive (see project decisions).
"""

from __future__ import annotations

import os

# --- image generation / editing (USD per image) ---
IMAGE_PRICING_USD = {
    # OpenRouter (same Gemini/Nano-Banana model as fal, ~60% cheaper, one key) — recommended
    "gemini-flash": 0.0387,       # google/gemini-2.5-flash-image (= Nano Banana), char-consistent
    "gemini-3-flash": 0.0685,     # google/gemini-3.1-flash-image (newer/higher quality)
    # fal
    "nano-banana-2": 0.10,        # Gemini image on fal — same model, fal markup
    "nano-banana-pro": 0.15,      # top character consistency + text rendering
    "flux-kontext": 0.04,         # identity across iterative edits (needs a reference image)
    "flux-dev": 0.025,            # solid text-to-image quality
    "flux-schnell": 0.003,        # cheapest/fastest draft (lower fidelity, no identity lock)
}
DEFAULT_IMAGE_MODEL = "gemini-flash"    # OpenRouter Gemini — cheap + character-consistent + one key

# image model keys that route through OpenRouter (rest go through fal)
OPENROUTER_IMAGE_MODELS = {"gemini-flash", "gemini-3-flash"}


def default_image_model() -> str:
    """The active image model. Override with VF_IMAGE_MODEL (e.g. flux-dev, flux-schnell) to cut cost
    when you aren't using reference-image identity locking."""
    return os.environ.get("VF_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)

# --- image-to-video (USD per second of output) ---
VIDEO_PRICING_USD_PER_S = {
    "wan-2.5": 0.05,              # 480p — cheapest practical HD workhorse
    "kling-2.5-turbo": 0.07,     # best price/quality flagship tier
}
DEFAULT_VIDEO_MODEL = "wan-2.5"


def image_cost(model: str | None = None) -> float:
    return IMAGE_PRICING_USD.get(model or default_image_model(), IMAGE_PRICING_USD[DEFAULT_IMAGE_MODEL])


def video_cost(model: str | None, duration_s: float) -> float:
    rate = VIDEO_PRICING_USD_PER_S.get(model or DEFAULT_VIDEO_MODEL,
                                       VIDEO_PRICING_USD_PER_S[DEFAULT_VIDEO_MODEL])
    return round(rate * max(duration_s, 0.0), 4)


# --- audio: TTS (per 1k chars), music (per minute), lip-sync (per second) ---
TTS_PRICING_USD_PER_1K = {
    "elevenlabs-multilingual-v2": 0.10,   # quality default (stable narration + speed control)
    "elevenlabs-v3": 0.10,                # most expressive (inline audio tags)
    "elevenlabs-turbo": 0.05,             # low latency
    "chatterbox": 0.025,                  # cheapest + zero-shot voice cloning via reference audio
}
DEFAULT_TTS_MODEL = "elevenlabs-multilingual-v2"

MUSIC_PRICING_USD_PER_MIN = {
    "cassetteai": 0.02,                   # cheap bed, exact-second duration (default; music is ducked bg)
    "elevenlabs-music": 0.80,             # premium bed
}
DEFAULT_MUSIC_MODEL = "cassetteai"

LIPSYNC_PRICING_USD_PER_S = {
    "veed-fabric": 0.08,                  # still-image talking head @480p (default)
    "omnihuman": 0.16,                    # premium still-image talking head
    "kling-avatar": 0.056,                # cheapest still-image avatar
}
DEFAULT_LIPSYNC_MODEL = "veed-fabric"


def tts_cost(model: str | None, chars: int) -> float:
    rate = TTS_PRICING_USD_PER_1K.get(model or DEFAULT_TTS_MODEL, TTS_PRICING_USD_PER_1K[DEFAULT_TTS_MODEL])
    return round(rate * max(chars, 0) / 1000.0, 4)


def music_cost(model: str | None, duration_s: float) -> float:
    rate = MUSIC_PRICING_USD_PER_MIN.get(model or DEFAULT_MUSIC_MODEL, MUSIC_PRICING_USD_PER_MIN[DEFAULT_MUSIC_MODEL])
    return round(rate * max(duration_s, 0.0) / 60.0, 4)


def lipsync_cost(model: str | None, duration_s: float) -> float:
    rate = LIPSYNC_PRICING_USD_PER_S.get(model or DEFAULT_LIPSYNC_MODEL, LIPSYNC_PRICING_USD_PER_S[DEFAULT_LIPSYNC_MODEL])
    return round(rate * max(duration_s, 0.0), 4)
