"""
AgentBrain — ReAct-style reasoning loop for server troubleshooting.
Think → Act → Observe → Decide → (loop or conclude)

This is the core agentic component. It doesn't follow a fixed pipeline —
it forms hypotheses, gathers targeted evidence, and reasons about findings
to reach a diagnosis.
"""

import asyncio
import logging
import re
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone

from models.server_models import ActionLevel
from core.agent_memory import (
    WorkingMemory, Hypothesis, HypothesisCategory, Fact, Evidence,
    EvidenceStrength, Thought, TimelineEvent,
)
from core.agent_tools import (
    AGENT_TOOLS, AgentTool, ToolResult, get_tools_for_category,
    get_tools_for_keywords,
)
from core.evidence_chain import EvidenceChain
from core.diagnosis_fingerprint import DiagnosisFingerprinter, SymptomVector

logger = logging.getLogger(__name__)

# Shared fingerprinter instance (persists across investigations)
_fingerprinter = DiagnosisFingerprinter()


# ═══════════════════════════════════════════════════════════════════
# Hypothesis Templates — Dell-specific failure modes
# ═══════════════════════════════════════════════════════════════════

HYPOTHESIS_TEMPLATES = {
    # Thermal
    "thermal_fan_failure": Hypothesis(
        id="thermal_fan_failure",
        description="Fan failure causing thermal buildup",
        category=HypothesisCategory.THERMAL, confidence=0.0,
        next_tool="check_fans",
        resolution_workflow="thermal_remediation",
    ),
    "thermal_airflow": Hypothesis(
        id="thermal_airflow",
        description="Airflow obstruction (blocked vents, missing blanking panels, dust)",
        category=HypothesisCategory.THERMAL, confidence=0.0,
        next_tool="check_temperatures",
        resolution_workflow="thermal_remediation",
    ),
    "thermal_workload": Hypothesis(
        id="thermal_workload",
        description="High CPU/GPU workload driving temperatures up",
        category=HypothesisCategory.THERMAL, confidence=0.0,
        next_tool="check_temperatures",
        resolution_workflow="thermal_remediation",
    ),
    "thermal_ambient": Hypothesis(
        id="thermal_ambient",
        description="Elevated ambient/inlet temperature (room too hot)",
        category=HypothesisCategory.THERMAL, confidence=0.0,
        next_tool="check_temperatures",
        resolution_workflow="thermal_remediation",
    ),
    # Power
    "power_psu_failure": Hypothesis(
        id="power_psu_failure",
        description="One or more PSUs failed or degraded",
        category=HypothesisCategory.POWER, confidence=0.0,
        next_tool="check_power_supplies",
        resolution_workflow="psu_replacement",
    ),
    "power_source_issue": Hypothesis(
        id="power_source_issue",
        description="Upstream power source problem (PDU, UPS, outlet)",
        category=HypothesisCategory.POWER, confidence=0.0,
        next_tool="check_power_supplies",
        resolution_workflow="power_source_check",
    ),
    # Memory
    "memory_dimm_failure": Hypothesis(
        id="memory_dimm_failure",
        description="DIMM failure (uncorrectable ECC or offline)",
        category=HypothesisCategory.MEMORY, confidence=0.0,
        next_tool="check_memory",
        resolution_workflow="memory_retrain",
    ),
    "memory_ecc_accumulation": Hypothesis(
        id="memory_ecc_accumulation",
        description="Correctable ECC errors accumulating (pre-failure indicator)",
        category=HypothesisCategory.MEMORY, confidence=0.0,
        next_tool="check_logs",
        resolution_workflow="memory_retrain",
    ),
    # Storage
    "storage_drive_failure": Hypothesis(
        id="storage_drive_failure",
        description="Physical disk failure or predictive failure",
        category=HypothesisCategory.STORAGE, confidence=0.0,
        next_tool="check_storage",
        resolution_workflow="raid_recovery",
    ),
    "storage_raid_degraded": Hypothesis(
        id="storage_raid_degraded",
        description="RAID virtual disk degraded or failed",
        category=HypothesisCategory.STORAGE, confidence=0.0,
        next_tool="check_storage",
        resolution_workflow="raid_recovery",
    ),
    # Network
    "network_link_down": Hypothesis(
        id="network_link_down",
        description="Network link down or NIC failure",
        category=HypothesisCategory.NETWORK, confidence=0.0,
        next_tool="check_network",
    ),
    # CPU
    "cpu_error": Hypothesis(
        id="cpu_error",
        description="CPU internal error (IERR/MCERR)",
        category=HypothesisCategory.CPU, confidence=0.0,
        next_tool="check_logs",
        resolution_workflow="cpu_ierr",
    ),
    # System / Boot
    "system_boot_failure": Hypothesis(
        id="system_boot_failure",
        description="Server not POSTing or boot failure",
        category=HypothesisCategory.SYSTEM, confidence=0.0,
        next_tool="check_health",
        resolution_workflow="flea_power_drain",
    ),
    "firmware_issue": Hypothesis(
        id="firmware_issue",
        description="Firmware bug or outdated BIOS/iDRAC causing instability",
        category=HypothesisCategory.FIRMWARE, confidence=0.0,
        next_tool="check_firmware",
        resolution_workflow="idrac_reset",
    ),
    # PCIe
    "pcie_error": Hypothesis(
        id="pcie_error",
        description="PCIe device error (AER fatal/non-fatal — completion timeout, poisoned TLP, link down)",
        category=HypothesisCategory.SYSTEM, confidence=0.0,
        next_tool="check_logs",
    ),
    # Machine Check
    "machine_check_error": Hypothesis(
        id="machine_check_error",
        description="CPU Machine Check Exception (MCE/MCA) — decoded via Intel MCA bank analysis",
        category=HypothesisCategory.CPU, confidence=0.0,
        next_tool="check_logs",
        resolution_workflow="cpu_ierr",
    ),
    # BIOS misconfiguration
    "bios_misconfiguration": Hypothesis(
        id="bios_misconfiguration",
        description="BIOS/UEFI misconfiguration (wrong boot mode, C-States, memory mode, virtualization)",
        category=HypothesisCategory.SYSTEM, confidence=0.0,
        next_tool="check_bios",
        resolution_workflow="bios_settings_change",
    ),
    # No POST / boot failure
    "no_post_failure": Hypothesis(
        id="no_post_failure",
        description="Server fails to POST — stuck at POST code, no video, amber power light",
        category=HypothesisCategory.SYSTEM, confidence=0.0,
        next_tool="check_post_codes",
    ),
}

# Keyword → hypothesis ID mapping for initial hypothesis formation
KEYWORD_HYPOTHESIS_MAP = {
    "hot": ["thermal_airflow", "thermal_fan_failure", "thermal_workload", "thermal_ambient"],
    "overheat": ["thermal_airflow", "thermal_fan_failure", "thermal_workload", "thermal_ambient"],
    "thermal": ["thermal_airflow", "thermal_fan_failure", "thermal_workload"],
    "temperature": ["thermal_airflow", "thermal_fan_failure", "thermal_ambient"],
    "fan": ["thermal_fan_failure", "thermal_airflow"],
    "loud": ["thermal_fan_failure", "thermal_workload"],
    "cooling": ["thermal_fan_failure", "thermal_airflow"],
    "throttle": ["thermal_workload", "thermal_fan_failure"],
    "power": ["power_psu_failure", "power_source_issue"],
    "shutdown": ["power_psu_failure", "power_source_issue", "thermal_fan_failure"],
    "psu": ["power_psu_failure"],
    "reboot": ["power_psu_failure", "cpu_error", "firmware_issue"],
    "memory": ["memory_dimm_failure", "memory_ecc_accumulation"],
    "ram": ["memory_dimm_failure", "memory_ecc_accumulation"],
    "dimm": ["memory_dimm_failure"],
    "ecc": ["memory_ecc_accumulation", "memory_dimm_failure"],
    "blue screen": ["memory_dimm_failure", "cpu_error"],
    "bsod": ["memory_dimm_failure", "cpu_error"],
    "disk": ["storage_drive_failure", "storage_raid_degraded"],
    "drive": ["storage_drive_failure", "storage_raid_degraded"],
    "raid": ["storage_raid_degraded", "storage_drive_failure"],
    "storage": ["storage_drive_failure", "storage_raid_degraded"],
    "degraded": ["storage_raid_degraded"],
    "slow": ["storage_drive_failure", "thermal_workload", "memory_ecc_accumulation"],
    "network": ["network_link_down"],
    "nic": ["network_link_down"],
    "link": ["network_link_down"],
    "connectivity": ["network_link_down"],
    "boot": ["system_boot_failure", "firmware_issue"],
    "post": ["system_boot_failure", "firmware_issue"],
    "cpu": ["cpu_error"],
    "ierr": ["cpu_error"],
    "firmware": ["firmware_issue"],
    "bios": ["firmware_issue"],
    "idrac": ["firmware_issue"],
    "crash": ["cpu_error", "machine_check_error", "memory_dimm_failure", "firmware_issue"],
    "hang": ["cpu_error", "machine_check_error", "firmware_issue"],
    "unresponsive": ["firmware_issue", "cpu_error", "system_boot_failure"],
    "pcie": ["pcie_error", "firmware_issue"],
    "pci": ["pcie_error"],
    "completion timeout": ["pcie_error"],
    "tlp": ["pcie_error"],
    "aer": ["pcie_error"],
    "machine check": ["machine_check_error", "cpu_error"],
    "mce": ["machine_check_error", "cpu_error"],
    "mca": ["machine_check_error", "cpu_error"],
    "mcerr": ["machine_check_error", "cpu_error"],
    "catast": ["machine_check_error", "cpu_error"],
    "update": ["firmware_issue"],
    "outdated": ["firmware_issue"],
    "driver": ["pcie_error", "firmware_issue"],
    "gpu": ["pcie_error", "thermal_workload"],
    "nvme": ["storage_drive_failure", "pcie_error"],
    "no post": ["no_post_failure", "system_boot_failure"],
    "won't post": ["no_post_failure", "system_boot_failure"],
    "amber": ["no_post_failure", "power_psu_failure"],
    "no video": ["no_post_failure", "system_boot_failure"],
    "stuck": ["no_post_failure", "system_boot_failure"],
    "configuration": ["bios_misconfiguration", "firmware_issue"],
    "c-state": ["bios_misconfiguration"],
    "c state": ["bios_misconfiguration"],
    "virtualization": ["bios_misconfiguration"],
    "boot mode": ["bios_misconfiguration", "system_boot_failure"],
    "uefi": ["bios_misconfiguration", "system_boot_failure"],
    "legacy": ["bios_misconfiguration", "system_boot_failure"],
    "tpm": ["bios_misconfiguration"],
    "settings": ["bios_misconfiguration"],
    "tsr": ["firmware_issue", "system_boot_failure"],
    "support": ["firmware_issue"],
    "escalate": ["firmware_issue"],
    "dispatch": ["storage_drive_failure", "memory_dimm_failure", "power_psu_failure"],
    "replace": ["storage_drive_failure", "memory_dimm_failure", "power_psu_failure"],
    "part": ["storage_drive_failure", "memory_dimm_failure", "power_psu_failure"],
}


class AgentBrain:
    """
    ReAct-style reasoning loop for Dell server troubleshooting.
    
    The brain forms hypotheses about what might be wrong, selects tools
    to gather evidence, observes the results, updates confidence scores,
    and either continues investigating or concludes with a diagnosis.
    """

    MAX_STEPS = 12

    def __init__(self, agent, config=None):
        """
        Args:
            agent: DellAIAgent instance (used to execute commands)
            config: AgentConfig (optional)
        """
        self.agent = agent
        self.config = config
        self.memory = WorkingMemory()
        self._stream_callback: Optional[Callable] = None
        # Persistent session state for multi-turn chat
        self._last_diagnosis: Optional[dict] = None
        self._last_issue: Optional[str] = None
        self._chat_history: List[dict] = []
        self._investigation_start: Optional[datetime] = None
        self._investigation_end: Optional[datetime] = None
        self._remediation_log: List[dict] = []
        self._tool_cache_times: Dict[str, float] = {}  # tool_name -> timestamp of last execution
        self._CACHE_TTL = 60  # seconds before cached data is considered stale
        self._evidence_chain: Optional[EvidenceChain] = None
        self._fingerprinter = _fingerprinter

    def set_stream_callback(self, callback: Callable):
        """Set async callback for streaming events to frontend: callback(event_type, data)"""
        self._stream_callback = callback

    async def _stream(self, event_type: str, data: dict):
        """Send a streaming event to the frontend."""
        if self._stream_callback:
            try:
                await self._stream_callback(event_type, data)
            except Exception as e:
                logger.warning(f"Stream callback error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Main Investigation Loop
    # ═══════════════════════════════════════════════════════════

    async def investigate(self, issue: str, action_level: ActionLevel) -> dict:
        """
        Run the full agentic investigation loop.
        Returns a structured report compatible with the existing frontend,
        plus the full reasoning chain.
        """
        self.memory = WorkingMemory()  # fresh memory for this investigation
        self._evidence_chain = EvidenceChain()  # fresh evidence chain
        start_time = time.time()
        logger.info(f"AgentBrain: Starting investigation — \"{issue}\"")

        # ── Step 0: Form initial hypotheses ──────────────────
        initial_hyps = self._form_initial_hypotheses(issue)

        # Record hypotheses in evidence chain
        hyp_event_ids = []
        for h in initial_hyps:
            eid = self._evidence_chain.record_hypothesis(
                h.id, h.description, h.category.value, h.confidence)
            hyp_event_ids.append(eid)

        thought0 = Thought(
            step=0,
            reasoning=f"Analyzing issue: \"{issue}\". Forming initial hypotheses based on keywords.",
            hypotheses_snapshot=[
                {"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)}
                for h in initial_hyps
            ],
            next_action="check_system_info",
            next_action_reason="Always identify the server first.",
        )
        self.memory.thought_chain.append(thought0)
        await self._stream("thought", thought0.to_dict())

        # Always start with system info + health
        for boot_tool in ["check_system_info", "check_health"]:
            tool = AGENT_TOOLS.get(boot_tool)
            if tool:
                result = await self._execute_tool(tool, action_level)
                if result and result.success:
                    self._observe(tool, result)
                    await self._stream("action_result", result.to_dict())

        # ── Step 1-N: ReAct loop ─────────────────────────────
        for step in range(1, self.MAX_STEPS + 1):
            if time.time() - start_time > 120:  # 2 minute timeout
                logger.warning("AgentBrain: Investigation timeout (120s)")
                break

            # THINK
            thought = self._think(step)
            self.memory.thought_chain.append(thought)
            await self._stream("thought", thought.to_dict())

            if thought.conclusion:
                logger.info(f"AgentBrain: Concluded at step {step}: {thought.conclusion}")
                break

            if not thought.next_action:
                logger.info(f"AgentBrain: No more actions to take at step {step}")
                break

            # ACT
            tool = AGENT_TOOLS.get(thought.next_action)
            if not tool:
                logger.warning(f"AgentBrain: Unknown tool {thought.next_action}")
                continue

            if thought.next_action in self.memory.tools_used:
                # Don't re-run the same tool (unless it's logs which can be re-scanned)
                if thought.next_action != "check_logs":
                    logger.info(f"AgentBrain: Skipping already-used tool {thought.next_action}")
                    continue

            # Record tool invocation in evidence chain
            top_hyp = self.memory.get_active_hypotheses()
            testing_hyp = top_hyp[0].id if top_hyp else "general"
            tool_eid = self._evidence_chain.record_tool_invocation(
                tool.name, {}, testing_hyp, hyp_event_ids[:1]) if self._evidence_chain else None

            result = await self._execute_tool(tool, action_level)

            # Record API call in evidence chain
            if self._evidence_chain and result and tool_eid:
                self._evidence_chain.record_api_call(
                    tool.name, result.to_dict() if result else {}, tool_eid)

            await self._stream("action_result", result.to_dict() if result else {"tool_name": tool.name, "success": False, "summary": "Tool execution failed"})

            if result and result.success:
                # OBSERVE
                findings = self._observe(tool, result)

                # Record evidence in chain
                if self._evidence_chain:
                    for fact in result.facts:
                        supports = fact.status in ("warning", "critical")
                        self._evidence_chain.record_evidence(
                            fact.description, supports,
                            "strong" if fact.status == "critical" else "moderate",
                            testing_hyp, [tool_eid] if tool_eid else [])

                await self._stream("findings", {
                    "step": step, "tool": tool.name,
                    "summary": result.summary,
                    "warnings": result.warnings,
                    "critical": result.critical,
                    "new_facts": len(result.facts),
                })

                # DECIDE — update hypotheses
                self._update_hypotheses(tool, result)
                await self._stream("hypothesis_update", {
                    "step": step,
                    "active": [
                        {"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)}
                        for h in self.memory.get_active_hypotheses()
                    ],
                    "ruled_out": [h.id for h in self.memory.hypotheses.values() if h.ruled_out],
                })

        # ── Conclude ─────────────────────────────────────────
        diagnosis = self._build_diagnosis()
        await self._stream("conclusion", diagnosis)

        # Record conclusion in evidence chain
        duration_ms = int((time.time() - start_time) * 1000)
        if self._evidence_chain:
            evidence_ids = [e.id for e in self._evidence_chain.events
                           if e.event_type.value == "evidence_collected"]
            self._evidence_chain.record_conclusion(
                diagnosis=diagnosis.get("summary", ""),
                confidence=diagnosis.get("confidence", 0),
                root_cause=diagnosis.get("root_cause", ""),
                remediation=diagnosis.get("remediation", ""),
                supporting_evidence_ids=evidence_ids[-5:],  # last 5 evidence events
            )

        # Record fingerprint for future instant recall
        try:
            facts_for_fp = [f.to_dict() for f in self.memory.facts.values()]
            symptoms = self._fingerprinter.extract_symptoms(facts_for_fp)
            server_model = None
            if self.agent and hasattr(self.agent, 'current_session') and self.agent.current_session:
                server_model = getattr(self.agent.current_session, 'server_host', None)
            self._fingerprinter.record_diagnosis(
                symptoms=symptoms,
                root_cause=diagnosis.get("root_cause", "unknown"),
                diagnosis=diagnosis.get("summary", ""),
                remediation=diagnosis.get("remediation", ""),
                confidence=diagnosis.get("confidence", 0),
                tools_used=list(self.memory.tools_used),
                duration_ms=duration_ms,
                server_model=server_model,
            )
            logger.info(f"AgentBrain: Diagnosis fingerprinted (duration={duration_ms}ms)")
        except Exception as e:
            logger.warning(f"AgentBrain: Fingerprint recording failed: {e}")

        # Build backwards-compatible report for the existing deep-dive UI
        full_report = self._build_compatible_report(issue, diagnosis)

        # Attach evidence chain ID to report for audit access
        if self._evidence_chain:
            full_report["evidence_chain_id"] = self._evidence_chain.investigation_id
            full_report["evidence_chain_hash"] = self._evidence_chain.chain_hash
            full_report["evidence_events"] = len(self._evidence_chain.events)

        return full_report

    # ═══════════════════════════════════════════════════════════
    # Step 0: Form Initial Hypotheses
    # ═══════════════════════════════════════════════════════════

    def _form_initial_hypotheses(self, issue: str) -> List[Hypothesis]:
        """Parse the issue text and form ranked initial hypotheses."""
        issue_lower = issue.lower()
        words = re.findall(r'\w+', issue_lower)
        hyp_scores: Dict[str, float] = {}

        for kw, hyp_ids in KEYWORD_HYPOTHESIS_MAP.items():
            # Substring match: 'overheating' contains 'overheat', 'fans' contains 'fan'
            # Require min 3 chars for reverse match (w in kw) to avoid 'a' matching 'raid'
            if kw in issue_lower or any(kw in w or (len(w) >= 3 and w in kw) for w in words):
                for hyp_id in hyp_ids:
                    hyp_scores[hyp_id] = hyp_scores.get(hyp_id, 0) + 0.15

        # If no keywords matched, add generic hypotheses
        if not hyp_scores:
            for hid in ["system_boot_failure", "firmware_issue", "thermal_airflow", "power_psu_failure"]:
                hyp_scores[hid] = 0.25

        # Create hypothesis objects from templates
        for hyp_id, score in hyp_scores.items():
            if hyp_id in HYPOTHESIS_TEMPLATES:
                template = HYPOTHESIS_TEMPLATES[hyp_id]
                hyp = Hypothesis(
                    id=template.id,
                    description=template.description,
                    category=template.category,
                    confidence=min(score, 0.5),
                    next_tool=template.next_tool,
                    resolution_workflow=template.resolution_workflow,
                )
                self.memory.add_hypothesis(hyp)

        return self.memory.get_active_hypotheses()

    # ═══════════════════════════════════════════════════════════
    # THINK — Decide what to do next
    # ═══════════════════════════════════════════════════════════

    def _think(self, step: int) -> Thought:
        """Given current working memory, decide the best next action."""
        active = self.memory.get_active_hypotheses()
        top = active[0] if active else None

        # Check if we can conclude
        if top and top.confidence >= 0.85:
            return Thought(
                step=step,
                reasoning=f"Hypothesis '{top.description}' has reached {round(top.confidence*100)}% confidence. Sufficient evidence to conclude.",
                hypotheses_snapshot=[{"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)} for h in active],
                conclusion=f"Root cause identified: {top.description} (confidence: {round(top.confidence*100)}%)",
            )

        # Check if all hypotheses are low-confidence and we've exhausted core tools
        if len(self.memory.tools_used) >= 9 and (not top or top.confidence < 0.4):
            return Thought(
                step=step,
                reasoning="Extensive data collected but no strong hypothesis emerged. Concluding with best available assessment.",
                hypotheses_snapshot=[{"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)} for h in active],
                conclusion=f"Investigation inconclusive. Best hypothesis: {top.description if top else 'None'} ({round(top.confidence*100) if top else 0}%)",
            )

        # Find the best next tool to run
        next_tool = None
        reason = ""

        if top and top.next_tool and top.next_tool not in self.memory.tools_used:
            next_tool = top.next_tool
            reason = f"Testing top hypothesis '{top.description}' — need {next_tool} data."
        else:
            # Find an unused tool relevant to any active hypothesis
            for hyp in active:
                if hyp.next_tool and hyp.next_tool not in self.memory.tools_used:
                    next_tool = hyp.next_tool
                    reason = f"Gathering evidence for hypothesis '{hyp.description}'."
                    break

            # If all hypothesis tools are used, check logs if not done
            if not next_tool and "check_logs" not in self.memory.tools_used:
                next_tool = "check_logs"
                reason = "Scanning system logs for error patterns and timeline data."

            # Broaden: collect data from any unused core tool to build full picture
            if not next_tool:
                core_order = ["check_temperatures", "check_fans", "check_power_supplies",
                              "check_memory", "check_storage", "check_network", "check_logs"]
                for ct in core_order:
                    if ct not in self.memory.tools_used:
                        next_tool = ct
                        reason = f"Broadening investigation — collecting {ct} data for complete picture."
                        break

        # Build reasoning narrative
        facts_summary = f"Known: {len(self.memory.facts)} facts"
        crit_facts = self.memory.get_facts_by_status("critical")
        warn_facts = self.memory.get_facts_by_status("warning")
        if crit_facts:
            facts_summary += f", {len(crit_facts)} critical"
        if warn_facts:
            facts_summary += f", {len(warn_facts)} warnings"

        hyp_summary = ", ".join([f"{h.description} ({round(h.confidence*100)}%)" for h in active[:3]])
        ruled_out = [h.id for h in self.memory.hypotheses.values() if h.ruled_out]

        reasoning = f"{facts_summary}. Active hypotheses: {hyp_summary}."
        if ruled_out:
            reasoning += f" Ruled out: {', '.join(ruled_out)}."
        if reason:
            reasoning += f" Next: {reason}"

        return Thought(
            step=step,
            reasoning=reasoning,
            hypotheses_snapshot=[{"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)} for h in active],
            next_action=next_tool,
            next_action_reason=reason,
            ruled_out=ruled_out,
        )

    # ═══════════════════════════════════════════════════════════
    # ACT — Execute a tool
    # ═══════════════════════════════════════════════════════════

    async def _execute_tool(self, tool: AgentTool, action_level: ActionLevel) -> Optional[ToolResult]:
        """Run a tool via the agent's execute_action interface."""
        try:
            logger.info(f"AgentBrain: Executing tool '{tool.name}' (command: {tool.command})")
            await self._stream("action_start", {
                "tool": tool.name, "description": tool.description, "command": tool.command,
            })

            raw_result = await self.agent.execute_action(
                action_level=ActionLevel(tool.action_level),
                command=tool.command,
                parameters=tool.parameters,
            )

            self.memory.tools_used.append(tool.name)
            self.memory.raw_data[tool.name] = raw_result
            self._tool_cache_times[tool.name] = time.time()

            # Parse the result using the tool's parser
            if tool.parser:
                return tool.parser(raw_result)
            else:
                return ToolResult(tool_name=tool.name, success=True,
                                  summary=f"{tool.name} completed", raw_data=raw_result)

        except Exception as e:
            logger.error(f"AgentBrain: Tool '{tool.name}' failed: {e}")
            self.memory.tools_used.append(tool.name)
            return ToolResult(tool_name=tool.name, success=False, summary=f"Failed: {str(e)}")

    def _is_tool_cached(self, tool_name: str) -> bool:
        """Check if a tool's data is fresh enough to use from cache."""
        cached_time = self._tool_cache_times.get(tool_name)
        if cached_time and (time.time() - cached_time) < self._CACHE_TTL:
            return tool_name in self.memory.raw_data
        return False

    def _get_cached_result(self, tool_name: str) -> Optional[ToolResult]:
        """Return cached parsed result for a tool if available."""
        raw_data = self.memory.raw_data.get(tool_name)
        if not raw_data:
            return None
        tool = AGENT_TOOLS.get(tool_name)
        if tool and tool.parser:
            try:
                return tool.parser(raw_data)
            except Exception:
                return None
        return ToolResult(tool_name=tool_name, success=True, summary=f"{tool_name} (cached)", raw_data=raw_data)

    # ═══════════════════════════════════════════════════════════
    # OBSERVE — Extract findings from tool results
    # ═══════════════════════════════════════════════════════════

    def _observe(self, tool: AgentTool, result: ToolResult) -> List[Fact]:
        """Parse tool result, add facts to working memory."""
        for fact in result.facts:
            self.memory.add_fact(fact)

        # Add timeline events for critical/warning findings
        now = datetime.now(timezone.utc)
        for msg in result.critical:
            self.memory.timeline.append(TimelineEvent(
                timestamp=now, description=msg, severity="critical", source=tool.name,
            ))
        for msg in result.warnings:
            self.memory.timeline.append(TimelineEvent(
                timestamp=now, description=msg, severity="warning", source=tool.name,
            ))

        return result.facts

    # ═══════════════════════════════════════════════════════════
    # DECIDE — Update hypothesis confidence based on findings
    # ═══════════════════════════════════════════════════════════

    def _update_hypotheses(self, tool: AgentTool, result: ToolResult):
        """Adjust hypothesis confidence based on what we just found."""

        has_critical = len(result.critical) > 0
        has_warnings = len(result.warnings) > 0

        for hyp in self.memory.get_active_hypotheses():
            # ── Thermal hypotheses ────────────────────────────
            if hyp.category == HypothesisCategory.THERMAL:
                if tool.name == "check_temperatures":
                    # Check for actual thermal-specific warnings vs unrelated tool warnings
                    temp_facts = result.facts
                    temp_critical = [f for f in temp_facts if f.status == "critical"]
                    temp_warnings = [f for f in temp_facts if f.status == "warning"]
                    if temp_critical:
                        hyp.adjust_confidence(+0.25)
                        hyp.supporting_evidence.append(Evidence(
                            fact_id="temp_critical", description="Critical temperature readings found",
                            supports=True, strength=EvidenceStrength.STRONG,
                        ))
                    elif temp_warnings:
                        hyp.adjust_confidence(+0.10)
                        hyp.supporting_evidence.append(Evidence(
                            fact_id="temp_warning", description="Elevated temperatures detected",
                            supports=True, strength=EvidenceStrength.WEAK,
                        ))
                    else:
                        # Temperatures normal — strong refutation for all thermal hypotheses
                        hyp.adjust_confidence(-0.30)
                        hyp.refuting_evidence.append(Evidence(
                            fact_id="temp_normal", description="All temperatures within normal limits",
                            supports=False, strength=EvidenceStrength.STRONG,
                        ))
                        if hyp.confidence < 0.25:
                            self.memory.rule_out(hyp.id, "Temperatures all normal")

                elif tool.name == "check_fans":
                    failed_fans = [f for f in result.facts if f.status == "critical"]
                    warning_fans = [f for f in result.facts if f.status == "warning"]
                    if failed_fans and hyp.id == "thermal_fan_failure":
                        hyp.adjust_confidence(+0.35)
                        hyp.supporting_evidence.append(Evidence(
                            fact_id="fan_failed", description=f"{len(failed_fans)} fan(s) failed",
                            supports=True, strength=EvidenceStrength.STRONG,
                        ))
                    elif not failed_fans and not warning_fans:
                        # All fans healthy — refute ALL thermal hypotheses, not just fan_failure
                        hyp.adjust_confidence(-0.25)
                        hyp.refuting_evidence.append(Evidence(
                            fact_id="fans_ok", description="All fans operational and within normal RPM",
                            supports=False, strength=EvidenceStrength.STRONG,
                        ))
                        if hyp.confidence < 0.25:
                            self.memory.rule_out(hyp.id, "All fans healthy")
                    elif not failed_fans and hyp.id == "thermal_fan_failure":
                        # Fans have warnings but none failed — only refute fan_failure
                        hyp.adjust_confidence(-0.20)
                        hyp.refuting_evidence.append(Evidence(
                            fact_id="fans_ok", description="No fan failures detected",
                            supports=False, strength=EvidenceStrength.MODERATE,
                        ))
                        if hyp.confidence < 0.25:
                            self.memory.rule_out(hyp.id, "No fan failures")
                    # Only boost airflow/workload if fans are actually running high RPM with warnings
                    if warning_fans and hyp.id in ("thermal_airflow", "thermal_workload"):
                        hyp.adjust_confidence(+0.05)

            # ── Power hypotheses ──────────────────────────────
            elif hyp.category == HypothesisCategory.POWER:
                if tool.name == "check_power_supplies":
                    # Check for specific PSU failures (not just generic critical flag)
                    psu_facts = result.facts
                    failed_psus = [f for f in psu_facts if f.status == "critical"]
                    
                    if failed_psus:
                        # Direct evidence of PSU failure — very high confidence
                        boost = 0.5 if len(failed_psus) >= 1 else 0.3
                        hyp.adjust_confidence(boost)
                        for pf in failed_psus[:2]:
                            desc = getattr(pf, 'description', 'PSU failure')
                            hyp.supporting_evidence.append(Evidence(
                                fact_id=f"psu_{getattr(pf, 'id', 'unknown')}", 
                                description=desc,
                                supports=True, strength=EvidenceStrength.STRONG,
                            ))
                        # If PSU is explicitly offline/unavailable, this is near-definitive
                        for pf in failed_psus:
                            desc_lower = getattr(pf, 'description', '').lower()
                            if 'unavailable' in desc_lower or 'offline' in desc_lower or 'absent' in desc_lower:
                                hyp.adjust_confidence(0.25)  # Extra boost for definitive failure
                    else:
                        hyp.adjust_confidence(-0.30)
                        hyp.refuting_evidence.append(Evidence(
                            fact_id="psu_ok", description="All PSUs healthy and operational",
                            supports=False, strength=EvidenceStrength.STRONG,
                        ))
                        if hyp.confidence < 0.15:
                            self.memory.rule_out(hyp.id, "All PSUs healthy")

            # ── Memory hypotheses ─────────────────────────────
            elif hyp.category == HypothesisCategory.MEMORY:
                if tool.name == "check_memory":
                    failed_dimms = [f for f in result.facts if f.status == "critical"]
                    if failed_dimms:
                        hyp.adjust_confidence(+0.5)
                        for fd in failed_dimms[:2]:
                            hyp.supporting_evidence.append(Evidence(
                                fact_id=f"dimm_{getattr(fd, 'id', '?')}", 
                                description=getattr(fd, 'description', 'DIMM failure'),
                                supports=True, strength=EvidenceStrength.STRONG,
                            ))
                    elif hyp.id == "memory_dimm_failure":
                        hyp.adjust_confidence(-0.25)
                        hyp.refuting_evidence.append(Evidence(
                            fact_id="dimms_ok", description="All DIMMs healthy",
                            supports=False, strength=EvidenceStrength.STRONG,
                        ))
                        if hyp.confidence < 0.15:
                            self.memory.rule_out(hyp.id, "All DIMMs healthy")

                elif tool.name == "check_logs":
                    mem_facts = [f for f in result.facts if any(kw in getattr(f, 'description', '').lower() for kw in ["memory", "ecc", "dimm"])]
                    if mem_facts and hyp.id == "memory_ecc_accumulation":
                        hyp.adjust_confidence(+0.2)
                        hyp.supporting_evidence.append(Evidence(
                            fact_id="ecc_in_logs", description=f"{len(mem_facts)} memory-related log entries",
                            supports=True, strength=EvidenceStrength.MODERATE,
                        ))

            # ── Storage hypotheses ────────────────────────────
            elif hyp.category == HypothesisCategory.STORAGE:
                if tool.name == "check_storage":
                    failed_drives = [f for f in result.facts if f.status == "critical"]
                    if failed_drives:
                        hyp.adjust_confidence(+0.5)
                        for fd in failed_drives[:2]:
                            hyp.supporting_evidence.append(Evidence(
                                fact_id=f"drive_{getattr(fd, 'id', '?')}",
                                description=getattr(fd, 'description', 'Drive failure'),
                                supports=True, strength=EvidenceStrength.STRONG,
                            ))
                    else:
                        hyp.adjust_confidence(-0.25)
                        hyp.refuting_evidence.append(Evidence(
                            fact_id="storage_ok", description="All storage devices healthy",
                            supports=False, strength=EvidenceStrength.STRONG,
                        ))
                        if hyp.confidence < 0.15:
                            self.memory.rule_out(hyp.id, "All storage devices healthy")

            # ── Network hypotheses ────────────────────────────
            elif hyp.category == HypothesisCategory.NETWORK:
                if tool.name == "check_network":
                    if has_warnings or has_critical:
                        hyp.adjust_confidence(+0.25)
                    else:
                        hyp.adjust_confidence(-0.25)
                        if hyp.confidence < 0.15:
                            self.memory.rule_out(hyp.id, "All NICs healthy")

            # ── CPU hypotheses ────────────────────────────────
            elif hyp.category == HypothesisCategory.CPU:
                if tool.name == "check_logs":
                    cpu_facts = [f for f in result.facts if "cpu" in f.description.lower() or "ierr" in f.description.lower() or "machine check" in f.description.lower()]
                    if cpu_facts:
                        hyp.adjust_confidence(+0.25)
                    else:
                        hyp.adjust_confidence(-0.1)

            # ── Log evidence applies broadly ──────────────────
            if tool.name == "check_logs":
                for f in result.facts:
                    desc_lower = f.description.lower()
                    if hyp.category == HypothesisCategory.THERMAL and any(kw in desc_lower for kw in ["thermal", "temperature", "fan", "overheat"]):
                        hyp.adjust_confidence(+0.05)
                    elif hyp.category == HypothesisCategory.POWER and any(kw in desc_lower for kw in ["power", "psu", "voltage"]):
                        hyp.adjust_confidence(+0.05)
                    elif hyp.category == HypothesisCategory.STORAGE and any(kw in desc_lower for kw in ["disk", "raid", "storage", "drive"]):
                        hyp.adjust_confidence(+0.05)

    # ═══════════════════════════════════════════════════════════
    # CONCLUDE — Build diagnosis and remediation plan
    # ═══════════════════════════════════════════════════════════

    def _build_diagnosis(self) -> dict:
        """Compile the final diagnosis from working memory."""
        top = self.memory.get_top_hypothesis()
        active = self.memory.get_active_hypotheses()
        crit_facts = self.memory.get_facts_by_status("critical")
        warn_facts = self.memory.get_facts_by_status("warning")

        # Root cause
        if top and top.confidence >= 0.5:
            root_cause = top.description
            confidence = round(top.confidence * 100)
            category = top.category.value
        elif top:
            root_cause = f"Likely: {top.description}"
            confidence = round(top.confidence * 100)
            category = top.category.value
        else:
            root_cause = "No specific hardware fault identified"
            confidence = 0
            category = "system"

        # Evidence chain
        evidence_chain = []
        if top:
            for ev in top.supporting_evidence:
                evidence_chain.append({"description": ev.description, "supports": True, "strength": ev.strength.value})
            for ev in top.refuting_evidence:
                evidence_chain.append({"description": ev.description, "supports": False, "strength": ev.strength.value})

        # Remediation plan from workflow
        remediation_steps = []
        workflow_name = ""
        if top and top.resolution_workflow:
            from ai.troubleshooting_engine import DELL_WORKFLOWS
            wf = DELL_WORKFLOWS.get(top.resolution_workflow, {})
            workflow_name = wf.get("name", "")
            remediation_steps = wf.get("steps", [])

        # Build narrative
        narrative = []
        narrative.append(f"Investigated issue across {len(self.memory.tools_used)} data sources.")
        narrative.append(f"Collected {len(self.memory.facts)} facts — {len(crit_facts)} critical, {len(warn_facts)} warnings.")
        if self.memory.get_active_hypotheses():
            narrative.append(f"Strongest hypothesis: {root_cause} ({confidence}% confidence).")
        ruled = [h for h in self.memory.hypotheses.values() if h.ruled_out]
        if ruled:
            narrative.append(f"Ruled out: {', '.join(h.description for h in ruled)}.")

        return {
            "root_cause": root_cause,
            "confidence": confidence,
            "category": category,
            "evidence_chain": evidence_chain,
            "workflow_name": workflow_name,
            "remediation_steps": remediation_steps,
            "narrative": narrative,
            "critical_findings": [f.to_dict() for f in crit_facts],
            "warning_findings": [f.to_dict() for f in warn_facts],
            "hypotheses_final": [h.to_dict() for h in active],
            "ruled_out": [{"id": h.id, "description": h.description} for h in ruled],
            "reasoning_chain": [t.to_dict() for t in self.memory.thought_chain],
            "tools_used": self.memory.tools_used,
        }

    # ═══════════════════════════════════════════════════════════
    # Backwards-compatible report builder
    # ═══════════════════════════════════════════════════════════

    def _build_compatible_report(self, issue: str, diagnosis: dict) -> dict:
        """
        Build a report structure that works with both the existing
        deep-dive frontend AND the new agentic investigation UI.
        Merges agentic diagnosis into the legacy report format.
        """
        # The existing troubleshoot_issue report runs the full pipeline.
        # We augment it with the agentic layer.
        return {
            "agentic": True,
            "diagnosis": diagnosis,
            "reasoning_chain": diagnosis.get("reasoning_chain", []),
            "working_memory": self.memory.to_dict(),
            # These fields are expected by the legacy deep-dive frontend:
            "recommendations": self._build_recommendations(diagnosis),
            "report": self._build_legacy_report(diagnosis),
            "collected_data": self._build_collected_data(),
        }

    def _build_recommendations(self, diagnosis: dict) -> List[dict]:
        """Convert diagnosis into recommendation format the frontend expects."""
        recs = []
        # Main recommendation from diagnosis
        if diagnosis.get("root_cause") and diagnosis.get("confidence", 0) > 0:
            recs.append({
                "action": f"Root Cause: {diagnosis['root_cause']}",
                "description": f"AI confidence: {diagnosis['confidence']}%. " + " ".join(diagnosis.get("narrative", [])),
                "priority": "critical" if diagnosis["confidence"] >= 70 else "high" if diagnosis["confidence"] >= 40 else "medium",
                "action_level_required": "read_only",
                "estimated_time": "Review",
                "risk_level": "low",
                "steps": diagnosis.get("remediation_steps", []),
                "commands": [],
            })

        # Remediation workflow as separate recommendation
        if diagnosis.get("workflow_name") and diagnosis.get("remediation_steps"):
            recs.append({
                "action": f"Workflow: {diagnosis['workflow_name']}",
                "description": f"Dell recommended workflow for this issue type.",
                "priority": "high",
                "action_level_required": "diagnostic",
                "estimated_time": "15-60 minutes",
                "risk_level": "medium",
                "steps": diagnosis["remediation_steps"],
                "commands": [],
            })

        # Add recommendations from critical findings
        for f in diagnosis.get("critical_findings", [])[:3]:
            recs.append({
                "action": f"Investigate: {f['component']}",
                "description": f["description"],
                "priority": "high",
                "action_level_required": "read_only",
                "estimated_time": "5 minutes",
                "risk_level": "low",
                "steps": [f"Review {f['component']} status", "Cross-reference with SEL logs"],
                "commands": [],
            })

        # Always recommend TSR collection
        recs.append({
            "action": "Collect Technical Support Report (TSR)",
            "description": "Gather full diagnostic data for Dell Support case analysis.",
            "priority": "medium",
            "action_level_required": "read_only",
            "estimated_time": "10-20 minutes",
            "risk_level": "low",
            "steps": ["Use Export TSR in Server Actions", "Attach to Dell Support case"],
            "commands": ["export_tsr"],
        })

        return recs

    def _build_legacy_report(self, diagnosis: dict) -> dict:
        """Build report dict matching the existing deep-dive report structure."""
        # Pull raw data from memory
        temps_raw = self.memory.raw_data.get("check_temperatures", {}).get("temperatures", [])
        fans_raw = self.memory.raw_data.get("check_fans", {}).get("fans", [])
        psus_raw = self.memory.raw_data.get("check_power_supplies", {}).get("power_supplies", [])
        mem_raw = self.memory.raw_data.get("check_memory", {}).get("memory", [])
        storage_raw = self.memory.raw_data.get("check_storage", {}).get("storage_devices", [])
        network_raw = self.memory.raw_data.get("check_network", {}).get("network_interfaces", [])
        health_raw = self.memory.raw_data.get("check_health", {}).get("health_status", {})
        sys_raw = self.memory.raw_data.get("check_system_info", {})
        si = sys_raw.get("server_info") or sys_raw.get("system_info") or {}

        def _is_healthy(s):
            if not s: return True
            return any(w in s.lower() for w in ("ok", "enabled", "operable", "online", "optimal", "ready", "present"))

        def hIcon(h):
            return "ok" if _is_healthy(h) else "critical"

        # System identity
        system_identity = {
            "model": si.get("model", ""),
            "service_tag": si.get("service_tag") or si.get("serial_number", ""),
            "bios_version": si.get("bios_version") or si.get("firmware_version", ""),
            "idrac_version": si.get("idrac_version", ""),
            "hostname": si.get("hostname", ""),
            "power_state": si.get("power_state", ""),
            "cpu_model": si.get("cpu_model", ""),
            "cpu_count": si.get("cpu_count", 0),
            "total_memory_gb": si.get("total_memory_gb", 0),
            "os": si.get("os_name", ""),
            "os_version": si.get("os_version", ""),
        }

        # Deep dive
        deep_dive = {
            "temperatures": [
                {"name": t.get("name","?"), "reading": t.get("reading_celsius"),
                 "status": t.get("status","?"),
                 "upper_critical": t.get("upper_threshold_critical"),
                 "upper_warning": t.get("upper_threshold_warning"),
                 "health": "critical" if (t.get("reading_celsius") or 0) > 80 else "warning" if (t.get("reading_celsius") or 0) > 70 else "ok"}
                for t in temps_raw
            ],
            "fans": [
                {"name": f.get("name","?"), "speed_rpm": f.get("speed_rpm"),
                 "status": f.get("status","?"), "health": hIcon(f.get("status"))}
                for f in fans_raw
            ],
            "power_supplies": [
                {"id": p.get("id","?"), "model": p.get("model",""),
                 "power_watts": p.get("power_watts"), "capacity_watts": p.get("capacity_watts"),
                 "status": p.get("status","?"), "efficiency": p.get("efficiency",""),
                 "firmware": p.get("firmware_version",""), "health": hIcon(p.get("status"))}
                for p in psus_raw
            ],
            "memory": [
                {"id": m.get("id","?"), "size_gb": m.get("size_gb"), "type": m.get("type",""),
                 "speed_mhz": m.get("speed_mhz"), "manufacturer": m.get("manufacturer",""),
                 "part_number": m.get("part_number",""), "serial": m.get("serial_number",""),
                 "status": m.get("status","?"), "slot": m.get("slot",""), "health": hIcon(m.get("status"))}
                for m in mem_raw
            ],
            "storage": [
                {"id": s.get("id","?"), "name": s.get("name",""), "model": s.get("model",""),
                 "capacity_gb": s.get("capacity_gb"), "media_type": s.get("media_type",""),
                 "protocol": s.get("protocol",""), "serial": s.get("serial_number",""),
                 "status": s.get("status","?"), "firmware": s.get("firmware_version",""),
                 "health": hIcon(s.get("status"))}
                for s in storage_raw
            ],
            "network": [
                {"id": n.get("id","?"), "name": n.get("name",""), "mac": n.get("mac_address",""),
                 "speed_mbps": n.get("speed_mbps"), "status": n.get("status","?"),
                 "ipv4": n.get("ipv4_address",""), "link_status": n.get("link_status",""),
                 "health": hIcon(n.get("status"))}
                for n in network_raw
            ],
        }

        # Engineer assessment from diagnosis
        risk_score = min(diagnosis.get("confidence", 0), 100)
        if risk_score >= 70:
            risk_level, risk_label = "critical", "Immediate Action Required"
        elif risk_score >= 40:
            risk_level, risk_label = "elevated", "Attention Needed"
        elif risk_score >= 15:
            risk_level, risk_label = "moderate", "Monitor Closely"
        else:
            risk_level, risk_label = "healthy", "System Appears Healthy"

        engineer_assessment = {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_label": risk_label,
            "top_concerns": [f["description"] for f in diagnosis.get("critical_findings", [])[:5]],
            "correlations_found": 0,
            "narrative": diagnosis.get("narrative", []),
            "recommendation_summary": diagnosis.get("root_cause", ""),
        }

        # Anomalies from critical/warning facts
        anomalies = []
        for f in diagnosis.get("critical_findings", []):
            anomalies.append({"type": "critical", "component": f.get("component","?"), "detail": f.get("description","")})
        for f in diagnosis.get("warning_findings", [])[:5]:
            anomalies.append({"type": "warning", "component": f.get("component","?"), "detail": f.get("description","")})

        # Correlations from evidence chain
        correlations = []
        for ev in diagnosis.get("evidence_chain", []):
            if ev.get("supports"):
                correlations.append({
                    "type": "evidence",
                    "severity": "warning",
                    "title": "Supporting Evidence",
                    "detail": ev["description"],
                    "action": "",
                })

        overall_health = "online"
        if isinstance(health_raw, dict):
            overall_health = health_raw.get("overall_status", "unknown")

        return {
            "system_identity": system_identity,
            "engineer_assessment": engineer_assessment,
            "deep_dive": deep_dive,
            "anomalies": anomalies,
            "correlations": correlations,
            "collection_summary": {
                "logs_collected": len(self.memory.raw_data.get("check_logs", {}).get("logs", [])),
                "temperatures_read": len(temps_raw),
                "fans_read": len(fans_raw),
                "psus_read": len(psus_raw),
                "dimms_read": len(mem_raw),
                "storage_devices_read": len(storage_raw),
                "network_interfaces_read": len(network_raw),
                "health_status": overall_health,
                "anomalies_found": len(anomalies),
            },
            "log_analysis": {},  # Logs are processed by agent, not duplicated here
            "sensor_analysis": {},
            "error_timeline": [],
        }

    def _build_collected_data(self) -> dict:
        """Build collected_data dict for legacy frontend compatibility."""
        return {
            "temperatures": self.memory.raw_data.get("check_temperatures", {}).get("temperatures", []),
            "fans": self.memory.raw_data.get("check_fans", {}).get("fans", []),
            "power_supplies": self.memory.raw_data.get("check_power_supplies", {}).get("power_supplies", []),
            "memory": self.memory.raw_data.get("check_memory", {}).get("memory", []),
            "storage": self.memory.raw_data.get("check_storage", {}).get("storage_devices", []),
            "network": self.memory.raw_data.get("check_network", {}).get("network_interfaces", []),
            "recent_logs": [],
            "health": self.memory.raw_data.get("check_health", {}).get("health_status"),
            "system_info": (self.memory.raw_data.get("check_system_info", {}).get("server_info")
                           or self.memory.raw_data.get("check_system_info", {}).get("system_info")),
        }

    # ═══════════════════════════════════════════════════════════════════
    # CHAT — Multi-turn conversational interface
    # ═══════════════════════════════════════════════════════════════════

    async def chat(self, message: str, action_level: ActionLevel) -> dict:
        """
        Handle a chat message from the user. The agent decides what to do:
        - If no investigation has run yet, start one
        - If asking a follow-up, answer from working memory
        - If asking to dig deeper, run targeted tools
        - If asking to remediate, propose or execute fixes
        """
        self._chat_history.append({"role": "user", "text": message, "ts": datetime.now(timezone.utc).isoformat()})
        if len(self._chat_history) > 200:
            self._chat_history = self._chat_history[-200:]

        # Guard against empty or whitespace-only messages
        if not message or not message.strip():
            response = {"type": "answer", "message": "I'm here to help! Ask me anything about the server, or describe an issue you'd like me to investigate."}
            response["chat_history"] = self._chat_history[-20:]
            return response

        msg_lower = message.lower().strip()

        # ── Detect intent ──────────────────────────────────────
        intent = self._classify_intent(msg_lower)
        logger.info(f"AgentBrain chat intent: {intent} for message: {message[:80]}")

        response = {}

        if intent == "quick_info":
            # Answer simple server questions from cached data or one quick API call
            answer = await self._answer_quick_info(msg_lower, action_level)
            response = {
                "type": "answer",
                "message": answer,
            }

        elif intent == "server_overview":
            # Quick comprehensive status report
            overview = await self._build_server_overview(action_level)
            response = {
                "type": "answer",
                "message": overview,
            }

        elif intent == "investigate":
            # Start or restart a full investigation
            self._investigation_start = datetime.now(timezone.utc)
            result = await self.investigate(issue=message, action_level=action_level)
            self._investigation_end = datetime.now(timezone.utc)
            self._last_diagnosis = result.get("diagnosis")
            self._last_issue = message
            response = {
                "type": "investigation",
                "message": f"All done! Here's what I found. {self._summarize_diagnosis()}",
                "data": result,
                "metrics": self._build_business_metrics(),
            }

        elif intent == "dig_deeper":
            # Run a targeted tool based on what they want to know more about
            target = self._extract_dig_target(msg_lower)
            result = await self._dig_deeper(target, action_level)
            response = {
                "type": "follow_up",
                "message": result.get("summary", "Here\u2019s what I found \u2014 take a look:"),
                "data": result,
            }

        elif intent == "remediate":
            # Propose remediation plan, wait for approval
            plan = self._propose_remediation()
            response = {
                "type": "remediation_proposal",
                "message": "I\u2019ve put together a remediation plan. Review the steps below and say **\u2018approve\u2019** when you\u2019re ready.",
                "plan": plan,
                "requires_approval": True,
            }

        elif intent == "approve_remediation":
            # Execute the remediation plan
            result = await self._execute_remediation(action_level)
            response = {
                "type": "remediation_result",
                "message": result.get("summary", "Remediation executed."),
                "data": result,
            }

        elif intent == "status":
            # Return current state summary
            response = {
                "type": "status",
                "message": self._build_status_summary(),
                "metrics": self._build_business_metrics(),
            }

        elif intent == "explain":
            # Explain the reasoning or a specific finding
            response = {
                "type": "explanation",
                "message": self._explain(msg_lower),
            }

        elif intent == "part_dispatch":
            # Generate part dispatch recommendation
            recommendation = self._build_part_dispatch()
            response = {
                "type": "follow_up",
                "message": recommendation["message"],
                "data": recommendation,
            }

        elif intent == "monitor":
            # Set up monitoring mode
            recommendation = self._build_monitor_recommendation()
            response = {
                "type": "follow_up",
                "message": recommendation["message"],
                "data": recommendation,
            }

        elif intent == "detail_query":
            # Answer from cached data with granular detail
            detail = self._answer_detail_query(msg_lower)
            response = {
                "type": "follow_up",
                "message": detail,
            }

        elif intent == "greeting":
            _greetings = [
                "Hey! \U0001f44b I'm **Medi-AI-tor**, your AI server diagnostics expert.",
                "Hello there! \U0001f44b I'm **Medi-AI-tor** \u2014 ready to help with your server.",
                "Hi! \U0001f44b **Medi-AI-tor** here \u2014 think of me as your AI server engineer.",
            ]
            import random as _rng
            greeting = _rng.choice(_greetings)
            if self._last_diagnosis:
                greeting += "\n\nI still have data from our last session. Feel free to ask follow-up questions, or describe a new issue."
            elif self.agent.is_connected():
                greeting += "\n\nI'm connected and ready to go! Try **\"give me a server overview\"** to start, or just describe what's happening."
            else:
                greeting += "\n\nConnect to a server using the sidebar, and I'll take it from there."
            response = {"type": "answer", "message": greeting}

        elif intent == "help":
            help_text = """Here's what I can do:

**📊 Quick Info** — Ask about the server model, RAM, CPU, BIOS version, power state, service tag
**🔍 Diagnostics** — Check temperatures, fans, power supplies, storage, network, firmware, BIOS settings, boot order, system logs
**🧪 Investigate** — Describe a problem and I'll form hypotheses, gather evidence, and diagnose the root cause
**🌐 iDRAC** — Check iDRAC network config, users, SSL certificates, job queue, lifecycle controller
**🔧 Remediate** — After an investigation, I can propose and execute fixes (with your approval)
**📋 TSR** — Collect Tech Support Reports for Dell support escalation

**Try these:**
• "Give me a server overview"
• "Check the temperatures"
• "Is my firmware up to date?"
• "Server is overheating and fans are loud"
• "Power supply redundancy lost"
• "Check system logs for errors"

I investigate like a senior Dell engineer — I form hypotheses, run targeted checks, and build an evidence chain to find root cause."""
            response = {"type": "answer", "message": help_text}

        elif intent == "thanks":
            responses = [
                "You're welcome! Happy to help \u2014 let me know if anything else comes up. \U0001f44d",
                "Glad I could help! I'm here whenever you need to troubleshoot. \U0001f60a",
                "Anytime! Feel free to ask more questions about the server.",
                "No problem! That's what I'm here for. \U0001f44d",
            ]
            import random as _rng
            response = {"type": "answer", "message": _rng.choice(responses)}

        elif intent == "about":
            response = {"type": "answer", "message": "I'm **Medi-AI-tor**, a purpose-built AI agent for Dell server diagnostics. I'm not an LLM — I'm a **ReAct reasoning engine** that uses hypothesis-driven investigation to diagnose server issues.\n\nI connect to Dell iDRAC controllers via the Redfish API, collect real telemetry data, decode hardware errors (MCA, PCIe AER), compare firmware against Dell's catalog, and arrive at a root-cause diagnosis with an evidence chain.\n\nI investigate like a senior support engineer would — but in ~30 seconds instead of 45+ minutes."}

        else:
            # General question — answer from working memory context
            response = {
                "type": "answer",
                "message": self._answer_from_context(msg_lower),
            }

        self._chat_history.append({"role": "agent", "text": response.get("message", ""), "ts": datetime.now(timezone.utc).isoformat()})
        if len(self._chat_history) > 200:
            self._chat_history = self._chat_history[-200:]
        response["chat_history"] = self._chat_history[-20:]  # last 20 messages
        return response

    def _classify_intent(self, msg: str) -> str:
        """Classify user message into an intent category."""
        if not msg or not isinstance(msg, str):
            return "general"
        # ── Greetings and meta-conversation (check first) ──
        # Use word-boundary checks to avoid substring false positives (e.g. "sup" in "supply")
        words = set(re.findall(r'\b\w+\b', msg))
        if words & {"hello", "howdy", "greetings"} or msg.strip() in ["hi", "hey", "hi!", "hey!"]:
            return "greeting"
        if any(p in msg for p in ["good morning", "good afternoon", "good evening", "what's up"]):
            return "greeting"

        if any(w in msg for w in ["help", "what can you do", "how do you work", "what are your capabilities",
                                   "how does this work", "what do you do", "guide me", "tutorial",
                                   "how to use", "show me what you can do", "getting started",
                                   "what should i ask", "what should i do first"]):
            return "help"

        if any(w in msg for w in ["thank", "thanks", "thx", "cheers", "appreciate", "great job",
                                   "good job", "nice work", "well done", "awesome", "perfect"]):
            return "thanks"

        if any(w in msg for w in ["who are you", "what are you", "about you", "your name",
                                   "are you an ai", "are you a bot", "are you real"]):
            return "about"

        # Approval of remediation
        if any(w in msg for w in ["approve", "yes fix", "go ahead", "execute fix", "do it", "yes remediate", "apply fix"]):
            if self._last_diagnosis and self._last_diagnosis.get("remediation_steps"):
                return "approve_remediation"

        # Remediation request
        if any(w in msg for w in ["fix it", "remediate", "repair", "resolve it", "auto-heal", "can you fix", "apply the fix"]):
            return "remediate"

        # Server overview / general health check (before detail_query and dig_deeper)
        if any(w in msg for w in ["server overview", "give me an overview", "system overview",
                                   "tell me about this server", "what can you tell me",
                                   "server summary", "system summary", "overall status",
                                   "give me a summary", "quick summary", "quick overview",
                                   "how is the server", "how's the server", "how is my server",
                                   "server report", "system report", "health report",
                                   "full status", "show me everything", "what do we have",
                                   "what is wrong", "what's wrong with", "any problems",
                                   "any issues", "is anything wrong", "health overview"]):
            return "server_overview"
        # Also match just "overview" as a standalone word
        if msg.strip() in ["overview", "status overview", "health check", "report"]:
            return "server_overview"

        # Quick info queries — simple factual questions about the server
        if any(w in msg for w in ["what model", "what server", "which server", "server model",
                                   "what is the model", "what's the model",
                                   "service tag", "serial number", "asset tag",
                                   "what is the service tag", "what's the service tag",
                                   "how much ram", "how much memory", "total memory", "total ram",
                                   "how many cpu", "how many processor", "what cpu", "what processor",
                                   "which cpu", "cpu model", "processor model",
                                   "what os", "which os", "operating system", "what operating",
                                   "bios version", "what bios", "idrac version", "what idrac",
                                   "what's the ip", "what is the ip", "ip address", "idrac ip",
                                   "power state", "is it on", "is the server on", "is it powered",
                                   "is the server powered", "is the server running", "is it running",
                                   "hostname", "what's the hostname", "what is the hostname",
                                   "who made", "manufacturer",
                                   "how many dimm", "how many drives", "how many disk",
                                   "how many nic", "how many network",
                                   "what's the warranty", "warranty status", "prosupport",
                                   "when was it manufactured", "how old is",
                                   "express service code", "esc code",
                                   "which psu", "which power supply", "which drive failed",
                                   "which dimm failed", "which component"]):
            return "quick_info"

        # ── Specific dig-deeper targets (must be BEFORE generic detail_query and status) ──

        # TSR collection
        if any(w in msg for w in ["collect tsr", "export tsr", "tsr", "support report", "tech support report"]):
            return "dig_deeper"

        # BIOS settings check
        if any(w in msg for w in ["bios settings", "check bios", "uefi settings", "c-state", "boot mode", "show bios"]):
            return "dig_deeper"

        # POST code / no-POST
        if any(w in msg for w in ["post code", "no post", "won't post", "check post"]):
            return "dig_deeper"

        # Boot order queries
        if any(w in msg for w in ["boot order", "boot sequence", "boot device", "boot priority",
                                   "what boots first", "pxe boot", "boot from"]):
            return "dig_deeper"

        # iDRAC queries (targeted, not investigation)
        if any(w in msg for w in ["idrac network", "idrac ip", "idrac address", "management ip",
                                   "idrac user", "idrac account", "who has access", "who can log in",
                                   "idrac config", "idrac setting", "bmc"]):
            return "dig_deeper"

        # Lifecycle controller
        if any(w in msg for w in ["lifecycle", "lc status", "lifecycle controller"]):
            return "dig_deeper"

        # Job queue
        if any(w in msg for w in ["job queue", "pending job", "scheduled job", "any jobs",
                                   "running job", "check jobs", "show jobs"]):
            return "dig_deeper"

        # SSL certificate
        if any(w in msg for w in ["certificate", "ssl cert", "tls cert", "cert expir",
                                   "when does the cert"]):
            return "dig_deeper"

        # ── Generic intent checks ──

        # Detail queries — asking for specifics about something already checked
        if any(w in msg for w in ["what are the", "which components", "list the", "show me specific",
                                   "what specific", "which firmware", "what needs", "what components",
                                   "what's outdated", "what is outdated", "need to be updated",
                                   "needs updating", "needs to be updated", "show details",
                                   "give me details", "what components need", "which ones",
                                   "what is out of date", "what's out of date", "show me the details",
                                   "what firmware", "what errors", "what warnings",
                                   "list them out", "list them", "please list", "critical entries",
                                   "warning entries", "critical and warning", "specific error",
                                   "specific firmware"]):
            return "detail_query"

        # Dig deeper
        if any(w in msg for w in ["dig deeper", "more detail", "tell me more", "zoom in", "drill down", "expand on",
                                   "what about the", "check the", "show me the", "look at"]):
            return "dig_deeper"

        # Explain
        if any(w in msg for w in ["why", "explain", "how did you", "what evidence", "reasoning", "how confident"]):
            return "explain"

        # Status check (exclude subsystem-specific status queries)
        if any(w in msg for w in ["status", "summary", "what do you know", "where are we", "metrics", "business value"]):
            if not any(w in msg for w in ["lifecycle", "controller", "lc ", "fan", "boot", "idrac", "certificate",
                                          "storage", "disk", "drive", "network", "nic", "power", "psu",
                                          "memory", "dimm", "temperature", "thermal", "firmware"]):
                return "status"

        # Part dispatch
        if any(w in msg for w in ["dispatch", "replace part", "send part", "need replacement", "part dispatch", "ship part"]):
            return "part_dispatch"

        # Monitor
        if any(w in msg for w in ["monitor", "watch", "keep an eye", "alert me", "notify"]):
            return "monitor"

        # Explicit full investigation request (must be BEFORE error/fan/firmware checks)
        if any(w in msg for w in ["run a full check", "full check", "full scan", "run full", "complete check",
                                   "full system check", "run a check", "scan everything", "check everything"]):
            return "investigate"

        # Fan speed / threshold queries (targeted, not full investigation)
        if any(w in msg for w in ["fan speed", "fan rpm", "fan threshold", "below threshold",
                                   "above threshold", "tell me what the fan", "how fast are the fan",
                                   "are the fans", "check fan", "fan status", "show fan",
                                   "how many fan", "fan health"]):
            return "dig_deeper"

        # Temperature queries (targeted)
        if any(w in msg for w in ["temperature reading", "how hot", "temp reading", "cpu temp",
                                   "inlet temp", "check temp", "temperature status", "show temp",
                                   "thermal status"]):
            return "dig_deeper"

        # Power supply queries (targeted, not full investigation)
        if any(w in msg for w in ["power supply", "power supplie", "psu status", "check power", "check psu",
                                   "power budget", "wattage", "psu health", "power redundancy",
                                   "show power", "power status"]):
            return "dig_deeper"

        # Memory queries (targeted)
        if any(w in msg for w in ["check memory", "dimm status", "ecc error", "memory health",
                                   "check ram", "check dimm", "show memory", "show dimm",
                                   "memory status", "show ram", "how many dimm"]):
            return "dig_deeper"

        # Storage queries (targeted)
        if any(w in msg for w in ["check storage", "check disk", "check drive", "disk health",
                                   "drive status", "storage health", "raid status", "show storage",
                                   "show disk", "show drive", "storage status", "list drive",
                                   "how many drive", "how many disk"]):
            return "dig_deeper"

        # Network queries (targeted)
        if any(w in msg for w in ["check network", "nic status", "link status", "network health",
                                   "check nic", "ethernet status", "show network", "show nic",
                                   "network status", "network interface"]):
            return "dig_deeper"

        # Firmware check (targeted, not full investigation)
        if any(w in msg for w in ["firmware", "up to date", "update check", "check firmware", "firmware stack",
                                   "idrac version", "bios version", "driver version", "outdated"]):
            return "dig_deeper"

        # Error / log queries (targeted log check, not full investigation)
        if any(w in msg for w in ["error", "any error", "system error", "errors in", "check error",
                                   "any issue", "any problem", "what's wrong", "anything wrong",
                                   "check log", "system log", "show log", "event log", "sel log",
                                   "check sel", "show sel", "log entries"]):
            return "dig_deeper"

        # If it looks like a problem description or explicit investigate request
        issue_keywords = list(KEYWORD_HYPOTHESIS_MAP.keys())
        if any(kw in msg for kw in issue_keywords) or any(w in msg for w in ["investigate", "troubleshoot", "diagnose", "analyze"]):
            return "investigate"

        # ── Conversational context: reference to previous response ──
        # (Check BEFORE "no prior investigation" fallback so follow-up questions work)
        if self._chat_history and len(self._chat_history) >= 2:
            last_agent = None
            for h in reversed(self._chat_history):
                if h.get("role") == "agent":
                    last_agent = h.get("text", "").lower()
                    break
            if last_agent:
                # "are those normal?" / "is that ok?" / "is that bad?" — answer from context
                if any(w in msg for w in ["is that normal", "are those normal", "is that ok", "is that bad",
                                          "is that good", "should i worry", "is that a problem",
                                          "what does that mean", "so what", "and?", "meaning?",
                                          "is that a lot", "is that enough", "is that high", "is that low",
                                          "is that too", "that seems", "sounds like", "looks like"]):
                    return "explain"
                # "tell me more" / "more details" about the last topic
                if any(w in msg for w in ["more", "detail", "elaborate", "expand", "continue",
                                          "go on", "keep going", "and then", "what else"]):
                    return "detail_query"
                # "what about X?" after a list was shown
                if msg.startswith("what about") or msg.startswith("how about"):
                    return "dig_deeper"
                # Short affirmative/negative responses
                if msg in ["yes", "no", "ok", "okay", "sure", "yep", "nope", "yeah", "nah"]:
                    return "general"

        # If we have no prior investigation, treat as investigation
        if not self._last_diagnosis:
            return "investigate"

        return "general"

    def _extract_dig_target(self, msg: str) -> str:
        """Extract what subsystem the user wants to dig deeper into."""
        # IMPORTANT: Specific multi-word targets MUST come before generic single-word targets
        # e.g. "idrac network" must match before "network", "boot order" before "boot"
        targets = {
            # Specific targets first (multi-word keywords)
            "idrac_network": ["idrac network", "idrac ip", "idrac address", "management ip", "management network", "bmc ip", "idrac config", "idrac setting"],
            "idrac_users": ["idrac user", "idrac account", "management user", "bmc user", "who has access", "who can log"],
            "idrac_cert": ["certificate", "ssl cert", "tls cert", "cert expir"],
            "boot_order": ["boot order", "boot sequence", "boot device", "boot priority", "what boots first"],
            "lifecycle": ["lifecycle", "lc status", "lifecycle controller", "lc log"],
            "jobs": ["job queue", "pending job", "scheduled job", "task queue", "show jobs", "check jobs", "any jobs"],
            "mca": ["mca", "mce", "machine check", "mcerr", "bank"],
            "pcie": ["pcie", "pci", "slot", "gpu", "hba", "aer"],
            "tsr": ["tsr", "support report", "tech support", "collect report", "escalat"],
            "post": ["post code", "no post", "won't boot", "amber", "no video", "power light", "boot fail"],
            # Generic targets after
            "thermal": ["thermal", "temperature", "temp", "heat", "hot"],
            "fan": ["fan", "cooling", "airflow", "speed", "rpm", "threshold"],
            "power": ["power", "psu", "voltage", "watt"],
            "memory": ["memory", "dimm", "ram", "ecc"],
            "storage": ["storage", "disk", "drive", "raid", "ssd", "hdd"],
            "network": ["network", "nic", "ethernet", "link", "port"],
            "logs": ["log", "sel", "event", "error in the"],
            "cpu": ["cpu", "processor", "ierr"],
            "firmware": ["firmware", "update", "version", "driver", "patch"],
            "bios": ["bios", "uefi", "boot mode", "c-state", "c state", "turbo", "virtualization", "tpm", "bios setting"],
            "error": ["error", "issue", "problem", "wrong", "fault"],
        }
        for target, keywords in targets.items():
            if any(kw in msg for kw in keywords):
                return target
        return "general"

    async def _dig_deeper(self, target: str, action_level: ActionLevel) -> dict:
        """Run targeted investigation on a specific subsystem."""
        tool_map = {
            "thermal": "check_temperatures",
            "fan": "check_fans",
            "power": "check_power_supplies",
            "memory": "check_memory",
            "storage": "check_storage",
            "network": "check_network",
            "logs": "check_logs",
            "error": "check_logs",
            "cpu": "check_system_info",
            "firmware": "check_firmware",
            "pcie": "check_logs",
            "mca": "check_logs",
            "bios": "check_bios",
            "post": "check_post_codes",
            "tsr": "collect_tsr",
            "boot_order": "check_boot_order",
            "idrac_network": "check_idrac_network",
            "idrac_users": "check_idrac_users",
            "lifecycle": "check_lifecycle",
            "jobs": "check_jobs",
            "idrac_cert": "check_idrac_cert",
        }
        tool_name = tool_map.get(target, "check_health")
        tool = AGENT_TOOLS.get(tool_name)
        if not tool:
            return {"summary": f"No tool available for '{target}'."}

        # Use cached data if fresh (< 60s old), otherwise re-fetch
        if self._is_tool_cached(tool_name):
            result = self._get_cached_result(tool_name)
            if result:
                logger.info(f"Using cached data for {tool_name}")
        else:
            result = await self._execute_tool(tool, action_level)

        if result and result.success:
            self._observe(tool, result)
            self._update_hypotheses(tool, result)

            # Build detailed summary
            facts = result.facts
            crit = [f for f in facts if f.status == "critical"]
            warn = [f for f in facts if f.status == "warning"]
            ok = [f for f in facts if f.status in ("ok", "normal")]

            # Firmware-specific clean summary with per-component detail
            if target == "firmware":
                if not crit and not warn:
                    lines = ["✅ **Firmware is up to date.** All components are running current firmware versions."]
                    if ok:
                        lines.append(f"Checked {len(ok)} firmware components — all current.")
                else:
                    lines = [f"**Firmware check**: found {len(result.critical)} critical and {len(result.warnings)} outdated components."]
                    if result.critical:
                        lines.append("")
                        lines.append("🔴 **Critical updates needed:**")
                        for item in result.critical:
                            lines.append(f"  • {item}")
                    if result.warnings:
                        lines.append("")
                        lines.append("🟡 **Outdated components:**")
                        for item in result.warnings:
                            lines.append(f"  • {item}")
                    # Add Dell support link with service tag
                    si = (self.memory.raw_data.get("check_system_info", {}).get("server_info")
                          or self.memory.raw_data.get("check_system_info", {}).get("system_info") or {})
                    tag = si.get("service_tag") or si.get("serial_number", "")
                    if tag and tag != "?" and tag != "Unknown":
                        lines.append("")
                        lines.append(f"📥 **Download updates from Dell Support:**")
                        lines.append(f"  https://www.dell.com/support/home/en-us/product-support/servicetag/{tag}/drivers")
                    lines.append("")
                    lines.append("Ask me to **dig deeper into firmware** or say **fix it** to start remediation.")
            # Error/log-specific clean summary — list each entry on its own line
            elif target in ("error", "logs"):
                if not crit and not warn:
                    lines = ["✅ **No errors found.** System logs are clean — no critical or warning events detected."]
                else:
                    lines = [f"**System log check**: found {len(result.critical)} critical and {len(result.warnings)} warning entries."]
                    if result.critical:
                        lines.append("")
                        lines.append("🔴 **Critical entries:**")
                        for item in result.critical:
                            lines.append(f"  • {item}")
                    if result.warnings:
                        lines.append("")
                        lines.append("🟡 **Warnings:**")
                        for item in result.warnings:
                            lines.append(f"  • {item}")
                    lines.append("")
                    lines.append("Ask **what are the critical entries** or **list the errors** for more detail.")
            # Fan-specific clean summary with RPM and threshold info
            elif target == "fan":
                fan_threshold = 12000  # RPM threshold for concern
                speeds = [f.value for f in facts if f.value and isinstance(f.value, (int, float))]
                avg_rpm = round(sum(speeds) / len(speeds)) if speeds else 0
                max_rpm = max(speeds) if speeds else 0
                if not crit and not warn:
                    lines = [f"✅ **All {len(facts)} fans healthy** — operating well below threshold"]
                    lines.append("")
                    lines.append(f"**Threshold**: {fan_threshold:,} RPM | **Average**: {avg_rpm:,} RPM | **Max**: {max_rpm:,} RPM")
                    lines.append("")
                    for f in facts:
                        rpm_val = f.value if f.value else "N/A"
                        pct = round((f.value / fan_threshold) * 100) if f.value and fan_threshold else 0
                        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
                        lines.append(f"  🟢 **{f.component}**: {rpm_val:,} RPM ({pct}% of threshold) {bar}")
                else:
                    lines = [f"**Fan check**: {len(facts)} fans scanned"]
                    lines.append("")
                    if crit:
                        lines.append(f"🔴 **{len(crit)} failed fans:**")
                        for f in crit:
                            lines.append(f"  • {f.description}")
                    if warn:
                        lines.append(f"🟡 **{len(warn)} warnings:**")
                        for f in warn:
                            lines.append(f"  • {f.description}")
                    if ok:
                        lines.append(f"🟢 {len(ok)} fans healthy")
            # Thermal-specific clean summary
            elif target == "thermal":
                if not crit and not warn:
                    lines = [f"✅ **All temperatures normal** — {len(facts)} sensors within limits"]
                    lines.append("")
                    for f in facts:
                        lines.append(f"  🟢 {f.description}")
                else:
                    lines = [f"**Temperature check**: {len(facts)} sensors scanned"]
                    lines.append("")
                    if crit:
                        lines.append("🔴 **Critical temperatures:**")
                        for f in crit:
                            lines.append(f"  • {f.description}")
                    if warn:
                        lines.append("🟡 **Elevated temperatures:**")
                        for f in warn:
                            lines.append(f"  • {f.description}")
                    if ok:
                        lines.append(f"🟢 {len(ok)} sensors normal")
            else:
                lines = [f"**{target.replace('_', ' ').title()}**: collected {len(facts)} data points."]
                if crit:
                    lines.append(f"🔴 **{len(crit)} critical:**")
                    for f in crit[:5]:
                        lines.append(f"  • {f.description}")
                if warn:
                    lines.append(f"🟡 **{len(warn)} warnings:**")
                    for f in warn[:5]:
                        lines.append(f"  • {f.description}")
                if ok:
                    ok_shown = min(len(ok), 8)
                    lines.append(f"🟢 **{len(ok)} healthy:**")
                    for f in ok[:ok_shown]:
                        lines.append(f"  • {f.description}")
                    if len(ok) > ok_shown:
                        lines.append(f"  • ...and {len(ok) - ok_shown} more")

            return {
                "summary": "\n".join(lines),
                "facts": [f.to_dict() for f in facts],
                "tool_used": tool_name,
                "critical_count": len(crit),
                "warning_count": len(warn),
                "ok_count": len(ok),
                "hypotheses": [
                    {"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)}
                    for h in self.memory.get_active_hypotheses()
                ],
            }
        return {"summary": f"Could not collect {target} data. Tool execution failed."}

    def _propose_remediation(self) -> dict:
        """Build a remediation proposal from the current diagnosis."""
        if not self._last_diagnosis:
            return {"steps": [], "workflow": "", "risk": "unknown", "message": "No investigation has been performed yet."}

        diag = self._last_diagnosis
        steps = diag.get("remediation_steps", [])
        workflow = diag.get("workflow_name", "")

        # Classify risk based on what the steps involve
        risk = "low"
        risky_words = ["restart", "reboot", "reset", "power cycle", "replace", "reseat", "flash", "update"]
        for s in steps:
            if any(w in s.lower() for w in risky_words):
                risk = "medium"
                break

        # Check if any steps require full control
        requires_full_control = any(w in s.lower() for s in steps for w in ["restart", "reboot", "reset", "power cycle", "flash"])

        return {
            "workflow": workflow,
            "steps": steps,
            "risk": risk,
            "root_cause": diag.get("root_cause", ""),
            "confidence": diag.get("confidence", 0),
            "requires_full_control": requires_full_control,
            "safe_steps": [s for s in steps if not any(w in s.lower() for w in risky_words)],
            "risky_steps": [s for s in steps if any(w in s.lower() for w in risky_words)],
        }

    # ═══════════════════════════════════════════════════════════════════
    # QUICK INFO — Answer simple server questions fast
    # ═══════════════════════════════════════════════════════════════════

    async def _answer_quick_info(self, msg: str, action_level: ActionLevel) -> str:
        """Answer simple factual questions about the server from cached data or a single API call."""
        # Try to get system info from cache first, otherwise fetch it
        si = (self.memory.raw_data.get("check_system_info", {}).get("server_info")
              or self.memory.raw_data.get("check_system_info", {}).get("system_info"))

        if not si:
            # Quick fetch — just run system info tool
            tool = AGENT_TOOLS.get("check_system_info")
            if tool:
                result = await self._execute_tool(tool, action_level)
                if result and result.success:
                    self._observe(tool, result)
                    si = self.memory.raw_data.get("check_system_info", {}).get("server_info") or \
                         self.memory.raw_data.get("check_system_info", {}).get("system_info") or {}

        if not si:
            return "I couldn't retrieve server information. Make sure the server is connected."

        model = si.get("model", "Unknown")
        tag = si.get("service_tag") or si.get("serial_number", "Unknown")
        bios_ver = si.get("bios_version") or si.get("firmware_version", "Unknown")
        idrac_ver = si.get("idrac_version", "Unknown")
        hostname = si.get("hostname", "Unknown")
        power_state = si.get("power_state", "Unknown")
        cpu_model = si.get("cpu_model", "Unknown")
        cpu_count = si.get("cpu_count", 0)
        total_mem = si.get("total_memory_gb", 0)
        os_name = si.get("os_name", "")
        os_version = si.get("os_version", "")

        # Determine what the user is asking about
        if any(w in msg for w in ["model", "what server", "which server", "what is this"]):
            lines = [f"This server is a **{model}** (Service Tag: **{tag}**)."]
            if hostname:
                lines.append(f"Hostname: {hostname}")
            lines.append(f"Power State: {power_state}")
            return "\n\n".join(lines)

        if any(w in msg for w in ["service tag", "serial number", "asset tag"]):
            lines = [f"**Service Tag:** {tag}", f"**Model:** {model}"]
            if hostname:
                lines.append(f"**Hostname:** {hostname}")
            return "\n".join(lines)

        if any(w in msg for w in ["express service code", "esc code"]):
            # Convert service tag to express service code (base-36 to decimal)
            try:
                esc = int(tag, 36) if tag and tag != "Unknown" else "N/A"
            except (ValueError, TypeError):
                esc = "N/A"
            return f"**Service Tag:** {tag}\n**Express Service Code:** {esc}"

        if any(w in msg for w in ["how much ram", "how much memory", "total memory", "total ram"]):
            # Also fetch DIMM details if available
            mem_data = self.memory.raw_data.get("check_memory", {}).get("memory", [])
            populated = sum(1 for m in mem_data if m.get("size_gb")) if mem_data else 0
            total_slots = len(mem_data) if mem_data else 0
            lines = [f"**Total Memory:** {total_mem} GB"]
            if mem_data:
                lines.append(f"**DIMMs:** {populated} populated out of {total_slots} slots")
                for m in mem_data[:4]:
                    if m.get("size_gb"):
                        slot = m.get("id", m.get("slot", "?"))
                        lines.append(f"  • {slot}: {m.get('size_gb')}GB {m.get('type','')} {m.get('speed_mhz','')}MHz")
                if populated > 4:
                    lines.append(f"  • ...and {populated - 4} more")
            else:
                lines.append("Say **check memory** for detailed DIMM information.")
            return "\n".join(lines)

        if any(w in msg for w in ["how many cpu", "how many processor", "what cpu", "what processor", "which cpu", "cpu model", "processor model"]):
            return f"**CPU:** {cpu_model}\n**Count:** {cpu_count} processor(s)"

        if any(w in msg for w in ["what os", "which os", "operating system", "what operating"]):
            if os_name:
                return f"**Operating System:** {os_name} {os_version}"
            return "OS information is not available via iDRAC Redfish. The server may not report OS details through the management interface."

        if any(w in msg for w in ["bios version", "what bios"]):
            return f"**BIOS Version:** {bios_ver}\n**Model:** {model}"

        if any(w in msg for w in ["idrac version", "what idrac"]):
            return f"**iDRAC Version:** {idrac_ver}\n**Model:** {model}\n**BIOS:** {bios_ver}"

        if any(w in msg for w in ["ip address", "idrac ip", "what's the ip", "what is the ip"]):
            # Try to get iDRAC network info
            idrac_net = self.memory.raw_data.get("check_idrac_network", {})
            if idrac_net:
                ip = idrac_net.get("IPv4Address", idrac_net.get("ip", "N/A"))
                return f"**iDRAC IP:** {ip}\n\nSay **check iDRAC network** for full network configuration."
            return f"Say **check iDRAC network** to retrieve the management IP address and network configuration."

        if any(w in msg for w in ["power state", "is it on", "is the server on", "is it powered", "is the server powered", "is the server running", "is it running", "powered on"]):
            icon = "🟢" if "on" in power_state.lower() else "🔴" if "off" in power_state.lower() else "🟡"
            return f"{icon} **Power State:** {power_state}"

        if any(w in msg for w in ["hostname", "what's the hostname", "what is the hostname"]):
            return f"**Hostname:** {hostname}"

        if any(w in msg for w in ["who made", "manufacturer"]):
            mfg = si.get("manufacturer", "Dell Inc.")
            return f"**Manufacturer:** {mfg}\n**Model:** {model}"

        if any(w in msg for w in ["how many dimm"]):
            mem_data = self.memory.raw_data.get("check_memory", {}).get("memory", [])
            if mem_data:
                populated = sum(1 for m in mem_data if m.get("size_gb"))
                return f"**DIMM Slots:** {len(mem_data)} total, {populated} populated\n**Total RAM:** {total_mem} GB"
            return f"**Total RAM:** {total_mem} GB. Say **check memory** for detailed DIMM slot information."

        if any(w in msg for w in ["how many drives", "how many disk"]):
            stor_data = self.memory.raw_data.get("check_storage", {}).get("storage_devices", [])
            if stor_data:
                return f"**Storage Devices:** {len(stor_data)} drive(s) detected. Say **check storage** for details."
            return "Say **check storage** to scan all physical and virtual drives."

        if any(w in msg for w in ["how many nic", "how many network"]):
            net_data = self.memory.raw_data.get("check_network", {}).get("network_interfaces", [])
            if net_data:
                return f"**Network Interfaces:** {len(net_data)} NIC(s) detected. Say **check network** for details."
            return "Say **check network** to scan all network interfaces."

        if any(w in msg for w in ["warranty", "prosupport"]):
            return f"Warranty status is not available via Redfish API. Check Dell's support site with **Service Tag: {tag}** at https://www.dell.com/support"

        # Which component failed — answer from cached facts
        if any(w in msg for w in ["which psu", "which power supply"]):
            psu_data = self.memory.raw_data.get("check_power_supplies", {}).get("power_supplies", [])
            if psu_data:
                lines = ["**Power Supply Status:**"]
                for p in psu_data:
                    pid = p.get("id", "?")
                    status = p.get("status", "?")
                    watts = p.get("power_watts", "?")
                    is_ok = "ok" in str(status).lower()
                    icon = "🟢" if is_ok else "🔴"
                    lines.append(f"  {icon} **{pid}**: {status} ({watts}W)")
                return "\n".join(lines)
            return "Say **check power supplies** to scan PSU status."

        if any(w in msg for w in ["which drive failed", "which disk"]):
            stor_data = self.memory.raw_data.get("check_storage", {}).get("storage_devices", [])
            if stor_data:
                failed = [d for d in stor_data if "ok" not in str(d.get("status", "")).lower()]
                if failed:
                    lines = [f"**{len(failed)} drive(s) with issues:**"]
                    for d in failed:
                        lines.append(f"  🔴 {d.get('name','?')}: {d.get('status','?')} ({d.get('capacity_gb',0)} GB {d.get('type','')})")
                    return "\n".join(lines)
                return "✅ All storage drives are healthy."
            return "Say **check storage** to scan drive health."

        if any(w in msg for w in ["which dimm", "which memory"]):
            mem_data = self.memory.raw_data.get("check_memory", {}).get("memory", [])
            if mem_data:
                failed = [m for m in mem_data if "ok" not in str(m.get("status", "")).lower() and m.get("size_gb")]
                if failed:
                    lines = [f"**{len(failed)} DIMM(s) with issues:**"]
                    for m in failed:
                        lines.append(f"  🔴 {m.get('id','?')}: {m.get('status','?')} ({m.get('size_gb',0)} GB)")
                    return "\n".join(lines)
                return "✅ All memory DIMMs are healthy."
            return "Say **check memory** to scan DIMM health."

        if any(w in msg for w in ["which component"]):
            # Show all components with issues
            crit_facts = self.memory.get_facts_by_status("critical")
            if crit_facts:
                lines = [f"**Components with issues ({len(crit_facts)}):**"]
                for f in crit_facts[:8]:
                    lines.append(f"  🔴 {getattr(f, 'description', str(f))}")
                return "\n".join(lines)
            return "✅ No component issues detected. Run an **overview** for a full check."

        # Default: return a comprehensive server identity card
        lines = [f"**{model}**", ""]
        lines.append(f"**Service Tag:** {tag}")
        if hostname:
            lines.append(f"**Hostname:** {hostname}")
        lines.append(f"**Power State:** {power_state}")
        lines.append(f"**CPU:** {cpu_model} × {cpu_count}")
        lines.append(f"**Memory:** {total_mem} GB")
        lines.append(f"**BIOS:** {bios_ver}")
        lines.append(f"**iDRAC:** {idrac_ver}")
        if os_name:
            lines.append(f"**OS:** {os_name} {os_version}")
        lines.append("")
        lines.append("Ask about any component, describe an issue, or say **help** for all options.")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════
    # SERVER OVERVIEW — Comprehensive single-shot status report
    # ═══════════════════════════════════════════════════════════════════

    async def _build_server_overview(self, action_level: ActionLevel) -> str:
        """Build a comprehensive server overview by running key read-only checks."""
        lines = []

        # Run core tools sequentially (iDRAC throttles concurrent Redfish requests)
        # but use cache for tools that were recently executed
        core_tools = ["check_system_info", "check_health", "check_temperatures", "check_fans",
                       "check_power_supplies", "check_memory", "check_storage", "check_network"]

        for tool_name in core_tools:
            tool = AGENT_TOOLS.get(tool_name)
            if not tool:
                continue

            # Use cached data if fresh
            if self._is_tool_cached(tool_name):
                result = self._get_cached_result(tool_name)
                if result:
                    # Re-observe cached results to ensure facts are in memory for grid
                    self._observe(tool, result)
                    await self._stream("action_result", result.to_dict())
                    continue

            result = await self._execute_tool(tool, action_level)
            if result and result.success:
                self._observe(tool, result)
                await self._stream("action_result", result.to_dict())

        # Build the overview from collected data
        si = (self.memory.raw_data.get("check_system_info", {}).get("server_info")
              or self.memory.raw_data.get("check_system_info", {}).get("system_info") or {})

        model = si.get("model", "Unknown Server")
        tag = si.get("service_tag") or si.get("serial_number", "?")
        bios_ver = si.get("bios_version", "?")
        idrac_ver = si.get("idrac_version", "?")
        hostname = si.get("hostname") or None
        power_state = si.get("power_state", "?")
        cpu_model = si.get("cpu_model", "?")
        cpu_count = si.get("cpu_count", 0)
        total_mem = si.get("total_memory_gb", 0)

        # Header — clean, no empty fields
        header_parts = [f"Service Tag: **{tag}**"]
        if hostname:
            header_parts.append(f"Host: {hostname}")
        header_parts.append(f"Power: {power_state}")
        
        lines.append(f"**{model}** — Server Overview")
        lines.append(" | ".join(header_parts))
        lines.append(f"CPU: {cpu_model} × {cpu_count} | RAM: {total_mem} GB | BIOS: {bios_ver} | iDRAC: {idrac_ver}")
        lines.append("")

        # Component health summary
        lines.append(self._build_component_health_summary() or "No component data collected.")
        lines.append("")

        # Quick stats — filter out noise
        crit_facts = self.memory.get_facts_by_status("critical")
        warn_facts = self.memory.get_facts_by_status("warning")
        
        # Filter out noisy warnings (NICs with OK status showing as warning due to link-down)
        warn_facts = [f for f in warn_facts if not (
            hasattr(f, 'description') and 'status=OK' in getattr(f, 'description', '')
        )]

        if crit_facts:
            label = "Critical Issue" if len(crit_facts) == 1 else "Critical Issues"
            lines.append(f"🔴 **{len(crit_facts)} {label}:**")
            for f in crit_facts[:5]:
                desc = getattr(f, 'description', str(f))
                lines.append(f"  • {desc}")
            if len(crit_facts) > 5:
                lines.append(f"  • ...and {len(crit_facts) - 5} more")
            lines.append("")

        if warn_facts:
            label = "Warning" if len(warn_facts) == 1 else "Warnings"
            lines.append(f"🟡 **{len(warn_facts)} {label}:**")
            for f in warn_facts[:5]:
                desc = getattr(f, 'description', str(f))
                lines.append(f"  • {desc}")
            if len(warn_facts) > 5:
                lines.append(f"  • ...and {len(warn_facts) - 5} more")
            lines.append("")

        if not crit_facts and not warn_facts:
            lines.append("✅ **All subsystems healthy** — no issues detected.")
            lines.append("")

        # Compact suggestion
        lines.append("Ask about any component, or describe an issue to investigate.")

        return "\n".join(lines)

    async def _execute_remediation(self, action_level: ActionLevel) -> dict:
        """Execute the approved remediation plan step-by-step."""
        plan = self._propose_remediation()
        results = []

        if not plan.get("steps"):
            return {"summary": "No remediation steps available.", "results": []}

        # Map remediation steps to executable commands
        step_commands = {
            "check fan": "get_fans",
            "check temperature": "get_temperature_sensors",
            "check power": "get_power_supplies",
            "check memory": "get_memory",
            "check storage": "get_storage_devices",
            "collect tsr": "export_tsr",
            "health check": "health_check",
            "run diagnostics": "run_diagnostics",
        }

        for i, step in enumerate(plan["steps"]):
            step_lower = step.lower()
            # Find matching command
            cmd = None
            for pattern, command in step_commands.items():
                if pattern in step_lower:
                    cmd = command
                    break

            step_result = {"step": i + 1, "description": step, "status": "noted"}

            if cmd:
                try:
                    exec_result = await self.agent.execute_action(
                        action_level=action_level, command=cmd, parameters={}
                    )
                    step_result["status"] = "executed"
                    step_result["command"] = cmd
                    step_result["success"] = True
                    logger.info(f"Remediation step {i+1} executed: {cmd}")
                except Exception as e:
                    step_result["status"] = "failed"
                    step_result["error"] = str(e)
                    step_result["success"] = False
                    logger.error(f"Remediation step {i+1} failed: {e}")
            else:
                step_result["status"] = "manual"
                step_result["note"] = "Requires manual intervention"

            results.append(step_result)
            self._remediation_log.append(step_result)

        executed = sum(1 for r in results if r.get("success"))
        manual = sum(1 for r in results if r["status"] == "manual")
        failed = sum(1 for r in results if r["status"] == "failed")

        summary = f"Remediation complete: {executed} steps executed, {manual} require manual action"
        if failed:
            summary += f", {failed} failed"

        return {
            "summary": summary,
            "results": results,
            "executed_count": executed,
            "manual_count": manual,
            "failed_count": failed,
            "workflow": plan.get("workflow", ""),
        }

    def _summarize_diagnosis(self) -> str:
        """One-line summary of the current diagnosis."""
        if not self._last_diagnosis:
            return "No investigation performed yet."
        d = self._last_diagnosis
        confidence = d.get('confidence', 0)
        crit = d.get('critical_findings', [])
        warn = d.get('warning_findings', [])
        root = d.get('root_cause', '?')
        evidence = d.get('evidence_chain', [])
        category = d.get('category', 'system')

        # Determine what the user originally asked about
        issue_category_map = {
            "thermal": ["hot", "overheat", "thermal", "temperature", "fan", "loud", "cooling", "throttle", "heat"],
            "power": ["power", "shutdown", "psu", "voltage"],
            "memory": ["memory", "ram", "dimm", "ecc", "blue screen", "bsod"],
            "storage": ["disk", "drive", "raid", "storage", "degraded"],
            "network": ["network", "nic", "link", "connectivity"],
            "firmware": ["firmware", "bios", "idrac", "update"],
            "cpu": ["cpu", "ierr", "crash", "hang", "mce", "mca"],
        }
        asked_about = None
        if self._last_issue:
            issue_lower = self._last_issue.lower()
            for cat, keywords in issue_category_map.items():
                if any(kw in issue_lower for kw in keywords):
                    asked_about = cat
                    break

        # If the user asked about one thing (e.g. thermal) but top hypothesis is a different category,
        # lead with "no <asked> issues" then mention what was actually found
        if asked_about and asked_about != category:
            parts = [f"Investigated \"{self._last_issue}\" — **no {asked_about} issues detected**."]
            if crit:
                parts.append(f"However, {len(crit)} other findings were noted ({category}: {root}). Ask follow-up questions to explore.")
            elif warn:
                parts.append(f"{len(warn)} minor warnings detected but nothing critical.")
            else:
                parts.append("All subsystems appear healthy.")
            # Add component health grid
            component_status = self._build_component_health_summary()
            if component_status:
                return " ".join(parts) + "\n\n" + component_status
            return " ".join(parts)

        # Check if the critical findings are actually related to the top hypothesis category
        category_keywords = {
            "thermal": ["thermal", "temperature", "fan", "heat", "cooling"],
            "power": ["power", "psu", "voltage"],
            "memory": ["memory", "dimm", "ecc", "ram"],
            "storage": ["storage", "disk", "drive", "raid"],
            "network": ["network", "nic", "link"],
            "firmware": ["firmware", "bios", "idrac", "update"],
            "cpu": ["cpu", "processor", "ierr", "mce"],
        }
        relevant_keywords = category_keywords.get(category, [])
        relevant_crit = [f for f in crit if any(kw in f.get("description", "").lower() for kw in relevant_keywords)] if relevant_keywords else crit

        # If the top hypothesis has no relevant critical findings, the reported issue wasn't found
        if not relevant_crit:
            parts = []
            if asked_about:
                # User asked about a specific category and nothing was found for it
                parts.append(f"Investigated \"{self._last_issue}\" — **no {category} issues detected**.")
            elif self._last_issue:
                # General query — show overall health
                parts.append(f"**System check complete.**")
            else:
                parts.append(f"No {category} issues detected.")
            if crit:
                parts.append(f"Found {len(crit)} findings to review — ask follow-up questions for detail.")
            elif warn:
                parts.append(f"{len(warn)} minor warnings detected but nothing critical.")
            else:
                parts.append("All subsystems appear healthy.")
            # Add component health grid
            component_status = self._build_component_health_summary()
            if component_status:
                return " ".join(parts) + "\n\n" + component_status
            return " ".join(parts)

        # Real problem detected with relevant critical findings
        parts = [f"Root cause: **{root}** ({confidence}% confidence)."]

        # Add component-by-component health summary
        component_status = self._build_component_health_summary()
        if component_status:
            parts.append("")
            parts.append(component_status)

        if crit:
            parts.append("")
            parts.append(f"🔴 **{len(crit)} critical findings** — ask for details on any subsystem.")
        if warn:
            parts.append(f"🟡 {len(warn)} warnings noted.")

        return "\n".join(parts)

    def _build_component_health_summary(self) -> str:
        """Build a component-by-component health grid from collected data."""
        lines = []
        # (label, tool_key, data_key, fact_id_patterns)
        components = [
            ("Temperatures", "check_temperatures", "temperatures", ["temp_", "temperature"]),
            ("Fans", "check_fans", "fans", ["fan_"]),
            ("Power Supplies", "check_power_supplies", "power_supplies", ["psu_"]),
            ("Memory (DIMMs)", "check_memory", "memory", ["dimm_", "memory"]),
            ("Storage", "check_storage", "storage_devices", ["storage_", "disk_", "drive_"]),
            ("Network", "check_network", "network_interfaces", ["nic_", "network"]),
            ("Firmware", "check_firmware", "firmware", ["firmware_"]),
            ("System Logs", "check_logs", "logs", ["log_", "mca_", "pcie_"]),
        ]

        for label, tool_key, data_key, fact_patterns in components:
            raw = self.memory.raw_data.get(tool_key, {})
            if not raw:
                continue

            # Count items
            items = raw.get(data_key, [])
            if isinstance(items, dict):
                items = list(items.values()) if items else []
            count = len(items) if isinstance(items, list) else 0

            # Count facts by status using fact ID patterns
            tool_facts = [f for f in self.memory.facts.values()
                          if hasattr(f, 'id') 
                          and any(p in getattr(f, 'id', '') for p in fact_patterns)]
            crit_count = sum(1 for f in tool_facts if getattr(f, 'status', '') == 'critical')
            warn_count = sum(1 for f in tool_facts if getattr(f, 'status', '') == 'warning')

            if crit_count > 0:
                icon = "🔴"
                status_text = f"{crit_count} critical"
                if warn_count:
                    status_text += f", {warn_count} warnings"
            elif warn_count > 0:
                icon = "🟡"
                status_text = f"{warn_count} warnings"
            else:
                icon = "🟢"
                status_text = "All healthy"

            detail = f"{count} checked" if count else "checked"
            lines.append(f"{icon} **{label}**: {status_text} ({detail})")

        if not lines:
            return ""
        return "**Component Health:**\n" + "\n".join(lines)

    def _build_status_summary(self) -> str:
        """Build a comprehensive status summary."""
        lines = []
        if self._last_issue:
            lines.append(f"Last investigation: \"{self._last_issue}\"")
        if self._last_diagnosis:
            d = self._last_diagnosis
            lines.append(f"Diagnosis: {d.get('root_cause', 'N/A')} — {d.get('confidence', 0)}% confidence")
            lines.append(f"Category: {d.get('category', 'N/A')}")
            lines.append(f"Evidence: {len(d.get('evidence_chain', []))} items")
            lines.append(f"Tools used: {', '.join(d.get('tools_used', []))}")
            lines.append(f"Ruled out: {len(d.get('ruled_out', []))} hypotheses")
        if self.memory.facts:
            crit = len(self.memory.get_facts_by_status("critical"))
            warn = len(self.memory.get_facts_by_status("warning"))
            lines.append(f"Known facts: {len(self.memory.facts)} ({crit} critical, {warn} warnings)")
        if self._remediation_log:
            lines.append(f"Remediation actions taken: {len(self._remediation_log)}")
        return "\n".join(lines) if lines else "No data collected yet. Describe your issue to begin."

    def _explain(self, msg: str) -> str:
        """Explain reasoning or specific findings, with conversational context awareness."""
        # Direct "why" questions about health/status — answer from findings, not context
        if any(w in msg for w in ["why is the health", "why is it critical", "why is the server critical",
                                   "what caused", "root cause", "main issue", "main problem"]):
            crit_facts = self.memory.get_facts_by_status("critical")
            if crit_facts:
                lines = [f"The server health is **Critical** because of these findings:"]
                for f in crit_facts[:5]:
                    lines.append(f"  🔴 {getattr(f, 'description', str(f))}")
                if self._last_diagnosis:
                    lines.append(f"\n**Root cause:** {self._last_diagnosis.get('root_cause', 'Run an investigation for diagnosis')}")
                else:
                    lines.append(f"\nSay **\"investigate\"** for a full root cause analysis.")
                return "\n".join(lines)
            return "The server health appears normal. Run an **overview** to check all components."

        # Check if this is a conversational follow-up (e.g. "is that a lot?" after RAM answer)
        if self._chat_history and len(self._chat_history) >= 2:
            last_agent_text = ""
            for h in reversed(self._chat_history):
                if h.get("role") == "agent":
                    last_agent_text = h.get("text", "")
                    break
            
            if last_agent_text:
                # Context-aware explanations based on what was just discussed
                lt = last_agent_text.lower()
                
                # RAM context
                if "memory" in lt or "ram" in lt or "gb" in lt or "dimm" in lt:
                    mem_gb = 0
                    import re as _re
                    m = _re.search(r'(\d+)\s*gb', lt)
                    if m:
                        mem_gb = int(m.group(1))
                    if mem_gb >= 256:
                        return f"**{mem_gb} GB is substantial** — that's a high-end server configuration, suitable for large databases, in-memory analytics, virtualization with many VMs, or high-performance computing workloads."
                    elif mem_gb >= 64:
                        return f"**{mem_gb} GB is a solid amount** — typical for mid-range server workloads including virtualization, moderate databases, and application servers."
                    elif mem_gb > 0:
                        return f"**{mem_gb} GB is relatively modest** for a server. Depending on the workload, you may want to consider expanding memory capacity."
                
                # Temperature context
                if "temperature" in lt or "°c" in lt or "temp" in lt:
                    return "For Dell servers, these temperature ranges are typical:\n\n• **Inlet**: Normal < 35°C, Warning > 38°C, Critical > 42°C\n• **CPU**: Normal < 70°C, Warning > 85°C, Critical > 95°C\n• **Exhaust**: Normal < 65°C, Warning > 75°C, Critical > 80°C\n\nIf any sensor is in the warning or critical range, check airflow, fan operation, and ambient room temperature."
                
                # Fan context  
                if "fan" in lt or "rpm" in lt:
                    return "Fan speeds vary by server model and thermal load. For Dell PowerEdge/PowerScale servers:\n\n• **Idle**: 3,000-8,000 RPM (quiet)\n• **Normal load**: 8,000-15,000 RPM\n• **High load / hot**: 15,000-25,000 RPM (loud)\n\nConsistently high fan speeds may indicate thermal issues. Low RPM with high temperatures could mean a fan failure."
                
                # Power context
                if "psu" in lt or "power supply" in lt or "power" in lt:
                    return "Dell servers use redundant power supplies for high availability. Key things to know:\n\n• **N+1 redundancy**: Server runs fine on one PSU if the other fails\n• **Redundancy lost** = one PSU is offline — the server is still running but not protected\n• **Both PSUs OK** = normal, healthy configuration\n• PSU failures are a common cause of unplanned outages — replace failed PSUs promptly"
                
                # Firmware context
                if "firmware" in lt or "bios" in lt or "idrac" in lt:
                    return "Firmware versions should be kept current for security and stability:\n\n• **BIOS** updates fix CPU microcode vulnerabilities and stability issues\n• **iDRAC** updates improve management capabilities and fix security flaws\n• **NIC/RAID/Drive** firmware can fix performance bugs and compatibility issues\n\nDell recommends using the Dell Repository Manager or iDRAC web UI for updates. Critical updates should be applied during the next maintenance window."
                
                # Generic "is that normal/ok" with no specific topic
                return f"Based on the data I've collected, this appears to be within normal parameters for this server model. If you want me to do a deeper analysis, say **\"run full investigation\"** and I'll check everything systematically."

        if not self._last_diagnosis:
            return "I haven't run a full investigation yet. Tell me the issue and I'll investigate, or say **\"help\"** to see what I can do."

        d = self._last_diagnosis
        lines = []

        if "confidence" in msg or "how confident" in msg:
            lines.append(f"My confidence is {d.get('confidence', 0)}% based on {len(d.get('evidence_chain', []))} pieces of evidence.")
            for ev in d.get("evidence_chain", []):
                icon = "✅" if ev.get("supports") else "❌"
                lines.append(f"  {icon} {ev['description']} (strength: {ev['strength']})")

        elif "ruled out" in msg or "why not" in msg:
            ruled = d.get("ruled_out", [])
            if ruled:
                lines.append(f"I ruled out {len(ruled)} hypotheses:")
                for r in ruled:
                    lines.append(f"  ❌ {r['description']}")
            else:
                lines.append("No hypotheses have been definitively ruled out.")

        elif "evidence" in msg:
            for ev in d.get("evidence_chain", []):
                icon = "✅" if ev.get("supports") else "❌"
                lines.append(f"{icon} {ev['description']} — strength: {ev['strength']}, supports: {ev['supports']}")

        else:
            # General explanation
            lines.append(f"I investigated \"{self._last_issue}\" using {len(d.get('tools_used', []))} tools.")
            lines.append(f"Diagnosis: {d.get('root_cause', 'N/A')} ({d.get('confidence', 0)}% confidence)")
            for n in d.get("narrative", []):
                lines.append(f"  {n}")

        return "\n".join(lines)

    def _answer_from_context(self, msg: str) -> str:
        """Answer a general question using working memory context."""
        if not self.memory.facts:
            return "I haven't collected any data yet. Try one of these:\n\n• **\"Give me a server overview\"** — Quick health check of all components\n• **\"Check temperatures\"** — Read all thermal sensors\n• **\"Check system logs\"** — Look for errors in the SEL\n• Or describe an issue like **\"server is overheating\"** and I'll investigate"

        # "what should I do" — give actionable advice based on findings
        if any(w in msg for w in ["what should", "what do i do", "next step", "recommend", "suggestion", "advice"]):
            crit = self.memory.get_facts_by_status("critical")
            if crit:
                lines = [f"Based on **{len(crit)} critical findings**, here's what I recommend:"]
                for i, f in enumerate(crit[:3], 1):
                    desc = getattr(f, 'description', str(f))
                    lines.append(f"  {i}. Address: {desc}")
                if self._last_diagnosis and self._last_diagnosis.get("remediation_steps"):
                    lines.append(f"\nSay **\"can you fix it\"** and I'll propose a remediation plan.")
                else:
                    lines.append(f"\nDescribe the main issue and I'll investigate and propose a fix.")
                return "\n".join(lines)
            return "✅ No critical issues found. The server appears healthy. Say **overview** for a full status check."

        # Search facts for relevant info
        relevant = []
        words = re.findall(r'\w+', msg)
        for fact in self.memory.facts.values():
            desc = getattr(fact, 'description', str(fact))
            if any(w in desc.lower() for w in words if len(w) > 2):
                relevant.append(fact)

        if relevant:
            lines = ["Based on the data I've collected:"]
            for f in relevant[:8]:
                status = getattr(f, 'status', 'ok')
                desc = getattr(f, 'description', str(f))
                icon = "🔴" if status == "critical" else "🟡" if status == "warning" else "🟢"
                lines.append(f"  {icon} {desc}")
            return "\n".join(lines)

        # If we have a last diagnosis, summarize it
        if self._last_diagnosis:
            d = self._last_diagnosis
            return f"My last investigation found: **{d.get('root_cause', 'N/A')}** ({d.get('confidence', 0)}% confidence).\n\nSay **\"explain\"** for the reasoning chain, or **\"can you fix it\"** for remediation."

        return f"I have {len(self.memory.facts)} data points but I'm not sure what you're asking. Try:\n\n• **\"overview\"** — full server health check\n• **\"check temps\"** — temperature sensors\n• **\"check logs\"** — system event log\n• **\"help\"** — see all my capabilities"

    def _answer_detail_query(self, msg: str) -> str:
        """Answer detail queries from cached investigation data — no re-running tools."""
        # Detect what subsystem the user is asking about
        topic = "general"
        if any(w in msg for w in ["firmware", "update", "outdated", "version", "component"]):
            topic = "firmware"
        elif any(w in msg for w in ["fan", "cooling", "rpm"]):
            topic = "fan"
        elif any(w in msg for w in ["temp", "thermal", "heat", "hot"]):
            topic = "thermal"
        elif any(w in msg for w in ["memory", "dimm", "ram", "ecc"]):
            topic = "memory"
        elif any(w in msg for w in ["storage", "disk", "drive", "raid"]):
            topic = "storage"
        elif any(w in msg for w in ["power", "psu", "voltage"]):
            topic = "power"
        elif any(w in msg for w in ["network", "nic", "link", "ethernet"]):
            topic = "network"
        elif any(w in msg for w in ["error", "log", "event", "critical", "warning", "entries", "sel"]):
            topic = "logs"

        # Pull from cached raw_data
        if topic == "firmware":
            fw_data = self.memory.raw_data.get("check_firmware", {})
            if not fw_data:
                return "I haven't checked firmware yet. Say **check firmware** and I'll scan all components."
            # Use the parsed results from knowledge_base
            from core.knowledge_base import check_firmware_against_catalog, get_firmware_summary
            fw_list = fw_data.get("firmware", fw_data.get("firmware_inventory", fw_data.get("data", [])))
            if isinstance(fw_list, dict):
                fw_list = fw_list.get("firmware", [])
            if not fw_list:
                return "Firmware inventory data is unavailable. Try saying **check firmware** to re-scan."
            results = check_firmware_against_catalog(fw_list)
            summary = get_firmware_summary(results)

            lines = [f"**Firmware Inventory Detail** — {summary['total_components']} components scanned"]
            lines.append("")

            if summary.get("critical_list"):
                lines.append("🔴 **Critical Updates Required:**")
                for item in summary["critical_list"]:
                    lines.append(f"  • **{item['component']}** — installed: `{item['installed']}`, latest: `{item['latest']}`")
                    if item.get("notes"):
                        lines.append(f"    _{item['notes']}_")
                lines.append("")

            if summary.get("outdated_list"):
                non_critical = [i for i in summary["outdated_list"] if not i.get("critical")]
                if non_critical:
                    lines.append("🟡 **Outdated (non-critical):**")
                    for item in non_critical:
                        lines.append(f"  • **{item['component']}** — installed: `{item['installed']}`, latest: `{item['latest']}`")
                    lines.append("")

            current = summary.get("up_to_date", 0)
            if current:
                lines.append(f"✅ **{current} components are up to date**")
                # Show a few current ones
                current_items = [r for r in results if getattr(r, 'status', '') == 'current' or (isinstance(r, dict) and r.get('status') == 'current')]
                for item in current_items[:3]:
                    name = item.get("component", "") if isinstance(item, dict) else getattr(item, "component", "")
                    ver = item.get("installed", "") if isinstance(item, dict) else getattr(item, "installed_version", "")
                    if name:
                        lines.append(f"  • {name}: `{ver}`")
                if len(current_items) > 3:
                    lines.append(f"  • ...and {len(current_items) - 3} more")

            lines.append("")
            lines.append(f"Overall firmware health: **{summary.get('health_score', '?')}%**")
            return "\n".join(lines)

        elif topic == "logs":
            log_data = self.memory.raw_data.get("check_logs", {})
            if not log_data:
                # Fall back: check if we have any critical/warning facts from ANY tool
                all_crit = [f for f in self.memory.facts
                            if not isinstance(f, str) and getattr(f, 'status', '') == 'critical']
                all_warn = [f for f in self.memory.facts
                            if not isinstance(f, str) and getattr(f, 'status', '') == 'warning']
                if all_crit or all_warn:
                    lines = ["**Known Issues from Investigation:**"]
                    lines.append("")
                    if all_crit:
                        lines.append(f"🔴 **Critical ({len(all_crit)}):**")
                        for f in all_crit[:10]:
                            desc = getattr(f, 'description', str(f))
                            comp = getattr(f, 'component', '')
                            lines.append(f"  • {desc}" + (f" ({comp})" if comp else ""))
                        lines.append("")
                    if all_warn:
                        lines.append(f"🟡 **Warnings ({len(all_warn)}):**")
                        for f in all_warn[:10]:
                            desc = getattr(f, 'description', str(f))
                            comp = getattr(f, 'component', '')
                            lines.append(f"  • {desc}" + (f" ({comp})" if comp else ""))
                    lines.append("")
                    lines.append("Say **check for errors** to scan system logs for more detail.")
                    return "\n".join(lines)
                return "I haven't checked system logs yet. Say **check for errors** and I'll scan the logs."

            # Pull decoded errors from raw_data
            mca_decoded = log_data.get("mca_decoded", [])
            pcie_decoded = log_data.get("pcie_decoded", [])
            raw_logs = log_data.get("logs", [])

            # Get critical and warning facts from memory
            log_facts_crit = [f for f in self.memory.facts
                              if not isinstance(f, str) and getattr(f, 'component', '') in ('SEL', 'Logs')
                              and getattr(f, 'status', '') == 'critical']
            log_facts_warn = [f for f in self.memory.facts
                              if not isinstance(f, str) and getattr(f, 'component', '') in ('SEL', 'Logs')
                              and getattr(f, 'status', '') == 'warning']

            lines = ["**System Log Detail**"]
            lines.append("")

            if mca_decoded:
                lines.append(f"🧠 **MCA (Machine Check) Errors** — {len(mca_decoded)} decoded:")
                for mca in mca_decoded:
                    desc = mca.get("description", "Unknown MCA error")
                    sev = mca.get("severity", "warning")
                    action = mca.get("action", "")
                    comp = mca.get("likely_component", "")
                    icon = "🔴" if sev == "critical" else "🟡"
                    lines.append(f"  {icon} **{desc}**")
                    if comp:
                        lines.append(f"    Component: {comp}")
                    if action:
                        lines.append(f"    Action: {action}")
                lines.append("")

            if pcie_decoded:
                lines.append(f"🔌 **PCIe Errors** — {len(pcie_decoded)} decoded:")
                for pcie in pcie_decoded:
                    desc = pcie.get("description", "Unknown PCIe error")
                    sev = pcie.get("severity", "warning")
                    action = pcie.get("action", "")
                    device = pcie.get("device_info", "")
                    cause = pcie.get("likely_cause", "")
                    icon = "🔴" if sev == "critical" else "🟡"
                    lines.append(f"  {icon} **{desc}**")
                    if device:
                        lines.append(f"    Device: {device}")
                    if cause:
                        lines.append(f"    Cause: {cause}")
                    if action:
                        lines.append(f"    Action: {action}")
                lines.append("")

            # Show raw critical log messages
            if log_facts_crit:
                crit_msgs = [f for f in log_facts_crit if getattr(f, 'metric', '') == 'log_entry']
                if crit_msgs:
                    lines.append(f"📋 **Critical Log Entries** — {len(crit_msgs)} entries:")
                    for f in crit_msgs[:10]:
                        lines.append(f"  🔴 {getattr(f, 'description', str(f))}")
                    lines.append("")

            if not mca_decoded and not pcie_decoded and not log_facts_crit:
                lines.append("✅ No critical or warning log entries found.")

            return "\n".join(lines)

        elif topic in ("fan", "thermal"):
            key = "check_fans" if topic == "fan" else "check_temperatures"
            label = "Fans" if topic == "fan" else "Temperatures"
            raw = self.memory.raw_data.get(key, {})
            if not raw:
                return f"I haven't checked {topic} data yet. Say **check {topic}** and I'll scan."
            items = raw.get("fans" if topic == "fan" else "temperatures", [])
            if not items:
                return f"No {topic} data available."
            lines = [f"**{label} Detail** — {len(items)} sensors"]
            lines.append("")
            for item in items:
                name = item.get("Name", item.get("name", item.get("MemberId", "?")))
                reading = item.get("Reading", item.get("reading", item.get("CurrentReading", "?")))
                units = item.get("ReadingUnits", item.get("units", ""))
                status = item.get("Status", {})
                health = status.get("Health", item.get("health", "OK")) if isinstance(status, dict) else status
                state = status.get("State", item.get("state", "")) if isinstance(status, dict) else ""
                icon = "🟢" if health in ("OK", "ok", None) else "🟡" if health == "Warning" else "🔴"
                unit_str = " RPM" if "rpm" in str(units).lower() or topic == "fan" else "°C" if topic == "thermal" else ""
                lines.append(f"  {icon} **{name}**: {reading}{unit_str} — {health or 'OK'}")
            return "\n".join(lines)

        # Generic: search facts
        relevant_facts = []
        for fact in self.memory.facts:
            desc = getattr(fact, 'description', str(fact)) if not isinstance(fact, str) else fact
            status = getattr(fact, 'status', 'ok') if not isinstance(fact, str) else 'ok'
            if status in ("critical", "warning") or topic == "general":
                relevant_facts.append(fact)

        if relevant_facts:
            lines = ["Here's what I've found:"]
            for f in relevant_facts[:12]:
                if isinstance(f, str):
                    lines.append(f"  🔵 {f}")
                else:
                    status = getattr(f, 'status', 'ok')
                    desc = getattr(f, 'description', str(f))
                    comp = getattr(f, 'component', '')
                    icon = "🔴" if status == "critical" else "🟡" if status == "warning" else "🟢"
                    lines.append(f"  {icon} {desc} ({comp})")
            return "\n".join(lines)

        return "I don't have detailed data on that yet. Try asking me to check a specific subsystem like firmware, fans, temperatures, memory, or storage."

    def _build_part_dispatch(self) -> dict:
        """Build part dispatch recommendation based on investigation evidence."""
        if not self._last_diagnosis:
            return {"message": "I need to investigate first before recommending a part dispatch. Describe the issue and I'll diagnose it."}

        diag = self._last_diagnosis
        root_cause = diag.get("root_cause", "")
        confidence = diag.get("confidence", 0)
        category = diag.get("category", "")
        evidence = diag.get("evidence_chain", [])

        # Part mapping based on diagnosis category and root cause
        part_recommendations = {
            "memory": {
                "part": "DIMM Memory Module",
                "dell_part_class": "Memory",
                "urgency": "high" if confidence >= 60 else "medium",
                "notes": "Check DIMM slot from SEL logs. Match speed/capacity of existing DIMMs.",
            },
            "storage": {
                "part": "Hard Drive / SSD",
                "dell_part_class": "Storage",
                "urgency": "high" if "predicted failure" in root_cause.lower() or "degraded" in root_cause.lower() else "medium",
                "notes": "Match drive type (SAS/SATA/NVMe), capacity, and form factor. Hot-swappable if RAID.",
            },
            "power": {
                "part": "Power Supply Unit (PSU)",
                "dell_part_class": "Power",
                "urgency": "high",
                "notes": "Match wattage and form factor. Redundant PSU — server may stay online during swap.",
            },
            "thermal": {
                "part": "Fan Module / Heatsink",
                "dell_part_class": "Cooling",
                "urgency": "medium",
                "notes": "Check which fan zone is affected. May also need thermal paste reapplication.",
            },
            "cpu": {
                "part": "Processor (CPU)",
                "dell_part_class": "Processor",
                "urgency": "high",
                "notes": "CPU replacement requires downtime. Verify socket type and TDP match.",
            },
            "network": {
                "part": "Network Interface Card (NIC)",
                "dell_part_class": "Network",
                "urgency": "medium",
                "notes": "Check SFP modules first. Match speed (1G/10G/25G/100G) and port count.",
            },
        }

        # Find matching part
        rec = None
        for cat_key, part_info in part_recommendations.items():
            if cat_key in category.lower() or cat_key in root_cause.lower():
                rec = part_info
                break

        if not rec:
            return {
                "message": f"Based on my diagnosis ({root_cause}, {confidence}% confidence), a part dispatch doesn't appear necessary at this time. The issue may be resolvable through configuration changes or firmware updates.\n\nIf you still need to dispatch a part, please specify which component.",
            }

        # Build detailed recommendation
        supporting_evidence = [e for e in evidence if e.get("supports")]
        evidence_lines = "\n".join([f"  • {e['description']}" for e in supporting_evidence[:5]])

        lines = [
            f"**Part Dispatch Recommendation**",
            f"",
            f"**Component:** {rec['part']}",
            f"**Dell Part Class:** {rec['dell_part_class']}",
            f"**Urgency:** {rec['urgency'].upper()}",
            f"**Dispatch Confidence:** {confidence}%",
            f"",
            f"**Root Cause:** {root_cause}",
            f"",
            f"**Supporting Evidence ({len(supporting_evidence)} items):**",
            evidence_lines,
            f"",
            f"**Notes:** {rec['notes']}",
            f"",
            f"**Recommended Actions Before Dispatch:**",
            f"  1. Collect TSR for Dell support case",
            f"  2. Document Service Tag and express service code",
            f"  3. Verify warranty/ProSupport entitlement",
            f"  4. Open Dell SR# with diagnostic evidence attached",
        ]

        return {
            "message": "\n".join(lines),
            "part": rec["part"],
            "urgency": rec["urgency"],
            "confidence": confidence,
            "dell_part_class": rec["dell_part_class"],
            "evidence_count": len(supporting_evidence),
        }

    def _build_monitor_recommendation(self) -> dict:
        """Build monitoring recommendation after remediation or investigation."""
        if not self._last_diagnosis:
            return {"message": "I need to investigate first. Describe the issue and I'll start monitoring after diagnosis."}

        diag = self._last_diagnosis
        root_cause = diag.get("root_cause", "")
        category = diag.get("category", "")

        # Build monitoring plan based on category
        monitor_targets = {
            "thermal": {"sensors": ["temperatures", "fans"], "interval": "5 min", "threshold": "CPU > 85°C, inlet > 35°C", "duration": "2 hours"},
            "power": {"sensors": ["power_supplies", "temperatures"], "interval": "5 min", "threshold": "PSU status != OK, voltage drift > 5%", "duration": "4 hours"},
            "memory": {"sensors": ["logs", "memory"], "interval": "10 min", "threshold": "New ECC errors, DIMM status change", "duration": "24 hours"},
            "storage": {"sensors": ["logs", "storage"], "interval": "10 min", "threshold": "RAID state change, new drive errors", "duration": "24 hours"},
            "cpu": {"sensors": ["temperatures", "logs"], "interval": "5 min", "threshold": "New MCE/IERR, CPU temp > 90°C", "duration": "4 hours"},
            "network": {"sensors": ["network", "logs"], "interval": "5 min", "threshold": "Link state change, CRC errors increasing", "duration": "2 hours"},
        }

        plan = None
        for cat_key, mon_info in monitor_targets.items():
            if cat_key in category.lower() or cat_key in root_cause.lower():
                plan = mon_info
                break

        if not plan:
            plan = {"sensors": ["health", "logs"], "interval": "10 min", "threshold": "Any new critical events", "duration": "2 hours"}

        lines = [
            f"**Post-Remediation Monitoring Plan**",
            f"",
            f"**Issue:** {root_cause}",
            f"**Monitoring Duration:** {plan['duration']}",
            f"**Check Interval:** {plan['interval']}",
            f"",
            f"**What I'll Watch:**",
        ]
        for sensor in plan["sensors"]:
            lines.append(f"  • {sensor.replace('_', ' ').title()} subsystem")
        lines.extend([
            f"",
            f"**Alert Threshold:** {plan['threshold']}",
            f"",
            f"**How to proceed:**",
            f"  • I'll re-check the relevant subsystems on your next message",
            f"  • Ask me 'What's the current status?' at any time for an update",
            f"  • If the issue recurs, I'll escalate with full diagnostic evidence",
            f"  • Say 'Collect TSR' to gather a support report for Dell",
        ])

        return {
            "message": "\n".join(lines),
            "monitoring_plan": plan,
        }

    # ═══════════════════════════════════════════════════════════════════
    # BUSINESS VALUE METRICS
    # ═══════════════════════════════════════════════════════════════════

    def _build_business_metrics(self) -> dict:
        """Calculate business value metrics for display."""
        # Time metrics
        investigation_seconds = 0
        if self._investigation_start and self._investigation_end:
            investigation_seconds = (self._investigation_end - self._investigation_start).total_seconds()

        # Manual equivalents (industry benchmarks)
        MANUAL_INVESTIGATION_MINUTES = 45   # avg time for L2 engineer to triage
        MANUAL_ESCALATION_HOURS = 4         # avg wait time for escalation
        HOURLY_DOWNTIME_COST = 5600         # avg cost per hour of server downtime (Gartner)
        TRUCK_ROLL_COST = 800               # avg cost of dispatching a field tech
        L2_ENGINEER_HOURLY = 95             # avg hourly rate

        tools_used = len(self.memory.tools_used) if self.memory else 0
        facts_collected = len(self.memory.facts) if self.memory else 0
        hypotheses_tested = len(self.memory.hypotheses) if self.memory else 0
        confidence = self._last_diagnosis.get("confidence", 0) if self._last_diagnosis else 0

        # Calculate savings
        time_saved_minutes = max(MANUAL_INVESTIGATION_MINUTES - (investigation_seconds / 60), 0)
        escalation_avoided = confidence >= 50  # high-confidence diagnosis avoids escalation
        potential_downtime_saved = MANUAL_ESCALATION_HOURS if escalation_avoided else 0
        cost_saved = round(
            (time_saved_minutes / 60) * L2_ENGINEER_HOURLY +  # engineer time
            (potential_downtime_saved * HOURLY_DOWNTIME_COST) +  # downtime cost
            (TRUCK_ROLL_COST if confidence >= 60 else 0),  # potential truck roll avoided
            2
        )

        return {
            "investigation_time_seconds": round(investigation_seconds, 1),
            "manual_equivalent_minutes": MANUAL_INVESTIGATION_MINUTES,
            "time_saved_minutes": round(time_saved_minutes, 1),
            "tools_used": tools_used,
            "facts_collected": facts_collected,
            "hypotheses_tested": hypotheses_tested,
            "confidence": confidence,
            "escalation_avoided": escalation_avoided,
            "potential_downtime_saved_hours": potential_downtime_saved,
            "estimated_cost_saved": cost_saved,
            "truck_roll_avoided": confidence >= 60,
            "data_points_analyzed": facts_collected,
            "subsystems_checked": tools_used,
            "remediation_steps_executed": len(self._remediation_log),
        }
