"""Queue interface. The orchestrator only ever sees these four methods."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class JobQueue(ABC):
    name: str = "base"

    @abstractmethod
    def enqueue(self, job_id: str, *, priority: int = 0) -> None:
        """Hand a created (PENDING) job to the queue. Higher priority is dispatched first."""

    @abstractmethod
    def drain(self, max_jobs: int | None = None) -> list[dict[str, Any]]:
        """Process queued jobs to completion and return their summaries.

        Sync backend: runs them inline now. RQ backend: this is a no-op that points at the
        separate `rq worker` processes (which is where draining actually happens in prod)."""

    @abstractmethod
    def depth(self) -> int:
        """Jobs currently waiting."""

    @abstractmethod
    def is_inline(self) -> bool:
        """True if drain() does the work in-process (sync); False if external workers do (rq)."""
