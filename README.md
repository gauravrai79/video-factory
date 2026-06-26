# Video Factory

High-throughput **image-to-video** automation for ecommerce catalogs (Flipkart Lifestyle/Apparel
engagement; multi-tenant by design). Turns a CSV of product SKUs into spec-compliant, watermarked,
QC-gated short videos at **20,000+/month**.

> This is a **batch orchestration project, not an ML project**. The generative step is a single API
> call behind a stable interface; the engineering is the pipeline around it — ingestion, a queue with
> SLA timers, deterministic finishing, a QC gate, and delivery.

---

## How this fits BGO Spine

This repo is a **self-contained Spine project**. It runs standalone today and is built to plug into
the Spine control/governance plane in production with **no code change** — exactly the `synced`
project model in Spine's `ACCESS_AND_ARCHITECTURE` §15.

It couples to Spine through the documented four touchpoints only (no shared code):

| Spine touchpoint | This repo |
|---|---|
| `spine.skills.json` (registry + connector block) | [`spine/spine.skills.json`](spine/spine.skills.json) |
| AOP (governed run procedure) | [`spine/aop/video_factory.yaml`](spine/aop/video_factory.yaml) |
| Connector → project API | `backend/` FastAPI app (the connector calls these endpoints) |
| `launchUrl` → product UI | `frontend/` ops + QC console |

**Governance reuse — the key win.** The factory inherits Spine's hardest-to-build parts instead of
re-implementing them:

| Factory need (from the SOW) | Spine primitive that *is* this |
|---|---|
| QC human gate (reviewer clears/rejects → rework loop) | **Approval gate** — writes go `pending → approve → execute` |
| Auto-QC posture (auto-pass clean, human only on flagged) | Auto-checks auto-approve; flagged → Spine **Approvals queue** |
| Per-video audit / compliance trail | **Hash-chained audit bus** (mirrored locally in `JobEvent`) |
| Multi-client isolation | **`(tenant_id, project)` scoping + Postgres RLS** |
| Governed access to fal.ai / Replicate / Drive | **Connector allow-list** |
| Promote a better prompt/model strategy after measuring reshoot rate | **Skill lifecycle Draft → … → Production, eval-gated** |
| Ops auth, Cognito later | Spine auth (`SPINE_AUTH_ENABLED` flip) |

Until plugged into Spine, the same seams run locally: the deterministic finishing/throughput lives in
this project's worker; the *decisions and writes* (generate-approve, deliver-approve) are modeled to
route through Spine's approval + audit in production.

---

## Architecture

```
Spine (control/governance plane — reused in prod)
   AOP run → guardrails → connector allow-list → APPROVAL GATE (=QC) → hash-chained audit
        │  governs decisions + writes
        ▼
Video Factory project (this repo)
   ├─ backend/         FastAPI + Postgres: job state machine + queue (Redis/RQ)
   │     pending → generating → finishing → qc → approved/rework → delivered
   │     SLA timers · idempotency · priority queue · model fallback   (deterministic spine)
   ├─ agents/          ADK (Spine standard, Gemini): Prompt-Builder · QC-flagger · Rework
   ├─ capabilities/    harvested from OpenMontage: fal.ai Kling/Seedance clients · cost model
   ├─ finishing.py     deterministic FFmpeg: dims · 2-pass size · clamp · watermark · music · supers
   └─ frontend/        ops console: CSV upload · batch dashboard · QC review screen
```

### Generation layer — aggregator, not direct vendor
Routes through **fal.ai** (primary) with **Replicate** as secondary. One integration; swap models by
changing a config string. This protects against vendor shutdowns (e.g. Sora's 2026 sunset) and lets
you A/B models per SKU category.

- **Default — Kling 2.1 Standard** (`VF_KLING_TIER`): the cost-smart volume tier — $0.56 per 10s clip
  vs $0.98 for Pro (~43% cheaper, ~$8K/mo less at 20K). Failed tasks don't consume credits. Bump to
  `pro` only if measured reshoot rate justifies it — generation cost dominates the P&L.
- **Escalation for hero SKUs / difficult prints — Seedance 2.0**: up to 9 reference images for garment
  fidelity (~$3.03 per 10s clip). Routed automatically; reserve the spend for SKUs that need it.

### Finishing layer — deterministic, 100% automatable
Everything the SOW mandates that isn't generative: enforce dimensions, two-pass encode to the 6–10 MB
band, clamp duration, burn the "Synthetically Generated" watermark, overlay callout supers, mux
non-copyrighted music, enforce the end-frame rule. **Generation runs audio-off; music is added here**
— cheaper and more controllable.

---

## Quick start (Phase-1 vertical slice — one SKU, no queue)

```bash
pip install -r requirements.txt
cp .env.example .env          # add FAL_KEY (+ GOOGLE_API_KEY for the Prompt-Builder agent)

# Dry run — builds prompt, prices the job, no paid API call:
python scripts/run_one.py --csv samples/skus.csv --row 0

# Real generation (announces cost, calls fal.ai, finishes to spec):
python scripts/run_one.py --csv samples/skus.csv --row 0 --execute
```

The slice does: **CSV row → Prompt-Builder → Kling image-to-video (fal.ai) → deterministic FFmpeg
finish → spec-compliant MP4 + hash-chained audit log.**

## Batch orchestration (Phase-2 — CSV → queue → workers)

```bash
# Dry run the whole CSV through the queue (no paid calls) and print the SLA view:
python scripts/run_batch.py --csv samples/skus.csv --sla

# Real generation across the batch (announces cost; needs FAL_KEY):
python scripts/run_batch.py --csv samples/skus.csv --execute

# Production fan-out: enqueue to Redis, drain with N parallel workers:
VF_QUEUE_BACKEND=rq python scripts/run_batch.py --csv samples/skus.csv --enqueue-only
VF_QUEUE_BACKEND=rq python scripts/worker.py      # run several of these
```

**Queue is pluggable** (`VF_QUEUE_BACKEND`): `sync` (default, in-process, zero infra, Windows-safe)
or `rq` (Redis, multi-worker, prod). One env var flips it — batch ingestion and the worker task are
backend-agnostic. Each job is **idempotent** (re-ingesting a CSV reuses jobs, never re-bills),
**priority-ordered** (premium/hero SKUs jump the queue), **SLA-timed** (tier-based enqueue→delivered
budgets, breaches derived from the audit log), and protected by a **per-job cost ceiling**. Generation
**retries and falls back** Kling↔Seedance per the AOP `on_failure: fallback_model` edge.

## Ops + QC console (Phase-3 UI)

```bash
pip install -r requirements.txt   # adds fastapi + uvicorn
python scripts/serve.py           # -> http://localhost:8310
```

A local web console (FastAPI + a zero-build SPA in [`frontend/`](frontend/)) over the same pipeline:

- **Ingest** a SKU CSV (drag the file in), pick dry-run vs **Execute (paid)**, pin a model, choose the
  output **spec** (landscape / portrait), toggle the **human QC gate**, optionally finish a stand-in
  clip — then jobs run on the background worker. Rows missing an `image_url` are flagged pre-flight.
- **Dashboard** — live job table (state, model, dry/live cost, SLA bar, fallback marker) + headline
  stats, auto-polling with a worker progress banner while the queue drains.
- **Job drawer** — in-browser video player (seekable), spec-compliance probe, est/actual cost, the
  **VLM QC verdict** with flagged issues, the fal request id, and the full **hash-chained audit trail**.
- **QC review** — jobs flagged by VLM auto-QC (or the human gate) show **Approve → deliver** /
  **Reject → rework** buttons.

API endpoints mirror the AOP connector allow-list (`/api/ingest`, `/api/jobs`, `/api/jobs/{id}`,
`/api/jobs/{id}/qc`, `/api/run`, `/api/media/...`). The sync backend drains in a background thread so
the UI stays responsive during multi-minute generations; switch to `VF_QUEUE_BACKEND=rq` for real
multi-worker fan-out.

## Phased build (matches the feasibility plan)
- **Phase 0** — spec lock (the 960×720/≤10 MB/10–12s vs 1080×1920/17 MB/13s contradiction; see
  [`backend/spec.py`](backend/spec.py)). Both encoded as presets + a `portrait` (9:16) option;
  default stays the written SOW until the client confirms. + fal.ai/credentials.
- **Phase 1** — thin vertical slice (the `run_one.py` CLI). ✅
- **Phase 2** — orchestration: pluggable queue (sync/RQ), state machine, retries, model fallback, SLA
  timers, idempotency, priority, cost-ceiling guardrail, batch CSV ingestion → 20K/month. ✅
- **Phase 3** — ops + QC web console (CSV upload, per-batch spec selector, batch dashboard, human QC
  gate, in-browser video review). ✅
- **Phase 4** — quality + cost: **VLM visual auto-QC** (defect flagging via fal vision → human gate),
  accurate fal-matched cost model + Standard-tier default, fal request-id traceability. ✅
  Still to come: cost dashboards, per-model quality tracking, Postgres/Railway + Google Drive delivery.

## Status
**Phases 1–4 runnable and verified against real fal.ai output.** Deterministic finishing, ingest, cost
model, and the Prompt-Builder run with no keys. The orchestrator drives the full state machine
(generate → finish → **VLM QC** → deliver) on the in-process queue with retries/fallback, idempotency,
priority, SLA tracking, and a hash-chained audit per job. The web console (`scripts/serve.py`) drives
all of it: CSV ingest, spec selection, live dashboard, in-browser review, and the QC gate. **Proven on
live Flipkart SKUs** — product images turned into spec-compliant delivered clips (landscape **and**
portrait), with VLM auto-QC correctly flagging a defective clip (artifact + face distortion) for review
and passing a clean one. Generation cost matches the fal dashboard (Kling Standard $0.56/10s).
RQ multi-worker fan-out is behind `VF_QUEUE_BACKEND=rq`; Postgres/Drive delivery remain next.
