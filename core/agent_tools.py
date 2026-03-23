"""
Agent Tool Registry — formalized tools the AgentBrain can invoke.
Each tool has a name, description, trigger keywords, command mapping,
and an output parser that extracts structured Findings for WorkingMemory.
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

from core.agent_memory import Fact, HypothesisCategory

logger = logging.getLogger(__name__)


def _is_healthy(status_str: Optional[str]) -> bool:
    if not status_str:
        return True
    s = status_str.lower()
    return any(w in s for w in ("ok", "enabled", "operable", "online", "optimal", "ready", "present"))


@dataclass
class ToolResult:
    """Structured output from running a tool."""
    tool_name: str
    success: bool
    summary: str                      # one-line human summary
    facts: List[Fact] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    critical: List[str] = field(default_factory=list)
    raw_data: Any = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name, "success": self.success,
            "summary": self.summary,
            "facts": [f.to_dict() for f in self.facts],
            "warnings": self.warnings, "critical": self.critical,
        }


@dataclass
class AgentTool:
    """A tool the agent can invoke during investigation."""
    name: str
    description: str
    command: str                       # maps to agent.execute_action command
    action_level: str                  # read_only, diagnostic, full_control
    categories: List[HypothesisCategory]  # which hypothesis categories this helps test
    trigger_keywords: List[str]        # keywords that suggest using this tool
    parser: Optional[Callable] = None  # function(raw_result) -> ToolResult
    parameters: Dict[str, Any] = field(default_factory=dict)
    cooldown_steps: int = 0            # min steps before re-using (0 = no limit)


# ═══════════════════════════════════════════════════════════════════
# Output parsers — extract Facts from raw command results
# ═══════════════════════════════════════════════════════════════════

def parse_temperatures(raw: Dict[str, Any]) -> ToolResult:
    temps = raw.get("temperatures", [])
    facts = []
    warnings, critical = [], []
    for i, t in enumerate(temps):
        reading = t.get("reading_celsius")
        name = t.get("name") or t.get("id") or f"Sensor-{i}"
        status = "ok"
        if reading and reading > 80:
            status = "critical"
            critical.append(f"{name}: {reading}°C (>80°C)")
        elif reading and reading > 70:
            status = "warning"
            warnings.append(f"{name}: {reading}°C (>70°C)")
        facts.append(Fact(
            id=f"temp_{i}", description=f"{name} = {reading}°C",
            component=name, metric="temperature",
            value=reading, unit="°C", status=status,
        ))
    readings = [t.get("reading_celsius") or 0 for t in temps if t.get("reading_celsius")]
    avg = round(sum(readings) / len(readings), 1) if readings else 0
    mx = max(readings) if readings else 0
    summary = f"{len(temps)} sensors — Avg: {avg}°C, Max: {mx}°C"
    if critical:
        summary += f" | {len(critical)} CRITICAL"
    elif warnings:
        summary += f" | {len(warnings)} elevated"
    else:
        summary += " | All within limits"
    return ToolResult(tool_name="check_temperatures", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical, raw_data=temps)


def parse_fans(raw: Dict[str, Any]) -> ToolResult:
    fans = raw.get("fans", [])
    facts, warnings, critical = [], [], []
    for i, f in enumerate(fans):
        name = f.get("name") or f.get("id") or f"Fan-{i}"
        rpm = f.get("speed_rpm")
        healthy = _is_healthy(f.get("status"))
        status = "ok" if healthy else "critical"
        if not healthy:
            critical.append(f"{name}: FAILED ({f.get('status', '?')})")
        facts.append(Fact(
            id=f"fan_{i}", description=f"{name} = {rpm} RPM" if rpm else f"{name} status={f.get('status','?')}",
            component=name, metric="speed_rpm", value=rpm, unit="RPM", status=status,
        ))
    speeds = [f.get("speed_rpm") or 0 for f in fans if f.get("speed_rpm")]
    avg_rpm = round(sum(speeds) / len(speeds)) if speeds else 0
    failed = sum(1 for f in fans if not _is_healthy(f.get("status")))
    summary = f"{len(fans)} fans — Avg: {avg_rpm} RPM"
    if failed:
        summary += f" | {failed} FAILED"
    elif avg_rpm > 12000:
        summary += " | RPMs elevated (possible thermal compensation)"
        warnings.append(f"Average fan speed {avg_rpm} RPM is high")
    else:
        summary += " | All healthy"
    return ToolResult(tool_name="check_fans", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical, raw_data=fans)


def parse_power_supplies(raw: Dict[str, Any]) -> ToolResult:
    psus = raw.get("power_supplies", [])
    facts, warnings, critical = [], [], []
    for i, p in enumerate(psus):
        pid = p.get("id") or f"PSU-{i}"
        watts = p.get("power_watts")
        psu_status = p.get("status", "?")
        healthy = _is_healthy(psu_status)
        status = "ok" if healthy else "critical"
        if not healthy:
            critical.append(f"{pid}: FAILED ({psu_status})")
            desc = f"{pid} FAILED — {psu_status}" + (f" ({watts}W rated)" if watts else "")
        else:
            desc = f"{pid} = {watts}W" if watts else f"{pid} status={psu_status}"
        facts.append(Fact(
            id=f"psu_{i}", description=desc,
            component=pid, metric="power_watts", value=watts, unit="W", status=status,
        ))
    total_w = sum(p.get("power_watts") or 0 for p in psus)
    failed = sum(1 for p in psus if not _is_healthy(p.get("status")))
    summary = f"{len(psus)} PSUs — Total: {total_w}W"
    if failed == len(psus) and len(psus) > 0:
        summary += " | ALL FAILED — imminent power loss"
    elif failed:
        summary += f" | {failed} degraded — redundancy lost"
    else:
        summary += " | All healthy"
    return ToolResult(tool_name="check_power_supplies", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical, raw_data=psus)


def parse_memory(raw: Dict[str, Any]) -> ToolResult:
    dimms = raw.get("memory", [])
    facts, warnings, critical = [], [], []
    for i, m in enumerate(dimms):
        mid = m.get("id") or m.get("location") or f"DIMM-{i}"
        size = m.get("size_gb")
        healthy = _is_healthy(m.get("status"))
        status = "ok" if healthy else "critical"
        if not healthy:
            critical.append(f"{mid}: FAILED ({m.get('status','?')})")
        desc = f"{mid} = {size}GB {m.get('type','')} {m.get('speed_mhz','?')}MHz" if size else f"{mid} (empty/absent)"
        facts.append(Fact(
            id=f"dimm_{i}", description=desc,
            component=mid, metric="size_gb", value=size, unit="GB", status=status,
        ))
    total_gb = sum(m.get("size_gb") or 0 for m in dimms)
    populated = sum(1 for m in dimms if m.get("size_gb"))
    failed = sum(1 for m in dimms if not _is_healthy(m.get("status")))
    summary = f"{populated}/{len(dimms)} DIMMs populated — {total_gb}GB total"
    if failed:
        summary += f" | {failed} FAILED"
    else:
        summary += " | All healthy"
    return ToolResult(tool_name="check_memory", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical, raw_data=dimms)


def parse_storage(raw: Dict[str, Any]) -> ToolResult:
    devs = raw.get("storage_devices", [])
    facts, warnings, critical = [], [], []
    for i, s in enumerate(devs):
        sid = s.get("id") or s.get("name") or f"Drive-{i}"
        cap = s.get("capacity_gb")
        healthy = _is_healthy(s.get("status"))
        status = "ok" if healthy else "critical"
        if not healthy:
            critical.append(f"{sid}: FAILED ({s.get('status','?')})")
        desc = f"{sid} {s.get('media_type','')} {cap}GB" if cap else f"{sid} status={s.get('status','?')}"
        facts.append(Fact(
            id=f"drive_{i}", description=desc,
            component=sid, metric="capacity_gb", value=cap, unit="GB", status=status,
        ))
    failed = sum(1 for s in devs if not _is_healthy(s.get("status")))
    summary = f"{len(devs)} storage devices"
    if failed:
        summary += f" | {failed} FAILED"
    else:
        summary += " | All healthy"
    return ToolResult(tool_name="check_storage", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical, raw_data=devs)


def parse_network(raw: Dict[str, Any]) -> ToolResult:
    nics = raw.get("network_interfaces", [])
    facts, warnings, critical = [], [], []
    for i, n in enumerate(nics):
        nid = n.get("id") or n.get("name") or f"NIC-{i}"
        speed = n.get("speed_mbps")
        nic_status = n.get("status", "")
        healthy = _is_healthy(nic_status)
        link = n.get("link_status", "")
        # Treat "Unknown" as informational, not a warning
        is_unknown = "unknown" in (nic_status or "").lower() or not nic_status
        status = "ok"
        if not healthy and not is_unknown:
            status = "warning"
        if link and "down" in link.lower():
            # Only warn for link-down on NICs with known-good status (not unconfigured ports)
            if not is_unknown:
                status = "warning"
                warnings.append(f"{nid}: link down")
        desc = f"{nid} {speed}Mbps link={link}" if speed and speed > 0 else f"{nid} status={nic_status or 'Unknown'}"
        facts.append(Fact(
            id=f"nic_{i}", description=desc,
            component=nid, metric="speed_mbps", value=speed, unit="Mbps", status=status,
        ))
    summary = f"{len(nics)} NICs"
    if warnings:
        summary += f" | {len(warnings)} link(s) down"
    else:
        summary += " | All connected"
    return ToolResult(tool_name="check_network", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical, raw_data=nics)


def parse_health(raw: Dict[str, Any]) -> ToolResult:
    hs = raw.get("health_status")
    if not hs:
        return ToolResult(tool_name="check_health", success=False, summary="Health data unavailable")
    overall = hs.get("overall_status", "unknown") if isinstance(hs, dict) else "unknown"
    # Normalize enum values to clean strings
    if hasattr(overall, 'value'):
        overall = overall.value
    overall = str(overall).lower().replace("serverstatus.", "")
    crits = hs.get("critical_issues", []) if isinstance(hs, dict) else []
    warns = hs.get("warnings", []) if isinstance(hs, dict) else []
    status = "ok" if overall in ("online", "ok") else "critical" if overall == "critical" else "warning"
    overall_label = {"online": "Healthy", "ok": "Healthy", "critical": "Critical", "warning": "Warning"}.get(overall, overall.title())
    facts = [Fact(id="health_overall", description=f"Overall server health: {overall_label}",
                  component="System", metric="health", value=overall, status=status)]
    summary = f"Health: {overall.upper()}"
    if crits:
        summary += f" | {len(crits)} critical issues"
    if warns:
        summary += f" | {len(warns)} warnings"
    return ToolResult(tool_name="check_health", success=True, summary=summary,
                      facts=facts, warnings=[str(w)[:100] for w in warns[:5]],
                      critical=[str(c)[:100] for c in crits[:5]], raw_data=hs)


def parse_logs(raw: Dict[str, Any]) -> ToolResult:
    from core.knowledge_base import scan_logs_for_mca_errors, scan_logs_for_pcie_errors

    logs = raw.get("logs", [])
    facts, warnings, critical = [], [], []
    crit_count = sum(1 for l in logs if (l.get("severity") or "").lower() in ("critical", "error"))
    warn_count = sum(1 for l in logs if (l.get("severity") or "").lower() == "warning")

    # Extract key log facts
    if crit_count:
        facts.append(Fact(id="log_critical_count", description=f"{crit_count} critical/error log entries",
                          component="Logs", metric="critical_count", value=crit_count, status="critical" if crit_count > 10 else "warning"))
        critical.append(f"{crit_count} critical/error entries in SEL")
    if warn_count:
        facts.append(Fact(id="log_warning_count", description=f"{warn_count} warning log entries",
                          component="Logs", metric="warning_count", value=warn_count, status="warning" if warn_count > 20 else "ok"))

    # Sample recent critical messages
    for i, l in enumerate(logs[:200]):
        sev = (l.get("severity") or "info").lower()
        if sev in ("critical", "error") and i < 10:
            msg = (l.get("message") or "")[:120]
            facts.append(Fact(id=f"log_crit_{i}", description=msg,
                              component="SEL", metric="log_entry", value=sev, status="critical"))

    # ── MCA (Machine Check Architecture) decoder ──────────
    mca_results = scan_logs_for_mca_errors(logs)
    for j, mca in enumerate(mca_results):
        facts.append(Fact(
            id=f"mca_{j}", description=f"MCA DECODED: {mca.description}",
            component=mca.likely_component, metric="mca_error",
            value=mca.error_type, status=mca.severity,
        ))
        entry = f"🧠 MCA Bank {mca.bank} ({mca.bank_name}): {mca.error_type} → {mca.action}"
        if mca.severity == "critical":
            critical.append(entry)
        else:
            warnings.append(entry)

    # ── PCIe AER (Advanced Error Reporting) decoder ───────
    pcie_results = scan_logs_for_pcie_errors(logs)
    for k, pcie in enumerate(pcie_results):
        facts.append(Fact(
            id=f"pcie_{k}", description=f"PCIe DECODED: {pcie.description}",
            component=pcie.device_info, metric="pcie_error",
            value=pcie.error_name, status=pcie.severity,
        ))
        entry = f"🔴 PCIe {pcie.error_type}: {pcie.error_name} on {pcie.device_info} → {pcie.action}"
        if pcie.severity == "critical":
            critical.append(entry)
        else:
            warnings.append(entry)

    mca_note = f", {len(mca_results)} MCA decoded" if mca_results else ""
    pcie_note = f", {len(pcie_results)} PCIe decoded" if pcie_results else ""
    summary = f"{len(logs)} log entries — {crit_count} critical/error, {warn_count} warning{mca_note}{pcie_note}"
    return ToolResult(tool_name="check_logs", success=True, summary=summary,
                      facts=facts, warnings=warnings, critical=critical,
                      raw_data={"logs": logs[:50], "mca_decoded": [vars(m) for m in mca_results],
                                "pcie_decoded": [vars(p) for p in pcie_results]})


def parse_system_info(raw: Dict[str, Any]) -> ToolResult:
    si = raw.get("system_info") or raw.get("server_info")
    if not si:
        return ToolResult(tool_name="check_system_info", success=False, summary="System info unavailable")
    model = si.get("model", "?")
    tag = si.get("service_tag") or si.get("serial_number", "?")
    bios = si.get("bios_version") or si.get("firmware_version", "?")
    idrac = si.get("idrac_version", "?")
    power = si.get("power_state", "?")
    hostname = si.get("hostname", "?")
    cpu_model = si.get("cpu_model", "?")
    cpu_count = si.get("cpu_count", 0)
    total_mem = si.get("total_memory_gb", 0)
    manufacturer = si.get("manufacturer", "Dell Inc.")

    facts = [
        Fact(id="sys_model", description=f"Model: {model}", component="System", metric="model", value=model, status="ok"),
        Fact(id="sys_tag", description=f"Service Tag: {tag}", component="System", metric="service_tag", value=tag, status="ok"),
        Fact(id="sys_bios", description=f"BIOS: {bios}", component="System", metric="bios_version", value=bios, status="ok"),
        Fact(id="sys_idrac", description=f"iDRAC: {idrac}", component="System", metric="idrac_version", value=str(idrac), status="ok"),
        Fact(id="sys_power", description=f"Power: {power}", component="System", metric="power_state", value=str(power), status="ok"),
        Fact(id="sys_hostname", description=f"Hostname: {hostname}", component="System", metric="hostname", value=str(hostname), status="ok"),
        Fact(id="sys_cpu", description=f"CPU: {cpu_model} × {cpu_count}", component="System", metric="cpu", value=cpu_model, status="ok"),
        Fact(id="sys_mem", description=f"Total RAM: {total_mem} GB", component="System", metric="total_memory_gb", value=str(total_mem), status="ok"),
    ]
    summary = f"{model} (Tag: {tag}) — BIOS {bios}, iDRAC {idrac}, CPU {cpu_model} × {cpu_count}, RAM {total_mem}GB, Power {power}"
    return ToolResult(tool_name="check_system_info", success=True, summary=summary,
                      facts=facts, raw_data=si)


# ═══════════════════════════════════════════════════════════════
# Firmware parser — compare against Dell catalog
# ═══════════════════════════════════════════════════════════════

def parse_firmware(raw: Any) -> ToolResult:
    """Parse firmware inventory and compare against Dell catalog."""
    from core.knowledge_base import check_firmware_against_catalog, get_firmware_summary

    fw_list = []
    if isinstance(raw, dict):
        fw_list = raw.get("firmware", raw.get("firmware_inventory", raw.get("data", [])))
        if isinstance(fw_list, dict):
            fw_list = fw_list.get("firmware", [])
    elif isinstance(raw, list):
        fw_list = raw

    if not fw_list:
        return ToolResult(
            tool_name="check_firmware", success=True,
            summary="No firmware inventory data available.",
            facts=[Fact(id="firmware_status", description="Firmware inventory unavailable",
                        component="Firmware", metric="status", value="unavailable", status="warning")],
        )

    results = check_firmware_against_catalog(fw_list)
    summary_data = get_firmware_summary(results)

    facts = [
        Fact(id="firmware_total", description=f"{summary_data['total_components']} firmware components scanned",
             component="Firmware", metric="total", value=summary_data["total_components"], status="ok"),
        Fact(id="firmware_current", description=f"{summary_data['up_to_date']} firmware components up to date",
             component="Firmware", metric="current", value=summary_data["up_to_date"], status="ok"),
        Fact(id="firmware_outdated", description=f"{summary_data['outdated']} firmware components outdated",
             component="Firmware", metric="outdated", value=summary_data["outdated"],
             status="warning" if summary_data["outdated"] > 0 else "ok"),
        Fact(id="firmware_critical", description=f"{summary_data['critical_updates']} critical firmware updates needed",
             component="Firmware", metric="critical_updates", value=summary_data["critical_updates"],
             status="critical" if summary_data["critical_updates"] > 0 else "ok"),
        Fact(id="firmware_health", description=f"Firmware health score: {summary_data['health_score']}%",
             component="Firmware", metric="health_score", value=summary_data["health_score"], status="ok"),
    ]

    warnings = []
    critical = []
    for item in summary_data.get("critical_list", []):
        url = item.get("url", "")
        link = f" — Download: {url}" if url and url != "https://www.dell.com/support/home/drivers" else " (Check Dell support for your model)"
        critical.append(f"CRITICAL UPDATE: {item['component']} — installed {item['installed']}, latest {item['latest']}{link}")
    for item in summary_data.get("outdated_list", []):
        if not item.get("critical"):
            url = item.get("url", "")
            link = f" — Download: {url}" if url and url != "https://www.dell.com/support/home/drivers" else ""
            warnings.append(f"Outdated: {item['component']} — {item['installed']} → {item['latest']}{link}")

    up = summary_data["up_to_date"]
    out = summary_data["outdated"]
    crit = summary_data["critical_updates"]
    score = summary_data["health_score"]
    summ = f"Firmware check: {up}/{summary_data['total_components']} current, {out} outdated, {crit} critical. Health: {score}%"

    return ToolResult(
        tool_name="check_firmware", success=True, summary=summ,
        facts=facts, warnings=warnings, critical=critical,
        raw_data=summary_data,
    )

def parse_bios_attributes(raw: Any) -> ToolResult:
    """Parse BIOS attributes and highlight key settings."""
    bios = {}
    if isinstance(raw, dict):
        bios_wrapper = raw.get("bios", raw)
        # Redfish returns {"attributes": {...}, "bios_version": ...} — extract the attributes dict
        if isinstance(bios_wrapper, dict) and "attributes" in bios_wrapper:
            bios = bios_wrapper["attributes"]
        else:
            bios = bios_wrapper

    if not bios:
        return ToolResult(
            tool_name="check_bios", success=True,
            summary="No BIOS attributes available.",
            facts=[Fact(id="bios_status", description="BIOS attributes unavailable",
                        component="BIOS", metric="status", value="unavailable", status="warning")],
        )

    # Key settings to highlight
    key_settings = {
        "BootMode": {"label": "Boot Mode", "recommended": "Uefi"},
        "SysProfile": {"label": "System Profile", "recommended": "PerfOptimized"},
        "LogicalProc": {"label": "Logical Processor (HT)", "recommended": "Enabled"},
        "ProcVirtualization": {"label": "Virtualization", "recommended": "Enabled"},
        "ProcCStates": {"label": "C-States", "recommended": None},
        "ProcTurboMode": {"label": "Turbo Mode", "recommended": "Enabled"},
        "MemOpMode": {"label": "Memory Mode", "recommended": "OptimizerMode"},
        "MemTest": {"label": "Memory Test", "recommended": "Enabled"},
        "SerialComm": {"label": "Serial Communication", "recommended": None},
        "EmbSata": {"label": "Embedded SATA", "recommended": None},
        "SecurityFreezeLock": {"label": "Security Freeze Lock", "recommended": None},
        "TpmSecurity": {"label": "TPM Security", "recommended": "On"},
        "AcPwrRcvry": {"label": "AC Power Recovery", "recommended": "Last"},
        "ProcX2Apic": {"label": "x2APIC Mode", "recommended": "Enabled"},
        "InBandManageabilityInterface": {"label": "In-Band Mgmt", "recommended": None},
    }

    facts = []
    warnings = []
    settings_found = 0
    total_attrs = len(bios)

    for attr_name, info in key_settings.items():
        val = bios.get(attr_name)
        if val is None:
            # Try case-insensitive match
            for k, v in bios.items():
                if k.lower() == attr_name.lower():
                    val = v
                    break
        if val is not None:
            settings_found += 1
            status = "ok"
            if info["recommended"] and str(val) != info["recommended"]:
                status = "warning"
                warnings.append(f"{info['label']}: {val} (recommended: {info['recommended']})")
            facts.append(Fact(
                id=f"bios_{attr_name}", description=f"{info['label']}: {val}",
                component="BIOS", metric=attr_name, value=str(val), status=status,
            ))

    summary = f"BIOS: {total_attrs} attributes scanned, {settings_found} key settings checked"
    if warnings:
        summary += f", {len(warnings)} non-optimal"

    return ToolResult(
        tool_name="check_bios", success=True, summary=summary,
        facts=facts, warnings=warnings,
        raw_data={"total_attributes": total_attrs, "key_settings": settings_found,
                  "all_attributes": bios},
    )


def parse_tsr_result(raw: Any) -> ToolResult:
    """Parse TSR (Tech Support Report) collection result."""
    data = {}
    if isinstance(raw, dict):
        data = raw.get("tsr_result", raw)

    success = data.get("success", False)
    job_id = data.get("job_id", data.get("collection_id", ""))
    status_msg = data.get("status", "unknown")

    if success:
        summary = f"TSR collection initiated — Job: {job_id or 'pending'}"
        facts = [Fact(id="tsr_status", description=f"TSR collection started: {job_id}",
                      component="Support", metric="tsr_job", value=str(job_id), status="ok")]
    else:
        summary = f"TSR collection failed: {status_msg}"
        facts = [Fact(id="tsr_status", description=f"TSR failed: {status_msg}",
                      component="Support", metric="tsr_job", value="failed", status="critical")]

    return ToolResult(
        tool_name="collect_tsr", success=success, summary=summary,
        facts=facts, raw_data=data,
    )


def parse_post_codes(raw: Any) -> ToolResult:
    """Parse POST codes for no-POST troubleshooting."""
    data = {}
    if isinstance(raw, dict):
        data = raw.get("post_codes", raw)

    current_code = data.get("current_post_code", data.get("CurrentPostCode", ""))
    last_state = data.get("last_state", data.get("LastState", ""))
    boot_progress = data.get("boot_progress", data.get("BootProgress", ""))
    post_history = data.get("post_code_history", data.get("PostCodeHistory", []))

    facts = []
    warnings = []
    critical = []

    if current_code:
        facts.append(Fact(id="post_current", description=f"Current POST code: {current_code}",
                          component="System", metric="post_code", value=str(current_code), status="ok"))

    if last_state:
        facts.append(Fact(id="post_last_state", description=f"Last boot state: {last_state}",
                          component="System", metric="boot_state", value=str(last_state), status="ok"))

    if boot_progress:
        facts.append(Fact(id="post_boot_progress", description=f"Boot progress: {boot_progress}",
                          component="System", metric="boot_progress", value=str(boot_progress), status="ok"))

    # Check for stuck POST
    stuck_keywords = ["error", "fail", "halt", "stuck", "0x00"]
    if current_code and any(kw in str(current_code).lower() for kw in stuck_keywords):
        critical.append(f"POST appears stuck at code: {current_code}")

    # Known Dell POST codes
    dell_post_codes = {
        "0x00": ("System halted or no POST", "critical"),
        "0x19": ("Pre-memory North Bridge init", "warning"),
        "0x36": ("CPU initialization error", "critical"),
        "0x52": ("Memory not detected", "critical"),
        "0x5A": ("Memory config error — wrong DIMM population", "critical"),
        "0x62": ("PCIe enumeration — possible stuck on bad card", "warning"),
        "0x76": ("USB initialization", "ok"),
        "0x90": ("Boot device selection", "ok"),
        "0xAE": ("Legacy boot started", "ok"),
        "0xFF": ("Boot complete / OS handoff", "ok"),
    }

    code_str = str(current_code).strip()
    if code_str in dell_post_codes:
        desc, sev = dell_post_codes[code_str]
        facts.append(Fact(id="post_decoded", description=f"POST decoded: {desc}",
                          component="System", metric="post_decoded", value=desc, status=sev))
        if sev == "critical":
            critical.append(f"POST code {code_str}: {desc}")
        elif sev == "warning":
            warnings.append(f"POST code {code_str}: {desc}")

    hist_count = len(post_history) if isinstance(post_history, list) else 0
    summary = f"POST codes: current={current_code or 'N/A'}, boot_progress={boot_progress or 'N/A'}"
    if hist_count:
        summary += f", {hist_count} history entries"

    return ToolResult(
        tool_name="check_post_codes", success=True, summary=summary,
        facts=facts, warnings=warnings, critical=critical,
        raw_data=data,
    )


# ═══════════════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════════════

AGENT_TOOLS: Dict[str, AgentTool] = {
    "check_system_info": AgentTool(
        name="check_system_info",
        description="Get server identity — model, service tag, BIOS version. Always run first.",
        command="get_server_info",
        action_level="read_only",
        categories=[HypothesisCategory.SYSTEM],
        trigger_keywords=["identify", "model", "service tag", "bios", "firmware"],
        parser=parse_system_info,
    ),
    "check_health": AgentTool(
        name="check_health",
        description="Get overall system health status, critical issues, and warnings.",
        command="health_check",
        action_level="read_only",
        categories=[HypothesisCategory.SYSTEM],
        trigger_keywords=["health", "status", "overall", "critical"],
        parser=parse_health,
    ),
    "check_temperatures": AgentTool(
        name="check_temperatures",
        description="Read all temperature sensors. Use when suspecting thermal issues or after finding fan anomalies.",
        command="get_temperature_sensors",
        action_level="read_only",
        categories=[HypothesisCategory.THERMAL],
        trigger_keywords=["hot", "thermal", "overheat", "temperature", "throttle", "fan", "cooling"],
        parser=parse_temperatures,
    ),
    "check_fans": AgentTool(
        name="check_fans",
        description="Read all fan speeds and status. Use to check cooling subsystem or correlate with thermal findings.",
        command="get_fans",
        action_level="read_only",
        categories=[HypothesisCategory.THERMAL],
        trigger_keywords=["fan", "cooling", "loud", "noise", "rpm", "airflow"],
        parser=parse_fans,
    ),
    "check_power_supplies": AgentTool(
        name="check_power_supplies",
        description="Check PSU status, wattage, and redundancy. Use for power or unexpected shutdown issues.",
        command="get_power_supplies",
        action_level="read_only",
        categories=[HypothesisCategory.POWER],
        trigger_keywords=["power", "psu", "shutdown", "reboot", "voltage", "watts", "redundancy"],
        parser=parse_power_supplies,
    ),
    "check_memory": AgentTool(
        name="check_memory",
        description="Get all DIMM details — size, type, speed, status. Use for memory errors or blue screens.",
        command="get_memory",
        action_level="read_only",
        categories=[HypothesisCategory.MEMORY],
        trigger_keywords=["memory", "ram", "dimm", "ecc", "blue screen", "bsod", "correctable"],
        parser=parse_memory,
    ),
    "check_storage": AgentTool(
        name="check_storage",
        description="Get all storage devices — drives, capacity, status. Use for RAID, disk, or I/O issues.",
        command="get_storage_devices",
        action_level="read_only",
        categories=[HypothesisCategory.STORAGE],
        trigger_keywords=["disk", "drive", "raid", "storage", "ssd", "hdd", "io", "slow", "degraded"],
        parser=parse_storage,
    ),
    "check_network": AgentTool(
        name="check_network",
        description="Get all NIC details — link status, speed, MAC. Use for connectivity or network issues.",
        command="get_network_interfaces",
        action_level="read_only",
        categories=[HypothesisCategory.NETWORK],
        trigger_keywords=["network", "nic", "link", "ethernet", "connectivity", "ip", "latency"],
        parser=parse_network,
    ),
    "check_logs": AgentTool(
        name="check_logs",
        description="Collect and scan SEL/LC logs for errors, patterns, and Dell error codes. Essential for any investigation.",
        command="collect_logs",
        action_level="read_only",
        categories=[
            HypothesisCategory.SYSTEM, HypothesisCategory.THERMAL,
            HypothesisCategory.POWER, HypothesisCategory.MEMORY,
            HypothesisCategory.STORAGE, HypothesisCategory.CPU,
        ],
        trigger_keywords=["log", "error", "event", "sel", "history", "when", "timeline"],
        parser=parse_logs,
    ),
    "check_firmware": AgentTool(
        name="check_firmware",
        description="Get all installed firmware versions and compare against Dell's latest catalog. Flags outdated BIOS, iDRAC, NIC, RAID, drive firmware.",
        command="get_firmware_inventory",
        action_level="read_only",
        categories=[HypothesisCategory.FIRMWARE, HypothesisCategory.SYSTEM],
        trigger_keywords=["firmware", "bios", "idrac", "update", "version", "outdated", "patch", "driver"],
        parser=parse_firmware,
    ),
    "check_bios": AgentTool(
        name="check_bios",
        description="Read BIOS/UEFI settings — boot mode, C-States, turbo, virtualization, memory mode, TPM. Highlights non-optimal configurations.",
        command="get_bios_attributes",
        action_level="read_only",
        categories=[HypothesisCategory.SYSTEM, HypothesisCategory.CPU, HypothesisCategory.FIRMWARE],
        trigger_keywords=["bios", "uefi", "boot", "c-state", "turbo", "virtualization", "tpm", "settings", "configuration"],
        parser=parse_bios_attributes,
    ),
    "collect_tsr": AgentTool(
        name="collect_tsr",
        description="Collect a Technical Support Report (TSR) from iDRAC — comprehensive system snapshot for Dell support escalation.",
        command="export_tsr",
        action_level="diagnostic",
        categories=[HypothesisCategory.SYSTEM],
        trigger_keywords=["tsr", "support", "collect", "export", "report", "escalate", "dell support"],
        parser=parse_tsr_result,
    ),
    "check_post_codes": AgentTool(
        name="check_post_codes",
        description="Get POST codes and boot progress — essential for no-POST and boot failure troubleshooting. Decodes Dell POST codes.",
        command="get_post_codes",
        action_level="read_only",
        categories=[HypothesisCategory.SYSTEM, HypothesisCategory.CPU],
        trigger_keywords=["post", "boot", "no post", "won't boot", "stuck", "power on", "amber", "no video"],
        parser=parse_post_codes,
    ),
}


def parse_boot_order(raw: Dict[str, Any]) -> ToolResult:
    """Parse boot order data."""
    boot_data = raw.get("boot_order", raw.get("data", {}))
    if isinstance(boot_data, dict):
        # Redfish returns: boot_order (list), boot_source_override_mode, boot_source_override_target, etc.
        current = boot_data.get("boot_order", boot_data.get("BootOrder", []))
        boot_mode = boot_data.get("boot_source_override_mode", boot_data.get("BootSourceOverrideMode", "Unknown"))
        override = boot_data.get("boot_source_override_target", boot_data.get("BootSourceOverrideTarget", "None"))
        enabled = boot_data.get("boot_source_override_enabled", boot_data.get("BootSourceOverrideEnabled", "Disabled"))
        allowed = boot_data.get("allowed_boot_sources", [])
        uefi_target = boot_data.get("uefi_target", "")
    else:
        current, boot_mode, override, enabled, allowed, uefi_target = [], "Unknown", "None", "Disabled", [], ""

    facts = [
        Fact(id="boot_mode", description=f"Boot mode: {boot_mode}", component="Boot", metric="boot_mode", value=str(boot_mode), status="ok"),
        Fact(id="boot_override", description=f"Boot override: {override} ({enabled})", component="Boot", metric="boot_override", value=str(override), status="ok"),
    ]
    if isinstance(current, list):
        for i, dev in enumerate(current):
            dev_name = dev if isinstance(dev, str) else str(dev)
            facts.append(Fact(id=f"boot_{i}", description=f"Boot #{i+1}: {dev_name}", component="Boot", metric="boot_order", value=dev_name, status="ok"))
    if allowed:
        facts.append(Fact(id="boot_allowed", description=f"Allowed boot sources: {', '.join(allowed)}", component="Boot", metric="allowed_sources", value=str(allowed), status="ok"))
    if uefi_target:
        facts.append(Fact(id="boot_uefi", description=f"UEFI target: {uefi_target}", component="Boot", metric="uefi_target", value=uefi_target, status="ok"))

    count = len(current) if isinstance(current, list) else 0
    summary = f"Boot order: {count} devices, mode={boot_mode}, override={override}"
    return ToolResult(tool_name="check_boot_order", success=True, summary=summary, facts=facts, raw_data=boot_data)


def parse_idrac_network(raw: Dict[str, Any]) -> ToolResult:
    """Parse iDRAC network configuration."""
    data = raw.get("idrac_network", raw.get("data", raw))
    facts, warnings = [], []

    if isinstance(data, dict):
        # Redfish returns {"interfaces": [...]} with each interface having detailed fields
        interfaces = data.get("interfaces", [])
        if interfaces:
            for i, iface in enumerate(interfaces):
                iface_id = iface.get("id", f"eth{i}")
                name = iface.get("name", iface_id)
                ip = iface.get("ipv4_address", "N/A")
                subnet = iface.get("ipv4_subnet", "N/A")
                gw = iface.get("ipv4_gateway", "N/A")
                mac = iface.get("mac_address", "N/A")
                origin = iface.get("ipv4_origin", "Unknown")
                speed = iface.get("speed_mbps", "N/A")
                hostname = iface.get("host_name", "")
                fqdn = iface.get("fqdn", "")
                dns = iface.get("dns_servers", [])
                vlan_on = iface.get("vlan_enabled", False)
                vlan_id = iface.get("vlan_id", "")
                status = iface.get("status", "OK")

                facts.extend([
                    Fact(id=f"idrac_ip_{i}", description=f"[{name}] IP: {ip} ({origin})", component="iDRAC Network", metric="ip", value=str(ip), status="ok"),
                    Fact(id=f"idrac_subnet_{i}", description=f"[{name}] Subnet: {subnet}", component="iDRAC Network", metric="subnet", value=str(subnet), status="ok"),
                    Fact(id=f"idrac_gw_{i}", description=f"[{name}] Gateway: {gw}", component="iDRAC Network", metric="gateway", value=str(gw), status="ok"),
                    Fact(id=f"idrac_mac_{i}", description=f"[{name}] MAC: {mac}", component="iDRAC Network", metric="mac", value=str(mac), status="ok"),
                    Fact(id=f"idrac_speed_{i}", description=f"[{name}] Speed: {speed} Mbps", component="iDRAC Network", metric="speed", value=str(speed), status="ok"),
                ])
                if hostname:
                    facts.append(Fact(id=f"idrac_hostname_{i}", description=f"[{name}] Hostname: {hostname}", component="iDRAC Network", metric="hostname", value=hostname, status="ok"))
                if fqdn:
                    facts.append(Fact(id=f"idrac_fqdn_{i}", description=f"[{name}] FQDN: {fqdn}", component="iDRAC Network", metric="fqdn", value=fqdn, status="ok"))
                if dns:
                    facts.append(Fact(id=f"idrac_dns_{i}", description=f"[{name}] DNS: {', '.join(dns)}", component="iDRAC Network", metric="dns", value=str(dns), status="ok"))
                if vlan_on:
                    facts.append(Fact(id=f"idrac_vlan_{i}", description=f"[{name}] VLAN: {vlan_id}", component="iDRAC Network", metric="vlan", value=str(vlan_id), status="ok"))

            primary = interfaces[0]
            primary_ip = primary.get("ipv4_address", "N/A")
            primary_mac = primary.get("mac_address", "N/A")
            primary_origin = primary.get("ipv4_origin", "")
            summary = f"iDRAC Network: {primary_ip} ({primary_origin}), MAC={primary_mac}, {len(interfaces)} interface(s)"
        else:
            # Fallback for flat dict format
            ip = data.get("IPv4Address", data.get("ip", "N/A"))
            mac = data.get("MACAddress", data.get("mac", "N/A"))
            facts.append(Fact(id="idrac_ip", description=f"iDRAC IP: {ip}", component="iDRAC Network", metric="ip", value=str(ip), status="ok"))
            summary = f"iDRAC Network: {ip}, MAC={mac}"
    else:
        summary = "iDRAC network data unavailable"

    return ToolResult(tool_name="check_idrac_network", success=True, summary=summary, facts=facts, warnings=warnings, raw_data=data)


def parse_idrac_users(raw: Dict[str, Any]) -> ToolResult:
    """Parse iDRAC user accounts."""
    data = raw.get("idrac_users", raw.get("data", raw))
    facts, warnings = [], []

    users = data if isinstance(data, list) else data.get("users", []) if isinstance(data, dict) else []
    for i, u in enumerate(users):
        name = u.get("UserName", u.get("username", f"User-{i}"))
        role = u.get("RoleId", u.get("role", "Unknown"))
        enabled = u.get("Enabled", u.get("enabled", "Unknown"))
        locked = u.get("Locked", u.get("locked", False))
        status = "warning" if locked else "ok"
        if locked:
            warnings.append(f"User '{name}' is LOCKED")
        facts.append(Fact(
            id=f"idrac_user_{i}", description=f"User: {name} (Role: {role}, Enabled: {enabled}, Locked: {locked})",
            component="iDRAC", metric="user", value=name, status=status,
        ))

    summary = f"iDRAC Users: {len(users)} accounts"
    if warnings:
        summary += f" | {len(warnings)} locked"
    return ToolResult(tool_name="check_idrac_users", success=True, summary=summary, facts=facts, warnings=warnings, raw_data=data)


def parse_lifecycle(raw: Dict[str, Any]) -> ToolResult:
    """Parse Lifecycle Controller status."""
    data = raw.get("lifecycle_status", raw.get("data", raw))
    facts = []

    if isinstance(data, dict):
        # Redfish returns: manager_status, manager_state, firmware_version, lc_service_available, lc_attributes
        mgr_health = data.get("manager_status", data.get("Status", "Unknown"))
        mgr_state = data.get("manager_state", data.get("State", "Unknown"))
        fw_ver = data.get("firmware_version", data.get("Version", "N/A"))
        lc_avail = data.get("lc_service_available", None)
        lc_attrs = data.get("lc_attributes", {})

        health_status = "ok" if _is_healthy(str(mgr_health)) else "warning"
        facts.extend([
            Fact(id="lc_health", description=f"Manager Health: {mgr_health}", component="Lifecycle", metric="health", value=str(mgr_health), status=health_status),
            Fact(id="lc_state", description=f"Manager State: {mgr_state}", component="Lifecycle", metric="state", value=str(mgr_state), status="ok"),
            Fact(id="lc_firmware", description=f"iDRAC Firmware: {fw_ver}", component="Lifecycle", metric="firmware", value=str(fw_ver), status="ok"),
        ])
        if lc_avail is not None:
            avail_str = "Available" if lc_avail else "Unavailable"
            facts.append(Fact(id="lc_service", description=f"LC Service: {avail_str}", component="Lifecycle", metric="lc_service", value=avail_str, status="ok" if lc_avail else "warning"))

        for attr_name, attr_val in lc_attrs.items():
            facts.append(Fact(id=f"lc_attr_{attr_name}", description=f"{attr_name}: {attr_val}", component="Lifecycle", metric=attr_name, value=str(attr_val), status="ok"))

        summary = f"Lifecycle Controller: Health={mgr_health}, State={mgr_state}, FW={fw_ver}"
        if lc_avail is not None:
            summary += f", LC Service={'Available' if lc_avail else 'Unavailable'}"
    else:
        summary = "Lifecycle Controller data unavailable"

    return ToolResult(tool_name="check_lifecycle", success=True, summary=summary, facts=facts, raw_data=data)


def parse_jobs(raw: Dict[str, Any]) -> ToolResult:
    """Parse iDRAC job queue."""
    data = raw.get("jobs", raw.get("data", raw))
    facts, warnings = [], []

    jobs = data if isinstance(data, list) else data.get("Members", data.get("jobs", [])) if isinstance(data, dict) else []

    def _get_state(j):
        return j.get("job_state", j.get("JobState", j.get("status", ""))).lower()

    pending = [j for j in jobs if _get_state(j) not in ("completed", "")]
    completed = [j for j in jobs if _get_state(j) == "completed"]

    for i, j in enumerate(jobs[:20]):
        name = j.get("name", j.get("Name", f"Job-{i}"))
        state = j.get("job_state", j.get("JobState", "Unknown"))
        pct = j.get("percent_complete", j.get("PercentComplete", "N/A"))
        msg = j.get("message", j.get("Message", ""))
        job_type = j.get("job_type", j.get("JobType", ""))
        start = j.get("start_time", j.get("StartTime", ""))
        status = "ok" if state.lower() == "completed" else "warning"
        desc = f"{name}: {state}"
        if pct and pct != "N/A":
            desc += f" ({pct}%)"
        if job_type:
            desc += f" [{job_type}]"
        if msg:
            desc += f" — {msg[:80]}"
        facts.append(Fact(
            id=f"job_{i}", description=desc,
            component="Jobs", metric="job_state", value=state, status=status,
        ))

    if not jobs:
        facts.append(Fact(id="jobs_empty", description="Job queue is empty — no pending or completed jobs",
                          component="Jobs", metric="job_count", value="0", status="ok"))

    summary = f"Job Queue: {len(jobs)} total, {len(pending)} pending, {len(completed)} completed"
    return ToolResult(tool_name="check_jobs", success=True, summary=summary, facts=facts, warnings=warnings, raw_data=data)


def parse_idrac_cert(raw: Dict[str, Any]) -> ToolResult:
    """Parse iDRAC SSL certificate info."""
    data = raw.get("ssl_certificates", raw.get("ssl_certificate", raw.get("data", raw)))
    facts, warnings = [], []

    if isinstance(data, dict):
        available = data.get("available", True)
        if not available:
            return ToolResult(tool_name="check_idrac_cert", success=True,
                              summary="SSL certificate service not available on this iDRAC.",
                              facts=[Fact(id="cert_na", description="Certificate service unavailable",
                                          component="Certificate", metric="status", value="unavailable", status="warning")],
                              raw_data=data)

        certs = data.get("certificates", [])
        if not certs:
            return ToolResult(tool_name="check_idrac_cert", success=True,
                              summary="No SSL certificates found.",
                              facts=[Fact(id="cert_none", description="No certificates found",
                                          component="Certificate", metric="status", value="none", status="warning")],
                              raw_data=data)

        for i, cert in enumerate(certs):
            cert_id = cert.get("id", f"cert-{i}")
            subject = cert.get("subject", {})
            issuer = cert.get("issuer", {})
            valid_from = cert.get("valid_not_before", cert.get("ValidNotBefore", "N/A"))
            valid_to = cert.get("valid_not_after", cert.get("ValidNotAfter", "N/A"))
            key_usage = cert.get("key_usage", cert.get("KeyUsage", []))

            # Format subject/issuer — could be dict or string
            if isinstance(subject, dict):
                subj_str = subject.get("CommonName", subject.get("CN", str(subject)))
            else:
                subj_str = str(subject)
            if isinstance(issuer, dict):
                iss_str = issuer.get("CommonName", issuer.get("CN", str(issuer)))
            else:
                iss_str = str(issuer)

            facts.extend([
                Fact(id=f"cert_{i}_subject", description=f"Certificate [{cert_id}] Subject: {subj_str}",
                     component="Certificate", metric="subject", value=subj_str, status="ok"),
                Fact(id=f"cert_{i}_issuer", description=f"Issuer: {iss_str}",
                     component="Certificate", metric="issuer", value=iss_str, status="ok"),
                Fact(id=f"cert_{i}_valid_from", description=f"Valid From: {valid_from}",
                     component="Certificate", metric="valid_from", value=str(valid_from), status="ok"),
                Fact(id=f"cert_{i}_valid_to", description=f"Valid To: {valid_to}",
                     component="Certificate", metric="valid_to", value=str(valid_to), status="ok"),
            ])

        summary = f"SSL Certificates: {len(certs)} found"
        if certs:
            first_to = certs[0].get("valid_not_after", certs[0].get("ValidNotAfter", "?"))
            summary += f", first expires: {first_to}"
    else:
        summary = "Certificate data unavailable"

    return ToolResult(tool_name="check_idrac_cert", success=True, summary=summary, facts=facts, warnings=warnings, raw_data=data)


# ═══════════════════════════════════════════════════════════════
# Additional Tool Registrations
# ═══════════════════════════════════════════════════════════════

AGENT_TOOLS["check_boot_order"] = AgentTool(
    name="check_boot_order",
    description="Get the server boot order, boot mode, and one-time override settings.",
    command="get_boot_order",
    action_level="read_only",
    categories=[HypothesisCategory.SYSTEM],
    trigger_keywords=["boot", "boot order", "boot sequence", "pxe", "uefi", "legacy"],
    parser=parse_boot_order,
)

AGENT_TOOLS["check_idrac_network"] = AgentTool(
    name="check_idrac_network",
    description="Get iDRAC management network configuration — IP, subnet, gateway, DNS, VLAN, MAC.",
    command="get_idrac_network_config",
    action_level="read_only",
    categories=[HypothesisCategory.SYSTEM],
    trigger_keywords=["idrac", "management", "bmc", "ip address", "network config"],
    parser=parse_idrac_network,
)

AGENT_TOOLS["check_idrac_users"] = AgentTool(
    name="check_idrac_users",
    description="List iDRAC user accounts with roles and lock status.",
    command="get_idrac_users",
    action_level="read_only",
    categories=[HypothesisCategory.SYSTEM],
    trigger_keywords=["idrac user", "account", "login", "access"],
    parser=parse_idrac_users,
)

AGENT_TOOLS["check_lifecycle"] = AgentTool(
    name="check_lifecycle",
    description="Get Lifecycle Controller status, version, and readiness.",
    command="get_lifecycle_status",
    action_level="read_only",
    categories=[HypothesisCategory.SYSTEM, HypothesisCategory.FIRMWARE],
    trigger_keywords=["lifecycle", "lc", "controller", "readiness"],
    parser=parse_lifecycle,
)

AGENT_TOOLS["check_jobs"] = AgentTool(
    name="check_jobs",
    description="Get iDRAC job queue — pending, running, and completed jobs.",
    command="get_jobs",
    action_level="read_only",
    categories=[HypothesisCategory.SYSTEM],
    trigger_keywords=["job", "queue", "pending", "scheduled", "task"],
    parser=parse_jobs,
)

AGENT_TOOLS["check_idrac_cert"] = AgentTool(
    name="check_idrac_cert",
    description="Get iDRAC SSL certificate details — subject, issuer, validity dates.",
    command="get_ssl_certificate_info",
    action_level="read_only",
    categories=[HypothesisCategory.SYSTEM],
    trigger_keywords=["certificate", "ssl", "tls", "cert", "expiry"],
    parser=parse_idrac_cert,
)


def get_tool(name: str) -> Optional[AgentTool]:
    return AGENT_TOOLS.get(name)


def get_tools_for_category(category: HypothesisCategory) -> List[AgentTool]:
    return [t for t in AGENT_TOOLS.values() if category in t.categories]


def get_tools_for_keywords(keywords: List[str]) -> List[AgentTool]:
    """Rank tools by keyword relevance."""
    scored = []
    for tool in AGENT_TOOLS.values():
        score = sum(1 for kw in keywords if any(tk in kw.lower() for tk in tool.trigger_keywords))
        if score > 0:
            scored.append((tool, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored]


# ═══════════════════════════════════════════════════════════════
# Health Scoring Tool — NEW
# ═══════════════════════════════════════════════════════════════

def parse_health_score(raw: Any) -> ToolResult:
    """Parse subsystem data and calculate comprehensive health score."""
    from core.health_scorer import health_scorer
    
    if not isinstance(raw, dict):
        return ToolResult(tool_name="check_health_score", success=False, 
                          summary="Invalid health data format")
    
    # Extract subsystem data
    subsystem_data = {}
    
    # Thermal data
    if "thermal" in raw:
        subsystem_data["thermal"] = raw["thermal"]
    elif "Temperatures" in raw or "Fans" in raw:
        subsystem_data["thermal"] = raw
    
    # Power data
    if "power" in raw:
        subsystem_data["power"] = raw["power"]
    elif "PowerSupplies" in raw:
        subsystem_data["power"] = raw
    
    # Memory data
    if "memory" in raw:
        subsystem_data["memory"] = raw["memory"]
    elif "Memory" in raw:
        subsystem_data["memory"] = raw
    
    # Calculate health scores
    health_result = health_scorer.calculate_overall_health(subsystem_data)
    
    facts = []
    
    # Overall health fact
    facts.append(Fact(
        id="overall_health_score",
        description=f"Server overall health score: {health_result['overall_score']}/100",
        component="system",
        metric="health_score",
        value=health_result['overall_score'],
        unit="score",
        status="critical" if health_result['overall_status'] == "CRITICAL" else 
                "warning" if health_result['overall_status'] == "WARNING" else "ok"
    ))
    
    # Subsystem health facts
    for subsystem_name, subsystem_health in health_result['subsystems'].items():
        facts.append(Fact(
            id=f"{subsystem_name}_health_score",
            description=f"{subsystem_name.title()} health: {subsystem_health.score:.1f}/100 - {subsystem_health.summary}",
            component=subsystem_name,
            metric="health_score",
            value=subsystem_health.score,
            unit="score",
            status="critical" if subsystem_health.status.value == 0 else 
                    "warning" if subsystem_health.status.value == 1 else "ok"
        ))
    
    # Critical and warning issues
    critical_issues = []
    warning_issues = []
    
    for subsystem_name, subsystem_health in health_result['subsystems'].items():
        for metric in subsystem_health.metrics:
            if metric.status.value == 0:  # CRITICAL
                critical_issues.append(f"{subsystem_name}: {metric.details}")
            elif metric.status.value == 1:  # WARNING
                warning_issues.append(f"{subsystem_name}: {metric.details}")
    
    summary = f"Health Score: {health_result['overall_score']}/100 ({health_result['overall_status']})"
    if critical_issues:
        summary += f" - {len(critical_issues)} critical"
    if warning_issues:
        summary += f" - {len(warning_issues)} warnings"
    
    return ToolResult(
        tool_name="check_health_score",
        success=True,
        summary=summary,
        facts=facts,
        critical=critical_issues,
        warnings=warning_issues,
        raw_data=health_result
    )

# Register the new tool
AGENT_TOOLS["check_health_score"] = AgentTool(
    name="check_health_score",
    description="Calculate comprehensive health score across all subsystems",
    command="check_health_score",
    action_level="read_only",
    categories=[HypothesisCategory.THERMAL, HypothesisCategory.POWER, 
                HypothesisCategory.MEMORY, HypothesisCategory.STORAGE,
                HypothesisCategory.NETWORK, HypothesisCategory.FIRMWARE],
    trigger_keywords=["health", "score", "overall", "status", "condition"],
    parser=parse_health_score
)
