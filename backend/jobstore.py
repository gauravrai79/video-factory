"""Job state machine + hash-chained audit.

Phase 1 uses stdlib sqlite3 (zero deps, real transactional semantics). Phase 2 swaps the connection
for Postgres on Railway with `(tenant_id, project)` RLS — the schema and the repository API are
already shaped for it, so it's a driver change, not a rewrite.

The audit chain mirrors Spine's tamper-evident audit bus: each event stores the hash of the previous
event + its own payload, so the full history of a job is verifiable end-to-end.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class State(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    FINISHING = "finishing"
    QC = "qc"
    APPROVED = "approved"
    REWORK = "rework"
    DELIVERED = "delivered"
    FAILED = "failed"


# Allowed transitions — the spine of the factory.
TRANSITIONS: dict[State, set[State]] = {
    # PENDING -> REWORK: the cost-ceiling guardrail holds a job for human approval before any paid
    # generation; REWORK -> GENERATING then resumes it once approved.
    State.PENDING: {State.GENERATING, State.REWORK, State.FAILED},
    State.GENERATING: {State.FINISHING, State.FAILED, State.REWORK},
    State.FINISHING: {State.QC, State.FAILED},
    State.QC: {State.APPROVED, State.REWORK, State.FAILED},
    State.APPROVED: {State.DELIVERED, State.FAILED},
    State.REWORK: {State.GENERATING, State.FAILED},
    State.DELIVERED: set(),
    State.FAILED: {State.GENERATING},  # manual retry
}


class TransitionError(RuntimeError):
    pass


def _db_path() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    # Phase 1 default: local file.
    p = Path(os.environ.get("VF_DB_PATH", "var/video_factory.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


@dataclass
class Job:
    job_id: str
    tenant_id: str
    project: str
    fsn: str
    state: State
    payload: dict[str, Any] = field(default_factory=dict)   # SKU manifest row, prompt, model route
    result: dict[str, Any] = field(default_factory=dict)    # clip path, finished path, cost, qc
    created_at: float = 0.0
    updated_at: float = 0.0


class JobStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _db_path()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                project TEXT NOT NULL,
                fsn TEXT NOT NULL,
                state TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                result TEXT NOT NULL DEFAULT '{}',
                idempotency_key TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL,
                ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(tenant_id, project, state);
            CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_log(job_id, seq);
            """
        )
        self.conn.commit()

    # ---- jobs ----

    def create(self, *, tenant_id: str, project: str, fsn: str,
               payload: dict[str, Any], idempotency_key: str | None = None) -> Job:
        now = time.time()
        job_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO jobs(job_id,tenant_id,project,fsn,state,payload,result,idempotency_key,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job_id, tenant_id, project, fsn, State.PENDING.value,
             json.dumps(payload), "{}", idempotency_key, now, now),
        )
        self.conn.commit()
        job = Job(job_id, tenant_id, project, fsn, State.PENDING, payload, {}, now, now)
        self.append_event(job, "created", {"fsn": fsn})
        return job

    def get(self, job_id: str) -> Optional[Job]:
        row = self.conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def find_by_idempotency_key(self, tenant_id: str, project: str, key: str) -> Optional[Job]:
        """Most-recent job for an idempotency key, scoped by tenant/project (Spine RLS shape).
        Used to skip re-ingesting the same SKU twice."""
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE tenant_id=? AND project=? AND idempotency_key=?"
            " ORDER BY created_at DESC LIMIT 1",
            (tenant_id, project, key),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def list(self, *, tenant_id: str | None = None, state: State | None = None) -> list[Job]:
        q, args = "SELECT * FROM jobs WHERE 1=1", []
        if tenant_id:
            q += " AND tenant_id=?"; args.append(tenant_id)
        if state:
            q += " AND state=?"; args.append(state.value)
        q += " ORDER BY created_at"
        return [self._row_to_job(r) for r in self.conn.execute(q, args).fetchall()]

    def transition(self, job: Job, to: State, detail: dict[str, Any] | None = None,
                   result_update: dict[str, Any] | None = None) -> Job:
        if to not in TRANSITIONS.get(job.state, set()):
            raise TransitionError(f"illegal transition {job.state.value} -> {to.value}")
        if result_update:
            job.result.update(result_update)
        job.state = to
        job.updated_at = time.time()
        self.conn.execute(
            "UPDATE jobs SET state=?, result=?, updated_at=? WHERE job_id=?",
            (to.value, json.dumps(job.result), job.updated_at, job.job_id),
        )
        self.conn.commit()
        self.append_event(job, f"state:{to.value}", detail or {})
        return job

    # ---- hash-chained audit (mirrors Spine) ----

    def append_event(self, job: Job, event: str, detail: dict[str, Any]) -> None:
        row = self.conn.execute(
            "SELECT seq, hash FROM audit_log WHERE job_id=? ORDER BY seq DESC LIMIT 1",
            (job.job_id,),
        ).fetchone()
        seq = (row["seq"] + 1) if row else 0
        prev_hash = row["hash"] if row else "0" * 64
        ts = time.time()
        body = json.dumps({"job_id": job.job_id, "seq": seq, "event": event,
                           "detail": detail, "prev_hash": prev_hash, "ts": ts}, sort_keys=True)
        h = hashlib.sha256(body.encode()).hexdigest()
        self.conn.execute(
            "INSERT INTO audit_log(job_id,tenant_id,project,seq,event,detail,prev_hash,hash,ts)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (job.job_id, job.tenant_id, job.project, seq, event, json.dumps(detail), prev_hash, h, ts),
        )
        self.conn.commit()

    def audit_trail(self, job_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT seq,event,detail,prev_hash,hash,ts FROM audit_log WHERE job_id=? ORDER BY seq",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def verify_chain(self, job_id: str) -> bool:
        prev = "0" * 64
        for r in self.conn.execute(
            "SELECT job_id,seq,event,detail,prev_hash,hash,ts FROM audit_log WHERE job_id=? ORDER BY seq",
            (job_id,),
        ).fetchall():
            if r["prev_hash"] != prev:
                return False
            body = json.dumps({"job_id": r["job_id"], "seq": r["seq"], "event": r["event"],
                               "detail": json.loads(r["detail"]), "prev_hash": r["prev_hash"],
                               "ts": r["ts"]}, sort_keys=True)
            if hashlib.sha256(body.encode()).hexdigest() != r["hash"]:
                return False
            prev = r["hash"]
        return True

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"], tenant_id=row["tenant_id"], project=row["project"],
            fsn=row["fsn"], state=State(row["state"]),
            payload=json.loads(row["payload"]), result=json.loads(row["result"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
