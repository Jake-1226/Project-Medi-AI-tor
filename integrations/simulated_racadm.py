"""
Simulated RACADM client for demo/development without a real Dell server.
Returns realistic RACADM-style data that mirrors a Dell PowerEdge R760.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta, timezone

from models.server_models import (
    ServerInfo, SystemInfo, ProcessorInfo, MemoryInfo, PowerSupplyInfo,
    TemperatureInfo, FanInfo, StorageInfo, NetworkInterfaceInfo,
    LogEntry, ServerStatus, ComponentType, Severity
)

logger = logging.getLogger(__name__)

_SERVICE_TAG = "DEMOABC"
_MODEL = "PowerEdge R760"
_BIOS_VERSION = "1.8.2"
_IDRAC_VERSION = "7.10.50.00"


class SimulatedRacadmClient:
    """Drop-in replacement for RacadmClient that returns realistic mock data."""

    def __init__(self, host: str = "demo", username: str = "root",
                 password: str = "calvin", timeout: int = 60):
        self.host = host
        self.username = username
        self.password = password
        self.timeout = timeout
        self._connected = False

    async def execute_command(self, command: str, args: List[str] = None) -> Tuple[bool, str]:
        logger.info(f"[DEMO] Simulated RACADM: racadm -r {self.host} {command} {args or ''}")
        return True, "[DEMO] Command simulated successfully."

    async def test_connection(self) -> bool:
        logger.info(f"[DEMO] Simulated RACADM connection test to {self.host}")
        self._connected = True
        return True

    async def get_server_info(self) -> Optional[ServerInfo]:
        return ServerInfo(
            host=self.host,
            model=_MODEL,
            service_tag=_SERVICE_TAG,
            firmware_version=_BIOS_VERSION,
            idrac_version=_IDRAC_VERSION,
            status=ServerStatus.ONLINE,
        )

    async def get_system_info(self) -> Optional[SystemInfo]:
        return SystemInfo(
            manufacturer="Dell Inc.",
            model=_MODEL,
            serial_number=_SERVICE_TAG,
            part_number="0DEMO12345",
            bios_version=_BIOS_VERSION,
            system_type="Physical",
            asset_tag="DEMO-ASSET",
            power_state="On",
            boot_order=["NIC.PxeDevice.1-1", "HardDisk.List.1-1"],
        )

    async def get_power_consumption(self) -> Optional[Dict[str, Any]]:
        return {
            "current_wattage": 320,
            "peak_wattage": 480,
            "min_wattage": 280,
            "average_wattage": 350,
        }

    async def get_temperature_sensors(self) -> Optional[Dict[str, Any]]:
        return {
            "sensors": [
                {"name": "System Board Inlet Temp", "reading": "23 C", "status": "OK"},
                {"name": "System Board Exhaust Temp", "reading": "38 C", "status": "OK"},
                {"name": "CPU1 Temperature", "reading": "55 C", "status": "OK"},
                {"name": "CPU2 Temperature", "reading": "53 C", "status": "OK"},
            ]
        }

    async def get_fan_info(self) -> Optional[Dict[str, Any]]:
        fans = []
        for i in range(1, 17):
            fans.append({"name": f"System Board Fan{i}", "reading": "7200 RPM", "status": "OK"})
        return {"fans": fans}

    async def get_storage_info(self) -> Optional[Dict[str, Any]]:
        return {
            "controllers": [
                {"name": "PERC H755 Front", "status": "OK", "firmware": "52.28.0-4682"}
            ],
            "disks": [
                {"name": "Physical Disk 0:0", "size": "1200 GB", "type": "HDD", "status": "OK"},
                {"name": "Physical Disk 0:1", "size": "1200 GB", "type": "HDD", "status": "OK"},
                {"name": "Physical Disk 0:4", "size": "960 GB", "type": "SSD", "status": "OK"},
                {"name": "Physical Disk 0:5", "size": "960 GB", "type": "SSD", "status": "OK"},
            ],
        }

    async def get_network_info(self) -> Optional[Dict[str, Any]]:
        return {
            "interfaces": [
                {"name": "NIC.Integrated.1-1", "mac": "F4:02:70:AA:BB:01", "link": "Up", "speed": "1 Gbps"},
                {"name": "NIC.Integrated.1-2", "mac": "F4:02:70:AA:BB:02", "link": "Up", "speed": "1 Gbps"},
                {"name": "NIC.Slot.3-1", "mac": "0C:42:A1:CC:DD:01", "link": "Up", "speed": "25 Gbps"},
            ]
        }

    async def get_system_logs(self) -> List[LogEntry]:
        base = datetime.now(timezone.utc)
        return [
            LogEntry(timestamp=base - timedelta(minutes=5), severity=Severity.INFO,
                     message="Successfully logged in using root.", source="USR0030",
                     component=ComponentType.SYSTEM, event_id="1"),
            LogEntry(timestamp=base - timedelta(hours=2), severity=Severity.WARNING,
                     message="System Board Inlet Temp above upper warning threshold.",
                     source="TMP0118", component=ComponentType.THERMAL, event_id="2"),
        ]

    async def get_lc_logs(self) -> List[LogEntry]:
        base = datetime.now(timezone.utc)
        return [
            LogEntry(timestamp=base - timedelta(days=1), severity=Severity.INFO,
                     message="Lifecycle Controller data backup was successful.",
                     source="LCL201", component=ComponentType.SYSTEM, event_id="3"),
        ]

    async def power_action(self, action: str) -> bool:
        logger.info(f"[DEMO] Simulated RACADM power action: {action}")
        return True

    async def set_boot_order(self, boot_devices: List[str]) -> bool:
        logger.info(f"[DEMO] Simulated RACADM boot order: {boot_devices}")
        return True

    async def get_idrac_settings(self) -> Optional[Dict[str, Any]]:
        return {
            "iDRAC.Info.Name": "iDRAC",
            "iDRAC.Info.Version": _IDRAC_VERSION,
            "iDRAC.NIC.DNSRacName": "idrac-DEMOABC",
        }

    async def create_support_assist_collection(self) -> Optional[str]:
        return "JID_DEMO_SA"

    async def export_system_configuration(self, filename: Optional[str] = None) -> Optional[str]:
        return filename or "/tmp/demo_scp_export.xml"

    async def import_system_configuration(self, filename: str) -> bool:
        return True

    async def update_firmware(self, component: str, firmware_file: str) -> bool:
        logger.info(f"[DEMO] Simulated firmware update: {component} -> {firmware_file}")
        return True

    # ── Structured methods (used by agent_core) ──────────────────
    async def get_processors_structured(self) -> List[ProcessorInfo]:
        return [
            ProcessorInfo(id="CPU.Socket.1", manufacturer="Intel Corporation",
                          model="Intel Xeon Gold 6430", cores=32, threads=64,
                          speed_mhz=2100, status="OK (Enabled)", socket="CPU 1"),
            ProcessorInfo(id="CPU.Socket.2", manufacturer="Intel Corporation",
                          model="Intel Xeon Gold 6430", cores=32, threads=64,
                          speed_mhz=2100, status="OK (Enabled)", socket="CPU 2"),
        ]

    async def get_memory_structured(self) -> List[MemoryInfo]:
        dimms = []
        for slot in ["A1", "A2", "B1", "B2", "C1", "C2", "D1", "D2"]:
            dimms.append(MemoryInfo(
                id=f"DIMM.Socket.{slot}", manufacturer="Samsung",
                part_number="M393A4K40EB3-CWE", size_gb=32, speed_mhz=4800,
                type="DDR5", status="OK (Enabled)", location=f"DIMM {slot}",
            ))
        return dimms

    async def get_storage_structured(self) -> List[StorageInfo]:
        return [
            StorageInfo(id="Disk.Bay.0", name="Physical Disk 0:0", manufacturer="TOSHIBA",
                        model="AL15SEB120NY", capacity_gb=1200, type="HDD",
                        interface="SAS", status="OK (Enabled)", firmware_version="DE0D",
                        serial_number="Y1G0A01FFVG"),
            StorageInfo(id="Disk.Bay.4", name="Physical Disk 0:4", manufacturer="Samsung",
                        model="MZ7L3960HCJR-00A07", capacity_gb=960, type="SSD",
                        interface="SATA", status="OK (Enabled)", firmware_version="GXA5602Q",
                        serial_number="Y5G0A05FFVG"),
        ]

    async def get_network_structured(self) -> List[NetworkInterfaceInfo]:
        return [
            NetworkInterfaceInfo(
                id="NIC.Integrated.1-1", name="Broadcom BCM5720 Port 1",
                mac_address="F4:02:70:AA:BB:01", speed_mbps=1000,
                status="OK (Enabled)", link_status="LinkUp", auto_negotiation=True,
                ipv4_addresses=["10.0.1.50"], ipv6_addresses=[],
            ),
        ]

    async def get_temperatures_structured(self) -> List[TemperatureInfo]:
        return [
            TemperatureInfo(id="InletTemp", name="System Board Inlet Temp",
                           reading_celsius=23.0, status="OK (Enabled)",
                           location="Inlet", upper_threshold_critical=47,
                           upper_threshold_non_critical=42),
            TemperatureInfo(id="CPU1Temp", name="CPU1 Temperature",
                           reading_celsius=55.0, status="OK (Enabled)",
                           location="CPU 1", upper_threshold_critical=100,
                           upper_threshold_non_critical=93),
        ]

    async def get_fans_structured(self) -> List[FanInfo]:
        fans = []
        for i in range(1, 9):
            fans.append(FanInfo(
                id=f"Fan.Embedded.{i}", name=f"System Board Fan{i}",
                speed_rpm=7200, status="OK (Enabled)",
                location=f"Fan{i}", min_speed_rpm=None, max_speed_rpm=None,
            ))
        return fans

    async def get_power_supplies_structured(self) -> List[PowerSupplyInfo]:
        return [
            PowerSupplyInfo(
                id="PSU.Slot.1", manufacturer="Dell", model="PWR SPLY,1400W,RDNT",
                power_watts=1400, input_voltage=208, output_voltage=12,
                efficiency=94, status="OK (Enabled)", firmware_version="00.24.4C",
            ),
            PowerSupplyInfo(
                id="PSU.Slot.2", manufacturer="Dell", model="PWR SPLY,1400W,RDNT",
                power_watts=1400, input_voltage=208, output_voltage=12,
                efficiency=94, status="OK (Enabled)", firmware_version="00.24.4C",
            ),
        ]

    async def get_firmware_inventory(self) -> List[Dict[str, Any]]:
        return [
            {"id": "BIOS", "name": "BIOS", "version": _BIOS_VERSION, "updateable": True},
            {"id": "iDRAC", "name": "iDRAC9", "version": _IDRAC_VERSION, "updateable": True},
            {"id": "PERC", "name": "PERC H755", "version": "52.28.0-4682", "updateable": True},
        ]

    async def get_bios_attributes(self) -> Dict[str, Any]:
        return {
            "attributes": {
                "BootMode": "Uefi",
                "ProcCStates": "Disabled",
                "ProcTurboMode": "Enabled",
                "ProcVirtualization": "Enabled",
                "SysProfile": "PerfOptimized",
            },
            "bios_version": _BIOS_VERSION,
        }

    async def get_idrac_info(self) -> Dict[str, Any]:
        return {
            "firmware_version": _IDRAC_VERSION,
            "model": "iDRAC9",
            "status": "OK",
        }

    async def get_virtual_console_info(self) -> Optional[Dict[str, Any]]:
        return {"virtual_console_enabled": True, "plugin_type": "HTML5"}
