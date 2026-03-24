// dashboard.js

import { API_URL } from './config.js';
import { state } from './script.js';
import {
    createRingChart,
    updateCPUChart,
    updateMemoryStack,
    updateNetworkChart
} from './chart.js';
import { getStatusColor } from './utils.js';

/* ============================
   Last Updated
============================ */
export function updateLastUpdated() {
    const now = new Date();
    const formatted = now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const elem = document.getElementById('lastUpdated');
    if (elem) elem.textContent = formatted;

    state.lastUpdate = now;
}


/* ============================
   Main Dashboard Update
============================ */
export async function updateDashboard() {

    try {
        const response = await fetch(API_URL);

        if (!response.ok) {
            console.warn("Failed to fetch latest snapshot");
            return;
        }

        const data = await response.json();
        console.log("Latest snapshot:", data);

        /* ======================================
           CPU
        ====================================== */

        const cpu = data.cpu_usage_percent ?? 0;

        createRingChart('cpuRing', cpu);
        updateCPUChart(cpu);

        const cpuValueElem = document.getElementById('cpuValue');
        if (cpuValueElem)
            cpuValueElem.textContent = cpu.toFixed(1);

        // Per-core bars
        if (data.cpu_per_core) {
            Object.entries(data.cpu_per_core).forEach(([core, value]) => {

                const coreElem = document.getElementById(`core${core}`);
                if (!coreElem) return;

                const fill = coreElem.querySelector('.bar-fill');
                const label = coreElem.querySelector('.bar-value');

                if (fill) {
                    fill.style.width = `${value}%`;
                    fill.style.backgroundColor =
                        getStatusColor(value, 70, 85);
                }

                if (label)
                    label.textContent = `${value.toFixed(0)}%`;
            });
        }

        // Load Average
        if (data.cpu_load_avg) {
            const loadElem = document.getElementById("loadAvg");
            if (loadElem) {
                loadElem.textContent =
                    `${data.cpu_load_avg["1m"]} ${data.cpu_load_avg["5m"]} ${data.cpu_load_avg["15m"]}`;
            }
        }

        // Frequency
        if (data.cpu_frequency) {
            const freqElem = document.getElementById("cpuFreq");
            if (freqElem) {
                freqElem.textContent =
                    `${(data.cpu_frequency.current / 1000).toFixed(2)} GHz`;
            }
        }

        /* ======================================
           MEMORY
        ====================================== */

        const memPercent = data.memory_percent ?? 0;

        createRingChart('memoryRing', memPercent);

        const memValueElem = document.getElementById('memoryValue');
        if (memValueElem)
            memValueElem.textContent = memPercent.toFixed(1);

        updateMemoryStack(
            data.memory_used_gb ?? 0,
            data.memory_cached_gb ?? 0,
            data.memory_free_gb ?? 0
        );

        // Detailed memory numbers
        if (document.getElementById("memUsed"))
            document.getElementById("memUsed").textContent =
                ((data.memory_used_gb ?? 0) * 1024).toFixed(0);

        if (document.getElementById("memFree"))
            document.getElementById("memFree").textContent =
                ((data.memory_free_gb ?? 0) * 1024).toFixed(0);

        if (document.getElementById("memCached"))
            document.getElementById("memCached").textContent =
                ((data.memory_cached_gb ?? 0) * 1024).toFixed(0);

        // Swap
        const swapFill = document.getElementById("swapFill");
        if (swapFill)
            swapFill.style.width = `${data.swap_percent ?? 0}%`;

        const swapValue = document.getElementById("swapValue");
        if (swapValue)
            swapValue.textContent =
                `${((data.swap_used_gb ?? 0) * 1024).toFixed(0)} / ${((data.swap_total_gb ?? 0) * 1024).toFixed(0)} MB`;

        /* ======================================
           DISK
        ====================================== */

        const diskPercent = data.disk_percent ?? 0;

        createRingChart('diskRing', diskPercent);

        const diskValueElem = document.getElementById('diskValue');
        if (diskValueElem)
            diskValueElem.textContent = diskPercent.toFixed(1);

        if (document.getElementById("diskTotal"))
            document.getElementById("diskTotal").textContent =
                data.disk_total_gb?.toFixed(1) ?? 0;

        if (document.getElementById("diskUsed"))
            document.getElementById("diskUsed").textContent =
                data.disk_used_gb?.toFixed(1) ?? 0;

        if (document.getElementById("diskFree"))
            document.getElementById("diskFree").textContent =
                data.disk_free_gb?.toFixed(1) ?? 0;

        const diskFill = document.getElementById("diskFill");
        if (diskFill)
            diskFill.style.width = `${diskPercent}%`;

        const readElem = document.getElementById('diskRead');
        const writeElem = document.getElementById('diskWrite');

        if (readElem)
            readElem.textContent =
                `${(data.disk_read_mb_s ?? 0).toFixed(1)} MB/s`;

        if (writeElem)
            writeElem.textContent =
                `${(data.disk_write_mb_s ?? 0).toFixed(1)} MB/s`;

        /* ======================================
           NETWORK
        ====================================== */

        const network = data.network_total_mbps ?? 0;

        const netElem = document.getElementById('networkValue');
        if (netElem)
            netElem.textContent = network.toFixed(1);

        updateNetworkChart(0, network);

        if (document.getElementById("activeConn"))
            document.getElementById("activeConn").textContent =
                data.network_active_connections ?? 0;

        if (document.getElementById("errorCount"))
            document.getElementById("errorCount").textContent =
                data.network_total_errors ?? 0;

        /* ======================================
           PROCESSES
        ====================================== */

        if (data.top_cpu_process) {
            const p = data.top_cpu_process;

            const name = document.getElementById('topCpuName');
            const usage = document.getElementById('topCpuUsage');

            if (name) name.textContent = p.name ?? '-';
            if (usage)
                usage.textContent =
                    `${(p.cpu_percent ?? 0).toFixed(1)}%`;
        }

        if (data.top_memory_process) {
            const p = data.top_memory_process;

            const name = document.getElementById('topMemName');
            const usage = document.getElementById('topMemUsage');

            if (name) name.textContent = p.name ?? '-';
            if (usage)
                usage.textContent =
                    `${(p.memory_percent ?? 0).toFixed(1)}%`;
        }

        if (document.getElementById("totalThreads"))
            document.getElementById("totalThreads").textContent =
                data.total_threads ?? 0;

        if (document.getElementById("zombieCount"))
            document.getElementById("zombieCount").textContent =
                data.zombie_count ?? 0;

        /* ====================================== */

        updateLastUpdated();

    } catch (err) {
        console.error("Dashboard update error:", err);
    }
}
