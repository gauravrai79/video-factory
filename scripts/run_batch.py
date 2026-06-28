"""Content-calendar batch — generate N posts for a character, queue them, drain.

  # Dry run a week of posts (no paid calls) + show the SLA view:
  python scripts/run_batch.py --character samples/luna.json --posts 7 --tags travel,glamour --sla

  # Enqueue only (for an external RQ worker to drain):
  VF_QUEUE_BACKEND=rq python scripts/run_batch.py --character samples/luna.json --posts 7 --enqueue-only

  # Real generation across the batch (needs FAL_KEY):
  python scripts/run_batch.py --character samples/luna.json --posts 7 --tags travel,glamour --execute

  # Inspect SLA without creating anything new:
  python scripts/run_batch.py --sla-only

Idempotent: re-running the same briefs reuses existing posts instead of re-billing (see create_job).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backend import sla as sla_mod                          # noqa: E402
from backend.agents.storyboard import plan_storyboard       # noqa: E402
from backend.characters import CharacterStore               # noqa: E402
from backend.jobqueue import get_queue                      # noqa: E402
from backend.jobstore import JobStore                       # noqa: E402
from backend.pipeline import cost_ceiling_usd, create_job   # noqa: E402
from backend.spec import get_spec                            # noqa: E402


def _load_character(store: JobStore, path: str):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    spec = {k: v for k, v in spec.items() if not k.startswith("_")}
    cs = CharacterStore(store)
    tenant = os.environ.get("VF_TENANT_ID", "factory")
    existing = cs.get_by_slug(tenant, spec.get("slug", spec["name"].lower()))
    if existing:
        return existing
    name = spec.pop("name")
    slug = spec.pop("slug", name.lower())
    return cs.create(tenant_id=tenant, name=name, slug=slug, **spec)


def _print_sla(store: JobStore, tenant_id: str) -> None:
    rows = sla_mod.evaluate(store, tenant_id=tenant_id)
    if not rows:
        print("  (no posts)")
        return
    print(f"  {'SLUG':<28} {'TIER':<8} {'STATE':<11} {'ELAPSED':>9} {'BUDGET':>8}  SLA")
    for s in rows:
        flag = "BREACH" if s.breached else ("done" if s.terminal else "ok")
        print(f"  {s.slug[:27]:<28} {s.tier:<8} {s.state:<11} {s.elapsed_s:>8.0f}s {s.budget_s:>7.0f}s  {flag}")
    print(f"  -> {len(rows)} posts, {sum(1 for s in rows if s.breached)} breaching SLA")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", help="Path to a character JSON (see samples/).")
    ap.add_argument("--posts", type=int, default=3, help="How many posts to plan.")
    ap.add_argument("--brief", default="daily content", help="Base brief; a #n suffix is added per post.")
    ap.add_argument("--format", default="reel")
    ap.add_argument("--tags", default="", help="Comma-separated scene tags.")
    ap.add_argument("--shots", type=int, default=6)
    ap.add_argument("--video-budget", type=int, default=2)
    ap.add_argument("--execute", action="store_true", help="Make real (paid) fal.ai calls.")
    ap.add_argument("--enqueue-only", action="store_true", help="Create + enqueue but don't drain.")
    ap.add_argument("--no-dedupe", action="store_true")
    ap.add_argument("--sla", action="store_true", help="Print the SLA view after the run.")
    ap.add_argument("--sla-only", action="store_true", help="Just print SLA for existing posts.")
    args = ap.parse_args()

    tenant_id = os.environ.get("VF_TENANT_ID", "factory")
    project = os.environ.get("VF_PROJECT", "influencer-factory")
    store = JobStore()

    if args.sla_only:
        print("SLA STATUS")
        _print_sla(store, tenant_id)
        return 0
    if not args.character:
        print("--character is required (or use --sla-only)", file=sys.stderr)
        return 1

    char = _load_character(store, args.character)
    spec = get_spec(args.format)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    queue = get_queue(deliver=True)

    print("=" * 72)
    print(f"CALENDAR  {char.name} ({char.slug})  spec={spec.name}  queue={queue.name}  "
          f"mode={'EXECUTE (paid)' if args.execute else 'DRY RUN'}")
    print(f"Posts: {args.posts}   cost ceiling/post: ${cost_ceiling_usd():.2f}")
    print("-" * 72)

    created, reused, est_total = 0, 0, 0.0
    for i in range(args.posts):
        sb = plan_storyboard(char, brief=f"{args.brief} #{i + 1}", fmt=args.format, tags=tags,
                             n_shots=args.shots, video_budget=args.video_budget, refine=args.execute)
        job, is_new = create_job(store, char, sb, tenant_id=tenant_id, project=project, spec=spec,
                                 execute=args.execute, dedupe=not args.no_dedupe)
        est_total += float(job.payload.get("est_cost_usd", 0.0))
        print(f"  {sb.slug[:34]:<35} pri={job.payload.get('priority'):>3}  "
              f"${job.payload.get('est_cost_usd'):<6.3f} [{'new' if is_new else 'reused'}]")
        if is_new:
            created += 1
            queue.enqueue(job.job_id, priority=int(job.payload.get("priority", 0)))
        else:
            reused += 1

    print("-" * 72)
    print(f"Created {created}, reused {reused}.  Est. spend: ${est_total:.2f}")
    print(f"Queue depth: {queue.depth()}")

    if args.enqueue_only or not queue.is_inline():
        print(">>> Enqueued. " + ("Run a worker: python scripts/worker.py"
                                  if not queue.is_inline() else "Skipping drain (--enqueue-only)."))
    else:
        print(">>> Draining queue inline (sync backend)...")
        by_state: dict[str, int] = {}
        for s in queue.drain():
            by_state[s["state"]] = by_state.get(s["state"], 0) + 1
        print("  Results by state: " + json.dumps(by_state))

    if args.sla:
        print("-" * 72)
        print("SLA STATUS")
        _print_sla(store, tenant_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
