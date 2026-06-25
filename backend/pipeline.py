"""Per-job orchestrator — drives one SKU through the state machine.

Phase 1 ran the whole job inline (CLI). Phase 2 splits creation from execution so a queued worker
can pick up an already-created PENDING job and run it: `create_job` records the job (priced, routed,
deduped) at enqueue time; `execute_job` runs it through generate -> finish -> qc -> deliver with
retries, model fallback, and the cost-ceiling guardrail. The legacy `run_job` (create + execute) is
preserved for the Phase 1 CLI.

The state transitions and audit events here are exactly what Spine's connector + approval gate govern
in production (see spine/aop/video_factory.yaml).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from .agents.prompt_builder import build_prompt, fallback_plan, resolve_route, PromptPlan
from .capabilities import fal_video
from .capabilities.cost import estimate_generation
from .finishing import Callout, finish
from .ingest import SkuRow
from .jobstore import Job, JobStore, State
from .spec import OutputSpec, get_spec


# --------------------------------------------------------------------------- routing helpers

PRIORITY_BY_TIER = {"premium": 100, "basic": 10}


def job_priority(row: SkuRow) -> int:
    """Higher runs first. Premium tier and hero SKUs jump the queue (they gate the catalog launch)."""
    p = PRIORITY_BY_TIER.get(row.tier, 10)
    if row.hero:
        p += 50
    return p


def idempotency_key(tenant_id: str, project: str, row: SkuRow, spec: OutputSpec, execute: bool) -> str:
    """Stable per (tenant, project, fsn, spec, mode). Re-ingesting the same CSV won't double-bill."""
    raw = f"{tenant_id}|{project}|{row.fsn}|{spec.name}|{'exec' if execute else 'dry'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cost_ceiling_usd() -> float:
    """Per-job estimated-cost ceiling (AOP guardrail). Over this, the job won't auto-generate."""
    return float(os.environ.get("VF_COST_CEILING_USD", "1.50"))


# --------------------------------------------------------------------------- create (enqueue time)

def create_job(
    store: JobStore,
    row: SkuRow,
    *,
    tenant_id: str,
    project: str,
    spec: OutputSpec | None = None,
    execute: bool = False,
    music_path: str | None = None,
    out_dir: str = "out",
    stand_in_clip: str | None = None,
    dedupe: bool = True,
    sla_seconds: float | None = None,
    force_model: str | None = None,
    human_qc: bool = False,
) -> tuple[Job, bool]:
    """Create (but do not run) a job. Returns (job, created): created=False means an existing
    non-failed job was reused (idempotency). Pricing + routing are computed cheaply here (no LLM,
    no paid call) so the batch report and priority are available before the worker runs."""
    spec = spec or get_spec()
    key = idempotency_key(tenant_id, project, row, spec, execute)

    if dedupe:
        existing = store.find_by_idempotency_key(tenant_id, project, key)
        if existing and existing.state != State.FAILED:
            return existing, False

    # Cheap route + price (deterministic — no LLM, no network).
    model, variant, reason = resolve_route(row, force_model)
    est = estimate_generation(model, variant, int(round(spec.max_duration_s)))
    if sla_seconds is None:
        from .sla import sla_seconds as _sla_for_tier
        sla_seconds = _sla_for_tier(row.tier)

    payload: dict[str, Any] = {
        "sku": row.__dict__,
        "spec": spec.name,
        "execute": execute,
        "music_path": music_path,
        "out_dir": out_dir,
        "stand_in_clip": stand_in_clip,
        "priority": job_priority(row),
        "route": {"model": model, "variant": variant, "reason": reason},
        "force_model": force_model,
        "human_qc": human_qc,
        "est_cost_usd": est,
        "sla_seconds": sla_seconds,
    }
    job = store.create(tenant_id=tenant_id, project=project, fsn=row.fsn,
                       payload=payload, idempotency_key=key)
    store.append_event(job, "enqueued", {"priority": payload["priority"],
                                         "est_cost_usd": est, "model": model})
    return job, True


# --------------------------------------------------------------------------- generation w/ fallback

def _generate_once(plan: PromptPlan, row: SkuRow, out_clip: str, execute: bool):
    if plan.model == "seedance":
        return fal_video.generate_seedance(
            prompt=plan.prompt, output_path=out_clip, image_url=row.image_url or None,
            reference_image_urls=plan.reference_image_urls or None,
            model_variant=plan.model_variant, duration=plan.duration,
            aspect_ratio=plan.aspect_ratio, execute=execute)
    return fal_video.generate_kling(
        prompt=plan.prompt, image_url=row.image_url, output_path=out_clip,
        model_variant=plan.model_variant, duration=plan.duration,
        aspect_ratio=plan.aspect_ratio, execute=execute)


def _generate_resilient(store: JobStore, job: Job, plan: PromptPlan, row: SkuRow,
                        spec: OutputSpec, out_clip: str, execute: bool,
                        *, attempts_per_model: int = 2, allow_fallback: bool = True):
    """Try the primary model with retries, then fall back to the alternate model (Kling<->Seedance),
    per AOP `generate.on_failure: fallback_model`. Returns the first successful GenResult, or the last
    failure. Each attempt is an audit event so the reshoot/fallback rate is measurable.

    allow_fallback=False (used when a model is force-pinned to cap cost) keeps retries on the pinned
    model only — so a cheap Kling run can't silently fall back to a pricier Seedance call."""
    plans = [plan]
    if allow_fallback:
        fb = fallback_plan(plan, row, spec)
        if fb is not None:
            plans.append(fb)

    last = None
    for attempt_plan in plans:
        for attempt in range(1, attempts_per_model + 1):
            gen = _generate_once(attempt_plan, row, out_clip, execute)
            last = gen
            if gen.success:
                if attempt_plan is not plan or attempt > 1:
                    store.append_event(job, "generation_recovered",
                                       {"model": attempt_plan.model, "attempt": attempt,
                                        "fell_back": attempt_plan is not plan})
                return gen, attempt_plan
            store.append_event(job, "generation_retry",
                               {"model": attempt_plan.model, "attempt": attempt,
                                "error": gen.error})
    return last, plans[-1]


# --------------------------------------------------------------------------- execute (worker time)

def execute_job(
    store: JobStore,
    job: Job,
    *,
    deliver: bool = True,
) -> Job:
    """Run an existing PENDING job through the machine. Self-contained: everything it needs is in
    `job.payload` (so an RQ worker in another process can run it from just a job_id)."""
    p = job.payload
    row = SkuRow(**p["sku"])
    spec = get_spec(p.get("spec"))
    execute = bool(p.get("execute", False))
    music_path = p.get("music_path")
    out_dir = p.get("out_dir", "out")
    stand_in_clip = p.get("stand_in_clip")

    # 1) Build prompt + route (read step). Full build (may LLM-refine if VF_USE_LLM=1).
    plan = build_prompt(row, spec, force_model=p.get("force_model"))
    store.append_event(job, "prompt_built",
                       {"model": plan.model, "variant": plan.model_variant,
                        "route": plan.route_reason, "llm_refined": plan.llm_refined})

    # Cost-ceiling guardrail (AOP). Over the ceiling, do not auto-generate — hold for approval.
    est = float(p.get("est_cost_usd", 0.0))
    ceiling = cost_ceiling_usd()
    if execute and est > ceiling:
        store.transition(
            job, State.REWORK,
            detail={"held": "cost_ceiling_exceeded", "est_cost_usd": est, "ceiling_usd": ceiling},
            result_update={"held": "cost_ceiling_exceeded", "est_cost_usd": est,
                           "ceiling_usd": ceiling,
                           "note": "needs human approval before paid generation"})
        return job

    out_clip = str(Path(out_dir) / "clips" / f"{row.fsn}.mp4")
    out_final = str(Path(out_dir) / "finished" / f"{row.fsn}.mp4")

    # 2) Generate (write step — governed by the approval gate in Spine; auto-approved under ceiling).
    store.transition(job, State.GENERATING, {"model": plan.model})
    gen, used_plan = _generate_resilient(store, job, plan, row, spec, out_clip, execute,
                                         allow_fallback=p.get("force_model") is None)
    if not gen.success:
        store.transition(job, State.FAILED, {"error": gen.error})
        return job

    clip_for_finish = gen.output_path if execute else stand_in_clip
    store.transition(job, State.FINISHING, result_update={
        "generation": {"model": gen.model, "provider": gen.provider,
                       "cost_usd": gen.cost_usd, "dry_run": not execute,
                       "fell_back": used_plan.model != plan.model}})

    if not clip_for_finish or not Path(clip_for_finish).is_file():
        # Dry run with no stand-in: stop at a priced plan (not a failure — nothing to finish).
        store.append_event(job, "dry_run_priced", {"est_cost_usd": gen.cost_usd})
        return job

    # 3) Finish to spec (read step — deterministic).
    callouts = [Callout(text=c, start_s=1.0 + i * 3.0, end_s=3.5 + i * 3.0)
                for i, c in enumerate(row.callouts[:2])]
    fr = finish(clip_for_finish, out_final, spec=spec, callouts=callouts, music_path=music_path)
    if not fr.success:
        store.transition(job, State.FAILED, {"error": fr.error})
        return job
    store.transition(job, State.QC, result_update={"finished": fr.probe,
                                                    "finished_path": fr.output_path})

    # 4) QC auto-check (write step). Flagged -> human review. Clean -> auto-approve, UNLESS the job
    #    opted into the human QC gate (Posture A), in which case it waits at QC for a reviewer.
    if not fr.compliant:
        store.transition(job, State.REWORK, {"violations": fr.violations})
        return job
    if p.get("human_qc"):
        store.append_event(job, "awaiting_human_qc", {"auto_checks": "passed"})
        return job  # stays at QC; a reviewer calls qc_decision()
    store.transition(job, State.APPROVED, {"auto_checks": "passed"})

    # 5) Deliver (write step — auto-proceeds once QC approved; the gate is QC).
    if deliver:
        _deliver(store, job, out_dir)
    return job


def qc_decision(store: JobStore, job: Job, *, approve: bool, reason: str = "",
                deliver: bool = True) -> Job:
    """Human QC gate: a reviewer clears or rejects a job sitting at QC. Approve -> APPROVED ->
    delivered; reject -> REWORK with a reason. Mirrors Spine's approval gate."""
    if job.state != State.QC:
        raise ValueError(f"job {job.fsn} is not awaiting QC (state={job.state.value})")
    if approve:
        store.transition(job, State.APPROVED, {"qc": "human_approved"})
        if deliver:
            _deliver(store, job, job.payload.get("out_dir", "out"))
    else:
        store.transition(job, State.REWORK, {"qc": "human_rejected", "reason": reason or "rejected"})
    return store.get(job.job_id) or job


def _deliver(store: JobStore, job: Job, out_dir: str) -> None:
    """Local delivery stub: copy the approved deliverable to out/delivered/ and mark DELIVERED.
    Google Drive is the production target (GOOGLE_DRIVE_FOLDER_ID); wired in Phase 3/4."""
    src = job.result.get("finished_path")
    if not src or not Path(src).is_file():
        return
    dest_dir = Path(out_dir) / "delivered"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(src).name
    shutil.copy2(src, dest)
    store.transition(job, State.DELIVERED, result_update={"delivered_path": str(dest)},
                     detail={"target": "local_stub", "note": "Drive delivery wired in Phase 3/4"})


# --------------------------------------------------------------------------- legacy (Phase 1 CLI)

def run_job(
    store: JobStore,
    row: SkuRow,
    *,
    tenant_id: str,
    project: str,
    spec: OutputSpec | None = None,
    execute: bool = False,
    music_path: str | None = None,
    out_dir: str = "out",
    stand_in_clip: str | None = None,
    deliver: bool = True,
    force_model: str | None = None,
) -> Job:
    """Phase 1 entry: create + execute one SKU inline. Kept for scripts/run_one.py."""
    job, _ = create_job(store, row, tenant_id=tenant_id, project=project, spec=spec,
                        execute=execute, music_path=music_path, out_dir=out_dir,
                        stand_in_clip=stand_in_clip, dedupe=False, force_model=force_model)
    return execute_job(store, job, deliver=deliver)


def summarize(job: Job, store: JobStore) -> dict[str, Any]:
    fresh = store.get(job.job_id) or job
    return {
        "job_id": fresh.job_id,
        "fsn": fresh.fsn,
        "state": fresh.state.value,
        "result": fresh.result,
        "audit_events": len(store.audit_trail(fresh.job_id)),
        "audit_chain_valid": store.verify_chain(fresh.job_id),
    }
