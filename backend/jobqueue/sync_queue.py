"""In-process priority queue — the default backend.

Enqueue is non-blocking (mirrors RQ semantics); drain() pops highest-priority-first and runs the
worker task inline. No Redis, no fork — runs anywhere, including Windows dev. Deterministic order
makes it the backend tests use.
"""

from __future__ import annotations

import heapq
import itertools
from typing import Any

from ..worker import process_job
from .base import JobQueue


class SyncQueue(JobQueue):
    name = "sync"

    def __init__(self, *, deliver: bool = True) -> None:
        self._heap: list[tuple[int, int, str]] = []
        self._counter = itertools.count()
        self._deliver = deliver

    def enqueue(self, job_id: str, *, priority: int = 0) -> None:
        # Negate priority for a max-heap; tie-break by insertion order (stable, FIFO within a tier).
        heapq.heappush(self._heap, (-priority, next(self._counter), job_id))

    def drain(self, max_jobs: int | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        n = 0
        while self._heap:
            if max_jobs is not None and n >= max_jobs:
                break
            _, _, job_id = heapq.heappop(self._heap)
            out.append(process_job(job_id, deliver=self._deliver))
            n += 1
        return out

    def depth(self) -> int:
        return len(self._heap)

    def is_inline(self) -> bool:
        return True
