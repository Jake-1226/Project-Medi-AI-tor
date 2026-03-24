/**
 * Fleet Management JavaScript
 * Handles multi-server management, monitoring, and operations
 */

class FleetManager {
    constructor() {
        this.servers = new Map();
        this.groups = new Map();
        this.alerts = [];
        this.currentTab = 'overview';
        this.refreshInterval = null;
        this.refreshRate = 30000; // 30 seconds
        this._authToken = sessionStorage.getItem('auth_token') || '';
        
        this.init();
    }
    
    /** Auth headers for all API calls. Token comes from sessionStorage or HTTP-only cookie. */
    _headers(json = true) {
        const h = {};
        if (json) h['Content-Type'] = 'application/json';
        if (this._authToken) h['Authorization'] = `Bearer ${this._authToken}`;
        return h;
    }

    // Intercept 401 responses and redirect to login
    _checkAuth(response) {
        if (response.status === 401) {
            sessionStorage.removeItem('auth_token');
            window.location.href = '/login';
            return false;
        }
        return true;
    }
    
    init() {
        this.setupEventListeners();
        this.loadFleetData();
        this.startAutoRefresh();
        this.updateUI();
        // Keyboard shortcut: Ctrl+K focuses server search
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const search = document.getElementById('serverSearch');
                if (search) { this.switchTab('servers'); search.focus(); }
            }
        });
        // Close modals on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
            }
        });
    }
    
    setupEventListeners() {
        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = e.target.dataset.tab;
                this.switchTab(tabName);
            });
        });
        
        // Server actions
        document.getElementById('addServerBtn')?.addEventListener('click', () => this.showAddServerModal());
        
        // Search and filter
        let _searchTimer = null;
        document.getElementById('serverSearch')?.addEventListener('input', (e) => {
            clearTimeout(_searchTimer);
            _searchTimer = setTimeout(() => this.filterServers(), 200);
        });
        
        document.getElementById('environmentFilter')?.addEventListener('change', () => {
            this.filterServers();
        });
        
        document.getElementById('statusFilter')?.addEventListener('change', () => {
            this.filterServers();
        });
        
        // Bulk actions
        document.getElementById('connectAllBtn')?.addEventListener('click', () => this.connectAllServers());
        document.getElementById('disconnectAllBtn')?.addEventListener('click', () => this.disconnectAllServers());
        document.getElementById('refreshFleetBtn')?.addEventListener('click', () => this.refreshFleetData());
        document.getElementById('bulkActionsBtn')?.addEventListener('click', () => this.showBulkActionsModal());
        
        // Auto-refresh
        this.startAutoRefresh();
        
        // Modal close handlers
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal') || e.target.classList.contains('modal-overlay')) {
                e.target.remove();
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                // Close any open modals
                document.querySelectorAll('.modal.active').forEach(modal => modal.remove());
            }
        });
        
        // Server card interactions
        document.addEventListener('click', (e) => {
            if (e.target.closest('.server-card')) {
                const card = e.target.closest('.server-card');
                const serverId = card.dataset.serverId;
                
                if (e.target.closest('.server-actions')) {
                    // Let the action buttons handle their own clicks
                    return;
                }
                
                // Clicking on the card (not actions) shows details
                this.showServerDetails(serverId);
            }
        });
        
        // Add Server Modal
        document.getElementById('closeAddServerModal')?.addEventListener('click', () => this.hideAddServerModal());
        document.getElementById('cancelAddServer')?.addEventListener('click', () => this.hideAddServerModal());
        document.getElementById('saveAddServer')?.addEventListener('click', () => this.addServer());
        
        // Server Details Modal
        document.getElementById('closeServerDetailsModal')?.addEventListener('click', () => this.hideServerDetailsModal());
        document.getElementById('closeServerDetails')?.addEventListener('click', () => this.hideServerDetailsModal());
        
        // Alert filters
        document.getElementById('alertTimeFilter')?.addEventListener('change', () => this.refreshAlerts());
        document.getElementById('alertTypeFilter')?.addEventListener('change', () => this.refreshAlerts());
        
        // Group management
        document.getElementById('createGroupBtn')?.addEventListener('click', () => this.showCreateGroupModal());
        document.getElementById('manageGroupsBtn')?.addEventListener('click', () => this.manageGroups());
        
        // Analytics
        document.getElementById('analyticsTimeRange')?.addEventListener('change', () => this.refreshAnalytics());
        document.getElementById('analyticsMetric')?.addEventListener('change', () => this.refreshAnalytics());
        document.getElementById('generateReportBtn')?.addEventListener('click', () => this.generateReport());
        
        // Export actions
        document.getElementById('exportServersBtn')?.addEventListener('click', () => this.exportServers());
        document.getElementById('exportAlertsBtn')?.addEventListener('click', () => this.exportAlerts());
    }
    
    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.tab === tabName) {
                btn.classList.add('active');
            }
        });
        
        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        
        const targetTab = document.getElementById(`${tabName}Tab`);
        if (targetTab) {
            targetTab.classList.add('active');
        }
        
        this.currentTab = tabName;
        
        // Refresh tab-specific data
        this.refreshTabData(tabName);
    }
    
    refreshTabData(tabName) {
        switch (tabName) {
            case 'overview':
                this.refreshOverview();
                break;
            case 'servers':
                this.refreshServersTable();
                break;
            case 'groups':
                this.refreshGroups();
                break;
            case 'alerts':
                this.refreshAlerts();
                break;
            case 'analytics':
                this.refreshAnalytics();
                break;
        }
    }
    
    /** Refresh the overview tab by re-fetching data and updating overview widgets */
    async refreshOverview() {
        await this.refreshFleetData();
    }
    
    /** Refresh the servers table by re-fetching data */
    async refreshServersTable() {
        await this.refreshFleetData();
    }
    
    /** Refresh alerts from the API */
    async refreshAlerts() {
        try {
            const response = await fetch('/api/fleet/alerts?hours=168', { headers: this._headers(false) });
            const data = await response.json();
            if (data.status === 'success') {
                this.alerts = data.alerts || data.data || [];
                this.updateAlerts();
            }
        } catch (e) {
            this.showToast('Failed to refresh alerts', 'error');
        }
    }
    
    async loadFleetData() {
        try {
            const response = await fetch('/api/fleet/overview', { headers: this._headers(false) });
            if (!this._checkAuth(response)) return;
            const data = await response.json();
            
            if (data.status === 'success') {
                this.servers.clear();
                
                // Load servers
                for (const [serverId, serverData] of Object.entries(data.data.servers)) {
                    this.servers.set(serverId, serverData);
                }
                
                // Load groups
                for (const [groupName, groupData] of Object.entries(data.data.groups || {})) {
                    this.groups.set(groupName, groupData);
                }
                
                // Load alerts from data
                this.alerts = data.data.recent_alerts || this.alerts;
                
                this.updateUI();
            }
        } catch (error) {
            this.showToast('Failed to load fleet data', 'error');
        }
    }
    
    async refreshFleetData() {
        this.showLoading(true);
        
        try {
            const response = await fetch('/api/fleet/overview', { headers: this._headers(false) });
            const data = await response.json();
            
            if (data.status === 'success') {
                // Update servers
                for (const [serverId, serverData] of Object.entries(data.data.servers)) {
                    this.servers.set(serverId, serverData);
                }
                
                // Update groups
                for (const [groupName, groupData] of Object.entries(data.data.groups || {})) {
                    this.groups.set(groupName, groupData);
                }
                
                this.updateUI();
                this.showToast('Fleet data refreshed', 'success');
            }
        } catch (error) {
            this.showToast('Failed to refresh fleet data', 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    updateUI() {
        this.updateHeaderStats();
        this.updateOverview();
        this.updateServersTable();
        this.updateGroups();
        this.updateAlerts();
    }
    
    updateHeaderStats() {
        const totalServers = this.servers.size;
        const onlineServers = Array.from(this.servers.values()).filter(s => s.status === 'online').length;
        const avgHealth = this.calculateAverageHealth();
        const totalAlerts = Array.from(this.servers.values()).reduce((sum, s) => sum + (s.alert_count || 0), 0);
        
        // Header stats (unique IDs)
        const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
        el('headerTotalServers', totalServers);
        el('headerOnlineServers', onlineServers);
        el('headerAvgHealth', avgHealth.toFixed(0) + '%');
        el('headerTotalAlerts', totalAlerts);
    }
    
    updateOverview() {
        // Update health distribution
        this.updateHealthDistribution();
        
        // Update environment distribution
        this.updateEnvironmentDistribution();
        
        // Update recent alerts
        this.updateRecentAlerts();
        
        // Update server cards
        this.updateServerCards();
    }
    
    updateHealthDistribution() {
        const healthCounts = {
            excellent: 0,
            good: 0,
            warning: 0,
            critical: 0
        };
        
        this.servers.forEach(server => {
            const health = server.health_score || 0;
            if (health >= 90) {
                healthCounts.excellent++;
            } else if (health >= 70) {
                healthCounts.good++;
            } else if (health >= 50) {
                healthCounts.warning++;
            } else {
                healthCounts.critical++;
            }
        });
        
        const total = Object.values(healthCounts).reduce((sum, count) => sum + count, 0);
        
        // Update bars
        document.getElementById('excellentBar').style.width = `${(healthCounts.excellent / total) * 100}%`;
        document.getElementById('goodBar').style.width = `${(healthCounts.good / total) * 100}%`;
        document.getElementById('warningBar').style.width = `${(healthCounts.warning / total) * 100}%`;
        document.getElementById('criticalBar').style.width = `${(healthCounts.critical / total) * 100}%`;
        
        // Update counts
        document.getElementById('excellentCount').textContent = healthCounts.excellent;
        document.getElementById('goodCount').textContent = healthCounts.good;
        document.getElementById('warningCount').textContent = healthCounts.warning;
        document.getElementById('criticalCount').textContent = healthCounts.critical;
        
        // Update fleet health circle with dynamic gradient
        const fleetHealth = this.calculateAverageHealth();
        const healthCircle = document.getElementById('fleetHealthCircle');
        if (healthCircle) {
            const pct = Math.min(100, Math.max(0, fleetHealth));
            const deg = (pct / 100) * 360;
            const color = pct >= 80 ? '#27ae60' : pct >= 60 ? '#f39c12' : '#e74c3c';
            healthCircle.style.background = `conic-gradient(${color} 0deg, ${color} ${deg}deg, #334155 ${deg}deg, #334155 360deg)`;
            document.getElementById('fleetHealthValue').textContent = fleetHealth.toFixed(0) + '%';
        }
    }
    
    updateEnvironmentDistribution() {
        const envCounts = {};
        
        this.servers.forEach(server => {
            const env = server.environment || 'unknown';
            envCounts[env] = (envCounts[env] || 0) + 1;
        });
        
        const envChart = document.getElementById('envChart');
        if (envChart) {
            envChart.innerHTML = '';
            
            Object.entries(envCounts).forEach(([env, count]) => {
                const envItem = document.createElement('div');
                envItem.className = 'env-item';
                envItem.innerHTML = `
                    <span class="env-name">${env.charAt(0).toUpperCase() + env.slice(1)}</span>
                    <span class="env-count">${count}</span>
                `;
                envChart.appendChild(envItem);
            });
        }
    }
    
    updateRecentAlerts() {
        const alertsContainer = document.getElementById('recentAlerts');
        if (!alertsContainer) return;
        
        // Get recent alerts (last 10)
        const recentAlerts = this.alerts.slice(-10);
        
        if (recentAlerts.length === 0) {
            alertsContainer.innerHTML = '<div class="no-alerts">No recent alerts</div>';
            return;
        }
        
        alertsContainer.innerHTML = recentAlerts.map(alert => `
            <div class="alert-item ${alert.type}">
                <span class="alert-icon">${this.getAlertIcon(alert.type)}</span>
                <div class="alert-content">
                    <div class="alert-server">${alert.server_name}</div>
                    <div class="alert-message">${alert.message}</div>
                </div>
                <span class="alert-time">${this.formatTime(alert.timestamp)}</span>
            </div>
        `).join('');
    }
    
    updateServerCards() {
        const serverCards = document.getElementById('serverCards');
        if (!serverCards) return;
        
        serverCards.innerHTML = Array.from(this.servers.values()).map(server => `
            <div class="server-card" onclick="fleetManager.showServerDetails('${server.id}')">
                <div class="server-header">
                    <div class="server-name">${server.name}</div>
                    <div class="server-status ${server.status}"></div>
                </div>
                <div class="server-metrics">
                    <div class="server-metric">
                        <div class="metric-value-small">${server.health_score.toFixed(0)}%</div>
                        <div class="metric-label-small">Health</div>
                    </div>
                    <div class="server-metric">
                        <div class="metric-value-small">${server.alert_count || 0}</div>
                        <div class="metric-label-small">Alerts</div>
                    </div>
                </div>
                <div class="server-info">
                    <div>📍 ${server.host}</div>
                    <div>🏷️ ${server.environment || 'Unknown'}</div>
                    <div>👁 ${server.location || 'Unknown'}</div>
                </div>
                <div class="server-actions">
                    <button class="server-action-btn" onclick="event.stopPropagation(); fleetManager.connectServer('${server.id}')">Connect</button>
                    <button class="server-action-btn" onclick="event.stopPropagation(); fleetManager.disconnectServer('${server.id}')">Disconnect</button>
                </div>
            </div>
        `).join('');
    }
    
    updateServersTable() {
        const tbody = document.getElementById('serversTableBody');
        if (!tbody) return;
        
        tbody.innerHTML = Array.from(this.servers.values()).map(server => `
            <tr>
                <td><input type="checkbox" class="server-row-check" value="${server.id}" data-server-id="${server.id}"></td>
                <td>
                    <strong>${server.name}</strong>
                    ${server.tags.length > 0 ? `<br><small>${server.tags.join(', ')}</small>` : ''}
                </td>
                <td>${server.host}:${server.port || 443}</td>
                <td>
                    <span class="env-badge">${server.environment || 'Unknown'}</span>
                </td>
                <td>
                    <span class="status-badge ${server.status}">${this.statusLabel(server.status)}</span>
                </td>
                <td>
                    <span class="health-badge ${this.getHealthLevel(server.health_score)}">${server.health_score.toFixed(1)}%</span>
                </td>
                <td>${server.alert_count || 0}</td>
                <td>${server.last_seen ? this.formatTime(server.last_seen) : 'Never'}</td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="fleetManager.showServerDetails('${server.id}')">Details</button>
                    <button class="btn btn-sm btn-outline" onclick="fleetManager.editServer('${server.id}')">Edit</button>
                </td>
            </tr>
        `).join('');
        // P6: Show server count
        const countEl = document.getElementById('serverTableCount');
        if (countEl) countEl.textContent = `${this.servers.size} server${this.servers.size !== 1 ? 's' : ''}`;
    }
    
    updateGroups() {
        const groupsGrid = document.getElementById('groupsGrid');
        if (!groupsGrid) return;
        
        groupsGrid.innerHTML = Array.from(this.groups.values()).map(group => `
            <div class="group-card">
                <div class="group-header">
                    <div class="group-name">${group.name}</div>
                    <div class="group-count">${group.server_ids.length}</div>
                </div>
                <div class="group-description">${group.description || 'No description'}</div>
                <div class="group-servers">
                    ${group.server_ids.slice(0, 5).map(serverId => {
                        const server = this.servers.get(serverId);
                        return server ? `<span class="group-server-tag">${server.name}</span>` : '';
                    }).join('')}
                    ${group.server_ids.length > 5 ? `<span class="group-server-tag">+${group.server_ids.length - 5} more</span>` : ''}
                </div>
                <div class="group-actions">
                    <button class="btn btn-sm btn-outline" onclick="fleetManager.editGroup('${group.name}')">Edit</button>
                    <button class="btn btn-sm btn-outline" onclick="fleetManager.deleteGroup('${group.name}')">Delete</button>
                </div>
            </div>
        `).join('');
    }
    
    updateAlerts() {
        const alertsContainer = document.getElementById('alertsContainer');
        if (!alertsContainer) return;
        
        const timeFilter = document.getElementById('alertTimeFilter')?.value || '24';
        const typeFilter = document.getElementById('alertTypeFilter')?.value || '';
        
        let filteredAlerts = this.alerts;
        
        // Filter by time
        const cutoffTime = new Date(Date.now() - (parseInt(timeFilter) * 60 * 60 * 1000));
        filteredAlerts = filteredAlerts.filter(alert => new Date(alert.timestamp) >= cutoffTime);
        
        // Filter by type
        if (typeFilter) {
            filteredAlerts = filteredAlerts.filter(alert => alert.type === typeFilter);
        }
        
        if (filteredAlerts.length === 0) {
            alertsContainer.innerHTML = '<div class="no-alerts">No alerts found</div>';
            return;
        }
        
        alertsContainer.innerHTML = filteredAlerts.map((alert, idx) => `
            <div class="alert-card ${alert.type}">
                <div class="alert-header">
                    <div class="alert-title">${alert.type.charAt(0).toUpperCase() + alert.type.slice(1)} Alert</div>
                    <div class="alert-timestamp">${this.formatTime(alert.timestamp)}</div>
                </div>
                <div class="alert-details">
                    <div class="alert-server-name">${alert.server_name || 'Unknown Server'}</div>
                    <div class="alert-message">${alert.message}</div>
                    ${alert.metric ? `<div class="alert-metric">Metric: ${alert.metric}</div>` : ''}
                </div>
                <div class="alert-actions">
                    <button class="alert-action" onclick="fleetManager.acknowledgeAlert(${idx})">Acknowledge</button>
                    <button class="alert-action" onclick="fleetManager.viewAlertDetails(${idx})">Details</button>
                </div>
            </div>
        `).join('');
    }
    
    async connectAllServers() {
        this.setButtonLoading('connectAllBtn', true);
        
        try {
            const response = await fetch('/api/fleet/connect-all', { method: 'POST', headers: this._headers(false) });
            
            if (response.ok) {
                const result = await response.json();
                const connected = Object.values(result.results).filter(status => status === 'connected').length;
                const total = Object.keys(result.results).length;
                
                this.showToast(`Connected ${connected}/${total} servers successfully`, 'success');
            } else {
                this.showToast('Failed to connect to all servers', 'error');
            }
        } catch (error) {
            this.showToast('Failed to connect to all servers', 'error');
        } finally {
            this.setButtonLoading('connectAllBtn', false);
        }
    }
    
    async disconnectAllServers() {
        this.setButtonLoading('disconnectAllBtn', true);
        
        try {
            const response = await fetch('/api/fleet/disconnect-all', { method: 'POST', headers: this._headers(false) });
            
            if (response.ok) {
                const result = await response.json();
                const disconnected = Object.values(result.results).filter(status => status === 'disconnected').length;
                const total = Object.keys(result.results).length;
                
                this.showToast(`Disconnected ${disconnected}/${total} servers successfully`, 'success');
            } else {
                this.showToast('Failed to disconnect from all servers', 'error');
            }
        } catch (error) {
            this.showToast('Failed to disconnect from all servers', 'error');
        } finally {
            this.setButtonLoading('disconnectAllBtn', false);
        }
    }
    
    async connectServer(serverId) {
        try {
            const response = await fetch(`/api/fleet/servers/${serverId}/connect`, { method: 'POST', headers: this._headers(false) });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast(`Connected to ${this.servers.get(serverId)?.name}`, 'success');
                await this.refreshFleetData();
            } else {
                throw new Error(data.message || 'Failed to connect server');
            }
        } catch (error) {
            this.showToast('Failed to connect to server', 'error');
        }
    }
    
    async disconnectServer(serverId) {
        try {
            const response = await fetch(`/api/fleet/servers/${serverId}/disconnect`, { method: 'POST', headers: this._headers(false) });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast(`Disconnected from ${this.servers.get(serverId)?.name}`, 'info');
                await this.refreshFleetData();
            } else {
                throw new Error(data.message || 'Failed to disconnect server');
            }
        } catch (error) {
            this.showToast('Failed to disconnect from server', 'error');
        }
    }
    
    showAddServerModal() {
        const modal = document.getElementById('addServerModal');
        if (modal) {
            modal.classList.add('active');
            // Reset form
            document.getElementById('addServerForm').reset();
        }
    }
    
    hideAddServerModal() {
        const modal = document.getElementById('addServerModal');
        if (modal) {
            modal.classList.remove('active');
            // P10: Clear form fields after closing
            const form = document.getElementById('addServerForm');
            if (form) form.reset();
            if (modal.parentElement === document.body) {
                modal.remove();
            }
        }
    }
    
    async addServer(passedData) {
        const serverData = passedData || {
            name: document.getElementById('serverName')?.value?.trim(),
            host: document.getElementById('serverHost')?.value?.trim(),
            username: document.getElementById('serverUsername')?.value?.trim(),
            password: document.getElementById('serverPassword')?.value,
            port: parseInt(document.getElementById('serverPort')?.value) || 443,
            environment: document.getElementById('serverEnvironment')?.value,
            location: document.getElementById('serverLocation')?.value?.trim(),
            tags: (document.getElementById('serverTags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
            notes: document.getElementById('serverNotes')?.value?.trim()
        };
        
        // Validate required fields
        if (!serverData.name || !serverData.host || !serverData.username || !serverData.password) {
            this.showToast('Please fill in all required fields (Name, Host, Username, Password)', 'error');
            return;
        }
        
        this.showLoading(true);
        
        try {
            const response = await fetch('/api/fleet/servers', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify(serverData)
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast(`Server "${serverData.name}" added successfully`, 'success');
                this.hideAddServerModal();
                await this.loadFleetData();
            } else {
                throw new Error(data.message || 'Failed to add server');
            }
        } catch (error) {
            this.showToast(error.message || 'Failed to add server', 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    showServerDetails(serverId) {
        const server = this.servers.get(serverId);
        if (!server) return;
        
        const healthLevel = this.getHealthLevel(server.health_score);
        const statusClass = server.status.toLowerCase();
        
        // Try the new HTML modal first, then fall back to dynamic
        const modal = document.getElementById('serverDetailModal') || document.getElementById('serverDetailsModal');
        const content = document.getElementById('serverDetailBody') || document.getElementById('serverDetailsContent');
        
        if (modal && content) {
            const titleEl = document.getElementById('serverDetailTitle');
            if (titleEl) titleEl.textContent = server.name;
            
            content.innerHTML = `
                <div class="server-detail-grid">
                    <div class="detail-section">
                        <h3>Connection</h3>
                        <div class="detail-row"><span class="detail-label">Host:</span><span class="detail-value">${server.host}:${server.port || 443}</span></div>
                        <div class="detail-row"><span class="detail-label">Status:</span><span class="detail-value"><span class="status-badge ${statusClass}">${server.status}</span></span></div>
                        <div class="detail-row"><span class="detail-label">Last Seen:</span><span class="detail-value">${server.last_seen ? this.formatTime(server.last_seen) : 'Never'}</span></div>
                    </div>
                    <div class="detail-section">
                        <h3>Health</h3>
                        <div class="health-indicator-lg ${healthLevel}">
                            <div class="health-bar-lg"><div class="health-fill-lg" style="width: ${server.health_score || 0}%"></div></div>
                            <span class="health-text-lg">${(server.health_score || 0).toFixed(0)}%</span>
                        </div>
                        <div class="detail-row"><span class="detail-label">Alerts:</span><span class="detail-value">${server.alert_count || 0}</span></div>
                    </div>
                    <div class="detail-section">
                        <h3>Info</h3>
                        <div class="detail-row"><span class="detail-label">Environment:</span><span class="detail-value">${server.environment || 'Not set'}</span></div>
                        <div class="detail-row"><span class="detail-label">Location:</span><span class="detail-value">${server.location || 'Not set'}</span></div>
                        <div class="detail-row"><span class="detail-label">Model:</span><span class="detail-value">${server.model || 'Unknown'}</span></div>
                        <div class="detail-row"><span class="detail-label">Service Tag:</span><span class="detail-value">${server.service_tag || 'Unknown'}</span></div>
                    </div>
                    <div class="detail-section">
                        <h3>Tags</h3>
                        <div class="tags-container">
                            ${(server.tags || []).map(tag => `<span class="tag">${tag}</span>`).join('') || '<span class="text-muted">No tags</span>'}
                        </div>
                        ${server.notes ? `<h3 style="margin-top:12px">Notes</h3><p class="notes-text">${server.notes}</p>` : ''}
                    </div>
                </div>
                <div class="detail-actions" style="margin-top:16px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button class="btn btn-primary" onclick="fleetManager.openTechnicianDashboard('${serverId}')">Open Dashboard</button>
                    <button class="btn btn-outline" onclick="fleetManager.openRealtimeMonitor('${serverId}')">Real-time Monitor</button>
                    <button class="btn btn-outline" onclick="fleetManager.editServer('${serverId}')">Edit Server</button>
                </div>
            `;
            
            // Wire up footer buttons
            const connectBtn = document.getElementById('serverDetailConnect');
            const deleteBtn = document.getElementById('serverDetailDelete');
            if (connectBtn) {
                connectBtn.onclick = () => {
                    modal.classList.remove('active');
                    if (server.status === 'online') {
                        this.disconnectServer(serverId);
                    } else {
                        this.connectServer(serverId);
                    }
                };
                connectBtn.textContent = server.status === 'online' ? 'Disconnect' : 'Connect';
            }
            if (deleteBtn) {
                deleteBtn.onclick = () => {
                    modal.classList.remove('active');
                    this.deleteServer(serverId);
                };
            }
            
            modal.classList.add('active');
        }
    }
    
    hideServerDetailsModal() {
        const modal = document.getElementById('serverDetailsModal');
        if (modal) {
            modal.classList.remove('active');
        }
    }
    
    filterServers(searchTerm = '') {
        const envFilter = document.getElementById('environmentFilter')?.value;
        const statusFilter = document.getElementById('statusFilter')?.value;
        
        let filteredServers = Array.from(this.servers.values());
        
        // Apply search filter
        if (searchTerm) {
            filteredServers = filteredServers.filter(server => 
                server.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                server.host.toLowerCase().includes(searchTerm.toLowerCase()) ||
                server.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()))
            );
        }
        
        // Apply environment filter
        if (envFilter) {
            filteredServers = filteredServers.filter(server => server.environment === envFilter);
        }
        
        // Apply status filter
        if (statusFilter) {
            filteredServers = filteredServers.filter(server => server.status === statusFilter);
        }
        
        // Update table
        const tbody = document.getElementById('serversTableBody');
        if (tbody) {
            tbody.innerHTML = filteredServers.map(server => `
                <tr>
                    <td><input type="checkbox" class="server-row-check" value="${server.id}" data-server-id="${server.id}"></td>
                    <td>
                        <strong>${server.name}</strong>
                        ${server.tags.length > 0 ? `<br><small>${server.tags.join(', ')}</small>` : ''}
                    </td>
                    <td>${server.host}:${server.port || 443}</td>
                    <td>
                        <span class="env-badge">${server.environment || 'Unknown'}</span>
                    </td>
                    <td>
                        <span class="status-badge ${server.status}">${server.status}</span>
                    </td>
                    <td>
                        <span class="health-badge ${this.getHealthLevel(server.health_score)}">${server.health_score.toFixed(1)}%</span>
                    </td>
                    <td>${server.alert_count || 0}</td>
                    <td>${server.last_seen ? this.formatTime(server.last_seen) : 'Never'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="fleetManager.showServerDetails('${server.id}')">Details</button>
                        <button class="btn btn-sm btn-outline" onclick="fleetManager.editServer('${server.id}')">Edit</button>
                    </td>
                </tr>
            `).join('');
        }
    }
    
    async refreshAnalytics() {
        try {
            const timeRange = document.getElementById('analyticsTimeRange')?.value || '24';
            const metric = document.getElementById('analyticsMetric')?.value || 'health';
            
            const response = await fetch(`/api/fleet/analytics?time_range=${timeRange}h&metric=${metric}`, { headers: this._headers(false) });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.renderAnalytics(data.data);
            }
        } catch (error) {
            this.showToast('Failed to load analytics', 'error');
        }
    }
    
    renderAnalytics(analytics) {
        // Update summary
        const summaryEl = document.getElementById('analyticsSummary');
        if (summaryEl) {
            const summary = analytics.summary || {};
            summaryEl.innerHTML = `
                <div class="summary-item">
                    <div class="summary-value">${summary.total_servers || 0}</div>
                    <div class="summary-label">Total Servers</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${(summary.avg_health || 0).toFixed(1)}%</div>
                    <div class="summary-label">Avg Health</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${(summary.online_percentage || 0).toFixed(1)}%</div>
                    <div class="summary-label">Online Rate</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${summary.total_alerts || 0}</div>
                    <div class="summary-label">Alerts</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${(summary.uptime_estimate || 0).toFixed(1)}%</div>
                    <div class="summary-label">Uptime</div>
                </div>
            `;
        }
        
        // Render charts if Chart.js is available
        if (typeof Chart !== 'undefined') {
            this.renderHealthTrendsChart(analytics);
            this.renderAlertTrendsChart(analytics);
        }
    }
    
    renderHealthTrendsChart(analytics) {
        const canvas = document.getElementById('healthTrendsChart');
        if (!canvas) return;
        
        // Destroy existing chart
        if (this._healthChart) this._healthChart.destroy();
        
        const dist = analytics.health_distribution || {};
        this._healthChart = new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: ['Excellent', 'Good', 'Warning', 'Critical'],
                datasets: [{
                    data: [dist.excellent || 0, dist.good || 0, dist.warning || 0, dist.critical || 0],
                    backgroundColor: ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 15 } }
                }
            }
        });
    }
    
    renderAlertTrendsChart(analytics) {
        const canvas = document.getElementById('alertTrendsChart');
        if (!canvas) return;
        
        if (this._alertChart) this._alertChart.destroy();
        
        const alerts = analytics.recent_alerts || [];
        const alertsByType = { critical: 0, warning: 0, info: 0 };
        alerts.forEach(a => { alertsByType[a.type] = (alertsByType[a.type] || 0) + 1; });
        
        this._alertChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: ['Critical', 'Warning', 'Info'],
                datasets: [{
                    label: 'Alert Count',
                    data: [alertsByType.critical, alertsByType.warning, alertsByType.info],
                    backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6'],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                    x: { ticks: { color: '#94a3b8' }, grid: { display: false } }
                }
            }
        });
    }
    
    async generateReport() {
        this.showLoading(true);
        try {
            const response = await fetch('/api/fleet/analytics/report', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify({})
            });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showReportModal(data.report);
            } else {
                this.showToast('Failed to generate report', 'error');
            }
        } catch (error) {
            this.showToast('Failed to generate report', 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    showReportModal(report) {
        const modal = document.getElementById('reportModal');
        const body = document.getElementById('reportBody');
        if (!modal || !body) return;
        
        const summary = report.fleet_summary || {};
        body.innerHTML = `
            <div class="report-content">
                <div class="report-header-info">
                    <p><strong>Generated:</strong> ${new Date(report.generated_at).toLocaleString()}</p>
                </div>
                <h3>Fleet Summary</h3>
                <div class="report-grid">
                    <div class="report-stat"><span class="stat-val">${summary.total_servers}</span><span class="stat-lbl">Total Servers</span></div>
                    <div class="report-stat"><span class="stat-val">${summary.online_servers}</span><span class="stat-lbl">Online</span></div>
                    <div class="report-stat"><span class="stat-val">${summary.offline_servers}</span><span class="stat-lbl">Offline</span></div>
                    <div class="report-stat"><span class="stat-val">${summary.error_servers}</span><span class="stat-lbl">Error</span></div>
                    <div class="report-stat"><span class="stat-val">${(summary.average_health_score || 0).toFixed(1)}%</span><span class="stat-lbl">Avg Health</span></div>
                    <div class="report-stat"><span class="stat-val">${summary.total_alerts}</span><span class="stat-lbl">Alerts</span></div>
                </div>
                ${report.server_details && report.server_details.length > 0 ? `
                <h3>Server Details</h3>
                <table class="report-table">
                    <thead><tr><th>Name</th><th>Host</th><th>Status</th><th>Health</th><th>Environment</th><th>Alerts</th></tr></thead>
                    <tbody>
                        ${report.server_details.map(s => `
                            <tr>
                                <td>${s.name}</td><td>${s.host}</td>
                                <td><span class="status-badge ${s.status}">${s.status}</span></td>
                                <td>${(s.health_score || 0).toFixed(0)}%</td>
                                <td>${s.environment || '-'}</td><td>${s.alert_count || 0}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ` : ''}
                ${report.recommendations && report.recommendations.length > 0 ? `
                <h3>Recommendations</h3>
                <ul class="report-recommendations">
                    ${report.recommendations.map(r => `<li class="rec-${r.priority}">${r.message}</li>`).join('')}
                </ul>
                ` : ''}
            </div>
        `;
        modal.classList.add('active');
    }
    
    downloadReport() {
        const body = document.getElementById('reportBody');
        if (!body) return;
        const blob = new Blob([body.innerText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `fleet-report-${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this.showToast('Report downloaded', 'success');
    }
    
    exportServers() {
        const servers = Array.from(this.servers.values());
        const csv = this.convertToCSV(servers);
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `fleet-servers-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
        this.showToast('Servers exported successfully', 'success');
    }
    
    exportAlerts() {
        const csv = this.convertAlertsToCSV(this.alerts);
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `fleet-alerts-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        
        URL.revokeObjectURL(url);
        this.showToast('Alerts exported successfully', 'success');
    }
    
    // Utility methods
    calculateAverageHealth() {
        const healthScores = Array.from(this.servers.values()).map(s => s.health_score || 0);
        return healthScores.length > 0 ? healthScores.reduce((sum, score) => sum + score, 0) / healthScores.length : 0;
    }
    
    getHealthLevel(score) {
        if (score >= 90) return 'excellent';
        if (score >= 70) return 'good';
        if (score >= 50) return 'warning';
        return 'critical';
    }
    
    // P9: Status text with icon for color-blind accessibility
    statusLabel(status) {
        const icons = { online: '●', offline: '○', error: '⚠', connecting: '◌' };
        return `${icons[status] || '?'} ${status}`;
    }

    getAlertIcon(type) {
        const icons = {
            critical: '🚨',
            warning: '⚠️',
            info: 'ℹ️'
        };
        return icons[type] || 'ℹ️';
    }
    
    formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString();
    }
    
    convertToCSV(data) {
        if (data.length === 0) return '';
        
        const headers = Object.keys(data[0]).filter(k => k !== 'password');
        const csvContent = [
            headers.join(','),
            ...data.map(row => headers.map(h => `"${String(row[h] ?? '').replace(/"/g, '""')}"`).join(','))
        ].join('\n');
        
        return csvContent;
    }
    
    convertAlertsToCSV(alerts) {
        if (alerts.length === 0) return '';
        
        const headers = ['timestamp', 'server_name', 'type', 'message', 'server_id'];
        const csvContent = [
            headers.join(','),
            ...alerts.map(alert => [
                alert.timestamp,
                alert.server_name,
                alert.type,
                alert.message,
                alert.server_id
            ].map(field => `"${field || ''}"`).join(','))
        ].join('\n');
        
        return csvContent;
    }
    
    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            if (show) {
                overlay.classList.add('active');
            } else {
                overlay.classList.remove('active');
            }
        }
    }
    
    showToast(message, type = 'info', duration) {
        if (!duration) duration = (type === 'error' || type === 'danger') ? 6000 : 3000;
        const container = document.getElementById('toastContainer');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <div class="toast-title">${type.charAt(0).toUpperCase() + type.slice(1)}</div>
            <div class="toast-message">${message}</div>
        `;
        
        container.appendChild(toast);
        
        // Trigger animation
        setTimeout(() => toast.classList.add('show'), 10);
        
        // Remove after duration
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    }
    
    setButtonLoading(buttonId, loading = true) {
        const button = document.getElementById(buttonId);
        if (button) {
            if (loading) {
                button.disabled = true;
                button.dataset.originalText = button.innerHTML;
                button.innerHTML = '<span class="btn-spinner"></span> Processing...';
                button.style.cursor = 'not-allowed';
            } else {
                button.disabled = false;
                button.innerHTML = button.dataset.originalText || button.innerHTML;
                button.style.cursor = 'pointer';
            }
        }
    }
    
    confirmAction(message, callback) {
        // Create confirmation modal
        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <h3>Confirm Action</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">✕</button>
                </div>
                <div class="modal-body">
                    <p>${message}</p>
                </div>
                <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                    <button class="btn btn-outline" onclick="this.closest('.modal').remove()">Cancel</button>
                    <button class="btn btn-danger" id="confirmBtn">Confirm</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Handle confirmation
        document.getElementById('confirmBtn').addEventListener('click', () => {
            modal.remove();
            callback();
        });
        
        // Handle cancel
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        this.refreshInterval = setInterval(() => {
            this.refreshFleetData();
        }, this.refreshRate);
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    // Group management methods
    async showCreateGroupModal() {
        const modal = document.getElementById('createGroupModal');
        if (!modal) return;
        
        // Populate server checklist
        const checklist = document.getElementById('groupServerChecklist');
        if (checklist) {
            checklist.innerHTML = Array.from(this.servers.entries()).map(([id, server]) => `
                <label class="checklist-item">
                    <input type="checkbox" value="${id}" class="group-server-check">
                    <span>${server.name} (${server.host})</span>
                </label>
            `).join('') || '<p class="text-muted">No servers available. Add servers first.</p>';
        }
        
        modal.classList.add('active');
        
        // Setup save button
        const saveBtn = document.getElementById('saveGroupBtn');
        if (saveBtn) {
            saveBtn.onclick = () => this.createGroup();
        }
    }
    
    async createGroup() {
        const name = document.getElementById('groupName')?.value?.trim();
        const description = document.getElementById('groupDescription')?.value?.trim() || '';
        
        if (!name) {
            this.showToast('Group name is required', 'error');
            return;
        }
        
        const selectedServers = Array.from(document.querySelectorAll('.group-server-check:checked')).map(cb => cb.value);
        
        try {
            this.showLoading(true);
            const response = await fetch('/api/fleet/groups', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify({ name, description, server_ids: selectedServers })
            });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast(`Group "${name}" created successfully`, 'success');
                document.getElementById('createGroupModal')?.classList.remove('active');
                document.getElementById('groupName').value = '';
                document.getElementById('groupDescription').value = '';
                await this.loadFleetData();
                this.refreshGroups();
            } else {
                this.showToast(data.detail || 'Failed to create group', 'error');
            }
        } catch (error) {
            this.showToast('Failed to create group', 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    async manageGroups() {
        // Fetch latest groups from API
        try {
            const response = await fetch('/api/fleet/groups', { headers: this._headers(false) });
            const data = await response.json();
            
            if (data.status === 'success') {
                this.groups.clear();
                for (const [name, groupData] of Object.entries(data.groups || {})) {
                    this.groups.set(name, groupData);
                }
                this.refreshGroups();
                this.switchTab('groups');
            }
        } catch (error) {
            this.showToast('Failed to load groups', 'error');
        }
    }
    
    async editGroup(groupName) {
        const group = this.groups.get(groupName);
        if (!group) return;
        
        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Edit Group: ${groupName}</h2>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">&#10005;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Description</label>
                        <textarea id="editGroupDesc" rows="2">${group.description || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label>Servers in Group (${group.server_count || 0})</label>
                        <div class="server-checklist">
                            ${Array.from(this.servers.entries()).map(([id, server]) => `
                                <label class="checklist-item">
                                    <input type="checkbox" value="${id}" class="edit-group-server-check" 
                                        ${(group.server_ids || []).includes(id) ? 'checked' : ''}>
                                    <span>${server.name} (${server.host})</span>
                                </label>
                            `).join('') || '<p>No servers available</p>'}
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Cancel</button>
                    <button class="btn btn-primary" id="saveEditGroupBtn">Save Changes</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        document.getElementById('saveEditGroupBtn').onclick = async () => {
            this.showToast(`Group "${groupName}" updated`, 'success');
            modal.remove();
            await this.loadFleetData();
            this.refreshGroups();
        };
    }
    
    async deleteGroup(groupName) {
        this.confirmAction(`Delete group "${groupName}"? Servers will not be deleted.`, async () => {
            try {
                const response = await fetch(`/api/fleet/groups/${encodeURIComponent(groupName)}`, { method: 'DELETE', headers: this._headers(false) });
                const data = await response.json();
                if (data.status === 'success') {
                    this.showToast(`Group "${groupName}" deleted`, 'success');
                    await this.loadFleetData();
                    this.refreshGroups();
                } else {
                    this.showToast(data.detail || 'Cannot delete this group', 'error');
                }
            } catch (error) {
                this.showToast('Failed to delete group', 'error');
            }
        });
    }
    
    // Bulk action methods
    showBulkActionsModal() {
        const selected = document.querySelectorAll('.server-row-check:checked');
        const count = selected.length;
        const modal = document.getElementById('bulkActionsModal');
        if (modal) {
            document.getElementById('bulkActionCount').textContent = `${count} server${count !== 1 ? 's' : ''} selected`;
            modal.classList.add('active');
        }
    }
    
    getSelectedServerIds() {
        return Array.from(document.querySelectorAll('.server-row-check:checked')).map(cb => cb.value);
    }
    
    async bulkConnect() {
        const ids = this.getSelectedServerIds();
        if (ids.length === 0) { this.showToast('No servers selected', 'warning'); return; }
        document.getElementById('bulkActionsModal')?.classList.remove('active');
        this.showLoading(true);
        for (const id of ids) {
            await this.connectServer(id);
        }
        this.showLoading(false);
        this.showToast(`Connected to ${ids.length} server(s)`, 'success');
        await this.loadFleetData();
    }
    
    async bulkDisconnect() {
        const ids = this.getSelectedServerIds();
        if (ids.length === 0) { this.showToast('No servers selected', 'warning'); return; }
        document.getElementById('bulkActionsModal')?.classList.remove('active');
        this.showLoading(true);
        for (const id of ids) {
            await this.disconnectServer(id);
        }
        this.showLoading(false);
        this.showToast(`Disconnected ${ids.length} server(s)`, 'success');
        await this.loadFleetData();
    }
    
    async bulkHealthCheck() {
        document.getElementById('bulkActionsModal')?.classList.remove('active');
        this.showLoading(true);
        try {
            const response = await fetch('/api/fleet/health-check', { method: 'POST', headers: this._headers(false) });
            const data = await response.json();
            this.showToast(data.message || 'Health check completed', 'success');
            await this.loadFleetData();
        } catch (error) {
            this.showToast('Health check failed', 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    async bulkDelete() {
        const ids = this.getSelectedServerIds();
        if (ids.length === 0) { this.showToast('No servers selected', 'warning'); return; }
        this.confirmAction(`Delete ${ids.length} server(s)? This cannot be undone.`, async () => {
            document.getElementById('bulkActionsModal')?.classList.remove('active');
            this.showLoading(true);
            for (const id of ids) {
                await this.performServerDeletion(id);
            }
            this.showLoading(false);
            await this.loadFleetData();
        });
    }
    
    editServer(serverId) {
        const server = this.servers.get(serverId);
        if (!server) return;
        
        // Create edit modal
        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.id = 'editServerModal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Edit Server</h2>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">✕</button>
                </div>
                <div class="modal-body">
                    <form id="editServerForm" class="add-server-form">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="editServerName">Server Name *</label>
                                <input type="text" id="editServerName" name="name" value="${server.name}" required>
                            </div>
                            <div class="form-group">
                                <label for="editServerHost">Host/IP *</label>
                                <input type="text" id="editServerHost" name="host" value="${server.host}" required>
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="editServerUsername">Username *</label>
                                <input type="text" id="editServerUsername" name="username" value="${server.username}" required>
                            </div>
                            <div class="form-group">
                                <label for="editServerPassword">Password</label>
                                <input type="password" id="editServerPassword" name="password" placeholder="Leave unchanged">
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="editServerPort">Port</label>
                                <input type="number" id="editServerPort" name="port" value="${server.port || 443}">
                            </div>
                            <div class="form-group">
                                <label for="editServerEnvironment">Environment</label>
                                <select id="editServerEnvironment" name="environment">
                                    <option value="production" ${server.environment === 'production' ? 'selected' : ''}>Production</option>
                                    <option value="staging" ${server.environment === 'staging' ? 'selected' : ''}>Staging</option>
                                    <option value="development" ${server.environment === 'development' ? 'selected' : ''}>Development</option>
                                    <option value="test" ${server.environment === 'test' ? 'selected' : ''}>Test</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="editServerLocation">Location</label>
                                <input type="text" id="editServerLocation" name="location" value="${server.location || ''}" placeholder="Data center, rack, etc.">
                            </div>
                            <div class="form-group">
                                <label for="editServerModel">Model</label>
                                <input type="text" id="editServerModel" name="model" value="${server.model || ''}" placeholder="PowerEdge R650, etc.">
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="editServerServiceTag">Service Tag</label>
                                <input type="text" id="editServerServiceTag" name="service_tag" value="${server.service_tag || ''}" placeholder="Dell service tag">
                            </div>
                            <div class="form-group">
                                <label for="editServerTags">Tags</label>
                                <input type="text" id="editServerTags" name="tags" value="${(server.tags || []).join(', ')}" placeholder="web, critical, production">
                            </div>
                        </div>
                        <div class="form-group">
                            <label for="editServerNotes">Notes</label>
                            <textarea id="editServerNotes" name="notes" rows="3" placeholder="Additional notes about this server">${server.notes || ''}</textarea>
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-outline" onclick="this.closest('.modal').remove()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Update Server</button>
                        </div>
                    </form>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Handle form submission
        const form = document.getElementById('editServerForm');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            const updateData = {};
            
            // Only include password if it's not empty
            for (let [key, value] of formData.entries()) {
                if (key === 'password' && !value) continue;
                if (key === 'tags') {
                    updateData[key] = value.split(',').map(tag => tag.trim()).filter(tag => tag);
                } else {
                    updateData[key] = value;
                }
            }
            
            try {
                this.showLoading(true);
                
                const response = await fetch(`/api/fleet/servers/${serverId}`, {
                    method: 'PUT',
                    headers: this._headers(),
                    body: JSON.stringify(updateData)
                });
                
                if (response.ok) {
                    this.showToast('Server updated successfully', 'success');
                    modal.remove();
                    this.loadFleetData(); // Refresh data
                } else {
                    const error = await response.json();
                    this.showToast(`Failed to update server: ${error.detail}`, 'error');
                }
            } catch (error) {
                this.showToast('Failed to update server', 'error');
            } finally {
                this.showLoading(false);
            }
        });
    }
    
    deleteServer(serverId) {
        const server = this.servers.get(serverId);
        if (!server) return;
        
        this.confirmAction(
            `Are you sure you want to delete server "${server.name}"? This action cannot be undone.`,
            () => this.performServerDeletion(serverId)
        );
    }
    
    async performServerDeletion(serverId) {
        try {
            this.showLoading(true);
            
            const response = await fetch(`/api/fleet/servers/${serverId}`, {
                method: 'DELETE',
                headers: this._headers(false)
            });
            
            if (response.ok) {
                this.showToast('Server deleted successfully', 'success');
                this.loadFleetData(); // Refresh data
            } else {
                const error = await response.json();
                this.showToast(`Failed to delete server: ${error.detail}`, 'error');
            }
        } catch (error) {
            this.showToast('Failed to delete server', 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    showAddServerModal() {
        // Check if modal already exists
        if (document.getElementById('addServerModal')) {
            return;
        }
        
        // Create add server modal
        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.id = 'addServerModal';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Add New Server</h2>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">✕</button>
                </div>
                <div class="modal-body">
                    <form id="addServerForm" class="add-server-form">
                        <div class="form-row">
                            <div class="form-group">
                                <label for="serverName">Server Name *</label>
                                <input type="text" id="serverName" name="name" required>
                            </div>
                            <div class="form-group">
                                <label for="serverHost">Host/IP *</label>
                                <input type="text" id="serverHost" name="host" required>
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="serverUsername">Username *</label>
                                <input type="text" id="serverUsername" name="username" required>
                            </div>
                            <div class="form-group">
                                <label for="serverPassword">Password *</label>
                                <input type="password" id="serverPassword" name="password" required>
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="serverPort">Port</label>
                                <input type="number" id="serverPort" name="port" value="443">
                            </div>
                            <div class="form-group">
                                <label for="serverEnvironment">Environment</label>
                                <select id="serverEnvironment" name="environment">
                                    <option value="production">Production</option>
                                    <option value="staging">Staging</option>
                                    <option value="development">Development</option>
                                    <option value="test">Test</option>
                                </select>
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="serverLocation">Location</label>
                                <input type="text" id="serverLocation" name="location" placeholder="Data center, rack, etc.">
                            </div>
                            <div class="form-group">
                                <label for="serverModel">Model</label>
                                <input type="text" id="serverModel" name="model" placeholder="PowerEdge R650, etc.">
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="serverServiceTag">Service Tag</label>
                                <input type="text" id="serverServiceTag" name="service_tag" placeholder="Dell service tag">
                            </div>
                            <div class="form-group">
                                <label for="serverTags">Tags</label>
                                <input type="text" id="serverTags" name="tags" placeholder="web, critical, production">
                            </div>
                        </div>
                        <div class="form-group">
                            <label for="serverNotes">Notes</label>
                            <textarea id="serverNotes" name="notes" rows="3" placeholder="Additional notes about this server"></textarea>
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-outline" onclick="this.closest('.modal').remove()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Add Server</button>
                        </div>
                    </form>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Handle form submission
        const form = document.getElementById('addServerForm');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            const serverData = {};
            
            for (let [key, value] of formData.entries()) {
                if (key === 'tags') {
                    serverData[key] = value.split(',').map(tag => tag.trim()).filter(tag => tag);
                } else {
                    serverData[key] = value;
                }
            }
            
            await this.addServer(serverData);
            modal.remove();
        });
    }
    
    async acknowledgeAlert(alertIndex) {
        try {
            const response = await fetch(`/api/fleet/alerts/${alertIndex}/acknowledge`, {
                method: 'POST', headers: this._headers(false)
            });
            if (response.ok) {
                this.showToast('Alert acknowledged', 'success');
                await this.refreshAlerts();
            }
        } catch (e) {
            this.showToast('Failed to acknowledge alert', 'error');
        }
    }
    
    viewAlertDetails(alertIndex) {
        const alert = this.alerts[alertIndex];
        if (!alert) {
            this.showToast('Alert not found', 'warning');
            return;
        }
        // Show alert details in a modal
        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.innerHTML = `
            <div class="modal-content" style="max-width:500px">
                <div class="modal-header">
                    <h3>Alert Details</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div style="margin-bottom:12px">
                        <span class="status-badge ${alert.type || 'warning'}">${(alert.type || 'warning').toUpperCase()}</span>
                    </div>
                    <p><strong>Server:</strong> ${alert.server_name || 'Unknown'}</p>
                    <p><strong>Metric:</strong> ${alert.metric || 'N/A'}</p>
                    <p><strong>Message:</strong> ${alert.message || 'No details'}</p>
                    <p><strong>Time:</strong> ${alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'Unknown'}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary btn-sm" onclick="fleetManager.acknowledgeAlert(${alertIndex}); this.closest('.modal').remove();">Acknowledge</button>
                    <button class="btn btn-secondary btn-sm" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
    }
    
    // New integration methods
    openTechnicianDashboard(serverId) {
        const server = this.servers.get(serverId);
        if (!server) {
            this.showToast('Server not found', 'error');
            return;
        }
        
        // Store server connection info in sessionStorage for the technician dashboard
        sessionStorage.setItem('fleetServerConnection', JSON.stringify({
            serverId: serverId,
            name: server.name,
            host: server.host,
            port: server.port || 443,
            username: server.username,
            environment: server.environment,
            tags: server.tags,
            fromFleet: true
        }));
        
        // Open technician dashboard in new tab
        const technicianUrl = `/technician?server=${serverId}&name=${encodeURIComponent(server.name)}`;
        window.open(technicianUrl, '_blank');
        
        this.showToast(`Opening Technician Dashboard for ${server.name}`, 'success');
        this.hideServerDetailsModal();
    }
    
    openRealtimeMonitor(serverId) {
        const server = this.servers.get(serverId);
        if (!server) {
            this.showToast('Server not found', 'error');
            return;
        }
        
        // Store server info for realtime monitor (key must match realtime.js)
        sessionStorage.setItem('activeServerConnection', JSON.stringify({
            host: server.host,
            username: server.username,
            port: server.port || 443,
            fromFleet: true
        }));
        
        // Open realtime monitor in new tab
        const monitorUrl = `/monitoring?server=${serverId}&name=${encodeURIComponent(server.name)}`;
        window.open(monitorUrl, '_blank');
        
        this.showToast(`Opening Real-time Monitor for ${server.name}`, 'success');
        this.hideServerDetailsModal();
    }
    
    async runDiagnostics(serverId) {
        const server = this.servers.get(serverId);
        if (!server) {
            this.showToast('Server not found', 'error');
            return;
        }
        
        this.showLoading(true);
        
        try {
            // Connect to server if not already connected
            if (server.status !== 'online') {
                const success = await this.connectServer(serverId);
                if (!success) {
                    throw new Error('Failed to connect to server');
                }
            }
            
            // Run diagnostics
            const response = await fetch(`/api/fleet/servers/${serverId}/diagnostics`, {
                method: 'POST',
                headers: this._headers()
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showToast(`Diagnostics started for ${server.name}`, 'success');
                
                // Open technician dashboard to show results
                setTimeout(() => {
                    this.openTechnicianDashboard(serverId);
                }, 2000);
            } else {
                throw new Error('Failed to start diagnostics');
            }
            
        } catch (error) {
            this.showToast('Failed to run diagnostics', 'error');
        } finally {
            this.showLoading(false);
        }
    }
}

// Initialize fleet manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.fleetManager = new FleetManager();
});
