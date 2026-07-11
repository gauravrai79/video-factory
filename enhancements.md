# Jango & Commando Zruv — Production Engine Spec

Everything from the review, consolidated and code-ready. Three modules:
1. Prompt generation (keyframe vs video)
2. Transition engine
3. Final assembly (cut rhythm + audio)

---

## 1. Prompt Generation

### 1.1 The one rule that fixes most of it

**Keyframe prompts describe a STILL, STABLE instant. Video prompts carry ALL the motion.**

The Scene 2 failure (empty scooter, grounded tiffin, crater pothole, pasted-in Jango) happened because the keyframe prompt contained motion language (`hangs in the air`, `beginning to spill`, `single frozen instant`). A still-image model can't hold a mid-air moment, so it collapses everything to rest. Move every motion word to the video stage.

### 1.2 Keyframe linter (run before sending any keyframe prompt)

Reject / strip a keyframe prompt if it contains any of these tokens (case-insensitive). These belong only in video prompts.

```json
{
  "banned_in_keyframe": [
    "mid-air", "in the air", "hangs", "hanging", "airborne", "flying",
    "tumbling", "tumbles", "spilling", "spills", "launches", "launching",
    "popping", "pops loose", "arc", "slow-motion", "slow motion",
    "just as", "in the act of", "about to", "mid-", "tracking shot",
    "camera pans", "camera tracks", "motion blur", "streaking", "bursting"
  ]
}
```

### 1.3 Required keyframe anchors (checklist the generator must satisfy)

For any keyframe, enforce these or the frame reads as broken/composited:

- **Agent present for any vehicle/action** — if a scooter moves, a *rider* must be in frame. No orphaned props.
- **Scale anchor for any hole/large object** — e.g. "pothole roughly the width of the scooter's wheel." Prevents crater artifacts.
- **Eyeline for observing characters** — if Jango watches something, his head is turned toward it, not at camera.
- **Single continuous ground plane** — characters and action share one floor; state it explicitly.
- **Matched lighting + render** — "single consistent light source; every element shares the same lighting and ink-line rendering so nothing looks composited." This is what stops Jango looking pasted in.
- **Scale cap on hero character** — Jango occupies ~1/4 frame height in wide-medium shots, not half. He's small; frame him small.
- **Footer** — always append `Sharp focus, crisp linework, no motion blur.`

### 1.4 Keyframe prompt template (parameterized)

```
Comic-book cinematic style — bold inked outlines, dramatic cel shading, rich saturated graphic-novel colors, high-contrast cinematic lighting.
Setting: {SETTING_BLOCK}. Single consistent light source — every element shares the same lighting and ink-line rendering so nothing looks composited.
Subject: {CHARACTER_NAME} — {CHARACTER_DESC}, {COSTUME}. {POSITION_AND_SCALE}. {EYELINE_AND_MOOD}. Natural proportions.
Frozen beat (stable, at rest): {STABLE_BEAT_DESCRIPTION_NO_MOTION_WORDS}. {SCALE_ANCHOR}.
Composition: {SHOT_TYPE} street tableau. One continuous ground plane — {DEPTH_LAYOUT}. {EYELINE_LINK}.
Sharp focus, crisp linework, no motion blur. Consistent character identity and wardrobe. No on-screen text, captions, logos, or watermarks.
```

**Reusable constants:**

```json
{
  "STYLE_ANCHOR": "Comic-book cinematic style — bold inked outlines, dramatic cel shading, rich saturated graphic-novel colors, high-contrast cinematic lighting.",
  "SETTING_BLOCK": "contemporary urban India — chaotic vibrant city street (Mumbai/Delhi vibe), Devanagari/Hindi signage, autorickshaws, chai stalls, street vendors, tangled overhead wires, weathered colorful concrete buildings, pedestrians in kurtas, sarees, salwar kameez, warm dusty daylight",
  "FOOTER_STILL": "Sharp focus, crisp linework, no motion blur. Consistent character identity and wardrobe. No on-screen text, captions, logos, or watermarks."
}
```

**Character costume strings (restate inline every time — reference image does not carry costume):**

```json
{
  "jango": "small fawn French Bulldog, compact muscular build, big round alert eyes, upright bat ears, tan tactical harness, natural four-legged proportions",
  "zruv": "blue full-body bodysuit with yellow metallic Z emblem on the chest (Z, never S), brown utility belt, silver forearm guards, brown boots",
  "champa": "sleek grey-and-white cat, lean build, alert green eyes"
}
```

**Worked example (Scene 2, fixed):**

```
Comic-book cinematic style — bold inked outlines, dramatic cel shading, rich saturated graphic-novel colors, high-contrast cinematic lighting.
Setting: contemporary urban India — chaotic vibrant city street (Mumbai/Delhi vibe), Devanagari/Hindi signage, autorickshaws, chai stalls, street vendors, tangled overhead wires, weathered colorful concrete buildings, pedestrians in kurtas, sarees, salwar kameez, warm dusty daylight. Single consistent light source — every element shares the same lighting and ink-line rendering so nothing looks composited.
Subject: Jango — small fawn French Bulldog, compact muscular build, big round alert eyes, upright bat ears, tan tactical harness. Sitting at the LEFT roadside in the MID-GROUND, about one-quarter of the frame height. Head turned to his right, watching the road, calm and unbothered. Natural four-legged proportions.
Frozen beat (stable, at rest): a man rides a red scooter that has just clipped the edge of a shallow pothole (pothole roughly the width of the scooter's front wheel); front wheel dips, rider leans. His steel tiffin box, strapped to the rear rack, has its lid springing open — one roti just lifting free, low and close to the lid.
Composition: wide-medium street tableau. One continuous ground plane — Jango near-left, scooter and pothole center-right, market crowd behind. Clear eyeline from Jango toward the scooter.
Sharp focus, crisp linework, no motion blur. Consistent character identity and wardrobe. No on-screen text, captions, logos, or watermarks.
```

### 1.5 Video prompt template (parameterized)

```
Animate from the keyframe. Keep every character's exact look, wardrobe, and the scene's ink style locked.
Action: {MOTION_DESCRIPTION_ALL_MOTION_HERE}.
Camera: {CAMERA_MOVE}.
Natural physics, weight, and expression; ambient street motion — traffic, pedestrians, swaying wires. {DIALOGUE_LINE_OR_NONE}. No on-screen text, captions, subtitles, logos, or watermarks.
```

**Conditional dialogue field — this fixes the boilerplate lip-sync bug:**

```
DIALOGUE_LINE_OR_NONE =
  if scene.has_dialogue:  'One short spoken line, accurate lip-sync: "{LINE}"'
  else:                   'No spoken dialogue in this shot.'
```

Never send "accurate lip-sync" to a scene with no dialogue — it animates a talking mouth on a silent character.

**Worked example (Scene 2, fixed):**

```
Animate from the keyframe. Keep every character's exact look, wardrobe, and the scene's ink style locked.
Action: the scooter bounces hard over the pothole; the tiffin lid flies fully open and the rotis launch upward in a comic slow-motion arc, tumbling through the air. The rider wobbles but keeps riding. Jango stays seated at the roadside, calmly turning his head to follow the flying rotis — unbothered, one ear flicking.
Camera: slow-motion medium shot tracking the airborne rotis, then settling on Jango's deadpan reaction.
Natural physics, weight, and expression; ambient street motion — traffic, pedestrians, swaying wires. No spoken dialogue in this shot. No on-screen text, captions, subtitles, logos, or watermarks.
```

### 1.6 Template bugs to fix in current code

- **`Featuring Jango (a animal)`** — template variable resolving to bad grammar. Drop the `(a {type})` interpolation entirely; the costume string already identifies the species.
- **Duplicate style/setting block** — video prompt currently repeats the full style + setting paragraph. Not needed once you use "Animate from the keyframe" + "keep the scene's ink style locked." Shorter prompt = less drift.
- **Per-shot character cap** — enforce max 3 named characters per shot, one spoken line per clip, and never Jango in a tight action frame beside a flexing Zruv (keep them separated by depth/scale).

---

## 2. Transition Engine

### 2.1 The problem

The splicer inserts a ~2s transition at *every* scene seam. That's why the rough cut cuts on a metronome (measured seams at 6→8, 16→18, 22→24…). Transitions only work when rare and meaningful.

### 2.2 Logic rules

- **Default is a hard cut.** No transition.
- Insert a transition **only when `location_id` changes** between consecutive scenes, **or** `time_jump == true`. Never inside a continuous beat.
- **Never two transitions back-to-back.**
- **Min 3 hard cuts between any two transitions** (`MIN_CUTS_BETWEEN = 3`).
- **Episode cap:** `max_transitions = ceil(scene_count / 3)`. A 12-scene episode gets ~4, not 11.
- Pick the transition by `beat_type` via the mapping table; if the tag has no mapping, hard cut.

### 2.3 Scene metadata schema

Add these fields to each scene object:

```json
{
  "scene_id": "s02",
  "location_id": "market_street_A",
  "time_jump": false,
  "beat_type": "impact_gag"
}
```

`beat_type` enum: `establishing`, `dialogue`, `reveal`, `punchline`, `chase`, `impact_gag`, `zruv_entrance`, `neutral`.

### 2.4 Transition mapping table

```json
{
  "beat_type_to_transition": {
    "reveal": "comic_panel_slam",
    "punchline": "comic_panel_slam",
    "chase": "whip_pan",
    "impact_gag": "dust_puff",
    "zruv_entrance": "hero_rush",
    "establishing": "blaze_whoosh",
    "dialogue": null,
    "neutral": null
  },
  "energy_alternates": {
    "chase": ["whip_pan", "blaze_whoosh"],
    "impact_gag": ["dust_puff", "dhoom_burst"]
  }
}
```

### 2.5 Splicer algorithm (pseudocode)

```python
def splice(scenes, mapping, MIN_CUTS_BETWEEN=3):
    timeline = []
    max_transitions = ceil(len(scenes) / 3)
    used = 0
    cuts_since_last = MIN_CUTS_BETWEEN  # allow one early if warranted

    for i, scene in enumerate(scenes):
        timeline.append(scene.clip)
        if i == len(scenes) - 1:
            break
        nxt = scenes[i + 1]

        location_changed = scene.location_id != nxt.location_id
        eligible = (location_changed or nxt.time_jump)
        transition = mapping["beat_type_to_transition"].get(nxt.beat_type)

        if (eligible
                and transition is not None
                and used < max_transitions
                and cuts_since_last >= MIN_CUTS_BETWEEN):
            timeline.append(load_transition(transition))  # ~2s clip
            used += 1
            cuts_since_last = 0
        else:
            cuts_since_last += 1  # hard cut

    return timeline
```

Result: most seams are hard cuts, transitions land only on genuine location/time shifts, and the metronome breaks.

---

## 3. Final Assembly (cut rhythm + audio)

### 3.1 Cut rhythm

The rough cut holds nearly every shot at the native ~6–8s Flow clip length. That evenness is the #1 amateur tell. Rules:

- **Cut inside clips.** Use only the best 2–3s of a 6s generation; don't lay whole clips end to end.
- **Vary shot length deliberately.** Mix punchy 1.5–2s beats, 3–4s holds, and the occasional 5–6s establishing shot. Avoid a uniform cadence.
- **Cut on the beat.** Align hard cuts to a musical beat or a stressed syllable in the VO, not to a fixed timer. Highest-leverage, zero-cost edit.

### 3.2 Audio normalization

Measured on the rough cut: integrated **−15.8 LUFS**, true peak **+0.9 dBTP** (clipping/distorting on peaks). Fix in the assembly stage for every episode:

Two-pass loudnorm (accurate) — pass 1 measures, pass 2 applies:

```bash
# Pass 1 — measure
ffmpeg -i in.mp4 -af loudnorm=I=-14:TP=-1:LRA=11:print_format=json -f null - 2>&1 | tail -20

# Pass 2 — apply measured values (fill in from pass 1 JSON)
ffmpeg -i in.mp4 -af \
"loudnorm=I=-14:TP=-1:LRA=11:measured_I=<mi>:measured_TP=<mtp>:measured_LRA=<mlra>:measured_thresh=<mth>:offset=<off>:linear=true" \
-c:v copy -c:a aac -b:a 192k out.mp4
```

Single-pass (good enough for batch automation):

```bash
ffmpeg -i in.mp4 -af "loudnorm=I=-14:TP=-1:LRA=11" -c:v copy -c:a aac -b:a 192k out.mp4
```

Targets: **−14 LUFS** integrated (YouTube), **−1 dBTP** ceiling (kills the clipping).

### 3.3 Aspect ratio

Current export is **1920×1080 (16:9), ~108s** — correct for a standard YouTube episode. Keep it for long-form. If you also want Shorts for discovery, that's a **separate 9:16 export** — reframe on the subject (Jango/Zruv center), don't just letterbox, and cut it to <60s around the strongest beat.

---

## Build order (test-one-then-propagate)

1. Ship the keyframe linter + anchor checklist (§1.2–1.3) and rerun **Scene 2 only**.
2. If the frame is clean, swap in the parameterized templates (§1.4–1.5) and fix the template bugs (§1.6).
3. Add scene metadata fields (§2.3) and replace the splicer with §2.5.
4. Add the loudnorm pass (§3.2) to final assembly.
5. Regenerate one full episode, check cut rhythm (§3.1), then propagate across all scenes.