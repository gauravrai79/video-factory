"""SLA timers + breach evaluation.

Every post carries a deadline from the moment it's created, so a busy content calendar can't quietly
fall behind. Deadlines are tier-based (a premium character gets a tighter SLA). We don't run a
background timer thread; breaches are computed on demand from the audit log (every event is already
timestamped + hash-chained), so the SLA view is derivable, tamper-evident, and stateless.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from .jobstore import Job, JobStore, State

TERMINAL = {State.DELIVERED, State.FAILED}
# A job still moving through these is "in flight" for SLA purposes.
ACTIVE = {State.PENDING, State.GENERATING, State.FINISHING, State.QC, State.APPROVED, State.REWORK}


def sla_seconds(tier: str) -> float:
    """Enqueue-to-delivered budget. Override via VF_SLA_PREMIUM_S / VF_SLA_BASIC_S."""
    if tier == "premium":
        return float(os.environ.get("VF_SLA_PREMIUM_S", str(2 * 3600)))   # 2h
    return float(os.environ.get("VF_SLA_BASIC_S", str(6 * 3600)))         # 6h


@dataclass
class SLAStatus:
    job_id: str
    slug: str
    tier: str
    state: str
    elapsed_s: float
    budget_s: float
    breached: bool
    terminal: bool

    @property
    def remaining_s(self) -> float:
        return round(self.budget_s - self.elapsed_s, 1)


def _completion_ts(store: JobStore, job: Job) -> float | None:
    """Timestamp of the last audit event for terminal jobs (when the clock stopped)."""
    trail = store.audit_trail(job.job_id)
    return trail[-1]["ts"] if trail else None


def status_for(store: JobStore, job: Job, *, now: float | None = None) -> SLAStatus:
    now = now if now is not None else time.time()
    tier = job.payload.get("tier", "basic")
    budget = float(job.payload.get("sla_seconds") or sla_seconds(tier))
    terminal = job.state in TERMINAL
    end = _completion_ts(store, job) if terminal else now
    elapsed = round((end or now) - job.created_at, 1)
    # A dry run isn't a real SLA commitment (no paid generation) — never count it as breached.
    is_dry = not bool(job.payload.get("execute", False))
    breached = (not is_dry) and (elapsed > budget) and not (terminal and job.state == State.DELIVERED)
    return SLAStatus(job_id=job.job_id, slug=job.slug, tier=tier, state=job.state.value,
                     elapsed_s=elapsed, budget_s=budget, breached=breached, terminal=terminal)


def evaluate(store: JobStore, *, tenant_id: str | None = None,
             now: float | None = None) -> list[SLAStatus]:
    """SLA status for every job (optionally tenant-scoped), worst breaches first."""
    jobs = store.list(tenant_id=tenant_id)
    rows = [status_for(store, j, now=now) for j in jobs]
    rows.sort(key=lambda s: (not s.breached, -(s.elapsed_s - s.budget_s)))
    return rows


def breaches(store: JobStore, *, tenant_id: str | None = None,
             now: float | None = None) -> list[SLAStatus]:
    return [s for s in evaluate(store, tenant_id=tenant_id, now=now) if s.breached]
