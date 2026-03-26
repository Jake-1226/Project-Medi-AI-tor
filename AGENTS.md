# Medi-AI-tor -- Development Guide

## Quick Start
```bash
pip install -r requirements.txt
pip install PyJWT cryptography
# Edit .env: set DEMO_MODE=true for development without a server
python main.py
# Open http://localhost:8000
```

## Project Structure
```
main.py                          FastAPI server, 70+ endpoints, auth middleware
core/
  agent_brain.py                 ReAct reasoning engine + chat system (2845 lines)
  agent_tools.py                 20+ diagnostic tools with parsers
  agent_core.py                  Connection management, command routing (49 handlers)
  agent_memory.py                Working memory (facts, hypotheses, evidence)
  evidence_chain.py              Cryptographic evidence provenance (audit trail)
  diagnosis_fingerprint.py       Pattern-based diagnosis recall (learning without ML)
  fleet_correlation.py           Cross-server symptom correlation engine
  session_handoff.py             Secure session transfer between technicians
  knowledge_base.py              MCA/PCIe decoders, firmware catalog, POST codes
  config.py                      Configuration management with security levels
  fleet_manager.py               Multi-server fleet management + health scoring
  realtime_monitor.py            WebSocket metric streaming (11 metrics)
  health_monitor.py              Automated health checks with alert callbacks
  health_scorer.py               Subsystem health scoring algorithms
  cache_manager.py               60-second Redfish response caching
  alert_system.py                Alert generation and severity classification
  automation_engine.py           Workflow automation
  analytics_engine.py            Fleet analytics and reporting
integrations/
  redfish_client.py              Async Redfish REST client (24 endpoints, $expand)
  racadm_client.py               RACADM CLI client
  ssh_client.py                  OS-level SSH connection with command whitelist
  simulated_redfish.py           Mock data for demo mode (PowerEdge R760)
  simulated_racadm.py            Mock data for demo mode
security/
  auth.py                        JWT auth, sessions, roles, encryption, lockout
models/
  server_models.py               Pydantic v2 data models (17 classes)
ai/
  predictive_analytics.py        Trend analysis, failure prediction
  predictive_maintenance.py      Maintenance scheduling
  troubleshooting_engine.py      Guided troubleshooting workflows
  log_analyzer.py                Log pattern analysis
templates/
  customer.html                  Customer AI chat page
  dashboard.html                 Technician dashboard (7 tabs, 108 buttons)
  fleet.html                     Fleet management (5 tabs)
  realtime.html                  Real-time monitoring dashboard
  login.html                     Authentication login page
  mobile.html                    Mobile-responsive view
static/
  css/customer.css               Customer chat styles (design system)
  css/style.css                  Technician dashboard styles (4400+ lines)
  js/customer.js                 Customer chat logic + SSE streaming
  js/app.js                      Technician dashboard logic (3700+ lines)
  js/fleet.js                    Fleet management logic (1800+ lines)
  js/realtime.js                 Real-time monitoring (WebSocket + polling)
tests/
  conftest.py                    Fixtures, markers, test config
  test_config.py                 26 tests -- config loading, security levels
  test_security.py               31 tests -- error sanitization, passwords, headers
  test_fleet_manager.py          33 tests -- fleet health scoring, alerts, groups
  test_api_auth.py               22 tests -- JWT login, RBAC, audit log
  test_api_endpoints.py          28 tests -- all API endpoints
  test_cache_manager.py          18 tests -- cache TTL, expiration
  test_health_scorer.py          15 tests -- health scoring algorithms
  test_predictive_analytics.py   15 tests -- trend analysis, failure prediction
```

## Key Commands
- **Run server:** `python main.py` or `python -m uvicorn main:app --host 0.0.0.0 --port 8000`
- **Demo mode:** Set `DEMO_MODE=true` in `.env`
- **Security level:** Set `SECURITY_LEVEL=high` in `.env` for full control

## Environment Variables
See `.env` for all options. Key ones:
- `DEMO_MODE` -- true/false, use simulated data
- `SECURITY_LEVEL` -- low (read-only) / medium (diagnostics) / high (full control)
- `LOG_LEVEL` -- DEBUG/INFO/WARNING/ERROR
- `SECRET_KEY` -- JWT signing key (change in production)
- `AUTH_ADMIN_PASSWORD` / `AUTH_OPERATOR_PASSWORD` / `AUTH_VIEWER_PASSWORD` -- override defaults
- `CORS_ORIGINS` -- comma-separated allowed origins (empty = allow all in dev)
- `VERIFY_SSL` -- false for self-signed iDRAC certs

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run unit tests (no server required) -- fast, ~6 seconds
python -m pytest tests/ -m "not integration" -v

# Run integration tests (requires server on port 8000)
RUN_INTEGRATION_TESTS=true python -m pytest tests/ -m "integration" -v

# Run ALL tests
RUN_INTEGRATION_TESTS=true python -m pytest tests/ -v

# Run specific test category
python -m pytest tests/test_config.py -v          # Configuration
python -m pytest tests/test_security.py -v         # Security features
python -m pytest tests/test_fleet_manager.py -v    # Fleet management
python -m pytest tests/test_api_auth.py -v         # Authentication API
python -m pytest tests/test_api_endpoints.py -v    # All API endpoints
```

### Test Markers
- `@pytest.mark.unit` -- no server required, pure logic tests
- `@pytest.mark.integration` -- requires live server at http://127.0.0.1:8000
- `@pytest.mark.slow` -- long-running tests
- `@pytest.mark.health` / `cache` / `predictive` -- category-specific

### Authentication (for integration tests)
Default credentials (override via env vars):
- admin / admin123 (full_control)
- operator / operator123 (diagnostic)
- viewer / viewer123 (read_only)

## Security Architecture

### Authentication Flow
1. User POSTs to `/api/auth/login` with `{username, password}`
2. Server validates credentials, returns JWT token + sets HTTP-only cookie
3. Subsequent API calls include `Authorization: Bearer <token>` header
4. Browser pages use the HTTP-only cookie (set with `SameSite=strict`)
5. WebSocket connections pass token as `?token=<jwt>` query parameter

### Authorization (RBAC)
| Role | Permissions | Can access |
|------|------------|-----------|
| `admin` | read_only, diagnostic, full_control | Everything including audit log, sessions |
| `operator` | read_only, diagnostic | Monitoring, diagnostics, but not power ops |
| `viewer` | read_only | View data only, no destructive operations |

### Security Middleware (applied to every request)
- **SecurityHeadersMiddleware**: CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- **RateLimitMiddleware**: per-IP limits (10/min on login, 60/min on execute, 120/min default)
- **_get_current_user()**: FastAPI dependency for JWT validation on protected endpoints

### Input Validation
- `_validate_host()` -- regex for hostnames/IPs, blocks path traversal and injection
- `_OS_COMMAND_WHITELIST` -- only whitelisted commands via `/api/os/execute`
- `custom_command` action restricted to admin role only
- `_sanitize_error()` -- strips file paths, stack traces, module names from client errors

### Audit Logging
Events tracked: LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, CONNECT_ATTEMPT, EXECUTE, BATCH_EXECUTE, OS_EXECUTE, OS_CMD_BLOCKED, RATE_LIMIT, WS_CONNECT, PASSWORD_CHANGE, MONITORING_START, MONITORING_STOP
- Each entry: timestamp, event type, source IP, username, detail
- Accessible via `GET /api/audit-log?limit=100` (admin only)
- In-memory ring buffer (last 10,000 events)

## Fleet Management

### Adding Servers
```bash
# Add a server
curl -X POST http://localhost:8000/api/fleet/servers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lab Server","host":"10.0.0.1","username":"root","password":"pass","port":443,"environment":"lab"}'
```

### Health Scoring
Health score (0-100%) computed from 5 subsystems:
- **Thermal**: max temperature vs thresholds (>85C = critical, >75C = warning)
- **Power**: % of PSUs with OK status
- **Memory**: % of populated DIMMs with OK status
- **Storage**: % of drives with OK status
- **System**: overall health from system info

Score updates on: server connect, fleet health check, monitoring cycle

### Alert Detection
Alerts generated for:
- Temperature > 85C (critical) or > 75C (warning)
- PSU status not OK/Enabled (critical)
- Alert history: last 1000 events, filterable by time and type

### Groups
Default groups: All Servers, Production, Critical, Development
Custom groups: create via API or fleet UI with server assignment

## Real-time Monitoring

### Starting Monitoring
```bash
# Connect to server first, then:
curl -X POST http://localhost:8000/monitoring/start \
  -H "Authorization: Bearer $TOKEN"
```

### Metrics Collected (every 30 seconds)
| Metric | Source | Thresholds |
|--------|--------|-----------|
| inlet_temp | Temperature sensors (inlet) | warn: 30C, crit: 35C |
| cpu_temp | Temperature sensors (CPU avg) | warn: 75C, crit: 85C |
| max_temp | Temperature sensors (max) | warn: 80C, crit: 90C |
| avg_fan_speed | Fan sensors (average RPM) | warn: 8000, crit: 10000 |
| power_consumption | PSU total watts | warn: 600W, crit: 750W |
| power_efficiency | % of healthy PSUs | warn: <80%, crit: <70% |
| memory_health | % of healthy DIMMs | warn: <80%, crit: <60% |
| storage_health | % of healthy drives | warn: <80%, crit: <60% |
| overall_health | Weighted composite | warn: <80%, crit: <60% |

### Data Flow
1. `realtime_monitor._collect_metrics()` queries Redfish every 30s
2. Parsed metrics stored in `MetricSeries` (100-point deque per metric)
3. WebSocket broadcasts `{"type":"metrics_update","metrics":{...}}` to all connected clients
4. Frontend updates metric cards, charts, and trend indicators
5. If WebSocket unavailable, frontend polls `/monitoring/metrics` every 10s

## Redfish Integration

### Verified Endpoints (24 against real server)
- System info, processors, memory, storage, network, firmware
- Temperature sensors, fans, power supplies
- System event logs, lifecycle logs
- BIOS attributes, boot order, jobs
- iDRAC network, users, certificate info
- $expand optimization for firmware (2x faster) and users (2.3x faster)
- Retry logic: GET requests retry once on 503/429/timeout

### Caching
- 60-second cache on all Redfish responses (configurable via `CACHE_RETENTION_HOURS`)
- Second request for same data returns in <5ms (vs 3-8 seconds uncached)
- Cache invalidated on write operations

## AI Chat System

### Intent Classification (17 intents)
- Greetings, help, thanks, about
- Quick info: model, RAM, BIOS version, power state, serial number
- Server overview (runs all core checks)
- Investigation (full ReAct reasoning loop)
- Specific checks: temperatures, firmware, boot order, logs, etc.
- Contextual follow-up: "is that a lot?" after RAM check

### Conversational Context
- Last 200 messages retained per session
- Follow-up awareness: "is that normal?" references previous tool result
- Intent matching uses 30+ keyword patterns with priority ordering

## Architecture
See `ARCHITECTURE.md` for the full design document including:
- ReAct reasoning loop details with confidence scoring
- Knowledge bases (MCA decoder, PCIe AER, firmware catalog, POST codes)
- Agent tools reference (15+ tools with Redfish endpoint mappings)
- Remediation safety model (action levels, approval gates)
- Business value metrics

---

## Design System

### Layout Tokens (`:root` in style.css)
| Token | Value | Usage |
|-------|-------|-------|
| `--sp-1` to `--sp-6`, `--sp-8` | 4-32px | All padding/margin/gap |
| `--radius-sm/md/lg/xl` | 6-12px | Border radius scale |
| `--grid-gap` | 10px | Grid gaps |
| `--content-padding` | 20px (12px mobile) | Tab content gutter |
| `--text-xs/sm/base/md/lg` | 0.72-1.05rem | Type scale |
| `--ease` | 0.15s ease | All transitions |

### Interaction States
All interactive elements must have: `:hover`, `:focus-visible`, `:active`, `:disabled` (buttons).
See "INTERACTION STATES" section in style.css (line ~3947).

### Error Handling
- User-facing errors: `showAlert(msg, type, {title, retry})`
- Catch blocks: `this._friendlyError(error)` for sanitization
- Preconditions: `this._requireConnection(action)` for unified messaging
