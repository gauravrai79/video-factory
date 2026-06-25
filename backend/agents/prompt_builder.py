"""Prompt-Builder — the reshoot-rate cost lever.

Turns an FSN manifest row into an optimized image-to-video prompt + model routing. Grounded in the
Kling/Seedance prompting structure harvested from OpenMontage (subject · subject motion · scene ·
framing · camera), tuned for ecommerce apparel where the deliverable must preserve garment fidelity
while adding controlled motion (front/back/rotation).

Deterministic by default (verified, no key needed). With VF_USE_LLM=1 + a configured key it refines
the prompt via Google ADK (Gemini) — the Spine-standard agent path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..ingest import SkuRow
from ..spec import OutputSpec


@dataclass
class PromptPlan:
    prompt: str
    model: str                 # "kling" | "seedance"
    model_variant: str
    duration: str
    aspect_ratio: str
    operation: str             # "image_to_video" | "reference_to_video"
    route_reason: str
    reference_image_urls: list[str] = field(default_factory=list)
    llm_refined: bool = False


# Negative/guard language baked in to protect garment fidelity and SOW rules.
_GUARD = (
    "Keep the garment shape, color, pattern, and proportions exactly faithful to the reference. "
    "No added logos, no text, no extra people, no distortion of fabric or print. Natural human "
    "proportions and motion."
)


_KLING_TIER_VARIANT = {"standard": "v2.1/standard", "pro": "v2.1/pro", "master": "v2.1/master"}


def kling_default_variant() -> str:
    """The Kling tier used for the volume default. Standard is the cost-smart choice for catalog
    SKUs (~43% cheaper than Pro at 20K/mo); set VF_KLING_TIER=pro|master to upgrade globally.
    Hero / difficult-print SKUs escalate to Seedance regardless (see route())."""
    tier = os.environ.get("VF_KLING_TIER", "standard").lower()
    return _KLING_TIER_VARIANT.get(tier, "v2.1/standard")


def route(row: SkuRow) -> tuple[str, str, str]:
    """Pick model + variant. Kling Standard is the volume default; Seedance for hero SKUs /
    difficult prints / multi-angle where garment fidelity justifies the higher cost."""
    if row.hero or row.is_difficult_print or len(row.image_urls) > 1:
        why = ("hero SKU" if row.hero else
               "difficult print" if row.is_difficult_print else
               "multiple seller angles available")
        return "seedance", "standard", f"Seedance 2.0 ({why}) for garment fidelity"
    variant = kling_default_variant()
    tier = variant.split("/")[-1]
    return "kling", variant, f"Kling 2.1 {tier} (volume default; escalate to Seedance for hero/difficult prints)"


def resolve_route(row: SkuRow, force_model: str | None = None) -> tuple[str, str, str]:
    """Routing with an optional manual override (ops can pin a model, e.g. to cap cost)."""
    if force_model:
        if force_model == "kling":
            return "kling", kling_default_variant(), "manual override -> kling"
        if force_model == "seedance":
            return "seedance", "standard", "manual override -> seedance"
        raise ValueError(f"force_model must be 'kling' or 'seedance', got {force_model!r}")
    return route(row)


def _deterministic_prompt(row: SkuRow) -> str:
    subject_bits = [b for b in [row.color, row.pattern, row.category or "apparel item", row.title] if b]
    subject = ", ".join(dict.fromkeys(subject_bits)) or "apparel product"
    usp = f" Highlight: {', '.join(row.usps[:3])}." if row.usps else ""
    return (
        f"Product showcase of {subject} on a clean studio background. "
        f"Subtle, smooth motion: slow turntable rotation revealing front, side, and back; "
        f"gentle natural fabric movement; soft catalog lighting. "
        f"Locked tripod feel with a slow controlled push-in. Premium ecommerce look.{usp} "
        f"{_GUARD}"
    )


def _llm_refine(base_prompt: str, row: SkuRow) -> tuple[str, bool]:
    """Optional ADK/Gemini refinement. Returns (prompt, refined?). Never raises into the pipeline."""
    if os.environ.get("VF_USE_LLM", "0") != "1":
        return base_prompt, False
    try:
        from google.adk.agents import LlmAgent          # type: ignore
        from google.adk.runners import InMemoryRunner    # type: ignore
        from google.genai import types                    # type: ignore

        model = os.environ.get("VF_AGENT_MODEL", "gemini-2.0-flash")
        agent = LlmAgent(
            name="prompt_builder",
            model=model,
            instruction=(
                "You are an expert ecommerce image-to-video prompt engineer. Improve the given prompt "
                "for an apparel product clip. Preserve garment fidelity, add only controlled motion "
                "(rotation/fabric), no logos/text/extra people. Return ONLY the improved prompt."
            ),
        )
        runner = InMemoryRunner(agent=agent, app_name="video_factory")
        import asyncio

        async def _run() -> str:
            session = await runner.session_service.create_session(
                app_name="video_factory", user_id="vf")
            msg = types.Content(role="user", parts=[types.Part(text=base_prompt)])
            out = ""
            async for ev in runner.run_async(user_id="vf", session_id=session.id, new_message=msg):
                if ev.content and ev.content.parts:
                    for p in ev.content.parts:
                        if getattr(p, "text", None):
                            out += p.text
            return out.strip()

        refined = asyncio.run(_run())
        return (refined or base_prompt), bool(refined)
    except Exception:
        # ADK not configured / network down — deterministic prompt is the contract.
        return base_prompt, False


def _plan_for(model: str, variant: str, reason: str, row: SkuRow, spec: OutputSpec,
              prompt: str, refined: bool) -> PromptPlan:
    # Generate slightly longer than the spec max so finishing can clamp cleanly into the band.
    gen_duration = str(int(round(spec.max_duration_s)))
    operation = "reference_to_video" if (model == "seedance" and len(row.image_urls) > 1) else "image_to_video"
    return PromptPlan(
        prompt=prompt,
        model=model,
        model_variant=variant,
        duration=gen_duration,
        aspect_ratio=spec.aspect_ratio,
        operation=operation,
        route_reason=reason,
        reference_image_urls=row.image_urls if operation == "reference_to_video" else [],
        llm_refined=refined,
    )


def build_prompt(row: SkuRow, spec: OutputSpec, force_model: str | None = None) -> PromptPlan:
    model, variant, reason = resolve_route(row, force_model)
    base = _deterministic_prompt(row)
    prompt, refined = _llm_refine(base, row)
    return _plan_for(model, variant, reason, row, spec, prompt, refined)


def fallback_plan(plan: PromptPlan, row: SkuRow, spec: OutputSpec) -> PromptPlan | None:
    """The alternate-model plan used when the primary model fails (AOP on_failure: fallback_model).
    Kling -> Seedance (reference fidelity for the retry); Seedance -> Kling (cheaper, still capable).
    Reuses the already-built prompt; only the model/variant/operation change."""
    if plan.model == "kling":
        return _plan_for("seedance", "standard",
                         "Seedance 2.0 fallback after Kling failure (reference fidelity)",
                         row, spec, plan.prompt, plan.llm_refined)
    if plan.model == "seedance":
        return _plan_for("kling", kling_default_variant(),
                         "Kling fallback after Seedance failure",
                         row, spec, plan.prompt, plan.llm_refined)
    return None
