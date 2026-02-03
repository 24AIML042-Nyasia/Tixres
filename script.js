
let serverUrl = 'http://localhost:8000';
let agents = [];

function showError(elementId, message) {
    const element = document.getElementById(elementId);
    element.textContent = message;
    element.style.display = 'block';
    setTimeout(() => {
        element.style.display = 'none';
    }, 5000);
}

function updateServerUrl() {
    const input = document.getElementById('serverUrl');
    serverUrl = input.value.trim().replace(/\/$/, '');
    localStorage.setItem('serverUrl', serverUrl);
    loadDashboard();
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Load tab content
    if (tabName === 'agents') loadAgents();
    else if (tabName === 'numeric') loadNumericMetrics();
    else if (tabName === 'json') loadJsonMetrics();
}

async function loadDashboard() {
    try {
        // Load summary
        const response = await fetch(`${serverUrl}/api/ui/metrics/summary`);
        if (!response.ok) throw new Error('Failed to connect to server');
        
        const data = await response.json();
        
        // Update stats
        document.getElementById('totalAgents').textContent = data.agents.total;
        document.getElementById('activeAgents').textContent = data.agents.active;
        document.getElementById('totalMetrics').textContent = data.metrics.total.toLocaleString();
        document.getElementById('metricsLastHour').textContent = data.metrics.last_hour.toLocaleString();
        document.getElementById('numericMetrics').textContent = data.metrics.numeric.toLocaleString();
        document.getElementById('jsonMetrics').textContent = data.metrics.json.toLocaleString();
        
        // Show dashboard
        document.getElementById('statsSection').style.display = 'grid';
        document.getElementById('tabsSection').style.display = 'block';
        
        // Load initial data
        loadAgents();
        
    } catch (error) {
        showError('configError', `Error: ${error.message}`);
    }
}

async function loadAgents() {
    const container = document.getElementById('agentsContent');
    container.innerHTML = '<div class="loading">Loading agents...</div>';

    try {
        const response = await fetch(`${serverUrl}/api/ui/agents`);
        if (!response.ok) throw new Error('Failed to load agents');
        
        agents = await response.json();
        
        if (agents.length === 0) {
            container.innerHTML = '<p style="text-align: center; padding: 2rem; color: #999;">No agents registered</p>';
            return;
        }
        
        // Update agent filters
        updateAgentFilters();
        
        // Render agents
        container.innerHTML = agents.map(agent => {
            const lastHeartbeat = agent.heartbeat ? new Date(agent.heartbeat) : null;
            const now = new Date();
            const isActive = lastHeartbeat && (now - lastHeartbeat) < 5 * 60 * 1000;
            
            return `
                <div class="agent-card">
                    <div class="agent-info">
                        <h3>${agent.hostname}</h3>
                        <p><strong>Agent ID:</strong> ${agent.agent_id}</p>
                        <p><strong>OS:</strong> ${agent.os} | <strong>Version:</strong> ${agent.agent_version}</p>
                        <p><strong>Created:</strong> ${new Date(agent.created_at).toLocaleString()}</p>
                        <p><strong>Last Heartbeat:</strong> ${lastHeartbeat ? lastHeartbeat.toLocaleString() : 'Never'}</p>
                    </div>
                    <div class="agent-status ${isActive ? 'active' : 'inactive'}">
                        ${isActive ? 'Active' : 'Inactive'}
                    </div>
                </div>
            `;
        }).join('');
        
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading agents: ${error.message}</div>`;
    }
}

function updateAgentFilters() {
    const numericFilter = document.getElementById('numericAgentFilter');
    const jsonFilter = document.getElementById('jsonAgentFilter');
    
    const options = agents.map(agent => 
        `<option value="${agent.agent_id}">${agent.hostname} (${agent.agent_id})</option>`
    ).join('');
    
    numericFilter.innerHTML = '<option value="">All Agents</option>' + options;
    jsonFilter.innerHTML = '<option value="">All Agents</option>' + options;
}

async function loadNumericMetrics() {
    const container = document.getElementById('numericContent');
    container.innerHTML = '<div class="loading">Loading numeric metrics...</div>';

    try {
        const agentId = document.getElementById('numericAgentFilter').value;
        const metricName = document.getElementById('numericMetricFilter').value;
        const limit = document.getElementById('numericLimit').value || 100;
        
        let url = `${serverUrl}/api/metrics/numeric?limit=${limit}`;
        if (agentId) url += `&agent_id=${agentId}`;
        if (metricName) url += `&metric_name=${metricName}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load metrics');
        
        const data = await response.json();
        
        if (data.metrics.length === 0) {
            container.innerHTML = '<p style="text-align: center; padding: 2rem; color: #999;">No metrics found</p>';
            return;
        }
        
        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Agent ID</th>
                        <th>Metric Name</th>
                        <th>Value</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.metrics.map(metric => `
                        <tr>
                            <td>${new Date(metric.timestamp).toLocaleString()}</td>
                            <td>${metric.agent_id}</td>
                            <td>${metric.metric_name}</td>
                            <td>${metric.value}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading metrics: ${error.message}</div>`;
    }
}

async function loadJsonMetrics() {
    const container = document.getElementById('jsonContent');
    container.innerHTML = '<div class="loading">Loading JSON metrics...</div>';

    try {
        const agentId = document.getElementById('jsonAgentFilter').value;
        const metricName = document.getElementById('jsonMetricFilter').value;
        const limit = document.getElementById('jsonLimit').value || 100;
        
        let url = `${serverUrl}/api/metrics/json?limit=${limit}`;
        if (agentId) url += `&agent_id=${agentId}`;
        if (metricName) url += `&metric_name=${metricName}`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load metrics');
        
        const data = await response.json();
        
        if (data.metrics.length === 0) {
            container.innerHTML = '<p style="text-align: center; padding: 2rem; color: #999;">No metrics found</p>';
            return;
        }
        
        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Agent ID</th>
                        <th>Metric Name</th>
                        <th>Value</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.metrics.map(metric => `
                        <tr>
                            <td>${new Date(metric.timestamp).toLocaleString()}</td>
                            <td>${metric.agent_id}</td>
                            <td>${metric.metric_name}</td>
                            <td class="json-value" title="${JSON.stringify(metric.value, null, 2)}">
                                ${JSON.stringify(metric.value)}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
    } catch (error) {
        container.innerHTML = `<div class="error">Error loading metrics: ${error.message}</div>`;
    }
}

// Initialize
window.addEventListener('load', () => {
    const savedUrl = localStorage.getItem('serverUrl');
    if (savedUrl) {
        document.getElementById('serverUrl').value = savedUrl;
        serverUrl = savedUrl;
        loadDashboard();
    }
});
