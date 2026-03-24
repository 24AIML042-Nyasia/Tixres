// charts.js
import { state } from './script.js';
import { getStatusColor } from './utils.js';

/* ---------------- RING ---------------- */
export function createRingChart(canvasId, value, maxValue = 100) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 45;
    const lineWidth = 12;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = lineWidth;
    ctx.stroke();

    const startAngle = -Math.PI / 2;
    const endAngle = startAngle + (2 * Math.PI * (value / maxValue));

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, endAngle);
    ctx.strokeStyle = getStatusColor(value, 70, 85);
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.stroke();
}

/* ---------------- CPU LINE ---------------- */
export function initCPUChart() {
    const canvas = document.getElementById('cpuChart');
    if (!canvas) return;
    state.charts.cpu.ctx = canvas.getContext('2d');
}

export function updateCPUChart(value) {
    const chart = state.charts.cpu;
    if (!chart.ctx) return;

    chart.data.push(value);
    if (chart.data.length > chart.maxPoints) chart.data.shift();

    const canvas = chart.ctx.canvas;
    const ctx = chart.ctx;
    const w = canvas.width;
    const h = canvas.height;

    const pad = 20;
    const cw = w - pad * 2;
    const ch = h - pad * 2;

    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = '#374151';
    for (let i = 0; i <= 4; i++) {
        const y = pad + (ch / 4) * i;
        ctx.beginPath();
        ctx.moveTo(pad, y);
        ctx.lineTo(w - pad, y);
        ctx.stroke();
    }

    if (chart.data.length > 1) {
        ctx.beginPath();
        ctx.strokeStyle = '#4ade80';
        ctx.lineWidth = 2;

        const spacing = cw / (chart.maxPoints - 1);
        const offset = chart.maxPoints - chart.data.length;

        chart.data.forEach((v, i) => {
            const x = pad + ((offset + i) * spacing);
            const y = pad + ch - (v / 100 * ch);
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });

        ctx.stroke();
    }
}

/* ---------------- MEMORY STACK ---------------- */
export function initMemoryStack() {
    const canvas = document.getElementById('memoryStack');
    if (!canvas) return;
    state.charts.memoryStack.ctx = canvas.getContext('2d');
}

export function updateMemoryStack(used, cached, free) {
    const chart = state.charts.memoryStack;
    if (!chart.ctx) return;

    const ctx = chart.ctx;
    const canvas = ctx.canvas;

    const total = used + cached + free;
    if (!total) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const usedW = (used / total) * canvas.width;
    const cachedW = (cached / total) * canvas.width;
    const freeW = (free / total) * canvas.width;

    let x = 0;
    ctx.fillStyle = '#4ade80';
    ctx.fillRect(x, 0, usedW, canvas.height);
    x += usedW;

    ctx.fillStyle = '#60a5fa';
    ctx.fillRect(x, 0, cachedW, canvas.height);
    x += cachedW;

    ctx.fillStyle = '#374151';
    ctx.fillRect(x, 0, freeW, canvas.height);
}

/* ---------------- NETWORK ---------------- */
export function initNetworkChart() {
    const canvas = document.getElementById('networkChart');
    if (!canvas) return;
    state.charts.network.ctx = canvas.getContext('2d');
}

export function updateNetworkChart(upload, download) {
    const chart = state.charts.network;
    if (!chart.ctx) return;

    chart.uploadData.push(upload);
    chart.downloadData.push(download);

    if (chart.uploadData.length > chart.maxPoints) {
        chart.uploadData.shift();
        chart.downloadData.shift();
    }

    const ctx = chart.ctx;
    const canvas = ctx.canvas;
    const w = canvas.width;
    const h = canvas.height;

    const pad = 20;
    const cw = w - pad * 2;
    const ch = h - pad * 2;

    ctx.clearRect(0, 0, w, h);

    const maxVal = Math.max(
        Math.max(...chart.uploadData, 1),
        Math.max(...chart.downloadData, 1)
    );

    const spacing = cw / (chart.maxPoints - 1);

    function drawLine(data, color) {
        if (data.length < 2) return;
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        const offset = chart.maxPoints - data.length;

        data.forEach((v, i) => {
            const x = pad + ((offset + i) * spacing);
            const y = pad + ch - (v / maxVal * ch);
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
    }

    drawLine(chart.uploadData, '#f59e0b');
    drawLine(chart.downloadData, '#60a5fa');
}
