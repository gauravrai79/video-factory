# Video Factory — Handover Note

**Repo:** https://github.com/raigauravbgo/video-factory
**What it is:** a high-throughput **image-to-video** factory for ecommerce catalogs (Flipkart
Lifestyle/Apparel). A CSV of product SKUs in → spec-compliant, watermarked, QC-gated short videos out,
engineered for **20,000+/month**. The generative step is one API call behind a stable interface; the
engineering is the pipeline around it — ingestion, a queued state machine with SLA timers, deterministic
finishing, a QC gate, and delivery.

**Status:** Phases 1–4 are built, runnable, and **verified against real fal.ai output** (live Flipkart
SKUs → delivered clips, landscape and portrait). See `README.md` for the full architecture.

---

## Built outside Spine — but 100% portable into it

This was built **standalone**, with **zero Spine code dependencies** — it runs completely on its own
today (CLI + local web console, SQLite, in-process queue, no external services beyond fal.ai). That was
deliberate: it let us move fast and prove the whole pipeline end-to-end without waiting on Spine.

But every seam was designed to **drop into the Spine control/governance plane in production with no code
change** — it matches the `synced` project model in Spine's `ACCESS_AND_ARCHITECTURE` §15. The coupling
is through the **four documented touchpoints only** (no shared code):

| Spine touchpoint | In this repo | Status |
|---|---|---|
| `spine.skills.json` (registry + connector block) | `spine/spine.skills.json` | present |
| AOP (governed run procedure) | `spine/aop/video_factory.yaml` | present |
| Connector → project API | `backend/api.py` (FastAPI; Spine calls these endpoints) | present |
| `launchUrl` → product UI | `frontend/` ops + QC console | present |

**The same seams already run locally**, just un-governed — so the swap is config, not a rewrite:

| Runs locally today | Becomes, under Spine, with no code change |
|---|---|
| Human QC gate in the web console (approve/reject → rework) | Spine **Approval gate** (`pending → approve → execute`) |
| Auto-QC: clean clips auto-approve, flagged → human | Auto-checks auto-approve; flagged → Spine **Approvals queue** |
| Per-job hash-chained audit log (SQLite) | Spine **hash-chained audit bus** (mirrored locally already) |
| `(tenant_id, project)` row scoping in SQLite | **Postgres + RLS** under Spine |
| Direct fal.ai calls | Spine **connector allow-list** |
| `FAL_KEY` / no auth | Spine auth (`SPINE_AUTH_ENABLED` flip) |

The API endpoints (`/api/ingest`, `/api/jobs`, `/api/jobs/{id}/qc`, …) already mirror the AOP connector
allow-list (`spine/aop/video_factory.yaml`), and the local audit chain mirrors Spine's audit bus. Nothing
needs to be undone to plug in — you point Spine at the connector and flip the governance on.

---

## Run it locally (no Spine, no infra)

```bash
pip install -r requirements.txt
cp .env.example .env          # add FAL_KEY (real key lives in .env — gitignored, never committed)

# Web console — ingest a CSV, watch the dashboard, review/approve clips:
python scripts/serve.py       # → http://localhost:8310

# Or headless CLI:
python scripts/run_one.py   --csv samples/flipkart_test_run.csv --row 0           # dry run (free)
python scripts/run_one.py   --csv samples/flipkart_test_run.csv --row 0 --execute # real (paid)
python scripts/run_batch.py --csv samples/skus.csv --sla                          # batch + SLA view
```

Dry runs cost nothing. Real generation needs `FAL_KEY` and `--execute` (or the **Execute** toggle in the
UI, which confirms before spending).

---

## What's done (Phases 1–4)

- **P1 — vertical slice:** CSV → Prompt-Builder → fal.ai → deterministic FFmpeg finish → spec-compliant
  MP4 + hash-chained audit.
- **P2 — orchestration:** pluggable queue (`sync` in-process default / `rq` Redis for prod, via
  `VF_QUEUE_BACKEND`), job state machine, retries + **model fallback** (Kling↔Seedance), **SLA timers**,
  **idempotency** (re-ingest never re-bills), tier **priority**, **per-job cost ceiling**, batch ingest.
- **P3 — ops + QC web console:** CSV ingest, per-batch **spec selector**, live dashboard, in-browser
  seekable video review, **human QC gate** (approve → deliver / reject → rework).
- **P4 — quality + cost:** **VLM visual auto-QC** (defect flagging via fal vision → human gate),
  **fal-accurate cost model** + Standard-tier default, fal **request-id** traceability, portrait spec.

## Key design decisions the team should know

- **Aggregator, not direct vendor.** All generation routes through **fal.ai** (Replicate as secondary).
  Swap models by changing a config string — protects against vendor shutdowns, enables A/B per category.
- **Kling 2.1 Standard is the default** (`VF_KLING_TIER`). $0.56/10s vs $0.98 for Pro — ~43% cheaper,
  ~$8K/mo less at 20K. Hero SKUs / difficult prints auto-escalate to **Seedance** (~$3.03/10s).
  Generation cost dominates the P&L, so the tier default is the biggest cost lever.
- **Cost model matches the fal dashboard exactly** (base + per-second formula, priced on billed
  duration). Every real call logs the fal `request_id` for line-by-line reconciliation.
- **Finishing is deterministic & 100% automatable** (FFmpeg): exact dims, 2-pass size band, watermark,
  callout supers, music. Generation runs audio-off; music added here.
- **VLM auto-QC is advisory and fail-safe.** If the vision call fails (no key, endpoint down), it
  degrades to deterministic checks only — a flaky VLM never blocks the line.
- **Governance contract:** the agent announces provider/model/cost before any paid call, never swaps
  providers/models silently, and honors the per-job cost ceiling.

## What's NOT built yet (next steps)

1. **Client spec decision (Phase 0, still open):** the SOW says 960×720 landscape; product photos are
   portrait. Both are encoded as presets plus a `portrait` (9:16) option that fills the frame — **the
   client needs to pick the delivery spec.** See `backend/spec.py`.
2. **Prompt-Builder is apparel-tuned.** Non-apparel SKUs (bottles, electronics) still generate but get
   "garment/fabric" prompt language — broaden to category-aware prompts before going general-merchandise.
3. **Production wiring:** Postgres/Railway (schema is already Postgres-shaped), RQ multi-worker fan-out
   (`VF_QUEUE_BACKEND=rq` + Redis), and Google Drive delivery (currently a local-copy stub).
4. **Rework agent** (auto-revise a rejected prompt) is referenced in the architecture but not built.
5. **VLM endpoint:** uses fal `any-llm/vision`, which fal marks deprecated — works today, degrades
   gracefully, but pick a supported vision endpoint before relying on it at scale.

## Gotchas

- **Secrets:** real `FAL_KEY` goes in `.env` (gitignored). Never put it in `.env.example` (tracked).
- **fal Kling constraints:** `duration` must be `5` or `10`s; `aspect_ratio` must be `16:9 / 9:16 / 1:1`.
  Both are normalized in `backend/capabilities/fal_video.py` (finishing clamps/pads to the exact spec).
- **Windows:** the `sync` queue runs in-process (no Redis/fork needed). RQ workers are Linux/macOS.
- **ffmpeg** auto-resolves via PATH or the winget install dir; override with `FFMPEG_BIN`.

---

*Questions: start with `README.md` (architecture + run instructions); each backend module has a
docstring explaining its role and the local-vs-Spine split.*
