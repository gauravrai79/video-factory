"""Phase-1 vertical slice — run one SKU end-to-end.

  python scripts/run_one.py --csv samples/skus.csv --row 0              # dry run (no paid call)
  python scripts/run_one.py --csv samples/skus.csv --row 0 --execute    # real fal.ai generation
  python scripts/run_one.py --csv samples/skus.csv --row 0 --finish-stand-in path/to/clip.mp4

Announces the generation decision + cost before any paid call, per the governance contract.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make the repo importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backend.ingest import load_csv          # noqa: E402
from backend.jobstore import JobStore        # noqa: E402
from backend.pipeline import run_job, summarize  # noqa: E402
from backend.spec import get_spec            # noqa: E402
from backend.agents.prompt_builder import build_prompt  # noqa: E402
from backend.capabilities.cost import monthly_projection  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--row", type=int, default=0)
    ap.add_argument("--execute", action="store_true", help="Make the real (paid) fal.ai call.")
    ap.add_argument("--finish-stand-in", help="Local clip to finish in a dry run (proves finishing).")
    ap.add_argument("--music", help="Background music to mux in finishing.")
    ap.add_argument("--spec", help="Override VF_SPEC_PRESET (sow_written | sample).")
    ap.add_argument("--model", choices=["kling", "seedance"],
                    help="Pin the generation model (overrides auto-routing; disables fallback).")
    args = ap.parse_args()

    spec = get_spec(args.spec)
    rows = load_csv(args.csv)
    if not rows:
        print(f"No SKU rows in {args.csv}", file=sys.stderr)
        return 1
    if args.row >= len(rows):
        print(f"--row {args.row} out of range (have {len(rows)})", file=sys.stderr)
        return 1
    row = rows[args.row]

    # Announce the decision BEFORE any paid call (governance contract).
    plan = build_prompt(row, spec, force_model=args.model)
    print("=" * 72)
    print(f"SKU {row.fsn} - {row.title or row.category}")
    print(f"Spec preset : {spec.name}  ({spec.width}x{spec.height}, "
          f"{spec.min_duration_s}-{spec.max_duration_s}s, {spec.min_size_mb}-{spec.max_size_mb}MB)")
    print(f"Model route : {plan.model} / {plan.model_variant}  - {plan.route_reason}")
    print(f"Operation   : {plan.operation}   LLM-refined: {plan.llm_refined}")
    print(f"Prompt      : {plan.prompt}")
    print("-" * 72)
    print("Prompt-Builder is the reshoot-rate lever. Monthly projection at this route:")
    proj = monthly_projection(model=plan.model, model_variant=plan.model_variant,
                              duration_s=int(round(spec.target_duration_s)))
    print(f"  per-video ${proj['total_per_video_usd']}  |  20K/mo ${proj['total_monthly_usd']:,}")
    print("=" * 72)

    if args.execute:
        print(f">>> EXECUTE: calling {plan.model} on fal.ai (paid). FAL_KEY "
              f"{'present' if os.environ.get('FAL_KEY') else 'MISSING'}.")
    else:
        print(">>> DRY RUN: no paid call." +
              (f" Finishing stand-in clip: {args.finish_stand_in}" if args.finish_stand_in else ""))

    store = JobStore()
    job = run_job(store, row, tenant_id=os.environ.get("VF_TENANT_ID", "flipkart"),
                  project=os.environ.get("VF_PROJECT", "video-factory"), spec=spec,
                  execute=args.execute, music_path=args.music,
                  stand_in_clip=args.finish_stand_in, force_model=args.model)

    print(json.dumps(summarize(job, store), indent=2))
    return 0 if job.state.value not in ("failed",) else 2


if __name__ == "__main__":
    raise SystemExit(main())
