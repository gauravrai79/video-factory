"""Backend selection. One env var (VF_QUEUE_BACKEND) flips sync <-> rq; nothing else changes."""

from __future__ import annotations

import os

from .base import JobQueue


def get_queue(*, deliver: bool = True, backend: str | None = None) -> JobQueue:
    backend = (backend or os.environ.get("VF_QUEUE_BACKEND", "sync")).lower()
    if backend == "sync":
        from .sync_queue import SyncQueue
        return SyncQueue(deliver=deliver)
    if backend == "rq":
        from .rq_queue import RQQueue
        return RQQueue(deliver=deliver)
    raise ValueError(f"Unknown VF_QUEUE_BACKEND={backend!r}. Choose: sync | rq")
