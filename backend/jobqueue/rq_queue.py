"""Redis/RQ backend — production fan-out across worker processes/machines.

Enqueue pushes `backend.worker.process_job(job_id)` onto an RQ queue keyed by REDIS_URL. Draining is
NOT done here — separate `rq worker` processes (started via scripts/worker.py) pull and run jobs in
parallel; that's the whole point of moving off the sync backend. RQ priority is expressed with two
queues (`vf-high`, `vf-default`) since RQ has no per-job priority; workers list high first.

Requires `redis` + `rq` (see requirements.txt) and a reachable Redis. Note RQ workers fork, so the
worker side is Linux/macOS; enqueueing from Windows is fine.
"""

from __future__ import annotations

import os
from typing import Any

from .base import JobQueue

HIGH_QUEUE = "vf-high"
DEFAULT_QUEUE = "vf-default"
PRIORITY_THRESHOLD = 50  # >= this routes to the high-priority queue (premium/hero land here)


def _connect():
    try:
        from redis import Redis  # type: ignore
        from rq import Queue      # type: ignore
    except ImportError as e:  # pragma: no cover - prod-only dep
        raise RuntimeError(
            "RQ backend needs `redis` and `rq` (pip install redis rq). "
            "Or use VF_QUEUE_BACKEND=sync for local runs."
        ) from e
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(url)
    return Queue, conn


class RQQueue(JobQueue):
    name = "rq"

    def __init__(self, *, deliver: bool = True) -> None:
        self._Queue, self._conn = _connect()
        self._deliver = deliver

    def _queue(self, priority: int):
        qname = HIGH_QUEUE if priority >= PRIORITY_THRESHOLD else DEFAULT_QUEUE
        return self._Queue(qname, connection=self._conn)

    def enqueue(self, job_id: str, *, priority: int = 0) -> None:
        self._queue(priority).enqueue(
            "backend.worker.process_job", job_id, deliver=self._deliver,
            job_timeout=int(os.environ.get("VF_JOB_TIMEOUT_S", "1800")),
            retry=None,  # generation retries/fallback are handled inside the task, not by RQ
        )

    def drain(self, max_jobs: int | None = None) -> list[dict[str, Any]]:
        # Draining happens in external `rq worker` processes; nothing to do here.
        return []

    def depth(self) -> int:
        return sum(self._Queue(q, connection=self._conn).count for q in (HIGH_QUEUE, DEFAULT_QUEUE))

    def is_inline(self) -> bool:
        return False
