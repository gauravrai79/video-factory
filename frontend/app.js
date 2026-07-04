"use strict";
const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then(async (r) => {
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
  return j;
});
const jbody = (p, m, body) => api(p, { method: m, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const jpost = (p, body) => jbody(p, "POST", body);
const jpatch = (p, body) => jbody(p, "PATCH", body);
const esc = (x) => String(x ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const splitList = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);

let characters = [], channels = [], episodes = [];
let epFilter = "all";

// ---------- header + stats ----------
async function refreshSummary() {
  const s = await api("/api/summary");
  $("#env-chips").innerHTML = [
    `<span class="chip"><b>${esc(s.tenant)}</b></span>`,
    `<span class="chip">img <b>${esc(s.image_model)}</b></span>`,
    `<span class="chip">vid <b>${esc(s.video_model)}</b></span>`,
    s.fal_key_present ? `<span class="chip ok">fal.ai ✓</span>` : `<span class="chip warn">no fal key</span>`,
  ].join("");
  $("#stats").innerHTML = [
    ["Channels", s.channels], ["Episodes", s.episodes], ["Characters", s.characters],
    ["Delivered", s.by_state.delivered || 0], ["Spent", "$" + Number(s.spent_usd || 0).toFixed(2)],
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
}

// ---------- characters (actors) ----------
async function refreshCharacters() {
  characters = await api("/api/characters");
  $("#char-grid").innerHTML = characters.length
    ? characters.map(actorCard).join("")
    : `<p class="empty">No actors yet — create one to start building your cast.</p>`;
}

function actorCard(c) {
  const thumb = c.reference_image_urls.length
    ? `<img src="${c.reference_image_urls[0]}" alt="${esc(c.name)}" />`
    : `<span class="ph">${esc((c.name || "?")[0])}</span>`;
  const traits = (c.personality && c.personality.traits) ? c.personality.traits.slice(0, 3).join(", ") : "";
  return `<div class="actor-card">
    <div class="actor-thumb">${thumb}</div>
    <div class="actor-meta">
      <div class="actor-name"><b>${esc(c.name)}</b> <small>${esc(c.species)}</small></div>
      <div class="badges">
        <span class="badge2 ${c.has_voice ? "on" : "off"}">🎤 voice ${c.has_voice ? "✓" : "–"}</span>
        <span class="badge2 ${c.has_reference ? "on" : "off"}">📸 ${c.reference_image_urls.length} ref${c.reference_image_urls.length === 1 ? "" : "s"}</span>
      </div>
      ${traits ? `<div class="persona-preview">${esc(traits)}</div>` : `<div class="persona-preview muted">no personality set</div>`}
      <div class="actor-actions">
        <button class="linklike" data-edit-actor="${c.character_id}">edit</button>
        <button class="linklike" data-upload="${c.character_id}">upload ref</button>
      </div>
    </div>
  </div>`;
}

// create character
$("#new-char-btn").addEventListener("click", () => { $("#char-form").hidden = !$("#char-form").hidden; });
$("#char-cancel").addEventListener("click", () => { $("#char-form").hidden = true; });
$("#char-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#char-msg");
  try {
    await jpost("/api/characters", {
      name: $("#c-name").value.trim(), species: $("#c-species").value, dna_prompt: $("#c-dna").value.trim(),
    });
    $("#char-form").reset(); $("#char-form").hidden = true; msg.textContent = "";
    refreshCharacters();
  } catch (err) { msg.className = "hint err"; msg.textContent = "Error: " + err.message; }
});

// upload reference image (base64, no generation)
const fileInput = Object.assign(document.createElement("input"), { type: "file", accept: "image/*", hidden: true });
document.body.appendChild(fileInput);
let uploadTarget = null;
function fileToB64(file) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.onerror = rej; r.readAsDataURL(file); });
}
fileInput.addEventListener("change", async () => {
  const f = fileInput.files[0]; if (!f || !uploadTarget) return;
  try {
    await jpost(`/api/characters/${uploadTarget}/reference`, { filename: f.name, data_base64: await fileToB64(f) });
    refreshCharacters();
    if (!$("#drawer").hidden) openActor(uploadTarget);
  } catch (err) { alert("Upload failed: " + err.message); }
  fileInput.value = ""; uploadTarget = null;
});

// edit actor drawer (voice + personality)
async function openActor(id) {
  const c = await api(`/api/characters/${id}`);
  const p = c.personality || {}, v = c.voice || {};
  const refs = c.reference_image_urls.map((u) => `<img class="ref-thumb" src="${u}" />`).join("") ||
    `<span class="muted">no reference images yet — click "add photo"</span>`;
  $("#drawer-body").innerHTML = `
    <h2>${esc(c.name)} <small>${esc(c.species)}</small></h2>
    <div class="section-title">Visual DNA (reference sheet)</div>
    <div class="ref-strip">${refs}</div>
    <button class="ghost sm" data-upload="${c.character_id}">+ add photo</button>
    <div class="section-title">Voice DNA</div>
    <div class="kv2">
      <label>Provider <input id="v-provider" value="${esc(v.provider || "elevenlabs")}" /></label>
      <label>Voice ID <input id="v-id" value="${esc(v.voice_id || "")}" placeholder="ElevenLabs voice id" /></label>
      <label>Signature line <input id="v-sig" value="${esc(v.signature_line || "")}" placeholder="a short preview line" /></label>
    </div>
    <div class="section-title">Personality DNA <small>(system prompt for writing + delivery)</small></div>
    <div class="kv2">
      <label>Backstory <textarea id="p-back" rows="2">${esc(p.backstory || "")}</textarea></label>
      <label>Traits <small>(comma-sep)</small> <input id="p-traits" value="${esc((p.traits || []).join(", "))}" /></label>
      <label>Speech style <input id="p-speech" value="${esc(p.speech_style || "")}" /></label>
      <label>Catchphrases <small>(comma-sep)</small> <input id="p-catch" value="${esc((p.catchphrases || []).join(", "))}" /></label>
      <label>Mannerisms <small>(comma-sep)</small> <input id="p-mann" value="${esc((p.mannerisms || []).join(", "))}" /></label>
    </div>
    <div class="post-actions"><button id="actor-save" data-actor="${c.character_id}">Save actor</button></div>
    <p class="hint" id="actor-msg"></p>`;
  $("#backdrop").hidden = false; $("#drawer").hidden = false;
}
async function saveActor(id) {
  const body = {
    voice: { provider: $("#v-provider").value.trim(), voice_id: $("#v-id").value.trim(), signature_line: $("#v-sig").value.trim() },
    personality: {
      backstory: $("#p-back").value.trim(), traits: splitList($("#p-traits").value),
      speech_style: $("#p-speech").value.trim(), catchphrases: splitList($("#p-catch").value),
      mannerisms: splitList($("#p-mann").value),
    },
  };
  try { await jpatch(`/api/characters/${id}`, body); $("#actor-msg").className = "hint ok"; $("#actor-msg").textContent = "Saved."; refreshCharacters(); }
  catch (err) { $("#actor-msg").className = "hint err"; $("#actor-msg").textContent = "Error: " + err.message; }
}

// ---------- channels ----------
async function refreshChannels() {
  channels = await api("/api/channels");
  $("#channel-grid").innerHTML = channels.length
    ? channels.map(channelCard).join("")
    : `<p class="empty">No channels yet — a channel is a series (premise + cast + format).</p>`;
  renderEpFilters();
}

function channelCard(ch) {
  const roster = ch.roster.map((r) =>
    `<span class="cast-chip" title="${esc(r.role)}">${esc(r.name)} <small>${esc(r.role)}${r.has_reference ? " 📸" : ""}${r.has_voice ? " 🎤" : ""}</small></span>`).join("") || `<span class="muted">no cast</span>`;
  return `<div class="channel-card">
    <div class="ch-head"><b>${esc(ch.name)}</b> <small>${esc(ch.platform)} · ${esc(ch.format)}</small></div>
    <div class="ch-premise">${esc(ch.premise || "no premise")}</div>
    <div class="roster">${roster}</div>
    <div class="ch-meta">${ch.target_scene_count} scenes · ${ch.target_duration_s}s · budget ${ch.video_budget} · ${esc(ch.writer_provider)} · <span class="art">${esc(ch.art_style || "no style")}</span></div>
    <div class="actor-actions"><button class="linklike" data-new-ep="${ch.channel_id}">+ episode</button></div>
  </div>`;
}

$("#new-channel-btn").addEventListener("click", () => {
  const f = $("#channel-form"); f.hidden = !f.hidden;
  if (!f.hidden) $("#cast-picker").innerHTML = characters.length
    ? characters.map((c) => `<label class="cast-opt"><input type="checkbox" value="${c.character_id}" /> ${esc(c.name)}</label>`).join("")
    : `<span class="muted">create characters first to cast them</span>`;
});
$("#channel-cancel").addEventListener("click", () => { $("#channel-form").hidden = true; });
$("#channel-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#channel-msg");
  const picked = [...document.querySelectorAll("#cast-picker input:checked")].map((i) => i.value);
  const cast = picked.map((id, i) => ({ character_id: id, role: i === 0 ? "lead" : "sidekick" }));
  try {
    await jpost("/api/channels", {
      name: $("#ch-name").value.trim(), platform: $("#ch-platform").value, format: $("#ch-format").value,
      premise: $("#ch-premise").value.trim(), art_style: $("#ch-style").value.trim(),
      target_scene_count: Number($("#ch-scenes").value), target_duration_s: Number($("#ch-dur").value),
      video_budget: Number($("#ch-budget").value), writer_provider: $("#ch-writer").value, cast,
    });
    $("#channel-form").reset(); $("#channel-form").hidden = true; msg.textContent = "";
    refreshChannels();
  } catch (err) { msg.className = "hint err"; msg.textContent = "Error: " + err.message; }
});

// ---------- episodes ----------
async function refreshEpisodes() {
  episodes = await api("/api/episodes");
  const shown = episodes.filter((e) => epFilter === "all" || e.channel_id === epFilter);
  $("#ep-empty").style.display = episodes.length ? "none" : "block";
  $("#ep-body").innerHTML = shown.map(epRow).join("");
}
function renderEpFilters() {
  const opts = [`<button data-epf="all" class="${epFilter === "all" ? "active" : ""}">all</button>`]
    .concat(channels.map((c) => `<button data-epf="${c.channel_id}" class="${epFilter === c.channel_id ? "active" : ""}">${esc(c.name)}</button>`));
  $("#ep-filters").innerHTML = opts.join("");
}
function stepper(ep) {
  return `<div class="stepper">` + ep.stages.map((st, i) =>
    `<span class="step ${i < ep.stage_index ? "done" : i === ep.stage_index ? "cur" : ""}">${esc(st)}</span>`).join("<i>›</i>") + `</div>`;
}
function epRow(e) {
  return `<tr>
    <td>${esc(e.channel_name)}</td><td>${e.number}</td><td>${esc(e.title)}</td>
    <td>${stepper(e)} <small class="muted">${esc(e.stage_status)}</small></td>
    <td><button class="linklike" data-episode="${e.episode_id}">open →</button></td></tr>`;
}
async function newEpisode(channelId) {
  const title = prompt("Episode title (optional):") || "";
  try { await jpost("/api/episodes", { channel_id: channelId, title }); refreshEpisodes(); refreshSummary(); }
  catch (err) { alert("Error: " + err.message); }
}
async function openEpisode(id) {
  const e = await api(`/api/episodes/${id}`);
  $("#drawer-body").innerHTML = `
    <h2>${esc(e.title)}</h2>
    <div class="fsn">${esc(e.channel_name)} · episode ${e.number}</div>
    ${stepper(e)}
    <div class="kv">
      <div class="k">Stage</div><div class="v">${esc(e.stage)} · ${esc(e.stage_status)}</div>
      <div class="k">Cast</div><div class="v">${e.cast.length} actor(s)</div>
      <div class="k">Scenes</div><div class="v">${e.scene_count}</div>
      <div class="k">Est / spent</div><div class="v">~$${Number(e.est_cost_usd || 0).toFixed(2)} / $${Number(e.spent_usd || 0).toFixed(2)}</div>
    </div>
    <p class="muted">Production stages (Ideate → Script → Refs → Scenes → Audio → Assemble) are wired in the next milestones. This is the episode shell.</p>`;
  $("#backdrop").hidden = false; $("#drawer").hidden = false;
}

// ---------- events + polling ----------
function closeDrawer() { $("#backdrop").hidden = true; $("#drawer").hidden = true; }
$("#drawer-close").addEventListener("click", closeDrawer);
$("#backdrop").addEventListener("click", closeDrawer);
document.addEventListener("click", (e) => {
  const t = e.target;
  if (t.dataset.editActor) return openActor(t.dataset.editActor);
  if (t.dataset.upload) { uploadTarget = t.dataset.upload; fileInput.click(); return; }
  if (t.dataset.actor) return saveActor(t.dataset.actor);
  if (t.dataset.newEp) return newEpisode(t.dataset.newEp);
  if (t.dataset.episode) return openEpisode(t.dataset.episode);
  if (t.dataset.epf) { epFilter = t.dataset.epf; renderEpFilters(); refreshEpisodes(); }
});

async function refreshAll() { try { await Promise.all([refreshSummary(), refreshCharacters(), refreshChannels(), refreshEpisodes()]); } catch (e) {} }
refreshAll();
setInterval(refreshSummary, 8000);
