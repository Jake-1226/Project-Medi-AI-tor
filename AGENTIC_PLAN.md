# Agentic Architecture Plan — Project Medi-AI-tor

## The Gap: Tool vs Agent

### What we have now (Tool)
```
Human → "server overheating" → Fixed Pipeline → Report
                                    │
                                    ├─ collect temps
                                    ├─ collect fans
                                    ├─ collect logs
                                    ├─ pattern match
                                    └─ return static report
```

Every troubleshooting run does the **same steps regardless of what it finds**.
The analysis is post-hoc — it collects everything, then summarizes.
There's no reasoning loop, no branching, no "I found X so now I should check Y."

### What we need (Agent)
```
Human → "server overheating"
          │
          ▼
    ┌─────────────┐
    │  AGENT LOOP  │◄──────────────────────────┐
    └──────┬──────┘                             │
           │                                    │
     ┌─────▼─────┐                              │
     │   THINK   │  "What do I know? What       │
     │           │   should I investigate next?" │
     └─────┬─────┘                              │
           │                                    │
     ┌─────▼─────┐                              │
     │    ACT    │  Execute ONE targeted action  │
     │           │  (check temps, pull SEL, etc) │
     └─────┬─────┘                              │
           │                                    │
     ┌─────▼─────┐                              │
     │  OBSERVE  │  Parse results, update        │
     │           │  working memory               │
     └─────┬─────┘                              │
           │                                    │
     ┌─────▼─────┐     ┌──────┐                 │
     │  DECIDE   │────►│ MORE │─────────────────┘
     │           │     │ INFO │
     └─────┬─────┘     └──────┘
           │
     ┌─────▼─────┐
     │ CONCLUDE  │  Diagnosis + Plan + Ask permission
     └───────────┘
```

The agent REASONS about what to do next based on what it already found.
It BRANCHES — if temps are fine, it doesn't waste time on thermal workflows.
It CHAINS — if logs mention DIMM A3, it specifically pulls A3 details.
It STOPS when it has enough evidence, not after a fixed checklist.

---

## Architecture — 4 Layers

### Layer 1: Agent Brain (NEW — `core/agent_brain.py`)

The reasoning engine. This is the core agentic component.

```python
class AgentBrain:
    """
    ReAct-style reasoning loop for server troubleshooting.
    Think → Act → Observe → Decide → (loop or conclude)
    """
    
    def __init__(self, agent: DellAIAgent, config: AgentConfig):
        self.agent = agent           # hardware interface
        self.working_memory = {}     # what the agent knows NOW
        self.thought_chain = []      # reasoning trace (visible to user)
        self.actions_taken = []      # audit trail
        self.hypothesis_stack = []   # ranked hypotheses
        self.max_steps = 15          # safety: don't loop forever
    
    async def investigate(self, issue: str, action_level: ActionLevel) -> AgentReport:
        """Main agentic loop — stream results to frontend via WebSocket"""
        
        # Step 0: Parse the issue, form initial hypotheses
        self.thought_chain.append(Thought(
            step=0,
            reasoning="Parsing issue description, forming initial hypotheses",
            hypotheses=self._form_initial_hypotheses(issue)
        ))
        
        for step in range(1, self.max_steps + 1):
            # THINK: What do I know? What's my top hypothesis? What would confirm/deny it?
            thought = self._think(step)
            self.thought_chain.append(thought)
            await self._stream_thought(thought)  # live to frontend
            
            if thought.conclusion:
                break  # Agent decided it has enough evidence
            
            # ACT: Execute the next best action
            action = thought.next_action
            result = await self._execute(action)
            self.actions_taken.append(action)
            await self._stream_action(action, result)
            
            # OBSERVE: Parse the result, extract findings
            findings = self._observe(action, result)
            self.working_memory.update(findings)
            await self._stream_findings(findings)
            
            # DECIDE: Update hypotheses, decide if more info needed
            self._update_hypotheses(findings)
        
        # CONCLUDE: Build final diagnosis + remediation plan
        return self._build_report()
```

**Key behaviors:**
- **Hypothesis-driven**: Doesn't collect everything — targets the most likely cause first
- **Evidence-based branching**: If temps are normal, skip thermal workflows entirely
- **Streaming**: Every thought/action/finding streams to the frontend in real-time
- **Auditable**: Full reasoning chain visible — "I checked X because Y, found Z, so now I think W"
- **Self-limiting**: Max steps prevent infinite loops

### Layer 2: Tool Registry (NEW — `core/agent_tools.py`)

Formalized tools the agent can invoke. Each tool has a name, description, input schema, and output parser. The agent *selects* which tool to use based on its current hypothesis.

```python
AGENT_TOOLS = {
    "check_temperatures": {
        "description": "Read all temperature sensors. Use when suspecting thermal issues.",
        "command": "get_temperature_sensors",
        "action_level": "read_only",
        "output_parser": parse_temperature_result,
        "triggers_if": ["hot", "thermal", "overheat", "fan", "throttle"],
    },
    "check_specific_dimm": {
        "description": "Get details for a specific DIMM slot. Use when logs mention a specific DIMM.",
        "command": "get_memory",
        "action_level": "read_only",
        "output_parser": parse_memory_result,
        "post_filter": lambda result, ctx: filter_to_dimm(result, ctx["target_dimm"]),
    },
    "pull_sel_window": {
        "description": "Pull SEL logs from a specific time window. Use to correlate events.",
        "command": "collect_logs",
        "action_level": "read_only",
        "output_parser": parse_logs_with_timewindow,
    },
    "run_live_thermal_snapshot": {
        "description": "Take a fresh thermal snapshot (clears cache). Use to compare against historical.",
        "command": "get_temperature_sensors",
        "pre_action": clear_sensor_cache,
        "action_level": "read_only",
        "output_parser": parse_temperature_delta,
    },
    # ... 20+ tools covering every investigation action
}
```

### Layer 3: Working Memory & Hypothesis Engine (NEW — `core/agent_memory.py`)

Structured knowledge that evolves during investigation.

```python
class WorkingMemory:
    """What the agent knows at any point during investigation"""
    
    # Facts (confirmed by data)
    confirmed_facts: List[Fact]          # "CPU0 Temp is 77°C"
    
    # Hypotheses (ranked by confidence)
    hypotheses: List[Hypothesis]          # "Thermal issue due to blocked airflow" (conf: 0.7)
    
    # Evidence chain
    evidence: Dict[str, List[Evidence]]   # hypothesis_id → supporting/refuting evidence
    
    # Timeline
    event_timeline: List[TimelineEvent]   # ordered events discovered during investigation
    
    # What we still need to know
    open_questions: List[str]             # "Is the fan failure recent or long-standing?"
    
    # Eliminated hypotheses
    ruled_out: List[Hypothesis]           # "Not a PSU issue — all PSUs healthy"


class Hypothesis:
    id: str
    description: str
    confidence: float           # 0.0 to 1.0
    category: str               # thermal, power, memory, storage, network, firmware
    supporting_evidence: List[str]
    refuting_evidence: List[str]
    next_investigation: str     # what tool to run next to test this hypothesis
    resolution_workflow: str    # which Dell workflow to use if confirmed
```

### Layer 4: Streaming Conversation UI (Frontend — `app.js`)

Replace the "click and wait" model with a **live investigation feed**.

```
┌─────────────────────────────────────────────────┐
│  🔍 Investigating: "Server overheating"         │
├─────────────────────────────────────────────────┤
│                                                 │
│  💭 Step 1: Forming initial hypotheses...       │
│     H1: Thermal issue (airflow/fan) — 60%       │
│     H2: High CPU workload — 25%                 │
│     H3: Ambient temperature — 15%               │
│                                                 │
│  🔧 Action: Checking temperature sensors...     │
│     ✅ 7 sensors read                           │
│     ⚠️ Finding: Exhaust Temp 77°C (elevated)    │
│     ✅ Inlet Temp 23°C (normal)                 │
│                                                 │
│  💭 Step 2: Exhaust hot but inlet cool →        │
│     Internal heat source, not ambient.           │
│     Updating: H3 ruled out. H1 → 75%.          │
│     Next: Check fan status.                      │
│                                                 │
│  🔧 Action: Checking fans...                    │
│     ✅ 16 fans read — all operational            │
│     ⚠️ Finding: Avg RPM 11,400 (elevated)       │
│                                                 │
│  💭 Step 3: Fans working hard but all healthy → │
│     Fans compensating. Not a fan failure.        │
│     Check CPU workload via logs...               │
│                                                 │
│  🔧 Action: Pulling recent SEL entries...       │
│     ✅ 191 entries scanned                       │
│     ⚠️ 12 thermal warnings in last 6h           │
│     ✅ No CPU errors                             │
│                                                 │
│  💭 Step 4: Thermal warnings cluster at 2pm →   │
│     Workload spike? Check if CPU-bound.          │
│     But no CPU errors. Could be airflow.         │
│     H1 confirmed at 85%.                         │
│                                                 │
│  ─────────────────────────────────────────────  │
│  📋 DIAGNOSIS                                    │
│                                                 │
│  Root Cause: Internal thermal buildup            │
│  Confidence: 85%                                 │
│  Evidence: Exhaust 77°C, inlet 23°C (54°C Δ),  │
│  all fans compensating at 11.4K RPM, thermal     │
│  warnings clustering in afternoon.               │
│                                                 │
│  📋 REMEDIATION PLAN                             │
│  1. Check blanking panels on unused drive bays   │
│  2. Inspect PCIe slot covers                     │
│  3. Clean dust filters                           │
│  4. If persists: set SysProfile=PerfOptimized    │
│                                                 │
│  [▶ Execute Step 1] [▶ Execute Step 2] [Skip]   │
└─────────────────────────────────────────────────┘
```

---

## Implementation Plan — Phases

### Phase 1: Agent Brain Core (HIGHEST PRIORITY)
**Files:** `core/agent_brain.py`, `core/agent_tools.py`, `core/agent_memory.py`

1. Build `WorkingMemory` and `Hypothesis` data models
2. Build `AgentTools` registry with all existing commands as formal tools
3. Build `AgentBrain` with the ReAct loop:
   - `_form_initial_hypotheses(issue)` — parse issue text, map to hypothesis templates
   - `_think(step)` — given current memory, pick the best next action
   - `_execute(action)` — run the tool, handle errors
   - `_observe(action, result)` — extract structured findings from raw data
   - `_update_hypotheses(findings)` — adjust confidence scores, rule out, confirm
   - `_build_report()` — compile final diagnosis, evidence chain, remediation plan
4. Wire into `main.py` as new `/investigate` endpoint (keep `/troubleshoot` as legacy)

### Phase 2: Streaming to Frontend
**Files:** `main.py` (WebSocket), `static/js/app.js`

1. New WebSocket message type: `investigation_stream`
2. Each agent step (thought, action, finding) streams as a typed event
3. Frontend renders a live investigation feed — each step appears in real-time
4. Reasoning chain is fully visible — user sees WHY the agent is doing what it's doing
5. User can **intervene** mid-investigation: "also check the RAID controller"

### Phase 3: Hypothesis Templates & Dell Knowledge Graph
**Files:** `ai/hypothesis_engine.py`, `ai/dell_knowledge_graph.py`

1. Structured hypothesis templates for every Dell failure mode:
   - Thermal: fan failure, airflow blockage, ambient, workload, heatsink
   - Power: PSU failure, redundancy loss, power source, cable
   - Memory: DIMM failure, ECC accumulation, slot failure, wrong population
   - Storage: drive failure, RAID degradation, controller issue, cable/backplane
   - Network: link down, NIC failure, driver, cable, switch-side
   - Firmware: BIOS bug, iDRAC hang, firmware mismatch
2. Dell knowledge graph linking error codes → components → failure modes → workflows
3. Confidence scoring model based on evidence strength

### Phase 4: Autonomous Remediation (with permission gates)
**Files:** `core/agent_brain.py` (extended), `core/remediation_engine.py`

1. After diagnosis, agent proposes a remediation **plan** (not just recommendations)
2. Plan has steps, each with a risk level and required action level
3. Frontend shows the plan with **approve/skip** gates per step
4. Agent executes approved steps, verifies each one worked, adapts if not
5. Example flow:
   ```
   Agent: "I want to clear the SEL to baseline, then monitor for 30 min"
   User: [Approve]
   Agent: *clears SEL*
   Agent: "SEL cleared. Setting up 30-min monitor. I'll alert if thermal warnings return."
   ... 30 min later ...
   Agent: "No new thermal warnings. Remediation appears successful."
   ```

### Phase 5: Multi-Step Investigation Patterns
**Files:** `ai/investigation_patterns.py`

1. Pre-built investigation patterns that the agent follows loosely:
   - "Thermal Triage": inlet → exhaust → fans → workload → airflow → remediate
   - "Memory Triage": SEL scan → identify DIMM → check ECC rate → test slot → recommend
   - "Boot Failure": POST codes → SEL → PSU → DIMM → BIOS → iDRAC → flea power
2. Agent uses these as **guides** but deviates based on evidence
3. Patterns are editable/extensible

### Phase 6: Agent Memory Across Sessions
**Files:** `core/agent_session_memory.py`

1. Persistent memory: "Last time I checked this server, DIMM A3 had correctable errors"
2. Trend detection: "ECC error rate on this server has doubled since last month"
3. Fleet knowledge: "3 of your 10 servers have the same BIOS version with known thermal bug"
4. Session history: full reasoning chains stored and reviewable

---

## Data Flow — New Agentic Path

```
POST /investigate
  │
  ▼
AgentBrain.investigate(issue, action_level)
  │
  ├── Step 0: _form_initial_hypotheses(issue)
  │     └── Uses: Dell knowledge graph, issue text parsing
  │     └── Streams: THOUGHT event to WebSocket
  │
  ├── Step 1-N: LOOP
  │     ├── _think(step)
  │     │     └── Evaluates: working_memory, hypothesis confidence, open_questions
  │     │     └── Selects: best next tool from AgentTools registry
  │     │     └── Streams: THOUGHT event
  │     │
  │     ├── _execute(action)
  │     │     └── Calls: agent.execute_action(tool.command, tool.params)
  │     │     └── Streams: ACTION event (tool name, params)
  │     │     └── Streams: RESULT event (raw data summary)
  │     │
  │     ├── _observe(action, result)
  │     │     └── Extracts: structured findings from raw result
  │     │     └── Updates: working_memory.confirmed_facts
  │     │     └── Streams: FINDING event (what was discovered)
  │     │
  │     └── _update_hypotheses(findings)
  │           └── Adjusts: confidence scores up/down
  │           └── Rules out: hypotheses with strong counter-evidence
  │           └── Promotes: hypotheses with strong supporting evidence
  │           └── Streams: HYPOTHESIS_UPDATE event
  │
  └── Conclude:
        ├── _build_diagnosis()  → root cause + confidence + evidence chain
        ├── _build_plan()       → remediation steps with risk levels
        └── _build_report()     → full structured report (backwards-compatible)
            └── Streams: CONCLUSION event
```

---

## What Makes This Actually Agentic

| Trait | Current (Tool) | New (Agent) |
|-------|---------------|-------------|
| **Decision-making** | Fixed pipeline, always collects everything | Chooses what to check based on evidence |
| **Branching** | None — same steps every time | If temps fine, skip thermal entirely |
| **Reasoning** | Pattern matching on keywords | Hypothesis testing with confidence scores |
| **Transparency** | Black box → report appears | Full reasoning chain visible in real-time |
| **Adaptability** | Same analysis regardless of findings | Pivots when evidence points elsewhere |
| **Memory** | Stateless — forgets between runs | Remembers past investigations, spots trends |
| **Goal-directed** | Collects data, presents it | Has a goal (find root cause), works toward it |
| **Self-evaluation** | None | Knows when it has enough evidence to stop |
| **Interaction** | One-shot request/response | Can ask user questions, accept mid-stream input |
| **Remediation** | Suggests actions, user must do them | Proposes plan, executes with permission, verifies |

---

## Priority Order for Implementation

1. **`core/agent_brain.py`** — The reasoning loop. This is THE agentic piece.
2. **`core/agent_tools.py`** — Tool registry so the brain can select tools.
3. **`core/agent_memory.py`** — Working memory structures.
4. **`main.py` → `/investigate` endpoint** — Wire it up.
5. **Frontend streaming UI** — Live investigation feed.
6. **Hypothesis templates** — Dell-specific failure mode knowledge.
7. **Remediation engine** — Execute-and-verify loop.
8. **Session memory** — Cross-investigation intelligence.

---

## Positioning Statement

> "Medi-AI-tor isn't a dashboard that shows you server data — it's an AI engineer that *investigates* problems. It forms hypotheses, gathers targeted evidence, reasons about what it finds, and delivers a diagnosis with a confidence score and remediation plan. You see its full reasoning chain in real-time, and it asks your permission before taking action. It's the difference between a thermometer and a doctor."
