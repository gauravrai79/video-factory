# AI Influencer Factory

A high-throughput media production system for **AI personalities**. Each character is a persistent,
visually-consistent persona; the factory turns a character + a content brief into a complete,
auto-assembled short-form post (reel / short / square), at scale, with minimal human intervention.

> This is an **orchestration project, not an ML project**. Generation is a set of API calls behind a
> stable interface; the engineering is everything around it — character consistency, story planning,
> a cost-aware still/video mix, deterministic assembly, a queue with SLA timers, identity QC, and an
> auditable state machine.

The repo began as an ecommerce product-video pipeline and was repurposed: the hard infrastructure
(queue, workers, retries, cost ceiling, SLA, hash-chained audit, FFmpeg finishing, VLM QC) is reused
almost unchanged; only the content layer is new.

---

## The core idea

```
Product → Prompt → Video            (old)
Character → Storyboard → Post       (new)
```

The primary entity is a **Character**. A storyboard planner expands a brief into an ordered shot
list, and the **cost lever** is per-shot: most shots are a generated still animated by **free FFmpeg
Ken Burns** motion; only a small budget of "hero" shots spend on paid image-to-video. A 6-shot reel
typically costs **~$0.50–1.00** instead of $3–4 of all-video generation.

```
Character (persona + reference images = "DNA")
   → Storyboard planner (brief + scene templates → shot list, each tagged still | kenburns | video)
      → per shot:  still (Nano Banana, identity-locked)  ──┬─ kenburns → free FFmpeg pan/zoom
                                                           └─ video    → Wan 2.5 / Kling 2.5 Turbo
         → Assemble (stitch shots, music, optional hook/handle) → identity QC → delivered reel
```

## Models (fal.ai)

| Job | Model | Cost |
|---|---|---|
| Character-consistent still | **Nano Banana 2** (up to 5 people consistent, no fine-tune) | ~$0.10 / image |
| Cheapest HD video | **Wan 2.5** (480p, default) | $0.05 / s |
| Higher-quality video | **Kling 2.5 Turbo Pro** | $0.07 / s |
| Ken Burns motion on a still | **FFmpeg `zoompan`** | $0.00 |

Single fal integration; models are config strings (`backend/capabilities/pricing.py`). Glamour/suggestive
personas use fal's `safety_tolerance` (1–6) per character. **Synthetic personas only — never a real
person's likeness.** Seedance is intentionally excluded (too expensive).

## Architecture

```
backend/
  api.py            FastAPI: characters · storyboards · jobs · qc · media · scenes · summary
  pipeline.py       per-post state machine: pending → generating (all shots) → finishing
                    (assemble) → qc → approved/rework → delivered  · cost ceiling · retries
  characters.py     Character entity + store (persona, reference images = "DNA", safety_tolerance)
  scene_library.py  ~25 curated scene templates the planner sequences from
  agents/
    storyboard.py   brief + character + templates → priced shot list (still | kenburns | video)
    prompt_builder.py  per-shot still/motion prompts (deterministic; optional Gemini refine)
    qc_flagger.py   identity/anatomy QC via fal vision (advisory; reference-aware)
  capabilities/
    fal_image.py    character-consistent stills + reference-sheet minting
    fal_video.py    image-to-video (Wan / Kling) + shared fal queue infra
    pricing.py      central model price table
    cost.py         per-post + content-calendar projections
  finishing.py      deterministic FFmpeg: Ken Burns · normalize · stitch · music · overlays · encode
  jobqueue/         pluggable queue: in-process `sync` (default) | Redis/RQ
  jobstore.py       SQLite today (Postgres-shaped) · hash-chained audit · idempotency
  sla.py            tier-based SLA timers, breaches derived from the audit log
frontend/           zero-build console: characters · new post (preview/price) · dashboard · QC · player
```

Every post is **idempotent** (re-running a brief reuses the job, never re-bills), **priority-ordered**
(premium characters jump the queue), **SLA-timed**, protected by a **per-post cost ceiling**, and
recorded in a **hash-chained audit log**. One failed video shot degrades gracefully to free Ken Burns
rather than failing the whole post. If a character has no reference images, identity is **bootstrapped
from the first generated still** so the rest of the post stays consistent.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add FAL_KEY for real generation
# requires ffmpeg on PATH (or set FFMPEG_BIN / FFPROBE_BIN)

# Plan + price one post (dry run, no paid calls):
python scripts/run_one.py --character samples/luna.json --brief "beach day" --tags travel,glamour

# Real generation (stills + video + assembly → delivered reel):
python scripts/run_one.py --character samples/luna.json --brief "beach day" --tags travel,glamour --execute
```

`samples/luna.json` (glamour persona) and `samples/jango.json` (a dog — characters aren't only human)
show the character schema. Provide real photos by setting `reference_images` to local paths, or let
the factory mint a reference sheet from `dna_prompt`.

## Content calendar (batch)

```bash
# Plan a week of posts for a character, dry run, with the SLA view:
python scripts/run_batch.py --character samples/luna.json --posts 7 --tags travel,glamour --sla

# Real generation across the batch:
python scripts/run_batch.py --character samples/luna.json --posts 7 --tags travel,glamour --execute

# Production fan-out: enqueue to Redis, drain with N workers:
VF_QUEUE_BACKEND=rq python scripts/run_batch.py --character samples/luna.json --posts 7 --enqueue-only
VF_QUEUE_BACKEND=rq python scripts/worker.py
```

## Console

```bash
python scripts/serve.py           # -> http://localhost:8310
```

Create characters, compose a post (preview the priced shot list before committing), watch posts run on
the background worker, review the in-browser player + identity-QC verdict + hash-chained audit, and
clear the human QC gate. The sync backend drains in a background thread so the UI stays responsive
during multi-minute generations; switch to `VF_QUEUE_BACKEND=rq` for multi-worker fan-out.

## Status

**v1 — generation only — runnable and verified.** Character store, storyboard planner, cost-mixed
still/video generation, FFmpeg Ken Burns + multi-shot assembly, identity QC, the full state machine
(generate → assemble → QC → deliver), idempotency, priority, SLA, and per-post hash-chained audit all
run; the deterministic parts (planning, assembly) verified end-to-end with real FFmpeg. Deployment
target is **Railway** (long-running workers + FFmpeg + Postgres; **not** Vercel — wrong shape for this
workload).

**Next phases (not in v1):** caption/hashtag generation, auto-publishing (Instagram Graph API,
YouTube), engagement analytics feeding back into planning, and per-character LoRA for the highest
consistency tier.
