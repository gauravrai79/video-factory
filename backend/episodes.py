"""Episode — one video moving through the stage-gated production pipeline.

An Episode belongs to a Channel and advances through stages, each with its own status and a human
gate: IDEA -> SCRIPT -> REFS -> SCENES -> AUDIO -> ASSEMBLY -> DONE. Nothing runs until a human
advances it, and every paid stage only runs on the previous stage's approved artifact — that's the
token-safety model (see PRD).

M1 defines the data model + state machine + store (create/list/get shells). The per-stage runners and
gate transitions are wired in later milestones.

Stored in the same SQLite DB as jobs; Postgres swap is a driver change.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from .jobstore import JobStore


class Stage(str, Enum):
    IDEA = "idea"
    SCRIPT = "script"
    REFS = "refs"
    SCENES = "scenes"
    AUDIO = "audio"
    ASSEMBLY = "assembly"
    DONE = "done"


class StageStatus(str, Enum):
    PENDING = "pending"                 # not started
    GENERATING = "generating"           # runner working
    AWAITING_REVIEW = "awaiting_review" # artifact ready, human gate open
    APPROVED = "approved"               # gate passed → advance
    REJECTED = "rejected"               # sent back


STAGE_ORDER = [Stage.IDEA, Stage.SCRIPT, Stage.REFS, Stage.SCENES, Stage.AUDIO,
               Stage.ASSEMBLY, Stage.DONE]

# Shot types the director assigns per scene — the long-form cost engine (cheap -> expensive).
SHOT_TYPES = ("broll", "still_kenburns", "lipsync_still", "hero_video")


def next_stage(stage: Stage) -> Stage:
    i = STAGE_ORDER.index(stage)
    return STAGE_ORDER[min(i + 1, len(STAGE_ORDER) - 1)]


@dataclass
class Scene:
    """One shot in an episode. Stored as a plain dict inside Episode.scenes (JSON-friendly)."""
    seq: int
    heading: str = ""                              # setting / time (e.g. "INT. OFFICE - NIGHT")
    action: str = ""                               # what happens
    camera: str = ""
    cast_present: list[str] = field(default_factory=list)      # character_ids in the shot
    dialogue: list[dict[str, str]] = field(default_factory=list)  # [{speaker, line, delivery}]
    narration: str = ""                            # VO text (narrator voice)
    shot_type: str = "still_kenburns"              # one of SHOT_TYPES
    duration_s: float = 4.0
    reference_image: dict[str, Any] = field(default_factory=dict)  # {path, status}
    clip: dict[str, Any] = field(default_factory=dict)             # {path, status}
    voice_clips: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Episode:
    episode_id: str
    channel_id: str
    number: int
    title: str = ""
    logline: str = ""
    stage: str = Stage.IDEA.value
    stage_status: str = StageStatus.PENDING.value
    idea: dict[str, Any] = field(default_factory=dict)      # approved concept
    idea_brief: str = ""                                    # optional creator steer for ideation
    idea_candidates: list[dict[str, Any]] = field(default_factory=list)  # ideate output (choose one)
    cast: list[str] = field(default_factory=list)           # resolved character_ids
    scenes: list[dict[str, Any]] = field(default_factory=list)  # list of Scene dicts
    style_note: str = ""                                    # applied to every scene's still prompt
    script_qc: dict[str, Any] = field(default_factory=dict)  # judge scorecard {score, breakdown, notes, iterations, passed}
    refs_batch_done: bool = False                           # preview approved -> full batch generated
    timeline: dict[str, Any] = field(default_factory=dict)  # the editable EDL (built at assembly)
    history: list[dict[str, Any]] = field(default_factory=list)  # stage/gate action trail
    stage_error: str = ""
    writer_model: str = ""
    est_cost_usd: float = 0.0
    spent_usd: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def log(self, event: str, detail: dict[str, Any] | None = None) -> None:
        self.history.append({"event": event, "detail": detail or {},
                             "stage": self.stage, "ts": time.time()})

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EpisodeStore:
    """CRUD for episodes, reusing the JobStore's sqlite connection/db path."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self.conn = self.store.conn
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ep_channel ON episodes(tenant_id, channel_id, number);
            """
        )
        self.conn.commit()

    def _next_number(self, tenant_id: str, channel_id: str) -> int:
        row = self.conn.execute(
            "SELECT MAX(number) AS n FROM episodes WHERE tenant_id=? AND channel_id=?",
            (tenant_id, channel_id),
        ).fetchone()
        return int((row["n"] or 0)) + 1

    def create(self, *, tenant_id: str, channel_id: str, title: str = "",
               cast: list[str] | None = None, **fields: Any) -> Episode:
        now = time.time()
        number = self._next_number(tenant_id, channel_id)
        ep = Episode(
            episode_id=str(uuid.uuid4()), channel_id=channel_id, number=number,
            title=title or f"Episode {number}", cast=cast or [],
            created_at=now, updated_at=now,
            **{k: v for k, v in fields.items() if k in Episode.__dataclass_fields__},
        )
        self.conn.execute(
            "INSERT INTO episodes(episode_id,tenant_id,channel_id,number,data,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (ep.episode_id, tenant_id, channel_id, number, json.dumps(ep.as_dict()), now, now),
        )
        self.conn.commit()
        return ep

    @staticmethod
    def _load(data: str) -> Episode:
        d = json.loads(data)
        return Episode(**{k: v for k, v in d.items() if k in Episode.__dataclass_fields__})

    def get(self, episode_id: str) -> Optional[Episode]:
        row = self.conn.execute(
            "SELECT data FROM episodes WHERE episode_id=?", (episode_id,)
        ).fetchone()
        return self._load(row["data"]) if row else None

    def list(self, tenant_id: str, channel_id: str | None = None) -> list[Episode]:
        if channel_id:
            rows = self.conn.execute(
                "SELECT data FROM episodes WHERE tenant_id=? AND channel_id=? ORDER BY number",
                (tenant_id, channel_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT data FROM episodes WHERE tenant_id=? ORDER BY created_at DESC", (tenant_id,)
            ).fetchall()
        return [self._load(r["data"]) for r in rows]

    def update(self, ep: Episode) -> Episode:
        ep.updated_at = time.time()
        self.conn.execute(
            "UPDATE episodes SET number=?, data=?, updated_at=? WHERE episode_id=?",
            (ep.number, json.dumps(ep.as_dict()), ep.updated_at, ep.episode_id),
        )
        self.conn.commit()
        return ep

    def delete(self, episode_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM episodes WHERE episode_id=?", (episode_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def patch(self, episode_id: str, **fields: Any) -> Episode | None:
        ep = self.get(episode_id)
        if not ep:
            return None
        for k, v in fields.items():
            if k in Episode.__dataclass_fields__ and k not in ("episode_id", "created_at"):
                setattr(ep, k, v)
        return self.update(ep)
