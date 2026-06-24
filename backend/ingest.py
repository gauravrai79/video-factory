"""CSV ingestion — the FSN manifest that ops uploads.

One row per SKU (FSN). Columns map the seller manifest + USPs/callouts. Unknown extra columns are
preserved in `extra` so different catalog exports still flow through. Mirrors the doc's ingestion
layer (Sheets/CSV → normalize → one job per FSN, tagged with tier).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Recognized columns (case-insensitive). Everything maps to a SKU manifest row.
CORE_COLUMNS = {
    "fsn", "title", "category", "tier", "image_url", "image_urls",
    "usps", "callouts", "color", "pattern", "hero",
}


@dataclass
class SkuRow:
    fsn: str
    title: str = ""
    category: str = ""
    tier: str = "basic"               # premium | basic — drives spec/model routing
    image_url: str = ""
    image_urls: list[str] = field(default_factory=list)   # multiple seller angles
    usps: list[str] = field(default_factory=list)
    callouts: list[str] = field(default_factory=list)
    color: str = ""
    pattern: str = ""
    hero: bool = False                # hero SKU -> Seedance route
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_difficult_print(self) -> bool:
        p = self.pattern.lower()
        return bool(p) and p not in ("solid", "plain", "none")


def _split(value: str) -> list[str]:
    if not value:
        return []
    # Support ';' or '|' separated lists inside a CSV cell.
    for sep in (";", "|"):
        if sep in value:
            return [v.strip() for v in value.split(sep) if v.strip()]
    return [value.strip()] if value.strip() else []


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y", "hero")


def parse_row(raw: dict[str, str]) -> SkuRow:
    low = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
    image_urls = _split(low.get("image_urls", "")) or _split(low.get("image_url", ""))
    row = SkuRow(
        fsn=low.get("fsn", "") or low.get("sku", ""),
        title=low.get("title", ""),
        category=low.get("category", ""),
        tier=(low.get("tier", "basic") or "basic").lower(),
        image_url=(image_urls[0] if image_urls else ""),
        image_urls=image_urls,
        usps=_split(low.get("usps", "")),
        callouts=_split(low.get("callouts", "")) or _split(low.get("usps", "")),
        color=low.get("color", ""),
        pattern=low.get("pattern", ""),
        hero=_truthy(low.get("hero", "")) or (low.get("tier", "").lower() == "premium"),
        extra={k: v for k, v in low.items() if k not in CORE_COLUMNS and v},
    )
    return row


def load_csv(path: str | Path) -> list[SkuRow]:
    rows: list[SkuRow] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            r = parse_row(raw)
            if r.fsn:
                rows.append(r)
    return rows
