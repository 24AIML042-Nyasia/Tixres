
  const AVAILABLE_AGENTS = ["agent_demo_web","agent_demo_db","agent_demo_cache","agent_demo_search","agent_demo_queue"];
  const AVAILABLE_METRICS = ["cpu_v1.0.0.usage_overall","disk_v1.0.0.usage","memory_v1.0.0.ram","network_v1.0.0.errors"];
  const METRIC_LABELS = {
    "cpu_v1.0.0.usage_overall":"CPU Usage",
    "disk_v1.0.0.usage":"Disk Usage",
    "memory_v1.0.0.ram":"Memory RAM",
    "network_v1.0.0.errors":"Network Errors"
  };
  const AGENT_COLORS = ["#ff7c5c","#2a8a7e","#7c6af4","#f4a742","#4ab8e8"];
  const AGENT_BG     = ["rgba(255,124,92,0.07)","rgba(42,138,126,0.07)","rgba(124,106,244,0.07)","rgba(244,167,66,0.07)","rgba(74,184,232,0.07)"];

  // cache points for modal re-render
  const pointsCache = {};

  const selected = { agents: new Set(), metrics: new Set() };
  let activeMeasurement = "1m";

  function buildDropdown(msId, items, labelFn) {
    const dd = document.getElementById(msId + "-dropdown");
    const key = msId === "ms-agents" ? "agents" : "metrics";

    // "Select All" / "Clear All" row
    const allDiv = document.createElement("div");
    allDiv.className = "ms-option all-option";
    allDiv.id = `all-opt-${msId}`;
    allDiv.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px";
    allDiv.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;flex:1">
        <input type="checkbox" id="chk-${msId}-all" onchange="toggleAll('${msId}','${key}')">
        <label for="chk-${msId}-all" style="cursor:pointer;flex:1">Select All</label>
      </div>
      <span onclick="clearAll('${msId}','${key}')" style="font-size:11px;color:var(--muted);cursor:pointer;padding:0 4px;user-select:none" onmouseover="this.style.color='var(--red)'" onmouseout="this.style.color='var(--muted)'">Clear</span>`;
    dd.appendChild(allDiv);

    items.forEach(item => {
      const div = document.createElement("div");
      div.className = "ms-option";
      div.innerHTML = `<input type="checkbox" id="chk-${msId}-${item}" value="${item}" onchange="toggleItem('${msId}','${item}')">
        <label for="chk-${msId}-${item}" style="cursor:pointer;flex:1">${labelFn ? labelFn(item) : item}</label>`;
      dd.appendChild(div);
    });
  }

  function clearAll(msId, key) {
    const items = key === "agents" ? AVAILABLE_AGENTS : AVAILABLE_METRICS;
    items.forEach(item => {
      selected[key].delete(item);
      const chk = document.getElementById(`chk-${msId}-${item}`);
      if (chk) chk.checked = false;
    });
    const allChk = document.getElementById(`chk-${msId}-all`);
    if (allChk) allChk.checked = false;
    renderTags(msId, key);
    updateTriggerLabel(msId, key);
    saveState();
  }

  function toggleAll(msId, key) {
    const allChk = document.getElementById(`chk-${msId}-all`);
    const items = key === "agents" ? AVAILABLE_AGENTS : AVAILABLE_METRICS;
    if (allChk.checked) {
      items.forEach(item => {
        selected[key].add(item);
        const chk = document.getElementById(`chk-${msId}-${item}`);
        if (chk) chk.checked = true;
      });
    } else {
      items.forEach(item => {
        selected[key].delete(item);
        const chk = document.getElementById(`chk-${msId}-${item}`);
        if (chk) chk.checked = false;
      });
    }
    renderTags(msId, key);
    updateTriggerLabel(msId, key);
    saveState();
  }

  function syncAllCheckbox(msId, key) {
    const items = key === "agents" ? AVAILABLE_AGENTS : AVAILABLE_METRICS;
    const allChk = document.getElementById(`chk-${msId}-all`);
    if (allChk) allChk.checked = selected[key].size === items.length;
  }

  function toggleDropdown(msId) {
    const trigger = document.querySelector(`#${msId} .ms-trigger`);
    const dd = document.getElementById(msId + "-dropdown");
    const isOpen = dd.classList.contains("open");
    document.querySelectorAll(".ms-dropdown.open").forEach(el => el.classList.remove("open"));
    document.querySelectorAll(".ms-trigger.open").forEach(el => el.classList.remove("open"));
    if (!isOpen) { dd.classList.add("open"); trigger.classList.add("open"); }
  }

  function toggleItem(msId, value) {
    const key = msId === "ms-agents" ? "agents" : "metrics";
    if (selected[key].has(value)) selected[key].delete(value);
    else selected[key].add(value);
    syncAllCheckbox(msId, key);
    renderTags(msId, key);
    updateTriggerLabel(msId, key);
    saveState();
  }

  function renderTags(msId, key) {
    const container = document.getElementById(msId + "-tags");
    container.innerHTML = "";
    selected[key].forEach(val => {
      const pill = document.createElement("span");
      pill.className = "tag-pill";
      const label = key === "metrics" ? (METRIC_LABELS[val] || val) : val;
      if (key === "agents") {
        const idx = AVAILABLE_AGENTS.indexOf(val);
        const color = AGENT_COLORS[idx] ?? AGENT_COLORS[0];
        pill.style.color = color;
        pill.style.borderColor = color.replace(")", ",0.4)").replace("#", "rgba(") ;
        // parse hex to rgba properly
        const r = parseInt(color.slice(1,3),16), g = parseInt(color.slice(3,5),16), b = parseInt(color.slice(5,7),16);
        pill.style.background = `rgba(${r},${g},${b},0.10)`;
        pill.style.borderColor = `rgba(${r},${g},${b},0.35)`;
        pill.style.color = color;
      }
      pill.innerHTML = `${label} <span class="rm" onclick="removeItem('${msId}','${key}','${val}')">✕</span>`;
      container.appendChild(pill);
    });
  }

  function removeItem(msId, key, val) {
    selected[key].delete(val);
    const chk = document.getElementById(`chk-${msId}-${val}`);
    if (chk) chk.checked = false;
    syncAllCheckbox(msId, key);
    renderTags(msId, key);
    updateTriggerLabel(msId, key);
    saveState();
  }

  function updateTriggerLabel(msId, key) {
    const label = document.querySelector(`#${msId} .ms-label`);
    const count = selected[key].size;
    label.textContent = count === 0 ? (key === "agents" ? "Select agents…" : "Select metrics…") : `${count} selected`;
  }

  document.addEventListener("click", e => {
    if (!e.target.closest(".multi-select")) {
      document.querySelectorAll(".ms-dropdown.open").forEach(el => el.classList.remove("open"));
      document.querySelectorAll(".ms-trigger.open").forEach(el => el.classList.remove("open"));
    }
  });

  function selectMeasurement(el) {
    document.querySelectorAll(".meas-btn").forEach(b => b.classList.remove("active"));
    el.classList.add("active");
    activeMeasurement = el.dataset.val;
    saveState();
  }

  async function pingServer() {
    const status = document.getElementById("pingStatus");
    status.style.color = "#f4a7c0"; status.textContent = "Pinging…";
    const base = normalizeBase(document.getElementById("baseUrl").value);
    if (!base) { status.style.color = "#ef4444"; status.textContent = "Invalid URL"; return; }
    try {
      const res = await fetch(`${base}/health`);
      if (res.ok) { status.style.color = "#2a8a7e"; status.textContent = "● Server reachable"; }
      else { status.style.color = "#e8445a"; status.textContent = `✗ ${res.status}`; }
    } catch { status.style.color = "#e8445a"; status.textContent = "✗ Unreachable"; }
  }

  function normalizeBase(raw) {
    if (!raw || !raw.trim()) return null;
    let url = raw.trim();
    if (!/^https?:\/\//i.test(url)) url = "http://" + url;
    if (url.endsWith("/")) url = url.slice(0, -1);
    try { return new URL(url).origin; } catch { return null; }
  }

  function fmt(v) { return v == null ? "—" : (typeof v === "number" ? v.toFixed(2) : v); }

  async function runQuery() {
    const agents = [...selected.agents];
    const metrics = [...selected.metrics];
    if (!agents.length || !metrics.length) { alert("Select at least one agent and one metric."); return; }
    const base = normalizeBase(document.getElementById("baseUrl").value);
    if (!base) { alert("Enter a valid Base URL."); return; }
    const startMinutes = document.getElementById("startMinutes").value || "240";
    document.getElementById("emptyState").style.display = "none";
    const wrapper = document.getElementById("resultsGrid");
    wrapper.innerHTML = "";

    agents.forEach(agent => {
      const agentIdx = AVAILABLE_AGENTS.indexOf(agent);
      const color = AGENT_COLORS[agentIdx] ?? AGENT_COLORS[0];
      const bg    = AGENT_BG[agentIdx]    ?? AGENT_BG[0];

      const row = document.createElement("div");
      row.className = "agent-row";

      // sticky label
      const label = document.createElement("div");
      label.className = "agent-row-label";
      label.style.borderLeft = `3px solid ${color}`;
      label.innerHTML = `
        <div class="a-dot" style="background:${color}"></div>
        <div class="a-name" style="color:${color}">${agent.replace("agent_demo_","")}</div>
        <div class="a-count">${metrics.length} metric${metrics.length > 1 ? "s" : ""}</div>`;
      row.appendChild(label);

      // cards strip
      const strip = document.createElement("div");
      strip.className = "agent-row-cards";
      strip.id = `strip-${agent}`;
      row.appendChild(strip);
      wrapper.appendChild(row);

      metrics.forEach(metric => {
        const card = createCard(agent, metric, color, bg);
        strip.appendChild(card);
        fetchRollup(base, agent, metric, activeMeasurement, startMinutes, color);
      });
    });
  }

  function cardId(agent, metric) { return `${agent}__${metric}`.replace(/\./g, "_"); }

  function createCard(agent, metric, color, bg) {
    const id = cardId(agent, metric);
    const metricLabel = METRIC_LABELS[metric] || metric;
    const el = document.createElement("div");
    el.className = "result-card";
    el.style.borderLeftColor = color;
    el.style.cursor = "pointer";
    el.dataset.cid = id;
    el.title = "Click to zoom in";
    el.onclick = () => {
      if (compareMode) { toggleCardCompare(agent, metric, color, el); }
      else { openModal(agent, metric, color); }
    };
    el.innerHTML = `
      <div class="card-compare-check">✓</div>
      <div class="result-card-header" style="background:${bg}">
        <div><span class="status-dot status-loading" id="dot-${id}"></span><span class="card-title" style="color:${color}">${metricLabel}</span></div>
        <div class="card-meta">${agent}</div>
      </div>
      <div class="stats-row" id="stats-${id}">
        <div class="stat-box"><div class="sv" style="color:${color}">—</div><div class="sk">Avg</div></div>
        <div class="stat-box"><div class="sv" style="color:${color}">—</div><div class="sk">Min</div></div>
        <div class="stat-box"><div class="sv" style="color:${color}">—</div><div class="sk">Max</div></div>
        <div class="stat-box"><div class="sv" style="color:${color}">—</div><div class="sk">Points</div></div>
      </div>
      <div class="chart-wrap"><canvas id="chart-${id}" style="height:120px"></canvas></div>`;
    return el;
  }

  async function fetchRollup(base, agent, metric, measurement, startMinutes, color) {
    const id = cardId(agent, metric);
    const params = new URLSearchParams({ measurement, metric_name: metric, start_minutes: startMinutes });
    try {
      const res = await fetch(`${base}/api/rollups/${agent}?${params}`);
      const data = await res.json();
      document.getElementById(`dot-${id}`).className = "status-dot status-ok";
      const points = data.points || [];
      if (!points.length) { updateStats(id, null); renderEmptyChart(`chart-${id}`); return; }
      const avgs = points.map(p => p.avg).filter(v => v != null);
      const mins = points.map(p => p.min).filter(v => v != null);
      const maxs = points.map(p => p.max).filter(v => v != null);
      updateStats(id, {
        avg: avgs.reduce((a,b)=>a+b,0)/avgs.length,
        min: Math.min(...mins), max: Math.max(...maxs), count: points.length
      });
      pointsCache[id] = { points, color };
      renderChart(`chart-${id}`, points, color);
    } catch (err) {
      document.getElementById(`dot-${id}`).className = "status-dot status-err";
    }
  }

  function updateStats(id, s) {
    const boxes = document.querySelectorAll(`#stats-${id} .stat-box .sv`);
    if (!s) { boxes.forEach(b => b.textContent = "—"); return; }
    boxes[0].textContent = fmt(s.avg);
    boxes[1].textContent = fmt(s.min);
    boxes[2].textContent = fmt(s.max);
    boxes[3].textContent = s.count;
  }

  // ── chart helpers ──────────────────────────────────────────────────────────
  // registry: canvasId -> { points, color, PAD, scales, dpr }
  const chartRegistry = {};

  function hexRgb(hex) {
    return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];
  }

  function setupHiDPI(canvas, cssW, cssH) {
    const dpr = window.devicePixelRatio || 1;
    canvas.width  = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width  = cssW + "px";
    canvas.style.height = cssH + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    return { ctx, dpr, W: cssW, H: cssH };
  }

  function drawChart(canvas, points, color, cssH) {
    const cssW = canvas.parentElement ? canvas.parentElement.clientWidth || 400 : 400;
    const { ctx, W, H } = setupHiDPI(canvas, cssW, cssH);
    const PAD = { top:14, right:14, bottom:34, left:48 };
    const cW = W - PAD.left - PAD.right, cH = H - PAD.top - PAD.bottom;
    const [r,g,b] = hexRgb(color);

    const avgs = points.map(p => p.avg ?? 0);
    const mins = points.map(p => p.min ?? 0);
    const maxs = points.map(p => p.max ?? 0);
    const allV = [...avgs, ...mins, ...maxs];
    const dMin = Math.min(...allV), dMax = Math.max(...allV);
    const range = dMax - dMin || 1;
    const n = points.length;

    const xS = i => PAD.left + (i / (n - 1 || 1)) * cW;
    const yS = v => PAD.top + cH - ((v - dMin) / range) * cH;

    // background
    ctx.fillStyle = "#f5f0e8"; ctx.fillRect(0, 0, W, H);

    // grid
    ctx.strokeStyle = "rgba(200,188,168,0.8)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (i / 4) * cH;
      ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke();
      ctx.fillStyle = "#8a7e6a"; ctx.font = "10px Inter,sans-serif"; ctx.textAlign = "right";
      ctx.fillText((dMax - (i/4)*range).toFixed(1), PAD.left - 6, y + 3.5);
    }

    // Y label
    ctx.save();
    ctx.translate(11, PAD.top + cH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("value", 0, 0);
    ctx.restore();

    // min/max band with gradient
    if (n > 1) {
      const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + cH);
      grad.addColorStop(0, `rgba(${r},${g},${b},0.18)`);
      grad.addColorStop(1, `rgba(${r},${g},${b},0.03)`);
      ctx.beginPath();
      ctx.moveTo(xS(0), yS(maxs[0]));
      for (let i = 1; i < n; i++) ctx.lineTo(xS(i), yS(maxs[i]));
      for (let i = n-1; i >= 0; i--) ctx.lineTo(xS(i), yS(mins[i]));
      ctx.closePath();
      ctx.fillStyle = grad; ctx.fill();
    }

    // avg line — smooth bezier
    ctx.beginPath();
    ctx.strokeStyle = color; ctx.lineWidth = 2.5;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.shadowColor = color; ctx.shadowBlur = 6;
    if (n === 1) {
      ctx.arc(xS(0), yS(avgs[0]), 3, 0, Math.PI*2);
      ctx.fillStyle = color; ctx.fill();
    } else {
      ctx.moveTo(xS(0), yS(avgs[0]));
      for (let i = 1; i < n; i++) ctx.lineTo(xS(i), yS(avgs[i]));
      ctx.stroke();
    }
    ctx.shadowBlur = 0;

    // dots
    avgs.forEach((v, i) => {
      ctx.beginPath();
      ctx.arc(xS(i), yS(v), 3, 0, Math.PI*2);
      ctx.fillStyle = color; ctx.fill();
      ctx.strokeStyle = "#f5f0e8"; ctx.lineWidth = 1.5; ctx.stroke();
    });

    // x labels
    const labelIdxs = n <= 4 ? avgs.map((_,i)=>i) : [0, Math.floor(n/2), n-1];
    labelIdxs.forEach(i => {
      const ts = new Date(points[i].bucket_start);
      ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
      ctx.fillText(ts.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}), xS(i), H - 16);
    });
    ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("time", PAD.left + cW/2, H - 4);

    // store for hover
    chartRegistry[canvas.id] = { points, color, PAD, xS, yS, dMin, dMax, range, cW, cH, W, H, cssH, cssW };
  }

  function renderEmptyChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    // remove any stale hover handlers and registry entry
    canvas.onmousemove = null;
    canvas.onmouseleave = null;
    delete chartRegistry[canvasId];
    const cssW = canvas.parentElement ? canvas.parentElement.clientWidth || 400 : 400;
    const cssH = canvas.style.height ? parseInt(canvas.style.height) || 220 : 220;
    const { ctx, W, H } = setupHiDPI(canvas, cssW, cssH);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#f5f0e8"; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#8a7e6a"; ctx.font = "13px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No data in range", W/2, H/2);
  }

  function renderChart(canvasId, points, color) {
    color = color || "#ff7c5c";
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const cssH = parseInt(canvas.style.height) || 120;
    drawChart(canvas, points, color, cssH);
    attachHover(canvas);
  }

  // ── hover tooltip ──────────────────────────────────────────────────────────
  // shared tooltip div
  let _tooltip = null;
  function getTooltip() {
    if (!_tooltip) {
      _tooltip = document.createElement("div");
      _tooltip.id = "chart-tooltip";
      _tooltip.style.cssText = `
        position:fixed; pointer-events:none; z-index:9999;
        background:#fdf8f0; border:1px solid #e0d8c8;
        border-radius:8px; padding:8px 12px; font-size:12px;
        color:#2a2218; box-shadow:0 8px 24px rgba(0,0,0,0.12);
        display:none; min-width:130px; line-height:1.6;
      `;
      document.body.appendChild(_tooltip);
    }
    return _tooltip;
  }

  function attachHover(canvas) {
    canvas.onmousemove = (e) => {
      const reg = chartRegistry[canvas.id];
      if (!reg) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const { points, color, PAD, xS, yS, W, H } = reg;
      const n = points.length;
      if (!n) return;

      // find nearest point by x
      let best = 0, bestDist = Infinity;
      for (let i = 0; i < n; i++) {
        const d = Math.abs(xS(i) - mx);
        if (d < bestDist) { bestDist = d; best = i; }
      }
      if (bestDist > 40) { getTooltip().style.display = "none"; return; }

      const p = points[best];
      const ts = new Date(p.bucket_start).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
      const tip = getTooltip();
      tip.innerHTML = `
        <div style="color:${color};font-weight:700;margin-bottom:4px">${ts}</div>
        <div>Avg <span style="color:${color};font-weight:600">${(p.avg??0).toFixed(2)}</span></div>
        <div>Min <span style="color:#8a7e6a">${(p.min??0).toFixed(2)}</span></div>
        <div>Max <span style="color:#8a7e6a">${(p.max??0).toFixed(2)}</span></div>
        <div>Count <span style="color:#8a7e6a">${p.count??'—'}</span></div>`;
      tip.style.display = "block";
      // position tooltip — flip if near right edge
      const tipW = 150, tipH = 100;
      let tx = e.clientX + 14, ty = e.clientY - 20;
      if (tx + tipW > window.innerWidth - 10) tx = e.clientX - tipW - 14;
      if (ty + tipH > window.innerHeight - 10) ty = e.clientY - tipH;
      tip.style.left = tx + "px";
      tip.style.top  = ty + "px";

      // crosshair on canvas — redraw without resizing
      const dpr = window.devicePixelRatio || 1;
      const ctx = canvas.getContext("2d");
      redrawChart(canvas, reg);
      ctx.save();
      ctx.strokeStyle = "rgba(100,80,60,0.25)"; ctx.lineWidth = 1; ctx.setLineDash([4,3]);
      const cx = xS(best), cy = yS(p.avg ?? 0);
      ctx.beginPath(); ctx.moveTo(cx, PAD.top); ctx.lineTo(cx, PAD.top + reg.cH); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(PAD.left, cy); ctx.lineTo(PAD.left + reg.cW, cy); ctx.stroke();
      ctx.setLineDash([]);
      // highlight dot
      ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI*2);
      ctx.fillStyle = color; ctx.fill();
      ctx.strokeStyle = "#f5f0e8"; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.restore();
    };
    canvas.onmouseleave = () => {
      getTooltip().style.display = "none";
      const reg = chartRegistry[canvas.id];
      if (reg) redrawChart(canvas, reg);
    };
  }

  // redraw without touching canvas dimensions
  function redrawChart(canvas, reg) {
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // use stored cssW/cssH so no resize occurs
    const { points, color, cssW, cssH } = reg;
    _drawChartNoResize(ctx, points, color, reg);
  }

  function _drawChartNoResize(ctx, points, color, reg) {
    const { PAD, xS, yS, dMin, dMax, range, cW, cH, W, H } = reg;
    const [r,g,b] = hexRgb(color);
    const avgs = points.map(p => p.avg ?? 0);
    const mins = points.map(p => p.min ?? 0);
    const maxs = points.map(p => p.max ?? 0);
    const n = points.length;

    ctx.fillStyle = "#f5f0e8"; ctx.fillRect(0, 0, W, H);

    // grid
    ctx.strokeStyle = "rgba(200,188,168,0.8)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (i / 4) * cH;
      ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke();
      ctx.fillStyle = "#8a7e6a"; ctx.font = "10px Inter,sans-serif"; ctx.textAlign = "right";
      ctx.fillText((dMax - (i/4)*range).toFixed(1), PAD.left - 6, y + 3.5);
    }
    ctx.save();
    ctx.translate(11, PAD.top + cH / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("value", 0, 0); ctx.restore();

    if (n > 1) {
      const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + cH);
      grad.addColorStop(0, `rgba(${r},${g},${b},0.18)`);
      grad.addColorStop(1, `rgba(${r},${g},${b},0.03)`);
      ctx.beginPath();
      ctx.moveTo(xS(0), yS(maxs[0]));
      for (let i = 1; i < n; i++) ctx.lineTo(xS(i), yS(maxs[i]));
      for (let i = n-1; i >= 0; i--) ctx.lineTo(xS(i), yS(mins[i]));
      ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
    }

    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2.5;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.shadowColor = color; ctx.shadowBlur = 6;
    if (n === 1) {
      ctx.arc(xS(0), yS(avgs[0]), 3, 0, Math.PI*2);
      ctx.fillStyle = color; ctx.fill();
    } else {
      ctx.moveTo(xS(0), yS(avgs[0]));
      for (let i = 1; i < n; i++) ctx.lineTo(xS(i), yS(avgs[i]));
      ctx.stroke();
    }
    ctx.shadowBlur = 0;

    avgs.forEach((v, i) => {
      ctx.beginPath(); ctx.arc(xS(i), yS(v), 3, 0, Math.PI*2);
      ctx.fillStyle = color; ctx.fill();
      ctx.strokeStyle = "#f5f0e8"; ctx.lineWidth = 1.5; ctx.stroke();
    });

    const labelIdxs = n <= 4 ? avgs.map((_,i)=>i) : [0, Math.floor(n/2), n-1];
    labelIdxs.forEach(i => {
      const ts = new Date(points[i].bucket_start);
      ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
      ctx.fillText(ts.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}), xS(i), H - 16);
    });
    ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("time", PAD.left + cW/2, H - 4);
  }

  // ── modal ──────────────────────────────────────────────────────────────────
  function openModal(agent, metric, color) {
    const id = cardId(agent, metric);
    const label = METRIC_LABELS[metric] || metric;
    document.getElementById("modalTitle").textContent = label;
    document.getElementById("modalTitle").style.color = color;
    document.getElementById("modalAgent").textContent = agent;

    // copy stats from card
    const boxes = document.querySelectorAll(`#stats-${id} .stat-box .sv`);
    ["ms-avg","ms-min","ms-max","ms-pts"].forEach((elId, i) => {
      const el = document.getElementById(elId);
      el.textContent = boxes[i] ? boxes[i].textContent : "—";
      el.style.color = color;
    });

    // draw large chart
    const cached = pointsCache[id];
    const canvas = document.getElementById("modalCanvas");
    document.getElementById("modalBackdrop").classList.add("open");
    document.body.style.overflow = "hidden";

    requestAnimationFrame(() => {
      // force full bitmap clear regardless of cached dimensions
      const dpr = window.devicePixelRatio || 1;
      const cssW = canvas.offsetWidth || 720;
      const cssH = 220;
      canvas.width  = cssW * dpr;
      canvas.height = cssH * dpr;
      canvas.style.width  = cssW + "px";
      canvas.style.height = cssH + "px";
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (cached && cached.points.length) {
        renderChart("modalCanvas", cached.points, color);
      } else {
        renderEmptyChart("modalCanvas");
      }
    });
  }

  function closeModal(e) {
    if (e.target === document.getElementById("modalBackdrop")) closeModalDirect();
  }

  function closeModalDirect() {
    document.getElementById("modalBackdrop").classList.remove("open");
    document.body.style.overflow = "";
  }

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeModalDirect(); closeCmpModalDirect(); }
  });

  // ── compare mode ───────────────────────────────────────────────────────────
  let compareMode = false;
  const compareSet = new Map(); // id -> { agent, metric, color, label }

  function toggleCompareMode() {
    compareMode = !compareMode;
    const btn = document.getElementById("compareToggleBtn");
    btn.classList.toggle("active", compareMode);
    btn.textContent = compareMode ? "✕ Exit Compare" : "⊕ Compare Mode";
    // update all cards
    document.querySelectorAll(".result-card").forEach(card => {
      card.classList.toggle("compare-selectable", compareMode);
      if (!compareMode) card.classList.remove("compare-selected");
    });
    if (!compareMode) { clearCompare(); }
  }

  function toggleCardCompare(agent, metric, color, el) {
    if (!compareMode) return;
    const id = cardId(agent, metric);
    const label = METRIC_LABELS[metric] || metric;
    if (compareSet.has(id)) {
      compareSet.delete(id);
      el.classList.remove("compare-selected");
    } else {
      compareSet.set(id, { agent, metric, color, label });
      el.classList.add("compare-selected");
    }
    renderTray();
  }

  function renderTray() {
    const tray = document.getElementById("compareTray");
    const chips = document.getElementById("trayChips");
    const count = document.getElementById("trayCount");
    chips.innerHTML = "";
    compareSet.forEach(({ agent, metric, color, label }, id) => {
      const chip = document.createElement("span");
      chip.className = "tray-chip";
      chip.style.borderColor = color; chip.style.color = color;
      chip.style.background = `${color}18`;
      chip.innerHTML = `<span>${label} <span style="opacity:0.6;font-weight:400">${agent.replace("agent_demo_","")}</span></span>
        <span class="tray-rm" onclick="removeTrayItem('${id}')">✕</span>`;
      chips.appendChild(chip);
    });
    count.textContent = compareSet.size > 0 ? `${compareSet.size} selected` : "";
    tray.classList.toggle("visible", compareSet.size > 0);
  }

  function removeTrayItem(id) {
    compareSet.delete(id);
    const card = document.querySelector(`[data-cid="${id}"]`);
    if (card) card.classList.remove("compare-selected");
    renderTray();
  }

  function clearCompare() {
    compareSet.clear();
    document.querySelectorAll(".result-card.compare-selected").forEach(c => c.classList.remove("compare-selected"));
    renderTray();
  }

  function openCompareModal() {
    if (compareSet.size < 2) { alert("Select at least 2 cards to compare."); return; }

    // group by metric
    const byMetric = {};
    compareSet.forEach(({ agent, metric, color, label }, id) => {
      if (!byMetric[metric]) byMetric[metric] = { label, metric, series: [] };
      const cached = pointsCache[id];
      const boxes = document.querySelectorAll(`#stats-${id} .stat-box .sv`);
      byMetric[metric].series.push({
        id, agent, color, label,
        points: cached ? cached.points : [],
        avg: boxes[0]?.textContent || "—",
        min: boxes[1]?.textContent || "—",
        max: boxes[2]?.textContent || "—",
        pts: boxes[3]?.textContent || "—",
      });
    });

    const metricGroups = Object.values(byMetric);
    const agentNames = [...new Set([...compareSet.values()].map(s => s.agent.replace("agent_demo_","")))];
    document.getElementById("cmpSubtitle").textContent =
      `${metricGroups.length} metric${metricGroups.length>1?"s":""} · ${agentNames.join(", ")}`;

    const chartsWrap = document.getElementById("cmpChartsWrap");
    chartsWrap.innerHTML = "";

    metricGroups.forEach((g, gi) => {
      const group = document.createElement("div");
      group.className = "cmp-group";

      // group title
      const title = document.createElement("div");
      title.className = "cmp-group-title";
      title.textContent = g.label;
      group.appendChild(title);

      // chart row: canvas + inline legend (stats embedded in legend)
      const chartRow = document.createElement("div");
      chartRow.className = "cmp-chart-row";

      const canvasWrap = document.createElement("div");
      canvasWrap.className = "cmp-canvas-wrap";
      const canvas = document.createElement("canvas");
      canvas.id = `cmp-canvas-${gi}`;
      canvas.height = 300;
      canvasWrap.appendChild(canvas);
      chartRow.appendChild(canvasWrap);

      // inline legend with stats beneath each entry
      const legend = document.createElement("div");
      legend.className = "cmp-inline-legend";
      g.series.forEach(s => {
        const item = document.createElement("div");
        item.className = "cmp-legend-item";
        item.style.cssText = "flex-direction:column;align-items:flex-start;gap:4px;padding-bottom:10px;border-bottom:1px solid var(--border);width:100%";
        item.innerHTML = `
          <div style="display:flex;align-items:center;gap:7px">
            <div class="cmp-legend-line" style="background:${s.color}"></div>
            <span class="cmp-legend-label" style="color:${s.color}">${s.agent.replace("agent_demo_","")}</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 10px;padding-left:2px;margin-top:2px">
            <div><div style="font-size:13px;font-weight:700;color:${s.color}">${s.avg}</div><div style="font-size:9px;color:var(--muted);text-transform:uppercase">Avg</div></div>
            <div><div style="font-size:13px;font-weight:700;color:${s.color}">${s.min}</div><div style="font-size:9px;color:var(--muted);text-transform:uppercase">Min</div></div>
            <div><div style="font-size:13px;font-weight:700;color:${s.color}">${s.max}</div><div style="font-size:9px;color:var(--muted);text-transform:uppercase">Max</div></div>
            <div><div style="font-size:13px;font-weight:700;color:${s.color}">${s.pts}</div><div style="font-size:9px;color:var(--muted);text-transform:uppercase">Pts</div></div>
          </div>`;
        legend.appendChild(item);
      });
      // remove border from last item
      if (legend.lastChild) legend.lastChild.style.borderBottom = "none";
      chartRow.appendChild(legend);
      group.appendChild(chartRow);
      chartsWrap.appendChild(group);
    });

    document.getElementById("cmpBackdrop").classList.add("open");
    document.body.style.overflow = "hidden";

    requestAnimationFrame(() => {
      metricGroups.forEach((g, gi) => {
        const canvas = document.getElementById(`cmp-canvas-${gi}`);
        if (!canvas) return;
        canvas.width = canvas.offsetWidth || 800;
        canvas.height = 300;
        renderCompareChart(canvas, g.series);
      });
    });
  }

  function renderCompareChart(canvas, series) {
    const cssW = canvas.parentElement ? canvas.parentElement.clientWidth || 800 : 800;
    const cssH = 300;
    const { ctx, W, H } = setupHiDPI(canvas, cssW, cssH);
    const PAD = { top:14, right:16, bottom:36, left:52 };
    const cW = W - PAD.left - PAD.right, cH = H - PAD.top - PAD.bottom;

    ctx.fillStyle = "#f5f0e8"; ctx.fillRect(0, 0, W, H);

    const allTimes = new Set();
    series.forEach(s => s.points.forEach(p => allTimes.add(p.bucket_start)));
    const timeKeys = [...allTimes].sort();
    if (!timeKeys.length) {
      ctx.fillStyle = "#8a7e6a"; ctx.font = "12px Inter,sans-serif";
      ctx.textAlign = "center"; ctx.fillText("No data", W/2, H/2);
      return;
    }

    let gMin = Infinity, gMax = -Infinity;
    series.forEach(s => s.points.forEach(p => {
      if (p.min != null && p.min < gMin) gMin = p.min;
      if (p.max != null && p.max > gMax) gMax = p.max;
    }));
    if (!isFinite(gMin)) { gMin = 0; gMax = 1; }
    const range = gMax - gMin || 1;

    const xS = i => PAD.left + (i / (timeKeys.length - 1 || 1)) * cW;
    const yS = v => PAD.top + cH - ((v - gMin) / range) * cH;

    // grid
    ctx.strokeStyle = "rgba(200,188,168,0.8)"; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PAD.top + (i / 4) * cH;
      ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke();
      ctx.fillStyle = "#8a7e6a"; ctx.font = "10px Inter,sans-serif"; ctx.textAlign = "right";
      ctx.fillText((gMax - (i/4)*range).toFixed(1), PAD.left - 5, y + 3.5);
    }
    ctx.save();
    ctx.translate(12, PAD.top + cH / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("value", 0, 0); ctx.restore();

    const labelIdxs = timeKeys.length <= 4 ? timeKeys.map((_,i)=>i) : [0, Math.floor(timeKeys.length/2), timeKeys.length-1];
    labelIdxs.forEach(i => {
      if (!timeKeys[i]) return;
      const ts = new Date(timeKeys[i]);
      ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
      ctx.fillText(ts.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}), xS(i), H - 18);
    });
    ctx.fillStyle = "#8a7e6a"; ctx.font = "9px Inter,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("time (bucket start)", PAD.left + cW/2, H - 4);

    series.forEach(s => {
      if (!s.points.length) return;
      const color = s.color;
      const [r,g,b] = hexRgb(color);
      const ptMap = {};
      s.points.forEach(p => { ptMap[p.bucket_start] = p; });
      const bandPts = timeKeys.map(t => ptMap[t]).filter(Boolean);

      // band
      if (bandPts.length > 1) {
        const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + cH);
        grad.addColorStop(0, `rgba(${r},${g},${b},0.14)`);
        grad.addColorStop(1, `rgba(${r},${g},${b},0.02)`);
        ctx.beginPath();
        ctx.moveTo(xS(timeKeys.indexOf(bandPts[0].bucket_start)), yS(bandPts[0].max ?? bandPts[0].avg ?? 0));
        bandPts.forEach(p => ctx.lineTo(xS(timeKeys.indexOf(p.bucket_start)), yS(p.max ?? p.avg ?? 0)));
        for (let i = bandPts.length-1; i >= 0; i--) {
          const p = bandPts[i];
          ctx.lineTo(xS(timeKeys.indexOf(p.bucket_start)), yS(p.min ?? p.avg ?? 0));
        }
        ctx.closePath(); ctx.fillStyle = grad; ctx.fill();
      }

      // avg line
      ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2.5;
      ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.shadowColor = color; ctx.shadowBlur = 5;
      let first = true;
      timeKeys.forEach((t, i) => {
        const p = ptMap[t]; if (!p) return;
        const x = xS(i), y = yS(p.avg ?? 0);
        first ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        first = false;
      });
      ctx.stroke(); ctx.shadowBlur = 0;

      // dots
      ctx.fillStyle = color;
      timeKeys.forEach((t, i) => {
        const p = ptMap[t]; if (!p) return;
        ctx.beginPath(); ctx.arc(xS(i), yS(p.avg ?? 0), 3, 0, Math.PI*2);
        ctx.fill(); ctx.strokeStyle = "#f5f0e8"; ctx.lineWidth = 1.5; ctx.stroke();
      });
    });

    // store for hover
    chartRegistry[canvas.id] = { points: null, series, color: null, PAD, xS, yS, gMin, gMax, range, cW, cH, W, H, cssH, timeKeys, isCompare: true };
    attachCompareHover(canvas);
  }

  function attachCompareHover(canvas) {
    canvas.onmousemove = (e) => {
      const reg = chartRegistry[canvas.id];
      if (!reg || !reg.isCompare) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const { series, PAD, xS, yS, timeKeys, cH } = reg;

      let best = 0, bestDist = Infinity;
      timeKeys.forEach((_, i) => {
        const d = Math.abs(xS(i) - mx);
        if (d < bestDist) { bestDist = d; best = i; }
      });
      if (bestDist > 40) { getTooltip().style.display = "none"; return; }

      const t = timeKeys[best];
      const ts = new Date(t).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
      let html = `<div style="color:#8a7e6a;font-weight:700;margin-bottom:6px">${ts}</div>`;
      series.forEach(s => {
        const p = s.points.find(pt => pt.bucket_start === t);
        if (!p) return;
        html += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
          <span style="width:10px;height:3px;background:${s.color};display:inline-block;border-radius:2px"></span>
          <span style="color:${s.color};font-weight:600">${s.agent.replace("agent_demo_","")}</span>
          <span style="color:#eef2f7;margin-left:auto">${(p.avg??0).toFixed(2)}</span>
        </div>`;
      });
      const tip = getTooltip();
      tip.innerHTML = html;
      tip.style.display = "block";
      let tx = e.clientX + 14, ty = e.clientY - 20;
      if (tx + 170 > window.innerWidth - 10) tx = e.clientX - 184;
      if (ty + 120 > window.innerHeight - 10) ty = e.clientY - 120;
      tip.style.left = tx + "px"; tip.style.top = ty + "px";
    };
    canvas.onmouseleave = () => { getTooltip().style.display = "none"; };
  }

  function closeCmpModal(e) { if (e.target === document.getElementById("cmpBackdrop")) closeCmpModalDirect(); }
  function closeCmpModalDirect() {
    document.getElementById("cmpBackdrop").classList.remove("open");
    document.body.style.overflow = "";
  }

  // ── persistence ────────────────────────────────────────────────────────────
  function saveState() {
    localStorage.setItem("tixres_state", JSON.stringify({
      agents:      [...selected.agents],
      metrics:     [...selected.metrics],
      measurement: activeMeasurement,
      startMinutes: document.getElementById("startMinutes").value,
      baseUrl:     document.getElementById("baseUrl").value,
    }));
  }

  function loadState() {
    try {
      const raw = localStorage.getItem("tixres_state");
      if (!raw) return;
      const s = JSON.parse(raw);
      if (s.baseUrl) document.getElementById("baseUrl").value = s.baseUrl;
      if (s.startMinutes) document.getElementById("startMinutes").value = s.startMinutes;
      if (s.measurement) {
        activeMeasurement = s.measurement;
        document.querySelectorAll(".meas-btn").forEach(b => {
          b.classList.toggle("active", b.dataset.val === s.measurement);
        });
      }
      if (Array.isArray(s.agents)) {
        s.agents.forEach(a => {
          if (!AVAILABLE_AGENTS.includes(a)) return;
          selected.agents.add(a);
          const chk = document.getElementById(`chk-ms-agents-${a}`);
          if (chk) chk.checked = true;
        });
        syncAllCheckbox("ms-agents", "agents");
        renderTags("ms-agents", "agents");
        updateTriggerLabel("ms-agents", "agents");
      }
      if (Array.isArray(s.metrics)) {
        s.metrics.forEach(m => {
          if (!AVAILABLE_METRICS.includes(m)) return;
          selected.metrics.add(m);
          const chk = document.getElementById(`chk-ms-metrics-${m}`);
          if (chk) chk.checked = true;
        });
        syncAllCheckbox("ms-metrics", "metrics");
        renderTags("ms-metrics", "metrics");
        updateTriggerLabel("ms-metrics", "metrics");
      }
      // auto-run if there was a previous selection
      if (selected.agents.size && selected.metrics.size) runQuery();
    } catch (_) {}
  }

  // ── view switching ─────────────────────────────────────────────────────────
  function switchView(view) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('view-' + view).classList.add('active');
    document.querySelectorAll('.nav-tab')[view === 'metrics' ? 0 : 1].classList.add('active');
  }

  // ── tickets & alerts ────────────────────────────────────────────────────────
  let currentRole = 'user';
  let taStatusFilter = '';
  let taAgentSelected = '';
  let taResolverAgentFilter = '';
  let taPriorityFilter = '';
  let taDetectorFilter = '';

  function setPriorityFilter(el) {
    document.querySelectorAll('#ta-priority-chips .meas-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
    taPriorityFilter = el.dataset.val;
  }

  function setDetectorFilter(val, el) {
    taDetectorFilter = val;
    document.getElementById('ta-detector-label').textContent = val || 'All detectors';
    document.getElementById('ta-detector-label').style.color = val ? 'var(--accent)' : '';
    document.querySelectorAll('#ms-ta-detector-dropdown .ms-option').forEach(o => { o.querySelector('.det-check') && (o.querySelector('.det-check').style.display = 'none'); o.style.background = ''; });
    if (el) { el.style.background = 'rgba(192,80,74,0.06)'; }
    document.getElementById('ms-ta-detector-dropdown').classList.remove('open');
    document.querySelector('#ms-ta-detector .ms-trigger').classList.remove('open');
  }

  function clearTimeRange() {
    document.getElementById('ta-time-from').value = '';
    document.getElementById('ta-time-to').value = '';
  }

  function buildDetectorDropdown(detectors) {
    const dd = document.getElementById('ms-ta-detector-dropdown');
    dd.innerHTML = '';
    const allDiv = document.createElement('div');
    allDiv.className = 'ms-option';
    allDiv.style.cssText = 'cursor:pointer;border-bottom:1px solid var(--border);font-style:italic;color:var(--muted)';
    allDiv.textContent = 'All detectors';
    allDiv.onclick = () => setDetectorFilter('', allDiv);
    dd.appendChild(allDiv);
    [...new Set(detectors)].sort().forEach(d => {
      const div = document.createElement('div');
      div.className = 'ms-option';
      div.style.cssText = 'cursor:pointer';
      div.innerHTML = `<span style="flex:1;font-size:13px">${d}</span><span class="det-check" style="color:var(--accent);display:none">✓</span>`;
      div.onclick = () => setDetectorFilter(d, div);
      dd.appendChild(div);
    });
    // restore label to match current filter without side effects
    const lbl = document.getElementById('ta-detector-label');
    if (lbl) { lbl.textContent = taDetectorFilter || 'All detectors'; lbl.style.color = taDetectorFilter ? 'var(--accent)' : ''; }
  }

  function applyClientFilters(items, timeField) {
    const from = document.getElementById('ta-time-from').value;
    const to   = document.getElementById('ta-time-to').value;
    return items.filter(item => {
      if (taPriorityFilter && item.severity !== taPriorityFilter) return false;
      if (from && new Date(item[timeField]) < new Date(from)) return false;
      if (to   && new Date(item[timeField]) > new Date(to))   return false;
      return true;
    });
  }

  function setRole(role) {
    currentRole = role;
    document.getElementById('roleUser').className = 'role-btn' + (role === 'user' ? ' active-user' : '');
    document.getElementById('roleResolver').className = 'role-btn' + (role === 'resolver' ? ' active-resolver' : '');
    document.getElementById('ta-agent-section').style.display = role === 'user' ? '' : 'none';
    document.getElementById('ta-resolver-agent-section').style.display = role === 'resolver' ? '' : 'none';
    // relabel detector section
    const hdr = document.getElementById('ta-detector-label-hdr');
    if (hdr) hdr.textContent = role === 'resolver' ? 'Metric Filter' : 'Detector Tag';
    // reset detector filter and repopulate
    taDetectorFilter = '';
    if (role === 'user') {
      buildDetectorDropdown(["zscore","threshold_cpu","disk_usage","memory_leak","nic_errors","thread_leak","proc_growth","generic_detector"]);
    } else {
      buildDetectorDropdown(["cpu_v1.0.0.usage_overall","disk_v1.0.0.usage","memory_v1.0.0.ram","network_v1.0.0.errors"]);
    }
  }

  function setStatusFilter(el) {
    document.querySelectorAll('#ta-filter-section .meas-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
    taStatusFilter = el.dataset.val;
  }

  function buildTaAgentDropdown() {
    const dd = document.getElementById('ms-ta-agents-dropdown');
    dd.innerHTML = '';
    AVAILABLE_AGENTS.forEach((agent, i) => {
      const color = AGENT_COLORS[i] ?? AGENT_COLORS[0];
      const div = document.createElement('div');
      div.className = 'ms-option';
      div.style.cssText = 'cursor:pointer';
      div.dataset.agent = agent;
      div.innerHTML = `
        <span style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0;display:inline-block"></span>
        <span style="flex:1;font-size:13px">${agent.replace('agent_demo_','')}</span>
        <span class="ta-check" style="color:${color};font-size:14px;display:none">✓</span>`;
      div.onclick = () => {
        // deselect all
        dd.querySelectorAll('.ms-option').forEach(o => {
          o.querySelector('.ta-check').style.display = 'none';
          o.style.background = '';
        });
        // select this
        div.querySelector('.ta-check').style.display = '';
        div.style.background = `${color}18`;
        taAgentSelected = agent;
        document.getElementById('ta-agent-label').textContent = agent.replace('agent_demo_','');
        document.getElementById('ta-agent-label').style.color = color;
        // close dropdown
        dd.classList.remove('open');
        document.querySelector('#ms-ta-agents .ms-trigger').classList.remove('open');
      };
      dd.appendChild(div);
    });
  }

  function buildResolverAgentDropdown() {
    const dd = document.getElementById('ms-ta-resolver-agents-dropdown');
    dd.innerHTML = '';
    // "All" option
    const allDiv = document.createElement('div');
    allDiv.className = 'ms-option';
    allDiv.style.cssText = 'cursor:pointer;border-bottom:1px solid var(--border)';
    allDiv.innerHTML = `<span style="flex:1;font-size:13px;font-weight:600;color:var(--accent)">All agents</span><span class="ra-check" style="font-size:14px;color:var(--accent)">✓</span>`;
    allDiv.onclick = () => {
      dd.querySelectorAll('.ms-option').forEach(o => { const c = o.querySelector('.ra-check'); if(c) c.style.display='none'; o.style.background=''; });
      allDiv.querySelector('.ra-check').style.display = '';
      taResolverAgentFilter = '';
      document.getElementById('ta-resolver-agent-label').textContent = 'All agents';
      document.getElementById('ta-resolver-agent-label').style.color = '';
      dd.classList.remove('open');
      document.querySelector('#ms-ta-resolver-agents .ms-trigger').classList.remove('open');
    };
    dd.appendChild(allDiv);

    AVAILABLE_AGENTS.forEach((agent, i) => {
      const color = AGENT_COLORS[i] ?? AGENT_COLORS[0];
      const div = document.createElement('div');
      div.className = 'ms-option';
      div.style.cssText = 'cursor:pointer';
      div.innerHTML = `
        <span style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0;display:inline-block"></span>
        <span style="flex:1;font-size:13px">${agent.replace('agent_demo_','')}</span>
        <span class="ra-check" style="color:${color};font-size:14px;display:none">✓</span>`;
      div.onclick = () => {
        dd.querySelectorAll('.ms-option').forEach(o => { const c = o.querySelector('.ra-check'); if(c) c.style.display='none'; o.style.background=''; });
        div.querySelector('.ra-check').style.display = '';
        div.style.background = `${color}18`;
        taResolverAgentFilter = agent;
        document.getElementById('ta-resolver-agent-label').textContent = agent.replace('agent_demo_','');
        document.getElementById('ta-resolver-agent-label').style.color = color;
        dd.classList.remove('open');
        document.querySelector('#ms-ta-resolver-agents .ms-trigger').classList.remove('open');
      };
      dd.appendChild(div);
    });
  }

  async function loadTicketsAlerts() {
    const base = normalizeBase(document.getElementById('baseUrl').value);
    if (!base) { alert('Enter a valid Base URL.'); return; }
    const main = document.getElementById('ta-main');
    main.innerHTML = '<div class="empty-state"><div class="icon">⏳</div><p>Loading…</p></div>';

    if (currentRole === 'user') {
      const agent = taAgentSelected || document.querySelector('input[name="ta-agent"]:checked')?.value;
      if (!agent) { main.innerHTML = '<div class="empty-state"><p>Select an agent first.</p></div>'; return; }
      await loadUserTickets(base, agent, main);
    } else {
      await loadResolverAlerts(base, main);
    }
  }

  async function loadUserTickets(base, agentId, main) {
    try {
      const params = new URLSearchParams({ limit: 50 });
      if (taStatusFilter)   params.set('status', taStatusFilter);
      if (taPriorityFilter) params.set('severity', taPriorityFilter);
      if (taDetectorFilter) params.set('detector', taDetectorFilter);
      const from = document.getElementById('ta-time-from').value;
      const to   = document.getElementById('ta-time-to').value;
      if (from) params.set('start', new Date(from).toISOString());
      if (to)   params.set('end',   new Date(to).toISOString());
      const res = await fetch(`${base}/api/tickets/${agentId}/latest?${params.toString()}`);
      const data = await res.json();
      let tickets = data.tickets || [];
      // populate detector dropdown from loaded data
      const allDetectors = tickets.flatMap(t => t.detectors || []);
      buildDetectorDropdown(allDetectors);
      // apply filters
      if (taStatusFilter) tickets = tickets.filter(t => t.status === taStatusFilter);
      if (taDetectorFilter) tickets = tickets.filter(t => (t.detectors||[]).includes(taDetectorFilter));
      tickets = applyClientFilters(tickets, 'last_occurred_at');
      main.innerHTML = '';
      const hdr = document.createElement('div');
      hdr.className = 'section-hdr';
      hdr.innerHTML = `Tickets for <span style="color:var(--accent)">${agentId}</span> <span class="count-badge">${tickets.length}</span>`;
      main.appendChild(hdr);
      if (!tickets.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.innerHTML = '<div class="icon">✅</div><p>No tickets match the filters.</p>';
        main.appendChild(empty);
        return;
      }
      tickets.forEach(t => main.appendChild(buildTicketCard(t, base)));
    } catch (e) {
      main.innerHTML = `<div class="empty-state"><p>Error: ${e}</p></div>`;
    }
  }

  async function loadResolverAlerts(base, main) {
    try {
      const params = new URLSearchParams({ limit: 50 });
      if (taStatusFilter) params.set('status', taStatusFilter);
      if (taPriorityFilter) params.set('severity', taPriorityFilter);
      if (taDetectorFilter) params.set('metric_name', taDetectorFilter);
      if (taResolverAgentFilter) params.set('agent_id', taResolverAgentFilter);
      const from = document.getElementById('ta-time-from').value;
      const to   = document.getElementById('ta-time-to').value;
      if (from) params.set('start', new Date(from).toISOString());
      if (to)   params.set('end',   new Date(to).toISOString());
      const res = await fetch(`${base}/api/alerts?${params}`);
      const data = await res.json();
      let alerts = data.items || [];
      // populate filter dropdown with metric names for resolver
      const allMetrics = [...new Set(alerts.map(a => a.metric_name))];
      buildDetectorDropdown(allMetrics);
      // client-side filters
      if (taResolverAgentFilter) {
        alerts = alerts.filter(a => {
          try { return JSON.parse(a.agent_ids || '[]').includes(taResolverAgentFilter); }
          catch { return false; }
        });
      }
      if (taDetectorFilter) {
        alerts = alerts.filter(a => a.metric_name === taDetectorFilter);
      }
      alerts = applyClientFilters(alerts, 'last_seen_at');
      main.innerHTML = '';
      const hdr = document.createElement('div');
      hdr.className = 'section-hdr';
      hdr.innerHTML = `Alerts <span class="count-badge">${alerts.length}</span>`;
      main.appendChild(hdr);
      if (!alerts.length) {
        main.innerHTML += '<div class="empty-state"><div class="icon">✅</div><p>No alerts match the filters.</p></div>';
        return;
      }
      alerts.forEach(a => main.appendChild(buildAlertCard(a, base)));
    } catch (e) {
      main.innerHTML = `<div class="empty-state"><p>Error: ${e}</p></div>`;
    }
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
  }

  function buildTicketCard(t, base) {
    const el = document.createElement('div');
    el.className = `ticket-card sev-${t.severity}`;
    const statusCls = t.status === 'OPEN' ? 'badge-open' : t.status === 'ACK' ? 'badge-ack' : 'badge-closed';
    const detectors = (t.detectors || []).map(d =>
      `<span class="detector-tag" style="cursor:pointer" title="Filter by ${d}" onclick="quickFilterDetector('${d}')">${d}</span>`
    ).join('');
    el.innerHTML = `
      <div class="ticket-header">
        <div class="ticket-metric">${t.metric_name}</div>
        <div class="ticket-badges">
          <span class="badge badge-${t.severity}" style="cursor:pointer" title="Filter by ${t.severity}" onclick="quickFilterPriority('${t.severity}')">${t.severity}</span>
          <span class="badge ${statusCls}">${t.status}</span>
        </div>
      </div>
      <div class="ticket-message">${t.message || '—'}</div>
      <div class="ticket-footer">
        <div class="ticket-detectors">${detectors}</div>
        <span>×${t.occurrence_count} · ${fmtTime(t.last_occurred_at)}</span>
      </div>`;
    return el;
  }

  function buildAlertCard(a, base) {
    const el = document.createElement('div');
    el.className = `alert-card sev-${a.severity}`;
    const agents = JSON.parse(a.agent_ids || '[]');
    const agentTags = agents.map(ag => `<span class="agent-tag">${ag.replace('agent_demo_','')}</span>`).join('');
    const statusCls = a.status === 'OPEN' ? 'badge-open' : a.status === 'ACK' ? 'badge-ack' : 'badge-closed';
    const typeCls = a.type === 'GROUP' ? 'badge-group' : 'badge-single';
    const actions = a.status === 'OPEN'
      ? `<div style="display:flex;gap:8px">
           <button class="ack-btn" onclick="ackAlert(${a.id},'${base}',this)">Acknowledge</button>
           <button class="resolve-btn" onclick="resolveAlert(${a.id},'${base}',this)">Resolve</button>
         </div>`
      : `<span style="font-size:11px;color:var(--muted)">${a.status === 'ACK' ? `Acked by ${a.acknowledged_by||'resolver'}` : `Closed ${fmtTime(a.closed_at)}`}</span>`;
    el.innerHTML = `
      <div class="ticket-header">
        <div class="ticket-metric">${a.metric_name}</div>
        <div class="ticket-badges">
          <span class="badge badge-${a.severity}" style="cursor:pointer" title="Filter by ${a.severity}" onclick="quickFilterPriority('${a.severity}')">${a.severity}</span>
          <span class="badge ${typeCls}">${a.type}</span>
          <span class="badge ${statusCls}" id="alert-status-${a.id}">${a.status}</span>
        </div>
      </div>
      <div class="alert-agents">${agentTags}</div>
      <div class="ticket-message">×${a.total_occurrence} occurrences · first ${fmtTime(a.first_seen_at)} · last ${fmtTime(a.last_seen_at)}</div>
      <div class="alert-footer">
        <span style="font-size:11px;color:var(--muted)">${a.purpose}</span>
        ${actions}
      </div>`;
    return el;
  }

  async function ackAlert(id, base, btn) {
    btn.disabled = true; btn.textContent = '…';
    try {
      const res = await fetch(`${base}/api/alerts/${id}/ack`, {
        method: 'PATCH',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({acked_by: 'resolver'})
      });
      if (res.ok) {
        const statusBadge = document.getElementById(`alert-status-${id}`);
        if (statusBadge) { statusBadge.textContent = 'ACK'; statusBadge.className = 'badge badge-ack'; }
        btn.closest('.alert-footer').querySelector('div').innerHTML =
          `<span style="font-size:11px;color:var(--muted)">Acked by resolver</span>`;
      } else { btn.disabled = false; btn.textContent = 'Acknowledge'; }
    } catch { btn.disabled = false; btn.textContent = 'Acknowledge'; }
  }

  async function resolveAlert(id, base, btn) {
    if (!confirm('Resolve this alert and close related tickets?')) return;
    btn.disabled = true; btn.textContent = '…';
    try {
      const res = await fetch(`${base}/api/alerts/${id}/resolve`, { method:'POST' });
      if (res.ok) { btn.closest('.alert-card').querySelector('.badge-open').textContent = 'CLOSED'; btn.closest('.alert-card').querySelector('.badge-open').className = 'badge badge-closed'; btn.remove(); }
      else { btn.disabled = false; btn.textContent = 'Resolve'; }
    } catch { btn.disabled = false; btn.textContent = 'Resolve'; }
  }

  function quickFilterPriority(sev) {
    taPriorityFilter = sev;
    document.querySelectorAll('#ta-priority-chips .meas-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.val === sev);
    });
    loadTicketsAlerts();
  }

  function quickFilterDetector(det) {
    taDetectorFilter = det;
    document.getElementById('ta-detector-label').textContent = det;
    document.getElementById('ta-detector-label').style.color = 'var(--accent)';
    loadTicketsAlerts();
  }

  buildDropdown("ms-agents", AVAILABLE_AGENTS, null);
  buildDropdown("ms-metrics", AVAILABLE_METRICS, m => METRIC_LABELS[m] || m);
  buildTaAgentDropdown();
  buildResolverAgentDropdown();
  setRole('user');
  loadState();
