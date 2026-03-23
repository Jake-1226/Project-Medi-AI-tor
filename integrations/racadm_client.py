"""
RACADM client for Dell iDRAC management
"""

import asyncio
import subprocess
import logging
import re
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import tempfile
import os

from models.server_models import (
    ServerInfo, SystemInfo, LogEntry, HealthStatus, ServerStatus, 
    ComponentType, Severity, ProcessorInfo, MemoryInfo, StorageInfo,
    NetworkInterfaceInfo, TemperatureInfo, FanInfo, PowerSupplyInfo
)

logger = logging.getLogger(__name__)

class RacadmClient:
    """Dell RACADM client for iDRAC management"""
    
    def __init__(self, host: str, username: str, password: str, timeout: int = 60):
        self.host = host
        self.username = username
        self.password = password
        self.timeout = timeout
        self.racadm_path = self._find_racadm()
        
    def _find_racadm(self) -> str:
        """Find RACADM executable path"""
        # Common RACADM paths
        possible_paths = [
            "racadm",  # If in PATH
            "C:\\Program Files\\Dell\\SysMgmt\\racadm\\racadm.exe",
            "C:\\Program Files (x86)\\Dell\\SysMgmt\\racadm\\racadm.exe",
            "/opt/dell/srvadmin/bin/racadm",
            "/usr/bin/racadm"
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, "--version"], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    logger.info(f"Found RACADM at: {path}")
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        logger.warning("RACADM not found. Please install Dell OpenManage Server Administrator")
        return "racadm"  # Default, will fail if not found
    
    async def execute_command(self, command: str, args: List[str] = None) -> Tuple[bool, str]:
        """Execute RACADM command"""
        if args is None:
            args = []
        
        cmd = [self.racadm_path, "-r", self.host, "-u", self.username, "-p", self.password] + args + [command]
        
        try:
            logger.debug(f"Executing RACADM command: {' '.join(cmd[:4])} *** {command}")
            
            # Run command asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='ignore').strip()
                logger.debug(f"RACADM command succeeded: {output[:100]}...")
                return True, output
            else:
                error_msg = stderr.decode('utf-8', errors='ignore').strip()
                logger.error(f"RACADM command failed: {error_msg}")
                return False, error_msg
                
        except asyncio.TimeoutError:
            logger.error(f"RACADM command timed out after {self.timeout} seconds")
            return False, f"Command timed out after {self.timeout} seconds"
        except Exception as e:
            logger.error(f"RACADM command error: {str(e)}")
            return False, str(e)
    
    async def test_connection(self) -> bool:
        """Test connection to iDRAC"""
        success, output = await self.execute_command("getsysinfo")
        return success
    
    async def get_server_info(self) -> Optional[ServerInfo]:
        """Get basic server information"""
        try:
            success, output = await self.execute_command("getsysinfo")
            if not success:
                return None
            
            # Parse RACADM output
            info = {}
            for line in output.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    info[key.strip()] = value.strip()
            
            return ServerInfo(
                host=self.host,
                model=info.get("System Model"),
                service_tag=info.get("Service Tag"),
                firmware_version=info.get("BIOS Version"),
                idrac_version=info.get("iDRAC Version"),
                status=ServerStatus.ONLINE  # If we can connect, assume online
            )
            
        except Exception as e:
            logger.error(f"Failed to get server info: {str(e)}")
            return None
    
    async def get_system_info(self) -> Optional[SystemInfo]:
        """Get detailed system information"""
        try:
            success, output = await self.execute_command("getsysinfo")
            if not success:
                return None
            
            # Parse system information
            info = {}
            for line in output.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    info[key.strip()] = value.strip()
            
            return SystemInfo(
                manufacturer="Dell Inc.",  # Dell servers
                model=info.get("System Model"),
                serial_number=info.get("Service Tag"),
                part_number=info.get("Chassis Service Tag"),
                bios_version=info.get("BIOS Version"),
                system_type=info.get("System Type"),
                asset_tag=info.get("Asset Tag"),
                power_state=info.get("Power Status")
            )
            
        except Exception as e:
            logger.error(f"Failed to get system info: {str(e)}")
            return None
    
    async def get_power_consumption(self) -> Optional[Dict[str, Any]]:
        """Get power consumption information"""
        try:
            success, output = await self.execute_command("getsensorinfo")
            if not success:
                return None
            
            power_info = {}
            current_sensor = None
            
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    current_sensor = line[1:-1]
                    power_info[current_sensor] = {}
                elif '=' in line and current_sensor:
                    key, value = line.split('=', 1)
                    power_info[current_sensor][key.strip()] = value.strip()
            
            return power_info
            
        except Exception as e:
            logger.error(f"Failed to get power consumption: {str(e)}")
            return None
    
    async def get_temperature_sensors(self) -> Optional[Dict[str, Any]]:
        """Get temperature sensor information"""
        try:
            success, output = await self.execute_command("getsensorinfo")
            if not success:
                return None
            
            temp_info = {}
            current_sensor = None
            
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    current_sensor = line[1:-1]
                    if 'Temp' in current_sensor or 'Temperature' in current_sensor:
                        temp_info[current_sensor] = {}
                elif '=' in line and current_sensor and current_sensor in temp_info:
                    key, value = line.split('=', 1)
                    temp_info[current_sensor][key.strip()] = value.strip()
            
            return temp_info
            
        except Exception as e:
            logger.error(f"Failed to get temperature sensors: {str(e)}")
            return None
    
    async def get_fan_info(self) -> Optional[Dict[str, Any]]:
        """Get fan information"""
        try:
            success, output = await self.execute_command("getsensorinfo")
            if not success:
                return None
            
            fan_info = {}
            current_sensor = None
            
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    current_sensor = line[1:-1]
                    if 'Fan' in current_sensor:
                        fan_info[current_sensor] = {}
                elif '=' in line and current_sensor and current_sensor in fan_info:
                    key, value = line.split('=', 1)
                    fan_info[current_sensor][key.strip()] = value.strip()
            
            return fan_info
            
        except Exception as e:
            logger.error(f"Failed to get fan info: {str(e)}")
            return None
    
    async def get_storage_info(self) -> Optional[Dict[str, Any]]:
        """Get storage controller and disk information"""
        try:
            # Get storage controller info
            success, output = await self.execute_command("storage getpdisks")
            if not success:
                return None
            
            storage_info = {"controllers": {}, "disks": {}}
            current_controller = None
            
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('Controller'):
                    current_controller = line
                    storage_info["controllers"][current_controller] = {}
                elif '=' in line and current_controller:
                    key, value = line.split('=', 1)
                    storage_info["controllers"][current_controller][key.strip()] = value.strip()
            
            # Get virtual disk info
            success, vdisk_output = await self.execute_command("storage getvdisks")
            if success:
                storage_info["virtual_disks"] = {}
                current_vdisk = None
                
                for line in vdisk_output.split('\n'):
                    line = line.strip()
                    if line.startswith('Virtual Disk'):
                        current_vdisk = line
                        storage_info["virtual_disks"][current_vdisk] = {}
                    elif '=' in line and current_vdisk:
                        key, value = line.split('=', 1)
                        storage_info["virtual_disks"][current_vdisk][key.strip()] = value.strip()
            
            return storage_info
            
        except Exception as e:
            logger.error(f"Failed to get storage info: {str(e)}")
            return None
    
    async def get_network_info(self) -> Optional[Dict[str, Any]]:
        """Get network interface information"""
        try:
            success, output = await self.execute_command("getnicinfo")
            if not success:
                return None
            
            network_info = {}
            current_nic = None
            
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('NIC'):
                    current_nic = line
                    network_info[current_nic] = {}
                elif '=' in line and current_nic:
                    key, value = line.split('=', 1)
                    network_info[current_nic][key.strip()] = value.strip()
            
            return network_info
            
        except Exception as e:
            logger.error(f"Failed to get network info: {str(e)}")
            return None
    
    async def get_system_logs(self) -> List[LogEntry]:
        """Get system logs from iDRAC"""
        logs = []
        try:
            # Get system event log
            success, output = await self.execute_command("getsel")
            if not success:
                return logs
            
            # Parse log entries
            for line in output.split('\n'):
                if line.strip() and not line.startswith('='):
                    # RACADM log format: ID, Date, Time, Severity, Message
                    parts = line.split('|')
                    if len(parts) >= 4:
                        try:
                            # Parse timestamp
                            date_part = parts[1].strip()
                            time_part = parts[2].strip()
                            timestamp_str = f"{date_part} {time_part}"
                            timestamp = datetime.strptime(timestamp_str, "%m/%d/%Y %H:%M:%S")
                            
                            # Parse severity
                            severity_str = parts[3].strip().upper()
                            severity_map = {
                                "INFO": Severity.INFO,
                                "WARNING": Severity.WARNING,
                                "CRITICAL": Severity.CRITICAL,
                                "ERROR": Severity.ERROR
                            }
                            severity = severity_map.get(severity_str, Severity.INFO)
                            
                            # Parse message
                            message = "|".join(parts[4:]).strip() if len(parts) > 4 else ""
                            
                            logs.append(LogEntry(
                                timestamp=timestamp,
                                severity=severity,
                                message=message,
                                source="iDRAC",
                                component=ComponentType.SYSTEM,
                                event_id=parts[0].strip()
                            ))
                            
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Failed to parse log line: {line} - {str(e)}")
                            continue
            
        except Exception as e:
            logger.error(f"Failed to get system logs: {str(e)}")
        
        return logs
    
    async def get_lc_logs(self) -> List[LogEntry]:
        """Get lifecycle controller logs"""
        logs = []
        try:
            success, output = await self.execute_command("lclog view")
            if not success:
                return logs
            
            # Parse LC log entries
            for line in output.split('\n'):
                if line.strip() and not line.startswith('='):
                    # Similar parsing as system logs
                    parts = line.split('|')
                    if len(parts) >= 4:
                        try:
                            date_part = parts[1].strip()
                            time_part = parts[2].strip()
                            timestamp_str = f"{date_part} {time_part}"
                            timestamp = datetime.strptime(timestamp_str, "%m/%d/%Y %H:%M:%S")
                            
                            severity_str = parts[3].strip().upper()
                            severity_map = {
                                "INFO": Severity.INFO,
                                "WARNING": Severity.WARNING,
                                "CRITICAL": Severity.CRITICAL,
                                "ERROR": Severity.ERROR
                            }
                            severity = severity_map.get(severity_str, Severity.INFO)
                            
                            message = "|".join(parts[4:]).strip() if len(parts) > 4 else ""
                            
                            logs.append(LogEntry(
                                timestamp=timestamp,
                                severity=severity,
                                message=message,
                                source="Lifecycle Controller",
                                component=ComponentType.FIRMWARE,
                                event_id=parts[0].strip()
                            ))
                            
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Failed to parse LC log line: {line} - {str(e)}")
                            continue
            
        except Exception as e:
            logger.error(f"Failed to get LC logs: {str(e)}")
        
        return logs
    
    async def power_action(self, action: str) -> bool:
        """Execute power action"""
        try:
            # Map action names to RACADM commands
            action_map = {
                "power_on": "powerup",
                "power_off": "powerdown",
                "power_cycle": "hardreset",
                "graceful_restart": "graceshutdown",
                "force_restart": "hardreset"
            }
            
            racadm_action = action_map.get(action.lower())
            if not racadm_action:
                logger.error(f"Unknown power action: {action}")
                return False
            
            success, output = await self.execute_command("serveraction", [racadm_action])
            return success
            
        except Exception as e:
            logger.error(f"Failed to execute power action {action}: {str(e)}")
            return False
    
    async def set_boot_order(self, boot_devices: List[str]) -> bool:
        """Set boot order"""
        try:
            # RACADM boot order setting
            for i, device in enumerate(boot_devices):
                success, _ = await self.execute_command("set", [f"BootSeq.{i+1}", device])
                if not success:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set boot order: {str(e)}")
            return False
    
    async def get_idrac_settings(self) -> Optional[Dict[str, Any]]:
        """Get iDRAC settings"""
        try:
            success, output = await self.execute_command("get", ["iDRAC.NIC.1.IPv4Address"])
            if not success:
                return None
            
            settings = {}
            for line in output.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    settings[key.strip()] = value.strip()
            
            return settings
            
        except Exception as e:
            logger.error(f"Failed to get iDRAC settings: {str(e)}")
            return None
    
    async def create_support_assist_collection(self) -> Optional[str]:
        """Create SupportAssist collection"""
        try:
            success, output = await self.execute_command("supportassist", ["collect"])
            if not success:
                return None
            
            # Extract collection ID or path from output
            collection_id = None
            for line in output.split('\n'):
                if "Collection ID" in line or "ID:" in line:
                    collection_id = line.split(':')[-1].strip()
                    break
            
            return collection_id
            
        except Exception as e:
            logger.error(f"Failed to create SupportAssist collection: {str(e)}")
            return None
    
    async def export_system_configuration(self, filename: Optional[str] = None) -> Optional[str]:
        """Export system configuration"""
        try:
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"system_config_{timestamp}.xml"
            
            success, output = await self.execute_command("getconfig", ["-f", filename])
            if success:
                return filename
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to export system configuration: {str(e)}")
            return None
    
    async def import_system_configuration(self, filename: str) -> bool:
        """Import system configuration"""
        try:
            success, _ = await self.execute_command("config", ["-f", filename])
            return success
            
        except Exception as e:
            logger.error(f"Failed to import system configuration: {str(e)}")
            return False
    
    async def update_firmware(self, component: str, firmware_file: str) -> bool:
        """Update firmware for a component"""
        try:
            # Map component names to RACADM component IDs
            component_map = {
                "bios": "BIOS",
                "idrac": "iDRAC",
                "nic": "NIC",
                "storage": "Controller"
            }
            
            racadm_component = component_map.get(component.lower())
            if not racadm_component:
                logger.error(f"Unknown component for firmware update: {component}")
                return False
            
            success, _ = await self.execute_command("update", ["-f", firmware_file, racadm_component])
            return success
            
        except Exception as e:
            logger.error(f"Failed to update firmware for {component}: {str(e)}")
            return False
    
    # ─── Helper: parse key=value blocks ────────────────────────
    def _parse_kv_output(self, output: str) -> Dict[str, str]:
        """Parse simple key = value RACADM output into a dict"""
        info = {}
        for line in output.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                info[key.strip()] = value.strip()
        return info

    def _parse_hwinv_instances(self, output: str) -> List[Dict[str, str]]:
        """Parse racadm hwinventory output into a list of instance dicts."""
        instances = []
        current = {}
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith('---') or line.startswith('==='):
                if current:
                    instances.append(current)
                    current = {}
                continue
            if line.startswith('[InstanceID:') or line.startswith('[Key:'):
                if current:
                    instances.append(current)
                current = {'_header': line}
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                current[key.strip()] = val.strip()
        if current:
            instances.append(current)
        return instances

    @staticmethod
    def _safe_int(value: str, default: Optional[int] = None) -> Optional[int]:
        """Safely parse an integer from a string"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(value: str, default: Optional[float] = None) -> Optional[float]:
        """Safely parse a float from a string"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _extract_number(text: str) -> Optional[float]:
        """Extract the first number from a string"""
        if not text:
            return None
        m = re.search(r'[\d.]+', text)
        if m:
            try:
                return float(m.group())
            except (ValueError, TypeError):
                return None
        return None

    def _parse_sensor_blocks(self, output: str) -> List[Dict[str, str]]:
        """Parse getsensorinfo output into list of {name, key=val} blocks"""
        blocks = []
        current_name = None
        current_data = {}
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                if current_name:
                    current_data['_name'] = current_name
                    blocks.append(current_data)
                current_name = None
                current_data = {}
                continue
            if line.startswith('[') and line.endswith(']'):
                if current_name:
                    current_data['_name'] = current_name
                    blocks.append(current_data)
                current_name = line[1:-1]
                current_data = {}
            elif '=' in line:
                key, val = line.split('=', 1)
                current_data[key.strip()] = val.strip()
        if current_name:
            current_data['_name'] = current_name
            blocks.append(current_data)
        return blocks

    # ─── Structured: Processors ──────────────────────────────────
    async def get_processors_structured(self) -> List[ProcessorInfo]:
        """Get processor info via hwinventory"""
        procs = []
        try:
            success, output = await self.execute_command("hwinventory")
            if not success:
                return procs
            instances = self._parse_hwinv_instances(output)
            for inst in instances:
                header = inst.get('_header', '')
                dev_type = inst.get('Device Type', '')
                if 'CPU' in header or 'Processor' in dev_type or 'CPU' in dev_type:
                    cores = self._safe_int(inst.get('NumberOfEnabledCores', inst.get('CoreCount', '')))
                    threads = self._safe_int(inst.get('NumberOfEnabledThreads', inst.get('ThreadCount', '')))
                    speed = self._safe_float(inst.get('CurrentClockSpeed', inst.get('MaxClockSpeed', '')))
                    procs.append(ProcessorInfo(
                        id=inst.get('InstanceID', inst.get('FQDD', f'CPU-{len(procs)}')),
                        manufacturer=inst.get('Manufacturer', inst.get('CPUManufacturer', None)),
                        model=inst.get('Model', inst.get('CPUFamily', None)),
                        cores=cores,
                        threads=threads,
                        speed_mhz=speed,
                        status=inst.get('PrimaryStatus', inst.get('Status', 'OK')),
                        socket=inst.get('InstanceID', inst.get('FQDD', None))
                    ))
        except Exception as e:
            logger.error(f"Failed to get processors via RACADM: {str(e)}")
        return procs

    # ─── Structured: Memory ──────────────────────────────────────
    async def get_memory_structured(self) -> List[MemoryInfo]:
        """Get memory DIMM info via hwinventory"""
        dimms = []
        try:
            success, output = await self.execute_command("hwinventory")
            if not success:
                return dimms
            instances = self._parse_hwinv_instances(output)
            for inst in instances:
                header = inst.get('_header', '')
                dev_type = inst.get('Device Type', '')
                if 'DIMM' in header or 'Memory' in dev_type or 'DIMM' in dev_type:
                    size_mb = self._safe_int(inst.get('Size', inst.get('MemorySizeInMB', '')))
                    size_gb = None
                    if size_mb is not None and size_mb > 0:
                        size_gb = size_mb // 1024 if size_mb >= 1024 else size_mb
                    speed = self._safe_int(inst.get('Speed', inst.get('CurrentOperatingSpeed', '')))
                    if size_gb and size_gb > 0:
                        dimms.append(MemoryInfo(
                            id=inst.get('InstanceID', inst.get('FQDD', f'DIMM-{len(dimms)}')),
                            manufacturer=inst.get('Manufacturer', None),
                            part_number=inst.get('PartNumber', inst.get('Model', None)),
                            size_gb=size_gb,
                            speed_mhz=speed,
                            type=inst.get('MemoryType', inst.get('Type', None)),
                            status=inst.get('PrimaryStatus', inst.get('Status', 'OK')),
                            location=inst.get('DeviceDescription', inst.get('BankLabel', None))
                        ))
        except Exception as e:
            logger.error(f"Failed to get memory via RACADM: {str(e)}")
        return dimms

    # ─── Structured: Storage ─────────────────────────────────────
    async def get_storage_structured(self) -> List[StorageInfo]:
        """Get physical disk info via hwinventory"""
        disks = []
        try:
            success, output = await self.execute_command("hwinventory")
            if not success:
                return disks
            instances = self._parse_hwinv_instances(output)
            for inst in instances:
                header = inst.get('_header', '')
                dev_type = inst.get('Device Type', '')
                if 'Disk' in header or 'Physical Disk' in dev_type or 'SSD' in dev_type or 'HDD' in dev_type:
                    cap_gb = None
                    raw_size = inst.get('SizeInBytes', inst.get('Size', ''))
                    cap_val = self._safe_int(raw_size.replace(',', '').split('.')[0] if raw_size else '')
                    if cap_val is not None and cap_val > 0:
                        if cap_val > 1024 ** 3:
                            cap_gb = cap_val // (1024 ** 3)
                        elif cap_val > 1024 ** 2:
                            cap_gb = cap_val // (1024 ** 2)
                        else:
                            cap_gb = cap_val
                    disks.append(StorageInfo(
                        id=inst.get('InstanceID', inst.get('FQDD', f'Disk-{len(disks)}')),
                        name=inst.get('DeviceDescription', inst.get('Name', None)),
                        manufacturer=inst.get('Manufacturer', inst.get('Vendor', None)),
                        model=inst.get('Model', inst.get('ProductID', None)),
                        capacity_gb=cap_gb,
                        type=inst.get('MediaType', inst.get('Device Type', None)),
                        interface=inst.get('BusProtocol', inst.get('Protocol', None)),
                        status=inst.get('PrimaryStatus', inst.get('Status', 'OK')),
                        firmware_version=inst.get('Revision', inst.get('FirmwareVersion', None)),
                        serial_number=inst.get('SerialNumber', None)
                    ))
        except Exception as e:
            logger.error(f"Failed to get storage via RACADM: {str(e)}")
        return disks

    # ─── Structured: Network ─────────────────────────────────────
    async def get_network_structured(self) -> List[NetworkInterfaceInfo]:
        """Get NIC info via hwinventory"""
        nics = []
        try:
            success, output = await self.execute_command("hwinventory")
            if not success:
                return nics
            instances = self._parse_hwinv_instances(output)
            for inst in instances:
                header = inst.get('_header', '')
                dev_type = inst.get('Device Type', '')
                if 'NIC' in header or 'Network' in dev_type or 'NIC' in dev_type or 'Ethernet' in dev_type:
                    raw_speed = inst.get('LinkSpeed', '')
                    speed = self._safe_int(raw_speed.replace('Mbps', '').replace('Gbps', '000').strip())
                    nics.append(NetworkInterfaceInfo(
                        id=inst.get('InstanceID', inst.get('FQDD', f'NIC-{len(nics)}')),
                        name=inst.get('DeviceDescription', inst.get('ProductName', None)),
                        mac_address=inst.get('CurrentMACAddress', inst.get('PermanentMACAddress', None)),
                        speed_mbps=speed,
                        status=inst.get('PrimaryStatus', inst.get('Status', 'OK')),
                        link_status=inst.get('LinkStatus', inst.get('MediaType', None)),
                        auto_negotiation=None,
                        ipv4_addresses=[],
                        ipv6_addresses=[]
                    ))
        except Exception as e:
            logger.error(f"Failed to get network via RACADM: {str(e)}")
        return nics

    # ─── Structured: Temperature sensors ─────────────────────────
    async def get_temperatures_structured(self) -> List[TemperatureInfo]:
        """Get temperature sensors from getsensorinfo"""
        temps = []
        try:
            success, output = await self.execute_command("getsensorinfo")
            if not success:
                return temps
            blocks = self._parse_sensor_blocks(output)
            for blk in blocks:
                name = blk.get('_name', '')
                if not any(kw in name for kw in ('Temp', 'Temperature', 'Inlet', 'Exhaust')):
                    continue
                reading = self._extract_number(blk.get('Reading', blk.get('Value', '')))
                warn_thresh = self._extract_number(blk.get('Upper Non-Critical Threshold', blk.get('Warning', '')))
                crit_thresh = self._extract_number(blk.get('Upper Critical Threshold', blk.get('Critical', blk.get('Failure', ''))))
                temps.append(TemperatureInfo(
                    id=f'Temp-{len(temps)}',
                    name=name,
                    reading_celsius=reading,
                    status=blk.get('Status', 'OK'),
                    location=name,
                    upper_threshold_critical=crit_thresh,
                    upper_threshold_non_critical=warn_thresh
                ))
        except Exception as e:
            logger.error(f"Failed to get structured temperatures: {str(e)}")
        return temps

    # ─── Structured: Fan sensors ─────────────────────────────────
    async def get_fans_structured(self) -> List[FanInfo]:
        """Get fan sensors from getsensorinfo"""
        fans = []
        try:
            success, output = await self.execute_command("getsensorinfo")
            if not success:
                return fans
            blocks = self._parse_sensor_blocks(output)
            for blk in blocks:
                name = blk.get('_name', '')
                if 'Fan' not in name:
                    continue
                rpm_val = self._extract_number(blk.get('Reading', blk.get('Value', '')))
                rpm = int(rpm_val) if rpm_val is not None else None
                fans.append(FanInfo(
                    id=f'Fan-{len(fans)}',
                    name=name,
                    speed_rpm=rpm,
                    status=blk.get('Status', 'OK'),
                    location=name,
                    min_speed_rpm=None,
                    max_speed_rpm=None
                ))
        except Exception as e:
            logger.error(f"Failed to get structured fans: {str(e)}")
        return fans

    # ─── Structured: Power Supplies ──────────────────────────────
    async def get_power_supplies_structured(self) -> List[PowerSupplyInfo]:
        """Get PSU info from hwinventory"""
        psus = []
        try:
            success, output = await self.execute_command("hwinventory")
            if not success:
                return psus
            instances = self._parse_hwinv_instances(output)
            for inst in instances:
                header = inst.get('_header', '')
                dev_type = inst.get('Device Type', '')
                if 'PSU' in header or 'Power Supply' in dev_type or 'PowerSupply' in header:
                    raw_watts = inst.get('TotalOutputPower', inst.get('DetailedState', inst.get('RatedMaxOutputPower', '')))
                    watts_val = self._extract_number(raw_watts)
                    watts = int(watts_val) if watts_val is not None else None
                    psus.append(PowerSupplyInfo(
                        id=inst.get('InstanceID', inst.get('FQDD', f'PSU-{len(psus)}')),
                        manufacturer=inst.get('Manufacturer', None),
                        model=inst.get('Model', inst.get('Name', None)),
                        power_watts=watts,
                        input_voltage=None,
                        output_voltage=None,
                        efficiency=None,
                        status=inst.get('PrimaryStatus', inst.get('Status', 'OK')),
                        firmware_version=inst.get('FirmwareVersion', inst.get('Revision', None))
                    ))
        except Exception as e:
            logger.error(f"Failed to get PSUs via RACADM: {str(e)}")
        return psus

    # ─── Firmware inventory via hwinventory ───────────────────────
    async def get_firmware_inventory(self) -> List[Dict[str, Any]]:
        """Get firmware versions from hwinventory"""
        fw_list = []
        try:
            success, output = await self.execute_command("hwinventory")
            if not success:
                return fw_list
            instances = self._parse_hwinv_instances(output)
            for inst in instances:
                dev_type = inst.get('Device Type', '')
                fw_ver = inst.get('FirmwareVersion', inst.get('Revision', inst.get('VersionString', '')))
                if fw_ver:
                    fw_list.append({
                        "id": inst.get('InstanceID', inst.get('FQDD', '')),
                        "name": inst.get('DeviceDescription', inst.get('Name', dev_type)),
                        "version": fw_ver,
                        "updateable": True,
                        "status": inst.get('PrimaryStatus', inst.get('Status', 'OK')),
                        "release_date": "",
                        "manufacturer": inst.get('Manufacturer', inst.get('Vendor', '')),
                        "description": dev_type,
                        "component_id": inst.get('ComponentID', ''),
                    })
        except Exception as e:
            logger.error(f"Failed to get firmware inventory via RACADM: {str(e)}")
        return fw_list

    # ─── BIOS attributes via get BIOS. ───────────────────────────
    async def get_bios_attributes(self) -> Dict[str, Any]:
        """Get BIOS attributes via racadm get BIOS."""
        attrs = {}
        try:
            success, output = await self.execute_command("get", ["BIOS."])
            if not success:
                return {"attributes": {}}
            for line in output.split('\n'):
                stripped = line.strip()
                if '=' in stripped and not stripped.startswith('#') and not stripped.startswith('['):
                    key, val = stripped.split('=', 1)
                    attrs[key.strip()] = val.strip()
            return {
                "attributes": attrs,
                "bios_version": "",
                "attribute_registry": "RACADM",
                "description": f"BIOS attributes ({len(attrs)} found)",
            }
        except Exception as e:
            logger.error(f"Failed to get BIOS attributes via RACADM: {str(e)}")
            return {"attributes": {}}

    # ─── iDRAC info ──────────────────────────────────────────────
    async def get_idrac_info(self) -> Dict[str, Any]:
        """Get iDRAC info"""
        try:
            success, output = await self.execute_command("getidracinfo")
            if not success:
                success, output = await self.execute_command("getsysinfo")
            if not success:
                return {}
            info = self._parse_kv_output(output)
            return {
                "id": "iDRAC",
                "firmware_version": info.get("iDRAC Version", info.get("Firmware Version", "")),
                "model": info.get("iDRAC Type", info.get("System Model", "")),
                "status": "OK (Enabled)",
                "date_time": "",
                "uuid": info.get("System ID", ""),
                "network_protocol": {},
            }
        except Exception as e:
            logger.error(f"Failed to get iDRAC info via RACADM: {str(e)}")
            return {}

    async def get_virtual_console_info(self) -> Optional[Dict[str, Any]]:
        """Get virtual console information"""
        try:
            success, output = await self.execute_command("get", ["idrac.VirtualConsole"])
            if not success:
                return None
            
            console_info = {}
            for line in output.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    console_info[key.strip()] = value.strip()
            
            return console_info
            
        except Exception as e:
            logger.error(f"Failed to get virtual console info: {str(e)}")
            return None
