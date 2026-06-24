# SOW output spec — finishing contract

**OPEN ITEM (Phase 0): lock the output spec with the client before building finishing further.**

| Source | Dimensions | Size | Duration |
|---|---|---|---|
| SOW (written) | 960×720 / 720p | ≤ 10 MB | 10–12 s |
| Delivered sample | 1080×1920 | 17 MB | 13 s |

Both are encoded as presets in [`backend/spec.py`](../backend/spec.py); select via `VF_SPEC_PRESET`.
Default = `sow_written`.

## Finishing mandates (deterministic, FFmpeg)
- Enforce exact dimensions — scale-to-fit + pad (never crop the product).
- Clamp duration into the band. A too-short generation is a QC violation, never stretched.
- Two-pass encode to land inside the size band.
- Burn the **"Synthetically Generated"** watermark, bottom-center, clear of product.
- Overlay callout supers (USPs) on a schedule.
- Mux non-copyrighted background music. **Generation runs audio-off**; music is added here.
- End-frame rule: final frame loops to the opening shot, no logos. *(Phase 2 refinement.)*

## QC parameters (13) — tiers
- **Auto-checkable:** dimensions, duration, file size, watermark presence, supers spell-check,
  font/color validation, color ΔE vs reference SKU; VLM-assisted: multiple models, missing garment,
  logo distortion.
- **Human gate:** pattern fidelity, garment construction, plus-size representation, inhuman motion.
  Routes to the Spine Approvals queue (the review UI).
