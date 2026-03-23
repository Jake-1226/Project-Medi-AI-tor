# Medi-AI-tor — 4-Minute Presentation Script

## Hackathon Category: AIOps / Serviceability
**Theme:** AI Agents — Autonomous operations with minimal human intervention

## Elevator Pitch (10 sec)

> "Medi-AI-tor is an AI agent that diagnoses Dell server problems the way a senior engineer would — it forms hypotheses, gathers evidence from live hardware, and arrives at a root-cause diagnosis in 30 seconds instead of 45 minutes. No LLM, no cloud — a purpose-built reasoning engine running locally against real Redfish APIs."

---

## Setup (Before You Present)

1. Two browser tabs ready: `/` (customer) and `/technician` (tech)
2. Server already connected on both (saves 15 sec)
3. Browser at ~90% zoom
4. Start on the **Customer Chat** page

---

## THE SCRIPT — 4 Minutes

### PART 1: Customer View (0:00–2:15)

#### Connect & Intro (0:00–0:20)

Show the customer chat page. Server is already connected.

> "This is the customer experience — an app owner notices their server acting up and talks to our AI agent in plain English. Let me show you what happens."

Point out: suggestion chip categories (Quick Questions, Diagnostics, Troubleshoot).

#### Live Investigation (0:20–1:20) ⭐ KEY MOMENT

Click **"🌡️ Overheating / Loud Fans"** chip.

> "Watch the agent think in real time — this is not a black box."

**Narrate as the thinking panel streams:**
- "It's connecting to the iDRAC via Redfish, forming hypotheses..."
- "Now it's checking temperatures — found elevated readings..."
- "Checking fans — all healthy, so it's ruling out fan failure..."
- "Checking logs, checking firmware..."
- "And here's the diagnosis — with confidence scores and evidence chain."

Point out:
- **Hypothesis bars** shifting in real time
- **Business metrics**: "30 seconds vs 45 minutes. $22K saved."
- **Diagnosis card** with root cause and evidence

#### Follow-Up Conversation (1:20–1:50)

> "Now the customer can have a conversation with the agent."

- Click **"Why do you think that?"** → "Fully explainable — shows every piece of evidence."
- Click **"Can you fix this?"** → "It proposes a remediation plan — safe steps vs risky steps. Won't reboot without your approval."
- Point out **Approve / Cancel** buttons → "Human-in-the-loop. Autonomous but controlled."

#### Quick Info Demo (1:50–2:15)

> "The agent also answers quick questions without a full investigation."

Type: **"What model is this server?"** → instant answer with model, tag, hostname
Type: **"Is my firmware up to date?"** → firmware check with Dell catalog comparison, **4 critical updates found**, download links provided

> "It knows the exact versions you should be running and links to Dell support."

---

### PART 2: Technician View (2:15–3:30)

#### Switch & Orient (2:15–2:30)

Click **Technician View** link.

> "Same AI brain, different interface — this is what the Dell support engineer sees."

Point out: shared connection, sidebar navigation, action level selector.

#### Dashboard Tour (2:30–2:50)

Quick clicks — **don't linger**, just flash each:
- **Health Status** → thermal gauges, fan table, power cards
- **System Info** → BIOS sub-tab showing settings audit
- **Logs** → filterable SEL with severity stats

> "Full visibility into every subsystem — live data from Redfish, not cached."

#### Technician Investigation (2:50–3:10)

Click an investigation chip. While it runs, point out:
- **Reasoning chain feed** with step-by-step hypothesis updates
- **12-section deep-dive report** — thermal, fans, power, memory, storage, network, firmware, logs
- **Engineer's Assessment** with risk score

> "Every sensor reading, every DIMM serial number, every drive status — the full picture."

#### Operations (3:10–3:30)

Quick showcase of operations capabilities:

- Click **Export TSR** in sidebar → "One-click Tech Support Report — the first step in any Dell SR."
  - Point out the **progress bar** tracking the iDRAC job in real time
- Flash the **Operations tab** → BIOS presets (Disable C-States, Enable PPR, Max Performance)
- Flash the **Troubleshooting tab** → Job Queue, POST Codes, Diagnostics

> "Full lifecycle: investigate, diagnose, remediate, export TSR, dispatch parts — all from one tool."

---

### CLOSING (3:30–3:45)

> "Two interfaces, one AI brain. The customer gets an intelligent conversation. The technician gets engineer-grade data and actionable controls."

> "30 seconds to diagnose what takes 45 minutes manually. No LLM, no cloud dependency — a purpose-built reasoning engine that runs locally against standard Redfish APIs. Works today on any Dell PowerEdge with iDRAC."

---

### Q&A BUFFER (3:45–4:00)

---

## Likely Questions & Answers

| Question | Answer |
|----------|--------|
| **"What AI model is this?"** | Not an LLM — it's a custom ReAct reasoning engine. Forms hypotheses, selects tools, observes results, updates confidence. Deterministic Python logic with domain-specific heuristics. No GPT, no cloud. |
| **"How does it talk to the server?"** | Redfish REST API over HTTPS — the DMTF industry standard. Same API Dell engineers use. Also supports RACADM over SSH as fallback. |
| **"Why not just use iDRAC?"** | iDRAC is the data source. This is the brain. iDRAC shows you sensor values — this cross-correlates them, decodes errors, forms a diagnosis, and proposes a fix. Thermometer vs doctor. |
| **"Is it making changes?"** | Read Only by default. Destructive actions require Full Control mode + explicit human approval. Three-tier permission model. |
| **"What about security?"** | Credentials in-memory only, HTTPS to iDRAC, no external calls, no data persistence, approval gate on all destructive actions. |
| **"Business value?"** | 44 min saved per incident, $22K+ savings (downtime + labor + escalation), firmware compliance, MCA/PCIe decoding eliminates L3 dependency. |
| **"Does it work on any Dell server?"** | Any PowerEdge with iDRAC + Redfish API (12G+). Tested on R660, R760, R650, R750. |
| **"How is this different from SupportAssist?"** | SupportAssist collects data. We reason about it — hypotheses, evidence, diagnosis, remediation. Lab test vs doctor. |

---

## Backup Plan

If the server is unreachable:
- Show the **iDRAC Check** button to demonstrate connectivity testing
- Walk through architecture doc and code structure
- Have screenshots of successful investigation ready
