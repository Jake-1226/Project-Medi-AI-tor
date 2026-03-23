/**
 * Real-time Monitoring Dashboard JavaScript
 * Handles WebSocket connections, metric updates, and chart rendering
 */

class RealtimeMonitor {
    constructor() {
        this.websocket = null;
        this.metrics = {};
        this.charts = {};
        this.alerts = [];
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 5000;
        this._authToken = sessionStorage.getItem('auth_token') || '';
        this._pollTimer = null;
        
        this.init();
    }
    
    /** Get auth headers for fetch calls */
    _headers() {
        const h = {};
        if (this._authToken) h['Authorization'] = `Bearer ${this._authToken}`;
        return h;
    }
    
    init() {
        this.setupEventListeners();
        this.connectWebSocket();
        this.initializeCharts();
        this.startPeriodicUpdates();
    }
    
    setupEventListeners() {
        // Connection controls
        document.getElementById('connect-btn')?.addEventListener('click', () => {
            this.connectWebSocket();
        });
        
        document.getElementById('disconnect-btn')?.addEventListener('click', () => {
            this.disconnectWebSocket();
        });
        
        // Chart controls
        document.querySelectorAll('.chart-button').forEach(button => {
            button.addEventListener('click', (e) => {
                this.handleChartControl(e.target);
            });
        });
        
        // Auto-refresh toggle
        document.getElementById('auto-refresh')?.addEventListener('change', (e) => {
            this.toggleAutoRefresh(e.target.checked);
        });
        
        // Alert controls
        document.getElementById('clear-alerts')?.addEventListener('click', () => {
            this.clearAlerts();
        });
        
        // Export data
        document.getElementById('export-data')?.addEventListener('click', () => {
            this.exportMetricsData();
        });
    }
    
    connectWebSocket() {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            return;
        }
        
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const token = this._authToken;
        const wsUrl = `${protocol}//${window.location.host}/ws/monitoring${token ? '?token=' + token : ''}`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus(true);
                this.showNotification('Connected to real-time monitoring', 'success');
                this._stopPolling();
            };
            
            this.websocket.onmessage = (event) => {
                this.handleWebSocketMessage(event);
            };
            
            this.websocket.onclose = () => {
                this.isConnected = false;
                this.updateConnectionStatus(false);
                this.attemptReconnect();
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.showNotification('WebSocket connection error', 'error');
            };
            
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.showNotification('Failed to connect to monitoring service', 'error');
        }
    }
    
    disconnectWebSocket() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        this.isConnected = false;
        this.updateConnectionStatus(false);
        this.showNotification('Disconnected from monitoring', 'info');
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            
            setTimeout(() => {
                this.connectWebSocket();
            }, this.reconnectDelay);
        } else {
            this.showNotification('WebSocket unavailable — falling back to polling', 'info');
            this._startPolling();
        }
    }
    
    /** Fallback: poll /monitoring/metrics every 10 seconds when WebSocket fails */
    _startPolling() {
        if (this._pollTimer) return;
        this._pollTimer = setInterval(async () => {
            try {
                const r = await fetch('/monitoring/metrics', { headers: this._headers() });
                if (r.ok) {
                    const data = await r.json();
                    const metrics = data.data?.metrics || data.metrics || {};
                    if (Object.keys(metrics).length > 0) {
                        this.updateMetrics(metrics);
                    }
                }
            } catch (e) { /* silent */ }
        }, 10000);
        // Immediate first poll
        fetch('/monitoring/metrics', { headers: this._headers() })
            .then(r => r.json())
            .then(data => { const m = data.data?.metrics || data.metrics || {}; if (Object.keys(m).length) this.updateMetrics(m); })
            .catch(() => {});
    }
    
    _stopPolling() {
        if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
    }
    
    handleWebSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            switch (data.type) {
                case 'metrics_update':
                    this.updateMetrics(data.metrics);
                    break;
                case 'alert':
                    this.addAlert(data);
                    break;
                case 'connection_status':
                    this.updateConnectionStatus(data.connected);
                    break;
                default:
                    break; // Unknown message type
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    }
    
    updateMetrics(metricsData) {
        this.metrics = metricsData;
        
        // Update metric cards
        Object.keys(metricsData).forEach(metricName => {
            this.updateMetricCard(metricName, metricsData[metricName]);
        });
        
        // Update charts
        this.updateCharts();
        
        // Check for alerts
        this.checkForAlerts(metricsData);
    }
    
    updateMetricCard(metricName, metricData) {
        const card = document.querySelector(`[data-metric="${metricName}"]`);
        if (!card) return;
        
        // Update value — target the .value span inside .metric-value
        const valueSpan = card.querySelector('.metric-value .value');
        if (valueSpan) {
            valueSpan.textContent = metricData.current_value != null ? metricData.current_value.toFixed(1) : '--';
        }
        
        // Update status
        const statusElement = card.querySelector('.metric-status');
        if (statusElement) {
            statusElement.className = `metric-status ${metricData.current_status}`;
            statusElement.textContent = metricData.current_status;
        }
        
        // Update trend
        const trendElement = card.querySelector('.trend-indicator');
        const trendTextElement = card.querySelector('.trend-text');
        if (trendElement && trendTextElement) {
            trendElement.className = `trend-indicator ${metricData.trend}`;
            trendTextElement.textContent = metricData.trend;
            
            // Update trend icon
            const trendIcons = {
                increasing: '↑',
                decreasing: '↓',
                stable: '→'
            };
            trendElement.textContent = trendIcons[metricData.trend] || '→';
        }
        
        // Update stats
        const avgElement = card.querySelector('.stat-avg');
        const maxElement = card.querySelector('.stat-max');
        const minElement = card.querySelector('.stat-min');
        
        if (avgElement) avgElement.textContent = metricData.average_10min?.toFixed(1) || '--';
        if (maxElement) maxElement.textContent = metricData.max_10min?.toFixed(1) || '--';
        if (minElement) minElement.textContent = metricData.min_10min?.toFixed(1) || '--';
        
        // Add animation for value changes
        if (valueSpan) {
            valueSpan.style.animation = 'none';
            setTimeout(() => {
                valueSpan.style.animation = 'pulse 0.5s ease';
            }, 10);
        }
    }
    
    initializeCharts() {
        // Initialize temperature chart
        this.initTemperatureChart();
        
        // Initialize power chart
        this.initPowerChart();
        
        // Initialize health chart
        this.initHealthChart();
    }
    
    initTemperatureChart() {
        const canvas = document.getElementById('temperature-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        this.charts.temperature = {
            canvas: canvas,
            ctx: ctx,
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Inlet Temp',
                        data: [],
                        borderColor: '#3498db',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)'
                    },
                    {
                        label: 'CPU Temp',
                        data: [],
                        borderColor: '#e74c3c',
                        backgroundColor: 'rgba(231, 76, 60, 0.1)'
                    }
                ]
            }
        };
        
        this.drawChart(this.charts.temperature);
    }
    
    initPowerChart() {
        const canvas = document.getElementById('power-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        this.charts.power = {
            canvas: canvas,
            ctx: ctx,
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Power Consumption (W)',
                        data: [],
                        borderColor: '#f39c12',
                        backgroundColor: 'rgba(243, 156, 18, 0.1)'
                    },
                    {
                        label: 'Efficiency (%)',
                        data: [],
                        borderColor: '#27ae60',
                        backgroundColor: 'rgba(39, 174, 96, 0.1)'
                    }
                ]
            }
        };
        
        this.drawChart(this.charts.power);
    }
    
    initHealthChart() {
        const canvas = document.getElementById('health-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        this.charts.health = {
            canvas: canvas,
            ctx: ctx,
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Overall Health',
                        data: [],
                        borderColor: '#9b59b6',
                        backgroundColor: 'rgba(155, 89, 182, 0.1)'
                    }
                ]
            }
        };
        
        this.drawChart(this.charts.health);
    }
    
    drawChart(chart) {
        const ctx = chart.ctx;
        const canvas = chart.canvas;
        const data = chart.data;
        
        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Simple line chart implementation
        const padding = 40;
        const chartWidth = canvas.width - 2 * padding;
        const chartHeight = canvas.height - 2 * padding;
        
        // Draw axes
        ctx.strokeStyle = '#bdc3c7';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(padding, padding);
        ctx.lineTo(padding, canvas.height - padding);
        ctx.lineTo(canvas.width - padding, canvas.height - padding);
        ctx.stroke();
        
        // Draw data lines
        data.datasets.forEach((dataset, datasetIndex) => {
            if (dataset.data.length < 2) return;
            
            ctx.strokeStyle = dataset.borderColor;
            ctx.lineWidth = 2;
            ctx.beginPath();
            
            dataset.data.forEach((value, index) => {
                const x = padding + (index / (dataset.data.length - 1)) * chartWidth;
                const y = canvas.height - padding - (value / 100) * chartHeight;
                
                if (index === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            });
            
            ctx.stroke();
        });
        
        // Draw labels
        ctx.fillStyle = '#2c3e50';
        ctx.font = '12px Arial';
        ctx.textAlign = 'center';
        
        // X-axis labels (time)
        const labelInterval = Math.ceil(data.labels.length / 10);
        data.labels.forEach((label, index) => {
            if (index % labelInterval === 0) {
                const x = padding + (index / (data.labels.length - 1)) * chartWidth;
                ctx.fillText(label, x, canvas.height - padding + 20);
            }
        });
    }
    
    updateCharts() {
        // Update chart data and redraw
        Object.keys(this.charts).forEach(chartName => {
            const chart = this.charts[chartName];
            // Update data based on current metrics
            this.updateChartData(chart);
            this.drawChart(chart);
        });
    }
    
    updateChartData(chart) {
        // Add current timestamp
        const now = new Date();
        const timeLabel = now.toLocaleTimeString();
        
        if (!chart.data.labels.includes(timeLabel)) {
            chart.data.labels.push(timeLabel);
            
            // Keep only last 20 data points
            if (chart.data.labels.length > 20) {
                chart.data.labels.shift();
                chart.data.datasets.forEach(dataset => {
                    dataset.data.shift();
                });
            }
        }
        
        // Update dataset values based on chart type
        if (chart === this.charts.temperature) {
            chart.data.datasets[0].data.push(this.metrics.inlet_temp?.current_value || 0);
            chart.data.datasets[1].data.push(this.metrics.cpu_temp?.current_value || 0);
        } else if (chart === this.charts.power) {
            chart.data.datasets[0].data.push(this.metrics.power_consumption?.current_value || 0);
            chart.data.datasets[1].data.push(this.metrics.power_efficiency?.current_value || 0);
        } else if (chart === this.charts.health) {
            chart.data.datasets[0].data.push(this.metrics.overall_health?.current_value || 0);
        }
    }
    
    checkForAlerts(metricsData) {
        const newAlerts = [];
        
        Object.keys(metricsData).forEach(metricName => {
            const metric = metricsData[metricName];
            
            if (metric.current_status === 'critical') {
                newAlerts.push({
                    type: 'critical',
                    metric: metricName,
                    message: `${metric.description} is critical: ${metric.current_value.toFixed(1)}${metric.unit}`,
                    timestamp: new Date().toISOString()
                });
            } else if (metric.current_status === 'warning') {
                newAlerts.push({
                    type: 'warning',
                    metric: metricName,
                    message: `${metric.description} is warning: ${metric.current_value.toFixed(1)}${metric.unit}`,
                    timestamp: new Date().toISOString()
                });
            }
        });
        
        // Add new alerts
        newAlerts.forEach(alert => {
            this.addAlert(alert);
        });
    }
    
    addAlert(alert) {
        // Check if alert already exists (avoid duplicates)
        const exists = this.alerts.some(existing => 
            existing.metric === alert.metric && 
            existing.type === alert.type &&
            existing.message === alert.message
        );
        
        if (!exists) {
            this.alerts.unshift(alert);
            
            // Keep only last 50 alerts
            if (this.alerts.length > 50) {
                this.alerts = this.alerts.slice(0, 50);
            }
            
            this.updateAlertsPanel();
            
            // Show notification for critical alerts
            if (alert.type === 'critical') {
                this.showNotification(alert.message, 'error');
            }
        }
    }
    
    updateAlertsPanel() {
        const alertsList = document.getElementById('alerts-list');
        if (!alertsList) return;
        
        alertsList.innerHTML = '';
        
        this.alerts.forEach(alert => {
            const alertElement = document.createElement('div');
            alertElement.className = `alert-item ${alert.type}`;
            alertElement.innerHTML = `
                <div class="alert-icon ${alert.type}">
                    ${alert.type === 'critical' ? '⚠️' : '⚡'}
                </div>
                <div class="alert-content">
                    <div class="alert-metric">${alert.metric}</div>
                    <div class="alert-message">${alert.message}</div>
                    <div class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</div>
                </div>
            `;
            
            alertsList.appendChild(alertElement);
        });
        
        // Update alerts count
        const alertsCount = document.getElementById('alerts-count');
        if (alertsCount) {
            alertsCount.textContent = this.alerts.length;
        }
    }
    
    clearAlerts() {
        this.alerts = [];
        this.updateAlertsPanel();
        this.showNotification('Alerts cleared', 'info');
    }
    
    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        const statusDot = document.getElementById('connection-dot');
        
        if (statusElement && statusDot) {
            if (connected) {
                statusElement.className = 'connection-status connected';
                statusElement.textContent = 'Connected';
                statusDot.className = 'connection-dot connected';
            } else {
                statusElement.className = 'connection-status disconnected';
                statusElement.textContent = 'Disconnected';
                statusDot.className = 'connection-dot disconnected';
            }
        }
        
        // Update button states
        const connectBtn = document.getElementById('connect-btn');
        const disconnectBtn = document.getElementById('disconnect-btn');
        
        if (connectBtn && disconnectBtn) {
            connectBtn.disabled = connected;
            disconnectBtn.disabled = !connected;
        }
    }
    
    handleChartControl(button) {
        // Remove active class from all buttons in the same group
        button.parentElement.querySelectorAll('.chart-button').forEach(btn => {
            btn.classList.remove('active');
        });
        
        // Add active class to clicked button
        button.classList.add('active');
        
        // Handle different chart controls
        const action = button.dataset.action;
        
        switch (action) {
            case 'refresh':
                this.updateCharts();
                break;
            case 'export':
                this.exportChartData(button.dataset.chart);
                break;
            case 'fullscreen':
                this.toggleChartFullscreen(button.dataset.chart);
                break;
        }
    }
    
    exportMetricsData() {
        const data = {
            timestamp: new Date().toISOString(),
            metrics: this.metrics,
            alerts: this.alerts
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `server-metrics-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
        
        this.showNotification('Metrics data exported', 'success');
    }
    
    exportChartData(chartName) {
        const chart = this.charts[chartName];
        if (!chart) return;
        
        const data = {
            timestamp: new Date().toISOString(),
            chart: chartName,
            data: chart.data
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `${chartName}-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
        
        this.showNotification(`${chartName} data exported`, 'success');
    }
    
    toggleChartFullscreen(chartName) {
        const chartElement = document.querySelector(`[data-chart="${chartName}"]`);
        if (!chartElement) return;
        
        if (!document.fullscreenElement) {
            chartElement.requestFullscreen().catch(err => {
                console.error(`Error attempting to enable fullscreen: ${err.message}`);
            });
        } else {
            document.exitFullscreen();
        }
    }
    
    toggleAutoRefresh(enabled) {
        if (enabled) {
            this.startPeriodicUpdates();
            this.showNotification('Auto-refresh enabled', 'success');
        } else {
            this.stopPeriodicUpdates();
            this.showNotification('Auto-refresh disabled', 'info');
        }
    }
    
    startPeriodicUpdates() {
        // Update charts every 5 seconds
        this.updateInterval = setInterval(() => {
            if (this.isConnected) {
                this.updateCharts();
            }
        }, 5000);
    }
    
    stopPeriodicUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        
        // Add to page
        document.body.appendChild(notification);
        
        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }
    
    // Public methods for external access
    getMetrics() {
        return this.metrics;
    }
    
    getAlerts() {
        return this.alerts;
    }
    
    isWebSocketConnected() {
        return this.isConnected;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.realtimeMonitor = new RealtimeMonitor();
});

// Global function called by the Connect & Monitor button in realtime.html
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
        // Connect to server via API
        const r = await fetch('/api/connect', {
            method: 'POST',
            headers,
            body: JSON.stringify({ host, username: user, password: pass, port })
        });
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            throw new Error(err.detail || `Connection failed (${r.status})`);
        }
        
        // Start monitoring
        const r2 = await fetch('/monitoring/start', { method: 'POST', headers });
        if (!r2.ok) {
            const err = await r2.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to start monitoring');
        }
        
        window.realtimeMonitor?.showNotification(`Connected to ${host} — monitoring started`, 'success');
        
        // Re-establish WebSocket with auth
        window.realtimeMonitor?.connectWebSocket();
        
    } catch (e) {
        window.realtimeMonitor?.showNotification(e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Connect & Monitor'; }
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.realtimeMonitor) {
        window.realtimeMonitor.disconnectWebSocket();
        window.realtimeMonitor._stopPolling();
    }
});
