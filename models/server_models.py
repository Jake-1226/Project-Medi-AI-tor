"""
Server-related data models for Dell Server AI Agent
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

class ActionLevel(str, Enum):
    READ_ONLY = "read_only"
    DIAGNOSTIC = "diagnostic"
    FULL_CONTROL = "full_control"

class ServerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class ComponentType(str, Enum):
    SYSTEM = "system"
    POWER = "power"
    THERMAL = "thermal"
    MEMORY = "memory"
    PROCESSOR = "processor"
    STORAGE = "storage"
    NETWORK = "network"
    FIRMWARE = "firmware"

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"

class ServerInfo(BaseModel):
    """Basic server information"""
    host: str
    model: Optional[str] = None
    service_tag: Optional[str] = None
    firmware_version: Optional[str] = None
    idrac_version: Optional[str] = None
    status: ServerStatus = ServerStatus.UNKNOWN
    last_updated: datetime = Field(default_factory=datetime.now)

class SystemInfo(BaseModel):
    """Detailed system information"""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    part_number: Optional[str] = None
    bios_version: Optional[str] = None
    system_type: Optional[str] = None
    asset_tag: Optional[str] = None
    power_state: Optional[str] = None
    boot_order: Optional[List[str]] = None

class ProcessorInfo(BaseModel):
    """Processor information"""
    id: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    cores: Optional[int] = None
    threads: Optional[int] = None
    speed_mhz: Optional[float] = None
    status: Optional[str] = None
    socket: Optional[str] = None

class MemoryInfo(BaseModel):
    """Memory module information"""
    id: str
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    size_gb: Optional[int] = None
    speed_mhz: Optional[int] = None
    type: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None

class PowerSupplyInfo(BaseModel):
    """Power supply information"""
    id: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    power_watts: Optional[int] = None
    input_voltage: Optional[float] = None
    output_voltage: Optional[float] = None
    efficiency: Optional[float] = None
    status: Optional[str] = None
    firmware_version: Optional[str] = None

class TemperatureInfo(BaseModel):
    """Temperature sensor information"""
    id: str
    name: Optional[str] = None
    reading_celsius: Optional[float] = None
    status: Optional[str] = None
    location: Optional[str] = None
    upper_threshold_critical: Optional[float] = None
    upper_threshold_non_critical: Optional[float] = None

class FanInfo(BaseModel):
    """Fan information"""
    id: str
    name: Optional[str] = None
    speed_rpm: Optional[int] = None
    status: Optional[str] = None
    location: Optional[str] = None
    min_speed_rpm: Optional[int] = None
    max_speed_rpm: Optional[int] = None

class StorageInfo(BaseModel):
    """Storage device information"""
    id: str
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    capacity_gb: Optional[int] = None
    type: Optional[str] = None  # HDD, SSD, NVMe
    interface: Optional[str] = None  # SATA, SAS, NVMe
    status: Optional[str] = None
    firmware_version: Optional[str] = None
    serial_number: Optional[str] = None

class NetworkInterfaceInfo(BaseModel):
    """Network interface information"""
    id: str
    name: Optional[str] = None
    mac_address: Optional[str] = None
    speed_mbps: Optional[int] = None
    status: Optional[str] = None
    link_status: Optional[str] = None
    auto_negotiation: Optional[bool] = None
    ipv4_addresses: Optional[List[str]] = None
    ipv6_addresses: Optional[List[str]] = None

class LogEntry(BaseModel):
    """Log entry model"""
    timestamp: datetime
    severity: Severity
    message: str
    source: Optional[str] = None
    component: Optional[ComponentType] = None
    event_id: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

class HealthStatus(BaseModel):
    """System health status"""
    overall_status: ServerStatus
    components: Dict[ComponentType, ServerStatus]
    critical_issues: List[LogEntry]
    warnings: List[LogEntry]
    last_check: datetime = Field(default_factory=datetime.now)

class PerformanceMetrics(BaseModel):
    """Performance metrics"""
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    disk_utilization: Optional[float] = None
    network_throughput: Optional[float] = None
    power_consumption: Optional[float] = None
    temperature_average: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class TroubleshootingRequest(BaseModel):
    """Troubleshooting request model"""
    server_info: ServerInfo
    issue_description: str
    action_level: ActionLevel = ActionLevel.READ_ONLY
    symptoms: Optional[List[str]] = None
    error_codes: Optional[List[str]] = None
    affected_components: Optional[List[ComponentType]] = None

class TroubleshootingRecommendation(BaseModel):
    """Troubleshooting recommendation"""
    action: str
    description: str
    priority: str  # low, medium, high, critical
    action_level_required: ActionLevel
    estimated_time: Optional[str] = None
    risk_level: str  # low, medium, high
    steps: Optional[List[str]] = None
    commands: Optional[List[str]] = None

class TroubleshootingResult(BaseModel):
    """Troubleshooting result"""
    issue_description: str
    diagnosis: str
    confidence_score: float
    recommendations: List[TroubleshootingRecommendation]
    root_cause: Optional[str] = None
    related_logs: List[LogEntry]
    action_taken: Optional[str] = None
    resolution_status: Optional[str] = None

class AgentAction(BaseModel):
    """Agent action model"""
    action_type: str
    action_level: ActionLevel
    parameters: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    status: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class ServerSession(BaseModel):
    """Server session information"""
    server_host: str
    session_id: Optional[str] = None
    connected_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    is_active: bool = True
    connection_method: str = "redfish"  # redfish, racadm, ssh
