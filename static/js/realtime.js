/**
 * Real-time Monitoring Dashboard JavaScript
 * Handles server connection, WebSocket streaming, metric cards, Chart.js charts, and alerts
 */

class RealtimeMonitor {
    constructor() {
        this.websocket = null;
        this.metrics = {};
        this.chartInstances = {};
        this.alerts = [];
        this.isConnected = false;
        this.isMonitoring = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        // XSS prevention
        this._esc = (s) => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };
        this.reconnectDelay = 5000;
        this._authToken = sessionStorage.getItem('auth_token') || '';
        this._pollTimer = null;
        this._chartUpdateTimer = null;
        this._connecting = false;

        this.init();
    }

    _headers(json = true) {
        const h = {};
        if (json) h['Content-Type'] = 'application/json';
        if (this._authToken) h['Authorization'] = `Bearer ${this._authToken}`;
        return h;
    }

    init() {
        this.setupEventListeners();
        this.initCharts();
        this._fetchInitialMetrics();
        // F9: Auto-fill connection fields from technician dashboard handoff
        this._loadHandoffConnection();
    }

    // F9: Pre-fill connection from technician dashboard
    _loadHandoffConnection() {
        try {
            const raw = sessionStorage.getItem('activeServerConnection');
            if (!raw) return;
            const conn = JSON.parse(raw);
            const hostEl = document.getElementById('monitorHost');
            const userEl = document.getElementById('monitorUser');
            if (hostEl && !hostEl.value && conn.host) hostEl.value = conn.host;
            if (userEl && !userEl.value && conn.username) userEl.value = conn.username;
        } catch (_) { /* ignore */ }
    }

    setupEventListeners() {
        document.getElementById('connect-btn')?.addEventListener('click', () => this.connectWebSocket());
        document.getElementById('disconnect-btn')?.addEventListener('click', () => this.disconnectWebSocket());
        document.getElementById('monitorConnectBtn')?.addEventListener('click', () => connectAndMonitor());
        document.querySelectorAll('.chart-button').forEach(btn => btn.addEventListener('click', (e) => this.handleChartControl(e.target)));
        document.getElementById('auto-refresh')?.addEventListener('change', (e) => this.toggleAutoRefresh(e.target.checked));
        document.getElementById('clear-alerts')?.addEventListener('click', () => this.clearAlerts());
        document.getElementById('export-data')?.addEventListener('click', () => this.exportMetricsData());
    }

    // ─── Connection ──────────────────────────────────────
    connectWebSocket() {
        if (this._connecting) return;
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) return;
        this._connecting = true;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = this._authToken;
        const wsUrl = `${protocol}//${window.location.host}/ws/monitoring${token ? '?token=' + token : ''}`;

        try {
            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                this._connecting = false;
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus(true);
                this.showNotification('WebSocket connected — receiving live metrics', 'success');
                this._stopPolling();
                this._startChartUpdates();
            };

            this.websocket.onmessage = (event) => this.handleMessage(event);

            this.websocket.onclose = () => {
                this._connecting = false;
                this.isConnected = false;
                this.updateConnectionStatus(false);
                this._stopChartUpdates();
                this.attemptReconnect();
            };

            this.websocket.onerror = () => {
                this._connecting = false;
                this.showNotification('WebSocket error — falling back to polling', 'warning');
            };

            // Timeout: if WS doesn't connect in 8s, show fallback message
            setTimeout(() => {
                if (this._connecting && !this.isConnected) {
                    this._connecting = false;
                    this.showNotification('Live connection unavailable — using periodic refresh instead', 'warning');
                    this.updateConnectionStatus(false, 'polling');
                }
            }, 8000);
        } catch (error) {
            this._connecting = false;
            this.showNotification('Failed to connect WebSocket', 'error');
        }
    }

    disconnectWebSocket() {
        if (this.websocket) { this.websocket.close(); this.websocket = null; }
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this._connecting = false;
        this._stopPolling();
        this._stopChartUpdates();
        this.updateConnectionStatus(false);
        this.showNotification('Disconnected', 'info');
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => this.connectWebSocket(), this.reconnectDelay);
        } else {
            this.showNotification('WebSocket unavailable — polling every 10s', 'info');
            this._startPolling();
        }
    }

    // ─── Polling fallback ────────────────────────────────
    _startPolling() {
        if (this._pollTimer) return;
        const poll = async () => {
            try {
                const r = await fetch('/monitoring/metrics', { headers: this._headers(false) });
                if (r.ok) {
                    const d = await r.json();
                    const m = d.data?.metrics || d.metrics || {};
                    if (Object.keys(m).length) this.updateMetrics(m);
                }
            } catch (e) { /* silent */ }
        };
        poll();
        this._pollTimer = setInterval(poll, 10000);
    }

    _stopPolling() {
        if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
    }

    async _fetchInitialMetrics() {
        try {
            // Check if server is already connected
            const statusR = await fetch('/api/server/quick-status', { headers: this._headers(false) });
            if (!statusR.ok) return;
            const statusData = await statusR.json();
            const sd = statusData.data || statusData;
            
            if (sd.connected === true) {
                // Server is already connected — update connection bar
                const hostInput = document.getElementById('monitorHost');
                const bar = document.getElementById('connectionBar');
                if (hostInput && sd.host) hostInput.value = sd.host;
                if (bar) bar.style.display = 'none'; // Hide connection form
                this.updateConnectionStatus(true);
                this.showNotification(`Connected to ${sd.model || sd.host || 'server'}`, 'success');
            }
            
            // Check if monitoring is already running
            const r = await fetch('/monitoring/metrics', { headers: this._headers(false) });
            if (r.ok) {
                const d = await r.json();
                const m = d.data?.metrics || {};
                this.isMonitoring = d.data?.monitoring_active || false;
                if (Object.keys(m).length && Object.values(m).some(v => v.current_value > 0)) {
                    this.updateMetrics(m);
                    this.showNotification('Live metrics loaded', 'success');
                    this._startPolling();
                    this._startChartUpdates();
                } else if (sd.connected === true && !this.isMonitoring) {
                    // Connected but monitoring not started — start it
                    try {
                        await fetch('/monitoring/start', { method: 'POST', headers: this._headers() });
                        this.showNotification('Monitoring auto-started', 'success');
                        this._startPolling();
                    } catch (e) { /* silent */ }
                }
            }
        } catch (e) { /* silent on startup */ }
    }

    // ─── Message handling ────────────────────────────────
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'metrics_update' && data.metrics) {
                this.updateMetrics(data.metrics);
            } else if (data.type === 'alert') {
                this.addAlert(data);
            }
        } catch (e) { /* ignore parse errors */ }
    }

    updateMetrics(metricsData) {
        this.metrics = metricsData;
        Object.entries(metricsData).forEach(([name, data]) => this.updateMetricCard(name, data));
        this.checkForAlerts(metricsData);
    }

    // ─── Metric cards ────────────────────────────────────
    updateMetricCard(metricName, m) {
        const card = document.querySelector(`[data-metric="${metricName}"]`);
        if (!card) return;

        // Set status on card element for CSS border coloring
        card.setAttribute('data-status', m.current_status || 'normal');

        const valEl = card.querySelector('.metric-value .value');
        if (valEl) valEl.textContent = (typeof m.current_value === 'number') ? m.current_value.toFixed(1) : '--';

        const statusEl = card.querySelector('.metric-status');
        if (statusEl) {
            statusEl.className = `metric-status ${m.current_status || 'normal'}`;
            statusEl.textContent = (m.current_status || 'normal').charAt(0).toUpperCase() + (m.current_status || 'normal').slice(1);
        }

        const trendEl = card.querySelector('.trend-indicator');
        const trendText = card.querySelector('.trend-text');
        if (trendEl && trendText) {
            const icons = { increasing: '↑', decreasing: '↓', stable: '→' };
            trendEl.className = `trend-indicator ${m.trend || 'stable'}`;
            trendEl.textContent = icons[m.trend] || '→';
            trendText.textContent = (m.trend || 'stable').charAt(0).toUpperCase() + (m.trend || 'stable').slice(1);
        }

        const avg = card.querySelector('.stat-avg');
        const max = card.querySelector('.stat-max');
        const min = card.querySelector('.stat-min');
        if (avg) avg.textContent = m.average_10min?.toFixed(1) || '--';
        if (max) max.textContent = m.max_10min?.toFixed(1) || '--';
        if (min) min.textContent = m.min_10min?.toFixed(1) || '--';
    }

    // ─── Chart.js charts ─────────────────────────────────
    initCharts() {
        const commonOpts = {
            responsive: true, maintainAspectRatio: false, animation: { duration: 400 },
            scales: {
                x: { display: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', maxTicksLimit: 10, font: { size: 10 } } },
                y: { display: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { size: 10 } }, beginAtZero: false }
            },
            plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } } }
        };

        const tempCanvas = document.getElementById('temperature-chart');
        if (tempCanvas) {
            this.chartInstances.temperature = new Chart(tempCanvas, {
                type: 'line',
                data: { labels: [], datasets: [
                    { label: 'Inlet Temp (°C)', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', tension: 0.3, fill: true },
                    { label: 'CPU Temp (°C)', data: [], borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', tension: 0.3, fill: true }
                ]},
                options: { ...commonOpts, scales: { ...commonOpts.scales, y: { ...commonOpts.scales.y, suggestedMin: 20, suggestedMax: 100 } } }
            });
        }

        const powerCanvas = document.getElementById('power-chart');
        if (powerCanvas) {
            this.chartInstances.power = new Chart(powerCanvas, {
                type: 'line',
                data: { labels: [], datasets: [
                    { label: 'Power (W)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', tension: 0.3, fill: true, yAxisID: 'y' },
                    { label: 'Efficiency (%)', data: [], borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,0.1)', tension: 0.3, fill: true, yAxisID: 'y1' }
                ]},
                options: {
                    ...commonOpts,
                    scales: {
                        ...commonOpts.scales,
                        y: { ...commonOpts.scales.y, position: 'left', title: { display: true, text: 'Watts', color: '#94a3b8' } },
                        y1: { display: true, position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#94a3b8' }, min: 0, max: 100, title: { display: true, text: '%', color: '#94a3b8' } }
                    }
                }
            });
        }

        const healthCanvas = document.getElementById('health-chart');
        if (healthCanvas) {
            this.chartInstances.health = new Chart(healthCanvas, {
                type: 'line',
                data: { labels: [], datasets: [
                    { label: 'Overall Health (%)', data: [], borderColor: '#a855f7', backgroundColor: 'rgba(168,85,247,0.15)', tension: 0.3, fill: true }
                ]},
                options: { ...commonOpts, scales: { ...commonOpts.scales, y: { ...commonOpts.scales.y, min: 0, max: 100 } } }
            });
        }
    }

    _pushChartPoint() {
        const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const maxPoints = 30;

        const pushTo = (chart, values) => {
            if (!chart) return;
            chart.data.labels.push(now);
            values.forEach((v, i) => chart.data.datasets[i]?.data.push(v));
            if (chart.data.labels.length > maxPoints) {
                chart.data.labels.shift();
                chart.data.datasets.forEach(ds => ds.data.shift());
            }
            chart.update('none');
        };

        pushTo(this.chartInstances.temperature, [
            this.metrics.inlet_temp?.current_value ?? null,
            this.metrics.cpu_temp?.current_value ?? null
        ]);
        pushTo(this.chartInstances.power, [
            this.metrics.power_consumption?.current_value ?? null,
            this.metrics.power_efficiency?.current_value ?? null
        ]);
        pushTo(this.chartInstances.health, [
            this.metrics.overall_health?.current_value ?? null
        ]);
    }

    _startChartUpdates() {
        this._stopChartUpdates();
        this._chartUpdateTimer = setInterval(() => this._pushChartPoint(), 5000);
    }

    _stopChartUpdates() {
        if (this._chartUpdateTimer) { clearInterval(this._chartUpdateTimer); this._chartUpdateTimer = null; }
    }

    // ─── Alerts ──────────────────────────────────────────
    checkForAlerts(metricsData) {
        Object.entries(metricsData).forEach(([name, m]) => {
            if (m.current_status === 'critical' || m.current_status === 'warning') {
                this.addAlert({
                    type: m.current_status,
                    metric: name,
                    message: `${m.description || name} is ${m.current_status}: ${typeof m.current_value === 'number' ? m.current_value.toFixed(1) : '?'}${m.unit || ''}`,
                    timestamp: new Date().toISOString()
                });
            }
        });
    }

    addAlert(alert) {
        // Deduplicate by metric + type (not message, which contains changing values)
        const exists = this.alerts.some(a => a.metric === alert.metric && a.type === alert.type);
        if (!exists) {
            this.alerts.unshift(alert);
            if (this.alerts.length > 50) this.alerts = this.alerts.slice(0, 50);
            this.updateAlertsPanel();
            if (alert.type === 'critical') this.showNotification(alert.message, 'error');
        }
    }

    updateAlertsPanel() {
        const list = document.getElementById('alerts-list');
        if (!list) return;

        if (this.alerts.length === 0) {
            list.innerHTML = '<div class="no-alerts">No active alerts</div>';
        } else {
            list.innerHTML = this.alerts.map(a => `
                <div class="alert-item ${this._esc(a.type)}">
                    <div class="alert-icon ${this._esc(a.type)}">${a.type === 'critical' ? '🔴' : '🟡'}</div>
                    <div class="alert-content">
                        <div class="alert-metric">${this._esc(a.metric)}</div>
                        <div class="alert-message">${this._esc(a.message)}</div>
                        <div class="alert-time">${new Date(a.timestamp).toLocaleTimeString()}</div>
                    </div>
                </div>
            `).join('');
        }

        const count = document.getElementById('alerts-count');
        if (count) count.textContent = this.alerts.length;
    }

    clearAlerts() {
        this.alerts = [];
        this.updateAlertsPanel();
        this.showNotification('Alerts cleared', 'info');
    }

    // ─── UI updates ──────────────────────────────────────
    updateConnectionStatus(connected) {
        const dot = document.getElementById('connection-dot');
        const text = document.getElementById('connection-text');
        if (dot) dot.className = `connection-dot ${connected ? 'connected' : 'disconnected'}`;
        if (text) text.textContent = connected ? 'Connected' : 'Disconnected';

        const connBtn = document.getElementById('connect-btn');
        const discBtn = document.getElementById('disconnect-btn');
        if (connBtn) connBtn.disabled = connected;
        if (discBtn) discBtn.disabled = !connected;
    }

    handleChartControl(button) {
        const action = button.dataset.action;
        const chartName = button.dataset.chart;
        switch (action) {
            case 'refresh':
                this._pushChartPoint();
                this.showNotification(`${chartName} chart refreshed`, 'success');
                break;
            case 'export':
                this.exportChartData(chartName);
                break;
            case 'fullscreen':
                this.toggleChartFullscreen(chartName);
                break;
        }
    }

    toggleAutoRefresh(enabled) {
        if (enabled) { this._startChartUpdates(); this.showNotification('Auto-refresh on', 'success'); }
        else { this._stopChartUpdates(); this.showNotification('Auto-refresh off', 'info'); }
    }

    // ─── Export ──────────────────────────────────────────
    exportMetricsData() {
        const data = { timestamp: new Date().toISOString(), metrics: this.metrics, alerts: this.alerts };
        this._downloadJson(data, `server-metrics-${new Date().toISOString().split('T')[0]}.json`);
        this.showNotification('Metrics exported', 'success');
    }

    exportChartData(chartName) {
        const chart = this.chartInstances[chartName];
        if (!chart) return;
        const data = { chart: chartName, labels: chart.data.labels, datasets: chart.data.datasets.map(ds => ({ label: ds.label, data: ds.data })) };
        this._downloadJson(data, `${chartName}-${new Date().toISOString().split('T')[0]}.json`);
        this.showNotification(`${chartName} data exported`, 'success');
    }

    _downloadJson(data, filename) {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = filename;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    toggleChartFullscreen(chartName) {
        const el = document.querySelector(`[data-chart="${chartName}"]`);
        if (!el) return;
        if (!document.fullscreenElement) el.requestFullscreen().catch(() => {});
        else document.exitFullscreen();
    }

    // ─── Notifications ───────────────────────────────────
    showNotification(message, type = 'info') {
        const n = document.createElement('div');
        n.className = `notification ${type}`;
        n.textContent = message;
        document.body.appendChild(n);
        requestAnimationFrame(() => n.classList.add('show'));
        setTimeout(() => { n.classList.remove('show'); setTimeout(() => n.remove(), 300); }, 4000);
    }

    isWebSocketConnected() { return this.isConnected; }
}

// ─── Initialize ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    window.realtimeMonitor = new RealtimeMonitor();
});

// ─── Connect & Monitor button handler ────────────────
async function connectAndMonitor() {
    const host = document.getElementById('monitorHost')?.value?.trim();
    const user = document.getElementById('monitorUser')?.value?.trim();
    const pass = document.getElementById('monitorPass')?.value;
    const port = parseInt(document.getElementById('monitorPort')?.value) || 443;

    if (!host || !user || !pass) {
        window.realtimeMonitor?.showNotification('Host, username, and password are required', 'error');
        return;
    }

    const btn = document.getElementById('monitorConnectBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Connecting...'; }

    const token = sessionStorage.getItem('auth_token') || '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
        // Step 1: Connect to server
        const r = await fetch('/api/connect', { method: 'POST', headers, body: JSON.stringify({ host, username: user, password: pass, port }) });
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            throw new Error(err.detail || `Connection failed (${r.status})`);
        }

        // Step 2: Start monitoring
        const r2 = await fetch('/monitoring/start', { method: 'POST', headers });
        if (!r2.ok) {
            const err = await r2.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to start monitoring');
        }

        if (btn) { btn.textContent = 'Connected'; btn.style.background = '#22c55e'; }
        window.realtimeMonitor?.showNotification(`Connected to ${host} — monitoring started`, 'success');
        window.realtimeMonitor?.updateConnectionStatus(true);

        // Hide connection form after successful connect
        const bar = document.getElementById('connectionBar');
        if (bar) bar.style.display = 'none';

        // Step 3: Connect WebSocket for live updates
        window.realtimeMonitor?.connectWebSocket();

    } catch (e) {
        window.realtimeMonitor?.showNotification(e.message, 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Connect & Monitor'; btn.style.background = ''; }
    }
}

// Cleanup
window.addEventListener('beforeunload', () => {
    if (window.realtimeMonitor) {
        window.realtimeMonitor.disconnectWebSocket();
        window.realtimeMonitor._stopPolling();
    }
});
