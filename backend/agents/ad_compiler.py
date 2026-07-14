"""Ad / script compiler — turns a free-form Markdown "prompt pack" (like the ones Claude writes for a
video ad) into our internal scene structure so the ONE-OFF pipeline can render it end-to-end.

It preserves the author's prompts VERBATIM (an ad is intentional) — the per-scene Imagen/still prompt
becomes the keyframe, the Veo/motion prompt becomes the video prompt override, and a global STYLE BASE
is expanded into each. A deterministic parser handles the common well-structured format (and doubles
as the $0 stub); an LLM fallback structures messier docs.

Output dict:
  {title, style_base, palette, aspect, scenes: [{seq, label, title, still_prompt, motion_prompt,
   start_s, end_s, duration_s}], voiceover: [str], voiceover_text, music}
"""
from __future__ import annotations

import re
from typing import Any

from .writer import _chat, _key, _parse_json, default_model

_SCENE_SPLIT = re.compile(r"\n(?=##\s+SCENE\b)", re.I)
_STYLE_HDR = re.compile(r"##\s*STYLE\s*BASE.*?\n(.*?)(?:\n##\s|\n---|\Z)", re.I | re.S)
_VO_HDR = re.compile(r"##\s*VOICEOVER.*?\n(.*?)(?:\n##\s|\n---|\Z)", re.I | re.S)
_MUSIC_HDR = re.compile(r"##\s*MUSIC.*?\n(.*?)(?:\n##\s|\n---|\Z)", re.I | re.S)
# a bold label ("**4a — Imagen (still):**") followed by its blockquote lines
_LABELLED = re.compile(
    r"\*\*\s*(?:(?P<tag>[0-9]+[a-z])\s*[—\-]\s*)?(?P<kind>Imagen|still|Veo|motion)[^*\n]*\*\*\s*\n"
    r"(?P<quote>(?:\s*>.*\n?)+)", re.I)
_TIMING = re.compile(r"\((?:~)?\s*(\d+)\s*[–\-]\s*(\d+)\s*s\)")
_HEAD_TITLE = re.compile(r"[·:]\s*[\"“](.+?)[\"”]")
_ONSCREEN = re.compile(r"On-?screen text[^:]*:\s*\**(.+)", re.I)


def _blockquote_text(quote: str) -> str:
    lines = [re.sub(r"^\s*>\s?", "", ln) for ln in quote.splitlines() if ln.strip().startswith(">")]
    return " ".join(l.strip() for l in lines).strip()


def _clean_title(text: str) -> str:
    return re.sub(r"[*_`]|\(.*?\)", "", text or "").strip(" .·—-\"“”")


def _expand(prompt: str, style_base: str) -> str:
    if not prompt:
        return ""
    out = re.sub(r"\[\s*STYLE\s*BASE\s*\]", style_base, prompt, flags=re.I)
    if style_base and "[STYLE BASE]" not in prompt.upper() and style_base.lower() not in out.lower():
        pass  # some scenes may not reference it; leave as-is
    return re.sub(r"\s+", " ", out).strip()


def parse_markdown(md: str) -> dict[str, Any]:
    """Deterministic parse of the well-structured 'prompt pack' format. Returns {} scenes-empty if it
    can't find scenes (caller may fall back to the LLM)."""
    md = md.replace("\r\n", "\n")
    title = ""
    m = re.search(r"^#\s+(.+)", md, re.M)
    if m:
        title = _clean_title(m.group(1))
    style_base = ""
    sm = _STYLE_HDR.search(md)
    if sm:
        style_base = _blockquote_text(sm.group(1)) or re.sub(r"\s+", " ", sm.group(1)).strip()
    voiceover: list[str] = []
    vm = _VO_HDR.search(md)
    if vm:
        numbered, bulleted = [], []
        for ln in vm.group(1).splitlines():
            if ln.strip().startswith("*") and ln.strip().endswith("*"):
                continue                              # skip italic production notes
            nq = re.match(r"\s*\d+\.\s*[\"“]?(.+?)[\"”]?\s*$", ln)
            bq = re.match(r"\s*[-*]\s*[\"“]?(.+?)[\"”]?\s*$", ln)
            if nq and len(nq.group(1).strip()) > 4:
                numbered.append(nq.group(1).strip())
            elif bq and len(bq.group(1).strip()) > 4:
                bulleted.append(bq.group(1).strip())
        voiceover = numbered or bulleted              # numbered narration wins over stray bullets
    music = ""
    mm = _MUSIC_HDR.search(md)
    if mm:
        music = re.sub(r"\s+", " ", mm.group(1)).strip()[:600]
    aspect = "9:16" if re.search(r"\b9:16\b.*master|vertical\s+master", md, re.I) else "16:9"

    scenes: list[dict] = []
    seq = 0
    for block in _SCENE_SPLIT.split(md):
        if not re.match(r"\s*##\s+SCENE", block, re.I):
            continue
        head = block.splitlines()[0]
        t = _TIMING.search(head)
        start_s, end_s = (int(t.group(1)), int(t.group(2))) if t else (None, None)
        ht = _HEAD_TITLE.search(head)
        head_title = _clean_title(ht.group(1)) if ht else ""
        on = _ONSCREEN.search(block)
        on_title = _clean_title(on.group(1)) if on else ""
        stills: list[tuple[str, str]] = []   # (tag, prompt)
        motions: list[tuple[str, str]] = []
        for lm in _LABELLED.finditer(block):
            kind = lm.group("kind").lower()
            tag = (lm.group("tag") or "").lower()
            text = _blockquote_text(lm.group("quote"))
            if not text:
                continue
            (stills if kind in ("imagen", "still") else motions).append((tag, text))
        if not stills and not motions:
            continue
        pairs = max(len(stills), len(motions), 1)
        span = ((end_s - start_s) if (start_s is not None and end_s is not None) else 8) / pairs
        for i in range(pairs):
            still = stills[i][1] if i < len(stills) else (stills[-1][1] if stills else "")
            motion = motions[i][1] if i < len(motions) else (motions[-1][1] if motions else still)
            dur = max(4.0, min(8.0, round(span, 1)))
            scenes.append({
                "seq": seq, "label": _clean_title(head.split("—")[-1].split("·")[0]) or f"Scene {seq+1}",
                "title": on_title or head_title,
                "still_prompt": _expand(still, style_base),
                "motion_prompt": _expand(motion, style_base),
                "start_s": start_s, "end_s": end_s, "duration_s": dur,
            })
            seq += 1
    return {"title": title or "Untitled ad", "style_base": style_base, "aspect": aspect,
            "voiceover": voiceover, "voiceover_text": " ".join(voiceover), "music": music,
            "scenes": scenes}


def _llm_compile(md: str, model: str | None) -> dict[str, Any]:
    model = model or default_model()
    system = ("You convert a free-form video-ad markdown 'prompt pack' into strict JSON our renderer "
              "can run. Preserve the author's image and motion prompts VERBATIM (only expand any "
              "[STYLE BASE] placeholder inline). Respond ONLY with JSON.")
    user = (
        "Markdown:\n" + md[:12000] + "\n\n"
        "Return JSON: {\"title\": str, \"style_base\": str, \"aspect\": \"16:9\"|\"9:16\", "
        "\"voiceover\": [str per line], \"music\": str, \"scenes\": [{\"title\": short on-screen text, "
        "\"still_prompt\": the keyframe/Imagen prompt with STYLE BASE expanded, \"motion_prompt\": the "
        "Veo/motion prompt with STYLE BASE expanded, \"duration_s\": number 4-8}]}. Split multi-clip "
        "scenes (e.g. 4a/4b) into separate scene entries.")
    text, _ = _chat(system, user, model, temperature=0.1, max_tokens=8000)
    data = _parse_json(text)
    scenes = []
    for i, s in enumerate(data.get("scenes") or []):
        scenes.append({"seq": i, "label": (s.get("title") or f"Scene {i+1}")[:60],
                       "title": s.get("title", ""), "still_prompt": (s.get("still_prompt") or "").strip(),
                       "motion_prompt": (s.get("motion_prompt") or s.get("still_prompt") or "").strip(),
                       "start_s": None, "end_s": None,
                       "duration_s": max(4.0, min(8.0, float(s.get("duration_s", 6) or 6)))})
    vo = data.get("voiceover") or []
    return {"title": data.get("title", "Untitled ad"), "style_base": data.get("style_base", ""),
            "aspect": data.get("aspect") if data.get("aspect") in ("16:9", "9:16") else "16:9",
            "voiceover": vo, "voiceover_text": " ".join(vo), "music": data.get("music", ""),
            "scenes": scenes}


def compile_md(md: str, *, model: str | None = None) -> dict[str, Any]:
    """Deterministic parse first (exact + free); fall back to the LLM only if it finds no scenes."""
    det = parse_markdown(md or "")
    if len(det.get("scenes") or []) >= 2 or not _key():
        return det
    try:
        llm = _llm_compile(md, model)
        return llm if llm.get("scenes") else det
    except Exception:  # noqa: BLE001 — never fail the import; deterministic is the floor
        return det
