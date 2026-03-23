"""
Simulated Redfish API client for demo/development without a real Dell server.
Returns realistic Dell PowerEdge R760 mock data for all Redfish endpoints.
"""

import logging
import random
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone

from models.server_models import (
    ServerInfo, SystemInfo, ProcessorInfo, MemoryInfo, PowerSupplyInfo,
    TemperatureInfo, FanInfo, StorageInfo, NetworkInterfaceInfo,
    LogEntry, HealthStatus, PerformanceMetrics, ServerStatus, ComponentType, Severity
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simulated data constants
# ---------------------------------------------------------------------------

_SERVICE_TAG = "DEMOABC"
_MODEL = "PowerEdge R760"
_BIOS_VERSION = "1.8.2"
_IDRAC_VERSION = "7.10.50.00"
_HOSTNAME = "demo-r760.lab.local"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_temp(base: float, jitter: float = 3.0) -> float:
    return round(base + random.uniform(-jitter, jitter), 1)


def _random_rpm(base: int, jitter: int = 500) -> int:
    return base + random.randint(-jitter, jitter)


class SimulatedRedfishClient:
    """Drop-in replacement for RedfishClient that returns realistic mock data."""

    def __init__(self, host: str = "demo", username: str = "root",
                 password: str = "calvin", port: int = 443,
                 verify_ssl: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{host}:{port}"
        self.session = True          # always "connected"
        self.auth_token = "SIM-TOKEN"
        self.system_id = "System.Embedded.1"
        self.chassis_id = "System.Embedded.1"
        self._sensor_cache = None
        self._connected = False

    # ── connection lifecycle ──────────────────────────────────────
    async def connect(self) -> bool:
        logger.info(f"[DEMO] Simulated Redfish connection to {self.host}")
        self._connected = True
        return True

    async def disconnect(self):
        logger.info("[DEMO] Simulated Redfish disconnect")
        self._connected = False
        self.session = None

    def _clear_sensor_cache(self):
        self._sensor_cache = None

    # ── helper used by agent_core (status mapping) ───────────────
    def _map_status(self, status_data: Dict) -> ServerStatus:
        health = status_data.get("Health", "Unknown")
        state = status_data.get("State", "Unknown")
        if health == "OK" and state == "Enabled":
            return ServerStatus.ONLINE
        elif health == "Warning":
            return ServerStatus.WARNING
        elif health in ("Critical", "Failed"):
            return ServerStatus.CRITICAL
        elif state == "Disabled":
            return ServerStatus.OFFLINE
        return ServerStatus.UNKNOWN

    def _get_status_string(self, status_data: Dict) -> str:
        return f"{status_data.get('Health', 'OK')} ({status_data.get('State', 'Enabled')})"

    # ── raw HTTP stubs (used by agent_core._execute_read_only_command) ──
    async def _get(self, endpoint: str, params=None, use_cache=True) -> Optional[Dict]:
        """Return simulated Redfish JSON for common endpoints."""
        ep = endpoint.lower()

        # Systems root
        if ep == f"systems/{self.system_id.lower()}" or ep == f"systems/{self.system_id}":
            return self._system_data()

        # Managers
        if "managers" in ep and "logservices" not in ep and "oem" not in ep and "jobs" not in ep:
            if ep.endswith("managers"):
                return {"Members": [{"@odata.id": "/redfish/v1/Managers/iDRAC.Embedded.1"}]}
            return self._manager_data()

        # Chassis sensors
        if "sensors" in ep:
            return {"Members": []}  # force legacy path

        # Power subsystem (16G+) -- force legacy for simplicity
        if "powersubsystem" in ep:
            return None

        # Thermal subsystem
        if "thermalsubsystem" in ep:
            return None

        return None  # default

    async def _post(self, endpoint: str, data: Dict) -> Optional[Dict]:
        ep = endpoint.lower()
        if "reset" in ep:
            return {"success": True, "status": 200}
        if "supportassist" in ep or "techsupportreport" in ep:
            return {
                "success": True, "status": 202,
                "_job_id": "JID_DEMO001",
                "_location": "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/Jobs/JID_DEMO001",
            }
        if "diagnostics" in ep:
            return {"success": True, "Id": "JID_DEMO_DIAG"}
        if "clearlog" in ep:
            return {"success": True}
        return {"success": True, "status": 200}

    async def _patch(self, endpoint: str, data: Dict) -> bool:
        return True

    # ── high-level data methods ──────────────────────────────────

    async def get_server_info(self) -> ServerInfo:
        return ServerInfo(
            host=self.host,
            model=_MODEL,
            service_tag=_SERVICE_TAG,
            firmware_version=_BIOS_VERSION,
            idrac_version=_IDRAC_VERSION,
            status=ServerStatus.ONLINE,
        )

    async def get_system_info(self) -> SystemInfo:
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

    async def get_processors(self) -> List[ProcessorInfo]:
        return [
            ProcessorInfo(id="CPU.Socket.1", manufacturer="Intel Corporation",
                          model="Intel Xeon Gold 6430 (Sapphire Rapids)", cores=32,
                          threads=64, speed_mhz=2100, status="OK (Enabled)", socket="CPU 1"),
            ProcessorInfo(id="CPU.Socket.2", manufacturer="Intel Corporation",
                          model="Intel Xeon Gold 6430 (Sapphire Rapids)", cores=32,
                          threads=64, speed_mhz=2100, status="OK (Enabled)", socket="CPU 2"),
        ]

    async def get_memory(self) -> List[MemoryInfo]:
        dimms = []
        slots = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4",
                 "C1", "C2", "C3", "C4", "D1", "D2", "D3", "D4"]
        for slot in slots:
            dimms.append(MemoryInfo(
                id=f"DIMM.Socket.{slot}",
                manufacturer="Samsung",
                part_number="M393A4K40EB3-CWE",
                size_gb=32,
                speed_mhz=4800,
                type="DDR5",
                status="OK (Enabled)",
                location=f"DIMM {slot}",
            ))
        return dimms

    async def get_power_supplies(self) -> List[PowerSupplyInfo]:
        return [
            PowerSupplyInfo(
                id="PSU.Slot.1", manufacturer="Dell", model="PWR SPLY,1400W,RDNT,LTON",
                power_watts=1400, input_voltage=208, output_voltage=12,
                efficiency=94, status="OK (Enabled)", firmware_version="00.24.4C",
            ),
            PowerSupplyInfo(
                id="PSU.Slot.2", manufacturer="Dell", model="PWR SPLY,1400W,RDNT,LTON",
                power_watts=1400, input_voltage=208, output_voltage=12,
                efficiency=94, status="OK (Enabled)", firmware_version="00.24.4C",
            ),
        ]

    async def get_temperature_sensors(self) -> List[TemperatureInfo]:
        return [
            TemperatureInfo(id="iDRAC.Embedded.1#SystemBoardInletTemp",
                           name="System Board Inlet Temp",
                           reading_celsius=_random_temp(23), status="OK (Enabled)",
                           location="Inlet", upper_threshold_critical=47,
                           upper_threshold_non_critical=42),
            TemperatureInfo(id="iDRAC.Embedded.1#SystemBoardExhaustTemp",
                           name="System Board Exhaust Temp",
                           reading_celsius=_random_temp(38), status="OK (Enabled)",
                           location="Exhaust", upper_threshold_critical=75,
                           upper_threshold_non_critical=70),
            TemperatureInfo(id="iDRAC.Embedded.1#CPU1Temp",
                           name="CPU1 Temperature",
                           reading_celsius=_random_temp(55, 5), status="OK (Enabled)",
                           location="CPU 1", upper_threshold_critical=100,
                           upper_threshold_non_critical=93),
            TemperatureInfo(id="iDRAC.Embedded.1#CPU2Temp",
                           name="CPU2 Temperature",
                           reading_celsius=_random_temp(53, 5), status="OK (Enabled)",
                           location="CPU 2", upper_threshold_critical=100,
                           upper_threshold_non_critical=93),
            TemperatureInfo(id="iDRAC.Embedded.1#DIMM.A1Temp",
                           name="DIMM A1 Temperature",
                           reading_celsius=_random_temp(35, 2), status="OK (Enabled)",
                           location="DIMM A1", upper_threshold_critical=85,
                           upper_threshold_non_critical=80),
            TemperatureInfo(id="iDRAC.Embedded.1#DIMM.B1Temp",
                           name="DIMM B1 Temperature",
                           reading_celsius=_random_temp(34, 2), status="OK (Enabled)",
                           location="DIMM B1", upper_threshold_critical=85,
                           upper_threshold_non_critical=80),
            TemperatureInfo(id="iDRAC.Embedded.1#VRTemp",
                           name="System Board VR Temp",
                           reading_celsius=_random_temp(42, 3), status="OK (Enabled)",
                           location="VR", upper_threshold_critical=100,
                           upper_threshold_non_critical=95),
        ]

    async def get_fans(self) -> List[FanInfo]:
        fans = []
        for i in range(1, 17):
            fans.append(FanInfo(
                id=f"Fan.Embedded.{i}",
                name=f"System Board Fan{i}",
                speed_rpm=_random_rpm(7200),
                status="OK (Enabled)",
                location=f"System Board Fan{i}",
                min_speed_rpm=None,
                max_speed_rpm=None,
            ))
        return fans

    async def get_storage_devices(self) -> List[StorageInfo]:
        drives = []
        for i in range(1, 9):
            drives.append(StorageInfo(
                id=f"Disk.Bay.{i-1}:Enclosure.Internal.0-1:RAID.SL.3-1",
                name=f"Physical Disk 0:{i-1}",
                manufacturer="TOSHIBA" if i <= 4 else "Samsung",
                model="AL15SEB120NY" if i <= 4 else "MZ7L3960HCJR-00A07",
                capacity_gb=1200 if i <= 4 else 960,
                type="HDD" if i <= 4 else "SSD",
                interface="SAS" if i <= 4 else "SATA",
                status="OK (Enabled)",
                firmware_version="DE0D" if i <= 4 else "GXA5602Q",
                serial_number=f"Y{i}G0A0{i}FFVG",
            ))
        return drives

    async def get_network_interfaces(self) -> List[NetworkInterfaceInfo]:
        return [
            NetworkInterfaceInfo(
                id="NIC.Integrated.1-1", name="Broadcom Gigabit Ethernet BCM5720 - Port 1",
                mac_address="F4:02:70:AA:BB:01", speed_mbps=1000,
                status="OK (Enabled)", link_status="LinkUp", auto_negotiation=True,
                ipv4_addresses=["10.0.1.50"], ipv6_addresses=[],
            ),
            NetworkInterfaceInfo(
                id="NIC.Integrated.1-2", name="Broadcom Gigabit Ethernet BCM5720 - Port 2",
                mac_address="F4:02:70:AA:BB:02", speed_mbps=1000,
                status="OK (Enabled)", link_status="LinkUp", auto_negotiation=True,
                ipv4_addresses=["10.0.1.51"], ipv6_addresses=[],
            ),
            NetworkInterfaceInfo(
                id="NIC.Slot.3-1", name="Mellanox ConnectX-6 Dx 25GbE SFP28 - Port 1",
                mac_address="0C:42:A1:CC:DD:01", speed_mbps=25000,
                status="OK (Enabled)", link_status="LinkUp", auto_negotiation=True,
                ipv4_addresses=["10.10.0.50"], ipv6_addresses=[],
            ),
            NetworkInterfaceInfo(
                id="NIC.Slot.3-2", name="Mellanox ConnectX-6 Dx 25GbE SFP28 - Port 2",
                mac_address="0C:42:A1:CC:DD:02", speed_mbps=25000,
                status="OK (Enabled)", link_status="LinkDown", auto_negotiation=True,
                ipv4_addresses=[], ipv6_addresses=[],
            ),
        ]

    async def get_logs(self, log_type: str = "System") -> List[LogEntry]:
        base_time = datetime.now(timezone.utc)
        logs = [
            LogEntry(
                timestamp=base_time - timedelta(minutes=5),
                severity=Severity.INFO,
                message="Successfully logged in using root, from 10.0.1.100.",
                source="USR0030", component=ComponentType.SYSTEM, event_id="1",
            ),
            LogEntry(
                timestamp=base_time - timedelta(hours=1),
                severity=Severity.INFO,
                message="The system was powered on.",
                source="SYS1003", component=ComponentType.POWER, event_id="2",
            ),
            LogEntry(
                timestamp=base_time - timedelta(hours=2),
                severity=Severity.WARNING,
                message="The system board inlet temperature is greater than the upper warning threshold.",
                source="TMP0118", component=ComponentType.THERMAL, event_id="3",
            ),
            LogEntry(
                timestamp=base_time - timedelta(hours=4),
                severity=Severity.INFO,
                message="The drive 0 in connector 0 of the integrated storage controller detected a SMART alert.",
                source="STR0038", component=ComponentType.STORAGE, event_id="4",
            ),
            LogEntry(
                timestamp=base_time - timedelta(days=1),
                severity=Severity.INFO,
                message="Lifecycle Controller data backup was successful.",
                source="LCL201", component=ComponentType.SYSTEM, event_id="5",
            ),
            LogEntry(
                timestamp=base_time - timedelta(days=2),
                severity=Severity.WARNING,
                message="Correctable memory error rate exceeded for DIMM A1.",
                source="MEM0701", component=ComponentType.MEMORY, event_id="6",
            ),
            LogEntry(
                timestamp=base_time - timedelta(days=3),
                severity=Severity.INFO,
                message="Firmware update completed successfully for BIOS.",
                source="RED0406", component=ComponentType.FIRMWARE, event_id="7",
            ),
            LogEntry(
                timestamp=base_time - timedelta(days=5),
                severity=Severity.CRITICAL,
                message="Machine Check Exception - CPU 0 Bank 5 MISC 0x0000000000000000 ADDR 0x0000FFFF12340000",
                source="CPU0005", component=ComponentType.PROCESSOR, event_id="8",
            ),
        ]
        return logs

    async def get_health_status(self) -> HealthStatus:
        logs = await self.get_logs()
        return HealthStatus(
            overall_status=ServerStatus.ONLINE,
            components={
                ComponentType.POWER: ServerStatus.ONLINE,
                ComponentType.THERMAL: ServerStatus.ONLINE,
                ComponentType.MEMORY: ServerStatus.ONLINE,
                ComponentType.STORAGE: ServerStatus.ONLINE,
                ComponentType.NETWORK: ServerStatus.ONLINE,
                ComponentType.PROCESSOR: ServerStatus.ONLINE,
            },
            critical_issues=[l for l in logs if l.severity == Severity.CRITICAL],
            warnings=[l for l in logs if l.severity == Severity.WARNING],
        )

    async def power_action(self, action: str) -> bool:
        logger.info(f"[DEMO] Simulated power action: {action}")
        return True

    async def set_boot_order(self, boot_devices: List[str]) -> bool:
        logger.info(f"[DEMO] Simulated set boot order: {boot_devices}")
        return True

    # ── BIOS ─────────────────────────────────────────────────────
    async def get_bios_attributes(self) -> Dict[str, Any]:
        return {
            "attributes": {
                "SystemModelName": _MODEL,
                "BootMode": "Uefi",
                "SecureBoot": "Enabled",
                "TpmSecurity": "On",
                "ProcCStates": "Disabled",
                "ProcTurboMode": "Enabled",
                "ProcHwPrefetcher": "Enabled",
                "ProcVirtualization": "Enabled",
                "MemOpMode": "OptimizerMode",
                "MemFrequency": "MaxPerf",
                "SysProfile": "PerfOptimized",
                "EmbSata": "AhciMode",
                "SerialComm": "OnConRedirCom2",
                "InternalUsb": "On",
                "SriovGlobalEnable": "Enabled",
                "OsWatchdogTimer": "Disabled",
                "PowerCycleRequest": "None",
            },
            "bios_version": _BIOS_VERSION,
            "attribute_registry": "BiosAttributeRegistry.v1_0_0",
            "description": "BIOS Configuration Current Settings",
        }

    async def set_bios_attributes(self, attributes: Dict[str, Any]) -> bool:
        logger.info(f"[DEMO] Simulated BIOS attribute change: {attributes}")
        return True

    # ── Firmware ─────────────────────────────────────────────────
    async def get_firmware_inventory(self) -> List[Dict[str, Any]]:
        return [
            {"id": "Current-BIOS", "name": "BIOS", "version": _BIOS_VERSION,
             "updateable": True, "status": "OK (Enabled)", "release_date": "2025-11-15T00:00:00Z",
             "manufacturer": "Dell Inc.", "description": "BIOS", "component_id": "159-BIOS"},
            {"id": "Current-iDRAC", "name": "Integrated Dell Remote Access Controller",
             "version": _IDRAC_VERSION, "updateable": True, "status": "OK (Enabled)",
             "release_date": "2025-12-01T00:00:00Z", "manufacturer": "Dell Inc.",
             "description": "iDRAC9", "component_id": "25227-iDRAC"},
            {"id": "Current-NIC-BCM5720", "name": "Broadcom Gigabit Ethernet BCM5720",
             "version": "22.00.6", "updateable": True, "status": "OK (Enabled)",
             "release_date": "2025-10-20T00:00:00Z", "manufacturer": "Broadcom",
             "description": "NIC firmware", "component_id": "20137-BCM5720"},
            {"id": "Current-RAID-PERC", "name": "PERC H755 Front",
             "version": "52.28.0-4682", "updateable": True, "status": "OK (Enabled)",
             "release_date": "2025-09-15T00:00:00Z", "manufacturer": "Dell Inc.",
             "description": "RAID controller firmware", "component_id": "1028-PERC"},
            {"id": "Current-CPLD", "name": "System CPLD",
             "version": "1.0.7", "updateable": True, "status": "OK (Enabled)",
             "release_date": "2025-08-01T00:00:00Z", "manufacturer": "Dell Inc.",
             "description": "CPLD firmware", "component_id": "CPLD-001"},
            {"id": "Current-PSU1", "name": "Power Supply 1",
             "version": "00.24.4C", "updateable": True, "status": "OK (Enabled)",
             "release_date": "2025-06-01T00:00:00Z", "manufacturer": "Dell Inc.",
             "description": "PSU firmware", "component_id": "PSU-001"},
            {"id": "Current-Mellanox", "name": "Mellanox ConnectX-6 Dx 25GbE",
             "version": "22.39.1002", "updateable": True, "status": "OK (Enabled)",
             "release_date": "2025-11-01T00:00:00Z", "manufacturer": "NVIDIA/Mellanox",
             "description": "NIC firmware", "component_id": "MLX-CX6Dx"},
        ]

    # ── Lifecycle ────────────────────────────────────────────────
    async def get_lifecycle_logs(self, max_entries: int = 500) -> List[Dict[str, Any]]:
        base = datetime.now(timezone.utc)
        return [
            {"id": "1", "created": (base - timedelta(minutes=10)).isoformat(), "severity": "OK",
             "message": "Successfully logged in using root from 10.0.1.100.",
             "message_id": "USR0030", "entry_type": "Event", "category": "System Event Log"},
            {"id": "2", "created": (base - timedelta(hours=1)).isoformat(), "severity": "OK",
             "message": "Job for BIOS.Setup.1-1 completed successfully.",
             "message_id": "RED0402", "entry_type": "Event", "category": "Lifecycle Log"},
            {"id": "3", "created": (base - timedelta(hours=3)).isoformat(), "severity": "Warning",
             "message": "System Board Inlet Temp sensor crossed upper warning threshold.",
             "message_id": "TMP0118", "entry_type": "Event", "category": "System Event Log"},
            {"id": "4", "created": (base - timedelta(days=1)).isoformat(), "severity": "OK",
             "message": "Firmware update completed successfully for BIOS.",
             "message_id": "RED0406", "entry_type": "Event", "category": "Lifecycle Log"},
            {"id": "5", "created": (base - timedelta(days=2)).isoformat(), "severity": "Critical",
             "message": "Machine Check Exception - CPU 0 Bank 5",
             "message_id": "CPU0005", "entry_type": "Event", "category": "System Event Log"},
        ]

    # ── TSR ──────────────────────────────────────────────────────
    async def export_tsr(self, share_type: str = "Local") -> Dict[str, Any]:
        return {
            "success": True, "job_id": "JID_DEMO001",
            "job_uri": "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/Jobs/JID_DEMO001",
            "method": "SupportAssistCollection",
            "message": "SupportAssist TSR collection initiated (Job: JID_DEMO001)",
        }

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        return {
            "success": True, "job_id": job_id, "name": "SA Export Local",
            "state": "Completed", "percent_complete": 100,
            "message": "Job completed successfully.",
            "start_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "end_time": _now_iso(), "completed": True, "failed": False,
        }

    # ── iDRAC ────────────────────────────────────────────────────
    async def reset_idrac(self) -> bool:
        logger.info("[DEMO] Simulated iDRAC reset")
        return True

    async def get_jobs(self) -> List[Dict[str, Any]]:
        return [
            {"id": "JID_DEMO001", "name": "BIOS Configuration",
             "job_type": "BIOSConfiguration", "job_state": "Completed",
             "message": "Job completed successfully.", "percent_complete": 100,
             "start_time": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
             "end_time": (datetime.now(timezone.utc) - timedelta(hours=5, minutes=55)).isoformat()},
            {"id": "JID_DEMO002", "name": "Firmware Update",
             "job_type": "FirmwareUpdate", "job_state": "Completed",
             "message": "Job completed successfully.", "percent_complete": 100,
             "start_time": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
             "end_time": (datetime.now(timezone.utc) - timedelta(days=2) + timedelta(minutes=10)).isoformat()},
        ]

    async def get_post_codes(self) -> Dict[str, Any]:
        return {
            "last_state": "SystemHardwareInitializationComplete",
            "oem_last_state": "OEM Specific POST Code",
            "post_code": "0x0000",
            "system_generation": "16G Monolithic",
            "power_state": "On",
            "boot_source_override": "None",
            "boot_source_override_enabled": "Disabled",
        }

    async def run_remote_diagnostics(self, diag_type: str = "Express") -> Dict[str, Any]:
        return {"success": True, "message": f"ePSA {diag_type} diagnostics initiated", "job_id": "JID_DEMO_DIAG"}

    async def virtual_ac_cycle(self) -> Dict[str, Any]:
        return {"success": True, "message": "Virtual AC power cycle initiated — server will drain flea power and restart"}

    async def get_support_assist_status(self) -> Dict[str, Any]:
        return {
            "registered": True, "available": True,
            "auto_collection": "Enabled",
            "last_collection": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            "proxy_support": "Off",
        }

    async def check_idrac_availability(self) -> Dict[str, Any]:
        return {
            "reachable": True, "redfish_available": True,
            "system_power_state": "On",
            "idrac_firmware": _IDRAC_VERSION,
            "redfish_version": "1.17.0",
            "model": _MODEL,
            "service_tag": _SERVICE_TAG,
        }

    async def get_boot_order(self) -> Dict[str, Any]:
        return {
            "boot_order": ["NIC.PxeDevice.1-1", "HardDisk.List.1-1", "NIC.PxeDevice.2-1"],
            "boot_source_override_target": "None",
            "boot_source_override_enabled": "Disabled",
            "boot_source_override_mode": "UEFI",
            "allowed_boot_sources": ["None", "Pxe", "Cd", "Hdd", "BiosSetup", "UefiTarget", "SDCard", "UefiHttp"],
            "uefi_target": "",
        }

    async def set_next_boot_device(self, device: str) -> Dict[str, Any]:
        return {"success": True, "device": device, "message": f"Next boot override set to {device} (one-time)"}

    async def clear_sel(self) -> Dict[str, Any]:
        return {"success": True, "message": "System Event Log cleared"}

    async def get_lifecycle_status(self) -> Dict[str, Any]:
        return {
            "manager_status": "OK",
            "manager_state": "Enabled",
            "firmware_version": _IDRAC_VERSION,
            "lc_service_available": True,
            "lc_attributes": {
                "LCAttributes.1#AutoBackup": "Disabled",
                "LCAttributes.1#AutoUpdate": "Disabled",
            },
        }

    async def get_idrac_network_config(self) -> Dict[str, Any]:
        return {
            "ipv4": {
                "address": self.host if self.host != "demo" else "192.168.1.120",
                "subnet_mask": "255.255.255.0",
                "gateway": "192.168.1.1",
                "dhcp_enabled": False,
            },
            "ipv6": {"enabled": False},
            "dns": {"dns1": "10.0.0.1", "dns2": "10.0.0.2"},
            "vlan": {"enabled": False, "id": 0},
            "mac_address": "D0:8E:79:AA:BB:CC",
            "nic_selection": "Dedicated",
        }

    async def get_idrac_users(self) -> List[Dict[str, Any]]:
        return [
            {"id": "1", "username": "", "role": "", "enabled": False, "locked": False},
            {"id": "2", "username": "root", "role": "Administrator", "enabled": True, "locked": False},
            {"id": "3", "username": "monitor", "role": "ReadOnly", "enabled": True, "locked": False},
        ]

    async def get_ssl_certificate_info(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "available": True,
            "subject": f"CN={self.host}",
            "issuer": "CN=iDRAC Default Certificate Authority",
            "valid_from": (now - timedelta(days=365)).isoformat(),
            "valid_to": (now + timedelta(days=365)).isoformat(),
            "serial_number": "DEMO123456",
            "days_until_expiry": 365,
            "is_self_signed": True,
        }

    async def get_idrac_info(self) -> Dict[str, Any]:
        return {
            "firmware_version": _IDRAC_VERSION,
            "model": "iDRAC9",
            "status": "OK",
            "state": "Enabled",
            "network": await self.get_idrac_network_config(),
            "service_tag": _SERVICE_TAG,
            "express_service_code": "12345678901",
        }

    # ── internal data builders ───────────────────────────────────
    def _system_data(self) -> Dict[str, Any]:
        return {
            "Id": self.system_id,
            "Model": _MODEL,
            "Manufacturer": "Dell Inc.",
            "SKU": _SERVICE_TAG,
            "SerialNumber": _SERVICE_TAG,
            "HostName": _HOSTNAME,
            "BiosVersion": _BIOS_VERSION,
            "PowerState": "On",
            "SystemType": "Physical",
            "AssetTag": "DEMO-ASSET",
            "Status": {"Health": "OK", "State": "Enabled"},
            "MemorySummary": {"TotalSystemMemoryGiB": 512, "Status": {"Health": "OK"}},
            "ProcessorSummary": {"Model": "Intel Xeon Gold 6430", "Count": 2, "Status": {"Health": "OK"}},
            "Boot": {
                "BootOrder": ["NIC.PxeDevice.1-1", "HardDisk.List.1-1"],
                "BootSourceOverrideTarget": "None",
                "BootSourceOverrideEnabled": "Disabled",
                "BootSourceOverrideMode": "UEFI",
                "BootSourceOverrideTarget@Redfish.AllowableValues": [
                    "None", "Pxe", "Cd", "Hdd", "BiosSetup", "UefiTarget",
                ],
                "UefiTargetBootSourceOverride": "",
            },
            "BootProgress": {
                "LastState": "SystemHardwareInitializationComplete",
                "OemLastState": "",
            },
            "Oem": {
                "Dell": {
                    "LastPostCode": "0x0000",
                    "SystemGeneration": "16G Monolithic",
                },
            },
        }

    def _manager_data(self) -> Dict[str, Any]:
        return {
            "Id": "iDRAC.Embedded.1",
            "Name": "Manager",
            "FirmwareVersion": _IDRAC_VERSION,
            "Status": {"Health": "OK", "State": "Enabled"},
        }
