import { $, qsParam, unwrapMetricValue } from "./utils.js";
import { WS_URL } from "./config.js";

import { LineChart } from "./charts.js";
import { createWsClient } from "./ws.js";
import {
  renderCpu,
  renderDisk,
  renderHardware,
  renderMemory,
  renderNetwork,
  renderProcesses,
  renderTopBar,
} from "./render.js";

window.__tixres_started = true;

const HIST_LEN = 30;
const HISTORY = {
  cpu: Array(HIST_LEN).fill(0),
  ram: Array(HIST_LEN).fill(0),
  netUp: Array(HIST_LEN).fill(0),
  netDn: Array(HIST_LEN).fill(0),
  diskR: Array(HIST_LEN).fill(0),
  diskW: Array(HIST_LEN).fill(0),
};

const state = {
  wsConnected: false,
  agents: [],
  selectedAgentId: null,
  selectedAgent: null,
  cpu: { overall: null, perCore: null, freq: null, temp: null, coreCount: null },
  memory: { ram: null, swap: null },
  disk: { usage: null, io: null },
  network: { io: null, connections: null, connectionsDetail: null },
  system: { uptime: null, info: null, processCount: null },
  processes: [],
  alerts: [],
  plugins: [],
  processSortKey: "cpu",
  processFilter: "",
};

const charts = {
  cpu: new LineChart($("#cpuChart"), {
    series: [
      {
        data: HISTORY.cpu,
        stroke: "#1f6feb",
        fill: "rgba(31,111,235,.12)",
        width: 2,
      },
    ],
    minY: 0,
    maxY: 100,
  }),
  ram: new LineChart($("#ramChart"), {
    series: [
      {
        data: HISTORY.ram,
        stroke: "#6e40c9",
        fill: "rgba(110,64,201,.12)",
        width: 2,
      },
    ],
    minY: 0,
    maxY: 100,
  }),
  net: new LineChart($("#netChart"), {
    series: [
      { data: HISTORY.netUp, stroke: "#3fb950", fill: null, width: 2 },
      { data: HISTORY.netDn, stroke: "#58a6ff", fill: null, width: 2 },
    ],
    minY: 0,
    maxY: null,
  }),
  disk: new LineChart($("#diskChart"), {
    series: [
      { data: HISTORY.diskR, stroke: "#58a6ff", fill: null, width: 2 },
      { data: HISTORY.diskW, stroke: "#d29922", fill: null, width: 2 },
    ],
    minY: 0,
    maxY: null,
  }),
};

function push(arr, val) {
  arr.shift();
  arr.push(val);
}

function metricTick() {
  const lastCpu = HISTORY.cpu[HISTORY.cpu.length - 1] ?? 0;
  const lastRam = HISTORY.ram[HISTORY.ram.length - 1] ?? 0;
  const lastNetUp = HISTORY.netUp[HISTORY.netUp.length - 1] ?? 0;
  const lastNetDn = HISTORY.netDn[HISTORY.netDn.length - 1] ?? 0;
  const lastDiskR = HISTORY.diskR[HISTORY.diskR.length - 1] ?? 0;
  const lastDiskW = HISTORY.diskW[HISTORY.diskW.length - 1] ?? 0;

  push(HISTORY.cpu, Number.isFinite(state.cpu.overall) ? state.cpu.overall : lastCpu);
  push(HISTORY.ram, Number.isFinite(state.memory.ram?.percent) ? state.memory.ram.percent : lastRam);
  push(HISTORY.netUp, Number.isFinite(state.network.io?.upload_mb_s) ? state.network.io.upload_mb_s : lastNetUp);
  push(HISTORY.netDn, Number.isFinite(state.network.io?.download_mb_s) ? state.network.io.download_mb_s : lastNetDn);
  push(HISTORY.diskR, Number.isFinite(state.disk.io?.read_mb_s) ? state.disk.io.read_mb_s : lastDiskR);
  push(HISTORY.diskW, Number.isFinite(state.disk.io?.write_mb_s) ? state.disk.io.write_mb_s : lastDiskW);

  charts.cpu.render();
  charts.ram.render();
  charts.net.render();
  charts.disk.render();
}

function clockTick() {
  const el = $("#clock");
  if (!el) return;
  el.textContent = new Date().toLocaleTimeString();
}


function handleMetric({ name, dtype, value }) {
  if (typeof name !== "string") return;
  const v = unwrapMetricValue(value);

  switch (name) {
    case "cpu_v1.0.0.usage_overall": {
      const n = Number(v);
      state.cpu.overall = Number.isFinite(n) ? n : null;
      renderCpu(state);
      break;
    }
    case "cpu_v1.0.0.usage_per_core": {
      state.cpu.perCore = v && typeof v === "object" ? v : null;
      renderCpu(state);
      break;
    }
    case "cpu_v1.0.0.frequency": {
      state.cpu.freq = v && typeof v === "object" ? v : null;
      renderCpu(state);
      break;
    }
    case "cpu_v1.0.0.temperature": {
      const n = Number(v);
      state.cpu.temp = Number.isFinite(n) ? n : null;
      renderCpu(state);
      renderHardware(state);
      break;
    }
    case "cpu_v1.0.0.core_count": {
      const n = Number(v);
      state.cpu.coreCount = Number.isFinite(n) ? n : null;
      renderHardware(state);
      break;
    }
    case "memory_v1.0.0.ram": {
      state.memory.ram = v && typeof v === "object" ? v : null;
      renderMemory(state);
      renderHardware(state);
      break;
    }
    case "memory_v1.0.0.swap": {
      state.memory.swap = v && typeof v === "object" ? v : null;
      renderMemory(state);
      break;
    }
    case "disk_v1.0.0.usage": {
      state.disk.usage = v && typeof v === "object" ? v : null;
      renderDisk(state);
      break;
    }
    case "disk_v1.0.0.io": {
      state.disk.io = v && typeof v === "object" ? v : null;
      renderDisk(state);
      break;
    }
    case "network_v1.0.0.io": {
      state.network.io = v && typeof v === "object" ? v : null;
      renderNetwork(state);
      break;
    }
    case "network_v1.0.0.connections": {
      state.network.connections = v && typeof v === "object" ? v : null;
      renderNetwork(state);
      break;
    }
    case "network_v1.0.0.connections_detail": {
      state.network.connectionsDetail = Array.isArray(v) ? v : null;
      renderNetwork(state);
      break;
    }
    case "system_v1.0.0.uptime": {
      state.system.uptime = v && typeof v === "object" ? v : null;
      renderTopBar(state);
      break;
    }
    case "system_v1.0.0.info": {
      state.system.info = v && typeof v === "object" ? v : null;
      renderHardware(state);
      break;
    }
    case "system_v1.0.0.process_count": {
      const n = Number(v);
      state.system.processCount = Number.isFinite(n) ? n : null;
      renderProcesses(state);
      break;
    }
    case "process_v1.0.0.top": {
      state.processes = Array.isArray(v) ? v : [];
      renderProcesses(state);
      break;
    }
    default:
      // ignore
      break;
  }
}

function selectAgent(id) {
  if (!id) return;
  state.selectedAgentId = id;
  state.selectedAgent = state.agents.find(a => a.agent_id === id) || null;
  
  // Clear real-time history
  Object.values(HISTORY).forEach(arr => arr.fill(0));
  
  // Update UI immediately
  renderTopBar(state);
}

const ws = createWsClient(WS_URL, {
  onOpen: () => {
    state.wsConnected = true;
    renderTopBar(state);
    ws.send({
      event: "ui_subscribe",
      data: {
        token: window.__tixres_token,
        agent_id: qsParam("agent_id")
      }
    });
  },
  onClose: () => {
    state.wsConnected = false;
    renderTopBar(state);
  },
  onMessage: (msg) => {
    const event = msg?.event;
    if (typeof event !== "string") return;
    if (event === "hello") return;

    if (event === "ui_subscribe" && msg.ok === true) {
      const data = msg.data || {};
      state.agents = Array.isArray(data.agents) ? data.agents : [];
      state.plugins = Array.isArray(data.plugins) ? data.plugins : [];
      const selected = data.selected_agent_id || qsParam("agent_id") || state.agents[0]?.agent_id || null;
      if (selected) {
        state.selectedAgentId = selected; // set for handleMetric
        selectAgent(selected);
      }

      const recent = Array.isArray(data.recent_metrics) ? data.recent_metrics : [];
      for (const row of recent) {
        handleMetric({
          name: row.metric_name,
          dtype: row.dtype,
          value: row.value,
        });
      }

      renderTopBar(state);
      renderCpu(state);
      renderMemory(state);
      renderDisk(state);
      renderNetwork(state);
      renderHardware(state);
      renderProcesses(state);
      return;
    }

    if (event === "ui_subscribe" && msg.ok === false) {
      sessionStorage.clear();
      location.href = "login.html?next=index.html";
      return;
    }

    if (event === "metric" && msg.ok === true) {
      const d = msg.data || {};
      if (state.selectedAgentId && d.agent_id !== state.selectedAgentId) return;
      handleMetric({ name: d.name, dtype: d.dtype, value: d.value });
      return;
    }

    if (event === "alert" && msg.ok === true) {
      const d = msg.data || {};
      if (state.selectedAgentId && d.agent_id !== state.selectedAgentId) return;
      state.alerts.unshift(d);
      if (state.alerts.length > 50) state.alerts.pop();
      if (typeof window.renderAlerts === "function") {
          window.renderAlerts(state);
      }
      return;
    }

    if ((event === "agent_connected" || event === "agent_disconnected") && msg.ok === true) {
      // Best-effort: refresh the badge; the next ui_subscribe will carry full state.
      renderTopBar(state);
      return;
    }
  },
});

function wireUiEvents() {
  const search = $("#proc-search");
  if (search) {
    search.addEventListener("input", (e) => {
      state.processFilter = String(e.target.value || "");
      renderProcesses(state);
    });
  }

  const pluginSelector = $("#plugin-selector");
  if (pluginSelector) {
    pluginSelector.addEventListener("change", (e) => {
      const pluginName = e.target.value || null;
      if (!state.selectedAgentId) return;

      ws.send({
        event: "ui_set_agent_plugin",
        data: {
          token: window.__tixres_token,
          agent_id: state.selectedAgentId,
          plugin: pluginName
        }
      });
      
      // Update local state temporarily for immediate UI feedback
      const agent = state.agents.find(a => a.agent_id === state.selectedAgentId);
      if (agent) agent.plugin = pluginName;
      renderTopBar(state);
    });
  }

  const selector = $("#agent-selector");
  if (selector) {
    selector.addEventListener("change", (e) => {
      const newId = e.target.value;
      if (!newId || newId === state.selectedAgentId) return;

      selectAgent(newId);
      
      // Also re-subscribe for real-time
      ws.send({
        event: "ui_subscribe",
        data: {
          token: window.__tixres_token,
          agent_id: newId
        }
      });
    });
  }

  document.querySelectorAll("button.tab-btn[data-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sort = btn.getAttribute("data-sort");
      state.processSortKey = sort || "cpu";
      document.querySelectorAll("button.tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderProcesses(state);
    });
  });

  const tb = $("#proc-tbody");
  if (tb) {
    tb.addEventListener("click", (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      const btn = target.closest("button.kill-btn");
      if (!btn || btn.disabled) return;

      // Read from dataset (set programmatically in render.js, no injection risk)
      const pidStr = btn.dataset.pid || "";
      const name = btn.dataset.name || "";
      const pid = parseInt(pidStr, 10);

      if (!pidStr || !Number.isFinite(pid) || pid <= 0) {
        console.warn("[kill] Invalid pid:", pidStr);
        return;
      }
      if (!state.selectedAgentId) {
        console.warn("[kill] No agent selected");
        return;
      }

      if (window.confirm(`Kill process "${name || pid}" (PID ${pid})?`)) {
        ws.send({
          event: "ui_run_once",
          data: {
            agent_id: state.selectedAgentId,
            name: "process_v1.0.0.kill",
            args: { pid, name },
          },
        });
        // Visually mark the button as pending
        btn.textContent = "Killing…";
        btn.disabled = true;
        btn.style.opacity = "0.5";
      }
    });
  }
}

wireUiEvents();
ws.connect();
clockTick();
metricTick();
window.setInterval(clockTick, 1000);
window.setInterval(metricTick, 1500);
