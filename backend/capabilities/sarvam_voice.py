"""Sarvam AI TTS — authentic Indian-language voices (Bulbul) for the Voice DNA renderer.

Why this exists: ElevenLabs multilingual will *say* Hindi text but with a non-native accent.
Sarvam's Bulbul is trained on Indian languages with native prosody/accents (and Hinglish
code-switching), so a Hindi channel sounds actually Indian. This is the recommended Hindi
path (separate best-in-class TTS + lip-sync beats any video model's native Hindi audio).

Activation: set SARVAM_API_KEY in .env. A character's Voice DNA opts in via
voice.provider == "sarvam" (+ voice.sarvam_speaker). When the key is absent the caller
falls back to ElevenLabs, so behaviour never regresses to silence.

Returns the same VoiceResult shape as capabilities.voice so the pipeline is provider-agnostic.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import requests

from ..finishing import FFMPEG, media_duration
from .voice import VoiceResult, _stub          # reuse the shared result + silence-stub

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
DEFAULT_MODEL = "bulbul:v2"
# Bulbul v2 speakers (verify/extend against your account's available voices).
KNOWN_SPEAKERS = {"anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh"}
_COST_PER_CHAR_USD = 0.00006                    # rough; refine against Sarvam billing


def _key() -> str | None:
    """Cleaned key, or None. Rejects a `#comment`-shaped value (python-dotenv parses an inline
    comment after a blank value AS the value — this guards that footgun)."""
    k = (os.environ.get("SARVAM_API_KEY") or "").strip()
    return k if (k and not k.startswith("#")) else None


def speak(*, text: str, output_path: str, speaker: str = "abhilash",
          language_code: str = "hi-IN", pace: float = 1.0, execute: bool = True) -> VoiceResult:
    """Render one Hindi (or other Indian-language) line to speech at output_path (.mp3)."""
    text = (text or "").strip()
    if not text:
        return VoiceResult(ok=False, model=DEFAULT_MODEL, error="empty text")
    est = round(len(text) * _COST_PER_CHAR_USD, 5)
    if not execute or not _key():
        # No key -> silence stub so the pipeline still flows; callers should prefer the
        # ElevenLabs fallback instead of reaching here when SARVAM_API_KEY is unset.
        return _stub(text, output_path, est, DEFAULT_MODEL)

    payload = {
        "inputs": [text[:500]],
        "target_language_code": language_code,
        "speaker": speaker if speaker in KNOWN_SPEAKERS else "abhilash",
        "pace": max(0.5, min(pace, 2.0)),
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
        "model": DEFAULT_MODEL,
    }
    try:
        r = requests.post(SARVAM_TTS_URL, json=payload,
                          headers={"api-subscription-key": _key(), "Content-Type": "application/json"},
                          timeout=120)
        r.raise_for_status()
        audios = (r.json() or {}).get("audios") or []
        if not audios:
            return VoiceResult(ok=False, model=DEFAULT_MODEL, error="no audio returned")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        wav = out.with_suffix(".sarvam.wav")
        wav.write_bytes(base64.b64decode(audios[0]))
        # Sarvam returns WAV; conform to the .mp3 the pipeline expects.
        subprocess.run([FFMPEG, "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "128k",
                        str(out)], capture_output=True)
        wav.unlink(missing_ok=True)
        if not out.is_file():
            return VoiceResult(ok=False, model=DEFAULT_MODEL, error="mp3 encode failed")
    except (requests.RequestException, ValueError, KeyError) as e:
        return VoiceResult(ok=False, model=DEFAULT_MODEL, error=f"sarvam tts failed: {e}")
    return VoiceResult(ok=True, path=output_path, duration_s=media_duration(output_path),
                       cost_usd=est, model=DEFAULT_MODEL)
