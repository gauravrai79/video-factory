"""Phase-2 batch orchestration — CSV -> N jobs -> queue -> drain.

  # Dry run the whole CSV through the queue (no paid calls), then print the SLA view:
  python scripts/run_batch.py --csv samples/skus.csv --sla

  # Enqueue only (e.g. for an external RQ worker to drain):
  VF_QUEUE_BACKEND=rq python scripts/run_batch.py --csv samples/skus.csv --enqueue-only

  # Real generation across the batch (announces total cost; needs FAL_KEY):
  python scripts/run_batch.py --csv samples/skus.csv --execute

  # Inspect SLA without enqueuing anything new:
  python scripts/run_batch.py --sla-only

Idempotent: re-running the same CSV reuses existing jobs instead of re-billing (see create_job).
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

from backend.ingest import load_csv               # noqa: E402
from backend.jobstore import JobStore             # noqa: E402
from backend.jobqueue import get_queue            # noqa: E402
from backend.pipeline import create_job, cost_ceiling_usd  # noqa: E402
from backend.spec import get_spec                 # noqa: E402
from backend import sla as sla_mod                 # noqa: E402


def _print_sla(store: JobStore, tenant_id: str) -> None:
    rows = sla_mod.evaluate(store, tenant_id=tenant_id)
    if not rows:
        print("  (no jobs)")
        return
    print(f"  {'FSN':<10} {'TIER':<8} {'STATE':<11} {'ELAPSED':>9} {'BUDGET':>8}  SLA")
    for s in rows:
        flag = "BREACH" if s.breached else ("done" if s.terminal else "ok")
        print(f"  {s.fsn:<10} {s.tier:<8} {s.state:<11} {s.elapsed_s:>8.0f}s {s.budget_s:>7.0f}s  {flag}")
    n_breach = sum(1 for s in rows if s.breached)
    print(f"  -> {len(rows)} jobs, {n_breach} breaching SLA")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="FSN manifest CSV to ingest.")
    ap.add_argument("--execute", action="store_true", help="Make real (paid) fal.ai calls.")
    ap.add_argument("--finish-stand-in", help="Local clip to finish for every dry-run job (demo).")
    ap.add_argument("--music", help="Background music muxed in finishing.")
    ap.add_argument("--spec", help="Override VF_SPEC_PRESET (sow_written | sample).")
    ap.add_argument("--enqueue-only", action="store_true",
                    help="Create + enqueue jobs but don't drain (for an external RQ worker).")
    ap.add_argument("--no-dedupe", action="store_true", help="Re-create jobs even if they exist.")
    ap.add_argument("--max", type=int, help="Cap number of CSV rows processed.")
    ap.add_argument("--sla", action="store_true", help="Print the SLA view after the run.")
    ap.add_argument("--sla-only", action="store_true", help="Just print SLA for existing jobs; no ingest.")
    args = ap.parse_args()

    tenant_id = os.environ.get("VF_TENANT_ID", "flipkart")
    project = os.environ.get("VF_PROJECT", "video-factory")
    store = JobStore()

    if args.sla_only:
        print("SLA STATUS")
        _print_sla(store, tenant_id)
        return 0

    if not args.csv:
        print("--csv is required (or use --sla-only)", file=sys.stderr)
        return 1

    spec = get_spec(args.spec)
    rows = load_csv(args.csv)
    if args.max:
        rows = rows[: args.max]
    if not rows:
        print(f"No SKU rows in {args.csv}", file=sys.stderr)
        return 1

    queue = get_queue(deliver=True)
    print("=" * 72)
    print(f"BATCH  tenant={tenant_id} project={project}  spec={spec.name}  "
          f"queue={queue.name}  mode={'EXECUTE (paid)' if args.execute else 'DRY RUN'}")
    print(f"Rows: {len(rows)}   cost ceiling/job: ${cost_ceiling_usd():.2f}")
    print("-" * 72)

    created, reused, est_total = 0, 0, 0.0
    for row in rows:
        job, is_new = create_job(
            store, row, tenant_id=tenant_id, project=project, spec=spec,
            execute=args.execute, music_path=args.music,
            stand_in_clip=args.finish_stand_in, dedupe=not args.no_dedupe,
        )
        est = float(job.payload.get("est_cost_usd", 0.0))
        est_total += est
        route = job.payload.get("route", {})
        tag = "new" if is_new else "reused"
        print(f"  {row.fsn:<10} pri={job.payload.get('priority'):>3}  "
              f"{route.get('model','?'):<9} ${est:<6.3f} [{tag}]")
        if is_new:
            created += 1
            queue.enqueue(job.job_id, priority=int(job.payload.get("priority", 0)))
        else:
            reused += 1

    print("-" * 72)
    print(f"Created {created}, reused {reused}.  Est. single-attempt generation: ${est_total:.2f}"
          f"  (monthly @20K ~ ${est_total / max(len(rows),1) * 20000:,.0f})")
    print(f"Queue depth: {queue.depth()}")

    if args.enqueue_only or not queue.is_inline():
        print(">>> Enqueued. " + ("Run a worker to drain: python scripts/worker.py"
                                  if not queue.is_inline() else "Skipping drain (--enqueue-only)."))
    else:
        print(">>> Draining queue inline (sync backend)...")
        summaries = queue.drain()
        by_state: dict[str, int] = {}
        for s in summaries:
            by_state[s["state"]] = by_state.get(s["state"], 0) + 1
        print("  Results by state: " + json.dumps(by_state))

    if args.sla or args.sla_only:
        print("-" * 72)
        print("SLA STATUS")
        _print_sla(store, tenant_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
