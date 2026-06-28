"""Shot prompt builder — turns a character + a scene beat into generation prompts.

Every shot needs a *still* prompt (generate the character in the scene, identity locked to the
reference images) and, when the shot is animated by a paid video model, a *motion* prompt (what
moves: camera + action). The character's look descriptor is injected automatically so the persona
carries through without manual prompting.

Deterministic by default. With VF_USE_LLM=1 + a configured key it refines the still prompt via
Gemini (ADK); it degrades silently to the deterministic prompt on any failure.
"""

from __future__ import annotations

import os

from ..characters import Character
from ..scene_library import SceneTemplate

# Guard language: photoreal, single consistent subject, no captions/watermarks baked in by the model
# (we add any supers deterministically in finishing).
_GUARD = (
    "Photorealistic, natural human proportions and skin, consistent identity matching the reference. "
    "No added text, captions, logos, or watermarks; no extra people unless described."
)


def still_prompt(char: Character, scene: SceneTemplate, *, clothing: str = "") -> str:
    """Prompt for the base still: the character, in the scene, identity-locked."""
    look = char.look_descriptor()
    persona = char.persona or {}
    wear = clothing or scene.clothing_hint or persona.get("clothing_style", "")
    wear_bit = f" wearing {wear}" if wear else ""
    subject = look if char.species == "person" else (persona.get("appearance") or char.dna_prompt or look)
    return (
        f"{subject}{wear_bit}, in {scene.environment}. "
        f"{scene.mood} mood, {scene.lighting}. "
        f"Shot on a high-end camera, shallow depth of field, editorial quality. {_GUARD}"
    )


def motion_prompt(char: Character, scene: SceneTemplate) -> str:
    """Prompt for image-to-video: keep the subject, add the scene's camera/action motion."""
    subject = char.name if char.species == "person" else f"the {char.persona.get('appearance', 'animal') or 'animal'}"
    return (
        f"{subject} in {scene.environment}. Camera: {scene.camera}. "
        f"Subtle, natural motion; {scene.mood} mood. Keep identity and clothing consistent, "
        f"smooth realistic movement, no warping or morphing."
    )


def refine_still_prompt(base_prompt: str) -> tuple[str, bool]:
    """Optional ADK/Gemini refinement of a still prompt. Returns (prompt, refined?). Never raises."""
    if os.environ.get("VF_USE_LLM", "0") != "1":
        return base_prompt, False
    try:
        from google.adk.agents import LlmAgent          # type: ignore
        from google.adk.runners import InMemoryRunner    # type: ignore
        from google.genai import types                    # type: ignore

        model = os.environ.get("VF_AGENT_MODEL", "gemini-2.0-flash")
        agent = LlmAgent(
            name="shot_prompt_builder",
            model=model,
            instruction=(
                "You are an expert photo/video prompt engineer for AI influencer content. Improve the "
                "given prompt for a photorealistic shot of a consistent character. Preserve identity, "
                "keep it tasteful and platform-safe, no text/logos/extra people. Return ONLY the prompt."
            ),
        )
        runner = InMemoryRunner(agent=agent, app_name="influencer_factory")
        import asyncio

        async def _run() -> str:
            session = await runner.session_service.create_session(
                app_name="influencer_factory", user_id="vf")
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
        return base_prompt, False
