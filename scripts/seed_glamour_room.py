"""Seed the "Tara's Glamour Room" channel + its cast into the DB (idempotent).

A cinematic AI glamour universe fronted by **Tara** (the Indian anchor — main IP) and her global
friends, exploring Indian fashion, confidence, beauty and men's lifestyle. Cast is deliberately small:

  • Tara     — lead / main IP (mid-30s desi glamour, saree + boss-lady energy).
  • Isabella — recurring guest (late-20s Brazilian, "foreign girl discovers Indian glamour"),
               introduced in Phase 2 and promoted to recurring in Phase 3.

Characters are created WITHOUT reference images — add those yourself (console, or
POST /api/characters/{id}/reference). Audio is native to the video engine (Veo 3.1 Lite); no TTS.

Usage:  python scripts/seed_glamour_room.py
Re-running is safe: it reuses existing characters/channel and updates their fields.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.jobstore import JobStore
from backend.channels import ChannelStore
from backend.characters import CharacterStore

TENANT = os.environ.get("VF_TENANT_ID", "factory")
CHANNEL_NAME = "Tara's Glamour Room"
CHANNEL_SLUG = "tara"      # kept stable so existing references/media don't orphan
_CHAR_FIELDS = ("species", "age", "persona", "reference_images", "dna_prompt",
                "safety_tolerance", "voice", "personality", "social_accounts", "posting_schedule")

PREMISE = (
    "\"Tara's Glamour Room\" is a cinematic AI glamour universe fronted by Tara — a curvy, confident "
    "Indian anchor in her mid-30s (saree + boss-lady energy) — and her global friends, exploring "
    "Indian fashion, confidence, beauty and men's lifestyle for a mostly-male audience. Tara is the "
    "main IP and the face of the page; guest 'global glamour' friends (foreign women discovering "
    "Indian fashion) are introduced over time.\n\n"
    "ROLLOUT — bias the content mix by phase:\n"
    "  • Phase 1 (first ~30-50 reels): 70-80% Tara. Establish the page identity — her face, visual "
    "style, caption voice, Hinglish delivery and the Indian-glamour theme — so the audience and the "
    "algorithm learn the page before variety is introduced.\n"
    "  • Phase 2: introduce guest girls via formats like 'Tara invites...', 'Tara's foreign friend "
    "tries Indian fashion', 'Global Glamour Club: Ep 1'. Lead trend: foreign women wearing Indian "
    "ethnic wear (novelty + Indian-male attention + cultural pride + glamour + contrast).\n"
    "  • Phase 3: promote whichever guest gets the most traction to recurring. Keep the cast SMALL — "
    "3-4 characters maximum.\n\n"
    "RECURRING SEGMENT FORMATS:\n"
    "  • Tara — Saree Tara · Office Tara · Tara Replies · Tara After Dark · Tara Rates Men's Style.\n"
    "  • Isabella (Brazilian guest -> recurring) — 'Brazilian girl wears a saree for the first time' · "
    "'kurti vs saree' · 'Indian men, explain this to me...' · 'Is this how you wear a dupatta?' · "
    "'Rate my Indian look'.\n\n"
    "BRAND FIT — Tara: perfume, watches, grooming, men's fashion, premium non-alcohol / "
    "whisky-alternative lifestyle, sunglasses, cars, dating apps, men's skincare, fitness wear. "
    "Isabella: ethnic wear, jewellery, beauty, travel, Indian grooming brands, perfume, men's "
    "accessories, festive campaigns."
)

CHANNEL = dict(
    platform="instagram",
    format="short_form",
    language="Hinglish",
    premise=PREMISE,
    art_style=("cinematic photorealistic glamour, warm premium lighting, shallow depth of field, "
               "editorial Bollywood-glam colour grade"),
    world=("contemporary upscale India — modern designer apartments, boutique studio sets, "
           "ethnic-wear boutiques, festive / Diwali sets, city rooftops at golden hour, luxe "
           "evening lounges"),
    target_scene_count=3,
    target_duration_s=30,
    video_budget=3,
    writer_provider="anthropic",
    posting_cadence="3 reels/week",
    series_memory={
        "bible": PREMISE,
        "phase": 1,
        "phase_note": "Phase 1: 70-80% Tara — establish page identity before introducing guests.",
        "cast_plan": {"Tara": "lead / main IP",
                      "Isabella": "Phase-2 Brazilian guest -> Phase-3 recurring"},
        "segments": {
            "Tara": ["Saree Tara", "Office Tara", "Tara Replies", "Tara After Dark",
                     "Tara Rates Men's Style"],
            "Isabella": ["Brazilian girl wears a saree for the first time", "kurti vs saree",
                         "Indian men, explain this to me...", "Is this how you wear a dupatta?",
                         "Rate my Indian look"],
        },
        "recaps": [],
    },
)

# (character slug, role) — order sets the roster; Tara leads.
CAST = [("tara", "lead"), ("isabella", "recurring")]


def _upsert_character(cs: CharacterStore, slug: str):
    spec = json.loads((Path("samples") / f"{slug}.json").read_text(encoding="utf-8"))
    fields = {k: v for k, v in spec.items() if k in _CHAR_FIELDS}
    char = cs.get_by_slug(TENANT, slug)
    if char:
        char = cs.patch(char.character_id, **fields)
        print(f"character: updated existing '{char.name}' ({char.character_id})")
    else:
        char = cs.create(tenant_id=TENANT, name=spec["name"], slug=spec["slug"], **fields)
        print(f"character: created '{char.name}' ({char.character_id})")
    return char


def main() -> int:
    store = JobStore()
    cs, chs = CharacterStore(store), ChannelStore(store)

    chars = {slug: _upsert_character(cs, slug) for slug, _ in CAST}
    cast = [{"character_id": chars[slug].character_id, "role": role} for slug, role in CAST]

    ch = chs.get_by_slug(TENANT, CHANNEL_SLUG)
    if ch:
        ch = chs.patch(ch.channel_id, name=CHANNEL_NAME, cast=cast, **CHANNEL)
        print(f"channel:   updated existing '{ch.name}' ({ch.channel_id})")
    else:
        ch = chs.create(tenant_id=TENANT, name=CHANNEL_NAME, slug=CHANNEL_SLUG, cast=cast, **CHANNEL)
        print(f"channel:   created '{ch.name}' ({ch.channel_id})")

    roster = ", ".join(f"{slug} ({role})" for slug, role in CAST)
    print(f"\n'{ch.name}' is live: channel '{ch.slug}' · {ch.format} · {ch.platform} · "
          f"lang={ch.language} · cast=[{roster}].")
    print("Reference images per character (add your own):")
    for slug in chars:
        print(f"  - {slug}: {len(chars[slug].reference_images)} refs  (id {chars[slug].character_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
