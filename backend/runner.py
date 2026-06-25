"""Drain PENDING jobs from the DB — the API's worker side for the sync backend.

The CLI's in-process SyncQueue lives for one command; a long-running API server can't hold that
queue across requests, so here the durable queue IS the jobs table (state=PENDING). `drain_*` picks
PENDING jobs in priority order and runs each via the same `worker.process_job` the RQ path uses.

`start_background_drain` runs that in a daemon thread so the HTTP request returns immediately and the
UI can poll job state as clips move through the machine. Each job opens its own JobStore (its own
sqlite connection), so cross-thread use is safe.
"""

from __future__ import annotations

import threading
from typing import Any

from .jobstore import JobStore, State
from .worker import process_job

_lock = threading.Lock()
_progress: dict[str, Any] = {"running": False, "total": 0, "done": 0, "current": None}


def pending_priority_sorted(store: JobStore) -> list:
    jobs = [j for j in store.list() if j.state == State.PENDING]
    jobs.sort(key=lambda j: -int(j.payload.get("priority", 0)))
    return jobs


def progress() -> dict[str, Any]:
    return dict(_progress)


def drain_pending(*, deliver: bool = True) -> list[dict[str, Any]]:
    """Process all PENDING jobs once, priority order. Blocking. Returns their summaries."""
    store = JobStore()
    out = []
    for job in pending_priority_sorted(store):
        out.append(process_job(job.job_id, deliver=deliver))
    return out


def start_background_drain(*, deliver: bool = True) -> bool:
    """Kick off draining in a daemon thread. Returns False if a drain is already running."""
    with _lock:
        if _progress["running"]:
            return False
        store = JobStore()
        job_ids = [j.job_id for j in pending_priority_sorted(store)]
        _progress.update(running=True, total=len(job_ids), done=0, current=None)

    def _run() -> None:
        try:
            for jid in job_ids:
                _progress["current"] = jid
                process_job(jid, deliver=deliver)
                _progress["done"] += 1
        finally:
            _progress.update(running=False, current=None)

    threading.Thread(target=_run, daemon=True).start()
    return True
