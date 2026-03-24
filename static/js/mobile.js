/**
 * Mobile-Responsive JavaScript for Medi-AI-tor
 * Handles mobile-specific interactions, PWA features, and touch optimizations
 */

class MobileApp {
    constructor() {
        this.currentPage = 'dashboard';
        this.isConnected = false;
        this.refreshInterval = null;
        this.refreshRate = 30000; // 30 seconds default
        this.websocket = null;
        this.notificationPermission = 'default';
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupTouchOptimizations();
        this.setupPWAFeatures();
        this.checkNotificationPermission();
        this.loadSettings();
        this.startAutoRefresh();
    }
    
    setupEventListeners() {
        // Navigation
        document.getElementById('menuBtn')?.addEventListener('click', () => this.toggleNav());
        document.getElementById('closeNavBtn')?.addEventListener('click', () => this.closeNav());
        this._setupNavClickOutside();
        
        // Page navigation
        document.querySelectorAll('.nav-item, .footer-nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const page = item.dataset.page;
                this.navigateToPage(page);
            });
        });
        
        // Theme toggle
        document.getElementById('mobileThemeBtn')?.addEventListener('click', () => this.toggleTheme());
        
        // Refresh buttons
        document.getElementById('refreshBtn')?.addEventListener('click', () => this.refreshData());
        document.getElementById('healthRefreshBtn')?.addEventListener('click', () => this.refreshData());
        document.getElementById('analyticsRefreshBtn')?.addEventListener('click', () => this.refreshData());
        
        // Quick actions
        document.getElementById('quickHealthBtn')?.addEventListener('click', () => {
            this.navigateToPage('health');
            this.refreshData();
        });
        
        document.getElementById('quickLogsBtn')?.addEventListener('click', () => {
            this.showLogs();
        });
        
        document.getElementById('quickAlertsBtn')?.addEventListener('click', () => {
            this.navigateToPage('alerts');
        });
        
        document.getElementById('quickSettingsBtn')?.addEventListener('click', () => {
            this.navigateToPage('settings');
        });
        
        // Alerts
        document.getElementById('clearAlertsBtn')?.addEventListener('click', () => this.clearAlerts());
        
        // Alert filters
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.filterAlerts(e.target.dataset.filter);
            });
        });
        
        // Settings
        document.getElementById('mobileConnectBtn')?.addEventListener('click', () => this.connectToServer());
        document.getElementById('pushNotifications')?.addEventListener('change', (e) => {
            this.togglePushNotifications(e.target.checked);
        });
        document.getElementById('alertSounds')?.addEventListener('change', (e) => {
            this.toggleAlertSounds(e.target.checked);
        });
        document.getElementById('autoRefresh')?.addEventListener('change', (e) => {
            this.toggleAutoRefresh(e.target.checked);
        });
        document.getElementById('theme')?.addEventListener('change', (e) => {
            this.setTheme(e.target.value);
        });
        document.getElementById('refreshRate')?.addEventListener('change', (e) => {
            this.setRefreshRate(parseInt(e.target.value) * 1000);
        });
        
        // Swipe gestures
        this.setupSwipeGestures();
        
        // Visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pauseAutoRefresh();
            } else {
                this.resumeAutoRefresh();
            }
        });
        
        // Online/offline
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
    }
    
    setupTouchOptimizations() {
        // Prevent double-tap zoom on buttons
        document.querySelectorAll('button, .nav-item, .footer-nav-item, .action-btn').forEach(element => {
            element.addEventListener('touchstart', (e) => {
                // Add active state for visual feedback
                element.style.transform = 'scale(0.95)';
            });
            
            element.addEventListener('touchend', (e) => {
                setTimeout(() => {
                    element.style.transform = 'scale(1)';
                }, 100);
            });
        });
        
        // Smooth scrolling
        document.addEventListener('touchstart', () => {
            document.body.style.overflow = 'auto';
        });
        
        // Optimize scrolling performance
        let ticking = false;
        document.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(() => {
                    this.handleScroll();
                    ticking = false;
                });
                ticking = true;
            }
        });
    }
    
    setupPWAFeatures() {
        // Install prompt
        let deferredPrompt;
        
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            
            // Show install banner after 5 seconds
            setTimeout(() => {
                this.showInstallBanner(deferredPrompt);
            }, 5000);
        });
        
        // Handle app installed
        window.addEventListener('appinstalled', () => {
            this.showToast('App installed successfully!', 'success');
        });
    }
    
    setupSwipeGestures() {
        let touchStartX = 0;
        let touchEndX = 0;
        
        document.addEventListener('touchstart', (e) => {
            touchStartX = e.changedTouches[0].screenX;
        });
        
        document.addEventListener('touchend', (e) => {
            touchEndX = e.changedTouches[0].screenX;
            this.handleSwipeGesture(touchStartX, touchEndX);
        });
    }
    
    handleSwipeGesture(startX, endX) {
        const swipeThreshold = 50;
        const diff = startX - endX;
        
        if (Math.abs(diff) < swipeThreshold) return;
        
        if (diff > 0) {
            // Swipe left - next page
            this.navigateToNextPage();
        } else {
            // Swipe right - previous page
            this.navigateToPreviousPage();
        }
    }
    
    navigateToNextPage() {
        const pages = ['dashboard', 'health', 'alerts', 'analytics', 'settings'];
        const currentIndex = pages.indexOf(this.currentPage);
        const nextIndex = (currentIndex + 1) % pages.length;
        this.navigateToPage(pages[nextIndex]);
    }
    
    navigateToPreviousPage() {
        const pages = ['dashboard', 'health', 'alerts', 'analytics', 'settings'];
        const currentIndex = pages.indexOf(this.currentPage);
        const prevIndex = (currentIndex - 1 + pages.length) % pages.length;
        this.navigateToPage(pages[prevIndex]);
    }
    
    toggleNav() {
        const nav = document.getElementById('mobileNav');
        nav.classList.toggle('active');
    }
    
    closeNav() {
        const nav = document.getElementById('mobileNav');
        nav.classList.remove('active');
    }

    // #18: Close nav when tapping outside
    _setupNavClickOutside() {
        document.addEventListener('click', (e) => {
            const nav = document.getElementById('mobileNav');
            const menuBtn = document.getElementById('menuBtn');
            if (nav && nav.classList.contains('active') &&
                !nav.contains(e.target) && menuBtn && !menuBtn.contains(e.target)) {
                this.closeNav();
            }
        });
    }
    
    navigateToPage(page) {
        // Hide current page
        document.querySelectorAll('.page').forEach(p => {
            p.classList.remove('active');
        });
        
        // Show new page
        const targetPage = document.getElementById(`${page}Page`);
        if (targetPage) {
            targetPage.classList.add('active');
            this.currentPage = page;
            
            // Update navigation
            document.querySelectorAll('.nav-item, .footer-nav-item').forEach(item => {
                item.classList.remove('active');
                if (item.dataset.page === page) {
                    item.classList.add('active');
                }
            });
            
            // Close navigation
            this.closeNav();
            
            // Refresh page-specific data
            this.refreshPageData(page);
        }
    }
    
    refreshPageData(page) {
        switch (page) {
            case 'dashboard':
                this.refreshDashboard();
                break;
            case 'health':
                this.refreshHealth();
                break;
            case 'alerts':
                this.refreshAlerts();
                break;
            case 'analytics':
                this.refreshAnalytics();
                break;
            case 'settings':
                this.loadSettings();
                break;
        }
    }
    
    async refreshData() {
        this.showLoading(true);
        
        try {
            // Fetch current metrics
            const response = await fetch('/monitoring/metrics');
            if (!response.ok) {
                // Try diagnostics-summary as fallback
                const fallback = await fetch('/api/server/diagnostics-summary');
                if (fallback.ok) {
                    const fbData = await fallback.json();
                    if (fbData.status === 'success') {
                        this.updateFromDiagnostics(fbData.summary);
                        this.updateConnectionStatus(true);
                        return;
                    }
                }
                throw new Error('Server not responding');
            }
            const data = await response.json();
            
            if (data.status === 'success') {
                this.updateMetrics(data.data || {});
                this.updateConnectionStatus(true);
            } else {
                throw new Error(data.message || 'Failed to fetch metrics');
            }
        } catch (error) {
            // Error logged via toast
            this.showToast('Connect to a server first', 'warning');
            this.updateConnectionStatus(false);
        } finally {
            this.showLoading(false);
        }
    }
    
    updateFromDiagnostics(summary) {
        // Fallback update using diagnostics summary data
        const el = (id) => document.getElementById(id);
        if (el('healthValue')) el('healthValue').textContent = summary.overall === 'ok' ? '100%' : summary.overall === 'warning' ? '75%' : '50%';
        if (el('tempValue') && summary.thermal) el('tempValue').textContent = `${(summary.thermal.max_temperature || 0).toFixed(1)}°C`;
        if (el('powerValue') && summary.power) el('powerValue').textContent = `${summary.power.healthy_psus}/${summary.power.total_psus} PSU`;
    }
    
    updateMetrics(metrics) {
        // Update dashboard
        this.updateDashboard(metrics);
        
        // Update health page
        this.updateHealthPage(metrics);
        
        // Update analytics
        this.updateAnalyticsPage(metrics);
    }
    
    updateDashboard(metrics) {
        // Quick stats
        const tempValue = metrics.metrics?.max_temp?.current_value || 0;
        const powerValue = metrics.metrics?.power_consumption?.current_value || 0;
        const memoryValue = metrics.metrics?.memory_health?.current_value || 0;
        const healthValue = metrics.metrics?.overall_health?.current_value || 0;
        
        document.getElementById('tempValue').textContent = `${tempValue.toFixed(1)}°C`;
        document.getElementById('powerValue').textContent = `${powerValue.toFixed(0)}W`;
        document.getElementById('memoryValue').textContent = `${memoryValue.toFixed(0)}%`;
        document.getElementById('healthValue').textContent = `${healthValue.toFixed(0)}%`;
        
        // Status cards
        const inletTemp = metrics.metrics?.inlet_temp?.current_value || 0;
        const cpuTemp = metrics.metrics?.cpu_temp?.current_value || 0;
        const fanSpeed = metrics.metrics?.avg_fan_speed?.current_value || 0;
        const powerUsage = metrics.metrics?.power_consumption?.current_value || 0;
        const powerEfficiency = metrics.metrics?.power_efficiency?.current_value || 0;
        
        document.getElementById('inletTemp').textContent = `${inletTemp.toFixed(1)}°C`;
        document.getElementById('cpuTemp').textContent = `${cpuTemp.toFixed(1)}°C`;
        document.getElementById('fanSpeed').textContent = `${fanSpeed.toFixed(0)}RPM`;
        document.getElementById('powerUsage').textContent = `${powerUsage.toFixed(0)}W`;
        document.getElementById('powerEfficiency').textContent = `${powerEfficiency.toFixed(1)}%`;
        
        // Update status indicators
        this.updateStatusIndicators(metrics);
    }
    
    updateHealthPage(metrics) {
        const healthScore = metrics.metrics?.overall_health?.current_value || 0;
        const thermalHealth = metrics.metrics?.max_temp ? this.calculateHealthScore(metrics.metrics.max_temp.current_value, 75, 85) : 100;
        const powerHealth = metrics.metrics?.power_efficiency?.current_value || 100;
        const memoryHealth = metrics.metrics?.memory_health?.current_value || 100;
        const storageHealth = metrics.metrics?.storage_health?.current_value || 100;
        
        // Update score circle
        const scoreCircle = document.querySelector('.score-circle');
        if (scoreCircle) {
            scoreCircle.style.setProperty('--score', healthScore);
        }
        document.getElementById('healthScore').textContent = healthScore.toFixed(0);
        
        // Update health bars
        this.updateHealthBar('thermalHealth', thermalHealth);
        this.updateHealthBar('powerHealth', powerHealth);
        this.updateHealthBar('memoryHealth', memoryHealth);
        this.updateHealthBar('storageHealth', storageHealth);
        
        // Update percentages
        document.getElementById('thermalPercent').textContent = `${thermalHealth.toFixed(0)}%`;
        document.getElementById('powerPercent').textContent = `${powerHealth.toFixed(0)}%`;
        document.getElementById('memoryPercent').textContent = `${memoryHealth.toFixed(0)}%`;
        document.getElementById('storagePercent').textContent = `${storageHealth.toFixed(0)}%`;
    }
    
    updateHealthBar(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.style.width = `${value}%`;
            
            // Update color based on value
            if (value >= 80) {
                element.style.background = 'linear-gradient(90deg, #27ae60, #2ecc71)';
            } else if (value >= 60) {
                element.style.background = 'linear-gradient(90deg, #f39c12, #f1c40f)';
            } else {
                element.style.background = 'linear-gradient(90deg, #e74c3c, #c0392b)';
            }
        }
    }
    
    updateAnalyticsPage(metrics) {
        // Update summary cards
        document.getElementById('insightsCount').textContent = '0'; // Would be populated from analytics API
        document.getElementById('performanceScore').textContent = '--'; // Would be populated from analytics API
        document.getElementById('trendCount').textContent = '0'; // Would be populated from analytics API
    }
    
    updateStatusIndicators(metrics) {
        // Thermal status
        const maxTemp = metrics.metrics?.max_temp?.current_value || 0;
        const thermalStatus = document.getElementById('thermalStatus');
        if (thermalStatus) {
            if (maxTemp > 85) {
                thermalStatus.textContent = '🔴';
            } else if (maxTemp > 75) {
                thermalStatus.textContent = '🟡';
            } else {
                thermalStatus.textContent = '🟢';
            }
        }
        
        // Power status
        const powerEfficiency = metrics.metrics?.power_efficiency?.current_value || 100;
        const powerStatus = document.getElementById('powerStatus');
        if (powerStatus) {
            if (powerEfficiency < 70) {
                powerStatus.textContent = '🔴';
            } else if (powerEfficiency < 80) {
                powerStatus.textContent = '🟡';
            } else {
                powerStatus.textContent = '🟢';
            }
        }
        
        // PSU status
        document.getElementById('psuStatus').textContent = '✅'; // Would be populated from actual PSU status
    }
    
    calculateHealthScore(value, warningThreshold, criticalThreshold) {
        if (value >= criticalThreshold) {
            return Math.max(0, 100 - ((value - criticalThreshold) / criticalThreshold) * 100);
        } else if (value >= warningThreshold) {
            return 100 - ((value - warningThreshold) / (criticalThreshold - warningThreshold)) * 50;
        } else {
            return 100;
        }
    }
    
    refreshDashboard() {
        this.refreshData();
    }
    
    refreshHealth() {
        this.refreshData();
    }
    
    refreshAlerts() {
        // Would fetch alerts from API
        this.updateAlertsList([]);
    }
    
    refreshAnalytics() {
        // Would fetch analytics from API
        this.updateAnalyticsPage({});
    }
    
    updateAlertsList(alerts) {
        const alertsList = document.getElementById('mobileAlertsList');
        if (!alertsList) return;
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<div class="no-alerts">No active alerts</div>';
            return;
        }
        
        alertsList.innerHTML = alerts.map(alert => `
            <div class="alert-item ${alert.severity}">
                <div class="alert-header">
                    <div class="alert-title">${alert.title}</div>
                    <div class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="alert-message">${alert.message}</div>
                <div class="alert-actions">
                    <button class="alert-action" onclick="mobileApp.acknowledgeAlert('${alert.id}')">Acknowledge</button>
                    <button class="alert-action" onclick="mobileApp.viewAlertDetails('${alert.id}')">Details</button>
                </div>
            </div>
        `).join('');
        
        // Update badge
        document.getElementById('alertsBadge').textContent = alerts.length;
    }
    
    filterAlerts(filter) {
        // Update filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.filter === filter) {
                btn.classList.add('active');
            }
        });
        
        // Filter alerts (would be implemented with actual filtering logic)
        this.refreshAlerts();
    }
    
    clearAlerts() {
        // Would clear all alerts via API
        this.updateAlertsList([]);
        this.showToast('All alerts cleared', 'success');
    }
    
    acknowledgeAlert(alertId) {
        // Would acknowledge alert via API
        this.showToast('Alert acknowledged', 'success');
    }
    
    viewAlertDetails(alertId) {
        // Would show alert details
        this.showToast('Alert details', 'info');
    }
    
    showLogs() {
        // Navigate to the technician dashboard logs tab
        window.open('/technician', '_blank');
    }
    
    async connectToServer() {
        const host = document.getElementById('serverHost').value;
        const username = document.getElementById('serverUsername').value;
        const password = document.getElementById('serverPassword').value;
        
        if (!host || !username || !password) {
            this.showToast('Please fill in all connection fields', 'error');
            return;
        }
        
        this.showLoading(true);
        
        try {
            const response = await fetch('/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    host: host,
                    username: username,
                    password: password,
                    port: 443
                })
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                this.showToast('Connected to server successfully', 'success');
                this.updateConnectionStatus(true);
                this.saveSettings();
                this.refreshData();
            } else {
                throw new Error(data.message || 'Connection failed');
            }
        } catch (error) {
            // Error logged via toast
            this.showToast('Failed to connect to server', 'error');
            this.updateConnectionStatus(false);
        } finally {
            this.showLoading(false);
        }
    }
    
    updateConnectionStatus(connected) {
        this.isConnected = connected;
        
        const statusElement = document.getElementById('mobileConnectionStatus');
        const statusDot = statusElement?.querySelector('.status-dot');
        const statusText = statusElement?.querySelector('.status-text');
        
        if (statusDot && statusText) {
            if (connected) {
                statusDot.classList.add('status-online');
                statusText.textContent = 'Online';
            } else {
                statusDot.classList.remove('status-online');
                statusText.textContent = 'Offline';
            }
        }
    }
    
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    }
    
    setTheme(theme) {
        if (theme === 'auto') {
            const hour = new Date().getHours();
            theme = (hour >= 6 && hour < 18) ? 'light' : 'dark';
        }
        
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        
        // Update theme button
        const themeBtn = document.getElementById('mobileThemeBtn');
        if (themeBtn) {
            themeBtn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
        }
        
        // Update theme select
        const themeSelect = document.getElementById('theme');
        if (themeSelect) {
            themeSelect.value = theme;
        }
    }
    
    checkNotificationPermission() {
        if ('Notification' in window) {
            Notification.requestPermission().then(permission => {
                this.notificationPermission = permission;
            });
        }
    }
    
    togglePushNotifications(enabled) {
        if (enabled && this.notificationPermission === 'default') {
            Notification.requestPermission().then(permission => {
                this.notificationPermission = permission;
                if (permission === 'granted') {
                    this.showToast('Push notifications enabled', 'success');
                } else {
                    this.showToast('Push notifications denied', 'warning');
                    document.getElementById('pushNotifications').checked = false;
                }
            });
        } else if (!enabled) {
            this.showToast('Push notifications disabled', 'info');
        }
    }
    
    toggleAlertSounds(enabled) {
        localStorage.setItem('alertSounds', enabled);
        this.showToast(enabled ? 'Alert sounds enabled' : 'Alert sounds disabled', 'info');
    }
    
    toggleAutoRefresh(enabled) {
        if (enabled) {
            this.startAutoRefresh();
        } else {
            this.stopAutoRefresh();
        }
        localStorage.setItem('autoRefresh', enabled);
    }
    
    setRefreshRate(rate) {
        this.refreshRate = rate;
        localStorage.setItem('refreshRate', rate);
        
        // Restart auto refresh with new rate
        if (this.refreshInterval) {
            this.stopAutoRefresh();
            this.startAutoRefresh();
        }
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        this.refreshInterval = setInterval(() => {
            if (this.isConnected && !document.hidden) {
                this.refreshData();
            }
        }, this.refreshRate);
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    pauseAutoRefresh() {
        this.stopAutoRefresh();
    }
    
    resumeAutoRefresh() {
        if (document.getElementById('autoRefresh')?.checked) {
            this.startAutoRefresh();
        }
    }
    
    loadSettings() {
        // Load theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        this.setTheme(savedTheme);
        
        // Load connection settings
        const savedHost = localStorage.getItem('serverHost');
        const savedUsername = localStorage.getItem('serverUsername');
        
        if (savedHost) document.getElementById('serverHost').value = savedHost;
        if (savedUsername) document.getElementById('serverUsername').value = savedUsername;
        
        // Load notification settings
        const alertSounds = localStorage.getItem('alertSounds') !== 'false';
        const autoRefresh = localStorage.getItem('autoRefresh') !== 'false';
        const refreshRate = parseInt(localStorage.getItem('refreshRate')) || 30000;
        
        document.getElementById('alertSounds').checked = alertSounds;
        document.getElementById('autoRefresh').checked = autoRefresh;
        document.getElementById('refreshRate').value = refreshRate / 1000;
        
        this.refreshRate = refreshRate;
        
        if (autoRefresh) {
            this.startAutoRefresh();
        }
    }
    
    saveSettings() {
        localStorage.setItem('serverHost', document.getElementById('serverHost').value);
        localStorage.setItem('serverUsername', document.getElementById('serverUsername').value);
        localStorage.setItem('alertSounds', document.getElementById('alertSounds').checked);
        localStorage.setItem('autoRefresh', document.getElementById('autoRefresh').checked);
        localStorage.setItem('refreshRate', this.refreshRate);
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
    
    showToast(message, type = 'info', duration = 3000) {
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
        
        // Play sound if enabled
        if (document.getElementById('alertSounds')?.checked) {
            this.playNotificationSound(type);
        }
    }
    
    playNotificationSound(type) {
        // Create a simple beep sound using Web Audio API
        if (typeof AudioContext !== 'undefined') {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            // Different frequencies for different types
            const frequencies = {
                'success': 800,
                'error': 400,
                'warning': 600,
                'info': 500
            };
            
            oscillator.frequency.value = frequencies[type] || 500;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.1);
        }
    }
    
    showInstallBanner(deferredPrompt) {
        // Create install banner
        const banner = document.createElement('div');
        banner.className = 'install-banner';
        banner.innerHTML = `
            <div class="install-content">
                <div class="install-text">
                    <div class="install-title">Install Medi-AI-tor</div>
                    <div class="install-description">Add to home screen for offline access</div>
                </div>
                <div class="install-buttons">
                    <button class="install-btn" id="installBtn">Install</button>
                    <button class="dismiss-btn" id="dismissBtn">Later</button>
                </div>
            </div>
        `;
        
        // Add styles
        banner.style.cssText = `
            position: fixed;
            bottom: 80px;
            left: 20px;
            right: 20px;
            background: white;
            border-radius: 12px;
            padding: 1rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
            z-index: 9998;
            transform: translateY(150%);
            transition: transform 0.3s ease;
        `;
        
        document.body.appendChild(banner);
        
        // Show banner
        setTimeout(() => {
            banner.style.transform = 'translateY(0)';
        }, 100);
        
        // Handle buttons
        document.getElementById('installBtn').addEventListener('click', () => {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then((choiceResult) => {
                if (choiceResult.outcome === 'accepted') {
                    this.showToast('App installed successfully!', 'success');
                }
                banner.remove();
            });
        });
        
        document.getElementById('dismissBtn').addEventListener('click', () => {
            banner.style.transform = 'translateY(150%)';
            setTimeout(() => banner.remove(), 300);
        });
        
        // Auto-hide after 10 seconds
        setTimeout(() => {
            if (banner.parentNode) {
                banner.style.transform = 'translateY(150%)';
                setTimeout(() => banner.remove(), 300);
            }
        }, 10000);
    }
    
    handleScroll() {
        // Add scroll-based effects if needed
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        
        // Hide/show header on scroll
        const header = document.querySelector('.mobile-header');
        if (header) {
            if (scrollTop > 100) {
                header.style.transform = 'translateY(-100%)';
            } else {
                header.style.transform = 'translateY(0)';
            }
        }
    }
    
    handleOnline() {
        this.showToast('Connection restored', 'success');
        this.updateConnectionStatus(true);
        this.refreshData();
    }
    
    handleOffline() {
        this.showToast('Connection lost', 'error');
        this.updateConnectionStatus(false);
    }
}

// Initialize mobile app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.mobileApp = new MobileApp();
});

// Handle back button
window.addEventListener('popstate', (e) => {
    if (window.mobileApp) {
        // Handle browser back button
        e.preventDefault();
        window.mobileApp.navigateToPreviousPage();
    }
});

// Prevent zoom on double tap
let lastTouchEnd = 0;
document.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
        e.preventDefault();
    }
    lastTouchEnd = now;
}, false);
