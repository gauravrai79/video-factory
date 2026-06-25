# Kling prompting — ecommerce apparel image-to-video (default route)

Harvested from OpenMontage `skills/creative/prompting` + `ai-video-gen`. Kling 3.0 Pro is the default
for apparel: strong multi-angle subject consistency, 1080p, lowest per-second cost in its tier, and
failed tasks don't consume credits.

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
