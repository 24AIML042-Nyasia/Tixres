let priorityFilter = "";

function normalizeBase(raw) {
  if (!raw || !raw.trim()) return null;
  let url = raw.trim();
  if (!/^https?:\/\//i.test(url)) url = "http://" + url;
  if (url.endsWith("/")) url = url.slice(0, -1);
  try { return new URL(url).origin; } catch { return null; }
}

function saveState() {
  const state = {
    base: document.getElementById("baseUrl").value,
    priority: priorityFilter,
    metric: document.getElementById("metricFilter").value,
    purpose: document.getElementById("purposeFilter").value,
  };
  localStorage.setItem("guidanceState", JSON.stringify(state));
}

function loadState() {
  try {
    const state = JSON.parse(localStorage.getItem("guidanceState") || "{}");
    if (state.base) document.getElementById("baseUrl").value = state.base;
    if (state.metric) document.getElementById("metricFilter").value = state.metric;
    if (state.purpose) document.getElementById("purposeFilter").value = state.purpose;
    if (state.priority) {
      const chip = document.querySelector(`.chip[data-val='${state.priority}']`);
      if (chip) setPriorityFilter(chip, false);
    }
  } catch {}
}

function pingServer() {
  const status = document.getElementById("pingStatus");
  status.textContent = "Pinging…";
  status.style.color = "#6b7280";
  const base = normalizeBase(document.getElementById("baseUrl").value);
  if (!base) { status.textContent = "Invalid URL"; status.style.color = "#ef4444"; return; }
  fetch(`${base}/health`).then(r => {
    status.textContent = r.ok ? "● Server reachable" : `✗ ${r.status}`;
    status.style.color = r.ok ? "#2a8a7e" : "#e8445a";
  }).catch(() => {
    status.textContent = "✗ Unreachable";
    status.style.color = "#e8445a";
  });
}

function setPriorityFilter(el, fetchNow = true) {
  document.querySelectorAll("#priorityChips .chip").forEach(c => c.classList.remove("active"));
  el.classList.add("active");
  priorityFilter = el.dataset.val || "";
  if (fetchNow) fetchGuidance();
  saveState();
}

function handleKey(e, cb) { if (e.key === "Enter") cb(); }

async function fetchGuidance() {
  const base = normalizeBase(document.getElementById("baseUrl").value);
  if (!base) { alert("Enter a valid Base URL."); return; }
  const params = new URLSearchParams({ limit: 100 });
  const metric = document.getElementById("metricFilter").value.trim();
  const purpose = document.getElementById("purposeFilter").value.trim();
  if (priorityFilter) params.set("priority", priorityFilter);
  if (metric) params.set("metric_name", metric);
  if (purpose) params.set("purpose", purpose);

  const grid = document.getElementById("guidanceGrid");
  grid.innerHTML = '<div class="empty-state"><div class="icon">⏳</div><p>Loading…</p></div>';

  try {
    const res = await fetch(`${base}/api/guidance?${params.toString()}`);
    const data = await res.json();
    renderGuidance(data.items || []);
    saveState();
  } catch (e) {
    grid.innerHTML = `<div class="empty-state"><p>Error: ${e}</p></div>`;
  }
}

function renderGuidance(items) {
  const grid = document.getElementById("guidanceGrid");
  const countBadge = document.getElementById("countBadge");
  countBadge.textContent = items.length;
  if (!items.length) {
    grid.innerHTML = '<div class="empty-state"><div class="icon">✅</div><p>No guidance matches the filters.</p></div>';
    return;
  }
  grid.innerHTML = "";
  items.forEach(item => {
    const card = document.createElement("div");
    card.className = "g-card";
    const steps = (item.resolution_steps || []).map(s => `<li>${s.action || s}</li>`).join("");
    const notes = item.resolver_notes ? `<div class="notes">${item.resolver_notes}</div>` : "";
    const meta = `
      <span class="badge badge-${item.priority}">Priority ${item.priority}</span>
      <span class="meta-pill">${item.purpose}</span>
      <span class="meta-pill">${item.metric_name}</span>
      <span class="meta-pill">Updated ${fmtTime(item.last_updated)}</span>`;

    card.innerHTML = `
      <div class="title">${item.metric_name}</div>
      <div class="meta">${meta}</div>
      <ol class="steps">${steps}</ol>
      ${notes}
    `;
    grid.appendChild(card);
  });
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

async function submitGuidance() {
  const base = normalizeBase(document.getElementById("baseUrl").value);
  if (!base) { alert("Enter a valid Base URL."); return; }

  const metric = document.getElementById("formMetric").value.trim();
  const priority = document.getElementById("formPriority").value;
  const purpose = document.getElementById("formPurpose").value.trim() || "general";
  const stepsRaw = document.getElementById("formSteps").value;
  const notes = document.getElementById("formNotes").value.trim();
  const status = document.getElementById("formStatus");

  const steps = stepsRaw.split(/\n+/).map(s => s.trim()).filter(Boolean).map((action, idx) => ({ step: idx + 1, action }));

  if (!metric || !steps.length) {
    status.textContent = "Metric and at least one step are required.";
    status.style.color = "#e8445a";
    return;
  }

  status.textContent = "Saving…";
  status.style.color = "#6b7280";

  try {
    const res = await fetch(`${base}/api/guidance`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        metric_name: metric,
        priority,
        purpose,
        resolution_steps: steps,
        resolver_notes: notes || null,
      }),
    });
    if (!res.ok) {
      const msg = await res.text();
      status.textContent = `Error ${res.status}: ${msg}`;
      status.style.color = "#e8445a";
      return;
    }
    status.textContent = "Saved. Refreshing…";
    status.style.color = "#2a8a7e";
    fetchGuidance();
  } catch (e) {
    status.textContent = `Error: ${e}`;
    status.style.color = "#e8445a";
  }
}

function resetFilters() {
  priorityFilter = "";
  document.querySelectorAll("#priorityChips .chip").forEach(c => c.classList.remove("active"));
  document.querySelector("#priorityChips .chip[data-val='']").classList.add("active");
  document.getElementById("metricFilter").value = "";
  document.getElementById("purposeFilter").value = "";
  fetchGuidance();
}

// init
loadState();
fetchGuidance();
