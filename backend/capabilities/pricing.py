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
