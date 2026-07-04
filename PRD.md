# PRD — AI Influencer Factory: Staged Production Pipeline (v2)

**Status:** Draft for review · **Owner:** gauravrai79 · **Date:** 2026-07-05

---

## 1. Summary

Turn the factory from an **autopilot** (one brief → auto-generated finished reel) into a
**stage-gated production line** that replicates the manual creative process for running content
channels: pick a character → develop the story → script it → build reference images → generate the
scenes (mixing cheap and expensive shot types like a real editor) → add voices and music → stitch the
final cut. A **human approval gate sits at every stage**, cheapest-first, so no expensive video/audio
tokens are spent on a bad idea, script, or image.

The system runs multiple **channels** (a YouTube spy-detective series; a themed Instagram glamour reel
account; etc.), each with recurring **characters** that are full **digital actors** — a locked look, a
locked voice, and a personality bible — kept consistent across every scene, episode, and channel.

Scope of this build ends at a **finished, downloadable video**. In-app timeline **editing is Phase 2**;
platform **auto-publishing is a later phase**.

---

## 2. Why (the problem with v1)

v1 plans a storyboard and auto-runs it straight to a delivered file. Wrong shape:

- **No story development** — the real first steps (*have an idea*, then *write a script*) don't exist.
- **No gates** — you can't approve/reject between steps, so a bad idea burns video money.
- **No series/channel** — no recurring premise, format, or cast bible above a single post.
- **Single character** — a scene can't feature a lead *and* a sidekick (Django + Zoom).
- **No audio, no voices.**
- **Character is invisible** and one-dimensional (a look, no voice, no personality).
- **Long-form is unaffordable** if every scene is generated hero video.

---

## 3. Goals / Non-goals

**Goals**
1. **Channels/Series** with premise, format, recurring cast, art style, and target length.
2. **Characters as digital actors** — visible reference sheet + locked **voice** + **personality
   bible** (system prompt) — castable together in one scene, reusable across channels.
3. The **staged pipeline** (ideate → script → reference images → scenes → audio → assemble) with a
   **human gate at every stage** (approve / edit / re-roll / reject) and per-asset re-roll.
4. **Cheapest-first spend** via a **shot-type cost engine** (b-roll / Ken Burns / lip-sync / hero
   video) so long-form is affordable and looks professionally edited.
5. One shared engine for **long-form** (15–20 scenes) **and short-form** (themed 3-scene reels).
6. **Full audio** — narrator VO + per-character voices + music bed, auto-ducked.
7. **Provider-configurable writers' room** (default Claude), **ElevenLabs** voices.
8. Final cut modeled as an **editable timeline (EDL)** so Phase-2 in-app editing bolts on cleanly.
9. Preserve v1 infra: queue/workers, hash-chained audit, cost ceiling, SLA, deterministic FFmpeg,
   fal image/video clients, SQLite→Postgres shape.

**Non-goals (this build)**
- In-app timeline editing → **Phase 2** (architecture prepared via the EDL).
- Auto-publishing to platforms → later phase.
- Engagement analytics / feedback loop → later phase.
- Per-character LoRA, 2.5D parallax shots → polish phase (reference images + the shot engine suffice).
- Real-person likenesses → never (synthetic personas only, hard constraint).

---

## 4. Core principle — stage-gated, cheapest-first, approve-to-advance

```
IDEATE        SCRIPT         REFERENCE IMGS     SCENES              AUDIO          ASSEMBLE
(LLM ~free)   (LLM ~free)    (image, cheap)     (mixed shot types)  (TTS+music $$) (FFmpeg, free)
   │ ▲           │ ▲             │ ▲               │ ▲                 │ ▲            │
   └─┘           └─┘             └─┘               └─┘                └─┘            └ final approve
  gate          gate            gate              gate               gate
```

Each gate: **Approve** (advance) · **Edit** (hand-tweak the artifact) · **Re-roll** (regenerate one
asset or the stage) · **Reject** (back up a stage). Paid stages show an estimated cost and require an
explicit **commit-spend** click; the per-job cost ceiling applies per stage; a per-episode budget caps
total spend. Rejected idea/script ≈ $0; a bad reference image ≈ $0.10 to re-roll — the expensive stages
only run on approved inputs. This is the token-safety mechanism.

---

## 5. Entity model

### Character — a digital actor (three DNAs)
Persistent, pre-mapped, locked across every scene / episode / channel.
```
character_id, name, slug, species,
# Visual DNA
reference_images (paths — the VISIBLE sheet), dna_prompt, safety_tolerance,
# Voice DNA
voice_provider, voice_id (preset OR cloned from an uploaded sample),
voice_params (pace, stability, accent), signature_line (preview),
# Personality DNA (structured — injected as SYSTEM PROMPT at every generative stage)
personality { backstory, traits[], speech_style, catchphrases[], relationships{}, mannerisms[] },
created_at
```
- **Voice DNA** is assigned once and reused for every line the character ever speaks → consistent by
  construction. Preset library **and** cloning from a sample are both supported.
- **Personality DNA** is the character's system prompt: it's system context when the writer drafts
  their dialogue, it flavors TTS delivery, and it adds behavioral cues to their image/motion prompts.
  In a two-hander, the writer receives *both* bibles so the relationship dynamic stays consistent.

### Channel — the show bible
```
channel_id, name, slug, platform, format (long_form|short_form), premise,
cast [{character_id, role: lead|sidekick|recurring}], narrator_voice_id,
art_style (text) + style_reference_images (image lock),
target_scene_count, target_duration_s, video_budget (max hero-video scenes),
writer_provider (default anthropic), writer_model,
series_memory (running bible + episode recaps — continuity across episodes),
posting_cadence, created_at
```

### Episode — moves through the pipeline
```
episode_id, channel_id, number, title, logline,
stage (idea|script|refs|scenes|audio|assembly|done),
stage_status (pending|generating|awaiting_review|approved|rejected),
idea, script, cast (resolved), scenes[], timeline (EDL), spent_usd, est_cost_usd, created_at
```

### Scene — the per-shot record (with shot type)
```
seq, heading, action, camera, cast_present[character_id],
dialogue [{speaker: character_id, line, delivery}], narration,
shot_type (broll | still_kenburns | lipsync_still | hero_video),
duration_s, reference_image{path,status}, clip{path,status},
voice_clips[{line, path}], status
```

---

## 6. The stages (detailed)

Costs per current pricing (`backend/capabilities/pricing.py`); verify before relying on figures.

### Stage 1 — Ideate  *(LLM · ~free)*
Channel bible + cast personalities + recent episode titles → **N episode concepts** (title, logline,
hook, beat outline). **Gate:** pick / edit / regenerate → locks `idea`.

### Stage 2 — Script  *(LLM · ~free)*
Approved idea + bible + cast → **scene-by-scene screenplay**: heading, action, camera, **dialogue
tagged by speaker**, **narration**, **`shot_type` per scene** (the director's cost call), cast present,
duration. Structured `scenes[]` so downstream is deterministic. **Gate:** inline edit any line/field ·
regenerate a scene or the script · approve → reveals the full estimated cost of the paid stages.

### Stage 3 — Reference images  *(fal image · ~$0.10/scene)*
Per scene, one still (Nano Banana, **multi-character** DNA injected, **art-style + style-ref locked**).
**Gate:** approve all · **re-roll individual weak images** (optional prompt tweak) · reject to script.
Only approved frames advance — no video spend on a bad frame.

### Stage 4 — Scenes (the shot-type cost engine)  *(mixed)*
Each scene renders per its `shot_type` — the director assigns the **cheapest shot that sells the beat**,
capped by the channel `video_budget`; **you can bump any scene up/down at the gate**:

| Shot type | Cost | Use |
|---|---|---|
| **B-roll cutaway** (stock-first: Pexels/Pixabay free API → generate if needed) | ~$0 | atmosphere, establishing, inserts |
| **Still + Ken Burns** pan/zoom | ~$0.10 | narration-over, reactions |
| **Lip-sync on a still** (fal lip-sync from the still + the voice line) | ~$0.10–0.15 | character **talking on-camera** (the dialogue-cost saver) |
| **Hero image-to-video** (Wan/Kling) | ~$0.30–0.50 | reserved: character **acting/moving** |

Per-scene QC (identity/anatomy) flags. **Gate:** approve · **re-roll individual clips** · reject a clip
to its reference. *Illustrative 16-scene episode: naïve all-hero ≈ $6.40 → edited mix ≈ $3.90 and looks
more produced.*

### Stage 5 — Audio  *(ElevenLabs + music · $$)*
(a) **Narration** in the channel narrator voice; (b) **dialogue** — each line in that character's locked
voice, delivery flavored by personality; (c) **music bed** (library-first, royalty-free) matched to
tone/length. **Gate:** approve · re-roll a line/voice/music · adjust levels.

### Stage 6 — Assemble → **editable timeline (EDL)**  *(FFmpeg · deterministic · free)*
Build an explicit **EDL** (ordered scenes with in/out, transitions, audio tracks: dialogue+narration+
music with **auto-ducking**, caption/overlay tracks), then render: Ken Burns on stills, **subtle
crossfade transitions**, mux audio, burn optional captions, encode to the channel format. **Gate:**
final review → approve → `done` (downloadable). Reject sends specific scenes back. *The EDL being a
first-class editable object is what enables Phase-2 editing with no re-architecture.*

---

## 7. Human-in-the-loop model
One gate per stage in an **Episode Workspace** (stepper). Actions: Approve · Edit · Re-roll (per-asset
or stage) · Reject. Paid stages: estimated cost + **commit-spend** click; per-stage ceiling +
per-episode budget cap. Every approval/re-roll/spend is a hash-chained audit event. An episode can sit
at any gate indefinitely; nothing runs until you advance it.

---

## 8. Provider abstraction (pluggable)

| Layer | Interface | Default | Notes |
|---|---|---|---|
| **Writer** | `WriterProvider.ideate()/script()` | Anthropic (Claude) | configurable per channel (Anthropic\|Gemini\|OpenAI) |
| **Image** | `generate_still()` | fal Nano Banana 2 | multi-character, style-locked (reuse v1) |
| **Video** | `generate_video()` | fal Wan 2.5 / Kling 2.5 Turbo | reuse v1 |
| **Lip-sync** | `lipsync(still, voice)` | fal lip-sync model | talking shots |
| **B-roll** | `broll(query)` | Pexels/Pixabay (free) → generate fallback | stock-first |
| **Voice** | `VoiceProvider.speak(text, voice_id)` | ElevenLabs | preset + cloning; per-character mapping |
| **Music** | `MusicProvider.get(brief,len)` | royalty-free library | generation optional |

All keys via `.env` (never committed).

---

## 9. Cost model
Per-episode estimate computed at script approval, shown before any paid stage.
- **Long-form (16 scenes, edited mix):** ~$3.90 image/video + ~$1–3 audio ≈ **$5–7 / episode**.
- **Short-form (3 scenes):** ~$1 image/video + ~$0.50 audio ≈ **$1.50 / reel**.
Gating keeps rejects near-$0; per-stage ceiling + per-episode budget prevent runaway spend.

---

## 10. UX / screens
1. **Channels** — list + create (premise, format, cast picker, art style + style ref, writer provider,
   length, video budget).
2. **Characters** — list **with visible reference-sheet thumbnails**; detail shows the full sheet,
   **voice preview (signature line)**, and the personality bible; actions: mint reference sheet /
   upload photos, assign/clone voice, edit personality. *(Fixes "I can't see the character.")*
3. **Episode Workspace** — the heart: a stepper (Ideate→Script→Refs→Scenes→Audio→Assemble), each step
   showing its artifact (idea cards / editable script / image grid / clip grid / audio preview / final
   player), the stage cost, and Approve / Edit / Re-roll / Reject.
4. **Library** — finished episodes per channel, downloadable.

---

## 11. Reuse vs build
**Reuse (from v1):** `jobstore` + hash-chained audit + idempotency · `jobqueue` (sync/RQ) ·
`finishing.py` (Ken Burns, stitch, mux — extend for transitions, audio ducking, EDL render) ·
`fal_image.py` / `fal_video.py` / `pricing.py` · `characters.py` (extend: voice + personality + visible
refs) · `sla.py` · cost ceiling.

**Build (new):** `channels.py` · `episodes.py` (+ staged state machine + EDL) · `agents/writer.py`
(provider-agnostic ideate/script) · `capabilities/voice.py` (ElevenLabs) · `capabilities/lipsync.py` ·
`capabilities/broll.py` (stock) · `capabilities/music.py` · shot-type director · audio-mux + EDL render
in finishing · staged orchestrator (replaces v1 auto-run) · new API (channels/episodes/stage actions) ·
Episode Workspace UI.

**Migration:** v1's `Storyboard`/auto-run `Job` → superseded by `Episode`. Characters carry over
(add voice + personality + visible refs). No production data to preserve.

---

## 12. Architecture / deployment
**Railway** (long workers + FFmpeg + Postgres). Each paid stage is a queued job so long-form fans out;
the Episode row is durable state. SQLite locally → Postgres in prod. Not Vercel.

---

## 13. Delivery plan (milestones)

- **M1 — Data & visibility:** Channel + Episode/Scene entities + stores; Character as digital actor —
  **reference sheet visible in UI**, voice field + preview, personality bible. (No new generation.)
- **M2 — Writers' room:** `WriterProvider` → Ideate + Script stages with gates + pricing. Approvable
  script, $0 spent.
- **M3 — Visual stages + shot engine:** reference-image stage (grid + per-asset re-roll) → Scenes stage
  with the **shot-type cost engine** (b-roll / Ken Burns / lip-sync / hero video) + per-clip re-roll →
  assemble silent cut with transitions.
- **M4 — Audio:** ElevenLabs VO + per-character voices + music + auto-ducked EDL assembly.
- **M5 — Workspace polish:** full Episode Workspace stepper, per-stage cost / commit-spend, budgets,
  long-form + short-form presets end-to-end. **← v2 done.**
- **Phase 2 — M6 In-app editing:** timeline UI over the EDL — reorder/trim/retime scenes, swap shot or
  re-roll from the timeline, change transitions, adjust audio levels/ducking, insert b-roll, titles/
  captions → re-render.
- **Later — M7 Publishing:** per-channel platform auto-publish + titles/captions/hashtags.
- **Later — M8 Polish:** 2.5D parallax shots, per-character LoRA, analytics feedback loop.

---

## 14. Success criteria
- Build channel *"Django, P.I."*, cast Django + Zoom (both with **visible reference sheets + locked
  voices + personality bibles**), and produce a **~2 min, 15–20 scene episode** through all gates —
  re-rolling ≥1 image and ≥1 clip, using a **mix of b-roll / Ken Burns / lip-sync / hero video** so
  video spend stays low, with narration + character voices + music — ending in a downloadable file,
  **without spending on video until images are approved.**
- Produce a **short-form themed glamour reel** (3 scenes) through the same engine.
- Every stage gated, priced, audited; total spend matches the fal/ElevenLabs dashboards.
- The final cut is an **editable EDL**, ready for Phase-2 timeline editing.
