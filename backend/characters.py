"""Character — a digital actor (the primary reusable cast entity).

A Character is a persistent actor (human or animal — a glamour model, or Jango the dog) that stays
consistent across every scene, episode, and channel. It carries three locked "DNAs":

  - Visual DNA   — reference images injected into every still/video generation (the face/body/look).
  - Voice DNA    — one locked voice (provider + voice_id, preset or cloned) reused for every spoken
                   line the character ever says, so the voice is consistent by construction.
  - Personality  — a structured character bible (backstory, traits, speech style, catchphrases,
                   relationships, mannerisms) rendered as a SYSTEM PROMPT and injected at every
                   generative stage: writer dialogue, TTS delivery, and visual/motion prompts.

Reference images live on local disk (a Railway volume). They are uploaded (real photos of Jango) or
minted from `dna_prompt` via a character-consistent image model (capabilities/fal_image).

Stored in the same SQLite DB as jobs; Postgres swap is a driver change.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
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
    reference_images: list[str] = field(default_factory=list)   # Visual DNA — local paths
    dna_prompt: str = ""                       # canonical look description (mints reference sheet)
    safety_tolerance: int = 5                  # fal safety_tolerance (1=strict..6=permissive)
    # Voice DNA — a locked voice reused for every line, across all scenes/episodes/channels.
    voice: dict[str, Any] = field(default_factory=dict)
    #   keys: provider (elevenlabs|...), voice_id, cloned (bool), params {pace,stability,accent},
    #         signature_line (a short preview line), preview_path (rendered signature audio)
    # Personality DNA — structured character bible; rendered as a system prompt (personality_prompt()).
    personality: dict[str, Any] = field(default_factory=dict)
    #   keys: backstory, traits (list), speech_style, catchphrases (list),
    #         relationships (dict name->relation), mannerisms (list)
    social_accounts: dict[str, str] = field(default_factory=dict)   # platform -> handle/url
    posting_schedule: dict[str, Any] = field(default_factory=dict)  # e.g. {"reels_per_day": 3}
    active: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def personality_prompt(self) -> str:
        """Render the personality bible as a system-prompt block for the writer / TTS delivery /
        motion prompts, so the actor behaves consistently everywhere. Empty if no bible set."""
        p = self.personality or {}
        lines: list[str] = []
        who = f"{self.name}" + (f" (a {self.species})" if self.species and self.species != "person" else "")
        lines.append(f"Character: {who}.")
        if p.get("backstory"):
            lines.append(f"Backstory: {p['backstory']}")
        if p.get("traits"):
            lines.append("Traits: " + ", ".join(p["traits"]))
        if p.get("speech_style"):
            lines.append(f"Speech style: {p['speech_style']}")
        if p.get("catchphrases"):
            lines.append("Catchphrases: " + "; ".join(f'"{c}"' for c in p["catchphrases"]))
        if p.get("mannerisms"):
            lines.append("Mannerisms: " + ", ".join(p["mannerisms"]))
        if p.get("relationships"):
            rel = "; ".join(f"{k}: {v}" for k, v in p["relationships"].items())
            lines.append(f"Relationships: {rel}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def voice_id(self) -> str | None:
        return (self.voice or {}).get("voice_id")

    def has_voice(self) -> bool:
        return bool(self.voice_id())

    def has_reference(self) -> bool:
        return bool(self.reference_images)

    def look_descriptor(self) -> str:
        """One compact line describing the character's LOOK — injected into every shot prompt so the
        model renders the right character (reinforcing, not replacing, the reference images). Prefers
        an explicit appearance/dna_prompt over a bare name so shots aren't under-specified."""
        pr = self.persona or {}
        # No "(a {species})" parenthetical — bad grammar ("a animal") and the appearance string
        # already names the species ("a small fawn French bulldog").
        who = self.name
        appearance = (pr.get("appearance") or self.dna_prompt or "").strip()
        bits = [
            who,
            f"{self.age}" if self.age else "",
            appearance,
            pr.get("facial_features", ""),
            pr.get("body_type", ""),
            pr.get("hair", ""),
        ]
        line = ", ".join(b for b in bits if b)
        return line or who

    def voice_description(self) -> str:
        """How this character SOUNDS, in words. Veo generates each clip independently and has no
        voice memory, so the same character drifts to a different voice every scene — injecting a
        fixed description into every video prompt keeps it recognisably the same character."""
        return ((self.voice or {}).get("description") or "").strip()

    def speaker_tag(self) -> str:
        """Short VISUAL tag for dialogue attribution in video prompts (\"the small fawn French
        bulldog\") — a name alone means nothing to the model; with two characters in frame the
        speaker must be identified by what it can SEE."""
        appearance = ((self.persona or {}).get("appearance") or self.dna_prompt or "").strip()
        if not appearance:
            return self.name
        words = appearance.split()[:10]
        # cut AT the first connective so the tag is a complete noun phrase, never a dangling
        # fragment like "...bulldog with a compact"
        for i, w in enumerate(words):
            if i >= 2 and w.lower().strip(",;.") in ("with", "wearing", "and", "in", "holding", "carrying"):
                words = words[:i]
                break
        head = " ".join(words).rstrip(",;.")
        for art in ("a ", "an ", "the "):
            if head.lower().startswith(art):
                head = head[len(art):]
                break
        return f"{self.name}, the {head}"


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

    def remove_reference_image(self, character_id: str, idx: int) -> Character | None:
        """Drop the reference image at index idx (and best-effort delete the file on disk)."""
        char = self.get(character_id)
        if not char or idx < 0 or idx >= len(char.reference_images):
            return None
        removed = char.reference_images.pop(idx)
        char = self.update(char)
        try:
            p = Path(removed)
            if p.is_file() and "characters" in p.parts:      # only our own uploaded refs
                p.unlink()
        except OSError:
            pass
        return char

    def patch(self, character_id: str, **fields: Any) -> Character | None:
        """Partial update — set only the given known fields (e.g. voice, personality, dna_prompt)."""
        char = self.get(character_id)
        if not char:
            return None
        for k, v in fields.items():
            if k in Character.__dataclass_fields__ and k not in ("character_id", "created_at"):
                setattr(char, k, v)
        return self.update(char)
