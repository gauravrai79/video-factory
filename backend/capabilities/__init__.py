"""Capability layer — generation clients harvested from OpenMontage.

These are clean extractions of OpenMontage's fal.ai generation logic (tools/video/kling_video.py,
seedance_video.py) without the BaseTool framework — just the API call, polling, and download. The
factory's worker calls these directly; the AOP governs *when* they run and audits the result.
"""
