"""Episode stage orchestrator — runs a stage's generator, then holds at its human gate.

The token-safety model: `run_stage` generates the CURRENT stage's artifact and parks the episode at
`awaiting_review`; nothing advances until a human calls `approve` (which promotes the artifact and
moves to the next stage) or `reject` (back up) or edits the artifact in place. Every action is logged
to the episode history.

M2 implements the IDEA and SCRIPT stages (writers' room, text-only, cheap). REFS/SCENES/AUDIO/ASSEMBLY
are wired in later milestones and return a "not available yet" result.
"""

from __future__ import annotations

from typing import Any

from .agents import writer
from .channels import Channel, ChannelStore
from .characters import Character, CharacterStore
from .episodes import Episode, EpisodeStore, Stage, StageStatus, next_stage


class StageError(RuntimeError):
    pass


def _cast_chars(cs: CharacterStore, ep: Episode, ch: Channel) -> list[Character]:
    ids = ep.cast or ch.cast_ids()
    out = [cs.get(cid) for cid in ids]
    return [c for c in out if c]


def _ctx(store, ep: Episode) -> tuple[EpisodeStore, ChannelStore, CharacterStore, Channel, list[Character]]:
    eps, chs, cs = EpisodeStore(store), ChannelStore(store), CharacterStore(store)
    ch = chs.get(ep.channel_id)
    if not ch:
        raise StageError("channel not found for episode")
    return eps, chs, cs, ch, _cast_chars(cs, ep, ch)


# --------------------------------------------------------------------------- run (generate stage)

def run_stage(store, ep: Episode) -> Episode:
    """Generate the current stage's artifact and park at awaiting_review."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    ep.writer_model = ch.writer_model or writer.default_model()
    ep.stage_status = StageStatus.GENERATING.value
    ep.stage_error = ""
    eps.update(ep)

    stage = Stage(ep.stage)
    if stage == Stage.IDEA:
        recent = [e.title for e in eps.list(_tenant_of(ep, eps), ch.channel_id) if e.episode_id != ep.episode_id]
        res = writer.ideate(ch, cast, recent_titles=recent, model=ep.writer_model)
        if not res.ok:
            return _fail(eps, ep, res.error or "ideation failed")
        ep.idea_candidates = res.data["ideas"]
        _bill(ep, res)
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("ideate", {"n": len(ep.idea_candidates), "model": res.model, "stub": res.stubbed})

    elif stage == Stage.SCRIPT:
        if not ep.idea:
            return _fail(eps, ep, "approve an idea before scripting")
        res = writer.script(ch, cast, ep.idea, model=ep.writer_model)
        if not res.ok:
            return _fail(eps, ep, res.error or "scripting failed")
        ep.scenes = res.data["scenes"]
        _bill(ep, res)
        ep.stage_status = StageStatus.AWAITING_REVIEW.value
        ep.log("script", {"scenes": len(ep.scenes), "model": res.model, "stub": res.stubbed})

    else:
        return _fail(eps, ep, f"stage '{stage.value}' runs in a later milestone")

    return eps.update(ep)


# --------------------------------------------------------------------------- gate actions

def approve_stage(store, ep: Episode, *, payload: dict[str, Any] | None = None) -> Episode:
    """Approve the current stage's artifact and advance to the next stage (pending)."""
    eps, chs, cs, ch, cast = _ctx(store, ep)
    payload = payload or {}
    stage = Stage(ep.stage)

    if stage == Stage.IDEA:
        chosen = payload.get("idea")
        if chosen is None:
            idx = int(payload.get("choice", 0))
            if idx < 0 or idx >= len(ep.idea_candidates):
                raise StageError("choice out of range")
            chosen = ep.idea_candidates[idx]
        ep.idea = chosen
        ep.title = (chosen.get("title") or ep.title)
        ep.logline = chosen.get("logline", "")
        ep.log("idea_approved", {"title": ep.title})
    elif stage == Stage.SCRIPT:
        if payload.get("scenes"):                 # accept human-edited scenes
            ep.scenes = payload["scenes"]
        if not ep.scenes:
            raise StageError("no script to approve")
        ep.log("script_approved", {"scenes": len(ep.scenes)})
    else:
        raise StageError(f"stage '{stage.value}' cannot be approved yet")

    ep.stage = next_stage(stage).value
    ep.stage_status = StageStatus.PENDING.value
    ep.stage_error = ""
    return eps.update(ep)


def reject_stage(store, ep: Episode, *, reason: str = "") -> Episode:
    """Reject the current artifact — reset it to pending so it can be re-run."""
    eps = EpisodeStore(store)
    stage = Stage(ep.stage)
    if stage == Stage.IDEA:
        ep.idea_candidates = []
    elif stage == Stage.SCRIPT:
        ep.scenes = []
    ep.stage_status = StageStatus.PENDING.value
    ep.log("rejected", {"reason": reason or "rejected"})
    return eps.update(ep)


def edit_artifact(store, ep: Episode, *, idea: dict[str, Any] | None = None,
                  scenes: list[dict[str, Any]] | None = None) -> Episode:
    """Hand-edit the current artifact in place (the Edit gate action)."""
    eps = EpisodeStore(store)
    if idea is not None:
        ep.idea = idea
        ep.title = idea.get("title", ep.title)
        ep.log("idea_edited", {})
    if scenes is not None:
        ep.scenes = scenes
        ep.log("script_edited", {"scenes": len(scenes)})
    return eps.update(ep)


# --------------------------------------------------------------------------- helpers

def _fail(eps: EpisodeStore, ep: Episode, msg: str) -> Episode:
    ep.stage_status = StageStatus.PENDING.value
    ep.stage_error = msg
    ep.log("stage_error", {"error": msg})
    return eps.update(ep)


def _bill(ep: Episode, res) -> None:
    ep.spent_usd = round(ep.spent_usd + float(res.cost_usd or 0.0), 4)


def _tenant_of(ep: Episode, eps: EpisodeStore) -> str:
    row = eps.conn.execute("SELECT tenant_id FROM episodes WHERE episode_id=?",
                           (ep.episode_id,)).fetchone()
    return row["tenant_id"] if row else "factory"
