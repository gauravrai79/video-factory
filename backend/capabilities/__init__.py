"""Capability layer — fal.ai generation clients.

Plain clients for the fal.ai queue API (submit, poll, download): fal_image (character-consistent
stills) and fal_video (image-to-video). Pricing lives in pricing.py. The worker calls these directly;
the orchestrator governs *when* they run and audits the result.
"""
