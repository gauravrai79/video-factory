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


def unit_checks() -> None:
    """Pure-function checks for the keyframe linter / frozen-beat fallback / transition splicer."""
    from backend.agents.writer import lint_keyframe, freeze_beat, _location_id
    from backend import transitions as tr
    from backend.finishing import ScoredShot

    check("lint flags motion words", bool(lint_keyframe("the tiffin tumbles mid-air, spilling rotis")))
    check("lint passes a frozen beat", not lint_keyframe(
        "a rider sits on a red scooter beside a shallow pothole; a steel tiffin rests on the rack"))
    frozen = freeze_beat("Jango sits by the pothole, the tiffin tumbles mid-air spilling rotis, dust settles")
    check("freeze_beat strips motion clauses", not lint_keyframe(frozen) and "Jango sits" in frozen)
    check("location_id derivation", _location_id("Market Street - Morning") == "market_street")

    # splicer: hard-cut default, transition only on location change with mapped+available kind,
    # never more than ceil(n/3), min 3 cuts between
    tmp = Path(tempfile.mkdtemp(prefix="vf_tr_"))
    clip = tmp / "t.mp4"
    clip.write_bytes(b"0")
    class _Ch:                                    # minimal channel stand-in
        transitions = [{"id": "x", "kind": "comic_slam", "path": str(clip)}]
    scenes = []
    for i in range(9):                            # location changes every scene, all 'reveal'
        scenes.append({"heading": f"Loc{i} - Day", "location_id": f"loc{i}", "beat_type": "reveal",
                       "time_jump": False})
    shots = [ScoredShot("video", "v.mp4", 4) for _ in scenes]
    out = tr.interleave(shots, scenes, _Ch())
    inserted = len(out) - len(shots)
    check("splicer caps + spaces transitions", 0 < inserted <= 3, f"inserted={inserted} (want 1..3)")
    same_loc = [dict(s, location_id="same") for s in scenes]
    out2 = tr.interleave(shots, same_loc, _Ch())
    check("no transition inside a continuous location", len(out2) == len(shots))
    out3 = tr.interleave(shots, same_loc, _Ch(), overrides={"2": "comic_slam", "5": "none"})
    check("seam override forces a transition", len(out3) == len(shots) + 1)
    out4 = tr.interleave(shots, scenes, _Ch(), overrides={str(i): "none" for i in range(1, 9)})
    check("seam override 'none' silences all seams", len(out4) == len(shots))
    shutil.rmtree(tmp, ignore_errors=True)

    # script QC: weighted composite + intent attachment
    from backend.agents.script_qc import composite, attach_intents
    check("qc composite full marks = 100", composite({k: 10 for k in ("hook", "narrative", "ending", "comedy", "virality")}) == 100.0)
    check("qc composite weights narrative highest",
          composite({"narrative": 10}) > composite({"hook": 10}) > composite({"ending": 0, "comedy": 10}))
    sc = [{"seq": 0}, {"seq": 1}]
    attach_intents(sc, [{"seq": 1, "purpose": "reveal", "must_show": ["ledger"], "mood": "tense"}])
    check("intents attach to the right scene", "intent" not in sc[0] and sc[1]["intent"]["must_show"] == ["ledger"])

    # format config: portrait vs landscape spec + aspect + scene-count derivation + presets
    from backend import formats
    from backend.episodes import Episode
    class _C:                                          # minimal channel stand-in
        target_duration_s = 120; target_scene_count = 0; language = "Hindi"
        def is_short(self): return False
    land = Episode(episode_id="x", channel_id="c", number=1, config={"layout": "landscape", "resolution": "1080p", "configured": True})
    port = Episode(episode_id="y", channel_id="c", number=1, config={"layout": "portrait", "resolution": "720p", "configured": True})
    ls, ps = formats.episode_spec(land, _C()), formats.episode_spec(port, _C())
    check("landscape spec 1920x1080", (ls.width, ls.height) == (1920, 1080))
    check("portrait spec 720x1280", (ps.width, ps.height) == (720, 1280))
    check("veo aspect portrait 9:16", formats.veo_aspect("portrait") == "9:16" and formats.veo_aspect("landscape") == "16:9")
    check("portrait framing hint is vertical", "9:16" in formats.framing_hint({"layout": "portrait"}))
    check("scene count derived from length", formats.default_scene_count(120) == 20 and formats.default_scene_count(30) == 5)
    check("presets include youtube + reel", {"youtube_long", "instagram_reel"} <= set(formats.PLATFORM_PRESETS))
    check("config back-compat for un-configured episode", formats.episode_config(Episode(episode_id="z", channel_id="c", number=1), _C())["layout"] == "landscape")

    # art-style library + concept assistant (stub) + sample assets present
    from backend import styles as style_lib
    from backend.agents import concept
    check("style library has 25+ styles", len(style_lib.ART_STYLES) >= 25)
    check("style ids unique", len({s["id"] for s in style_lib.ART_STYLES}) == len(style_lib.ART_STYLES))
    check("prompt_for resolves id -> prompt", "comic" in style_lib.prompt_for("comic_cinematic").lower()
          and style_lib.prompt_for("free text look") == "free text look")
    samples = Path("frontend/assets/styles")
    missing = [s["id"] for s in style_lib.ART_STYLES if not (samples / f"{s['id']}.jpg").is_file()]
    check("every style has a sample image", not missing, f"missing: {missing[:5]}")
    cd = concept.draft_concept("a detective dog in Mumbai")
    check("concept stub returns full scaffold", cd.ok and cd.data.get("premise") and cd.data.get("style_ids"))


def main() -> int:
    unit_checks()
    store = JobStore()
    eps, chs = EpisodeStore(store), ChannelStore(store)
    ch = next((c for c in chs.list(TENANT) if c.cast_ids()), None)
    if not ch:
        print("no channel with cast — cannot run e2e"); return 2
    print(f"channel: {ch.name}  (cast={len(ch.cast_ids())}, world={'set' if ch.world else 'none'})")

    ep = eps.create(tenant_id=TENANT, channel_id=ch.channel_id, title="__E2E_SMOKE__", cast=ch.cast_ids())
    try:
        # --- SETUP (step 0: format config) ---
        check("new episode starts at setup", ep.stage == "setup")
        ep = pl.configure(store, ep, {"layout": "portrait", "duration_s": 60, "scene_count": 4,
                                      "resolution": "720p", "music": True})
        check("config saved + advanced to idea", ep.stage == "idea" and ep.config.get("layout") == "portrait")

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

        # --- SCENES (individual clips only — NO stitching here) ---
        ep = pl.generate_scenes(store, ep)
        okc = sum(1 for s in ep.scenes if (s.get("clip") or {}).get("status") == "ok")
        check("all scene clips generated", okc == len(ep.scenes), f"{okc}/{len(ep.scenes)}")
        check("scenes stage does NOT stitch", not (ep.timeline or {}).get("rough_cut"))
        # subset regen: only the chosen scene, others untouched
        p0 = (ep.scenes[0].get("clip") or {}).get("path")
        ep = pl.generate_scenes(store, ep, seqs=[1])
        check("subset regen leaves others untouched", (ep.scenes[0].get("clip") or {}).get("path") == p0)
        # idempotency: full re-run must not re-charge
        spent_before = ep.spent_usd
        ep = pl.generate_scenes(store, ep)
        check("scenes re-run is idempotent ($0 delta)", abs(ep.spent_usd - spent_before) < 1e-6,
              f"{spent_before} -> {ep.spent_usd}")
        ep = pl.approve_stage(store, ep)
        check("advanced to audio", ep.stage == "audio")

        # --- AUDIO (optional music bed; skippable) ---
        ep = pl.generate_audio(store, ep)
        check("music bed generated", bool((ep.timeline or {}).get("music")))
        ep = pl.approve_stage(store, ep, payload={"skip_music": True})
        check("audio skippable (clips carry audio)", ep.stage == "assembly"
              and (ep.timeline or {}).get("music") is None)

        # --- ASSEMBLY (THE stitch: clips + transitions + loudnorm) ---
        ep = pl.run_stage(store, ep)
        final = (ep.timeline or {}).get("final_video")
        check("final video produced", bool(final) and Path(final).is_file())
        dur = media_duration(final) if final else 0
        want = sum(min(s.get("duration_s", 5), s.get("scripted_duration_s") or 99) for s in ep.scenes)
        check("final cut not collapsed", dur > want * 0.6, f"{dur}s vs ~{want}s")
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
