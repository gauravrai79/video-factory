"""Worker task — the unit of work a queue runs.

`process_job(job_id)` is the only thing the queue ever calls. It takes just a job_id (everything else
is in the DB), so it runs identically inline (sync queue) or in a separate RQ worker process. This is
the function RQ enqueues; keeping it module-level and side-effect-free at import time is what lets RQ
pickle a reference to it.
"""

from __future__ import annotations

from typing import Any

from .jobstore import JobStore, State
from .pipeline import execute_job, summarize


def process_job(job_id: str, *, deliver: bool = True) -> dict[str, Any]:
    """Run one already-created job to a terminal (or held) state. Safe to call from any process."""
    store = JobStore()
    job = store.get(job_id)
    if job is None:
        return {"job_id": job_id, "error": "job not found"}
    if job.state != State.PENDING:
        # Already picked up / completed — idempotent no-op for at-least-once queues.
        return summarize(job, store)
    execute_job(store, job, deliver=deliver)
    return summarize(job, store)
