"""Background runner for the paid, multi-asset episode stages (refs batch, scenes, audio).

These stages generate many assets (16 images, N clips, N voices) over minutes. Running them inline
would block the HTTP request and hide progress behind a single spinner. Instead we run them in a
daemon thread that persists the episode after each asset, so the UI can poll GET /api/episodes/{id}
and watch the grid fill in one-by-one. One job per episode at a time.
"""

from __future__ import annotations

import threading
from typing import Any

from . import episode_pipeline as pl
from .episodes import EpisodeStore, StageStatus
from .jobstore import JobStore

_lock = threading.Lock()
_running: set[str] = set()


def is_running(episode_id: str) -> bool:
    with _lock:
        return episode_id in _running


def start(episode_id: str, fn_name: str, **kwargs: Any) -> bool:
    """Run pl.<fn_name>(store, ep, **kwargs) in the background. Returns False if one is already
    running for this episode. Marks the stage `generating` up-front so the first poll shows it."""
    with _lock:
        if episode_id in _running:
            return False
        _running.add(episode_id)

    # mark generating synchronously so the caller's immediate response already shows it
    try:
        es0 = EpisodeStore(JobStore())
        ep0 = es0.get(episode_id)
        if ep0:
            ep0.stage_status = StageStatus.GENERATING.value
            ep0.stage_error = ""
            es0.update(ep0)
    except Exception:
        pass

    def _work() -> None:
        try:
            store = JobStore()
            es = EpisodeStore(store)
            ep = es.get(episode_id)
            if not ep:
                return
            getattr(pl, fn_name)(store, ep, **kwargs)
        except Exception as e:  # noqa: BLE001 — surface any failure as a stage error, don't crash the thread
            try:
                store = JobStore()
                es = EpisodeStore(store)
                ep = es.get(episode_id)
                if ep:
                    ep.stage_status = StageStatus.PENDING.value
                    ep.stage_error = str(e)[:200]
                    ep.log("stage_error", {"error": str(e)[:200]})
                    es.update(ep)
            except Exception:
                pass
        finally:
            with _lock:
                _running.discard(episode_id)

    threading.Thread(target=_work, daemon=True, name=f"episode-{episode_id[:8]}").start()
    return True
