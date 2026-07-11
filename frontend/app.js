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
}
const channel = () => S.channels.find((c) => c.channel_id === S.channelId) || S.channels[0];
const charById = (id) => S.characters.find((c) => c.character_id === id);

/* ---------------- router ---------------- */
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [a, b, c, d, e] = h.split("/");
  if (a === "c" && b) return { cid: b, view: c || "overview", id: d, stage: e };
  return { view: "home" };
}
const go = (h) => { location.hash = h; };

async function route() {
  const r = parseHash();
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
const STAGES = [["idea", "Idea"], ["script", "Script"], ["refs", "Refs"], ["scenes", "Scenes"], ["audio", "Audio"], ["assembly", "Assembly"], ["done", "Done"]];
function viewWorkspace() {
  const e = S.ep; if (!e) return `<p class="muted">Episode not found.</p>`;
  const idx = STAGES.findIndex(([k]) => k === e.stage);
  const viewed = (parseHash().stage && STAGES.some(([k]) => k === parseHash().stage)) ? parseHash().stage : e.stage;
  const readOnly = viewed !== e.stage;
  const steps = STAGES.map(([k, label], i) => {
    const reached = i <= idx || e.stage === "done";
    const cls = (i < idx || e.stage === "done") ? "done" : (i === idx ? "current" : "");
    const viewing = k === viewed ? "viewing" : "";
    const num = (i < idx || e.stage === "done") ? icon("check", "icon") : (i + 1);
    const attr = reached ? `data-nav="c/${S.channelId}/ep/${e.episode_id}/${k}"` : "disabled";
    return `<button class="step ${cls} ${viewing}" ${attr} style="${reached ? "" : "opacity:.45;cursor:default"}"><span class="num">${num}</span>${label}</button>`;
  }).join(`<span class="step-sep">${icon("arrow", "icon")}</span>`);
  const banner = readOnly ? `<div class="chip" style="margin-bottom:14px">${icon("check","icon")} Viewing an approved stage (read-only) · <button class="linkish" data-nav="c/${S.channelId}/ep/${e.episode_id}/${e.stage}">back to current</button></div>` : "";
  return `<a class="ws-back" data-nav="c/${S.channelId}/episodes">${icon("back")} Episodes</a>
    <div class="ws-head" style="margin-top:12px"><h1>${esc(e.title)}</h1>
      <div class="ws-meta"><span>${e.cast.length} cast</span><span>${e.scene_count} scenes</span><span>writer ${esc(e.writer_model || "—")}</span><span>spent ${fmt$(e.spent_usd)}</span></div></div>
    <div class="stepper">${steps}</div>
    ${banner}
    <div class="stage-body" id="stagebody">${renderStage(e, viewed, readOnly)}</div>`;
}

function renderStage(e, stage, readOnly) {
  stage = stage || e.stage;
  const errBar = (!readOnly && e.stage_error) ? `<div class="err-banner">${icon("x", "icon")} ${esc(e.stage_error)}</div>` : "";
  const gen = !readOnly && e.generating;
  switch (stage) {
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
    const bar = gen
      ? `<div class="stage-intro">${spin()} Rewriting + QC-judging the script… (may take a minute — it revises until it passes)</div>`
      : actionBar([`<button class="btn btn-primary" data-approve>${icon("check")} Approve script</button>`, `<button class="btn btn-ghost" data-run>${icon("refresh")} Rewrite all</button>`]);
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
  return `<div class="sc"><div class="h"><b>${esc(s.heading || "scene")}</b><span class="shot-tag shot-${s.shot_type}">${shotLabel(s.shot_type)}</span><small>${s.duration_s}s</small>${edit}</div>
    <div class="act">${esc(s.action || "")}</div>${s.narration ? `<div class="vo">${icon("mic","icon")} ${esc(s.narration)}</div>` : ""}
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
    <div class="field"><label>Action — the cinematic shot (blocking, expressions, props, lighting)</label><textarea id="s-act" rows="4">${esc(s.action || "")}</textarea></div>
    <div class="row-3"><div class="field"><label>Camera</label><input id="s-cam" value="${esc(s.camera || "")}"/></div>
      <div class="field"><label>Shot type</label><select id="s-shot">${opts(s.shot_type, shots, (x) => x, shotLabel)}</select></div>
      <div class="field"><label>Duration (s)</label><input type="number" step="0.5" id="s-dur" value="${s.duration_s || 5}"/></div></div>
    <div class="field"><label>Narration / VO (optional)</label><textarea id="s-narr" rows="2">${esc(s.narration || "")}</textarea></div>
    <div class="field"><label>Dialogue</label><div id="s-dlg">${dlgRows || `<span class="muted">No dialogue in this scene.</span>`}</div></div>`;
  openModal(`Edit scene ${seq + 1}`, body, async () => {
    const scenes = (S.ep.scenes || []).map((x) => ({ ...x }));
    const ns = scenes[seq];
    ns.heading = $("#s-head").value; ns.action = $("#s-act").value; ns.camera = $("#s-cam").value;
    ns.motion = ns.action; ns.frozen_beat = "";   // backend re-derives the still-safe frozen beat
    ns.shot_type = $("#s-shot").value; ns.duration_s = +$("#s-dur").value; ns.narration = $("#s-narr").value;
    ns.dialogue = [...document.querySelectorAll("#s-dlg [data-dlg]")].map((r, i) => ({
      speaker: r.querySelector(".d-spk").value, line: r.querySelector(".d-line").value.trim(),
      delivery: ((s.dialogue || [])[i] || {}).delivery || "",
    })).filter((d) => d.line);
    S.ep = await jpatch(`/api/episodes/${S.ep.episode_id}/artifact`, { scenes });
    render(); toast("Scene updated");
  }, "Save scene");
}
const shotLabel = (t) => ({ broll: "b-roll", still_kenburns: "ken burns", lipsync_still: "lip-sync", hero_video: "hero video" }[t] || t);

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
  return `<div class="tile ${state}"><div class="thumb">${inner}</div>
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
  const sel = (S.sceneSel || new Set()).has(s.seq);
  const working = gen && !okClip;
  const inner = s.still_url ? `<img src="${s.still_url}?t=${e.updated_at}"/>` : `<div class="spin-lg"></div>`;
  const clipTag = s.clip_url ? `<span class="clip-tag">${icon("play","icon")} clip</span>` : "";
  const overlay = working ? `<div class="spin-lg" style="position:absolute"></div>` : (failed ? `<div class="fail">${icon("x","icon")} failed</div>` : "");
  const check = (!ro && !gen) ? `<label class="tile-check" data-selscene="${s.seq}"><input type="checkbox" ${sel ? "checked" : ""} tabindex="-1"/></label>` : "";
  const open = (!ro && !gen) ? `data-scenegen="${s.seq}"` : "";
  return `<div class="tile ${okClip ? "done" : (working ? "working" : (failed ? "fail" : ""))}">
    <div class="thumb" ${open}>${inner}${clipTag}${overlay}${check}</div>
    <div class="row"><small>#${s.seq + 1}</small><span class="shot-tag shot-${s.shot_type}">${shotLabel(s.shot_type)}</span>
      ${(!ro && !gen) ? `<button class="reroll-link" data-scenegen="${s.seq}">${icon("edit","icon")} prompt</button>` : ""}</div></div>`;
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
  if (ro) return `${e.audio_cut_url ? `<video class="player" controls preload="metadata" src="${e.audio_cut_url}?t=${e.updated_at}"></video>` : ""}<div class="grid tiles">${e.scenes.map((s) => audioTile(e, s, false, true)).join("")}</div>`;
  const anyAudio = e.scenes.some((s) => (s.audio || {}).status === "ok");
  if (gen || e.stage_status === "awaiting_review" || (anyAudio && !e.audio_cut_url)) {
    const progress = gen ? progBar(e.audio_done_count, e.scene_count, "Generating voices + music", e.spent_usd) : "";
    const player = (!gen && e.audio_cut_url) ? `<video class="player" controls preload="metadata" src="${e.audio_cut_url}?t=${e.updated_at}"></video>` : "";
    const grid = `<div class="grid tiles">${e.scenes.map((s) => audioTile(e, s, gen)).join("")}</div>`;
    let bar = "";
    if (!gen && e.audio_cut_url) bar = actionBar([`<button class="btn btn-primary" data-approve>${icon("check")} Approve audio</button>`, `<button class="btn btn-ghost" data-run>${icon("refresh")} Regenerate</button>`]);
    else if (!gen && anyAudio) bar = actionBar([`<button class="btn btn-primary" data-run>${icon("refresh")} Finish audio (mix)</button>`]);
    return `${progress}${player}<div class="section-title" style="margin-top:0">Voiced cut · review with sound</div>${grid}${bar}`;
  }
  return `<p class="stage-intro">Narrator VO + each character's locked voice + a music bed; lip-sync on talking shots, then a voiced cut. ~${fmt$(e.stage_estimate_usd)}.</p>
    <button class="btn btn-primary" data-run ${gen ? "disabled" : ""}>${gen ? spin() : icon("mic")} ${gen ? "Working…" : `Generate voices + music (~${fmt$(e.stage_estimate_usd)})`}</button>`;
}
function audioTile(e, s, gen, ro) {
  const done = (s.audio || {}).status === "ok";
  let state = gen ? "working" : (done ? "done" : "queued");
  const inner = s.still_url ? `<img src="${s.still_url}?t=${e.updated_at}"/>` : `<div class="spin-lg"></div>`;
  return `<div class="tile ${state}"><div class="thumb">${inner}${(gen && !done) ? `<div class="spin-lg" style="position:absolute"></div>` : ""}${done ? `<span class="clip-tag">${icon("mic","icon")}</span>` : ""}</div>
    <div class="row"><small>#${s.seq + 1}</small><span class="shot-tag shot-${s.shot_type}">${shotLabel(s.shot_type)}</span>
      ${done && !gen && !ro ? `<button class="reroll-link" data-reroll="${s.seq}">re-roll</button>` : ""}</div></div>`;
}

/* --- Assembly / Done --- */
function stageAssembly(e, gen, ro) {
  if (ro) return e.final_url ? `<video class="player" controls preload="metadata" src="${e.final_url}?t=${e.updated_at}"></video>` : `<p class="muted">Not assembled.</p>`;
  if (e.stage_status === "awaiting_review" && e.final_url) {
    return `<video class="player" controls preload="metadata" src="${e.final_url}?t=${e.updated_at}"></video>
      ${actionBar([`<button class="btn btn-primary" data-approve>${icon("check")} Approve &amp; finish</button>`, `<a class="btn btn-ghost" href="${e.final_url}" download>${icon("download")} Download</a>`])}`;
  }
  return `<p class="stage-intro">Build the final cut + editable timeline (EDL). Free — no generation.</p>
    <button class="btn btn-primary" data-run ${gen ? "disabled" : ""}>${gen ? spin() : icon("film")} ${gen ? "Assembling…" : "Assemble final"}</button>`;
}
function stageDone(e) {
  return `<div class="done-banner">${icon("check")} Episode complete</div>
    ${e.final_url ? `<video class="player" controls preload="metadata" src="${e.final_url}?t=${e.updated_at}"></video>
      <a class="btn btn-primary" href="${e.final_url}" download>${icon("download")} Download episode</a>` : ""}`;
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
  const t = ev.target.closest("[data-nav],[data-dd],[data-selchan],[data-newchannel],[data-editchannel],[data-newchar],[data-editchar],[data-uploadref],[data-newep],[data-delep],[data-runidea],[data-pickidea],[data-run],[data-approve],[data-runrefs],[data-refsbatch],[data-reroll],[data-reopen],[data-editscene],[data-delref],[data-refedit],[data-gentrans],[data-deltrans],[data-scenegen],[data-selscene],[data-selall],[data-genselected],[data-genremaining]");
  // close dropdown on outside click
  if (!ev.target.closest(".dropdown,[data-dd]") && S.ddOpen) { S.ddOpen = false; const d = $(".dropdown"); if (d) d.remove(); }
  if (!t) return;
  const d = t.dataset;
  if (d.nav !== undefined) return go(d.nav);
  if (d.dd !== undefined) { S.ddOpen = !S.ddOpen; return S.ddOpen ? renderDropdown() : ($(".dropdown") && $(".dropdown").remove()); }
  if (d.selchan) { S.ddOpen = false; S.channelId = d.selchan; return go(`c/${d.selchan}/overview`); }
  if (d.newchannel !== undefined) return modalChannel();
  if (d.editchannel) return modalChannel(S.channels.find((c) => c.channel_id === d.editchannel));
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

function modalChannel(ch) {
  const c = ch || {};
  const sel = (ch && ch.cast || []).map((m) => m.character_id);
  openModal(ch ? "Edit channel" : "New channel", `
    <div class="row-2"><div class="field"><label>Name</label><input id="f-name" value="${esc(c.name || "")}" placeholder="Zruv Adventures"/></div>
      <div class="field"><label>Platform</label><input id="f-plat" value="${esc(c.platform || "youtube")}"/></div></div>
    <div class="row-2"><div class="field"><label>Format</label><select id="f-fmt"><option value="long_form" ${c.format === "long_form" ? "selected" : ""}>long_form</option><option value="short_form" ${c.format === "short_form" ? "selected" : ""}>short_form</option></select></div>
      <div class="field"><label>Art style</label><input id="f-style" value="${esc(c.art_style || "")}" placeholder="3D Pixar comic style, vibrant"/></div></div>
    <div class="field"><label>Premise</label><textarea id="f-prem" rows="3" placeholder="What the series is about…">${esc(c.premise || "")}</textarea></div>
    <div class="row-3"><div class="field"><label>Scenes</label><input type="number" id="f-scenes" value="${c.target_scene_count || 16}"/></div>
      <div class="field"><label>Duration (s)</label><input type="number" id="f-dur" value="${c.target_duration_s || 120}"/></div>
      <div class="field"><label>Video budget</label><input type="number" id="f-budget" value="${c.video_budget ?? 3}"/></div></div>
    <div class="row-2"><div class="field"><label>Writer provider</label><input id="f-writer" value="${esc(c.writer_provider || "openrouter")}"/></div>
      <div class="field"><label>Narrator voice</label><input id="f-narr" value="${esc(c.narrator_voice_id || "")}" placeholder="e.g. Brian"/></div></div>
    <div class="field"><label>Cast (first checked = lead)</label><div class="checks">${castChecks(sel)}</div></div>`,
    async () => {
      const picked = [...document.querySelectorAll(".modal .checks input:checked")].map((i) => i.value);
      const cast = picked.map((id, i) => ({ character_id: id, role: i === 0 ? "lead" : "sidekick" }));
      const body = { name: $("#f-name").value.trim(), platform: $("#f-plat").value.trim(), format: $("#f-fmt").value, art_style: $("#f-style").value.trim(), premise: $("#f-prem").value.trim(), target_scene_count: +$("#f-scenes").value, target_duration_s: +$("#f-dur").value, video_budget: +$("#f-budget").value, writer_provider: $("#f-writer").value.trim(), narrator_voice_id: $("#f-narr").value.trim(), cast };
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
