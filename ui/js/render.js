import { $, clamp, fmtBytes, fmtPercent, fmtRateFromMBps, fmtNumber } from "./utils.js";

function setText(id, text) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
}

function setHtml(id, html) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = html;
}

function setBar(id, pct, className) {
  const el = $(id);
  if (!el) return;
  const p = clamp(Number(pct), 0, 100);
  el.style.width = `${p}%`;
  if (className) el.className = `bar-fill ${className}`;
}

export function renderTopBar(state) {
  const selector = $("#agent-selector");
  if (selector) {
    const currentVal = selector.value;
    const html = state.agents
      .map((a) => {
        const name = a.hostname || a.agent_id;
        const status = a.connected ? "●" : "○";
        return `<option value="${a.agent_id}" ${
          a.agent_id === state.selectedAgentId ? "selected" : ""
        }>${status} ${name}</option>`;
      })
      .join("");
    if (!html) {
      selector.innerHTML = '<option value="">No agents found</option>';
    } else {
      selector.innerHTML = html;
    }
  }

  const pluginSelector = $("#plugin-selector");
  if (pluginSelector) {
    const currentAgent = state.agents.find((a) => a.agent_id === state.selectedAgentId);
    const activePlugin = currentAgent ? currentAgent.plugin : null;
    const html = (state.plugins || [])
      .map(
        (p) =>
          `<option value="${p}" ${p === activePlugin ? "selected" : ""}>${p.replace(
            /_/g,
            " "
          )}</option>`
      )
      .join("");
    pluginSelector.innerHTML = `<option value="">Default (Global Template)</option>${html}`;
  }

  setText("system-badge", state.wsConnected ? "Live" : "Connecting…");
  const badge = $("system-badge");
  if (badge) {
    badge.className = `card-badge ${state.wsConnected ? "badge-ok" : "badge-info"}`;
  }

  const uptime = state.system.uptime?.formatted;
  setText("agent-uptime", uptime ? `Uptime: ${uptime}` : "Uptime: —");
}

export function renderCpu(state) {
  const overall = state.cpu.overall;
  setText("cpu-overall", Number.isFinite(overall) ? `${Math.round(overall)}%` : "—");
  setBar("cpu-bar", overall ?? 0, overall > 80 ? "bar-red" : overall > 60 ? "bar-amber" : "bar-blue");

  const freq = state.cpu.freq?.current;
  const ghz = Number.isFinite(freq) ? freq / 1000 : null; // psutil returns MHz
  setText("cpu-ghz", ghz ? `${ghz.toFixed(1)} GHz` : "—");

  const temp = state.cpu.temp;
  const tempEl = $("cpu-temp");
  if (tempEl) {
    if (!Number.isFinite(temp) || temp < 0) {
      tempEl.textContent = "—";
      tempEl.style.color = "#8b949e";
    } else {
      tempEl.textContent = `${Math.round(temp)}°C`;
      tempEl.style.color = temp > 80 ? "#f85149" : temp > 70 ? "#d29922" : "#3fb950";
    }
  }

  const cpu = Number.isFinite(overall) ? overall : 0;
  const cLabel = cpu > 70 ? "high load" : cpu > 45 ? "moderate load" : "low load";
  const interp = $("cpu-interp");
  if (interp) {
    interp.textContent = cLabel;
    interp.className = cpu > 70 ? "int-hot" : cpu > 45 ? "int-warn" : "int-ok";
  }

  const badge = $("cpu-badge");
  if (badge) {
    badge.textContent = cpu > 70 ? "High" : cpu > 45 ? "Moderate" : "Normal";
    badge.className = `card-badge ${cpu > 70 ? "badge-danger" : cpu > 45 ? "badge-warn" : "badge-info"}`;
  }

  const perCore = state.cpu.perCore;
  if (perCore && typeof perCore === "object") {
    const keys = Object.keys(perCore).sort((a, b) => Number(a) - Number(b));
    const maxCores = 32;
    const shown = keys.slice(0, maxCores);
    const html = shown
      .map((k) => {
        const v = Number(perCore[k]);
        const pct = Number.isFinite(v) ? v : 0;
        const col = pct > 75 ? "#f85149" : pct > 50 ? "#d29922" : "#1f6feb";
        return `<div class="core-box"><div class="core-label">C${k}</div><div class="core-val" style="color:${col}">${Math.round(
          pct
        )}%</div><div class="minibar"><div class="minibar-fill" style="width:${clamp(
          pct,
          0,
          100
        )}%;background:${col}"></div></div></div>`;
      })
      .join("");
    setHtml("core-grid", html);
  }
}

export function renderMemory(state) {
  const ram = state.memory.ram;
  if (ram) {
    setText("ram-used", Number.isFinite(ram.used_gb) ? `${ram.used_gb.toFixed(1)} GB` : "—");
    setText("ram-avail", Number.isFinite(ram.available_gb) ? `${ram.available_gb.toFixed(1)} GB` : "—");
    setText("ram-total", Number.isFinite(ram.total_gb) ? `${ram.total_gb.toFixed(0)} GB` : "—");
    setText("ram-total-inline", Number.isFinite(ram.total_gb) ? `${ram.total_gb.toFixed(0)} GB` : "—");
    setText("ram-pct", Number.isFinite(ram.percent) ? fmtPercent(ram.percent, 0) : "—");
    setBar("ram-bar", ram.percent ?? 0, "bar-purple");

    const badge = $("ram-badge");
    if (badge) {
      const p = Number(ram.percent) || 0;
      badge.textContent = p > 85 ? "High" : p > 65 ? "Moderate" : "Healthy";
      badge.className = `card-badge ${p > 85 ? "badge-danger" : p > 65 ? "badge-warn" : "badge-ok"}`;
    }
  }

  const swap = state.memory.swap;
  if (swap) {
    setText("swap-pct", Number.isFinite(swap.percent) ? fmtPercent(swap.percent, 0) : "—");
    setText("swap-total", Number.isFinite(swap.total_gb) ? `${swap.total_gb.toFixed(0)} GB` : "—");
    setBar("swap-bar", swap.percent ?? 0, "bar-amber");
  }
}

export function renderDisk(state) {
  const usage = state.disk.usage;
  if (usage && typeof usage === "object") {
    const mounts = Object.keys(usage);
    let anyWarn = false;
    const html = mounts
      .map((mount) => {
        const u = usage[mount] || {};
        const pct = Number(u.percent) || 0;
        const used = Number(u.used_gb);
        const total = Number(u.total_gb);
        const warn = pct >= 85;
        anyWarn = anyWarn || warn;
        const barClass = warn ? "bar-red" : pct > 60 ? "bar-amber" : "bar-green";
        return `<div class="disk-item"><div class="disk-path">${mount}${warn ? '<span class="card-badge badge-warn" style="margin-left:6px;font-size:9px">Low space</span>' : ""}</div><div class="bar-track"><div class="bar-fill ${barClass}" style="width:${clamp(
          pct,
          0,
          100
        )}%"></div></div><div class="disk-row"><span>${Number.isFinite(used) ? used.toFixed(0) : "—"} GB used</span><span>${Math.round(
          pct
        )}%</span><span>${Number.isFinite(total) ? total.toFixed(0) : "—"} GB</span></div></div>`;
      })
      .join("");
    setHtml("disk-list", html);

    const warnBar = $("warn-bar");
    const warnText = $("warn-text");
    if (warnBar && warnText) {
      if (anyWarn) {
        const worst = mounts
          .map((m) => ({ m, pct: Number(usage[m]?.percent) || 0 }))
          .sort((a, b) => b.pct - a.pct)[0];
        warnText.textContent = `Disk ${worst.m} is at ${Math.round(worst.pct)}% capacity — consider cleanup`;
        warnBar.style.display = "flex";
      } else {
        warnBar.style.display = "none";
      }
    }

    const diskBadge = $("disk-badge");
    if (diskBadge) {
      diskBadge.textContent = anyWarn ? "Warning" : "Active";
      diskBadge.className = `card-badge ${anyWarn ? "badge-warn" : "badge-info"}`;
    }
  }

  const io = state.disk.io;
  if (io) {
    setText("disk-read", Number.isFinite(io.read_mb_s) ? fmtRateFromMBps(io.read_mb_s) : "—");
    setText("disk-write", Number.isFinite(io.write_mb_s) ? fmtRateFromMBps(io.write_mb_s) : "—");
  }
}

export function renderNetwork(state) {
  const io = state.network.io;
  if (io) {
    setText("net-up", Number.isFinite(io.upload_mb_s) ? fmtRateFromMBps(io.upload_mb_s) : "—");
    setText("net-dn", Number.isFinite(io.download_mb_s) ? fmtRateFromMBps(io.download_mb_s) : "—");

    setText(
      "net-sent",
      Number.isFinite(io.total_sent_bytes) ? fmtBytes(io.total_sent_bytes) : "—"
    );
    setText(
      "net-recv",
      Number.isFinite(io.total_recv_bytes) ? fmtBytes(io.total_recv_bytes) : "—"
    );
  }

  const conns = state.network.connections;
  if (conns) setText("net-conns", fmtNumber(conns.total, 0));

  const detail = state.network.connectionsDetail;
  if (Array.isArray(detail)) {
    const html = detail
      .slice(0, 6)
      .map((c) => {
        const proc = c.proc || c.pid || "unknown";
        const addr = c.remote || c.local || "";
        const status = c.status || "";
        return `<div class="conn-item"><span class="conn-proc">${proc}</span><span class="conn-addr">${addr}</span><span class="conn-state">${status}</span></div>`;
      })
      .join("");
    setHtml("proc-net", html);
    setHtml("conn-detail", html);
  }
}

export function renderHardware(state) {
  const info = state.system.info;
  if (info) {
    setText("hw-os", `${info.system || "—"} ${info.release || ""}`.trim() || "—");
    setText("hw-cpu", info.processor || info.machine || "—");
  }

  if (Number.isFinite(state.cpu.coreCount)) {
    setText("hw-cores", `${state.cpu.coreCount} threads`);
  }

  if (state.memory.ram && Number.isFinite(state.memory.ram.total_gb)) {
    setText("hw-ram", `${state.memory.ram.total_gb.toFixed(0)} GB`);
  }

  if (Number.isFinite(state.cpu.temp) && state.cpu.temp >= 0) {
    setText("hw-cpu-max-temp", `${Math.round(state.cpu.temp)}°C`);
  }
}

export function renderProcesses(state) {
  const procs = Array.isArray(state.processes) ? state.processes : [];
  setText("proc-count", state.system.processCount ? `${state.system.processCount} processes` : `${procs.length} processes`);

  const filter = (state.processFilter || "").toLowerCase();
  const sortKey = state.processSortKey || "cpu";

  let data = procs.slice();
  if (filter) {
    data = data.filter((p) => {
      const name = String(p.name || "").toLowerCase();
      const pid = String(p.pid || "");
      return name.includes(filter) || pid.includes(filter);
    });
  }

  data.sort((a, b) => {
    if (sortKey === "pid") return (a.pid || 0) - (b.pid || 0);
    if (sortKey === "mem") return (b.mem_mb || 0) - (a.mem_mb || 0);
    return (b.cpu_percent || 0) - (a.cpu_percent || 0);
  });

  const tb = $("proc-tbody");
  if (!tb) return;

  tb.innerHTML = "";
  for (const p of data.slice(0, 50)) {
    const cpu = Number(p.cpu_percent) || 0;
    const mem = Number(p.mem_mb);
    const cpuBar = clamp(cpu * 4, 0, 100);
    const memBar = Number.isFinite(mem) ? clamp(mem / 25, 0, 100) : 0;
    const cpuCol = cpu > 15 ? "#f85149" : cpu > 8 ? "#d29922" : "#1f6feb";
    const status = String(p.status || "");
    const statusCol = status === "running" ? "#3fb950" : "#8b949e";
    const pidStr = p.pid != null ? String(p.pid) : "";
    const nameStr = p.name != null ? String(p.name) : "";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="pid-tag">${pidStr || "—"}</td>
      <td class="proc-name"></td>
      <td style="color:${cpuCol};font-weight:500">${cpu.toFixed(1)}%</td>
      <td><div class="bar-track" style="margin:0"><div class="bar-fill" style="width:${cpuBar}%;background:${cpuCol}"></div></div></td>
      <td>${Number.isFinite(mem) ? mem.toFixed(0) : "—"}</td>
      <td><div class="bar-track" style="margin:0"><div class="bar-fill bar-purple" style="width:${memBar}%"></div></div></td>
      <td><span style="color:${statusCol};font-size:10px">${status || "—"}</span></td>
      <td></td>
    `;
    // Set process name safely (no XSS)
    tr.querySelector(".proc-name").textContent = nameStr || "—";

    // Build kill button with dataset (avoids attribute injection)
    const killBtn = document.createElement("button");
    killBtn.className = "kill-btn";
    killBtn.textContent = "Kill";
    killBtn.dataset.pid = pidStr;
    killBtn.dataset.name = nameStr;
    if (!pidStr) killBtn.disabled = true;
    tr.querySelector("td:last-child").appendChild(killBtn);

    tb.appendChild(tr);
  }
}

export function renderAlerts(state) {
  const container = $("alerts-container");
  if (!container) return;

  if (state.alerts.length === 0) {
    container.innerHTML = '<div class="alert-empty">No active anomalies detected.</div>';
    return;
  }

  container.innerHTML = state.alerts
    .map((a) => {
      const time = a.last_seen || a.timestamp || "";
      const timeStr = time ? (time.includes("T") ? time.split("T")[1].split(".")[0] : time.split(" ")[1] || time) : "";
      return `
        <div class="alert-item severity-${a.severity}">
          <div class="alert-content">
            <div class="alert-title" style="text-transform: capitalize;">${a.anomaly_type.replace(/_/g, " ")}: ${a.service}</div>
            <div class="alert-meta">${a.severity} • ${timeStr} • ${a.plugin || "detector"}</div>
          </div>
          ${a.count > 1 ? `<div class="alert-count">${a.count}x</div>` : ""}
        </div>
      `;
    })
    .join("");
}

window.renderAlerts = renderAlerts;

