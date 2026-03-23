# Medi-AI-tor — Development Guide

## Quick Start
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set DEMO_MODE=true for development without a server
python main.py
# Open http://localhost:8000
```

## Project Structure
```
main.py                          FastAPI server, all endpoints
core/
  agent_brain.py                 ReAct reasoning engine + chat system
  agent_tools.py                 15+ diagnostic tools with parsers
  agent_core.py                  Connection management, command routing
  agent_memory.py                Working memory (facts, hypotheses, evidence)
  knowledge_base.py              MCA/PCIe decoders, firmware catalog
  config.py                      Configuration management
  fleet_manager.py               Multi-server fleet management
  health_scorer.py               Health score calculation
  cache_manager.py               Redfish response caching
integrations/
  redfish_client.py              Async Redfish REST client
  racadm_client.py               RACADM CLI client
  simulated_redfish.py           Mock data for demo mode
  simulated_racadm.py            Mock data for demo mode
  ssh_client.py                  OS-level SSH connection
templates/
  customer.html                  Customer chat page
  dashboard.html                 Technician dashboard
  fleet.html                     Fleet management
static/
  css/customer.css               Customer chat styles
  css/style.css                  Technician dashboard styles
  js/customer.js                 Customer chat logic
  js/app.js                      Technician dashboard logic
  js/fleet.js                    Fleet management logic
```

## Key Commands
- **Run server:** `python -m uvicorn main:app --host 0.0.0.0 --port 8000`
- **Demo mode:** Set `DEMO_MODE=true` in `.env`
- **Security level:** Set `SECURITY_LEVEL=high` in `.env` for full control

## Environment Variables
See `.env.example` for all options. Key ones:
- `DEMO_MODE` — true/false, use simulated data
- `SECURITY_LEVEL` — low/medium/high
- `LOG_LEVEL` — DEBUG/INFO/WARNING/ERROR

## Testing Against Real Server
- iDRAC IP: configured at connection time via UI
- Default port: 443 (Redfish over HTTPS)
- Credentials: entered in the connection form (never stored on disk)

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run unit tests (no server required) — fast, ~6 seconds
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

### Test Structure
```
tests/
  conftest.py                 Fixtures, markers, test config
  test_config.py              26 tests — config loading, security levels, permissions
  test_security.py            31 tests — error sanitization, host validation, passwords, headers
  test_fleet_manager.py       33 tests — fleet add/connect/health/alerts/groups
  test_api_auth.py            22 tests — JWT login, RBAC, logout, unauthenticated blocking
  test_api_endpoints.py       28 tests — page routes, connection, execute, fleet, audit
  test_cache_manager.py       18 tests — cache TTL, expiration, invalidation
  test_health_scorer.py       15 tests — health scoring algorithms
  test_predictive_analytics.py 15 tests — trend analysis, failure prediction
```

### Authentication (for integration tests)
Default credentials (override via env vars):
- admin / admin123 (full_control)
- operator / operator123 (diagnostic)
- viewer / viewer123 (read_only)

## Architecture
See `ARCHITECTURE.md` for the full design document.
