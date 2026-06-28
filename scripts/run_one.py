"""Run one post end-to-end for a character.

  # Dry run (plan + price, no paid calls):
  python scripts/run_one.py --character samples/luna.json --brief "beach day" --tags travel,glamour

  # Real generation (needs FAL_KEY):
  python scripts/run_one.py --character samples/luna.json --brief "beach day" --tags travel,glamour --execute

Announces the planned storyboard + cost before any paid call.
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

from backend.agents.storyboard import plan_storyboard       # noqa: E402
from backend.characters import CharacterStore               # noqa: E402
from backend.jobstore import JobStore                       # noqa: E402
from backend.pipeline import create_job, execute_job, summarize  # noqa: E402
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True, help="Path to a character JSON (see samples/).")
    ap.add_argument("--brief", default="", help="Content brief, e.g. 'beach day'.")
    ap.add_argument("--format", default="reel", help="reel | square | longform")
    ap.add_argument("--tags", default="", help="Comma-separated scene tags, e.g. travel,glamour.")
    ap.add_argument("--shots", type=int, default=6)
    ap.add_argument("--video-budget", type=int, default=2, help="Max paid video shots; rest are Ken Burns.")
    ap.add_argument("--execute", action="store_true", help="Make the real (paid) fal.ai calls.")
    args = ap.parse_args()

    tenant = os.environ.get("VF_TENANT_ID", "factory")
    project = os.environ.get("VF_PROJECT", "influencer-factory")
    store = JobStore()
    char = _load_character(store, args.character)
    spec = get_spec(args.format)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    sb = plan_storyboard(char, brief=args.brief, fmt=args.format, tags=tags,
                         n_shots=args.shots, video_budget=args.video_budget,
                         refine=args.execute)
    print("=" * 72)
    print(f"Character : {char.name} ({char.slug})  refs: {len(char.reference_images)}")
    print(f"Post      : {sb.slug}   format={sb.format}  spec={spec.name} {spec.width}x{spec.height}")
    print(f"Shots     : {len(sb.shots)}  (~{sb.total_duration_s}s)   est ${sb.est_cost_usd}")
    for s in sb.shots:
        print(f"   [{s.seq}] {s.template_key:<14} {s.render_mode:<9} {s.duration_s}s  ${s.est_cost_usd}")
    print("=" * 72)
    print(">>> EXECUTE (paid)" if args.execute else ">>> DRY RUN (no paid call)")

    job, _ = create_job(store, char, sb, tenant_id=tenant, project=project, spec=spec,
                        execute=args.execute)
    execute_job(store, job, deliver=True)
    print(json.dumps(summarize(job, store), indent=2))
    return 0 if store.get(job.job_id).state.value != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
