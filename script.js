// main.js
import { CONFIG } from './config.js';
import { initCPUChart, initMemoryStack, initNetworkChart } from './chart.js';
import { updateDashboard } from './dashboard.js';
import { updateTickets, initTicketFilters } from './tickets.js';

const TICKET_POLL_INTERVAL = 15_000; // refresh tickets every 15 s

function init() {
    initCPUChart();
    initMemoryStack();
    initNetworkChart();
    initTicketFilters();

    updateDashboard();
    updateTickets();

    setInterval(updateDashboard, CONFIG.UPDATE_INTERVAL);
    setInterval(updateTickets,   TICKET_POLL_INTERVAL);
}

document.addEventListener('DOMContentLoaded', init);