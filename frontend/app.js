"use strict";
/* ============================ AI Influencer Factory — Studio SPA ============================ */
const $ = (s, r = document) => r.querySelector(s);
const esc = (x) => String(x ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt$ = (n) => "$" + Number(n || 0).toFixed(Number(n) < 1 ? 3 : 2);
const api = async (p, o) => { const r = await fetch(p, o); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || j.error || r.statusText); return j; };
const jbody = (p, m, b) => api(p, { method: m, headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) });
const jget = (p) => api(p);
const jpost = (p, b) => jbody(p, "POST", b);
const jpatch = (p, b) => jbody(p, "PATCH", b);
const jdel = (p) => api(p, { method: "DELETE" });
const splitList = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);

function toast(msg, kind = "") {
  const t = document.createElement("div"); t.className = "toast " + kind; t.innerHTML = `${icon(kind === "err" ? "x" : "check")}<span>${esc(msg)}</span>`;
  $("#toast-root").appendChild(t); setTimeout(() => t.remove(), 3500);
}

/* ---------------- SVG icons (Lucide-style) ---------------- */
const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 7.5h4M17 7.5h4M3 12h18M3 16.5h4M17 16.5h4"/>',
  folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7l-2-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z"/>',
  settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2Z"/><circle cx="12" cy="12" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  sparkles: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4Z"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  play: '<path d="m6 3 14 9-14 9V3Z"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  arrow: '<path d="M5 12h14M12 5l7 7-7 7"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
  wand: '<path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8 19 13M15 9h0M17.8 6.2 19 5M3 21l9-9M12.2 6.2 11 5"/>',
};
const icon = (name, cls = "icon") => `<svg class="${cls}" viewBox="0 0 24 24">${ICONS[name] || ""}</svg>`;

/* ---------------- state + data ---------------- */
const S = { summary: {}, channels: [], characters: [], episodes: [], channelId: null, ep: null, ddOpen: false };
let pollTimer = null;

async function loadCore() {
  const [summary, channels, characters] = await Promise.all([jget("/api/summary"), jget("/api/channels"), jget("/api/characters")]);
  S.summary = summary; S.channels = channels; S.characters = characters;
  ensureStyles();   // warm the art-style library (non-blocking) for the wizard + edit picker
}
const channel = () => S.channels.find((c) => c.channel_id === S.channelId) || S.channels[0];
const charById = (id) => S.characters.find((c) => c.character_id === id);

/* ---------------- router ---------------- */
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [a, b, c, d, e] = h.split("/");
  if (a === "quick") return { view: "quick", id: b, stage: c };   // one-off, outside channels
  if (a === "c" && b) return { cid: b, view: c || "overview", id: d, stage: e };
  return { view: "home" };
}
const go = (h) => { location.hash = h; };

async function route() {
  const r = parseHash();
  if (r.view === "quick") {
    if (r.id) { try { S.ep = await jget(`/api/episodes/${r.id}`); } catch { S.ep = null; } }
    else { S.ep = null; try { S.oneoffs = await jget("/api/oneoff"); } catch (e) { S.oneoffs = []; } }
    render(); managePolling(); return;
  }
  if (r.view === "home" || !S.channels.length) return render();
  if (r.cid && S.channelId !== r.cid) S.channelId = r.cid;
  if (!channel()) { S.channelId = S.channels[0]?.channel_id; }
  try { if (S.channelId) await reloadEpisodes(); } catch (e) {}
  if (r.view === "ep" && r.id) { try { S.ep = await jget(`/api/episodes/${r.id}`); } catch { S.ep = null; } }
  else S.ep = null;
  render();
  managePolling();
}
window.addEventListener("hashchange", route);

/* ---------------- shell ---------------- */
function railItem(view, ic, label) {
  const active = (parseHash().view === view) || (view === "episodes" && parseHash().view === "ep");
  return `<button class="rail-item ${active ? "active" : ""}" data-nav="c/${S.channelId}/${view}">${icon(ic)}<span>${label}</span></button>`;
}

function render() {
  if (!S.channels.length) return renderNoChannels();
  const ch = channel();
  const s = S.summary;
  const keyChip = s.fal_key_present ? `<span class="chip ok">${icon("check", "icon")} fal live</span>` : `<span class="chip warn">no fal key</span>`;
  $("#app").innerHTML = `
    <div class="shell">
      <div class="topbar">
        <div class="brand"><span class="logo">${icon("sparkles", "icon")}</span><b>Factory</b></div>
        <button class="chan-switch" data-dd>${icon("film", "icon")}<span>${esc(ch.name)}</span><span class="sub">${esc(ch.format)}</span>${icon("chevron", "icon")}</button>
        <div class="top-actions">
          <span class="chip">${icon("image","icon")} ${esc(s.image_model || "")}</span>
          ${keyChip}
          <button class="icon-btn" data-nav="c/${S.channelId}/settings" title="Channel settings">${icon("settings")}</button>
        </div>
      </div>
      <nav class="rail">
        ${railItem("overview", "grid", "Overview")}
        ${railItem("cast", "users", "Cast")}
        ${railItem("episodes", "film", "Episodes")}
        ${railItem("transitions", "sparkles", "Transitions")}
        <button class="rail-item ${parseHash().view === "quick" ? "active" : ""}" data-nav="quick">${icon("wand")}<span>Quick Video</span></button>
        <div class="rail-spacer"></div>
        <button class="rail-item" data-newchannel>${icon("plus")}<span>New channel</span></button>
        ${railItem("settings", "settings", "Settings")}
      </nav>
      <main class="main"><div class="page" id="page"></div></main>
    </div>`;
  if (S.ddOpen) renderDropdown();
  const v = parseHash().view;
  const page = $("#page");
  if (v === "cast") page.innerHTML = viewCast();
  else if (v === "characters") page.innerHTML = viewCharacter(parseHash().id);
  else if (v === "transitions") page.innerHTML = viewTransitions();
  else if (v === "episodes") page.innerHTML = viewEpisodes();
  else if (v === "quick") page.innerHTML = parseHash().id ? viewWorkspace() : viewQuickVideo();
  else if (v === "ep") page.innerHTML = viewWorkspace();
  else if (v === "settings") page.innerHTML = viewSettings();
  else page.innerHTML = viewOverview();
}

function renderDropdown() {
  const old = $(".dropdown"); if (old) old.remove();
  const dd = document.createElement("div"); dd.className = "dropdown";
  dd.innerHTML = S.channels.map((c) => `<button class="dd-item ${c.channel_id === S.channelId ? "active" : ""}" data-selchan="${c.channel_id}">
      <span class="dot" style="opacity:${c.channel_id === S.channelId ? 1 : 0}"></span><span>${esc(c.name)}</span><small style="margin-left:auto">${esc(c.platform)}</small></button>`).join("")
    + `<div class="dd-sep"></div><button class="dd-item" data-newchannel>${icon("plus","icon")}<span>New channel</span></button>`;
  $("#app").appendChild(dd);
}

function renderNoChannels() {
  $("#app").innerHTML = `<div style="display:grid;place-items:center;height:100vh;text-align:center">
    <div><span class="logo" style="width:48px;height:48px;margin:0 auto 16px">${icon("sparkles","icon")}</span>
    <h1 style="font-size:24px">AI Influencer Factory</h1>
    <p class="muted" style="margin:8px 0 20px">Create your first channel (series) to begin.</p>
    <button class="btn btn-primary" data-newchannel style="margin:0 auto">${icon("plus")} New channel</button></div></div>`;
}

/* ---------------- views ---------------- */
function viewOverview() {
  const ch = channel();
  const eps = S.episodes;
  return `<div class="page-head"><div><h1>${esc(ch.name)}</h1><div class="sub">${esc(ch.platform)} · ${esc(ch.format)} · ${ch.target_scene_count} scenes · ${esc(ch.art_style || "no art style set")}</div></div>
    <button class="btn btn-primary" data-newep>${icon("plus")} New episode</button></div>
    <div class="card" style="cursor:default;padding:18px 20px;background:var(--panel)"><div class="muted" style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Premise</div>${esc(ch.premise || "No premise yet — set one in Settings.")}</div>
    <div class="section-title">Cast</div>
    <div class="grid cast">${(ch.roster || []).map(rosterMini).join("") || `<p class="muted">No cast — add characters in the Cast tab.</p>`}</div>
    <div class="section-title">Recent episodes</div>
    ${eps.length ? `<div class="grid eps">${eps.slice(0, 6).map(epCard).join("")}</div>` : `<p class="muted">No episodes yet.</p>`}`;
}
function rosterMini(r) {
  const c = charById(r.character_id) || {};
  const img = (c.reference_image_urls || [])[0];
  return `<div class="card actor" data-nav="c/${S.channelId}/characters/${r.character_id}">
    ${img ? `<img src="${img}"/>` : `<div class="ph">${esc((r.name || "?")[0])}</div>`}
    <div class="meta"><b>${esc(r.name)}</b><div class="badges"><span class="mini-badge">${esc(r.role)}</span></div></div></div>`;
}

function viewCast() {
  return `<div class="page-head"><div><h1>Cast</h1><div class="sub">Reusable actors — reference photos lock identity across every scene.</div></div></div>
    <div class="grid cast">
      <button class="add-card" data-newchar>${icon("plus")}<span>New character</span></button>
      ${S.characters.map(actorCard).join("")}
    </div>`;
}
function actorCard(c) {
  const img = (c.reference_image_urls || [])[0];
  const traits = (c.personality && c.personality.traits || []).slice(0, 3).join(", ");
  return `<div class="card actor" data-nav="c/${S.channelId}/characters/${c.character_id}">
    ${img ? `<img src="${img}"/>` : `<div class="ph">${esc((c.name || "?")[0])}</div>`}
    <div class="meta"><b>${esc(c.name)}</b>
      <div class="badges">
        <span class="mini-badge ${c.has_voice ? "on" : ""}">${icon("mic", "icon")} ${c.has_voice ? "voice" : "no voice"}</span>
        <span class="mini-badge ${c.has_reference ? "on" : ""}">${(c.reference_image_urls || []).length} ref</span>
      </div></div></div>`;
}

function viewCharacter(id) {
  const c = charById(id); if (!c) return `<p class="muted">Character not found.</p>`;
  const p = c.personality || {}, v = c.voice || {};
  const refs = (c.reference_image_urls || []).map((u, i) => `<div class="ref-thumb"><img src="${u}"/><button class="ref-del" data-delref="${c.character_id}:${i}" title="Delete photo">${icon("x","icon")}</button></div>`).join("") || `<p class="muted">No reference photos.</p>`;
  return `<a class="ws-back" data-nav="c/${S.channelId}/cast">${icon("back")} Cast</a>
    <div class="page-head" style="margin-top:12px"><div><h1>${esc(c.name)}</h1><div class="sub">${esc(c.species)}</div></div>
      <div style="display:flex;gap:10px"><button class="btn btn-ghost" data-uploadref="${c.character_id}">${icon("upload")} Add photo</button>
      <button class="btn btn-ghost" data-editchar="${c.character_id}">${icon("edit")} Edit</button></div></div>
    <div class="char-detail">
      <div><div class="section-title" style="margin-top:0">Visual DNA</div><div class="ref-sheet">${refs}</div></div>
      <div>
        <div class="section-title" style="margin-top:0">Voice DNA</div>
        <div class="kv"><div class="k">Provider</div><div>${esc(v.provider || "—")}</div><div class="k">Voice ID</div><div>${esc(v.voice_id || "not set")}</div></div>
        <div class="section-title">Personality</div>
        ${p.backstory ? `<p style="font-size:13px">${esc(p.backstory)}</p>` : `<p class="muted">No personality set.</p>`}
        <div class="kv" style="margin-top:10px">
          ${p.traits && p.traits.length ? `<div class="k">Traits</div><div>${esc(p.traits.join(", "))}</div>` : ""}
          ${p.speech_style ? `<div class="k">Speech</div><div>${esc(p.speech_style)}</div>` : ""}
          ${p.catchphrases && p.catchphrases.length ? `<div class="k">Catchphrases</div><div>${esc(p.catchphrases.join("; "))}</div>` : ""}
        </div>
        <div class="section-title">Look / appearance</div>
        <p style="font-size:13px" class="muted">${esc(c.dna_prompt || "not set")}</p>
      </div>
    </div>`;
}

function viewTransitions() {
  const ch = channel(); if (!ch) return `<p class="muted">No channel.</p>`;
  const lib = ch.transitions || [], templates = ch.transition_templates || [];
  const gen = S.genTransition;
  const tiles = lib.length ? lib.map((t) => `
    <div class="tile done"><div class="thumb"><video src="${t.video_url}" muted loop playsinline
      onmouseover="this.play()" onmouseout="this.pause();this.currentTime=0"></video></div>
      <div class="row"><small>${esc(t.label || t.kind)}</small>
        <button class="reroll-link" data-deltrans="${t.id}">${icon("x","icon")} delete</button></div></div>`).join("")
    : `<p class="muted">No transitions yet — generate a few below. Each is made once (~$0.20) and reused in every episode.</p>`;
  const genRow = templates.map((tpl) => `<button class="btn btn-ghost btn-sm" data-gentrans="${tpl.kind}" ${gen ? "disabled" : ""}>${gen === tpl.kind ? spin() : icon("plus")} ${esc(tpl.label)}</button>`).join("");
  return `<div class="page-head"><div><h1>Transitions</h1><div class="sub">Reusable ~2s clips (with whoosh) auto-spliced between scenes at location cuts — made once, reused every episode.</div></div></div>
    <div class="grid tiles">${tiles}</div>
    <div class="section-title">Generate a transition <small class="muted">· ~$0.20 each, ~1 min</small></div>
    <div style="display:flex;flex-wrap:wrap;gap:8px">${genRow}</div>`;
}

function viewEpisodes() {
  return `<div class="page-head"><div><h1>Episodes</h1><div class="sub">${channel().name}</div></div>
    <button class="btn btn-primary" data-newep>${icon("plus")} New episode</button></div>
    ${S.episodes.length ? `<div class="grid eps">${S.episodes.map(epCard).join("")}</div>`
      : `<div class="empty">${icon("film")}<div>No episodes yet — create your first.</div></div>`}`;
}
function epCard(e) {
  const thumb = e.final_url || e.audio_cut_url || e.rough_cut_url;
  const first = (e.scenes || []).find((s) => s.still_url);
  return `<div class="card" data-nav="c/${S.channelId}/ep/${e.episode_id}">
    <div class="epcard-thumb">${first ? `<img src="${first.still_url}"/>` : `<div class="ph">${icon("film")}</div>`}</div>
    <div class="epcard-body"><b>${esc(e.title)}</b>
      <div class="epcard-meta"><span class="stbadge ${e.stage}">${esc(e.stage)}</span>
        <small>${e.generating ? "generating…" : esc(e.stage_status)}</small>
        <button class="icon-btn" data-delep="${e.episode_id}" title="delete" style="margin-left:auto;width:28px;height:28px">${icon("trash")}</button></div></div></div>`;
}

function viewSettings() {
  const ch = channel();
  return `<div class="page-head"><div><h1>Channel settings</h1><div class="sub">${esc(ch.name)}</div></div>
    <button class="btn btn-ghost" data-editchannel="${ch.channel_id}">${icon("edit")} Edit channel</button></div>
    <div class="kv" style="max-width:640px">
      <div class="k">Platform</div><div>${esc(ch.platform)}</div>
      <div class="k">Format</div><div>${esc(ch.format)}</div>
      <div class="k">Art style</div><div>${esc(ch.art_style || "— (empty: images default to photoreal)")}</div>
      <div class="k">Premise</div><div>${esc(ch.premise || "—")}</div>
      <div class="k">Scenes / duration</div><div>${ch.target_scene_count} · ${ch.target_duration_s}s</div>
      <div class="k">Video budget</div><div>${ch.video_budget} hero shots</div>
      <div class="k">Writer</div><div>${esc(ch.writer_provider)}</div>
      <div class="k">Narrator voice</div><div>${esc(ch.narrator_voice_id || "—")}</div>
      <div class="k">Cast</div><div>${(ch.roster || []).map((r) => esc(r.name) + " (" + esc(r.role) + ")").join(", ") || "—"}</div>
    </div>`;
}

/* ---------------- episode workspace ---------------- */
const STAGES = [["setup", "Setup"], ["idea", "Idea"], ["script", "Script"], ["refs", "Refs"], ["scenes", "Scenes"], ["audio", "Audio"], ["assembly", "Assembly"], ["done", "Done"]];
function viewWorkspace() {
  const e = S.ep; if (!e) return `<p class="muted">Episode not found.</p>`;
  // one-off videos live outside channels and skip Setup/Idea/Script (compiled from the script)
  const stages = e.oneoff ? STAGES.filter(([k]) => !["setup", "idea", "script"].includes(k)) : STAGES;
  const base = e.oneoff ? `quick/${e.episode_id}` : `c/${S.channelId}/ep/${e.episode_id}`;
  const backNav = e.oneoff ? "quick" : `c/${S.channelId}/episodes`;
  const idx = stages.findIndex(([k]) => k === e.stage);
  const viewed = (parseHash().stage && stages.some(([k]) => k === parseHash().stage)) ? parseHash().stage : e.stage;
  const readOnly = viewed !== e.stage;
  const steps = stages.map(([k, label], i) => {
    const reached = i <= idx || e.stage === "done";
    const cls = (i < idx || e.stage === "done") ? "done" : (i === idx ? "current" : "");
    const viewing = k === viewed ? "viewing" : "";
    const num = (i < idx || e.stage === "done") ? icon("check", "icon") : (i + 1);
    const attr = reached ? `data-nav="${base}/${k}"` : "disabled";
    return `<button class="step ${cls} ${viewing}" ${attr} style="${reached ? "" : "opacity:.45;cursor:default"}"><span class="num">${num}</span>${label}</button>`;
  }).join(`<span class="step-sep">${icon("arrow", "icon")}</span>`);
  const banner = readOnly ? `<div class="chip" style="margin-bottom:14px">${icon("check","icon")} Viewing an approved stage (read-only) · <button class="linkish" data-nav="${base}/${e.stage}">back to current</button></div>` : "";
  const meta = e.oneoff
    ? `<span>${e.scene_count} scenes</span><span>${esc((e.config || {}).aspect || "16:9")}</span>${e.has_voiceover ? "<span>voiceover</span>" : ""}<span>spent ${fmt$(e.spent_usd)}</span>`
    : `<span>${e.cast.length} cast</span><span>${e.scene_count} scenes</span><span>writer ${esc(e.writer_model || "—")}</span><span>spent ${fmt$(e.spent_usd)}</span>`;
  return `<a class="ws-back" data-nav="${backNav}">${icon("back")} ${e.oneoff ? "Quick Video" : "Episodes"}</a>
    <div class="ws-head" style="margin-top:12px"><h1>${esc(e.title)}</h1>
      <div class="ws-meta">${meta}</div></div>
    <div class="stepper">${steps}</div>
    ${banner}
    <div class="stage-body" id="stagebody">${renderStage(e, viewed, readOnly)}</div>`;
}

/* ---------------- Quick Video (one-off from a script) ---------------- */
const SAMPLE_MD = "# My Ad — Prompt Pack\n\n## STYLE BASE (append to every prompt)\n> Cinematic, premium brand film, moody lighting.\n\n## SCENE 1 — HOOK (0–8s) · \"Your headline\"\n**Imagen (still):**\n> A striking hero image. [STYLE BASE]\n**Veo (motion):**\n> Slow push-in. Ambient hum, no dialogue. [STYLE BASE]\nOn-screen text: **Your headline.**\n\n## VOICEOVER SCRIPT\n1. \"Your first narration line.\"\n2. \"Your closing line.\"";
function viewQuickVideo() {
  const list = (S.oneoffs || []).map((e) => `<button class="ep-card" data-nav="quick/${e.episode_id}">
      <div class="ep-card-top"><b>${esc(e.title)}</b><span class="chip">${esc(e.stage)}</span></div>
      <div class="muted">${e.scene_count} scenes · ${esc((e.config || {}).aspect || "16:9")} · spent ${fmt$(e.spent_usd)}</div>
      ${e.final_url ? `<span class="chip ok">${icon("check","icon")} rendered</span>` : ""}</button>`).join("");
  return `<div class="page-head"><h1>${icon("wand")} Quick Video</h1>
      <p class="muted">Paste a Markdown prompt-pack (scenes with image + motion prompts, optional voiceover). It compiles into the same keyframe→video→assembly pipeline — outside channels. No cast needed.</p></div>
    <div class="qv-form">
      <div class="field"><label>Script (Markdown)</label><textarea id="qv-md" rows="12" placeholder="Paste your prompt pack…" oninput="S.qvDraft=this.value">${esc(S.qvDraft || "")}</textarea></div>
      <div class="field"><label>Product assets <small class="muted">to show the real tool: add a scene with <code>**Asset:** dashboard.png</code> (optional <code>**Motion:** zoom in</code>) and attach the file here</small></label>
        <input type="file" id="qv-assets" multiple accept="image/*,video/*" onchange="qvAddAssets(this.files)"/>
        <div id="qv-asset-list" style="margin-top:8px">${qvAssetChips()}</div></div>
      <div class="row-3">
        <div class="field"><label>Aspect</label><select id="qv-aspect"><option value="16:9">16:9 landscape</option><option value="9:16">9:16 vertical</option></select></div>
        <div class="field"><label>Resolution</label><select id="qv-res"><option value="720p">720p</option><option value="1080p">1080p</option></select></div>
        <div class="field"><label>Voice (VO)</label><input id="qv-voice" value="Rachel" placeholder="narrator voice"/></div>
      </div>
      <label class="chk"><input type="checkbox" id="qv-music" checked/> Background music bed</label>
      <div style="margin-top:14px;display:flex;gap:10px"><button class="btn btn-primary" data-qvcreate>${icon("wand")} Compile &amp; create</button>
        <button class="btn btn-ghost" onclick="document.getElementById('qv-md').value=SAMPLE_MD">Load sample</button></div>
    </div>
    ${list ? `<div class="section-title">Your videos</div><div class="ep-grid">${list}</div>` : ""}`;
}
function qvAssetChips() {
  const names = Object.keys(S.qvAssets || {});
  if (!names.length) return `<span class="muted" style="font-size:12.5px">No files attached.</span>`;
  return names.map((n) => `<span class="chip">${icon("image","icon")} ${esc(n)}</span>`).join(" ")
    + ` <button class="linkish" onclick="S.qvAssets={};document.getElementById('qv-asset-list').innerHTML=qvAssetChips()">clear</button>`;
}
async function qvAddAssets(files) {
  S.qvAssets = S.qvAssets || {};
  for (const f of files) {
    const b64 = await new Promise((r) => { const rd = new FileReader(); rd.onload = () => r(rd.result.split(",")[1]); rd.readAsDataURL(f); });
    S.qvAssets[f.name] = b64;
  }
  const el = document.getElementById("qv-asset-list"); if (el) el.innerHTML = qvAssetChips();
}
async function quickCreate() {
  const md = $("#qv-md").value.trim();
  if (!md) { toast("Paste a script first", "err"); return; }
  const body = { md, aspect: $("#qv-aspect").value, resolution: $("#qv-res").value, voice: $("#qv-voice").value.trim() || "Rachel", music: $("#qv-music").checked, assets: S.qvAssets || {} };
  try { const ep = await jpost("/api/oneoff", body); S.qvDraft = ""; S.qvAssets = {}; toast("Compiled ✨"); go(`quick/${ep.episode_id}`); }
  catch (err) { toast(err.message, "err"); }
}

function renderStage(e, stage, readOnly) {
  stage = stage || e.stage;
  const errBar = (!readOnly && e.stage_error) ? `<div class="err-banner">${icon("x", "icon")} ${esc(e.stage_error)}</div>` : "";
  const gen = !readOnly && e.generating;
  switch (stage) {
    case "setup": return errBar + stageSetup(e, gen, readOnly);
    case "idea": return errBar + stageIdea(e, gen, readOnly);
    case "script": return errBar + stageScript(e, gen, readOnly);
    case "refs": return errBar + stageRefs(e, gen, readOnly);
    case "scenes": return errBar + stageScenes(e, gen, readOnly);
    case "audio": return errBar + stageAudio(e, gen, readOnly);
    case "assembly": return errBar + stageAssembly(e, gen, readOnly);
    case "done": return stageDone(e);
    default: return "";
  }
}

/* --- Setup (step 0: format config) --- */
function setupSuggestScenes(dur) { return Math.max(3, Math.min(30, Math.round((+dur || 60) / 6))); }
function setupCost(n, res, music) { const ps = res === "1080p" ? 0.08 : 0.05; return n * 6 * ps + n * 0.04 + (music ? 0.03 : 0); }
function setupEstHtml(n, res, music) {
  return `Estimated generation cost: <b>~$${setupCost(n, res, music).toFixed(2)}</b> <span class="muted">· ${n} scenes · ${res} · ${music ? "music" : "no music"}</span>`;
}
function updateSetupEst() {
  const n = +($("#cfg-scenes").value || 0), res = $("#cfg-res").value, music = $("#cfg-music").checked, dur = +($("#cfg-duration").value || 0);
  const sug = $("#cfg-scene-sugg"); if (sug) sug.textContent = `≈${setupSuggestScenes(dur)} for ${dur || 0}s`;
  const est = $("#cfg-est"); if (est) est.innerHTML = setupEstHtml(n, res, music);
}
function setLayout(v) {
  $("#cfg-layout").value = v;
  document.querySelectorAll('[data-setupseg="layout"]').forEach((b) => b.classList.toggle("on", b.dataset.val === v));
}
function applyPreset(id) {
  const p = (S.ep.platform_presets || []).find((x) => x.id === id); if (!p) return;
  S.setupPreset = id;
  if (p.layout) setLayout(p.layout);
  if (p.duration_s) { $("#cfg-duration").value = p.duration_s; $("#cfg-scenes").value = setupSuggestScenes(p.duration_s); }
  if (p.resolution) $("#cfg-res").value = p.resolution;
  if (p.qc_threshold) $("#cfg-qc").value = String(p.qc_threshold);
  if (p.pacing) $("#cfg-pacing").value = p.pacing;
  if (typeof p.music === "boolean") $("#cfg-music").checked = p.music;
  if (p.transitions) $("#cfg-trans").checked = p.transitions !== "off";
  document.querySelectorAll(".preset-btn").forEach((b) => b.classList.toggle("on", b.dataset.preset === id));
  updateSetupEst();
}
function stageSetup(e, gen, ro) {
  const c = e.config || {};
  S.setupPreset = c.platform;
  const presets = (e.platform_presets || []).filter((p) => p.id !== "custom");
  const seg = (id, val, opts) => opts.map(([v, l]) => `<button type="button" class="seg-btn ${val === v ? "on" : ""}" data-setupseg="${id}" data-val="${v}" onclick="setLayout('${v}')">${l}</button>`).join("");
  const configured = e.config_saved && e.stage !== "setup";
  const warn = (e.config_saved && ["refs", "scenes", "audio", "assembly", "done"].includes(e.stage))
    ? `<p class="hint">${icon("x","icon")} Changing layout or resolution won't retro-change stills/clips already generated — re-roll those to apply the new format.</p>` : "";
  const opt = (v, l, cur) => `<option value="${v}" ${String(cur) === String(v) ? "selected" : ""}>${l}</option>`;
  return `<p class="stage-intro">Set the format for <b>this episode</b> — everything downstream (script length, framing, render) follows from here. Defaults come from the channel; a preset stamps a platform in one click.</p>
    <div class="cfg-presets">${presets.map((p) => `<button type="button" class="preset-btn" data-preset="${p.id}" onclick="applyPreset('${p.id}')">${icon("film","icon")} ${esc(p.label)}</button>`).join("")}</div>
    <div class="cfg-form">
      <div class="field"><label>Layout</label><div class="seg">${seg("layout", c.layout, [["landscape", "▭ Landscape 16:9"], ["portrait", "▮ Portrait 9:16"]])}</div><input type="hidden" id="cfg-layout" value="${c.layout}"/></div>
      <div class="row-3">
        <div class="field"><label>Length (seconds)</label><input type="number" id="cfg-duration" value="${c.duration_s}" min="8" max="600" oninput="updateSetupEst()"/></div>
        <div class="field"><label>Scenes <small class="muted" id="cfg-scene-sugg">≈${setupSuggestScenes(c.duration_s)} for ${c.duration_s}s</small></label><input type="number" id="cfg-scenes" value="${c.scene_count}" min="3" max="30" oninput="updateSetupEst()"/></div>
        <div class="field"><label>Resolution</label><select id="cfg-res" onchange="updateSetupEst()">${opt("720p", "720p (cheaper)", c.resolution)}${opt("1080p", "1080p (×1.6 cost)", c.resolution)}</select></div>
      </div>
      <div class="row-3">
        <div class="field"><label>Language</label><input id="cfg-lang" value="${esc(c.language || "")}"/></div>
        <div class="field"><label>Pacing</label><select id="cfg-pacing">${opt("dialogue", "Dialogue-heavy", c.pacing)}${opt("balanced", "Balanced", c.pacing)}${opt("action", "Action-heavy", c.pacing)}</select></div>
        <div class="field"><label>Script QC bar</label><select id="cfg-qc">${opt("60", "Lax (60)", c.qc_threshold)}${opt("75", "Default (75)", c.qc_threshold)}${opt("85", "Strict (85)", c.qc_threshold)}</select></div>
      </div>
      <div class="row-2" style="margin:4px 0 6px">
        <label class="chk"><input type="checkbox" id="cfg-music" ${c.music ? "checked" : ""} onchange="updateSetupEst()"/> Background music bed</label>
        <label class="chk"><input type="checkbox" id="cfg-trans" ${c.transitions !== "off" ? "checked" : ""}/> Auto transitions at scene cuts</label>
      </div>
      ${warn}
      <div class="cfg-est" id="cfg-est">${setupEstHtml(c.scene_count, c.resolution, c.music)}</div>
      <button class="btn btn-primary" data-saveconfig>${icon("check")} ${configured ? "Update setup" : "Save & start ideas"}</button>
    </div>`;
}

function modalRevise() {
  const q = S.ep.script_qc || {};
  const notes = (q.notes || []).join("\n");
  const body = `<p class="hint">The writer will apply these notes to the <b>current</b> script (not start over), then re-score it. Edit them or add your own direction — one note per line.</p>
    <div class="field"><label>Feedback / direction</label><textarea id="rev-notes" rows="10">${esc(notes)}</textarea></div>`;
  openModal("Revise with feedback", body, async () => {
    $("#m-msg").className = "hint"; $("#m-msg").textContent = "Revising + re-judging… (up to a minute)";
    S.ep = await jpost(`/api/episodes/${S.ep.episode_id}/script/revise`,
                       { notes: $("#rev-notes").value.split("\n").map((x) => x.trim()).filter(Boolean) });
    render(); managePolling(); toast(`Revised — QC now ${(S.ep.script_qc || {}).score ?? "?"}/100`);
  }, "Revise this script");
}

/* --- Idea --- */
function stageIdea(e, gen, ro) {
  if (ro) return e.idea && e.idea.title
    ? `<div class="idea" style="max-width:560px"><div class="top"><b>${esc(e.idea.title)}</b></div><div class="log">${esc(e.idea.logline || "")}</div>${e.idea.hook ? `<div class="hook"><span>hook</span>${esc(e.idea.hook)}</div>` : ""}${(e.idea.beats || []).length ? `<ul>${e.idea.beats.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}</div>`
    : `<p class="muted">No idea recorded.</p>`;
  const brief = `<div class="field" style="max-width:640px"><label>Idea brief (optional — steer the concepts)</label>
    <textarea id="idea-brief" rows="2" placeholder="e.g. a rainy-night stakeout; introduce a cat burglar">${esc(e.idea_brief || "")}</textarea></div>`;
  if (e.stage_status === "awaiting_review" && e.idea_candidates.length) {
    return `<p class="stage-intro">Pick the best idea — the model that wrote it goes on to write the script.</p>
      <div class="idea-col">${e.idea_candidates.map(ideaCard).join("")}</div>
      <div style="margin:18px 0">${brief}</div>
      <button class="btn btn-ghost" data-runidea>${icon("refresh")} Regenerate all models</button>`;
  }
  return `<p class="stage-intro">A panel of models (Opus 4.8 · GPT-5.5 · DeepSeek V4 Pro · GLM 5.2) each proposes an idea at once, grounded in the channel premise + cast. Near-free.</p>
    ${brief}<div style="margin-top:14px"><button class="btn btn-primary" data-runidea ${gen ? "disabled" : ""}>${gen ? spin() : icon("sparkles")} ${gen ? "Generating…" : "Generate ideas"}</button></div>`;
}
function ideaCard(x, i) {
  const beats = (x.beats || []).map((b) => `<li>${esc(b)}</li>`).join("");
  return `<div class="idea"><div class="top"><b>${esc(x.title || "Untitled")}</b>${x.model_label ? `<span class="model-badge">${esc(x.model_label)}</span>` : ""}</div>
    <div class="log">${esc(x.logline || "")}</div>${x.hook ? `<div class="hook"><span>hook</span>${esc(x.hook)}</div>` : ""}
    ${beats ? `<ul>${beats}</ul>` : ""}<div class="pick"><button class="btn btn-primary btn-sm" data-pickidea="${i}">${icon("check")} Use this</button></div></div>`;
}

/* --- Script --- */
function qcScorecard(e) {
  const q = e.script_qc || {};
  if (q.score == null) return "";
  const dims = [["hook", "Hook", 25], ["narrative", "Narrative", 30], ["ending", "Ending", 20], ["comedy", "Comedy", 10], ["virality", "Virality", 15]];
  const bd = q.breakdown || {};
  const bars = dims.map(([k, label, w]) => {
    const v = Math.max(0, Math.min(10, Number(bd[k] || 0)));
    return `<div class="qc-dim"><span class="qc-label">${label} <small class="muted">×${w}</small></span>
      <span class="qc-bar"><span class="qc-fill ${v >= 7.5 ? "good" : v >= 5 ? "mid" : "bad"}" style="width:${v * 10}%"></span></span>
      <span class="qc-val">${v}</span></div>`;
  }).join("");
  const notes = (q.notes || []).length ? `<ul class="qc-notes">${q.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : "";
  return `<div class="qc-card ${q.passed ? "pass" : "fail"}">
    <div class="qc-head"><b>Script QC ${q.score}/100</b>
      <span class="chip">${q.passed ? `${icon("check","icon")} passed` : `${icon("x","icon")} below ${q.threshold ?? 75}`}</span>
      <small class="muted">${q.iterations || 1} draft${(q.iterations || 1) > 1 ? "s" : ""} · judge ${esc(q.judge_model || "—")}</small></div>
    ${bars}${notes}</div>`;
}
function stageScript(e, gen, ro) {
  if (ro) return e.scenes.length
    ? `${qcScorecard(e)}<div class="script">${e.scenes.map((s) => sceneRow(s, false)).join("")}</div>
       ${actionBar([`<button class="btn btn-primary" data-reopen="script">${icon("edit")} Edit / re-write script</button>`])}`
    : `<p class="muted">No script recorded.</p>`;
  const chosen = e.idea && e.idea.title ? `<div class="stage-intro"><b>${esc(e.idea.title)}</b> — ${esc(e.idea.logline || "")}</div>` : "";
  if (e.stage_status === "awaiting_review" && e.scenes.length) {
    const hasNotes = ((e.script_qc || {}).notes || []).length;
    const prev = e.script_prev || {};
    const canRevert = prev.scenes > 0;
    const bar = gen
      ? `<div class="stage-intro">${spin()} Writing + QC-judging the script… (may take a minute — it revises until it passes)</div>`
      : actionBar([`<button class="btn btn-primary" data-approve>${icon("check")} Approve script</button>`,
          ...(hasNotes ? [`<button class="btn btn-ghost" data-revise>${icon("sparkles")} Revise with feedback</button>`] : []),
          ...(canRevert ? [`<button class="btn btn-ghost" data-revertscript title="Swap back to the previous version">${icon("back")} Revert to previous${prev.score != null ? ` (QC ${prev.score})` : ""}</button>`] : []),
          `<button class="btn btn-ghost" data-run>${icon("refresh")} Rewrite from scratch</button>`]);
    return `${chosen}${gen ? "" : qcScorecard(e)}<div class="section-title" style="margin-top:0">Script — ${e.scenes.length} scenes ${gen ? "" : `<small class="muted">· click <b>edit</b> on any scene</small>`}</div>
      <div class="script"${gen ? ' style="opacity:.45;pointer-events:none"' : ""}>${e.scenes.map((s) => sceneRow(s, !gen)).join("")}</div>
      ${bar}`;
  }
  return `${chosen}<p class="stage-intro">Expand the idea into a scene-by-scene script (dialogue, narration, shot types). Near-free.</p>
    <button class="btn btn-primary" data-run ${gen ? "disabled" : ""}>${gen ? spin() : icon("edit")} ${gen ? "Writing…" : "Write script"}</button>`;
}
function sceneRow(s, editable) {
  const nm = (id) => (charById(id) || {}).name || "?";
  const edit = editable ? `<button class="reroll-link" data-editscene="${s.seq}">${icon("edit","icon")} edit</button>` : "";
  const motion = s.motion || s.action || "";
  const frame = s.frozen_beat && s.frozen_beat.trim() && s.frozen_beat !== motion;
  return `<div class="sc"><div class="h"><b>${esc(s.heading || "scene")}</b><span class="shot-tag shot-${s.shot_type}">${shotLabel(s.shot_type)}</span><small>${s.duration_s}s</small>${edit}</div>
    ${frame ? `<div class="act"><span class="sc-lbl">Frame</span>${esc(s.frozen_beat)}</div>` : ""}
    <div class="act">${frame ? `<span class="sc-lbl">Action</span>` : ""}${esc(motion)}</div>${s.narration ? `<div class="vo">${icon("mic","icon")} ${esc(s.narration)}</div>` : ""}
    ${(s.dialogue || []).map((d) => `<div class="line"><b>${esc(nm(d.speaker))}</b>: ${esc(d.line)}${d.delivery ? ` <em>(${esc(d.delivery)})</em>` : ""}</div>`).join("")}</div>`;
}
function modalScene(seq) {
  const s = (S.ep.scenes || [])[seq]; if (!s) return;
  const shots = ["broll", "still_kenburns", "lipsync_still", "hero_video"];
  const opts = (sel, list, val = (x) => x, lbl = (x) => x) => list.map((x) => `<option value="${esc(val(x))}" ${val(x) === sel ? "selected" : ""}>${esc(lbl(x))}</option>`).join("");
  const dlgRows = (s.dialogue || []).map((d, i) => `<div class="row-2" data-dlg="${i}">
      <div class="field"><label>Speaker</label><select class="d-spk">${opts(d.speaker, S.characters, (c) => c.character_id, (c) => c.name)}</select></div>
      <div class="field"><label>Line (${esc(S.ep.language || "")})</label><input class="d-line" value="${esc(d.line || "")}"/></div></div>`).join("");
  const body = `
    <div class="field"><label>Heading (location - time)</label><input id="s-head" value="${esc(s.heading || "")}"/></div>
    <div class="field"><label>Frame — the keyframe still: setup, who's where, props, expressions, lighting (no motion words)</label><textarea id="s-frozen" rows="4">${esc(s.frozen_beat || s.action || "")}</textarea></div>
    <div class="field"><label>Action — what MOVES in the shot: the motion + comic timing</label><textarea id="s-act" rows="3">${esc(s.motion || s.action || "")}</textarea></div>
    <div class="row-3"><div class="field"><label>Camera</label><input id="s-cam" value="${esc(s.camera || "")}"/></div>
      <div class="field"><label>Shot type</label><select id="s-shot">${opts(s.shot_type, shots, (x) => x, shotLabel)}</select></div>
      <div class="field"><label>Duration (s)</label><input type="number" step="0.5" id="s-dur" value="${s.duration_s || 5}"/></div></div>
    <div class="field"><label>Narration / VO (optional)</label><textarea id="s-narr" rows="2">${esc(s.narration || "")}</textarea></div>
    <div class="field"><label>Dialogue</label><div id="s-dlg">${dlgRows || `<span class="muted">No dialogue in this scene.</span>`}</div></div>`;
  openModal(`Edit scene ${seq + 1}`, body, async () => {
    const scenes = (S.ep.scenes || []).map((x) => ({ ...x }));
    const ns = scenes[seq];
    ns.heading = $("#s-head").value; ns.camera = $("#s-cam").value;
    ns.motion = ns.action = $("#s-act").value;     // Action = motion; action kept for legacy paths
    ns.frozen_beat = $("#s-frozen").value;         // your explicit keyframe (backend re-derives only if it has motion words)
    ns.shot_type = $("#s-shot").value; ns.duration_s = +$("#s-dur").value; ns.narration = $("#s-narr").value;
    ns.dialogue = [...document.querySelectorAll("#s-dlg [data-dlg]")].map((r, i) => ({
      speaker: r.querySelector(".d-spk").value, line: r.querySelector(".d-line").value.trim(),
      delivery: ((s.dialogue || [])[i] || {}).delivery || "",
    })).filter((d) => d.line);
    S.ep = await jpatch(`/api/episodes/${S.ep.episode_id}/artifact`, { scenes });
    render(); toast("Scene updated");
  }, "Save scene");
}
const shotLabel = (t) => ({ broll: "b-roll", still_kenburns: "ken burns", lipsync_still: "lip-sync", hero_video: "hero video", asset: "asset" }[t] || t);

/* --- Refs (preview + live batch grid) --- */
function stageRefs(e, gen, ro) {
  if (ro) return `<div class="grid tiles">${e.scenes.map((s) => refTile(e, s, false, true)).join("")}</div>
    ${actionBar([`<button class="btn btn-primary" data-reopen="refs">${icon("edit")} Edit / re-roll references</button>`])}`;
  const unit = Number(e.image_unit_cost || 0);
  const styleBox = `<div class="field" style="max-width:640px"><label>Style note (optional — applied to every image)</label>
    <textarea id="style-note" rows="2" placeholder="e.g. warmer lighting; more exaggerated cartoon proportions">${esc(e.style_note || "")}</textarea></div>`;
  const partial = !gen && !e.refs_batch_done && e.refs_done_count > 1;   // batch crashed midway
  // batch running / done / partially done → live grid
  if (gen || e.refs_batch_done || partial) {
    const done = e.refs_done_count, total = e.scene_count;
    const progress = gen ? progBar(done, total, "Generating reference images", e.spent_usd) : "";
    const grid = `<div class="grid tiles">${e.scenes.map((s) => refTile(e, s, gen)).join("")}</div>`;
    let bar = "";
    if (!gen && e.refs_batch_done) bar = actionBar([`<button class="btn btn-primary" data-approve>${icon("check")} Approve references</button>`, `<button class="btn btn-ghost" data-runrefs>${icon("refresh")} Start over</button>`]);
    else if (partial) bar = actionBar([`<button class="btn btn-primary" data-refsbatch>${icon("refresh")} Resume — generate the rest</button>`]);
    return `${progress}<div class="section-title" style="margin-top:0">Reference images (${done}/${total})</div>${grid}${bar}`;
  }
  // preview ready → approve look / tweak
  if (e.stage_status === "awaiting_review") {
    const p = e.scenes.find((s) => s.still_url) || e.scenes[0] || {};
    const n = Math.max(0, e.scene_count - 1); const cost = (n * unit).toFixed(2);
    return `<p class="stage-intro">Preview one shot to approve the look (character + art style). Then generate the rest — you'll watch them fill in.</p>
      <div class="preview-cap">Scene ${(p.seq ?? 0) + 1}: ${esc(p.heading || "")}</div>
      ${p.still_url ? `<div class="preview-hero"><img src="${p.still_url}?t=${Date.now()}"/></div>` : `<div class="err-banner">Preview failed — regenerate.</div>`}
      ${styleBox}
      <div style="display:flex;gap:10px;margin-top:14px"><button class="btn btn-primary" data-refsbatch>${icon("check")} Looks good — generate all ${n} (~$${cost})</button>
      <button class="btn btn-ghost" data-runrefs>${icon("refresh")} Regenerate preview (~${fmt$(unit)})</button></div>`;
  }
  // initial
  return `<p class="stage-intro">Generate ONE preview to approve the look (character identity + channel art style), then batch the rest at ~${fmt$(unit)}/image via Gemini.</p>
    ${styleBox}<div style="margin-top:14px"><button class="btn btn-primary" data-runrefs ${gen ? "disabled" : ""}>${gen ? spin() : icon("image")} ${gen ? "Generating…" : "Generate preview"}</button></div>`;
}
function refTile(e, s, gen, ro) {
  const ri = s.reference_image || {};
  const ok = ri.status === "ok" && s.still_url;
  let state = "queued", inner = `<div class="spin-lg"></div>`;
  if (ok) { state = "done"; inner = `<img src="${s.still_url}?t=${e.updated_at}"/>`; }
  else if (ri.status === "failed") { state = "fail"; inner = `<div class="fail">${icon("x","icon")} failed</div>`; }
  else if (gen) { state = "working"; }
  const canReroll = (ok || ri.status === "failed") && !gen && !ro;
  const qc = ri.qc;
  const qcBadge = qc && !qc.passed ? `<span class="qc-flag" title="${esc((qc.reasons || []).join(" · "))}">⚠ QC</span>` : "";
  return `<div class="tile ${state}"><div class="thumb">${inner}${qcBadge}</div>
    <div class="row"><small>#${s.seq + 1}</small><span class="shot-tag shot-${s.shot_type}">${shotLabel(s.shot_type)}</span>
      ${canReroll ? `<button class="reroll-link" data-refedit="${s.seq}">${icon("edit","icon")} edit</button>` : ""}
      ${canReroll ? `<button class="reroll-link" data-reroll="${s.seq}">re-roll</button>` : ""}</div></div>`;
}
function modalRefEdit(seq) {
  const s = (S.ep.scenes || [])[seq]; if (!s) return;
  const ri = s.reference_image || {};
  const models = S.ep.image_models || [];
  const cur = ri.model || (models[0] && models[0].id) || "";
  const img = s.still_url
    ? `<img src="${s.still_url}?t=${Date.now()}" style="width:100%;border-radius:10px;border:1px solid var(--border)"/>`
    : `<div class="err-banner">Image failed — edit the prompt/model and regenerate.</div>`;
  const body = `${img}
    <div class="field" style="margin-top:12px"><label>Image prompt — edit to change what's drawn</label>
      <textarea id="ref-prompt" rows="6">${esc(ri.prompt || "")}</textarea></div>
    <div class="field"><label>Image model</label>
      <select id="ref-model">${models.map((m) => `<option value="${m.id}" ${m.id === cur ? "selected" : ""}>${esc(m.label)} — ${fmt$(m.cost)}</option>`).join("")}</select></div>`;
  openModal(`Scene ${seq + 1} — reference image`, body, async () => {
    $("#m-msg").className = "hint"; $("#m-msg").textContent = "Regenerating (~15s)…";
    S.ep = await jpost(`/api/episodes/${S.ep.episode_id}/scene/${seq}/reroll`,
                       { prompt: $("#ref-prompt").value.trim(), model: $("#ref-model").value });
    render(); toast("Reference regenerated");
  }, "Regenerate");
}

/* --- Scenes (per-scene control grid) --- */
const SCENE_UNIT = 0.30;   // ~6s Veo clip @720p + audio
function stageScenes(e, gen, ro) {
  if (ro) return `${e.rough_cut_url ? `<video class="player" controls preload="metadata" src="${e.rough_cut_url}?t=${e.updated_at}"></video>` : ""}<div class="grid tiles">${e.scenes.map((s) => sceneTile(e, s, false, true)).join("")}</div>`;
  S.sceneSel = S.sceneSel || new Set();
  const done = e.scenes_done_count, total = e.scene_count;
  const progress = gen ? progBar(done, total, "Rendering scenes", e.spent_usd) : "";
  const player = (!gen && e.rough_cut_url) ? `<video class="player" controls preload="metadata" src="${e.rough_cut_url}?t=${e.updated_at}"></video>` : "";
  const grid = `<div class="grid tiles">${e.scenes.map((s) => sceneTile(e, s, gen)).join("")}</div>`;
  const sel = [...S.sceneSel].filter((n) => e.scenes.some((s) => s.seq === n));
  const remaining = e.scenes.filter((s) => (s.clip || {}).status !== "ok");
  const allDone = total > 0 && done >= total;
  const controls = gen ? `<p class="stage-intro">${spin()} Generating — fills in live; you can leave and come back.</p>` : `<div class="scene-controls">
      <label class="chk"><input type="checkbox" data-selall ${sel.length === total && total ? "checked" : ""}/> Select all</label>
      <button class="btn btn-primary" data-genselected ${sel.length ? "" : "disabled"}>${icon("film")} Generate selected (${sel.length}) · ~$${(sel.length * SCENE_UNIT).toFixed(2)}</button>
      ${remaining.length ? `<button class="btn btn-ghost" data-genremaining>${icon("film")} Generate ${remaining.length} remaining · ~$${(remaining.length * SCENE_UNIT).toFixed(2)}</button>` : ""}
      ${allDone ? `<button class="btn btn-primary" data-approve>${icon("check")} Approve cut</button>` : ""}</div>`;
  return `${progress}${player}
    <div class="section-title" style="margin-top:0">Scenes (${done}/${total}) <small class="muted">· click a shot to edit its prompt &amp; generate, or tick multiple and generate together</small></div>
    ${controls}${grid}`;
}
function sceneTile(e, s, gen, ro) {
  const clip = s.clip || {}; const okClip = clip.status === "ok"; const failed = clip.status === "failed";
  const isAsset = s.asset;
  const sel = (S.sceneSel || new Set()).has(s.seq);
  const working = gen && !okClip;
  const inner = s.still_url ? `<img src="${s.still_url}?t=${e.updated_at}"/>` : `<div class="spin-lg"></div>`;
  const clipTag = s.clip_url ? `<span class="clip-tag">${icon("play","icon")} clip</span>` : "";
  const assetTag = isAsset ? `<span class="asset-tag">${icon("image","icon")} ${esc(s.asset_kind || "asset")}</span>` : "";
  const qc = clip.qc;
  const qcBadge = qc && !qc.passed ? `<span class="qc-flag" title="${esc((qc.reasons || []).join(" · "))}">⚠ QC</span>` : "";
  const overlay = (working ? `<div class="spin-lg" style="position:absolute"></div>` : (failed ? `<div class="fail">${icon("x","icon")} failed</div>` : "")) + qcBadge;
  const check = (!ro && !gen) ? `<label class="tile-check" data-selscene="${s.seq}"><input type="checkbox" ${sel ? "checked" : ""} tabindex="-1"/></label>` : "";
  // asset scenes have no editable prompt — they use a real uploaded file
  const open = (!ro && !gen && !isAsset) ? `data-scenegen="${s.seq}"` : "";
  return `<div class="tile ${okClip ? "done" : (working ? "working" : (failed ? "fail" : ""))}">
    <div class="thumb" ${open}>${inner}${clipTag}${assetTag}${overlay}${check}</div>
    <div class="row"><small>#${s.seq + 1}</small><span class="shot-tag shot-${s.shot_type}">${shotLabel(s.shot_type)}</span>
      ${(!ro && !gen && !isAsset) ? `<button class="reroll-link" data-scenegen="${s.seq}">${icon("edit","icon")} prompt</button>` : (isAsset ? `<span class="muted" style="font-size:11px">your file</span>` : "")}</div></div>`;
}
async function modalSceneGen(seq) {
  const s = (S.ep.scenes || [])[seq]; if (!s) return;
  let prompt = "";
  try { prompt = (await jget(`/api/episodes/${S.ep.episode_id}/scene/${seq}/veo-prompt`)).prompt || ""; } catch (err) {}
  const media = s.clip_url ? `<video src="${s.clip_url}?t=${S.ep.updated_at}" controls style="width:100%;border-radius:10px"></video>`
    : (s.still_url ? `<img src="${s.still_url}?t=${S.ep.updated_at}" style="width:100%;border-radius:10px;border:1px solid var(--border)"/>` : "");
  const body = `${media}
    <div class="field" style="margin-top:12px"><label>Veo prompt — describe the shot; any dialogue in "quotes" is spoken (native audio + lip-sync)</label>
      <textarea id="veo-prompt" rows="8">${esc(prompt)}</textarea></div>`;
  openModal(`Scene ${seq + 1} — generate`, body, async () => {
    S.ep = await jpost(`/api/episodes/${S.ep.episode_id}/scenes/generate`,
                       { seqs: [seq], prompts: { [seq]: $("#veo-prompt").value.trim() } });
    render(); managePolling(); toast("Generating scene…");
  }, "Generate this scene (~$0.30)");
}

/* --- Audio --- */
function stageAudio(e, gen, ro) {
  const music = (e.timeline || {}).music;
  if (ro) return `<p class="muted">${music ? "Music bed generated." : "Music skipped — the clips carry their own audio."}</p>`;
  const player = music ? `<audio controls src="/api/episodes/${e.episode_id}/music?t=${e.updated_at}" style="width:100%;max-width:620px"></audio>` : "";
  return `<p class="stage-intro">Your clips already carry native voice + SFX. This stage only adds an optional background <b>music bed</b> (mixed under the dialogue at assembly).</p>
    ${player}
    <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
      <button class="btn btn-primary" data-run ${gen ? "disabled" : ""}>${gen ? spin() : icon("mic")} ${gen ? "Composing…" : (music ? "Regenerate music" : `Generate music (~${fmt$(e.stage_estimate_usd)})`)}</button>
      ${music ? `<button class="btn btn-primary" data-approve>${icon("check")} Approve with music</button>` : ""}
      <button class="btn btn-ghost" data-skipmusic>${icon("arrow")} Skip — audio is in the clips</button>
    </div>`;
}

/* --- Assembly / Done --- */
const TRANSITION_LABELS = { hero_rush: "Hero rush", blaze: "Blaze whoosh", comic_slam: "Comic slam", whip_pan: "Whip pan", dust_puff: "Dust puff", dhoom: "DHOOM burst" };
function seamEditor(e) {
  const ch = channel() || {};
  const kinds = [...new Set((ch.transitions || []).map((t) => t.kind))];
  if (!kinds.length) return `<p class="muted">No transition library yet — generate some in the Transitions tab, or every seam is a clean hard cut.</p>`;
  const seams = (e.timeline || {}).seams || {};
  const opts = (cur) => [`<option value="auto" ${cur === "auto" ? "selected" : ""}>Auto (rules)</option>`,
    `<option value="none" ${cur === "none" ? "selected" : ""}>None — hard cut</option>`,
    ...kinds.map((k) => `<option value="${k}" ${cur === k ? "selected" : ""}>${TRANSITION_LABELS[k] || k}</option>`)].join("");
  const rows = e.scenes.slice(1).map((s, idx) => {
    const i = idx + 1;                       // incoming shot index
    const prev = e.scenes[idx];
    const cur = seams[String(i)] || "auto";
    return `<div class="seam-row">
      <span class="seam-scenes"><img src="${prev.still_url || ""}?t=${e.updated_at}"/><span class="seam-arrow">${icon("arrow","icon")}</span><img src="${s.still_url || ""}?t=${e.updated_at}"/></span>
      <small class="muted">#${prev.seq + 1} → #${s.seq + 1}${(prev.heading || "") !== (s.heading || "") ? " · location change" : ""}</small>
      <select class="seam-sel" data-seam="${i}">${opts(cur)}</select></div>`;
  }).join("");
  return `<details class="seam-box"><summary>Transitions between scenes <small class="muted">· Auto follows the cut-rhythm rules; override any seam</small></summary>
    <div class="seam-list">${rows}</div>
    <button class="btn btn-ghost btn-sm" data-saveseams style="margin-top:8px">${icon("check")} Save seam choices</button></details>`;
}
function stageAssembly(e, gen, ro) {
  if (ro) return e.final_url ? `<video class="player" controls preload="metadata" src="${e.final_url}?t=${e.updated_at}"></video>` : `<p class="muted">Not assembled.</p>`;
  const player = e.final_url ? `<video class="player" controls preload="metadata" src="${e.final_url}?t=${e.updated_at}"></video>` : "";
  const bar = e.final_url && e.stage_status === "awaiting_review"
    ? actionBar([`<button class="btn btn-primary" data-approve>${icon("check")} Approve &amp; finish</button>`,
                 `<button class="btn btn-ghost" data-run>${icon("refresh")} Re-render cut</button>`,
                 `<a class="btn btn-ghost" href="${e.final_url}" download>${icon("download")} Download</a>`])
    : `<div style="margin-top:14px"><button class="btn btn-primary" data-run ${gen ? "disabled" : ""}>${gen ? spin() : icon("film")} ${gen ? "Rendering…" : "Render final cut"}</button></div>`;
  const titles = e.titles_url ? `<a class="btn btn-ghost" href="${e.titles_url}" download>${icon("download")} Titles (.srt)</a>` : "";
  const intro = e.oneoff
    ? `The stitch: clips (native ambient) ${e.has_voiceover ? "+ voiceover (music ducked under it) " : ""}+ loudness normalization → text-free master. On-screen titles ship as a timed .srt to composite.`
    : `The stitch: clips (native audio) + transitions + ${(e.timeline || {}).music ? "music bed" : "no music"} + loudness normalization → final episode.`;
  return `<p class="stage-intro">${intro}</p>
    ${e.oneoff ? "" : seamEditor(e)}${player}${bar}${titles ? `<div style="margin-top:10px">${titles}</div>` : ""}`;
}
function stageDone(e) {
  return `<div class="done-banner">${icon("check")} ${e.oneoff ? "Video" : "Episode"} complete</div>
    ${e.final_url ? `<video class="player" controls preload="metadata" src="${e.final_url}?t=${e.updated_at}"></video>
      <div style="display:flex;gap:10px;margin-top:12px"><a class="btn btn-primary" href="${e.final_url}" download>${icon("download")} Download ${e.oneoff ? "video" : "episode"}</a>
      ${e.titles_url ? `<a class="btn btn-ghost" href="${e.titles_url}" download>${icon("download")} Titles (.srt)</a>` : ""}</div>` : ""}`;
}

/* ---------------- small helpers ---------------- */
const spin = () => `<span class="spin" style="width:15px;height:15px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;display:inline-block;animation:spin .8s linear infinite"></span>`;
function progBar(done, total, label, spent) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return `<div class="prog"><span class="spin"></span><b>${done}/${total}</b> <span class="muted">${label}</span><div class="bar"><i style="width:${pct}%"></i></div><b>${fmt$(spent)}</b></div>`;
}
function actionBar(btns) { return `<div class="actionbar"><span class="cost">spent <b>${fmt$(S.ep.spent_usd)}</b></span>${btns.join("")}</div>`; }

/* ---------------- polling ---------------- */
function managePolling() {
  const shouldPoll = parseHash().view === "ep" && S.ep && S.ep.generating;
  if (shouldPoll && !pollTimer) pollTimer = setInterval(pollEpisode, 1600);
  if (!shouldPoll && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}
async function pollEpisode() {
  if (!S.ep) return;
  try {
    const fresh = await jget(`/api/episodes/${S.ep.episode_id}`);
    S.ep = fresh;
    const body = $("#stagebody"); if (body) body.innerHTML = renderStage(fresh);
    if (!fresh.generating) { clearInterval(pollTimer); pollTimer = null; render(); }  // full re-render when done (stepper etc.)
  } catch (e) { /* transient */ }
}

/* ---------------- actions ---------------- */
async function refreshEp() { S.ep = await jget(`/api/episodes/${S.ep.episode_id}`); const b = $("#stagebody"); if (b) b.innerHTML = renderStage(S.ep); managePolling(); }
async function epAct(fn, optimisticGen) {
  try {
    if (optimisticGen && S.ep) { S.ep.generating = true; const b = $("#stagebody"); if (b) b.innerHTML = renderStage(S.ep); }
    S.ep = await fn(); render(); managePolling();
  } catch (err) { toast(err.message, "err"); try { await refreshEp(); } catch (e) {} }
}

document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-nav],[data-dd],[data-selchan],[data-newchannel],[data-editchannel],[data-newchar],[data-editchar],[data-uploadref],[data-newep],[data-delep],[data-runidea],[data-pickidea],[data-run],[data-approve],[data-runrefs],[data-refsbatch],[data-reroll],[data-reopen],[data-editscene],[data-delref],[data-refedit],[data-gentrans],[data-deltrans],[data-scenegen],[data-selscene],[data-selall],[data-genselected],[data-genremaining],[data-skipmusic],[data-saveseams],[data-saveconfig],[data-delchannel],[data-qvcreate],[data-revise],[data-revertscript]");
  // close dropdown on outside click
  if (!ev.target.closest(".dropdown,[data-dd]") && S.ddOpen) { S.ddOpen = false; const d = $(".dropdown"); if (d) d.remove(); }
  if (!t) return;
  const d = t.dataset;
  if (d.nav !== undefined) return go(d.nav);
  if (d.dd !== undefined) { S.ddOpen = !S.ddOpen; return S.ddOpen ? renderDropdown() : ($(".dropdown") && $(".dropdown").remove()); }
  if (d.selchan) { S.ddOpen = false; S.channelId = d.selchan; return go(`c/${d.selchan}/overview`); }
  if (d.newchannel !== undefined) return channelWizard();
  if (d.editchannel) return modalChannel(S.channels.find((c) => c.channel_id === d.editchannel));
  if (d.delchannel !== undefined) return delChannel(d.delchannel);
  if (d.newchar !== undefined) return modalCharacter();
  if (d.editchar) return modalCharacter(charById(d.editchar));
  if (d.uploadref) return uploadRef(d.uploadref);
  if (d.delref) {
    const [cid, idx] = d.delref.split(":");
    if (!confirm("Delete this reference photo?")) return;
    try { await jdel(`/api/characters/${cid}/reference/${idx}`); S.characters = await jget("/api/characters"); toast("Photo deleted"); render(); }
    catch (err) { toast(err.message, "err"); }
    return;
  }
  if (d.newep !== undefined) return newEpisode();
  if (d.delep) return delEpisode(d.delep);
  // workspace stage actions
  if (d.runidea !== undefined) { const brief = $("#idea-brief") ? $("#idea-brief").value.trim() : ""; return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/run`, { brief }), true); }
  if (d.pickidea !== undefined) return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/approve`, { choice: Number(d.pickidea) }));
  if (d.run !== undefined) {
    const isScript = S.ep.stage === "script";               // inline stage — resolves when done
    return epAct(async () => {
      const r = await jpost(`/api/episodes/${S.ep.episode_id}/run`, {});
      if (isScript) toast("Script rewritten", "ok");
      return r;
    }, true);
  }
  if (d.approve !== undefined) return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/approve`, {}));
  if (d.runrefs !== undefined) { const sn = $("#style-note") ? $("#style-note").value.trim() : ""; return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/run`, { style_note: sn }), true); }
  if (d.refsbatch !== undefined) { const sn = $("#style-note") ? $("#style-note").value.trim() : ""; const n = S.ep.scene_count - 1, cost = (n * S.ep.image_unit_cost).toFixed(2); if (!confirm(`Generate ${n} more images (~$${cost})?`)) return; return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/refs/batch`, { style_note: sn }), true); }
  if (d.reroll !== undefined) return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/scene/${d.reroll}/reroll`, {}), true);
  if (d.reopen !== undefined) return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/reopen`, { stage: d.reopen }));
  if (d.editscene !== undefined) return modalScene(Number(d.editscene));
  if (d.refedit !== undefined) return modalRefEdit(Number(d.refedit));
  if (d.scenegen !== undefined) return modalSceneGen(Number(d.scenegen));
  if (d.selscene !== undefined) { const n = Number(d.selscene); S.sceneSel = S.sceneSel || new Set(); S.sceneSel.has(n) ? S.sceneSel.delete(n) : S.sceneSel.add(n); return render(); }
  if (d.selall !== undefined) { const all = (S.ep.scenes || []).map((s) => s.seq); S.sceneSel = (S.sceneSel && S.sceneSel.size === all.length) ? new Set() : new Set(all); return render(); }
  if (d.genselected !== undefined) {
    const seqs = [...(S.sceneSel || [])]; if (!seqs.length) return;
    if (!confirm(`Generate ${seqs.length} scene(s) (~$${(seqs.length * SCENE_UNIT).toFixed(2)})?`)) return;
    return epAct(async () => { const r = await jpost(`/api/episodes/${S.ep.episode_id}/scenes/generate`, { seqs }); S.sceneSel = new Set(); return r; }, true);
  }
  if (d.revise !== undefined) return modalRevise();
  if (d.revertscript !== undefined) return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/script/revert`, {}).then((r) => { toast(`Reverted — QC ${(r.script_qc || {}).score ?? "?"}/100`); return r; }));
  if (d.qvcreate !== undefined) return quickCreate();
  if (d.saveconfig !== undefined) {
    const body = { platform: S.setupPreset, layout: $("#cfg-layout").value, duration_s: +$("#cfg-duration").value,
      scene_count: +$("#cfg-scenes").value, resolution: $("#cfg-res").value, language: $("#cfg-lang").value.trim(),
      pacing: $("#cfg-pacing").value, qc_threshold: +$("#cfg-qc").value, music: $("#cfg-music").checked,
      transitions: $("#cfg-trans").checked ? "auto" : "off" };
    return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/config`, body));
  }
  if (d.skipmusic !== undefined) return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/approve`, { skip_music: true }));
  if (d.saveseams !== undefined) {
    const seams = {};
    document.querySelectorAll(".seam-sel[data-seam]").forEach((sel) => { seams[sel.dataset.seam] = sel.value; });
    try { S.ep = await jpost(`/api/episodes/${S.ep.episode_id}/seams`, { seams }); toast("Seams saved — render the cut to apply"); render(); }
    catch (err) { toast(err.message, "err"); }
    return;
  }
  if (d.genremaining !== undefined) {
    const rem = (S.ep.scenes || []).filter((s) => (s.clip || {}).status !== "ok").map((s) => s.seq);
    if (!rem.length) return;
    if (!confirm(`Generate ${rem.length} remaining scene(s) (~$${(rem.length * SCENE_UNIT).toFixed(2)})?`)) return;
    return epAct(() => jpost(`/api/episodes/${S.ep.episode_id}/scenes/generate`, { seqs: rem }), true);
  }
  if (d.gentrans) {
    if (!confirm(`Generate a "${d.gentrans}" transition (~$0.20, ~1 min)?`)) return;
    S.genTransition = d.gentrans; render();
    try { const c = await jpost(`/api/channels/${S.channelId}/transitions`, { kind: d.gentrans }); S.channels = S.channels.map((x) => x.channel_id === c.channel_id ? c : x); toast("Transition added", "ok"); }
    catch (err) { toast(err.message, "err"); }
    S.genTransition = null; render(); return;
  }
  if (d.deltrans) {
    if (!confirm("Delete this transition?")) return;
    try { const c = await jdel(`/api/channels/${S.channelId}/transitions/${d.deltrans}`); S.channels = S.channels.map((x) => x.channel_id === c.channel_id ? c : x); toast("Deleted"); }
    catch (err) { toast(err.message, "err"); }
    render(); return;
  }
});

async function newEpisode() {
  const title = prompt("Episode title (optional):") || "";
  try { const e = await jpost("/api/episodes", { channel_id: S.channelId, title }); await reloadEpisodes(); go(`c/${S.channelId}/ep/${e.episode_id}`); }
  catch (err) { toast(err.message, "err"); }
}
async function delEpisode(id) {
  if (!confirm("Delete this episode and its media?")) return;
  try { await jdel(`/api/episodes/${id}`); await reloadEpisodes(); toast("Episode deleted"); render(); }
  catch (err) { toast(err.message, "err"); }
}
async function reloadEpisodes() { S.episodes = await jget(`/api/episodes?channel_id=${S.channelId}`); }
async function delChannel(id) {
  const ch = (S.channels || []).find((c) => c.channel_id === id) || {};
  const eps = await jget(`/api/episodes?channel_id=${id}`).catch(() => []);
  const typed = prompt(`This deletes "${ch.name}" and ${eps.length} episode(s) with all their media. Characters are kept.\n\nType the channel name to confirm:`);
  if (typed == null) return;
  if (typed.trim() !== (ch.name || "").trim()) { toast("Name didn't match — not deleted", "err"); return; }
  try {
    await jdel(`/api/channels/${id}`);
    $("#modal-root").innerHTML = "";
    await loadCore();
    if (S.channelId === id) { S.channelId = (S.channels[0] || {}).channel_id || null; location.hash = S.channelId ? `c/${S.channelId}/overview` : ""; }
    toast("Channel deleted"); render();
  } catch (err) { toast(err.message, "err"); }
}

/* file upload for character reference */
let uploadTargetId = null;
$("#hidden-file").addEventListener("change", async (ev) => {
  const f = ev.target.files[0]; if (!f || !uploadTargetId) return;
  const b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.readAsDataURL(f); });
  try { await jpost(`/api/characters/${uploadTargetId}/reference`, { filename: f.name, data_base64: b64 }); S.characters = await jget("/api/characters"); toast("Photo added", "ok"); render(); }
  catch (err) { toast(err.message, "err"); }
  ev.target.value = ""; uploadTargetId = null;
});
function uploadRef(id) { uploadTargetId = id; $("#hidden-file").click(); }

/* ---------------- modals ---------------- */
function openModal(title, bodyHtml, onSave, saveLabel = "Save") {
  const root = $("#modal-root");
  root.innerHTML = `<div class="scrim"><div class="modal"><div class="modal-head"><h3>${esc(title)}</h3><button class="icon-btn" data-mclose>${icon("x")}</button></div>
    <div class="modal-body">${bodyHtml}<p class="hint" id="m-msg"></p></div>
    <div class="modal-foot"><button class="btn btn-ghost" data-mclose>Cancel</button><button class="btn btn-primary" id="m-save">${saveLabel}</button></div></div></div>`;
  const close = () => { root.innerHTML = ""; };
  root.querySelectorAll("[data-mclose]").forEach((b) => b.onclick = close);
  $("#m-save").onclick = async () => { try { await onSave(); close(); } catch (e) { $("#m-msg").className = "hint err"; $("#m-msg").textContent = e.message; } };
}
const castChecks = (selected = []) => S.characters.map((c) => `<label><input type="checkbox" value="${c.character_id}" ${selected.includes(c.character_id) ? "checked" : ""}/> ${esc(c.name)}</label>`).join("") || `<span class="muted">Create characters first.</span>`;

/* ---------------- New-channel wizard ---------------- */
const PLATFORMS = [["youtube", "YouTube", "▭"], ["instagram", "Instagram", "▮"], ["tiktok", "TikTok", "♪"]];
const TONES = ["comedy", "action-comedy", "thriller", "wholesome", "educational", "satire", "drama"];
async function ensureStyles() { if (!S.styles) { try { S.styles = (await jget("/api/styles")).styles || []; } catch (e) { S.styles = []; } } }
function styleById(id) { return (S.styles || []).find((s) => s.id === id); }

async function channelWizard() {
  await ensureStyles();
  S.wiz = { step: 1, name: "", platform: "youtube", brief: "", tagline: "", premise: "", tone: "comedy", styleId: "", cast: [], voice: "", drafting: false };
  renderWizard();
}
function wizSaveStep() {
  const w = S.wiz;
  if (w.step === 1) { w.brief = $("#wz-brief") ? $("#wz-brief").value : w.brief; w.name = $("#wz-name") ? $("#wz-name").value : w.name; }
  if (w.step === 2) { ["name2:name", "tag:tagline", "prem:premise", "tone:tone"].forEach((m) => { const [id, k] = m.split(":"); const el = $("#wz-" + id); if (el) w[k] = el.value; }); }
  if (w.step === 4) { const v = $("#wz-voice"); if (v) w.voice = v.value; w.cast = [...document.querySelectorAll(".wz-cast input:checked")].map((i) => i.value); }
}
function wizGo(step) { wizSaveStep(); S.wiz.step = step; renderWizard(); }
function wizPlat(p) { S.wiz.platform = p; document.querySelectorAll("[data-wzplat]").forEach((b) => b.classList.toggle("on", b.dataset.wzplat === p)); }
function wizPickStyle(id) { S.wiz.styleId = id; document.querySelectorAll(".style-tile").forEach((t) => t.classList.toggle("on", t.dataset.style === id)); }
async function wizDraft() {
  wizSaveStep();
  if (!S.wiz.brief.trim()) { toast("Tell me what the show is about first", "err"); return; }
  S.wiz.drafting = true; renderWizard();
  try {
    const d = await jpost("/api/assist/premise", { brief: S.wiz.brief, platform: S.wiz.platform });
    S.wiz.name = S.wiz.name || d.name || ""; S.wiz.tagline = d.tagline || ""; S.wiz.premise = d.premise || "";
    S.wiz.tone = d.tone || "comedy"; S.wiz.styleId = (d.style_ids || [])[0] || S.wiz.styleId;
    if (d.stubbed) toast("Drafted (offline scaffold — add an API key for richer concepts)");
  } catch (err) { toast(err.message, "err"); }
  S.wiz.drafting = false; renderWizard();
}
async function wizCreate() {
  wizSaveStep(); const w = S.wiz;
  if (!w.name.trim()) { toast("Give the channel a name", "err"); return; }
  const shortForm = w.platform !== "youtube";
  const body = { name: w.name.trim(), platform: w.platform, format: shortForm ? "short_form" : "long_form",
    premise: w.premise.trim(), tagline: w.tagline.trim(), tone: w.tone, art_style_id: w.styleId,
    narrator_voice_id: w.voice.trim(),
    cast: w.cast.map((id, i) => ({ character_id: id, role: i === 0 ? "lead" : "sidekick" })) };
  try {
    const nc = await jpost("/api/channels", body);
    $("#modal-root").innerHTML = ""; S.wiz = null;
    S.channelId = nc.channel_id; await loadCore(); await reloadEpisodes();
    location.hash = `c/${nc.channel_id}/overview`; toast("Channel created ✨"); render();
  } catch (err) { toast(err.message, "err"); }
}
function wizStepDots(step) {
  return ["Idea", "Premise", "Style", "Cast"].map((l, i) => `<span class="wz-dot ${i + 1 === step ? "on" : i + 1 < step ? "done" : ""}">${i + 1 < step ? icon("check", "icon") : i + 1}</span><span class="wz-dot-l">${l}</span>`).join('<span class="wz-dot-sep"></span>');
}
function renderWizard() {
  const w = S.wiz; if (!w) return;
  let body = "", foot = "", title = "New channel";
  if (w.step === 1) {
    title = "What's the show?";
    body = `<div class="field"><label>Platform</label><div class="plat-tiles">${PLATFORMS.map(([id, l, g]) => `<button type="button" class="plat-tile ${w.platform === id ? "on" : ""}" data-wzplat="${id}" onclick="wizPlat('${id}')"><span class="plat-g">${g}</span>${l}</button>`).join("")}</div></div>
      <div class="field"><label>What's the show about? <small class="muted">one line is enough</small></label>
        <textarea id="wz-brief" rows="3" placeholder="e.g. a detective dog in Mumbai who busts scams with clever jugaad">${esc(w.brief)}</textarea></div>
      <div class="field"><label>Channel name <small class="muted">optional — the assistant can suggest one</small></label><input id="wz-name" value="${esc(w.name)}" placeholder="leave blank to auto-name"/></div>`;
    foot = `<button class="btn btn-primary" onclick="wizGo(2)">Next: premise ${icon("arrow","icon")}</button>`;
  } else if (w.step === 2) {
    title = "Shape the premise";
    body = `<div class="wz-assist"><button class="btn btn-primary" onclick="wizDraft()" ${w.drafting ? "disabled" : ""}>${w.drafting ? spin() : icon("sparkles","icon")} ${w.premise ? "Regenerate" : "Draft with AI"}</button>
        <span class="muted">${w.drafting ? "Thinking…" : "Turns your one-liner into a name, tagline & premise"}</span></div>
      <div class="row-2"><div class="field"><label>Channel name</label><input id="wz-name2" value="${esc(w.name)}"/></div>
        <div class="field"><label>Tagline</label><input id="wz-tag" value="${esc(w.tagline)}" placeholder="one catchy line"/></div></div>
      <div class="field"><label>Premise <small class="muted">the engine of every episode</small></label><textarea id="wz-prem" rows="6" placeholder="Draft with AI, or write it here…">${esc(w.premise)}</textarea></div>
      <div class="field"><label>Tone</label><select id="wz-tone">${TONES.map((t) => `<option value="${t}" ${w.tone === t ? "selected" : ""}>${t}</option>`).join("")}</select></div>`;
    foot = `<button class="btn btn-ghost" onclick="wizGo(1)">${icon("back","icon")} Back</button><button class="btn btn-primary" onclick="wizGo(3)">Next: style ${icon("arrow","icon")}</button>`;
  } else if (w.step === 3) {
    title = "Pick the look";
    const tiles = (S.styles || []).map((s) => `<button type="button" class="style-tile ${w.styleId === s.id ? "on" : ""}" data-style="${s.id}" onclick="wizPickStyle('${s.id}')">
        <img loading="lazy" src="${s.sample_url}" alt="${esc(s.label)}"/><span>${esc(s.label)}</span></button>`).join("");
    body = `<p class="muted" style="margin:0 0 12px">Same character in every style — click the look you want.</p>
      <div class="style-gallery">${tiles || '<span class="muted">No style samples yet — run scripts/gen_style_samples.py.</span>'}</div>`;
    foot = `<button class="btn btn-ghost" onclick="wizGo(2)">${icon("back","icon")} Back</button><button class="btn btn-primary" onclick="wizGo(4)" ${w.styleId ? "" : "disabled"}>Next: cast ${icon("arrow","icon")}</button>`;
  } else {
    title = "Cast & review";
    const st = styleById(w.styleId);
    body = `<div class="field"><label>Cast <small class="muted">first checked = lead</small></label><div class="checks wz-cast">${(S.characters || []).map((c) => `<label><input type="checkbox" value="${c.character_id}" ${w.cast.includes(c.character_id) ? "checked" : ""}/> ${esc(c.name)}</label>`).join("") || '<span class="muted">Create characters first (you can add them later).</span>'}</div></div>
      <div class="field"><label>Narrator voice <small class="muted">optional</small></label><input id="wz-voice" value="${esc(w.voice)}" placeholder="e.g. a voice id"/></div>
      <div class="wz-review"><b>${esc(w.name || "(unnamed)")}</b> <span class="chip">${esc(w.platform)}</span> <span class="chip">${esc(w.tone)}</span>
        ${st ? `<div class="wz-review-style"><img src="${st.sample_url}"/><span>${esc(st.label)}</span></div>` : ""}
        <p class="muted">${esc(w.tagline || "")}</p></div>`;
    foot = `<button class="btn btn-ghost" onclick="wizGo(3)">${icon("back","icon")} Back</button><button class="btn btn-primary" onclick="wizCreate()">${icon("check","icon")} Create channel</button>`;
  }
  $("#modal-root").innerHTML = `<div class="scrim"><div class="modal modal-wide"><div class="modal-head"><h3>${esc(title)}</h3><button class="icon-btn" onclick="document.getElementById('modal-root').innerHTML=''">${icon("x")}</button></div>
    <div class="wz-steps">${wizStepDots(w.step)}</div>
    <div class="modal-body">${body}</div>
    <div class="modal-foot">${foot}</div></div></div>`;
}

function modalChannel(ch) {
  const c = ch || {};
  const sel = (ch && ch.cast || []).map((m) => m.character_id);
  openModal(ch ? "Edit channel" : "New channel", `
    <div class="row-2"><div class="field"><label>Name</label><input id="f-name" value="${esc(c.name || "")}" placeholder="Zruv Adventures"/></div>
      <div class="field"><label>Platform</label><input id="f-plat" value="${esc(c.platform || "youtube")}"/></div></div>
    <div class="row-2"><div class="field"><label>Format</label><select id="f-fmt"><option value="long_form" ${c.format === "long_form" ? "selected" : ""}>long_form</option><option value="short_form" ${c.format === "short_form" ? "selected" : ""}>short_form</option></select></div>
      <div class="field"><label>Tone</label><select id="f-tone">${["", ...TONES].map((t) => `<option value="${t}" ${(c.tone || "") === t ? "selected" : ""}>${t || "—"}</option>`).join("")}</select></div></div>
    <div class="row-2"><div class="field"><label>Art style — library</label><select id="f-styleid" onchange="const s=(S.styles||[]).find(x=>x.id===this.value); if(s){document.getElementById('f-style').value=s.prompt;}">
        <option value="">Custom (use text below)</option>${(S.styles || []).map((s) => `<option value="${s.id}" ${c.art_style_id === s.id ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select></div>
      <div class="field"><label>Art style — text</label><input id="f-style" value="${esc(c.art_style || "")}" placeholder="3D Pixar comic style, vibrant"/></div></div>
    <div class="field"><label>Premise</label><textarea id="f-prem" rows="3" placeholder="What the series is about…">${esc(c.premise || "")}</textarea></div>
    <div class="row-3"><div class="field"><label>Scenes</label><input type="number" id="f-scenes" value="${c.target_scene_count || 16}"/></div>
      <div class="field"><label>Duration (s)</label><input type="number" id="f-dur" value="${c.target_duration_s || 120}"/></div>
      <div class="field"><label>Video budget</label><input type="number" id="f-budget" value="${c.video_budget ?? 3}"/></div></div>
    <div class="row-2"><div class="field"><label>Writer provider</label><input id="f-writer" value="${esc(c.writer_provider || "openrouter")}"/></div>
      <div class="field"><label>Narrator voice</label><input id="f-narr" value="${esc(c.narrator_voice_id || "")}" placeholder="e.g. Brian"/></div></div>
    <div class="field"><label>Cast (first checked = lead)</label><div class="checks">${castChecks(sel)}</div></div>
    ${ch ? `<div class="danger-zone"><div><b>Delete channel</b><br><small class="muted">Removes this channel and all its episodes + media. Characters are kept.</small></div><button type="button" class="btn btn-danger" data-delchannel="${ch.channel_id}">${icon("trash","icon")} Delete</button></div>` : ""}`,
    async () => {
      const picked = [...document.querySelectorAll(".modal .checks input:checked")].map((i) => i.value);
      const cast = picked.map((id, i) => ({ character_id: id, role: i === 0 ? "lead" : "sidekick" }));
      const body = { name: $("#f-name").value.trim(), platform: $("#f-plat").value.trim(), format: $("#f-fmt").value, tone: $("#f-tone").value, art_style_id: $("#f-styleid").value, art_style: $("#f-style").value.trim(), premise: $("#f-prem").value.trim(), target_scene_count: +$("#f-scenes").value, target_duration_s: +$("#f-dur").value, video_budget: +$("#f-budget").value, writer_provider: $("#f-writer").value.trim(), narrator_voice_id: $("#f-narr").value.trim(), cast };
      if (ch) await jpatch(`/api/channels/${ch.channel_id}`, body); else { const nc = await jpost("/api/channels", body); S.channelId = nc.channel_id; location.hash = `c/${nc.channel_id}/overview`; }
      await loadCore(); await reloadEpisodes(); render();
    }, ch ? "Save" : "Create");
}

function modalCharacter(c) {
  const p = (c && c.personality) || {}, v = (c && c.voice) || {};
  openModal(c ? "Edit character" : "New character", `
    <div class="row-2"><div class="field"><label>Name</label><input id="f-name" value="${esc(c ? c.name : "")}"/></div>
      <div class="field"><label>Species</label><select id="f-species"><option value="person" ${c && c.species === "person" ? "selected" : ""}>person</option><option value="animal" ${c && c.species === "animal" ? "selected" : ""}>animal</option></select></div></div>
    <div class="field"><label>Look / appearance <small>(reference photos override this)</small></label><textarea id="f-dna" rows="2">${esc(c ? c.dna_prompt : "")}</textarea></div>
    <div class="row-2"><div class="field"><label>Voice provider</label><input id="f-vprov" value="${esc(v.provider || "elevenlabs")}"/></div>
      <div class="field"><label>Voice ID</label><input id="f-vid" value="${esc(v.voice_id || "")}" placeholder="e.g. Rachel"/></div></div>
    <div class="field"><label>Backstory / personality</label><textarea id="f-back" rows="3">${esc(p.backstory || "")}</textarea></div>
    <div class="row-2"><div class="field"><label>Traits (comma-sep)</label><input id="f-traits" value="${esc((p.traits || []).join(", "))}"/></div>
      <div class="field"><label>Speech style</label><input id="f-speech" value="${esc(p.speech_style || "")}"/></div></div>`,
    async () => {
      const body = { name: $("#f-name").value.trim(), species: $("#f-species").value, dna_prompt: $("#f-dna").value.trim(),
        voice: { provider: $("#f-vprov").value.trim(), voice_id: $("#f-vid").value.trim() },
        personality: { backstory: $("#f-back").value.trim(), traits: splitList($("#f-traits").value), speech_style: $("#f-speech").value.trim(), catchphrases: (p.catchphrases || []), mannerisms: (p.mannerisms || []) } };
      if (c) await jpatch(`/api/characters/${c.character_id}`, body); else await jpost("/api/characters", body);
      S.characters = await jget("/api/characters"); render();
    }, c ? "Save" : "Create");
}

/* ---------------- init ---------------- */
(async function init() {
  try {
    await loadCore();
    if (S.channels.length && !S.channelId) S.channelId = (parseHash().cid) || S.channels[0].channel_id;
    if (S.channelId) await reloadEpisodes();
    await route();
    // light refresh of core every 15s (channels/characters/keys)
    setInterval(async () => { try { await loadCore(); if (S.channelId) await reloadEpisodes(); if (!S.ep) render(); } catch (e) {} }, 15000);
  } catch (e) { $("#app").innerHTML = `<div class="empty" style="padding-top:80px">${icon("x")}<div>Failed to load: ${esc(e.message)}</div></div>`; }
})();
