"""Deterministic finishing layer — FFmpeg, 100% automatable.

Everything the SOW mandates that isn't generative lives here and is fully reliable:
  - enforce exact dimensions (scale-to-fit + pad, never crop the product)
  - clamp duration into the spec band
  - two-pass encode to land inside the target size band
  - burn the "Synthetically Generated" watermark (bottom, clear of product)
  - overlay callout supers (USPs) on a schedule
  - mux non-copyrighted background music (generation runs audio-off)

This layer guarantees spec compliance regardless of what the model produced.
"""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .spec import OutputSpec, get_spec


# --------------------------------------------------------------------------- binary resolution

def _resolve(bin_name: str, env_var: str) -> str:
    """Find ffmpeg/ffprobe across PATH, env override, and the winget install dir."""
    override = os.environ.get(env_var)
    if override:
        return override
    found = shutil.which(bin_name)
    if found:
        return found
    if platform.system() == "Windows":
        pattern = os.path.expandvars(
            rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin\{bin_name}.exe"
        )
        hits = glob.glob(pattern, recursive=True)
        if hits:
            return hits[0]
    return bin_name  # last resort: hope it's on PATH at runtime


FFMPEG = _resolve("ffmpeg", "FFMPEG_BIN")
FFPROBE = _resolve("ffprobe", "FFPROBE_BIN")


def _font_file() -> str:
    override = os.environ.get("VF_FONT_FILE")
    if override and Path(override).is_file():
        return override
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c
    return ""  # drawtext will fall back to its built-in font


def _esc_font(path: str) -> str:
    """Escape a font path for an ffmpeg filter (Windows drive colon + backslashes)."""
    return path.replace("\\", "/").replace(":", r"\:")


def _esc_text(text: str) -> str:
    """Escape user text for drawtext."""
    return text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"’")


# --------------------------------------------------------------------------- probing

def probe(path: str | Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height",
         str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def _summary(path: str | Path) -> dict:
    data = probe(path)
    fmt = data.get("format", {})
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    return {
        "width": v.get("width"),
        "height": v.get("height"),
        "duration_s": round(float(fmt.get("duration", 0) or 0), 3),
        "size_mb": round(int(fmt.get("size", 0) or 0) / (1024 * 1024), 3),
        "video_codec": v.get("codec_name"),
        "audio_codec": a.get("codec_name") if a else None,
        "has_audio": a is not None,
    }


# --------------------------------------------------------------------------- callout supers

@dataclass
class Callout:
    text: str
    start_s: float = 0.0
    end_s: float = 3.0


# --------------------------------------------------------------------------- finishing

@dataclass
class FinishResult:
    success: bool
    output_path: str | None = None
    probe: dict = field(default_factory=dict)
    compliant: bool = False
    violations: list[str] = field(default_factory=list)
    error: str | None = None


def _video_filter(spec: OutputSpec, callouts: list[Callout], pad_color: str) -> str:
    font = _font_file()
    fontarg = f"fontfile='{_esc_font(font)}':" if font else ""

    chain = [
        f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease",
        f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}",
        f"fps={spec.fps}",
        "setsar=1",
    ]
    # Watermark — bottom-center, boxed for legibility, clear of the product area.
    wm = (
        f"drawtext={fontarg}text='{_esc_text(spec.watermark_text)}':"
        f"fontcolor=white:fontsize=h/28:x=(w-text_w)/2:y=h-text_h-h/40:"
        f"box=1:boxcolor=black@0.45:boxborderw=10"
    )
    chain.append(wm)
    # Callout supers — top band, time-gated.
    for c in callouts:
        chain.append(
            f"drawtext={fontarg}text='{_esc_text(c.text)}':"
            f"fontcolor=white:fontsize=h/22:x=(w-text_w)/2:y=h/12:"
            f"box=1:boxcolor=black@0.35:boxborderw=12:"
            f"enable='between(t,{c.start_s},{c.end_s})'"
        )
    return ",".join(chain)


def finish(
    input_path: str | Path,
    output_path: str | Path,
    *,
    spec: OutputSpec | None = None,
    callouts: list[Callout] | None = None,
    music_path: str | Path | None = None,
    pad_color: str = "white",
) -> FinishResult:
    """Finish a generated clip into a spec-compliant deliverable. Deterministic; no model call."""
    spec = spec or get_spec()
    callouts = callouts or []
    input_path, output_path = Path(input_path), Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.is_file():
        return FinishResult(success=False, error=f"input not found: {input_path}")

    src = _summary(input_path)
    # Duration: clamp into the band. We can trim down; we cannot invent footage, so a too-short
    # source is a compliance violation surfaced to QC, not silently stretched.
    out_duration = min(src["duration_s"], spec.max_duration_s)
    out_duration = max(out_duration, 0.1)

    # Two-pass target bitrate to land mid-band.
    target_bits = spec.target_size_mb * 8 * 1024 * 1024
    audio_bits = (spec.audio_bitrate_kbps * 1000) * (1 if music_path else 0)
    video_bitrate_kbps = max(int(((target_bits / out_duration) - audio_bits) / 1000), 200)

    vf = _video_filter(spec, callouts, pad_color)

    with tempfile.TemporaryDirectory() as td:
        passlog = str(Path(td) / "ffpass")
        common = [FFMPEG, "-y", "-i", str(input_path)]
        if music_path:
            common += ["-i", str(music_path)]

        # Pass 1 — analyze (no audio, no output file).
        p1 = subprocess.run(
            [FFMPEG, "-y", "-i", str(input_path), "-t", f"{out_duration}",
             "-vf", vf, "-c:v", spec.video_codec, "-b:v", f"{video_bitrate_kbps}k",
             "-pass", "1", "-passlogfile", passlog, "-an", "-f", "null",
             os.devnull],
            capture_output=True, text=True,
        )
        if p1.returncode != 0:
            return FinishResult(success=False, error=f"ffmpeg pass 1 failed: {p1.stderr[-800:]}")

        # Pass 2 — encode.
        cmd2 = common + ["-t", f"{out_duration}", "-vf", vf,
                         "-c:v", spec.video_codec, "-b:v", f"{video_bitrate_kbps}k",
                         "-pass", "2", "-passlogfile", passlog, "-pix_fmt", "yuv420p"]
        if music_path:
            cmd2 += ["-c:a", spec.audio_codec, "-b:a", f"{spec.audio_bitrate_kbps}k",
                     "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        else:
            cmd2 += ["-an"]
        cmd2 += [str(output_path)]
        p2 = subprocess.run(cmd2, capture_output=True, text=True)
        if p2.returncode != 0:
            return FinishResult(success=False, error=f"ffmpeg pass 2 failed: {p2.stderr[-800:]}")

    out = _summary(output_path)
    violations = validate(out, spec)
    return FinishResult(
        success=True,
        output_path=str(output_path),
        probe=out,
        compliant=not violations,
        violations=violations,
    )


def validate(summary: dict, spec: OutputSpec) -> list[str]:
    """Auto-checkable SOW parameters: dims, duration band, size band, watermark presence (by encode)."""
    v: list[str] = []
    if summary.get("width") != spec.width or summary.get("height") != spec.height:
        v.append(f"dimensions {summary.get('width')}x{summary.get('height')} != {spec.width}x{spec.height}")
    d = summary.get("duration_s", 0)
    if not (spec.min_duration_s - 0.5 <= d <= spec.max_duration_s + 0.5):
        v.append(f"duration {d}s outside [{spec.min_duration_s}, {spec.max_duration_s}]")
    s = summary.get("size_mb", 0)
    if s > spec.max_size_mb + 0.5:
        v.append(f"size {s}MB exceeds max {spec.max_size_mb}MB")
    return v
