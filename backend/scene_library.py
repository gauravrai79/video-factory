"""Scene library — the curated catalog the storyboard planner picks from.

A scene template is a reusable shot blueprint: environment, camera, mood, lighting, and a default
render mode. The planner sequences templates into a storyboard and lets the character/brief override
details. Curated (not free-form) so cost and look stay predictable — see project decisions.

`render_bias` is the cost lever: "still" shots become a generated image + free Ken Burns motion;
"video" shots spend on an image-to-video model. The planner keeps most shots on stills and reserves
video for a few hero beats.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SceneTemplate:
    key: str
    label: str
    environment: str
    camera: str
    mood: str
    lighting: str
    render_bias: str = "still"          # "still" (cheap, Ken Burns) | "video" (paid motion)
    duration_s: float = 3.5
    clothing_hint: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


# Curated catalog. Keep render_bias mostly "still"; mark only motion-defining beats as "video".
SCENE_TEMPLATES: dict[str, SceneTemplate] = {t.key: t for t in [
    SceneTemplate("morning_coffee", "Morning coffee", "cozy sunlit kitchen or cafe with a coffee cup",
                  "slow push-in", "warm, intimate, relaxed", "soft warm morning light",
                  clothing_hint="casual loungewear", tags=("lifestyle", "daily")),
    SceneTemplate("gym_mirror", "Gym mirror selfie", "modern gym in front of a large mirror",
                  "handheld selfie framing", "confident, energetic", "bright even gym light",
                  render_bias="still", clothing_hint="athletic wear", tags=("fitness", "glamour")),
    SceneTemplate("beach_walk", "Beach walk", "sandy beach at the waterline",
                  "tracking alongside, gentle handheld", "free, breezy, carefree",
                  "golden hour sun", render_bias="video", duration_s=4.0,
                  clothing_hint="swimwear or light summer dress", tags=("travel", "glamour")),
    SceneTemplate("luxury_hotel", "Luxury hotel suite", "upscale hotel suite with a city or sea view",
                  "slow lateral dolly", "aspirational, elegant", "soft diffused interior light",
                  clothing_hint="elegant resortwear", tags=("luxury", "travel")),
    SceneTemplate("airport_lounge", "Airport lounge", "sleek airport lounge with large windows",
                  "static with subtle parallax", "jet-set, anticipatory", "cool daylight",
                  clothing_hint="chic travel outfit", tags=("travel", "lifestyle")),
    SceneTemplate("shopping_mall", "Shopping stroll", "bright modern shopping mall or boutique street",
                  "slow follow", "playful, indulgent", "mixed retail lighting",
                  clothing_hint="trendy streetwear", tags=("fashion", "lifestyle")),
    SceneTemplate("cooking", "Cooking at home", "stylish home kitchen mid-recipe",
                  "overhead and close inserts", "homely, warm, capable", "warm practical kitchen light",
                  render_bias="video", clothing_hint="casual chic with an apron", tags=("lifestyle", "food")),
    SceneTemplate("selfie_vlog", "Selfie vlog", "close talking-to-camera framing, any setting",
                  "handheld selfie, eye contact", "candid, friendly, direct", "soft frontal light",
                  render_bias="video", duration_s=4.5, clothing_hint="everyday outfit",
                  tags=("vlog", "talking")),
    SceneTemplate("rooftop_sunset", "Rooftop sunset", "city rooftop terrace at sunset",
                  "slow orbit", "dreamy, romantic, golden", "warm sunset backlight",
                  clothing_hint="evening outfit", tags=("luxury", "glamour")),
    SceneTemplate("date_night", "Date night", "dim ambient restaurant or bar",
                  "shallow-focus push-in", "flirty, glamorous", "moody warm ambient light",
                  clothing_hint="cocktail dress / sharp eveningwear", tags=("glamour", "lifestyle")),
    SceneTemplate("fashion_tryon", "Fashion try-on", "boutique fitting area or bedroom mirror",
                  "static framing, quick outfit reveals", "stylish, fun", "clean even light",
                  clothing_hint="multiple outfit changes", tags=("fashion", "haul")),
    SceneTemplate("travel_diary", "Travel diary", "iconic outdoor landmark or scenic vista",
                  "wide establishing then push-in", "adventurous, awed", "natural daylight",
                  render_bias="video", duration_s=4.0, clothing_hint="travel outfit",
                  tags=("travel", "story")),
    SceneTemplate("poolside", "Poolside lounging", "luxury pool deck with loungers",
                  "slow crane-down", "languid, sun-soaked", "bright midday sun",
                  clothing_hint="swimwear", tags=("luxury", "glamour")),
    SceneTemplate("city_street", "City street walk", "busy stylish city street",
                  "tracking from the front", "cool, self-assured", "urban daylight",
                  render_bias="video", clothing_hint="street style", tags=("fashion", "urban")),
    SceneTemplate("park_stroll", "Park stroll", "leafy park path with dappled light",
                  "gentle handheld follow", "calm, wholesome", "dappled natural light",
                  clothing_hint="smart casual", tags=("lifestyle", "outdoor")),
    SceneTemplate("car_selfie", "Car selfie", "interior of a parked stylish car",
                  "static selfie framing", "candid, glam", "soft window light",
                  clothing_hint="day outfit", tags=("lifestyle", "glamour")),
    SceneTemplate("getting_ready", "Getting ready", "vanity / mirror with makeup and lights",
                  "close inserts and mirror framing", "intimate, anticipatory", "warm vanity bulbs",
                  clothing_hint="robe to outfit reveal", tags=("beauty", "glamour")),
    SceneTemplate("yoga", "Yoga / stretch", "calm studio or balcony with a mat",
                  "slow lateral move", "serene, controlled", "soft morning light",
                  render_bias="video", clothing_hint="activewear", tags=("fitness", "wellness")),
    SceneTemplate("bookstore_cafe", "Bookstore cafe", "cozy bookstore cafe corner",
                  "slow push-in", "thoughtful, soft", "warm lamp light",
                  clothing_hint="smart casual knitwear", tags=("lifestyle", "cozy")),
    SceneTemplate("nightlife", "Night out", "neon-lit nightlife street or club entrance",
                  "handheld energetic", "bold, vibrant", "neon mixed light",
                  render_bias="video", clothing_hint="party outfit", tags=("glamour", "night")),
    SceneTemplate("garden", "Garden / florals", "lush garden or flower field",
                  "slow drifting move", "fresh, romantic", "soft overcast or golden light",
                  clothing_hint="flowy dress", tags=("nature", "glamour")),
    # --- animal / pet beats (e.g. Jango the dog) ---
    SceneTemplate("pet_park", "Pet at the park", "open grassy park, pet playing",
                  "low tracking with the pet", "joyful, lively", "bright natural daylight",
                  render_bias="video", duration_s=4.0, tags=("pet", "outdoor")),
    SceneTemplate("pet_home", "Pet at home", "cozy living room with the pet on a couch",
                  "slow push-in to the pet", "warm, adorable", "soft indoor light",
                  tags=("pet", "cozy")),
    SceneTemplate("pet_treat", "Pet treat moment", "kitchen, pet awaiting a treat",
                  "close handheld", "playful, eager", "warm kitchen light",
                  render_bias="video", tags=("pet", "fun")),
    SceneTemplate("pet_walk", "Pet on a walk", "tree-lined street or trail on a leash walk",
                  "tracking alongside", "easygoing, happy", "dappled daylight",
                  render_bias="video", duration_s=4.0, tags=("pet", "outdoor")),
]}


def get_template(key: str) -> SceneTemplate | None:
    return SCENE_TEMPLATES.get(key)


def templates_for_tags(tags: list[str]) -> list[SceneTemplate]:
    """Templates matching any of the given tags (e.g. ['travel','glamour']); all if none given."""
    if not tags:
        return list(SCENE_TEMPLATES.values())
    want = {t.lower() for t in tags}
    return [t for t in SCENE_TEMPLATES.values() if want & {x.lower() for x in t.tags}]


def catalog() -> list[dict]:
    """Lightweight catalog for the API/planner: key, label, tags, render_bias."""
    return [{"key": t.key, "label": t.label, "tags": list(t.tags),
             "render_bias": t.render_bias, "duration_s": t.duration_s}
            for t in SCENE_TEMPLATES.values()]
