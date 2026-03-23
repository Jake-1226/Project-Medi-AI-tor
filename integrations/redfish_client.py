"""
Redfish API client for Dell server management
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin
import ssl
from datetime import datetime

from models.server_models import (
    ServerInfo, SystemInfo, ProcessorInfo, MemoryInfo, PowerSupplyInfo,
    TemperatureInfo, FanInfo, StorageInfo, NetworkInterfaceInfo,
    LogEntry, HealthStatus, PerformanceMetrics, ServerStatus, ComponentType, Severity
)
from core.cache_manager import cache_manager

logger = logging.getLogger(__name__)

class RedfishClient:
    """Dell Redfish API client for server management"""
    
    def __init__(self, host: str, username: str, password: str, port: int = 443, verify_ssl: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{host}:{port}"
        self.session = None
        self.auth_token = None
        self.system_id = None
        self.chassis_id = None
        
    def _url(self, path: str) -> str:
        """Build a full URL from a Redfish path.
        Accepts both relative ('Systems') and absolute ('/redfish/v1/Systems') paths."""
        if path.startswith('/'):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/redfish/v1/{path}"

    async def connect(self) -> bool:
        """Establish connection to the Redfish API"""
        try:
            # Create SSL context
            ssl_context = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            # Create session with generous timeout
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=60, connect=20),
                auth=aiohttp.BasicAuth(self.username, self.password)
            )
            
            # Test basic connectivity first
            root_url = f"{self.base_url}/redfish/v1"
            logger.info(f"Testing Redfish connectivity to {root_url}")
            async with self.session.get(root_url) as response:
                if response.status != 200:
                    logger.error(f"Redfish root endpoint returned {response.status}")
                    await self.session.close()
                    self.session = None
                    return False
                root_data = await response.json()
                logger.info(f"Redfish root OK: {root_data.get('RedfishVersion', 'unknown')}")
            
            # Try to get auth token (optional - basic auth is the fallback)
            await self._get_auth_token()
            
            # Get system information
            systems = await self._get("Systems")
            if systems and systems.get("Members"):
                self.system_id = systems["Members"][0]["@odata.id"].split("/")[-1]
                logger.info(f"Connected to Dell server {self.host}, System ID: {self.system_id}")
            else:
                logger.error("No systems found on the server")
                return False

            # Discover chassis ID for Power/Thermal (needed for 16G+)
            chassis = await self._get("Chassis")
            if chassis and chassis.get("Members"):
                self.chassis_id = chassis["Members"][0]["@odata.id"].split("/")[-1]
                logger.info(f"Chassis ID: {self.chassis_id}")

            return True
                
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Cannot reach Redfish endpoint at {self.base_url}: {str(e)}")
            return False
        except asyncio.TimeoutError:
            logger.error(f"Redfish connection timed out for {self.base_url}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Redfish API: {type(e).__name__}: {str(e)}")
            return False
    
    async def disconnect(self):
        """Close the connection"""
        if self.session:
            await self.session.close()
            self.session = None
            self.auth_token = None
    
    async def _get_auth_token(self):
        """Get authentication token from Redfish API"""
        try:
            auth_url = f"{self.base_url}/redfish/v1/Sessions"
            auth_data = {"UserName": self.username, "Password": self.password}
            headers = {"Content-Type": "application/json"}
            
            async with self.session.post(auth_url, json=auth_data, headers=headers) as response:
                if response.status in (200, 201):
                    self.auth_token = response.headers.get("X-Auth-Token")
                    if self.auth_token:
                        self.session._default_headers["X-Auth-Token"] = self.auth_token
                        logger.info("Successfully obtained Redfish auth token")
                    else:
                        logger.info("Session created but no X-Auth-Token header, using basic auth")
                else:
                    logger.info(f"Token auth not available (status {response.status}), using basic auth")
                    
        except Exception as e:
            logger.info(f"Token auth skipped, using basic auth: {str(e)}")
    
    async def _get(self, endpoint: str, params: Optional[Dict] = None, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Make GET request to Redfish API with caching and retry support"""
        if not self.session:
            raise RuntimeError("Not connected to Redfish API")
        
        url = self._url(endpoint)
        
        # Try cache first
        if use_cache:
            cached_result = await cache_manager.get(endpoint, params)
            if cached_result is not None:
                logger.debug(f"Cache hit for {endpoint}")
                return cached_result
        
        # Retry up to 2 times on transient failures
        last_error = None
        for attempt in range(2):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if use_cache:
                            etag = response.headers.get("ETag")
                            await cache_manager.set(endpoint, data, params, etag)
                        return data
                    elif response.status in (503, 429):
                        # Service unavailable or rate limited — retry after brief delay
                        logger.warning(f"GET {url} => {response.status}, retrying...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        text = await response.text()
                        logger.error(f"GET {url} => {response.status}: {text[:200]}")
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt == 0:
                    logger.warning(f"GET {url} transient error: {e}, retrying...")
                    await asyncio.sleep(0.5)
                    continue
                logger.error(f"GET {url} error after retry: {type(e).__name__}: {str(e)}")
            except Exception as e:
                logger.error(f"GET {url} error: {type(e).__name__}: {str(e)}")
                return None
        return None
    
    async def _post(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make POST request to Redfish API"""
        if not self.session:
            raise RuntimeError("Not connected to Redfish API")
        
        url = self._url(endpoint)
        try:
            async with self.session.post(url, json=data) as response:
                if response.status in [200, 201, 202, 204]:
                    # Capture Location header — iDRAC returns job URI here on 202 Accepted
                    location = response.headers.get("Location", "")
                    try:
                        body = await response.json()
                    except Exception:
                        body = {"success": True, "status": response.status}
                    if location and isinstance(body, dict):
                        body["_location"] = location
                        # Extract job ID from Location URL (e.g. /redfish/v1/Managers/.../Jobs/JID_xxx)
                        if "/Jobs/" in location or "/JID_" in location:
                            job_id = location.rstrip("/").rsplit("/", 1)[-1]
                            body["_job_id"] = job_id
                    return body
                else:
                    text = await response.text()
                    logger.error(f"POST {url} => {response.status}: {text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"POST {url} error: {type(e).__name__}: {str(e)}")
            return None
    
    async def _patch(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """Make PATCH request to Redfish API"""
        if not self.session:
            raise RuntimeError("Not connected to Redfish API")
        
        url = self._url(endpoint)
        try:
            async with self.session.patch(url, json=data) as response:
                if response.status in [200, 202]:
                    return True
                else:
                    logger.error(f"PATCH request failed: {response.status} - {await response.text()}")
                    return False
        except Exception as e:
            logger.error(f"PATCH request error: {str(e)}")
            return False
    
    async def get_server_info(self) -> Optional[ServerInfo]:
        """Get basic server information"""
        try:
            if not self.system_id:
                return None
            
            system_data = await self._get(f"Systems/{self.system_id}")
            if not system_data:
                return None
            
            # Get manager/iDRAC info
            manager_data = await self._get("Managers")
            idrac_info = None
            if manager_data and manager_data.get("Members"):
                manager_url = manager_data["Members"][0]["@odata.id"]
                idrac_data = await self._get(manager_url.replace("/redfish/v1/", ""))
                if idrac_data:
                    idrac_info = idrac_data.get("FirmwareVersion")
            
            return ServerInfo(
                host=self.host,
                model=system_data.get("Model"),
                service_tag=system_data.get("SKU"),
                firmware_version=system_data.get("BiosVersion"),
                idrac_version=idrac_info,
                status=self._map_status(system_data.get("Status", {}))
            )
            
        except Exception as e:
            logger.error(f"Failed to get server info: {str(e)}")
            return None
    
    async def get_system_info(self) -> Optional[SystemInfo]:
        """Get detailed system information"""
        try:
            if not self.system_id:
                return None
            
            system_data = await self._get(f"Systems/{self.system_id}")
            if not system_data:
                return None
            
            return SystemInfo(
                manufacturer=system_data.get("Manufacturer"),
                model=system_data.get("Model"),
                serial_number=system_data.get("SerialNumber"),
                part_number=system_data.get("PartNumber"),
                bios_version=system_data.get("BiosVersion"),
                system_type=system_data.get("SystemType"),
                asset_tag=system_data.get("AssetTag"),
                power_state=system_data.get("PowerState"),
                boot_order=system_data.get("Boot", {}).get("BootOrder", [])
            )
            
        except Exception as e:
            logger.error(f"Failed to get system info: {str(e)}")
            return None
    
    async def get_processors(self) -> List[ProcessorInfo]:
        """Get processor information"""
        processors = []
        try:
            if not self.system_id:
                return processors
            
            processors_data = await self._get(f"Systems/{self.system_id}/Processors")
            if not processors_data:
                return processors
            
            for processor_member in processors_data.get("Members", []):
                processor_url = processor_member["@odata.id"].replace("/redfish/v1/", "")
                processor_info = await self._get(processor_url)
                
                if processor_info:
                    processors.append(ProcessorInfo(
                        id=processor_info.get("Id"),
                        manufacturer=processor_info.get("Manufacturer"),
                        model=processor_info.get("Model"),
                        cores=processor_info.get("TotalCores"),
                        threads=processor_info.get("TotalThreads"),
                        speed_mhz=processor_info.get("MaxSpeedMHz"),
                        status=self._get_status_string(processor_info.get("Status", {})),
                        socket=processor_info.get("Socket")
                    ))
            
        except Exception as e:
            logger.error(f"Failed to get processors: {str(e)}")
        
        return processors
    
    async def get_memory(self) -> List[MemoryInfo]:
        """Get memory information"""
        memory_modules = []
        try:
            if not self.system_id:
                return memory_modules
            
            memory_data = await self._get(f"Systems/{self.system_id}/Memory")
            if not memory_data:
                return memory_modules
            
            for memory_member in memory_data.get("Members", []):
                memory_url = memory_member["@odata.id"].replace("/redfish/v1/", "")
                memory_info = await self._get(memory_url)
                
                if memory_info:
                    cap_mib = memory_info.get("CapacityMiB")
                    size_gb = cap_mib // 1024 if cap_mib and cap_mib > 0 else None
                    speed = (memory_info.get("OperatingSpeedMhz")
                             or memory_info.get("OperatingSpeedMHz")
                             or (memory_info.get("AllowedSpeedsMHz", [None])[0] if memory_info.get("AllowedSpeedsMHz") else None))
                    memory_modules.append(MemoryInfo(
                        id=memory_info.get("Id"),
                        manufacturer=memory_info.get("Manufacturer"),
                        part_number=memory_info.get("PartNumber"),
                        size_gb=size_gb,
                        speed_mhz=speed,
                        type=memory_info.get("MemoryDeviceType") or memory_info.get("MemoryType"),
                        status=self._get_status_string(memory_info.get("Status", {})),
                        location=memory_info.get("DeviceLocator")
                    ))
            
        except Exception as e:
            logger.error(f"Failed to get memory: {str(e)}")
        
        return memory_modules
    
    async def get_power_supplies(self) -> List[PowerSupplyInfo]:
        """Get power supply information (tries Chassis path first for 16G+, then legacy)"""
        power_supplies = []
        try:
            if not self.system_id:
                return power_supplies

            power_data = None
            psu_members = None

            # 16G+ path: Chassis/{id}/PowerSubsystem/PowerSupplies
            if self.chassis_id:
                ps_collection = await self._get(f"Chassis/{self.chassis_id}/PowerSubsystem/PowerSupplies")
                if ps_collection and ps_collection.get("Members"):
                    psu_members = []
                    for m in ps_collection["Members"]:
                        psu_url = m["@odata.id"].replace("/redfish/v1/", "")
                        psu_data = await self._get(psu_url)
                        if psu_data:
                            psu_members.append(psu_data)

            if psu_members:
                for psu in psu_members:
                    power_supplies.append(PowerSupplyInfo(
                        id=psu.get("Id", psu.get("MemberId")),
                        manufacturer=psu.get("Manufacturer"),
                        model=psu.get("Model"),
                        power_watts=psu.get("PowerCapacityWatts"),
                        input_voltage=psu.get("InputVoltage"),
                        output_voltage=psu.get("OutputNominalVoltage"),
                        efficiency=psu.get("EfficiencyPercent") or psu.get("EfficiencyRatings", [{}])[0].get("EfficiencyPercent") if psu.get("EfficiencyRatings") else None,
                        status=self._get_status_string(psu.get("Status", {})),
                        firmware_version=psu.get("FirmwareVersion")
                    ))
            else:
                # Legacy path: Systems/{id}/Power
                power_data = await self._get(f"Systems/{self.system_id}/Power")
                if power_data:
                    for psu in power_data.get("PowerSupplies", []):
                        power_supplies.append(PowerSupplyInfo(
                            id=psu.get("MemberId"),
                            manufacturer=psu.get("Manufacturer"),
                            model=psu.get("Model"),
                            power_watts=psu.get("PowerCapacityWatts"),
                            input_voltage=psu.get("InputVolts"),
                            output_voltage=psu.get("OutputVolts"),
                            efficiency=psu.get("EfficiencyPercent"),
                            status=self._get_status_string(psu.get("Status", {})),
                            firmware_version=psu.get("FirmwareVersion")
                        ))

        except Exception as e:
            logger.error(f"Failed to get power supplies: {str(e)}")

        return power_supplies
    
    async def _get_all_chassis_sensors(self) -> List[Dict[str, Any]]:
        """Fetch all Chassis sensors once and cache them for reuse by temp/fan methods."""
        if not self.chassis_id:
            return []
        if hasattr(self, '_sensor_cache') and self._sensor_cache is not None:
            return self._sensor_cache
        sensors_collection = await self._get(f"Chassis/{self.chassis_id}/Sensors")
        if not sensors_collection or not sensors_collection.get("Members"):
            self._sensor_cache = []
            return []
        all_sensors = []
        for m in sensors_collection["Members"]:
            s_url = m["@odata.id"].replace("/redfish/v1/", "")
            s_data = await self._get(s_url)
            if s_data:
                all_sensors.append(s_data)
        self._sensor_cache = all_sensors
        return all_sensors

    def _clear_sensor_cache(self):
        """Clear sensor cache so next call re-fetches."""
        self._sensor_cache = None

    async def get_temperature_sensors(self) -> List[TemperatureInfo]:
        """Get temperature sensor information (tries Chassis path first for 16G+)"""
        temperatures = []
        try:
            if not self.system_id:
                return temperatures

            # 16G+ path: Chassis sensors filtered to Temperature
            if self.chassis_id:
                all_sensors = await self._get_all_chassis_sensors()
                temp_sensors = [s for s in all_sensors if s.get("ReadingType") == "Temperature"]
                if temp_sensors:
                    for s in temp_sensors:
                        thresholds = s.get("Thresholds", {})
                        temperatures.append(TemperatureInfo(
                            id=s.get("Id"),
                            name=s.get("Name"),
                            reading_celsius=s.get("Reading"),
                            status=self._get_status_string(s.get("Status", {})),
                            location=s.get("PhysicalContext", s.get("Name")),
                            upper_threshold_critical=thresholds.get("UpperCritical", {}).get("Reading"),
                            upper_threshold_non_critical=thresholds.get("UpperCaution", {}).get("Reading")
                        ))
                    return temperatures

            # Legacy path
            thermal_data = await self._get(f"Systems/{self.system_id}/Thermal")
            if thermal_data:
                for temp in thermal_data.get("Temperatures", []):
                    temperatures.append(TemperatureInfo(
                        id=temp.get("MemberId"),
                        name=temp.get("Name"),
                        reading_celsius=temp.get("ReadingCelsius"),
                        status=self._get_status_string(temp.get("Status", {})),
                        location=temp.get("PhysicalContext"),
                        upper_threshold_critical=temp.get("UpperThresholdCritical"),
                        upper_threshold_non_critical=temp.get("UpperThresholdNonCritical")
                    ))

        except Exception as e:
            logger.error(f"Failed to get temperature sensors: {str(e)}")

        return temperatures
    
    async def get_fans(self) -> List[FanInfo]:
        """Get fan information (tries Chassis Sensors path for 16G+)"""
        fans = []
        try:
            if not self.system_id:
                return fans

            # 16G+ path: Chassis sensors filtered to Rotational
            if self.chassis_id:
                all_sensors = await self._get_all_chassis_sensors()
                fan_sensors = [s for s in all_sensors if s.get("ReadingType") == "Rotational"]
                if fan_sensors:
                    for s in fan_sensors:
                        fans.append(FanInfo(
                            id=s.get("Id"),
                            name=s.get("Name"),
                            speed_rpm=int(s["Reading"]) if s.get("Reading") is not None else None,
                            status=self._get_status_string(s.get("Status", {})),
                            location=s.get("PhysicalContext", s.get("Name")),
                            min_speed_rpm=None,
                            max_speed_rpm=None
                        ))
                    return fans

            # Legacy path
            thermal_data = await self._get(f"Systems/{self.system_id}/Thermal")
            if thermal_data:
                for fan in thermal_data.get("Fans", []):
                    fans.append(FanInfo(
                        id=fan.get("MemberId"),
                        name=fan.get("Name"),
                        speed_rpm=fan.get("Reading"),
                        status=self._get_status_string(fan.get("Status", {})),
                        location=fan.get("PhysicalContext"),
                        min_speed_rpm=fan.get("MinReadingRange"),
                        max_speed_rpm=fan.get("MaxReadingRange")
                    ))

        except Exception as e:
            logger.error(f"Failed to get fans: {str(e)}")

        return fans
    
    async def get_storage_devices(self) -> List[StorageInfo]:
        """Get storage device information"""
        storage_devices = []
        try:
            if not self.system_id:
                return storage_devices
            
            storage_data = await self._get(f"Systems/{self.system_id}/Storage")
            if not storage_data:
                return storage_devices
            
            for storage_member in storage_data.get("Members", []):
                storage_url = storage_member["@odata.id"].replace("/redfish/v1/", "")
                storage_info = await self._get(storage_url)
                
                if storage_info:
                    for drive in storage_info.get("Drives", []):
                        drive_url = drive["@odata.id"].replace("/redfish/v1/", "")
                        drive_info = await self._get(drive_url)
                        
                        if drive_info:
                            storage_devices.append(StorageInfo(
                                id=drive_info.get("Id"),
                                name=drive_info.get("Name"),
                                manufacturer=drive_info.get("Manufacturer"),
                                model=drive_info.get("Model"),
                                capacity_gb=drive_info.get("CapacityBytes", 0) // (1024**3) if drive_info.get("CapacityBytes") else None,
                                type=drive_info.get("MediaType"),
                                interface=drive_info.get("Protocol"),
                                status=self._get_status_string(drive_info.get("Status", {})),
                                firmware_version=drive_info.get("FirmwareVersion"),
                                serial_number=drive_info.get("SerialNumber")
                            ))
            
        except Exception as e:
            logger.error(f"Failed to get storage devices: {str(e)}")
        
        return storage_devices
    
    async def get_network_interfaces(self) -> List[NetworkInterfaceInfo]:
        """Get network interface information"""
        network_interfaces = []
        try:
            if not self.system_id:
                return network_interfaces
            
            network_data = await self._get(f"Systems/{self.system_id}/EthernetInterfaces")
            if not network_data:
                return network_interfaces
            
            for network_member in network_data.get("Members", []):
                network_url = network_member["@odata.id"].replace("/redfish/v1/", "")
                network_info = await self._get(network_url)
                
                if network_info:
                    network_interfaces.append(NetworkInterfaceInfo(
                        id=network_info.get("Id"),
                        name=network_info.get("Name"),
                        mac_address=network_info.get("MACAddress"),
                        speed_mbps=network_info.get("SpeedMbps"),
                        status=self._get_status_string(network_info.get("Status", {})),
                        link_status=network_info.get("LinkStatus"),
                        auto_negotiation=network_info.get("AutoNeg"),
                        ipv4_addresses=[addr.get("Address") for addr in network_info.get("IPv4Addresses", [])],
                        ipv6_addresses=[addr.get("Address") for addr in network_info.get("IPv6Addresses", [])]
                    ))
            
        except Exception as e:
            logger.error(f"Failed to get network interfaces: {str(e)}")
        
        return network_interfaces
    
    async def get_logs(self, log_type: str = "System") -> List[LogEntry]:
        """Get system logs"""
        logs = []
        try:
            # Get manager for logs
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return logs
            
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            
            # Get log service
            log_service_data = await self._get(f"{manager_url}/LogServices")
            if not log_service_data:
                return logs
            
            for log_service_member in log_service_data.get("Members", []):
                member_id = log_service_member.get("@odata.id", "")
                member_name = log_service_member.get("Name", "")
                # Match by name or by URL path (Sel, Lclog, etc.)
                if log_type.lower() in member_name.lower() or log_type.lower() in member_id.lower() or "sel" in member_id.lower() or "lclog" in member_id.lower():
                    log_service_url = member_id.replace("/redfish/v1/", "")
                    log_entries_data = await self._get(f"{log_service_url}/Entries")
                    
                    if log_entries_data:
                        for entry in log_entries_data.get("Members", []):
                            severity_map = {
                                "OK": Severity.INFO,
                                "Warning": Severity.WARNING,
                                "Critical": Severity.CRITICAL,
                                "Error": Severity.ERROR
                            }
                            
                            logs.append(LogEntry(
                                timestamp=datetime.fromisoformat(entry.get("Created", "").replace("Z", "+00:00")),
                                severity=severity_map.get(entry.get("Severity"), Severity.INFO),
                                message=entry.get("Message", ""),
                                source=entry.get("MessageId"),
                                component=ComponentType.SYSTEM,
                                event_id=entry.get("Id"),
                                raw_data=entry
                            ))
            
        except Exception as e:
            logger.error(f"Failed to get logs: {str(e)}")
        
        return logs
    
    async def get_health_status(self) -> Optional[HealthStatus]:
        """Get overall system health status"""
        try:
            if not self.system_id:
                return None
            
            system_data = await self._get(f"Systems/{self.system_id}")
            if not system_data:
                return None
            
            overall_status = self._map_status(system_data.get("Status", {}))
            
            # Get component statuses
            components = {}
            
            # Get power health (16G+ Chassis path, then legacy)
            power_ok = False
            if self.chassis_id:
                ps_data = await self._get(f"Chassis/{self.chassis_id}/PowerSubsystem")
                if ps_data:
                    components[ComponentType.POWER] = self._map_status(ps_data.get("Status", {}))
                    power_ok = True
            if not power_ok:
                power_data = await self._get(f"Systems/{self.system_id}/Power")
                if power_data:
                    components[ComponentType.POWER] = self._map_status(power_data.get("Status", {}))
            
            # Get thermal health (16G+ Chassis path, then legacy)
            thermal_ok = False
            if self.chassis_id:
                ts_data = await self._get(f"Chassis/{self.chassis_id}/ThermalSubsystem")
                if ts_data:
                    components[ComponentType.THERMAL] = self._map_status(ts_data.get("Status", {}))
                    thermal_ok = True
            if not thermal_ok:
                thermal_data = await self._get(f"Systems/{self.system_id}/Thermal")
                if thermal_data:
                    components[ComponentType.THERMAL] = self._map_status(thermal_data.get("Status", {}))
            
            # Get memory health
            memory_data = await self._get(f"Systems/{self.system_id}/Memory")
            if memory_data:
                components[ComponentType.MEMORY] = self._map_status(memory_data.get("Status", {})) if memory_data.get("Status") else ServerStatus.ONLINE
            
            # Get storage health
            storage_data = await self._get(f"Systems/{self.system_id}/Storage")
            if storage_data:
                components[ComponentType.STORAGE] = self._map_status(storage_data.get("Status", {})) if storage_data.get("Status") else ServerStatus.ONLINE
            
            # Get recent logs for issues
            recent_logs = await self.get_logs()
            critical_issues = [log for log in recent_logs if log.severity == Severity.CRITICAL]
            warnings = [log for log in recent_logs if log.severity == Severity.WARNING]
            
            return HealthStatus(
                overall_status=overall_status,
                components=components,
                critical_issues=critical_issues,
                warnings=warnings
            )
            
        except Exception as e:
            logger.error(f"Failed to get health status: {str(e)}")
            return None
    
    async def power_action(self, action: str) -> bool:
        """Execute power action (On, Off, GracefulRestart, ForceRestart, ForceOff)"""
        try:
            if not self.system_id:
                return False
            
            reset_data = {"ResetType": action}
            result = await self._post(f"Systems/{self.system_id}/Actions/ComputerSystem.Reset", reset_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to execute power action {action}: {str(e)}")
            return False
    
    async def set_boot_order(self, boot_devices: List[str]) -> bool:
        """Set boot order"""
        try:
            if not self.system_id:
                return False
            
            boot_data = {"Boot": {"BootOrder": boot_devices}}
            return await self._patch(f"Systems/{self.system_id}", boot_data)
            
        except Exception as e:
            logger.error(f"Failed to set boot order: {str(e)}")
            return False
    
    def _map_status(self, status_data: Dict) -> ServerStatus:
        """Map Redfish status to ServerStatus enum"""
        health = status_data.get("Health", "Unknown")
        state = status_data.get("State", "Unknown")
        
        if health == "OK" and state == "Enabled":
            return ServerStatus.ONLINE
        elif health == "Warning":
            return ServerStatus.WARNING
        elif health in ["Critical", "Failed"]:
            return ServerStatus.CRITICAL
        elif state == "Disabled":
            return ServerStatus.OFFLINE
        else:
            return ServerStatus.UNKNOWN
    
    def _get_status_string(self, status_data: Dict) -> str:
        """Get status string from status data"""
        if not status_data:
            return "Unknown"
        health = status_data.get("Health")
        state = status_data.get("State")
        if health and state:
            return f"{health} ({state})"
        elif health:
            return health
        elif state:
            return state
        return "Unknown"

    # ─── BIOS Attributes ────────────────────────────────────────
    async def get_bios_attributes(self) -> Dict[str, Any]:
        """Get all BIOS configuration attributes"""
        try:
            if not self.system_id:
                return {}
            bios_data = await self._get(f"Systems/{self.system_id}/Bios")
            if not bios_data:
                return {}
            attrs = bios_data.get("Attributes", {})
            # Also grab registry info if available
            result = {
                "attributes": attrs,
                "bios_version": bios_data.get("Id", ""),
                "attribute_registry": bios_data.get("AttributeRegistry", ""),
                "description": bios_data.get("Description", ""),
            }
            return result
        except Exception as e:
            logger.error(f"Failed to get BIOS attributes: {str(e)}")
            return {}

    async def set_bios_attributes(self, attributes: Dict[str, Any]) -> bool:
        """Set BIOS attributes (requires reboot to apply)"""
        try:
            if not self.system_id:
                return False
            # PATCH to Bios/Settings for pending changes
            settings_data = {"Attributes": attributes}
            return await self._patch(f"Systems/{self.system_id}/Bios/Settings", settings_data)
        except Exception as e:
            logger.error(f"Failed to set BIOS attributes: {str(e)}")
            return False

    # ─── Firmware Inventory ─────────────────────────────────────
    async def get_firmware_inventory(self) -> List[Dict[str, Any]]:
        """Get all installed firmware versions from UpdateService.
        Uses $expand to fetch all members in a single request (2x faster)."""
        firmware_list = []
        try:
            # Try $expand first (supported on iDRAC9 16G+) — single request for all members
            fw_inv = await self._get("UpdateService/FirmwareInventory", 
                                      params={"$expand": "*($levels=1)"}, use_cache=True)
            if fw_inv and fw_inv.get("Members"):
                members = fw_inv["Members"]
                # Check if members are already expanded (have Version field)
                if members and "Version" in members[0]:
                    for fw_data in members:
                        firmware_list.append({
                            "id": fw_data.get("Id", ""),
                            "name": fw_data.get("Name", ""),
                            "version": fw_data.get("Version", ""),
                            "updateable": fw_data.get("Updateable", False),
                            "status": self._get_status_string(fw_data.get("Status", {})),
                            "release_date": fw_data.get("ReleaseDate", ""),
                            "manufacturer": fw_data.get("Manufacturer", ""),
                            "description": fw_data.get("Description", ""),
                            "component_id": fw_data.get("SoftwareId", ""),
                        })
                    return firmware_list

            # Fallback: fetch each member individually (slower but compatible)
            fw_inv = await self._get("UpdateService/FirmwareInventory", use_cache=True)
            if not fw_inv:
                return firmware_list
            for member in fw_inv.get("Members", []):
                fw_url = member["@odata.id"].replace("/redfish/v1/", "")
                fw_data = await self._get(fw_url)
                if fw_data:
                    firmware_list.append({
                        "id": fw_data.get("Id", ""),
                        "name": fw_data.get("Name", ""),
                        "version": fw_data.get("Version", ""),
                        "updateable": fw_data.get("Updateable", False),
                        "status": self._get_status_string(fw_data.get("Status", {})),
                        "release_date": fw_data.get("ReleaseDate", ""),
                        "manufacturer": fw_data.get("Manufacturer", ""),
                        "description": fw_data.get("Description", ""),
                        "component_id": fw_data.get("SoftwareId", ""),
                    })
        except Exception as e:
            logger.error(f"Failed to get firmware inventory: {str(e)}")
        return firmware_list

    # ─── Lifecycle Logs ─────────────────────────────────────────
    async def get_lifecycle_logs(self, max_entries: int = 500) -> List[Dict[str, Any]]:
        """Get Lifecycle Controller logs"""
        lc_logs = []
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return lc_logs
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            log_services = await self._get(f"{manager_url}/LogServices")
            if not log_services:
                return lc_logs
            for svc in log_services.get("Members", []):
                svc_url = svc["@odata.id"].replace("/redfish/v1/", "")
                svc_data = await self._get(svc_url)
                svc_name = (svc_data or {}).get("Name", "") if svc_data else ""
                entries_data = await self._get(f"{svc_url}/Entries")
                if entries_data:
                    for entry in entries_data.get("Members", [])[:max_entries]:
                        lc_logs.append({
                            "id": entry.get("Id", ""),
                            "created": entry.get("Created", ""),
                            "severity": entry.get("Severity", "OK"),
                            "message": entry.get("Message", ""),
                            "message_id": entry.get("MessageId", ""),
                            "entry_type": entry.get("EntryType", ""),
                            "category": svc_name,
                            "oem": entry.get("Oem", {}),
                        })
        except Exception as e:
            logger.error(f"Failed to get lifecycle logs: {str(e)}")
        return lc_logs

    # ─── TSR (Tech Support Report) Export ────────────────────────
    async def export_tsr(self, share_type: str = "Local") -> Dict[str, Any]:
        """Trigger a Tech Support Report (TSR) collection via Dell OEM Redfish.
        
        Returns dict with: success, job_id, job_uri, message/error.
        The job_id can be used with get_job_status() to poll for completion.
        """
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")

            def _extract_job(result):
                """Extract job_id and location from POST result."""
                if not result or not isinstance(result, dict):
                    return None, None
                job_id = result.get("_job_id") or result.get("Id") or result.get("JobID")
                location = result.get("_location", "")
                return job_id, location

            # Attempt 1: SupportAssist collection (preferred on 15G/16G iDRAC9)
            sa_result = await self._post(
                f"{manager_url}/Oem/Dell/DellLCService/Actions/DellLCService.SupportAssistCollection",
                {"ShareType": share_type, "DataSelectorArrayIn": ["HWData", "OSAppData", "TTYLogs"]}
            )
            if sa_result is not None:
                job_id, location = _extract_job(sa_result)
                logger.info(f"TSR SupportAssist collection initiated — job_id={job_id}, location={location}")
                return {
                    "success": True, "job_id": job_id, "job_uri": location,
                    "method": "SupportAssistCollection",
                    "message": f"SupportAssist TSR collection initiated{f' (Job: {job_id})' if job_id else ''}"
                }

            # Attempt 2: ExportTechSupportReport with RebootJobType (16G)
            tsr_payload = {"ShareType": share_type}
            result = await self._post(
                f"{manager_url}/Oem/Dell/DellLCService/Actions/DellLCService.ExportTechSupportReport",
                tsr_payload
            )
            if result is not None:
                job_id, location = _extract_job(result)
                logger.info(f"TSR ExportTechSupportReport initiated — job_id={job_id}, location={location}")
                return {
                    "success": True, "job_id": job_id, "job_uri": location,
                    "method": "ExportTechSupportReport",
                    "message": f"TSR export initiated{f' (Job: {job_id})' if job_id else ''}"
                }

            return {"success": False, "error": "TSR export action not available on this iDRAC. SupportAssist and ExportTechSupportReport both failed."}
        except Exception as e:
            logger.error(f"Failed to export TSR: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Poll a specific iDRAC job by ID and return its current status.
        
        For SupportAssist TSR jobs, iDRAC creates paired jobs:
        - "SA Export Local" (returned in Location header) — stays New/Scheduled until collection finishes
        - "SupportAssist Collection" (companion) — does the actual work and reports progress
        This method finds the companion job and reports its progress when the primary is queued.
        """
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")

            # Try Dell OEM Jobs path first
            job = await self._get(f"{manager_url}/Oem/Dell/Jobs/{job_id}")
            if not job:
                job = await self._get(f"JobService/Jobs/{job_id}")
            if not job:
                return {"success": False, "error": f"Job {job_id} not found"}

            state = job.get("JobState", job.get("TaskState", "Unknown"))
            pct = job.get("PercentComplete", 0)
            msg = job.get("Message", "")
            name = job.get("Name", "")
            finished_states = ("completed", "completedwitherrors", "failed")

            # For SA Export jobs stuck at New/Scheduled, look for companion SupportAssist Collection job
            companion = None
            if name == "SA Export Local" and state.lower() in ("new", "scheduled"):
                try:
                    jobs_data = await self._get(f"{manager_url}/Oem/Dell/Jobs?$expand=*($levels=1)")
                    members = jobs_data.get("Members", []) if jobs_data else []
                    # Find the most recent running/new SupportAssist Collection job
                    sa_jobs = [j for j in members
                               if j.get("Name") == "SupportAssist Collection"
                               and j.get("JobState", "").lower() in ("running", "new", "scheduled")]
                    if sa_jobs:
                        # Pick the one closest in start time to our job
                        companion = sa_jobs[-1]  # most recent
                except Exception as e:
                    logger.debug(f"Could not fetch companion job: {e}")

            if companion:
                comp_state = companion.get("JobState", "Unknown")
                comp_pct = companion.get("PercentComplete", 0)
                comp_msg = companion.get("Message", "")
                return {
                    "success": True,
                    "job_id": job_id,
                    "name": name,
                    "state": f"Collecting ({comp_state})",
                    "percent_complete": comp_pct,
                    "message": comp_msg or f"SupportAssist collection in progress",
                    "start_time": job.get("StartTime", ""),
                    "end_time": job.get("EndTime", ""),
                    "completed": False,
                    "failed": False,
                    "companion_job": companion.get("Id", ""),
                }

            return {
                "success": True,
                "job_id": job_id,
                "name": name,
                "state": state,
                "percent_complete": pct,
                "message": msg,
                "start_time": job.get("StartTime", ""),
                "end_time": job.get("EndTime", ""),
                "completed": state.lower() in finished_states,
                "failed": state.lower() in ("failed", "completedwitherrors"),
            }
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {str(e)}")
            return {"success": False, "error": str(e)}

    # ─── iDRAC Reset ────────────────────────────────────────────
    async def reset_idrac(self) -> bool:
        """Reset/reboot the iDRAC"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return False
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            result = await self._post(f"{manager_url}/Actions/Manager.Reset", {"ResetType": "GracefulRestart"})
            return result is not None
        except Exception as e:
            logger.error(f"Failed to reset iDRAC: {str(e)}")
            return False

    # ─── Jobs ───────────────────────────────────────────────────
    async def get_jobs(self) -> List[Dict[str, Any]]:
        """Get iDRAC job queue"""
        jobs = []
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return jobs
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            jobs_data = await self._get(f"{manager_url}/Oem/Dell/Jobs")
            if not jobs_data:
                # Try standard Redfish job service
                jobs_data = await self._get("JobService/Jobs")
            if jobs_data:
                for member in jobs_data.get("Members", []):
                    job_url = member["@odata.id"].replace("/redfish/v1/", "")
                    job = await self._get(job_url)
                    if job:
                        jobs.append({
                            "id": job.get("Id", ""),
                            "name": job.get("Name", ""),
                            "job_type": job.get("JobType", ""),
                            "job_state": job.get("JobState", ""),
                            "message": job.get("Message", ""),
                            "percent_complete": job.get("PercentComplete"),
                            "start_time": job.get("StartTime", ""),
                            "end_time": job.get("EndTime", ""),
                        })
        except Exception as e:
            logger.error(f"Failed to get jobs: {str(e)}")
        return jobs

    # ─── Virtual Console info (POST codes) ──────────────────────
    async def get_post_codes(self) -> Dict[str, Any]:
        """Get last POST code / boot progress from the system"""
        try:
            if not self.system_id:
                return {}
            system_data = await self._get(f"Systems/{self.system_id}")
            if not system_data:
                return {}
            boot_progress = system_data.get("BootProgress", {})
            oem = system_data.get("Oem", {}).get("Dell", {})
            return {
                "last_state": boot_progress.get("LastState", ""),
                "oem_last_state": boot_progress.get("OemLastState", ""),
                "post_code": oem.get("LastPostCode", ""),
                "system_generation": oem.get("SystemGeneration", ""),
                "power_state": system_data.get("PowerState", ""),
                "boot_source_override": system_data.get("Boot", {}).get("BootSourceOverrideTarget", ""),
                "boot_source_override_enabled": system_data.get("Boot", {}).get("BootSourceOverrideEnabled", ""),
            }
        except Exception as e:
            logger.error(f"Failed to get POST codes: {str(e)}")
            return {}

    # ─── Remote Diagnostics (ePSA / Dell Diagnostics) ──────────
    async def run_remote_diagnostics(self, diag_type: str = "Express") -> Dict[str, Any]:
        """Trigger Dell remote diagnostics via OEM Redfish action"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")

            # 16G iDRAC requires RebootJobType for diagnostics
            diag_payloads = [
                {"RunMode": diag_type, "RebootJobType": "GracefulRebootWithForcedShutdown"},
                {"RunMode": diag_type},
            ]
            for payload in diag_payloads:
                result = await self._post(
                    f"{manager_url}/Oem/Dell/DellLCService/Actions/DellLCService.RunePSADiagnostics",
                    payload
                )
                if result is not None:
                    job_id = result.get("Id") if isinstance(result, dict) else None
                    return {"success": True, "message": f"ePSA {diag_type} diagnostics initiated", "job_id": job_id}

            return {"success": False, "error": "Remote diagnostics not available — the server may need to be in a powered-on OS state, or this iDRAC firmware does not support remote ePSA."}
        except Exception as e:
            logger.error(f"Failed to run remote diagnostics: {str(e)}")
            return {"success": False, "error": str(e)}

    # ─── Virtual AC Power Cycle (flea power drain) ───────────────
    async def virtual_ac_cycle(self) -> Dict[str, Any]:
        """Perform a virtual AC power cycle (drain flea power) via Dell OEM"""
        try:
            if not self.system_id:
                return {"success": False, "error": "No system ID"}
            # Dell OEM action for virtual AC cycle
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            result = await self._post(
                f"{manager_url}/Oem/Dell/DellLCService/Actions/DellLCService.VirtualACPowerCycle",
                {}
            )
            if result is not None:
                return {"success": True, "message": "Virtual AC power cycle initiated — server will drain flea power and restart"}
            return {"success": False, "error": "Virtual AC cycle not supported on this iDRAC"}
        except Exception as e:
            logger.error(f"Failed to perform virtual AC cycle: {str(e)}")
            return {"success": False, "error": str(e)}

    # ─── SupportAssist Status ────────────────────────────────────
    async def get_support_assist_status(self) -> Dict[str, Any]:
        """Check SupportAssist registration and status"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"registered": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            sa_data = await self._get(f"{manager_url}/Oem/Dell/DellSupportAssist")
            if not sa_data:
                return {"registered": False, "available": False, "message": "SupportAssist not available via Redfish"}
            return {
                "registered": sa_data.get("SupportAssistRegistered", False),
                "available": True,
                "auto_collection": sa_data.get("SupportAssistAutoCollect", ""),
                "last_collection": sa_data.get("SupportAssistLastCollection", ""),
                "proxy_support": sa_data.get("ProxySupport", ""),
            }
        except Exception as e:
            logger.error(f"Failed to get SupportAssist status: {str(e)}")
            return {"registered": False, "error": str(e)}

    # ─── iDRAC Availability Check (ping test) ────────────────────
    async def check_idrac_availability(self) -> Dict[str, Any]:
        """Quick health check — is iDRAC responding at all?"""
        result = {
            "reachable": False,
            "redfish_available": False,
            "system_power_state": None,
            "idrac_firmware": None,
        }
        try:
            root_url = f"{self.base_url}/redfish/v1"
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10),
                auth=aiohttp.BasicAuth(self.username, self.password)
            ) as session:
                async with session.get(root_url) as response:
                    result["reachable"] = True
                    if response.status == 200:
                        result["redfish_available"] = True
                        data = await response.json()
                        result["redfish_version"] = data.get("RedfishVersion", "")
                # Quick system check
                sys_url = f"{self.base_url}/redfish/v1/Systems"
                async with session.get(sys_url) as response:
                    if response.status == 200:
                        sys_data = await response.json()
                        if sys_data.get("Members"):
                            sys_id = sys_data["Members"][0]["@odata.id"]
                            async with session.get(f"{self.base_url}{sys_id}") as sys_resp:
                                if sys_resp.status == 200:
                                    sd = await sys_resp.json()
                                    result["system_power_state"] = sd.get("PowerState")
                                    result["model"] = sd.get("Model")
                                    result["service_tag"] = sd.get("SKU") or sd.get("SerialNumber")
                # Manager check
                mgr_url = f"{self.base_url}/redfish/v1/Managers"
                async with session.get(mgr_url) as response:
                    if response.status == 200:
                        mgr_data = await response.json()
                        if mgr_data.get("Members"):
                            mgr_id = mgr_data["Members"][0]["@odata.id"]
                            async with session.get(f"{self.base_url}{mgr_id}") as mgr_resp:
                                if mgr_resp.status == 200:
                                    md = await mgr_resp.json()
                                    result["idrac_firmware"] = md.get("FirmwareVersion")
        except aiohttp.ClientConnectorError:
            result["reachable"] = False
        except asyncio.TimeoutError:
            result["reachable"] = False
            result["timeout"] = True
        except Exception as e:
            result["error"] = str(e)
        return result

    # ─── Boot Order ────────────────────────────────────────────
    async def get_boot_order(self) -> Dict[str, Any]:
        """Get current boot order and one-time boot settings"""
        try:
            if not self.system_id:
                return {}
            system_data = await self._get(f"Systems/{self.system_id}")
            if not system_data:
                return {}
            boot = system_data.get("Boot", {})
            return {
                "boot_order": boot.get("BootOrder", []),
                "boot_source_override_target": boot.get("BootSourceOverrideTarget", ""),
                "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled", ""),
                "boot_source_override_mode": boot.get("BootSourceOverrideMode", ""),
                "allowed_boot_sources": boot.get("BootSourceOverrideTarget@Redfish.AllowableValues", []),
                "uefi_target": boot.get("UefiTargetBootSourceOverride", ""),
            }
        except Exception as e:
            logger.error(f"Failed to get boot order: {str(e)}")
            return {}

    async def set_next_boot_device(self, device: str) -> Dict[str, Any]:
        """Set one-time boot device override"""
        try:
            if not self.system_id:
                return {"success": False, "error": "No system ID"}
            success = await self._patch(f"Systems/{self.system_id}", {
                "Boot": {
                    "BootSourceOverrideTarget": device,
                    "BootSourceOverrideEnabled": "Once"
                }
            })
            return {"success": success, "device": device, "message": f"Next boot override set to {device} (one-time)"}
        except Exception as e:
            logger.error(f"Failed to set next boot: {str(e)}")
            return {"success": False, "error": str(e)}

    # ─── Clear System Event Log ──────────────────────────────────
    async def clear_sel(self) -> Dict[str, Any]:
        """Clear the System Event Log"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            result = await self._post(
                f"{manager_url}/LogServices/Sel/Actions/LogService.ClearLog", {}
            )
            return {"success": True, "message": "System Event Log cleared"}
        except Exception as e:
            logger.error(f"Failed to clear SEL: {str(e)}")
            return {"success": False, "error": str(e)}

    # ─── Lifecycle Controller Status ─────────────────────────────
    async def get_lifecycle_status(self) -> Dict[str, Any]:
        """Get Lifecycle Controller status and remote services readiness"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"status": "unknown"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            # Try Dell OEM LC attributes
            lc_attr = await self._get(f"{manager_url}/Oem/Dell/DellLCService")
            # Also get LC attributes for readiness
            mgr = await self._get(manager_url)
            lc_status = await self._get(f"{manager_url}/Oem/Dell/DellAttributes/LifecycleController.Embedded.1")
            result = {
                "manager_status": (mgr or {}).get("Status", {}).get("Health", "Unknown"),
                "manager_state": (mgr or {}).get("Status", {}).get("State", "Unknown"),
                "firmware_version": (mgr or {}).get("FirmwareVersion", ""),
                "lc_service_available": lc_attr is not None,
            }
            if lc_status and "Attributes" in lc_status:
                attrs = lc_status["Attributes"]
                result["lc_attributes"] = {
                    k: v for k, v in attrs.items()
                    if any(kw in k.lower() for kw in ("lifecycle", "remote", "collect", "auto"))
                }
            return result
        except Exception as e:
            logger.error(f"Failed to get LC status: {str(e)}")
            return {"status": "error", "error": str(e)}

    # ─── iDRAC Network Configuration ─────────────────────────────
    async def get_idrac_network_config(self) -> Dict[str, Any]:
        """Get detailed iDRAC network configuration"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            # Get Ethernet interfaces
            eth_coll = await self._get(f"{manager_url}/EthernetInterfaces")
            interfaces = []
            if eth_coll and eth_coll.get("Members"):
                for member in eth_coll["Members"]:
                    eth_url = member["@odata.id"].replace("/redfish/v1/", "")
                    eth = await self._get(eth_url)
                    if eth:
                        ipv4 = eth.get("IPv4Addresses", [{}])
                        ipv6 = eth.get("IPv6Addresses", [{}])
                        interfaces.append({
                            "id": eth.get("Id", ""),
                            "name": eth.get("Name", ""),
                            "mac_address": eth.get("MACAddress", ""),
                            "speed_mbps": eth.get("SpeedMbps"),
                            "status": eth.get("Status", {}).get("Health", ""),
                            "ipv4_address": ipv4[0].get("Address", "") if ipv4 else "",
                            "ipv4_subnet": ipv4[0].get("SubnetMask", "") if ipv4 else "",
                            "ipv4_gateway": ipv4[0].get("Gateway", "") if ipv4 else "",
                            "ipv4_origin": ipv4[0].get("AddressOrigin", "") if ipv4 else "",
                            "ipv6_address": ipv6[0].get("Address", "") if ipv6 else "",
                            "vlan_enabled": eth.get("VLAN", {}).get("VLANEnable", False),
                            "vlan_id": eth.get("VLAN", {}).get("VLANId"),
                            "host_name": eth.get("HostName", ""),
                            "fqdn": eth.get("FQDN", ""),
                            "dns_servers": eth.get("NameServers", []),
                        })
            return {"interfaces": interfaces}
        except Exception as e:
            logger.error(f"Failed to get iDRAC network config: {str(e)}")
            return {"error": str(e)}

    # ─── iDRAC User Accounts ─────────────────────────────────────
    async def get_idrac_users(self) -> List[Dict[str, Any]]:
        """Get iDRAC user accounts. Uses $expand for speed."""
        users = []
        try:
            acct_svc = await self._get("AccountService")
            if not acct_svc:
                return users
            acct_url = acct_svc.get("Accounts", {}).get("@odata.id", "").replace("/redfish/v1/", "")
            if not acct_url:
                return users
            
            # Try $expand first (single request)
            acct_coll = await self._get(acct_url, params={"$expand": "*($levels=1)"})
            if acct_coll and acct_coll.get("Members"):
                for acct in acct_coll["Members"]:
                    if acct.get("UserName"):
                        users.append({
                            "id": acct.get("Id", ""),
                            "username": acct.get("UserName", ""),
                            "role": acct.get("RoleId", ""),
                            "enabled": acct.get("Enabled", False),
                            "locked": acct.get("Locked", False),
                        })
                if users:
                    return users
            
            # Fallback: individual fetches
            acct_coll = await self._get(acct_url)
            if not acct_coll or not acct_coll.get("Members"):
                return users
            for member in acct_coll["Members"]:
                member_url = member["@odata.id"].replace("/redfish/v1/", "")
                acct = await self._get(member_url)
                if acct and acct.get("UserName"):
                    users.append({
                        "id": acct.get("Id", ""),
                        "username": acct.get("UserName", ""),
                        "role": acct.get("RoleId", ""),
                        "enabled": acct.get("Enabled", False),
                        "locked": acct.get("Locked", False),
                    })
        except Exception as e:
            logger.error(f"Failed to get iDRAC users: {str(e)}")
        return users

    # ─── SSL Certificate Info ────────────────────────────────────
    async def get_ssl_certificate_info(self) -> Dict[str, Any]:
        """Get iDRAC SSL certificate details"""
        try:
            cert_svc = await self._get("CertificateService")
            if not cert_svc:
                return {"available": False}
            certs_url = cert_svc.get("CertificateLocations", {}).get("@odata.id", "").replace("/redfish/v1/", "")
            if not certs_url:
                return {"available": False}
            certs = await self._get(certs_url)
            cert_list = []
            if certs and certs.get("Links", {}).get("Certificates"):
                for cert_ref in certs["Links"]["Certificates"][:5]:
                    cert_url = cert_ref["@odata.id"].replace("/redfish/v1/", "")
                    cert_data = await self._get(cert_url)
                    if cert_data:
                        cert_list.append({
                            "id": cert_data.get("Id", ""),
                            "subject": cert_data.get("Subject", {}),
                            "issuer": cert_data.get("Issuer", {}),
                            "valid_not_before": cert_data.get("ValidNotBefore", ""),
                            "valid_not_after": cert_data.get("ValidNotAfter", ""),
                            "key_usage": cert_data.get("KeyUsage", []),
                        })
            return {"available": True, "certificates": cert_list}
        except Exception as e:
            logger.error(f"Failed to get SSL cert info: {str(e)}")
            return {"available": False, "error": str(e)}

    # ─── NMI (Non-Maskable Interrupt) ────────────────────────────
    async def send_nmi(self) -> Dict[str, Any]:
        """Send NMI diagnostic interrupt to the host"""
        try:
            if not self.system_id:
                return {"success": False, "error": "No system ID"}
            result = await self._post(
                f"Systems/{self.system_id}/Actions/ComputerSystem.Reset",
                {"ResetType": "Nmi"}
            )
            if result is not None:
                return {"success": True, "message": "NMI sent to host — this may trigger a crash dump"}
            return {"success": False, "error": "NMI action not supported"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Export Server Configuration Profile ──────────────────────
    async def export_scp(self) -> Dict[str, Any]:
        """Export Server Configuration Profile (SCP) via Dell OEM"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            result = await self._post(
                f"{manager_url}/Actions/Oem/EID_674_Manager.ExportSystemConfiguration",
                {"ExportFormat": "JSON", "ShareParameters": {"Target": "ALL"}}
            )
            if result is not None:
                return {"success": True, "message": "SCP export initiated", "data": result}
            return {"success": False, "error": "SCP export not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Delete all pending jobs ─────────────────────────────────
    async def delete_all_jobs(self) -> Dict[str, Any]:
        """Clear the iDRAC job queue"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {"success": False, "error": "No manager found"}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            result = await self._post(
                f"{manager_url}/Oem/Dell/DellJobService/Actions/DellJobService.DeleteJobQueue",
                {"JobID": "JID_CLEARALL"}
            )
            if result is not None:
                return {"success": True, "message": "All pending jobs cleared"}
            return {"success": False, "error": "Job queue clear not supported"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── iDRAC / Manager info ───────────────────────────────────
    async def get_idrac_info(self) -> Dict[str, Any]:
        """Get detailed iDRAC/manager information"""
        try:
            manager_data = await self._get("Managers")
            if not manager_data or not manager_data.get("Members"):
                return {}
            manager_url = manager_data["Members"][0]["@odata.id"].replace("/redfish/v1/", "")
            mgr = await self._get(manager_url)
            if not mgr:
                return {}
            # Also get network protocol info
            net_proto = await self._get(f"{manager_url}/NetworkProtocol")
            return {
                "id": mgr.get("Id", ""),
                "firmware_version": mgr.get("FirmwareVersion", ""),
                "model": mgr.get("Model", ""),
                "status": self._get_status_string(mgr.get("Status", {})),
                "date_time": mgr.get("DateTime", ""),
                "uuid": mgr.get("UUID", ""),
                "network_protocol": {
                    "hostname": (net_proto or {}).get("HostName", ""),
                    "https_enabled": (net_proto or {}).get("HTTPS", {}).get("ProtocolEnabled", False),
                    "ssh_enabled": (net_proto or {}).get("SSH", {}).get("ProtocolEnabled", False),
                    "ipmi_enabled": (net_proto or {}).get("IPMI", {}).get("ProtocolEnabled", False),
                    "snmp_enabled": (net_proto or {}).get("SNMP", {}).get("ProtocolEnabled", False),
                } if net_proto else {},
            }
        except Exception as e:
            logger.error(f"Failed to get iDRAC info: {str(e)}")
            return {}
