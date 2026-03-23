// ═══════════════════════════════════════════════════════════
// CUSTOMER CHAT — Medi-AI-tor Conversational AI Agent
// ═══════════════════════════════════════════════════════════

class CustomerChat {
    constructor() {
        this.apiBase = '';
        this.connected = false;
        this.serverInfo = null;
        this.actionLevel = 'read_only';
        this._userAtBottom = true;
        this.init();
    }

    init() {
        // Connect form
        document.getElementById('connectForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.connect();
        });
        document.getElementById('disconnectBtn')?.addEventListener('click', () => this.disconnect());

        // Chat form
        document.getElementById('chatForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.send();
        });

        // Auto-resize textarea
        const input = document.getElementById('chatInput');
        if (input) {
            input.addEventListener('input', () => {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 120) + 'px';
            });
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.send();
                }
            });
        }

        // Suggestion chips
        document.querySelectorAll('.suggest-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const input = document.getElementById('chatInput');
                if (!input) return;
                if (!this.connected) {
                    this.showToast('Connect to a server first', 'warning');
                    return;
                }
                input.value = chip.dataset.msg;
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 120) + 'px';
                this.send();
            });
        });

        // Mobile sidebar toggle
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const sidebar = document.getElementById('chatSidebar');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', () => {
                sidebar?.classList.toggle('open');
                sidebarOverlay?.classList.toggle('active');
            });
        }
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', () => {
                sidebar?.classList.remove('open');
                sidebarOverlay.classList.remove('active');
            });
        }

        // Scroll-to-bottom FAB
        const chatMessages = document.getElementById('chatMessages');
        const scrollBtn = document.getElementById('scrollBottomBtn');
        if (chatMessages && scrollBtn) {
            chatMessages.addEventListener('scroll', () => {
                const gap = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight;
                this._userAtBottom = gap < 80;
                scrollBtn.style.display = this._userAtBottom ? 'none' : 'flex';
            });
            scrollBtn.addEventListener('click', () => {
                chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
            });
        }

        // Load saved connection
        this.loadSaved();
        this.setInputEnabled(false);
    }

    // ─── Input State Management ─────────────────────────────
    setInputEnabled(enabled) {
        const input = document.getElementById('chatInput');
        const send = document.getElementById('chatSend');
        const hint = document.getElementById('inputHint');
        if (input) {
            input.disabled = !enabled;
            input.placeholder = enabled
                ? 'Describe your server issue or ask a question...'
                : 'Connect to a server to start chatting';
        }
        if (send) send.disabled = !enabled;
        if (hint) hint.textContent = enabled
            ? 'Press Enter to send · Shift+Enter for new line'
            : 'Connect to a server to start chatting';
    }

    // ─── Toast Notifications ────────────────────────────────
    showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `<span>${message}</span><button class="toast-close" aria-label="Dismiss">&times;</button>`;
        container.appendChild(toast);
        toast.querySelector('.toast-close')?.addEventListener('click', () => {
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        });
        setTimeout(() => {
            if (toast.parentNode) {
                toast.classList.add('removing');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    }

    // ─── Smart Scroll ───────────────────────────────────────
    scrollToBottom(force = false) {
        const container = document.getElementById('chatMessages');
        if (!container) return;
        if (force || this._userAtBottom) {
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
        }
    }

    // ─── Connection ───────────────────────────────────────
    async connect() {
        const host = document.getElementById('cHost').value.trim();
        const user = document.getElementById('cUser').value.trim();
        const pass = document.getElementById('cPass').value.trim();
        const port = parseInt(document.getElementById('cPort').value) || 443;

        if (!host || !user || !pass) {
            this.showToast('Please fill in all connection fields', 'warning');
            return;
        }

        const btn = document.getElementById('connectBtn');
        const status = document.getElementById('connectStatus');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Connecting...';
        status.innerHTML = '';

        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 30000);
            const r = await fetch(`${this.apiBase}/connect`, {
                signal: controller.signal,
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, username: user, password: pass, port })
            });
            const data = await r.json();
            clearTimeout(timeout);

            if (r.ok) {
                this.connected = true;
                this.serverInfo = { host, username: user, password: pass, port };
                this.saveConnection();
                this.updateConnectionUI(true, host);
                this.setInputEnabled(true);
                status.textContent = '';
                this.showToast(`Connected to ${host}`, 'success');

                // Close mobile sidebar after connecting
                document.getElementById('chatSidebar')?.classList.remove('open');
                document.getElementById('sidebarOverlay')?.classList.remove('active');

                this.addMsg('agent', `Connected to **${host}**. Let me get a quick overview of this server...`);
                
                // Auto-fetch server overview after connecting
                setTimeout(() => {
                    const input = document.getElementById('chatInput');
                    if (input) {
                        input.value = 'Give me a server overview';
                        this.send();
                    }
                }, 500);
            } else {
                const errMsg = data.detail || 'Connection failed';
                status.innerHTML = `<div class="connect-error">
                    <span class="error-icon">⚠️</span>
                    <span class="error-text">${errMsg}</span>
                    <button class="error-retry" onclick="chat.connect()">Retry</button>
                </div>`;
            }
        } catch (err) {
            const errMsg = err.name === 'AbortError' ? 'Connection timed out — server may be unreachable' : err.message;
            status.innerHTML = `<div class="connect-error">
                <span class="error-icon">⚠️</span>
                <span class="error-text">${errMsg}</span>
                <button class="error-retry" onclick="chat.connect()">Retry</button>
            </div>`;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span class="c-btn-icon" id="connectIcon">🔗</span><span id="connectLabel">Connect</span>';
        }
    }

    disconnect() {
        this.connected = false;
        this.serverInfo = null;
        this.setInputEnabled(false);
        localStorage.removeItem('mediAItor_conn');
        // Clean up active operations
        if (this._thinkingTimer) { clearInterval(this._thinkingTimer); this._thinkingTimer = null; }
        // Remove any active thinking panels
        document.querySelectorAll('[id^="thinking-"]').forEach(el => el.remove());
        // Reset agent status
        const asState = document.getElementById('asState');
        const asFacts = document.getElementById('asFacts');
        const asHyps = document.getElementById('asHyps');
        const asConf = document.getElementById('asConf');
        if (asState) asState.textContent = 'Idle';
        if (asFacts) asFacts.textContent = '0';
        if (asHyps) asHyps.textContent = '0';
        if (asConf) asConf.textContent = '—';
        this.updateConnectionUI(false);
        this.addMsg('system', 'Disconnected from server.');
        this.showToast('Disconnected', 'info');
    }

    updateConnectionUI(connected, host) {
        const nav = document.getElementById('navConnection');
        const connectSec = document.getElementById('connectSection');
        const serverSec = document.getElementById('serverInfoSection');
        const card = document.getElementById('serverInfoCard');
        // Sanitize host to prevent XSS
        const safeHost = (host || '').replace(/[<>"'&]/g, c => ({'<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','&':'&amp;'}[c]));

        if (connected) {
            nav.innerHTML = `<span class="conn-dot conn-on"></span> ${safeHost}`;
            connectSec.style.display = 'none';
            serverSec.style.display = 'block';
            card.innerHTML = `<div class="si-row"><span class="si-label">Host</span><span class="si-val">${safeHost}</span></div>
                <div class="si-row"><span class="si-label">Port</span><span class="si-val">${this.serverInfo?.port || 443}</span></div>
                <div class="si-row"><span class="si-label">Status</span><span class="si-val" style="color:var(--green)">Connected</span></div>`;
        } else {
            nav.innerHTML = '<span class="conn-dot conn-off"></span> Not Connected';
            connectSec.style.display = 'block';
            serverSec.style.display = 'none';
        }
    }

    saveConnection() {
        if (this.serverInfo) {
            localStorage.setItem('mediAItor_conn', JSON.stringify({
                host: this.serverInfo.host,
                username: this.serverInfo.username,
                port: this.serverInfo.port
            }));
        }
    }

    loadSaved() {
        try {
            const saved = JSON.parse(localStorage.getItem('mediAItor_conn'));
            if (saved?.host) {
                document.getElementById('cHost').value = saved.host;
                document.getElementById('cUser').value = saved.username || '';
                if (saved.port) document.getElementById('cPort').value = saved.port;
                // Auto-focus password field since host/user are pre-filled
                setTimeout(() => {
                    const passField = document.getElementById('cPass');
                    if (passField && saved.host && saved.username) passField.focus();
                }, 300);
            }
        } catch (e) {}
    }

    // ─── Chat ─────────────────────────────────────────────
    async send() {
        const input = document.getElementById('chatInput');
        const msg = input.value.trim();
        if (!msg) return;

        if (!this.connected) {
            this.addMsg('system', 'Please connect to a server first using the panel on the left.');
            return;
        }

        input.value = '';
        input.style.height = 'auto';

        // Hide suggestions with animation after first message
        const sug = document.getElementById('chatSuggestions');
        if (sug && !sug.classList.contains('hiding')) sug.classList.add('hiding');

        this.addMsg('user', msg);

        // Create a live thinking panel instead of static dots
        const thinkingId = this.addThinkingPanel();
        this.updateAgentStatus('Investigating...');
        this._thinkingStepCount = 0;
        this._thinkingStartTime = Date.now();

        try {
            // Use SSE streaming endpoint for live progress
            const r = await fetch(`${this.apiBase}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg, action_level: this.actionLevel })
            });

            // Check if we got SSE or a plain JSON response (e.g. error)
            const contentType = r.headers.get('content-type') || '';
            if (!contentType.includes('text/event-stream')) {
                // Fallback: plain JSON response
                const result = await r.json();
                document.getElementById(thinkingId)?.remove();
                if (result.type === 'error') {
                    this.addMsg('system', result.message);
                    this.updateAgentStatus('Error');
                } else {
                    this._handleResult(result);
                }
                return;
            }

            // Process SSE stream
            const reader = r.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalResult = null;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        if (event.event === 'heartbeat') continue;

                        if (event.event === 'thought') {
                            this._thinkingStepCount++;
                            this.updateThinkingPanel(thinkingId, event.data);
                            this.updateAgentStatus(`Thinking... Step ${this._thinkingStepCount}`);
                        } else if (event.event === 'action_start') {
                            this.updateThinkingActionStart(thinkingId, event.data);
                        } else if (event.event === 'action_result') {
                            this.updateThinkingAction(thinkingId, event.data);
                        } else if (event.event === 'findings') {
                            this.updateThinkingFindings(thinkingId, event.data);
                        } else if (event.event === 'hypothesis_update') {
                            this.updateThinkingHypotheses(thinkingId, event.data);
                        } else if (event.event === 'conclusion') {
                            this.updateThinkingConclusion(thinkingId, event.data);
                        } else if (event.event === 'complete') {
                            finalResult = event.data;
                        } else if (event.event === 'error') {
                            document.getElementById(thinkingId)?.remove();
                            this.addMsg('system', event.data?.message || 'Unknown error');
                            this.updateAgentStatus('Error');
                            return;
                        }
                    } catch (e) { /* skip unparseable */ }
                }
            }

            // Finalize: collapse thinking panel, show result
            this.finalizeThinkingPanel(thinkingId);

            if (finalResult) {
                this._handleResult(finalResult);
            }

        } catch (err) {
            document.getElementById(thinkingId)?.remove();
            this.addMsg('system', `Network error: ${err.message}`);
            this.updateAgentStatus('Error');
        }
    }

    _handleResult(result) {
        if (result.type === 'error') {
            this.addMsg('system', result.message);
            this.updateAgentStatus('Error');
            return;
        }
        switch (result.type) {
            case 'investigation':
                this.handleInvestigation(result);
                break;
            case 'follow_up':
                this.handleFollowUp(result);
                break;
            case 'remediation_proposal':
                this.handleRemediationProposal(result);
                break;
            case 'remediation_result':
                this.handleRemediationResult(result);
                break;
            case 'status':
                this.handleStatus(result);
                break;
            case 'explanation':
            case 'answer':
            default:
                this.handleAnswer(result);
                break;
        }
    }

    // ─── Rich Response Handlers ───────────────────────────────

    handleAnswer(result) {
        const msg = result.message || '';
        let html = '';
        
        // Detect if this is a server overview (contains "Component Health:")
        if (msg.includes('Component Health:') || msg.includes('Server Overview')) {
            html = this._renderServerOverview(msg);
        } else if (msg.includes('**Total Memory:**') || msg.includes('DIMMs:')) {
            html = this._renderMemoryInfo(msg);
        } else if (msg.includes('**CPU:**') || msg.includes('processor(s)')) {
            html = this._renderCpuInfo(msg);
        } else {
            html = `<div class="msg-answer">${this.formatText(msg)}</div>`;
        }
        
        if (result.metrics) {
            html += this._buildMetricsCard(result.metrics);
        }
        
        this.addMsgHtml('agent', html);
        
        const followUps = this._buildContextualFollowUps(msg, result.data);
        if (followUps.length) this.addFollowUps(followUps);
        this.updateAgentStatus('Ready');
    }

    _renderServerOverview(msg) {
        const lines = msg.split('\n').filter(l => l.trim());
        let html = '<div class="overview-card-chat">';
        
        // Parse header line (model name)
        const headerMatch = msg.match(/\*\*(.+?)\*\*\s*—\s*Server Overview/);
        const tagMatch = msg.match(/Service Tag:\s*\*\*(.+?)\*\*/);
        const powerMatch = msg.match(/Power:\s*(\w+)/);
        const cpuMatch = msg.match(/CPU:\s*(.+?)\s*\|/);
        const ramMatch = msg.match(/RAM:\s*(.+?)\s*\|/);
        const biosMatch = msg.match(/BIOS:\s*(.+?)\s*\|/);
        const idracMatch = msg.match(/iDRAC:\s*(.+?)$/m);
        
        // Server identity header
        html += `<div class="ov-header">
            <div class="ov-model">${headerMatch ? headerMatch[1] : 'Server'}</div>
            <div class="ov-badges">
                ${tagMatch ? `<span class="ov-badge tag">${tagMatch[1]}</span>` : ''}
                ${powerMatch ? `<span class="ov-badge ${powerMatch[1] === 'On' ? 'power-on' : 'power-off'}">${powerMatch[1] === 'On' ? '● On' : '○ Off'}</span>` : ''}
            </div>
        </div>`;
        
        // Specs row
        html += '<div class="ov-specs">';
        if (cpuMatch) html += `<div class="ov-spec"><span class="ov-spec-label">CPU</span><span class="ov-spec-val">${cpuMatch[1].trim()}</span></div>`;
        if (ramMatch) html += `<div class="ov-spec"><span class="ov-spec-label">RAM</span><span class="ov-spec-val">${ramMatch[1].trim()}</span></div>`;
        if (biosMatch) html += `<div class="ov-spec"><span class="ov-spec-label">BIOS</span><span class="ov-spec-val">${biosMatch[1].trim()}</span></div>`;
        if (idracMatch) html += `<div class="ov-spec"><span class="ov-spec-label">iDRAC</span><span class="ov-spec-val">${idracMatch[1].trim()}</span></div>`;
        html += '</div>';
        
        // Component health grid
        const healthLines = lines.filter(l => l.match(/^🟢|^🟡|^🔴/) && l.includes(':'));
        if (healthLines.length) {
            html += '<div class="ov-health-grid">';
            healthLines.forEach(line => {
                const icon = line.startsWith('🟢') ? '🟢' : line.startsWith('🟡') ? '🟡' : '🔴';
                const statusClass = line.startsWith('🟢') ? 'ok' : line.startsWith('🟡') ? 'warn' : 'crit';
                const text = line.replace(/^[🟢🟡🔴]\s*/, '').replace(/\*\*/g, '');
                const nameMatch = text.match(/^(.+?):\s*(.+)/);
                if (nameMatch) {
                    html += `<div class="ov-health-item ${statusClass}">
                        <span class="ov-health-icon">${icon}</span>
                        <span class="ov-health-name">${nameMatch[1]}</span>
                        <span class="ov-health-val">${nameMatch[2]}</span>
                    </div>`;
                }
            });
            html += '</div>';
        }
        
        // Critical issues
        const critSection = msg.match(/Critical Issues:[\s\S]*?(?=🟡|What would|$)/);
        if (critSection) {
            const critLines = critSection[0].split('\n').filter(l => l.trim().startsWith('•'));
            if (critLines.length) {
                html += '<div class="ov-alerts">';
                html += '<div class="ov-alerts-title">Critical Issues</div>';
                critLines.forEach(l => {
                    html += `<div class="ov-alert critical">${l.replace('•', '').trim()}</div>`;
                });
                html += '</div>';
            }
        }
        
        // Warnings
        const warnSection = msg.match(/Warnings:[\s\S]*?(?=What would|$)/);
        if (warnSection) {
            const warnLines = warnSection[0].split('\n').filter(l => l.trim().startsWith('•'));
            if (warnLines.length) {
                html += '<div class="ov-alerts">';
                html += '<div class="ov-alerts-title">Warnings</div>';
                warnLines.slice(0, 3).forEach(l => {
                    html += `<div class="ov-alert warning">${l.replace('•', '').trim()}</div>`;
                });
                if (warnLines.length > 3) html += `<div class="ov-alert-more">+${warnLines.length - 3} more</div>`;
                html += '</div>';
            }
        }
        
        html += '</div>';
        return html;
    }

    _renderMemoryInfo(msg) {
        const totalMatch = msg.match(/Total Memory:\*\*\s*(\d+\s*\w+)/);
        const dimmMatch = msg.match(/DIMMs:\*\*\s*(\d+)\s*populated/);
        
        let html = '<div class="info-card-chat">';
        html += '<div class="info-card-header">🧠 Memory</div>';
        if (totalMatch) html += `<div class="info-card-big">${totalMatch[1]}</div>`;
        if (dimmMatch) html += `<div class="info-card-sub">${dimmMatch[1]} DIMMs populated</div>`;
        
        // Parse DIMM list
        const dimmLines = msg.split('\n').filter(l => l.trim().startsWith('•'));
        if (dimmLines.length) {
            html += '<div class="info-card-list">';
            dimmLines.forEach(l => {
                html += `<div class="info-card-list-item">${l.replace('•', '').trim()}</div>`;
            });
            html += '</div>';
        }
        html += '</div>';
        return html;
    }

    _renderCpuInfo(msg) {
        const cpuMatch = msg.match(/CPU:\*\*\s*(.+)/);
        const countMatch = msg.match(/Count:\*\*\s*(\d+)/);
        
        let html = '<div class="info-card-chat">';
        html += '<div class="info-card-header">🖥️ Processor</div>';
        if (cpuMatch) html += `<div class="info-card-big">${cpuMatch[1].trim()}</div>`;
        if (countMatch) html += `<div class="info-card-sub">${countMatch[1]} socket(s)</div>`;
        html += '</div>';
        return html;
    }

    handleInvestigation(result) {
        const diag = result.data?.diagnosis || {};
        const chain = result.data?.reasoning_chain || diag.reasoning_chain || [];
        const recs = result.data?.recommendations || diag.recommendations || [];

        let html = '';
        
        // ── Diagnosis header card ──
        const confidence = diag.confidence || 0;
        const confColor = confidence >= 70 ? 'var(--green)' : confidence >= 40 ? 'var(--yellow)' : 'var(--red)';
        const category = diag.category || 'unknown';
        const catIcon = {thermal:'🌡️',power:'⚡',memory:'🧠',storage:'💾',network:'🌐',firmware:'📦',cpu:'🖥️'}[category] || '🔍';
        
        if (diag.root_cause) {
            html += `<div class="inv-diagnosis-card">
                <div class="inv-diag-header">
                    <span class="inv-diag-icon">${catIcon}</span>
                    <div class="inv-diag-info">
                        <div class="inv-diag-title">${this.formatText(diag.root_cause)}</div>
                        <div class="inv-diag-meta">
                            <span class="inv-conf-badge" style="color:${confColor}">
                                <span class="inv-conf-bar" style="width:${confidence}%;background:${confColor}"></span>
                                ${confidence}% confidence
                            </span>
                            <span class="inv-cat-badge">${catIcon} ${category}</span>
                            <span class="inv-evidence-badge">${(diag.evidence_chain || []).length} evidence points</span>
                        </div>
                    </div>
                </div>`;
            
            // Critical findings
            if (diag.critical_findings?.length) {
                html += '<div class="inv-findings"><strong>Critical Findings:</strong>';
                diag.critical_findings.slice(0, 5).forEach(f => {
                    html += `<div class="inv-finding critical">🔴 ${f.description || f}</div>`;
                });
                html += '</div>';
            }
            
            // Warning findings
            if (diag.warning_findings?.length) {
                html += '<div class="inv-findings"><strong>Warnings:</strong>';
                diag.warning_findings.slice(0, 3).forEach(f => {
                    html += `<div class="inv-finding warning">🟡 ${f.description || f}</div>`;
                });
                html += '</div>';
            }
            
            html += '</div>';
        } else {
            html += `<div class="msg-answer">${this.formatText(result.message)}</div>`;
        }

        // ── Reasoning chain (collapsible) ──
        if (chain.length > 0) {
            html += `<details class="inv-chain-details">
                <summary class="inv-chain-summary">💭 ${chain.length}-step reasoning chain</summary>
                <div class="inv-chain">`;
            chain.forEach(t => {
                const icon = t.conclusion ? '✅' : t.next_action ? '🔍' : '💭';
                html += `<div class="inv-chain-step">
                    <span class="inv-step-num">${t.step}</span>
                    <div class="inv-step-body">
                        <div class="inv-step-text">${t.reasoning || ''}</div>
                        ${t.next_action ? `<div class="inv-step-action">→ ${t.next_action}</div>` : ''}
                        ${t.conclusion ? `<div class="inv-step-conclusion">✅ ${t.conclusion}</div>` : ''}
                    </div>
                </div>`;
            });
            html += '</div></details>';
        }

        // ── Hypotheses explored ──
        if (diag.hypotheses_final?.length) {
            html += '<div class="inv-hypotheses"><strong>Hypotheses Explored:</strong>';
            diag.hypotheses_final.forEach(h => {
                const pct = Math.round((h.confidence || 0) * 100);
                const cls = pct >= 70 ? 'bar-high' : pct >= 40 ? 'bar-med' : 'bar-low';
                html += `<div class="msg-hyp-row">
                    <span class="msg-hyp-name">${h.description || h.id}</span>
                    <div class="msg-hyp-bar"><div class="msg-hyp-fill ${cls}" style="width:${pct}%"></div></div>
                    <span class="msg-hyp-pct">${pct}%</span>
                </div>`;
            });
            html += '</div>';
        }

        // ── Recommendations ──
        if (recs.length > 0 || diag.remediation_steps?.length) {
            const steps = recs.length ? recs : diag.remediation_steps;
            html += '<div class="inv-recs"><strong>Recommended Actions:</strong><ol>';
            (Array.isArray(steps) ? steps : []).slice(0, 6).forEach(r => {
                const text = typeof r === 'string' ? r : (r.description || r.title || r.message || '');
                if (text) html += `<li>${text}</li>`;
            });
            html += '</ol></div>';
        }

        this.addMsgHtml('agent', html);

        // Contextual follow-ups based on diagnosis
        const followUps = ['Show me the evidence'];
        if (diag.category === 'thermal') followUps.push('Check temperatures now');
        if (diag.category === 'power') followUps.push('Check power supplies');
        if (diag.category === 'memory') followUps.push('Check memory details');
        if (diag.remediation_steps?.length) followUps.push('Can you fix this?');
        followUps.push('What else should I check?');
        this.addFollowUps(followUps);

        if (result.metrics) this.renderMetrics(result.metrics);
        this.updateAgentStatus('Investigation complete', result.metrics);
    }

    handleFollowUp(result) {
        let html = `<div class="msg-answer">${this.formatText(result.message)}</div>`;
        const data = result.data || {};
        const facts = data.facts || [];
        const tool = data.tool_used || '';

        // ── Rich facts display ──
        if (facts.length > 0) {
            const critCount = facts.filter(f => f.status === 'critical').length;
            const warnCount = facts.filter(f => f.status === 'warning').length;
            const okCount = facts.filter(f => f.status === 'ok').length;
            
            // Summary bar
            html += `<div class="facts-summary-bar">
                <span class="facts-total">${facts.length} data points</span>
                ${critCount ? `<span class="facts-badge critical">${critCount} critical</span>` : ''}
                ${warnCount ? `<span class="facts-badge warning">${warnCount} warning</span>` : ''}
                ${okCount ? `<span class="facts-badge ok">${okCount} ok</span>` : ''}
            </div>`;

            // Facts table with proper formatting
            html += '<div class="msg-facts">';
            facts.forEach(f => {
                const statusIcon = f.status === 'ok' ? '🟢' : f.status === 'warning' ? '🟡' : f.status === 'critical' ? '🔴' : '⚪';
                const val = f.value != null ? (f.unit ? `${f.value}${f.unit}` : String(f.value)) : '';
                const name = f.component || f.description || '';
                html += `<div class="msg-fact-row ${f.status || ''}">
                    <span class="fact-icon">${statusIcon}</span>
                    <span class="msg-fact-name">${name}</span>
                    ${val ? `<span class="msg-fact-val">${val}</span>` : ''}
                </div>`;
            });
            html += '</div>';
        }

        // Hypotheses
        if (data.hypotheses?.length) {
            html += '<div class="inv-hypotheses"><strong>Active Hypotheses:</strong>';
            data.hypotheses.forEach(h => {
                const pct = Math.round((h.confidence || 0) * 100);
                const cls = pct >= 70 ? 'bar-high' : pct >= 40 ? 'bar-med' : 'bar-low';
                html += `<div class="msg-hyp-row">
                    <span class="msg-hyp-name">${h.description}</span>
                    <div class="msg-hyp-bar"><div class="msg-hyp-fill ${cls}" style="width:${pct}%"></div></div>
                    <span class="msg-hyp-pct">${pct}%</span>
                </div>`;
            });
            html += '</div>';
        }

        this.addMsgHtml('agent', html);
        
        // Contextual follow-ups based on what was checked
        const followUps = this._buildContextualFollowUps(result.message, data);
        this.addFollowUps(followUps.length ? followUps : ['What else should I check?', 'Run full investigation', 'Can you fix this?']);
        this.updateAgentStatus('Ready');
    }

    handleStatus(result) {
        let html = `<div class="msg-status-card">
            <div class="msg-status-header">📊 Current Status</div>
            <div class="msg-status-body">${this.formatText(result.message)}</div>
        </div>`;
        
        if (result.metrics) {
            html += this._buildMetricsCard(result.metrics);
        }
        
        this.addMsgHtml('agent', html);
        this.addFollowUps(['Run another investigation', 'Check temperatures', 'Check system logs']);
        this.updateAgentStatus('Ready');
    }

    handleRemediationProposal(result) {
        const plan = result.plan || {};
        let html = `<div class="msg-remed-card">`;
        
        // Header with risk badge
        const riskColors = {low: 'var(--green)', medium: 'var(--yellow)', high: 'var(--red)'};
        html += `<div class="msg-remed-header">
            <span class="msg-remed-icon">🔧</span>
            <div>
                <div class="msg-remed-title">${plan.workflow || 'Remediation Plan'}</div>
                <div class="msg-remed-meta">
                    For: ${plan.root_cause || '?'} · 
                    Confidence: <strong>${plan.confidence || 0}%</strong> · 
                    Risk: <span style="color:${riskColors[plan.risk] || riskColors.low};font-weight:700">${(plan.risk || 'low').toUpperCase()}</span>
                </div>
            </div>
        </div>`;

        if (plan.safe_steps?.length) {
            html += `<div class="msg-remed-steps"><div class="remed-steps-label safe">Safe Steps (auto-executable)</div><ol>`;
            plan.safe_steps.forEach(s => html += `<li><span class="step-badge safe">SAFE</span> ${s}</li>`);
            html += '</ol></div>';
        }
        if (plan.risky_steps?.length) {
            html += `<div class="msg-remed-steps"><div class="remed-steps-label caution">Steps Requiring Caution</div><ol>`;
            plan.risky_steps.forEach(s => html += `<li><span class="step-badge caution">CAUTION</span> ${s}</li>`);
            html += '</ol></div>';
        }
        if (plan.requires_full_control) {
            html += `<div class="remed-warning">⚠️ Some steps require <strong>Full Control</strong> action level</div>`;
        }

        html += `<div class="msg-remed-actions">
            <button class="remed-approve" onclick="chat.approveRemediation()">✅ Approve & Execute</button>
            <button class="remed-reject" onclick="chat.addMsg('system','Remediation cancelled.')">✕ Cancel</button>
        </div>`;
        html += `</div>`;

        this.addMsgHtml('agent', html);
        this.updateAgentStatus('Awaiting approval');
    }

    async approveRemediation() {
        const input = document.getElementById('chatInput');
        if (input) input.value = 'approve';
        await this.send();
    }

    handleRemediationResult(result) {
        const data = result.data || {};
        let html = `<div class="msg-remed-result-card">
            <div class="msg-remed-result-header">🔧 Remediation Results</div>
            <div class="msg-answer">${this.formatText(result.message)}</div>`;

        if (data.results?.length) {
            html += '<div class="remed-results-list">';
            data.results.forEach(r => {
                const icon = r.success || r.status === 'executed' ? '✅' : r.status === 'manual' ? '🔧' : r.status === 'noted' ? '📝' : '❌';
                const cls = r.success || r.status === 'executed' ? 'success' : r.status === 'manual' ? 'manual' : r.status === 'noted' ? 'noted' : 'failed';
                html += `<div class="remed-result-step ${cls}">
                    <span class="remed-result-icon">${icon}</span>
                    <span class="remed-result-text">Step ${r.step}: ${r.description}</span>
                    <span class="remed-result-status">${r.status}</span>
                </div>`;
            });
            html += '</div>';
            
            // Summary counts
            const executed = data.executed_count || data.results.filter(r => r.success || r.status === 'executed').length;
            const manual = data.manual_count || data.results.filter(r => r.status === 'manual').length;
            const failed = data.failed_count || data.results.filter(r => r.status === 'failed').length;
            html += `<div class="remed-result-summary">
                ${executed ? `<span class="remed-count success">${executed} executed</span>` : ''}
                ${manual ? `<span class="remed-count manual">${manual} manual</span>` : ''}
                ${failed ? `<span class="remed-count failed">${failed} failed</span>` : ''}
            </div>`;
        }
        html += '</div>';

        this.addMsgHtml('agent', html);
        this.addFollowUps(['What\'s the current status?', 'Run health check', 'Run another investigation']);
        this.updateAgentStatus('Remediation complete');
    }

    // ─── Contextual Follow-ups Builder ────────────────────────
    _buildContextualFollowUps(message, data) {
        const msg = (message || '').toLowerCase();
        const tool = data?.tool_used || '';
        const followUps = [];
        
        // Based on what tool was used
        if (tool.includes('temp') || msg.includes('temperature')) {
            followUps.push('Check fan speeds', 'Check power supplies', 'Run full investigation');
        } else if (tool.includes('fan') || msg.includes('fan')) {
            followUps.push('Check temperatures', 'Check power consumption', 'Run full investigation');
        } else if (tool.includes('power') || msg.includes('power')) {
            followUps.push('Check temperatures', 'Check system logs', 'Can you fix this?');
        } else if (tool.includes('memory') || msg.includes('memory') || msg.includes('ram')) {
            followUps.push('Check system logs for ECC errors', 'Check BIOS settings', 'Run full investigation');
        } else if (tool.includes('storage') || msg.includes('storage') || msg.includes('disk') || msg.includes('raid')) {
            followUps.push('Check system logs', 'Check firmware versions', 'Run full investigation');
        } else if (tool.includes('firmware') || msg.includes('firmware') || msg.includes('bios')) {
            followUps.push('Check BIOS settings', 'Check system logs', 'What needs updating?');
        } else if (tool.includes('log') || msg.includes('log') || msg.includes('error')) {
            followUps.push('Run full investigation', 'Check temperatures', 'Can you fix this?');
        } else if (tool.includes('network') || msg.includes('network') || msg.includes('nic')) {
            followUps.push('Check system logs', 'Check firmware', 'Run full investigation');
        } else if (msg.includes('model') || msg.includes('service tag') || msg.includes('overview')) {
            followUps.push('Run health check', 'Check temperatures', 'Check system logs');
        }
        
        // Always offer these if nothing specific
        if (followUps.length === 0) {
            followUps.push('Give me a server overview', 'Check temperatures', 'Check system logs');
        }
        
        // Add a "deep" option if there are critical findings
        if (data?.critical_count > 0) {
            followUps.unshift('Run full investigation');
        }
        
        return followUps.slice(0, 4); // Max 4 follow-ups
    }

    // ─── Metrics Card Builder ─────────────────────────────────
    _buildMetricsCard(metrics) {
        if (!metrics) return '';
        const m = metrics;
        return `<div class="msg-metrics-card">
            <div class="metrics-header">📊 Business Impact</div>
            <div class="metrics-grid">
                ${m.investigation_time_seconds ? `<div class="metric-item"><span class="metric-val">${m.investigation_time_seconds.toFixed(0)}s</span><span class="metric-lbl">Investigation</span></div>` : ''}
                ${m.time_saved_minutes ? `<div class="metric-item highlight"><span class="metric-val">${m.time_saved_minutes.toFixed(0)} min</span><span class="metric-lbl">Time Saved</span></div>` : ''}
                ${m.estimated_cost_saved ? `<div class="metric-item highlight"><span class="metric-val">$${m.estimated_cost_saved.toFixed(0)}</span><span class="metric-lbl">Cost Saved</span></div>` : ''}
                ${m.facts_collected ? `<div class="metric-item"><span class="metric-val">${m.facts_collected}</span><span class="metric-lbl">Facts</span></div>` : ''}
                ${m.hypotheses_tested ? `<div class="metric-item"><span class="metric-val">${m.hypotheses_tested}</span><span class="metric-lbl">Hypotheses</span></div>` : ''}
                ${m.subsystems_checked ? `<div class="metric-item"><span class="metric-val">${m.subsystems_checked}</span><span class="metric-lbl">Subsystems</span></div>` : ''}
                ${m.escalation_avoided ? '<div class="metric-item good"><span class="metric-val">✓</span><span class="metric-lbl">No Escalation</span></div>' : ''}
                ${m.truck_roll_avoided ? '<div class="metric-item good"><span class="metric-val">✓</span><span class="metric-lbl">No Truck Roll</span></div>' : ''}
            </div>
        </div>`;
    }

    // ─── Message Rendering ────────────────────────────────
    addMsg(role, text) {
        const container = document.getElementById('chatMessages');
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        const div = document.createElement('div');
        div.id = id;
        div.className = `chat-msg msg-${role}`;

        const avatarIcon = role === 'user' ? '👤' : role === 'agent' ? '🧠' : 'ℹ️';
        const name = role === 'user' ? 'You' : role === 'agent' ? 'Medi-AI-tor' : 'System';
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        div.innerHTML = `
            <div class="msg-avatar">${avatarIcon}</div>
            <div class="msg-body">
                <div class="msg-meta">
                    <span class="msg-name">${name}</span>
                    <span class="msg-time">${time}</span>
                </div>
                <div class="msg-text"><p>${this.formatText(text)}</p></div>
            </div>`;

        container.appendChild(div);
        this.scrollToBottom();
        return id;
    }

    addMsgHtml(role, html) {
        const container = document.getElementById('chatMessages');
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        const div = document.createElement('div');
        div.id = id;
        div.className = `chat-msg msg-${role}`;

        const avatarIcon = role === 'agent' ? '🧠' : 'ℹ️';
        const name = role === 'agent' ? 'Medi-AI-tor' : 'System';
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        div.innerHTML = `
            <div class="msg-avatar">${avatarIcon}</div>
            <div class="msg-body">
                <div class="msg-meta">
                    <span class="msg-name">${name}</span>
                    <span class="msg-time">${time}</span>
                </div>
                <div class="msg-text">${html}</div>
            </div>`;

        container.appendChild(div);
        this.scrollToBottom();
        return id;
    }

    addTyping() {
        const container = document.getElementById('chatMessages');
        const id = 'typing-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'chat-msg msg-agent msg-typing';
        div.innerHTML = `
            <div class="msg-avatar">🧠</div>
            <div class="msg-body">
                <div class="msg-name">Medi-AI-tor</div>
                <div class="msg-text"><span class="typing-dots"><span></span><span></span><span></span></span></div>
            </div>`;
        container.appendChild(div);
        this.scrollToBottom();
        return id;
    }

    // ─── Dynamic Thinking Panel ──────────────────────────
    addThinkingPanel() {
        // Clean up any existing thinking panel timer
        if (this._thinkingTimer) { clearInterval(this._thinkingTimer); this._thinkingTimer = null; }
        const container = document.getElementById('chatMessages');
        const id = 'thinking-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        const div = document.createElement('div');
        div.id = id;
        div.className = 'chat-msg msg-agent msg-thinking-panel';
        div.innerHTML = `
            <div class="msg-avatar">🧠</div>
            <div class="msg-body">
                <div class="msg-name">Medi-AI-tor</div>
                <div class="msg-text">
                    <div class="thinking-container">
                        <div class="thinking-header">
                            <span class="collapse-chevron">▾</span>
                            <span class="thinking-pulse"></span>
                            <span class="thinking-title">Agent is investigating...</span>
                            <span class="thinking-timer">0s</span>
                        </div>
                        <div class="thinking-steps"></div>
                    </div>
                </div>
            </div>`;
        container.appendChild(div);
        this.scrollToBottom();

        // Start timer
        this._thinkingTimer = setInterval(() => {
            const el = div.querySelector('.thinking-timer');
            if (el) {
                const elapsed = Math.round((Date.now() - this._thinkingStartTime) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                el.textContent = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
            }
        }, 1000);

        return id;
    }

    updateThinkingPanel(panelId, thought) {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const stepsEl = panel.querySelector('.thinking-steps');
        if (!stepsEl) return;

        const step = thought.step || this._thinkingStepCount;
        const reasoning = thought.reasoning || '';
        const nextAction = thought.next_action || '';
        const conclusion = thought.conclusion || '';

        // Choose icon based on content
        let icon = '💭';
        if (nextAction.includes('temperature') || nextAction.includes('thermal')) icon = '🌡️';
        else if (nextAction.includes('fan')) icon = '🌀';
        else if (nextAction.includes('power')) icon = '⚡';
        else if (nextAction.includes('memory')) icon = '🧠';
        else if (nextAction.includes('storage')) icon = '💾';
        else if (nextAction.includes('network')) icon = '🌐';
        else if (nextAction.includes('firmware')) icon = '📦';
        else if (nextAction.includes('log')) icon = '📋';
        else if (nextAction.includes('health')) icon = '❤️';
        else if (nextAction.includes('system_info') || nextAction.includes('server')) icon = '🖥️';
        else if (conclusion) icon = '✅';

        const stepDiv = document.createElement('div');
        stepDiv.className = 'thinking-step thinking-step-new';

        let stepHtml = `<span class="thinking-step-icon">${icon}</span>`;
        stepHtml += `<span class="thinking-step-text">`;

        if (conclusion) {
            stepHtml += `<strong>Conclusion:</strong> ${conclusion.substring(0, 150)}`;
        } else {
            stepHtml += reasoning.substring(0, 120);
            if (nextAction) stepHtml += ` → <em class="thinking-action">${nextAction}</em>`;
        }
        stepHtml += `</span>`;
        stepDiv.innerHTML = stepHtml;

        stepsEl.appendChild(stepDiv);

        // Trigger animation
        requestAnimationFrame(() => stepDiv.classList.remove('thinking-step-new'));

        // Update header
        const title = panel.querySelector('.thinking-title');
        if (title) {
            if (conclusion) {
                title.textContent = 'Investigation complete';
            } else if (nextAction) {
                const actionName = nextAction.replace('check_', '').replace(/_/g, ' ');
                title.textContent = `Checking ${actionName}...`;
            } else {
                title.textContent = `Reasoning... (step ${step})`;
            }
        }

        // Auto scroll
        const container = document.getElementById('chatMessages');
        this.scrollToBottom();
    }

    updateThinkingActionStart(panelId, data) {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const stepsEl = panel.querySelector('.thinking-steps');
        if (!stepsEl) return;

        const toolName = (data.tool || data.tool_name || '').replace('check_', '').replace(/_/g, ' ');
        const stepDiv = document.createElement('div');
        stepDiv.className = 'thinking-step thinking-step-action-start thinking-step-new';
        stepDiv.innerHTML = `<span class="thinking-step-icon">⏳</span>
            <span class="thinking-step-text">Running <strong>${toolName || 'tool'}</strong>...</span>`;
        stepsEl.appendChild(stepDiv);
        requestAnimationFrame(() => stepDiv.classList.remove('thinking-step-new'));

        const container = document.getElementById('chatMessages');
        this.scrollToBottom();
    }

    updateThinkingAction(panelId, actionResult) {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const stepsEl = panel.querySelector('.thinking-steps');
        if (!stepsEl) return;

        // Remove the "Running..." step if it exists
        const pending = stepsEl.querySelector('.thinking-step-action-start:last-of-type');
        if (pending) pending.remove();

        const summary = actionResult.summary || '';
        const success = actionResult.success !== false;
        const critCount = (actionResult.critical || []).length;
        const warnCount = (actionResult.warnings || []).length;

        const stepDiv = document.createElement('div');
        stepDiv.className = 'thinking-step thinking-step-result thinking-step-new';

        let icon = success ? '📊' : '⚠️';
        if (critCount > 0) icon = '🔴';
        else if (warnCount > 0) icon = '🟡';

        let badge = '';
        if (critCount > 0) badge += `<span class="thinking-badge badge-crit">${critCount} critical</span>`;
        if (warnCount > 0) badge += `<span class="thinking-badge badge-warn">${warnCount} warning</span>`;

        stepDiv.innerHTML = `<span class="thinking-step-icon">${icon}</span>
            <span class="thinking-step-text thinking-result-text">${summary.substring(0, 150)} ${badge}</span>`;

        stepsEl.appendChild(stepDiv);
        requestAnimationFrame(() => stepDiv.classList.remove('thinking-step-new'));

        const container = document.getElementById('chatMessages');
        this.scrollToBottom();
    }

    updateThinkingFindings(panelId, data) {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const stepsEl = panel.querySelector('.thinking-steps');
        if (!stepsEl) return;
        
        const findings = data.findings || data.facts || [];
        if (findings.length === 0) return;
        
        const critical = findings.filter(f => f.status === 'critical').length;
        const warning = findings.filter(f => f.status === 'warning').length;
        const ok = findings.filter(f => f.status === 'ok').length;
        
        const stepDiv = document.createElement('div');
        stepDiv.className = 'thinking-step thinking-step-new';
        let icon = critical > 0 ? '🔴' : warning > 0 ? '🟡' : '🟢';
        let summary = `${findings.length} findings: `;
        if (critical) summary += `${critical} critical `;
        if (warning) summary += `${warning} warning `;
        if (ok) summary += `${ok} ok`;
        stepDiv.innerHTML = `<span class="thinking-step-icon">${icon}</span><span class="thinking-step-text">${summary}</span>`;
        stepsEl.appendChild(stepDiv);
        requestAnimationFrame(() => stepDiv.classList.remove('thinking-step-new'));
        
        // Update facts count in sidebar
        const factsEl = document.getElementById('asFacts');
        if (factsEl) factsEl.textContent = parseInt(factsEl.textContent || '0') + findings.length;
    }

    updateThinkingHypotheses(panelId, data) {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const stepsEl = panel.querySelector('.thinking-steps');
        if (!stepsEl) return;

        const hyps = data.hypotheses || data.active || [];
        if (hyps.length === 0) return;

        // Show mini hypothesis bars inline
        const stepDiv = document.createElement('div');
        stepDiv.className = 'thinking-step thinking-step-hyp thinking-step-new';

        let barsHtml = '<span class="thinking-step-icon">📈</span><span class="thinking-step-text">';
        const top = hyps.slice(0, 3);
        top.forEach(h => {
            const pct = Math.round((h.confidence || 0) * 100);
            const name = (h.description || h.id || '').substring(0, 35);
            const cls = pct >= 60 ? 'th-bar-high' : pct >= 30 ? 'th-bar-med' : 'th-bar-low';
            barsHtml += `<span class="th-hyp-mini"><span class="th-hyp-name">${name}</span><span class="th-hyp-bar ${cls}" style="width:${Math.max(pct, 5)}%"></span><span class="th-hyp-pct">${pct}%</span></span>`;
        });
        barsHtml += '</span>';
        stepDiv.innerHTML = barsHtml;

        stepsEl.appendChild(stepDiv);
        requestAnimationFrame(() => stepDiv.classList.remove('thinking-step-new'));

        // Update sidebar
        if (hyps.length > 0) {
            const best = hyps.reduce((a, b) => (a.confidence || 0) > (b.confidence || 0) ? a : b);
            const pct = Math.round((best.confidence || 0) * 100);
            document.getElementById('asConf').textContent = pct + '%';
            document.getElementById('asHyps').textContent = hyps.length;
        }
    }

    updateThinkingConclusion(panelId, data) {
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const stepsEl = panel.querySelector('.thinking-steps');
        if (!stepsEl) return;

        const msg = data.conclusion || data.message || 'Investigation concluded.';
        const stepDiv = document.createElement('div');
        stepDiv.className = 'thinking-step thinking-step-conclusion thinking-step-new';
        stepDiv.innerHTML = `<span class="thinking-step-icon">✅</span>
            <span class="thinking-step-text"><strong>${msg.substring(0, 200)}</strong></span>`;
        stepsEl.appendChild(stepDiv);
        requestAnimationFrame(() => stepDiv.classList.remove('thinking-step-new'));

        this.updateAgentStatus('Concluded');
        const container = document.getElementById('chatMessages');
        this.scrollToBottom();
    }

    finalizeThinkingPanel(panelId) {
        if (this._thinkingTimer) {
            clearInterval(this._thinkingTimer);
            this._thinkingTimer = null;
        }
        const panel = document.getElementById(panelId);
        if (!panel) return;

        // Stop pulse animation
        const pulse = panel.querySelector('.thinking-pulse');
        if (pulse) pulse.classList.add('pulse-done');

        // Update header
        const title = panel.querySelector('.thinking-title');
        const elapsed = Math.round((Date.now() - this._thinkingStartTime) / 1000);
        if (title) title.textContent = `Investigation completed in ${elapsed}s`;

        // Make panel collapsible
        const header = panel.querySelector('.thinking-header');
        const steps = panel.querySelector('.thinking-steps');
        if (header && steps) {
            header.style.cursor = 'pointer';
            header.addEventListener('click', () => {
                steps.classList.toggle('collapsed');
                header.classList.toggle('collapsed');
            });
        }
    }

    addFollowUps(options) {
        const container = document.getElementById('chatMessages');
        const lastMsg = container.querySelector('.chat-msg.msg-agent:last-of-type .msg-text');
        const div = document.createElement('div');
        div.className = 'msg-followups';

        // Create buttons with listeners BEFORE appending to DOM
        options.forEach(o => {
            const btn = document.createElement('button');
            btn.className = 'followup-chip';
            btn.textContent = o;
            btn.addEventListener('click', () => {
                const input = document.getElementById('chatInput');
                if (input) input.value = o;
                div.remove();
                this.send();
            });
            div.appendChild(btn);
        });

        if (lastMsg) {
            lastMsg.appendChild(div);
        } else {
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-msg msg-agent';
            const avatar = document.createElement('div');
            avatar.className = 'msg-avatar';
            avatar.style.visibility = 'hidden';
            avatar.textContent = '🧠';
            const body = document.createElement('div');
            body.className = 'msg-body';
            body.appendChild(div);
            wrapper.appendChild(avatar);
            wrapper.appendChild(body);
            container.appendChild(wrapper);
        }
        this.scrollToBottom();
    }

    formatText(text) {
        if (!text) return '';
        // Escape HTML first
        let safe = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        // Code blocks (triple backtick)
        safe = safe.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) => {
            return `<pre class="code-block"><code>${code.trim()}</code></pre>`;
        });
        // Inline code
        safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
        // Bold
        safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Italic
        safe = safe.replace(/\*(.*?)\*/g, '<em>$1</em>');
        // Bullet lists (lines starting with • or -)
        safe = safe.replace(/^[•\-]\s+(.+)$/gm, '<li>$1</li>');
        safe = safe.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
        // Numbered lists
        safe = safe.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
        // Newlines to <br> (but not inside <pre> or <ul>)
        safe = safe.replace(/\n/g, '<br>');
        // Clean up <br> inside <ul> and <pre>
        safe = safe.replace(/<ul><br>/g, '<ul>');
        safe = safe.replace(/<br><\/ul>/g, '</ul>');
        safe = safe.replace(/<br><li>/g, '<li>');
        safe = safe.replace(/<\/li><br>/g, '</li>');
        return safe;
    }

    // ─── Sidebar Updates ──────────────────────────────────
    updateAgentStatus(state, metrics) {
        document.getElementById('asState').textContent = state;
        if (metrics) {
            document.getElementById('asFacts').textContent = metrics.facts_collected || 0;
            document.getElementById('asHyps').textContent = metrics.hypotheses_tested || 0;
            document.getElementById('asConf').textContent = metrics.confidence ? metrics.confidence + '%' : '—';
        }
    }

    renderMetrics(m) {
        const section = document.getElementById('metricsSection');
        const card = document.getElementById('metricsCard');
        if (!section || !card || !m) return;

        section.style.display = 'block';
        const timeSaved = Math.round(m.time_saved_minutes || 0);
        const cost = Math.round(m.estimated_cost_saved || 0).toLocaleString();
        const agentTime = Math.round(m.investigation_time_seconds || 0);

        card.innerHTML = `
            <div class="mc-row mc-highlight"><span class="mc-label">⏱ AI Time</span><span class="mc-val">${agentTime}s</span></div>
            <div class="mc-row"><span class="mc-label">vs Manual</span><span class="mc-val">~45 min</span></div>
            <div class="mc-row mc-highlight"><span class="mc-label">⏰ Time Saved</span><span class="mc-val">${timeSaved} min</span></div>
            <div class="mc-row mc-highlight"><span class="mc-label">💰 Cost Saved</span><span class="mc-val">$${cost}</span></div>
            <div class="mc-row"><span class="mc-label">📊 Data Points</span><span class="mc-val">${m.facts_collected || 0}</span></div>
            <div class="mc-row"><span class="mc-label">🔍 Subsystems</span><span class="mc-val">${m.subsystems_checked || 0}</span></div>
            <div class="mc-row"><span class="mc-label">📈 Escalation</span><span class="mc-val">${m.escalation_avoided ? '✅ Avoided' : '—'}</span></div>
            <div class="mc-row"><span class="mc-label">🚛 Truck Roll</span><span class="mc-val">${m.truck_roll_avoided ? '✅ Avoided' : '—'}</span></div>`;
    }
}

// Initialize
const chat = new CustomerChat();
