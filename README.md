# Medi-AI-tor

**AI-powered Dell server diagnostics that think like a senior support engineer.**

Medi-AI-tor connects to Dell iDRAC controllers via Redfish API, collects live telemetry, forms hypotheses about what's wrong, gathers evidence, and arrives at a root-cause diagnosis with an evidence chain — in ~30 seconds instead of 45+ minutes.

> Built for the Dell Technologies Hackathon 2026. Tested against a live Dell PowerScale F710 (Service Tag 3KQ38Y3).

---

## Key Features

| Feature | Description |
|---------|-------------|
| **AI Diagnostics** | ReAct reasoning loop: hypothesize, investigate, diagnose — 17 intents, 90%+ confidence on real failures |
| **Customer Chat** | Natural language interface with SSE live-thinking animation |
| **Technician Dashboard** | 7 tabs, 108 operation buttons, data freshness timestamps, 60-second auto-refresh |
| **Fleet Management** | Multi-server monitoring, health scoring, alert aggregation, group management |
| **Real-time Monitoring** | WebSocket metric streaming (temps, fans, power, health) with 30-second collection |
| **Security** | JWT authentication, 3 roles (admin/operator/viewer), rate limiting, audit logging |
| **188 Automated Tests** | Unit + integration tests across config, security, fleet, API, and predictive analytics |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
pip install PyJWT cryptography  # For authentication

# Configure (optional — works out of the box)
cp .env.example .env  # Edit DEMO_MODE=true for no-server testing

# Run
python main.py
# Open http://localhost:8000
```

### Default Login Credentials
| Role | Username | Password | Permissions |
|------|----------|----------|-------------|
| Admin | `admin` | `admin123` | Full control |
| Operator | `operator` | `operator123` | Read + diagnostics |
| Viewer | `viewer` | `viewer123` | Read only |

Override via environment: `AUTH_ADMIN_PASSWORD=your-strong-password`

## Pages

| URL | Page | Auth Required |
|-----|------|---------------|
| `/` | Customer AI Chat | No |
| `/login` | Login | No |
| `/technician` | Technician Dashboard | Yes (redirects to /login) |
| `/fleet` | Fleet Management | No (API calls require auth) |
| `/monitoring` | Real-time Monitoring | No (API calls require auth) |

## Architecture

```
Browser ─── SSE/WebSocket ──┐
                             │
         Python / FastAPI Backend
         ┌───────────────────────────────────────┐
         │  AgentBrain (ReAct Reasoning Loop)     │
         │  Hypothesize → Tool → Observe → Update │
         │                                         │
         │  Working Memory   Knowledge Base        │
         │  (Facts, Hyps,    (MCA, PCIe,           │
         │   Evidence)        Firmware, POST)       │
         │                                         │
         │  15+ Diagnostic Tools                   │
         │  Auth (JWT) │ Rate Limiting │ Audit Log │
         └──────────────────┬──────────────────────┘
                            │ HTTPS (Redfish REST API)
         ┌──────────────────▼──────────────────────┐
         │  Dell PowerEdge Server (iDRAC)           │
         │  Sensors, Logs, Firmware, BIOS            │
         └──────────────────────────────────────────┘
```

**No LLM. No cloud API. No external dependency.** The intelligence is a purpose-built reasoning engine encoding how Dell engineers troubleshoot.

## How It Works

When a user says *"Server is overheating and fans are loud"*:

1. **Hypothesize**: Map to candidates — `thermal_issue` (0.6), `fan_failure` (0.5)
2. **Investigate**: Run `check_temperatures` via Redfish → 7 sensors, inlet 77°C
3. **Update**: `thermal_issue` → 0.85 (strong evidence)
4. **Investigate**: Run `check_fans` → 16 fans healthy → `fan_failure` → 0.15 (ruled out)
5. **Conclude**: Thermal issue, 90% confidence, with evidence chain and remediation plan

**Total: ~30 seconds. Manual: 30-60 minutes.**

## API Reference

All API endpoints require JWT authentication (except public pages and `/api/health`).

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Use the returned token
TOKEN="eyJhbG..."

# Connect to server
curl -X POST http://localhost:8000/api/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"host":"192.168.1.100","username":"root","password":"calvin","port":443}'

# Execute command
curl -X POST http://localhost:8000/api/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"health_check","action_level":"read_only","parameters":{}}'

# Batch execute (multiple commands)
curl -X POST http://localhost:8000/api/execute/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"commands":[{"action":"get_server_info"},{"action":"health_check"}]}'

# AI Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"check temperatures","action_level":"read_only"}'
```

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Authenticate, returns JWT |
| POST | `/api/auth/logout` | Invalidate session |
| GET | `/api/auth/me` | Current user info |
| POST | `/api/connect` | Connect to Dell server |
| POST | `/api/execute` | Execute single command |
| POST | `/api/execute/batch` | Execute multiple commands |
| POST | `/api/chat/stream` | SSE streaming AI chat |
| GET | `/api/fleet/overview` | Fleet status + health scores |
| POST | `/api/fleet/servers` | Add server to fleet |
| POST | `/api/fleet/health-check` | Run fleet-wide health check |
| POST | `/monitoring/start` | Start real-time monitoring |
| GET | `/monitoring/metrics` | Current metric snapshot |
| GET | `/api/audit-log` | Audit trail (admin only) |
| GET | `/api/health` | Server health check (public) |

## Security

| Feature | Implementation |
|---------|---------------|
| **Authentication** | JWT tokens via `Authorization: Bearer` header + HTTP-only cookies |
| **Authorization** | 3 roles: admin (full_control), operator (diagnostic), viewer (read_only) |
| **Rate Limiting** | Per-IP: 10/min on login, 60/min on execute, 120/min default |
| **Security Headers** | CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, X-XSS-Protection |
| **CORS** | Configurable via `CORS_ORIGINS` env var (wildcard in dev only) |
| **Error Sanitization** | Internal details stripped from client responses, logged server-side |
| **Input Validation** | Hostname regex, OS command whitelist, action level enforcement |
| **Audit Logging** | All sensitive operations logged with timestamp, IP, user, action |
| **Credential Protection** | Passwords never in localStorage, never in API responses, never logged |
| **Account Lockout** | 5 failed attempts = 15-minute lockout |

## Testing

```bash
# Unit tests (no server required, ~6 seconds)
python -m pytest tests/ -m "not integration" -v

# Integration tests (requires running server, ~6 minutes)
RUN_INTEGRATION_TESTS=true python -m pytest tests/ -m "integration" -v
```

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_config.py` | 26 | Config defaults, env loading, action permissions |
| `test_security.py` | 31 | Error sanitization, host validation, passwords, encryption, headers |
| `test_fleet_manager.py` | 33 | Add/connect/health scoring/alerts/groups |
| `test_api_auth.py` | 22 | JWT login, RBAC, logout, unauthenticated blocking |
| `test_api_endpoints.py` | 28 | Page routes, connection, execute, fleet, audit |
| `test_cache_manager.py` | 18 | Cache TTL, expiration, invalidation |
| `test_health_scorer.py` | 15 | Health scoring algorithms |
| `test_predictive_analytics.py` | 15 | Trend analysis, failure prediction |
| **Total** | **188** | **100% pass rate** |

## Environment Variables

```bash
# Server
SERVER_HOST=127.0.0.1
SERVER_PORT=8000

# Security
SECURITY_LEVEL=high              # low/medium/high
SECRET_KEY=change-this-secret-key
AUTH_ADMIN_PASSWORD=              # Override default admin password
CORS_ORIGINS=                    # Comma-separated origins (empty = allow all in dev)

# Redfish
REDFISH_PORT=443
CONNECTION_TIMEOUT=30
VERIFY_SSL=false                 # false for self-signed iDRAC certs

# Demo mode (no real server needed)
DEMO_MODE=false

# Logging
LOG_LEVEL=INFO
```

## Project Structure

```
main.py                          FastAPI server, 70+ endpoints, auth middleware
core/
  agent_brain.py                 ReAct reasoning engine (2845 lines)
  agent_tools.py                 20+ diagnostic tool parsers
  agent_core.py                  Connection management, 49 command handlers
  agent_memory.py                Working memory (facts, hypotheses, evidence)
  config.py                      Configuration with security levels
  fleet_manager.py               Multi-server fleet management + health scoring
  realtime_monitor.py            WebSocket metric streaming
  health_monitor.py              Automated health checks with alerts
  health_scorer.py               Subsystem health scoring algorithms
  cache_manager.py               60-second Redfish response cache
  knowledge_base.py              MCA/PCIe decoders, firmware catalog
integrations/
  redfish_client.py              Async Redfish client (24 endpoints, $expand optimization)
  ssh_client.py                  OS-level SSH with command whitelist
  simulated_redfish.py           Demo mode mock data
security/
  auth.py                        JWT, sessions, roles, encryption, lockout
models/
  server_models.py               Pydantic data models (17 classes)
templates/
  customer.html                  Customer AI chat page
  dashboard.html                 Technician dashboard (7 tabs, 108 buttons)
  fleet.html                     Fleet management (5 tabs)
  realtime.html                  Real-time monitoring dashboard
  login.html                     Authentication login page
  mobile.html                    Mobile-responsive view
tests/
  8 test files                   188 tests (124 unit + 54 integration + 10 existing)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Server Communication | Redfish REST API (HTTPS) |
| Authentication | PyJWT + cryptography (Fernet) |
| Frontend | Vanilla JS + CSS (zero build step) |
| Data Models | Pydantic v2 |
| HTTP Client | aiohttp (async) |
| Testing | pytest + pytest-asyncio + httpx |
| State | In-memory (no database required) |

## Real Server Test Results

Tested against Dell PowerScale F710 (iDRAC 100.71.148.195):

| Subsystem | Result |
|-----------|--------|
| Processors | 2x Intel Xeon Gold 6442Y (48C/96T each) |
| Memory | 512 GB DDR5 (16 DIMMs, all healthy) |
| Storage | 11x Samsung 3.84TB NVMe SSDs |
| Power | PSU.Slot.1 Critical (UnavailableOffline) -- detected and alerted |
| Temperatures | 11 sensors, inlet 34°C, max 85°C |
| Fleet Health Score | 79.0% (PSU failure dragging it down) |
| Monitoring | Real-time: 50% power efficiency, 100% memory/storage health |

---

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design document and reasoning engine details.

See [AGENTS.md](AGENTS.md) for developer guide, testing instructions, and security documentation.
