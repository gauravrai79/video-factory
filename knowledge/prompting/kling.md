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
- `operation=image_to_video`, `model_variant=v2.1/pro`, `duration` ≈ spec max (finishing clamps down),
  `aspect_ratio` from the spec (4:3 for 960×720).
- **Audio off** — music added in finishing.
