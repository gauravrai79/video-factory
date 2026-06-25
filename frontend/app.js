"use strict";
const $ = (s) => document.querySelector(s);
const api = (p, o) => fetch(p, o).then(async (r) => {
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
  return j;
});

const STATES = ["pending", "generating", "finishing", "qc", "approved", "rework", "delivered", "failed"];
let filter = "all";
let pollTimer = null;

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
    `<span class="chip">spec <b>${esc(s.spec)}</b></span>`,
    `<span class="chip">ceiling <b>${fmtUsd(s.cost_ceiling_usd)}</b></span>`,
    s.fal_key_present ? `<span class="chip ok">fal.ai ✓ live</span>`
                      : `<span class="chip warn">fal.ai key missing (dry-run only)</span>`,
  ].join("");

  const d = s.drain || {};
  const draining = d.running;
  const pct = d.total ? Math.round((d.done / d.total) * 100) : 0;
  const cards = [
    ["Total jobs", s.total_jobs],
    ["Delivered", (s.by_state.delivered || 0)],
    ["In flight", (s.by_state.generating || 0) + (s.by_state.finishing || 0) + (s.by_state.pending || 0)],
    ["Awaiting QC", (s.by_state.qc || 0)],
    ["Rework / failed", (s.by_state.rework || 0) + (s.by_state.failed || 0)],
    ["Spent (real)", `<small>${fmtUsd(s.spent_usd)}</small>`],
    ["SLA breaches", s.sla_breaches],
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const drainCard = `<div class="stat"><div class="k">Worker</div>
    <div class="v">${draining ? `${d.done}/${d.total}` : "idle"}</div>
    ${draining ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ""}</div>`;
  $("#stats").innerHTML = cards + drainCard;

  // live worker banner — the at-a-glance "what's happening right now"
  const banner = $("#worker-banner");
  if (draining) {
    banner.hidden = false; banner.className = "worker-banner run";
    banner.innerHTML = `<span class="spin"></span> Worker running — generating &amp; finishing clips… <b>${d.done}/${d.total}</b> done`;
  } else {
    banner.hidden = true;
  }
  // poll faster while the worker is draining
  setPoll(draining ? 1200 : 5000);
}

// ---- jobs table ----
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
  if (j.media.delivered) return `<a class="play" href="/api/media/delivered/${j.fsn}" target="_blank">▶ play</a>`;
  if (j.media.finished) return `<a class="play" href="/api/media/finished/${j.fsn}" target="_blank">▶ play</a>`;
  return `<span class="dash">—</span>`;
}

function costCell(j) {
  // Real spend ONLY for execute jobs. Dry runs show the price as an estimate, never as spend.
  if (j.execute) {
    return j.cost_usd != null ? `<b>${fmtUsd(j.cost_usd)}</b>`
                              : `<span class="dash">~${fmtUsd(j.est_cost_usd)}</span>`;
  }
  return `<span class="est">~${fmtUsd(j.cost_usd ?? j.est_cost_usd)}<em>est</em></span>`;
}

function rowHtml(j) {
  const model = (j.model || "—") + (j.fell_back ? " ⤳" : "");
  const mode = j.execute ? `<span class="mode live">live</span>` : `<span class="mode dry">dry</span>`;
  const errFlag = j.state === "failed" && j.error ? `<span class="row-err" title="${esc(j.error)}">⚠</span>` : "";
  const imgFlag = !j.has_image ? `<span class="row-err" title="no image_url — generation will fail">⚠ no image</span>` : "";
  return `<tr>
    <td class="fsn" title="${esc(j.fsn)}">${esc(j.fsn)}</td>
    <td class="prod" title="${esc(j.title)}">${esc(j.title || "—")} ${imgFlag}</td>
    <td>${esc(j.tier)}</td>
    <td>${esc(model)} ${mode}</td>
    <td><span class="badge s-${j.state}">${j.state}</span>${errFlag}</td>
    <td>${costCell(j)}</td>
    <td>${slaBar(j)}</td>
    <td>${outputCell(j)}</td>
    <td><button class="linklike" data-job="${j.job_id}">${j.state === "qc" ? "review →" : "view →"}</button></td>
  </tr>`;
}

// ---- drawer (job detail + QC) ----
async function openJob(jobId) {
  const j = await api(`/api/jobs/${jobId}`);
  const v = j;
  const hasVideo = v.media.delivered || v.media.finished;
  const vsrc = v.media.delivered ? `/api/media/delivered/${v.fsn}` : `/api/media/finished/${v.fsn}`;
  const fin = v.finished || {};
  const qcBlock = v.state === "qc" ? `
    <div class="section-title">Human QC gate</div>
    <p>This clip passed auto-checks and is awaiting a reviewer.</p>
    <div class="qc-actions">
      <button class="btn-approve" data-qc="approve" data-job="${v.job_id}">✓ Approve &amp; deliver</button>
      <button class="btn-reject" data-qc="reject" data-job="${v.job_id}">✕ Reject → rework</button>
    </div>` : "";
  const errBanner = v.error ? `<div class="err-banner"><b>Failed${v.failed_stage ? ` at ${esc(v.failed_stage)}` : ""}:</b> ${esc(v.error)}${!v.has_image ? "<br>↳ This SKU has no <b>image_url</b> — add a direct product image URL and re-ingest." : ""}</div>` : "";
  const viol = (v.violations || []).map((x) => `<div class="viol">⚠ ${esc(x)}</div>`).join("");
  const vlmBlock = vlmHtml(v.vlm_qc);
  const held = v.held ? `<div class="held">⏸ held: ${esc(v.held)} — ${esc((v.result && v.result.note) || "")}</div>` : "";

  $("#drawer-body").innerHTML = `
    <h2>${esc(v.title || v.fsn)}</h2>
    <div class="fsn">${esc(v.fsn)} · <span class="badge s-${v.state}">${v.state}</span></div>
    ${hasVideo ? `<video controls preload="metadata" src="${vsrc}"></video>` : ""}
    ${errBanner}${held}${viol}${vlmBlock}
    ${qcBlock}
    <div class="kv">
      <div class="k">Model</div><div class="v">${esc(v.model)}${v.force_model ? " (pinned)" : ""}${v.fell_back ? " · fell back" : ""}</div>
      <div class="k">Mode</div><div class="v">${v.execute ? "execute (paid)" : "dry-run"}${v.human_qc ? " · human QC" : ""}</div>
      <div class="k">Est / actual</div><div class="v">~${fmtUsd(v.est_cost_usd)} / ${fmtUsd(v.cost_usd)}</div>
      <div class="k">Priority</div><div class="v">${esc(v.priority)}</div>
      ${v.request_id ? `<div class="k">fal request</div><div class="v">${esc(v.request_id)}</div>` : ""}
      <div class="k">SLA</div><div class="v">${fmtDur(v.sla.elapsed_s)} / ${fmtDur(v.sla.budget_s)} ${v.sla.breached ? "⚠ BREACH" : "ok"}</div>
      ${fin.width ? `<div class="k">Output</div><div class="v">${fin.width}×${fin.height} · ${fin.duration_s}s · ${fin.size_mb}MB · ${fin.video_codec}</div>` : ""}
    </div>
    <div class="section-title">Audit trail <span class="${v.audit_chain_valid ? "chainok" : "chainbad"}">${v.audit_chain_valid ? "⛓ chain valid" : "⛓ CHAIN INVALID"}</span></div>
    <div class="timeline">${(v.audit || []).map(evHtml).join("")}</div>`;
  $("#backdrop").hidden = false; $("#drawer").hidden = false;
}

function vlmHtml(q) {
  if (!q) return "";
  if (!q.ran) return `<div class="vlm skip">🔍 VLM QC skipped${q.error ? ` — ${esc(q.error)}` : ""}</div>`;
  const issues = (q.issues || []).map((i) =>
    `<div class="vlm-issue ${esc(i.severity || "")}">${esc((i.severity || "").toUpperCase())} · ${esc(i.type || "")}: ${esc(i.detail || "")}</div>`).join("");
  const cls = q.passed ? "pass" : "fail";
  const head = q.passed ? "✓ VLM QC passed" : "⚠ VLM QC flagged — needs human review";
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
  await api(`/api/jobs/${jobId}/qc`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve, reason }),
  });
  await openJob(jobId); refreshAll();
}

// ---- ingest ----
$("#csv").addEventListener("change", (e) => {
  $("#csv-label").textContent = e.target.files[0] ? e.target.files[0].name : "Choose a SKU manifest CSV…";
});

$("#ingest-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("#csv").files[0];
  if (!file) return;
  const msg = $("#ingest-msg");
  const btn = $("#ingest-btn");
  const fd = new FormData();
  fd.append("file", file);
  fd.append("execute", $("#execute").checked);
  fd.append("human_qc", $("#human_qc").checked);
  fd.append("model", $("#model").value);
  fd.append("stand_in", $("#standin").value.trim());
  fd.append("auto_run", "true");
  btn.disabled = true; msg.className = "hint"; msg.textContent = "Ingesting…";
  if ($("#execute").checked && !confirm("Execute mode makes REAL paid fal.ai calls. Continue?")) {
    btn.disabled = false; msg.textContent = ""; return;
  }
  try {
    const r = await api("/api/ingest", { method: "POST", body: fd });
    if (r.warnings && r.warnings.length) {
      msg.className = "hint err";
      msg.innerHTML = `Created ${r.created.length}, reused ${r.reused.length}.<br>⚠ ${r.warnings.map(esc).join("<br>⚠ ")}`
        + (r.blocked_run ? "<br><b>Run blocked</b> — fix the CSV (add image URLs) and re-ingest, or these will fail." : "");
    } else {
      msg.className = "hint ok";
      msg.textContent = `Created ${r.created.length}, reused ${r.reused.length}.` + (r.drain_started ? " Worker started — watch the banner above the table." : "");
    }
    refreshAll();
  } catch (err) {
    msg.className = "hint err"; msg.textContent = "Error: " + err.message;
  } finally { btn.disabled = false; }
});

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
  try { await Promise.all([refreshSummary(), refreshJobs()]); } catch (e) { /* transient */ }
}
refreshAll();
setPoll(5000);
