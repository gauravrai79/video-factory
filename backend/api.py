"""Video Factory ops + QC console — FastAPI app.

This is the `backend/` API the README/AOP describe: the connector calls these endpoints, and the
`frontend/` ops console (served at `/`) drives them. Endpoints mirror the AOP connector allow-list:
ingest_batch, list_jobs, get_job, generate (drain), qc_decision, deliver.

Run it:  python scripts/serve.py        (or: uvicorn backend.api:app --reload --port 8310)

The sync backend drains in a background thread so the UI stays responsive while clips are generated
(real fal calls take minutes). Each request opens its own JobStore (its own sqlite connection), so
reads stay fresh while the worker thread writes (WAL + busy_timeout, set in JobStore).
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import runner, sla as sla_mod
from .ingest import parse_row
from .jobstore import JobStore, State
from .pipeline import create_job, cost_ceiling_usd, qc_decision
from .spec import PRESETS, get_spec

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OUT_DIR = ROOT / "out"
MEDIA_KINDS = {"finished", "delivered", "clips"}

app = FastAPI(title="Video Factory", version="0.3.0")


def _tenant() -> str:
    return os.environ.get("VF_TENANT_ID", "flipkart")


def _project() -> str:
    return os.environ.get("VF_PROJECT", "video-factory")


def _has_media(fsn: str, kind: str) -> bool:
    return (OUT_DIR / kind / f"{fsn}.mp4").is_file()


def _job_view(store: JobStore, job, *, full: bool = False) -> dict[str, Any]:
    p = job.payload or {}
    sku = p.get("sku", {}) or {}
    s = sla_mod.status_for(store, job)
    view: dict[str, Any] = {
        "job_id": job.job_id,
        "fsn": job.fsn,
        "title": sku.get("title", ""),
        "category": sku.get("category", ""),
        "tier": sku.get("tier", "basic"),
        "state": job.state.value,
        "model": (p.get("route") or {}).get("model"),
        "force_model": p.get("force_model"),
        "execute": bool(p.get("execute")),
        "human_qc": bool(p.get("human_qc")),
        "priority": p.get("priority"),
        "est_cost_usd": p.get("est_cost_usd"),
        "cost_usd": (job.result.get("generation") or {}).get("cost_usd"),
        "request_id": (job.result.get("generation") or {}).get("request_id"),
        "fell_back": (job.result.get("generation") or {}).get("fell_back"),
        "finished": job.result.get("finished"),
        "violations": job.result.get("violations"),
        "vlm_qc": job.result.get("vlm_qc"),
        "held": job.result.get("held"),
        "error": job.result.get("error"),
        "failed_stage": job.result.get("failed_stage"),
        "has_image": bool(sku.get("image_url") or sku.get("image_urls")),
        "sla": {"elapsed_s": s.elapsed_s, "budget_s": s.budget_s,
                "breached": s.breached, "remaining_s": s.remaining_s},
        "media": {k: _has_media(job.fsn, k) for k in MEDIA_KINDS},
        "updated_at": job.updated_at,
        "created_at": job.created_at,
    }
    if full:
        view["payload"] = p
        view["result"] = job.result
        view["audit"] = store.audit_trail(job.job_id)
        view["audit_chain_valid"] = store.verify_chain(job.job_id)
    return view


# --------------------------------------------------------------------------- API

@app.get("/api/summary")
def summary() -> dict[str, Any]:
    store = JobStore()
    jobs = store.list(tenant_id=_tenant())
    by_state: dict[str, int] = {}
    spent = 0.0
    for j in jobs:
        by_state[j.state.value] = by_state.get(j.state.value, 0) + 1
        spent += float((j.result.get("generation") or {}).get("cost_usd") or 0) if j.payload.get("execute") else 0
    breaches = [s for s in sla_mod.evaluate(store, tenant_id=_tenant()) if s.breached]
    return {
        "tenant": _tenant(),
        "project": _project(),
        "queue_backend": os.environ.get("VF_QUEUE_BACKEND", "sync"),
        "spec": get_spec().name,
        "specs": [{"name": p.name, "label": f"{p.name} · {p.width}×{p.height} · "
                   f"{int(p.min_duration_s)}-{int(p.max_duration_s)}s"} for p in PRESETS.values()],
        "fal_key_present": bool(os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")),
        "cost_ceiling_usd": cost_ceiling_usd(),
        "total_jobs": len(jobs),
        "by_state": by_state,
        "spent_usd": round(spent, 4),
        "sla_breaches": len(breaches),
        "drain": runner.progress(),
    }


@app.get("/api/jobs")
def list_jobs(state: str | None = None) -> list[dict[str, Any]]:
    store = JobStore()
    st = State(state) if state else None
    jobs = store.list(tenant_id=_tenant(), state=st)
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [_job_view(store, j) for j in jobs]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    store = JobStore()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return _job_view(store, job, full=True)


@app.post("/api/ingest")
async def ingest(
    file: UploadFile | None = File(default=None),
    execute: bool = Form(default=False),
    model: str | None = Form(default=None),
    human_qc: bool = Form(default=False),
    stand_in: str | None = Form(default=None),
    spec: str | None = Form(default=None),
    auto_run: bool = Form(default=True),
) -> dict[str, Any]:
    """Upload a CSV manifest -> create + (optionally) start running jobs. Mirrors AOP ingest_batch."""
    if file is None:
        raise HTTPException(400, "CSV file required")
    try:
        out_spec = get_spec(spec or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    raw = (await file.read()).decode("utf-8-sig")
    rows = [parse_row(r) for r in csv.DictReader(io.StringIO(raw))]
    rows = [r for r in rows if r.fsn]
    if not rows:
        raise HTTPException(400, "no valid SKU rows (need an 'fsn' column)")

    # Pre-flight: generation needs a DIRECT image URL, not a product-page URL. Warn (don't silently
    # fail) so the operator sees the problem before a paid run instead of after N failed jobs.
    no_image = [r.fsn for r in rows if not (r.image_url or r.image_urls)]
    page_urls = [r.fsn for r in rows if r.fsn.startswith("http")]
    warnings: list[str] = []
    if no_image:
        warnings.append(f"{len(no_image)} row(s) have no image_url — generation will fail for them. "
                        "Provide a direct product image URL (e.g. a .jpg), not a product-page link.")
    if page_urls:
        warnings.append(f"{len(page_urls)} row(s) use a URL as the FSN — looks like a product-page "
                        "link in the 'fsn' column. FSN should be the SKU id; the image goes in 'image_url'.")

    store = JobStore()
    created, reused = [], []
    for row in rows:
        job, is_new = create_job(
            store, row, tenant_id=_tenant(), project=_project(), spec=out_spec,
            execute=execute, force_model=(model or None), human_qc=human_qc,
            stand_in_clip=(stand_in or None), dedupe=True,
        )
        (created if is_new else reused).append(job.fsn)

    # Don't auto-run a paid batch that will obviously fail; surface the warning and let the operator fix it.
    block_run = execute and bool(no_image)
    started = (runner.start_background_drain() if (auto_run and not block_run) else False)
    return {"created": created, "reused": reused, "count": len(rows),
            "warnings": warnings, "blocked_run": block_run,
            "drain_started": started, "drain": runner.progress()}


@app.post("/api/run")
def run() -> dict[str, Any]:
    """Drain PENDING jobs in the background (generate -> finish -> qc -> deliver)."""
    started = runner.start_background_drain()
    return {"drain_started": started, "drain": runner.progress()}


@app.post("/api/jobs/{job_id}/qc")
def qc(job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Human QC decision: {"approve": true} clears -> delivered; {"approve": false, "reason": ...} -> rework."""
    store = JobStore()
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        job = qc_decision(store, job, approve=bool(body.get("approve")),
                          reason=str(body.get("reason", "")))
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _job_view(store, job, full=True)


@app.get("/api/media/{kind}/{fsn}")
def media(kind: str, fsn: str):
    if kind not in MEDIA_KINDS:
        raise HTTPException(404, "unknown media kind")
    path = OUT_DIR / kind / f"{fsn}.mp4"
    if not path.is_file():
        raise HTTPException(404, "media not found")
    return FileResponse(str(path), media_type="video/mp4")  # Starlette handles Range -> seekable


@app.get("/api/sla")
def sla() -> list[dict[str, Any]]:
    store = JobStore()
    return [{"fsn": s.fsn, "tier": s.tier, "state": s.state, "elapsed_s": s.elapsed_s,
             "budget_s": s.budget_s, "remaining_s": s.remaining_s, "breached": s.breached}
            for s in sla_mod.evaluate(store, tenant_id=_tenant())]


# --------------------------------------------------------------------------- frontend (served last)

if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
else:  # pragma: no cover
    @app.get("/")
    def _no_frontend() -> JSONResponse:
        return JSONResponse({"error": "frontend/ not found"}, status_code=500)
