# AI Influencer Factory

A staged, human-gated studio for producing **AI video** — from a recurring cartoon/comic series with
persistent characters to a one-off ad compiled from a Markdown script. You drive a channel or a script
through a production line (idea → script → keyframes → video → audio → assembly), reviewing and
re-rolling at every gate, and the factory renders a finished, downloadable cut.

> This is an **orchestration project, not an ML project**. Generation is a set of API calls behind a
> stable interface; the engineering is everything around it — a stage-gated state machine, character
> consistency, a keyframe/video split, script + vision QC, cost-fitting, deterministic FFmpeg
> assembly, and per-episode format config.

The repo began as an ecommerce product-video pipeline and was repurposed; the FFmpeg finishing,
job store, and cost/QC scaffolding carried over, and the content layer was rebuilt around a
character-driven, human-in-the-loop production pipeline.

---

## The two ways to make a video

**1. A channel series** (recurring characters, many episodes)

```
Channel (show bible: premise · art style · cast · format)
  └─ Episode ── Setup → Idea → Script → Refs → Scenes → Audio → Assembly → Done
                (each stage generates its artifact, then HOLDS at a human gate)
```

**2. Quick Video** (a one-off, outside channels) — paste a Markdown "prompt-pack" (an ad, an
explainer) and it compiles straight into the same Refs → Scenes → Assembly engine, honoring your
prompts verbatim, with a global voiceover track and a timed on-screen-title `.srt`.

Nothing runs until a human advances it; every paid stage only runs on the previous stage's approved
artifact. That's the token-safety model.

## The engine

| Job | Model / tool | Notes |
|---|---|---|
| **Video (per scene)** | **Veo 3.1 Lite** (fal, image-to-video) | native audio in ONE pass — dialogue + lip-sync + SFX; ~$0.05/s @720p |
| **Keyframe still** | **Nano Banana / Gemini** (OpenRouter) | character reference images + `image_config.aspect_ratio` → identity-locked, native portrait/landscape |
| **Voiceover** | **ElevenLabs** (fal) | one clean narration track, ducked under music (one-off) |
| **Music** | fal music gen | optional bed |
| **Asset scenes / Ken Burns** | **FFmpeg** | real screenshots/recordings animated (pan/zoom), $0 |

Every scene is a keyframe animated by Veo: the **still carries the character/style, the video prompt
carries only motion** (the "frozen beat / motion" split), which keeps identity stable and stops the
model hallucinating a mid-air pose into a static frame. **Synthetic personas only — never a real
person's likeness.**

## What's in the box

- **Guided channel wizard** — a one-liner becomes a name, tagline, premise and tone (LLM premise
  assistant), and you pick the look from a **visual gallery of 31 art styles** (same mascot rendered
  in each).
- **Per-episode format config** (the Setup stage) — landscape/portrait (native 9:16, not cropped),
  length → scene count, resolution, language, pacing, music, transitions, QC bar. Platform presets
  (YouTube / Shorts / Reel / TikTok). The same channel can ship a 2-min landscape episode and a 30s
  vertical Reel.
- **Script QC gate** — a cross-model judge scores hook / narrative / ending / comedy / virality into
  a 0–100 composite and drives a targeted revision loop until it passes (or parks with a scorecard).
  It also distills a per-scene **intent contract** (`must_show`) that flows downstream.
- **Vision QC** — each generated still and clip is checked against its intent (elements present,
  on-model, action happened); a failure triggers one corrective re-roll and a ⚠ badge.
- **Per-scene control** — the Scenes stage is a grid: edit any Veo prompt, generate one / selected /
  all, re-roll, with speech-fit durations so lip-sync isn't rushed.
- **Transition library** — per-channel reusable ~2s Veo clips, auto-spliced by cut-rhythm rules
  (hard-cut default, only at location changes) with a human **seam editor** at assembly.
- **Assembly** — clips (native audio) + transitions + optional music + **loudness normalization**
  (−14 LUFS / −1 dBTP) → final MP4.
- **Quick Video / one-off** — Markdown → video, with **asset scenes**: drop in a real product
  screenshot or screen-recording for a specific beat (rendered with a pan so wide UI isn't cropped),
  while AI carries the rest. Text-free master + `titles.srt` for external compositing.

## Architecture

```
backend/
  api.py              FastAPI: channels · characters · episodes · one-off · transitions · media · styles
  episode_pipeline.py the stage state machine: run_stage / approve / reroll per stage; generation orchestration
  episodes.py         Episode entity + store (stage, config, scenes, script_qc, timeline)
  channels.py         Channel (show bible) + store
  characters.py       Character (persona, reference images = identity, speaker tag)
  formats.py          per-episode format config + platform presets + OutputSpec (aspect/resolution/length)
  oneoff.py           Quick Video: compile a Markdown pack → an Episode under a hidden system channel
  transitions.py      per-channel transition clip library + cut-rhythm splicer + seam overrides
  finishing.py        deterministic FFmpeg: Ken Burns · asset pan/fit · stitch · music/VO duck · loudnorm
  styles.py           31-style art library (+ scripts/gen_style_samples.py renders the visual gallery)
  agents/
    writer.py         script writer (story structure, keyframe/video split, cast auto-fix) + revision
    script_qc.py      cross-model QC judge + intent contract
    media_qc.py       vision QC of stills/clips against the intent (Gate 2 / Gate 3)
    concept.py        channel-concept assistant (one-liner → name/tagline/premise/tone/styles)
    ad_compiler.py    Markdown prompt-pack → structured scenes (verbatim prompts, VO, titles, assets)
    shot_prompt.py    keyframe (still) + Veo (video) prompt builders
  capabilities/       fal_video (Veo) · fal_image · or_image (Gemini) · voice (ElevenLabs) · music · pricing
  jobstore.py         SQLite (Postgres-shaped) · hash-chained audit · idempotency
frontend/             zero-build vanilla-JS SPA: channel wizard · workspace stepper · scene grid · Quick Video
scripts/              serve.py · e2e_smoke.py (run before every handover) · gen_style_samples.py
```

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env     # add FAL_KEY (Veo/stills/voice) and OPENROUTER_API_KEY (writer/QC/Gemini)
# requires ffmpeg on PATH (or set FFMPEG_BIN / FFPROBE_BIN)

python scripts/serve.py  # -> http://localhost:8310
```

In the console: **New channel** (guided wizard) → create an episode → walk it through the stages, or
open **Quick Video** to compile a Markdown script into a one-off. Real generation needs the API keys;
without them every capability stubs at $0 so the whole pipeline is runnable/testable.

```bash
python scripts/e2e_smoke.py   # drives the full pipeline in stub mode ($0); run before shipping changes
```

## Cost

A ~2-minute episode is roughly **$4–5** (Veo scenes + a little for stills/VO/music); asset scenes and
Ken Burns are **$0**. Every stage is idempotent (re-running never re-bills a finished scene) and gated,
so you approve spend stage by stage.

## Status

Runnable end-to-end and verified: the staged channel pipeline (idea → assembly), Quick Video one-off
with asset scenes, script + vision QC, per-episode format config with native portrait, the transition
library, and loudness-normalized assembly all work; `scripts/e2e_smoke.py` covers the flow in stub
mode. Deployment target is **Railway** (long-running workers + FFmpeg + Postgres).

**Not yet:** burned-in captions, auto-publishing (YouTube / Instagram), 9:16 re-render of a landscape
master, and analytics feeding back into ideation.
