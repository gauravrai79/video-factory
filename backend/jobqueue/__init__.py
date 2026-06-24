"""Pluggable job queue.

Two backends, one interface, selected by VF_QUEUE_BACKEND:
  - `sync` (default): in-process, priority-ordered, drains on demand. Zero infra, runs on Windows,
    deterministic for tests. This is the Phase-1/dev path.
  - `rq`: Redis-backed RQ for production fan-out across worker processes/machines (Linux).

Adding a backend = implement JobQueue + register in factory.get_queue(). Nothing else changes —
batch ingestion and the worker task are backend-agnostic (they only ever call enqueue / drain).
"""

from .base import JobQueue
from .factory import get_queue

__all__ = ["JobQueue", "get_queue"]
