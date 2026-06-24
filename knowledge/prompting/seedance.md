# Seedance 2.0 prompting — hero SKUs / difficult prints (fallback route)

Harvested from OpenMontage `skills/creative/prompting/seedance-prompting.md` + `seedance-2-0`. Reserve
Seedance for high-value SKUs, difficult prints, or when multiple seller angles exist — it costs more
and caps at 720p on fal, so it is not the default path.

## When routed here
- `row.hero == true` (premium/hero SKU), or
- difficult print (pattern not solid/plain), or
- multiple reference images available (multi-angle garment fidelity).

## Reference-to-video
Accepts up to **9 reference images** in one call — pass the seller's front/back/side angles as
`reference_image_urls` to anchor garment identity and pattern fidelity across the rotation.

## Structure
Same 5-aspect spec as Kling, plus:
- Emphasize **pattern/print fidelity** explicitly (the reason Seedance was chosen).
- Director-level camera control is available but keep it restrained for catalog consistency.

## Parameters
- `operation=reference_to_video` (multi-image) or `image_to_video` (single), `model_variant=standard`,
  `resolution=720p`, `generate_audio=false`. Secondary aggregator: Replicate (`seedance_replicate`).
