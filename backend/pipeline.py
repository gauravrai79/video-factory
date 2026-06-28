"""Per-post orchestrator — drives one storyboard through the state machine.

`create_job` records a post (a planned storyboard for a character) as a PENDING job — priced and
deduped — at creation time. `execute_job` runs it: for each shot it generates a character-consistent
still, animates the shots marked `video` (the rest get free Ken Burns motion), assembles the reel,
runs identity QC, and delivers.

The state transitions and audit events are the same spine the rest of the factory governs:
  PENDING -> GENERATING (make all shot media) -> FINISHING (assemble) -> QC -> APPROVED -> DELIVERED
with the cost-ceiling guardrail and the human QC gate unchanged.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .agents.qc_flagger import run_vlm_qc, vlm_qc_enabled
from .agents.storyboard import Shot, Storyboard
from .capabilities import fal_image, fal_video
from .capabilities.fal_video import image_ref
from .characters import Character
from .finishing import ShotMedia, assemble
from .jobstore import Job, JobStore, State
from .spec import OutputSpec, get_spec


# --------------------------------------------------------------------------- routing helpers

PRIORITY_BY_TIER = {"premium": 100, "basic": 10}


def job_priority(tier: str) -> int:
    """Higher runs first. A premium character's posts jump the queue."""
    return PRIORITY_BY_TIER.get(tier, 10)


def idempotency_key(tenant_id: str, project: str, slug: str, spec: OutputSpec, execute: bool) -> str:
    """Stable per (tenant, project, post slug, spec, mode). Re-creating the same post won't double-bill."""
    raw = f"{tenant_id}|{project}|{slug}|{spec.name}|{'exec' if execute else 'dry'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cost_ceiling_usd() -> float:
    """Per-post estimated-cost ceiling. Over this, the post won't auto-generate (held for approval)."""
    return float(os.environ.get("VF_COST_CEILING_USD", "1.50"))


def _rebuild_storyboard(d: dict[str, Any]) -> Storyboard:
    shots = [Shot(**s) for s in d.get("shots", [])]
    return Storyboard(**{**d, "shots": shots})


# --------------------------------------------------------------------------- create (enqueue time)

def create_job(
    store: JobStore,
    character: Character,
    storyboard: Storyboard,
    *,
    tenant_id: str,
    project: str,
    spec: OutputSpec | None = None,
    execute: bool = True,
    music_path: str | None = None,
    out_dir: str = "out",
    dedupe: bool = True,
    sla_seconds: float | None = None,
    human_qc: bool = False,
    tier: str = "basic",
) -> tuple[Job, bool]:
    """Create (but do not run) a post job. Returns (job, created): created=False reused an existing
    non-failed job (idempotency). The storyboard is already priced by the planner."""
    spec = spec or get_spec(storyboard.format)
    key = idempotency_key(tenant_id, project, storyboard.slug, spec, execute)

    if dedupe:
        existing = store.find_by_idempotency_key(tenant_id, project, key)
        if existing and existing.state != State.FAILED:
            return existing, False

    if sla_seconds is None:
        from .sla import sla_seconds as _sla_for_tier
        sla_seconds = _sla_for_tier(tier)

    payload: dict[str, Any] = {
        "character": character.as_dict(),
        "storyboard": storyboard.as_dict(),
        "spec": spec.name,
        "execute": execute,
        "music_path": music_path,
        "out_dir": out_dir,
        "priority": job_priority(tier),
        "tier": tier,
        "human_qc": human_qc,
        "safety_tolerance": character.safety_tolerance,
        "est_cost_usd": storyboard.est_cost_usd,
        "sla_seconds": sla_seconds,
    }
    job = store.create(tenant_id=tenant_id, project=project, slug=storyboard.slug,
                       payload=payload, idempotency_key=key)
    store.append_event(job, "enqueued", {"priority": payload["priority"],
                                         "est_cost_usd": storyboard.est_cost_usd,
                                         "shots": len(storyboard.shots)})
    return job, True


# --------------------------------------------------------------------------- shot generation

def _gen_still_resilient(char: Character, shot: Shot, out_path: str, refs: list[str],
                         safety: int, store: JobStore, job: Job, *, attempts: int = 2):
    """Generate one shot's still with a retry. Returns the GenResult (success or last failure)."""
    last = None
    for attempt in range(1, attempts + 1):
        res = fal_image.generate_still(
            prompt=shot.still_prompt, output_path=out_path,
            reference_image_urls=refs or None, model=shot.image_model,
            safety_tolerance=safety, execute=True)
        last = res
        if res.success:
            if attempt > 1:
                store.append_event(job, "still_recovered", {"seq": shot.seq, "attempt": attempt})
            return res
        store.append_event(job, "still_retry", {"seq": shot.seq, "attempt": attempt, "error": res.error})
    return last


# --------------------------------------------------------------------------- execute (worker time)

def execute_job(store: JobStore, job: Job, *, deliver: bool = True) -> Job:
    """Run an existing PENDING post job through the machine. Self-contained: everything it needs is
    in `job.payload`, so an RQ worker in another process can run it from just a job_id."""
    p = job.payload
    char = Character(**p["character"])
    sb = _rebuild_storyboard(p["storyboard"])
    spec = get_spec(p.get("spec"))
    execute = bool(p.get("execute", True))
    music_path = p.get("music_path")
    out_dir = p.get("out_dir", "out")
    safety = int(p.get("safety_tolerance", char.safety_tolerance))
    slug = job.slug

    # Cost-ceiling guardrail. Over the ceiling, hold for human approval before any paid generation.
    est = float(p.get("est_cost_usd", sb.est_cost_usd))
    ceiling = cost_ceiling_usd()
    if execute and est > ceiling:
        store.transition(
            job, State.REWORK,
            detail={"held": "cost_ceiling_exceeded", "est_cost_usd": est, "ceiling_usd": ceiling},
            result_update={"held": "cost_ceiling_exceeded", "est_cost_usd": est,
                           "ceiling_usd": ceiling, "note": "needs approval before paid generation"})
        return job

    # Dry run: price only, no media. (The planning endpoint is the normal preview path.)
    if not execute:
        store.append_event(job, "dry_run_priced", {"est_cost_usd": est, "shots": len(sb.shots)})
        return job

    store.transition(job, State.GENERATING, {"shots": len(sb.shots)})

    stills_dir = Path(out_dir) / "stills" / slug
    clips_dir = Path(out_dir) / "clips" / slug
    medias: list[ShotMedia] = []
    refs = list(char.reference_images)         # character "DNA"; bootstrapped from shot 0 if empty
    bootstrapped = not refs
    total_cost = 0.0

    for shot in sb.shots:
        still_path = str(stills_dir / f"{shot.seq:03d}.png")
        sres = _gen_still_resilient(char, shot, still_path, refs, safety, store, job)
        if not sres or not sres.success:
            store.transition(job, State.FAILED,
                             detail={"error": sres.error if sres else "still gen failed", "seq": shot.seq},
                             result_update={"error": sres.error if sres else "still gen failed",
                                            "failed_stage": "generation"})
            return job
        total_cost += sres.cost_usd
        if not refs:                            # lock identity for the rest of the post
            refs = [still_path]

        zoom = "in" if shot.seq % 2 == 0 else "out"
        if shot.render_mode == "video":
            clip_path = str(clips_dir / f"{shot.seq:03d}.mp4")
            vres = fal_video.generate_video(
                prompt=shot.motion_prompt, image_url=image_ref(still_path),
                output_path=clip_path, model=shot.video_model,
                duration_s=shot.duration_s, aspect_ratio=spec.aspect_ratio, execute=True)
            if vres.success:
                total_cost += vres.cost_usd
                store.append_event(job, "shot_video", {"seq": shot.seq, "cost_usd": vres.cost_usd})
                medias.append(ShotMedia("video", clip_path, shot.duration_s))
                continue
            # Graceful: one failed video shot degrades to free Ken Burns, it doesn't fail the post.
            store.append_event(job, "shot_video_degraded", {"seq": shot.seq, "error": vres.error})
        medias.append(ShotMedia("kenburns", still_path, shot.duration_s, zoom=zoom))

    store.transition(job, State.FINISHING, result_update={
        "generation": {"cost_usd": round(total_cost, 4), "shots": len(medias),
                       "refs_bootstrapped": bootstrapped}})

    out_final = str(Path(out_dir) / "finished" / f"{slug}.mp4")
    fr = assemble(medias, out_final, spec=spec, music_path=music_path,
                  hook=(sb.caption_hook or None))
    if not fr.success:
        store.transition(job, State.FAILED, detail={"error": fr.error},
                         result_update={"error": fr.error, "failed_stage": "finishing"})
        return job

    # Identity QC (advisory) — compares the post against the character's reference.
    ref0 = refs[0] if refs else None
    vlm = run_vlm_qc(fr.output_path, spec, reference_image=ref0) if vlm_qc_enabled() else None
    if vlm is not None:
        store.append_event(job, "vlm_qc",
                           {"ran": vlm.ran, "passed": vlm.passed, "issues": len(vlm.issues),
                            "model": vlm.model, "request_id": vlm.request_id, "error": vlm.error})
    vlm_flagged = bool(vlm and vlm.ran and not vlm.passed)

    qc_update: dict[str, Any] = {"finished": fr.probe, "finished_path": fr.output_path,
                                 "gen_cost_usd": round(total_cost, 4)}
    if vlm is not None:
        qc_update["vlm_qc"] = vlm.as_dict()
    store.transition(job, State.QC, result_update=qc_update)

    if not fr.compliant:
        store.transition(job, State.REWORK, {"violations": fr.violations})
        return job
    if vlm_flagged or p.get("human_qc"):
        store.append_event(job, "awaiting_human_qc",
                           {"reason": "vlm_flagged" if vlm_flagged else "human_qc",
                            "issues": (vlm.issues if vlm else [])})
        return job  # stays at QC; a reviewer calls qc_decision()
    store.transition(job, State.APPROVED,
                     {"auto_checks": "passed", "vlm_qc": "passed" if (vlm and vlm.ran) else "skipped"})

    if deliver:
        _deliver(store, job, out_dir)
    return job


def qc_decision(store: JobStore, job: Job, *, approve: bool, reason: str = "",
                deliver: bool = True) -> Job:
    """Human QC gate: a reviewer clears or rejects a post sitting at QC."""
    if job.state != State.QC:
        raise ValueError(f"post {job.slug} is not awaiting QC (state={job.state.value})")
    if approve:
        store.transition(job, State.APPROVED, {"qc": "human_approved"})
        if deliver:
            _deliver(store, job, job.payload.get("out_dir", "out"))
    else:
        store.transition(job, State.REWORK, {"qc": "human_rejected", "reason": reason or "rejected"})
    return store.get(job.job_id) or job


def _deliver(store: JobStore, job: Job, out_dir: str) -> None:
    """Local delivery: copy the approved post to out/delivered/ and mark DELIVERED. (Auto-publishing
    to social platforms is a later phase; v1 stops at a delivered file.)"""
    import shutil
    src = job.result.get("finished_path")
    if not src or not Path(src).is_file():
        return
    dest_dir = Path(out_dir) / "delivered"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{job.slug}.mp4"
    shutil.copy2(src, dest)
    store.transition(job, State.DELIVERED, result_update={"delivered_path": str(dest)},
                     detail={"target": "local", "note": "auto-publishing wired in a later phase"})


def summarize(job: Job, store: JobStore) -> dict[str, Any]:
    fresh = store.get(job.job_id) or job
    return {
        "job_id": fresh.job_id,
        "slug": fresh.slug,
        "state": fresh.state.value,
        "result": fresh.result,
        "audit_events": len(store.audit_trail(fresh.job_id)),
        "audit_chain_valid": store.verify_chain(fresh.job_id),
    }
