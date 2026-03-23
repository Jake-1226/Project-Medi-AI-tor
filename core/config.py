"""
Configuration management for Dell Server AI Agent
"""

import os
from typing import Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class SecurityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class AgentConfig(BaseModel):
    """Configuration for the Dell AI Agent"""
    
    # Server connection settings
    default_redfish_port: int = 443
    connection_timeout: int = 30
    max_retries: int = 3
    
    # Security settings
    security_level: SecurityLevel = SecurityLevel.HIGH
    require_https: bool = True
    verify_ssl: bool = False  # Often needed for iDRAC with self-signed certs
    
    # Logging configuration
    log_level: LogLevel = LogLevel.INFO
    log_file: Optional[str] = None
    max_log_size: int = 10 * 1024 * 1024  # 10MB
    
    # Agent behavior
    max_concurrent_operations: int = 5
    operation_timeout: int = 300  # 5 minutes
    auto_save_logs: bool = True
    
    # AI/ML settings
    enable_ai_recommendations: bool = True
    confidence_threshold: float = 0.7
    
    # Data retention
    log_retention_days: int = 30
    cache_retention_hours: int = 24
    
    # Dell-specific settings
    racadm_timeout: int = 60
    redfish_api_version: str = "1.8.0"
    
    # Demo / simulation mode — set to True or DEMO_MODE=true to use
    # simulated Redfish/RACADM clients instead of connecting to a real server
    demo_mode: bool = False
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Create configuration from environment variables"""
        return cls(
            default_redfish_port=int(os.getenv("REDFISH_PORT", "443")),
            connection_timeout=int(os.getenv("CONNECTION_TIMEOUT", "30")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            security_level=SecurityLevel(os.getenv("SECURITY_LEVEL", "medium")),
            require_https=os.getenv("REQUIRE_HTTPS", "true").lower() == "true",
            verify_ssl=os.getenv("VERIFY_SSL", "false").lower() == "true",
            log_level=LogLevel(os.getenv("LOG_LEVEL", "INFO")),
            log_file=os.getenv("LOG_FILE"),
            max_concurrent_operations=int(os.getenv("MAX_CONCURRENT_OPERATIONS", "5")),
            operation_timeout=int(os.getenv("OPERATION_TIMEOUT", "300")),
            auto_save_logs=os.getenv("AUTO_SAVE_LOGS", "true").lower() == "true",
            enable_ai_recommendations=os.getenv("ENABLE_AI_RECOMMENDATIONS", "true").lower() == "true",
            confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.7")),
            log_retention_days=int(os.getenv("LOG_RETENTION_DAYS", "30")),
            cache_retention_hours=int(os.getenv("CACHE_RETENTION_HOURS", "24")),
            racadm_timeout=int(os.getenv("RACADM_TIMEOUT", "60")),
            redfish_api_version=os.getenv("REDFISH_API_VERSION", "1.8.0"),
            demo_mode=os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return self.model_dump()
    
    def is_action_allowed(self, action_level, security_level: Optional[SecurityLevel] = None) -> bool:
        """Check if an action is allowed based on security level"""
        level = security_level or self.security_level
        
        # Normalize action_level to string for comparison
        al = action_level.value if hasattr(action_level, 'value') else str(action_level)
        
        # Define action permissions by security level
        permissions = {
            SecurityLevel.LOW: ["read_only"],
            SecurityLevel.MEDIUM: ["read_only", "diagnostic"],
            SecurityLevel.HIGH: ["read_only", "diagnostic", "full_control"]
        }
        
        return al in permissions.get(level, [])
