"""Character — the primary entity of the influencer factory.

A Character is a persistent persona (human or animal — e.g. a glamour model, or Jango the dog) that
must stay visually and behaviorally consistent across thousands of generated posts. Its reference
images are its "DNA": they're injected into every still/video generation so the same face/body/look
carries through. The persona text is injected into every prompt so the system never has to be
re-prompted by hand.

Reference images live on local disk (a Railway volume) for v1 — see project decisions. They are
either uploaded by the operator (e.g. real photos of Jango) or minted once from `dna_prompt` via a
character-consistent image model (see capabilities/fal_image.mint_reference_sheet).

Stored in the same SQLite DB as jobs; Postgres swap is a driver change (the repository API is shaped
for it).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .jobstore import JobStore


@dataclass
class Character:
    character_id: str
    name: str
    slug: str                                  # url/file-safe id, e.g. "luna" or "jango"
    species: str = "person"                    # "person" | "animal" — keeps the model general
    age: str = ""                              # free text ("24", "young adult"), persona only
    # Persona is a free-form structured blob; these keys feed the prompt builder when present.
    persona: dict[str, Any] = field(default_factory=dict)
    #   recognized persona keys: appearance, facial_features, body_type, hair, voice, personality,
    #   clothing_style, environments (list), niche, tone
    reference_images: list[str] = field(default_factory=list)   # local paths = character "DNA"
    dna_prompt: str = ""                       # canonical look description (mints reference sheet)
    safety_tolerance: int = 5                  # fal safety_tolerance (1=strict..6=permissive)
    social_accounts: dict[str, str] = field(default_factory=dict)   # platform -> handle/url
    posting_schedule: dict[str, Any] = field(default_factory=dict)  # e.g. {"reels_per_day": 3}
    active: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def look_descriptor(self) -> str:
        """One compact line describing the character's look — injected into every shot prompt so a
        text-only generation (or an LLM refine) keeps the persona without manual prompting."""
        pr = self.persona
        bits = [
            self.name,
            f"{self.age}" if self.age else "",
            self.species if self.species != "person" else "",
            pr.get("appearance", ""),
            pr.get("facial_features", ""),
            pr.get("body_type", ""),
            pr.get("hair", ""),
        ]
        line = ", ".join(b for b in bits if b)
        return line or self.dna_prompt or self.name


class CharacterStore:
    """CRUD for characters, reusing the JobStore's sqlite connection/db path."""

    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self.conn = self.store.conn
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS characters (
                character_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_char_slug ON characters(tenant_id, slug);
            """
        )
        self.conn.commit()

    def create(self, *, tenant_id: str, name: str, slug: str, **fields: Any) -> Character:
        now = time.time()
        char = Character(
            character_id=str(uuid.uuid4()), name=name, slug=slug,
            created_at=now, updated_at=now,
            **{k: v for k, v in fields.items() if k in Character.__dataclass_fields__},
        )
        self.conn.execute(
            "INSERT INTO characters(character_id,tenant_id,slug,name,data,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (char.character_id, tenant_id, slug, name, json.dumps(char.as_dict()), now, now),
        )
        self.conn.commit()
        return char

    def get(self, character_id: str) -> Optional[Character]:
        row = self.conn.execute(
            "SELECT data FROM characters WHERE character_id=?", (character_id,)
        ).fetchone()
        return Character(**json.loads(row["data"])) if row else None

    def get_by_slug(self, tenant_id: str, slug: str) -> Optional[Character]:
        row = self.conn.execute(
            "SELECT data FROM characters WHERE tenant_id=? AND slug=?", (tenant_id, slug)
        ).fetchone()
        return Character(**json.loads(row["data"])) if row else None

    def list(self, tenant_id: str) -> list[Character]:
        rows = self.conn.execute(
            "SELECT data FROM characters WHERE tenant_id=? ORDER BY created_at", (tenant_id,)
        ).fetchall()
        return [Character(**json.loads(r["data"])) for r in rows]

    def update(self, char: Character) -> Character:
        char.updated_at = time.time()
        self.conn.execute(
            "UPDATE characters SET slug=?, name=?, data=?, updated_at=? WHERE character_id=?",
            (char.slug, char.name, json.dumps(char.as_dict()), char.updated_at, char.character_id),
        )
        self.conn.commit()
        return char

    def add_reference_images(self, character_id: str, paths: list[str]) -> Character | None:
        char = self.get(character_id)
        if not char:
            return None
        char.reference_images = list(dict.fromkeys([*char.reference_images, *paths]))
        return self.update(char)
