// tickets.js
import { AGENT_ID } from './config.js';

const TICKETS_API = `http://localhost:8000/api/tickets/${AGENT_ID}/latest`;

let currentFilter = 'all';
let allTickets    = [];

/* ─── Helpers ────────────────────────────────────────────── */

function timeAgo(isoString) {
    if (!isoString) return '--';
    const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
    if (diff <  60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function severityClass(s = '') {
    const v = s.toLowerCase();
    if (v === 'critical') return 'critical';
    if (v === 'warning')  return 'warning';
    return 'info';
}

/* ─── Render ─────────────────────────────────────────────── */

function renderTickets(tickets) {
    const list   = document.getElementById('ticketList');
    const empty  = document.getElementById('ticketsEmpty');
    if (!list || !empty) return;

    list.innerHTML = '';

    const visible = currentFilter === 'all'
        ? tickets
        : tickets.filter(t => t.status === currentFilter);

    if (visible.length === 0) {
        empty.classList.remove('hidden');
        list.style.display = 'none';
    } else {
        empty.classList.add('hidden');
        list.style.display = '';

        visible.forEach((ticket, idx) => {
            const sc    = severityClass(ticket.severity);
            const isCrit = sc === 'critical';
            const row   = document.createElement('div');

            row.className = `ticket-row ${isCrit ? 'critical-pulse' : ''}`;
            row.style.animationDelay = `${idx * 40}ms`;

            row.innerHTML = `
                <div class="ticket-severity-strip ${sc}"></div>
                <div class="ticket-content">
                    <div class="ticket-message">${ticket.message ?? '(no message)'}</div>
                    <div class="ticket-meta">
                        <span class="ticket-metric">${ticket.metric_name ?? ''}</span>
                        ${ticket.detector ? `<span class="ticket-detector">· ${ticket.detector}</span>` : ''}
                    </div>
                </div>
                <span class="ticket-severity-pill ${sc}">${ticket.severity ?? 'info'}</span>
                <div class="ticket-right">
                    <span class="ticket-status ${(ticket.status ?? 'open').toLowerCase()}">${ticket.status ?? 'open'}</span>
                    <span class="ticket-time">${timeAgo(ticket.created_at)}</span>
                </div>
            `;

            list.appendChild(row);
        });
    }

    // Update open-ticket badge
    const openCount = tickets.filter(t => t.status === 'open').length;
    const badge     = document.getElementById('ticketOpenCount');
    if (badge) {
        badge.textContent = openCount === 0 ? '0 open' : `${openCount} open`;
        badge.classList.toggle('none', openCount === 0);
    }
}

/* ─── Fetch ──────────────────────────────────────────────── */

export async function updateTickets() {
    try {
        const res = await fetch(`${TICKETS_API}?limit=20`);
        if (!res.ok) {
            console.warn('Failed to fetch tickets:', res.status);
            return;
        }

        const data  = await res.json();
        allTickets  = data.tickets ?? [];
        renderTickets(allTickets);

    } catch (err) {
        console.error('Ticket fetch error:', err);
    }
}

/* ─── Filter buttons ─────────────────────────────────────── */

export function initTicketFilters() {
    document.querySelectorAll('.ticket-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.ticket-filter-btn')
                    .forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            renderTickets(allTickets);
        });
    });
}