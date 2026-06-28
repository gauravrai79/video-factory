"use strict";
const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then(async (r) => {
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
  return j;
});
const jpost = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const STATES = ["pending", "generating", "finishing", "qc", "approved", "rework", "delivered", "failed"];
let filter = "all";
let pollTimer = null;
let characters = [];

const fmtUsd = (n) => (n == null ? "—" : "$" + Number(n).toFixed(n < 1 ? 3 : 2));
const fmtDur = (s) => {
  if (s == null) return "—";
  if (s < 90) return Math.round(s) + "s";
  if (s < 5400) return Math.round(s / 60) + "m";
  return (s / 3600).toFixed(1) + "h";
};
const esc = (x) => String(x ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---- header + stats ----
async function refreshSummary() {
  const s = await api("/api/summary");
  $("#env-chips").innerHTML = [
    `<span class="chip"><b>${esc(s.tenant)}</b> / ${esc(s.project)}</span>`,
    `<span class="chip">queue <b>${esc(s.queue_backend)}</b></span>`,
    `<span class="chip">img <b>${esc(s.image_model)}</b></span>`,
    `<span class="chip">vid <b>${esc(s.video_model)}</b></span>`,
    `<span class="chip">ceiling <b>${fmtUsd(s.cost_ceiling_usd)}</b></span>`,
    s.fal_key_present ? `<span class="chip ok">fal.ai ✓ live</span>`
                      : `<span class="chip warn">fal.ai key missing (dry-run only)</span>`,
  ].join("");

  const d = s.drain || {};
  const draining = d.running;
  const pct = d.total ? Math.round((d.done / d.total) * 100) : 0;
  const cards = [
    ["Characters", s.characters],
    ["Posts", s.total_jobs],
    ["Delivered", (s.by_state.delivered || 0)],
    ["In flight", (s.by_state.generating || 0) + (s.by_state.finishing || 0) + (s.by_state.pending || 0)],
    ["Awaiting QC", (s.by_state.qc || 0)],
    ["Rework / failed", (s.by_state.rework || 0) + (s.by_state.failed || 0)],
    ["Spent", `<small>${fmtUsd(s.spent_usd)}</small>`],
    ["SLA breaches", s.sla_breaches],
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const drainCard = `<div class="stat"><div class="k">Worker</div>
    <div class="v">${draining ? `${d.done}/${d.total}` : "idle"}</div>
    ${draining ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ""}</div>`;
  $("#stats").innerHTML = cards + drainCard;

  const banner = $("#worker-banner");
  if (draining) {
    banner.hidden = false; banner.className = "worker-banner run";
    banner.innerHTML = `<span class="spin"></span> Worker running — generating &amp; assembling posts… <b>${d.done}/${d.total}</b> done`;
  } else { banner.hidden = true; }
  setPoll(draining ? 1200 : 5000);
}

// ---- characters ----
async function refreshCharacters() {
  characters = await api("/api/characters");
  $("#char-list").innerHTML = characters.length
    ? characters.map((c) => `<div class="char-chip" title="${esc(c.dna_prompt || "")}">
        <b>${esc(c.name)}</b> <small>${esc(c.species)}${c.reference_images && c.reference_images.length ? ` · ${c.reference_images.length} refs` : " · no refs"}</small></div>`).join("")
    : `<p class="empty">No characters yet — create one below.</p>`;
  const sel = $("#p-character");
  const cur = sel.value;
  sel.innerHTML = characters.map((c) => `<option value="${c.character_id}">${esc(c.name)} (${esc(c.slug)})</option>`).join("");
  if (cur) sel.value = cur;
}

$("#char-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#char-msg"), btn = $("#char-btn");
  const body = {
    name: $("#c-name").value.trim(),
    species: $("#c-species").value,
    dna_prompt: $("#c-dna").value.trim(),
    safety_tolerance: Number($("#c-safety").value) || 5,
    persona: { niche: $("#c-niche").value.trim() },
  };
  if (!body.name) return;
  btn.disabled = true; msg.className = "hint"; msg.textContent = "Creating…";
  try {
    await jpost("/api/characters", body);
    msg.className = "hint ok"; msg.textContent = `Created ${body.name}.`;
    $("#char-form").reset(); $("#c-safety").value = 5;
    await refreshCharacters();
  } catch (err) { msg.className = "hint err"; msg.textContent = "Error: " + err.message; }
  finally { btn.disabled = false; }
});

// ---- new post ----
function postBody() {
  return {
    character_id: $("#p-character").value,
    brief: $("#p-brief").value.trim(),
    format: $("#p-format").value,
    tags: $("#p-tags").value.split(",").map((t) => t.trim()).filter(Boolean),
    n_shots: Number($("#p-shots").value) || 6,
    video_budget: Number($("#p-video").value) || 0,
    execute: $("#p-execute").checked,
    human_qc: $("#p-human").checked,
  };
}

function renderPreview(sb) {
  const rows = sb.shots.map((s) =>
    `<tr><td>${s.seq}</td><td>${esc(s.template_key)}</td>
     <td><span class="mode ${s.render_mode === "video" ? "live" : "dry"}">${s.render_mode}</span></td>
     <td>${s.duration_s}s</td><td>${fmtUsd(s.est_cost_usd)}</td></tr>`).join("");
  $("#preview-box").hidden = false;
  $("#preview-box").innerHTML = `
    <div class="prev-head"><b>${esc(sb.slug)}</b> · ${sb.shots.length} shots · est <b>${fmtUsd(sb.est_cost_usd)}</b></div>
    <table class="prev-table"><thead><tr><th>#</th><th>scene</th><th>render</th><th>dur</th><th>est</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

$("#preview-btn").addEventListener("click", async () => {
  const msg = $("#post-msg");
  if (!$("#p-character").value) { msg.className = "hint err"; msg.textContent = "Create/select a character first."; return; }
  msg.className = "hint"; msg.textContent = "Planning…";
  try {
    const r = await jpost("/api/storyboards", { ...postBody(), create: false, refine: false });
    renderPreview(r.storyboard); msg.textContent = "";
  } catch (err) { msg.className = "hint err"; msg.textContent = "Error: " + err.message; }
});

$("#post-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#post-msg"), btn = $("#post-btn");
  const body = postBody();
  if (!body.character_id) { msg.className = "hint err"; msg.textContent = "Select a character."; return; }
  if (body.execute && !confirm("Execute mode makes REAL paid fal.ai calls. Continue?")) return;
  btn.disabled = true; msg.className = "hint"; msg.textContent = "Creating…";
  try {
    const r = await jpost("/api/storyboards", { ...body, create: true, run: true });
    const warn = (r.warnings || []).length ? " ⚠ " + r.warnings.map(esc).join(" ") : "";
    msg.className = warn ? "hint err" : "hint ok";
    msg.innerHTML = `Post <b>${esc(r.slug)}</b> created (est ${fmtUsd(r.est_cost_usd)}).` +
      (r.blocked_run ? " <b>Run blocked</b> — no FAL_KEY, so it stays pending." : r.drain_started ? " Worker started." : "") + warn;
    renderPreview(r.storyboard);
    refreshAll();
  } catch (err) { msg.className = "hint err"; msg.textContent = "Error: " + err.message; }
  finally { btn.disabled = false; }
});

// ---- posts table ----
async function refreshJobs() {
  const jobs = await api("/api/jobs");
  const shown = jobs.filter((j) => filter === "all" || j.state === filter);
  $("#empty").style.display = jobs.length ? "none" : "block";
  renderFilters(jobs);
  $("#jobs-body").innerHTML = shown.map(rowHtml).join("");
}

function renderFilters(jobs) {
  const counts = { all: jobs.length };
  for (const j of jobs) counts[j.state] = (counts[j.state] || 0) + 1;
  const opts = ["all", ...STATES.filter((s) => counts[s])];
  $("#filters").innerHTML = opts.map((s) =>
    `<button data-f="${s}" class="${filter === s ? "active" : ""}">${s} ${counts[s] || 0}</button>`).join("");
}

function slaBar(j) {
  const pct = Math.min(100, Math.round((j.sla.elapsed_s / j.sla.budget_s) * 100));
  return `<div class="sla-mini" title="${fmtDur(j.sla.elapsed_s)} / ${fmtDur(j.sla.budget_s)}">
    <div class="bar ${j.sla.breached ? "breach" : ""}"><i style="width:${pct}%"></i></div></div>`;
}

function outputCell(j) {
  if (j.media.delivered) return `<a class="play" href="/api/media/delivered/${esc(j.slug)}" target="_blank">▶ play</a>`;
  if (j.media.finished) return `<a class="play" href="/api/media/finished/${esc(j.slug)}" target="_blank">▶ play</a>`;
  return `<span class="dash">—</span>`;
}

function costCell(j) {
  if (j.cost_usd != null) return `<b>${fmtUsd(j.cost_usd)}</b>`;
  return `<span class="est">~${fmtUsd(j.est_cost_usd)}<em>est</em></span>`;
}

function rowHtml(j) {
  const mode = j.execute ? `<span class="mode live">live</span>` : `<span class="mode dry">dry</span>`;
  const errFlag = j.state === "failed" && j.error ? `<span class="row-err" title="${esc(j.error)}">⚠</span>` : "";
  return `<tr>
    <td class="prod">${esc(j.character || "—")}</td>
    <td class="fsn" title="${esc(j.brief)}">${esc(j.slug)}</td>
    <td>${esc(j.format)} ${mode}</td>
    <td>${esc(j.shots)}</td>
    <td><span class="badge s-${j.state}">${j.state}</span>${errFlag}</td>
    <td>${costCell(j)}</td>
    <td>${slaBar(j)}</td>
    <td>${outputCell(j)}</td>
    <td><button class="linklike" data-job="${j.job_id}">${j.state === "qc" ? "review →" : "view →"}</button></td>
  </tr>`;
}

// ---- drawer (post detail + QC) ----
async function openJob(jobId) {
  const v = await api(`/api/jobs/${jobId}`);
  const hasVideo = v.media.delivered || v.media.finished;
  const vsrc = v.media.delivered ? `/api/media/delivered/${v.slug}` : `/api/media/finished/${v.slug}`;
  const fin = v.finished || {};
  const qcBlock = v.state === "qc" ? `
    <div class="section-title">Human QC gate</div>
    <p>This post passed auto-checks and is awaiting a reviewer.</p>
    <div class="qc-actions">
      <button class="btn-approve" data-qc="approve" data-job="${v.job_id}">✓ Approve &amp; deliver</button>
      <button class="btn-reject" data-qc="reject" data-job="${v.job_id}">✕ Reject → rework</button>
    </div>` : "";
  const errBanner = v.error ? `<div class="err-banner"><b>Failed${v.failed_stage ? ` at ${esc(v.failed_stage)}` : ""}:</b> ${esc(v.error)}</div>` : "";
  const viol = (v.violations || []).map((x) => `<div class="viol">⚠ ${esc(x)}</div>`).join("");
  const vlmBlock = vlmHtml(v.vlm_qc);
  const held = v.held ? `<div class="held">⏸ held: ${esc(v.held)} — ${esc((v.result && v.result.note) || "")}</div>` : "";

  $("#drawer-body").innerHTML = `
    <h2>${esc(v.slug)}</h2>
    <div class="fsn">${esc(v.character)} · ${esc(v.format)} · <span class="badge s-${v.state}">${v.state}</span></div>
    ${hasVideo ? `<video controls preload="metadata" src="${vsrc}"></video>` : ""}
    ${errBanner}${held}${viol}${vlmBlock}
    ${qcBlock}
    <div class="kv">
      <div class="k">Brief</div><div class="v">${esc(v.brief || "—")}</div>
      <div class="k">Mode</div><div class="v">${v.execute ? "execute (paid)" : "dry-run"}${v.human_qc ? " · human QC" : ""}</div>
      <div class="k">Est / actual</div><div class="v">~${fmtUsd(v.est_cost_usd)} / ${fmtUsd(v.cost_usd)}</div>
      <div class="k">Shots</div><div class="v">${esc(v.shots)}</div>
      <div class="k">Priority</div><div class="v">${esc(v.priority)}</div>
      <div class="k">SLA</div><div class="v">${fmtDur(v.sla.elapsed_s)} / ${fmtDur(v.sla.budget_s)} ${v.sla.breached ? "⚠ BREACH" : "ok"}</div>
      ${fin.width ? `<div class="k">Output</div><div class="v">${fin.width}×${fin.height} · ${fin.duration_s}s · ${fin.size_mb}MB · ${fin.video_codec}</div>` : ""}
    </div>
    <div class="section-title">Audit trail <span class="${v.audit_chain_valid ? "chainok" : "chainbad"}">${v.audit_chain_valid ? "⛓ chain valid" : "⛓ CHAIN INVALID"}</span></div>
    <div class="timeline">${(v.audit || []).map(evHtml).join("")}</div>`;
  $("#backdrop").hidden = false; $("#drawer").hidden = false;
}

function vlmHtml(q) {
  if (!q) return "";
  if (!q.ran) return `<div class="vlm skip">🔍 Identity QC skipped${q.error ? ` — ${esc(q.error)}` : ""}</div>`;
  const issues = (q.issues || []).map((i) =>
    `<div class="vlm-issue ${esc(i.severity || "")}">${esc((i.severity || "").toUpperCase())} · ${esc(i.type || "")}: ${esc(i.detail || "")}</div>`).join("");
  const cls = q.passed ? "pass" : "fail";
  const head = q.passed ? "✓ Identity QC passed" : "⚠ Identity QC flagged — needs human review";
  return `<div class="vlm ${cls}"><b>${head}</b> <small>(${esc(q.model || "")})</small>
    ${q.summary ? `<div class="vlm-sum">${esc(q.summary)}</div>` : ""}${issues}</div>`;
}

function evHtml(e) {
  let det = "";
  try { det = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail); } catch { det = ""; }
  if (det === "{}" || det === '""') det = "";
  return `<div class="ev"><div class="name">${esc(e.event)}</div>${det ? `<div class="det">${esc(det)}</div>` : ""}</div>`;
}

function closeDrawer() { $("#backdrop").hidden = true; $("#drawer").hidden = true; }

async function qcDecide(jobId, approve) {
  const reason = approve ? "" : (prompt("Reason for rejection (optional):") || "rejected by reviewer");
  await jpost(`/api/jobs/${jobId}/qc`, { approve, reason });
  await openJob(jobId); refreshAll();
}

// ---- events ----
$("#run-btn").addEventListener("click", async () => { await api("/api/run", { method: "POST" }); refreshAll(); });
$("#drawer-close").addEventListener("click", closeDrawer);
$("#backdrop").addEventListener("click", closeDrawer);

document.addEventListener("click", (e) => {
  const job = e.target.closest("[data-job]");
  if (job && e.target.dataset.qc) return qcDecide(job.dataset.job, e.target.dataset.qc === "approve");
  if (job) return openJob(job.dataset.job);
  const f = e.target.closest("[data-f]");
  if (f) { filter = f.dataset.f; refreshJobs(); }
});

// ---- polling ----
function setPoll(ms) {
  if (pollTimer && pollTimer.ms === ms) return;
  if (pollTimer) clearInterval(pollTimer.id);
  pollTimer = { ms, id: setInterval(refreshAll, ms) };
}
async function refreshAll() {
  try { await Promise.all([refreshSummary(), refreshCharacters(), refreshJobs()]); } catch (e) { /* transient */ }
}
refreshAll();
setPoll(5000);
