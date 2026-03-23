# Medi-AI-tor — Architecture & Design Document

## Table of Contents
1. [What is Medi-AI-tor?](#what-is-medi-ai-tor)
2. [Frequently Asked Questions](#frequently-asked-questions)
3. [Architecture Overview](#architecture-overview)
4. [Tech Stack](#tech-stack)
5. [How the Agent Reasons](#how-the-agent-reasons)
6. [Agent Tools](#agent-tools)
7. [Knowledge Bases](#knowledge-bases)
8. [Chat System](#chat-system)
9. [Remediation & Safety](#remediation--safety)
10. [Data Flow Example](#data-flow-example)
11. [Business Value](#business-value)
12. [Security Architecture](#security-architecture)
13. [Fleet Management Architecture](#fleet-management-architecture)
14. [Real-time Monitoring Architecture](#real-time-monitoring-architecture)
15. [Testing Architecture](#testing-architecture)

---

## What is Medi-AI-tor?

Medi-AI-tor is an **AI agent that diagnoses Dell PowerEdge server problems the way a senior support engineer would** — it connects to the server's iDRAC management controller, collects live telemetry, forms hypotheses about what's wrong, gathers evidence to test each one, and arrives at a root-cause diagnosis with an evidence chain. It does this in ~30 seconds instead of the 45+ minutes it takes a human.

It is **not** an LLM chatbot. There is no GPT, no Gemini, no cloud AI service. The intelligence is a **purpose-built reasoning engine** written in Python that encodes how Dell engineers actually troubleshoot — hypothesis-driven investigation with tool-assisted evidence gathering.

---

## Frequently Asked Questions

### "What AI agent is this? What model does it use?"

Medi-AI-tor is a **custom-built agentic reasoning engine** — not a wrapper around a large language model. It uses:

- A **ReAct (Reason + Act) loop** — the agent forms hypotheses, selects diagnostic tools, observes results, updates confidence scores, and iterates until it reaches a conclusion. This is the same reasoning pattern used by state-of-the-art AI agents, implemented as deterministic Python logic with domain-specific heuristics.
- A **hypothesis catalog** mapping ~20 failure modes (thermal, memory, storage, firmware, PCIe, MCA, etc.) to investigation strategies.
- **Hardware-specific knowledge bases** — MCA bank decoders, PCIe AER error tables, Dell firmware catalogs, BIOS best-practice rules, POST code lookup tables.
- **15+ structured diagnostic tools** that query the server via Redfish API and parse responses into structured facts.

There is **no external API dependency**. The agent runs entirely locally on the Python backend.

### "How does it query the server? Where does the data come from?"

All data comes directly from the **Dell iDRAC management controller** via the industry-standard **Redfish REST API** (DMTF standard, HTTPS). The agent makes async HTTPS requests to endpoints like `/redfish/v1/Systems/`, `/Chassis/Thermal`, `/UpdateService/FirmwareInventory`, parses the JSON responses, and converts them into structured `Fact` objects that feed the reasoning loop. It also supports **RACADM over SSH** as a fallback for older iDRAC versions. No data is stored permanently. No data leaves the local network.

### "Why is this better than just using iDRAC directly?"

iDRAC is a **data source** — it shows raw sensor readings, log entries, and hardware inventory. You still need a human to know which endpoints to check, interpret hundreds of values, cross-correlate across subsystems, and form a diagnosis.

| Capability | iDRAC Web UI | Medi-AI-tor |
|-----------|-------------|------------|
| View temperature sensors | ✅ Manual navigation | ✅ Auto-collected + threshold analysis |
| Cross-correlate thermal + fan + power | ❌ Manual | ✅ Automatic reasoning across subsystems |
| Decode MCA/MCE errors | ❌ Raw hex codes | ✅ Decoded to component + severity + action |
| Decode PCIe AER errors | ❌ Raw error codes | ✅ Mapped to root cause + corrective action |
| Compare firmware to Dell catalog | ❌ Manual lookup | ✅ Automatic with download links |
| Audit BIOS settings | ❌ Manual review of 200+ attributes | ✅ Flags non-optimal C-States/boot mode/TPM |
| Diagnose root cause with evidence | ❌ Requires engineer skill | ✅ Hypothesis-driven with confidence scores |
| Propose + execute remediation | ❌ Manual | ✅ With human-in-the-loop approval gate |
| Natural language interaction | ❌ | ✅ Chat-based, plain English |
| Time to diagnosis | 30–60 minutes | ~30 seconds |

**The analogy: iDRAC is a thermometer. Medi-AI-tor is the doctor.**

### "Is it making changes to the server?"

By default, **no**. The system has three action levels:

| Level | What it can do | Risk |
|-------|---------------|------|
| **Read Only** (default) | Query sensors, read logs, check firmware | Zero — pure observation |
| **Diagnostic** | Run ePSA diagnostics, export TSR | Low — non-destructive tests |
| **Full Control** | Reboot, change BIOS, push firmware | High — requires explicit approval |

Even at Full Control, destructive actions require a **human approval gate** — the agent proposes a plan, shows safe vs. risky steps, and waits for the user to click Approve before executing anything.

### "What about security?"

- **Credentials stay in-memory** — never written to disk or logged
- **All communication is HTTPS** to the iDRAC (standard Redfish)
- **No external API calls** — the agent runs 100% locally
- **No data persistence** — working memory is cleared between sessions
- **Three-tier permission model** with explicit approval for destructive actions

### "Does this work with any Dell server?"

Yes — any Dell PowerEdge with iDRAC and Redfish API enabled (12th generation and newer). Tested on R660, R760, R650, R750.

### "How is this different from Dell SupportAssist?"

SupportAssist **collects** data and sends it to Dell. Medi-AI-tor **reasons** about the data — it forms hypotheses, rules out wrong paths, diagnoses root cause with evidence, proposes fixes, and can execute them with approval. It's the difference between a lab test and a doctor.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BROWSER (Two Views)                          │
│  ┌──────────────────────┐   ┌──────────────────────────────────┐   │
│  │  Customer Chat (/)   │   │  Technician Dashboard            │   │
│  │  Natural language     │   │  (/technician)                   │   │
│  │  + SSE live thinking  │   │  Hardware deep-dive, logs, ops   │   │
│  └─────────┬────────────┘   └──────────────┬───────────────────┘   │
└────────────┼────────────────────────────────┼──────────────────────┘
             │                                │
┌────────────▼────────────────────────────────▼──────────────────────┐
│                    Python / FastAPI Backend                         │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                AgentBrain — ReAct Reasoning Loop             │   │
│  │   Hypothesize → Select Tool → Execute → Observe → Update    │   │
│  │        ↑                                        │            │   │
│  │        └──────────── Loop (up to 12 steps) ─────┘            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────────┐   │
│  │ Working      │ │ Knowledge    │ │ 15+ Diagnostic Tools      │   │
│  │ Memory       │ │ Base         │ │ (Thermal, Memory, Storage, │   │
│  │ (Facts,      │ │ (MCA, PCIe,  │ │  Network, Firmware, BIOS, │   │
│  │  Hypotheses, │ │  Firmware,   │ │  Logs, Boot, Jobs, SSL,   │   │
│  │  Evidence)   │ │  POST codes) │ │  iDRAC, Lifecycle, TSR)   │   │
│  └──────────────┘ └──────────────┘ └───────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────┐                  │
│  │     DellAIAgent — Connection & Command Router │                  │
│  └────────────────────┬─────────────────────────┘                  │
└───────────────────────┼─────────────────────────────────────────────┘
                        │ HTTPS (Redfish REST API)
┌───────────────────────▼─────────────────────────────────────────────┐
│                    Dell PowerEdge Server                             │
│         iDRAC Controller — Sensors, Logs, Firmware, BIOS            │
└─────────────────────────────────────────────────────────────────────┘
```

### Two Interfaces, One Brain

| View | URL | Audience | Purpose |
|------|-----|----------|---------|
| **Customer Chat** | `/` | End-user / App owner | Describe problem in plain English, get a diagnosis |
| **Technician Dashboard** | `/technician` | Dell support / Field tech | Full hardware deep-dive with actionable controls |

Both share the same `AgentBrain` instance — same reasoning engine, same working memory.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend** | Python 3.11+ / FastAPI | Async, fast, native SSE streaming support |
| **Server Comm** | Redfish REST API (HTTPS) | Industry standard, works on all modern iDRAC |
| **Fallback** | RACADM (SSH) | Older iDRAC compatibility |
| **Frontend** | Vanilla JS + CSS | Zero dependencies, instant load, no build step |
| **Data Models** | Pydantic v2 | Type-safe request/response validation |
| **HTTP Client** | aiohttp | Async concurrent Redfish calls |
| **State** | In-memory only | No database needed, no persistence, no cloud |

### Key Files

```
main.py                        → FastAPI server, all endpoints
core/agent_brain.py            → ReAct reasoning loop + chat system
core/agent_tools.py            → 15+ tool definitions + Redfish parsers
core/agent_core.py             → Connection management, command routing
core/knowledge_base.py         → MCA/PCIe decoders, firmware catalog
core/agent_memory.py           → Working memory, hypotheses, evidence
integrations/redfish_client.py → Async Redfish REST client
templates/customer.html        → Customer chat page
templates/dashboard.html       → Technician dashboard
static/js/app.js               → Technician frontend (2700+ lines)
static/js/customer.js          → Customer frontend with SSE streaming
```

---

## How the Agent Reasons

When a user says *"Server is overheating and fans are loud"*:

**Step 1 — Hypothesize**: Map keywords to candidate root causes:
- `thermal_issue` (confidence: 0.6) — "overheating" keyword
- `fan_failure` (confidence: 0.5) — "fans" keyword
- `power_issue` (confidence: 0.3) — secondary possibility

**Step 2 — Investigate** (ReAct loop):
1. **Think**: "Thermal is highest confidence. Need temperature data."
2. **Act**: Execute `check_temperatures` → Redfish `/Chassis/Thermal`
3. **Observe**: 7 sensors, max 77°C at inlet → **strong thermal evidence**
4. **Update**: `thermal_issue` → 0.85, `fan_failure` → 0.6
5. **Think**: "Need fan data to distinguish thermal from fan failure."
6. **Act**: Execute `check_fans`
7. **Observe**: 16 fans, all healthy, avg 7200 RPM → **fans are fine**
8. **Update**: `fan_failure` → 0.15 (rule out), `thermal_issue` → 0.90 (confirmed)

**Step 3 — Conclude**: Root cause = thermal issue (90% confidence). Evidence: elevated inlet temp, healthy fans, thermal log warnings. Remediation: check airflow, clean filters.

**Total time: ~30 seconds. Manual equivalent: 30–60 minutes.**

### Confidence Updates

- **Strong supporting evidence**: +0.25 (e.g., temp > 80°C for thermal hypothesis)
- **Moderate supporting**: +0.15
- **Weak refuting**: -0.10
- **Strong refuting**: -0.30 (e.g., all temps normal for thermal hypothesis)
- **Convergence**: hypothesis reaches ≥ 0.85, or all others ruled out, or max 12 steps

---

## Agent Tools

15+ diagnostic tools, each mapping to a Redfish endpoint with a structured parser:

| Tool | What it Analyzes |
|------|-----------------|
| `check_system_info` | Model, service tag, CPU, RAM, power state |
| `check_temperatures` | All temp sensors vs. thresholds |
| `check_fans` | Fan RPMs, failures |
| `check_power` | PSU status, wattage |
| `check_memory` | DIMM status, ECC errors |
| `check_storage` | Drive health, RAID status |
| `check_network` | NIC link state, speed |
| `collect_logs` | System Event Log + automatic MCA/PCIe decoding |
| `check_firmware` | Installed versions vs. Dell catalog, with download links |
| `check_bios` | Non-optimal settings (C-States, boot mode, TPM, turbo) |
| `check_boot_order` | Boot sequence, UEFI target |
| `check_idrac_network` | iDRAC IP, DNS, VLAN config |
| `check_idrac_users` | User accounts, privileges |
| `check_lifecycle` | Lifecycle controller status |
| `check_jobs` | iDRAC job queue, pending tasks |
| `check_idrac_cert` | SSL certificate expiry |
| `check_post_codes` | POST code decoder for no-POST troubleshooting |
| `collect_tsr` | SupportAssist TSR collection with job tracking |

Each parser converts raw Redfish JSON into structured `Fact` objects with status (ok / warning / critical).

---

## Knowledge Bases

### MCA (Machine Check Architecture) Decoder
Decodes Intel CPU error registers into human-readable diagnoses. Maps MCA banks 0–13 to components (I-cache, D-cache, L2 cache, memory controller) and MCACOD patterns to error types, severity, and Dell remediation workflows. **This is L3-engineer knowledge, automated.**

### PCIe AER Decoder
Maps PCIe fatal/non-fatal error codes to root causes and corrective actions. Covers 13 fatal types (Data Link Protocol Error, Surprise Down, Completion Timeout, Malformed TLP, etc.) and 8 correctable types.

### Dell Firmware Catalog
Latest known-good versions for BIOS, iDRAC, NIC, RAID, Drive, CPLD per PowerEdge generation. Flags critical updates with direct Dell support download links.

### POST Code Decoder
Maps Dell POST progress codes to failure stages and corrective actions for no-POST troubleshooting.

---

## Chat System

The agent handles **20+ conversational intents** via keyword matching with priority ordering:

| Category | Examples |
|----------|---------|
| **Quick Info** | "What model is this?", "How much RAM?", "BIOS version?", "Power state?" |
| **Server Overview** | "Give me an overview" → runs all core checks, builds summary |
| **Investigation** | "Server is overheating" → full ReAct reasoning loop with SSE streaming |
| **Dig Deeper** | "Check temperatures", "Show boot order", "Check firmware", "Show job queue" |
| **Remediation** | "Can you fix this?" → proposes plan with approval gate |
| **Explanation** | "Why do you think that?" → shows evidence chain |
| **Operations** | "Collect TSR", "Dispatch a part", "Monitor the server" |

### SSE Live Thinking

The customer page uses Server-Sent Events to stream the agent's reasoning in real time — each tool execution, hypothesis update, and finding appears as an animated panel element with confidence bars and color-coded badges.

---

## Remediation & Safety

1. **Action levels** gate what's available: Read Only → Diagnostic → Full Control
2. **Remediation proposals** separate safe steps (collect TSR) from risky steps (reboot, BIOS change)
3. **Human approval gate** — user sees the plan, clicks Approve or Cancel
4. **Built-in workflows**: thermal remediation, memory replacement, firmware update, PCIe reseat, BIOS settings change, no-POST troubleshooting, part dispatch, TSR collection

---

## Data Flow Example

```
User: "Server is overheating and fans are loud"
  ↓
POST /chat/stream → AgentBrain.investigate()
  ↓
1. Form hypotheses: thermal_issue (0.6), fan_failure (0.5), power_issue (0.3)
2. Run check_temperatures → 7 sensors, inlet 77°C → thermal_issue → 0.85
3. Run check_fans → 16 fans healthy, avg 7200 RPM → fan_failure → 0.15
4. Conclude: thermal issue (90% confidence)
  ↓
Return diagnosis + evidence chain + remediation plan
  ↓
Frontend: live thinking animation → diagnosis card → business metrics
```

---

## Business Value

| Metric | Value |
|--------|-------|
| **Investigation time** | ~30 seconds (vs. 45 min manual) |
| **Cost savings** | $22K+ per incident (downtime + labor + truck roll) |
| **Escalation avoidance** | High-confidence diagnosis at the edge, no L3 wait |
| **Data points per investigation** | 40–100+ facts across all subsystems |
| **MCA/PCIe decoding** | Eliminates L3 engineer dependency for complex errors |
| **Firmware compliance** | Instant fleet-wide audit with download links |
| **Full lifecycle** | Investigate → Diagnose → Remediate → Monitor → Dispatch |

---

*Built for Dell Technologies Hackathon 2026*
*Medi-AI-tor -- AI-powered server diagnostics that think like an engineer*

---

## Security Architecture

### Authentication & Authorization
```
Browser → POST /api/auth/login {username, password}
  → AuthManager.authenticate()
  → JWT token + HTTP-only SameSite cookie
  → All subsequent API calls: Authorization: Bearer <token>
  → WebSocket: ?token=<jwt> query parameter
```

Three roles with cascading permissions:
- **admin**: read_only + diagnostic + full_control + audit log + session management
- **operator**: read_only + diagnostic
- **viewer**: read_only

### Security Middleware Stack
Every request passes through:
1. **RateLimitMiddleware** — per-IP rate limiting (10-120 req/min depending on endpoint)
2. **CORSMiddleware** — configurable origins (wildcard only in development)
3. **SecurityHeadersMiddleware** — CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff

### Credential Protection
- iDRAC passwords: never in localStorage, never in API responses, never logged
- Fleet server passwords: stored in memory only, excluded from `to_dict()` serialization
- OS command execution: whitelist-based, `custom_command` requires admin role

---

## Fleet Management Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Fleet Manager (core/fleet_manager.py)                   │
│  ┌───────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ ServerInfo │  │ ServerGroup  │  │ ActiveConnections│  │
│  │ (per host) │  │ (named sets) │  │ (Redfish clients)│  │
│  └─────┬─────┘  └──────────────┘  └────────┬────────┘  │
│        │                                     │           │
│  Health Scoring ←── _collect_server_metrics ──┘           │
│  (thermal + power + memory + storage + system)            │
│        │                                                  │
│  Alert Detection ←── _check_server_alerts                 │
│  (temp thresholds + PSU status)                           │
│        │                                                  │
│  Fleet Overview ←── get_fleet_overview                    │
│  (aggregated stats + per-server health)                   │
└─────────────────────────────────────────────────────────┘
```

Health score computation: 5 subsystem scores averaged (0-100%):
- Thermal: 100 if max_temp < 65C, 80 if < 75C, 60 if < 85C, 20 if >= 85C
- Power: (healthy PSUs / total PSUs) * 100
- Memory: (healthy DIMMs / populated DIMMs) * 100
- Storage: (healthy drives / total drives) * 100
- System: 100 if OK, 70 if Warning, 30 if Critical

---

## Real-time Monitoring Architecture

```
┌─────────────────────────────────────────────────────────┐
│  RealtimeMonitor (core/realtime_monitor.py)               │
│                                                           │
│  _monitoring_loop (every 30 seconds):                     │
│    1. _collect_metrics() → Redfish API queries            │
│    2. _update_metric() → MetricSeries + threshold check   │
│    3. _broadcast_updates() → WebSocket to all clients     │
│                                                           │
│  11 Metrics: inlet_temp, cpu_temp, max_temp,              │
│    avg_fan_speed, max_fan_speed, power_consumption,       │
│    power_efficiency, memory_health, storage_health,       │
│    overall_health                                         │
│                                                           │
│  MetricSeries: 100-point deque per metric                 │
│    → trend calculation (linear regression)                │
│    → 10-min avg/max/min                                   │
│    → status: normal/warning/critical                      │
└─────────────────────────────────────────────────────────┘
```

Frontend fallback: if WebSocket fails after 5 retries, the monitoring page polls `/monitoring/metrics` every 10 seconds.

---

## Testing Architecture

```
tests/
├── conftest.py              Shared fixtures (sample data, mock clients)
├── test_config.py           26 unit tests — config loading, permissions
├── test_security.py         31 tests — 25 unit + 6 integration
├── test_fleet_manager.py    33 unit tests — fleet operations
├── test_api_auth.py         22 integration tests — auth flow
├── test_api_endpoints.py    28 integration tests — all endpoints
├── test_cache_manager.py    18 unit tests — caching
├── test_health_scorer.py    15 unit tests — scoring
└── test_predictive_analytics.py  15 unit tests — prediction
```

Total: 188 tests (124 unit + 54 integration + 10 existing), 100% pass rate.

Run: `python -m pytest tests/ -m "not integration" -v` (unit, ~6 seconds)
Run: `RUN_INTEGRATION_TESTS=true python -m pytest tests/ -m "integration" -v` (requires server)
