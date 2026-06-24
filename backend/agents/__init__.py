"""ADK agents (Spine standard). Prompt-Builder today; QC-flagger and Rework next.

Each agent has a deterministic fallback so the pipeline runs without an LLM key, and uses Google ADK
(Gemini) when VF_USE_LLM=1 and a key is configured — the same per-project LLM model Report Factory
uses (ADK_PROVIDER / model env).
"""
