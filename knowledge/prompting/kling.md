# Kling prompting — ecommerce apparel image-to-video (default route)

Harvested from OpenMontage `skills/creative/prompting` + `ai-video-gen`. Kling is the default model
for clean catalog SKUs: strong multi-angle subject consistency, and failed tasks don't consume credits.

## Tier & cost (the biggest cost lever at 20K/month)
Kling 2.1 pricing on fal = base for the first 5s + a per-additional-second rate (a 10s clip is the
SOW target):

| Tier | first 5s | +per sec | **10s clip** |
|------|----------|----------|--------------|
| **standard** (default) | $0.28 | $0.056 | **$0.56** |
| pro | $0.49 | $0.098 | $0.98 |

**Standard is the volume default** (`VF_KLING_TIER=standard`) — ~43% cheaper than Pro, ~$8K/month
less at 20K. Pro buys marginal quality that rarely matters for a product-rotation clip. Reserve the
spend for fidelity where it counts: hero SKUs and difficult prints **escalate to Seedance**, not Kling
Pro (see `backend/agents/prompt_builder.py::route`). Set `VF_KLING_TIER=pro` only if QC reshoot rate
on Standard proves too high — measure first; generation cost dominates the P&L.

## Structure (5-aspect)
1. **Subject** — the garment, described from the reference (color, pattern, category, fit).
2. **Subject motion** — subtle: slow turntable rotation (front → side → back), gentle fabric movement.
3. **Scene** — clean studio / seamless background; premium ecommerce look.
4. **Framing** — full product in frame, centered, safe margins for watermark + supers.
5. **Camera** — locked tripod feel + slow controlled push-in; no whip pans.

## Guardrails (preserve garment fidelity — the reshoot lever)
- Keep shape, color, pattern, proportions exactly faithful to the reference.
- No added logos, no text, no extra people, no fabric/print distortion.
- Natural human proportions and motion (avoid the "inhuman motion" QC fail).

## Parameters
- `operation=image_to_video`, `model_variant=v2.1/pro`.
- `duration` — fal's Kling accepts ONLY `"5"` or `"10"` (string seconds). Any other value (e.g. `"12"`)
  → HTTP 422. `fal_video._kling_duration()` snaps to the allowed set; finishing clamps into the spec band.
- `aspect_ratio` — fal's Kling accepts ONLY `16:9 / 9:16 / 1:1`. The spec's `4:3` is NOT valid →
  `fal_video._kling_aspect()` maps to the nearest supported ratio; finishing scales + pads to the exact
  spec dimensions, so the generator only needs a valid frame.
- **Audio off** — music added in finishing.
