"""Art-style library — the visual looks a channel can pick from.

Each style has a stable `id`, a human `label`, the `prompt` fragment that gets injected as the
channel's `art_style` (and thus leads every visual prompt), and `tags` for grouping. A shared sample
image per style (same mascot rendered in every look) lives at frontend/assets/styles/{id}.jpg so the
picker is visual — see scripts/gen_style_samples.py.
"""
from __future__ import annotations

# The subject rendered identically across every style so the samples are directly comparable.
SAMPLE_SUBJECT = ("a friendly cartoon fox character mascot, upper-body three-quarter portrait, "
                  "confident happy expression, plain soft neutral studio background, centered")

ART_STYLES: list[dict] = [
    # --- comic / ink ---
    {"id": "comic_cinematic", "label": "Comic-book cinematic", "tags": ["comic"],
     "prompt": "Comic-book cinematic style — bold inked outlines, dramatic cel shading, rich "
               "saturated graphic-novel colors, high-contrast cinematic lighting"},
    {"id": "superhero_comic", "label": "Superhero comic", "tags": ["comic"],
     "prompt": "Classic American superhero comic-book style — bold ink linework, Ben-Day halftone "
               "dots, dynamic foreshortening, vivid primary colors"},
    {"id": "manga_bw", "label": "Manga (B&W)", "tags": ["comic", "anime"],
     "prompt": "Black-and-white manga style — clean screentones, expressive linework, dramatic "
               "speed lines, high contrast, no color"},
    {"id": "noir_ink", "label": "Noir ink", "tags": ["comic"],
     "prompt": "High-contrast noir ink style — heavy blacks, stark chiaroscuro lighting, moody "
               "shadows, limited desaturated palette, graphic-novel inking"},
    {"id": "graphic_novel_painted", "label": "Painted graphic novel", "tags": ["comic", "painterly"],
     "prompt": "Painted graphic-novel style — richly rendered digital painting with visible brush "
               "texture, cinematic lighting, mature illustrative detail"},
    # --- 3D / animation ---
    {"id": "pixar_3d", "label": "3D Pixar-style", "tags": ["3d"],
     "prompt": "Polished 3D animated feature style (Pixar/DreamWorks) — soft global illumination, "
               "appealing rounded character design, subsurface skin, cinematic depth of field"},
    {"id": "lowpoly_3d", "label": "Low-poly 3D", "tags": ["3d"],
     "prompt": "Stylized low-poly 3D render — faceted geometry, flat shaded facets, clean pastel "
               "palette, soft ambient occlusion"},
    {"id": "claymation", "label": "Claymation", "tags": ["3d", "craft"],
     "prompt": "Claymation stop-motion style — visible fingerprints in modeling clay, handcrafted "
               "sets, soft studio lighting, tactile plasticine texture"},
    {"id": "felt_puppet", "label": "Felt puppet", "tags": ["craft"],
     "prompt": "Handcrafted felt-and-fabric puppet style — soft stitched textures, button eyes, "
               "cozy diorama sets, warm soft lighting"},
    {"id": "papercut", "label": "Papercut collage", "tags": ["craft"],
     "prompt": "Layered papercut collage style — cut-paper shapes with soft drop shadows, textured "
               "construction paper, flat depth layers"},
    # --- anime ---
    {"id": "anime_modern", "label": "Anime cel (modern)", "tags": ["anime"],
     "prompt": "Modern anime cel-shaded style — clean crisp linework, flat cel shading with soft "
               "gradients, vibrant colors, expressive large eyes"},
    {"id": "ghibli_watercolor", "label": "Ghibli-esque watercolor", "tags": ["anime", "painterly"],
     "prompt": "Ghibli-esque hand-painted anime style — lush watercolor backgrounds, soft warm "
               "light, gentle nostalgic palette, delicate detail"},
    {"id": "retro_anime_90s", "label": "90s retro anime", "tags": ["anime", "retro"],
     "prompt": "1990s retro anime style — grainy cel animation look, muted film palette, hand-drawn "
               "linework, VHS-era softness"},
    # --- painterly ---
    {"id": "watercolor_storybook", "label": "Watercolor storybook", "tags": ["painterly"],
     "prompt": "Children's watercolor storybook style — soft washes, visible paper grain, gentle "
               "warm palette, loose expressive edges"},
    {"id": "oil_painting", "label": "Oil painting", "tags": ["painterly"],
     "prompt": "Classical oil painting style — rich impasto brushstrokes, warm chiaroscuro lighting, "
               "painterly canvas texture, old-master palette"},
    {"id": "gouache", "label": "Gouache illustration", "tags": ["painterly"],
     "prompt": "Gouache illustration style — matte opaque paint, bold flat shapes with painterly "
               "texture, warm mid-century palette"},
    {"id": "impressionist", "label": "Impressionist", "tags": ["painterly"],
     "prompt": "Impressionist painting style — loose visible dabs of color, soft diffused light, "
               "vibrant broken-color palette"},
    # --- vector / flat ---
    {"id": "flat_vector", "label": "Flat vector", "tags": ["vector"],
     "prompt": "Clean flat vector illustration — bold simple shapes, limited flat color palette, "
               "no gradients, crisp geometric design"},
    {"id": "minimal_line", "label": "Minimal line art", "tags": ["vector"],
     "prompt": "Minimal single-weight line-art style — elegant continuous linework, mostly white "
               "space, one or two accent colors"},
    {"id": "corporate_memphis", "label": "Modern flat (Memphis)", "tags": ["vector"],
     "prompt": "Modern flat 'corporate memphis' illustration — rounded characters, bright cheerful "
               "flat palette, simple geometric backgrounds"},
    # --- retro / pixel / digital ---
    {"id": "pixel_art", "label": "Pixel art", "tags": ["retro", "pixel"],
     "prompt": "16-bit pixel-art style — crisp pixels, limited retro palette, dithered shading, "
               "isometric-friendly game sprites"},
    {"id": "retro_80s_cartoon", "label": "Retro 80s cartoon", "tags": ["retro"],
     "prompt": "1980s Saturday-morning cartoon style — bold outlines, flat bright colors, simple "
               "cel shading, retro action-cartoon energy"},
    {"id": "vaporwave", "label": "Vaporwave", "tags": ["retro", "digital"],
     "prompt": "Vaporwave/synthwave style — neon magenta-and-cyan palette, retro grid horizons, "
               "chrome, glow, 80s aesthetic"},
    {"id": "cyberpunk_neon", "label": "Cyberpunk neon", "tags": ["digital"],
     "prompt": "Cyberpunk neon style — rain-slicked neon city glow, saturated magenta/teal lighting, "
               "high-tech grime, cinematic contrast"},
    # --- photoreal ---
    {"id": "photoreal_cinematic", "label": "Photoreal cinematic", "tags": ["photoreal"],
     "prompt": "Photorealistic cinematic style — filmic lighting, shallow depth of field, natural "
               "skin and materials, color-graded like a feature film"},
    {"id": "cinematic_film_still", "label": "Cinematic film still", "tags": ["photoreal"],
     "prompt": "Moody cinematic film-still — anamorphic look, dramatic practical lighting, teal-and-"
               "orange grade, 35mm grain"},
    # --- world / craft / misc ---
    {"id": "ukiyoe", "label": "Ukiyo-e woodblock", "tags": ["world"],
     "prompt": "Japanese ukiyo-e woodblock-print style — flat color fields, elegant outlines, "
               "traditional patterns, subtle paper texture"},
    {"id": "charcoal_sketch", "label": "Charcoal sketch", "tags": ["sketch"],
     "prompt": "Expressive charcoal sketch style — smudged graphite shading, rough paper texture, "
               "loose gestural linework, monochrome"},
    {"id": "crayon_kids", "label": "Crayon / kids drawing", "tags": ["sketch", "craft"],
     "prompt": "Child's crayon drawing style — waxy scribbled color, wobbly outlines, naive "
               "charming proportions, paper texture"},
    {"id": "sticker_kawaii", "label": "Sticker kawaii", "tags": ["vector"],
     "prompt": "Cute kawaii sticker style — thick white die-cut outline, glossy bright colors, "
               "simple adorable chibi shapes"},
    {"id": "chalkboard", "label": "Chalkboard", "tags": ["sketch"],
     "prompt": "Chalkboard illustration style — white and pastel chalk on dark slate, hand-drawn "
               "texture, dusty smudges"},
]

_BY_ID = {s["id"]: s for s in ART_STYLES}


def get(style_id: str) -> dict | None:
    return _BY_ID.get(style_id)


def prompt_for(style_id_or_text: str) -> str:
    """Resolve a style id to its prompt; if it's not a known id, treat it as a literal art-style string."""
    s = _BY_ID.get(style_id_or_text or "")
    return s["prompt"] if s else (style_id_or_text or "")
