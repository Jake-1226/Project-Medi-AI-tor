// Dell Server AI Agent - Frontend JavaScript

class DellAIAgent {
    constructor() {
        this.currentServer = null;
        this.fromFleet = false;
        this.fleetServerInfo = null;
        
        this.apiBase = '';
        this.websocket = null;
        this.actionLevel = 'read_only';
        this.rawLogs = [];
        this.rawLcLogs = [];
        this.maxLogs = 2000;
        this.inventory = {};
        this.monitoringInterval = null;
        this.monitoringSnapshots = [];
        this.lastDataRefresh = null;
        this._tabScrollPositions = {};
        
        // Auth token from login session
        this._authToken = sessionStorage.getItem('auth_token') || '';
        
        // Cache frequently accessed DOM elements to reduce getElementById calls
        this._dom = {};
        
        this.init();
    }
    
    /** Get a cached DOM element by ID. Lazily caches on first access. */
    _el(id) {
        if (!this._dom[id]) this._dom[id] = document.getElementById(id);
        return this._dom[id];
    }
    
    init() {
        this.setupEventListeners();
        this.setupWebSocket();
        this.loadSavedSettings();
        this.checkFleetServerConnection();
        this.updateUI();
        this.setupKeyboardShortcuts();
        this.injectAgentThinkingStyles();
        this._setQuickActionsEnabled(false);
        // P10: Show API status in sidebar
        this._checkApiHealth();
        // P6: Warn before navigating away while connected
        window.addEventListener('beforeunload', (e) => {
            if (this.currentServer) { e.preventDefault(); e.returnValue = ''; }
        });
    }

    async _checkApiHealth() {
        try {
            const t0 = Date.now();
            const r = await fetch('/api/health');
            const latency = Date.now() - t0;
            const d = await r.json();
            const el = document.getElementById('apiStatus');
            if (el) el.textContent = `API: ${d.status || 'ok'} · ${latency}ms`;
        } catch (_) {}
    }
    
    setupEventListeners() {
        // Connection form
        document.getElementById('connectBtn')?.addEventListener('click', () => this.connectToServer());
        document.getElementById('disconnectBtn')?.addEventListener('click', () => {
            if (this.currentServer) {
                this._showInlineConfirm(document.getElementById('actionResultContainer'),
                    `Disconnect from ${this.currentServer.host}?`, false,
                    () => this.disconnectFromServer());
            } else { this.disconnectFromServer(); }
        });
        
        // OS Connection form
        document.getElementById('osConnectBtn')?.addEventListener('click', () => this.connectToOS());
        document.getElementById('osDisconnectBtn')?.addEventListener('click', () => this.disconnectFromOS());
        
        // Action level selector (supports both old .action-level-btn and new .level-pill)
        document.querySelectorAll('.action-level-btn, .level-pill').forEach(btn => {
            btn.addEventListener('click', (e) => this.selectActionLevel(e.target.closest('.action-level-btn, .level-pill')));
        });
        
        // Quick actions
        document.getElementById('getServerInfoBtn')?.addEventListener('click', () => this.executeAction('get_full_inventory'));
        document.getElementById('collectLogsBtn')?.addEventListener('click', () => this.executeAction('collect_logs'));
        document.getElementById('healthCheckBtn')?.addEventListener('click', () => this.executeAction('health_check'));
        document.getElementById('performanceAnalysisBtn')?.addEventListener('click', () => this.executeAction('performance_analysis'));
        
        // Server actions
        document.getElementById('tsrExportBtn')?.addEventListener('click', () => this.executeServerAction('export_tsr'));
        document.getElementById('runDiagnosticsBtn')?.addEventListener('click', () => this.runDiagnostics('Express'));
        document.getElementById('gracefulShutdownBtn')?.addEventListener('click', () => this.confirmAndExecute('graceful_shutdown', 'Graceful Shutdown'));
        document.getElementById('powerCycleBtn')?.addEventListener('click', () => this.confirmAndExecute('force_restart', 'Power Cycle'));
        document.getElementById('vacCycleBtn')?.addEventListener('click', () => this.confirmAndExecute('virtual_ac_cycle', 'Virtual AC Cycle (Flea Power Drain)'));
        document.getElementById('resetIdracBtn')?.addEventListener('click', () => this.confirmAndExecute('reset_idrac', 'Reset iDRAC'));
        document.getElementById('supportAssistBtn')?.addEventListener('click', () => this.checkSupportAssist());
        
        // iDRAC availability check
        document.getElementById('checkIdracBtn')?.addEventListener('click', () => this.checkIdracAvailability());
        
        // F1: Banner expand button
        document.getElementById('bannerExpandBtn')?.addEventListener('click', () => this._expandBanner());
        // V1: Compact disconnect button
        document.getElementById('compactDisconnectBtn')?.addEventListener('click', () => {
            if (this.currentServer) {
                this._showInlineConfirm(document.getElementById('actionResultContainer'),
                    `Disconnect from ${this.currentServer.host}?`, false,
                    () => this.disconnectFromServer());
            }
        });
        
        // P4: Auto-clear input error state on focus
        document.querySelectorAll('.form-input, .form-select, .form-textarea').forEach(el => {
            el.addEventListener('focus', () => el.classList.remove('input-error'));
        });
        
        // SR# auto-save on blur
        document.getElementById('srNumber')?.addEventListener('blur', () => this.saveSrNumber());
        
        // Troubleshooting
        document.getElementById('startTroubleshootingBtn')?.addEventListener('click', () => this.startTroubleshooting());
        
        // Lifecycle logs
        document.getElementById('refreshLcLogsBtn')?.addEventListener('click', () => this.fetchLifecycleLogs());
        document.getElementById('lcSeverityFilter')?.addEventListener('change', () => this.renderFilteredLcLogs());
        let _lcSearchTimer = null;
        document.getElementById('lcSearchInput')?.addEventListener('input', () => {
            clearTimeout(_lcSearchTimer);
            _lcSearchTimer = setTimeout(() => this.renderFilteredLcLogs(), 200);
        });
        
        // Monitoring
        document.getElementById('startMonitoringBtn')?.addEventListener('click', () => this.startMonitoring());
        document.getElementById('stopMonitoringBtn')?.addEventListener('click', () => this.stopMonitoring());
        
        // Tabs (supports both old .tab and new .sidebar-link)
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchTab(e.target));
        });
        document.querySelectorAll('.sidebar-link[data-tab]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.switchTab(e.target.closest('.sidebar-link'));
            });
        });

        // Sidebar toggle
        document.getElementById('sidebarToggle')?.addEventListener('click', () => {
            document.getElementById('sidebar')?.classList.toggle('sidebar-collapsed');
            document.querySelector('.main-content')?.classList.toggle('main-expanded');
        });
        
        // Sub-tabs
        document.querySelectorAll('.sub-tab').forEach(st => {
            st.addEventListener('click', (e) => this.switchSubTab(e.target));
        });
        
        // Log filters
        document.getElementById('logSeverityFilter')?.addEventListener('change', () => this.renderFilteredLogs());
        // Log search with debounce for performance on large log sets
        let _logSearchTimer = null;
        document.getElementById('logSearchInput')?.addEventListener('input', () => {
            clearTimeout(_logSearchTimer);
            _logSearchTimer = setTimeout(() => this.renderFilteredLogs(), 200);
        });
        
        // Form submissions
        document.getElementById('connectionForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.connectToServer();
        });
        
        document.getElementById('troubleshootingForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.startTroubleshooting();
        });
        // Auto-grow investigation textarea
        const issueTA = document.getElementById('issueDescription');
        if (issueTA) issueTA.addEventListener('input', function() { this.style.height = 'auto'; this.style.height = Math.min(this.scrollHeight, 200) + 'px'; });

        // Agent Chat
        document.getElementById('agentChatFab')?.addEventListener('click', () => this.toggleChatPanel());
        document.getElementById('agentChatMinimize')?.addEventListener('click', () => this.toggleChatPanel());
        document.getElementById('agentChatForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendChatMessage();
        });
        
        // Initialize theme
        this.initTheme();
        document.querySelectorAll('.agent-suggest-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const chatInput = document.getElementById('agentChatInput');
                if (chatInput) { chatInput.value = chip.dataset.msg; this.sendChatMessage(); }
            });
        });
    }
    
    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws?token=${this._authToken || ''}`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                this.log('WebSocket connected', 'success');
                this._hideDisconnectBanner();
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (e) { /* ignore malformed WS messages */ }
            };
            
            this.websocket.onclose = () => {
                this.log('WebSocket disconnected', 'warning');
                // P7: Show disconnect banner if we had an active server
                if (this.currentServer) this._showDisconnectBanner();
                setTimeout(() => this.setupWebSocket(), 5000);
            };
            
            this.websocket.onerror = (error) => {
                this.log('WebSocket error', 'error');
            };
        } catch (error) {
            this.log('Failed to setup WebSocket', 'error');
        }
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'response':
                this.handleActionResponse(data.data);
                break;
            case 'troubleshooting_result':
                this.handleTroubleshootingResult(data.recommendations);
                break;
            case 'error':
                this.log(data.message, 'error');
                break;
            default:
                // Unknown WebSocket message type — silently ignore
        }
    }
    
    async connectToServer() {
        // Guard against double-click / double-submit
        const connectBtn = document.getElementById('connectBtn');
        if (connectBtn?.disabled || this._connectingInProgress) return;
        this._connectingInProgress = true;

        const hostEl = document.getElementById('serverHost');
        const userEl = document.getElementById('username');
        const passEl = document.getElementById('password');
        const host = hostEl?.value?.trim();
        const username = userEl?.value?.trim();
        const password = passEl?.value?.trim();
        const port = parseInt(document.getElementById('port')?.value) || 443;
        
        // Validate with visual feedback on empty fields
        let valid = true;
        [hostEl, userEl, passEl].forEach(el => { if (el) el.classList.remove('input-error'); });
        if (!host) { if (hostEl) hostEl.classList.add('input-error'); valid = false; }
        if (!username) { if (userEl) userEl.classList.add('input-error'); valid = false; }
        if (!password) { if (passEl) passEl.classList.add('input-error'); valid = false; }
        if (!valid) { this.showAlert('Fill in all connection fields.', 'warning', { title: 'Missing fields' }); return; }
        
        // Button loading state — prevent double-click
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');
        if (connectBtn) { connectBtn.disabled = true; connectBtn.textContent = 'Connecting...'; connectBtn.classList.add('btn-loading'); }
        this.showLoading(true, 'Connecting to iDRAC...');
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);
            const response = await fetch(`/api/connect`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ host, username, password, port }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            const result = await response.json();
            
            if (response.ok) {
                this.currentServer = { host, username, password, port };
                this.saveSettings();
                this.showAlert('Connected to server successfully!', 'success');
                this.log(`Connected to server: ${host}`, 'success');
                
                // Clear password field from DOM for security
                const pwField = document.getElementById('password');
                if (pwField) pwField.value = '';
                
                // P7: Update chat panel subtitle with connected server
                const chatSub = document.getElementById('agentChatSubtitle');
                if (chatSub) chatSub.textContent = `Connected to ${host}`;
                
                // Update button states
                if (connectBtn) { connectBtn.textContent = 'Connected'; connectBtn.disabled = true; connectBtn.classList.remove('btn-loading'); }
                if (disconnectBtn) disconnectBtn.disabled = false;
                
                // Update iDRAC status dot + panel state
                const idracDot = document.getElementById('idracStatusDot');
                if (idracDot) { idracDot.classList.add('connected'); idracDot.classList.remove('error'); }
                const idracPanel = document.getElementById('idracPanel');
                if (idracPanel) { idracPanel.classList.add('panel-connected'); idracPanel.classList.remove('panel-error'); }
                
                // Update topbar with server identity (click to copy host)
                const statusEl = document.querySelector('.topbar-connection');
                if (statusEl) {
                    statusEl.innerHTML = `<span class="status-indicator status-online"></span> 
                        <strong title="Click to copy" style="cursor:pointer" onclick="navigator.clipboard.writeText('${this.currentServer.host}').then(()=>app.showAlert('Copied ${this.currentServer.host}','info'))">${this.currentServer.host}</strong>
                        <span style="opacity:0.6;margin-left:4px">Connected</span>`;
                }
                
                // Update connection mode bar
                this.updateConnectionMode();

                // F1: Collapse connect banner to compact bar
                this._collapseBanner(host, result.server_info);

                // Auto-fetch all dashboard data
                setTimeout(() => this.fetchAllDashboardData(), 1000);
                // Start auto-refresh every 60 seconds
                this._startAutoRefresh();

                // F2: Scroll metrics into view after data arrives
                setTimeout(() => {
                    const metrics = document.getElementById('overviewMetricsContainer');
                    if (metrics) metrics.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }, 2000);

                // F8: Enable quick-action buttons
                this._setQuickActionsEnabled(true);

                // F9: Store connection for cross-page handoff (monitoring, fleet)
                sessionStorage.setItem('activeServerConnection', JSON.stringify({ host, username, port }));
            } else {
                this.showAlert(`Connection failed: ${result.detail}`, 'danger');
                this.log(`Connection failed: ${result.detail}`, 'error');
                if (connectBtn) { connectBtn.textContent = 'Connect iDRAC'; connectBtn.disabled = false; connectBtn.classList.remove('btn-loading'); }
                const idracDot = document.getElementById('idracStatusDot');
                if (idracDot) { idracDot.classList.add('error'); idracDot.classList.remove('connected'); }
                const idracPanel = document.getElementById('idracPanel');
                if (idracPanel) { idracPanel.classList.add('panel-error'); idracPanel.classList.remove('panel-connected'); }
            }
        } catch (error) {
            const msg = error.name === 'AbortError'
                ? 'Connection timed out after 30 seconds. Check that the iDRAC IP is correct and reachable.'
                : this._friendlyError(error);
            this.showAlert(msg, 'danger', { title: 'Connection failed', retry: () => this.connectToServer() });
            this.log(`Network error: ${error.message}`, 'error');
            if (connectBtn) { connectBtn.textContent = 'Connect iDRAC'; connectBtn.disabled = false; connectBtn.classList.remove('btn-loading'); }
        } finally {
            this.showLoading(false);
            this._connectingInProgress = false;
        }
    }
    
    async disconnectFromServer() {
        this._stopAutoRefresh();
        this.stopMonitoring();
        try {
            this.currentServer = null;
            this.showAlert('Disconnected from server', 'info');
            this.log('Disconnected from server', 'info');
            this.saveSettings();
            
            // Reset button states
            const connectBtn = document.getElementById('connectBtn');
            const disconnectBtn = document.getElementById('disconnectBtn');
            if (connectBtn) { connectBtn.textContent = 'Connect iDRAC'; connectBtn.disabled = false; }
            if (disconnectBtn) disconnectBtn.disabled = true;
            
            // Reset iDRAC status dot + panel state
            const idracDot = document.getElementById('idracStatusDot');
            if (idracDot) { idracDot.classList.remove('connected', 'error'); }
            const idracPanel = document.getElementById('idracPanel');
            if (idracPanel) { idracPanel.classList.remove('panel-connected', 'panel-error'); }
            
            // F1: Expand banner back to full form
            this._expandBanner();
            
            // F8: Disable quick-action buttons
            this._setQuickActionsEnabled(false);
            
            // F9: Clear cross-page handoff
            sessionStorage.removeItem('activeServerConnection');
            
            // Try to disconnect via API
            try {
                const response = await fetch(`/api/disconnect`, {
                    method: 'POST',
                    headers: this._getAuthHeaders()
                });
                const result = await response.json();
                if (response.ok) {
                    this.log('API disconnect successful', 'success');
                }
            } catch (error) {
                this.log('API disconnect not available, using UI-only disconnect', 'info');
            }
            this.updateConnectionMode();
            
            // Reset topbar connection status
            const statusEl = document.querySelector('.topbar-connection');
            if (statusEl) {
                statusEl.innerHTML = `<span class="status-indicator status-offline"></span> Disconnected`;
            }
        } catch (error) {
            this.showAlert(`Disconnect error: ${this._friendlyError(error)}`, 'danger');
            this.log(`Disconnect error: ${error.message}`, 'error');
        } finally {
            this.showLoading(false);
        }
    }
    
    _startAutoRefresh() {
        this._stopAutoRefresh();
        this._autoRefreshTimer = setInterval(() => {
            if (this.currentServer) {
                this.fetchAllDashboardData(true); // silent auto-refresh
            }
        }, 60000);
    }

    _stopAutoRefresh() {
        if (this._autoRefreshTimer) {
            clearInterval(this._autoRefreshTimer);
            this._autoRefreshTimer = null;
        }
    }

    // ─── F1: Banner collapse / expand ────────────────────────────
    _collapseBanner(host, serverInfo) {
        const banner = document.getElementById('connectBanner');
        if (!banner) return;
        banner.classList.add('banner-connected');
        const serverId = document.getElementById('compactServerId');
        if (serverId) serverId.textContent = host;
        const model = document.getElementById('compactServerModel');
        if (model && serverInfo) {
            const parts = [];
            if (serverInfo.model) parts.push(serverInfo.model);
            if (serverInfo.service_tag) parts.push(serverInfo.service_tag);
            if (serverInfo.power_state) parts.push(`Power: ${serverInfo.power_state}`);
            model.textContent = parts.length ? `(${parts.join(' · ')})` : '';
        }
    }

    _expandBanner() {
        const banner = document.getElementById('connectBanner');
        if (banner) banner.classList.remove('banner-connected');
    }

    // ─── F5: Inline confirmation UX ──────────────────────────────
    _showInlineConfirm(anchorEl, message, isDanger, onConfirm) {
        // Remove any existing inline-confirm in the same area
        const previousFocus = document.activeElement;
        document.querySelectorAll('.inline-confirm').forEach(el => el.remove());
        const div = document.createElement('div');
        div.className = `inline-confirm${isDanger ? '' : ' inline-confirm-warn'}`;
        div.innerHTML = `
            <span class="confirm-msg">${isDanger ? '⚠️ ' : ''}${message}</span>
            <button class="confirm-yes">${isDanger ? 'Yes, proceed' : 'Confirm'}</button>
            <button class="confirm-no">Cancel</button>`;
        const yesBtn = div.querySelector('.confirm-yes');
        const noBtn = div.querySelector('.confirm-no');
        // Double-click prevention: disable after first click
        yesBtn.addEventListener('click', () => { yesBtn.disabled = true; noBtn.disabled = true; onConfirm(); div.remove(); });
        noBtn.addEventListener('click', () => { div.remove(); if (previousFocus) previousFocus.focus(); });
        if (anchorEl) {
            anchorEl.style.display = 'block';
            anchorEl.innerHTML = '';
            anchorEl.appendChild(div);
            anchorEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            // Focus the cancel button for keyboard users (safer default)
            requestAnimationFrame(() => noBtn.focus());
        } else {
            const alert = document.getElementById('alertContainer');
            if (alert) alert.appendChild(div);
        }
    }

    // ─── F8: Quick-action enable/disable ─────────────────────────
    _setQuickActionsEnabled(enabled) {
        const ids = ['healthCheckBtn', 'getServerInfoBtn', 'collectLogsBtn', 'performanceAnalysisBtn',
                     'gracefulShutdownBtn', 'powerCycleBtn', 'vacCycleBtn', 'resetIdracBtn'];
        ids.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = !enabled;
        });
    }

    // ─── P7: Disconnection recovery banner ───────────────────────
    _showDisconnectBanner() {
        if (document.getElementById('disconnectBanner')) return; // already shown
        const container = document.getElementById('alertContainer');
        if (!container) return;
        const banner = document.createElement('div');
        banner.className = 'disconnect-banner';
        banner.id = 'disconnectBanner';
        banner.innerHTML = `
            <span class="disconnect-icon">⚠</span>
            <span class="disconnect-msg">Connection interrupted — real-time updates paused. Reconnecting...</span>
            <button class="btn btn-sm btn-primary" onclick="app.fetchAllDashboardData(); document.getElementById('disconnectBanner')?.remove();">Refresh now</button>
            <button class="btn btn-sm btn-outline" onclick="document.getElementById('disconnectBanner')?.remove()">Dismiss</button>`;
        container.prepend(banner);
    }

    _hideDisconnectBanner() {
        document.getElementById('disconnectBanner')?.remove();
    }

    _getAuthHeaders() {
        // Token is in HTTP-only cookie, automatically sent by browser
        // But also support explicit token for API calls
        const token = this._authToken || '';
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return headers;
    }

    // ─── OS Connection via SSH ────────────────────────────────
    async connectToOS() {
        const host = document.getElementById('osHost')?.value?.trim();
        const username = document.getElementById('osUsername')?.value?.trim();
        const password = document.getElementById('osPassword')?.value;
        const port = parseInt(document.getElementById('osPort')?.value) || 22;
        
        if (!host || !username) {
            this.showAlert('OS Host and Username are required', 'warning');
            return;
        }
        
        const btn = document.getElementById('osConnectBtn');
        const resultDiv = document.getElementById('osConnectResult');
        if (btn) { btn.disabled = true; btn.textContent = 'Connecting...'; }
        
        try {
            const response = await fetch('/api/os/connect', {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ host, username, password, port })
            });
            const data = await response.json();
            
            if (response.ok && data.status === 'success') {
                this.osConnected = true;
                this.osInfo = data.os_info;
                
                const dot = document.getElementById('osStatusDot');
                if (dot) dot.classList.add('connected');
                const osPanel = document.getElementById('osPanel');
                if (osPanel) { osPanel.classList.add('panel-connected'); osPanel.classList.remove('panel-error'); }
                
                const disconnectBtn = document.getElementById('osDisconnectBtn');
                if (disconnectBtn) disconnectBtn.disabled = false;
                
                if (resultDiv) {
                    resultDiv.style.display = 'block';
                    resultDiv.innerHTML = `<div class="alert alert-success">Connected to ${data.os_type || 'OS'} - ${data.os_info?.hostname || host}</div>`;
                }
                
                this.showAlert(`Connected to OS (${data.os_type}) via SSH`, 'success');
                this.log(`SSH connected to ${host}:${port} (${data.os_type})`, 'success');
            } else {
                throw new Error(data.detail || 'SSH connection failed');
            }
        } catch (error) {
            const dot = document.getElementById('osStatusDot');
            if (dot) { dot.classList.remove('connected'); dot.classList.add('error'); }
            const osPanel = document.getElementById('osPanel');
            if (osPanel) { osPanel.classList.add('panel-error'); osPanel.classList.remove('panel-connected'); }
            if (resultDiv) {
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = `<div class="alert alert-danger">${error.message}</div>`;
            }
            this.showAlert(`OS connection failed: ${this._friendlyError(error)}`, 'danger', { title: 'SSH error' });
            this.log(`SSH connection failed: ${error.message}`, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Connect OS'; }
            this.updateConnectionMode();
        }
    }
    
    async disconnectFromOS() {
        try {
            await fetch('/api/os/disconnect', { method: 'POST' });
            this.osConnected = false;
            this.osInfo = null;
            
            const dot = document.getElementById('osStatusDot');
            if (dot) { dot.classList.remove('connected', 'error'); }
            const osPanel = document.getElementById('osPanel');
            if (osPanel) { osPanel.classList.remove('panel-connected', 'panel-error'); }
            const disconnectBtn = document.getElementById('osDisconnectBtn');
            if (disconnectBtn) disconnectBtn.disabled = true;
            const resultDiv = document.getElementById('osConnectResult');
            if (resultDiv) resultDiv.style.display = 'none';
            
            this.showAlert('SSH disconnected', 'info');
            this.log('SSH disconnected', 'info');
        } catch (error) {
            this.log(`SSH disconnect error: ${error.message}`, 'error');
        }
        this.updateConnectionMode();
    }
    
    async executeOSAction(action, params = {}) {
        if (!this.osConnected) {
            this.showAlert('Connect to OS via SSH first', 'warning');
            return null;
        }
        
        try {
            const response = await fetch('/api/os/execute', {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action, parameters: params })
            });
            const data = await response.json();
            if (data.status === 'success') return data.result;
            throw new Error(data.detail || 'OS command failed');
        } catch (error) {
            this.log(`OS action ${action} failed: ${error.message}`, 'error');
            return null;
        }
    }
    
    async updateConnectionMode() {
        try {
            const response = await fetch('/api/connection/status');
            const data = await response.json();
            if (data.status !== 'success') return;
            
            const conn = data.connection;
            const modeBar = document.getElementById('connectionModeBar');
            const modeBadge = document.getElementById('connectionModeBadge');
            const modeFeatures = document.getElementById('connectionModeFeatures');
            
            if (modeBar) modeBar.style.display = conn.mode !== 'disconnected' ? 'flex' : 'none';
            if (modeBadge) {
                modeBadge.textContent = conn.mode.replace('_', ' ');
                modeBadge.className = `mode-badge ${conn.mode}`;
            }
            if (modeFeatures && conn.features) {
                const available = Object.entries(conn.features).filter(([,v]) => v.available).length;
                const total = Object.keys(conn.features).length;
                modeFeatures.textContent = `${available}/${total} features available`;
            }
            
            // Update iDRAC status dot
            const idracDot = document.getElementById('idracStatusDot');
            if (idracDot) {
                idracDot.classList.toggle('connected', conn.idrac.connected);
                idracDot.classList.toggle('error', !conn.idrac.connected && this.currentServer);
            }
        } catch (error) {
            // Silently fail - connection status is informational
        }
    }
    
    async executeAction(command, parameters = {}) {
        if (!this._requireConnection('running actions')) return;
        
        // Visual feedback on quick action buttons
        const btnMap = {
            'get_full_inventory': 'getServerInfoBtn',
            'collect_logs': 'collectLogsBtn',
            'health_check': 'healthCheckBtn',
            'performance_analysis': 'performanceAnalysisBtn',
        };
        const btnId = btnMap[command];
        const btn = btnId ? document.getElementById(btnId) : null;
        if (btn) {
            btn.disabled = true;
            btn._origHTML = btn.innerHTML;
            btn.classList.add('btn-loading');
        }
        
        this.showLoading(true);
        this.log(`Executing action: ${command}`, 'info');
        
        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({
                    action: command,
                    action_level: this.actionLevel,
                    parameters: parameters
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                this.handleActionResponse(result.result);
                this.log(`✅ ${command} completed successfully`, 'success');
                // Flash success on button
                if (btn) {
                    btn.classList.remove('btn-loading');
                    btn.classList.add('btn-success');
                    btn.innerHTML = '✅ Done';
                    setTimeout(() => { btn.classList.remove('btn-success'); btn.innerHTML = btn._origHTML; }, 2500);
                }
            } else {
                // Enhanced error messages with context
                let errorMsg = result.detail || 'Unknown error';
                if (errorMsg.includes('timeout')) errorMsg += ' — Check iDRAC responsiveness';
                else if (errorMsg.includes('auth')) errorMsg += ' — Verify credentials';
                else if (errorMsg.includes('refused')) errorMsg += ' — Check network/firewall';
                this.log(`❌ ${command} failed: ${errorMsg}`, 'error');
                this.showAlert(`Action failed: ${errorMsg}`, 'danger');
                // Flash error on button
                if (btn) {
                    btn.classList.remove('btn-loading');
                    btn.classList.add('btn-error');
                    btn.innerHTML = '❌ Failed';
                    setTimeout(() => { btn.classList.remove('btn-error'); btn.innerHTML = btn._origHTML; }, 3000);
                }
            }
        } catch (error) {
            this.log(`❌ Network error during ${command}: ${error.message}`, 'error');
            this.showAlert(this._friendlyError(error), 'danger', {
                title: 'Action failed',
                retry: () => this.executeAction(command, parameters)
            });
            if (btn) {
                btn.classList.remove('btn-loading');
                btn.classList.add('btn-error');
                btn.innerHTML = '❌ Error';
                setTimeout(() => { btn.classList.remove('btn-error'); btn.innerHTML = btn._origHTML; }, 3000);
            }
        } finally {
            this.showLoading(false);
            if (btn) btn.disabled = false;
        }
    }
    
    async startTroubleshooting() {
        const issueDescription = document.getElementById('issueDescription').value;
        if (!this._requireConnection('starting investigation')) return;
        if (!issueDescription) { this.showAlert('Describe the issue to investigate.', 'warning'); return; }

        const tsTab = document.querySelector('[data-tab="troubleshooting"]');
        if (tsTab) this.switchTab(tsTab);
        const recSubTab = document.querySelector('[data-subtab="ts-recommendations"]');
        if (recSubTab) this.switchSubTab(recSubTab);

        const container = document.getElementById('recommendationsContainer');
        if (!container) return;

        // ── Build live agentic investigation panel ────────────────
        container.innerHTML = `
            <div class="agent-investigation" id="agentPanel">
                <div class="agent-header">
                    <div class="agent-header-left">
                        <span class="agent-pulse"></span>
                        <h4>🧠 AI Agent Investigating</h4>
                    </div>
                    <span class="agent-issue">"${issueDescription}"</span>
                </div>
                <div class="agent-feed" id="agentFeed"></div>
                <div class="agent-status" id="agentStatus">Forming hypotheses...</div>
            </div>`;
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });

        const feed = document.getElementById('agentFeed');
        const statusEl = document.getElementById('agentStatus');
        const delay = (ms) => new Promise(r => setTimeout(r, ms));

        const addFeedItem = (type, html) => {
            const div = document.createElement('div');
            div.className = `agent-feed-item agent-fi-${type}`;
            div.innerHTML = html;
            feed.appendChild(div);
            div.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        };

        this.log('🧠 Starting agentic AI investigation...', 'info');

        try {
            if (statusEl) statusEl.textContent = 'Connecting to /investigate endpoint...';

            const response = await fetch(`/api/investigate`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({
                    server_info: this.currentServer,
                    issue_description: issueDescription,
                    action_level: this.actionLevel
                })
            });
            const result = await response.json();

            if (response.ok && result.agentic) {
                // Render the reasoning chain as a live feed
                const chain = result.reasoning_chain || result.diagnosis?.reasoning_chain || [];
                const diagnosis = result.diagnosis || {};

                for (let i = 0; i < chain.length; i++) {
                    const t = chain[i];
                    await delay(120);

                    // Thought
                    let thoughtHtml = `<div class="agent-thought-head">💭 Step ${t.step}</div><p class="agent-thought-text">${t.reasoning}</p>`;
                    if (t.hypotheses && t.hypotheses.length) {
                        thoughtHtml += '<div class="agent-hyp-list">';
                        t.hypotheses.forEach(h => {
                            const pct = Math.round(h.confidence * 100);
                            const barCls = pct >= 70 ? 'agent-bar-high' : pct >= 40 ? 'agent-bar-med' : 'agent-bar-low';
                            thoughtHtml += `<div class="agent-hyp-row"><span class="agent-hyp-name">${h.description}</span><div class="agent-hyp-bar"><div class="agent-hyp-fill ${barCls}" style="width:${pct}%"></div></div><span class="agent-hyp-pct">${pct}%</span></div>`;
                        });
                        thoughtHtml += '</div>';
                    }
                    if (t.ruled_out && t.ruled_out.length) {
                        thoughtHtml += `<div class="agent-ruled-out">❌ Ruled out: ${t.ruled_out.join(', ')}</div>`;
                    }
                    if (t.next_action) {
                        thoughtHtml += `<div class="agent-next-action">🔧 Next: <strong>${t.next_action}</strong> — ${t.next_action_reason || ''}</div>`;
                    }
                    if (t.conclusion) {
                        thoughtHtml += `<div class="agent-conclusion">✅ <strong>${t.conclusion}</strong></div>`;
                    }
                    addFeedItem('thought', thoughtHtml);
                    if (statusEl) statusEl.textContent = t.conclusion ? 'Investigation complete' : `Step ${t.step}: ${t.next_action || 'Analyzing...'}`;
                }

                // Show diagnosis summary in the feed
                if (diagnosis.root_cause) {
                    await delay(200);
                    let diagHtml = `<div class="agent-diag-header">📋 DIAGNOSIS</div>`;
                    diagHtml += `<div class="agent-diag-cause"><strong>Root Cause:</strong> ${diagnosis.root_cause}</div>`;
                    diagHtml += `<div class="agent-diag-conf">Confidence: <strong>${diagnosis.confidence}%</strong> | Category: ${diagnosis.category || '?'}</div>`;
                    if (diagnosis.evidence_chain?.length) {
                        diagHtml += '<div class="agent-evidence"><strong>Evidence:</strong><ul>';
                        diagnosis.evidence_chain.forEach(e => {
                            diagHtml += `<li class="${e.supports ? 'agent-ev-support' : 'agent-ev-refute'}">${e.supports ? '✅' : '❌'} ${e.description} <em>(${e.strength})</em></li>`;
                        });
                        diagHtml += '</ul></div>';
                    }
                    if (diagnosis.remediation_steps?.length) {
                        diagHtml += `<div class="agent-remediation"><strong>🔧 Remediation: ${diagnosis.workflow_name || ''}</strong><ol>`;
                        diagnosis.remediation_steps.forEach(s => diagHtml += `<li>${s}</li>`);
                        diagHtml += '</ol></div>';
                    }
                    if (diagnosis.ruled_out?.length) {
                        diagHtml += `<div class="agent-ruled-summary">Ruled out: ${diagnosis.ruled_out.map(r => r.description).join(', ')}</div>`;
                    }
                    addFeedItem('diagnosis', diagHtml);
                }

                if (statusEl) { statusEl.innerHTML = '<span class="agent-done-badge">✅ Investigation Complete</span> — Scroll down for full deep-dive report'; }

                await delay(500);

                // Render business value metrics bar
                if (result.metrics) {
                    this.renderInvestigationMetrics(result.metrics, container);
                }

                // Now render the full deep-dive report below the investigation feed
                this.renderFullAnalysisReport(result, issueDescription);
                this.log(`🧠 Agentic investigation complete — ${(result.recommendations||[]).length} recommendations, confidence: ${diagnosis.confidence || '?'}%`, 'success');
                // Auto-scroll results into view
                container.scrollIntoView({ behavior: 'smooth', block: 'start' });

            } else if (response.ok) {
                // Fallback: non-agentic response (legacy endpoint returned)
                this.renderFullAnalysisReport(result, issueDescription);
                this.log(`🔍 Analysis complete — ${(result.recommendations||[]).length} recommendations`, 'success');
                container.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } else {
                container.innerHTML = `<div class="ts-error"><h4>❌ Investigation Failed</h4><p>${result.detail}</p></div>`;
                this.log(`❌ Investigation failed: ${result.detail}`, 'error');
            }
        } catch (error) {
            container.innerHTML = `<div class="ts-error"><h4>❌ Network Error</h4><p>${error.message}</p></div>`;
            this.log(`❌ Investigation error: ${error.message}`, 'error');
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // KEYBOARD SHORTCUTS
    // ═══════════════════════════════════════════════════════════════

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+K or Cmd+K to toggle chat panel
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.toggleChatPanel();
            }
            // Escape to close chat panel
            if (e.key === 'Escape') {
                const panel = document.getElementById('agentChatPanel');
                if (panel && panel.classList.contains('agent-chat-open')) {
                    this.toggleChatPanel();
                }
                // Also dismiss inline confirms
                document.querySelectorAll('.inline-confirm').forEach(el => el.remove());
            }
            // Ctrl+R or Cmd+R to refresh current tab data
            if ((e.ctrlKey || e.metaKey) && e.key === 'r' && this.currentServer) {
                e.preventDefault();
                this.fetchAllDashboardData();
                this.showAlert('Refreshing data...', 'info');
            }
        });
        // F6: Show keyboard shortcut legend briefly on first load
        const legend = document.getElementById('kbdLegend');
        if (legend && !sessionStorage.getItem('kbdLegendShown')) {
            setTimeout(() => { legend.classList.add('visible'); }, 2000);
            setTimeout(() => { legend.classList.remove('visible'); sessionStorage.setItem('kbdLegendShown', '1'); }, 8000);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // AGENT THINKING STEPS — Injected CSS for SSE streaming UI
    // ═══════════════════════════════════════════════════════════════

    injectAgentThinkingStyles() {
        if (document.getElementById('agent-thinking-styles')) return;
        const style = document.createElement('style');
        style.id = 'agent-thinking-styles';
        style.textContent = `
            .agent-thinking-steps {
                display: flex;
                flex-direction: column;
                gap: 6px;
                padding: 4px 0;
            }
            .agent-think-step {
                display: flex;
                align-items: flex-start;
                gap: 6px;
                padding: 4px 8px;
                border-left: 3px solid var(--accent-blue, #3b82f6);
                background: rgba(59,130,246,0.06);
                border-radius: 0 6px 6px 0;
                font-size: 0.88em;
                line-height: 1.45;
                animation: agentStepFadeIn 0.3s ease-out;
            }
            .agent-think-step span:first-child {
                flex-shrink: 0;
            }
            @keyframes agentStepFadeIn {
                from { opacity: 0; transform: translateY(6px); }
                to   { opacity: 1; transform: translateY(0); }
            }
            .agent-followups {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                padding: 8px 0 4px;
            }
            .agent-followup-chip {
                background: var(--surface-2, #f1f5f9);
                border: 1px solid var(--border-color, #e2e8f0);
                border-radius: 16px;
                padding: 4px 12px;
                font-size: 0.82em;
                cursor: pointer;
                transition: all 0.15s;
                color: var(--text-primary, #1e293b);
            }
            .agent-followup-chip:hover {
                background: var(--accent-blue, #3b82f6);
                color: #fff;
                border-color: var(--accent-blue, #3b82f6);
            }
        `;
        document.head.appendChild(style);
    }

    // ═══════════════════════════════════════════════════════════════
    // AGENT CHAT — Multi-turn conversational interface
    // ═══════════════════════════════════════════════════════════════

    toggleChatPanel() {
        const panel = document.getElementById('agentChatPanel');
        const fab = document.getElementById('agentChatFab');
        if (!panel) return;
        const isOpen = panel.classList.toggle('agent-chat-open');
        if (fab) fab.style.display = isOpen ? 'none' : 'flex';
        if (isOpen) {
            document.getElementById('agentChatInput')?.focus();
        }
    }

    async sendChatMessage() {
        const input = document.getElementById('agentChatInput');
        const sendBtn = document.getElementById('agentChatSend');
        const msg = input?.value?.trim();
        if (!msg || !this.currentServer) {
            if (!this.currentServer) this.addChatMsg('system', 'Please connect to a server first.');
            return;
        }

        const container = document.getElementById('agentChatMessages');
        input.value = '';

        // Disable input during send to prevent concurrent messages
        if (input) input.disabled = true;
        if (sendBtn) sendBtn.disabled = true;

        // Hide suggestion chips after first message
        const sug = document.getElementById('agentChatSuggestions');
        if (sug) sug.style.display = 'none';

        // Add user message
        this.addChatMsg('user', msg);

        // Add typing indicator
        const typingId = this.addChatMsg('agent-typing', '');
        const subtitle = document.getElementById('agentChatSubtitle');
        if (subtitle) subtitle.textContent = 'Thinking...';
        if (container) container.scrollTop = container.scrollHeight;

        try {
            const response = await fetch('/chat/stream', {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ message: msg, action_level: this.actionLevel })
            });

            // Remove typing indicator
            document.getElementById(typingId)?.remove();

            if (response.headers.get('content-type')?.includes('text/event-stream')) {
                // ── SSE streaming response ──────────────────────────
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let thinkingDiv = null;

                if (subtitle) subtitle.textContent = 'Streaming...';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        try {
                            const event = JSON.parse(line.slice(6));
                            const evType = event.event || event.type;
                            const evData = event.data || {};

                            if (evType === 'thought' || evType === 'action_start' || evType === 'action_result') {
                                if (!thinkingDiv) {
                                    thinkingDiv = document.createElement('div');
                                    thinkingDiv.className = 'agent-chat-msg agent-msg-agent';
                                    thinkingDiv.innerHTML = '<div class="agent-msg-content agent-thinking-steps"></div>';
                                    container.appendChild(thinkingDiv);
                                }
                                const stepsDiv = thinkingDiv.querySelector('.agent-thinking-steps');
                                const icon = evType === 'thought' ? '🤔' : evType === 'action_start' ? '🔍' : '📊';
                                const text = evData.summary || evData.thought || evData.tool || evData.message || JSON.stringify(evData);
                                stepsDiv.innerHTML += `<div class="agent-think-step"><span>${icon}</span> <span>${this.escapeHtml(typeof text === 'string' ? text : JSON.stringify(text))}</span></div>`;
                                container.scrollTop = container.scrollHeight;
                                if (subtitle) subtitle.textContent = evType === 'thought' ? 'Thinking...' : evType === 'action_start' ? 'Running action...' : 'Processing result...';
                            }

                            if (evType === 'complete') {
                                const result = evData;
                                if (thinkingDiv) {
                                    thinkingDiv.style.opacity = '0.6';
                                    thinkingDiv.style.fontSize = '0.82em';
                                }
                                const responseText = result.message || result.summary || (typeof result === 'string' ? result : JSON.stringify(result));
                                this._addAgentChatResponse(container, responseText, result);
                                if (subtitle) subtitle.textContent = 'Ready';
                                this.log(`🧠 Chat (streamed): ${(responseText || '').substring(0, 80)}`, 'info');
                            }
                        } catch (e) { /* skip malformed SSE events */ }
                    }
                }
                // If no complete event came, try to parse leftover buffer
                if (!thinkingDiv && buffer) {
                    try {
                        const finalData = JSON.parse(buffer.replace(/^data:\s*/, ''));
                        this._addAgentChatResponse(container, finalData.message || JSON.stringify(finalData), finalData);
                    } catch(e) { /* ignore */ }
                }
                if (subtitle && subtitle.textContent === 'Streaming...') subtitle.textContent = 'Ready';

            } else {
                // ── Regular JSON response fallback (original /api/chat) ──
                const result = await response.json();

                if (result.type === 'error') {
                    this.addChatMsg('system', result.message);
                    if (subtitle) subtitle.textContent = 'Error';
                    return;
                }

                // Render agent response based on type
                if (result.type === 'investigation') {
                    this.addChatMsg('agent', result.message);
                    if (result.data) this.renderInvestigationFromChat(result.data, msg);
                    if (result.metrics) this.renderChatMetrics(result.metrics);
                    if (subtitle) subtitle.textContent = 'Investigation complete';
                    this.showChatFollowUps(['Why do you think that?', 'Dig deeper into temperatures', 'Can you fix this?', 'Show me the evidence']);

                } else if (result.type === 'remediation_proposal') {
                    this.renderRemediationProposal(result);
                    if (subtitle) subtitle.textContent = 'Awaiting approval';

                } else if (result.type === 'remediation_result') {
                    this.renderRemediationResult(result);
                    if (subtitle) subtitle.textContent = 'Remediation executed';

                } else if (result.type === 'follow_up') {
                    this.addChatMsg('agent', result.message);
                    if (result.data?.hypotheses) this.renderChatHypotheses(result.data.hypotheses);
                    if (subtitle) subtitle.textContent = 'Ready';
                    this.showChatFollowUps(['Can you fix this?', 'What else should I check?', 'Explain the evidence']);

                } else {
                    this.addChatMsg('agent', result.message);
                    if (result.metrics) this.renderChatMetrics(result.metrics);
                    if (subtitle) subtitle.textContent = 'Ready';
                }

                this.log(`🧠 Chat: [${result.type}] ${(result.message||'').substring(0, 80)}`, 'info');
            }
        } catch (error) {
            document.getElementById(typingId)?.remove();
            this.addChatMsg('system', `Network error: ${this._friendlyError(error)}`);
            if (subtitle) subtitle.textContent = 'Error';
        } finally {
            // Re-enable input after send completes
            if (input) { input.disabled = false; input.focus(); }
            if (sendBtn) sendBtn.disabled = false;
            // Always reset subtitle after send completes
            if (subtitle) {
                subtitle.textContent = this.currentServer ? `Connected to ${this.currentServer.host}` : 'Ready';
            }
        }
        if (container) container.scrollTop = container.scrollHeight;
    }

    addChatMsg(role, text) {
        const container = document.getElementById('agentChatMessages');
        if (!container) return '';
        text = text || '';
        const id = 'chat-msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        const div = document.createElement('div');
        div.id = id;
        div.className = `agent-chat-msg agent-msg-${role}`;

        if (role === 'agent-typing') {
            div.innerHTML = '<div class="agent-msg-content"><span class="agent-typing-dots"><span>.</span><span>.</span><span>.</span></span></div>';
        } else if (role === 'user') {
            div.innerHTML = `<div class="agent-msg-content">${this.escapeHtml(text)}</div>`;
        } else {
            // agent, system — render with line breaks
            const formatted = text.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            div.innerHTML = `<div class="agent-msg-content">${formatted}</div>`;
        }

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return id;
    }

    escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = text;
        return d.innerHTML;
    }

    formatChatResponse(text) {
        if (!text) return '';
        return text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    _addAgentChatResponse(container, text, data) {
        const formatted = this.formatChatResponse(text);
        const div = document.createElement('div');
        div.className = 'agent-chat-msg agent-msg-agent';
        div.innerHTML = `<div class="agent-msg-content">${formatted}</div>`;
        container.appendChild(div);

        // Show follow-up suggestions if available
        const followups = data?.follow_up_suggestions || data?.data?.follow_up_suggestions;
        if (followups && followups.length) {
            this.showChatFollowUps(followups.slice(0, 4));
        }
        container.scrollTop = container.scrollHeight;
    }

    showChatFollowUps(options) {
        const container = document.getElementById('agentChatMessages');
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'agent-chat-followups';
        div.innerHTML = options.map(o => `<button class="agent-followup-chip">${o}</button>`).join('');
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        div.querySelectorAll('.agent-followup-chip').forEach(btn => {
            btn.addEventListener('click', () => {
                const chatInput = document.getElementById('agentChatInput');
                if (chatInput) { chatInput.value = btn.textContent; this.sendChatMessage(); }
                div.remove();
            });
        });
    }

    renderChatMetrics(metrics) {
        const el = document.getElementById('agentChatMetrics');
        if (!el || !metrics) return;
        el.style.display = 'block';
        const timeSaved = Math.round(metrics.time_saved_minutes || 0);
        const cost = Math.round(metrics.estimated_cost_saved || 0).toLocaleString();
        const agentTime = Math.round(metrics.investigation_time_seconds || 0);
        el.innerHTML = `
            <div class="agent-metrics-row">
                <div class="agent-metric"><span class="agent-metric-val">${agentTime}s</span><span class="agent-metric-lbl">AI Time</span></div>
                <div class="agent-metric"><span class="agent-metric-val">${timeSaved}m</span><span class="agent-metric-lbl">Time Saved</span></div>
                <div class="agent-metric"><span class="agent-metric-val">$${cost}</span><span class="agent-metric-lbl">Cost Saved</span></div>
                <div class="agent-metric"><span class="agent-metric-val">${metrics.facts_collected || 0}</span><span class="agent-metric-lbl">Data Points</span></div>
                <div class="agent-metric"><span class="agent-metric-val">${metrics.escalation_avoided ? '✅' : '—'}</span><span class="agent-metric-lbl">Escalation Avoided</span></div>
                <div class="agent-metric"><span class="agent-metric-val">${metrics.truck_roll_avoided ? '✅' : '—'}</span><span class="agent-metric-lbl">Truck Roll Avoided</span></div>
            </div>`;
    }

    renderChatHypotheses(hypotheses) {
        if (!hypotheses?.length) return;
        const container = document.getElementById('agentChatMessages');
        const div = document.createElement('div');
        div.className = 'agent-chat-msg agent-msg-agent';
        let html = '<div class="agent-msg-content"><div class="agent-hyp-list">';
        hypotheses.forEach(h => {
            const pct = Math.round(h.confidence * 100);
            const cls = pct >= 70 ? 'agent-bar-high' : pct >= 40 ? 'agent-bar-med' : 'agent-bar-low';
            html += `<div class="agent-hyp-row"><span class="agent-hyp-name">${h.description}</span><div class="agent-hyp-bar"><div class="agent-hyp-fill ${cls}" style="width:${pct}%"></div></div><span class="agent-hyp-pct">${pct}%</span></div>`;
        });
        html += '</div></div>';
        div.innerHTML = html;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    renderRemediationProposal(result) {
        const plan = result.plan || {};
        let html = `<div class="agent-msg-content">`;
        html += `<div class="agent-remediation-card">`;
        html += `<div class="agent-remed-header">🔧 Remediation Plan: ${plan.workflow || 'Custom'}</div>`;
        html += `<div class="agent-remed-cause">For: ${plan.root_cause || '?'} (${plan.confidence || 0}% confidence)</div>`;
        html += `<div class="agent-remed-risk">Risk: <span class="agent-remed-risk-${plan.risk || 'low'}">${(plan.risk || 'low').toUpperCase()}</span></div>`;
        if (plan.safe_steps?.length) {
            html += '<div class="agent-remed-section"><strong>Safe steps (auto-executable):</strong><ol>';
            plan.safe_steps.forEach(s => html += `<li>🟢 ${s}</li>`);
            html += '</ol></div>';
        }
        if (plan.risky_steps?.length) {
            html += '<div class="agent-remed-section"><strong>Steps requiring approval:</strong><ol>';
            plan.risky_steps.forEach(s => html += `<li>🟡 ${s}</li>`);
            html += '</ol></div>';
        }
        if (plan.requires_full_control) {
            html += '<div class="agent-remed-warn">⚠️ Some steps require Full Control action level</div>';
        }
        html += `<div class="agent-remed-actions">`;
        html += `<button class="agent-remed-approve" onclick="document.getElementById('agentChatInput').value='approve'; app.sendChatMessage();">✅ Approve & Execute</button>`;
        html += `<button class="agent-remed-reject" onclick="app.addChatMsg('system','Remediation cancelled.');">❌ Cancel</button>`;
        html += `</div></div></div>`;

        const container = document.getElementById('agentChatMessages');
        const div = document.createElement('div');
        div.className = 'agent-chat-msg agent-msg-agent';
        div.innerHTML = html;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    renderRemediationResult(result) {
        const data = result.data || {};
        let html = `<div class="agent-msg-content"><div class="agent-remediation-card">`;
        html += `<div class="agent-remed-header">✅ Remediation Results</div>`;
        html += `<p>${result.message || 'Remediation completed.'}</p>`;
        if (data.results?.length) {
            html += '<div class="agent-remed-steps">';
            data.results.forEach(r => {
                const icon = r.success ? '✅' : r.status === 'manual' ? '🔧' : '❌';
                const cls = r.success ? 'success' : r.status === 'manual' ? 'manual' : 'failed';
                html += `<div class="agent-remed-step agent-remed-step-${cls}">${icon} Step ${r.step}: ${r.description} <em>(${r.status})</em></div>`;
            });
            html += '</div>';
        }
        html += `</div></div>`;

        const container = document.getElementById('agentChatMessages');
        const div = document.createElement('div');
        div.className = 'agent-chat-msg agent-msg-agent';
        div.innerHTML = html;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;

        this.addChatMsg('agent', result.message);
    }

    renderInvestigationFromChat(data, issue) {
        // Also render in the main troubleshooting tab
        const tsTab = document.querySelector('[data-tab="troubleshooting"]');
        if (tsTab) this.switchTab(tsTab);
        const recSubTab = document.querySelector('[data-subtab="ts-recommendations"]');
        if (recSubTab) this.switchSubTab(recSubTab);

        const container = document.getElementById('recommendationsContainer');
        if (!container) return;

        // Render the reasoning chain + deep-dive report
        const chain = data.reasoning_chain || data.diagnosis?.reasoning_chain || [];
        const diagnosis = data.diagnosis || {};

        container.innerHTML = `
            <div class="agent-investigation" id="agentPanel">
                <div class="agent-header">
                    <div class="agent-header-left">
                        <span class="agent-pulse" style="background:#16a34a;animation:none;"></span>
                        <h4>🧠 Investigation Complete</h4>
                    </div>
                    <span class="agent-issue">"${issue}"</span>
                </div>
                <div class="agent-feed" id="agentFeed"></div>
                <div class="agent-status"><span class="agent-done-badge">✅ Complete</span> — ${chain.length} reasoning steps, ${diagnosis.confidence || 0}% confidence</div>
            </div>`;

        const feed = document.getElementById('agentFeed');
        chain.forEach(t => {
            let html = `<div class="agent-thought-head">💭 Step ${t.step}</div><p class="agent-thought-text">${t.reasoning}</p>`;
            if (t.hypotheses?.length) {
                html += '<div class="agent-hyp-list">';
                t.hypotheses.forEach(h => {
                    const pct = Math.round(h.confidence * 100);
                    const cls = pct >= 70 ? 'agent-bar-high' : pct >= 40 ? 'agent-bar-med' : 'agent-bar-low';
                    html += `<div class="agent-hyp-row"><span class="agent-hyp-name">${h.description}</span><div class="agent-hyp-bar"><div class="agent-hyp-fill ${cls}" style="width:${pct}%"></div></div><span class="agent-hyp-pct">${pct}%</span></div>`;
                });
                html += '</div>';
            }
            if (t.conclusion) html += `<div class="agent-conclusion">✅ <strong>${t.conclusion}</strong></div>`;
            const div = document.createElement('div');
            div.className = 'agent-feed-item agent-fi-thought';
            div.innerHTML = html;
            feed.appendChild(div);
        });

        if (diagnosis.root_cause) {
            let diagHtml = `<div class="agent-diag-header">📋 DIAGNOSIS</div>`;
            diagHtml += `<div class="agent-diag-cause"><strong>Root Cause:</strong> ${diagnosis.root_cause}</div>`;
            diagHtml += `<div class="agent-diag-conf">Confidence: <strong>${diagnosis.confidence}%</strong></div>`;
            const div = document.createElement('div');
            div.className = 'agent-feed-item agent-fi-diagnosis';
            div.innerHTML = diagHtml;
            feed.appendChild(div);
        }

        // Render metrics bar if available
        if (data.metrics) {
            this.renderInvestigationMetrics(data.metrics, container);
        }

        this.renderFullAnalysisReport(data, issue);
    }

    renderInvestigationMetrics(metrics, container) {
        if (!metrics) return;
        const timeSaved = Math.round(metrics.time_saved_minutes || 0);
        const cost = Math.round(metrics.estimated_cost_saved || 0).toLocaleString();
        const agentTime = Math.round(metrics.investigation_time_seconds || 0);
        const metricsDiv = document.createElement('div');
        metricsDiv.className = 'agent-bv-bar';
        metricsDiv.innerHTML = `
            <div class="agent-bv-title">📊 Business Value Impact</div>
            <div class="agent-bv-grid">
                <div class="agent-bv-card"><div class="agent-bv-num">${agentTime}s</div><div class="agent-bv-label">AI Investigation</div><div class="agent-bv-compare">vs 45min manual</div></div>
                <div class="agent-bv-card agent-bv-highlight"><div class="agent-bv-num">${timeSaved}m</div><div class="agent-bv-label">Time Saved</div><div class="agent-bv-compare">per incident</div></div>
                <div class="agent-bv-card agent-bv-highlight"><div class="agent-bv-num">$${cost}</div><div class="agent-bv-label">Est. Cost Saved</div><div class="agent-bv-compare">downtime + labor</div></div>
                <div class="agent-bv-card"><div class="agent-bv-num">${metrics.facts_collected || 0}</div><div class="agent-bv-label">Data Points</div><div class="agent-bv-compare">${metrics.subsystems_checked || 0} subsystems</div></div>
                <div class="agent-bv-card"><div class="agent-bv-num">${metrics.hypotheses_tested || 0}</div><div class="agent-bv-label">Hypotheses Tested</div><div class="agent-bv-compare">evidence-based</div></div>
                <div class="agent-bv-card"><div class="agent-bv-num">${metrics.escalation_avoided ? '✅ Yes' : '—'}</div><div class="agent-bv-label">Escalation Avoided</div><div class="agent-bv-compare">${metrics.truck_roll_avoided ? '+ truck roll' : ''}</div></div>
            </div>`;
        container.appendChild(metricsDiv);
    }

    renderFullAnalysisReport(result, issueDescription) {
        const container = document.getElementById('recommendationsContainer');
        if (!container) return;
        // If agentic feed is present, append below it; otherwise clear
        if (!result.agentic) container.innerHTML = '';
        const v = (val, fb='N/A') => val != null && val !== '' ? val : fb;

        const recs = result.recommendations || [];
        const rpt = result.report || {};
        const data = result.collected_data || {};
        const la = rpt.log_analysis || {};
        const sa = rpt.sensor_analysis || {};
        const anomalies = rpt.anomalies || [];
        const cs = rpt.collection_summary || {};
        const dd = rpt.deep_dive || {};
        const corr = rpt.correlations || [];
        const eng = rpt.engineer_assessment || {};
        const sysId = rpt.system_identity || {};

        const hIcon = (h) => h === 'ok' ? '🟢' : h === 'warning' ? '🟡' : h === 'critical' ? '🔴' : '⚪';
        const healthIcon = cs.health_status === 'online' ? '🟢' : cs.health_status === 'warning' ? '🟡' : cs.health_status === 'critical' ? '🔴' : '⚪';

        // ═══════════════════════════════════════════════════════════
        // 1. ENGINEER'S ASSESSMENT — risk gauge + narrative
        // ═══════════════════════════════════════════════════════════
        const riskPct = eng.risk_score || 0;
        const riskColor = riskPct >= 70 ? '#dc2626' : riskPct >= 40 ? '#f59e0b' : riskPct >= 15 ? '#3b82f6' : '#16a34a';
        const riskIcon = riskPct >= 70 ? '🔴' : riskPct >= 40 ? '🟡' : riskPct >= 15 ? '🔵' : '🟢';
        container.innerHTML += `
        <div class="dd-assessment">
            <div class="dd-assess-left">
                <div class="dd-risk-gauge">
                    <svg viewBox="0 0 120 70" class="dd-gauge-svg">
                        <path d="M10,65 A50,50 0 0,1 110,65" fill="none" stroke="#e2e8f0" stroke-width="10" stroke-linecap="round"/>
                        <path d="M10,65 A50,50 0 0,1 110,65" fill="none" stroke="${riskColor}" stroke-width="10" stroke-linecap="round"
                              stroke-dasharray="${riskPct * 1.57} 157" class="dd-gauge-fill"/>
                    </svg>
                    <div class="dd-gauge-label"><span class="dd-gauge-num">${riskPct}</span><span class="dd-gauge-sub">/100</span></div>
                </div>
                <div class="dd-risk-tag" style="color:${riskColor}">${riskIcon} ${eng.risk_label || 'Unknown'}</div>
            </div>
            <div class="dd-assess-right">
                <h4>Engineer's Assessment</h4>
                <div class="dd-narrative">${(eng.narrative || []).map(n => `<p>${n}</p>`).join('')}</div>
                ${eng.top_concerns?.length ? `<div class="dd-concerns"><strong>Top Concerns:</strong><ul>${eng.top_concerns.map(c => `<li>${c}</li>`).join('')}</ul></div>` : ''}
            </div>
        </div>`;

        // ═══════════════════════════════════════════════════════════
        // 2. SYSTEM IDENTITY CARD
        // ═══════════════════════════════════════════════════════════
        if (sysId.model || sysId.service_tag) {
            container.innerHTML += `
            <details class="dd-section" open>
                <summary class="dd-section-head"><span>🖥️ System Identity</span><span class="dd-section-badge">${v(sysId.model,'Server')}</span></summary>
                <div class="dd-section-body">
                    <div class="dd-id-grid">
                        <div class="dd-id-item"><span class="dd-id-label">Model</span><span class="dd-id-val">${v(sysId.model)}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">Service Tag</span><span class="dd-id-val dd-id-tag">${v(sysId.service_tag)}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">BIOS</span><span class="dd-id-val">${v(sysId.bios_version)}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">iDRAC FW</span><span class="dd-id-val">${v(sysId.idrac_version)}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">CPU</span><span class="dd-id-val">${v(sysId.cpu_model)} (x${sysId.cpu_count || '?'})</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">Memory</span><span class="dd-id-val">${sysId.total_memory_gb || '?'} GB</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">Power State</span><span class="dd-id-val">${v(sysId.power_state)}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">Hostname</span><span class="dd-id-val">${v(sysId.hostname)}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">OS</span><span class="dd-id-val">${v(sysId.os)} ${v(sysId.os_version,'')}</span></div>
                        <div class="dd-id-item"><span class="dd-id-label">Health</span><span class="dd-id-val">${healthIcon} ${v(cs.health_status)}</span></div>
                    </div>
                </div>
            </details>`;
        }

        // ═══════════════════════════════════════════════════════════
        // 3. DATA COLLECTION SUMMARY BAR
        // ═══════════════════════════════════════════════════════════
        container.innerHTML += `
        <div class="dd-stats-bar">
            <div class="dd-stat-chip"><strong>${cs.logs_collected || 0}</strong> Logs</div>
            <div class="dd-stat-chip"><strong>${cs.temperatures_read || 0}</strong> Sensors</div>
            <div class="dd-stat-chip"><strong>${cs.fans_read || 0}</strong> Fans</div>
            <div class="dd-stat-chip"><strong>${cs.psus_read || 0}</strong> PSUs</div>
            <div class="dd-stat-chip"><strong>${cs.dimms_read || 0}</strong> DIMMs</div>
            <div class="dd-stat-chip"><strong>${cs.storage_devices_read || 0}</strong> Drives</div>
            <div class="dd-stat-chip"><strong>${cs.network_interfaces_read || 0}</strong> NICs</div>
            <div class="dd-stat-chip ${anomalies.length ? 'dd-stat-alert' : ''}"><strong>${anomalies.length}</strong> Anomalies</div>
            <div class="dd-stat-chip ${corr.length ? 'dd-stat-alert' : ''}"><strong>${corr.length}</strong> Correlations</div>
        </div>`;

        // ═══════════════════════════════════════════════════════════
        // 4. ANOMALIES + CORRELATIONS
        // ═══════════════════════════════════════════════════════════
        if (anomalies.length || corr.length) {
            let alertHtml = `<details class="dd-section dd-section-alert" open>
                <summary class="dd-section-head"><span>⚠️ Findings & Correlations</span><span class="dd-section-badge">${anomalies.length + corr.length} items</span></summary>
                <div class="dd-section-body">`;
            anomalies.forEach(a => {
                const cls = a.type === 'critical' ? 'dd-alert-crit' : 'dd-alert-warn';
                alertHtml += `<div class="dd-alert-card ${cls}"><span class="dd-alert-icon">${a.type === 'critical' ? '🔴' : '🟡'}</span><div><strong>${a.component}</strong><p>${a.detail}</p></div></div>`;
            });
            corr.forEach(c => {
                const cls = c.severity === 'critical' ? 'dd-alert-crit' : 'dd-alert-warn';
                alertHtml += `<div class="dd-alert-card ${cls} dd-corr-card"><span class="dd-alert-icon">🔗</span><div><strong>${c.title}</strong><p>${c.detail}</p><p class="dd-corr-action"><strong>Action:</strong> ${c.action}</p></div></div>`;
            });
            alertHtml += '</div></details>';
            container.innerHTML += alertHtml;
        }

        // ═══════════════════════════════════════════════════════════
        // 5. DEEP DIVE — THERMAL (clickable, shows every sensor)
        // ═══════════════════════════════════════════════════════════
        if (dd.temperatures?.length) {
            const t = sa.temperature || {};
            let html = `<details class="dd-section">
                <summary class="dd-section-head"><span>🌡️ Thermal Deep Dive</span><span class="dd-section-badge">${dd.temperatures.length} sensors &mdash; Max: ${t.max || '?'}°C</span></summary>
                <div class="dd-section-body">
                <div class="dd-comp-grid">`;
            dd.temperatures.forEach(s => {
                const pct = Math.min(((s.reading || 0) / 100) * 100, 100);
                const barCls = s.health === 'critical' ? 'dd-bar-crit' : s.health === 'warning' ? 'dd-bar-warn' : 'dd-bar-ok';
                html += `<div class="dd-comp-card dd-comp-${s.health}">
                    <div class="dd-comp-title">${s.name}</div>
                    <div class="dd-comp-big">${s.reading != null ? s.reading + '°C' : 'N/A'}</div>
                    <div class="dd-temp-bar"><div class="dd-temp-bar-fill ${barCls}" style="width:${pct}%"></div></div>
                    <div class="dd-comp-meta">${s.upper_warning ? 'Warn: '+s.upper_warning+'°C' : ''} ${s.upper_critical ? '| Crit: '+s.upper_critical+'°C' : ''}</div>
                    <div class="dd-comp-status">${hIcon(s.health)} ${s.status}</div>
                </div>`;
            });
            html += '</div></div></details>';
            container.innerHTML += html;
        }

        // ═══════════════════════════════════════════════════════════
        // 6. DEEP DIVE — FANS
        // ═══════════════════════════════════════════════════════════
        if (dd.fans?.length) {
            const f = sa.fans || {};
            let html = `<details class="dd-section">
                <summary class="dd-section-head"><span>💨 Fan Deep Dive</span><span class="dd-section-badge">${dd.fans.length} fans &mdash; Avg: ${f.avg_rpm || '?'} RPM</span></summary>
                <div class="dd-section-body"><div class="dd-comp-grid">`;
            dd.fans.forEach(fan => {
                const pct = Math.min(((fan.speed_rpm || 0) / 20000) * 100, 100);
                html += `<div class="dd-comp-card dd-comp-${fan.health}">
                    <div class="dd-comp-title">${fan.name}</div>
                    <div class="dd-comp-big">${fan.speed_rpm != null ? fan.speed_rpm + ' RPM' : 'N/A'}</div>
                    <div class="dd-temp-bar"><div class="dd-temp-bar-fill ${fan.health === 'ok' ? 'dd-bar-ok' : 'dd-bar-crit'}" style="width:${pct}%"></div></div>
                    <div class="dd-comp-status">${hIcon(fan.health)} ${fan.status}</div>
                </div>`;
            });
            html += '</div></div></details>';
            container.innerHTML += html;
        }

        // ═══════════════════════════════════════════════════════════
        // 7. DEEP DIVE — POWER SUPPLIES
        // ═══════════════════════════════════════════════════════════
        if (dd.power_supplies?.length) {
            let html = `<details class="dd-section">
                <summary class="dd-section-head"><span>⚡ Power Supply Deep Dive</span><span class="dd-section-badge">${dd.power_supplies.length} PSUs</span></summary>
                <div class="dd-section-body"><div class="dd-comp-grid dd-comp-wide">`;
            dd.power_supplies.forEach(p => {
                html += `<div class="dd-comp-card dd-comp-${p.health}">
                    <div class="dd-comp-title">${p.id}</div>
                    <div class="dd-comp-big">${p.power_watts != null ? p.power_watts + 'W' : 'N/A'}</div>
                    <div class="dd-comp-meta">Capacity: ${v(p.capacity_watts,'?')}W | Model: ${v(p.model,'-')}</div>
                    <div class="dd-comp-meta">Efficiency: ${v(p.efficiency,'-')} | FW: ${v(p.firmware,'-')}</div>
                    <div class="dd-comp-status">${hIcon(p.health)} ${p.status}</div>
                </div>`;
            });
            html += '</div></div></details>';
            container.innerHTML += html;
        }

        // ═══════════════════════════════════════════════════════════
        // 8. DEEP DIVE — MEMORY (every DIMM)
        // ═══════════════════════════════════════════════════════════
        if (dd.memory?.length) {
            const m = sa.memory || {};
            let html = `<details class="dd-section">
                <summary class="dd-section-head"><span>🧠 Memory Deep Dive</span><span class="dd-section-badge">${dd.memory.length} DIMMs &mdash; ${m.total_gb || '?'} GB total</span></summary>
                <div class="dd-section-body">
                <table class="dd-table"><thead><tr><th>Slot</th><th>Size</th><th>Type</th><th>Speed</th><th>Manufacturer</th><th>Part #</th><th>Serial</th><th>Status</th></tr></thead><tbody>`;
            dd.memory.forEach(d => {
                const cls = d.health === 'critical' ? 'dd-row-crit' : '';
                html += `<tr class="${cls}"><td>${v(d.id)}</td><td>${d.size_gb ? d.size_gb+'GB' : '-'}</td><td>${v(d.type,'-')}</td><td>${d.speed_mhz ? d.speed_mhz+'MHz' : '-'}</td><td>${v(d.manufacturer,'-')}</td><td><code>${v(d.part_number,'-')}</code></td><td><code>${v(d.serial,'-')}</code></td><td>${hIcon(d.health)} ${d.status}</td></tr>`;
            });
            html += '</tbody></table></div></details>';
            container.innerHTML += html;
        }

        // ═══════════════════════════════════════════════════════════
        // 9. DEEP DIVE — STORAGE (every drive)
        // ═══════════════════════════════════════════════════════════
        if (dd.storage?.length) {
            let html = `<details class="dd-section">
                <summary class="dd-section-head"><span>💾 Storage Deep Dive</span><span class="dd-section-badge">${dd.storage.length} devices</span></summary>
                <div class="dd-section-body">
                <table class="dd-table"><thead><tr><th>ID</th><th>Name</th><th>Model</th><th>Capacity</th><th>Media</th><th>Protocol</th><th>FW</th><th>Serial</th><th>Status</th></tr></thead><tbody>`;
            dd.storage.forEach(d => {
                const cls = d.health === 'critical' ? 'dd-row-crit' : '';
                html += `<tr class="${cls}"><td>${v(d.id)}</td><td>${v(d.name,'-')}</td><td>${v(d.model,'-')}</td><td>${d.capacity_gb ? d.capacity_gb+'GB' : '-'}</td><td>${v(d.media_type,'-')}</td><td>${v(d.protocol,'-')}</td><td>${v(d.firmware,'-')}</td><td><code>${v(d.serial,'-')}</code></td><td>${hIcon(d.health)} ${d.status}</td></tr>`;
            });
            html += '</tbody></table></div></details>';
            container.innerHTML += html;
        }

        // ═══════════════════════════════════════════════════════════
        // 10. DEEP DIVE — NETWORK
        // ═══════════════════════════════════════════════════════════
        if (dd.network?.length) {
            let html = `<details class="dd-section">
                <summary class="dd-section-head"><span>🌐 Network Deep Dive</span><span class="dd-section-badge">${dd.network.length} interfaces</span></summary>
                <div class="dd-section-body">
                <table class="dd-table"><thead><tr><th>ID</th><th>Name</th><th>MAC</th><th>IPv4</th><th>Speed</th><th>Link</th><th>Status</th></tr></thead><tbody>`;
            dd.network.forEach(n => {
                html += `<tr><td>${v(n.id)}</td><td>${v(n.name,'-')}</td><td><code>${v(n.mac,'-')}</code></td><td>${v(n.ipv4,'-')}</td><td>${n.speed_mbps ? n.speed_mbps+'Mbps' : '-'}</td><td>${v(n.link_status,'-')}</td><td>${hIcon(n.health)} ${n.status}</td></tr>`;
            });
            html += '</tbody></table></div></details>';
            container.innerHTML += html;
        }

        // ═══════════════════════════════════════════════════════════
        // 11. LOG ANALYSIS (expanded)
        // ═══════════════════════════════════════════════════════════
        const sevC = la.severity_counts || {};
        const timeline = la.error_timeline || [];
        const recentCrit = la.recent_critical || [];
        const errorCodes = la.error_codes_found || [];
        const compErrors = la.component_errors || {};

        let logHtml = `<details class="dd-section" open>
            <summary class="dd-section-head"><span>📋 Log Analysis</span><span class="dd-section-badge">${la.total_entries || 0} entries scanned</span></summary>
            <div class="dd-section-body">`;

        logHtml += `<div class="ts-log-sev-row">
            <span class="badge badge-crit">${sevC.critical || 0} Critical</span>
            <span class="badge" style="background:#fff3cd;color:#856404">${sevC.error || 0} Error</span>
            <span class="badge badge-warn">${sevC.warning || 0} Warning</span>
            <span class="badge badge-info">${sevC.info || 0} Info</span>
        </div>`;

        if (errorCodes.length) {
            logHtml += `<div class="ts-dell-codes"><strong>Dell Error Codes:</strong> ${errorCodes.map(c => `<code class="ts-code-badge">${c}</code>`).join(' ')}</div>`;
        }

        const compEntries = Object.entries(compErrors).sort((a,b) => b[1] - a[1]);
        if (compEntries.length) {
            logHtml += '<div class="ts-comp-errors"><strong>Component Mentions:</strong><div class="ts-comp-bars">';
            const maxComp = compEntries[0][1];
            compEntries.forEach(([comp, cnt]) => {
                logHtml += `<div class="ts-comp-bar-row"><span class="ts-comp-name">${comp}</span><div class="ts-comp-bar"><div class="ts-comp-bar-fill" style="width:${Math.round((cnt / maxComp) * 100)}%"></div></div><span class="ts-comp-cnt">${cnt}</span></div>`;
            });
            logHtml += '</div></div>';
        }

        if (timeline.length) {
            logHtml += '<div class="ts-timeline"><strong>Error Timeline (72h):</strong><div class="ts-timeline-chart">';
            const maxBucket = Math.max(...timeline.map(b => b.critical + b.error + b.warning), 1);
            timeline.forEach(b => {
                const pct = Math.round(((b.critical + b.error + b.warning) / maxBucket) * 100);
                logHtml += `<div class="ts-timeline-bar-col"><div class="ts-timeline-bar-stack" style="height:${Math.max(pct, 4)}%">
                    ${b.critical ? `<div class="ts-tl-crit" style="flex:${b.critical}"></div>` : ''}
                    ${b.error ? `<div class="ts-tl-err" style="flex:${b.error}"></div>` : ''}
                    ${b.warning ? `<div class="ts-tl-warn" style="flex:${b.warning}"></div>` : ''}
                </div><span class="ts-tl-label">${b.label.split('-')[0]}h</span></div>`;
            });
            logHtml += '</div><div class="ts-tl-legend"><span class="ts-tl-leg-crit">■ Critical</span><span class="ts-tl-leg-err">■ Error</span><span class="ts-tl-leg-warn">■ Warning</span></div></div>';
        }

        if (recentCrit.length) {
            logHtml += `<details class="ts-log-viewer" open><summary><strong>Recent Critical/Error Entries (${recentCrit.length})</strong></summary><div class="ts-log-entries">`;
            recentCrit.forEach(l => {
                const sevCls = l.severity === 'critical' ? 'ts-log-crit' : 'ts-log-err';
                logHtml += `<div class="ts-log-entry ${sevCls}"><span class="ts-log-time">${l.hours_ago}h ago</span><span class="ts-log-sev">${l.severity.toUpperCase()}</span><span class="ts-log-msg">${l.message}</span>${l.event_id ? `<code class="ts-log-eid">${l.event_id}</code>` : ''}</div>`;
            });
            logHtml += '</div></details>';
        }

        // Full log viewer (all 50 recent)
        const allLogs = data.recent_logs || [];
        if (allLogs.length) {
            logHtml += `<details class="ts-log-viewer"><summary><strong>All Recent Log Entries (${allLogs.length})</strong></summary><div class="ts-log-entries">`;
            allLogs.forEach(l => {
                const s = (l.severity || 'info').toLowerCase();
                const cls = s === 'critical' ? 'ts-log-crit' : s === 'error' ? 'ts-log-err' : '';
                logHtml += `<div class="ts-log-entry ${cls}"><span class="ts-log-time">${v(l.timestamp,'?').substring(0,19)}</span><span class="ts-log-sev">${s.toUpperCase()}</span><span class="ts-log-msg">${l.message}</span>${l.event_id ? `<code class="ts-log-eid">${l.event_id}</code>` : ''}</div>`;
            });
            logHtml += '</div></details>';
        }

        logHtml += '</div></details>';
        container.innerHTML += logHtml;

        // ═══════════════════════════════════════════════════════════
        // 12. AI RECOMMENDATIONS
        // ═══════════════════════════════════════════════════════════
        const critCount = recs.filter(r => r.priority === 'critical').length;
        const highCount = recs.filter(r => r.priority === 'high').length;
        container.innerHTML += `
        <details class="dd-section" open>
            <summary class="dd-section-head"><span>🤖 AI Recommendations</span><span class="dd-section-badge">${recs.length} actions</span></summary>
            <div class="dd-section-body">
                <div class="ts-summary-badges" style="margin-bottom:12px">
                    ${critCount ? `<span class="badge badge-crit">${critCount} Critical</span>` : ''}
                    ${highCount ? `<span class="badge badge-warn">${highCount} High</span>` : ''}
                    <span class="badge badge-ok">${recs.length - critCount - highCount} Other</span>
                </div>
            </div>
        </details>`;

        recs.forEach((rec, idx) => {
            const card = document.createElement('div');
            card.className = `recommendation-card ${rec.priority}-priority`;
            const priorityIcon = {'critical':'🔴','high':'🟠','medium':'🟡','low':'🟢'}[rec.priority] || '⚪';
            const levelLabel = {'read_only':'Read Only','diagnostic':'Diagnostic','full_control':'Full Control'}[rec.action_level_required] || rec.action_level_required;
            const cmdId = `rec-cmd-${idx}`;
            card.innerHTML = `
                <div class="rec-header"><span class="rec-number">#${idx + 1}</span><h4>${rec.action}</h4></div>
                <p class="rec-desc">${rec.description}</p>
                <div class="recommendation-meta">
                    <span class="badge priority-${rec.priority}">${priorityIcon} ${rec.priority.toUpperCase()}</span>
                    <span class="badge badge-level">${levelLabel}</span>
                    ${rec.estimated_time ? `<span class="badge badge-time">⏱️ ${rec.estimated_time}</span>` : ''}
                    <span class="badge risk-${rec.risk_level}">Risk: ${rec.risk_level}</span>
                </div>
                ${rec.steps?.length ? `<details class="rec-steps-details" ${idx === 0 ? 'open' : ''}><summary><strong>Steps (${rec.steps.length})</strong></summary><ol class="rec-steps-list">${rec.steps.map(s => `<li>${s}</li>`).join('')}</ol></details>` : ''}
                ${rec.commands?.length ? `<div class="recommendation-commands">${rec.commands.map(cmd => `<button class="btn btn-sm btn-primary rec-run-btn" data-cmd="${cmd}" id="${cmdId}-${cmd}" onclick="app.executeRecommendationWithProgress(this, '${cmd}')"><code>${cmd}</code> ▶</button>`).join(' ')}</div><div class="rec-output" id="${cmdId}-output"></div>` : ''}`;
            container.appendChild(card);
        });

        // Copy diagnosis + Raw JSON toggle (Engineer/Technician needs)
        const toolbox = document.createElement('div');
        toolbox.className = 'dd-toolbox';
        toolbox.style.cssText = 'display:flex;gap:8px;margin-top:16px;flex-wrap:wrap';
        toolbox.innerHTML = `
            <button class="btn btn-sm btn-outline" id="copyDiagnosisBtn" title="Copy diagnosis text to clipboard">📋 Copy Diagnosis</button>
            <button class="btn btn-sm btn-outline" id="toggleRawJsonBtn" title="Show raw Redfish JSON data">{ } Raw JSON</button>
        `;
        container.appendChild(toolbox);

        document.getElementById('copyDiagnosisBtn')?.addEventListener('click', () => {
            const text = container.innerText;
            navigator.clipboard.writeText(text).then(() => this.showAlert('Diagnosis copied to clipboard', 'success'))
                .catch(() => this.showAlert('Copy failed — try selecting text manually', 'warning'));
        });
        document.getElementById('toggleRawJsonBtn')?.addEventListener('click', () => {
            let rawEl = document.getElementById('rawJsonSection');
            if (rawEl) { rawEl.style.display = rawEl.style.display === 'none' ? 'block' : 'none'; return; }
            rawEl = document.createElement('details');
            rawEl.id = 'rawJsonSection';
            rawEl.className = 'dd-section';
            rawEl.innerHTML = `<summary class="dd-section-head"><span>{ } Raw Collected Data (JSON)</span></summary>
                <div class="dd-section-body"><pre style="max-height:400px;overflow:auto;font-size:0.75rem;white-space:pre-wrap;word-break:break-all">${this._escapeHtml(JSON.stringify(result.collected_data || result, null, 2))}</pre></div>`;
            container.appendChild(rawEl);
        });

        setTimeout(() => container.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
    }
    
    async executeRecommendationWithProgress(btnEl, action) {
        const commandMap = {
            'Check power supply status': 'get_power_supplies',
            'Check temperature sensors': 'get_temperature_sensors',
            'Verify fan operation': 'get_fans',
            'Check storage controller status': 'get_storage_devices',
            'Check network interface status': 'get_network_interfaces',
            'Collect comprehensive logs': 'collect_logs',
            'Perform health check': 'health_check',
            'Check system information': 'get_server_info',
            'Run memory diagnostics': 'run_diagnostics',
            'Check memory configuration': 'get_memory',
            'Check firmware versions': 'get_firmware_inventory',
            'export_tsr': 'export_tsr',
            'get_power_supplies': 'get_power_supplies',
            'get_temperature_sensors': 'get_temperature_sensors',
            'get_fans': 'get_fans',
            'get_storage_devices': 'get_storage_devices',
            'get_network_interfaces': 'get_network_interfaces',
            'get_memory': 'get_memory',
            'collect_logs': 'collect_logs',
            'health_check': 'health_check',
        };

        const command = commandMap[action] || action;
        const isFullControl = (command === 'export_tsr' || command === 'run_diagnostics');
        const actionLevel = isFullControl ? 'full_control' : 'read_only';

        // Find the output div (sibling of the commands div)
        const outputDiv = btnEl.closest('.recommendation-card')?.querySelector('.rec-output');
        const origHTML = btnEl.innerHTML;

        // Show loading state on button
        btnEl.disabled = true;
        btnEl.innerHTML = `<span class="rec-spinner"></span> Running...`;

        // Show loading bar in output
        if (outputDiv) {
            outputDiv.style.display = 'block';
            outputDiv.innerHTML = `
                <div class="rec-output-loading">
                    <div class="rec-output-bar"><div class="rec-output-bar-fill rec-bar-animate"></div></div>
                    <span>Fetching <code>${command}</code> from server...</span>
                </div>`;
        }

        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action_level: actionLevel, action: command, parameters: {} })
            });
            const result = await response.json();

            if (response.ok && result.result) {
                btnEl.innerHTML = `<code>${action}</code> ✅`;
                btnEl.classList.remove('btn-primary');
                btnEl.classList.add('btn-success-outline');
                this.log(`✅ ${command} completed`, 'success');
                this.handleActionResponse(result.result);

                // Show summary in output div
                if (outputDiv) {
                    const summary = this._summarizeCommandResult(command, result.result);
                    outputDiv.innerHTML = `<div class="rec-output-result rec-output-ok">${summary}</div>`;
                }
            } else {
                btnEl.innerHTML = `<code>${action}</code> ❌`;
                btnEl.classList.remove('btn-primary');
                btnEl.classList.add('btn-danger-outline');
                if (outputDiv) {
                    outputDiv.innerHTML = `<div class="rec-output-result rec-output-err">❌ ${result.detail || 'Command failed'}</div>`;
                }
            }
        } catch (error) {
            btnEl.innerHTML = `<code>${action}</code> ❌`;
            if (outputDiv) {
                outputDiv.innerHTML = `<div class="rec-output-result rec-output-err">❌ ${error.message}</div>`;
            }
        } finally {
            btnEl.disabled = false;
        }
    }

    _summarizeCommandResult(command, data) {
        const lines = [];
        if (command === 'get_temperature_sensors' && data.temperatures) {
            const temps = data.temperatures;
            const readings = temps.filter(t => t.reading_celsius).map(t => t.reading_celsius);
            lines.push(`<strong>🌡️ ${temps.length} sensors</strong> — Avg: ${readings.length ? (readings.reduce((a,b)=>a+b,0)/readings.length).toFixed(1) : '?'}°C, Max: ${readings.length ? Math.max(...readings) : '?'}°C`);
            temps.slice(0, 4).forEach(t => lines.push(`&nbsp;&nbsp;${t.name || t.id}: <strong>${t.reading_celsius || '?'}°C</strong> (${t.status || 'OK'})`));
            if (temps.length > 4) lines.push(`&nbsp;&nbsp;<em>...and ${temps.length - 4} more</em>`);
        } else if (command === 'get_fans' && data.fans) {
            const fans = data.fans;
            const speeds = fans.filter(f => f.speed_rpm).map(f => f.speed_rpm);
            lines.push(`<strong>💨 ${fans.length} fans</strong> — Avg: ${speeds.length ? Math.round(speeds.reduce((a,b)=>a+b,0)/speeds.length) : '?'} RPM`);
            fans.slice(0, 4).forEach(f => lines.push(`&nbsp;&nbsp;${f.name || f.id}: <strong>${f.speed_rpm || '?'} RPM</strong> (${f.status || 'OK'})`));
            if (fans.length > 4) lines.push(`&nbsp;&nbsp;<em>...and ${fans.length - 4} more</em>`);
        } else if (command === 'get_power_supplies' && data.power_supplies) {
            const psus = data.power_supplies;
            lines.push(`<strong>⚡ ${psus.length} PSUs</strong>`);
            psus.forEach(p => lines.push(`&nbsp;&nbsp;${p.id}: ${p.power_watts || '?'}W — ${p.status || 'OK'}`));
        } else if (command === 'get_memory' && data.memory) {
            const mems = data.memory;
            const totalGB = mems.reduce((s, m) => s + (m.size_gb || 0), 0);
            lines.push(`<strong>🧠 ${mems.length} DIMMs</strong> — Total: ${totalGB} GB`);
            const sample = mems.filter(m => m.size_gb).slice(0, 3);
            sample.forEach(m => lines.push(`&nbsp;&nbsp;${m.id}: ${m.size_gb}GB ${m.type || ''} ${m.speed_mhz ? m.speed_mhz + 'MHz' : ''} (${m.status || 'OK'})`));
            if (mems.length > 3) lines.push(`&nbsp;&nbsp;<em>...and ${mems.length - 3} more</em>`);
        } else if (command === 'health_check' && data.health_status) {
            const h = data.health_status;
            const icon = h.overall_status === 'online' ? '✅' : h.overall_status === 'warning' ? '⚠️' : '🔴';
            lines.push(`<strong>${icon} Health: ${(h.overall_status || 'unknown').toUpperCase()}</strong>`);
            if (h.critical_issues?.length) lines.push(`&nbsp;&nbsp;Critical: ${h.critical_issues.length} issues`);
            if (h.warnings?.length) lines.push(`&nbsp;&nbsp;Warnings: ${h.warnings.length}`);
        } else if (command === 'collect_logs' && data.logs) {
            lines.push(`<strong>📋 ${data.logs.length} log entries collected</strong>`);
            const crits = data.logs.filter(l => l.severity === 'critical' || l.severity === 'error');
            if (crits.length) lines.push(`&nbsp;&nbsp;⚠️ ${crits.length} critical/error entries`);
            data.logs.slice(0, 3).forEach(l => lines.push(`&nbsp;&nbsp;[${l.severity || '?'}] ${(l.message || '').slice(0, 80)}`));
        } else if (command === 'export_tsr' && data.tsr_result) {
            const t = data.tsr_result;
            lines.push(t.success ? `<strong>✅ TSR initiated</strong> — ${t.message || ''}` : `<strong>❌ TSR failed</strong> — ${t.error || ''}`);
        } else {
            lines.push(`<strong>✅ Command completed</strong>`);
            const keys = Object.keys(data).filter(k => k !== 'connection_info');
            keys.slice(0, 3).forEach(k => {
                const v = data[k];
                if (Array.isArray(v)) lines.push(`&nbsp;&nbsp;${k}: ${v.length} items`);
                else if (typeof v === 'object' && v) lines.push(`&nbsp;&nbsp;${k}: ${JSON.stringify(v).slice(0, 80)}`);
                else lines.push(`&nbsp;&nbsp;${k}: ${v}`);
            });
        }
        return lines.join('<br>');
    }

    async executeRecommendation(action) {
        // Legacy fallback — redirect to the progress version
        const btn = document.querySelector(`[data-cmd="${action}"]`);
        if (btn) {
            this.executeRecommendationWithProgress(btn, action);
        } else {
            const commandMap = {
                'export_tsr': 'export_tsr', 'get_power_supplies': 'get_power_supplies',
                'get_temperature_sensors': 'get_temperature_sensors', 'get_fans': 'get_fans',
                'get_storage_devices': 'get_storage_devices', 'get_network_interfaces': 'get_network_interfaces',
                'get_memory': 'get_memory', 'collect_logs': 'collect_logs', 'health_check': 'health_check',
            };
            const command = commandMap[action];
            if (command) await this.executeAction(command);
            else this.log(`Manual action: ${action}`, 'info');
        }
    }
    
    selectActionLevel(button) {
        // Remove selected class from all action level buttons
        document.querySelectorAll('.action-level-btn, .level-pill').forEach(btn => {
            btn.classList.remove('selected');
        });
        
        // Add selected class to clicked button
        button.classList.add('selected');
        
        // Update action level
        this.actionLevel = button.dataset.actionLevel;
        
        // Save setting
        localStorage.setItem('actionLevel', this.actionLevel);
        
        this.log(`Action level changed to: ${this.actionLevel}`, 'info');
    }
    
    switchTab(tabElement) {
        // Save scroll position of current tab before switching
        const currentContent = document.querySelector('.tab-content.active');
        if (currentContent) {
            this._tabScrollPositions[currentContent.id] = currentContent.scrollTop;
        }
        
        // Remove active class from all tabs/sidebar-links and contents
        document.querySelectorAll('.tab, .sidebar-link[data-tab]').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        // Add active class to selected tab
        tabElement.classList.add('active');
        
        // Also sync the sidebar link if switching from a .tab element
        const tabName = tabElement.dataset.tab;
        document.querySelectorAll(`.sidebar-link[data-tab="${tabName}"], .tab[data-tab="${tabName}"]`).forEach(el => el.classList.add('active'));
        
        // P4: Update browser tab title to reflect current section
        const tabLabels = { overview: 'Overview', system: 'System Info', health: 'Health', logs: 'Logs',
                           troubleshooting: 'AI Investigation', operations: 'Operations', advanced: 'Advanced' };
        document.title = `${tabLabels[tabName] || tabName} — Medi-AI-tor`;
        
        // Show corresponding content
        const content = document.getElementById(`${tabName}Content`);
        if (content) {
            content.classList.add('active');
            // Restore scroll position
            const savedPos = this._tabScrollPositions[content.id];
            if (savedPos) {
                requestAnimationFrame(() => { content.scrollTop = savedPos; });
            }
        }
        
        // F7: If tab has no data yet and we're connected, show loading hint (all tabs)
        const emptyContainers = {
            'system': 'systemInfoContainer',
            'health': 'healthStatusContainer',
            'logs': 'logsContainer',
            'troubleshooting': 'recommendationsContainer',
            'operations': 'opsResultBios',
            'advanced': 'lifecycleLogsContainer',
        };
        const containerId = emptyContainers[tabName];
        if (containerId && this.currentServer) {
            const container = document.getElementById(containerId);
            if (container && (container.innerHTML.includes('placeholder-text') || container.innerHTML.trim() === '')) {
                container.innerHTML = '<div class="loading-hint"><div class="spinner"></div><p>Loading data...</p></div>';
            }
        }
    }
    
    // ─── Data Fetch ───────────────────────────────────────────────
    async fetchAllDashboardData(silent = false) {
        if (!this.currentServer) return;
        
        if (!silent) {
            this.log('Loading dashboard data...', 'info');
            this.showAlert('Loading server data...', 'info');
        }
        
        try {
            // Use batch endpoint for parallel execution
            const response = await fetch('/api/execute/batch', {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({
                    commands: [
                        { action: 'get_server_info', parameters: {} },
                        { action: 'get_processors', parameters: {} },
                        { action: 'get_memory', parameters: {} },
                        { action: 'get_power_supplies', parameters: {} },
                        { action: 'get_temperature_sensors', parameters: {} },
                        { action: 'get_fans', parameters: {} },
                        { action: 'get_storage_devices', parameters: {} },
                        { action: 'get_network_interfaces', parameters: {} },
                        { action: 'health_check', parameters: {} },
                        { action: 'collect_logs', parameters: {} },
                    ]
                })
            });
            
            if (!response.ok) {
                // Fallback to sequential if batch fails
                this.log('Batch fetch failed, using sequential...', 'warning');
                try {
                    await this.executeAction('get_full_inventory');
                } catch (_) {
                    this.showAlert('Could not load server data. Check the connection and try Refresh.', 'danger');
                }
                return;
            }
            
            const data = await response.json();
            if (data.status === 'success' && data.results) {
                // Process each result through the existing handler
                const failedCmds = [];
                for (const [action, result] of Object.entries(data.results)) {
                    if (result.status === 'success' && result.result) {
                        this.handleActionResponse(result.result);
                    } else {
                        failedCmds.push(action);
                    }
                }
                this.lastDataRefresh = Date.now();
                if (failedCmds.length > 0) {
                    this.log(`⚠️ Failed to load: ${failedCmds.join(', ')}`, 'warning');
                    this.showAlert(`Partial data: ${failedCmds.length} source(s) failed`, 'warning');
                } else {
                    this.log('Dashboard data loaded', 'success');
                }
            }
        } catch (err) {
            this.log('Failed to load data: ' + err.message, 'error');
            // Fallback to get_full_inventory
            try {
                await this.executeAction('get_full_inventory');
            } catch (e) {
                this.showAlert('Failed to load server data', 'danger', {
                    title: 'Data load error',
                    retry: () => this.fetchAllDashboardData()
                });
            }
        }
    }

    // ─── Helpers ────────────────────────────────────────────────
    _v(val, fallback = 'N/A') { return val != null && val !== '' ? val : fallback; }
    _badge(status) {
        const s = String(status).toLowerCase();
        if (s.includes('ok') || s === 'online' || s.includes('enabled')) return 'badge-ok';
        if (s.includes('warn') || s === 'warning') return 'badge-warn';
        if (s.includes('crit') || s.includes('fail') || s === 'critical' || s === 'offline') return 'badge-crit';
        return 'badge-info';
    }
    _tileCls(status) {
        const s = String(status).toLowerCase();
        if (s.includes('ok') || s === 'online') return 'tile-ok';
        if (s.includes('warn')) return 'tile-warn';
        if (s.includes('crit') || s.includes('fail')) return 'tile-crit';
        return 'tile-info';
    }
    _tempCls(reading, warnThresh, critThresh) {
        if (critThresh && reading >= critThresh) return 'gauge-crit';
        if (warnThresh && reading >= warnThresh) return 'gauge-warn';
        return 'gauge-ok';
    }

    switchSubTab(el) {
        const parent = el.closest('.tab-content');
        if (!parent) return;
        parent.querySelectorAll('.sub-tab').forEach(s => s.classList.remove('active'));
        parent.querySelectorAll('.sub-tab-content').forEach(c => c.classList.remove('active'));
        el.classList.add('active');
        const target = document.getElementById(el.dataset.subtab);
        if (target) target.classList.add('active');
        // P8: Hide ops result containers from previous sub-tab
        parent.querySelectorAll('.ops-result').forEach(r => { r.style.display = 'none'; });
    }

    // ─── Main Response Router ───────────────────────────────────
    handleActionResponse(data) {
        if (data.connection_info) this.displayConnectionInfo(data.connection_info);
        if (data.server_info) this.displayServerInfo(data.server_info);
        if (data.system_info) this.displaySystemInfo(data.system_info);
        if (data.processors) this.displayProcessors(data.processors);
        if (data.memory) this.displayMemory(data.memory);
        if (data.storage_devices) this.displayStorage(data.storage_devices);
        if (data.network_adapters) this.displayNetworkAdapters(data.network_adapters);
        if (data.power_supplies) this.displayPowerSupplies(data.power_supplies);
        if (data.fans) this.displayFans(data.fans);
        if (data.temperatures) this.displayTemperatures(data.temperatures);
        if (data.health_status) this.displayHealthStatus(data.health_status);
        if (data.thermal_status) this.displayThermalStatus(data.thermal_status);
        if (data.power_status) this.displayPowerStatus(data.power_status);
        if (data.storage_status) this.displayStorageStatus(data.storage_status);
        if (data.memory_status) this.displayMemoryStatus(data.memory_status);
        if (data.idrac_info) this.displayIdracInfo(data.idrac_info);
        if (data.post_codes) this.displayPostCodes(data.post_codes);
        if (data.lifecycle_logs) { this.rawLcLogs = data.lifecycle_logs; this.renderFilteredLcLogs(); }
        if (data.jobs) this.displayJobs(data.jobs);
        if (data.tsr_result) this.displayTsrResult(data.tsr_result);
        // Build overview metrics from whatever we have
        this.buildOverviewMetrics(data);
    }

    // ─── Server Actions (full_control level) ────────────────────
    async executeServerAction(command, parameters = {}) {
        if (!this._requireConnection('executing actions')) return;
        this.showLoading(true);
        this.log(`Executing server action: ${command}`, 'info');
        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action_level: 'full_control', action: command, parameters })
            });
            const result = await response.json();
            const container = document.getElementById('actionResultContainer');
            if (response.ok) {
                this.handleActionResponse(result.result);
                this.log(`✅ ${command} completed`, 'success');
                // Auto-switch to relevant tab for certain actions
                if (command === 'export_tsr') {
                    document.querySelector('[data-tab="troubleshooting"]')?.click();
                    setTimeout(() => document.querySelector('[data-subtab="ts-tsr"]')?.click(), 200);
                }
                // Action-specific guidance
                const guidance = {
                    'force_restart': 'Server is restarting. Monitor power status in the Health tab. Expect 2-5 min downtime.',
                    'graceful_shutdown': 'Graceful shutdown initiated. OS will stop services first — may take 1-5 min.',
                    'virtual_ac_cycle': 'Virtual AC cycle initiated. Server will fully power off then back on.',
                    'reset_idrac': 'iDRAC is resetting. Connection will drop for 30-60 seconds — do NOT refresh.',
                    'export_tsr': 'TSR export started. This can take 5-15 minutes. Check Troubleshooting > TSR Status.',
                    'clear_sel': 'System Event Log cleared. Old events are gone — collect fresh logs if needed.',
                }[command] || '';
                if (container) {
                    container.style.display = 'block';
                    container.className = 'action-result result-success';
                    container.innerHTML = `<strong>✅ ${command}</strong> — Action completed successfully.${guidance ? `<div class="action-guidance">${guidance}</div>` : ''}`;
                }
                // F3: Schedule a delayed data refresh after power/destructive ops
                const refreshOps = ['force_restart', 'graceful_shutdown', 'virtual_ac_cycle', 'clear_sel'];
                if (refreshOps.includes(command)) {
                    const delay = command === 'force_restart' ? 15000 : command === 'graceful_shutdown' ? 20000 : 5000;
                    setTimeout(() => { if (this.currentServer) this.fetchAllDashboardData(); }, delay);
                }
            } else {
                this.log(`❌ ${command} failed: ${result.detail}`, 'error');
                if (container) {
                    container.style.display = 'block';
                    container.className = 'action-result result-error';
                    container.innerHTML = `<strong>❌ ${command}</strong> — ${result.detail}`;
                }
            }
        } catch (error) {
            this.log(`❌ ${command} error: ${error.message}`, 'error');
        } finally { this.showLoading(false); }
    }

    handleTroubleshootingResult(recommendations) {
        if (!recommendations || !Array.isArray(recommendations)) {
            this.showAlert('No recommendations returned', 'warning');
            return;
        }
        const container = document.getElementById('troubleshootingResultsContainer') || document.getElementById('actionResultContainer');
        if (container) {
            let html = '<div class="section-block"><h3>AI Recommendations</h3>';
            recommendations.forEach((rec, i) => {
                const priority = rec.priority || 'medium';
                const badgeColor = priority === 'critical' ? '#ef4444' : priority === 'high' ? '#f59e0b' : '#3b82f6';
                html += `<div style="padding:8px 0;border-bottom:1px solid var(--border,rgba(99,102,241,0.1))">
                    <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600;background:${badgeColor}20;color:${badgeColor}">${priority.toUpperCase()}</span>
                    <strong>${rec.title || rec.description || 'Recommendation ' + (i+1)}</strong>
                    <p style="margin:4px 0 0;font-size:0.82rem;color:var(--text-secondary)">${rec.description || rec.message || ''}</p>
                </div>`;
            });
            html += '</div>';
            container.innerHTML = html;
            container.style.display = 'block';
        }
        this.showAlert(`${recommendations.length} recommendation(s) generated`, 'success');
    }

    confirmAndExecute(command, label) {
        if (!this._requireConnection('running diagnostics')) return;
        // Dangerous operations require typed confirmation
        const dangerOps = ['raid_delete_vd', 'drive_secure_erase', 'raid_reset_controller', 'bios_reset_defaults', 'idrac_reset'];
        if (dangerOps.includes(command)) {
            const confirmText = prompt(`\u26A0\uFE0F DESTRUCTIVE OPERATION: ${label}\n\nThis action cannot be undone.\nType "CONFIRM" to proceed:`);
            if (confirmText !== 'CONFIRM') {
                this.showAlert('Operation cancelled', 'info');
                return;
            }
        }
        // F5: Inline confirmation instead of browser confirm()
        this._showInlineConfirm(
            document.getElementById('actionResultContainer'),
            `Execute "${label}"? This may affect server availability.`,
            false,
            () => this.executeServerAction(command)
        );
    }

    // ─── SR# Tracking ───────────────────────────────────────────
    saveSrNumber() {
        const sr = document.getElementById('srNumber')?.value || '';
        localStorage.setItem('dellAgentSR', sr);
        this.showAlert(sr ? `SR# ${sr} saved` : 'SR# cleared', 'info');
        this.log(sr ? `Service Request #${sr} saved` : 'SR# cleared', 'info');
    }

    loadSrNumber() {
        const sr = localStorage.getItem('dellAgentSR') || '';
        const el = document.getElementById('srNumber');
        if (el) el.value = sr;
    }

    // ─── iDRAC Availability Check (pre-connection) ──────────────
    async checkIdracAvailability() {
        const host = document.getElementById('serverHost')?.value;
        const username = document.getElementById('username')?.value;
        const password = document.getElementById('password')?.value;
        const resultDiv = document.getElementById('idracCheckResult');
        if (!host) { this.showAlert('Enter a host IP first', 'warning'); return; }
        if (resultDiv) { resultDiv.style.display = 'block'; resultDiv.innerHTML = '<em>Checking iDRAC...</em>'; }
        this.log(`Checking iDRAC availability at ${host}...`, 'info');
        try {
            const response = await fetch(`/api/check-idrac`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ host, username: username || '', password: password || '', port: 443 })
            });
            const result = await response.json();
            const d = result.data || {};
            let html = '';
            if (d.reachable) {
                html = `<span class="badge badge-ok">REACHABLE</span> `;
                if (d.redfish_available) html += `<span class="badge badge-ok">Redfish v${d.redfish_version || '?'}</span> `;
                if (d.system_power_state) html += `Power: <strong>${d.system_power_state}</strong> `;
                if (d.model) html += `| ${d.model} `;
                if (d.service_tag) html += `(${d.service_tag}) `;
                if (d.idrac_firmware) html += `| iDRAC FW: ${d.idrac_firmware}`;
                this.log(`iDRAC at ${host} is reachable. Power: ${d.system_power_state || 'unknown'}`, 'success');
            } else {
                html = `<span class="badge badge-crit">UNREACHABLE</span> `;
                if (d.timeout) html += 'Connection timed out. ';
                html += 'Server may be powered off or iDRAC is not responding. ';
                html += '<br><small>Try: Check network path, verify IP, try iDRAC Direct USB connection.</small>';
                this.log(`iDRAC at ${host} is NOT reachable`, 'error');
            }
            if (resultDiv) {
                const ts = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
                resultDiv.innerHTML = `<small style="color:var(--text-muted)">${ts}</small> ${html}`;
            }
        } catch (error) {
            if (resultDiv) resultDiv.innerHTML = `<span class="badge badge-crit">ERROR</span> ${error.message}`;
            this.log(`iDRAC check error: ${error.message}`, 'error');
        }
    }

    // ─── Remote Diagnostics ─────────────────────────────────────
    async runDiagnostics(type = 'Express') {
        if (!this._requireConnection('running diagnostics')) return;
        const container = document.getElementById('diagnosticsResultContainer');
        this._showInlineConfirm(container, `Run ${type} ePSA diagnostics? Server must be powered on.`, false, () => this._runDiagnosticsConfirmed(type));
    }

    async _runDiagnosticsConfirmed(type) {
        this.log(`Starting ${type} ePSA diagnostics...`, 'info');
        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action_level: 'full_control', command: 'run_diagnostics', parameters: { type } })
            });
            const result = await response.json();
            const dr = (result.data || {}).diagnostics_result || {};
            const container = document.getElementById('diagnosticsResultContainer');
            if (dr.success) {
                this.log(`Diagnostics initiated: ${dr.message}`, 'success');
                if (container) container.innerHTML = `<div class="section-block" style="border-left-color:var(--success-green)"><h4>Diagnostics Started</h4><p>${dr.message}</p>${dr.job_id ? `<p>Job ID: <code>${dr.job_id}</code></p>` : ''}<p style="color:#888;font-size:0.88rem">Monitor progress in the Job Queue sub-tab.</p></div>`;
            } else {
                this.log(`Diagnostics failed: ${dr.error}`, 'error');
                if (container) container.innerHTML = `<div class="section-block" style="border-left-color:var(--danger-red)"><h4>Diagnostics Failed</h4><p>${dr.error}</p></div>`;
            }
        } catch (error) {
            this.log(`Diagnostics error: ${error.message}`, 'error');
            this.showAlert(this._friendlyError(error), 'danger', { title: 'Diagnostics failed' });
        }
    }

    // ─── SupportAssist Status ───────────────────────────────────
    async checkSupportAssist() {
        if (!this._requireConnection('checking SupportAssist')) return;
        this.log('Checking SupportAssist status...', 'info');
        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action_level: 'read_only', command: 'get_support_assist_status', parameters: {} })
            });
            const result = await response.json();
            const sa = (result.data || {}).support_assist || {};
            const container = document.getElementById('supportAssistContainer');
            if (!container) return;
            if (sa.available) {
                container.innerHTML = `
                    <div class="section-block">
                        <h4>SupportAssist Status</h4>
                        <table class="data-table"><tbody>
                            <tr><td><strong>Registered</strong></td><td><span class="badge ${sa.registered ? 'badge-ok' : 'badge-warn'}">${sa.registered ? 'Yes' : 'No'}</span></td></tr>
                            <tr><td><strong>Auto Collection</strong></td><td>${this._v(sa.auto_collection)}</td></tr>
                            <tr><td><strong>Last Collection</strong></td><td>${this._v(sa.last_collection)}</td></tr>
                            <tr><td><strong>Proxy Support</strong></td><td>${this._v(sa.proxy_support)}</td></tr>
                        </tbody></table>
                        ${!sa.registered ? '<p style="color:var(--warning-yellow);margin-top:10px"><strong>Recommendation:</strong> Register SupportAssist for proactive monitoring and automated case creation.</p>' : ''}
                    </div>`;
            } else {
                container.innerHTML = `<div class="section-block" style="border-left-color:var(--warning-yellow)"><h4>SupportAssist</h4><p>${sa.message || sa.error || 'Not available'}</p><p style="color:#888;font-size:0.88rem">SupportAssist status requires Redfish connection to iDRAC.</p></div>`;
            }
            this.log('SupportAssist status retrieved', 'info');
            // Switch to the sub-tab
            const tab = document.querySelector('[data-tab="troubleshooting"]');
            if (tab) this.switchTab(tab);
            setTimeout(() => {
                const st = document.querySelector('[data-subtab="ts-supportassist"]');
                if (st) this.switchSubTab(st);
            }, 100);
        } catch (error) {
            this.log(`SupportAssist check error: ${error.message}`, 'error');
            this.showAlert(this._friendlyError(error), 'danger', { title: 'SupportAssist check failed' });
        }
    }

    // ─── BIOS Presets ───────────────────────────────────────────
    async applyBiosPreset(attributes) {
        if (!this._requireConnection('applying BIOS presets')) return;
        const attrNames = Object.keys(attributes).join(', ');
        const resultDiv = document.getElementById('biosPresetResult');
        this._showInlineConfirm(resultDiv, `Apply BIOS changes: ${attrNames}? Takes effect on next reboot.`, false, () => this._applyBiosPresetConfirmed(attributes, attrNames, resultDiv));
    }

    async _applyBiosPresetConfirmed(attributes, attrNames, resultDiv) {
        this.log(`Applying BIOS preset: ${attrNames}`, 'info');
        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action_level: 'full_control', command: 'set_bios_attributes', parameters: { attributes } })
            });
            const result = await response.json();
            const data = result.data || {};
            if (data.bios_set) {
                this.log(`BIOS preset applied — reboot required`, 'success');
                if (resultDiv) { resultDiv.style.display = 'block'; resultDiv.className = 'action-result result-success'; resultDiv.innerHTML = `<strong>BIOS changes staged.</strong> Attributes: ${attrNames}. <em>Reboot required to apply.</em>`; }
            } else {
                this.log(`BIOS preset failed`, 'error');
                if (resultDiv) { resultDiv.style.display = 'block'; resultDiv.className = 'action-result result-error'; resultDiv.innerHTML = `<strong>Failed to apply BIOS changes.</strong> This feature requires Redfish connection with full_control action level.`; }
            }
        } catch (error) {
            this.log(`BIOS preset error: ${error.message}`, 'error');
            if (resultDiv) { resultDiv.style.display = 'block'; resultDiv.className = 'action-result result-error'; resultDiv.innerHTML = `Error: ${error.message}`; }
        }
    }

    // ─── Operations Tab: Generic operation runner ─────────────
    async runOperation(operation, params = {}) {
        if (!this._requireConnection('running operations')) return;

        // Determine which result container to use based on the operation prefix
        const prefixMap = {
            'bios_': 'opsResultBios', 'set_next_boot': 'opsResultBios',
            'raid_': 'opsResultRaid',
            'drive_': 'opsResultDrives',
            'power_': 'opsResultPower', 'thermal_': 'opsResultPower',
            'idrac_': 'opsResultIdrac',
            'fw_': 'opsResultFirmware',
            'nic_': 'opsResultNetwork',
            'boot_': 'opsResultOs', 'os_': 'opsResultOs', 'lc_': 'opsResultOs',
        };
        let resultId = 'opsResultBios';
        for (const [prefix, id] of Object.entries(prefixMap)) {
            if (operation.startsWith(prefix)) { resultId = id; break; }
        }
        const resultDiv = document.getElementById(resultId);

        // Determine action level needed
        const readOnlyOps = [
            'bios_get_all', 'raid_list_vd', 'raid_controller_info', 'drive_list', 'drive_smart_data', 'drive_predictive',
            'drive_media_patrol', 'power_read_budget', 'power_history', 'idrac_get_network', 'idrac_list_users',
            'idrac_view_cert', 'fw_check_catalog', 'fw_job_status', 'fw_compliance_report', 'nic_inventory',
            'nic_statistics', 'boot_get_order', 'os_get_drivers', 'lc_get_status', 'lc_get_remote_services',
            'thermal_read_sensors', 'thermal_read_fans',
        ];
        const fullControlOps = [
            'bios_set', 'set_next_boot', 'power_on', 'power_graceful_shutdown', 'power_cycle',
            'power_vac_cycle', 'idrac_reset', 'idrac_clear_sel', 'idrac_export_config',
            'fw_cancel_jobs', 'boot_set_next',
        ];
        const dangerOps = [
            'raid_delete_vd', 'raid_reset_controller', 'drive_secure_erase', 'power_force_off', 'power_nmi',
            'idrac_delete_user', 'idrac_factory_reset', 'idrac_import_config', 'lc_wipe',
        ];

        let actionLevel = 'diagnostic';
        if (readOnlyOps.includes(operation)) actionLevel = 'read_only';
        if (fullControlOps.includes(operation)) actionLevel = 'full_control';
        if (dangerOps.includes(operation)) actionLevel = 'full_control';

        // F5: Inline confirmation for dangerous operations
        if (dangerOps.includes(operation)) {
            const opLabels = {
                'raid_delete_vd': 'Delete Virtual Disk - All data will be lost',
                'raid_reset_controller': 'Reset RAID Controller - May disrupt storage',
                'drive_secure_erase': 'Secure Erase Drive - Data permanently destroyed',
                'power_force_off': 'Force Power Off - No graceful OS shutdown',
                'power_nmi': 'Send NMI - May cause system crash/memory dump',
                'idrac_delete_user': 'Delete iDRAC User Account',
                'idrac_factory_reset': 'Factory Reset iDRAC - All settings will be lost',
                'idrac_import_config': 'Import Server Config - May change all settings',
                'lc_wipe': 'Wipe Lifecycle Controller - Cannot be undone',
            };
            const label = opLabels[operation] || operation;
            this._showInlineConfirm(resultDiv, label, true, () => this._executeOperation(operation, params, actionLevel, resultDiv));
            return;
        }
        // Inline confirmation for full-control writes
        if (fullControlOps.includes(operation)) {
            this._showInlineConfirm(resultDiv, `${operation} — changes server configuration`, false, () => this._executeOperation(operation, params, actionLevel, resultDiv));
            return;
        }

        await this._executeOperation(operation, params, actionLevel, resultDiv);
    }

    // Extracted operation execution (called after confirmation)
    async _executeOperation(operation, params, actionLevel, resultDiv) {
        this.log(`Running operation: ${operation}`, 'info');
        if (resultDiv) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'ops-result';
            resultDiv.innerHTML = `<div class="ops-result-title">⏳ Running: ${operation}</div><p>Sending command to server...</p>`;
        }

        try {
            // ── Map operation → backend command + params ──────────
            const commandMap = {
                // ── BIOS ──
                'bios_set':              { cmd: 'set_bios_attributes', p: () => ({attributes: params}) },
                'bios_get_all':          { cmd: 'get_bios_attributes', p: () => ({}) },
                'set_next_boot':         { cmd: 'set_next_boot_device', p: () => ({device: typeof params === 'string' ? params : (params.device || params)}) },
                
                // ── RAID / Storage ──
                'raid_list_vd':          { cmd: 'get_storage_devices', p: () => ({}) },
                'raid_create_vd':        { cmd: 'get_storage_devices', p: () => ({detail: 'create_vd', ...params}) },
                'raid_delete_vd':        { cmd: 'get_storage_devices', p: () => ({detail: 'delete_vd', ...params}) },
                'raid_init_vd':          { cmd: 'get_storage_devices', p: () => ({detail: 'init_vd', ...params}) },
                'raid_controller_info':  { cmd: 'get_storage_devices', p: () => ({}) },
                'raid_check_consistency':{ cmd: 'get_storage_devices', p: () => ({detail: 'consistency_check'}) },
                'raid_clear_foreign':    { cmd: 'get_storage_devices', p: () => ({detail: 'clear_foreign'}) },
                'raid_import_foreign':   { cmd: 'get_storage_devices', p: () => ({detail: 'import_foreign'}) },
                'raid_set_patrol_read':  { cmd: 'get_storage_devices', p: () => ({detail: 'patrol_read'}) },
                'raid_reset_controller': { cmd: 'get_storage_devices', p: () => ({detail: 'reset_controller'}) },
                'raid_rebuild':          { cmd: 'get_storage_devices', p: () => ({detail: 'rebuild', ...params}) },
                'raid_assign_hotspare':  { cmd: 'get_storage_devices', p: () => ({detail: 'assign_hotspare', ...params}) },
                'raid_remove_hotspare':  { cmd: 'get_storage_devices', p: () => ({detail: 'remove_hotspare', ...params}) },
                'raid_replace_drive':    { cmd: 'get_storage_devices', p: () => ({detail: 'replace_drive', ...params}) },
                
                // ── Drive Management ──
                'drive_list':            { cmd: 'get_storage_devices', p: () => ({}) },
                'drive_smart_data':      { cmd: 'get_storage_devices', p: () => ({detail: 'smart'}) },
                'drive_predictive':      { cmd: 'get_storage_devices', p: () => ({detail: 'predictive'}) },
                'drive_media_patrol':    { cmd: 'get_storage_devices', p: () => ({detail: 'patrol'}) },
                'drive_blink_on':        { cmd: 'get_storage_devices', p: () => ({detail: 'blink_on', ...params}) },
                'drive_blink_off':       { cmd: 'get_storage_devices', p: () => ({detail: 'blink_off', ...params}) },
                'drive_set_online':      { cmd: 'get_storage_devices', p: () => ({detail: 'set_online', ...params}) },
                'drive_set_offline':     { cmd: 'get_storage_devices', p: () => ({detail: 'set_offline', ...params}) },
                'drive_secure_erase':    { cmd: 'get_storage_devices', p: () => ({detail: 'secure_erase', ...params}) },
                'drive_convert_raid':    { cmd: 'get_storage_devices', p: () => ({detail: 'convert_raid', ...params}) },
                'drive_convert_nonraid': { cmd: 'get_storage_devices', p: () => ({detail: 'convert_nonraid', ...params}) },
                
                // ── Power & Thermal ──
                'power_on':              { cmd: 'power_on', p: () => ({}) },
                'power_graceful_shutdown': { cmd: 'graceful_shutdown', p: () => ({}) },
                'power_cycle':           { cmd: 'power_cycle', p: () => ({}) },
                'power_force_off':       { cmd: 'force_power_off', p: () => ({}) },
                'power_nmi':             { cmd: 'send_nmi', p: () => ({}) },
                'power_vac_cycle':       { cmd: 'virtual_ac_cycle', p: () => ({}) },
                'power_read_budget':     { cmd: 'get_power_supplies', p: () => ({}) },
                'power_set_cap':         { cmd: 'get_power_supplies', p: () => ({detail: 'set_cap', ...params}) },
                'power_remove_cap':      { cmd: 'get_power_supplies', p: () => ({detail: 'remove_cap'}) },
                'power_history':         { cmd: 'get_power_supplies', p: () => ({}) },
                'thermal_read_sensors':  { cmd: 'get_temperature_sensors', p: () => ({}) },
                'thermal_read_fans':     { cmd: 'get_fans', p: () => ({}) },
                'thermal_profile_default': { cmd: 'set_bios_attributes', p: () => ({attributes: {FanSpeedOffset: 'Off'}}) },
                'thermal_profile_perf':  { cmd: 'set_bios_attributes', p: () => ({attributes: {FanSpeedOffset: 'High'}}) },
                'thermal_profile_quiet': { cmd: 'set_bios_attributes', p: () => ({attributes: {FanSpeedOffset: 'Low'}}) },
                'thermal_exhaust_temp':  { cmd: 'get_temperature_sensors', p: () => ({}) },
                
                // ── iDRAC Management ──
                'idrac_reset':           { cmd: 'reset_idrac', p: () => ({}) },
                'idrac_get_network':     { cmd: 'get_idrac_network_config', p: () => ({}) },
                'idrac_set_static_ip':   { cmd: 'get_idrac_network_config', p: () => ({detail: 'set_static', ...params}) },
                'idrac_set_dhcp':        { cmd: 'get_idrac_network_config', p: () => ({detail: 'set_dhcp'}) },
                'idrac_set_vlan':        { cmd: 'get_idrac_network_config', p: () => ({detail: 'set_vlan', ...params}) },
                'idrac_list_users':      { cmd: 'get_idrac_users', p: () => ({}) },
                'idrac_create_user':     { cmd: 'get_idrac_users', p: () => ({detail: 'create', ...params}) },
                'idrac_change_password': { cmd: 'get_idrac_users', p: () => ({detail: 'change_password', ...params}) },
                'idrac_delete_user':     { cmd: 'get_idrac_users', p: () => ({detail: 'delete', ...params}) },
                'idrac_view_cert':       { cmd: 'get_ssl_certificate_info', p: () => ({}) },
                'idrac_generate_csr':    { cmd: 'get_ssl_certificate_info', p: () => ({detail: 'generate_csr'}) },
                'idrac_upload_cert':     { cmd: 'get_ssl_certificate_info', p: () => ({detail: 'upload_cert', ...params}) },
                'idrac_test_syslog':     { cmd: 'get_idrac_info', p: () => ({detail: 'test_syslog'}) },
                'idrac_launch_vconsole': { cmd: 'get_idrac_info', p: () => ({detail: 'vconsole'}) },
                'idrac_mount_iso':       { cmd: 'get_idrac_info', p: () => ({detail: 'mount_iso', ...params}) },
                'idrac_unmount_media':   { cmd: 'get_idrac_info', p: () => ({detail: 'unmount_media'}) },
                'idrac_clear_sel':       { cmd: 'clear_sel', p: () => ({}) },
                'idrac_clear_lc_log':    { cmd: 'get_lifecycle_logs', p: () => ({detail: 'clear'}) },
                'idrac_export_config':   { cmd: 'export_scp', p: () => ({}) },
                'idrac_import_config':   { cmd: 'export_scp', p: () => ({detail: 'import', ...params}) },
                'idrac_factory_reset':   { cmd: 'reset_idrac', p: () => ({detail: 'factory'}) },
                'idrac_get_info':        { cmd: 'get_idrac_info', p: () => ({}) },
                
                // ── Firmware Lifecycle ──
                'fw_check_catalog':      { cmd: 'get_firmware_inventory', p: () => ({}) },
                'fw_update_bios':        { cmd: 'update_firmware', p: () => ({component: 'BIOS', ...params}) },
                'fw_update_idrac':       { cmd: 'update_firmware', p: () => ({component: 'iDRAC', ...params}) },
                'fw_update_nic':         { cmd: 'update_firmware', p: () => ({component: 'NIC', ...params}) },
                'fw_update_raid':        { cmd: 'update_firmware', p: () => ({component: 'RAID', ...params}) },
                'fw_update_drive':       { cmd: 'update_firmware', p: () => ({component: 'Drive', ...params}) },
                'fw_update_cpld':        { cmd: 'update_firmware', p: () => ({component: 'CPLD', ...params}) },
                'fw_rollback':           { cmd: 'get_firmware_inventory', p: () => ({detail: 'rollback', ...params}) },
                'fw_schedule_update':    { cmd: 'get_firmware_inventory', p: () => ({detail: 'schedule', ...params}) },
                'fw_job_status':         { cmd: 'get_jobs', p: () => ({}) },
                'fw_cancel_jobs':        { cmd: 'delete_all_jobs', p: () => ({}) },
                'fw_compliance_report':  { cmd: 'get_firmware_inventory', p: () => ({}) },
                'fw_download_catalog':   { cmd: 'get_firmware_inventory', p: () => ({detail: 'download_catalog'}) },
                
                // ── Network Config ──
                'nic_inventory':         { cmd: 'get_network_interfaces', p: () => ({}) },
                'nic_statistics':        { cmd: 'get_network_interfaces', p: () => ({detail: 'statistics'}) },
                'nic_enable_port':       { cmd: 'get_network_interfaces', p: () => ({detail: 'enable_port', ...params}) },
                'nic_disable_port':      { cmd: 'get_network_interfaces', p: () => ({detail: 'disable_port', ...params}) },
                'nic_create_team':       { cmd: 'get_network_interfaces', p: () => ({detail: 'create_team', ...params}) },
                'nic_partition':         { cmd: 'get_network_interfaces', p: () => ({detail: 'partition', ...params}) },
                'nic_set_vlan':          { cmd: 'get_network_interfaces', p: () => ({detail: 'set_vlan', ...params}) },
                'nic_wake_on_lan':       { cmd: 'get_network_interfaces', p: () => ({detail: 'wol', ...params}) },
                
                // ── OS & Boot ──
                'boot_get_order':        { cmd: 'get_boot_order', p: () => ({}) },
                'boot_set_hdd_first':    { cmd: 'set_next_boot_device', p: () => ({device: 'Hdd'}) },
                'boot_set_pxe_first':    { cmd: 'set_next_boot_device', p: () => ({device: 'Pxe'}) },
                'boot_set_cd_first':     { cmd: 'set_next_boot_device', p: () => ({device: 'Cd'}) },
                'os_get_drivers':        { cmd: 'get_system_info', p: () => ({}) },
                'os_attach_iso':         { cmd: 'get_idrac_info', p: () => ({detail: 'mount_iso', ...params}) },
                'os_unattended_install': { cmd: 'get_lifecycle_status', p: () => ({detail: 'unattended', ...params}) },
                'lc_get_status':         { cmd: 'get_lifecycle_status', p: () => ({}) },
                'lc_get_remote_services': { cmd: 'get_lifecycle_status', p: () => ({}) },
                'lc_repart':             { cmd: 'get_lifecycle_status', p: () => ({detail: 'reprovision'}) },
                'lc_wipe':               { cmd: 'get_lifecycle_status', p: () => ({detail: 'wipe'}) },
            };

            const mapping = commandMap[operation];
            if (mapping) {
                const response = await fetch(`/api/execute`, {
                    method: 'POST',
                    headers: this._getAuthHeaders(),
                    body: JSON.stringify({ action: mapping.cmd, action_level: actionLevel, parameters: mapping.p() })
                });
                const result = await response.json();
                const data = result.result || result.data || result;
                this.log(`Operation ${operation} completed`, 'success');
                if (resultDiv) {
                    resultDiv.className = 'ops-result ops-result-ok';
                    resultDiv.innerHTML = this._renderOpsResult(operation, data);
                    // F4: Scroll result into view
                    resultDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            } else {
                // Stub — operation not yet mapped to a backend command
                this.log(`Operation ${operation} — stub (ready for backend integration)`, 'info');
                if (resultDiv) {
                    resultDiv.className = 'ops-result';
                    resultDiv.innerHTML = `<div class="ops-result-title">🔧 ${operation}</div><p>This operation is scaffolded and ready for backend integration.</p><p style="color:var(--text-muted);font-size:0.78rem;margin-top:6px">Action level: <strong>${actionLevel}</strong> | Parameters: <code>${JSON.stringify(params)}</code></p>`;
                }
            }
        } catch (error) {
            this.log(`Operation ${operation} failed: ${error.message}`, 'error');
            if (resultDiv) {
                resultDiv.className = 'ops-result ops-result-err';
                resultDiv.innerHTML = `<div class="ops-result-title">❌ ${operation} failed</div><p>${error.message}</p>`;
                resultDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    }

    // ─── Status color map (centralized for all render functions) ──
    static STATUS = { ok: '#10b981', warn: '#f59e0b', crit: '#ef4444', info: '#3b82f6', muted: '#6b7280' };

    // Consistent timestamp format across all displays
    _ts() { return new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); }

    _statusColor(status) {
        const s = (status || '').toLowerCase();
        if (s.includes('ok') || s.includes('online') || s.includes('healthy') || s.includes('enabled') || s === 'true') return DellAIAgent.STATUS.ok;
        if (s.includes('warn') || s.includes('degraded')) return DellAIAgent.STATUS.warn;
        if (s.includes('crit') || s.includes('fail') || s.includes('error') || s.includes('offline')) return DellAIAgent.STATUS.crit;
        if (s.includes('running') || s.includes('progress') || s.includes('connecting')) return DellAIAgent.STATUS.info;
        return DellAIAgent.STATUS.muted;
    }

    // ─── Rich HTML renderers for operation results ──────────
    _renderOpsResult(op, data) {
        const v = (x) => x ?? 'N/A';
        const S = DellAIAgent.STATUS;
        const badge = (text, color) => `<span class="badge" style="background:${color}20;color:${color}">${text}</span>`;
        const sbadge = (status) => { const c = this._statusColor(status); const label = (status||'unknown').toUpperCase(); return badge(label, c); };
        const row = (label, val) => `<tr><td class="tbl-cell">${label}</td><td class="tbl-cell-val">${val}</td></tr>`;
        const tbl = (rows) => `<table class="data-table mt-2">${rows}</table>`;

        // ── BIOS attributes ──
        if (op === 'bios_get_all' && data.bios) {
            const attrs = data.bios;
            const keys = Object.keys(attrs).sort();
            const highlight = ['BootMode','ProcCStates','ProcTurboMode','SysMemMode','TpmSecurity','SriovGlobalEnable','ProcVirtualization','LogicalProc'];
            let importantRows = '';
            let allRows = '';
            for (const k of keys) {
                const r = row(k, v(attrs[k]));
                if (highlight.includes(k)) importantRows += r;
                allRows += r;
            }
            return `<div class="ops-result-title">📋 BIOS Attributes (${keys.length} total)</div>` +
                `<p style="font-size:0.75rem;color:var(--text-muted)">Key settings highlighted first</p>` +
                (importantRows ? `<div style="margin:8px 0;padding:8px;background:var(--bg-input);border-radius:6px"><strong style="font-size:0.75rem">⭐ Key Settings</strong>${tbl(importantRows)}</div>` : '') +
                `<details style="margin-top:8px"><summary style="cursor:pointer;font-size:0.78rem;color:var(--accent)">Show all ${keys.length} attributes</summary>${tbl(allRows)}</details>`;
        }
        if ((op === 'bios_set' || op.startsWith('thermal_profile')) && data.bios_set !== undefined) {
            return data.bios_set
                ? `<div class="ops-result-title">✅ BIOS Changes Staged</div><p>Changes will take effect on next reboot. A server reboot is required to apply.</p>`
                : `<div class="ops-result-title">⚠️ BIOS Set Failed</div><p>The server did not accept the attribute changes. The attribute may not exist on this server model, or the value may be invalid.</p>`;
        }

        // ── Storage / RAID / Drives ──
        if ((op.startsWith('raid_') || op.startsWith('drive_')) && data.storage_devices) {
            const devs = data.storage_devices;
            let html = `<div class="ops-result-title">💾 Storage Inventory (${devs.length} device${devs.length!==1?'s':''})</div>`;
            if (devs.length === 0) return html + '<p>No storage devices found.</p>';
            for (const d of devs) {
                const status = (d.status || '').toLowerCase();
                const statusBadge = sbadge(d.status);
                html += `<div style="margin:8px 0;padding:10px;background:var(--bg-input);border-radius:8px;border:1px solid var(--border-color)">`;
                html += `<div style="display:flex;justify-content:space-between;align-items:center"><strong>${v(d.name || d.model)}</strong>${statusBadge}</div>`;
                html += tbl(
                    row('Type', v(d.media_type || d.type)) +
                    row('Capacity', d.capacity_gb ? `${d.capacity_gb} GB` : v(d.capacity)) +
                    row('Model', v(d.model)) +
                    row('Serial', v(d.serial_number)) +
                    row('Protocol', v(d.protocol)) +
                    row('RAID Level', v(d.raid_level))
                );
                html += `</div>`;
            }
            return html;
        }

        // ── Power supplies ──
        if ((op.startsWith('power_') && !['power_on','power_graceful_shutdown','power_cycle','power_force_off','power_vac_cycle','power_nmi'].includes(op)) && data.power_supplies) {
            const ps = data.power_supplies;
            let html = `<div class="ops-result-title">⚡ Power Supplies (${ps.length})</div>`;
            let totalWatts = 0;
            for (const p of ps) {
                const pw = p.power_watts || 0;
                totalWatts += pw;
                const status = (p.status || '').toLowerCase();
                const statusBadge = sbadge(p.status);
                html += `<div style="margin:6px 0;padding:8px;background:var(--bg-input);border-radius:6px">`;
                html += `<div style="display:flex;justify-content:space-between"><strong>${v(p.name)}</strong>${statusBadge}</div>`;
                html += tbl(row('Power Draw', `${pw} W`) + row('Capacity', p.capacity_watts ? `${p.capacity_watts} W` : 'N/A') + row('Model', v(p.model)) + row('Serial', v(p.serial_number)));
                html += `</div>`;
            }
            html += `<div style="margin-top:10px;padding:8px;background:rgba(99,102,241,0.08);border-radius:6px;text-align:center"><strong>Total Power Draw: ${totalWatts} W</strong></div>`;
            return html;
        }

        // ── Temperature sensors ──
        if (op === 'thermal_read_sensors' && data.temperatures) {
            const temps = data.temperatures;
            let html = `<div class="ops-result-title">🌡️ Temperature Sensors (${temps.length})</div>`;
            for (const t of temps) {
                const reading = t.reading_celsius || 0;
                const upper = t.upper_threshold_critical || 100;
                const pct = Math.min(100, (reading / upper) * 100);
                const color = pct > 80 ? '#ef4444' : pct > 60 ? '#f59e0b' : '#10b981';
                html += `<div style="margin:4px 0;display:flex;align-items:center;gap:8px;font-size:0.8rem">`;
                html += `<span style="min-width:180px;color:var(--text-muted)">${v(t.name)}</span>`;
                html += `<div style="flex:1;height:8px;background:var(--bg-input);border-radius:4px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${color};border-radius:4px"></div></div>`;
                html += `<span style="min-width:60px;text-align:right;font-weight:600;color:${color}">${reading}°C</span>`;
                html += `</div>`;
            }
            return html;
        }

        // ── Fan readings ──
        if (op === 'thermal_read_fans' && data.fans) {
            const fans = data.fans;
            let html = `<div class="ops-result-title">🌀 Fan Status (${fans.length})</div>`;
            for (const f of fans) {
                const rpm = f.speed_rpm || 0;
                const status = (f.status || '').toLowerCase();
                const statusBadge = sbadge(f.status);
                html += `<div style="margin:4px 0;display:flex;align-items:center;gap:8px;font-size:0.8rem">`;
                html += `<span style="min-width:150px;color:var(--text-muted)">${v(f.name)}</span>`;
                html += statusBadge;
                html += `<span style="font-weight:600">${rpm.toLocaleString()} RPM</span>`;
                html += `</div>`;
            }
            return html;
        }

        // ── Power actions ──
        if (['power_on','power_graceful_shutdown','power_cycle','power_force_off','power_vac_cycle'].includes(op)) {
            const success = data.success || data.power_action;
            const icon = (data.success === true || data.power_action) ? '✅' : '⚠️';
            return `<div class="ops-result-title">${icon} Power Action: ${op}</div><p>${data.success ? 'Command sent successfully.' : 'Action result: ' + JSON.stringify(data)}</p>`;
        }

        // ── NMI ──
        if (op === 'power_nmi' && data.nmi_result) {
            return data.nmi_result.success
                ? `<div class="ops-result-title">✅ NMI Sent</div><p>${data.nmi_result.message}</p>`
                : `<div class="ops-result-title">⚠️ NMI Failed</div><p>${data.nmi_result.error}</p>`;
        }

        // ── iDRAC Network ──
        if ((op.startsWith('idrac_') && (op.includes('network') || op.includes('static') || op.includes('dhcp') || op.includes('vlan'))) && data.idrac_network) {
            const net = data.idrac_network;
            if (net.interfaces && net.interfaces.length) {
                let html = `<div class="ops-result-title">🌐 iDRAC Network Interfaces (${net.interfaces.length})</div>`;
                for (const iface of net.interfaces) {
                    html += `<div style="margin:8px 0;padding:10px;background:var(--bg-input);border-radius:8px;border:1px solid var(--border-color)">`;
                    html += `<strong>${v(iface.name)} (${v(iface.id)})</strong>`;
                    html += tbl(
                        row('MAC Address', v(iface.mac_address)) +
                        row('IPv4 Address', `${v(iface.ipv4_address)} / ${v(iface.ipv4_subnet)}`) +
                        row('Gateway', v(iface.ipv4_gateway)) +
                        row('Origin', v(iface.ipv4_origin)) +
                        row('Speed', iface.speed_mbps ? `${iface.speed_mbps} Mbps` : 'N/A') +
                        row('FQDN', v(iface.fqdn)) +
                        row('DNS', (iface.dns_servers || []).join(', ') || 'N/A') +
                        row('VLAN', iface.vlan_enabled ? `Enabled (ID: ${iface.vlan_id})` : 'Disabled')
                    );
                    html += `</div>`;
                }
                return html;
            }
            return `<div class="ops-result-title">🌐 iDRAC Network</div><pre>${JSON.stringify(net, null, 2)}</pre>`;
        }

        // ── iDRAC Users ──
        if ((op.startsWith('idrac_') && (op.includes('user') || op.includes('password'))) && data.idrac_users) {
            const users = data.idrac_users;
            let html = `<div class="ops-result-title">👤 iDRAC User Accounts (${users.length})</div>`;
            if (users.length === 0) return html + '<p>No user accounts found.</p>';
            html += `<table style="width:100%;border-collapse:collapse;font-size:0.8rem;margin-top:8px">`;
            html += `<tr style="border-bottom:1px solid var(--border-color)"><th style="text-align:left;padding:4px 8px;color:var(--text-muted)">ID</th><th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Username</th><th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Role</th><th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Enabled</th><th style="text-align:left;padding:4px 8px;color:var(--text-muted)">Locked</th></tr>`;
            for (const u of users) {
                html += `<tr style="border-bottom:1px solid var(--border-color)"><td style="padding:4px 8px">${v(u.id)}</td><td style="padding:4px 8px;font-weight:600">${v(u.username)}</td><td style="padding:4px 8px">${v(u.role)}</td><td style="padding:4px 8px">${u.enabled ? badge('Yes','#10b981') : badge('No','#6b7280')}</td><td style="padding:4px 8px">${u.locked ? badge('LOCKED','#ef4444') : badge('No','#10b981')}</td></tr>`;
            }
            html += `</table>`;
            return html;
        }

        // ── SSL Certs ──
        if ((op.startsWith('idrac_') && (op.includes('cert') || op.includes('csr'))) && data.ssl_certificates) {
            const certs = data.ssl_certificates;
            if (!certs.available) return `<div class="ops-result-title">🔒 SSL Certificates</div><p>Certificate service not available.</p>`;
            let html = `<div class="ops-result-title">🔒 SSL Certificates (${(certs.certificates||[]).length})</div>`;
            for (const c of (certs.certificates || [])) {
                html += `<div style="margin:8px 0;padding:10px;background:var(--bg-input);border-radius:8px;border:1px solid var(--border-color)">`;
                html += `<strong>Certificate: ${v(c.id)}</strong>`;
                html += tbl(
                    row('Subject', JSON.stringify(c.subject || {})) +
                    row('Issuer', JSON.stringify(c.issuer || {})) +
                    row('Valid From', v(c.valid_not_before)) +
                    row('Valid Until', v(c.valid_not_after)) +
                    row('Key Usage', (c.key_usage || []).join(', '))
                );
                html += `</div>`;
            }
            return html;
        }

        // ── iDRAC reset / clear SEL / export SCP ──
        if ((op === 'idrac_reset' || op === 'idrac_factory_reset') && data.idrac_reset !== undefined) return data.idrac_reset ? `<div class="ops-result-title">✅ iDRAC Reset</div><p>iDRAC is rebooting. It will be unavailable for ~2 minutes.</p>` : `<div class="ops-result-title">⚠️ iDRAC Reset</div><p>Reset command may not have been accepted.</p>`;
        if ((op === 'idrac_clear_sel' || op === 'idrac_clear_lc_log') && data.clear_sel) return data.clear_sel.success ? `<div class="ops-result-title">✅ Log Cleared</div><p>${data.clear_sel.message}</p>` : `<div class="ops-result-title">⚠️ Clear Log Failed</div><p>${data.clear_sel.error}</p>`;
        if ((op === 'idrac_export_config' || op === 'idrac_import_config') && data.scp_export) return data.scp_export.success ? `<div class="ops-result-title">✅ Server Config Operation</div><p>${data.scp_export.message}</p>` : `<div class="ops-result-title">⚠️ Config Operation Failed</div><p>${data.scp_export.error}</p>`;

        // ── Firmware inventory ──
        if ((op === 'fw_check_catalog' || op === 'fw_compliance_report' || op.startsWith('fw_update_') || op === 'fw_rollback' || op === 'fw_download_catalog') && data.firmware_inventory) {
            const fw = data.firmware_inventory;
            let html = `<div class="ops-result-title">📦 Firmware Inventory (${fw.length} components)</div>`;
            if (fw.length === 0) return html + '<p>No firmware data returned.</p>';
            html += `<table style="width:100%;border-collapse:collapse;font-size:0.78rem;margin-top:8px">`;
            html += `<tr style="border-bottom:1px solid var(--border-color)"><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">Component</th><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">Version</th><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">Updateable</th></tr>`;
            for (const f of fw) {
                html += `<tr style="border-bottom:1px solid var(--border-color)"><td style="padding:4px 6px">${v(f.name || f.Name)}</td><td style="padding:4px 6px;font-family:monospace">${v(f.version || f.Version)}</td><td style="padding:4px 6px">${(f.updateable || f.Updateable) ? badge('Yes','#10b981') : badge('No','#6b7280')}</td></tr>`;
            }
            html += `</table>`;
            return html;
        }

        // ── Job queue ──
        if (op === 'fw_job_status' && data.jobs) {
            const jobs = data.jobs;
            let html = `<div class="ops-result-title">📋 Job Queue (${jobs.length} jobs)</div>`;
            if (jobs.length === 0) return html + '<p>No jobs in queue.</p>';
            html += `<table style="width:100%;border-collapse:collapse;font-size:0.78rem;margin-top:8px">`;
            html += `<tr style="border-bottom:1px solid var(--border-color)"><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">Job ID</th><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">Name</th><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">Status</th><th style="text-align:left;padding:4px 6px;color:var(--text-muted)">% Complete</th></tr>`;
            for (const j of jobs) {
                const jStatus = (j.job_status || j.JobState || '').toLowerCase();
                const sb = sbadge(j.job_status || j.JobState);
                html += `<tr style="border-bottom:1px solid var(--border-color)"><td style="padding:4px 6px;font-family:monospace">${v(j.job_id || j.Id)}</td><td style="padding:4px 6px">${v(j.name || j.Name)}</td><td style="padding:4px 6px">${sb}</td><td style="padding:4px 6px">${v(j.percent_complete || j.PercentComplete)}%</td></tr>`;
            }
            html += `</table>`;
            return html;
        }
        if (op === 'fw_cancel_jobs' && data.delete_jobs) return data.delete_jobs.success ? `<div class="ops-result-title">✅ Jobs Cleared</div><p>${data.delete_jobs.message}</p>` : `<div class="ops-result-title">⚠️ Clear Jobs Failed</div><p>${data.delete_jobs.error}</p>`;

        // ── Network interfaces ──
        if ((op.startsWith('nic_')) && data.network_interfaces) {
            const nics = data.network_interfaces;
            let html = `<div class="ops-result-title">🔌 Network Interfaces (${nics.length})</div>`;
            for (const n of nics) {
                const status = (n.status || '').toLowerCase();
                const statusBadge = sbadge(n.status);
                html += `<div style="margin:6px 0;padding:8px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border-color)">`;
                html += `<div style="display:flex;justify-content:space-between"><strong>${v(n.name)}</strong>${statusBadge}</div>`;
                html += tbl(row('MAC', v(n.mac_address)) + row('Speed', n.speed_mbps ? `${n.speed_mbps} Mbps` : 'N/A') + row('Link', v(n.link_status)));
                html += `</div>`;
            }
            return html;
        }

        // ── Boot order ──
        if (op === 'boot_get_order' && data.boot_order) {
            const b = data.boot_order;
            let html = `<div class="ops-result-title">🥾 Boot Configuration</div>`;
            html += tbl(
                row('Current Override', v(b.boot_source_override_target)) +
                row('Override Enabled', v(b.boot_source_override_enabled)) +
                row('Boot Mode', v(b.boot_source_override_mode)) +
                row('UEFI Target', v(b.uefi_target))
            );
            if (b.boot_order && b.boot_order.length) {
                html += `<div style="margin-top:10px"><strong style="font-size:0.78rem">Boot Order:</strong><ol style="margin:4px 0 0 20px;font-size:0.8rem">`;
                for (const item of b.boot_order) html += `<li style="padding:2px 0">${item}</li>`;
                html += `</ol></div>`;
            }
            if (b.allowed_boot_sources && b.allowed_boot_sources.length) {
                html += `<div style="margin-top:8px;font-size:0.75rem;color:var(--text-muted)"><strong>Allowed boot targets:</strong> ${b.allowed_boot_sources.join(', ')}</div>`;
            }
            return html;
        }
        if ((op === 'boot_set_next' || op.startsWith('boot_set_')) && data.next_boot) return data.next_boot.success ? `<div class="ops-result-title">✅ Next Boot Set</div><p>${data.next_boot.message}</p>` : `<div class="ops-result-title">⚠️ Set Next Boot Failed</div><p>${data.next_boot.error}</p>`;

        // ── Lifecycle Controller status ──
        if ((op.startsWith('lc_') || op === 'os_unattended_install') && data.lifecycle_status) {
            const lc = data.lifecycle_status;
            let html = `<div class="ops-result-title">🔄 Lifecycle Controller Status</div>`;
            const healthBadge = (lc.manager_status || '').toLowerCase() === 'ok' ? badge('Healthy','#10b981') : badge(v(lc.manager_status),'#f59e0b');
            html += tbl(
                row('Health', healthBadge) +
                row('State', v(lc.manager_state)) +
                row('Firmware', v(lc.firmware_version)) +
                row('LC Service', lc.lc_service_available ? badge('Available','#10b981') : badge('Unavailable','#6b7280'))
            );
            if (lc.lc_attributes && Object.keys(lc.lc_attributes).length) {
                html += `<details style="margin-top:8px"><summary style="cursor:pointer;font-size:0.78rem;color:var(--accent)">LC Attributes (${Object.keys(lc.lc_attributes).length})</summary>`;
                html += tbl(Object.entries(lc.lc_attributes).map(([k,val]) => row(k, v(val))).join(''));
                html += `</details>`;
            }
            return html;
        }

        // ── VAC cycle ──
        if (op === 'power_vac_cycle' && data.vac_result) return data.vac_result.success ? `<div class="ops-result-title">✅ Virtual AC Cycle</div><p>${data.vac_result.message}</p>` : `<div class="ops-result-title">⚠️ VAC Cycle Failed</div><p>${data.vac_result.error}</p>`;

        // ── iDRAC info (catch-all for idrac operations returning idrac_info) ──
        if (data.idrac_info && typeof data.idrac_info === 'object') {
            const info = data.idrac_info;
            let html = `<div class="ops-result-title">🖥️ iDRAC Information</div>`;
            html += tbl(
                row('Firmware', v(info.firmware_version)) +
                row('Model', v(info.model)) +
                row('Status', v(info.status || info.state)) +
                row('Service Tag', v(info.service_tag))
            );
            return html;
        }

        // ── System info (for os_get_drivers etc) ──
        if (data.system_info && typeof data.system_info === 'object') {
            const si = data.system_info;
            let html = `<div class="ops-result-title">🖥️ System Information</div>`;
            html += tbl(
                row('Model', v(si.model)) +
                row('Manufacturer', v(si.manufacturer)) +
                row('Serial', v(si.serial_number)) +
                row('BIOS', v(si.bios_version)) +
                row('Power State', v(si.power_state))
            );
            return html;
        }

        // ── Success/fail for operations that return a simple result ──
        if (data.success !== undefined) {
            const icon = data.success ? '✅' : '⚠️';
            const msg = data.message || data.error || (data.success ? 'Operation completed successfully.' : 'Operation did not succeed.');
            return `<div class="ops-result-title">${icon} ${op.replace(/_/g, ' ')}</div><p>${msg}</p>`;
        }

        // ── Generic fallback ──
        return `<div class="ops-result-title">📋 ${op.replace(/_/g, ' ')}</div><pre style="max-height:300px;overflow:auto;font-size:0.78rem;background:var(--bg-input);padding:12px;border-radius:8px">${JSON.stringify(data, null, 2)}</pre>`;
    }

    // ─── Overview: Connection Info ──────────────────────────────
    displayConnectionInfo(ci) {
        const c = document.getElementById('connectionInfoContainer');
        if (!c || !ci) return;
        c.innerHTML = `
            <h4>Connection</h4>
            <div class="conn-info-bar">
                <div class="conn-item"><span class="conn-label">Host:</span><span class="conn-value">${this._v(ci.host)}</span></div>
                <div class="conn-item"><span class="conn-label">Method:</span><span class="conn-value">${this._v(ci.method).toUpperCase()}</span></div>
                <div class="conn-item"><span class="conn-label">Connected:</span><span class="conn-value">${ci.connected_at ? new Date(ci.connected_at).toLocaleString() : 'N/A'}</span></div>
                <div class="conn-item"><span class="conn-label">Available:</span><span class="conn-value">${(ci.available_methods || []).map(m => m.toUpperCase()).join(', ') || 'None'}</span></div>
            </div>`;
    }

    // ─── Overview: Server Info ───────────────────────────────────
    displayServerInfo(info) {
        const c = document.getElementById('serverInfoContainer');
        if (!c) return;
        this.inventory.server_info = info;
        const statusBadge = this._badge(info.status);
        c.innerHTML = `
            <div class="section-block">
                <h4>Server Identity</h4>
                <div class="metric-tiles">
                    <div class="metric-tile ${this._tileCls(info.status)}">
                        <div class="tile-value">${this._v(info.model, '—')}</div>
                        <div class="tile-label">Model</div>
                    </div>
                    <div class="metric-tile tile-info">
                        <div class="tile-value">${this._v(info.service_tag, '—')}</div>
                        <div class="tile-label">Service Tag</div>
                    </div>
                    <div class="metric-tile tile-info">
                        <div class="tile-value">${this._v(info.firmware_version, '—')}</div>
                        <div class="tile-label">BIOS / Firmware</div>
                    </div>
                    <div class="metric-tile tile-info">
                        <div class="tile-value">${this._v(info.idrac_version, '—')}</div>
                        <div class="tile-label">iDRAC Version</div>
                    </div>
                    <div class="metric-tile ${this._tileCls(info.status)}">
                        <div class="tile-value"><span class="badge ${statusBadge}">${this._v(info.status)}</span></div>
                        <div class="tile-label">Status</div>
                    </div>
                </div>
            </div>`;
    }

    buildOverviewMetrics(data) {
        const c = document.getElementById('overviewMetricsContainer');
        if (!c) return;
        const tiles = [];
        
        // Overall health tile (first, most prominent)
        if (data.health_status) {
            const hs = data.health_status;
            const overall = (hs.overall_status || 'unknown').toLowerCase();
            const crits = (hs.critical_issues || []).length;
            const warns = (hs.warnings || []).length;
            const cls = overall.includes('ok') ? 'tile-ok' : overall.includes('warn') ? 'tile-warn' : 'tile-crit';
            const label = crits > 0 ? `${crits} critical` : warns > 0 ? `${warns} warnings` : 'All clear';
            tiles.push(`<div class="metric-tile ${cls}"><div class="tile-value">${overall.toUpperCase()}</div><div class="tile-label">Server Health</div><div class="tile-sub">${label}</div></div>`);
        }
        
        if (data.processors && data.processors.length) {
            const totalCores = data.processors.reduce((s, p) => s + (p.cores || 0), 0);
            const totalThreads = data.processors.reduce((s, p) => s + (p.threads || 0), 0);
            tiles.push(`<div class="metric-tile tile-info"><div class="tile-value">${data.processors.length}</div><div class="tile-label">CPUs</div><div class="tile-sub">${totalCores}C / ${totalThreads}T</div></div>`);
        }
        if (data.memory && data.memory.length) {
            const totalGB = data.memory.reduce((s, m) => s + (m.size_gb || 0), 0);
            const populated = data.memory.filter(m => (m.size_gb || 0) > 0).length;
            tiles.push(`<div class="metric-tile tile-info"><div class="tile-value">${totalGB} GB</div><div class="tile-label">Memory</div><div class="tile-sub">${populated}/${data.memory.length} DIMMs</div></div>`);
        }
        if (data.storage_devices && data.storage_devices.length) {
            const totalTB = (data.storage_devices.reduce((s, d) => s + (d.capacity_gb || 0), 0) / 1024).toFixed(1);
            const healthy = data.storage_devices.filter(d => (d.status || '').toLowerCase().includes('ok')).length;
            const cls = healthy === data.storage_devices.length ? 'tile-ok' : 'tile-warn';
            tiles.push(`<div class="metric-tile ${cls}"><div class="tile-value">${totalTB} TB</div><div class="tile-label">Storage</div><div class="tile-sub">${healthy}/${data.storage_devices.length} healthy</div></div>`);
        }
        if (data.network_interfaces && data.network_interfaces.length) {
            const up = data.network_interfaces.filter(n => (n.link_status || '').toLowerCase().includes('up')).length;
            tiles.push(`<div class="metric-tile tile-info"><div class="tile-value">${data.network_interfaces.length}</div><div class="tile-label">NICs</div><div class="tile-sub">${up} link up</div></div>`);
        }
        if (data.temperatures && data.temperatures.length) {
            const readings = data.temperatures.filter(t => t.reading_celsius != null).map(t => t.reading_celsius);
            if (readings.length) {
                const avg = (readings.reduce((a, b) => a + b, 0) / readings.length).toFixed(1);
                const max = Math.max(...readings).toFixed(1);
                const cls = max > 80 ? 'tile-crit' : max > 65 ? 'tile-warn' : 'tile-ok';
                tiles.push(`<div class="metric-tile ${cls}"><div class="tile-value">${avg}&deg;C</div><div class="tile-label">Avg Temp</div><div class="tile-sub">Peak: ${max}&deg;C</div></div>`);
            }
        }
        if (data.fans && data.fans.length) {
            const speeds = data.fans.filter(f => f.speed_rpm != null).map(f => f.speed_rpm);
            if (speeds.length) {
                const avg = Math.round(speeds.reduce((a, b) => a + b, 0) / speeds.length);
                const max = Math.max(...speeds);
                const cls = max > 15000 ? 'tile-warn' : 'tile-ok';
                tiles.push(`<div class="metric-tile ${cls}"><div class="tile-value">${avg.toLocaleString()}</div><div class="tile-label">Avg Fan RPM</div><div class="tile-sub">${data.fans.length} fans</div></div>`);
            }
        }
        if (data.power_supplies && data.power_supplies.length) {
            const totalW = data.power_supplies.reduce((s, ps) => s + (ps.power_watts || 0), 0);
            const healthy = data.power_supplies.filter(ps => {
                const st = (ps.status || '').toLowerCase();
                return st.includes('ok') || st.includes('enabled');
            }).length;
            const cls = healthy === data.power_supplies.length ? 'tile-ok' : healthy === 0 ? 'tile-crit' : 'tile-warn';
            tiles.push(`<div class="metric-tile ${cls}"><div class="tile-value">${totalW}W</div><div class="tile-label">PSU</div><div class="tile-sub">${healthy}/${data.power_supplies.length} healthy</div></div>`);
        }
        if (data.logs && data.logs.length) {
            const crits = data.logs.filter(l => l.severity === 'critical').length;
            const errs = data.logs.filter(l => l.severity === 'error').length;
            const cls = crits > 0 ? 'tile-crit' : errs > 0 ? 'tile-warn' : 'tile-ok';
            tiles.push(`<div class="metric-tile ${cls}"><div class="tile-value">${data.logs.length}</div><div class="tile-label">Events</div><div class="tile-sub">${crits} critical, ${errs} errors</div></div>`);
        }
        if (tiles.length) {
            const now = this._ts();
            c.innerHTML = `<div class="metric-tiles">${tiles.join('')}</div><div class="data-timestamp">Updated: ${now}</div>`;
        }
    }

    // ─── System Info Tab: General ───────────────────────────────
    displaySystemInfo(info) {
        const c = document.getElementById('systemInfoContainer');
        if (!c) return;
        this.inventory.system_info = info;
        c.innerHTML = `
            <table class="data-table">
                <thead><tr><th colspan="2">System Configuration</th></tr></thead>
                <tbody>
                    <tr><td><strong>Manufacturer</strong></td><td>${this._v(info.manufacturer)}</td></tr>
                    <tr><td><strong>Model</strong></td><td>${this._v(info.model)}</td></tr>
                    <tr><td><strong>Serial Number</strong></td><td>${this._v(info.serial_number)}</td></tr>
                    <tr><td><strong>Part Number</strong></td><td>${this._v(info.part_number)}</td></tr>
                    <tr><td><strong>BIOS Version</strong></td><td>${this._v(info.bios_version)}</td></tr>
                    <tr><td><strong>System Type</strong></td><td>${this._v(info.system_type)}</td></tr>
                    <tr><td><strong>Asset Tag</strong></td><td>${this._v(info.asset_tag)}</td></tr>
                    <tr><td><strong>Power State</strong></td><td><span class="badge ${info.power_state === 'On' ? 'badge-ok' : 'badge-offline'}">${this._v(info.power_state)}</span></td></tr>
                    ${info.boot_order && info.boot_order.length ? `<tr><td><strong>Boot Order</strong></td><td>${info.boot_order.join(' &rarr; ')}</td></tr>` : ''}
                </tbody>
            </table>`;
    }

    // ─── System Info Tab: Processors ────────────────────────────
    displayProcessors(procs) {
        const c = document.getElementById('processorsContainer');
        if (!c) return;
        this.inventory.processors = procs;
        if (!procs.length) { c.innerHTML = '<p class="placeholder-text">No processor data available.</p>'; return; }
        const totalCores = procs.reduce((s, p) => s + (p.cores || 0), 0);
        const totalThreads = procs.reduce((s, p) => s + (p.threads || 0), 0);
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${procs.length}</div><div class="tile-label">Sockets</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${totalCores}</div><div class="tile-label">Total Cores</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${totalThreads}</div><div class="tile-label">Total Threads</div></div>
            </div>
            <table class="data-table">
                <thead><tr><th>Socket</th><th>Manufacturer</th><th>Model</th><th>Cores</th><th>Threads</th><th>Speed</th><th>Status</th></tr></thead>
                <tbody>${procs.map(p => `
                    <tr>
                        <td>${this._v(p.socket || p.id)}</td>
                        <td>${this._v(p.manufacturer)}</td>
                        <td>${this._v(p.model)}</td>
                        <td>${this._v(p.cores)}</td>
                        <td>${this._v(p.threads)}</td>
                        <td>${p.speed_mhz ? p.speed_mhz + ' MHz' : 'N/A'}</td>
                        <td><span class="badge ${this._badge(p.status)}">${this._v(p.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>
            <div class="data-timestamp">Refreshed: ${this._ts()}</div>`;
    }

    // ─── System Info Tab: Memory ────────────────────────────────
    displayMemory(mem) {
        const c = document.getElementById('memoryContainer');
        if (!c) return;
        this.inventory.memory = mem;
        if (!mem.length) { c.innerHTML = '<p class="placeholder-text">No memory data available.</p>'; return; }
        const totalGB = mem.reduce((s, m) => s + (m.size_gb || 0), 0);
        const populated = mem.filter(m => m.size_gb && m.size_gb > 0).length;
        const types = [...new Set(mem.map(m => m.type).filter(Boolean))];
        const speeds = [...new Set(mem.map(m => m.speed_mhz).filter(Boolean))];
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${totalGB} GB</div><div class="tile-label">Total Installed</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${populated} / ${mem.length}</div><div class="tile-label">Slots Populated</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${types.join(', ') || 'N/A'}</div><div class="tile-label">Memory Type</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${speeds.join(', ') || 'N/A'}</div><div class="tile-label">Speed (MHz)</div></div>
            </div>
            <table class="data-table">
                <thead><tr><th>Slot</th><th>Manufacturer</th><th>Part Number</th><th>Size</th><th>Type</th><th>Speed</th><th>Status</th></tr></thead>
                <tbody>${mem.map(m => `
                    <tr>
                        <td>${this._v(m.location || m.id)}</td>
                        <td>${this._v(m.manufacturer)}</td>
                        <td>${this._v(m.part_number)}</td>
                        <td>${m.size_gb ? m.size_gb + ' GB' : 'Empty'}</td>
                        <td>${this._v(m.type)}</td>
                        <td>${m.speed_mhz ? m.speed_mhz + ' MHz' : 'N/A'}</td>
                        <td><span class="badge ${this._badge(m.status)}">${this._v(m.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>
            <div class="data-timestamp">Refreshed: ${this._ts()}</div>`;
    }

    // ─── System Info Tab: Storage ───────────────────────────────
    displayStorage(devs) {
        const c = document.getElementById('storageContainer');
        if (!c) return;
        this.inventory.storage = devs;
        if (!devs.length) { c.innerHTML = '<p class="placeholder-text">No storage data available.</p>'; return; }
        const totalTB = (devs.reduce((s, d) => s + (d.capacity_gb || 0), 0) / 1024).toFixed(2);
        const byType = {};
        devs.forEach(d => { const t = d.type || 'Unknown'; byType[t] = (byType[t] || 0) + 1; });
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${devs.length}</div><div class="tile-label">Drives</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${totalTB} TB</div><div class="tile-label">Total Capacity</div></div>
                ${Object.entries(byType).map(([t, n]) => `<div class="metric-tile tile-info"><div class="tile-value">${n}</div><div class="tile-label">${t}</div></div>`).join('')}
            </div>
            <table class="data-table">
                <thead><tr><th>ID</th><th>Name</th><th>Manufacturer</th><th>Model</th><th>Capacity</th><th>Type</th><th>Interface</th><th>Serial</th><th>Firmware</th><th>Status</th></tr></thead>
                <tbody>${devs.map(s => `
                    <tr>
                        <td>${this._v(s.id)}</td>
                        <td>${this._v(s.name)}</td>
                        <td>${this._v(s.manufacturer)}</td>
                        <td>${this._v(s.model)}</td>
                        <td>${s.capacity_gb ? s.capacity_gb + ' GB' : 'N/A'}</td>
                        <td>${this._v(s.type)}</td>
                        <td>${this._v(s.interface)}</td>
                        <td><code>${this._v(s.serial_number)}</code></td>
                        <td>${this._v(s.firmware_version)}</td>
                        <td><span class="badge ${this._badge(s.status)}">${this._v(s.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>
            <div class="data-timestamp">Refreshed: ${this._ts()}</div>`;
    }

    // ─── System Info Tab: Network ───────────────────────────────
    displayNetwork(nics) {
        const c = document.getElementById('networkContainer');
        if (!c) return;
        this.inventory.network = nics;
        if (!nics.length) { c.innerHTML = '<p class="placeholder-text">No network data available.</p>'; return; }
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${nics.length}</div><div class="tile-label">Interfaces</div></div>
                <div class="metric-tile ${nics.some(n => (n.link_status || '').toLowerCase().includes('up')) ? 'tile-ok' : 'tile-warn'}">
                    <div class="tile-value">${nics.filter(n => (n.link_status || '').toLowerCase().includes('up')).length}</div>
                    <div class="tile-label">Links Up</div>
                </div>
            </div>
            <table class="data-table">
                <thead><tr><th>ID</th><th>Name</th><th>MAC Address</th><th>Speed</th><th>Link</th><th>Auto-Neg</th><th>IPv4</th><th>IPv6</th><th>Status</th></tr></thead>
                <tbody>${nics.map(n => `
                    <tr>
                        <td>${this._v(n.id)}</td>
                        <td>${this._v(n.name)}</td>
                        <td><code>${this._v(n.mac_address)}</code></td>
                        <td>${n.speed_mbps ? n.speed_mbps + ' Mbps' : 'N/A'}</td>
                        <td><span class="badge ${(n.link_status || '').toLowerCase().includes('up') ? 'badge-ok' : 'badge-warn'}">${this._v(n.link_status)}</span></td>
                        <td>${n.auto_negotiation != null ? (n.auto_negotiation ? 'Yes' : 'No') : 'N/A'}</td>
                        <td>${n.ipv4_addresses && n.ipv4_addresses.length ? n.ipv4_addresses.join(', ') : 'N/A'}</td>
                        <td>${n.ipv6_addresses && n.ipv6_addresses.length ? n.ipv6_addresses.join(', ') : 'N/A'}</td>
                        <td><span class="badge ${this._badge(n.status)}">${this._v(n.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>
            <div class="data-timestamp">Refreshed: ${this._ts()}</div>`;
    }

    // ─── Health Tab: Overall ────────────────────────────────────
    displayHealthStatus(status) {
        const c = document.getElementById('healthStatusContainer');
        if (!c) return;
        this.inventory.health = status;
        const overall = (status.overall_status || 'unknown').toLowerCase();
        const compEntries = Object.entries(status.components || {});
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile ${this._tileCls(overall)}">
                    <div class="tile-value"><span class="badge ${this._badge(overall)}">${overall.toUpperCase()}</span></div>
                    <div class="tile-label">Overall Health</div>
                </div>
                <div class="metric-tile ${(status.critical_issues || []).length ? 'tile-crit' : 'tile-ok'}">
                    <div class="tile-value">${(status.critical_issues || []).length}</div>
                    <div class="tile-label">Critical Issues</div>
                </div>
                <div class="metric-tile ${(status.warnings || []).length ? 'tile-warn' : 'tile-ok'}">
                    <div class="tile-value">${(status.warnings || []).length}</div>
                    <div class="tile-label">Warnings</div>
                </div>
                <div class="metric-tile tile-info">
                    <div class="tile-value">${compEntries.length}</div>
                    <div class="tile-label">Monitored Components</div>
                </div>
            </div>
            ${compEntries.length ? `
            <table class="data-table">
                <thead><tr><th>Component</th><th>Status</th></tr></thead>
                <tbody>${compEntries.map(([comp, st]) => `
                    <tr><td>${comp}</td><td><span class="badge ${this._badge(st)}">${st}</span></td></tr>
                `).join('')}</tbody>
            </table>` : ''}
            <div class="data-timestamp">Health check as of: ${this._ts()}</div>`;
        // Also populate Issues sub-tab
        this.displayIssues(status);
    }

    displayIssues(status) {
        const c = document.getElementById('issuesContainer');
        if (!c) return;
        const crits = status.critical_issues || [];
        const warns = status.warnings || [];
        if (!crits.length && !warns.length) {
            c.innerHTML = '<div class="section-block"><h4>No Issues Detected</h4><p>All systems operating normally.</p></div>';
            return;
        }
        let html = '';
        if (crits.length) {
            html += `<div class="section-block" style="border-left-color:var(--danger-red)"><h4>Critical Issues (${crits.length})</h4>
                <table class="data-table"><thead><tr><th>Time</th><th>Message</th><th>Source</th><th>Component</th></tr></thead><tbody>
                ${crits.map(i => `<tr><td>${new Date(i.timestamp).toLocaleString()}</td><td>${this._v(i.message)}</td><td>${this._v(i.source)}</td><td>${this._v(i.component)}</td></tr>`).join('')}
                </tbody></table></div>`;
        }
        if (warns.length) {
            html += `<div class="section-block" style="border-left-color:var(--warning-yellow)"><h4>Warnings (${warns.length})</h4>
                <table class="data-table"><thead><tr><th>Time</th><th>Message</th><th>Source</th><th>Component</th></tr></thead><tbody>
                ${warns.map(w => `<tr><td>${new Date(w.timestamp).toLocaleString()}</td><td>${this._v(w.message)}</td><td>${this._v(w.source)}</td><td>${this._v(w.component)}</td></tr>`).join('')}
                </tbody></table></div>`;
        }
        c.innerHTML = html;
    }

    // ─── Health Tab: Thermal ────────────────────────────────────
    displayTemperatures(temps) {
        const c = document.getElementById('thermalContainer');
        if (!c) return;
        this.inventory.temperatures = temps;
        if (!temps.length) { c.innerHTML = '<p class="placeholder-text">No thermal data available.</p>'; return; }
        const readings = temps.filter(t => t.reading_celsius != null);
        const avg = readings.length ? (readings.reduce((s, t) => s + t.reading_celsius, 0) / readings.length).toFixed(1) : 'N/A';
        const max = readings.length ? Math.max(...readings.map(t => t.reading_celsius)).toFixed(1) : 'N/A';
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${temps.length}</div><div class="tile-label">Sensors</div></div>
                <div class="metric-tile ${avg !== 'N/A' && avg > 70 ? 'tile-warn' : 'tile-ok'}"><div class="tile-value">${avg}&deg;C</div><div class="tile-label">Avg Temperature</div></div>
                <div class="metric-tile ${max !== 'N/A' && max > 80 ? 'tile-crit' : max > 65 ? 'tile-warn' : 'tile-ok'}"><div class="tile-value">${max}&deg;C</div><div class="tile-label">Peak Temperature</div></div>
            </div>
            <div class="thermal-gauge-grid">
                ${temps.map(t => {
                    const val = t.reading_celsius != null ? t.reading_celsius : null;
                    const cls = val != null ? this._tempCls(val, t.upper_threshold_non_critical, t.upper_threshold_critical) : '';
                    return `<div class="thermal-gauge">
                        <div class="gauge-name">${this._v(t.name || t.id)}</div>
                        <div class="gauge-value ${cls}">${val != null ? val + '&deg;C' : 'N/A'}</div>
                        <div class="gauge-range">${t.upper_threshold_non_critical != null ? 'Warn: ' + t.upper_threshold_non_critical + '&deg;C' : ''} ${t.upper_threshold_critical != null ? '| Crit: ' + t.upper_threshold_critical + '&deg;C' : ''}</div>
                        <div style="font-size:0.78rem;color:#aaa;margin-top:2px">Status: ${this._v(t.status)} | Location: ${this._v(t.location)}</div>
                    </div>`;
                }).join('')}
            </div>
            <table class="data-table" style="margin-top:18px">
                <thead><tr><th>Sensor</th><th>Reading</th><th>Location</th><th>Warn Threshold</th><th>Crit Threshold</th><th>Status</th></tr></thead>
                <tbody>${temps.map(t => `
                    <tr>
                        <td>${this._v(t.name || t.id)}</td>
                        <td>${t.reading_celsius != null ? t.reading_celsius + '&deg;C' : 'N/A'}</td>
                        <td>${this._v(t.location)}</td>
                        <td>${t.upper_threshold_non_critical != null ? t.upper_threshold_non_critical + '&deg;C' : 'N/A'}</td>
                        <td>${t.upper_threshold_critical != null ? t.upper_threshold_critical + '&deg;C' : 'N/A'}</td>
                        <td><span class="badge ${this._badge(t.status)}">${this._v(t.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>
            <div class="data-timestamp">Temperature readings as of: ${this._ts()}</div>`;
    }

    // ─── Health Tab: Fans (appended to Thermal) ─────────────────
    displayFans(fans) {
        const tc = document.getElementById('thermalContainer');
        if (!tc) return;
        this.inventory.fans = fans;
        if (!fans.length) return;
        const speeds = fans.filter(f => f.speed_rpm != null).map(f => f.speed_rpm);
        const avg = speeds.length ? Math.round(speeds.reduce((a, b) => a + b, 0) / speeds.length) : 'N/A';
        tc.innerHTML += `
            <h4 style="margin-top:24px">Fan Status</h4>
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${fans.length}</div><div class="tile-label">Fans</div></div>
                <div class="metric-tile tile-ok"><div class="tile-value">${avg}</div><div class="tile-label">Avg RPM</div></div>
            </div>
            <table class="data-table">
                <thead><tr><th>Fan</th><th>Speed (RPM)</th><th>Location</th><th>Min RPM</th><th>Max RPM</th><th>Status</th></tr></thead>
                <tbody>${fans.map(f => `
                    <tr>
                        <td>${this._v(f.name || f.id)}</td>
                        <td>${f.speed_rpm != null ? f.speed_rpm : 'N/A'}</td>
                        <td>${this._v(f.location)}</td>
                        <td>${f.min_speed_rpm != null ? f.min_speed_rpm : 'N/A'}</td>
                        <td>${f.max_speed_rpm != null ? f.max_speed_rpm : 'N/A'}</td>
                        <td><span class="badge ${this._badge(f.status)}">${this._v(f.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>`;
    }

    // ─── Health Tab: Power ──────────────────────────────────────
    displayPowerSupplies(psus) {
        const c = document.getElementById('powerContainer');
        if (!c) return;
        this.inventory.power_supplies = psus;
        if (!psus.length) { c.innerHTML = '<p class="placeholder-text">No power supply data available.</p>'; return; }
        const totalW = psus.reduce((s, p) => s + (p.power_watts || 0), 0);
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${psus.length}</div><div class="tile-label">PSUs Installed</div></div>
                <div class="metric-tile tile-info"><div class="tile-value">${totalW}W</div><div class="tile-label">Total Capacity</div></div>
            </div>
            <div class="component-cards">
                ${psus.map(ps => `
                    <div class="component-card">
                        <h5>PSU ${this._v(ps.id)}</h5>
                        <div class="detail-row"><span class="detail-label">Manufacturer</span><span class="detail-value">${this._v(ps.manufacturer)}</span></div>
                        <div class="detail-row"><span class="detail-label">Model</span><span class="detail-value">${this._v(ps.model)}</span></div>
                        <div class="detail-row"><span class="detail-label">Capacity</span><span class="detail-value">${ps.power_watts ? ps.power_watts + 'W' : 'N/A'}</span></div>
                        <div class="detail-row"><span class="detail-label">Input Voltage</span><span class="detail-value">${ps.input_voltage != null ? ps.input_voltage + 'V' : 'N/A'}</span></div>
                        <div class="detail-row"><span class="detail-label">Output Voltage</span><span class="detail-value">${ps.output_voltage != null ? ps.output_voltage + 'V' : 'N/A'}</span></div>
                        <div class="detail-row"><span class="detail-label">Efficiency</span><span class="detail-value">${ps.efficiency != null ? ps.efficiency + '%' : 'N/A'}</span></div>
                        <div class="detail-row"><span class="detail-label">Firmware</span><span class="detail-value">${this._v(ps.firmware_version)}</span></div>
                        <div class="detail-row"><span class="detail-label">Status</span><span class="detail-value"><span class="badge ${this._badge(ps.status)}">${this._v(ps.status)}</span></span></div>
                    </div>`).join('')}
            </div>
            <div class="data-timestamp">PSU data as of: ${this._ts()}</div>`;
    }

    displayPerformanceMetrics(metrics) {
        const c = document.getElementById('overviewMetricsContainer');
        if (!c) return;
        const tiles = [];
        if (metrics.power_consumption != null) tiles.push(`<div class="metric-tile tile-info"><div class="tile-value">${metrics.power_consumption}W</div><div class="tile-label">Power Draw</div></div>`);
        if (metrics.temperature_average != null) tiles.push(`<div class="metric-tile ${metrics.temperature_average > 70 ? 'tile-warn' : 'tile-ok'}"><div class="tile-value">${metrics.temperature_average.toFixed(1)}&deg;C</div><div class="tile-label">Avg Temp</div></div>`);
        if (metrics.temperature_max != null) tiles.push(`<div class="metric-tile ${metrics.temperature_max > 80 ? 'tile-crit' : 'tile-ok'}"><div class="tile-value">${metrics.temperature_max.toFixed(1)}&deg;C</div><div class="tile-label">Max Temp</div></div>`);
        if (metrics.fan_speed_average != null) tiles.push(`<div class="metric-tile tile-ok"><div class="tile-value">${metrics.fan_speed_average.toFixed(0)}</div><div class="tile-label">Avg Fan RPM</div></div>`);
        if (tiles.length) c.innerHTML += `<div class="metric-tiles">${tiles.join('')}</div>`;
    }

    // ─── System Info Tab: BIOS Settings ─────────────────────────
    displayBios(bios) {
        const c = document.getElementById('biosContainer');
        if (!c) return;
        this.inventory.bios = bios;
        const attrs = bios.attributes || {};
        const keys = Object.keys(attrs);
        if (!keys.length) { c.innerHTML = '<p class="placeholder-text">No BIOS attributes available (requires Redfish).</p>'; return; }
        c.innerHTML = `
            <div class="section-block">
                <h4>BIOS Configuration</h4>
                <div class="detail-row"><span class="detail-label">Registry</span><span class="detail-value">${this._v(bios.attribute_registry)}</span></div>
                <div class="detail-row"><span class="detail-label">Total Attributes</span><span class="detail-value">${keys.length}</span></div>
            </div>
            <div class="bios-search-bar">
                <input type="text" class="form-input" id="biosSearchInput" placeholder="Search BIOS attributes..." oninput="app.filterBiosTable()">
            </div>
            <div class="bios-count" id="biosCount">Showing ${keys.length} of ${keys.length} attributes</div>
            <table class="data-table" id="biosTable">
                <thead><tr><th>Attribute</th><th>Value</th></tr></thead>
                <tbody>${keys.sort().map(k => `<tr><td><strong>${k}</strong></td><td><code>${String(attrs[k])}</code></td></tr>`).join('')}</tbody>
            </table>`;
    }

    filterBiosTable() {
        const search = (document.getElementById('biosSearchInput')?.value || '').toLowerCase();
        const table = document.getElementById('biosTable');
        if (!table) return;
        const rows = table.querySelectorAll('tbody tr');
        let shown = 0;
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const match = !search || text.includes(search);
            row.style.display = match ? '' : 'none';
            if (match) shown++;
        });
        const countEl = document.getElementById('biosCount');
        if (countEl) countEl.textContent = `Showing ${shown} of ${rows.length} attributes`;
    }

    // ─── System Info Tab: Firmware Inventory ────────────────────
    displayFirmware(fwList) {
        const c = document.getElementById('firmwareContainer');
        if (!c) return;
        this.inventory.firmware = fwList;
        if (!fwList.length) { c.innerHTML = '<p class="placeholder-text">No firmware inventory available (requires Redfish).</p>'; return; }
        const updateable = fwList.filter(f => f.updateable).length;
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${fwList.length}</div><div class="tile-label">Components</div></div>
                <div class="metric-tile tile-ok"><div class="tile-value">${updateable}</div><div class="tile-label">Updateable</div></div>
            </div>
            <table class="data-table">
                <thead><tr><th>Component</th><th>Version</th><th>Updateable</th><th>Manufacturer</th><th>Release Date</th><th>Status</th></tr></thead>
                <tbody>${fwList.map(fw => `
                    <tr>
                        <td><strong>${this._v(fw.name)}</strong><br><span style="font-size:0.8rem;color:#888">${this._v(fw.component_id)}</span></td>
                        <td><code>${this._v(fw.version)}</code></td>
                        <td><span class="${fw.updateable ? 'fw-updateable' : 'fw-not-updateable'}">${fw.updateable ? 'Yes' : 'No'}</span></td>
                        <td>${this._v(fw.manufacturer)}</td>
                        <td>${this._v(fw.release_date)}</td>
                        <td><span class="badge ${this._badge(fw.status)}">${this._v(fw.status)}</span></td>
                    </tr>`).join('')}
                </tbody>
            </table>`;
    }

    // ─── System Info Tab: iDRAC ─────────────────────────────────
    displayIdracInfo(info) {
        const c = document.getElementById('idracContainer');
        if (!c) return;
        if (!info || !info.firmware_version) { c.innerHTML = '<p class="placeholder-text">No iDRAC info available.</p>'; return; }
        const np = info.network_protocol || {};
        c.innerHTML = `
            <div class="section-block">
                <h4>iDRAC Controller</h4>
                <table class="data-table">
                    <tbody>
                        <tr><td><strong>Model</strong></td><td>${this._v(info.model)}</td></tr>
                        <tr><td><strong>Firmware</strong></td><td><code>${this._v(info.firmware_version)}</code></td></tr>
                        <tr><td><strong>Status</strong></td><td><span class="badge ${this._badge(info.status)}">${this._v(info.status)}</span></td></tr>
                        <tr><td><strong>Date/Time</strong></td><td>${info.date_time ? new Date(info.date_time).toLocaleString() : 'N/A'}</td></tr>
                        <tr><td><strong>UUID</strong></td><td><code>${this._v(info.uuid)}</code></td></tr>
                        <tr><td><strong>Hostname</strong></td><td>${this._v(np.hostname)}</td></tr>
                    </tbody>
                </table>
            </div>
            <h4>Network Protocols</h4>
            <div class="idrac-protocol-grid">
                <div class="protocol-item"><div class="proto-name">HTTPS</div><div class="proto-status" style="color:${np.https_enabled ? 'var(--success-green)' : 'var(--danger-red)'}">${np.https_enabled ? 'Enabled' : 'Disabled'}</div></div>
                <div class="protocol-item"><div class="proto-name">SSH</div><div class="proto-status" style="color:${np.ssh_enabled ? 'var(--success-green)' : 'var(--danger-red)'}">${np.ssh_enabled ? 'Enabled' : 'Disabled'}</div></div>
                <div class="protocol-item"><div class="proto-name">IPMI</div><div class="proto-status" style="color:${np.ipmi_enabled ? 'var(--success-green)' : 'var(--danger-red)'}">${np.ipmi_enabled ? 'Enabled' : 'Disabled'}</div></div>
                <div class="protocol-item"><div class="proto-name">SNMP</div><div class="proto-status" style="color:${np.snmp_enabled ? 'var(--success-green)' : 'var(--danger-red)'}">${np.snmp_enabled ? 'Enabled' : 'Disabled'}</div></div>
            </div>`;
    }

    displayNetworkAdapters(adapters) {
        this.displayNetwork(adapters);
    }
    
    displayThermalStatus(data) {
        if (data.temperatures) this.displayTemperatures(data.temperatures);
        if (data.fans) this.displayFans(data.fans);
    }
    
    displayPowerStatus(data) {
        if (data.power_supplies) this.displayPowerSupplies(data.power_supplies);
    }
    
    displayStorageStatus(data) {
        if (data.drives) this.displayStorage(data.drives);
        else this.displayStorage(data);
    }
    
    displayMemoryStatus(data) {
        if (data.dimms) this.displayMemory(data.dimms);
        else this.displayMemory(data);
    }

    // ─── Troubleshooting Tab: POST Codes ────────────────────────
    displayPostCodes(codes) {
        const c = document.getElementById('postCodeContainer');
        if (!c) return;
        if (!codes || (!codes.last_state && !codes.post_code)) { c.innerHTML = '<p class="placeholder-text">No POST code data available.</p>'; return; }
        c.innerHTML = `
            <div class="post-code-display">
                <div class="post-code-value">${this._v(codes.post_code, '—')}</div>
                <div class="post-code-label">Last POST Code</div>
            </div>
            <table class="data-table">
                <tbody>
                    <tr><td><strong>Boot Progress</strong></td><td>${this._v(codes.last_state)}</td></tr>
                    <tr><td><strong>OEM Last State</strong></td><td>${this._v(codes.oem_last_state)}</td></tr>
                    <tr><td><strong>Power State</strong></td><td><span class="badge ${codes.power_state === 'On' ? 'badge-ok' : 'badge-offline'}">${this._v(codes.power_state)}</span></td></tr>
                    <tr><td><strong>System Generation</strong></td><td>${this._v(codes.system_generation)}</td></tr>
                    <tr><td><strong>Boot Source Override</strong></td><td>${this._v(codes.boot_source_override)}</td></tr>
                    <tr><td><strong>Override Enabled</strong></td><td>${this._v(codes.boot_source_override_enabled)}</td></tr>
                </tbody>
            </table>`;
    }

    // ─── Troubleshooting Tab: Job Queue ─────────────────────────
    displayJobs(jobs) {
        const c = document.getElementById('jobsContainer');
        if (!c) return;
        if (!jobs || !jobs.length) { c.innerHTML = '<p class="placeholder-text">No jobs in queue.</p>'; return; }
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${jobs.length}</div><div class="tile-label">Jobs</div></div>
                <div class="metric-tile tile-ok"><div class="tile-value">${jobs.filter(j => j.job_state === 'Completed').length}</div><div class="tile-label">Completed</div></div>
                <div class="metric-tile tile-warn"><div class="tile-value">${jobs.filter(j => j.job_state === 'Running' || j.job_state === 'Scheduled').length}</div><div class="tile-label">Active</div></div>
            </div>
            <table class="data-table">
                <thead><tr><th>ID</th><th>Name</th><th>Type</th><th>State</th><th>Progress</th><th>Message</th><th>Start</th></tr></thead>
                <tbody>${jobs.map(j => `
                    <tr>
                        <td><code>${this._v(j.id)}</code></td>
                        <td>${this._v(j.name)}</td>
                        <td>${this._v(j.job_type)}</td>
                        <td><span class="badge ${j.job_state === 'Completed' ? 'badge-ok' : j.job_state === 'Failed' ? 'badge-crit' : 'badge-info'}">${this._v(j.job_state)}</span></td>
                        <td>${j.percent_complete != null ? j.percent_complete + '%' : 'N/A'}</td>
                        <td>${this._v(j.message)}</td>
                        <td>${this._v(j.start_time)}</td>
                    </tr>`).join('')}
                </tbody>
            </table>`;
    }

    // ─── Troubleshooting Tab: TSR Result ────────────────────────
    displayTsrResult(tsr) {
        const c = document.getElementById('tsrStatusContainer');
        if (!c) return;
        if (tsr.success) {
            const jobId = tsr.job_id || '';
            const method = tsr.method || 'TSR Export';
            c.innerHTML = `
                <div class="section-block" style="border-left-color: var(--success-green)" id="tsrJobBlock">
                    <h4>📦 TSR Collection In Progress</h4>
                    <p><strong>Method:</strong> ${method}</p>
                    <p>${this._v(tsr.message, 'Tech Support Report collection has been started.')}</p>
                    ${jobId ? `<p><strong>Job ID:</strong> <code>${jobId}</code></p>` : ''}
                    <div id="tsrProgressArea" style="margin-top:12px">
                        <div style="display:flex;align-items:center;gap:10px">
                            <div style="flex:1;background:#2a2d35;border-radius:6px;height:24px;overflow:hidden">
                                <div id="tsrProgressBar" style="width:0%;height:100%;background:linear-gradient(90deg,#4a9eff,#00c6ff);border-radius:6px;transition:width 0.5s ease;display:flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:600;color:#fff">0%</div>
                            </div>
                            <span id="tsrProgressPct" style="font-weight:600;min-width:40px">0%</span>
                        </div>
                        <p id="tsrStatusMsg" style="color:#aaa;font-size:0.85rem;margin-top:6px">Waiting for iDRAC to begin collection...</p>
                    </div>
                </div>`;
            // Start polling if we have a job ID
            if (jobId) {
                this._pollTsrJob(jobId);
            } else {
                document.getElementById('tsrStatusMsg').textContent = 'No job ID returned — check Job Queue tab manually.';
            }
        } else {
            c.innerHTML = `
                <div class="section-block" style="border-left-color: var(--danger-red)">
                    <h4>❌ TSR Export Failed</h4>
                    <p>${this._v(tsr.error, 'Unable to initiate TSR export.')}</p>
                    <p style="color:#888;font-size:0.88rem;margin-top:8px">Try exporting manually via the iDRAC web UI (see instructions below).</p>
                </div>`;
        }
    }

    async _pollTsrJob(jobId) {
        const bar = document.getElementById('tsrProgressBar');
        const pct = document.getElementById('tsrProgressPct');
        const msg = document.getElementById('tsrStatusMsg');
        const block = document.getElementById('tsrJobBlock');
        if (!bar || !pct || !msg || !block) return;

        let attempts = 0;
        const maxAttempts = 120; // poll for up to 10 minutes (every 5s)

        const poll = async () => {
            attempts++;
            try {
                const response = await fetch(`/api/execute`, {
                    method: 'POST',
                    headers: this._getAuthHeaders(),
                    body: JSON.stringify({ action_level: 'full_control', command: 'get_job_status', parameters: { job_id: jobId } })
                });
                const result = await response.json();
                const job = result?.data?.job_status;

                if (!job || !job.success) {
                    msg.textContent = `Polling... (attempt ${attempts}) — ${job?.error || 'waiting for response'}`;
                    if (attempts < maxAttempts) setTimeout(poll, 5000);
                    return;
                }

                const percent = job.percent_complete || 0;
                const state = job.state || 'Unknown';
                const jobMsg = job.message || '';

                bar.style.width = `${percent}%`;
                bar.textContent = `${percent}%`;
                pct.textContent = `${percent}%`;
                msg.textContent = `${state}${jobMsg ? ' — ' + jobMsg : ''}`;
                this.log(`TSR Job ${jobId}: ${state} (${percent}%)`, 'info');

                if (job.completed) {
                    // Handle "already running" failure — show note to wait and retry
                    const alreadyRunning = job.failed && jobMsg.toLowerCase().includes('already running');
                    if (alreadyRunning) {
                        block.style.borderLeftColor = 'var(--warning-amber)';
                        bar.style.background = 'linear-gradient(90deg,#f59e0b,#fbbf24)';
                        bar.style.width = '100%';
                        bar.textContent = '—';
                        pct.textContent = '—';
                        block.querySelector('h4').textContent = '⏳ TSR Already In Progress';
                        msg.innerHTML = `<strong>Another SupportAssist collection is already running on this server.</strong><br><span style="color:#aaa;font-size:0.85rem">Wait for the current collection to complete, then try again. Check the <strong>Job Queue</strong> sub-tab for the active job.</span>`;
                        this.log(`⏳ TSR Job ${jobId}: another collection already running`, 'warning');
                        this.executeAction('get_jobs');
                        return;
                    }

                    block.style.borderLeftColor = job.failed ? 'var(--warning-amber)' : 'var(--success-green)';
                    bar.style.background = job.failed ? 'linear-gradient(90deg,#f59e0b,#ef4444)' : 'linear-gradient(90deg,#10b981,#34d399)';
                    bar.style.width = '100%';
                    bar.textContent = '100%';
                    pct.textContent = '100%';

                    const statusIcon = job.failed ? '⚠️' : '✅';
                    const statusText = job.failed ? 'TSR completed with errors' : 'TSR collection completed successfully';
                    block.querySelector('h4').textContent = `${statusIcon} ${statusText}`;
                    msg.innerHTML = `<strong>${state}</strong>${jobMsg ? ' — ' + jobMsg : ''}<br><span style="color:#888;font-size:0.85rem">The TSR file is stored on the iDRAC. Access it via: <code>https://${this.currentServer}/sysmgmt/2012/server/SA/TSR</code> or the iDRAC web UI under Maintenance → SupportAssist.</span>`;
                    this.log(`✅ TSR Job ${jobId} completed: ${state}`, 'success');
                    // Refresh job queue display
                    this.executeAction('get_jobs');
                    return;
                }

                if (attempts < maxAttempts) setTimeout(poll, 5000);
                else msg.textContent = `Polling stopped after ${maxAttempts} attempts. Check Job Queue tab.`;
            } catch (e) {
                msg.textContent = `Poll error: ${e.message}. Retrying...`;
                if (attempts < maxAttempts) setTimeout(poll, 5000);
            }
        };

        setTimeout(poll, 3000); // Start polling after 3s
    }

    // ─── Advanced Tab: Lifecycle Logs ────────────────────────────
    async fetchLifecycleLogs() {
        await this.executeAction('get_lifecycle_logs');
    }

    renderFilteredLcLogs() {
        const container = document.getElementById('lifecycleLogsContainer');
        if (!container) return;
        const sevFilter = document.getElementById('lcSeverityFilter')?.value || 'all';
        const searchVal = (document.getElementById('lcSearchInput')?.value || '').toLowerCase();
        let filtered = this.rawLcLogs;
        if (sevFilter !== 'all') filtered = filtered.filter(l => l.severity === sevFilter);
        if (searchVal) filtered = filtered.filter(l =>
            (l.message || '').toLowerCase().includes(searchVal) ||
            (l.message_id || '').toLowerCase().includes(searchVal) ||
            (l.category || '').toLowerCase().includes(searchVal)
        );
        if (!filtered.length) { container.innerHTML = '<p class="placeholder-text">No lifecycle logs match the filter.</p>'; return; }
        container.innerHTML = filtered.slice(0, 500).map(log => {
            const sevCls = log.severity === 'Critical' ? 'lc-critical' : log.severity === 'Warning' ? 'lc-warning' : 'lc-ok';
            return `<div class="lc-log-entry ${sevCls}">
                <div>${this._v(log.message, '(no message)')}</div>
                <div class="lc-meta">
                    <span>${log.created ? new Date(log.created).toLocaleString() : 'N/A'}</span>
                    <span>${this._v(log.severity)}</span>
                    <span>${this._v(log.message_id)}</span>
                    <span>${this._v(log.category)}</span>
                </div>
            </div>`;
        }).join('');
        container.scrollTop = 0;
    }

    // ─── Advanced Tab: Monitoring ────────────────────────────────
    async startMonitoring() {
        if (this.monitoringInterval) return;
        if (!this._requireConnection('starting monitoring')) return;
        this.monitoringSnapshots = [];
        document.getElementById('startMonitoringBtn').disabled = true;
        document.getElementById('stopMonitoringBtn').disabled = false;
        const badge = document.getElementById('monitoringStatus');
        if (badge) { badge.textContent = 'Active'; badge.className = 'monitoring-badge monitoring-active'; }
        this.log('Monitoring started (30s interval)', 'info');
        await this.captureSnapshot();
        this.monitoringInterval = setInterval(() => this.captureSnapshot(), 30000);
    }

    stopMonitoring() {
        if (this.monitoringInterval) { clearInterval(this.monitoringInterval); this.monitoringInterval = null; }
        this.monitoringSnapshots = [];
        document.getElementById('startMonitoringBtn').disabled = false;
        document.getElementById('stopMonitoringBtn').disabled = true;
        const badge = document.getElementById('monitoringStatus');
        if (badge) { badge.textContent = 'Stopped'; badge.className = 'monitoring-badge'; }
        this.log('Monitoring stopped', 'info');
    }

    async captureSnapshot() {
        try {
            const response = await fetch(`/api/execute`, {
                method: 'POST',
                headers: this._getAuthHeaders(),
                body: JSON.stringify({ action_level: this.actionLevel, action: 'health_check', parameters: {} })
            });
            const result = await response.json();
            if (!response.ok) return;
            const data = result.result || result.data || {};
            const snap = { time: new Date(), data };
            this.monitoringSnapshots.push(snap);
            if (this.monitoringSnapshots.length > 60) this.monitoringSnapshots.shift();
            this.renderMonitoringSnapshots();
        } catch (e) { this.log(`Monitoring snapshot error: ${e.message}`, 'error'); }
    }

    renderMonitoringSnapshots() {
        const c = document.getElementById('monitoringContainer');
        if (!c) return;
        if (!this.monitoringSnapshots.length) { c.innerHTML = '<p class="placeholder-text">No snapshots yet.</p>'; return; }
        const latest = this.monitoringSnapshots[this.monitoringSnapshots.length - 1];
        const hs = latest?.data?.health_status || {};
        const overall = hs.overall_status || 'unknown';
        const crits = (hs.critical_issues || []).length;
        const warns = (hs.warnings || []).length;
        c.innerHTML = `
            <div class="metric-tiles">
                <div class="metric-tile tile-info"><div class="tile-value">${this.monitoringSnapshots.length}</div><div class="tile-label">Snapshots</div></div>
                <div class="metric-tile ${this._tileCls(overall)}"><div class="tile-value"><span class="badge ${this._badge(overall)}">${String(overall).toUpperCase()}</span></div><div class="tile-label">Current Status</div></div>
                <div class="metric-tile ${crits ? 'tile-crit' : 'tile-ok'}"><div class="tile-value">${crits}</div><div class="tile-label">Critical Issues</div></div>
                <div class="metric-tile ${warns ? 'tile-warn' : 'tile-ok'}"><div class="tile-value">${warns}</div><div class="tile-label">Warnings</div></div>
            </div>
            <div style="max-height:300px;overflow-y:auto">
                ${this.monitoringSnapshots.slice().reverse().map(s => {
                    const shs = s?.data?.health_status || {};
                    return `<div class="monitoring-snapshot">
                        <div class="snap-time">${(s.time ? s.time.toLocaleTimeString() : 'N/A')}</div>
                        <span class="badge ${this._badge(shs.overall_status || 'unknown')}">${String(shs.overall_status || 'unknown').toUpperCase()}</span>
                        — ${(shs.critical_issues || []).length} critical, ${(shs.warnings || []).length} warnings
                    </div>`;
                }).join('')}
            </div>`; 
    }

    // ─── Advanced Tab: runAdvanced dispatcher ─────────────────────
    async runAdvanced(action) {
        if (!this._requireConnection('running advanced actions')) return;

        // Map action -> endpoint + result container
        const mapping = {
            'diagnostics_summary': { url: '/api/server/diagnostics-summary', resultId: 'advDiagnosticsResult' },
            'connectivity_test':   { cmd: 'connectivity_test', resultId: 'advDiagnosticsResult' },
            'check_idrac':         { url: '/check-idrac', method: 'POST', body: {}, resultId: 'advDiagnosticsResult' },
            'post_codes':          { cmd: 'get_post_codes', resultId: 'advDiagnosticsResult' },
            'support_collection':  { cmd: 'export_tsr', level: 'diagnostic', resultId: 'advDiagnosticsResult' },
            'health_score':        { cmd: 'check_health_score', resultId: 'advHealthResult' },
            'server_snapshot':     { url: '/api/server/snapshot', resultId: 'advSnapshotResult' },
            'server_timeline':     { url: '/api/server/timeline', resultId: 'advSnapshotResult' },
            'predictive_analysis': { url: '/predictive-analysis', method: 'POST', body: {}, resultId: 'advPredictiveResult' },
            'firmware_compliance': { cmd: 'get_firmware_inventory', resultId: 'advPredictiveResult' },
            'audit_log':          { url: '/api/audit-log?limit=50', resultId: 'advAuditResult' },
        };

        const m = mapping[action];
        if (!m) { this.showAlert(`Unknown advanced action: ${action}`, 'error'); return; }

        const resultDiv = document.getElementById(m.resultId);
        if (resultDiv) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'action-result';
            resultDiv.innerHTML = `<div style="padding:12px;color:var(--text-muted)">Running ${action}...</div>`;
        }

        try {
            let data;
            if (m.url) {
                // Direct API endpoint call
                const opts = { method: m.method || 'GET', headers: this._getAuthHeaders() };
                if (m.body) opts.body = JSON.stringify(m.body);
                const r = await fetch(m.url, opts);
                data = await r.json();
            } else if (m.cmd) {
                // Via /api/execute
                const r = await fetch('/api/execute', {
                    method: 'POST',
                    headers: this._getAuthHeaders(),
                    body: JSON.stringify({ action: m.cmd, action_level: m.level || this.actionLevel, parameters: {} })
                });
                data = await r.json();
                data = data.result || data;
            }

            this.log(`Advanced: ${action} completed`, 'success');
            if (resultDiv) {
                resultDiv.className = 'action-result result-success';
                resultDiv.innerHTML = this._renderAdvancedResult(action, data);
            }
        } catch (error) {
            this.log(`Advanced ${action} failed: ${error.message}`, 'error');
            if (resultDiv) {
                resultDiv.className = 'action-result result-error';
                resultDiv.innerHTML = `<strong>Error:</strong> ${error.message}`;
            }
        }
    }

    _renderAdvancedResult(action, data) {
        const v = (x) => x ?? 'N/A';
        const badge = (text, color) => `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600;background:${color}20;color:${color}">${text}</span>`;

        if (action === 'diagnostics_summary') {
            const s = data.data || data.summary || data;
            const overall = s.overall || 'unknown';
            const color = overall === 'ok' ? '#10b981' : overall === 'warning' ? '#f59e0b' : '#ef4444';
            let html = `<h4>Diagnostics Summary</h4><p>${badge(overall.toUpperCase(), color)}</p>`;
            if (s.components) {
                html += '<table class="data-table" style="margin-top:8px"><thead><tr><th>Component</th><th>Status</th></tr></thead><tbody>';
                for (const [comp, st] of Object.entries(s.components)) {
                    html += `<tr><td>${comp}</td><td><span class="badge ${this._badge(st)}">${st}</span></td></tr>`;
                }
                html += '</tbody></table>';
            }
            if (s.alerts?.length) {
                html += `<h5 style="margin-top:12px">Alerts (${s.alerts.length})</h5>`;
                s.alerts.forEach(a => { html += `<div style="padding:4px 0;font-size:0.82rem">${badge(a.severity || 'info', a.severity === 'critical' ? '#ef4444' : '#f59e0b')} ${a.message}</div>`; });
            }
            if (s.recommendations?.length) {
                html += `<h5 style="margin-top:12px">Recommendations</h5><ul style="font-size:0.82rem;padding-left:18px">`;
                s.recommendations.forEach(r => { html += `<li>${typeof r === 'string' ? r : r.message || JSON.stringify(r)}</li>`; });
                html += '</ul>';
            }
            return html;
        }

        if (action === 'health_score') {
            const hs = data.health_score || data.health_data || data;
            let html = '<h4>Health Score Breakdown</h4>';
            if (typeof hs === 'object') {
                html += '<table class="data-table"><thead><tr><th>Subsystem</th><th>Score</th><th>Status</th></tr></thead><tbody>';
                for (const [k, val] of Object.entries(hs)) {
                    if (typeof val === 'number') {
                        const color = val >= 80 ? '#10b981' : val >= 60 ? '#f59e0b' : '#ef4444';
                        html += `<tr><td>${k}</td><td><strong>${val.toFixed(1)}%</strong></td><td>${badge(val >= 80 ? 'OK' : val >= 60 ? 'WARN' : 'CRITICAL', color)}</td></tr>`;
                    }
                }
                html += '</tbody></table>';
            } else {
                html += `<p>Score: <strong>${v(hs)}</strong></p>`;
            }
            return html;
        }

        if (action === 'server_snapshot') {
            const snap = data.data || data;
            let html = '<h4>Server Snapshot</h4>';
            html += `<p style="font-size:0.82rem;color:var(--text-muted)">Captured at: ${snap.timestamp || new Date().toISOString()}</p>`;
            if (typeof snap === 'object') {
                html += `<details style="margin-top:8px"><summary style="cursor:pointer;font-size:0.85rem;font-weight:600">View Full Snapshot Data</summary><pre style="max-height:400px;overflow:auto;font-size:0.75rem;padding:10px;background:var(--bg-input);border-radius:6px;margin-top:6px">${JSON.stringify(snap, null, 2)}</pre></details>`;
            }
            return html;
        }

        if (action === 'server_timeline') {
            const tl = data.data || data.timeline || data;
            let html = '<h4>Snapshot Timeline</h4>';
            if (Array.isArray(tl) && tl.length) {
                html += `<p style="font-size:0.82rem">${tl.length} snapshot(s) recorded</p>`;
                tl.slice(-10).reverse().forEach(s => {
                    html += `<div style="padding:6px 0;border-bottom:1px solid var(--border-color);font-size:0.82rem">${s.timestamp || 'Unknown time'} — ${s.overall || s.status || 'captured'}</div>`;
                });
            } else {
                html += '<p>No snapshots recorded yet. Take a snapshot first.</p>';
            }
            return html;
        }

        if (action === 'predictive_analysis') {
            const pa = data.predictive_report || data;
            let html = '<h4>Predictive Analysis Report</h4>';
            if (pa.summary) {
                html += `<p>Predictions: ${pa.summary.total_predictions || 0} | High Risk: ${pa.summary.high_risk_count || 0}</p>`;
            }
            if (pa.predictions?.length) {
                pa.predictions.forEach(p => {
                    const color = p.risk_level === 'critical' ? '#ef4444' : p.risk_level === 'high' ? '#f59e0b' : '#3b82f6';
                    html += `<div style="padding:8px;margin:6px 0;background:var(--bg-input);border-radius:6px;border-left:3px solid ${color}">${badge(p.risk_level?.toUpperCase() || 'INFO', color)} <strong>${p.component || 'System'}</strong><br><span style="font-size:0.82rem">${p.recommendation || p.message || 'No details'}</span></div>`;
                });
            }
            return html;
        }

        if (action === 'connectivity_test') {
            const ct = data.connectivity_results || data;
            let html = '<h4>Connectivity Test</h4>';
            if (typeof ct === 'object') {
                for (const [k, val] of Object.entries(ct)) {
                    if (typeof val === 'boolean') {
                        html += `<div style="padding:4px 0">${val ? '✅' : '❌'} ${k}</div>`;
                    } else if (typeof val === 'object') {
                        html += `<div style="padding:4px 0"><strong>${k}:</strong> ${JSON.stringify(val)}</div>`;
                    }
                }
            }
            return html;
        }

        if (action === 'post_codes') {
            const codes = data.post_codes || data;
            let html = '<h4>POST Code History</h4>';
            if (Array.isArray(codes) && codes.length) {
                html += '<table class="data-table"><thead><tr><th>Code</th><th>Description</th><th>Time</th></tr></thead><tbody>';
                codes.forEach(c => {
                    html += `<tr><td><code>${c.code || c.MessageId || '?'}</code></td><td>${c.message || c.Message || ''}</td><td>${c.timestamp || c.Created || ''}</td></tr>`;
                });
                html += '</tbody></table>';
            } else {
                html += '<p>No POST codes recorded or server booted normally.</p>';
            }
            return html;
        }

        if (action === 'firmware_compliance') {
            const fw = data.firmware_inventory || data.firmware || data;
            let html = '<h4>Firmware Compliance Report</h4>';
            if (Array.isArray(fw) && fw.length) {
                html += `<p>${fw.length} firmware components found</p>`;
                html += '<table class="data-table"><thead><tr><th>Component</th><th>Version</th></tr></thead><tbody>';
                fw.forEach(f => { html += `<tr><td>${f.name || f.Name || '?'}</td><td>${f.version || f.Version || '?'}</td></tr>`; });
                html += '</tbody></table>';
            }
            return html;
        }

        // Default: show raw JSON
        return `<h4>${action}</h4><pre style="max-height:400px;overflow:auto;font-size:0.75rem;padding:10px;background:var(--bg-input);border-radius:6px">${JSON.stringify(data, null, 2)}</pre>`;
    }

    // ─── Logs Tab ───────────────────────────────────────────────
    displayLogs(logs) {
        this.rawLogs = [...logs].slice(0, this.maxLogs);
        this.renderFilteredLogs();
    }

    renderFilteredLogs() {
        const container = document.getElementById('logsContainer');
        if (!container) return;
        const sevFilter = document.getElementById('logSeverityFilter')?.value || 'all';
        const searchVal = (document.getElementById('logSearchInput')?.value || '').toLowerCase();
        let filtered = this.rawLogs;
        if (sevFilter !== 'all') filtered = filtered.filter(l => l.severity === sevFilter);
        if (searchVal) filtered = filtered.filter(l =>
            (l.message || '').toLowerCase().includes(searchVal) ||
            (l.source || '').toLowerCase().includes(searchVal) ||
            (l.component || '').toLowerCase().includes(searchVal)
        );
        // Stats bar
        const stats = document.getElementById('logStatsBar');
        if (stats) {
            const total = this.rawLogs.length;
            const crits = this.rawLogs.filter(l => l.severity === 'critical').length;
            const errs = this.rawLogs.filter(l => l.severity === 'error').length;
            const warns = this.rawLogs.filter(l => l.severity === 'warning').length;
            const infos = this.rawLogs.filter(l => l.severity === 'info').length;
            stats.innerHTML = `
                <span class="stat-item"><span class="stat-dot" style="background:var(--dell-dark-gray)"></span> Total: ${total}</span>
                <span class="stat-item"><span class="stat-dot" style="background:var(--danger-red)"></span> Critical: ${crits}</span>
                <span class="stat-item"><span class="stat-dot" style="background:#e67e22"></span> Error: ${errs}</span>
                <span class="stat-item"><span class="stat-dot" style="background:var(--warning-yellow)"></span> Warning: ${warns}</span>
                <span class="stat-item"><span class="stat-dot" style="background:var(--info-blue)"></span> Info: ${infos}</span>
                <span class="stat-item">| Showing: ${filtered.length}</span>`;
        }
        if (!filtered.length) { container.innerHTML = '<p class="placeholder-text">No logs match the current filter.</p>'; return; }
        container.innerHTML = filtered.map(log => `
            <div class="log-entry log-${log.severity}">
                <span class="timestamp">${new Date(log.timestamp).toLocaleString()}</span>
                <span class="severity">[${(log.severity || '').toUpperCase()}]</span>
                <span class="message">${this._v(log.message, '')}</span>
                ${log.source ? `<span class="source">(${log.source})</span>` : ''}
                ${log.component ? `<span class="source">[${log.component}]</span>` : ''}
                ${log.event_id ? `<span class="source">ID:${log.event_id}</span>` : ''}
            </div>
        `).join('');
        container.scrollTop = 0;
    }

    // ─── Theme Management ───────────────────────────────────────────
    initTheme() {
        const savedTheme = localStorage.getItem('medi-ai-tor-theme') || 'dark';
        this.setTheme(savedTheme);
        
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
        }
    }
    
    setTheme(theme) {
        const body = document.body;
        const themeIcon = document.querySelector('.theme-icon');
        const themeText = document.querySelector('.theme-text');
        
        body.setAttribute('data-theme', theme);
        
        if (theme === 'light') {
            if (themeIcon) themeIcon.textContent = '☀️';
            if (themeText) themeText.textContent = 'Light';
        } else {
            if (themeIcon) themeIcon.textContent = '🌙';
            if (themeText) themeText.textContent = 'Dark';
        }
        
        localStorage.setItem('medi-ai-tor-theme', theme);
        
        // Apply theme-specific CSS variables
        this.applyThemeVariables(theme);
    }
    
    toggleTheme() {
        const currentTheme = document.body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    }
    
    applyThemeVariables(theme) {
        const root = document.documentElement;
        const themeStyles = document.getElementById('theme-styles');
        
        if (theme === 'light') {
            // Override CSS variables to match the names used in style.css
            themeStyles.innerHTML = `
                :root {
                    --bg-body: #f1f5f9;
                    --bg-sidebar: #1e293b;
                    --bg-card: #ffffff;
                    --bg-card-hover: #f8fafc;
                    --bg-input: #ffffff;
                    --border-color: #cbd5e1;
                    --text-primary: #0f172a;
                    --text-secondary: #475569;
                    --text-muted: #64748b;
                    --text-secondary-fix: #475569;
                    --text-muted-fix: #64748b;
                    --accent: #4f46e5;
                    --accent-hover: #4338ca;
                }
                .tech-body { background: var(--bg-body); color: var(--text-primary); }
                .sidebar { background: var(--bg-sidebar); }
                .sidebar-link { color: #cbd5e1; }
                .sidebar-link:hover { color: #f1f5f9; }
                .sidebar-link.active { color: #f1f5f9; }
                .sidebar-section-label { color: #94a3b8; }
                .sidebar-version { color: #94a3b8; }
                .topbar { background: #ffffff; border-bottom-color: var(--border-color); }
                .topbar-toggle { color: var(--text-primary); }
                .connect-banner { background: var(--bg-card); border-color: var(--border-color); }
                .connect-panel { background: var(--bg-card); border-color: var(--border-color); }
                .form-input { background: var(--bg-input); border-color: var(--border-color); color: var(--text-primary); }
                .form-input::placeholder { color: var(--text-muted); }
                .card, .section-card, .component-card, .metric-card { 
                    background: var(--bg-card); border-color: var(--border-color); color: var(--text-primary); 
                }
                .sub-tab { color: var(--text-secondary); }
                .sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
                .data-table thead th { background: #f8fafc; color: var(--text-secondary); border-color: var(--border-color); }
                .data-table tbody td { border-color: var(--border-color); color: var(--text-primary); }
                .log-container { background: var(--bg-card); border-color: var(--border-color); }
                .chip { background: #eef2ff; border-color: #c7d2fe; color: #4338ca; }
                .recommendation-card { background: linear-gradient(135deg, #f8fafc, #ffffff); border-color: var(--border-color); }
                .badge-ok { background: #dcfce7; color: #166534; }
                .badge-warn { background: #fef9c3; color: #854d0e; }
                .badge-crit { background: #fee2e2; color: #991b1b; }
                .badge-info { background: #dbeafe; color: #1e40af; }
                .alert { border-color: var(--border-color); }
                .section-block { background: #f8fafc; }
                .section-block h4 { color: var(--accent); }
            `;
        } else {
            // Dark mode — restore defaults (style.css :root is already dark)
            themeStyles.innerHTML = '';
        }
    }

    // ─── Unchanged infrastructure methods ───────────────────────
    updateConnectionStatus(connected) {
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');
        const idracDot = document.getElementById('idracStatusDot');
        
        if (connected) {
            if (connectBtn) { connectBtn.disabled = true; connectBtn.textContent = 'Connected'; }
            if (disconnectBtn) disconnectBtn.disabled = false;
            if (idracDot) { idracDot.classList.add('connected'); idracDot.classList.remove('error'); }
        } else {
            if (connectBtn) { connectBtn.disabled = false; connectBtn.textContent = 'Connect iDRAC'; }
            if (disconnectBtn) disconnectBtn.disabled = true;
            if (idracDot) { idracDot.classList.remove('connected', 'error'); }
        }
    }
    
    // ─── P1: Structured alert system ─────────────────────────────
    showAlert(message, type, options = {}) {
        const alertContainer = document.getElementById('alertContainer');
        if (!alertContainer) return;
        const icons = { success: '✓', warning: '⚠', danger: '✕', error: '✕', info: 'ℹ' };
        const icon = icons[type] || icons.info;
        const duration = type === 'danger' || type === 'error' ? 8000 : 5000;
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        let html = `<span class="alert-icon">${icon}</span><div class="alert-body">`;
        if (options.title) html += `<div class="alert-title">${options.title}</div>`;
        html += `<span>${this._escapeHtml(message)}</span>`;
        if (options.retry) html += ` <button class="btn btn-sm btn-outline" style="margin-left:8px;font-size:0.75rem" data-retry>Retry</button>`;
        html += `</div><button class="alert-dismiss" aria-label="Dismiss">×</button>`;
        alert.innerHTML = html;
        alert.querySelector('.alert-dismiss').addEventListener('click', () => alert.remove());
        if (options.retry) alert.querySelector('[data-retry]').addEventListener('click', () => { alert.remove(); options.retry(); });
        alertContainer.appendChild(alert);
        // Limit visible alerts to 5
        while (alertContainer.children.length > 5) alertContainer.removeChild(alertContainer.firstChild);
        setTimeout(() => { if (alert.parentNode) alert.remove(); }, duration);
    }

    showToast(message, type = 'info') {
        this.showAlert(message, type);
    }

    // Sanitize user-facing error messages — never show raw stack traces
    _friendlyError(error) {
        const msg = typeof error === 'string' ? error : (error?.message || 'An unexpected error occurred');
        // Strip internal details
        if (/traceback|file ["/\\]|modulenot|errno|ECONNREFUSED/i.test(msg)) return 'A server error occurred. Please try again.';
        if (msg.length > 200) return msg.slice(0, 197) + '...';
        return msg;
    }

    _escapeHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    // Unified precondition check — replaces 8 different "connect first" messages
    _requireConnection(action) {
        if (!this.currentServer) {
            this.showAlert('Connect to a server before ' + (action || 'using this feature') + '.', 'warning', { title: 'Not connected' });
            return false;
        }
        return true;
    }
    
    log(message, type = 'info') {
        const logContainer = document.getElementById('outputLog');
        if (!logContainer) return;
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry log-${type}`;
        logEntry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
        while (logContainer.children.length > 100) { logContainer.removeChild(logContainer.firstChild); }
    }
    
    showLoading(show, context) {
        document.querySelectorAll('.loading-indicator').forEach(el => {
            el.style.display = show ? 'flex' : 'none';
            const p = el.querySelector('p');
            if (p) p.textContent = show && context ? context : 'Processing...';
        });
    }
    
    saveSettings() {
        localStorage.setItem('dellAgentSettings', JSON.stringify({
            currentServer: {
                host: this.currentServer?.host || '',
                username: this.currentServer?.username || '',
                port: this.currentServer?.port || 443,
                // password intentionally NOT saved to localStorage
            },
            actionLevel: this.actionLevel
        }));
    }
    
    loadSavedSettings() {
        try {
            const settings = JSON.parse(localStorage.getItem('dellAgentSettings') || '{}');
            if (settings.actionLevel) {
                this.actionLevel = settings.actionLevel;
                const btn = document.querySelector(`[data-action-level="${this.actionLevel}"]`);
                if (btn) this.selectActionLevel(btn);
            }
            if (settings.currentServer) {
                document.getElementById('serverHost').value = settings.currentServer.host || '';
                document.getElementById('username').value = settings.currentServer.username || '';
                // password intentionally NOT restored from localStorage
                document.getElementById('port').value = settings.currentServer.port || 443;
            }
            
            // No auto-reconnect — user must enter password each session
        } catch (error) { this.log('Failed to load saved settings', 'error'); }
        this.loadSrNumber();
        // Auto-populate SR# from URL parameter (e.g., /technician?sr=SR123456)
        const urlSr = new URLSearchParams(window.location.search).get('sr') || new URLSearchParams(window.location.search).get('SR');
        if (urlSr) { const srEl = document.getElementById('srNumber'); if (srEl) srEl.value = urlSr; }
    }
    
    updateUI() { this.updateConnectionStatus(false); }
    
    checkFleetServerConnection() {
        // Check if we're coming from fleet management with server info
        const fleetServerConnection = sessionStorage.getItem('fleetServerConnection');
        const urlParams = new URLSearchParams(window.location.search);
        const serverId = urlParams.get('server');
        const serverName = urlParams.get('name');
        
        if (fleetServerConnection) {
            try {
                this.fleetServerInfo = JSON.parse(fleetServerConnection);
                this.fromFleet = true;
                
                // Update UI to show fleet connection
                this.updateFleetConnectionUI();
                
                // Auto-connect to the server
                this.connectToFleetServer();
                
            } catch (error) {
                this.log('Error parsing fleet server info', 'error');
                sessionStorage.removeItem('fleetServerConnection');
            }
        } else if (serverId && serverName) {
            // Handle URL parameters as fallback
            this.fleetServerInfo = {
                serverId: serverId,
                name: serverName,
                fromFleet: true
            };
            this.fromFleet = true;
            this.updateFleetConnectionUI();
        }
    }
    
    updateFleetConnectionUI() {
        if (!this.fleetServerInfo) return;
        
        // Update header to show fleet connection
        const headerTitle = document.querySelector('.dashboard-title');
        if (headerTitle) {
            headerTitle.innerHTML = `🖥️ ${this.fleetServerInfo.name} <span class="fleet-badge">From Fleet</span>`;
        }
        
        // Add fleet-specific styles
        if (!document.getElementById('fleetStyles')) {
            const style = document.createElement('style');
            style.id = 'fleetStyles';
            style.textContent = `
                .fleet-badge {
                    background: #3498db;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 0.75rem;
                    margin-left: 8px;
                }
                .fleet-connection-info {
                    background: #f8f9fa;
                    padding: 1rem;
                    border-radius: 8px;
                    border-left: 4px solid #3498db;
                    margin-bottom: 1rem;
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    async connectToFleetServer() {
        if (!this.fleetServerInfo) return;
        
        // Pre-fill the connection form with fleet server details
        const hostEl = document.getElementById('serverHost');
        const userEl = document.getElementById('username');
        const portEl = document.getElementById('port');
        if (hostEl) hostEl.value = this.fleetServerInfo.host || '';
        if (userEl) userEl.value = this.fleetServerInfo.username || '';
        if (portEl) portEl.value = this.fleetServerInfo.port || 443;
        
        // Focus the password field so user can complete the connection
        const passEl = document.getElementById('password');
        if (passEl) {
            passEl.focus();
            this.showAlert('Enter the password to connect to this server.', 'info', { title: `Connecting to ${this.fleetServerInfo.name}` });
        }
        
        // Clean up the sessionStorage handoff
        sessionStorage.removeItem('fleetServerConnection');
    }
}

// Initialize the application
const app = new DellAIAgent();
window.DellAIAgent = DellAIAgent;
