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
    <div class="kv2" style="margin-top:10px">
      <label>Look / appearance <small>(text description; your reference photos override this for generation)</small>
        <textarea id="c-dnaprompt" rows="2">${esc(c.dna_prompt || "")}</textarea></label>
    </div>
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
    dna_prompt: $("#c-dnaprompt").value.trim(),
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
    <div class="actor-actions"><button class="linklike" data-new-ep="${ch.channel_id}">+ episode</button>
      <button class="linklike" data-edit-channel="${ch.channel_id}">edit</button></div>
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

// edit channel drawer
function _opt(val, cur, label) { return `<option value="${val}" ${val === cur ? "selected" : ""}>${label || val}</option>`; }
async function openChannel(id) {
  const c = await api(`/api/channels/${id}`);
  const casts = characters.map((ch) => {
    const inCast = (c.cast || []).find((m) => m.character_id === ch.character_id);
    return `<label class="cast-opt"><input type="checkbox" value="${ch.character_id}" ${inCast ? "checked" : ""}/> ${esc(ch.name)}</label>`;
  }).join("") || `<span class="muted">no characters</span>`;
  $("#drawer-body").innerHTML = `
    <h2>Edit channel</h2>
    <div class="fsn">${esc(c.slug)}</div>
    <div class="kv2">
      <label>Name <input id="ec-name" value="${esc(c.name)}"/></label>
      <label>Platform <input id="ec-platform" value="${esc(c.platform)}"/></label>
      <label>Format <select id="ec-format">${_opt("long_form", c.format)}${_opt("short_form", c.format)}</select></label>
      <label>Art style <input id="ec-style" value="${esc(c.art_style)}"/></label>
      <label>Premise <textarea id="ec-premise" rows="3">${esc(c.premise)}</textarea></label>
      <label>Narrator voice <input id="ec-narr" value="${esc(c.narrator_voice_id)}"/></label>
      <div class="row2">
        <label>Scenes <input type="number" id="ec-scenes" value="${c.target_scene_count}"/></label>
        <label>Duration (s) <input type="number" id="ec-dur" value="${c.target_duration_s}"/></label>
      </div>
      <div class="row2">
        <label>Video budget <input type="number" id="ec-budget" value="${c.video_budget}"/></label>
        <label>Writer <input id="ec-writer" value="${esc(c.writer_provider)}"/></label>
      </div>
    </div>
    <div class="section-title">Cast <small>(first checked = lead)</small></div>
    <div id="ec-cast" class="cast-picker">${casts}</div>
    <div class="post-actions"><button id="ec-save" data-channel="${c.channel_id}">Save channel</button></div>
    <p class="hint" id="ec-msg"></p>`;
  $("#backdrop").hidden = false; $("#drawer").hidden = false;
}
async function saveChannel(id) {
  const picked = [...document.querySelectorAll("#ec-cast input:checked")].map((i) => i.value);
  const cast = picked.map((cid, i) => ({ character_id: cid, role: i === 0 ? "lead" : "sidekick" }));
  const body = {
    name: $("#ec-name").value.trim(), platform: $("#ec-platform").value.trim(), format: $("#ec-format").value,
    art_style: $("#ec-style").value.trim(), premise: $("#ec-premise").value.trim(),
    narrator_voice_id: $("#ec-narr").value.trim(), target_scene_count: Number($("#ec-scenes").value),
    target_duration_s: Number($("#ec-dur").value), video_budget: Number($("#ec-budget").value),
    writer_provider: $("#ec-writer").value.trim(), cast,
  };
  try { await jpatch(`/api/channels/${id}`, body); $("#ec-msg").className = "hint ok"; $("#ec-msg").textContent = "Saved."; refreshChannels(); }
  catch (err) { $("#ec-msg").className = "hint err"; $("#ec-msg").textContent = "Error: " + err.message; }
}

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
    <td class="ep-actions"><button class="linklike" data-episode="${e.episode_id}">open →</button>
      <button class="linklike del" data-del-ep="${e.episode_id}" title="delete episode">🗑</button></td></tr>`;
}
async function delEpisode(id) {
  if (!confirm("Delete this episode and its generated media? This can't be undone.")) return;
  try {
    await api(`/api/episodes/${id}`, { method: "DELETE" });
    if (!$("#drawer").hidden) closeDrawer();
    refreshEpisodes(); refreshSummary();
  } catch (err) { alert("Error: " + err.message); }
}
async function newEpisode(channelId) {
  const title = prompt("Episode title (optional):") || "";
  try { await jpost("/api/episodes", { channel_id: channelId, title }); refreshEpisodes(); refreshSummary(); }
  catch (err) { alert("Error: " + err.message); }
}
let curEpisode = null;
async function openEpisode(id) {
  curEpisode = await api(`/api/episodes/${id}`);
  renderEpisode();
  $("#backdrop").hidden = false; $("#drawer").hidden = false;
}

const SHOT_LABEL = { broll: "b-roll", still_kenburns: "Ken Burns", lipsync_still: "lip-sync", hero_video: "hero video" };

function ideaCard(idea, i, canApprove) {
  const beats = (idea.beats || []).map((b) => `<li>${esc(b)}</li>`).join("");
  const badge = idea.model_label ? `<span class="model-badge">${esc(idea.model_label)}</span>` : "";
  return `<div class="idea-card">
    <div class="idea-title"><b>${esc(idea.title || "Untitled")}</b>${badge}</div>
    <div class="idea-log">${esc(idea.logline || "")}</div>
    ${idea.hook ? `<div class="idea-hook"><span>hook</span> ${esc(idea.hook)}</div>` : ""}
    ${beats ? `<ul class="idea-beats">${beats}</ul>` : ""}
    ${canApprove ? `<button class="mini" data-approve-idea="${curEpisode.episode_id}" data-choice="${i}">use this ✓</button>` : ""}
  </div>`;
}

function sceneRow(s) {
  const dlg = (s.dialogue || []).length ? `💬 ${s.dialogue.length}` : "";
  return `<div class="scene-row">
    <div class="scene-seq">${s.seq + 1}</div>
    <div class="scene-body">
      <div class="scene-head"><b>${esc(s.heading || "scene")}</b>
        <span class="shot shot-${s.shot_type}">${SHOT_LABEL[s.shot_type] || s.shot_type}</span>
        <small>${s.duration_s}s ${dlg}</small></div>
      <div class="scene-action">${esc(s.action || "")}</div>
      ${s.narration ? `<div class="scene-vo">🎙 ${esc(s.narration)}</div>` : ""}
      ${(s.dialogue || []).map((d) => `<div class="scene-line"><b>${esc(nameOf(d.speaker))}</b>: ${esc(d.line)}${d.delivery ? ` <em>(${esc(d.delivery)})</em>` : ""}</div>`).join("")}
    </div></div>`;
}
function nameOf(cid) { const c = characters.find((x) => x.character_id === cid); return c ? c.name : "?"; }

function refTile(s) {
  const ri = s.reference_image || {};
  const img = s.still_url
    ? `<img src="${s.still_url}?t=${Date.now()}" />`
    : `<div class="ph-tile">${ri.status === "failed" ? "✕ failed" : "—"}</div>`;
  const hero = s.shot_type === "hero_video" && s.clip_url ? `<span class="clip-tag">▶ clip</span>` : "";
  return `<div class="ref-tile">
    <div class="rt-img">${img}${hero}</div>
    <div class="rt-meta"><span class="shot shot-${s.shot_type}">${SHOT_LABEL[s.shot_type] || s.shot_type}</span>
      <small>#${s.seq + 1}</small>
      <button class="linklike" data-reroll="${curEpisode.episode_id}" data-seq="${s.seq}">re-roll</button></div>
  </div>`;
}

function stagePanel(e) {
  const busy = e.stage_status === "generating";
  const err = e.stage_error ? `<div class="err-banner">${esc(e.stage_error)}</div>` : "";
  const est = Number(e.stage_estimate_usd || 0).toFixed(2);
  // REFS — preview one, then batch the rest
  if (e.stage === "refs") {
    const unit = Number(e.image_unit_cost || 0);
    const previewCost = unit.toFixed(3);
    const batchN = Math.max(0, e.scene_count - 1);
    const batchCost = (batchN * unit).toFixed(2);
    const styleBox = `<label class="brief-label">Style note <small>(optional — applied to every reference image)</small>
      <textarea id="style-note" rows="2" placeholder="e.g. warmer lighting; more cinematic wide shots; less saturated; softer film grain">${esc(e.style_note || "")}</textarea></label>`;
    // preview ready, not yet batched → approve the look or tweak the style note
    if (e.stage_status === "awaiting_review" && !e.refs_batch_done) {
      const p = e.scenes.find((s) => s.still_url) || e.scenes[0] || {};
      const pimg = p.still_url ? `<img class="preview-img" src="${p.still_url}?t=${Date.now()}"/>` : `<div class="ph-tile big">preview failed — regenerate</div>`;
      return `${err}<div class="section-title">Preview — approve the look before generating all ${e.scene_count} images</div>
        <div class="preview-cap">Scene ${(p.seq ?? 0) + 1}: ${esc(p.heading || "")} · ${esc((p.cast_present || []).length ? "features cast" : "no cast")}</div>
        <div class="preview-wrap">${pimg}</div>
        ${styleBox}
        <div class="gate-row">
          <button data-refs-batch="${e.episode_id}">✓ Looks good — generate all ${batchN} more (~$${batchCost})</button>
          <button class="ghost" data-run-refs="${e.episode_id}">↻ regenerate preview (~$${previewCost})</button>
        </div>`;
    }
    // full batch done → review grid + approve
    if (e.stage_status === "awaiting_review" && e.refs_batch_done) {
      return `${err}<div class="section-title">Reference images (${e.refs_done_count}/${e.scene_count}) — re-roll any weak frame before video</div>
        <div class="ref-grid">${e.scenes.map(refTile).join("")}</div>
        <div class="gate-row"><button data-approve-generic="${e.episode_id}">Approve references ✓</button>
          <button class="ghost" data-run-refs="${e.episode_id}">↻ start over (new preview)</button></div>`;
    }
    // initial → generate the single preview
    return `${err}<div class="section-title">Reference images — preview first</div>
      <p class="muted">Generate ONE preview to approve the look (and tweak the style), then batch the rest. ~$${previewCost}/image via Gemini.</p>
      ${styleBox}
      <button data-run-refs="${e.episode_id}" ${busy ? "disabled" : ""}>${busy ? "working…" : `🎨 Generate preview image (~$${previewCost})`}</button>`;
  }
  // SCENES
  if (e.stage === "scenes") {
    const hero = e.scenes.filter((s) => s.shot_type === "hero_video").length;
    if (e.stage_status === "awaiting_review") {
      return `${err}${e.rough_cut_url ? `<video controls preload="metadata" src="${e.rough_cut_url}?t=${Date.now()}"></video>` : ""}
        <div class="section-title">Silent rough cut — ${hero} hero video, rest Ken Burns (audio comes next)</div>
        <div class="ref-grid">${e.scenes.map(refTile).join("")}</div>
        <div class="gate-row"><button data-approve-generic="${e.episode_id}">Approve cut ✓</button>
          <button class="ghost" data-run-paid="${e.episode_id}">↻ re-render (~$${est})</button></div>`;
    }
    return `${err}<div class="section-title">Render scenes</div>
      <p class="muted">Generate motion: <b>${hero}</b> hero-video shot(s); the rest use free Ken Burns on their stills, then stitch a silent rough cut with crossfades. ≈ <b>$${est}</b>.</p>
      <button data-run-paid="${e.episode_id}" ${busy ? "disabled" : ""}>${busy ? "working…" : `🎬 Render scenes (~$${est})`}</button>`;
  }
  // AUDIO
  if (e.stage === "audio") {
    if (e.stage_status === "awaiting_review") {
      return `${err}${e.audio_cut_url ? `<video controls preload="metadata" src="${e.audio_cut_url}?t=${Date.now()}"></video>` : ""}
        <div class="section-title">Voiced cut — review with 🔊 sound. Re-roll a scene if a voice is off.</div>
        <div class="ref-grid">${e.scenes.map(refTile).join("")}</div>
        <div class="gate-row"><button data-approve-generic="${e.episode_id}">Approve audio ✓</button>
          <button class="ghost" data-run-paid="${e.episode_id}">↻ regenerate all (~$${est})</button></div>`;
    }
    return `${err}<div class="section-title">Audio — voices + music</div>
      <p class="muted">Narrator VO + each character's voice (their locked Voice DNA) + a music bed; lip-sync on talking shots, then a voiced cut. ≈ <b>$${est}</b>.</p>
      <button data-run-paid="${e.episode_id}" ${busy ? "disabled" : ""}>${busy ? "working…" : `🔊 Generate voices + music (~$${est})`}</button>`;
  }
  // ASSEMBLY
  if (e.stage === "assembly") {
    if (e.stage_status === "awaiting_review") {
      return `${err}${e.final_url ? `<video controls preload="metadata" src="${e.final_url}?t=${Date.now()}"></video>` : ""}
        <div class="section-title">Final cut — last look</div>
        <div class="gate-row"><button data-approve-generic="${e.episode_id}">Approve &amp; finish ✓</button>
          ${e.final_url ? `<a class="ghost dl" href="${e.final_url}" download>⬇ download</a>` : ""}</div>`;
    }
    return `${err}<div class="section-title">Assemble final</div>
      <p class="muted">Build the final cut + editable timeline (EDL). Free — no generation spend.</p>
      <button data-run="${e.episode_id}" ${busy ? "disabled" : ""}>${busy ? "working…" : "🎬 Assemble final"}</button>`;
  }
  // DONE
  if (e.stage === "done") {
    return `<div class="done-banner">✓ Episode complete</div>
      ${e.final_url ? `<video controls preload="metadata" src="${e.final_url}?t=${Date.now()}"></video>
        <div class="gate-row"><a class="dl-btn" href="${e.final_url}" download>⬇ Download episode</a></div>` : ""}`;
  }
  // IDEA
  if (e.stage === "idea") {
    const briefBox = `<label class="brief-label">Idea brief <small>(optional — steer what gets generated)</small>
      <textarea id="idea-brief" rows="2" placeholder="e.g. a rainy-night stakeout; introduce a cat burglar villain; keep it lighthearted">${esc(e.idea_brief || "")}</textarea></label>`;
    if (e.stage_status === "awaiting_review" && e.idea_candidates.length) {
      return `${err}<div class="section-title">Pick an episode idea — one from each model (the winner writes the script)</div>
        <div class="idea-grid">${e.idea_candidates.map((x, i) => ideaCard(x, i, true)).join("")}</div>
        ${briefBox}
        <div class="gate-row"><button class="ghost" data-run-idea="${e.episode_id}">↻ regenerate ideas</button></div>`;
    }
    return `${err}<div class="section-title">Ideate — a panel of models</div>
      <p class="muted">All models propose an idea at once (Opus 4.8 · GPT-5.5 · DeepSeek V4 Pro · GLM 5.2), grounded in the channel premise + cast and steered by your brief. Pick the best — that model writes the script.</p>
      ${briefBox}
      <button data-run-idea="${e.episode_id}" ${busy ? "disabled" : ""}>${busy ? "working…" : "✨ Generate ideas (all models)"}</button>`;
  }
  // SCRIPT
  if (e.stage === "script") {
    const chosen = e.idea && e.idea.title ? `<div class="chosen">📌 <b>${esc(e.idea.title)}</b> — ${esc(e.idea.logline || "")}</div>` : "";
    if (e.stage_status === "awaiting_review" && e.scenes.length) {
      return `${err}${chosen}<div class="section-title">Script — ${e.scenes.length} scenes</div>
        <div class="scene-list">${e.scenes.map(sceneRow).join("")}</div>
        <div class="gate-row">
          <button data-approve-script="${e.episode_id}">Approve script ✓</button>
          <button class="ghost" data-run="${e.episode_id}">↻ rewrite</button>
        </div>`;
    }
    return `${err}${chosen}<div class="section-title">Script</div>
      <p class="muted">Expand the idea into a scene-by-scene script (dialogue, narration, shot types). Text only.</p>
      <button data-run="${e.episode_id}" ${busy ? "disabled" : ""}>${busy ? "working…" : "✍ Write script"}</button>`;
  }
  return `${err}<div class="stage-next">Stage <b>${esc(e.stage)}</b>.</div>`;
}

function renderEpisode() {
  const e = curEpisode;
  $("#drawer-body").innerHTML = `
    <h2>${esc(e.title)}</h2>
    <div class="fsn">${esc(e.channel_name)} · episode ${e.number} · <small>${esc(e.stage)}/${esc(e.stage_status)}</small></div>
    ${stepper(e)}
    <div class="ep-meta"><span>${e.cast.length} cast</span> · <span>${e.scene_count} scenes</span> · <span>writer ${esc(e.writer_model || "—")}</span> · <span>spent $${Number(e.spent_usd || 0).toFixed(3)}</span></div>
    ${stagePanel(e)}
    ${(e.history || []).length ? `<div class="section-title">History</div><div class="timeline">${e.history.slice().reverse().map((h) => `<div class="ev"><div class="name">${esc(h.event)}</div><div class="det">${esc(JSON.stringify(h.detail))}</div></div>`).join("")}</div>` : ""}`;
}

async function epAction(fn) {
  try { curEpisode = await fn(); renderEpisode(); refreshEpisodes(); refreshSummary(); }
  catch (err) { alert("Error: " + err.message); }
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
  if (t.dataset.editChannel) return openChannel(t.dataset.editChannel);
  if (t.dataset.channel) return saveChannel(t.dataset.channel);
  if (t.dataset.delEp) return delEpisode(t.dataset.delEp);
  if (t.dataset.episode) return openEpisode(t.dataset.episode);
  if (t.dataset.runIdea) {
    const brief = ($("#idea-brief") ? $("#idea-brief").value : "").trim();
    if (curEpisode) { curEpisode.stage_status = "generating"; curEpisode.idea_brief = brief; renderEpisode(); }
    return epAction(() => jpost(`/api/episodes/${t.dataset.runIdea}/run`, { brief }));
  }
  if (t.dataset.run) { if (curEpisode) { curEpisode.stage_status = "generating"; renderEpisode(); } return epAction(() => jpost(`/api/episodes/${t.dataset.run}/run`, {})); }
  if (t.dataset.runPaid) {
    const est = curEpisode ? Number(curEpisode.stage_estimate_usd || 0).toFixed(2) : "?";
    if (!confirm(`This runs a PAID stage — approx $${est} of generation. Continue?`)) return;
    if (curEpisode) { curEpisode.stage_status = "generating"; renderEpisode(); }
    return epAction(() => jpost(`/api/episodes/${t.dataset.runPaid}/run`, {}));
  }
  if (t.dataset.runRefs) {
    const sn = ($("#style-note") ? $("#style-note").value : "").trim();
    if (curEpisode) { curEpisode.stage_status = "generating"; curEpisode.style_note = sn; renderEpisode(); }
    return epAction(() => jpost(`/api/episodes/${t.dataset.runRefs}/run`, { style_note: sn }));
  }
  if (t.dataset.refsBatch) {
    const sn = ($("#style-note") ? $("#style-note").value : "").trim();
    const n = curEpisode ? Math.max(0, curEpisode.scene_count - 1) : 0;
    const cost = curEpisode ? (n * Number(curEpisode.image_unit_cost || 0)).toFixed(2) : "?";
    if (!confirm(`Generate ${n} more reference images (~$${cost})? The preview look will be applied to all.`)) return;
    if (curEpisode) { curEpisode.stage_status = "generating"; renderEpisode(); }
    return epAction(() => jpost(`/api/episodes/${t.dataset.refsBatch}/refs/batch`, { style_note: sn }));
  }
  if (t.dataset.reroll) return epAction(() => jpost(`/api/episodes/${t.dataset.reroll}/scene/${t.dataset.seq}/reroll`, {}));
  if (t.dataset.approveIdea) return epAction(() => jpost(`/api/episodes/${t.dataset.approveIdea}/approve`, { choice: Number(t.dataset.choice) }));
  if (t.dataset.approveScript) return epAction(() => jpost(`/api/episodes/${t.dataset.approveScript}/approve`, {}));
  if (t.dataset.approveGeneric) return epAction(() => jpost(`/api/episodes/${t.dataset.approveGeneric}/approve`, {}));
  if (t.dataset.epf) { epFilter = t.dataset.epf; renderEpFilters(); refreshEpisodes(); }
});

async function refreshAll() { try { await Promise.all([refreshSummary(), refreshCharacters(), refreshChannels(), refreshEpisodes()]); } catch (e) {} }
refreshAll();
setInterval(refreshSummary, 8000);
