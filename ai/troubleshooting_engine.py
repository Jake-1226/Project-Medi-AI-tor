"""
AI-powered troubleshooting engine for Dell servers
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import re

from core.config import AgentConfig
from models.server_models import (
    TroubleshootingRecommendation, ActionLevel, LogEntry, HealthStatus,
    SystemInfo, ComponentType, Severity
)

logger = logging.getLogger(__name__)


# ── Dell-specific error code knowledge base ─────────────────────
DELL_ERROR_CODES = {
    "PSU": {
        "PSU0001": "Power supply lost AC input",
        "PSU0003": "Power supply failed",
        "PSU0006": "Power supply AC lost",
        "PSU0016": "Power supply performance degraded",
    },
    "CPU": {
        "CPU0000": "CPU internal error (IERR)",
        "CPU0001": "CPU thermal trip",
        "CPU0005": "CPU configuration error",
        "CPU0700": "CPU machine check error",
    },
    "MEM": {
        "MEM0001": "Single-bit ECC error (correctable)",
        "MEM0002": "Multi-bit ECC error (uncorrectable)",
        "MEM0007": "Memory module missing or not detected",
        "MEM0701": "Correctable memory error rate exceeded",
        "MEM1205": "Memory PPR (Post Package Repair) event",
    },
    "HWC": {
        "HWC2003": "CMOS battery low or failed",
        "HWC1001": "Hardware configuration error",
    },
    "VLT": {
        "VLT0204": "System board voltage out of range",
    },
    "FAN": {
        "FAN0001": "Fan removed or failed",
        "FAN0002": "Fan speed warning",
    },
    "STO": {
        "STO0101": "Physical disk failure predicted",
        "STO0102": "Physical disk failed",
        "STO0201": "Virtual disk degraded",
        "STO0202": "Virtual disk failed",
    },
}

# ── Known Dell resolution workflows ─────────────────────────────
DELL_WORKFLOWS = {
    "memory_retrain": {
        "name": "Memory DIMM Retrain",
        "description": "Re-train memory bus timing to recover from intermittent errors",
        "steps": [
            "Identify the failing DIMM from SEL logs (look for the DIMM slot ID)",
            "Reseat the DIMM — power off, unplug, press & hold power 15s, reseat DIMM, reconnect",
            "If errors persist, swap the DIMM to a different slot to isolate DIMM vs slot failure",
            "Enable Post Package Repair (PPR) in BIOS: PprOnUCE=Enabled, PprType=Hard",
            "Run ePSA memory diagnostics to verify",
            "If still failing, replace the DIMM (Dell dispatch under warranty)"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "30-60 minutes",
        "risk_level": "medium",
    },
    "flea_power_drain": {
        "name": "Flea Power Drain (Virtual AC Cycle)",
        "description": "Drain residual power from system boards to clear hung states",
        "steps": [
            "Attempt Virtual AC Cycle via iDRAC (use the VAC button in Server Actions)",
            "If iDRAC is unresponsive: physically unplug all power cables",
            "Press and hold the power button for 30 seconds to drain flea power",
            "Wait 60 seconds, then reconnect power cables",
            "Power on the server and verify POST completes"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "5-10 minutes",
        "risk_level": "low",
    },
    "tsr_collection": {
        "name": "Collect Technical Support Report (TSR)",
        "description": "Gather all diagnostic data for Dell Support case analysis",
        "steps": [
            "Use the 'Export TSR' button in Server Actions for remote collection",
            "If remote TSR fails, log into iDRAC web UI → Maintenance → SupportAssist",
            "Click 'Start a Collection', select all data sets, click 'Collect'",
            "Download the TSR zip file once complete",
            "Attach the TSR to your Dell Support case (reference your SR#)"
        ],
        "action_level": ActionLevel.READ_ONLY,
        "estimated_time": "10-20 minutes",
        "risk_level": "low",
    },
    "thermal_remediation": {
        "name": "Thermal Issue Remediation",
        "description": "Address overheating conditions that may cause throttling or shutdown",
        "steps": [
            "Check ambient/inlet temperature — should be below 35°C (95°F)",
            "Inspect server air intake and exhaust for blockage or dust",
            "Verify all fans are operational (check Fan sub-tab in Health Status)",
            "If a fan is failed, replace it (hot-swappable on most Dell servers)",
            "Check for missing blanks on unused drive bays or PCIe slots",
            "If thermal throttling persists, consider BIOS fan offset: set SysProfile=PerfOptimized",
            "Run ePSA diagnostics to verify thermal subsystem"
        ],
        "action_level": ActionLevel.DIAGNOSTIC,
        "estimated_time": "15-30 minutes",
        "risk_level": "low",
    },
    "raid_recovery": {
        "name": "RAID Array Recovery",
        "description": "Recover degraded or failed RAID virtual disks",
        "steps": [
            "Check Storage sub-tab for physical disk and virtual disk status",
            "If a single disk failed in a redundant array, the VD is degraded but data is intact",
            "Identify the failed disk slot and replace with a compatible drive",
            "If a hot spare is configured, rebuild should start automatically",
            "Monitor rebuild progress in iDRAC → Storage → Virtual Disks",
            "If VD is failed (non-redundant or multiple disk loss), data recovery may be needed",
            "Collect TSR before any further action and contact Dell Support"
        ],
        "action_level": ActionLevel.READ_ONLY,
        "estimated_time": "Variable (hours)",
        "risk_level": "medium",
    },
    "idrac_reset": {
        "name": "iDRAC Reset / Recovery",
        "description": "Reset a hung or unresponsive iDRAC controller",
        "steps": [
            "Try soft reset: use 'Reset iDRAC' button in Server Actions",
            "If iDRAC web/Redfish is unresponsive, try RACADM: racadm racreset",
            "If RACADM also fails, use iDRAC Direct USB port with a laptop",
            "Last resort: pull server power, wait 30s, restore power (iDRAC resets on AC cycle)",
            "After iDRAC comes back (~2 min), verify connectivity",
            "Check iDRAC firmware version — update if outdated"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "5-15 minutes",
        "risk_level": "low",
    },
    "cpu_ierr": {
        "name": "CPU Internal Error (IERR) Investigation",
        "description": "Investigate CPU machine check / IERR events",
        "steps": [
            "Collect TSR immediately — IERR data is volatile",
            "Check SEL for CPU error codes (CPU0000, CPU0700)",
            "Note whether the error is on CPU1 or CPU2",
            "Check BIOS and iDRAC firmware versions — update if not current",
            "Run ePSA Extended diagnostics targeting CPU",
            "If IERR recurs, contact Dell Support with TSR — may need CPU replacement",
            "Workaround: disable affected CPU's C-States in BIOS (ProcCStates=Disabled)"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "30-60 minutes",
        "risk_level": "medium",
    },
    "pcie_remediation": {
        "name": "PCIe Device Error Remediation",
        "description": "Address PCIe AER fatal/non-fatal errors (completion timeout, poisoned TLP, link down)",
        "steps": [
            "Identify the affected PCIe device and slot from SEL/LC logs",
            "Check firmware inventory — update PCIe device firmware if outdated",
            "Reseat the PCIe card (power off server first)",
            "Clean PCIe gold contacts with isopropyl alcohol if dusty",
            "Try the card in a different PCIe slot to isolate slot vs card failure",
            "Update BIOS — many PCIe issues are resolved by BIOS updates",
            "If NIC/HBA: check cables and SFP modules",
            "If errors persist, replace the PCIe device"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "20-40 minutes",
        "risk_level": "medium",
    },
    "firmware_update": {
        "name": "Firmware Update via iDRAC",
        "description": "Update outdated firmware components via Redfish SimpleUpdate",
        "steps": [
            "Check firmware inventory against Dell's latest catalog",
            "Identify critical updates (BIOS, iDRAC, NIC, RAID controller)",
            "Download firmware package from Dell support or use Dell Repository Manager",
            "Push firmware via iDRAC Redfish SimpleUpdate API",
            "Monitor update job status in iDRAC Job Queue",
            "Schedule server reboot if BIOS update requires it",
            "Verify new firmware version after reboot"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "15-45 minutes",
        "risk_level": "medium",
    },
    "psu_replacement": {
        "name": "Power Supply Replacement",
        "description": "Replace a failed or degraded power supply unit to restore redundancy",
        "steps": [
            "Identify the failed PSU slot from the Health Status → Power tab",
            "Verify the server is running on the remaining healthy PSU(s)",
            "Order a replacement PSU matching the same model and wattage rating",
            "PSUs are hot-swappable: pull the failed PSU handle and slide it out",
            "Insert the new PSU firmly until the latch clicks into place",
            "Verify the new PSU shows OK status in iDRAC within 30 seconds",
            "Confirm power redundancy is restored in the System Event Log"
        ],
        "action_level": ActionLevel.READ_ONLY,
        "estimated_time": "5-10 minutes (with replacement on hand)",
        "risk_level": "low",
    },
    "power_source_check": {
        "name": "Upstream Power Source Investigation",
        "description": "Investigate upstream power issues (PDU, UPS, outlet, cables)",
        "steps": [
            "Check if the PSU input LED is lit — if not, the wall/PDU side has no power",
            "Verify the power cable is firmly seated at both the PSU and the PDU/outlet",
            "Try a known-good power cable from another server",
            "Check the PDU breaker — reset if tripped",
            "If on a UPS, verify the UPS is online and has battery/utility power",
            "If multiple servers lost power, escalate to facilities/data center operations",
            "Once power is restored, verify both PSUs show OK and redundancy is restored"
        ],
        "action_level": ActionLevel.READ_ONLY,
        "estimated_time": "10-20 minutes",
        "risk_level": "low",
    },
    "bios_settings_change": {
        "name": "BIOS/UEFI Settings Change",
        "description": "Modify BIOS settings to resolve performance, boot, or stability issues",
        "steps": [
            "Read current BIOS attributes via Redfish",
            "Identify misconfigured settings (boot mode, C-States, turbo, memory mode)",
            "Propose specific attribute changes with before/after values",
            "Apply BIOS attribute changes via Redfish SetBiosAttributes",
            "Create a scheduled BIOS config job (requires reboot to take effect)",
            "Schedule server reboot during maintenance window",
            "Verify new BIOS settings after reboot"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "10-20 minutes + reboot",
        "risk_level": "medium",
    },
    "tsr_collection": {
        "name": "TSR (Tech Support Report) Collection",
        "description": "Collect comprehensive system snapshot for Dell support escalation",
        "steps": [
            "Initiate TSR collection via iDRAC Redfish API",
            "Monitor collection job progress (typically 3-8 minutes)",
            "Download TSR package from iDRAC",
            "Attach TSR to Dell Service Request (SR#)",
            "Include agent diagnostic summary and evidence chain",
            "Recommend next steps based on Dell support SLA"
        ],
        "action_level": ActionLevel.DIAGNOSTIC,
        "estimated_time": "5-10 minutes",
        "risk_level": "low",
    },
    "no_post_troubleshooting": {
        "name": "No-POST / Boot Failure Troubleshooting",
        "description": "Diagnose server that fails to POST or boot — amber power light, no video, stuck POST code",
        "steps": [
            "Check iDRAC availability (if iDRAC responds, BMC is alive)",
            "Read current POST code and boot progress via Redfish",
            "Check SEL/LC logs for pre-failure events",
            "Decode POST code against Dell POST code table",
            "If memory-related POST code: check DIMM population rules",
            "If PCIe-related POST code: try removing add-in cards",
            "If CPU-related POST code: check CPU seating and power",
            "Perform AC power drain (unplug, hold power 30s, replug)",
            "If still no POST: collect TSR and escalate to Dell support"
        ],
        "action_level": ActionLevel.FULL_CONTROL,
        "estimated_time": "15-45 minutes",
        "risk_level": "medium",
    },
    "part_dispatch": {
        "name": "Part Dispatch Recommendation",
        "description": "Generate evidence-based part replacement recommendation for Dell support",
        "steps": [
            "Review investigation diagnosis and confidence level",
            "Identify the failed or failing component from evidence",
            "Map to Dell part class and replacement procedure",
            "Collect TSR for Dell support case documentation",
            "Document Service Tag, Express Service Code, and iDRAC IP",
            "Generate dispatch recommendation with evidence summary",
            "Open Dell SR# via TechDirect or phone support"
        ],
        "action_level": ActionLevel.READ_ONLY,
        "estimated_time": "5-10 minutes",
        "risk_level": "low",
    },
}


class TroubleshootingEngine:
    """AI engine for troubleshooting Dell server issues"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.confidence_threshold = config.confidence_threshold
        
        # Common issue patterns and solutions
        self.issue_patterns = {
            "power_issues": {
                "keywords": ["power", "shutdown", "restart", "boot", "psu", "power supply"],
                "recommendations": [
                    TroubleshootingRecommendation(
                        action="Check power supply status",
                        description="Verify all power supplies are functioning properly and connected securely",
                        priority="high",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="2 minutes",
                        risk_level="low",
                        steps=[
                            "Check power supply LEDs on the server",
                            "Verify power cables are securely connected",
                            "Check iDRAC power supply status"
                        ],
                        commands=["get_power_supplies", "health_check"]
                    ),
                    TroubleshootingRecommendation(
                        action="Verify power source",
                        description="Check if the server is receiving adequate power from the source",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="1 minute",
                        risk_level="low",
                        steps=[
                            "Check power outlet functionality",
                            "Verify UPS or PDU status",
                            "Check circuit breaker"
                        ]
                    )
                ]
            },
            "overheating": {
                "keywords": ["overheat", "temperature", "hot", "thermal", "fan", "cooling"],
                "recommendations": [
                    TroubleshootingRecommendation(
                        action="Check temperature sensors",
                        description="Monitor all temperature sensors to identify overheating components",
                        priority="critical",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="1 minute",
                        risk_level="low",
                        commands=["get_temperature_sensors"]
                    ),
                    TroubleshootingRecommendation(
                        action="Verify fan operation",
                        description="Check if all fans are operating at correct speeds",
                        priority="high",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="2 minutes",
                        risk_level="low",
                        commands=["get_fans"]
                    ),
                    TroubleshootingRecommendation(
                        action="Check airflow and ventilation",
                        description="Ensure proper airflow around the server and vents are not blocked",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="5 minutes",
                        risk_level="low",
                        steps=[
                            "Check server vents for dust or obstructions",
                            "Verify rack ventilation",
                            "Check room temperature and humidity"
                        ]
                    )
                ]
            },
            "memory_issues": {
                "keywords": ["memory", "ram", "dim", "memory error", "ecc", "blue screen"],
                "recommendations": [
                    TroubleshootingRecommendation(
                        action="Run memory diagnostics",
                        description="Execute comprehensive memory diagnostics to identify faulty modules",
                        priority="high",
                        action_level_required=ActionLevel.DIAGNOSTIC,
                        estimated_time="30 minutes",
                        risk_level="low",
                        steps=[
                            "Launch iDRAC virtual console",
                            "Run built-in memory diagnostics",
                            "Check for ECC errors in system logs"
                        ]
                    ),
                    TroubleshootingRecommendation(
                        action="Check memory configuration",
                        description="Verify memory modules are properly seated and configured",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="10 minutes",
                        risk_level="medium",
                        commands=["get_memory"],
                        steps=[
                            "Check memory module seating",
                            "Verify memory channel population",
                            "Check for mismatched memory modules"
                        ]
                    )
                ]
            },
            "storage_issues": {
                "keywords": ["disk", "storage", "raid", "controller", "drive", "ssd", "hdd"],
                "recommendations": [
                    TroubleshootingRecommendation(
                        action="Check storage controller status",
                        description="Verify RAID controller and physical disk status",
                        priority="high",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="2 minutes",
                        risk_level="low",
                        commands=["get_storage_devices"]
                    ),
                    TroubleshootingRecommendation(
                        action="Run storage diagnostics",
                        description="Execute storage controller diagnostics to identify failing drives",
                        priority="high",
                        action_level_required=ActionLevel.DIAGNOSTIC,
                        estimated_time="45 minutes",
                        risk_level="low",
                        steps=[
                            "Access storage controller via iDRAC",
                            "Run controller diagnostics",
                            "Check drive SMART status"
                        ]
                    ),
                    TroubleshootingRecommendation(
                        action="Check RAID configuration",
                        description="Verify RAID array status and configuration",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="5 minutes",
                        risk_level="low",
                        steps=[
                            "Check RAID array status",
                            "Verify hot spares",
                            "Check rebuild progress if applicable"
                        ]
                    )
                ]
            },
            "network_issues": {
                "keywords": ["network", "nic", "ethernet", "connectivity", "ping", "link"],
                "recommendations": [
                    TroubleshootingRecommendation(
                        action="Check network interface status",
                        description="Verify all network interfaces are operational and configured correctly",
                        priority="high",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="2 minutes",
                        risk_level="low",
                        commands=["get_network_interfaces"]
                    ),
                    TroubleshootingRecommendation(
                        action="Verify network configuration",
                        description="Check IP configuration, VLAN settings, and network paths",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="5 minutes",
                        risk_level="low",
                        steps=[
                            "Check IP address configuration",
                            "Verify default gateway",
                            "Test network connectivity",
                            "Check DNS resolution"
                        ]
                    ),
                    TroubleshootingRecommendation(
                        action="Check physical network connections",
                        description="Verify network cables and switch ports are functioning",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="10 minutes",
                        risk_level="low",
                        steps=[
                            "Check network cable connections",
                            "Verify switch port status",
                            "Check link lights on NIC and switch"
                        ]
                    )
                ]
            },
            "firmware_issues": {
                "keywords": ["firmware", "bios", "idrac", "update", "version", "upgrade"],
                "recommendations": [
                    TroubleshootingRecommendation(
                        action="Check firmware versions",
                        description="Verify current firmware versions and check for updates",
                        priority="medium",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="2 minutes",
                        risk_level="low",
                        commands=["firmware_check"]
                    ),
                    TroubleshootingRecommendation(
                        action="Update firmware",
                        description="Update system firmware to latest stable versions",
                        priority="low",
                        action_level_required=ActionLevel.FULL_CONTROL,
                        estimated_time="60 minutes",
                        risk_level="high",
                        steps=[
                            "Download latest firmware from Dell support",
                            "Schedule maintenance window",
                            "Create backup before update",
                            "Update BIOS/iDRAC firmware",
                            "Verify system functionality post-update"
                        ],
                        commands=["update_firmware"]
                    )
                ]
            }
        }
    
    async def analyze_issue(
        self,
        issue_description: str,
        logs: List[LogEntry],
        health_status: Optional[HealthStatus],
        system_info: Optional[SystemInfo],
        action_level: ActionLevel
    ) -> List[TroubleshootingRecommendation]:
        """Analyze an issue and provide troubleshooting recommendations"""
        
        issue_lower = issue_description.lower()
        all_recommendations = []

        # ── Phase 1: Match issue keywords to pattern categories ──────
        matched_categories = []
        for category, cfg in self.issue_patterns.items():
            for keyword in cfg["keywords"]:
                if keyword in issue_lower:
                    matched_categories.append(category)
                    break

        for category in matched_categories:
            for rec in self.issue_patterns[category]["recommendations"]:
                if self._is_action_level_allowed(rec.action_level_required, action_level):
                    all_recommendations.append(rec)

        # ── Phase 2: Match Dell workflows by keyword ─────────────────
        workflow_map = {
            "memory_retrain": ["memory error", "ecc", "dimm", "correctable", "uncorrectable", "mem0", "retrain", "ppr"],
            "flea_power_drain": ["no post", "won't boot", "dead", "hung", "no power", "flea", "stuck", "unresponsive server"],
            "tsr_collection": ["tsr", "support case", "dell support", "service request", "sr#"],
            "thermal_remediation": ["overheat", "thermal", "hot", "throttl", "fan fail", "temperature warning", "inlet temp"],
            "raid_recovery": ["raid", "degraded", "disk fail", "virtual disk", "rebuild", "storage fail"],
            "idrac_reset": ["idrac hang", "idrac unresponsive", "can't reach idrac", "idrac down", "management controller"],
            "cpu_ierr": ["ierr", "machine check", "cpu error", "cpu0000", "cpu0700", "blue screen", "bsod", "crash"],
        }
        for wf_key, keywords in workflow_map.items():
            if any(kw in issue_lower for kw in keywords):
                wf = DELL_WORKFLOWS[wf_key]
                if self._is_action_level_allowed(wf["action_level"], action_level):
                    all_recommendations.append(TroubleshootingRecommendation(
                        action=wf["name"],
                        description=wf["description"],
                        priority="high",
                        action_level_required=wf["action_level"],
                        estimated_time=wf["estimated_time"],
                        risk_level=wf["risk_level"],
                        steps=wf["steps"],
                    ))

        # ── Phase 3: Analyse live log data for Dell error codes ──────
        dell_code_recs = self._analyze_dell_error_codes(logs, action_level)
        all_recommendations.extend(dell_code_recs)

        # ── Phase 4: Context recommendations from health/logs ────────
        context_recs = await self._get_context_recommendations(
            logs, health_status, system_info, action_level
        )
        all_recommendations.extend(context_recs)

        # ── Phase 5: If nothing specific matched, generic triage ─────
        if not all_recommendations:
            all_recommendations = self._get_general_recommendations(issue_description, logs, action_level)

        # ── Always suggest TSR collection at the end ─────────────────
        tsr_wf = DELL_WORKFLOWS["tsr_collection"]
        all_recommendations.append(TroubleshootingRecommendation(
            action=tsr_wf["name"],
            description="Always collect a TSR when opening a Dell Support case",
            priority="medium",
            action_level_required=tsr_wf["action_level"],
            estimated_time=tsr_wf["estimated_time"],
            risk_level=tsr_wf["risk_level"],
            steps=tsr_wf["steps"],
            commands=["export_tsr"],
        ))

        # De-dup, sort, return top 12
        unique_recs = self._deduplicate_recommendations(all_recommendations)
        sorted_recs = sorted(unique_recs, key=lambda x: self._priority_score(x.priority), reverse=True)
        return sorted_recs[:12]

    def _analyze_dell_error_codes(self, logs: List[LogEntry], action_level: ActionLevel) -> List[TroubleshootingRecommendation]:
        """Scan logs for known Dell error codes and produce targeted recommendations."""
        recs = []
        seen_prefixes = set()
        for log in logs:
            msg = log.message or ""
            event_id = log.event_id or ""
            combined = f"{msg} {event_id}"
            for prefix, codes in DELL_ERROR_CODES.items():
                if prefix in seen_prefixes:
                    continue
                for code, meaning in codes.items():
                    if code in combined:
                        seen_prefixes.add(prefix)
                        # Map prefix to workflow
                        wf_key = {"MEM": "memory_retrain", "PSU": "flea_power_drain",
                                  "CPU": "cpu_ierr", "FAN": "thermal_remediation",
                                  "STO": "raid_recovery", "VLT": "flea_power_drain",
                                  "HWC": "tsr_collection"}.get(prefix, "tsr_collection")
                        wf = DELL_WORKFLOWS.get(wf_key, DELL_WORKFLOWS["tsr_collection"])
                        if self._is_action_level_allowed(wf["action_level"], action_level):
                            recs.append(TroubleshootingRecommendation(
                                action=f"[{code}] {meaning}",
                                description=f"Dell error code {code} detected in logs: {meaning}. Follow the {wf['name']} workflow.",
                                priority="critical" if log.severity in [Severity.CRITICAL, Severity.ERROR] else "high",
                                action_level_required=wf["action_level"],
                                estimated_time=wf["estimated_time"],
                                risk_level=wf["risk_level"],
                                steps=wf["steps"],
                            ))
                        break
        return recs
    
    def _get_general_recommendations(
        self, issue_description: str, logs: List[LogEntry], action_level: ActionLevel
    ) -> List[TroubleshootingRecommendation]:
        """Get general troubleshooting recommendations"""
        
        recommendations = [
            TroubleshootingRecommendation(
                action="Collect comprehensive logs",
                description="Gather all system logs for detailed analysis",
                priority="high",
                action_level_required=ActionLevel.READ_ONLY,
                estimated_time="5 minutes",
                risk_level="low",
                commands=["collect_logs"]
            ),
            TroubleshootingRecommendation(
                action="Perform health check",
                description="Run comprehensive system health assessment",
                priority="high",
                action_level_required=ActionLevel.READ_ONLY,
                estimated_time="2 minutes",
                risk_level="low",
                commands=["health_check"]
            ),
            TroubleshootingRecommendation(
                action="Check system information",
                description="Review system configuration and status",
                priority="medium",
                action_level_required=ActionLevel.READ_ONLY,
                estimated_time="1 minute",
                risk_level="low",
                commands=["get_server_info", "get_system_info"]
            )
        ]
        
        # Filter by action level
        return [
            rec for rec in recommendations
            if self._is_action_level_allowed(rec.action_level_required, action_level)
        ]
    
    async def _get_context_recommendations(
        self,
        logs: List[LogEntry],
        health_status: Optional[HealthStatus],
        system_info: Optional[SystemInfo],
        action_level: ActionLevel
    ) -> List[TroubleshootingRecommendation]:
        """Get recommendations based on current system context"""
        
        recommendations = []
        
        # Analyze recent critical logs
        recent_critical = [
            log for log in logs
            if log.severity in [Severity.CRITICAL, Severity.ERROR] and
            log.timestamp > datetime.now(timezone.utc) - timedelta(hours=24)
        ]
        
        if recent_critical:
            recommendations.append(TroubleshootingRecommendation(
                action="Investigate recent critical errors",
                description=f"Found {len(recent_critical)} critical errors in the last 24 hours",
                priority="critical",
                action_level_required=ActionLevel.READ_ONLY,
                estimated_time="15 minutes",
                risk_level="low",
                steps=[
                    "Review critical error messages",
                    "Check for recurring patterns",
                    "Identify affected components"
                ]
            ))
        
        # Check health status
        if health_status:
            if health_status.overall_status.value in ["critical", "warning"]:
                recommendations.append(TroubleshootingRecommendation(
                    action="Address system health issues",
                    description=f"System health status: {health_status.overall_status.value}",
                    priority="high",
                    action_level_required=ActionLevel.READ_ONLY,
                    estimated_time="10 minutes",
                    risk_level="low",
                    steps=[
                        "Review component health status",
                        "Address critical component failures",
                        "Monitor system stability"
                    ]
                ))
        
        # Check for temperature issues in logs
        temp_logs = [log for log in logs if "temperature" in log.message.lower() or "thermal" in log.message.lower()]
        if temp_logs:
            recommendations.append(TroubleshootingRecommendation(
                action="Monitor temperature issues",
                description=f"Found {len(temp_logs)} temperature-related log entries",
                priority="medium",
                action_level_required=ActionLevel.READ_ONLY,
                estimated_time="5 minutes",
                risk_level="low",
                commands=["get_temperature_sensors", "get_fans"]
            ))
        
        # Check for power issues in logs
        power_logs = [log for log in logs if "power" in log.message.lower() or "psu" in log.message.lower()]
        if power_logs:
            recommendations.append(TroubleshootingRecommendation(
                action="Investigate power issues",
                description=f"Found {len(power_logs)} power-related log entries",
                priority="medium",
                action_level_required=ActionLevel.READ_ONLY,
                estimated_time="5 minutes",
                risk_level="low",
                commands=["get_power_supplies"]
            ))
        
        # Filter by action level
        return [
            rec for rec in recommendations
            if self._is_action_level_allowed(rec.action_level_required, action_level)
        ]
    
    def _is_action_level_allowed(self, required: ActionLevel, available: ActionLevel) -> bool:
        """Check if required action level is available"""
        level_hierarchy = {
            ActionLevel.READ_ONLY: 1,
            ActionLevel.DIAGNOSTIC: 2,
            ActionLevel.FULL_CONTROL: 3
        }
        
        return level_hierarchy[required] <= level_hierarchy[available]
    
    def _priority_score(self, priority: str) -> int:
        """Convert priority string to numeric score for sorting"""
        priority_scores = {
            "critical": 4,
            "high": 3,
            "medium": 2,
            "low": 1
        }
        return priority_scores.get(priority, 0)
    
    def _deduplicate_recommendations(self, recommendations: List[TroubleshootingRecommendation]) -> List[TroubleshootingRecommendation]:
        """Remove duplicate recommendations based on action"""
        seen_actions = set()
        unique_recs = []
        
        for rec in recommendations:
            if rec.action not in seen_actions:
                seen_actions.add(rec.action)
                unique_recs.append(rec)
        
        return unique_recs
