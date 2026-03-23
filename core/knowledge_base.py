"""
Advanced Diagnostic Knowledge Bases for Dell Server AI Agent
═══════════════════════════════════════════════════════════════
1. MCA (Machine Check Architecture) Bank → Error → Action lookup
2. PCIe AER (Advanced Error Reporting) Code → Root Cause → Action
3. Dell Firmware Catalog — latest known-good versions per model
4. Firmware update via Redfish SimpleUpdate
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 1. MACHINE CHECK ARCHITECTURE (MCA) DECODER
#    Intel/AMD CPU error bank → error type → action mapping
#    Reference: Intel SDM Vol 3B Ch 15, Dell TechDirect MCA guide
# ═══════════════════════════════════════════════════════════════

@dataclass
class MCADecodeResult:
    """Decoded Machine Check Architecture error."""
    bank: int
    bank_name: str
    error_type: str
    description: str
    severity: str          # critical, warning, informational
    likely_component: str  # CPU, memory controller, PCIe, QPI/UPI, cache
    action: str
    dell_workflow: Optional[str] = None
    escalation_needed: bool = False
    additional_info: str = ""

# Intel MCA Bank definitions (Xeon Scalable / Ice Lake / Sapphire Rapids)
MCA_BANKS = {
    0: {
        "name": "IFU (Instruction Fetch Unit)",
        "component": "CPU Core",
        "errors": {
            0x0001: ("Instruction cache parity error", "warning", "Run ePSA CPU diagnostics. If recurring, replace CPU.", "cpu_ierr"),
            0x0005: ("Internal parity error", "critical", "Collect TSR immediately. Contact Dell Support for CPU replacement.", "cpu_ierr"),
            0x0010: ("Microcode ROM parity error", "critical", "Update BIOS/microcode first. If persists, CPU replacement needed.", "cpu_ierr"),
            0x0150: ("IFU internal error", "critical", "Collect TSR. Try BIOS update. May need CPU replacement.", "cpu_ierr"),
        }
    },
    1: {
        "name": "DCU (Data Cache Unit)",
        "component": "CPU Core",
        "errors": {
            0x0001: ("Data cache L1 parity error", "warning", "Monitor frequency. If isolated, update BIOS. If recurring, replace CPU.", "cpu_ierr"),
            0x0010: ("Data cache read error", "critical", "Collect TSR. Run ePSA CPU diagnostics. May need replacement.", "cpu_ierr"),
            0x0174: ("DCU poison consumption", "critical", "Upstream error consumed by DCU. Check other MCA banks for root cause.", "cpu_ierr"),
        }
    },
    2: {
        "name": "DTLB (Data TLB)",
        "component": "CPU Core",
        "errors": {
            0x0001: ("TLB parity error", "warning", "Monitor. Try BIOS microcode update.", "cpu_ierr"),
            0x0014: ("TLB internal error", "critical", "Collect TSR. CPU replacement likely needed.", "cpu_ierr"),
        }
    },
    3: {
        "name": "MLC (Mid-Level Cache / L2)",
        "component": "CPU Core",
        "errors": {
            0x0001: ("L2 tag parity error", "warning", "Update BIOS microcode. Monitor for recurrence.", "cpu_ierr"),
            0x0010: ("L2 data read error", "warning", "Update BIOS. Run ePSA cache test. Replace CPU if recurring.", "cpu_ierr"),
            0x0135: ("L2 multi-hit error", "critical", "Serious cache coherency issue. Collect TSR, replace CPU.", "cpu_ierr"),
            0x0174: ("L2 poison consumption", "critical", "Check other banks for upstream error.", "cpu_ierr"),
        }
    },
    4: {
        "name": "IMC (Integrated Memory Controller)",
        "component": "Memory Subsystem",
        "errors": {
            0x0001: ("Memory read ECC error", "warning", "Identify failing DIMM from SEL. Reseat DIMM. Run memory diagnostics.", "memory_retrain"),
            0x0005: ("Memory address/command parity", "critical", "Memory controller error. Try reseating DIMMs. May need CPU replacement if IMC is faulty.", "memory_retrain"),
            0x0008: ("Memory scrubbing uncorrectable", "critical", "Replace failing DIMM. Enable PPR in BIOS.", "memory_retrain"),
            0x0010: ("Memory write error", "critical", "Reseat DIMMs. Swap DIMM to different channel to isolate DIMM vs IMC.", "memory_retrain"),
            0x0080: ("Memory channel failover", "warning", "A memory channel has been disabled. Check DIMM population rules.", "memory_retrain"),
            0x0090: ("Persistent memory error", "critical", "Replace DIMM. Run full memory diagnostic.", "memory_retrain"),
        }
    },
    5: {
        "name": "Intel QPI / UPI (Inter-processor Link)",
        "component": "CPU Interconnect",
        "errors": {
            0x0002: ("QPI/UPI link width degraded", "warning", "Check CPU seating. Reseat both CPUs. If in dual-CPU config, check CPU2 first.", None),
            0x0010: ("QPI/UPI link failure", "critical", "Reseat CPUs. Check for bent pins. May need new CPU or motherboard.", "cpu_ierr"),
            0x0020: ("QPI/UPI CRC error", "warning", "Clean CPU socket contacts. Reseat CPU. Update BIOS.", None),
        }
    },
    6: {
        "name": "IIO (Integrated I/O — PCIe Root Complex)",
        "component": "PCIe Subsystem",
        "errors": {
            0x0001: ("PCIe completion timeout", "warning", "Check PCIe device seating. Update device firmware. Try different slot.", None),
            0x0002: ("PCIe poisoned TLP received", "critical", "PCIe device sent bad data. Identify device in slot. Update drivers/firmware.", None),
            0x0004: ("PCIe unsupported request", "warning", "Driver/firmware incompatibility. Update device driver and firmware.", None),
            0x0010: ("PCIe ECRC error", "warning", "Enable/disable ECRC in BIOS. Update PCIe device firmware.", None),
            0x0029: ("PCIe ACS violation", "warning", "SR-IOV configuration issue. Check BIOS settings for ACS.", None),
            0x0090: ("IIO internal error", "critical", "Possible motherboard issue. Collect TSR, contact Dell Support.", "cpu_ierr"),
        }
    },
    7: {
        "name": "M2M (Mesh to Memory)",
        "component": "Memory Controller/Mesh",
        "errors": {
            0x0001: ("M2M read error", "critical", "Memory controller error. Check DIMMs in the affected channel.", "memory_retrain"),
            0x0005: ("M2M bucket error", "critical", "Internal mesh error. Collect TSR. Likely motherboard or CPU issue.", "cpu_ierr"),
        }
    },
    9: {
        "name": "CHA (Caching/Home Agent — LLC/L3)",
        "component": "CPU Last-Level Cache",
        "errors": {
            0x000A: ("LLC tag error", "warning", "Update BIOS microcode. Monitor.", "cpu_ierr"),
            0x000B: ("LLC data read error", "warning", "Update BIOS. Run ePSA. Replace CPU if recurring.", "cpu_ierr"),
            0x0136: ("LLC multi-hit", "critical", "Cache coherency failure. CPU replacement needed.", "cpu_ierr"),
        }
    },
    13: {
        "name": "IMC HA (Home Agent)",
        "component": "Memory Subsystem",
        "errors": {
            0x0001: ("HA read error", "critical", "Memory read error at Home Agent level. Replace failing DIMM.", "memory_retrain"),
            0x0010: ("HA write error", "critical", "Memory write path error. Reseat DIMMs, check channel population.", "memory_retrain"),
        }
    },
}

# Common MCACOD (Machine Check Architecture Code) patterns
MCACOD_PATTERNS = {
    0x0000: "No error",
    0x0001: "Unclassified error",
    0x0005: "Internal parity error",
    0x0010: "Generic external (bus/interconnect) error",
    0x0100: "Memory controller read error — generic",
    0x0110: "Memory controller read error — specific channel",
    0x0120: "Memory controller write error",
    0x0150: "Memory controller command/address error",
    0x0400: "Internal timer error",
    0x0E0B: "Generic internal unclassified error",
    0x0C00: "Bus/interconnect error — observation",
    0x0E00: "Bus/interconnect error — participation",
    0x0F00: "Bus/interconnect error — request/response",
}


def decode_mca_error(bank: int, status: int = 0, misc: int = 0,
                     addr: int = 0, log_message: str = "") -> MCADecodeResult:
    """Decode a Machine Check Architecture error from bank + status registers.
    
    Args:
        bank: MCA bank number (0-13+)
        status: MSR_IA32_MCi_STATUS register value
        misc: MSR_IA32_MCi_MISC value (optional)
        addr: MSR_IA32_MCi_ADDR value (optional)
        log_message: Raw log message for pattern matching
    """
    bank_info = MCA_BANKS.get(bank, {
        "name": f"Unknown Bank {bank}",
        "component": "Unknown",
        "errors": {}
    })

    # Extract MCACOD from status (bits 15:0)
    mcacod = status & 0xFFFF if status else 0

    # Try exact match first
    if mcacod in bank_info["errors"]:
        desc, sev, action, workflow = bank_info["errors"][mcacod]
    else:
        # Try pattern match on the log message
        desc, sev, action, workflow = _match_mca_from_log(bank, log_message, bank_info)

    return MCADecodeResult(
        bank=bank,
        bank_name=bank_info["name"],
        error_type=desc,
        description=f"MCA Bank {bank} ({bank_info['name']}): {desc}",
        severity=sev,
        likely_component=bank_info["component"],
        action=action,
        dell_workflow=workflow,
        escalation_needed=(sev == "critical"),
        additional_info=f"MCACOD=0x{mcacod:04X}" + (f", ADDR=0x{addr:016X}" if addr else ""),
    )


def _match_mca_from_log(bank: int, log_message: str, bank_info: dict) -> Tuple[str, str, str, Optional[str]]:
    """Try to match MCA error from log message text when register values aren't available."""
    msg_lower = log_message.lower()
    
    # Pattern matching on common Dell SEL message formats
    patterns = [
        (r"ierr|internal error", "CPU Internal Error (IERR)", "critical",
         "Collect TSR immediately. Check BIOS/firmware versions. Run ePSA CPU diagnostics.", "cpu_ierr"),
        (r"mcerr|machine check", "Machine Check Error (MCERR)", "critical",
         "Collect TSR. Decode MCA registers from TSR. Check for known BIOS fixes.", "cpu_ierr"),
        (r"catast|catastrophic", "Catastrophic error", "critical",
         "Hardware failure. Collect TSR, contact Dell Support immediately.", "cpu_ierr"),
        (r"corrected.*machine.*check|cmc", "Corrected Machine Check (CMC)", "warning",
         "Monitor frequency. If rate increases, schedule maintenance window.", None),
        (r"thermtrip|thermal.*trip", "CPU Thermal Trip", "critical",
         "CPU overheated. Check cooling immediately. May need thermal paste reapplication.", "thermal_remediation"),
        (r"ecc.*uncorrect|uce|multi.?bit", "Uncorrectable ECC (UCE)", "critical",
         "Replace failing DIMM immediately. Enable PPR. Run memory diagnostics.", "memory_retrain"),
        (r"ecc.*correct|ce|single.?bit", "Correctable ECC (CE)", "warning",
         "Monitor rate. If >10/day, schedule DIMM replacement. Enable PPR.", "memory_retrain"),
        (r"pci.*fatal|pcie.*error", "PCIe Fatal Error", "critical",
         "Check PCIe device in affected slot. Update firmware. Try reseating.", None),
    ]

    for pattern, desc, sev, action, workflow in patterns:
        if re.search(pattern, msg_lower):
            return desc, sev, action, workflow

    # Default: return generic info based on bank
    return (f"Error in {bank_info['name']}", "warning",
            f"Collect TSR. Check {bank_info['component']} health.", bank_info["errors"].get(0x0001, (None,None,None,None))[3])


def scan_logs_for_mca_errors(logs: List[Dict]) -> List[MCADecodeResult]:
    """Scan a list of log entries for Machine Check errors and decode them."""
    results = []
    mca_patterns = [
        r"machine\s*check", r"mca\s*bank", r"ierr", r"mcerr",
        r"cpu\d*\s*err", r"catast", r"corrected\s*machine",
        r"cpu\d*.*internal\s*error", r"thermtrip",
    ]
    combined_pattern = "|".join(mca_patterns)

    for log in logs:
        msg = log.get("message", "") or ""
        severity = log.get("severity", "")
        if not re.search(combined_pattern, msg, re.IGNORECASE):
            continue

        # Try to extract bank number from message
        bank_match = re.search(r"bank\s*[:#]?\s*(\d+)", msg, re.IGNORECASE)
        bank = int(bank_match.group(1)) if bank_match else 0

        # Try to extract status register
        status_match = re.search(r"status[=:\s]*(?:0x)?([0-9a-fA-F]+)", msg, re.IGNORECASE)
        status = int(status_match.group(1), 16) if status_match else 0

        result = decode_mca_error(bank=bank, status=status, log_message=msg)
        result.additional_info += f" | Source: {msg[:100]}"
        results.append(result)

    return results


# ═══════════════════════════════════════════════════════════════
# 2. PCIe AER (Advanced Error Reporting) DECODER
#    Error code → root cause → action mapping
#    Reference: PCIe Base Spec 5.0, Dell PCIe troubleshooting guide
# ═══════════════════════════════════════════════════════════════

@dataclass
class PCIeDecodeResult:
    """Decoded PCIe AER error."""
    error_type: str        # fatal, non-fatal, correctable
    error_name: str
    description: str
    likely_cause: str
    action: str
    slot_info: str
    device_info: str
    severity: str
    requires_reboot: bool = False
    firmware_related: bool = False

# PCIe AER Uncorrectable (Fatal) errors — bit position in AER status register
PCIE_FATAL_ERRORS = {
    0x00000001: {
        "name": "Training Error",
        "cause": "PCIe link failed to train during initialization",
        "action": "Reseat the PCIe card. Check for physical damage. Try a different slot.",
        "requires_reboot": True,
    },
    0x00000010: {
        "name": "Data Link Protocol Error (DLLP)",
        "cause": "Data link layer protocol violation — often a hardware issue",
        "action": "Reseat PCIe card. Clean gold contacts. Try different slot. If NIC/HBA, check cable.",
        "requires_reboot": True,
    },
    0x00000020: {
        "name": "Surprise Down Error",
        "cause": "PCIe device unexpectedly removed or lost power",
        "action": "Check PCIe card seating and power connectors. Check for thermal shutdown of device.",
        "requires_reboot": True,
    },
    0x00001000: {
        "name": "Poisoned TLP Received",
        "cause": "A Transaction Layer Packet arrived with poisoned data — upstream device sent bad data",
        "action": "Update device firmware/driver. If NIC, check cable integrity. If GPU, check VRAM.",
        "requires_reboot": False,
        "firmware_related": True,
    },
    0x00002000: {
        "name": "Flow Control Protocol Error",
        "cause": "Flow control credit violation — device misbehaving",
        "action": "Update device firmware. Check for known firmware bugs. Try BIOS update.",
        "requires_reboot": True,
        "firmware_related": True,
    },
    0x00004000: {
        "name": "Completion Timeout",
        "cause": "A PCIe request didn't get a response in time — device hung or too slow",
        "action": "Increase completion timeout in BIOS if available. Update device firmware. Check device health.",
        "requires_reboot": False,
        "firmware_related": True,
    },
    0x00008000: {
        "name": "Completer Abort",
        "cause": "Target device actively refused a request — usually a config/driver issue",
        "action": "Update device driver. Check BIOS PCIe settings (MMIO, ACS, ARI).",
        "requires_reboot": False,
    },
    0x00010000: {
        "name": "Unexpected Completion",
        "cause": "Received a completion that wasn't expected — usually a firmware bug",
        "action": "Update device firmware and BIOS. Check for known errata.",
        "requires_reboot": False,
        "firmware_related": True,
    },
    0x00020000: {
        "name": "Receiver Overflow",
        "cause": "Device's receive buffer overflowed — device too slow to process",
        "action": "Update device firmware. Check device thermals. May need hardware replacement.",
        "requires_reboot": True,
    },
    0x00040000: {
        "name": "Malformed TLP",
        "cause": "Transaction Layer Packet format is invalid — hardware issue",
        "action": "Reseat PCIe card. Try different slot. Likely hardware fault — replace if recurring.",
        "requires_reboot": True,
    },
    0x00080000: {
        "name": "ECRC Error",
        "cause": "End-to-end CRC check failed — data corruption in transit",
        "action": "Toggle ECRC in BIOS (PcieEcrc). Update device firmware. Check signal integrity.",
        "requires_reboot": False,
        "firmware_related": True,
    },
    0x00100000: {
        "name": "Unsupported Request Error",
        "cause": "Device received a request it doesn't understand — driver/config mismatch",
        "action": "Update device driver and firmware. Check BIOS PCIe settings. Verify IOMMU/VT-d config.",
        "requires_reboot": False,
        "firmware_related": True,
    },
    0x00200000: {
        "name": "ACS Violation",
        "cause": "Access Control Services violation — SR-IOV / virtualization misconfiguration",
        "action": "Check SR-IOV settings. Verify ACS is enabled in BIOS for VMs. Update hypervisor drivers.",
        "requires_reboot": False,
    },
    0x00400000: {
        "name": "Internal Error (Device)",
        "cause": "PCIe device reported an internal hardware error",
        "action": "Update device firmware. If recurring, replace the device.",
        "requires_reboot": True,
    },
}

# PCIe AER Correctable errors
PCIE_CORRECTABLE_ERRORS = {
    0x00000001: {
        "name": "Receiver Error",
        "cause": "8b/10b or 128b/130b decode error — signal integrity issue",
        "action": "Check cable quality (if external). Clean PCIe contacts. Monitor frequency.",
    },
    0x00000040: {
        "name": "Bad TLP",
        "cause": "TLP with bad LCRC — usually signal integrity",
        "action": "Reseat PCIe card. Check for dust. Monitor error rate.",
    },
    0x00000080: {
        "name": "Bad DLLP",
        "cause": "Data Link Layer Packet CRC error",
        "action": "Reseat card. Clean contacts. If frequent, try different slot.",
    },
    0x00000100: {
        "name": "Replay Num Rollover",
        "cause": "Too many TLP replay attempts — link instability",
        "action": "Reseat card. Update firmware. If recurring, possible slot/card failure.",
    },
    0x00001000: {
        "name": "Replay Timer Timeout",
        "cause": "Replay timer expired — device slow to acknowledge",
        "action": "Update device firmware. Check device thermals. Monitor frequency.",
    },
    0x00002000: {
        "name": "Advisory Non-Fatal Error",
        "cause": "Non-fatal error promoted from uncorrectable — usually harmless",
        "action": "Monitor. Usually informational. Update firmware if frequent.",
    },
    0x00004000: {
        "name": "Corrected Internal Error",
        "cause": "Device corrected an internal error — informational",
        "action": "Monitor rate. If increasing, schedule device firmware update or replacement.",
    },
    0x00008000: {
        "name": "Header Log Overflow",
        "cause": "Error logging buffer full — too many errors to log",
        "action": "Investigate root cause of high error rate. Likely another error type driving this.",
    },
}

# Common PCIe device types and slot identification
PCIE_DEVICE_TYPES = {
    "mellanox": "Network Adapter (Mellanox/NVIDIA ConnectX)",
    "broadcom": "Network Adapter (Broadcom)",
    "intel": "Network Adapter (Intel)",
    "qlogic": "HBA/Network (QLogic/Marvell)",
    "nvidia": "GPU (NVIDIA)",
    "perc": "RAID Controller (Dell PERC)",
    "boss": "Boot Optimized Storage (Dell BOSS)",
    "nvme": "NVMe SSD",
    "gpu": "GPU Accelerator",
    "nic": "Network Interface Card",
    "hba": "Host Bus Adapter (SAS/FC)",
    "ssd": "Solid State Drive",
}


def decode_pcie_error(error_code: int = 0, is_fatal: bool = True,
                       slot: str = "", device: str = "",
                       log_message: str = "") -> PCIeDecodeResult:
    """Decode a PCIe AER error from error code or log message."""
    error_db = PCIE_FATAL_ERRORS if is_fatal else PCIE_CORRECTABLE_ERRORS
    error_type = "Fatal" if is_fatal else "Correctable"

    # Try exact code match
    if error_code in error_db:
        info = error_db[error_code]
        return PCIeDecodeResult(
            error_type=error_type,
            error_name=info["name"],
            description=f"PCIe {error_type}: {info['name']}",
            likely_cause=info["cause"],
            action=info["action"],
            slot_info=slot or "Unknown",
            device_info=device or _identify_pcie_device(log_message),
            severity="critical" if is_fatal else "warning",
            requires_reboot=info.get("requires_reboot", False),
            firmware_related=info.get("firmware_related", False),
        )

    # Pattern match from log message
    return _match_pcie_from_log(log_message, error_type)


def _identify_pcie_device(log_message: str) -> str:
    """Try to identify the PCIe device from log message."""
    msg_lower = log_message.lower()
    for key, name in PCIE_DEVICE_TYPES.items():
        if key in msg_lower:
            return name
    # Try Bus:Device.Function notation
    bdf_match = re.search(r"(\d+:\d+[:.]\d+)", log_message)
    if bdf_match:
        return f"Device at BDF {bdf_match.group(1)}"
    return "Unknown PCIe device"


def _match_pcie_from_log(log_message: str, error_type: str) -> PCIeDecodeResult:
    """Match PCIe error from log message text."""
    msg_lower = log_message.lower()
    
    patterns = [
        (r"completion\s*timeout", "Completion Timeout", "critical" if "fatal" in error_type.lower() else "warning",
         "PCIe device did not respond in time",
         "Update device firmware. Increase timeout in BIOS if available.", True),
        (r"poison", "Poisoned TLP", "critical",
         "Upstream device sent corrupted data",
         "Update device firmware and driver. Check device health.", True),
        (r"surprise\s*down|link\s*down", "Surprise Link Down", "critical",
         "PCIe device lost power or was removed",
         "Check card seating and power. Check for thermal shutdown.", False),
        (r"malformed", "Malformed TLP", "critical",
         "Invalid PCIe packet format — hardware issue",
         "Reseat card. Try different slot. Replace if recurring.", False),
        (r"unsupported\s*request", "Unsupported Request", "warning",
         "Driver/firmware compatibility issue",
         "Update device driver and firmware. Check BIOS settings.", True),
        (r"receiver\s*error|signal\s*integrity", "Receiver Error", "warning",
         "Signal quality issue on PCIe link",
         "Clean contacts. Reseat card. Check for dust.", False),
        (r"corrected\s*internal", "Corrected Internal", "informational",
         "Device self-corrected an internal error",
         "Monitor rate. Update firmware if frequent.", True),
        (r"aer|advanced\s*error", "AER Error (Generic)", "warning",
         "PCIe Advanced Error Reporting event",
         "Check device health. Update firmware and drivers.", True),
    ]

    for pattern, name, sev, cause, action, fw in patterns:
        if re.search(pattern, msg_lower):
            return PCIeDecodeResult(
                error_type=error_type, error_name=name,
                description=f"PCIe {error_type}: {name}",
                likely_cause=cause, action=action,
                slot_info="", device_info=_identify_pcie_device(log_message),
                severity=sev, firmware_related=fw,
            )

    return PCIeDecodeResult(
        error_type=error_type, error_name="Unknown PCIe Error",
        description=f"PCIe {error_type} error detected",
        likely_cause="Unknown — collect TSR for detailed analysis",
        action="Collect TSR. Check PCIe device health. Update all firmware.",
        slot_info="", device_info=_identify_pcie_device(log_message),
        severity="warning",
    )


def scan_logs_for_pcie_errors(logs: List[Dict]) -> List[PCIeDecodeResult]:
    """Scan log entries for PCIe errors and decode them."""
    results = []
    pcie_patterns = [
        r"pci[e\s]", r"aer\b", r"completion\s*timeout", r"poison.*tlp",
        r"link.*down", r"malformed", r"receiver\s*error", r"bus.*error",
    ]
    combined = "|".join(pcie_patterns)

    for log in logs:
        msg = log.get("message", "") or ""
        if not re.search(combined, msg, re.IGNORECASE):
            continue
        is_fatal = any(w in msg.lower() for w in ("fatal", "uncorrectable", "critical"))
        result = decode_pcie_error(log_message=msg, is_fatal=is_fatal)
        result.slot_info = result.slot_info or _extract_slot(msg)
        results.append(result)

    return results


def _extract_slot(msg: str) -> str:
    """Extract PCIe slot info from log message."""
    slot_match = re.search(r"slot\s*[:#]?\s*(\d+)", msg, re.IGNORECASE)
    if slot_match:
        return f"Slot {slot_match.group(1)}"
    bdf_match = re.search(r"(\d+:\d+[:.]\d+)", msg)
    if bdf_match:
        return f"BDF {bdf_match.group(1)}"
    return ""


# ═══════════════════════════════════════════════════════════════
# 3. DELL FIRMWARE CATALOG
#    Known-good firmware versions per PowerEdge model
#    Agent compares installed vs catalog and flags outdated
# ═══════════════════════════════════════════════════════════════

@dataclass
class FirmwareCheckResult:
    """Result of comparing installed firmware against catalog."""
    component: str
    installed_version: str
    latest_version: str
    is_current: bool
    is_critical: bool     # critical update (security, stability)
    update_url: str
    notes: str
    category: str         # bios, idrac, nic, raid, drive, cpld

# Dell firmware catalog — latest known-good versions
# Updated for common PowerEdge 14G/15G/16G models
DELL_FIRMWARE_CATALOG = {
    # ─── BIOS ──────────────────────────────────────────────
    "BIOS": {
        "PowerEdge R740": {"version": "2.19.1", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=RM9Y5", "notes": "Security fixes + stability"},
        "PowerEdge R740xd": {"version": "2.19.1", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=RM9Y5", "notes": "Security fixes + stability"},
        "PowerEdge R640": {"version": "2.19.1", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=V5P1N", "notes": "Security fixes + stability"},
        "PowerEdge R750": {"version": "1.13.0", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=JXTJR", "notes": "Security + PCIe stability"},
        "PowerEdge R750xa": {"version": "1.13.0", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=JXTJR", "notes": "Security + PCIe stability"},
        "PowerEdge R650": {"version": "1.13.0", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=4FN97", "notes": "Security + memory stability"},
        "PowerEdge R660": {"version": "1.7.2", "critical": False, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=YGTR5", "notes": "Latest"},
        "PowerEdge R760": {"version": "1.7.2", "critical": False, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=R97J5", "notes": "Latest"},
        "_default": {"version": "2.19.1", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Check Dell support for your model"},
    },
    # ─── iDRAC ─────────────────────────────────────────────
    "iDRAC": {
        "iDRAC9": {"version": "7.10.50.00", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=X4JNY", "notes": "Security + Redfish improvements"},
        "iDRAC8": {"version": "2.83.83.83", "critical": True, "url": "https://www.dell.com/support/home/drivers/driversdetails?driverid=8NCVW", "notes": "Security fixes"},
        "_default": {"version": "7.10.50.00", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Update to latest"},
    },
    # ─── NIC Firmware ──────────────────────────────────────
    "NIC": {
        "Broadcom 5720": {"version": "22.02.6", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Stability update"},
        "Broadcom 57414": {"version": "22.41.4", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Performance + stability"},
        "Intel X710": {"version": "9.30", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Security + link stability"},
        "Intel E810": {"version": "4.40", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Security + RDMA fixes"},
        "Mellanox ConnectX-5": {"version": "16.35.4", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Performance"},
        "Mellanox ConnectX-6": {"version": "22.39.3", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Latest"},
        "_default": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check Dell support"},
    },
    # ─── RAID Controller (PERC) ────────────────────────────
    "RAID": {
        "PERC H740P": {"version": "52.16.1-4514", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Critical stability fix"},
        "PERC H745": {"version": "52.16.1-4514", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Critical stability fix"},
        "PERC H755": {"version": "52.16.1-4514", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "Critical stability fix"},
        "PERC H755N": {"version": "52.16.1-4514", "critical": True, "url": "https://www.dell.com/support/home/drivers", "notes": "NVMe optimization"},
        "BOSS-S1": {"version": "2.5.13.3024", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Boot device stability"},
        "BOSS-S2": {"version": "2.5.13.3024", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Boot device stability"},
        "_default": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check Dell support"},
    },
    # ─── Drive Firmware ────────────────────────────────────
    "Drive": {
        "HGST": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check Dell support for drive-specific FW"},
        "Seagate": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check for recall notices"},
        "Samsung": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "NVMe firmware updates recommended"},
        "Intel": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check for data loss advisories"},
        "Micron": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "SSD firmware important for reliability"},
        "Toshiba": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check Dell support"},
        "KIOXIA": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "NVMe updates recommended"},
        "_default": {"version": "latest", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "Check Dell support"},
    },
    # ─── CPLD ──────────────────────────────────────────────
    "CPLD": {
        "_default": {"version": "1.1.6", "critical": False, "url": "https://www.dell.com/support/home/drivers", "notes": "CPLD updates rare but important"},
    },
}


def check_firmware_against_catalog(installed_firmware: List[Dict],
                                    server_model: str = "") -> List[FirmwareCheckResult]:
    """Compare installed firmware inventory against the Dell catalog.
    
    Args:
        installed_firmware: List from redfish get_firmware_inventory()
        server_model: e.g. "PowerEdge R740"
    """
    results = []

    for fw in installed_firmware:
        name = fw.get("name", "")
        version = fw.get("version", "")
        component_id = fw.get("component_id", "")
        updateable = fw.get("updateable", False)
        if not name or not version:
            continue

        # Classify the firmware component
        category, catalog_entry = _classify_and_lookup(name, component_id, server_model)
        if not catalog_entry:
            continue

        latest = catalog_entry.get("version", "latest")
        is_current = _compare_versions(version, latest)

        results.append(FirmwareCheckResult(
            component=name,
            installed_version=version,
            latest_version=latest,
            is_current=is_current,
            is_critical=catalog_entry.get("critical", False) and not is_current,
            update_url=catalog_entry.get("url", ""),
            notes=catalog_entry.get("notes", ""),
            category=category,
        ))

    return results


def _classify_and_lookup(name: str, component_id: str, model: str) -> Tuple[str, Optional[Dict]]:
    """Classify a firmware component and find its catalog entry."""
    name_lower = name.lower()
    
    # BIOS
    if "bios" in name_lower or "system bios" in name_lower:
        cat = DELL_FIRMWARE_CATALOG["BIOS"]
        return "bios", cat.get(model, cat["_default"])

    # iDRAC
    if "idrac" in name_lower or "lifecycle" in name_lower:
        cat = DELL_FIRMWARE_CATALOG["iDRAC"]
        if "idrac9" in name_lower or "idrac 9" in name_lower:
            return "idrac", cat.get("iDRAC9", cat["_default"])
        elif "idrac8" in name_lower or "idrac 8" in name_lower:
            return "idrac", cat.get("iDRAC8", cat["_default"])
        return "idrac", cat["_default"]

    # NIC
    if any(kw in name_lower for kw in ("nic", "network", "ethernet", "broadcom", "intel", "mellanox", "connectx")):
        cat = DELL_FIRMWARE_CATALOG["NIC"]
        for key in cat:
            if key != "_default" and key.lower() in name_lower:
                return "nic", cat[key]
        return "nic", cat["_default"]

    # RAID
    if any(kw in name_lower for kw in ("perc", "raid", "boss", "storage controller")):
        cat = DELL_FIRMWARE_CATALOG["RAID"]
        for key in cat:
            if key != "_default" and key.lower() in name_lower:
                return "raid", cat[key]
        return "raid", cat["_default"]

    # Drive
    if any(kw in name_lower for kw in ("disk", "drive", "ssd", "nvme", "hdd")):
        cat = DELL_FIRMWARE_CATALOG["Drive"]
        for key in cat:
            if key != "_default" and key.lower() in name_lower:
                return "drive", cat[key]
        return "drive", cat["_default"]

    # CPLD
    if "cpld" in name_lower:
        return "cpld", DELL_FIRMWARE_CATALOG["CPLD"]["_default"]

    return "other", None


def _compare_versions(installed: str, latest: str) -> bool:
    """Compare version strings. Returns True if installed >= latest."""
    if latest == "latest":
        return True  # Can't compare without specific version
    try:
        inst_parts = [int(x) for x in re.findall(r'\d+', installed)]
        lat_parts = [int(x) for x in re.findall(r'\d+', latest)]
        # Pad shorter list
        max_len = max(len(inst_parts), len(lat_parts))
        inst_parts.extend([0] * (max_len - len(inst_parts)))
        lat_parts.extend([0] * (max_len - len(lat_parts)))
        return inst_parts >= lat_parts
    except (ValueError, TypeError):
        return installed == latest


def get_firmware_summary(results: List[FirmwareCheckResult]) -> Dict[str, Any]:
    """Generate a summary of firmware check results."""
    total = len(results)
    current = sum(1 for r in results if r.is_current)
    outdated = [r for r in results if not r.is_current]
    critical = [r for r in outdated if r.is_critical]

    return {
        "total_components": total,
        "up_to_date": current,
        "outdated": len(outdated),
        "critical_updates": len(critical),
        "health_score": round((current / total * 100) if total else 100, 1),
        "outdated_list": [
            {
                "component": r.component,
                "installed": r.installed_version,
                "latest": r.latest_version,
                "critical": r.is_critical,
                "category": r.category,
                "url": r.update_url,
                "notes": r.notes,
            }
            for r in outdated
        ],
        "critical_list": [
            {
                "component": r.component,
                "installed": r.installed_version,
                "latest": r.latest_version,
                "category": r.category,
                "url": r.update_url,
                "notes": r.notes,
            }
            for r in critical
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 4. REDFISH SIMPLE UPDATE — Firmware push to iDRAC
# ═══════════════════════════════════════════════════════════════

async def push_firmware_update(redfish_client, firmware_url: str,
                                component: str = "") -> Dict[str, Any]:
    """Push a firmware update to iDRAC via Redfish SimpleUpdate.
    
    The iDRAC will download the firmware from the URL and apply it.
    Supports HTTP/HTTPS/CIFS/NFS URLs.
    
    Args:
        redfish_client: RedfishClient instance
        firmware_url: URL to the firmware .EXE or .d9 package
        component: Component name for logging
    """
    try:
        payload = {
            "ImageURI": firmware_url,
            "@Redfish.OperationApplyTime": "Immediate",
        }
        
        result = await redfish_client._post(
            "UpdateService/Actions/UpdateService.SimpleUpdate",
            payload
        )
        
        if result:
            job_id = result.get("Id", "") or ""
            # Try to extract job ID from response headers or body
            if not job_id and isinstance(result, dict):
                location = result.get("@odata.id", "")
                if "JID_" in location:
                    job_id = location.split("/")[-1]
            
            return {
                "success": True,
                "job_id": job_id,
                "message": f"Firmware update initiated for {component}. Job: {job_id}",
                "firmware_url": firmware_url,
                "status": "scheduled",
            }
        else:
            return {
                "success": False,
                "message": f"SimpleUpdate request failed for {component}. Check iDRAC logs.",
                "firmware_url": firmware_url,
                "status": "failed",
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error pushing firmware update: {str(e)}",
            "firmware_url": firmware_url,
            "status": "error",
        }


async def check_update_job_status(redfish_client, job_id: str) -> Dict[str, Any]:
    """Check the status of a firmware update job."""
    try:
        job_data = await redfish_client._get(f"Managers/iDRAC.Embedded.1/Oem/Dell/Jobs/{job_id}")
        if not job_data:
            job_data = await redfish_client._get(f"TaskService/Tasks/{job_id}")
        
        if job_data:
            return {
                "job_id": job_id,
                "status": job_data.get("JobState", job_data.get("TaskState", "Unknown")),
                "percent_complete": job_data.get("PercentComplete", 0),
                "message": job_data.get("Message", ""),
            }
        return {"job_id": job_id, "status": "Unknown", "message": "Could not retrieve job status"}
    except Exception as e:
        return {"job_id": job_id, "status": "Error", "message": str(e)}
