"""End-to-end pipeline smoke test — run BEFORE handing over changes.

Drives a throwaway episode through every stage (script -> refs -> scenes -> audio ->
assembly -> done) in STUB mode ($0, no API calls) on the real channel, asserting the
state transitions and that each stage produces its artifact. Catches the classes of bug
that kept reaching the user: broken assembly (WinError/xfade collapse), stale flags,
missing artifacts, no-double-charge, and the character->motion routing.

Usage:  python scripts/e2e_smoke.py
Exit 0 = all checks pass. Non-zero = something is broken; do NOT hand over.
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv(".env")
# STUB MODE: drop generation keys so every capability stubs at $0. Keep ffmpeg paths.
for _k in ("FAL_KEY", "OPENROUTER_API_KEY", "SARVAM_API_KEY", "GOOGLE_API_KEY", "VF_USE_LLM"):
    os.environ.pop(_k, None)
_OUT = tempfile.mkdtemp(prefix="vf_e2e_")
os.environ["VF_OUT_DIR"] = _OUT

from backend.jobstore import JobStore
from backend.episodes import EpisodeStore, StageStatus
from backend.channels import ChannelStore
from backend import episode_pipeline as pl
from backend.finishing import media_duration

TENANT = os.environ.get("VF_TENANT_ID", "factory")
_fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def main() -> int:
    store = JobStore()
    eps, chs = EpisodeStore(store), ChannelStore(store)
    ch = next((c for c in chs.list(TENANT) if c.cast_ids()), None)
    if not ch:
        print("no channel with cast — cannot run e2e"); return 2
    print(f"channel: {ch.name}  (cast={len(ch.cast_ids())}, world={'set' if ch.world else 'none'})")

    ep = eps.create(tenant_id=TENANT, channel_id=ch.channel_id, title="__E2E_SMOKE__", cast=ch.cast_ids())
    try:
        # --- SCRIPT (skip ideate which needs keys; seed an idea) ---
        ep.idea = {"title": "E2E", "logline": "smoke test", "hook": "x", "beats": ["a", "b"]}
        ep.stage = "script"; eps.update(ep)
        ep = pl.run_stage(store, ep)
        check("script generated", bool(ep.scenes), f"{len(ep.scenes)} scenes")
        check("script awaiting_review", ep.stage_status == StageStatus.AWAITING_REVIEW.value)
        check("refs flag reset by rewrite", ep.refs_batch_done is False)
        # character->motion routing: no scene with cast is a bare still
        bad = [s["seq"] for s in ep.scenes if (s.get("cast_present") and s.get("shot_type") in ("broll", "still_kenburns"))]
        check("no character stuck in a still", not bad, f"scenes {bad}")
        ep = pl.approve_stage(store, ep)
        check("advanced to refs", ep.stage == "refs")

        # --- REFS (preview + batch) ---
        ep = pl.run_stage(store, ep)
        prev = [s for s in ep.scenes if (s.get("reference_image") or {}).get("status") == "ok"]
        check("refs preview made 1 image", len(prev) == 1)
        check("preview file exists", bool(prev) and Path(prev[0]["reference_image"]["path"]).is_file())
        ep = pl.generate_refs_batch(store, ep)
        okc = sum(1 for s in ep.scenes if (s.get("reference_image") or {}).get("status") == "ok")
        check("all refs generated", okc == len(ep.scenes), f"{okc}/{len(ep.scenes)}")
        check("refs_batch_done set", ep.refs_batch_done is True)
        ep = pl.approve_stage(store, ep)
        check("advanced to scenes", ep.stage == "scenes")

        # --- SCENES (rough cut) ---
        ep = pl.generate_scenes(store, ep)
        rough = (ep.timeline or {}).get("rough_cut")
        check("rough cut assembled", bool(rough) and Path(rough).is_file())
        dur = media_duration(rough) if rough else 0
        want = sum(s.get("duration_s", 5) for s in ep.scenes)
        check("rough cut not collapsed (xfade)", dur > want * 0.6, f"{dur}s vs ~{want}s scripted")
        # idempotency: re-run must not re-charge
        spent_before = ep.spent_usd
        ep = pl.generate_scenes(store, ep)
        check("scenes re-run is idempotent ($0 delta)", abs(ep.spent_usd - spent_before) < 1e-6,
              f"{spent_before} -> {ep.spent_usd}")
        ep = pl.approve_stage(store, ep)
        check("advanced to audio", ep.stage == "audio")

        # --- AUDIO ---
        ep = pl.generate_audio(store, ep)
        acut = (ep.timeline or {}).get("audio_cut")
        check("audio cut assembled", bool(acut) and Path(acut).is_file())
        ep = pl.approve_stage(store, ep)
        check("advanced to assembly", ep.stage == "assembly")

        # --- ASSEMBLY ---
        ep = pl.run_stage(store, ep)
        final = (ep.timeline or {}).get("final_video")
        check("final video produced", bool(final) and Path(final).is_file())
        ep = pl.approve_stage(store, ep)
        check("advanced to done", ep.stage == "done")
    finally:
        try:
            eps.delete(ep.episode_id)
        except Exception:
            store.conn.execute("delete from episodes where episode_id=?", (ep.episode_id,)); store.conn.commit()
        shutil.rmtree(_OUT, ignore_errors=True)

    print("\n" + ("ALL PASS ✅" if not _fails else f"FAILED ❌  ({len(_fails)}): " + ", ".join(_fails)))
    return 0 if not _fails else 1


if __name__ == "__main__":
    sys.exit(main())
