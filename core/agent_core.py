"""
Core AI Agent for Dell Server Management
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from core.config import AgentConfig
from integrations.redfish_client import RedfishClient
from integrations.racadm_client import RacadmClient
from models.server_models import (
    ActionLevel, ServerInfo, SystemInfo, HealthStatus, LogEntry,
    TroubleshootingRequest, TroubleshootingResult, TroubleshootingRecommendation,
    AgentAction, ServerSession, ComponentType, Severity, ServerStatus
)
from ai.troubleshooting_engine import TroubleshootingEngine
from ai.log_analyzer import LogAnalyzer

logger = logging.getLogger(__name__)

class DellAIAgent:
    """Main AI Agent for Dell Server Management"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.redfish_client: Optional[RedfishClient] = None
        self.racadm_client: Optional[RacadmClient] = None
        self.current_session: Optional[ServerSession] = None
        self.troubleshooting_engine = TroubleshootingEngine(config)
        self.log_analyzer = LogAnalyzer(config)
        self.action_history: List[AgentAction] = []
        
    async def connect_to_server(self, host: str, username: str, password: str, port: int = 443) -> bool:
        """Connect to a Dell server using available methods"""
        try:
            # Close any existing connections first
            if self.redfish_client:
                await self.redfish_client.disconnect()
                self.redfish_client = None
            self.racadm_client = None

            # ── Demo / simulation mode ───────────────────────────
            if self.config.demo_mode:
                from integrations.simulated_redfish import SimulatedRedfishClient
                from integrations.simulated_racadm import SimulatedRacadmClient
                self.redfish_client = SimulatedRedfishClient(
                    host=host, username=username, password=password, port=port
                )
                await self.redfish_client.connect()
                self.racadm_client = SimulatedRacadmClient(
                    host=host, username=username, password=password
                )
                await self.racadm_client.test_connection()
                self.current_session = ServerSession(
                    server_host=host,
                    connection_method="redfish",
                    is_active=True
                )
                logger.info(f"[DEMO] Connected to simulated server {host}")
                return True

            # Try Redfish first (preferred)
            self.redfish_client = RedfishClient(
                host=host, username=username, password=password, 
                port=port, verify_ssl=self.config.verify_ssl
            )
            
            if await self.redfish_client.connect():
                self.current_session = ServerSession(
                    server_host=host,
                    connection_method="redfish",
                    is_active=True
                )
                logger.info(f"Connected to {host} via Redfish API")
                
                # Also try RACADM if available
                try:
                    self.racadm_client = RacadmClient(host, username, password, self.config.racadm_timeout)
                    if await self.racadm_client.test_connection():
                        logger.info(f"RACADM also available for {host}")
                    else:
                        self.racadm_client = None
                except Exception as e:
                    logger.warning(f"RACADM not available: {str(e)}")
                    self.racadm_client = None
                
                return True
            else:
                # Fallback to RACADM only
                self.redfish_client = None
                self.racadm_client = RacadmClient(host, username, password, self.config.racadm_timeout)
                
                if await self.racadm_client.test_connection():
                    self.current_session = ServerSession(
                        server_host=host,
                        connection_method="racadm",
                        is_active=True
                    )
                    logger.info(f"Connected to {host} via RACADM")
                    return True
                else:
                    logger.error(f"Failed to connect to {host} via any method")
                    return False
                    
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from current server"""
        try:
            if self.redfish_client:
                await self.redfish_client.disconnect()
                self.redfish_client = None
            
            self.racadm_client = None
            self.current_session = None
            logger.info("Disconnected from server")
            
        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")
    
    async def execute_action(self, action_level: ActionLevel, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an agent action based on the specified action level"""
        action = AgentAction(
            action_type=command,
            action_level=action_level,
            parameters=parameters
        )
        
        try:
            # Check if action is allowed based on security level
            if not self.config.is_action_allowed(action_level):
                raise PermissionError(f"Action level '{action_level}' not allowed with current security settings")
            
            # Check if we're connected to a server
            if not self.current_session:
                raise RuntimeError("Not connected to any server")
            
            result = await self._execute_command(action_level, command, parameters)
            action.result = result
            action.status = "completed"
            
            # Log the action
            self.action_history.append(action)
            logger.info(f"Executed action: {command} with level: {action_level}")
            
            return result
            
        except Exception as e:
            action.error_message = str(e)
            action.status = "failed"
            self.action_history.append(action)
            logger.error(f"Action failed: {command} - {str(e)}")
            raise
    
    async def _execute_command(self, action_level: ActionLevel, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a specific command based on action level"""
        
        # Read-only actions (always allowed)
        if action_level == ActionLevel.READ_ONLY:
            return await self._execute_read_only_command(command, parameters)
        
        # Diagnostic actions (modate risk)
        elif action_level == ActionLevel.DIAGNOSTIC:
            return await self._execute_diagnostic_command(command, parameters)
        
        # Full control actions (high risk)
        elif action_level == ActionLevel.FULL_CONTROL:
            return await self._execute_full_control_command(command, parameters)
        
        else:
            raise ValueError(f"Unknown action level: {action_level}")
    
    async def _execute_read_only_command(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute read-only commands"""
        
        if command == "get_server_info":
            if self.redfish_client:
                info = await self.redfish_client.get_server_info()
                si = info.model_dump() if info else {}
                # Enrich with CPU, memory, hostname, power from Redfish Systems endpoint
                try:
                    system_data = await self.redfish_client._get(f"Systems/{self.redfish_client.system_id}")
                    if system_data and isinstance(system_data, dict):
                        si["power_state"] = system_data.get("PowerState", "Unknown")
                        si["hostname"] = system_data.get("HostName", "")
                        si["manufacturer"] = system_data.get("Manufacturer", "Dell Inc.")
                        mem_summary = system_data.get("MemorySummary", {})
                        si["total_memory_gb"] = mem_summary.get("TotalSystemMemoryGiB", 0)
                        proc_summary = system_data.get("ProcessorSummary", {})
                        si["cpu_model"] = proc_summary.get("Model", "Unknown")
                        si["cpu_count"] = proc_summary.get("Count", 0)
                        si["bios_version"] = system_data.get("BiosVersion", si.get("firmware_version", "?"))
                except Exception as e:
                    logger.warning(f"Could not enrich server info: {e}")
                return {"server_info": si}
            else:
                info = await self.racadm_client.get_server_info()
            return {"server_info": info.model_dump() if info else None}
        
        elif command == "get_system_info":
            if self.redfish_client:
                info = await self.redfish_client.get_system_info()
            else:
                info = await self.racadm_client.get_system_info()
            return {"system_info": info.model_dump() if info else None}
        
        elif command == "get_processors":
            if self.redfish_client:
                processors = await self.redfish_client.get_processors()
                return {"processors": [p.model_dump() for p in processors]}
            elif self.racadm_client:
                processors = await self.racadm_client.get_processors_structured()
                return {"processors": [p.model_dump() for p in processors]}
            return {"processors": []}
        
        elif command == "get_memory":
            if self.redfish_client:
                memory = await self.redfish_client.get_memory()
                return {"memory": [m.model_dump() for m in memory]}
            elif self.racadm_client:
                memory = await self.racadm_client.get_memory_structured()
                return {"memory": [m.model_dump() for m in memory]}
            return {"memory": []}
        
        elif command == "get_power_supplies":
            if self.redfish_client:
                power_supplies = await self.redfish_client.get_power_supplies()
                return {"power_supplies": [ps.model_dump() for ps in power_supplies]}
            elif self.racadm_client:
                power_supplies = await self.racadm_client.get_power_supplies_structured()
                return {"power_supplies": [ps.model_dump() for ps in power_supplies]}
            return {"power_supplies": []}
        
        elif command == "get_temperature_sensors":
            if self.redfish_client:
                temperatures = await self.redfish_client.get_temperature_sensors()
                return {"temperatures": [t.model_dump() for t in temperatures]}
            elif self.racadm_client:
                temperatures = await self.racadm_client.get_temperatures_structured()
                return {"temperatures": [t.model_dump() for t in temperatures]}
            return {"temperatures": []}
        
        elif command == "get_fans":
            if self.redfish_client:
                fans = await self.redfish_client.get_fans()
                return {"fans": [f.model_dump() for f in fans]}
            elif self.racadm_client:
                fans = await self.racadm_client.get_fans_structured()
                return {"fans": [f.model_dump() for f in fans]}
            return {"fans": []}
        
        elif command == "get_storage_devices":
            if self.redfish_client:
                storage = await self.redfish_client.get_storage_devices()
                return {"storage_devices": [s.model_dump() for s in storage]}
            elif self.racadm_client:
                storage = await self.racadm_client.get_storage_structured()
                return {"storage_devices": [s.model_dump() for s in storage]}
            return {"storage_devices": []}
        
        elif command == "get_network_interfaces":
            if self.redfish_client:
                network = await self.redfish_client.get_network_interfaces()
                return {"network_interfaces": [n.model_dump() for n in network]}
            elif self.racadm_client:
                network = await self.racadm_client.get_network_structured()
                return {"network_interfaces": [n.model_dump() for n in network]}
            return {"network_interfaces": []}
        
        elif command == "health_check":
            if self.redfish_client:
                health = await self.redfish_client.get_health_status()
            else:
                # Create basic health status from RACADM logs
                logs = await self.racadm_client.get_system_logs()
                health = HealthStatus(
                    overall_status=ServerStatus.ONLINE,
                    components={},
                    critical_issues=[log for log in logs if log.severity == Severity.CRITICAL],
                    warnings=[log for log in logs if log.severity == Severity.WARNING]
                )
            return {"health_status": health.model_dump() if health else None}
        
        elif command == "collect_logs":
            logs = []
            if self.redfish_client:
                logs.extend(await self.redfish_client.get_logs())
            
            if self.racadm_client:
                logs.extend(await self.racadm_client.get_system_logs())
                logs.extend(await self.racadm_client.get_lc_logs())
            
            # Sort logs by timestamp
            logs.sort(key=lambda x: x.timestamp, reverse=True)
            return {"logs": [log.model_dump() for log in logs]}

        elif command == "get_bios_attributes":
            if self.redfish_client:
                bios = await self.redfish_client.get_bios_attributes()
                return {"bios": bios}
            elif self.racadm_client:
                bios = await self.racadm_client.get_bios_attributes()
                return {"bios": bios}
            return {"bios": {}}

        elif command == "get_firmware_inventory":
            if self.redfish_client:
                fw = await self.redfish_client.get_firmware_inventory()
                return {"firmware_inventory": fw}
            elif self.racadm_client:
                fw = await self.racadm_client.get_firmware_inventory()
                return {"firmware_inventory": fw}
            return {"firmware_inventory": []}

        elif command == "get_lifecycle_logs":
            if self.redfish_client:
                lc = await self.redfish_client.get_lifecycle_logs()
                return {"lifecycle_logs": lc}
            elif self.racadm_client:
                lc_logs = await self.racadm_client.get_lc_logs()
                return {"lifecycle_logs": [l.model_dump() for l in lc_logs]}
            return {"lifecycle_logs": []}

        elif command == "get_idrac_info":
            if self.redfish_client:
                info = await self.redfish_client.get_idrac_info()
                return {"idrac_info": info}
            elif self.racadm_client:
                info = await self.racadm_client.get_idrac_info()
                return {"idrac_info": info}
            return {"idrac_info": {}}

        elif command == "get_post_codes":
            if self.redfish_client:
                codes = await self.redfish_client.get_post_codes()
                return {"post_codes": codes}
            return {"post_codes": {}}

        elif command == "get_jobs":
            if self.redfish_client:
                jobs = await self.redfish_client.get_jobs()
                return {"jobs": jobs}
            return {"jobs": []}

        elif command == "get_boot_order":
            if self.redfish_client:
                boot = await self.redfish_client.get_boot_order()
                return {"boot_order": boot}
            return {"boot_order": {}}

        elif command == "get_lifecycle_status":
            if self.redfish_client:
                lc = await self.redfish_client.get_lifecycle_status()
                return {"lifecycle_status": lc}
            return {"lifecycle_status": {}}

        elif command == "get_idrac_network_config":
            if self.redfish_client:
                net = await self.redfish_client.get_idrac_network_config()
                return {"idrac_network": net}
            return {"idrac_network": {}}

        elif command == "get_idrac_users":
            if self.redfish_client:
                users = await self.redfish_client.get_idrac_users()
                return {"idrac_users": users}
            return {"idrac_users": []}

        elif command == "get_ssl_certificate_info":
            if self.redfish_client:
                cert = await self.redfish_client.get_ssl_certificate_info()
                return {"ssl_certificates": cert}
            return {"ssl_certificates": {"available": False}}

        elif command == "performance_analysis":
            performance_data = {}
            if self.redfish_client:
                self.redfish_client._clear_sensor_cache()
                power_supplies = await self.redfish_client.get_power_supplies()
                if power_supplies:
                    performance_data["power_consumption"] = sum(
                        ps.power_watts for ps in power_supplies if ps.power_watts
                    )
                temperatures = await self.redfish_client.get_temperature_sensors()
                if temperatures:
                    temp_readings = [t.reading_celsius for t in temperatures if t.reading_celsius]
                    if temp_readings:
                        performance_data["temperature_average"] = round(sum(temp_readings) / len(temp_readings), 1)
                        performance_data["temperature_max"] = max(temp_readings)
                fans = await self.redfish_client.get_fans()
                if fans:
                    fan_speeds = [f.speed_rpm for f in fans if f.speed_rpm]
                    if fan_speeds:
                        performance_data["fan_speed_average"] = round(sum(fan_speeds) / len(fan_speeds))
            elif self.racadm_client:
                temps = await self.racadm_client.get_temperatures_structured()
                if temps:
                    readings = [t.reading_celsius for t in temps if t.reading_celsius]
                    if readings:
                        performance_data["temperature_average"] = round(sum(readings) / len(readings), 1)
                        performance_data["temperature_max"] = max(readings)
                fans = await self.racadm_client.get_fans_structured()
                if fans:
                    speeds = [f.speed_rpm for f in fans if f.speed_rpm]
                    if speeds:
                        performance_data["fan_speed_average"] = round(sum(speeds) / len(speeds))
            return {"performance_metrics": performance_data}

        elif command == "get_support_assist_status":
            if self.redfish_client:
                sa = await self.redfish_client.get_support_assist_status()
                return {"support_assist": sa}
            return {"support_assist": {"registered": False, "available": False, "message": "Requires Redfish"}}

        elif command == "check_idrac_availability":
            host = parameters.get("host", self.current_session.server_host if self.current_session else "")
            username = parameters.get("username", "")
            password = parameters.get("password", "")
            if not host:
                return {"availability": {"reachable": False, "error": "No host specified"}}
            from integrations.redfish_client import RedfishClient as RC
            checker = RC(host=host, username=username, password=password, port=443, verify_ssl=False)
            avail = await checker.check_idrac_availability()
            return {"availability": avail}

        elif command == "get_full_inventory":
            result = {}
            # Server info
            if self.redfish_client:
                self.redfish_client._clear_sensor_cache()
                info = await self.redfish_client.get_server_info()
                result["server_info"] = info.model_dump() if info else None
                sys_info = await self.redfish_client.get_system_info()
                result["system_info"] = sys_info.model_dump() if sys_info else None
                processors = await self.redfish_client.get_processors()
                result["processors"] = [p.model_dump() for p in processors]
                memory = await self.redfish_client.get_memory()
                result["memory"] = [m.model_dump() for m in memory]
                power_supplies = await self.redfish_client.get_power_supplies()
                result["power_supplies"] = [ps.model_dump() for ps in power_supplies]
                temperatures = await self.redfish_client.get_temperature_sensors()
                result["temperatures"] = [t.model_dump() for t in temperatures]
                fans = await self.redfish_client.get_fans()
                result["fans"] = [f.model_dump() for f in fans]
                storage = await self.redfish_client.get_storage_devices()
                result["storage_devices"] = [s.model_dump() for s in storage]
                network = await self.redfish_client.get_network_interfaces()
                result["network_interfaces"] = [n.model_dump() for n in network]
                health = await self.redfish_client.get_health_status()
                result["health_status"] = health.model_dump() if health else None
                logs_list = await self.redfish_client.get_logs()
                logs_list.sort(key=lambda x: x.timestamp, reverse=True)
                result["logs"] = [l.model_dump() for l in logs_list]
                # New deep data
                result["bios"] = await self.redfish_client.get_bios_attributes()
                result["firmware_inventory"] = await self.redfish_client.get_firmware_inventory()
                result["idrac_info"] = await self.redfish_client.get_idrac_info()
                result["post_codes"] = await self.redfish_client.get_post_codes()
            elif self.racadm_client:
                info = await self.racadm_client.get_server_info()
                result["server_info"] = info.model_dump() if info else None
                sys_info = await self.racadm_client.get_system_info()
                result["system_info"] = sys_info.model_dump() if sys_info else None
                # Structured hardware data via hwinventory
                processors = await self.racadm_client.get_processors_structured()
                result["processors"] = [p.model_dump() for p in processors]
                memory = await self.racadm_client.get_memory_structured()
                result["memory"] = [m.model_dump() for m in memory]
                storage = await self.racadm_client.get_storage_structured()
                result["storage_devices"] = [s.model_dump() for s in storage]
                network = await self.racadm_client.get_network_structured()
                result["network_interfaces"] = [n.model_dump() for n in network]
                # Sensor data
                temperatures = await self.racadm_client.get_temperatures_structured()
                result["temperatures"] = [t.model_dump() for t in temperatures]
                fans = await self.racadm_client.get_fans_structured()
                result["fans"] = [f.model_dump() for f in fans]
                power_supplies = await self.racadm_client.get_power_supplies_structured()
                result["power_supplies"] = [ps.model_dump() for ps in power_supplies]
                # Logs
                sel_logs = await self.racadm_client.get_system_logs()
                lc_logs = await self.racadm_client.get_lc_logs()
                all_logs = sel_logs + lc_logs
                all_logs.sort(key=lambda x: x.timestamp, reverse=True)
                result["logs"] = [l.model_dump() for l in all_logs]
                # Health status
                crit_issues = [l for l in all_logs if l.severity == Severity.CRITICAL]
                warn_issues = [l for l in all_logs if l.severity == Severity.WARNING]
                result["health_status"] = {
                    "overall_status": "critical" if crit_issues else ("warning" if warn_issues else "online"),
                    "components": {},
                    "critical_issues": [l.model_dump() for l in crit_issues],
                    "warnings": [l.model_dump() for l in warn_issues],
                }
                # Deep data via RACADM
                result["bios"] = await self.racadm_client.get_bios_attributes()
                result["firmware_inventory"] = await self.racadm_client.get_firmware_inventory()
                result["idrac_info"] = await self.racadm_client.get_idrac_info()
                result["post_codes"] = {}
            # Connection metadata
            result["connection_info"] = {
                "host": self.current_session.server_host if self.current_session else None,
                "method": self.current_session.connection_method if self.current_session else None,
                "connected_at": self.current_session.connected_at.isoformat() if self.current_session else None,
                "available_methods": self.get_available_methods(),
            }
            return result
        
        else:
            raise ValueError(f"Unknown read-only command: {command}")
    
    async def _execute_diagnostic_command(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute diagnostic commands"""
        
        # Try read-only commands first
        try:
            result = await self._execute_read_only_command(command, parameters)
            return result
        except ValueError:
            pass  # Not a read-only command, continue to diagnostic-specific

        result = {}
        # Diagnostic-specific commands
        if command == "performance_analysis":
            # Collect performance metrics
            performance_data = {}
            
            if self.redfish_client:
                # Get power consumption
                power_supplies = await self.redfish_client.get_power_supplies()
                if power_supplies:
                    performance_data["power_consumption"] = sum(
                        ps.power_watts for ps in power_supplies if ps.power_watts
                    )
                
                # Get temperature data
                temperatures = await self.redfish_client.get_temperature_sensors()
                if temperatures:
                    temp_readings = [t.reading_celsius for t in temperatures if t.reading_celsius]
                    if temp_readings:
                        performance_data["temperature_average"] = sum(temp_readings) / len(temp_readings)
                        performance_data["temperature_max"] = max(temp_readings)
                
                # Get fan speeds
                fans = await self.redfish_client.get_fans()
                if fans:
                    fan_speeds = [f.speed_rpm for f in fans if f.speed_rpm]
                    if fan_speeds:
                        performance_data["fan_speed_average"] = sum(fan_speeds) / len(fan_speeds)
            
            elif self.racadm_client:
                # Get performance data from RACADM
                power_info = await self.racadm_client.get_power_consumption()
                if power_info:
                    performance_data["power_info"] = power_info
                
                temp_info = await self.racadm_client.get_temperature_sensors()
                if temp_info:
                    performance_data["temperature_info"] = temp_info
                
                fan_info = await self.racadm_client.get_fan_info()
                if fan_info:
                    performance_data["fan_info"] = fan_info
            
            result.update({"performance_metrics": performance_data})
        
        elif command == "connectivity_test":
            # Test connectivity to various services
            connectivity_results = {}
            
            # Test Redfish connectivity
            if self.redfish_client:
                connectivity_results["redfish"] = "connected"
            else:
                connectivity_results["redfish"] = "not_available"
            
            # Test RACADM connectivity
            if self.racadm_client:
                connectivity_results["racadm"] = "connected"
            else:
                connectivity_results["racadm"] = "not_available"
            
            result.update({"connectivity_results": connectivity_results})
        
        elif command == "firmware_check":
            firmware_info = {}
            
            if self.redfish_client:
                server_info = await self.redfish_client.get_server_info()
                if server_info:
                    firmware_info["bios"] = server_info.firmware_version
                    firmware_info["idrac"] = server_info.idrac_version
            
            elif self.racadm_client:
                server_info = await self.racadm_client.get_server_info()
                if server_info:
                    firmware_info["bios"] = server_info.firmware_version
                    firmware_info["idrac"] = server_info.idrac_version
            
            result.update({"firmware_info": firmware_info})

        else:
            raise ValueError(f"Unknown diagnostic command: {command}")
        
        return result
    
    async def _execute_full_control_command(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute full control commands (high risk)"""
        parameters = parameters or {}
        
        # Try diagnostic commands first (which includes read-only)
        try:
            result = await self._execute_diagnostic_command(command, parameters)
            return result
        except ValueError:
            pass  # Not a diagnostic command, continue to full-control-specific

        result = {}
        # Full control commands
        if command == "power_on":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("On")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("power_on")
            
            result.update({"power_action": "power_on", "success": success})
        
        elif command == "power_off":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("ForceOff")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("power_off")
            
            result.update({"power_action": "power_off", "success": success})
        
        elif command == "restart_server":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("GracefulRestart")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("graceful_restart")
            
            result.update({"power_action": "restart", "success": success})
        
        elif command == "force_restart":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("ForceRestart")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("force_restart")
            
            result.update({"power_action": "force_restart", "success": success})
        
        elif command == "set_boot_order":
            boot_devices = parameters.get("boot_devices", [])
            if not boot_devices:
                raise ValueError("boot_devices parameter required")
            
            success = False
            if self.redfish_client:
                success = await self.redfish_client.set_boot_order(boot_devices)
            elif self.racadm_client:
                success = await self.racadm_client.set_boot_order(boot_devices)
            
            result.update({"boot_order_set": boot_devices, "success": success})
        
        elif command == "create_support_collection":
            collection_id = None
            if self.racadm_client:
                collection_id = await self.racadm_client.create_support_assist_collection()
            
            result.update({"support_collection_id": collection_id})
        
        elif command == "export_tsr":
            tsr_result = {}
            if self.redfish_client:
                tsr_result = await self.redfish_client.export_tsr(parameters.get("share_type", "Local"))
            elif self.racadm_client:
                collection_id = await self.racadm_client.create_support_assist_collection()
                tsr_result = {"success": collection_id is not None, "collection_id": collection_id}
            result.update({"tsr_result": tsr_result})

        elif command == "get_job_status":
            job_id = parameters.get("job_id", "")
            if not job_id:
                result.update({"job_status": {"success": False, "error": "No job_id provided"}})
            elif self.redfish_client:
                job_status = await self.redfish_client.get_job_status(job_id)
                result.update({"job_status": job_status})
            else:
                result.update({"job_status": {"success": False, "error": "No Redfish client"}})

        elif command == "check_health_score":
            # Collect data from multiple subsystems
            subsystem_data = {}
            
            if self.redfish_client:
                # Get thermal data
                try:
                    thermal = await self.redfish_client.get_temperature_sensors()
                    if thermal:
                        subsystem_data["thermal"] = thermal
                except Exception as e:
                    logger.warning(f"Failed to get thermal data for health scoring: {e}")
                
                # Get power data
                try:
                    power = await self.redfish_client.get_power_supplies()
                    if power:
                        subsystem_data["power"] = power
                except Exception as e:
                    logger.warning(f"Failed to get power data for health scoring: {e}")
                
                # Get memory data
                try:
                    memory = await self.redfish_client.get_memory()
                    if memory:
                        subsystem_data["memory"] = memory
                except Exception as e:
                    logger.warning(f"Failed to get memory data for health scoring: {e}")
            
            result.update({"health_data": subsystem_data})

        elif command == "reset_idrac":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.reset_idrac()
            result.update({"idrac_reset": success})

        elif command == "graceful_shutdown":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("GracefulShutdown")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("graceful_shutdown")
            result.update({"power_action": "graceful_shutdown", "success": success})

        elif command == "set_bios_attributes":
            attrs = parameters.get("attributes", {})
            if not attrs:
                raise ValueError("attributes parameter required")
            success = False
            if self.redfish_client:
                success = await self.redfish_client.set_bios_attributes(attrs)
            result.update({"bios_set": success, "pending_reboot": success})

        elif command == "run_diagnostics":
            diag_type = parameters.get("type", "Express")
            if self.redfish_client:
                diag_result = await self.redfish_client.run_remote_diagnostics(diag_type)
                return {"diagnostics_result": diag_result}
            return {"diagnostics_result": {"success": False, "error": "Diagnostics require Redfish connection"}}

        elif command == "virtual_ac_cycle":
            if self.redfish_client:
                vac_result = await self.redfish_client.virtual_ac_cycle()
                return {"vac_result": vac_result}
            return {"vac_result": {"success": False, "error": "Virtual AC cycle requires Redfish connection"}}

        elif command == "export_config":
            filename = parameters.get("filename")
            exported_file = None
            if self.racadm_client:
                exported_file = await self.racadm_client.export_system_configuration(filename)
            
            result.update({"exported_config_file": exported_file})
        
        elif command == "update_firmware":
            component = parameters.get("component")
            firmware_file = parameters.get("firmware_file")
            
            if not component or not firmware_file:
                raise ValueError("component and firmware_file parameters required")
            
            success = False
            if self.racadm_client:
                success = await self.racadm_client.update_firmware(component, firmware_file)
            
            result.update({"firmware_update": {"component": component, "success": success}})

        elif command == "power_cycle":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("PowerCycle")
                if not success:
                    success = await self.redfish_client.power_action("ForceRestart")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("power_cycle")
            result.update({"power_action": "power_cycle", "success": success})

        elif command == "force_power_off":
            success = False
            if self.redfish_client:
                success = await self.redfish_client.power_action("ForceOff")
            elif self.racadm_client:
                success = await self.racadm_client.power_action("power_off")
            result.update({"power_action": "force_power_off", "success": success})

        elif command == "send_nmi":
            if self.redfish_client:
                nmi_result = await self.redfish_client.send_nmi()
                return {"nmi_result": nmi_result}
            return {"nmi_result": {"success": False, "error": "NMI requires Redfish connection"}}

        elif command == "set_next_boot_device":
            device = parameters.get("device", "")
            if not device:
                raise ValueError("device parameter required")
            if self.redfish_client:
                boot_result = await self.redfish_client.set_next_boot_device(device)
                return {"next_boot": boot_result}
            return {"next_boot": {"success": False, "error": "Requires Redfish connection"}}

        elif command == "clear_sel":
            if self.redfish_client:
                sel_result = await self.redfish_client.clear_sel()
                return {"clear_sel": sel_result}
            return {"clear_sel": {"success": False, "error": "Requires Redfish connection"}}

        elif command == "export_scp":
            if self.redfish_client:
                scp_result = await self.redfish_client.export_scp()
                return {"scp_export": scp_result}
            return {"scp_export": {"success": False, "error": "Requires Redfish connection"}}

        elif command == "delete_all_jobs":
            if self.redfish_client:
                del_result = await self.redfish_client.delete_all_jobs()
                return {"delete_jobs": del_result}
            return {"delete_jobs": {"success": False, "error": "Requires Redfish connection"}}

        else:
            raise ValueError(f"Unknown full control command: {command}")
        
        return result
    
    async def troubleshoot_issue(self, issue_description: str, action_level: ActionLevel) -> dict:
        """AI-powered troubleshooting — collects all data and returns a full analysis report."""
        from datetime import datetime, timedelta, timezone
        import re

        collected = {
            "logs": [], "health_status": None, "system_info": None,
            "temperatures": [], "fans": [], "power_supplies": [],
            "memory": [], "storage": [], "network": [],
        }
        report = {
            "collection_summary": {},
            "log_analysis": {},
            "sensor_analysis": {},
            "anomalies": [],
            "error_timeline": [],
        }

        try:
            # ── Phase 1: Collect everything ──────────────────────────
            if self.redfish_client:
                self.redfish_client._sensor_cache = None  # fresh readings

                try:
                    collected["logs"] = await self.redfish_client.get_logs()
                except Exception as e:
                    logger.warning(f"Log collection failed: {e}")

                try:
                    collected["health_status"] = await self.redfish_client.get_health_status()
                except Exception as e:
                    logger.warning(f"Health check failed: {e}")

                try:
                    collected["system_info"] = await self.redfish_client.get_system_info()
                except Exception as e:
                    logger.warning(f"System info failed: {e}")

                try:
                    collected["temperatures"] = [t.model_dump() for t in await self.redfish_client.get_temperature_sensors()]
                except Exception as e:
                    logger.warning(f"Temp sensor read failed: {e}")

                try:
                    collected["fans"] = [f.model_dump() for f in await self.redfish_client.get_fans()]
                except Exception as e:
                    logger.warning(f"Fan read failed: {e}")

                try:
                    collected["power_supplies"] = [p.model_dump() for p in await self.redfish_client.get_power_supplies()]
                except Exception as e:
                    logger.warning(f"PSU read failed: {e}")

                try:
                    collected["memory"] = [m.model_dump() for m in await self.redfish_client.get_memory()]
                except Exception as e:
                    logger.warning(f"Memory read failed: {e}")

                try:
                    collected["storage"] = [s.model_dump() for s in await self.redfish_client.get_storage_devices()]
                except Exception as e:
                    logger.warning(f"Storage read failed: {e}")

                try:
                    collected["network"] = [n.model_dump() for n in await self.redfish_client.get_network_interfaces()]
                except Exception as e:
                    logger.warning(f"Network read failed: {e}")

            if self.racadm_client:
                try:
                    collected["logs"].extend(await self.racadm_client.get_system_logs())
                except Exception:
                    pass
                try:
                    collected["logs"].extend(await self.racadm_client.get_lc_logs())
                except Exception:
                    pass

            # Sort logs newest first (normalize tz for comparison)
            def _tz_safe(ts):
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts
            collected["logs"].sort(key=lambda x: _tz_safe(x.timestamp), reverse=True)

            # ── Phase 2: Analyze logs ────────────────────────────────
            logs = collected["logs"]
            now = datetime.now(timezone.utc)
            sev_counts = {"critical": 0, "error": 0, "warning": 0, "info": 0}
            recent_critical = []
            error_codes_found = []
            component_errors = {}  # component -> count

            for log in logs:
                sev = (log.severity.value if hasattr(log.severity, 'value') else str(log.severity)).lower()
                sev_counts[sev] = sev_counts.get(sev, 0) + 1

                if sev in ("critical", "error"):
                    # Normalize timezone: make log timestamp offset-aware (UTC) if naive
                    ts = log.timestamp
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = (now - ts).total_seconds() / 3600
                    if age <= 72:
                        recent_critical.append({
                            "message": log.message[:200],
                            "severity": sev,
                            "timestamp": log.timestamp.isoformat(),
                            "event_id": log.event_id or "",
                            "hours_ago": round(age, 1),
                        })

                # Extract Dell error codes
                combined = f"{log.message} {log.event_id or ''}"
                for match in re.findall(r'(PSU|CPU|MEM|FAN|STO|VLT|HWC)\d{4}', combined):
                    error_codes_found.append(match)

                # Track component error frequency
                for comp in ["CPU", "Memory", "Power", "Fan", "Storage", "Network", "RAID", "Thermal", "BIOS", "iDRAC"]:
                    if comp.lower() in log.message.lower():
                        component_errors[comp] = component_errors.get(comp, 0) + 1

            # Build error timeline (last 72h, grouped by 6h buckets)
            timeline = []
            for bucket_start_h in range(0, 72, 6):
                bucket_end_h = bucket_start_h + 6
                bucket_logs = [
                    l for l in logs
                    if bucket_start_h <= (now - (l.timestamp.replace(tzinfo=timezone.utc) if l.timestamp.tzinfo is None else l.timestamp)).total_seconds() / 3600 < bucket_end_h
                    and (l.severity.value if hasattr(l.severity, 'value') else str(l.severity)).lower() in ("critical", "error", "warning")
                ]
                if bucket_logs or bucket_start_h < 24:
                    timeline.append({
                        "label": f"{bucket_start_h}-{bucket_end_h}h ago",
                        "critical": sum(1 for l in bucket_logs if (l.severity.value if hasattr(l.severity, 'value') else '').lower() == 'critical'),
                        "error": sum(1 for l in bucket_logs if (l.severity.value if hasattr(l.severity, 'value') else '').lower() == 'error'),
                        "warning": sum(1 for l in bucket_logs if (l.severity.value if hasattr(l.severity, 'value') else '').lower() == 'warning'),
                    })

            report["log_analysis"] = {
                "total_entries": len(logs),
                "severity_counts": sev_counts,
                "recent_critical": recent_critical[:20],
                "error_codes_found": list(set(error_codes_found)),
                "component_errors": component_errors,
                "error_timeline": timeline,
            }

            # ── Phase 3: Analyze sensors ────────────────────────────
            temps = collected["temperatures"]
            fans = collected["fans"]
            psus = collected["power_supplies"]

            temp_readings = [t.get("reading_celsius") or 0 for t in temps if t.get("reading_celsius")]
            fan_speeds = [f.get("speed_rpm") or 0 for f in fans if f.get("speed_rpm")]
            anomalies = []

            if temp_readings:
                avg_temp = sum(temp_readings) / len(temp_readings)
                max_temp = max(temp_readings)
                hot_sensors = [t for t in temps if (t.get("reading_celsius") or 0) > 70]
                report["sensor_analysis"]["temperature"] = {
                    "count": len(temps),
                    "avg": round(avg_temp, 1),
                    "max": round(max_temp, 1),
                    "min": round(min(temp_readings), 1),
                    "hot_sensors": [{"name": t.get("name","?"), "reading": t.get("reading_celsius")} for t in hot_sensors],
                }
                if max_temp > 80:
                    anomalies.append({"type": "critical", "component": "Temperature", "detail": f"Sensor reading {max_temp}°C exceeds 80°C threshold"})
                elif max_temp > 70:
                    anomalies.append({"type": "warning", "component": "Temperature", "detail": f"Sensor reading {max_temp}°C is elevated"})

            # Helper: check if a status string indicates healthy
            def _is_healthy(status_str):
                if not status_str:
                    return True  # no status = assume OK
                s = status_str.lower()
                return any(w in s for w in ("ok", "enabled", "operable", "online", "optimal", "ready", "present"))

            if fan_speeds:
                avg_fan = sum(fan_speeds) / len(fan_speeds)
                failed_fans = [f for f in fans if not _is_healthy(f.get("status"))]
                report["sensor_analysis"]["fans"] = {
                    "count": len(fans),
                    "avg_rpm": round(avg_fan),
                    "max_rpm": max(fan_speeds),
                    "min_rpm": min(fan_speeds),
                    "failed_fans": [{"name": f.get("name","?"), "status": f.get("status","?")} for f in failed_fans],
                }
                if failed_fans:
                    anomalies.append({"type": "critical", "component": "Fans", "detail": f"{len(failed_fans)} fan(s) in abnormal state"})
                if avg_fan > 12000:
                    anomalies.append({"type": "warning", "component": "Fans", "detail": f"Average fan speed {round(avg_fan)} RPM is very high — possible thermal issue"})

            if psus:
                failed_psus = [p for p in psus if not _is_healthy(p.get("status"))]
                total_watts = sum(p.get("power_watts") or 0 for p in psus)
                report["sensor_analysis"]["power"] = {
                    "count": len(psus),
                    "total_watts": total_watts,
                    "failed_psus": [{"id": p.get("id","?"), "status": p.get("status","?")} for p in failed_psus],
                }
                if failed_psus:
                    anomalies.append({"type": "critical", "component": "Power", "detail": f"{len(failed_psus)} PSU(s) in abnormal state"})

            mem = collected["memory"]
            if mem:
                total_gb = sum(m.get("size_gb") or 0 for m in mem)
                failed_dimms = [m for m in mem if not _is_healthy(m.get("status"))]
                report["sensor_analysis"]["memory"] = {
                    "dimm_count": len(mem),
                    "total_gb": total_gb,
                    "failed_dimms": [{"id": m.get("id","?"), "status": m.get("status","?")} for m in failed_dimms],
                }
                if failed_dimms:
                    anomalies.append({"type": "critical", "component": "Memory", "detail": f"{len(failed_dimms)} DIMM(s) in abnormal state"})

            storage = collected["storage"]
            if storage:
                failed_drives = [s for s in storage if not _is_healthy(s.get("status"))]
                report["sensor_analysis"]["storage"] = {
                    "device_count": len(storage),
                    "failed_devices": [{"id": s.get("id","?"), "status": s.get("status","?")} for s in failed_drives],
                }
                if failed_drives:
                    anomalies.append({"type": "critical", "component": "Storage", "detail": f"{len(failed_drives)} storage device(s) in abnormal state"})

            report["anomalies"] = anomalies

            # ── Phase 3b: System identity ──────────────────────────────
            si = collected["system_info"]
            hs = collected["health_status"]
            system_identity = {}
            if si:
                sid = si.model_dump() if hasattr(si, 'model_dump') else {}
                system_identity = {
                    "model": sid.get("model", ""),
                    "manufacturer": sid.get("manufacturer", "Dell Inc."),
                    "service_tag": sid.get("service_tag", ""),
                    "bios_version": sid.get("bios_version", ""),
                    "hostname": sid.get("hostname", ""),
                    "os": sid.get("os_name", ""),
                    "os_version": sid.get("os_version", ""),
                    "cpu_model": sid.get("cpu_model", ""),
                    "cpu_count": sid.get("cpu_count", 0),
                    "total_memory_gb": sid.get("total_memory_gb", 0),
                    "power_state": sid.get("power_state", ""),
                    "idrac_version": sid.get("idrac_version", ""),
                }
            report["system_identity"] = system_identity

            # ── Phase 3c: Per-component deep-dive tables ───────────────
            report["deep_dive"] = {
                "temperatures": [
                    {"name": t.get("name","?"), "reading": t.get("reading_celsius"), "status": t.get("status","?"),
                     "upper_critical": t.get("upper_threshold_critical"), "upper_warning": t.get("upper_threshold_warning"),
                     "health": "critical" if (t.get("reading_celsius") or 0) > 80 else "warning" if (t.get("reading_celsius") or 0) > 70 else "ok"}
                    for t in temps
                ],
                "fans": [
                    {"name": f.get("name","?"), "speed_rpm": f.get("speed_rpm"), "status": f.get("status","?"),
                     "health": "ok" if _is_healthy(f.get("status")) else "critical"}
                    for f in fans
                ],
                "power_supplies": [
                    {"id": p.get("id","?"), "model": p.get("model",""), "power_watts": p.get("power_watts"),
                     "capacity_watts": p.get("capacity_watts"), "status": p.get("status","?"),
                     "efficiency": p.get("efficiency",""), "firmware": p.get("firmware_version",""),
                     "health": "ok" if _is_healthy(p.get("status")) else "critical"}
                    for p in psus
                ],
                "memory": [
                    {"id": m.get("id","?"), "size_gb": m.get("size_gb"), "type": m.get("type",""),
                     "speed_mhz": m.get("speed_mhz"), "manufacturer": m.get("manufacturer",""),
                     "part_number": m.get("part_number",""), "serial": m.get("serial_number",""),
                     "status": m.get("status","?"), "slot": m.get("slot",""),
                     "health": "ok" if _is_healthy(m.get("status")) else "critical"}
                    for m in mem
                ],
                "storage": [
                    {"id": s.get("id","?"), "name": s.get("name",""), "model": s.get("model",""),
                     "capacity_gb": s.get("capacity_gb"), "media_type": s.get("media_type",""),
                     "protocol": s.get("protocol",""), "serial": s.get("serial_number",""),
                     "status": s.get("status","?"), "firmware": s.get("firmware_version",""),
                     "health": "ok" if _is_healthy(s.get("status")) else "critical"}
                    for s in storage
                ],
                "network": [
                    {"id": n.get("id","?"), "name": n.get("name",""), "mac": n.get("mac_address",""),
                     "speed_mbps": n.get("speed_mbps"), "status": n.get("status","?"),
                     "ipv4": n.get("ipv4_address",""), "link_status": n.get("link_status",""),
                     "health": "ok" if _is_healthy(n.get("status")) else "warning"}
                    for n in collected["network"]
                ],
            }

            # ── Phase 3d: Cross-subsystem correlations ──────────────────
            correlations = []
            # Thermal + Fan correlation
            if temp_readings and fan_speeds:
                avg_temp_val = sum(temp_readings) / len(temp_readings)
                avg_fan_val = sum(fan_speeds) / len(fan_speeds)
                if avg_temp_val > 65 and avg_fan_val > 10000:
                    correlations.append({
                        "type": "thermal_fan",
                        "severity": "warning",
                        "title": "Thermal-Fan Correlation",
                        "detail": f"High avg temp ({round(avg_temp_val,1)}°C) with elevated fan speeds ({round(avg_fan_val)} RPM) — fans are compensating for heat.",
                        "action": "Check airflow, clean dust filters, verify no blanking panels are missing."
                    })
                if any(not _is_healthy(f.get("status")) for f in fans) and max(temp_readings) > 70:
                    correlations.append({
                        "type": "fan_failure_thermal",
                        "severity": "critical",
                        "title": "Fan Failure Causing Thermal Stress",
                        "detail": "Failed fan(s) detected alongside high temperatures — direct causal link.",
                        "action": "Replace failed fan immediately. Hot-swappable on most Dell servers."
                    })
            # Power + Component correlation
            if psus and any(not _is_healthy(p.get("status")) for p in psus):
                psu_fail_count = sum(1 for p in psus if not _is_healthy(p.get("status")))
                if psu_fail_count >= len(psus):
                    correlations.append({
                        "type": "total_power_loss",
                        "severity": "critical",
                        "title": "Complete Power Redundancy Lost",
                        "detail": f"All {len(psus)} PSUs are in abnormal state — imminent power failure risk.",
                        "action": "Emergency: replace PSU immediately, verify power source, check PDU."
                    })
                elif psu_fail_count > 0:
                    correlations.append({
                        "type": "partial_power_loss",
                        "severity": "warning",
                        "title": "Power Redundancy Degraded",
                        "detail": f"{psu_fail_count} of {len(psus)} PSU(s) degraded — running without redundancy.",
                        "action": "Replace failed PSU. Server runs on remaining PSU but has no failover."
                    })
            # Memory errors in logs + DIMM status
            mem_log_count = component_errors.get("Memory", 0)
            failed_dimm_count = sum(1 for m in mem if not _is_healthy(m.get("status")))
            if mem_log_count > 5 and failed_dimm_count == 0:
                correlations.append({
                    "type": "memory_errors_healthy_dimms",
                    "severity": "warning",
                    "title": "Memory Errors with Healthy DIMMs",
                    "detail": f"{mem_log_count} memory-related log entries but all DIMMs report OK — intermittent/correctable ECC errors.",
                    "action": "Monitor error rate. If increasing, run memory diagnostics and consider DIMM retrain or preemptive replacement."
                })
            elif failed_dimm_count > 0:
                correlations.append({
                    "type": "dimm_failure",
                    "severity": "critical",
                    "title": "DIMM Failure Detected",
                    "detail": f"{failed_dimm_count} DIMM(s) in failed state.",
                    "action": "Identify failed DIMM slot from SEL logs. Reseat or replace the DIMM."
                })
            # Storage + log correlation
            storage_log_count = component_errors.get("Storage", 0) + component_errors.get("RAID", 0)
            failed_drive_count = sum(1 for s in storage if not _is_healthy(s.get("status")))
            if storage_log_count > 3 or failed_drive_count > 0:
                correlations.append({
                    "type": "storage_issue",
                    "severity": "critical" if failed_drive_count > 0 else "warning",
                    "title": "Storage Subsystem Issue",
                    "detail": f"{failed_drive_count} drive(s) failed, {storage_log_count} storage log entries.",
                    "action": "Check RAID status. If degraded, replace failed drive. If failed VD, collect TSR before any action."
                })

            report["correlations"] = correlations

            # ── Phase 3e: Engineer's Assessment ─────────────────────────
            # Risk scoring: 0-100
            risk_score = 0
            top_concerns = []
            if anomalies:
                crit_anomalies = [a for a in anomalies if a["type"] == "critical"]
                warn_anomalies = [a for a in anomalies if a["type"] == "warning"]
                risk_score += len(crit_anomalies) * 25
                risk_score += len(warn_anomalies) * 10
                for a in crit_anomalies[:3]:
                    top_concerns.append(a["detail"])
                for a in warn_anomalies[:2]:
                    top_concerns.append(a["detail"])
            if correlations:
                crit_corr = [c for c in correlations if c["severity"] == "critical"]
                risk_score += len(crit_corr) * 15
            # Log severity weight
            risk_score += min(sev_counts.get("critical", 0) * 2, 20)
            risk_score += min(sev_counts.get("error", 0), 10)
            risk_score = min(risk_score, 100)

            if risk_score >= 70:
                risk_level = "critical"
                risk_label = "Immediate Action Required"
            elif risk_score >= 40:
                risk_level = "elevated"
                risk_label = "Attention Needed"
            elif risk_score >= 15:
                risk_level = "moderate"
                risk_label = "Monitor Closely"
            else:
                risk_level = "healthy"
                risk_label = "System Appears Healthy"

            # Build engineer narrative
            narrative_parts = []
            if si:
                sid2 = si.model_dump() if hasattr(si, 'model_dump') else {}
                narrative_parts.append(f"Server: {sid2.get('model','')} (Tag: {sid2.get('service_tag','N/A')})")
            health_str = hs.overall_status.value if hs else "unknown"
            narrative_parts.append(f"Overall health: {health_str}")
            narrative_parts.append(f"Scanned {len(logs)} log entries, {len(temps)} sensors, {len(fans)} fans, {len(psus)} PSUs, {len(mem)} DIMMs, {len(storage)} drives, {len(collected['network'])} NICs")
            if sev_counts.get("critical", 0) > 0:
                narrative_parts.append(f"Found {sev_counts['critical']} critical log entries — review needed")
            if correlations:
                narrative_parts.append(f"Identified {len(correlations)} cross-subsystem correlation(s)")
            if not anomalies and not correlations:
                narrative_parts.append("No hardware anomalies detected. Issue may be software/OS-level or intermittent.")

            report["engineer_assessment"] = {
                "risk_score": risk_score,
                "risk_level": risk_level,
                "risk_label": risk_label,
                "top_concerns": top_concerns[:5],
                "correlations_found": len(correlations),
                "narrative": narrative_parts,
                "recommendation_summary": "",  # filled after AI engine runs
            }

            report["collection_summary"] = {
                "logs_collected": len(logs),
                "temperatures_read": len(temps),
                "fans_read": len(fans),
                "psus_read": len(psus),
                "dimms_read": len(mem),
                "storage_devices_read": len(storage),
                "network_interfaces_read": len(collected["network"]),
                "health_status": health_str,
                "anomalies_found": len(anomalies),
            }

            # ── Phase 4: AI recommendation engine ────────────────────
            recommendations = await self.troubleshooting_engine.analyze_issue(
                issue_description=issue_description,
                logs=logs,
                health_status=collected["health_status"],
                system_info=collected["system_info"],
                action_level=action_level
            )

            # Add correlation-driven recommendations
            for corr in correlations:
                if corr["severity"] == "critical":
                    recommendations.append(TroubleshootingRecommendation(
                        action=corr["title"],
                        description=corr["detail"],
                        priority="critical",
                        action_level_required=ActionLevel.READ_ONLY,
                        estimated_time="Immediate",
                        risk_level="high",
                        steps=[corr["action"]],
                    ))

            # Fill summary into assessment
            rec_actions = [r.action if hasattr(r, 'action') else r.get('action','') for r in recommendations[:5]]
            report["engineer_assessment"]["recommendation_summary"] = f"Top actions: {'; '.join(rec_actions)}"

            logger.info(f"Generated {len(recommendations)} troubleshooting recommendations with full analysis report (risk={risk_score})")

            return {
                "recommendations": [r.model_dump() if hasattr(r, 'model_dump') else r for r in recommendations],
                "report": report,
                "collected_data": {
                    "temperatures": temps,
                    "fans": fans,
                    "power_supplies": psus,
                    "memory": mem,
                    "storage": storage,
                    "network": [n for n in collected["network"]],
                    "recent_logs": [{"message": l.message[:200], "severity": (l.severity.value if hasattr(l.severity, 'value') else str(l.severity)), "timestamp": l.timestamp.isoformat(), "event_id": l.event_id or ""} for l in logs[:50]],
                    "health": collected["health_status"].model_dump() if collected["health_status"] else None,
                    "system_info": collected["system_info"].model_dump() if collected["system_info"] else None,
                },
            }

        except Exception as e:
            logger.error(f"Troubleshooting failed: {str(e)}")
            raise
    
    async def get_action_history(self, limit: int = 50) -> List[AgentAction]:
        """Get recent action history"""
        return self.action_history[-limit:] if self.action_history else []
    
    async def get_session_info(self) -> Optional[ServerSession]:
        """Get current session information"""
        return self.current_session
    
    def is_connected(self) -> bool:
        """Check if connected to a server"""
        return self.current_session is not None and self.current_session.is_active
    
    def get_available_methods(self) -> List[str]:
        """Get available connection methods"""
        methods = []
        if self.redfish_client:
            methods.append("redfish")
        if self.racadm_client:
            methods.append("racadm")
        return methods
