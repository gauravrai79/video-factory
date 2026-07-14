"""Channel — the show bible (a series / account with a recurring format).

A Channel is the top-level entity above episodes: it fixes the premise, platform, format (long vs
short form), the recurring cast, the art style, the target length, the per-episode video budget, and
which writer model drafts its stories. Episodes inherit all of this. A `series_memory` keeps a running
bible + episode recaps so a new episode remembers the last (recurring gags, relationships).

Example — "Django, P.I.": youtube · long_form · premise "a golden-retriever detective and his sidekick
Zoom solve a mystery each episode, Sherlock-noir tone" · cast [Django=lead, Zoom=sidekick] ·
art_style "noir cinematic" · 16 scenes · 120s.

Stored in the same SQLite DB as jobs; Postgres swap is a driver change.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .jobstore import JobStore

FORMATS = ("long_form", "short_form")
CAST_ROLES = ("lead", "sidekick", "recurring")


@dataclass
class Channel:
    channel_id: str
    name: str
    slug: str
    platform: str = "youtube"                   # youtube | instagram | tiktok | ...
    format: str = "long_form"                   # long_form | short_form
    premise: str = ""                           # the show's concept (drives ideation)
    cast: list[dict[str, str]] = field(default_factory=list)   # [{character_id, role}]
    narrator_voice_id: str = ""                 # channel-level narrator voice
    art_style: str = ""                         # e.g. "noir cinematic", "photoreal glamour"
    art_style_id: str = ""                      # id from styles.ART_STYLES (blank = custom art_style)
    tone: str = ""                              # comedy | thriller | wholesome | … (steers the writer)
    tagline: str = ""                           # short show tagline
    world: str = ""                             # setting/location bible injected into EVERY visual prompt
    language: str = "English"                   # spoken language for dialogue + narration + VO
    style_reference_images: list[str] = field(default_factory=list)   # lock the look
    target_scene_count: int = 16                # long-form ~15-20; short-form ~3
    target_duration_s: int = 120
    video_budget: int = 4                       # max hero-video scenes/episode (cost cap)
    writer_provider: str = "anthropic"          # anthropic | gemini | openai
    writer_model: str = ""                      # blank -> provider default
    series_memory: dict[str, Any] = field(default_factory=dict)   # {bible, recaps: [..]}
    transitions: list[dict[str, Any]] = field(default_factory=list)  # reusable ~2s transition clips
    #   each: {id, kind, label, path, prompt, created_at}
    posting_cadence: str = ""
    active: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def cast_ids(self) -> list[str]:
        return [c.get("character_id") for c in self.cast if c.get("character_id")]

    def lead_id(self) -> str | None:
        for c in self.cast:
            if c.get("role") == "lead":
                return c.get("character_id")
        return self.cast_ids()[0] if self.cast else None

    def is_short(self) -> bool:
        return self.format == "short_form"


class ChannelStore:
    """CRUD for channels, reusing the JobStore's sqlite connection/db path."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self.conn = self.store.conn
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_slug ON channels(tenant_id, slug);
            """
        )
        self.conn.commit()

    def create(self, *, tenant_id: str, name: str, slug: str, **fields: Any) -> Channel:
        now = time.time()
        ch = Channel(
            channel_id=str(uuid.uuid4()), name=name, slug=slug,
            created_at=now, updated_at=now,
            **{k: v for k, v in fields.items() if k in Channel.__dataclass_fields__},
        )
        self.conn.execute(
            "INSERT INTO channels(channel_id,tenant_id,slug,name,data,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (ch.channel_id, tenant_id, slug, name, json.dumps(ch.as_dict()), now, now),
        )
        self.conn.commit()
        return ch

    @staticmethod
    def _load(data: str) -> Channel:
        d = json.loads(data)
        return Channel(**{k: v for k, v in d.items() if k in Channel.__dataclass_fields__})

    def get(self, channel_id: str) -> Optional[Channel]:
        row = self.conn.execute(
            "SELECT data FROM channels WHERE channel_id=?", (channel_id,)
        ).fetchone()
        return self._load(row["data"]) if row else None

    def get_by_slug(self, tenant_id: str, slug: str) -> Optional[Channel]:
        row = self.conn.execute(
            "SELECT data FROM channels WHERE tenant_id=? AND slug=?", (tenant_id, slug)
        ).fetchone()
        return self._load(row["data"]) if row else None

    def list(self, tenant_id: str) -> list[Channel]:
        rows = self.conn.execute(
            "SELECT data FROM channels WHERE tenant_id=? ORDER BY created_at", (tenant_id,)
        ).fetchall()
        return [self._load(r["data"]) for r in rows]

    def update(self, ch: Channel) -> Channel:
        ch.updated_at = time.time()
        self.conn.execute(
            "UPDATE channels SET slug=?, name=?, data=?, updated_at=? WHERE channel_id=?",
            (ch.slug, ch.name, json.dumps(ch.as_dict()), ch.updated_at, ch.channel_id),
        )
        self.conn.commit()
        return ch

    def patch(self, channel_id: str, **fields: Any) -> Channel | None:
        ch = self.get(channel_id)
        if not ch:
            return None
        for k, v in fields.items():
            if k in Channel.__dataclass_fields__ and k not in ("channel_id", "created_at"):
                setattr(ch, k, v)
        return self.update(ch)
