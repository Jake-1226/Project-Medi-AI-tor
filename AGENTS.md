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

## Architecture
See `ARCHITECTURE.md` for the full design document.
