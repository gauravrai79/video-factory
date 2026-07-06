"""Deterministic finishing + assembly layer — FFmpeg, 100% automatable.

Turns a storyboard's per-shot media (generated stills and video clips) into one finished post:
  - Ken Burns motion on stills (free pan/zoom — the cost lever that avoids paid video)
  - normalize every shot to the exact platform dimensions (scale-to-fit + pad, never crop)
  - stitch shots in order (hard cut or crossfade)
  - optional opening hook super + optional @handle watermark (off by default)
  - mux non-copyrighted background music (generation runs audio-off)
  - encode to the platform spec at a target bitrate

This layer guarantees spec compliance regardless of what the models produced.
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
    """Find ffmpeg/ffprobe across PATH, env override, and the winget install dir.
    The override is only trusted if it actually points at a file — a blank/garbage env value
    (e.g. an inline .env comment mis-parsed by dotenv) must not shadow auto-detection."""
    override = (os.environ.get(env_var) or "").strip()
    if override and Path(override).is_file():
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


def media_duration(path: str | Path) -> float:
    """Duration in seconds of any media file (audio or video), 0.0 on failure."""
    try:
        return round(float(probe(path).get("format", {}).get("duration", 0) or 0), 3)
    except Exception:
        return 0.0


def stub_image(output_path: str | Path, *, width: int = 1280, height: int = 720,
               color: str = "gray") -> bool:
    """Write a solid placeholder PNG. Used by no-key image stubs so the whole pipeline (refs ->
    scenes -> assembly) runs end-to-end at $0 for tests, matching the voice/lipsync stubs."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}",
           "-frames:v", "1", str(out)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def stub_video(output_path: str | Path, *, duration_s: float = 6.0, width: int = 1280,
               height: int = 720, color: str = "gray") -> bool:
    """Write a placeholder MP4 (solid color + silent audio track) of the given length. Used by the
    no-key native-video (Veo) stub so refs->scenes->assembly run end-to-end at $0, and the clip
    carries an audio track like the real native-audio output."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = max(1.0, float(duration_s))
    cmd = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r=24",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-shortest", str(out)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


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


@dataclass
class ShotMedia:
    """One resolved shot ready to assemble: a still image (Ken Burns) or a video clip."""
    render_mode: str               # "kenburns" | "video"
    media_path: str                # png for kenburns, mp4 for video
    duration_s: float
    zoom: str = "in"               # "in" | "out" — Ken Burns direction (stills only)


def _overlays_filter(spec: OutputSpec, hook: str | None) -> str:
    """drawtext pieces appended after dimensioning: optional @handle watermark + opening hook."""
    font = _font_file()
    fontarg = f"fontfile='{_esc_font(font)}':" if font else ""
    pieces: list[str] = []
    if spec.watermark_text:
        pieces.append(
            f"drawtext={fontarg}text='{_esc_text(spec.watermark_text)}':"
            f"fontcolor=white@0.85:fontsize=h/34:x=(w-text_w)/2:y=h-text_h-h/40:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2"
        )
    if hook:
        pieces.append(
            f"drawtext={fontarg}text='{_esc_text(hook)}':"
            f"fontcolor=white:fontsize=h/22:x=(w-text_w)/2:y=h/8:"
            f"box=1:boxcolor=black@0.4:boxborderw=16:enable='between(t,0.3,2.8)'"
        )
    return ",".join(pieces)


def _dimension_chain(spec: OutputSpec, pad_color: str) -> str:
    return (f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,"
            f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2:color={pad_color},"
            f"fps={spec.fps},setsar=1,format=yuv420p")


def ken_burns_clip(image_path: str | Path, out_path: str | Path, *, duration_s: float,
                   spec: OutputSpec, zoom: str = "in", pad_color: str = "black") -> bool:
    """Animate a still with a slow pan/zoom (free motion). Oversamples first so zoompan doesn't
    jitter, then renders to exact spec dims."""
    fps = spec.fps
    frames = max(int(round(duration_s * fps)), 1)
    ow, oh = spec.width * 2, spec.height * 2          # oversample to keep the zoom smooth
    # Subtle, slow drift (max ~1.12x) reads as gentle motion, not a hard slideshow zoom.
    if zoom == "out":
        zexpr = "if(eq(on,0),1.12,max(zoom-0.0009,1.0))"
    else:
        zexpr = "min(zoom+0.0009,1.12)"
    vf = (
        f"scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},"
        f"zoompan=z='{zexpr}':d={frames}:fps={fps}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={spec.width}x{spec.height},"
        f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2:color={pad_color},"
        f"setsar=1,format=yuv420p"
    )
    cmd = [FFMPEG, "-y", "-loop", "1", "-i", str(image_path), "-t", f"{duration_s}",
           "-vf", vf, "-r", str(fps), "-c:v", spec.video_codec, "-pix_fmt", "yuv420p",
           "-an", str(out_path)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def normalize_video_shot(clip_path: str | Path, out_path: str | Path, *, duration_s: float,
                         spec: OutputSpec, pad_color: str = "black", keep_audio: bool = False) -> bool:
    """Trim a generated video clip to the shot duration and conform it to spec dims/fps.
    keep_audio=True preserves the clip's own audio track (e.g. a lip-sync talking clip)."""
    cmd = [FFMPEG, "-y", "-i", str(clip_path), "-t", f"{duration_s}",
           "-vf", _dimension_chain(spec, pad_color), "-r", str(spec.fps),
           "-c:v", spec.video_codec, "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-b:a", "128k"] if keep_audio else ["-an"])
    cmd += [str(out_path)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def _video_graph(n: int, durations: list[float], transition_s: float) -> tuple[str, str]:
    """Filtergraph joining n normalized inputs. transition_s>0 -> crossfade chain, else hard concat.
    Returns (graph, out_label)."""
    if n == 1:
        return "", "[0:v]"
    if transition_s and transition_s > 0:
        segs, prev, timeline = [], "[0:v]", durations[0]
        for k in range(1, n):
            off = max(timeline - transition_s, 0.0)
            out = f"[x{k}]"
            segs.append(f"{prev}[{k}:v]xfade=transition=fade:duration={transition_s}:offset={off:.3f}{out}")
            prev, timeline = out, timeline + durations[k] - transition_s
        return ";".join(segs), prev
    inp = "".join(f"[{i}:v]" for i in range(n))
    return f"{inp}concat=n={n}:v=1:a=0[cat]", "[cat]"


def assemble(
    shots: list[ShotMedia],
    output_path: str | Path,
    *,
    spec: OutputSpec | None = None,
    music_path: str | Path | None = None,
    hook: str | None = None,
    pad_color: str = "black",
    transition_s: float = 0.0,
) -> FinishResult:
    """Assemble per-shot media into one finished post. Deterministic; no model call.
    transition_s>0 crossfades between shots (subtle); 0 is a hard cut."""
    spec = spec or get_spec()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not shots:
        return FinishResult(success=False, error="no shots to assemble")

    missing = [s.media_path for s in shots if not Path(s.media_path).is_file()]
    if missing:
        return FinishResult(success=False, error=f"missing shot media: {missing[:3]}")

    with tempfile.TemporaryDirectory() as td:
        # 1) Normalize each shot to identical spec params so they concat cleanly.
        parts: list[str] = []
        for i, sh in enumerate(shots):
            part = str(Path(td) / f"shot_{i:03d}.mp4")
            ok = (ken_burns_clip(sh.media_path, part, duration_s=sh.duration_s, spec=spec,
                                 zoom=sh.zoom, pad_color=pad_color)
                  if sh.render_mode == "kenburns"
                  else normalize_video_shot(sh.media_path, part, duration_s=sh.duration_s,
                                            spec=spec, pad_color=pad_color))
            if not ok or not Path(part).is_file():
                return FinishResult(success=False, error=f"failed to normalize shot {i} ({sh.render_mode})")
            parts.append(part)

        overlays = _overlays_filter(spec, hook)

        # 2) Concat (filter_complex, robust across identical inputs) + overlays + music, encode to spec.
        cmd = [FFMPEG, "-y"]
        for p in parts:
            cmd += ["-i", p]
        if music_path:
            cmd += ["-i", str(music_path)]

        # Offsets must come from the ACTUAL normalized clip lengths, not the scripted
        # durations: a hero video may be physically shorter than its scripted slot, and
        # feeding scripted values to the chained xfade drifts each offset past the real
        # end of the intermediate stream, collapsing the whole cut to a few seconds.
        actual_durs = [media_duration(p) for p in parts]
        graph, base_label = _video_graph(len(parts), actual_durs, transition_s)
        if overlays:
            filtergraph = (graph + ";" if graph else "") + f"{base_label}{overlays}[v]"
            vlabel = "[v]"
        else:
            filtergraph, vlabel = graph, base_label

        if filtergraph:
            cmd += ["-filter_complex", filtergraph, "-map", vlabel]
        else:                                   # single shot, no overlays — map directly
            cmd += ["-map", "0:v:0"]
        cmd += ["-c:v", spec.video_codec, "-b:v", f"{spec.video_bitrate_kbps}k",
                "-pix_fmt", "yuv420p", "-r", str(spec.fps)]
        if music_path:
            mi = len(parts)
            cmd += ["-map", f"{mi}:a:0", "-c:a", spec.audio_codec,
                    "-b:a", f"{spec.audio_bitrate_kbps}k", "-shortest"]
        else:
            cmd += ["-an"]
        cmd += [str(output_path)]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return FinishResult(success=False, error=f"assembly failed: {res.stderr[-800:]}")

    out = _summary(output_path)
    violations = validate(out, spec)
    return FinishResult(success=True, output_path=str(output_path), probe=out,
                        compliant=not violations, violations=violations)


@dataclass
class ScoredShot:
    """A shot for the audio-scored assembly: video + a per-scene voice track (or embedded audio)."""
    render_mode: str                 # "kenburns" (still) | "video" (silent clip) | "talking" (clip w/ audio)
    media_path: str
    duration_s: float
    audio_path: str | None = None    # scene voice track (narration+dialogue); None -> silence
    zoom: str = "in"


def assemble_scored(
    shots: list[ScoredShot],
    output_path: str | Path,
    *,
    spec: OutputSpec | None = None,
    music_path: str | Path | None = None,
    music_gain: float = 0.10,          # bed sits well under the voice (was 0.16 — too loud over VO)
    pad_color: str = "black",
) -> FinishResult:
    """Assemble shots with per-scene audio into one voiced+scored cut. Each scene becomes a
    self-contained video+audio clip (so audio stays synced), then all are concatenated and a music
    bed is mixed under the voices (ducked by `music_gain`). Deterministic; no model call."""
    spec = spec or get_spec()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not shots:
        return FinishResult(success=False, error="no shots to assemble")
    missing = [s.media_path for s in shots if not Path(s.media_path).is_file()]
    if missing:
        return FinishResult(success=False, error=f"missing shot media: {missing[:3]}")

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        scene_clips: list[str] = []
        for i, sh in enumerate(shots):
            vpart = str(tdp / f"v_{i:03d}.mp4")
            if sh.render_mode == "kenburns":
                ok = ken_burns_clip(sh.media_path, vpart, duration_s=sh.duration_s, spec=spec,
                                    zoom=sh.zoom, pad_color=pad_color)
            elif sh.render_mode == "talking":
                ok = normalize_video_shot(sh.media_path, vpart, duration_s=sh.duration_s, spec=spec,
                                          pad_color=pad_color, keep_audio=True)
            else:
                ok = normalize_video_shot(sh.media_path, vpart, duration_s=sh.duration_s, spec=spec,
                                          pad_color=pad_color)
            if not ok or not Path(vpart).is_file():
                return FinishResult(success=False, error=f"failed to render shot {i} ({sh.render_mode})")

            if sh.render_mode == "talking":       # already carries its own audio
                scene_clips.append(vpart)
                continue

            apart = str(tdp / f"a_{i:03d}.m4a")
            if sh.audio_path and Path(sh.audio_path).is_file():
                acmd = [FFMPEG, "-y", "-i", str(sh.audio_path), "-af", "apad", "-t", f"{sh.duration_s}",
                        "-ar", "44100", "-ac", "2", "-c:a", "aac", "-b:a", "128k", apart]
            else:
                acmd = [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", f"{sh.duration_s}", "-c:a", "aac", "-b:a", "128k", apart]
            if subprocess.run(acmd, capture_output=True, text=True).returncode != 0:
                return FinishResult(success=False, error=f"failed to build audio for shot {i}")

            scene = str(tdp / f"s_{i:03d}.mp4")
            mcmd = [FFMPEG, "-y", "-i", vpart, "-i", apart, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", scene]
            if subprocess.run(mcmd, capture_output=True, text=True).returncode != 0:
                return FinishResult(success=False, error=f"failed to mux shot {i}")
            scene_clips.append(scene)

        # concat all scene clips (video+audio) + mix the music bed under the voices, in one command.
        cmd = [FFMPEG, "-y"]
        for sc in scene_clips:
            cmd += ["-i", sc]
        if music_path:
            cmd += ["-stream_loop", "-1", "-i", str(music_path)]
        n = len(scene_clips)
        concat_in = "".join(f"[{i}:v][{i}:a]" for i in range(n))
        fg = f"{concat_in}concat=n={n}:v=1:a=1[cv][ca]"
        if music_path:
            fg += f";[{n}:a]volume={music_gain}[mus];[ca][mus]amix=inputs=2:duration=first:dropout_transition=0[a]"
            alabel = "[a]"
        else:
            alabel = "[ca]"
        cmd += ["-filter_complex", fg, "-map", "[cv]", "-map", alabel,
                "-c:v", spec.video_codec, "-b:v", f"{spec.video_bitrate_kbps}k",
                "-pix_fmt", "yuv420p", "-r", str(spec.fps),
                "-c:a", spec.audio_codec, "-b:a", f"{spec.audio_bitrate_kbps}k", "-shortest",
                str(output_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return FinishResult(success=False, error=f"scored assembly failed: {res.stderr[-800:]}")

    out = _summary(output_path)
    violations = validate(out, spec)
    return FinishResult(success=True, output_path=str(output_path), probe=out,
                        compliant=not violations, violations=violations)


def validate(summary: dict, spec: OutputSpec) -> list[str]:
    """Auto-checkable delivery parameters: exact dimensions and duration within the platform band."""
    v: list[str] = []
    if summary.get("width") != spec.width or summary.get("height") != spec.height:
        v.append(f"dimensions {summary.get('width')}x{summary.get('height')} != {spec.width}x{spec.height}")
    d = summary.get("duration_s", 0)
    if not (spec.min_duration_s - 0.5 <= d <= spec.max_duration_s + 0.5):
        v.append(f"duration {d}s outside [{spec.min_duration_s}, {spec.max_duration_s}]")
    return v
