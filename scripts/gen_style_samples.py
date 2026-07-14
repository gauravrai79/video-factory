"""Generate the shared art-style sample gallery — the SAME mascot rendered in every style so the
channel-wizard picker is visual and directly comparable. Run once; commits ~30 small JPGs to
frontend/assets/styles/. Re-run with --force to overwrite, or --only <id,id> for specific styles.

    python scripts/gen_style_samples.py
    python scripts/gen_style_samples.py --only pixel_art,ukiyoe --force
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv(".env")

from backend.capabilities import or_image
from backend.finishing import FFMPEG
from backend.styles import ART_STYLES, SAMPLE_SUBJECT

OUT = Path("frontend/assets/styles")
OUT.mkdir(parents=True, exist_ok=True)


def _downscale(src: Path, dst: Path, size: int = 512) -> bool:
    """Square-crop + downscale to keep the committed gallery small."""
    cmd = [FFMPEG, "-y", "-i", str(src),
           "-vf", f"scale={size}:{size}:force_original_aspect_ratio=increase,crop={size}:{size}",
           "-q:v", "5", str(dst)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def main() -> int:
    force = "--force" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    spent = 0.0
    done = 0
    for st in ART_STYLES:
        if only and st["id"] not in only:
            continue
        final = OUT / f"{st['id']}.jpg"
        if final.exists() and not force:
            print(f"  skip {st['id']} (exists)")
            continue
        prompt = f"Art style: {st['prompt']}. {SAMPLE_SUBJECT}. No text or watermark."
        tmp = OUT / f"_{st['id']}.png"
        res = or_image.generate_still(prompt=prompt, output_path=str(tmp), model="gemini-flash",
                                      aspect_ratio="1:1", execute=True)
        spent += res.cost_usd
        if not res.success or not tmp.exists():
            print(f"  FAIL {st['id']}: {res.error}")
            continue
        ok = _downscale(tmp, final)
        tmp.unlink(missing_ok=True)
        print(f"  {'ok ' if ok else 'DL-FAIL'} {st['id']}  (${res.cost_usd})")
        done += ok
    print(f"\n{done} samples generated, ~${round(spent, 2)} spent -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
