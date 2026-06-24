"""RQ worker entrypoint — drains the production queue (VF_QUEUE_BACKEND=rq).

  VF_QUEUE_BACKEND=rq REDIS_URL=redis://localhost:6379/0 python scripts/worker.py

Listens high-priority queue first. Each task is backend.worker.process_job(job_id), which runs the
job through generate -> finish -> qc -> deliver with retries + model fallback. Run as many of these as
you need for throughput; RQ distributes jobs across them.

Note: RQ workers fork, so this side runs on Linux/macOS (the production target). On Windows, use the
sync backend (the default) via scripts/run_batch.py — it drains inline, no Redis needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> int:
    try:
        from redis import Redis      # type: ignore
        from rq import Queue, Worker  # type: ignore
    except ImportError:
        print("RQ worker needs `redis` and `rq` (pip install redis rq).", file=sys.stderr)
        return 1

    from backend.jobqueue.rq_queue import HIGH_QUEUE, DEFAULT_QUEUE

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(url)
    queues = [Queue(HIGH_QUEUE, connection=conn), Queue(DEFAULT_QUEUE, connection=conn)]
    print(f"Video Factory worker up on {url}; listening: {[q.name for q in queues]}")
    Worker(queues, connection=conn).work(with_scheduler=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
